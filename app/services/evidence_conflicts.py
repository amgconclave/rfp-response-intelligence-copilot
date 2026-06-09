from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    EvidenceConflictClaim,
    EvidenceConflictItem,
    EvidenceConflictPackResponse,
    EvidenceConflictResponse,
)
from app.models.domain import Chunk, Citation, Document
from app.repositories.memory import InMemoryRepository


class EvidenceConflictService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def conflict_report(self, trace_id: str) -> EvidenceConflictResponse:
        claims = self._claims()
        conflicts = self._conflicts(claims)
        return EvidenceConflictResponse(
            title="Evidence Conflict Resolver",
            conflicts=conflicts,
            summary=self._summary(claims, conflicts),
            reviewer_queue=self._reviewer_queue(conflicts),
            endpoint_references=self._endpoint_references(conflicts),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def conflict_pack(
        self,
        trace_id: str,
        conflicts: EvidenceConflictResponse,
        write_artifact: bool = True,
    ) -> EvidenceConflictPackResponse:
        pack = self._pack_payload(trace_id, conflicts)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "conflict_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"evidence_conflict_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"evidence_conflict_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["conflict_pack_markdown"] = artifact_path
            pack["artifact_paths"]["conflict_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return EvidenceConflictPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            conflicts=conflicts,
            trace_id=trace_id,
        )

    def _claims(self) -> list[EvidenceConflictClaim]:
        claims: list[EvidenceConflictClaim] = []
        for document in sorted(self.repo.documents.values(), key=lambda item: item.filename):
            if document.document_type == "rfp":
                continue
            for chunk in self._chunks(document.id):
                lowered = chunk.text.lower()
                for spec in self._claim_specs():
                    if document.filename not in spec["filenames"]:
                        continue
                    if not any(term in lowered for term in spec["terms"]):
                        continue
                    claims.append(
                        EvidenceConflictClaim(
                            claim_id=f"{spec['claim_type']}:{document.filename}:{chunk.id}",
                            topic=spec["topic"],
                            claim_type=spec["claim_type"],
                            normalized_claim=spec["normalized_claim"],
                            stance=spec["stance"],
                            source_owner=self._owner(document),
                            authority_rank=self._authority_rank(document),
                            citation=self._citation(document, chunk),
                            snippet=self._snippet(chunk.text, spec["terms"]),
                        )
                    )
        return claims

    def _conflicts(self, claims: list[EvidenceConflictClaim]) -> list[EvidenceConflictItem]:
        claims_by_type = {claim.claim_type: claim for claim in claims}
        conflicts: list[EvidenceConflictItem] = []
        for spec in self._conflict_specs():
            available = [claims_by_type[key] for key in spec["claim_types"] if key in claims_by_type]
            if len(available) < spec["min_claims"]:
                continue
            primary = sorted(available, key=lambda item: item.authority_rank)[0]
            others = [claim for claim in available if claim.claim_id != primary.claim_id]
            citations = [primary.citation, *[claim.citation for claim in others]]
            conflicts.append(
                EvidenceConflictItem(
                    conflict_id=spec["conflict_id"],
                    topic=spec["topic"],
                    severity=spec["severity"],
                    status=spec["status"],
                    reviewer_owner=spec["reviewer_owner"],
                    resolution_guidance=spec["resolution_guidance"],
                    cited_resolution=self._cited_resolution(spec, primary, others),
                    primary_claim=primary,
                    conflicting_claims=others,
                    citations=citations,
                    reviewer_actions=self._reviewer_actions(spec, available),
                    endpoint_references=self._conflict_endpoint_refs(spec, available),
                )
            )
        return conflicts

    def _summary(
        self,
        claims: list[EvidenceConflictClaim],
        conflicts: list[EvidenceConflictItem],
    ) -> dict[str, Any]:
        severity_counts = Counter(item.severity for item in conflicts)
        status_counts = Counter(item.status for item in conflicts)
        owner_counts = Counter(item.reviewer_owner for item in conflicts)
        blocking = sum(1 for item in conflicts if item.status == "blocked")
        needs_review = sum(1 for item in conflicts if item.status in {"needs_review", "blocked"})
        return {
            "claim_count": len(claims),
            "conflict_count": len(conflicts),
            "blocking_conflict_count": blocking,
            "needs_review_count": needs_review,
            "high_severity_count": sum(1 for item in conflicts if item.severity in {"high", "critical"}),
            "topics": sorted({item.topic for item in conflicts}),
            "severity_counts": dict(sorted(severity_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "owner_counts": dict(sorted(owner_counts.items())),
            "citation_count": sum(len(item.citations) for item in conflicts),
        }

    def _reviewer_queue(self, conflicts: list[EvidenceConflictItem]) -> list[dict[str, Any]]:
        return [
            {
                "conflict_id": item.conflict_id,
                "owner": item.reviewer_owner,
                "severity": item.severity,
                "status": item.status,
                "topic": item.topic,
                "action": item.resolution_guidance,
                "sources": [citation.filename for citation in item.citations],
            }
            for item in sorted(conflicts, key=lambda row: (self._severity_rank(row.severity), row.conflict_id))
        ]

    def _endpoint_references(self, conflicts: list[EvidenceConflictItem]) -> list[dict[str, Any]]:
        rows = [reference for conflict in conflicts for reference in conflict.endpoint_references]
        return sorted(rows, key=lambda item: (item["endpoint"], item["conflict_id"]))

    def _pack_payload(self, trace_id: str, conflicts: EvidenceConflictResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Evidence Conflict Resolver Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": conflicts.summary,
            "conflicts": [item.model_dump(mode="json") for item in conflicts.conflicts],
            "reviewer_queue": conflicts.reviewer_queue,
            "endpoint_references": conflicts.endpoint_references,
            "local_proof_commands": conflicts.local_proof_commands,
            "limitations": conflicts.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Evidence Conflict Resolver Pack",
            "",
            "## Summary",
            "",
            f"- Claims scanned: {summary['claim_count']}",
            f"- Conflicts found: {summary['conflict_count']}",
            f"- Needs review: {summary['needs_review_count']}",
            f"- Blocking conflicts: {summary['blocking_conflict_count']}",
            f"- High severity conflicts: {summary['high_severity_count']}",
            "",
            "## Conflict Matrix",
            "",
            "| Conflict | Topic | Severity | Status | Owner | Resolution | Sources |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for item in pack["conflicts"]:
            sources = ", ".join(dict.fromkeys(citation["filename"] for citation in item["citations"]))
            lines.append(
                f"| {self._md(item['conflict_id'])} | {self._md(item['topic'])} | "
                f"{self._md(item['severity'])} | {self._md(item['status'])} | "
                f"{self._md(item['reviewer_owner'])} | {self._md(item['resolution_guidance'])} | "
                f"{self._md(sources)} |"
            )
        lines.extend(["", "## Cited Resolutions", ""])
        for item in pack["conflicts"]:
            lines.extend(
                [
                    f"### {item['conflict_id']}",
                    "",
                    item["cited_resolution"],
                    "",
                    "- Primary claim: "
                    + self._md(
                        f"{item['primary_claim']['normalized_claim']} "
                        f"({item['primary_claim']['citation']['filename']})"
                    ),
                ]
            )
            for claim in item["conflicting_claims"]:
                lines.append(
                    "- Related claim: "
                    + self._md(f"{claim['normalized_claim']} ({claim['citation']['filename']})")
                )
        lines.extend(["", "## Reviewer Queue", ""])
        for row in pack["reviewer_queue"]:
            lines.append(
                f"- {row['owner']} / {row['conflict_id']} / {row['severity']}: {row['action']}"
            )
        lines.extend(["", "## Endpoint References", ""])
        for row in pack["endpoint_references"]:
            lines.append(
                f"- {row['endpoint']}: {row['conflict_id']} ({row['why_it_matters']})"
            )
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Conflict Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _claim_specs(self) -> list[dict[str, Any]]:
        return [
            self._claim_spec(
                "implementation_timeline",
                "prior_case_study_30_day_pilot",
                ["prior_proposal.md"],
                ["30-day pilot"],
                "Northstar prior proposal describes a 30-day pilot case study.",
                "case_study",
            ),
            self._claim_spec(
                "implementation_timeline",
                "current_implementation_30_business_days",
                ["implementation_guide.md"],
                ["30 business days"],
                "Current implementation guide plans standard implementation for 30 business days.",
                "current_policy",
            ),
            self._claim_spec(
                "subprocessor_residency",
                "local_demo_no_external_subprocessors",
                ["dpa_privacy_policy.md"],
                ["no external subprocessors by default"],
                "Local demo uses no external subprocessors by default.",
                "default_scope",
            ),
            self._claim_spec(
                "subprocessor_residency",
                "optional_cloud_subprocessor_review",
                ["dpa_privacy_policy.md", "pricing_notes.md"],
                ["optional openai", "azure openai", "azure ai search", "qdrant cloud"],
                "Optional cloud providers require customer-approved subprocessor and data-region review.",
                "production_scope",
            ),
            self._claim_spec(
                "commercial_scope",
                "demo_pricing_tiers_only",
                ["pricing_notes.md"],
                ["fake commercial tiers for demonstration only"],
                "Pricing tiers are fake and for demonstration only.",
                "demo_only",
            ),
            self._claim_spec(
                "commercial_scope",
                "enterprise_custom_deployment_scope",
                ["pricing_notes.md"],
                ["enterprise tier", "custom deployment"],
                "Enterprise tier language describes custom multi-business-unit deployment scope.",
                "commercial_scope",
            ),
            self._claim_spec(
                "disaster_recovery_sla",
                "standard_rto_rpo_targets",
                ["disaster_recovery_plan.md"],
                ["24 hour rto", "4 hour rpo"],
                "DR plan lists standard production RTO and RPO targets when services are configured.",
                "target",
            ),
            self._claim_spec(
                "disaster_recovery_sla",
                "no_absolute_uptime_or_zero_loss",
                ["disaster_recovery_plan.md"],
                ["does not guarantee zero data loss", "99.99 percent uptime"],
                "DR plan explicitly disclaims zero-data-loss, active-active, and universal uptime guarantees.",
                "restriction",
            ),
            self._claim_spec(
                "identity_access",
                "local_api_key_auth",
                ["security_policy.md", "implementation_guide.md"],
                ["api key in local demo mode", "api-key protected"],
                "Local/demo access uses API-key protected endpoints.",
                "local_scope",
            ),
            self._claim_spec(
                "identity_access",
                "production_sso_auth",
                ["security_policy.md", "implementation_guide.md"],
                ["saml", "oidc", "production setup should configure"],
                "Production deployments should configure SAML or OIDC SSO.",
                "production_scope",
            ),
        ]

    def _conflict_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "conflict_id": "conflict_implementation_timeline",
                "topic": "implementation_timeline",
                "claim_types": ["prior_case_study_30_day_pilot", "current_implementation_30_business_days"],
                "min_claims": 2,
                "severity": "medium",
                "status": "needs_review",
                "reviewer_owner": "solutions",
                "resolution_guidance": (
                    "Use the implementation guide for current commitments; describe the prior proposal as "
                    "a case study only."
                ),
                "endpoint_paths": ["/rfp/timeline-plan", "/rfp/draft-response", "/rfp/review-answer"],
                "why_it_matters": "Prevents a case-study pilot duration from becoming a current contractual timeline.",
            },
            {
                "conflict_id": "conflict_subprocessor_scope",
                "topic": "subprocessor_residency",
                "claim_types": ["local_demo_no_external_subprocessors", "optional_cloud_subprocessor_review"],
                "min_claims": 2,
                "severity": "high",
                "status": "blocked",
                "reviewer_owner": "legal",
                "resolution_guidance": (
                    "Qualify no-subprocessor claims as local-demo only and attach approved cloud "
                    "subprocessor/residency language for production."
                ),
                "endpoint_paths": [
                    "/compliance/evidence-matrix",
                    "/procurement/question-risk",
                    "/rfp/contract-risk",
                ],
                "why_it_matters": (
                    "Avoids privacy answers that overstate no-subprocessor or data-residency commitments."
                ),
            },
            {
                "conflict_id": "conflict_commercial_scope",
                "topic": "commercial_scope",
                "claim_types": ["demo_pricing_tiers_only", "enterprise_custom_deployment_scope"],
                "min_claims": 2,
                "severity": "high",
                "status": "needs_review",
                "reviewer_owner": "finance",
                "resolution_guidance": (
                    "Do not quote sample tiers as approved pricing; route enterprise scope, usage costs, "
                    "discounts, and payment terms to finance."
                ),
                "endpoint_paths": ["/rfp/win-strategy", "/rfp/pricing-risk-memo", "/bid/scenario-analysis"],
                "why_it_matters": "Keeps fake local pricing fixtures out of customer-facing commercial responses.",
            },
            {
                "conflict_id": "conflict_disaster_recovery_sla",
                "topic": "disaster_recovery_sla",
                "claim_types": ["standard_rto_rpo_targets", "no_absolute_uptime_or_zero_loss"],
                "min_claims": 2,
                "severity": "high",
                "status": "needs_review",
                "reviewer_owner": "engineering",
                "resolution_guidance": (
                    "State RTO/RPO as targets subject to configured hosting and order-form approval; "
                    "do not promise zero data loss, active-active failover, or universal uptime."
                ),
                "endpoint_paths": ["/compliance/evidence-matrix", "/procurement/question-risk", "/rfp/review-answer"],
                "why_it_matters": "Prevents DR targets from being rewritten as absolute SLA commitments.",
            },
            {
                "conflict_id": "conflict_identity_access_scope",
                "topic": "identity_access",
                "claim_types": ["local_api_key_auth", "production_sso_auth"],
                "min_claims": 2,
                "severity": "medium",
                "status": "resolved_with_qualifier",
                "reviewer_owner": "security",
                "resolution_guidance": (
                    "Separate local demo API-key auth from production SSO commitments in every security answer."
                ),
                "endpoint_paths": ["/rfp/query", "/procurement/question-risk", "/runtime/demo-readiness"],
                "why_it_matters": "Keeps local portfolio runtime details from weakening enterprise SSO positioning.",
            },
        ]

    def _claim_spec(
        self,
        topic: str,
        claim_type: str,
        filenames: list[str],
        terms: list[str],
        normalized_claim: str,
        stance: str,
    ) -> dict[str, Any]:
        return {
            "topic": topic,
            "claim_type": claim_type,
            "filenames": filenames,
            "terms": terms,
            "normalized_claim": normalized_claim,
            "stance": stance,
        }

    def _cited_resolution(
        self,
        spec: dict[str, Any],
        primary: EvidenceConflictClaim,
        others: list[EvidenceConflictClaim],
    ) -> str:
        files = ", ".join(dict.fromkeys([primary.citation.filename, *[claim.citation.filename for claim in others]]))
        return f"{spec['resolution_guidance']} Source precedence is based on {files}."

    def _reviewer_actions(
        self,
        spec: dict[str, Any],
        claims: list[EvidenceConflictClaim],
    ) -> list[dict[str, Any]]:
        return [
            {
                "owner": spec["reviewer_owner"],
                "action": spec["resolution_guidance"],
                "evidence_to_check": [claim.citation.filename for claim in claims],
                "approval_status": "required" if spec["status"] in {"blocked", "needs_review"} else "qualified",
            },
            {
                "owner": "proposal_owner",
                "action": "Update draft language so it uses the cited resolution and avoids unsupported absolutes.",
                "evidence_to_check": [claim.claim_type for claim in claims],
                "approval_status": "required",
            },
        ]

    def _conflict_endpoint_refs(
        self,
        spec: dict[str, Any],
        claims: list[EvidenceConflictClaim],
    ) -> list[dict[str, Any]]:
        sources = sorted({claim.citation.filename for claim in claims})
        return [
            {
                "conflict_id": spec["conflict_id"],
                "endpoint": path,
                "why_it_matters": spec["why_it_matters"],
                "source_files": sources,
            }
            for path in spec["endpoint_paths"]
        ]

    def _chunks(self, document_id: str) -> list[Chunk]:
        return [chunk for chunk in self.repo.chunks.values() if chunk.document_id == document_id]

    def _citation(self, document: Document, chunk: Chunk) -> Citation:
        return Citation(
            document_id=document.id,
            chunk_id=chunk.id,
            filename=document.filename,
            page=chunk.metadata.get("page"),
            snippet=chunk.text[:260],
            score=1.0,
        )

    def _snippet(self, text: str, terms: list[str]) -> str:
        lowered = text.lower()
        offsets = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
        start = max(0, min(offsets) - 80) if offsets else 0
        return re.sub(r"\s+", " ", text[start : start + 320]).strip()

    def _owner(self, document: Document) -> str:
        return {
            "security": "security",
            "compliance": "legal",
            "privacy": "legal",
            "pricing": "finance",
            "implementation": "solutions",
            "disaster_recovery": "engineering",
            "proposal": "proposal_owner",
            "product": "product",
            "support": "customer_success",
        }.get(document.document_type, "proposal_owner")

    def _authority_rank(self, document: Document) -> int:
        ranks = {
            "security": 10,
            "privacy": 12,
            "compliance": 14,
            "disaster_recovery": 16,
            "implementation": 18,
            "pricing": 20,
            "product": 25,
            "support": 28,
            "proposal": 45,
        }
        return ranks.get(document.document_type, 50)

    def _severity_rank(self, severity: str) -> int:
        return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 9)

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/evidence/conflicts" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/evidence/conflict-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'rg "evidence/conflicts|evidence/conflict-pack|Evidence Conflict|'
                'conflict_packs|Conflict Resolver" app dashboard docs README.md tests Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\conflict_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Conflict detection is deterministic and rule-based over the local corpus; it is not a legal opinion.",
            "The resolver flags scope, source precedence, and ambiguity conflicts, not every semantic contradiction.",
            "Reviewer owners must approve final customer-facing language before submission.",
            "Live GRC, CRM, contract repository, and pricing system records are not consulted in local mock mode.",
        ]

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
