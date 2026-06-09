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
    ComplianceEvidenceMatrixResponse,
    ProcurementApprovalPackResponse,
    ProcurementQuestionRiskItem,
    ProcurementQuestionRiskResponse,
)
from app.models.domain import Citation, RequirementMatrixRow, ResponseMemoryMatch, ReviewFinding, TokenUsage
from app.repositories.memory import InMemoryRepository
from app.services.compliance import ComplianceControlMappingService
from app.services.customer_intelligence import CustomerIntelligenceService
from app.services.retrieval import RetrievalService
from app.services.review_board import RfpReviewBoardService

SENSITIVE_CATEGORIES = {"security", "privacy", "legal", "commercial", "ai_governance", "disaster_recovery"}


class ProcurementQuestionRiskService:
    def __init__(
        self,
        repo: InMemoryRepository,
        settings: Settings,
        retrieval: RetrievalService,
        customer_intelligence: CustomerIntelligenceService,
        review_board: RfpReviewBoardService,
        compliance: ComplianceControlMappingService,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.retrieval = retrieval
        self.customer_intelligence = customer_intelligence
        self.review_board = review_board
        self.compliance = compliance

    async def question_risk(
        self,
        trace_id: str,
        analysis: AnalyzeResponse,
        requirement_matrix: list[RequirementMatrixRow],
        review_findings: list[ReviewFinding] | None = None,
    ) -> ProcurementQuestionRiskResponse:
        compliance_matrix = self.compliance.evidence_matrix(
            f"{trace_id}-compliance",
            analysis=analysis,
            requirement_matrix=requirement_matrix,
            review_findings=review_findings or [],
        )
        questions = [
            await self._question_item(spec, trace_id, compliance_matrix)
            for spec in self._question_specs()
        ]
        return ProcurementQuestionRiskResponse(
            title="Procurement Q&A Risk Simulator + Approval Workflow",
            questions=questions,
            coverage_summary=self._coverage_summary(questions, compliance_matrix),
            approval_summary=self._approval_summary(questions),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def approval_pack(
        self,
        trace_id: str,
        question_risk: ProcurementQuestionRiskResponse,
        write_artifact: bool = True,
    ) -> ProcurementApprovalPackResponse:
        pack = self._pack_payload(trace_id, question_risk)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "procurement_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"procurement_approval_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"procurement_approval_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["procurement_approval_markdown"] = artifact_path
            pack["artifact_paths"]["procurement_approval_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ProcurementApprovalPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            question_risk=question_risk,
            trace_id=trace_id,
        )

    async def _question_item(
        self,
        spec: dict[str, Any],
        trace_id: str,
        compliance_matrix: ComplianceEvidenceMatrixResponse,
    ) -> ProcurementQuestionRiskItem:
        citations = await self.retrieval.search(spec["query"], top_k=4)
        citations = self._filtered_citations(citations, spec)
        memory_matches = self.customer_intelligence.search_response_memory(
            spec["query"],
            f"{trace_id}-{spec['id']}-memory",
            category=spec.get("memory_category"),
            customer_profile_id="regulated_healthcare",
            top_k=2,
        )
        evidence_gaps = self._evidence_gaps(spec, citations, compliance_matrix)
        draft_answer = self._draft_answer(spec, citations, memory_matches, evidence_gaps)
        unsupported_claim = bool(spec.get("unsupported_claim")) or self._unsupported_from_text(spec, citations)
        answer_review = self.review_board.review_answer(
            spec["question"],
            draft_answer,
            citations,
            evidence_gaps,
            TokenUsage(input_tokens=120 + len(spec["question"].split()), output_tokens=80),
            f"{trace_id}-{spec['id']}-review",
        )
        review_unsupported = any(finding.category == "unsupported_claim" for finding in answer_review.findings)
        unsupported_claim = unsupported_claim or review_unsupported
        evidence_support = self._evidence_support(spec, citations, evidence_gaps)
        risk_level = self._risk_level(spec, evidence_support, unsupported_claim, answer_review.findings)
        approval_status = self._approval_status(spec, risk_level, evidence_support, unsupported_claim)
        return ProcurementQuestionRiskItem(
            question_id=spec["id"],
            question_type=spec["question_type"],
            category=spec["category"],
            question=spec["question"],
            risk_level=risk_level,
            required_reviewer_role=spec["reviewer_role"],
            approval_status=approval_status,
            evidence_support=evidence_support,
            unsupported_claim_flag=unsupported_claim,
            citations=citations,
            snippets=self._snippets(citations),
            approved_memory_matches=memory_matches,
            draft_answer=draft_answer,
            reviewer_checklist=self._reviewer_checklist(spec, approval_status, evidence_support),
            escalation_owner=spec["escalation_owner"],
            evidence_gaps=evidence_gaps,
            approval_rationale=self._approval_rationale(spec, approval_status, evidence_support, unsupported_claim),
            review_findings=answer_review.findings,
        )

    def _filtered_citations(self, citations: list[Citation], spec: dict[str, Any]) -> list[Citation]:
        if not citations:
            return []
        filenames = set(spec.get("priority_files", []))
        if not filenames:
            return citations
        priority = [citation for citation in citations if citation.filename in filenames]
        return priority or citations[:2]

    def _evidence_gaps(
        self,
        spec: dict[str, Any],
        citations: list[Citation],
        compliance_matrix: ComplianceEvidenceMatrixResponse,
    ) -> list[str]:
        gaps: list[str] = []
        present_files = {citation.filename for citation in citations}
        missing_files = [filename for filename in spec.get("priority_files", []) if filename not in present_files]
        if missing_files:
            gaps.append("Priority evidence not retrieved: " + ", ".join(missing_files))
        if not citations:
            gaps.append("No approved local citation supports this procurement question.")
        if spec.get("requires_contract_approval"):
            gaps.append("Customer-specific contract or order-form approval is required before commitment.")
        relevant_controls = [
            mapping
            for mapping in compliance_matrix.control_mappings
            if any(term in mapping.control_family.lower() for term in spec.get("control_terms", []))
        ]
        for mapping in relevant_controls:
            gaps.extend(mapping.missing_evidence_warnings[:2])
            gaps.extend(mapping.unsupported_claim_flags[:2])
        return self._unique(gaps)

    def _draft_answer(
        self,
        spec: dict[str, Any],
        citations: list[Citation],
        memory_matches: list[ResponseMemoryMatch],
        evidence_gaps: list[str],
    ) -> str:
        if spec.get("unsupported_claim") or not citations:
            return (
                f"Do not claim support for this {spec['question_type']} ask yet. "
                "The local evidence pack does not contain enough approved proof, so the response should state the gap "
                f"and route the item to {spec['reviewer_role']}."
            )
        memory_text = memory_matches[0].text if memory_matches else spec["safe_answer"]
        sources = ", ".join(citation.filename for citation in citations[:2])
        if evidence_gaps:
            return (
                f"{memory_text} Use only qualified language backed by {sources}. "
                f"Before submission, resolve: {'; '.join(evidence_gaps[:2])}."
            )
        return f"{memory_text} Evidence is currently supported by {sources}."

    def _unsupported_from_text(self, spec: dict[str, Any], citations: list[Citation]) -> bool:
        lowered = spec["question"].lower()
        source_text = " ".join(f"{citation.filename} {citation.snippet}" for citation in citations).lower()
        unsupported_terms = spec.get("unsupported_terms", [])
        return any(term in lowered and term not in source_text for term in unsupported_terms)

    def _evidence_support(
        self,
        spec: dict[str, Any],
        citations: list[Citation],
        evidence_gaps: list[str],
    ) -> str:
        if not citations:
            return "missing"
        priority_files = set(spec.get("priority_files", []))
        if priority_files and not priority_files.intersection({citation.filename for citation in citations}):
            return "missing"
        if evidence_gaps and not all("customer-specific" in gap.lower() for gap in evidence_gaps):
            return "partial"
        return "supported"

    def _risk_level(
        self,
        spec: dict[str, Any],
        evidence_support: str,
        unsupported_claim: bool,
        findings: list[ReviewFinding],
    ) -> str:
        if unsupported_claim or evidence_support == "missing":
            return "high"
        if any(finding.severity == "high" for finding in findings):
            return "high"
        if spec["base_risk"] == "high" or evidence_support == "partial":
            return "high" if spec["category"] in SENSITIVE_CATEGORIES else "medium"
        return spec["base_risk"]

    def _approval_status(
        self,
        spec: dict[str, Any],
        risk_level: str,
        evidence_support: str,
        unsupported_claim: bool,
    ) -> str:
        if unsupported_claim or evidence_support == "missing":
            return "blocked"
        if spec["category"] in SENSITIVE_CATEGORIES or spec.get("requires_contract_approval"):
            return "requires_reviewer_approval"
        if risk_level == "low" and evidence_support == "supported":
            return "auto_ready"
        return "requires_reviewer_approval"

    def _reviewer_checklist(
        self,
        spec: dict[str, Any],
        approval_status: str,
        evidence_support: str,
    ) -> list[str]:
        checklist = [
            f"Confirm cited snippets answer the {spec['question_type']} question exactly.",
            "Verify no customer-specific promise is introduced beyond approved evidence.",
            f"Record {spec['reviewer_role']} signoff before external use when approval is required.",
        ]
        if evidence_support != "supported":
            checklist.append("Attach additional evidence or rewrite with a missing-evidence caveat.")
        if approval_status == "blocked":
            checklist.append("Block the draft answer until the gap has an owner-approved exception.")
        return checklist

    def _approval_rationale(
        self,
        spec: dict[str, Any],
        approval_status: str,
        evidence_support: str,
        unsupported_claim: bool,
    ) -> str:
        if approval_status == "blocked":
            return "Blocked because the answer is unsupported or missing local evidence."
        if approval_status == "auto_ready":
            return "Auto-ready because the question is low risk and backed by retrieved local evidence."
        if unsupported_claim:
            return "Requires approval because unsupported-claim detection fired."
        return (
            f"Requires {spec['reviewer_role']} approval because {spec['category']} responses can create "
            f"customer-facing commitments even when evidence support is {evidence_support}."
        )

    def _coverage_summary(
        self,
        questions: list[ProcurementQuestionRiskItem],
        compliance_matrix: ComplianceEvidenceMatrixResponse,
    ) -> dict[str, Any]:
        evidence_counts = Counter(question.evidence_support for question in questions)
        risk_counts = Counter(question.risk_level for question in questions)
        category_counts = Counter(question.category for question in questions)
        supported = evidence_counts.get("supported", 0)
        covered = supported + evidence_counts.get("partial", 0)
        return {
            "question_count": len(questions),
            "question_types": [question.question_type for question in questions],
            "categories": dict(sorted(category_counts.items())),
            "risk_counts": dict(sorted(risk_counts.items())),
            "evidence_support_counts": dict(sorted(evidence_counts.items())),
            "evidence_supported_count": supported,
            "evidence_supported_or_partial_count": covered,
            "coverage_ratio": round(covered / len(questions), 2) if questions else 0,
            "unsupported_claim_count": sum(question.unsupported_claim_flag for question in questions),
            "citation_count": sum(len(question.citations) for question in questions),
            "compliance_control_coverage": compliance_matrix.coverage_summary,
        }

    def _approval_summary(self, questions: list[ProcurementQuestionRiskItem]) -> dict[str, Any]:
        status_counts = Counter(question.approval_status for question in questions)
        reviewer_counts = Counter(question.required_reviewer_role for question in questions)
        return {
            "status_counts": dict(sorted(status_counts.items())),
            "auto_ready_count": status_counts.get("auto_ready", 0),
            "approvals_required_count": status_counts.get("requires_reviewer_approval", 0),
            "blocked_count": status_counts.get("blocked", 0),
            "reviewer_role_counts": dict(sorted(reviewer_counts.items())),
            "high_risk_question_ids": [question.question_id for question in questions if question.risk_level == "high"],
            "blocked_question_ids": [question.question_id for question in questions if question.approval_status == "blocked"],
        }

    def _pack_payload(
        self,
        trace_id: str,
        question_risk: ProcurementQuestionRiskResponse,
    ) -> dict[str, Any]:
        high_risk_questions = [
            question.model_dump(mode="json")
            for question in question_risk.questions
            if question.risk_level == "high"
        ]
        approved_or_blocked = [
            {
                "question_id": question.question_id,
                "question_type": question.question_type,
                "approval_status": question.approval_status,
                "draft_answer": question.draft_answer,
                "reviewer": question.required_reviewer_role,
                "rationale": question.approval_rationale,
            }
            for question in question_risk.questions
            if question.approval_status in {"auto_ready", "blocked", "requires_reviewer_approval"}
        ]
        return {
            "trace_id": trace_id,
            "title": "Procurement Q&A Approval Workflow Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": {
                "coverage_summary": question_risk.coverage_summary,
                "approval_summary": question_risk.approval_summary,
            },
            "high_risk_questions": high_risk_questions,
            "approved_blocked_draft_answers": approved_or_blocked,
            "reviewer_checklist": self._pack_reviewer_checklist(question_risk.questions),
            "escalation_owners": self._escalation_owners(question_risk.questions),
            "evidence_gaps": self._pack_evidence_gaps(question_risk.questions),
            "local_proof_commands": question_risk.local_proof_commands,
            "limitations": question_risk.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        approval = pack["summary"]["approval_summary"]
        coverage = pack["summary"]["coverage_summary"]
        lines = [
            "# Procurement Q&A Approval Workflow Pack",
            "",
            "## Approval Workflow Summary",
            "",
            f"- Questions: {coverage['question_count']}",
            f"- Evidence coverage ratio: {coverage['coverage_ratio']}",
            f"- Auto-ready: {approval['auto_ready_count']}",
            f"- Approvals required: {approval['approvals_required_count']}",
            f"- Blocked: {approval['blocked_count']}",
            f"- Unsupported claims: {coverage['unsupported_claim_count']}",
            "",
            "## High-Risk Questions",
            "",
            "| ID | Type | Category | Risk | Reviewer | Status | Evidence | Unsupported |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for question in pack["high_risk_questions"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(question["question_id"]),
                        self._md(question["question_type"]),
                        self._md(question["category"]),
                        self._md(question["risk_level"]),
                        self._md(question["required_reviewer_role"]),
                        self._md(question["approval_status"]),
                        self._md(question["evidence_support"]),
                        self._md(question["unsupported_claim_flag"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Approved and Blocked Draft Answers", ""])
        for item in pack["approved_blocked_draft_answers"]:
            lines.extend(
                [
                    f"### {item['question_id']} - {item['question_type']}",
                    "",
                    f"- Status: {item['approval_status']}",
                    f"- Reviewer: {item['reviewer']}",
                    f"- Rationale: {item['rationale']}",
                    "",
                    item["draft_answer"],
                    "",
                ]
            )
        lines.extend(["## Reviewer Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_checklist"])
        lines.extend(["", "## Escalation Owners", ""])
        for owner in pack["escalation_owners"]:
            lines.append(
                f"- {owner['owner']}: {owner['question_count']} questions, "
                f"blocked={owner['blocked_count']}, approval_required={owner['approval_required_count']}"
            )
        lines.extend(["", "## Evidence Gaps", ""])
        if pack["evidence_gaps"]:
            lines.extend(
                f"- {gap['question_id']} ({gap['owner']}): {gap['gap']}"
                for gap in pack["evidence_gaps"]
            )
        else:
            lines.append("- None")
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Procurement Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _pack_reviewer_checklist(self, questions: list[ProcurementQuestionRiskItem]) -> list[str]:
        checklist = [
            "Review every blocked and high-risk buyer question before customer submission.",
            "Approve only answers with cited local evidence or explicit exception wording.",
            "Confirm legal/commercial/security commitments match customer contract and DPA boundaries.",
            "Capture reviewer, date, source files, and unresolved limitations in the RFP workspace.",
        ]
        for question in questions:
            if question.approval_status != "auto_ready":
                checklist.append(f"{question.question_id}: {question.required_reviewer_role} signoff required.")
        return self._unique(checklist)

    def _escalation_owners(self, questions: list[ProcurementQuestionRiskItem]) -> list[dict[str, Any]]:
        grouped: dict[str, list[ProcurementQuestionRiskItem]] = {}
        for question in questions:
            grouped.setdefault(question.escalation_owner, []).append(question)
        return [
            {
                "owner": owner,
                "question_count": len(rows),
                "blocked_count": sum(row.approval_status == "blocked" for row in rows),
                "approval_required_count": sum(row.approval_status == "requires_reviewer_approval" for row in rows),
                "question_ids": [row.question_id for row in rows],
            }
            for owner, rows in sorted(grouped.items())
        ]

    def _pack_evidence_gaps(self, questions: list[ProcurementQuestionRiskItem]) -> list[dict[str, str]]:
        return [
            {
                "question_id": question.question_id,
                "question_type": question.question_type,
                "owner": question.escalation_owner,
                "gap": gap,
            }
            for question in questions
            for gap in question.evidence_gaps
        ]

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

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/procurement/question-risk" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/procurement/approval-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python scripts\\dashboard_smoke.py",
            "python -m app.demo",
            (
                'rg "procurement/question-risk|procurement/approval-pack|Procurement Q&A|Approval Workflow|'
                'procurement_packs|question risk" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\procurement_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The simulator is deterministic and local; it does not replace a real procurement, legal, or security review workflow.",
            "Evidence support is based on sample documents and in-memory retrieval, not live GRC, CRM, ticketing, contract, or billing systems.",
            "Approval statuses model triage decisions; they do not create legally binding approvals or customer commitments.",
            "Unsupported-claim flags are intentionally conservative so reviewers can inspect blocked answers before reuse.",
        ]

    def _question_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "pq_security_architecture",
                "question_type": "security architecture",
                "category": "security",
                "question": "Describe the security architecture, SSO, MFA, encryption, and audit logging controls.",
                "query": "security architecture SSO MFA encryption audit logging role based access TLS AES-256",
                "safe_answer": "The platform uses documented identity, access, encryption, and audit controls for enterprise response workflows.",
                "reviewer_role": "Security Architect",
                "escalation_owner": "security",
                "priority_files": ["security_policy.md", "ai_governance_security.md"],
                "control_terms": ["access", "encryption", "audit"],
                "memory_category": "security",
                "base_risk": "high",
            },
            {
                "id": "pq_privacy_dpa",
                "question_type": "privacy/DPA",
                "category": "privacy",
                "question": "Can you provide DPA, subprocessors, retention, deletion, and data processing terms?",
                "query": "DPA data processing subprocessors retention deletion personal data privacy",
                "safe_answer": "Privacy responses should use DPA-backed language covering processing roles, retention, deletion, and subprocessor review.",
                "reviewer_role": "Legal Privacy Reviewer",
                "escalation_owner": "legal",
                "priority_files": ["dpa_privacy_policy.md", "compliance_policy.md"],
                "control_terms": ["privacy", "data"],
                "memory_category": "compliance",
                "base_risk": "high",
            },
            {
                "id": "pq_sla_support",
                "question_type": "SLA/support",
                "category": "support",
                "question": "What SLA, support tiers, severity response targets, and uptime commitments are available?",
                "query": "SLA support tiers severity response targets uptime availability customer success",
                "safe_answer": "Support terms should cite approved support tiers and distinguish response targets from contractual uptime guarantees.",
                "reviewer_role": "Customer Success Lead",
                "escalation_owner": "customer_success",
                "priority_files": ["sla_support_policy.md", "customer_success_onboarding.md"],
                "control_terms": ["sla"],
                "memory_category": "implementation",
                "base_risk": "medium",
                "requires_contract_approval": True,
                "unsupported_terms": ["99.99", "guarantee"],
            },
            {
                "id": "pq_disaster_recovery",
                "question_type": "disaster recovery",
                "category": "disaster_recovery",
                "question": "Summarize disaster recovery, backup, RTO, RPO, and business continuity posture.",
                "query": "disaster recovery backup RTO RPO business continuity tabletop recovery procedure",
                "safe_answer": "Disaster recovery language should cite the DR plan and avoid over-promising beyond documented RTO/RPO boundaries.",
                "reviewer_role": "Engineering DR Owner",
                "escalation_owner": "engineering",
                "priority_files": ["disaster_recovery_plan.md"],
                "control_terms": ["disaster"],
                "memory_category": "security",
                "base_risk": "high",
            },
            {
                "id": "pq_ai_governance",
                "question_type": "AI governance/model claims",
                "category": "ai_governance",
                "question": "How are model providers governed, and can you claim prompts are never used for training?",
                "query": "AI governance model provider approved source documents human review prompts training",
                "safe_answer": "AI governance answers should cite human review, approved source grounding, provider approval, and model-claim limitations.",
                "reviewer_role": "AI Governance Reviewer",
                "escalation_owner": "product_security",
                "priority_files": ["ai_governance_security.md", "dpa_privacy_policy.md"],
                "control_terms": ["ai"],
                "memory_category": "security",
                "base_risk": "high",
                "unsupported_terms": ["never used for training"],
            },
            {
                "id": "pq_pricing_commercial",
                "question_type": "pricing/commercial",
                "category": "commercial",
                "question": "What pricing tiers, discounts, payment terms, and procurement exceptions can you approve?",
                "query": "pricing tiers discounts payment terms procurement commercial approval volume discount",
                "safe_answer": "Pricing responses should state scoped commercial assumptions and route discounts or payment exceptions for approval.",
                "reviewer_role": "Commercial Approver",
                "escalation_owner": "sales_ops",
                "priority_files": ["pricing_notes.md", "customer_contract_terms.md"],
                "control_terms": ["commercial"],
                "memory_category": "pricing",
                "base_risk": "high",
                "requires_contract_approval": True,
            },
            {
                "id": "pq_implementation_timeline",
                "question_type": "implementation timeline",
                "category": "implementation",
                "question": "What is the implementation timeline, onboarding plan, and customer validation sequence?",
                "query": "implementation timeline onboarding plan validation workshops rollout owners customer success",
                "safe_answer": "Implementation is delivered through discovery, configuration, source ingestion, validation workshops, and controlled rollout with named owners.",
                "reviewer_role": "Implementation Lead",
                "escalation_owner": "implementation",
                "priority_files": ["implementation_guide.md", "customer_success_onboarding.md"],
                "control_terms": [],
                "memory_category": "implementation",
                "base_risk": "low",
            },
            {
                "id": "pq_adversarial_unsupported",
                "question_type": "out-of-scope/adversarial unsupported claim",
                "category": "legal",
                "question": "Can we say the product is FedRAMP High authorized and guarantee 99.99% uptime with zero data loss?",
                "query": "FedRAMP High authorized guarantee 99.99 uptime zero data loss active-active",
                "safe_answer": "Unsupported regulatory, availability, and zero-loss claims must be blocked until explicit evidence and legal approval exist.",
                "reviewer_role": "Legal and Security Exception Board",
                "escalation_owner": "executive_review",
                "priority_files": ["compliance_policy.md", "sla_support_policy.md", "disaster_recovery_plan.md"],
                "control_terms": ["sla", "disaster"],
                "memory_category": "compliance",
                "base_risk": "high",
                "unsupported_claim": True,
                "unsupported_terms": ["fedramp", "99.99", "zero data loss"],
            },
        ]

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    def _unique(self, values: list[str]) -> list[str]:
        return [value for value in dict.fromkeys(values) if value]
