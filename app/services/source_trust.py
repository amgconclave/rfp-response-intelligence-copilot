from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    CitationLineageAuditResponse,
    EvidenceConflictResponse,
    EvidenceFreshnessResponse,
    SourceTrustGateResponse,
    SourceTrustItem,
    SourceTrustPackResponse,
)


class SourceTrustGateService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def trust_gate(
        self,
        trace_id: str,
        freshness: EvidenceFreshnessResponse,
        conflicts: EvidenceConflictResponse,
        lineage: CitationLineageAuditResponse,
    ) -> SourceTrustGateResponse:
        conflict_index = self._conflict_index(conflicts)
        lineage_index = self._lineage_index(lineage)
        sources = [
            self._source_item(source, conflict_index[source.filename], lineage_index[source.filename])
            for source in freshness.sources
        ]
        summary = self._summary(sources, conflicts, lineage)
        return SourceTrustGateResponse(
            title="Source Trust Gate",
            status=self._status(summary),
            generated_at=datetime.now(UTC).isoformat(),
            sources=sorted(sources, key=lambda item: (self._decision_rank(item.trust_decision), item.filename)),
            summary=summary,
            reviewer_queue=self._reviewer_queue(sources),
            retrieval_policy_updates=self._retrieval_policy_updates(sources),
            endpoint_references=self._endpoint_references(sources),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def trust_pack(
        self,
        trace_id: str,
        source_trust: SourceTrustGateResponse,
        write_artifact: bool = True,
    ) -> SourceTrustPackResponse:
        pack = self._pack_payload(trace_id, source_trust)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "source_trust"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"source_trust_gate_{safe_trace_id}.md"
            json_path = pack_dir / f"source_trust_gate_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["source_trust_markdown"] = artifact_path
            pack["artifact_paths"]["source_trust_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return SourceTrustPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            source_trust=source_trust,
            trace_id=trace_id,
        )

    def _source_item(
        self,
        source: Any,
        conflicts: list[dict[str, Any]],
        lineages: list[dict[str, Any]],
    ) -> SourceTrustItem:
        blocking_conflicts = [item for item in conflicts if item["status"] == "blocked"]
        high_conflicts = [item for item in conflicts if item["severity"] in {"high", "critical"}]
        lineage_issues = [
            item for item in lineages if item["integrity_status"] in {"missing_reference", "stale_or_changed"}
        ]
        generated_claim_flags = [item for item in lineages if item["integrity_status"] == "generated_claim_flag"]
        risk = 100 - int(source.freshness_score)
        risk += len(blocking_conflicts) * 35
        risk += (len(high_conflicts) - len(blocking_conflicts)) * 18
        risk += (len(conflicts) - len(high_conflicts)) * 8
        risk += len(lineage_issues) * 25
        risk += len(generated_claim_flags) * 12
        if source.expiry_status == "expired":
            risk += 18
        if source.risk_level in {"high", "critical"}:
            risk += 10
        trust_score = max(0, min(100, 100 - risk))
        decision = self._decision(source, trust_score, blocking_conflicts, lineage_issues)
        guardrails = self._guardrails(source, conflicts, lineages, decision)
        owners = sorted(
            {
                source.policy_owner,
                *[str(item["reviewer_owner"]) for item in conflicts if item.get("reviewer_owner")],
                *[str(item["policy_owner"]) for item in lineages if item.get("policy_owner")],
            }
        )
        return SourceTrustItem(
            source_id=f"source-trust-{self._slug(source.filename)}",
            filename=source.filename,
            document_type=source.document_type,
            policy_owner=source.policy_owner,
            trust_score=trust_score,
            trust_decision=decision,
            approval_required=decision != "approved_to_reuse",
            freshness_score=source.freshness_score,
            freshness_risk_level=source.risk_level,
            expiry_status=source.expiry_status,
            citation_use_count=source.citation_use_count,
            conflict_count=len(conflicts),
            blocking_conflict_count=len(blocking_conflicts),
            lineage_issue_count=len(lineage_issues) + len(generated_claim_flags),
            retrieval_policy=self._retrieval_policy(decision, trust_score, source.citation_use_count),
            guardrails=guardrails,
            reviewer_owners=owners,
            endpoint_references=sorted(set(source.endpoint_references)),
            source_path=source.source_path,
        )

    def _decision(
        self,
        source: Any,
        trust_score: int,
        blocking_conflicts: list[dict[str, Any]],
        lineage_issues: list[dict[str, Any]],
    ) -> str:
        if blocking_conflicts or source.expiry_status == "expired" or source.risk_level == "critical":
            return "blocked_until_owner_review"
        if lineage_issues or trust_score < 55:
            return "restricted"
        if trust_score < 75 or source.risk_level == "high":
            return "needs_review"
        return "approved_to_reuse"

    def _retrieval_policy(self, decision: str, trust_score: int, citation_use_count: int) -> str:
        if decision == "blocked_until_owner_review":
            return "block"
        if decision == "restricted":
            return "suppress"
        if decision == "needs_review":
            return "review_before_use"
        if trust_score >= 88 and citation_use_count >= 2:
            return "boost"
        return "allow"

    def _guardrails(
        self,
        source: Any,
        conflicts: list[dict[str, Any]],
        lineages: list[dict[str, Any]],
        decision: str,
    ) -> list[str]:
        guardrails = list(source.risk_drivers)
        guardrails.extend(source.unsupported_claim_flags)
        guardrails.extend(
            f"{item['conflict_id']}: {item['resolution_guidance']}"
            for item in conflicts
            if item.get("status") in {"blocked", "needs_review"}
        )
        guardrails.extend(
            f"Citation lineage issue: {item['integrity_status']} from {item['source_label']}"
            for item in lineages
            if item.get("integrity_status") != "verified"
        )
        if decision == "approved_to_reuse":
            guardrails.append("Reuse allowed with current citations and standard proposal review.")
        return list(dict.fromkeys(guardrails))[:8]

    def _summary(
        self,
        sources: list[SourceTrustItem],
        conflicts: EvidenceConflictResponse,
        lineage: CitationLineageAuditResponse,
    ) -> dict[str, Any]:
        decisions = Counter(source.trust_decision for source in sources)
        policies = Counter(source.retrieval_policy for source in sources)
        owners = Counter(owner for source in sources for owner in source.reviewer_owners if source.approval_required)
        avg_score = round(sum(source.trust_score for source in sources) / len(sources), 2) if sources else 0
        return {
            "source_count": len(sources),
            "average_trust_score": avg_score,
            "approved_count": decisions.get("approved_to_reuse", 0),
            "needs_review_count": decisions.get("needs_review", 0),
            "restricted_count": decisions.get("restricted", 0),
            "blocked_count": decisions.get("blocked_until_owner_review", 0),
            "approval_required_count": sum(1 for source in sources if source.approval_required),
            "decision_counts": dict(sorted(decisions.items())),
            "retrieval_policy_counts": dict(sorted(policies.items())),
            "owner_review_counts": dict(sorted(owners.items())),
            "freshness_source_count": len(sources),
            "conflict_count": conflicts.summary["conflict_count"],
            "blocking_conflict_count": conflicts.summary["blocking_conflict_count"],
            "lineage_blocking_issue_count": lineage.summary["blocking_issue_count"],
            "lineage_integrity_score": lineage.score,
        }

    def _status(self, summary: dict[str, Any]) -> str:
        if summary["blocked_count"] > 0:
            return "blocked"
        if summary["approval_required_count"] > 0:
            return "needs_review"
        return "pass"

    def _reviewer_queue(self, sources: list[SourceTrustItem]) -> list[dict[str, Any]]:
        rows = []
        for source in sources:
            if not source.approval_required:
                continue
            rows.append(
                {
                    "source_id": source.source_id,
                    "filename": source.filename,
                    "decision": source.trust_decision,
                    "trust_score": source.trust_score,
                    "owners": source.reviewer_owners,
                    "action": self._reviewer_action(source),
                    "guardrails": source.guardrails,
                }
            )
        return sorted(rows, key=lambda item: (self._decision_rank(item["decision"]), item["filename"]))

    def _reviewer_action(self, source: SourceTrustItem) -> str:
        if source.trust_decision == "blocked_until_owner_review":
            return "Resolve blocking expiry, source conflict, or source-owner approval before retrieval reuse."
        if source.trust_decision == "restricted":
            return "Suppress from default retrieval and use only with explicit reviewer-approved wording."
        return "Require owner approval before this source can be boosted or used in final customer wording."

    def _retrieval_policy_updates(self, sources: list[SourceTrustItem]) -> list[dict[str, Any]]:
        rows = []
        for source in sources:
            rows.append(
                {
                    "source_id": source.source_id,
                    "filename": source.filename,
                    "policy": source.retrieval_policy,
                    "trust_score": source.trust_score,
                    "decision": source.trust_decision,
                    "expected_behavior": self._policy_behavior(source),
                    "endpoint_references": source.endpoint_references,
                }
            )
        return sorted(rows, key=lambda item: (item["policy"], item["filename"]))

    def _policy_behavior(self, source: SourceTrustItem) -> str:
        return {
            "boost": "Prefer this source for matching RFP requirements because it is current and frequently cited.",
            "allow": "Allow normal retrieval and citation reuse.",
            "review_before_use": "Retrieve normally, but require owner approval before final draft export.",
            "suppress": "Do not retrieve by default; use only when a reviewer explicitly selects this source.",
            "block": "Block customer-facing citation reuse until source owner clears the gate.",
        }[source.retrieval_policy]

    def _endpoint_references(self, sources: list[SourceTrustItem]) -> list[dict[str, Any]]:
        rows = []
        for source in sources:
            for endpoint in source.endpoint_references:
                rows.append(
                    {
                        "endpoint": endpoint,
                        "filename": source.filename,
                        "trust_decision": source.trust_decision,
                        "retrieval_policy": source.retrieval_policy,
                        "trust_score": source.trust_score,
                    }
                )
        return sorted(rows, key=lambda item: (item["endpoint"], item["filename"]))

    def _pack_payload(self, trace_id: str, source_trust: SourceTrustGateResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Source Trust Gate Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "status": source_trust.status,
            "summary": source_trust.summary,
            "sources": [source.model_dump(mode="json") for source in source_trust.sources],
            "reviewer_queue": source_trust.reviewer_queue,
            "retrieval_policy_updates": source_trust.retrieval_policy_updates,
            "endpoint_references": source_trust.endpoint_references,
            "local_proof_commands": source_trust.local_proof_commands,
            "limitations": source_trust.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Source Trust Gate Pack",
            "",
            "## Summary",
            "",
            f"- Status: {pack['status']}",
            f"- Sources scored: {summary['source_count']}",
            f"- Average trust score: {summary['average_trust_score']}",
            f"- Approved sources: {summary['approved_count']}",
            f"- Approval required: {summary['approval_required_count']}",
            f"- Blocked sources: {summary['blocked_count']}",
            f"- Conflict count: {summary['conflict_count']}",
            f"- Citation lineage blocking issues: {summary['lineage_blocking_issue_count']}",
            "",
            "## Source Trust Matrix",
            "",
            "| Source | Owner | Score | Decision | Retrieval | Freshness | Conflicts | Lineage Issues | Guardrails |",
            "| --- | --- | ---: | --- | --- | --- | ---: | ---: | --- |",
        ]
        for source in pack["sources"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(source["filename"]),
                        self._md(", ".join(source["reviewer_owners"])),
                        self._md(source["trust_score"]),
                        self._md(source["trust_decision"]),
                        self._md(source["retrieval_policy"]),
                        self._md(f"{source['freshness_score']}/{source['expiry_status']}"),
                        self._md(source["conflict_count"]),
                        self._md(source["lineage_issue_count"]),
                        self._md("; ".join(source["guardrails"]) or "None"),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Reviewer Queue", ""])
        if pack["reviewer_queue"]:
            for item in pack["reviewer_queue"]:
                lines.append(
                    f"- {item['filename']} / {item['decision']} / score {item['trust_score']}: {item['action']}"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Retrieval Policy Updates", ""])
        for item in pack["retrieval_policy_updates"]:
            lines.append(
                f"- {item['policy']} | {item['filename']} | score {item['trust_score']}: "
                f"{item['expected_behavior']}"
            )
        lines.extend(["", "## Endpoint References", ""])
        for item in pack["endpoint_references"][:40]:
            lines.append(
                f"- {item['endpoint']}: {item['filename']} "
                f"({item['retrieval_policy']}, score {item['trust_score']})"
            )
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Source Trust Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _conflict_index(self, conflicts: EvidenceConflictResponse) -> defaultdict[str, list[dict[str, Any]]]:
        index: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for conflict in conflicts.conflicts:
            row = {
                "conflict_id": conflict.conflict_id,
                "severity": conflict.severity,
                "status": conflict.status,
                "reviewer_owner": conflict.reviewer_owner,
                "resolution_guidance": conflict.resolution_guidance,
            }
            for citation in conflict.citations:
                index[citation.filename].append(row)
        return index

    def _lineage_index(self, lineage: CitationLineageAuditResponse) -> defaultdict[str, list[dict[str, Any]]]:
        index: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in lineage.lineages:
            index[item.filename].append(
                {
                    "integrity_status": item.integrity_status,
                    "source_label": item.source_label,
                    "policy_owner": item.policy_owner,
                }
            )
        for flag in lineage.generated_claim_flags:
            index["generated_response_text"].append(
                {
                    "integrity_status": "generated_claim_flag",
                    "source_label": flag["source_label"],
                    "policy_owner": "proposal_owner",
                }
            )
        return index

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/evidence/source-trust" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/evidence/source-trust-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'rg "source-trust|Source Trust|source_trust|storage/source_trust" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\source_trust -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Source trust uses deterministic local scoring over sample corpus signals.",
            "The gate recommends retrieval policy changes but does not mutate a live vector index.",
            "Freshness and expiry depend on local fixture metadata and runtime date.",
            "Reviewer approvals, GRC records, CRM outcome data, and production policy repositories are not connected.",
        ]

    def _decision_rank(self, decision: str) -> int:
        return {
            "blocked_until_owner_review": 0,
            "restricted": 1,
            "needs_review": 2,
            "approved_to_reuse": 3,
        }.get(decision, 9)

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "source"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
