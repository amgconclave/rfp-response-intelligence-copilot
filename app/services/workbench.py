import json
import re
from collections import Counter

from app.core.config import Settings
from app.models.api import AnalyzeResponse, CustomerFitResponse, ExportPackageResponse
from app.models.domain import DraftResponse, RequirementMatrixRow, ResponseMemoryMatch, RfpRequirement
from app.repositories.memory import InMemoryRepository
from app.services.metrics import MetricsService
from app.vectorstores.embedding import tokenize


class RfpWorkbenchService:
    def __init__(self, repo: InMemoryRepository, settings: Settings, metrics: MetricsService) -> None:
        self.repo = repo
        self.settings = settings
        self.metrics = metrics

    def create_requirement_matrix(self, analysis: AnalyzeResponse) -> list[RequirementMatrixRow]:
        return [self._row_from_requirement(requirement) for requirement in analysis.requirements]

    def export_package(
        self,
        analysis: AnalyzeResponse,
        draft: DraftResponse,
        trace_id: str,
        write_artifact: bool = True,
        customer_fit: CustomerFitResponse | None = None,
        response_memory_matches: list[ResponseMemoryMatch] | None = None,
    ) -> ExportPackageResponse:
        matrix = self.create_requirement_matrix(analysis)
        package = self._package_payload(analysis, draft, matrix, customer_fit, response_memory_matches or [])
        markdown = self._render_markdown(package)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            export_dir = self.settings.storage_dir / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = export_dir / f"rfp_export_{safe_trace_id}.md"
            json_path = export_dir / f"rfp_export_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(package, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return ExportPackageResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            package=package,
            trace_id=trace_id,
        )

    def _row_from_requirement(self, requirement: RfpRequirement) -> RequirementMatrixRow:
        evidence_refs = self._evidence_refs(requirement)
        missing_evidence = list(requirement.missing_info)
        if not evidence_refs:
            missing_evidence.append("No local approved evidence matched this requirement.")
        owner_role = self._owner_role(requirement.category)
        status = self._status(requirement, evidence_refs, missing_evidence)
        risk_level = self._risk_level(requirement, status, missing_evidence)
        suggested_response = self._suggested_response(requirement, owner_role, evidence_refs)
        return RequirementMatrixRow(
            requirement_id=requirement.id,
            category=requirement.category,
            requirement_text=requirement.text,
            priority=requirement.priority,
            owner_role=owner_role,
            status=status,
            risk_level=risk_level,
            evidence_refs=evidence_refs,
            suggested_response=suggested_response,
            missing_evidence=missing_evidence,
        )

    def _evidence_refs(self, requirement: RfpRequirement) -> list[str]:
        explicit_refs = list(dict.fromkeys(requirement.evidence_refs))
        scored_refs: list[tuple[int, str]] = []
        requirement_tokens = self._signal_tokens(requirement.text)
        category_tokens = set(self._category_keywords(requirement.category))
        for chunk in self.repo.chunks.values():
            document = self.repo.documents.get(chunk.document_id)
            if not document or document.document_type == "rfp":
                continue
            chunk_tokens = self._signal_tokens(chunk.text)
            overlap_score = len(requirement_tokens & chunk_tokens)
            category_score = len(category_tokens & chunk_tokens)
            document_score = 2 if requirement.category in f"{document.document_type} {document.filename}".lower() else 0
            score = overlap_score + category_score + document_score
            if score >= 2:
                filename = chunk.metadata.get("filename", document.filename)
                page = chunk.metadata.get("page")
                ref = f"{filename} p.{page}" if page else filename
                scored_refs.append((score, ref))
        ranked_refs = [
            ref
            for _, ref in sorted(scored_refs, key=lambda item: (-item[0], item[1]))
        ]
        return list(dict.fromkeys(explicit_refs + ranked_refs))[:3]

    def _signal_tokens(self, text: str) -> set[str]:
        stop_words = {
            "and",
            "are",
            "can",
            "for",
            "from",
            "how",
            "must",
            "shall",
            "should",
            "the",
            "this",
            "through",
            "with",
        }
        return {token for token in tokenize(text) if len(token) > 2 and token not in stop_words}

    def _category_keywords(self, category: str) -> list[str]:
        keywords = {
            "security": ["security", "sso", "saml", "oidc", "encryption", "tls", "aes-256", "incident"],
            "compliance": ["soc", "gdpr", "compliance", "audit", "subprocessors", "policy"],
            "pricing": ["pricing", "price", "fees", "tiers", "usage", "cost", "commercial"],
            "implementation": ["implementation", "pilot", "integration", "repositories", "rollout"],
            "functional": ["document", "dashboard", "retrieval", "citations", "responses", "workflow"],
        }
        return keywords.get(category, keywords["functional"])

    def _owner_role(self, category: str) -> str:
        owners = {
            "security": "Security Architect",
            "compliance": "Compliance Lead",
            "pricing": "Commercial Owner",
            "implementation": "Implementation Lead",
            "functional": "Solutions Engineer",
        }
        return owners.get(category, "Solutions Engineer")

    def _status(self, requirement: RfpRequirement, evidence_refs: list[str], missing_evidence: list[str]) -> str:
        if evidence_refs and not missing_evidence:
            return "evidence_found"
        if evidence_refs:
            return "needs_review"
        if requirement.priority == "high" or requirement.category in {"security", "compliance"}:
            return "blocked"
        return "not_started"

    def _risk_level(
        self,
        requirement: RfpRequirement,
        status: str,
        missing_evidence: list[str],
    ) -> str:
        if status == "blocked" or missing_evidence:
            return "high"
        if requirement.priority == "high" or requirement.category in {"security", "compliance", "pricing"}:
            return "medium"
        return "low"

    def _suggested_response(
        self,
        requirement: RfpRequirement,
        owner_role: str,
        evidence_refs: list[str],
    ) -> str:
        if evidence_refs:
            refs = ", ".join(evidence_refs)
            return (
                f"Confirm with {owner_role}, then respond that the solution addresses this "
                f"{requirement.category} requirement using approved evidence from {refs}."
            )
        return (
            f"Do not claim support yet. Assign {owner_role} to locate approved evidence or "
            "document an explicit exception before submission."
        )

    def _package_payload(
        self,
        analysis: AnalyzeResponse,
        draft: DraftResponse,
        matrix: list[RequirementMatrixRow],
        customer_fit: CustomerFitResponse | None = None,
        response_memory_matches: list[ResponseMemoryMatch] | None = None,
    ) -> dict:
        status_counts = Counter(row.status for row in matrix)
        risk_counts = Counter(row.risk_level for row in matrix)
        missing_evidence = sorted(
            {
                item
                for row in matrix
                for item in row.missing_evidence
            }
            | set(analysis.missing_information)
        )
        high_risk_requirements = [row.requirement_text for row in matrix if row.risk_level == "high"]
        risks = sorted(set(analysis.risks + draft.risks + high_risk_requirements))
        package = {
            "executive_summary": {
                "requirement_count": len(matrix),
                "evidence_found": status_counts.get("evidence_found", 0),
                "needs_review": status_counts.get("needs_review", 0),
                "blocked": status_counts.get("blocked", 0),
                "high_risk": risk_counts.get("high", 0),
                "deadline_count": len(analysis.deadlines),
                "draft_section_count": len(draft.sections),
            },
            "deadlines": analysis.deadlines,
            "requirement_matrix": [row.model_dump(mode="json") for row in matrix],
            "drafted_sections": [section.model_dump(mode="json") for section in draft.sections],
            "citations": [citation.model_dump(mode="json") for citation in draft.citations],
            "risks": risks,
            "missing_evidence": missing_evidence,
            "eval_usage_summary": self.metrics.totals(),
            "assumptions": draft.assumptions,
            "revision_notes": draft.revision_notes,
            "trace_ids": {
                "analysis": analysis.trace_id,
                "draft": draft.trace_id,
            },
        }
        if customer_fit is not None:
            package["customer_fit"] = customer_fit.model_dump(mode="json")
        if response_memory_matches:
            package["response_memory_matches"] = [
                match.model_dump(mode="json") for match in response_memory_matches
            ]
        return package

    def _render_markdown(self, package: dict) -> str:
        summary = package["executive_summary"]
        lines = [
            "# RFP Response Export Package",
            "",
            "## Executive Summary",
            "",
            f"- Requirements: {summary['requirement_count']}",
            f"- Evidence found: {summary['evidence_found']}",
            f"- Needs review: {summary['needs_review']}",
            f"- Blocked: {summary['blocked']}",
            f"- High risk: {summary['high_risk']}",
            f"- Deadlines detected: {summary['deadline_count']}",
            f"- Draft sections: {summary['draft_section_count']}",
            "",
            "## Requirement Matrix",
            "",
            "| ID | Category | Priority | Owner | Status | Risk | Evidence | Requirement |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in package["requirement_matrix"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md_cell(row["requirement_id"]),
                        self._md_cell(row["category"]),
                        self._md_cell(row["priority"]),
                        self._md_cell(row["owner_role"]),
                        self._md_cell(row["status"]),
                        self._md_cell(row["risk_level"]),
                        self._md_cell(", ".join(row["evidence_refs"]) or "Missing"),
                        self._md_cell(row["requirement_text"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Suggested Responses", ""])
        for row in package["requirement_matrix"]:
            lines.extend([f"### {row['requirement_id']}", "", row["suggested_response"], ""])
            if row["missing_evidence"]:
                lines.extend(["Missing evidence:", ""])
                lines.extend(f"- {item}" for item in row["missing_evidence"])
                lines.append("")
        if package.get("customer_fit"):
            fit = package["customer_fit"]
            profile = fit["customer_profile"]
            lines.extend(
                [
                    "## Customer Fit",
                    "",
                    f"- Profile: {profile['name']} ({profile['industry']}, {profile['region']})",
                    f"- Fit score: {fit['fit_score']}",
                    f"- Risk tolerance: {profile['risk_tolerance']}",
                    "",
                    "Recommended positioning:",
                    "",
                ]
            )
            lines.extend(f"- {item}" for item in fit["recommended_positioning"])
            lines.extend(["", "Profile risks:", ""])
            if fit["profile_risks"]:
                lines.extend(f"- {item}" for item in fit["profile_risks"])
            else:
                lines.append("- None")
            lines.append("")
        if package.get("response_memory_matches"):
            lines.extend(
                [
                    "## Approved Response Memory",
                    "",
                    "| Snippet | Category | Confidence | Tags | Citations |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for match in package["response_memory_matches"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            self._md_cell(match["title"]),
                            self._md_cell(match["category"]),
                            self._md_cell(match["confidence"]),
                            self._md_cell(", ".join(match["tags"])),
                            self._md_cell(", ".join(match["citations"])),
                        ]
                    )
                    + " |"
                )
            lines.append("")
        lines.extend(["## Drafted Sections", ""])
        for section in package["drafted_sections"]:
            lines.extend([f"### {section['title']}", "", section["body"], ""])
        lines.extend(["## Citations", ""])
        if package["citations"]:
            lines.extend(["| Source | Page | Score | Snippet |", "| --- | --- | --- | --- |"])
            for citation in package["citations"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            self._md_cell(citation["filename"]),
                            self._md_cell(citation.get("page") or ""),
                            self._md_cell(citation["score"]),
                            self._md_cell(citation["snippet"]),
                        ]
                    )
                    + " |"
                )
            lines.append("")
        else:
            lines.extend(["No citations were included in the draft.", ""])
        lines.extend(["## Risks", ""])
        lines.extend(f"- {risk}" for risk in package["risks"]) if package["risks"] else lines.append("- None")
        lines.extend(["", "## Missing Evidence", ""])
        if package["missing_evidence"]:
            lines.extend(f"- {item}" for item in package["missing_evidence"])
        else:
            lines.append("- None")
        usage = package["eval_usage_summary"]
        lines.extend(
            [
                "",
                "## Eval and Usage Summary",
                "",
                f"- Requests recorded: {usage['request_count']}",
                f"- Input tokens: {usage['input_tokens']}",
                f"- Output tokens: {usage['output_tokens']}",
                f"- Estimated cost: {usage['estimated_cost']}",
                f"- Average latency ms: {usage['average_latency_ms']}",
                "",
                "## Assumptions and Revision Notes",
                "",
            ]
        )
        for item in package["assumptions"] + package["revision_notes"]:
            lines.append(f"- {item}")
        return "\n".join(lines).strip() + "\n"

    def _md_cell(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
