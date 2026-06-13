from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ProposalEvidenceRoomManifestResponse,
    ProposalReleaseRoomResponse,
    ProposalSubmissionEscrowPackResponse,
    ProposalSubmissionEscrowRecord,
    ProposalSubmissionEscrowResponse,
)


class ProposalSubmissionEscrowService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def escrow(
        self,
        trace_id: str,
        release_room: ProposalReleaseRoomResponse,
        evidence_room: ProposalEvidenceRoomManifestResponse,
    ) -> ProposalSubmissionEscrowResponse:
        records = self._records(evidence_room)
        owner_queue = self._owner_signoff_queue(release_room, records)
        checkpoints = self._checkpoints(trace_id, release_room, evidence_room, records, owner_queue)
        custody_score = self._custody_score(release_room, records, owner_queue)
        eval_assertions = self._eval_assertions(records, owner_queue, checkpoints, release_room)
        status = self._status(release_room, records, owner_queue, eval_assertions)
        return ProposalSubmissionEscrowResponse(
            title="Proposal Submission Escrow Ledger",
            escrow_id=f"proposal-submission-escrow-{self._slug(trace_id)}",
            status=status,
            custody_score=custody_score,
            generated_at=datetime.now(UTC).isoformat(),
            summary=self._summary(release_room, evidence_room, records, owner_queue, checkpoints, custody_score),
            release_snapshot=evidence_room.release_snapshot,
            escrow_records=records,
            owner_signoff_queue=owner_queue,
            custody_checkpoints=checkpoints,
            eval_assertions=eval_assertions,
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        escrow: ProposalSubmissionEscrowResponse,
        write_artifact: bool = True,
    ) -> ProposalSubmissionEscrowPackResponse:
        pack = self._pack_payload(trace_id, escrow)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "proposal_submission_escrow"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_submission_escrow_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_submission_escrow_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["proposal_submission_escrow_markdown"] = artifact_path
            pack["artifact_paths"]["proposal_submission_escrow_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalSubmissionEscrowPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            escrow=escrow,
            trace_id=trace_id,
        )

    def _records(self, evidence_room: ProposalEvidenceRoomManifestResponse) -> list[ProposalSubmissionEscrowRecord]:
        records: list[ProposalSubmissionEscrowRecord] = []
        for index, item in enumerate(evidence_room.manifest_items, start=1):
            has_hash = bool(item.sha256)
            missing_required = item.required_for_submission and item.status != "present"
            custody_state = (
                "hash_locked" if has_hash else "regeneration_required" if missing_required else "optional_hold"
            )
            approval_status = "needs_owner_signoff" if missing_required else "ready_for_signoff"
            records.append(
                ProposalSubmissionEscrowRecord(
                    record_id=f"escrow:{index:02d}:{item.artifact_root}",
                    artifact_root=item.artifact_root,
                    custody_state=custody_state,
                    status=item.status,
                    required_for_submission=item.required_for_submission,
                    owner_role=self._owner_for_artifact(item.artifact_root),
                    approval_status=approval_status,
                    sha256=item.sha256,
                    file_name=item.file_name,
                    latest_file_path=item.latest_file_path,
                    source_endpoint=item.producer_endpoint,
                    checkpoint_key=f"submission-escrow:{index:02d}:{self._slug(item.artifact_root)}",
                    trace_refs=item.source_endpoints,
                    blocking_reasons=self._blocking_reasons(item.status, item.required_for_submission, has_hash),
                )
            )
        return records

    def _owner_signoff_queue(
        self,
        release_room: ProposalReleaseRoomResponse,
        records: list[ProposalSubmissionEscrowRecord],
    ) -> list[dict[str, Any]]:
        queue: list[dict[str, Any]] = []
        seen: set[str] = set()
        for record in records:
            if record.blocking_reasons:
                queue_id = f"artifact:{record.artifact_root}"
                seen.add(queue_id)
                queue.append(
                    {
                        "queue_id": queue_id,
                        "owner_role": record.owner_role,
                        "priority": "high" if record.required_for_submission else "medium",
                        "reason": "; ".join(record.blocking_reasons),
                        "required_action": f"Regenerate {record.artifact_root} and rerun escrow.",
                        "source_endpoint": record.source_endpoint,
                        "checkpoint_key": record.checkpoint_key,
                    }
                )
        for item in release_room.hitl_queue:
            queue_id = f"release:{item.get('source', item.get('item_id', item.get('owner_role', 'review')))}"
            if queue_id in seen:
                continue
            queue.append(
                {
                    "queue_id": queue_id,
                    "owner_role": item.get("owner_role", "Proposal Manager"),
                    "priority": item.get("priority", "medium"),
                    "reason": item.get("reason", "Release-room human review required."),
                    "required_action": item.get("required_action", "Resolve release-room review before lock."),
                    "source_endpoint": item.get("source", "/proposal/release-room"),
                    "checkpoint_key": item.get("checkpoint_key", "submission-escrow:release-room-review"),
                }
            )
        return sorted(queue, key=lambda row: (row["priority"] != "high", row["owner_role"], row["queue_id"]))

    def _checkpoints(
        self,
        trace_id: str,
        release_room: ProposalReleaseRoomResponse,
        evidence_room: ProposalEvidenceRoomManifestResponse,
        records: list[ProposalSubmissionEscrowRecord],
        owner_queue: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        required_missing = [
            record.artifact_root
            for record in records
            if record.required_for_submission and record.status != "present"
        ]
        missing_hash = [
            record.artifact_root for record in records if record.required_for_submission and not record.sha256
        ]
        return [
            {
                "sequence": 1,
                "state": "release_room_loaded",
                "status": "blocked" if release_room.status == "blocked_by_release_controls" else "complete",
                "checkpoint_key": f"{self._slug(trace_id)}:01:release-room",
                "decision": release_room.status,
                "owner_role": "Executive Sponsor",
                "blocking_items": [] if release_room.status != "blocked_by_release_controls" else ["release_room"],
            },
            {
                "sequence": 2,
                "state": "evidence_manifest_loaded",
                "status": "blocked" if required_missing else "complete",
                "checkpoint_key": f"{self._slug(trace_id)}:02:evidence-room",
                "decision": evidence_room.status,
                "owner_role": "Proposal Manager",
                "blocking_items": required_missing,
            },
            {
                "sequence": 3,
                "state": "artifact_hash_lock",
                "status": "blocked" if missing_hash else "complete",
                "checkpoint_key": f"{self._slug(trace_id)}:03:hash-lock",
                "decision": f"{len(records) - len(missing_hash)}/{len(records)} records hash locked or optional",
                "owner_role": "Proposal Operations",
                "blocking_items": missing_hash,
            },
            {
                "sequence": 4,
                "state": "owner_signoff",
                "status": "pending" if owner_queue else "complete",
                "checkpoint_key": f"{self._slug(trace_id)}:04:owner-signoff",
                "decision": f"{len(owner_queue)} owner queue item(s)",
                "owner_role": "Proposal Manager",
                "blocking_items": [row["queue_id"] for row in owner_queue],
            },
            {
                "sequence": 5,
                "state": "escrow_release",
                "status": "complete" if not owner_queue and not required_missing else "blocked",
                "checkpoint_key": f"{self._slug(trace_id)}:05:escrow-release",
                "decision": "release_locked" if not owner_queue and not required_missing else "hold_for_controls",
                "owner_role": "Executive Sponsor",
                "blocking_items": required_missing,
            },
        ]

    def _custody_score(
        self,
        release_room: ProposalReleaseRoomResponse,
        records: list[ProposalSubmissionEscrowRecord],
        owner_queue: list[dict[str, Any]],
    ) -> int:
        missing_required = sum(1 for record in records if record.required_for_submission and record.status != "present")
        missing_hash = sum(1 for record in records if record.required_for_submission and not record.sha256)
        release_penalty = 20 if release_room.status == "blocked_by_release_controls" else 0
        return max(
            0,
            100 - (missing_required * 18) - (missing_hash * 8) - min(25, len(owner_queue) * 3) - release_penalty,
        )

    def _status(
        self,
        release_room: ProposalReleaseRoomResponse,
        records: list[ProposalSubmissionEscrowRecord],
        owner_queue: list[dict[str, Any]],
        eval_assertions: list[dict[str, Any]],
    ) -> str:
        if any(not assertion["passed"] for assertion in eval_assertions):
            return "blocked_by_escrow_controls"
        if release_room.status == "blocked_by_release_controls":
            return "blocked_by_release_controls"
        if any(record.required_for_submission and record.status != "present" for record in records):
            return "requires_artifact_regeneration"
        if owner_queue:
            return "awaiting_owner_signoff"
        return "release_locked"

    def _summary(
        self,
        release_room: ProposalReleaseRoomResponse,
        evidence_room: ProposalEvidenceRoomManifestResponse,
        records: list[ProposalSubmissionEscrowRecord],
        owner_queue: list[dict[str, Any]],
        checkpoints: list[dict[str, Any]],
        custody_score: int,
    ) -> dict[str, Any]:
        hash_locked = sum(1 for record in records if record.custody_state == "hash_locked")
        missing_required = sum(1 for record in records if record.required_for_submission and record.status != "present")
        return {
            "release_room_status": release_room.status,
            "evidence_room_status": evidence_room.status,
            "custody_score": custody_score,
            "record_count": len(records),
            "hash_locked_count": hash_locked,
            "missing_required_count": missing_required,
            "owner_signoff_count": len(owner_queue),
            "checkpoint_count": len(checkpoints),
            "blocked_checkpoint_count": sum(1 for checkpoint in checkpoints if checkpoint["status"] == "blocked"),
            "radar_patterns_used": [
                "typed contracts",
                "structured outputs",
                "dependency injection",
                "state machine workflow",
                "checkpointing",
                "traceable node transitions",
                "eval-friendly design",
            ],
        }

    def _eval_assertions(
        self,
        records: list[ProposalSubmissionEscrowRecord],
        owner_queue: list[dict[str, Any]],
        checkpoints: list[dict[str, Any]],
        release_room: ProposalReleaseRoomResponse,
    ) -> list[dict[str, Any]]:
        missing_required = [
            record for record in records if record.required_for_submission and record.status != "present"
        ]
        routed_missing = {
            row["queue_id"].replace("artifact:", "")
            for row in owner_queue
            if row["queue_id"].startswith("artifact:")
        }
        return [
            {
                "assertion_id": "escrow-records-checkpointed",
                "assertion": "every escrow artifact record has a checkpoint key",
                "observed": sum(1 for record in records if record.checkpoint_key),
                "expected": len(records),
                "passed": all(record.checkpoint_key for record in records),
            },
            {
                "assertion_id": "missing-required-artifacts-routed",
                "assertion": "missing required artifacts are routed to owner signoff or regeneration holds",
                "observed": len(routed_missing),
                "expected": len(missing_required),
                "passed": all(record.artifact_root in routed_missing for record in missing_required),
            },
            {
                "assertion_id": "escrow-checkpoints-ordered",
                "assertion": "custody checkpoints are replayable and ordered",
                "observed": [checkpoint["sequence"] for checkpoint in checkpoints],
                "expected": list(range(1, len(checkpoints) + 1)),
                "passed": [checkpoint["sequence"] for checkpoint in checkpoints]
                == list(range(1, len(checkpoints) + 1)),
            },
            {
                "assertion_id": "provider-optionality-preserved",
                "assertion": "submission escrow does not require external provider calls",
                "observed": release_room.provider_route.get("local_mock_default"),
                "expected": True,
                "passed": release_room.provider_route.get("local_mock_default") is True,
            },
        ]

    def _blocking_reasons(self, status: str, required: bool, has_hash: bool) -> list[str]:
        reasons: list[str] = []
        if required and status != "present":
            reasons.append("required artifact missing")
        if required and not has_hash:
            reasons.append("required artifact has no SHA-256 lock")
        return reasons

    def _owner_for_artifact(self, artifact_root: str) -> str:
        mapping = {
            "buyer_intelligence": "Proposal Manager",
            "buyer_contracts": "Platform Owner",
            "agent_council": "Proposal Manager",
            "decision_provenance": "AI Governance Reviewer",
            "submission_certifications": "Executive Sponsor",
            "proposal_assurance": "AI Governance Reviewer",
            "proposal_review_gates": "Proposal Manager",
            "proposal_release_room": "Executive Sponsor",
            "proposal_observability": "Platform Owner",
            "trace_exports": "Platform Owner",
            "verification_evidence": "QA Lead",
        }
        return mapping.get(artifact_root, "Proposal Operations")

    def _pack_payload(self, trace_id: str, escrow: ProposalSubmissionEscrowResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Submission Escrow Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "escrow": escrow.model_dump(mode="json"),
            "operator_checklist": [
                "Resolve every owner signoff queue row before buyer-facing submission.",
                "Regenerate missing required artifact roots and rerun the escrow ledger.",
                "Verify SHA-256 hashes match the final files attached to the buyer packet.",
                "Keep mock/local provider posture unless model-risk, privacy, and cost approvals pass.",
                "Archive the escrow JSON alongside the final proposal response package.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        escrow = pack["escrow"]
        summary = escrow["summary"]
        lines = [
            "# Proposal Submission Escrow Pack",
            "",
            "## Escrow Summary",
            "",
            f"- Status: {escrow['status']}",
            f"- Custody score: {escrow['custody_score']}",
            f"- Records: {summary['record_count']}",
            f"- Hash locked: {summary['hash_locked_count']}",
            f"- Missing required: {summary['missing_required_count']}",
            f"- Owner signoff queue: {summary['owner_signoff_count']}",
            "",
            "## Escrow Records",
            "",
            "| Artifact root | State | Owner | Approval | Hash | Checkpoint |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for record in escrow["escrow_records"]:
            short_hash = record["sha256"][:12] if record["sha256"] else "missing"
            lines.append(
                f"| `{self._md(record['artifact_root'])}` | {record['custody_state']} | "
                f"{self._md(record['owner_role'])} | {record['approval_status']} | "
                f"`{short_hash}` | `{self._md(record['checkpoint_key'])}` |"
            )
        lines.extend(["", "## Owner Signoff Queue", ""])
        if escrow["owner_signoff_queue"]:
            lines.append("| Owner | Priority | Reason | Action |")
            lines.append("| --- | --- | --- | --- |")
            for row in escrow["owner_signoff_queue"]:
                lines.append(
                    f"| {self._md(row['owner_role'])} | {row['priority']} | "
                    f"{self._md(row['reason'])} | {self._md(row['required_action'])} |"
                )
        else:
            lines.append("No owner signoff rows are open.")
        lines.extend(["", "## Custody Checkpoints", ""])
        for checkpoint in escrow["custody_checkpoints"]:
            lines.append(
                f"- {checkpoint['sequence']}. {checkpoint['state']} ({checkpoint['status']}): "
                f"{self._md(checkpoint['decision'])} `{self._md(checkpoint['checkpoint_key'])}`"
            )
        lines.extend(["", "## Eval Assertions", ""])
        lines.extend(
            f"- {assertion['assertion_id']}: {'pass' if assertion['passed'] else 'fail'}"
            for assertion in escrow["eval_assertions"]
        )
        lines.extend(["", "## Operator Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["operator_checklist"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in escrow["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in escrow["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/submission-escrow", "purpose": "View escrow custody ledger."},
            {"method": "POST", "path": "/proposal/submission-escrow-pack", "purpose": "Write escrow pack."},
            {"method": "GET", "path": "/proposal/release-room", "purpose": "Source release decision board."},
            {"method": "GET", "path": "/proposal/evidence-room", "purpose": "Source artifact manifest."},
            {"method": "GET", "path": "/artifacts/inventory", "purpose": "Source latest generated artifacts."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/submission-escrow" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/submission-escrow-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q tests/test_proposal_submission_escrow.py",
            "python -m app.demo",
            (
                'rg "proposal/submission-escrow|Proposal Submission Escrow|proposal_submission_escrow" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\proposal_submission_escrow "
                "-ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Submission escrow is a local custody ledger; it does not upload or lock files in a customer portal.",
            "Owner signoffs are deterministic workflow records, not legally binding digital signatures.",
            "SHA-256 hashes prove local artifact integrity only for files present when the ledger is generated.",
            "Missing artifacts are expected on a clean checkout until pack endpoints or python -m app.demo run.",
            "External provider posture remains optional and is inherited from local provider-resilience controls.",
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
