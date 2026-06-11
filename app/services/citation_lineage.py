from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    CitationLineageAuditResponse,
    CitationLineageItem,
    CitationLineagePackResponse,
)
from app.models.domain import Answer, Citation, DraftResponse
from app.repositories.memory import InMemoryRepository


class CitationLineageService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def audit(
        self,
        trace_id: str,
        answers: list[Answer] | None = None,
        drafts: list[DraftResponse] | None = None,
        export_payloads: list[dict[str, Any]] | None = None,
    ) -> CitationLineageAuditResponse:
        citations = self._collect_citations(answers or [], drafts or [], export_payloads or [])
        lineages = [
            self._lineage_item(citation, source_kind, source_label, index)
            for index, (citation, source_kind, source_label) in enumerate(citations, start=1)
        ]
        claim_flags = self._claim_flags(answers or [], drafts or [], export_payloads or [])
        summary = self._summary(
            lineages,
            claim_flags,
            len(answers or []),
            len(drafts or []),
            len(export_payloads or []),
        )
        return CitationLineageAuditResponse(
            title="Citation Lineage + Integrity Audit",
            status="pass" if summary["blocking_issue_count"] == 0 else "needs_review",
            score=summary["integrity_score"],
            summary=summary,
            lineages=lineages,
            missing_citations=[
                item.model_dump(mode="json") for item in lineages if item.integrity_status == "missing_reference"
            ],
            stale_citations=[
                item.model_dump(mode="json") for item in lineages if item.integrity_status == "stale_or_changed"
            ],
            generated_claim_flags=claim_flags,
            owner_followups=self._owner_followups(lineages, claim_flags),
            endpoint_references=self._endpoint_references(lineages),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def lineage_pack(
        self,
        trace_id: str,
        lineage: CitationLineageAuditResponse,
        write_artifact: bool = True,
    ) -> CitationLineagePackResponse:
        pack = self._pack_payload(trace_id, lineage)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "citation_lineage"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"citation_lineage_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"citation_lineage_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["citation_lineage_markdown"] = artifact_path
            pack["artifact_paths"]["citation_lineage_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return CitationLineagePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            lineage=lineage,
            trace_id=trace_id,
        )

    def _collect_citations(
        self,
        answers: list[Answer],
        drafts: list[DraftResponse],
        export_payloads: list[dict[str, Any]],
    ) -> list[tuple[Citation, str, str]]:
        collected: list[tuple[Citation, str, str]] = []
        for index, answer in enumerate(answers, start=1):
            label = answer.question[:90] or f"answer_{index}"
            collected.extend((citation, "answer", label) for citation in answer.citations)
        for index, draft in enumerate(drafts, start=1):
            label = f"draft_{index}:{draft.trace_id}"
            collected.extend((citation, "draft", label) for citation in draft.citations)
        for index, package in enumerate(export_payloads, start=1):
            label = f"export_{index}:{package.get('trace_ids', {}).get('draft', 'local')}"
            for raw in package.get("citations", []):
                try:
                    citation = Citation.model_validate(raw)
                except Exception:
                    continue
                collected.append((citation, "export", label))
        return collected

    def _lineage_item(
        self,
        citation: Citation,
        source_kind: str,
        source_label: str,
        index: int,
    ) -> CitationLineageItem:
        document = self.repo.documents.get(citation.document_id)
        chunk = self.repo.chunks.get(citation.chunk_id)
        filename_match = bool(document and document.filename == citation.filename)
        snippet_match = bool(chunk and self._snippet_matches(citation.snippet, chunk.text))
        flags: list[str] = []
        if document is None:
            flags.append("Citation document_id is not present in the repository.")
        if chunk is None:
            flags.append("Citation chunk_id is not present in the repository.")
        if document is not None and not filename_match:
            flags.append("Citation filename does not match the stored document filename.")
        if chunk is not None and not snippet_match:
            flags.append("Citation snippet no longer matches the stored chunk text.")
        if citation.score < 0.2:
            flags.append("Citation retrieval score is below reviewer threshold.")

        if document is None or chunk is None:
            status = "missing_reference"
            risk = "critical"
        elif not filename_match or not snippet_match:
            status = "stale_or_changed"
            risk = "high"
        elif citation.score < 0.2:
            status = "needs_review"
            risk = "medium"
        else:
            status = "verified"
            risk = "low"

        owner = self._owner_for(document.document_type if document else "unknown", citation.filename)
        endpoints = self._endpoints_for(document.document_type if document else "unknown", citation.filename)
        return CitationLineageItem(
            citation_id=f"cit_{index:03d}",
            source_kind=source_kind,
            source_label=source_label,
            document_id=citation.document_id,
            chunk_id=citation.chunk_id,
            filename=citation.filename,
            document_exists=document is not None,
            chunk_exists=chunk is not None,
            filename_match=filename_match,
            snippet_match=snippet_match,
            integrity_status=status,
            risk_level=risk,
            risk_flags=flags,
            score=round(citation.score, 4),
            document_type=document.document_type if document else "unknown",
            policy_owner=owner,
            source_path=document.metadata.get("path") if document else None,
            citation_snippet=citation.snippet,
            repository_excerpt=(chunk.text[:360].strip() if chunk else None),
            endpoint_references=endpoints,
        )

    def _snippet_matches(self, snippet: str, text: str) -> bool:
        normalized_snippet = self._normalize(snippet)
        normalized_text = self._normalize(text)
        if not normalized_snippet or not normalized_text:
            return False
        probe = normalized_snippet[:140]
        return probe in normalized_text or normalized_text[:140] in normalized_snippet

    def _claim_flags(
        self,
        answers: list[Answer],
        drafts: list[DraftResponse],
        export_payloads: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        checks = [
            ("fedramp", "FedRAMP claims require explicit certification evidence or exception approval."),
            ("hipaa", "HIPAA claims require explicit compliance evidence or qualified wording."),
            ("99.99", "Availability guarantees require source-specific SLA evidence."),
            ("zero data loss", "Zero-data-loss claims require disaster recovery evidence and owner approval."),
            ("guarantee", "Guarantee language must be tied to an approved contractual source."),
            ("active-active", "Active-active architecture claims need current architecture evidence."),
        ]
        sources: list[tuple[str, str, str, int]] = []
        for answer in answers:
            sources.append(("answer", answer.question, answer.answer_text, len(answer.citations)))
        for draft in drafts:
            for section in draft.sections:
                sources.append(("draft", section.title, section.body, len(draft.citations)))
        for package in export_payloads:
            citation_count = len(package.get("citations", []))
            for section in package.get("drafted_sections", []):
                sources.append(
                    (
                        "export",
                        section.get("title", "export_section"),
                        section.get("body", ""),
                        citation_count,
                    )
                )

        flags: list[dict[str, Any]] = []
        for source_kind, source_label, text, citation_count in sources:
            lowered = text.lower()
            for term, message in checks:
                approval_terms = {"fedramp", "hipaa", "guarantee", "zero data loss"}
                if term in lowered and (citation_count == 0 or term in approval_terms):
                    flags.append(
                        {
                            "source_kind": source_kind,
                            "source_label": source_label,
                            "claim": message,
                            "citation_count": citation_count,
                            "recommended_action": (
                                "Verify cited source lineage or route reviewer approval before reuse."
                            ),
                        }
                    )
        return flags

    def _summary(
        self,
        lineages: list[CitationLineageItem],
        claim_flags: list[dict[str, Any]],
        answer_count: int,
        draft_count: int,
        export_count: int,
    ) -> dict[str, Any]:
        statuses = Counter(item.integrity_status for item in lineages)
        risks = Counter(item.risk_level for item in lineages)
        owners = Counter(item.policy_owner for item in lineages)
        blocking = statuses.get("missing_reference", 0) + statuses.get("stale_or_changed", 0) + len(claim_flags)
        score = max(0, 100 - statuses.get("missing_reference", 0) * 30 - statuses.get("stale_or_changed", 0) * 20)
        score = max(0, score - statuses.get("needs_review", 0) * 10 - len(claim_flags) * 8)
        return {
            "answer_count": answer_count,
            "draft_count": draft_count,
            "export_count": export_count,
            "citation_count": len(lineages),
            "verified_count": statuses.get("verified", 0),
            "missing_reference_count": statuses.get("missing_reference", 0),
            "stale_or_changed_count": statuses.get("stale_or_changed", 0),
            "needs_review_count": statuses.get("needs_review", 0),
            "generated_claim_flag_count": len(claim_flags),
            "blocking_issue_count": blocking,
            "integrity_score": score,
            "status_counts": dict(sorted(statuses.items())),
            "risk_counts": dict(sorted(risks.items())),
            "owner_counts": dict(sorted(owners.items())),
            "endpoint_count": len({endpoint for item in lineages for endpoint in item.endpoint_references}),
        }

    def _owner_followups(
        self,
        lineages: list[CitationLineageItem],
        claim_flags: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "owner": item.policy_owner,
                "filename": item.filename,
                "citation_id": item.citation_id,
                "risk_level": item.risk_level,
                "status": item.integrity_status,
                "action": self._owner_action(item),
                "risk_flags": item.risk_flags,
            }
            for item in lineages
            if item.integrity_status != "verified"
        ]
        if claim_flags:
            rows.append(
                {
                    "owner": "proposal_owner",
                    "filename": "generated_response_text",
                    "citation_id": "generated_claim_flags",
                    "risk_level": "high",
                    "status": "needs_review",
                    "action": "Review generated absolute or regulated claims before customer reuse.",
                    "risk_flags": [flag["claim"] for flag in claim_flags],
                }
            )
        return rows

    def _endpoint_references(self, lineages: list[CitationLineageItem]) -> list[dict[str, Any]]:
        rows = []
        for item in lineages:
            for endpoint in item.endpoint_references:
                rows.append(
                    {
                        "endpoint": endpoint,
                        "citation_id": item.citation_id,
                        "filename": item.filename,
                        "status": item.integrity_status,
                        "risk_level": item.risk_level,
                    }
                )
        return sorted(rows, key=lambda item: (item["endpoint"], item["filename"], item["citation_id"]))

    def _pack_payload(self, trace_id: str, lineage: CitationLineageAuditResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Citation Lineage + Integrity Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": lineage.summary,
            "lineages": [item.model_dump(mode="json") for item in lineage.lineages],
            "missing_citations": lineage.missing_citations,
            "stale_citations": lineage.stale_citations,
            "generated_claim_flags": lineage.generated_claim_flags,
            "owner_followups": lineage.owner_followups,
            "endpoint_references": lineage.endpoint_references,
            "local_proof_commands": lineage.local_proof_commands,
            "limitations": lineage.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Citation Lineage + Integrity Pack",
            "",
            "## Summary",
            "",
            f"- Integrity score: {summary['integrity_score']}",
            f"- Citations audited: {summary['citation_count']}",
            f"- Verified citations: {summary['verified_count']}",
            f"- Missing references: {summary['missing_reference_count']}",
            f"- Stale or changed references: {summary['stale_or_changed_count']}",
            f"- Generated claim flags: {summary['generated_claim_flag_count']}",
            "",
            "## Citation Lineage Matrix",
            "",
            "| ID | Source | File | Owner | Status | Risk | Score | Flags |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- |",
        ]
        for item in pack["lineages"]:
            lines.append(
                f"| {self._md(item['citation_id'])} | {self._md(item['source_kind'])} | "
                f"{self._md(item['filename'])} | {self._md(item['policy_owner'])} | "
                f"{self._md(item['integrity_status'])} | {self._md(item['risk_level'])} | "
                f"{self._md(item['score'])} | {self._md('; '.join(item['risk_flags']) or 'None')} |"
            )
        lines.extend(["", "## Missing Or Stale Citations", ""])
        flagged = pack["missing_citations"] + pack["stale_citations"]
        if flagged:
            for item in flagged:
                lines.append(
                    f"- {item['citation_id']} / {item['filename']}: "
                    f"{item['integrity_status']} ({'; '.join(item['risk_flags'])})"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Generated Claim Flags", ""])
        if pack["generated_claim_flags"]:
            for flag in pack["generated_claim_flags"]:
                lines.append(
                    f"- {flag['source_kind']} / {flag['source_label']}: "
                    f"{flag['claim']} Action: {flag['recommended_action']}"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Owner Follow-ups", ""])
        if pack["owner_followups"]:
            for item in pack["owner_followups"]:
                lines.append(
                    f"- {item['owner']} owns {item['filename']} / {item['citation_id']}: {item['action']}"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Endpoint References", ""])
        for item in pack["endpoint_references"]:
            lines.append(
                f"- {item['endpoint']}: {item['filename']} / {item['citation_id']} "
                f"({item['status']}, {item['risk_level']})"
            )
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Citation Lineage Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _owner_action(self, item: CitationLineageItem) -> str:
        if item.integrity_status == "missing_reference":
            return "Regenerate the answer/draft after re-ingesting the source corpus."
        if item.integrity_status == "stale_or_changed":
            return "Refresh the generated response because cited source text has changed."
        if item.integrity_status == "needs_review":
            return "Reviewer should approve or replace the weak citation before submission."
        return "No follow-up required."

    def _owner_for(self, document_type: str, filename: str) -> str:
        catalog_owner = self._catalog().get(filename, {}).get("policy_owner")
        if catalog_owner:
            return catalog_owner
        return {
            "security": "security",
            "compliance": "legal",
            "privacy": "legal",
            "support": "customer_success",
            "disaster_recovery": "engineering",
            "pricing": "finance",
            "implementation": "solutions",
            "customer_success": "customer_success",
            "product": "product",
            "proposal": "proposal_owner",
            "contract": "legal",
            "rfp": "proposal_owner",
        }.get(document_type, "proposal_owner")

    def _endpoints_for(self, document_type: str, filename: str) -> list[str]:
        by_type = {
            "rfp": ["/rfp/analyze", "/rfp/requirement-matrix"],
            "security": ["/rfp/query", "/rfp/review-answer", "/evidence/citation-lineage"],
            "compliance": ["/compliance/evidence-matrix", "/evidence/citation-lineage"],
            "privacy": ["/privacy/retention-guardrails", "/evidence/citation-lineage"],
            "support": ["/procurement/question-risk", "/evidence/citation-lineage"],
            "disaster_recovery": ["/evidence/conflicts", "/evidence/citation-lineage"],
            "pricing": ["/rfp/pricing-risk-memo", "/evidence/citation-lineage"],
            "implementation": ["/rfp/timeline-plan", "/evidence/citation-lineage"],
            "customer_success": ["/rfp/leadership-brief", "/evidence/citation-lineage"],
            "product": ["/rfp/draft-response", "/evidence/citation-lineage"],
            "proposal": ["/rfp/response-memory/search", "/evidence/citation-lineage"],
            "contract": ["/rfp/contract-risk", "/evidence/citation-lineage"],
        }
        endpoints = by_type.get(document_type, ["/rfp/query", "/evidence/citation-lineage"])
        catalog_endpoints = self._catalog().get(filename, {}).get("endpoint_references", [])
        return sorted(set(endpoints + list(catalog_endpoints)))

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/evidence/citation-lineage" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/evidence/citation-lineage-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'rg "citation-lineage|Citation Lineage|citation_lineage|stale citation|integrity audit" '
                "app dashboard docs README.md tests sample_data Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\citation_lineage -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Citation lineage is repository-local and deterministic; it does not query external document systems.",
            "Snippet matching checks stored chunk text, not immutable source-control history.",
            (
                "Generated-claim flags are conservative text checks and do not replace legal, security, "
                "or compliance review."
            ),
            (
                "Freshness, expiry, and source-precedence risks are handled by adjacent Evidence Freshness "
                "and Conflict packs."
            ),
        ]

    def _catalog(self) -> dict[str, dict[str, Any]]:
        return {
            "security_policy.md": {"policy_owner": "security"},
            "compliance_policy.md": {"policy_owner": "legal"},
            "dpa_privacy_policy.md": {"policy_owner": "legal"},
            "sla_support_policy.md": {"policy_owner": "customer_success"},
            "ai_governance_security.md": {"policy_owner": "product"},
            "disaster_recovery_plan.md": {"policy_owner": "engineering"},
            "customer_contract_terms.md": {"policy_owner": "legal"},
            "pricing_notes.md": {"policy_owner": "finance"},
            "implementation_guide.md": {"policy_owner": "solutions"},
            "product_overview.md": {"policy_owner": "product"},
            "prior_proposal.md": {"policy_owner": "proposal_owner"},
            "customer_success_onboarding.md": {"policy_owner": "customer_success"},
            "acme_enterprise_rfp.md": {"policy_owner": "proposal_owner"},
        }

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip().rstrip(".")

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
