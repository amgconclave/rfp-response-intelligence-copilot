# ruff: noqa: E501

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    ObjectionEvalAssertion,
    ObjectionHandlingPackResponse,
    ObjectionHandlingResponse,
    ObjectionResponseItem,
    ObjectionWorkflowTransition,
    WinStrategyResponse,
)
from app.models.domain import Citation, RequirementMatrixRow, ResponseMemoryMatch, ReviewFinding, TokenUsage
from app.repositories.memory import InMemoryRepository
from app.services.customer_intelligence import CustomerIntelligenceService
from app.services.retrieval import RetrievalService
from app.services.review_board import RfpReviewBoardService


class CompetitiveObjectionHandlingService:
    def __init__(
        self,
        repo: InMemoryRepository,
        settings: Settings,
        retrieval: RetrievalService,
        customer_intelligence: CustomerIntelligenceService,
        review_board: RfpReviewBoardService,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.retrieval = retrieval
        self.customer_intelligence = customer_intelligence
        self.review_board = review_board

    async def objection_handling(
        self,
        trace_id: str,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        win_strategy: WinStrategyResponse | None = None,
        response_memory_matches: list[ResponseMemoryMatch] | None = None,
        review_findings: list[ReviewFinding] | None = None,
        competitor_context: list[str] | None = None,
        pricing_notes: list[str] | None = None,
        objection_notes: list[str] | None = None,
        top_k: int = 4,
    ) -> ObjectionHandlingResponse:
        specs = self._objection_specs(objection_notes or [])
        objections = [
            await self._objection_item(
                spec,
                trace_id,
                top_k,
                analysis,
                requirement_matrix or [],
                win_strategy,
                response_memory_matches or [],
                review_findings or [],
                competitor_context or [],
                pricing_notes or [],
            )
            for spec in specs
        ]
        return ObjectionHandlingResponse(
            title="Competitive Objection Handling Pack",
            objections=objections,
            coverage_summary=self._coverage_summary(objections),
            confidence_summary=self._confidence_summary(objections),
            workflow_summary=self._workflow_summary(objections),
            eval_assertions=self._eval_assertions(objections),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def handling_pack(
        self,
        trace_id: str,
        objection_handling: ObjectionHandlingResponse,
        write_artifact: bool = True,
    ) -> ObjectionHandlingPackResponse:
        pack = self._pack_payload(trace_id, objection_handling)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "objection_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"competitive_objection_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"competitive_objection_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["objection_pack_markdown"] = artifact_path
            pack["artifact_paths"]["objection_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ObjectionHandlingPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            objection_handling=objection_handling,
            trace_id=trace_id,
        )

    async def _objection_item(
        self,
        spec: dict[str, Any],
        trace_id: str,
        top_k: int,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        win_strategy: WinStrategyResponse | None,
        memory_matches: list[ResponseMemoryMatch],
        review_findings: list[ReviewFinding],
        competitor_context: list[str],
        pricing_notes: list[str],
    ) -> ObjectionResponseItem:
        query = self._query(spec, analysis, competitor_context, pricing_notes)
        citations = await self.retrieval.search(query, top_k=top_k)
        citations = self._filtered_citations(citations, spec)
        if not memory_matches:
            memory_matches = self.customer_intelligence.search_response_memory(
                query,
                f"{trace_id}-{spec['id']}-memory",
                category=spec.get("memory_category"),
                customer_profile_id="regulated_healthcare",
                top_k=2,
            )
        missing = self._missing_evidence(spec, citations, matrix, review_findings, win_strategy)
        confidence = self._confidence(spec, citations, missing, win_strategy)
        risk_level = self._risk_level(spec, confidence, missing, win_strategy)
        approval_status = self._approval_status(spec, risk_level, missing)
        response = self._cited_response(spec, citations, memory_matches, missing, win_strategy)
        review = self.review_board.review_answer(
            spec["buyer_objection"],
            response,
            citations,
            missing,
            TokenUsage(input_tokens=140 + len(spec["buyer_objection"].split()), output_tokens=120),
            f"{trace_id}-{spec['id']}-review",
        )
        if any(finding.severity == "high" for finding in review.findings):
            risk_level = "high"
            if approval_status == "ready_with_review":
                approval_status = "requires_reviewer_approval"
        checkpoint_key = f"objection:{spec['id']}:{approval_status}"
        route_decision = self._route_decision(approval_status)
        workflow_trace = self._workflow_trace(
            trace_id,
            spec,
            citations,
            missing,
            confidence,
            risk_level,
            approval_status,
            route_decision,
        )
        return ObjectionResponseItem(
            objection_id=spec["id"],
            concern_type=spec["concern_type"],
            buyer_objection=spec["buyer_objection"],
            competitor_angle=self._competitor_angle(spec, competitor_context, win_strategy),
            response_posture=self._response_posture(spec, risk_level, confidence, win_strategy),
            cited_response=response,
            confidence=confidence,
            risk_level=risk_level,
            approval_status=approval_status,
            required_reviewer_role=spec["reviewer_role"],
            citations=citations,
            source_snippets=self._snippets(citations),
            missing_evidence=missing,
            reviewer_notes=self._reviewer_notes(spec, approval_status, review.findings),
            recommended_followups=self._recommended_followups(spec, risk_level, missing),
            checkpoint_key=checkpoint_key,
            route_decision=route_decision,
            workflow_trace=workflow_trace,
        )

    def _query(
        self,
        spec: dict[str, Any],
        analysis: AnalyzeResponse | None,
        competitor_context: list[str],
        pricing_notes: list[str],
    ) -> str:
        parts = [spec["query"], *competitor_context, *pricing_notes]
        if analysis:
            parts.extend(analysis.security_questions)
            parts.extend(analysis.compliance_asks)
            parts.extend(analysis.pricing_mentions)
        return " ".join(parts)

    def _filtered_citations(self, citations: list[Citation], spec: dict[str, Any]) -> list[Citation]:
        priority_files = set(spec.get("priority_files", []))
        if not priority_files:
            return citations
        priority = [citation for citation in citations if citation.filename in priority_files]
        return priority or citations[:2]

    def _missing_evidence(
        self,
        spec: dict[str, Any],
        citations: list[Citation],
        matrix: list[RequirementMatrixRow],
        review_findings: list[ReviewFinding],
        win_strategy: WinStrategyResponse | None,
    ) -> list[str]:
        gaps: list[str] = []
        filenames = {citation.filename for citation in citations}
        missing_files = [filename for filename in spec.get("priority_files", []) if filename not in filenames]
        if missing_files:
            gaps.append("Priority objection evidence not retrieved: " + ", ".join(missing_files))
        if not citations:
            gaps.append("No approved citation supports this objection response.")
        blocked_rows = [
            row
            for row in matrix
            if row.category == spec["matrix_category"] and (row.status == "blocked" or row.risk_level == "high")
        ]
        if blocked_rows:
            gaps.append(f"{len(blocked_rows)} related {spec['matrix_category']} requirement rows need review.")
        if any(finding.severity == "high" and finding.category in spec["finding_categories"] for finding in review_findings):
            gaps.append("High-severity review finding overlaps this objection category.")
        if spec["concern_type"] == "pricing" and win_strategy and win_strategy.pricing_risk["risk_level"] == "high":
            gaps.append("High pricing risk requires commercial approval before reuse.")
        if spec["concern_type"] == "competitor" and win_strategy and win_strategy.competitor_risk_profile["risk_level"] == "high":
            gaps.append("High competitor pressure requires an approved talk track.")
        return self._unique(gaps)

    def _confidence(
        self,
        spec: dict[str, Any],
        citations: list[Citation],
        missing: list[str],
        win_strategy: WinStrategyResponse | None,
    ) -> float:
        if not citations:
            return 0.2
        priority_hits = sum(citation.filename in spec.get("priority_files", []) for citation in citations)
        score = 0.52 + min(0.22, len(citations) * 0.05) + min(0.18, priority_hits * 0.06)
        score -= min(0.28, len(missing) * 0.07)
        if win_strategy and spec["concern_type"] in {"competitor", "pricing"}:
            score += 0.04 if win_strategy.win_score >= 70 else -0.04
        return round(max(0.1, min(0.92, score)), 2)

    def _risk_level(
        self,
        spec: dict[str, Any],
        confidence: float,
        missing: list[str],
        win_strategy: WinStrategyResponse | None,
    ) -> str:
        if not missing and confidence >= 0.72 and spec["base_risk"] != "high":
            return "medium" if spec["base_risk"] == "medium" else "low"
        if confidence < 0.45 or missing:
            return "high" if spec["base_risk"] == "high" or len(missing) >= 2 else "medium"
        if spec["concern_type"] == "pricing" and win_strategy and win_strategy.pricing_risk["risk_level"] == "high":
            return "high"
        return spec["base_risk"]

    def _approval_status(self, spec: dict[str, Any], risk_level: str, missing: list[str]) -> str:
        if not missing and risk_level == "low":
            return "ready_with_review"
        if not missing and spec["concern_type"] in {"implementation", "competitor"}:
            return "ready_with_review"
        if missing and risk_level == "high":
            return "blocked_until_evidence"
        return "requires_reviewer_approval"

    def _cited_response(
        self,
        spec: dict[str, Any],
        citations: list[Citation],
        memory_matches: list[ResponseMemoryMatch],
        missing: list[str],
        win_strategy: WinStrategyResponse | None,
    ) -> str:
        if not citations:
            return (
                f"Do not answer this {spec['concern_type']} objection as a supported claim yet. "
                f"Route it to {spec['reviewer_role']} and state that approved source evidence is still required."
            )
        approved_text = memory_matches[0].text if memory_matches else spec["safe_response"]
        sources = ", ".join(citation.filename for citation in citations[:3])
        posture = win_strategy.recommended_response_posture if win_strategy else spec["default_posture"]
        if missing:
            return (
                f"{approved_text} Use the qualified posture '{posture}' and cite {sources}. "
                f"Before external submission, resolve: {'; '.join(missing[:2])}."
            )
        return f"{approved_text} Recommended posture: {posture}. Supported by {sources}."

    def _competitor_angle(
        self,
        spec: dict[str, Any],
        competitor_context: list[str],
        win_strategy: WinStrategyResponse | None,
    ) -> str:
        if competitor_context:
            return competitor_context[0]
        if win_strategy:
            angles = win_strategy.competitor_risk_profile.get("likely_competitor_angles", [])
            if angles:
                return angles[0]
        return spec["competitor_angle"]

    def _response_posture(
        self,
        spec: dict[str, Any],
        risk_level: str,
        confidence: float,
        win_strategy: WinStrategyResponse | None,
    ) -> str:
        if risk_level == "high" or confidence < 0.5:
            return spec["cautious_posture"]
        if win_strategy and win_strategy.win_level in {"strong", "competitive"}:
            return spec["strong_posture"]
        return spec["default_posture"]

    def _reviewer_notes(
        self,
        spec: dict[str, Any],
        approval_status: str,
        findings: list[ReviewFinding],
    ) -> list[str]:
        notes = [
            f"{spec['reviewer_role']} must confirm the response does not exceed cited evidence.",
            "Use only cited local evidence and approved response memory before customer reuse.",
        ]
        if approval_status == "blocked_until_evidence":
            notes.append("Block external use until missing evidence is attached or the objection is rewritten.")
        notes.extend(f"{finding.category}: {finding.message}" for finding in findings[:2])
        return self._unique(notes)

    def _recommended_followups(
        self,
        spec: dict[str, Any],
        risk_level: str,
        missing: list[str],
    ) -> list[dict[str, Any]]:
        followups = [
            {
                "owner": spec["owner"],
                "action": spec["owner_action"],
                "priority": "high" if risk_level == "high" else "medium",
            },
            {
                "owner": "sales",
                "action": "Confirm customer-specific language and avoid naming competitors unless approved.",
                "priority": "medium",
            },
        ]
        if missing:
            followups.append(
                {
                    "owner": spec["owner"],
                    "action": "Attach missing evidence or add a caveat before submission.",
                    "priority": "high",
                }
            )
        return followups

    def _coverage_summary(self, objections: list[ObjectionResponseItem]) -> dict[str, Any]:
        concern_counts = Counter(item.concern_type for item in objections)
        risk_counts = Counter(item.risk_level for item in objections)
        approval_counts = Counter(item.approval_status for item in objections)
        cited = sum(bool(item.citations) for item in objections)
        return {
            "objection_count": len(objections),
            "concern_counts": dict(sorted(concern_counts.items())),
            "risk_counts": dict(sorted(risk_counts.items())),
            "approval_status_counts": dict(sorted(approval_counts.items())),
            "cited_objection_count": cited,
            "citation_count": sum(len(item.citations) for item in objections),
            "coverage_ratio": round(cited / len(objections), 2) if objections else 0,
            "blocked_count": approval_counts.get("blocked_until_evidence", 0),
            "approval_required_count": approval_counts.get("requires_reviewer_approval", 0),
        }

    def _confidence_summary(self, objections: list[ObjectionResponseItem]) -> dict[str, Any]:
        if not objections:
            return {"average_confidence": 0, "low_confidence_count": 0, "high_confidence_count": 0}
        average = round(sum(item.confidence for item in objections) / len(objections), 2)
        return {
            "average_confidence": average,
            "low_confidence_count": sum(item.confidence < 0.5 for item in objections),
            "high_confidence_count": sum(item.confidence >= 0.72 for item in objections),
            "lowest_confidence_objection_ids": [
                item.objection_id for item in sorted(objections, key=lambda row: row.confidence)[:2]
            ],
        }

    def _workflow_summary(self, objections: list[ObjectionResponseItem]) -> dict[str, Any]:
        transitions = [transition for item in objections for transition in item.workflow_trace]
        route_counts = Counter(item.route_decision for item in objections)
        owner_counts = Counter(transition.owner_role for transition in transitions)
        checkpoint_keys = [item.checkpoint_key for item in objections]
        return {
            "workflow_name": "competitive_objection_review",
            "pattern_coverage": [
                "typed contracts",
                "structured outputs",
                "dependency injection",
                "state machine workflow",
                "checkpointing",
                "conditional routing",
                "traceable node transitions",
                "eval-friendly design",
            ],
            "transition_count": len(transitions),
            "checkpoint_count": len(checkpoint_keys),
            "checkpoint_keys": checkpoint_keys,
            "route_decision_counts": dict(sorted(route_counts.items())),
            "owner_counts": dict(sorted(owner_counts.items())),
            "replay_status": "pass" if transitions and all(item.workflow_trace for item in objections) else "needs_review",
        }

    def _eval_assertions(self, objections: list[ObjectionResponseItem]) -> list[ObjectionEvalAssertion]:
        concern_types = {item.concern_type for item in objections}
        checkpoint_keys = [item.checkpoint_key for item in objections]
        transitions = [transition for item in objections for transition in item.workflow_trace]
        return [
            ObjectionEvalAssertion(
                assertion_id="objection-required-concern-coverage",
                description="Default pack covers competitor, pricing, security, compliance, and implementation objections.",
                passed={"competitor", "pricing", "security", "compliance", "implementation"} <= concern_types,
                evidence=", ".join(sorted(concern_types)),
                related_objection_ids=[item.objection_id for item in objections],
            ),
            ObjectionEvalAssertion(
                assertion_id="objection-checkpoints-unique",
                description="Every objection has a replayable checkpoint key for reviewer handoff.",
                passed=len(checkpoint_keys) == len(set(checkpoint_keys)) == len(objections),
                evidence=", ".join(checkpoint_keys),
                related_objection_ids=[item.objection_id for item in objections],
            ),
            ObjectionEvalAssertion(
                assertion_id="objection-route-decisions-terminal",
                description="Each objection reaches an explicit terminal route decision.",
                passed=all(item.route_decision in {"ready", "review", "blocked"} for item in objections),
                evidence=", ".join(f"{item.objection_id}:{item.route_decision}" for item in objections),
                related_objection_ids=[item.objection_id for item in objections],
            ),
            ObjectionEvalAssertion(
                assertion_id="objection-transition-replay-complete",
                description="Every objection emits classify, retrieve, score, route, and handoff transitions.",
                passed=all(len(item.workflow_trace) >= 5 for item in objections),
                evidence=f"transitions={len(transitions)} objections={len(objections)}",
                related_objection_ids=[item.objection_id for item in objections],
            ),
        ]

    def _route_decision(self, approval_status: str) -> str:
        if approval_status == "ready_with_review":
            return "ready"
        if approval_status == "blocked_until_evidence":
            return "blocked"
        return "review"

    def _workflow_trace(
        self,
        trace_id: str,
        spec: dict[str, Any],
        citations: list[Citation],
        missing: list[str],
        confidence: float,
        risk_level: str,
        approval_status: str,
        route_decision: str,
    ) -> list[ObjectionWorkflowTransition]:
        source_refs = [citation.filename for citation in citations]
        route_owner = spec["owner"] if route_decision != "ready" else "sales"
        rows = [
            {
                "from_state": None,
                "to_state": "classified",
                "decision": f"concern_type={spec['concern_type']}",
                "status": "complete",
                "owner_role": "proposal_manager",
                "evidence": spec["buyer_objection"],
            },
            {
                "from_state": "classified",
                "to_state": "evidence_retrieved",
                "decision": f"citations={len(citations)} priority_files={len(spec.get('priority_files', []))}",
                "status": "complete" if citations else "needs_review",
                "owner_role": "solutions",
                "evidence": ", ".join(source_refs[:4]) or "No retrieved citation.",
            },
            {
                "from_state": "evidence_retrieved",
                "to_state": "confidence_scored",
                "decision": f"confidence={confidence} risk={risk_level}",
                "status": "complete",
                "owner_role": "proposal_manager",
                "evidence": f"missing_evidence={len(missing)}",
            },
            {
                "from_state": "confidence_scored",
                "to_state": "review_route_selected",
                "decision": f"approval_status={approval_status} route={route_decision}",
                "status": "blocked" if route_decision == "blocked" else "complete",
                "owner_role": route_owner,
                "evidence": "; ".join(missing[:2]) or "No blocking evidence gap.",
            },
            {
                "from_state": "review_route_selected",
                "to_state": "handoff_ready",
                "decision": f"reviewer={spec['reviewer_role']}",
                "status": "needs_review" if route_decision in {"review", "blocked"} else "complete",
                "owner_role": spec["reviewer_role"],
                "evidence": f"checkpoint=objection:{spec['id']}:{approval_status}",
            },
        ]
        transitions: list[ObjectionWorkflowTransition] = []
        for index, row in enumerate(rows, start=1):
            next_state = rows[index]["to_state"] if index < len(rows) else None
            transitions.append(
                ObjectionWorkflowTransition(
                    transition_id=f"{spec['id']}_transition_{index}",
                    objection_id=spec["id"],
                    sequence=index,
                    from_state=row["from_state"],
                    to_state=row["to_state"],
                    decision=row["decision"],
                    status=row["status"],
                    checkpoint_key=f"{trace_id}:{spec['id']}:{index}:{row['to_state']}",
                    owner_role=row["owner_role"],
                    evidence=row["evidence"],
                    source_refs=source_refs,
                    next_state=next_state,
                )
            )
        return transitions

    def _pack_payload(self, trace_id: str, objection_handling: ObjectionHandlingResponse) -> dict[str, Any]:
        workflow_summary = objection_handling.workflow_summary or self._workflow_summary(objection_handling.objections)
        eval_assertions = objection_handling.eval_assertions or self._eval_assertions(objection_handling.objections)
        return {
            "trace_id": trace_id,
            "title": "Competitive Objection Handling Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": {
                "coverage_summary": objection_handling.coverage_summary,
                "confidence_summary": objection_handling.confidence_summary,
                "workflow_summary": workflow_summary,
            },
            "objection_responses": [item.model_dump(mode="json") for item in objection_handling.objections],
            "high_risk_objections": [
                item.model_dump(mode="json")
                for item in objection_handling.objections
                if item.risk_level == "high"
            ],
            "reviewer_workflow": self._reviewer_workflow(objection_handling.objections),
            "workflow_transitions": [
                transition.model_dump(mode="json")
                for item in objection_handling.objections
                for transition in item.workflow_trace
            ],
            "eval_assertions": [assertion.model_dump(mode="json") for assertion in eval_assertions],
            "endpoint_references": objection_handling.endpoint_references,
            "local_proof_commands": objection_handling.local_proof_commands,
            "limitations": objection_handling.limitations,
            "artifact_paths": {},
        }

    def _reviewer_workflow(self, objections: list[ObjectionResponseItem]) -> list[dict[str, Any]]:
        return [
            {
                "objection_id": item.objection_id,
                "concern_type": item.concern_type,
                "reviewer": item.required_reviewer_role,
                "approval_status": item.approval_status,
                "confidence": item.confidence,
                "required_action": item.recommended_followups[0]["action"] if item.recommended_followups else "Review response.",
            }
            for item in objections
        ]

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        coverage = pack["summary"]["coverage_summary"]
        confidence = pack["summary"]["confidence_summary"]
        workflow = pack["summary"]["workflow_summary"]
        lines = [
            "# Competitive Objection Handling Pack",
            "",
            "## Summary",
            "",
            f"- Objections: {coverage['objection_count']}",
            f"- Coverage ratio: {coverage['coverage_ratio']}",
            f"- Average confidence: {confidence['average_confidence']}",
            f"- Blocked: {coverage['blocked_count']}",
            f"- Approvals required: {coverage['approval_required_count']}",
            f"- Workflow transitions: {workflow['transition_count']}",
            f"- Replay status: {workflow['replay_status']}",
            "",
            "## Objection Responses",
            "",
        ]
        for item in pack["objection_responses"]:
            citations = ", ".join(citation["filename"] for citation in item["citations"]) or "None"
            lines.extend(
                [
                    f"### {item['concern_type'].title()} - {item['objection_id']}",
                    "",
                    f"- Risk: {item['risk_level']}",
                    f"- Confidence: {item['confidence']}",
                    f"- Approval: {item['approval_status']}",
                    f"- Reviewer: {item['required_reviewer_role']}",
                    f"- Citations: {citations}",
                    f"- Competitor angle: {item['competitor_angle']}",
                    "",
                    item["cited_response"],
                    "",
                ]
            )
        lines.extend(["## High-Risk Objections", ""])
        if pack["high_risk_objections"]:
            for item in pack["high_risk_objections"]:
                lines.append(f"- {item['objection_id']} ({item['concern_type']}): {item['approval_status']}")
        else:
            lines.append("- None")
        lines.extend(["", "## Reviewer Workflow", ""])
        lines.append("| Objection | Concern | Reviewer | Status | Confidence | Required action |")
        lines.append("| --- | --- | --- | --- | ---: | --- |")
        for row in pack["reviewer_workflow"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(row["objection_id"]),
                        self._md(row["concern_type"]),
                        self._md(row["reviewer"]),
                        self._md(row["approval_status"]),
                        self._md(row["confidence"]),
                        self._md(row["required_action"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Workflow Trace", ""])
        lines.append("| Objection | Seq | From | To | Decision | Status | Checkpoint | Owner |")
        lines.append("| --- | ---: | --- | --- | --- | --- | --- | --- |")
        for row in pack["workflow_transitions"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(row["objection_id"]),
                        self._md(row["sequence"]),
                        self._md(row["from_state"] or "START"),
                        self._md(row["to_state"]),
                        self._md(row["decision"]),
                        self._md(row["status"]),
                        self._md(row["checkpoint_key"]),
                        self._md(row["owner_role"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Eval Assertions", ""])
        lines.append("| Assertion | Passed | Evidence |")
        lines.append("| --- | --- | --- |")
        for assertion in pack["eval_assertions"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(assertion["assertion_id"]),
                        self._md(assertion["passed"]),
                        self._md(assertion["evidence"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Endpoint References", ""])
        for endpoint in pack["endpoint_references"]:
            lines.append(f"- {endpoint['method']} {endpoint['path']}: {endpoint['purpose']}")
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Objection Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {
                "method": "POST",
                "path": "/rfp/objection-handling",
                "purpose": "Generate structured cited objection responses by concern type.",
            },
            {
                "method": "POST",
                "path": "/rfp/objection-handling-pack",
                "purpose": "Write Markdown/JSON objection handling reviewer artifacts.",
            },
            {
                "method": "POST",
                "path": "/rfp/win-strategy",
                "purpose": "Provide competitor and pricing risk context for objection posture.",
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/objection-handling" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/objection-handling-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python scripts\\dashboard_smoke.py",
            "python -m app.demo",
            (
                'rg "objection-handling|Competitive Objection|objection_packs|Objection Handling" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\objection_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Objection handling is deterministic and local; it does not monitor live competitor pricing or external sales intelligence.",
            "Responses are suitable for reviewer triage, not automatic customer submission without sales, legal, security, or commercial approval.",
            "Confidence is based on local citation coverage, priority evidence, and known risk signals, not probabilistic model calibration.",
            "Competitor names and live pricing should be supplied by the seller and approved before external use.",
        ]

    def _objection_specs(self, objection_notes: list[str]) -> list[dict[str, Any]]:
        specs = [
            {
                "id": "obj_competitor_platform",
                "concern_type": "competitor",
                "matrix_category": "product",
                "buyer_objection": "A competitor says they can provide the same RFP automation with a broader workflow bundle.",
                "query": "competitive differentiation response automation workflow evidence citations product platform implementation security",
                "safe_response": "Position the copilot around grounded RFP response workflows, citation discipline, review routing, and local auditability rather than generic workflow breadth.",
                "competitor_angle": "Competitor may frame bundled workflow coverage as a lower-risk single-platform choice.",
                "default_posture": "Acknowledge the bundle, then differentiate on cited RFP safety, evidence workflow, and reviewer controls.",
                "strong_posture": "Lead with proof of governed RFP response quality, not feature-count comparisons.",
                "cautious_posture": "Avoid direct competitor claims and use source-backed differentiators only.",
                "reviewer_role": "Sales Strategy Reviewer",
                "owner": "sales",
                "owner_action": "Approve the competitive talk track and decide whether competitor naming is allowed.",
                "priority_files": ["product_overview.md", "prior_proposal.md", "implementation_guide.md"],
                "finding_categories": ["missing_evidence", "unsupported_claim"],
                "memory_category": "implementation",
                "base_risk": "medium",
            },
            {
                "id": "obj_pricing_discount",
                "concern_type": "pricing",
                "matrix_category": "pricing",
                "buyer_objection": "The competitor is cheaper and procurement is asking for a discount or price match.",
                "query": "pricing discount tiers usage implementation services payment terms procurement price match competitor",
                "safe_response": "Tie pricing to scoped tiers, implementation services, usage assumptions, and approval guardrails instead of promising a price match.",
                "competitor_angle": "Competitor may use discount pressure to compress scope and approval rigor.",
                "default_posture": "Defend value and route nonstandard commercial terms for approval.",
                "strong_posture": "Use value framing plus clear discount guardrails.",
                "cautious_posture": "Do not promise a discount, payment exception, or price match without commercial approval.",
                "reviewer_role": "Commercial Approver",
                "owner": "sales_ops",
                "owner_action": "Confirm discount guardrails, package boundary, and payment-term approval path.",
                "priority_files": ["pricing_notes.md", "customer_contract_terms.md"],
                "finding_categories": ["pricing", "missing_evidence", "high_risk_requirement"],
                "memory_category": "pricing",
                "base_risk": "high",
            },
            {
                "id": "obj_security_trust",
                "concern_type": "security",
                "matrix_category": "security",
                "buyer_objection": "Security is concerned about SSO, MFA, encryption, auditability, and tenant isolation.",
                "query": "SSO MFA encryption TLS AES-256 audit logging tenant isolation role based access security policy",
                "safe_response": "Answer with documented identity, access, encryption, and audit controls, and route architecture commitments to security review.",
                "competitor_angle": "Competitor may claim stronger controls or faster security approval.",
                "default_posture": "Use precise control evidence and avoid unverified assurance language.",
                "strong_posture": "Lead with cited identity, encryption, audit, and review workflow controls.",
                "cautious_posture": "Keep claims limited to cited controls and require security signoff.",
                "reviewer_role": "Security Architect",
                "owner": "security",
                "owner_action": "Validate security-language precision and attach architecture evidence.",
                "priority_files": ["security_policy.md", "ai_governance_security.md"],
                "finding_categories": ["security", "unsupported_claim", "weak_citation"],
                "memory_category": "security",
                "base_risk": "high",
            },
            {
                "id": "obj_compliance_assurance",
                "concern_type": "compliance",
                "matrix_category": "compliance",
                "buyer_objection": "Compliance needs SOC 2, GDPR, DPA, subprocessors, retention, and AI governance assurance.",
                "query": "SOC 2 GDPR DPA subprocessors retention deletion AI governance compliance audit privacy",
                "safe_response": "Use compliance and privacy policy evidence, cite DPA boundaries, and avoid unsupported certifications or blanket assurances.",
                "competitor_angle": "Competitor may imply broader certifications or lower review burden.",
                "default_posture": "Map each compliance ask to evidence, owner, and limitation.",
                "strong_posture": "Lead with evidence-mapped control coverage and transparent limitations.",
                "cautious_posture": "Do not claim unavailable certifications or unapproved legal terms.",
                "reviewer_role": "Legal Compliance Reviewer",
                "owner": "legal",
                "owner_action": "Approve compliance and DPA wording before external use.",
                "priority_files": ["compliance_policy.md", "dpa_privacy_policy.md", "ai_governance_security.md"],
                "finding_categories": ["compliance", "unsupported_claim", "missing_evidence"],
                "memory_category": "compliance",
                "base_risk": "high",
            },
            {
                "id": "obj_implementation_risk",
                "concern_type": "implementation",
                "matrix_category": "implementation",
                "buyer_objection": "Implementation may take too long or require too much customer effort.",
                "query": "implementation timeline onboarding rollout validation workshops owner customer success integration plan",
                "safe_response": "Describe discovery, configuration, source ingestion, validation workshops, customer success ownership, and rollout checkpoints.",
                "competitor_angle": "Competitor may promise a faster implementation without naming evidence or customer validation steps.",
                "default_posture": "Convert delivery concern into a named plan with milestones and owner accountability.",
                "strong_posture": "Lead with a concrete implementation plan and validation sequence.",
                "cautious_posture": "Avoid fixed delivery commitments beyond approved implementation evidence.",
                "reviewer_role": "Implementation Lead",
                "owner": "solutions",
                "owner_action": "Confirm timeline assumptions, SME availability, and customer validation checkpoints.",
                "priority_files": ["implementation_guide.md", "customer_success_onboarding.md"],
                "finding_categories": ["implementation", "missing_evidence"],
                "memory_category": "implementation",
                "base_risk": "medium",
            },
        ]
        for index, note in enumerate(objection_notes[:3], start=1):
            specs.append(
                {
                    "id": f"obj_custom_{index}",
                    "concern_type": "custom",
                    "matrix_category": "proposal",
                    "buyer_objection": note,
                    "query": note,
                    "safe_response": "Use a qualified response backed by retrieved local evidence and route any unsupported claim for review.",
                    "competitor_angle": "Customer supplied a custom objection needing local evidence validation.",
                    "default_posture": "Acknowledge the concern and answer only with cited evidence.",
                    "strong_posture": "Use cited proof points and keep commitments narrow.",
                    "cautious_posture": "Treat this as reviewer-gated until evidence and wording are approved.",
                    "reviewer_role": "Proposal Reviewer",
                    "owner": "solutions",
                    "owner_action": "Classify the custom objection and attach approved evidence.",
                    "priority_files": [],
                    "finding_categories": ["missing_evidence", "unsupported_claim"],
                    "memory_category": None,
                    "base_risk": "medium",
                }
            )
        return specs

    def _snippets(self, citations: list[Citation]) -> list[dict[str, Any]]:
        return [
            {
                "filename": citation.filename,
                "chunk_id": citation.chunk_id,
                "score": citation.score,
                "snippet": citation.snippet,
            }
            for citation in citations
        ]

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    def _unique(self, values: list[str]) -> list[str]:
        return [value for value in dict.fromkeys(values) if value]
