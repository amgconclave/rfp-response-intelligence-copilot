from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    AnswerReuseCoveragePackResponse,
    AnswerReuseCoverageResponse,
    AnswerReuseCoverageRow,
    AnswerReuseSnippet,
)
from app.models.domain import RfpRequirement
from app.services.answer_reuse_library import AnswerReuseLibraryService
from app.vectorstores.embedding import tokenize


class AnswerReuseCoverageService:
    def __init__(self, settings: Settings, answer_reuse_library: AnswerReuseLibraryService) -> None:
        self.settings = settings
        self.answer_reuse_library = answer_reuse_library

    def coverage(
        self,
        trace_id: str,
        analysis: AnalyzeResponse,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
        min_match_score: int = 2,
        top_snippets_per_requirement: int = 3,
    ) -> AnswerReuseCoverageResponse:
        library = self.answer_reuse_library.library(
            f"{trace_id}-library",
            category=category,
            customer_profile_id=customer_profile_id,
            include_expired=include_expired,
        )
        rows = [
            self._coverage_row(
                requirement,
                library.snippets,
                min_match_score=max(1, min_match_score),
                top_k=max(1, top_snippets_per_requirement),
            )
            for requirement in analysis.requirements
        ]
        summary = self._summary(rows, library.summary)
        return AnswerReuseCoverageResponse(
            title="Answer Reuse Coverage Map",
            status=self._status(summary),
            generated_at=datetime.now(UTC).isoformat(),
            requirements=rows,
            summary=summary,
            owner_queue=self._owner_queue(rows),
            workflow=self._workflow(summary),
            trace_spans=self._trace_spans(trace_id, analysis, rows, library.summary),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        coverage: AnswerReuseCoverageResponse | None = None,
        analysis: AnalyzeResponse | None = None,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
        min_match_score: int = 2,
        top_snippets_per_requirement: int = 3,
        write_artifact: bool = True,
    ) -> AnswerReuseCoveragePackResponse:
        if coverage is None:
            if analysis is None:
                raise ValueError("Provide coverage or analysis to build an Answer Reuse Coverage Pack.")
            coverage = self.coverage(
                f"{trace_id}-coverage",
                analysis,
                category=category,
                customer_profile_id=customer_profile_id,
                include_expired=include_expired,
                min_match_score=min_match_score,
                top_snippets_per_requirement=top_snippets_per_requirement,
            )
        pack = self._pack_payload(trace_id, coverage)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "answer_reuse_coverage"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"answer_reuse_coverage_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"answer_reuse_coverage_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["answer_reuse_coverage_markdown"] = artifact_path
            pack["artifact_paths"]["answer_reuse_coverage_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return AnswerReuseCoveragePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            coverage=coverage,
            trace_id=trace_id,
        )

    def _coverage_row(
        self,
        requirement: RfpRequirement,
        snippets: list[AnswerReuseSnippet],
        min_match_score: int,
        top_k: int,
    ) -> AnswerReuseCoverageRow:
        matches = [
            match
            for match in (
                self._match_payload(requirement, snippet)
                for snippet in snippets
                if snippet.category == requirement.category or requirement.category == "functional"
            )
            if match["match_score"] >= min_match_score
        ]
        matches = sorted(
            matches,
            key=lambda item: (
                item["reuse_decision"] != "approved_for_reuse",
                -item["match_score"],
                -item["confidence"],
                item["snippet_id"],
            ),
        )[:top_k]
        coverage_status = self._coverage_status(requirement, matches)
        owner = self._owner(requirement, matches)
        return AnswerReuseCoverageRow(
            requirement_id=requirement.id,
            requirement_text=requirement.text,
            category=requirement.category,
            priority=requirement.priority,
            coverage_status=coverage_status,
            coverage_score=self._coverage_score(matches),
            recommended_action=self._recommended_action(coverage_status, owner),
            owner=owner,
            matched_snippets=matches,
            missing_terms=self._missing_terms(requirement, matches),
            citation_refs=sorted({ref for match in matches for ref in match["citation_refs"]}),
            transition_trace=self._transitions(requirement, coverage_status, matches),
            endpoint_impact=[
                "/rfp/answer-reuse-library",
                "/rfp/answer-reuse-coverage",
                "/rfp/draft-response",
                "/rfp/export-package",
            ],
        )

    def _match_payload(self, requirement: RfpRequirement, snippet: AnswerReuseSnippet) -> dict[str, Any]:
        requirement_terms = self._terms(requirement.text)
        snippet_terms = self._terms(" ".join([snippet.title, snippet.reusable_text, *snippet.tags]))
        overlap = sorted(requirement_terms & snippet_terms)
        category_bonus = 2 if requirement.category == snippet.category else 0
        decision_bonus = 2 if snippet.reuse_decision == "approved_for_reuse" else 0
        score = len(overlap) + category_bonus + decision_bonus
        return {
            "snippet_id": snippet.snippet_id,
            "title": snippet.title,
            "category": snippet.category,
            "owner": snippet.owner,
            "reuse_decision": snippet.reuse_decision,
            "expiry_status": snippet.expiry_status,
            "confidence": snippet.confidence,
            "match_score": score,
            "matched_terms": overlap[:12],
            "citation_refs": snippet.citation_refs,
            "source_files": snippet.source_files,
        }

    def _coverage_status(self, requirement: RfpRequirement, matches: list[dict[str, Any]]) -> str:
        if not matches:
            return "gap_new_answer_required" if requirement.priority == "high" else "gap_draft_required"
        if matches[0]["reuse_decision"] == "approved_for_reuse":
            return "reuse_ready"
        if any(match["reuse_decision"] == "blocked" for match in matches):
            return "blocked_by_governance"
        return "owner_review_required"

    def _coverage_score(self, matches: list[dict[str, Any]]) -> int:
        if not matches:
            return 0
        best = matches[0]
        base = min(100, best["match_score"] * 10)
        if best["reuse_decision"] == "approved_for_reuse":
            base += 10
        if best["reuse_decision"] == "blocked":
            base -= 35
        if best["expiry_status"] != "current":
            base -= 10
        return max(0, min(100, base))

    def _owner(self, requirement: RfpRequirement, matches: list[dict[str, Any]]) -> str:
        if matches:
            return matches[0]["owner"]
        return {
            "security": "security",
            "compliance": "compliance",
            "pricing": "commercial",
            "implementation": "solutions",
        }.get(requirement.category, "proposal_manager")

    def _recommended_action(self, coverage_status: str, owner: str) -> str:
        return {
            "reuse_ready": "Reuse the top approved snippet with cited source checks during final export.",
            "owner_review_required": f"Route matched snippet to {owner} before customer-facing reuse.",
            "blocked_by_governance": (
                f"Keep reusable language out of the draft until {owner} resolves governance blockers."
            ),
            "gap_new_answer_required": f"Draft a new cited answer and assign {owner} as the response owner.",
            "gap_draft_required": f"Draft new language and confirm evidence with {owner}.",
        }[coverage_status]

    def _missing_terms(self, requirement: RfpRequirement, matches: list[dict[str, Any]]) -> list[str]:
        requirement_terms = self._terms(requirement.text)
        matched_terms = {term for match in matches for term in match["matched_terms"]}
        return sorted(term for term in requirement_terms - matched_terms if len(term) > 4)[:8]

    def _transitions(
        self,
        requirement: RfpRequirement,
        coverage_status: str,
        matches: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        top_decision = matches[0]["reuse_decision"] if matches else "no_match"
        states = [
            (None, "requirement_loaded", requirement.category, "pass"),
            ("requirement_loaded", "snippet_match_scored", str(len(matches)), "pass" if matches else "review"),
            ("snippet_match_scored", "reuse_policy_routed", top_decision, "pass" if matches else "review"),
            (
                "reuse_policy_routed",
                "coverage_decision_recorded",
                coverage_status,
                self._transition_status(coverage_status),
            ),
        ]
        return [
            {
                "sequence": index,
                "from_state": from_state,
                "to_state": to_state,
                "decision": decision,
                "status": status,
                "checkpoint_key": f"answer-reuse-coverage:{requirement.id}:{to_state}",
            }
            for index, (from_state, to_state, decision, status) in enumerate(states, start=1)
        ]

    def _transition_status(self, coverage_status: str) -> str:
        if coverage_status == "reuse_ready":
            return "pass"
        if coverage_status == "blocked_by_governance":
            return "blocked"
        return "review"

    def _summary(
        self,
        rows: list[AnswerReuseCoverageRow],
        library_summary: dict[str, Any],
    ) -> dict[str, Any]:
        statuses = Counter(row.coverage_status for row in rows)
        owners = Counter(row.owner for row in rows if row.coverage_status != "reuse_ready")
        reusable = statuses.get("reuse_ready", 0)
        total = len(rows)
        return {
            "requirement_count": total,
            "reuse_ready_count": reusable,
            "owner_review_count": statuses.get("owner_review_required", 0),
            "blocked_count": statuses.get("blocked_by_governance", 0),
            "gap_count": statuses.get("gap_new_answer_required", 0) + statuses.get("gap_draft_required", 0),
            "coverage_ratio": round(reusable / total, 2) if total else 0.0,
            "average_coverage_score": round(sum(row.coverage_score for row in rows) / total, 1) if total else 0.0,
            "status_counts": dict(sorted(statuses.items())),
            "owner_review_counts": dict(sorted(owners.items())),
            "library_summary": library_summary,
        }

    def _status(self, summary: dict[str, Any]) -> str:
        if summary["blocked_count"] > 0:
            return "blocked"
        if summary["owner_review_count"] > 0 or summary["gap_count"] > 0:
            return "needs_review"
        return "ready"

    def _owner_queue(self, rows: list[AnswerReuseCoverageRow]) -> list[dict[str, Any]]:
        return [
            {
                "requirement_id": row.requirement_id,
                "owner": row.owner,
                "coverage_status": row.coverage_status,
                "recommended_action": row.recommended_action,
                "checkpoint_key": row.transition_trace[-1]["checkpoint_key"],
            }
            for row in rows
            if row.coverage_status != "reuse_ready"
        ]

    def _workflow(self, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "pattern": "state_machine_workflow",
            "states": [
                "requirement_loaded",
                "snippet_match_scored",
                "reuse_policy_routed",
                "coverage_decision_recorded",
            ],
            "conditional_routes": {
                "reuse_ready": "approved snippet can move into draft/export with citation checks",
                "owner_review_required": "route to snippet owner before final wording",
                "blocked_by_governance": "hold customer-facing reuse until governance blocker clears",
                "gap_new_answer_required": "draft new cited answer and create evidence task",
                "gap_draft_required": "draft new language and verify evidence",
            },
            "checkpoint_count": summary["requirement_count"] * 4,
        }

    def _trace_spans(
        self,
        trace_id: str,
        analysis: AnalyzeResponse,
        rows: list[AnswerReuseCoverageRow],
        library_summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {
                "span_id": f"{trace_id}-requirements",
                "name": "load_requirements",
                "input": {"analysis_trace_id": analysis.trace_id},
                "output": {"requirement_count": len(analysis.requirements)},
            },
            {
                "span_id": f"{trace_id}-library",
                "name": "load_governed_snippets",
                "input": {"source": "/rfp/answer-reuse-library"},
                "output": library_summary,
            },
            {
                "span_id": f"{trace_id}-coverage",
                "name": "route_reuse_coverage",
                "input": {"row_count": len(rows)},
                "output": {
                    "reuse_ready": sum(1 for row in rows if row.coverage_status == "reuse_ready"),
                    "review_or_gap": sum(1 for row in rows if row.coverage_status != "reuse_ready"),
                },
            },
        ]

    def _pack_payload(self, trace_id: str, coverage: AnswerReuseCoverageResponse) -> dict[str, Any]:
        return {
            "title": "Answer Reuse Coverage Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
            "coverage": coverage.model_dump(mode="json"),
            "reviewer_checklist": [
                "Confirm reuse-ready rows still answer the exact RFP requirement.",
                "Route owner-review rows through named snippet owners before export.",
                "Draft new cited answers for gap rows and attach source requests where evidence is missing.",
            ],
            "governance_controls": [
                "Requirement coverage is scored from local accepted snippets and never calls an external LLM.",
                "Only approved snippets can be marked reuse_ready.",
                "Every requirement row has a deterministic checkpoint trail and owner route.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        coverage = pack["coverage"]
        summary = coverage["summary"]
        lines = [
            f"# {pack['title']}",
            "",
            f"- Generated at: {pack['generated_at']}",
            f"- Trace ID: {pack['trace_id']}",
            f"- Status: {coverage['status']}",
            f"- Requirements: {summary['requirement_count']}",
            f"- Reuse ready: {summary['reuse_ready_count']}",
            f"- Owner review: {summary['owner_review_count']}",
            f"- Gaps: {summary['gap_count']}",
            "",
            "## Requirement Coverage",
            "",
            "| Requirement | Category | Status | Score | Owner | Top Snippet | Action |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in coverage["requirements"]:
            top = row["matched_snippets"][0]["title"] if row["matched_snippets"] else "New answer required"
            lines.append(
                "| "
                f"{self._md(row['requirement_id'])} | "
                f"{self._md(row['category'])} | "
                f"{self._md(row['coverage_status'])} | "
                f"{row['coverage_score']} | "
                f"{self._md(row['owner'])} | "
                f"{self._md(top)} | "
                f"{self._md(row['recommended_action'])} |"
            )
        lines.extend(["", "## Owner Queue", ""])
        if coverage["owner_queue"]:
            lines.extend(
                f"- {item['owner']}: {item['requirement_id']} - {item['recommended_action']}"
                for item in coverage["owner_queue"]
            )
        else:
            lines.append("- No owner actions required.")
        lines.extend(["", "## Workflow", "", f"- Pattern: {coverage['workflow']['pattern']}"])
        lines.extend(f"- State: {state}" for state in coverage["workflow"]["states"])
        lines.extend(["", "## Reviewer Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_checklist"])
        lines.extend(["", "## Governance Controls", ""])
        lines.extend(f"- {item}" for item in pack["governance_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"- `{command}`" for command in coverage["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in coverage["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifact Paths", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _terms(self, value: str) -> set[str]:
        stop = {
            "and",
            "are",
            "for",
            "from",
            "must",
            "provide",
            "required",
            "shall",
            "that",
            "the",
            "with",
        }
        return {token for token in tokenize(value) if len(token) > 2 and token not in stop}

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-coverage",
                "purpose": "Map RFP requirements to governed reusable snippets and owner routes.",
            },
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-coverage-pack",
                "purpose": "Write Markdown/JSON Answer Reuse Coverage artifacts.",
                "expected_artifacts": ["storage/answer_reuse_coverage/*.md", "storage/answer_reuse_coverage/*.json"],
            },
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-library",
                "purpose": "Provides the governed snippet inventory used for coverage scoring.",
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-coverage" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" '
                '-d "{\\"analyzed_payload\\":{}}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-coverage-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" '
                '-d "{\\"write_artifact\\":true,\\"analyzed_payload\\":{}}"'
            ),
            (
                'rg "answer-reuse-coverage|Answer Reuse Coverage|answer_reuse_coverage" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\answer_reuse_coverage -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Coverage is deterministic keyword/category matching over local fixtures, not semantic approval.",
            "Requirement extraction quality depends on the local RFP analysis payload supplied by the caller.",
            "Owner routes are local governance artifacts and do not update external ticketing or workflow tools.",
        ]

    def _md(self, value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
