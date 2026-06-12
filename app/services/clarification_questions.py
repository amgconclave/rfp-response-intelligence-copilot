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
    ClarificationEvalAssertion,
    ClarificationQuestionItem,
    ClarificationQuestionPackResponse,
    ClarificationQuestionResponse,
    ClarificationWorkflowTransition,
    ContractRiskResponse,
    DealReadinessScorecardResponse,
)
from app.models.domain import Citation, EvidenceGap, RequirementMatrixRow, ReviewFinding
from app.services.retrieval import RetrievalService


class ClarificationQuestionService:
    def __init__(self, settings: Settings, retrieval: RetrievalService) -> None:
        self.settings = settings
        self.retrieval = retrieval

    async def create_questions(
        self,
        trace_id: str,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        evidence_gaps: list[EvidenceGap] | None = None,
        review_findings: list[ReviewFinding] | None = None,
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        contract_risk: ContractRiskResponse | None = None,
        top_k: int = 4,
        max_questions: int = 8,
    ) -> ClarificationQuestionResponse:
        matrix = requirement_matrix or []
        findings = review_findings or []
        seeds = self._seeds(analysis, matrix, evidence_gaps or [], findings, readiness_scorecard, contract_risk)
        questions = [
            await self._question_item(seed, index, trace_id, top_k, matrix)
            for index, seed in enumerate(seeds[:max(1, max_questions)], start=1)
        ]
        summary = self._summary(questions, seeds)
        return ClarificationQuestionResponse(
            title="RFP Clarification Question Workflow",
            status=self._status(summary),
            questions=questions,
            summary=summary,
            reviewer_queue=self._reviewer_queue(questions),
            workflow_summary=self._workflow_summary(questions),
            trace_spans=self._trace_spans(trace_id, questions),
            eval_assertions=self._eval_assertions(questions),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def question_pack(
        self,
        trace_id: str,
        clarification_questions: ClarificationQuestionResponse,
        write_artifact: bool = True,
    ) -> ClarificationQuestionPackResponse:
        pack = self._pack_payload(trace_id, clarification_questions)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "clarification_questions"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"clarification_question_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"clarification_question_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["clarification_pack_markdown"] = artifact_path
            pack["artifact_paths"]["clarification_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ClarificationQuestionPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            clarification_questions=clarification_questions,
            trace_id=trace_id,
        )

    def _seeds(
        self,
        analysis: AnalyzeResponse | None,
        matrix: list[RequirementMatrixRow],
        gaps: list[EvidenceGap],
        findings: list[ReviewFinding],
        readiness: DealReadinessScorecardResponse | None,
        contract_risk: ContractRiskResponse | None,
    ) -> list[dict[str, Any]]:
        rows = {row.requirement_id: row for row in matrix}
        seeds: list[dict[str, Any]] = []
        for gap in gaps:
            row = rows.get(gap.requirement_ids[0]) if gap.requirement_ids else None
            if self._is_clarification_candidate(gap, row):
                seeds.append(
                    {
                        "source": "evidence_gap",
                        "category": row.category if row else self._category_from_text(gap.title),
                        "priority": self._priority(gap.severity),
                        "title": gap.title,
                        "question_text": self._question_from_gap(gap, row),
                        "rationale": self._rationale_from_gap(gap, row),
                        "audience": self._audience(gap, row),
                        "owner_role": self._owner_role(gap.owner_team, row),
                        "reviewer_role": self._reviewer_role(row.category if row else gap.owner_team),
                        "requirement_ids": gap.requirement_ids,
                        "gap_ids": [gap.gap_id],
                        "missing_evidence": gap.source_signals or gap.closure_acceptance_criteria,
                        "query": self._query(gap.title, row.requirement_text if row else " ".join(gap.source_signals)),
                    }
                )
        for item in analysis.missing_information if analysis else []:
            seeds.append(
                {
                    "source": "analysis_missing_information",
                    "category": self._category_from_text(item),
                    "priority": "medium",
                    "title": f"Clarify RFP missing information: {item}",
                    "question_text": f"Can you clarify the expected scope or acceptance criteria for: {item}?",
                    "rationale": "The RFP analysis flagged missing information that should be confirmed before final response language.",
                    "audience": "buyer",
                    "owner_role": "proposal_manager",
                    "reviewer_role": "proposal_manager",
                    "requirement_ids": [],
                    "gap_ids": [],
                    "missing_evidence": [item],
                    "query": self._query(item, "rfp missing information clarification"),
                }
            )
        for row in matrix:
            if row.status == "blocked" or row.missing_evidence or row.risk_level == "high":
                seeds.append(
                    {
                        "source": "requirement_matrix",
                        "category": row.category,
                        "priority": "high" if row.risk_level == "high" else row.priority,
                        "title": f"Clarify requirement {row.requirement_id}",
                        "question_text": self._question_from_row(row),
                        "rationale": "The requirement is blocked, high-risk, or lacks approved local evidence.",
                        "audience": "buyer" if row.category in {"pricing", "implementation"} else "internal_sme",
                        "owner_role": row.owner_role,
                        "reviewer_role": self._reviewer_role(row.category),
                        "requirement_ids": [row.requirement_id],
                        "gap_ids": [],
                        "missing_evidence": row.missing_evidence,
                        "query": self._query(row.requirement_text, row.category),
                    }
                )
        for finding in findings:
            if finding.severity in {"critical", "high"} or finding.category in {"missing_evidence", "unsupported_claim"}:
                seeds.append(
                    {
                        "source": "review_finding",
                        "category": self._category_from_text(finding.message),
                        "priority": self._priority(finding.severity),
                        "title": f"Clarify review finding {finding.finding_id}",
                        "question_text": f"What approved source or exception language should we use for: {finding.message}?",
                        "rationale": f"Review board finding requires closure: {finding.recommendation}",
                        "audience": "internal_sme",
                        "owner_role": self._owner_for_category(self._category_from_text(finding.message)),
                        "reviewer_role": self._reviewer_role(self._category_from_text(finding.message)),
                        "requirement_ids": [finding.related_requirement_id] if finding.related_requirement_id else [],
                        "gap_ids": [],
                        "missing_evidence": [finding.message],
                        "query": self._query(finding.message, finding.recommendation),
                    }
                )
        seeds.extend(self._readiness_seeds(readiness))
        seeds.extend(self._contract_risk_seeds(contract_risk))
        return self._dedupe(seeds)

    async def _question_item(
        self,
        seed: dict[str, Any],
        index: int,
        trace_id: str,
        top_k: int,
        matrix: list[RequirementMatrixRow],
    ) -> ClarificationQuestionItem:
        citations = await self.retrieval.search(seed["query"], top_k=top_k)
        citations = self._citation_filter(citations, seed["category"])
        confidence = self._confidence(seed, citations)
        evidence_status = "supported_context" if citations else "needs_source"
        approval_status = self._approval_status(seed, citations, confidence)
        clarification_id = f"clarification_{index:02d}_{self._slug(seed['category'])}"
        workflow_trace = self._workflow_trace(clarification_id, seed, citations, approval_status, confidence)
        return ClarificationQuestionItem(
            clarification_id=clarification_id,
            question_text=seed["question_text"],
            category=seed["category"],
            priority=seed["priority"],
            audience=seed["audience"],
            owner_role=seed["owner_role"],
            reviewer_role=seed["reviewer_role"],
            rationale=seed["rationale"],
            evidence_status=evidence_status,
            confidence=confidence,
            approval_status=approval_status,
            related_requirement_ids=seed["requirement_ids"],
            related_gap_ids=seed["gap_ids"],
            citations=citations,
            source_snippets=self._snippets(citations),
            missing_evidence=seed["missing_evidence"][:5],
            recommended_followups=self._followups(seed, matrix, citations),
            workflow_trace=workflow_trace,
        )

    def _is_clarification_candidate(self, gap: EvidenceGap, row: RequirementMatrixRow | None) -> bool:
        if gap.severity in {"critical", "high"}:
            return True
        if gap.missing_source_type in {"rfp_clarification", "pricing_exception", "implementation_plan"}:
            return True
        return bool(row and (row.status == "blocked" or row.risk_level == "high"))

    def _question_from_gap(self, gap: EvidenceGap, row: RequirementMatrixRow | None) -> str:
        if row:
            return (
                f"Can you confirm the expected scope, evidence, or acceptable assumption for "
                f"{row.requirement_id}: {self._clip(row.requirement_text, 150)}?"
            )
        signal = gap.source_signals[0] if gap.source_signals else gap.title
        return f"Can you clarify the buyer expectation or approved source needed for: {self._clip(signal, 150)}?"

    def _question_from_row(self, row: RequirementMatrixRow) -> str:
        if row.category == "pricing":
            return f"Can you confirm the commercial boundary, discount approval, and pricing assumption for {row.requirement_id}?"
        if row.category == "implementation":
            return f"Can you confirm implementation timeline, integration ownership, and acceptance criteria for {row.requirement_id}?"
        return f"What approved evidence or exception language should support {row.requirement_id}: {self._clip(row.requirement_text, 150)}?"

    def _rationale_from_gap(self, gap: EvidenceGap, row: RequirementMatrixRow | None) -> str:
        if row:
            return f"{row.requirement_id} is {row.status} with {row.risk_level} risk and needs clarification before submission."
        return f"{gap.gap_id} needs closure criteria before customer-facing response reuse."

    def _readiness_seeds(self, readiness: DealReadinessScorecardResponse | None) -> list[dict[str, Any]]:
        if not readiness:
            return []
        return [
            {
                "source": "readiness_blocker",
                "category": self._category_from_text(blocker),
                "priority": "high",
                "title": f"Clarify readiness blocker: {blocker}",
                "question_text": f"What decision, evidence, or exception is required to clear this submission blocker: {blocker}?",
                "rationale": "The readiness scorecard identifies this blocker before final submission.",
                "audience": "internal_sme",
                "owner_role": self._owner_for_category(self._category_from_text(blocker)),
                "reviewer_role": self._reviewer_role(self._category_from_text(blocker)),
                "requirement_ids": [],
                "gap_ids": [],
                "missing_evidence": [blocker],
                "query": self._query(blocker, "readiness blocker evidence"),
            }
            for blocker in readiness.blockers[:4]
        ]

    def _contract_risk_seeds(self, contract_risk: ContractRiskResponse | None) -> list[dict[str, Any]]:
        if not contract_risk:
            return []
        seeds = []
        for clause in contract_risk.risky_clauses[:4]:
            if clause.risk_level not in {"critical", "high"}:
                continue
            seeds.append(
                {
                    "source": "contract_risk",
                    "category": clause.category,
                    "priority": "high",
                    "title": f"Clarify contract risk {clause.clause_id}",
                    "question_text": f"Can legal confirm the fallback position or redline for {clause.title}?",
                    "rationale": clause.rationale,
                    "audience": "internal_sme",
                    "owner_role": "legal",
                    "reviewer_role": "legal",
                    "requirement_ids": [],
                    "gap_ids": [],
                    "missing_evidence": clause.missing_evidence or [clause.suggested_redline],
                    "query": self._query(clause.clause_text, clause.category),
                }
            )
        return seeds

    def _dedupe(self, seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for seed in seeds:
            key = self._slug(" ".join(seed["requirement_ids"]) or seed["question_text"])
            current = unique.get(key)
            if not current or self._rank(seed["priority"]) > self._rank(current["priority"]):
                unique[key] = seed
        return sorted(
            unique.values(),
            key=lambda item: (-self._rank(item["priority"]), item["audience"], item["category"], item["question_text"]),
        )

    def _citation_filter(self, citations: list[Citation], category: str) -> list[Citation]:
        if not citations:
            return []
        preferred = {
            "security": ["security", "governance", "policy"],
            "compliance": ["compliance", "privacy", "dpa"],
            "pricing": ["pricing", "proposal"],
            "implementation": ["implementation", "onboarding", "success"],
            "legal": ["contract", "privacy", "dpa"],
        }.get(category, [])
        filtered = [
            citation
            for citation in citations
            if any(term in citation.filename.lower() or term in citation.snippet.lower() for term in preferred)
        ]
        return filtered or citations[:3]

    def _confidence(self, seed: dict[str, Any], citations: list[Citation]) -> float:
        base = 0.38 + min(0.32, len(citations) * 0.08)
        if seed["priority"] == "high":
            base -= 0.04
        if seed["audience"] == "buyer" and not citations:
            base -= 0.08
        return round(max(0.2, min(0.92, base)), 2)

    def _approval_status(self, seed: dict[str, Any], citations: list[Citation], confidence: float) -> str:
        if seed["priority"] == "high" or seed["audience"] == "buyer":
            return "requires_reviewer_approval"
        if not citations or confidence < 0.5:
            return "needs_internal_source"
        return "ready_for_review"

    def _workflow_trace(
        self,
        clarification_id: str,
        seed: dict[str, Any],
        citations: list[Citation],
        approval_status: str,
        confidence: float,
    ) -> list[ClarificationWorkflowTransition]:
        evidence_refs = [f"{citation.filename}:{citation.chunk_id}" for citation in citations]
        states = [
            (None, "drafted", "pass", seed["owner_role"], "question_created", "Gap converted into a clarification question."),
            ("drafted", "evidence_checked", "pass" if citations else "warn", seed["owner_role"], "retrieval_context_attached" if citations else "source_needed", f"{len(citations)} supporting source snippets found."),
            ("evidence_checked", "reviewer_routed", "pass", seed["reviewer_role"], "hitl_required", "Human reviewer owns wording before buyer/internal circulation."),
            ("reviewer_routed", approval_status, "warn" if approval_status != "ready_for_review" else "pass", seed["reviewer_role"], approval_status, f"Confidence {confidence} and audience {seed['audience']} set approval route."),
        ]
        return [
            ClarificationWorkflowTransition(
                transition_id=f"{clarification_id}_transition_{index:02d}",
                clarification_id=clarification_id,
                sequence=index,
                from_state=from_state,
                to_state=to_state,
                status=status,
                owner_role=owner,
                decision=decision,
                checkpoint_key=f"clarification:{clarification_id}:{to_state}",
                trace_note=note,
                evidence_refs=evidence_refs,
            )
            for index, (from_state, to_state, status, owner, decision, note) in enumerate(states, start=1)
        ]

    def _summary(self, questions: list[ClarificationQuestionItem], seeds: list[dict[str, Any]]) -> dict[str, Any]:
        categories = Counter(question.category for question in questions)
        owners = Counter(question.owner_role for question in questions)
        approval = Counter(question.approval_status for question in questions)
        buyer_count = sum(1 for question in questions if question.audience == "buyer")
        cited_count = sum(1 for question in questions if question.citations)
        return {
            "question_count": len(questions),
            "candidate_seed_count": len(seeds),
            "buyer_question_count": buyer_count,
            "internal_question_count": len(questions) - buyer_count,
            "high_priority_count": sum(1 for question in questions if question.priority == "high"),
            "cited_question_count": cited_count,
            "citation_coverage": round(cited_count / len(questions), 2) if questions else 0,
            "approval_required_count": sum(
                1 for question in questions if question.approval_status != "ready_for_review"
            ),
            "category_counts": dict(sorted(categories.items())),
            "owner_counts": dict(sorted(owners.items())),
            "approval_status_counts": dict(sorted(approval.items())),
        }

    def _status(self, summary: dict[str, Any]) -> str:
        if summary["question_count"] == 0:
            return "no_clarifications_needed"
        if summary["approval_required_count"] > 0:
            return "requires_review"
        return "ready_for_review"

    def _reviewer_queue(self, questions: list[ClarificationQuestionItem]) -> list[dict[str, Any]]:
        return [
            {
                "clarification_id": question.clarification_id,
                "reviewer_role": question.reviewer_role,
                "owner_role": question.owner_role,
                "priority": question.priority,
                "approval_status": question.approval_status,
                "question_text": question.question_text,
                "required_action": self._required_action(question),
            }
            for question in questions
            if question.approval_status != "ready_for_review"
        ]

    def _workflow_summary(self, questions: list[ClarificationQuestionItem]) -> dict[str, Any]:
        transitions = [transition for question in questions for transition in question.workflow_trace]
        return {
            "workflow_name": "clarification_question_hitl_review",
            "transition_count": len(transitions),
            "checkpoint_count": len(transitions),
            "replay_status": "pass" if all(question.workflow_trace for question in questions) else "warn",
            "durable_state_keys": [transition.checkpoint_key for transition in transitions],
            "blocked_or_review_count": sum(
                1 for question in questions if question.approval_status != "ready_for_review"
            ),
        }

    def _trace_spans(self, trace_id: str, questions: list[ClarificationQuestionItem]) -> list[dict[str, Any]]:
        return [
            {
                "span_id": f"{trace_id}-{question.clarification_id}",
                "name": "clarification_question.evaluate",
                "category": question.category,
                "audience": question.audience,
                "citation_count": len(question.citations),
                "approval_status": question.approval_status,
                "confidence": question.confidence,
            }
            for question in questions
        ]

    def _eval_assertions(self, questions: list[ClarificationQuestionItem]) -> list[ClarificationEvalAssertion]:
        ids = [question.clarification_id for question in questions]
        return [
            ClarificationEvalAssertion(
                assertion_id="clarification_has_owner",
                description="Every clarification question has an owner and reviewer role.",
                passed=all(question.owner_role and question.reviewer_role for question in questions),
                evidence=f"{len(questions)} questions checked.",
                related_clarification_ids=ids,
            ),
            ClarificationEvalAssertion(
                assertion_id="clarification_has_workflow",
                description="Every clarification question includes durable workflow checkpoints.",
                passed=all(len(question.workflow_trace) >= 4 for question in questions),
                evidence="Workflow trace includes drafted, evidence_checked, reviewer_routed, and approval states.",
                related_clarification_ids=ids,
            ),
            ClarificationEvalAssertion(
                assertion_id="buyer_questions_require_hitl",
                description="Buyer-facing clarification questions require human review before release.",
                passed=all(
                    question.approval_status == "requires_reviewer_approval"
                    for question in questions
                    if question.audience == "buyer"
                ),
                evidence=f"{sum(1 for question in questions if question.audience == 'buyer')} buyer questions checked.",
                related_clarification_ids=[
                    question.clarification_id for question in questions if question.audience == "buyer"
                ],
            ),
        ]

    def _pack_payload(self, trace_id: str, clarification_questions: ClarificationQuestionResponse) -> dict[str, Any]:
        questions = [question.model_dump(mode="json") for question in clarification_questions.questions]
        return {
            "title": "RFP Clarification Question Pack",
            "trace_id": trace_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": clarification_questions.summary,
            "question_table": questions,
            "buyer_ready_questions": [
                question
                for question in questions
                if question["audience"] == "buyer" and question["approval_status"] == "requires_reviewer_approval"
            ],
            "internal_sme_questions": [question for question in questions if question["audience"] != "buyer"],
            "reviewer_queue": clarification_questions.reviewer_queue,
            "workflow_transitions": [
                transition.model_dump(mode="json")
                for question in clarification_questions.questions
                for transition in question.workflow_trace
            ],
            "trace_spans": clarification_questions.trace_spans,
            "eval_assertions": [item.model_dump(mode="json") for item in clarification_questions.eval_assertions],
            "endpoint_references": clarification_questions.endpoint_references,
            "local_proof_commands": clarification_questions.local_proof_commands,
            "jd_skills_demonstrated": [
                "Human-in-the-loop clarification routing for buyer-facing and internal SME questions.",
                "Traceable workflow checkpoints and local spans for proposal governance review.",
                "Evidence-gap and retrieval-aware question generation without external CRM or LLM dependencies.",
                "Deterministic artifact export for reviewer handoff and auditability.",
            ],
            "limitations": clarification_questions.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        lines = [
            f"# {pack['title']}",
            "",
            f"- Trace ID: `{pack['trace_id']}`",
            f"- Generated at: {pack['generated_at']}",
            f"- Questions: {pack['summary']['question_count']}",
            f"- Buyer-facing: {pack['summary']['buyer_question_count']}",
            f"- Approval required: {pack['summary']['approval_required_count']}",
            f"- Citation coverage: {pack['summary']['citation_coverage']}",
            "",
            "## Clarification Questions",
        ]
        for question in pack["question_table"]:
            lines.extend(
                [
                    "",
                    f"### {question['clarification_id']} ({question['category']})",
                    f"- Priority: {question['priority']}",
                    f"- Audience: {question['audience']}",
                    f"- Owner: {question['owner_role']}",
                    f"- Reviewer: {question['reviewer_role']}",
                    f"- Approval: {question['approval_status']}",
                    f"- Confidence: {question['confidence']}",
                    f"- Question: {question['question_text']}",
                    f"- Rationale: {question['rationale']}",
                ]
            )
            self._append_list(lines, "Missing evidence", question["missing_evidence"])
            self._append_list(
                lines,
                "Citations",
                [
                    f"{citation['filename']} ({citation['score']}): {citation['snippet']}"
                    for citation in question["citations"]
                ],
            )
            self._append_list(lines, "Follow-ups", question["recommended_followups"])
        lines.extend(["", "## Reviewer Queue"])
        for row in pack["reviewer_queue"]:
            lines.append(
                f"- `{row['clarification_id']}` -> {row['reviewer_role']} / {row['approval_status']}: "
                f"{row['required_action']}"
            )
        lines.extend(["", "## Workflow Trace"])
        for transition in pack["workflow_transitions"]:
            lines.append(
                f"- {transition['transition_id']}: {transition['from_state']} -> {transition['to_state']} "
                f"({transition['status']}, {transition['owner_role']})"
            )
        lines.extend(["", "## Eval Assertions"])
        for assertion in pack["eval_assertions"]:
            lines.append(f"- {assertion['assertion_id']}: {assertion['passed']} - {assertion['evidence']}")
        lines.extend(["", "## Local Proof Commands"])
        lines.extend(f"- `{command}`" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations"])
        lines.extend(f"- {item}" for item in pack["limitations"])
        return "\n".join(lines) + "\n"

    def _append_list(self, lines: list[str], label: str, values: list[str]) -> None:
        if not values:
            return
        lines.append(f"- {label}:")
        lines.extend(f"  - {value}" for value in values[:6])

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

    def _followups(
        self,
        seed: dict[str, Any],
        matrix: list[RequirementMatrixRow],
        citations: list[Citation],
    ) -> list[str]:
        followups = [
            "Review wording with the listed owner before adding it to a buyer-facing clarification log.",
            "Attach the response or decision to the final proposal package when resolved.",
        ]
        if not citations:
            followups.insert(0, "Request an approved source document or explicit exception before drafting final language.")
        if seed["audience"] == "buyer":
            followups.append("Send only after proposal manager approval and account owner context review.")
        related = [row for row in matrix if row.requirement_id in seed["requirement_ids"]]
        if related:
            followups.append(f"Update requirement matrix row {related[0].requirement_id} after closure.")
        return followups

    def _required_action(self, question: ClarificationQuestionItem) -> str:
        if question.audience == "buyer":
            return "Approve buyer-facing wording and confirm whether to send through the official RFP channel."
        if question.evidence_status == "needs_source":
            return "Provide approved evidence, exception language, or mark the answer as unsupported."
        return "Review source context and approve final internal guidance."

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "POST", "path": "/rfp/clarification-questions", "purpose": "Generate HITL clarification questions."},
            {"method": "POST", "path": "/rfp/clarification-question-pack", "purpose": "Write Markdown/JSON clarification pack."},
            {"method": "POST", "path": "/rfp/evidence-gaps", "purpose": "Source gap inputs for question generation."},
            {"method": "POST", "path": "/rfp/source-request-pack", "purpose": "Owner source request companion workflow."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/clarification-questions" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/clarification-question-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Clarification questions are deterministic local workflow artifacts, not automatically sent to a buyer.",
            "Reviewer assignments are role-based placeholders and should be mapped to real users in production.",
            "Retrieval citations provide context for the question, but unanswered buyer clarifications still require explicit closure.",
            "No external RFP portal, CRM, email, or ticketing integration is invoked.",
        ]

    def _owner_role(self, owner_team: str, row: RequirementMatrixRow | None) -> str:
        if row:
            return row.owner_role
        return {
            "security": "security_architect",
            "compliance": "compliance_lead",
            "legal": "legal",
            "finance": "finance",
            "solutions": "solutions_architect",
            "implementation": "implementation_lead",
        }.get(owner_team.lower(), owner_team or "proposal_manager")

    def _reviewer_role(self, category: str) -> str:
        return {
            "security": "security_architect",
            "compliance": "compliance_lead",
            "privacy": "privacy_counsel",
            "legal": "legal",
            "pricing": "commercial_owner",
            "implementation": "implementation_lead",
        }.get(category, "proposal_manager")

    def _owner_for_category(self, category: str) -> str:
        return {
            "security": "security_architect",
            "compliance": "compliance_lead",
            "pricing": "commercial_owner",
            "implementation": "implementation_lead",
            "legal": "legal",
        }.get(category, "proposal_manager")

    def _audience(self, gap: EvidenceGap, row: RequirementMatrixRow | None) -> str:
        if gap.missing_source_type == "rfp_clarification":
            return "buyer"
        if row and row.category in {"pricing", "implementation"}:
            return "buyer"
        return "internal_sme"

    def _category_from_text(self, text: str) -> str:
        lowered = text.lower()
        if any(term in lowered for term in ["security", "sso", "encryption", "incident", "mfa"]):
            return "security"
        if any(term in lowered for term in ["compliance", "gdpr", "soc 2", "privacy", "dpa", "subprocessor"]):
            return "compliance"
        if any(term in lowered for term in ["price", "pricing", "discount", "commercial", "fee"]):
            return "pricing"
        if any(term in lowered for term in ["implementation", "timeline", "migration", "integration", "onboarding"]):
            return "implementation"
        if any(term in lowered for term in ["contract", "liability", "indemnity", "legal"]):
            return "legal"
        return "proposal"

    def _priority(self, severity: str) -> str:
        return "high" if severity in {"critical", "high"} else "medium" if severity == "medium" else "low"

    def _rank(self, priority: str) -> int:
        return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(priority, 1)

    def _query(self, *parts: str) -> str:
        return " ".join(part for part in parts if part).strip()

    def _clip(self, text: str, limit: int) -> str:
        compact = " ".join(text.split())
        return compact if len(compact) <= limit else f"{compact[: limit - 3].rstrip()}..."

    def _slug(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:72] or "item"
