from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ArtifactInventoryResponse,
    ProposalEvidenceRoomItem,
    ProposalEvidenceRoomManifestPackResponse,
    ProposalEvidenceRoomManifestResponse,
    ProposalReleaseRoomResponse,
)


class ProposalEvidenceRoomService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def manifest(
        self,
        trace_id: str,
        release_room: ProposalReleaseRoomResponse,
        artifact_inventory: ArtifactInventoryResponse,
    ) -> ProposalEvidenceRoomManifestResponse:
        items = self._manifest_items(artifact_inventory)
        missing_required = [item for item in items if item.required_for_submission and item.status != "present"]
        integrity_controls = self._integrity_controls(release_room, artifact_inventory, items)
        status = self._status(release_room, missing_required)
        return ProposalEvidenceRoomManifestResponse(
            title="Buyer Proposal Evidence Room Manifest",
            manifest_id=f"proposal-evidence-room-{self._slug(trace_id)}",
            status=status,
            generated_at=datetime.now(UTC).isoformat(),
            summary=self._summary(release_room, artifact_inventory, items, missing_required),
            release_snapshot=self._release_snapshot(release_room),
            manifest_items=items,
            approval_manifest=self._approval_manifest(release_room),
            integrity_controls=integrity_controls,
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        manifest: ProposalEvidenceRoomManifestResponse,
        write_artifact: bool = True,
    ) -> ProposalEvidenceRoomManifestPackResponse:
        pack = self._pack_payload(trace_id, manifest)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "proposal_evidence_room"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_evidence_room_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_evidence_room_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["proposal_evidence_room_markdown"] = artifact_path
            pack["artifact_paths"]["proposal_evidence_room_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalEvidenceRoomManifestPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            manifest=manifest,
            trace_id=trace_id,
        )

    def _manifest_items(self, artifact_inventory: ArtifactInventoryResponse) -> list[ProposalEvidenceRoomItem]:
        inventory_by_key = {item.key: item for item in artifact_inventory.directories}
        items: list[ProposalEvidenceRoomItem] = []
        for spec in self._required_artifact_specs():
            inventory_item = inventory_by_key.get(spec["artifact_root"])
            latest = inventory_item.latest_files[0] if inventory_item and inventory_item.latest_files else None
            path = Path(latest.path) if latest else None
            sha256 = self._sha256(path) if path and path.exists() else None
            status = "present" if latest and sha256 else "missing"
            missing_reason = None if status == "present" else f"Generate with {spec['producer_endpoint']}."
            items.append(
                ProposalEvidenceRoomItem(
                    item_id=f"evidence-room:{spec['artifact_root']}",
                    artifact_root=spec["artifact_root"],
                    producer_endpoint=spec["producer_endpoint"],
                    reviewer_purpose=spec["reviewer_purpose"],
                    status=status,
                    latest_file_path=latest.path if latest else None,
                    file_name=latest.name if latest else None,
                    sha256=sha256,
                    size_bytes=latest.size_bytes if latest else None,
                    last_modified=latest.last_modified if latest else None,
                    required_for_submission=spec["required_for_submission"],
                    source_endpoints=spec["source_endpoints"],
                    missing_reason=missing_reason,
                )
            )
        return items

    def _required_artifact_specs(self) -> list[dict[str, Any]]:
        return [
            self._artifact_spec(
                "buyer_intelligence",
                "POST /proposal/buyer-intelligence-pack",
                "Durable buyer workflow, HITL queue, governance gates, provider routes, and replay state.",
                ["/proposal/buyer-intelligence", "/proposal/buyer-intelligence-replay"],
            ),
            self._artifact_spec(
                "buyer_contracts",
                "POST /proposal/buyer-contracts-pack",
                "Typed structured-output contracts for sales, presales, compliance, procurement, and proposal roles.",
                ["/proposal/buyer-contracts"],
            ),
            self._artifact_spec(
                "agent_council",
                "POST /proposal/agent-council-pack",
                "Governed multi-agent handoffs, tool access, shared state, and token budget estimates.",
                ["/proposal/agent-council"],
            ),
            self._artifact_spec(
                "decision_provenance",
                "POST /proposal/decision-provenance-pack",
                "Decision graph linking checkpoints, provider policy, evidence gates, and approval controls.",
                ["/proposal/decision-provenance"],
            ),
            self._artifact_spec(
                "submission_certifications",
                "POST /proposal/submission-certification-pack",
                "Final certification gates, reviewer queue, source artifacts, and eval assertions.",
                ["/proposal/submission-certification"],
            ),
            self._artifact_spec(
                "proposal_assurance",
                "POST /proposal/assurance-bundle-pack",
                (
                    "Checksummed control manifest across workflow, replay, contracts, council, provenance, "
                    "and provider posture."
                ),
                ["/proposal/assurance-bundle"],
            ),
            self._artifact_spec(
                "proposal_review_gates",
                "POST /proposal/review-gate-pack",
                "Role-specific release criteria and task delegations for sales, presales, compliance, and procurement.",
                ["/proposal/review-gate"],
            ),
            self._artifact_spec(
                "proposal_release_room",
                "POST /proposal/release-room-pack",
                "Release decision board, HITL queue, durable checkpoints, provider route, and trace coverage.",
                ["/proposal/release-room"],
            ),
            self._artifact_spec(
                "proposal_observability",
                "POST /ops/proposal-observability-pack",
                (
                    "Trace analysis, retrieval diagnostics, experiment comparison, provider posture, "
                    "and governance findings."
                ),
                ["/ops/proposal-observability"],
            ),
            self._artifact_spec(
                "trace_exports",
                "POST /ops/trace-export-pack",
                "JSONL-ready trace export with retrieval diagnostics, eval dataset manifest, and HITL signals.",
                ["/ops/trace-export"],
                required_for_submission=False,
            ),
            self._artifact_spec(
                "verification_evidence",
                "POST /ops/verification-evidence-pack",
                (
                    "Acceptance evidence ledger for pytest, ruff, evals, dashboard smoke, demo, release gate, "
                    "and final audit."
                ),
                ["/ops/verification-evidence"],
            ),
        ]

    def _artifact_spec(
        self,
        artifact_root: str,
        producer_endpoint: str,
        reviewer_purpose: str,
        source_endpoints: list[str],
        required_for_submission: bool = True,
    ) -> dict[str, Any]:
        return {
            "artifact_root": artifact_root,
            "producer_endpoint": producer_endpoint,
            "reviewer_purpose": reviewer_purpose,
            "source_endpoints": source_endpoints,
            "required_for_submission": required_for_submission,
        }

    def _status(
        self,
        release_room: ProposalReleaseRoomResponse,
        missing_required: list[ProposalEvidenceRoomItem],
    ) -> str:
        if release_room.status == "blocked_by_release_controls":
            return "blocked_by_release_controls"
        if missing_required:
            return "requires_artifact_regeneration"
        if release_room.hitl_queue:
            return "requires_human_evidence_review"
        return "ready_for_buyer_evidence_review"

    def _summary(
        self,
        release_room: ProposalReleaseRoomResponse,
        artifact_inventory: ArtifactInventoryResponse,
        items: list[ProposalEvidenceRoomItem],
        missing_required: list[ProposalEvidenceRoomItem],
    ) -> dict[str, Any]:
        present = [item for item in items if item.status == "present"]
        required = [item for item in items if item.required_for_submission]
        hash_count = sum(1 for item in present if item.sha256)
        return {
            "release_room_status": release_room.status,
            "release_readiness_score": release_room.readiness_score,
            "release_decision_count": release_room.summary["decision_count"],
            "hitl_queue_count": len(release_room.hitl_queue),
            "artifact_inventory_directories": artifact_inventory.total_directories,
            "manifest_item_count": len(items),
            "required_item_count": len(required),
            "present_item_count": len(present),
            "missing_required_count": len(missing_required),
            "hash_coverage_ratio": round(hash_count / len(items), 3) if items else 0.0,
            "missing_required_roots": [item.artifact_root for item in missing_required],
            "storage_ignored_status": artifact_inventory.ignored_status,
            "radar_patterns_used": [
                "durable workflows",
                "human-in-the-loop",
                "governance",
                "provider flexibility",
                "trace analysis",
                "shared state",
            ],
        }

    def _release_snapshot(self, release_room: ProposalReleaseRoomResponse) -> dict[str, Any]:
        return {
            "room_id": release_room.room_id,
            "status": release_room.status,
            "release_recommendation": release_room.release_recommendation,
            "readiness_score": release_room.readiness_score,
            "provider_route": release_room.provider_route,
            "durable_checkpoint_count": len(release_room.durable_checkpoints),
            "trace_source_count": len(release_room.trace_coverage),
            "eval_assertion_count": len(release_room.eval_assertions),
        }

    def _approval_manifest(self, release_room: ProposalReleaseRoomResponse) -> dict[str, Any]:
        owners: dict[str, dict[str, Any]] = {}
        for item in release_room.hitl_queue:
            owner = str(item["owner_role"])
            row = owners.setdefault(owner, {"owner_role": owner, "queue_count": 0, "priorities": [], "sources": []})
            row["queue_count"] += 1
            row["priorities"].append(item.get("priority", "medium"))
            row["sources"].append(item.get("source"))
        for decision in release_room.decision_board:
            owner = decision.owner_role
            row = owners.setdefault(owner, {"owner_role": owner, "queue_count": 0, "priorities": [], "sources": []})
            row["sources"].append(decision.source_endpoint)
        return {
            "status": "requires_named_owner_approval" if release_room.hitl_queue else "no_open_approvals",
            "owner_count": len(owners),
            "required_owners": sorted(owners.values(), key=lambda row: row["owner_role"]),
            "approval_policy": [
                "Every non-pass release-room decision needs a named owner approval or risk acceptance.",
                "Every required artifact must have a local SHA-256 hash before buyer-facing submission.",
                "External provider routes remain disabled unless cost, privacy, model-risk, and owner approvals pass.",
            ],
        }

    def _integrity_controls(
        self,
        release_room: ProposalReleaseRoomResponse,
        artifact_inventory: ArtifactInventoryResponse,
        items: list[ProposalEvidenceRoomItem],
    ) -> list[dict[str, Any]]:
        missing_hashes = [item.artifact_root for item in items if item.status == "present" and not item.sha256]
        missing_required = [
            item.artifact_root for item in items if item.required_for_submission and item.status != "present"
        ]
        controls = [
            {
                "control_id": "evidence-room-hash-coverage",
                "status": "pass" if not missing_hashes else "blocked",
                "owner_role": "Proposal Operations",
                "evidence": f"{sum(1 for item in items if item.sha256)} artifacts have SHA-256 hashes.",
                "required_action": "Regenerate missing local artifacts and rerun the manifest.",
                "blocking_items": missing_hashes,
            },
            {
                "control_id": "evidence-room-required-artifacts",
                "status": "pass" if not missing_required else "needs_review",
                "owner_role": "Proposal Manager",
                "evidence": f"{len(missing_required)} required artifact roots are missing.",
                "required_action": "Generate each required pack before customer-facing submission.",
                "blocking_items": missing_required,
            },
            {
                "control_id": "evidence-room-release-state",
                "status": "pass" if release_room.status != "blocked_by_release_controls" else "blocked",
                "owner_role": "Executive Sponsor",
                "evidence": f"Release room status is {release_room.status}.",
                "required_action": "Clear release-room blockers before approving the evidence room.",
                "blocking_items": [] if release_room.status != "blocked_by_release_controls" else ["release_room"],
            },
            {
                "control_id": "evidence-room-storage-policy",
                "status": (
                    "pass" if artifact_inventory.ignored_status == "ignored_by_gitignore_storage_rule" else "warn"
                ),
                "owner_role": "Engineering",
                "evidence": f"Storage ignored status is {artifact_inventory.ignored_status}.",
                "required_action": "Keep generated customer evidence out of git and regenerate locally.",
                "blocking_items": [],
            },
        ]
        return controls

    def _pack_payload(self, trace_id: str, manifest: ProposalEvidenceRoomManifestResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Buyer Proposal Evidence Room Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "manifest": manifest.model_dump(mode="json"),
            "operator_checklist": [
                "Regenerate all missing required artifact roots before buyer-facing submission.",
                "Verify SHA-256 hashes for every present artifact in the manifest.",
                "Resolve or explicitly accept release-room decisions with named human owners.",
                "Attach trace export and verification evidence when reviewers request eval or observability proof.",
                "Keep external providers optional until model-risk, cost, privacy, and procurement controls pass.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        manifest = pack["manifest"]
        summary = manifest["summary"]
        lines = [
            "# Buyer Proposal Evidence Room Pack",
            "",
            "## Manifest Summary",
            "",
            f"- Status: {manifest['status']}",
            f"- Release room status: {summary['release_room_status']}",
            f"- Release readiness score: {summary['release_readiness_score']}",
            f"- Required artifacts: {summary['required_item_count']}",
            f"- Present artifacts: {summary['present_item_count']}",
            f"- Missing required artifacts: {summary['missing_required_count']}",
            f"- Hash coverage ratio: {summary['hash_coverage_ratio']}",
            f"- Storage ignored status: {summary['storage_ignored_status']}",
            "",
            "## Artifact Manifest",
            "",
            "| Artifact root | Status | Required | SHA-256 | Latest file | Producer |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for item in manifest["manifest_items"]:
            short_hash = item["sha256"][:12] if item["sha256"] else "missing"
            lines.append(
                f"| `{self._md(item['artifact_root'])}` | {item['status']} | "
                f"{item['required_for_submission']} | `{short_hash}` | "
                f"{self._md(item['file_name'] or item['missing_reason'] or '')} | "
                f"{self._md(item['producer_endpoint'])} |"
            )
        lines.extend(["", "## Approval Manifest", ""])
        approval = manifest["approval_manifest"]
        lines.append(f"- Status: {approval['status']}")
        lines.append(f"- Required owner count: {approval['owner_count']}")
        if approval["required_owners"]:
            lines.append("")
            lines.append("| Owner | Queue count | Sources |")
            lines.append("| --- | --- | --- |")
            for owner in approval["required_owners"]:
                sources = ", ".join(sorted({str(source) for source in owner["sources"] if source}))
                lines.append(f"| {self._md(owner['owner_role'])} | {owner['queue_count']} | {self._md(sources)} |")
        lines.extend(["", "## Integrity Controls", ""])
        for control in manifest["integrity_controls"]:
            lines.append(
                f"- {control['control_id']} ({control['status']}): "
                f"{self._md(control['evidence'])} {self._md(control['required_action'])}"
            )
        lines.extend(["", "## Operator Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["operator_checklist"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in manifest["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in manifest["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/evidence-room", "purpose": "View artifact evidence manifest."},
            {"method": "POST", "path": "/proposal/evidence-room-pack", "purpose": "Write evidence room pack."},
            {"method": "GET", "path": "/proposal/release-room", "purpose": "Source release decision board."},
            {"method": "GET", "path": "/artifacts/inventory", "purpose": "Source latest local artifact files."},
            {"method": "GET", "path": "/ops/verification-evidence", "purpose": "Source local verification ledger."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/evidence-room" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/evidence-room-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q tests/test_proposal_evidence_room.py",
            "python -m app.demo",
            (
                'rg "proposal/evidence-room|Buyer Proposal Evidence Room|proposal_evidence_room" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\proposal_evidence_room -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The evidence room reads local generated artifacts; it does not upload files to a customer portal.",
            "Hashes prove local file integrity only and are not a replacement for enterprise document control.",
            "Human approvals are manifest rows, not live signatures in legal, GRC, CRM, or procurement systems.",
            "Missing artifacts may be expected on a clean checkout until pack endpoints or python -m app.demo run.",
            "External provider posture remains optional and is summarized from local provider-resilience controls.",
        ]

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
