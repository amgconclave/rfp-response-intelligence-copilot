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
    ContractRiskResponse,
    ProcurementQuestionRiskResponse,
    ProcurementRiskDeskItem,
    ProcurementRiskDeskPackResponse,
    ProcurementRiskDeskResponse,
)
from app.models.domain import Citation, RequirementMatrixRow, ReviewFinding
from app.services.retrieval import RetrievalService


class ProcurementRiskDeskService:
    """Deterministic packet-level procurement risk desk for local portfolio mode."""

    def __init__(self, settings: Settings, retrieval: RetrievalService) -> None:
        self.settings = settings
        self.retrieval = retrieval

    async def risk_desk(
        self,
        trace_id: str,
        analysis: AnalyzeResponse,
        requirement_matrix: list[RequirementMatrixRow],
        review_findings: list[ReviewFinding] | None = None,
        contract_risk: ContractRiskResponse | None = None,
        win_strategy: Any | None = None,
        procurement_risk: ProcurementQuestionRiskResponse | None = None,
    ) -> ProcurementRiskDeskResponse:
        specs = self._risk_specs()
        risks = [
            await self._risk_item(
                spec,
                analysis,
                requirement_matrix,
                review_findings or [],
                contract_risk,
                win_strategy,
                procurement_risk,
            )
            for spec in specs
        ]
        risks = sorted(risks, key=lambda item: (-item.risk_score, item.category))
        return ProcurementRiskDeskResponse(
            title="Procurement Risk Desk Pack",
            risks=risks,
            summary=self._summary(risks),
            owner_routing=self._owner_routing(risks),
            workflow_stages=self._workflow_stages(risks),
            human_review_queue=self._human_review_queue(risks),
            trace_spans=self._trace_spans(trace_id, risks),
            governance_summary=self._governance_summary(risks),
            packet_sources=self._packet_sources(analysis, contract_risk),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def risk_desk_pack(
        self,
        trace_id: str,
        risk_desk: ProcurementRiskDeskResponse,
        write_artifact: bool = True,
    ) -> ProcurementRiskDeskPackResponse:
        pack = self._pack_payload(trace_id, risk_desk)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "procurement_risk_desk"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"procurement_risk_desk_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"procurement_risk_desk_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["risk_desk_markdown"] = artifact_path
            pack["artifact_paths"]["risk_desk_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ProcurementRiskDeskPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            risk_desk=risk_desk,
            trace_id=trace_id,
        )

    async def _risk_item(
        self,
        spec: dict[str, Any],
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
        contract_risk: ContractRiskResponse | None,
        win_strategy: Any | None,
        procurement_risk: ProcurementQuestionRiskResponse | None,
    ) -> ProcurementRiskDeskItem:
        citations = await self.retrieval.search(spec["query"], top_k=4)
        citations = self._prioritize_citations(citations, spec)
        signals = self._signals(spec, analysis, matrix, findings, contract_risk, win_strategy, procurement_risk)
        evidence_gaps = self._evidence_gaps(spec, citations, contract_risk, procurement_risk)
        score = self._score(spec, signals, evidence_gaps, citations)
        severity = "critical" if score >= 85 else "high" if score >= 70 else "medium" if score >= 45 else "low"
        status = "blocked" if severity == "critical" or not citations else "needs_owner_review" if severity in {"high", "medium"} else "monitor"
        return ProcurementRiskDeskItem(
            risk_id=spec["id"],
            category=spec["category"],
            title=spec["title"],
            severity=severity,
            risk_score=score,
            status=status,
            owner_role=spec["owner_role"],
            reviewer_role=spec["reviewer_role"],
            due_hint=spec["due_hint"],
            source_signals=signals or [f"No strong {spec['category']} signal found in the local packet."],
            rationale=self._rationale(spec, severity, signals, evidence_gaps),
            recommended_actions=self._actions(spec, status),
            evidence_gaps=evidence_gaps,
            related_requirement_ids=self._related_requirement_ids(spec, matrix),
            related_contract_clause_ids=self._related_contract_clause_ids(spec, contract_risk),
            citations=citations,
            snippets=self._snippets(citations),
        )

    def _signals(
        self,
        spec: dict[str, Any],
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
        contract_risk: ContractRiskResponse | None,
        win_strategy: Any | None,
        procurement_risk: ProcurementQuestionRiskResponse | None,
    ) -> list[str]:
        terms = spec["terms"]
        signals: list[str] = []
        text_fields = [*analysis.risks, *analysis.missing_information, *analysis.pricing_mentions, *analysis.compliance_asks, *analysis.security_questions]
        for value in text_fields:
            if self._contains(value, terms):
                signals.append(f"RFP analysis signal: {self._clip(value, 150)}")
        for row in matrix:
            if self._contains(" ".join([row.category, row.requirement_text, *row.missing_evidence]), terms):
                state = "blocked" if row.status == "blocked" else row.risk_level
                signals.append(f"Requirement {row.requirement_id} ({state}): {self._clip(row.requirement_text, 130)}")
        for finding in findings:
            if self._contains(" ".join([finding.category, finding.message, finding.recommendation]), terms):
                signals.append(f"Review finding {finding.severity}: {self._clip(finding.message, 130)}")
        if contract_risk:
            for clause in contract_risk.risky_clauses:
                if clause.category in spec.get("contract_categories", set()) or self._contains(clause.title + " " + clause.clause_text, terms):
                    signals.append(f"Contract {clause.clause_id} ({clause.risk_level}): {clause.title}")
        if win_strategy and spec["category"] == "pricing":
            pricing = getattr(win_strategy, "pricing_risk", {}) or {}
            signals.extend(str(driver) for driver in pricing.get("risk_drivers", [])[:4])
            signals.append(f"Pricing risk level from win strategy: {pricing.get('risk_level', 'unknown')}.")
        if procurement_risk:
            for question in procurement_risk.questions:
                if question.category in spec.get("procurement_categories", set()) or self._contains(question.question, terms):
                    signals.append(f"Procurement Q&A {question.question_id} ({question.approval_status}): {question.question_type}")
        return self._unique(signals)[:10]

    def _evidence_gaps(
        self,
        spec: dict[str, Any],
        citations: list[Citation],
        contract_risk: ContractRiskResponse | None,
        procurement_risk: ProcurementQuestionRiskResponse | None,
    ) -> list[str]:
        gaps: list[str] = []
        present = {citation.filename for citation in citations}
        missing_priority = [filename for filename in spec.get("priority_files", []) if filename not in present]
        if missing_priority:
            gaps.append("Priority desk evidence not retrieved: " + ", ".join(missing_priority))
        if not citations:
            gaps.append("No approved local source supports this risk desk category.")
        if contract_risk and spec.get("contract_categories"):
            for warning in contract_risk.missing_evidence_warnings[:3]:
                if self._contains(warning, spec["terms"]):
                    gaps.append(warning)
        if procurement_risk:
            for question in procurement_risk.questions:
                if question.category in spec.get("procurement_categories", set()):
                    gaps.extend(question.evidence_gaps[:2])
        return self._unique(gaps)[:8]

    def _score(
        self,
        spec: dict[str, Any],
        signals: list[str],
        evidence_gaps: list[str],
        citations: list[Citation],
    ) -> int:
        score = spec["base_score"] + min(30, len(signals) * 5) + min(20, len(evidence_gaps) * 4)
        if not citations:
            score += 18
        if any("blocked" in signal.lower() or "critical" in signal.lower() or "high" in signal.lower() for signal in signals):
            score += 12
        return min(100, score)

    def _summary(self, risks: list[ProcurementRiskDeskItem]) -> dict[str, Any]:
        severity_counts = Counter(risk.severity for risk in risks)
        status_counts = Counter(risk.status for risk in risks)
        category_counts = Counter(risk.category for risk in risks)
        return {
            "risk_count": len(risks),
            "critical_count": severity_counts.get("critical", 0),
            "high_count": severity_counts.get("high", 0),
            "blocked_count": status_counts.get("blocked", 0),
            "needs_owner_review_count": status_counts.get("needs_owner_review", 0),
            "category_counts": dict(sorted(category_counts.items())),
            "severity_counts": dict(sorted(severity_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
            "average_risk_score": round(sum(risk.risk_score for risk in risks) / len(risks), 1) if risks else 0,
            "citation_count": sum(len(risk.citations) for risk in risks),
            "evidence_gap_count": sum(len(risk.evidence_gaps) for risk in risks),
        }

    def _owner_routing(self, risks: list[ProcurementRiskDeskItem]) -> list[dict[str, Any]]:
        grouped: dict[str, list[ProcurementRiskDeskItem]] = {}
        for risk in risks:
            grouped.setdefault(risk.owner_role, []).append(risk)
        return [
            {
                "owner_role": owner,
                "risk_count": len(rows),
                "blocked_count": sum(row.status == "blocked" for row in rows),
                "highest_severity": self._highest_severity(rows),
                "risk_ids": [row.risk_id for row in rows],
                "next_action": self._owner_next_action(owner, rows),
            }
            for owner, rows in sorted(grouped.items())
        ]

    def _workflow_stages(self, risks: list[ProcurementRiskDeskItem]) -> list[dict[str, Any]]:
        blocked = [risk.risk_id for risk in risks if risk.status == "blocked" or risk.severity == "critical"]
        owner_review = [risk.risk_id for risk in risks if risk.status == "needs_owner_review"]
        ready = [risk.risk_id for risk in risks if risk.status == "monitor"]
        return [
            {
                "stage_id": "prd_stage_1_packet_scan",
                "name": "Packet risk scan",
                "status": "complete",
                "checkpoint_id": "procurement-risk-desk.packet-scan.v1",
                "resumable": True,
                "blocked_risks": [],
                "governance_pattern": "durable_workflow",
                "exit_criteria": "All risk categories scored with source signals and citation diagnostics.",
            },
            {
                "stage_id": "prd_stage_2_owner_review",
                "name": "Owner review and evidence closure",
                "status": "blocked" if blocked else "in_progress" if owner_review else "complete",
                "checkpoint_id": "procurement-risk-desk.owner-review.v1",
                "resumable": True,
                "blocked_risks": blocked,
                "governance_pattern": "human_in_the_loop",
                "exit_criteria": "Every high or critical risk has an owner decision, cited support, or explicit exception.",
            },
            {
                "stage_id": "prd_stage_3_submission_release",
                "name": "Procurement submission release gate",
                "status": "blocked" if blocked else "waiting" if owner_review else "ready",
                "checkpoint_id": "procurement-risk-desk.release-gate.v1",
                "resumable": True,
                "blocked_risks": blocked or owner_review,
                "governance_pattern": "governance",
                "exit_criteria": "No blocked risk remains and reviewer approvals are attached to customer-facing commitments.",
                "ready_risks": ready,
            },
        ]

    def _human_review_queue(self, risks: list[ProcurementRiskDeskItem]) -> list[dict[str, Any]]:
        queue = []
        for risk in risks:
            if risk.status == "monitor" and risk.severity == "low":
                continue
            queue.append(
                {
                    "risk_id": risk.risk_id,
                    "category": risk.category,
                    "owner_role": risk.owner_role,
                    "reviewer_role": risk.reviewer_role,
                    "priority": self._review_priority(risk),
                    "approval_gate": self._approval_gate(risk),
                    "sla_hint": risk.due_hint,
                    "evidence_gap_count": len(risk.evidence_gaps),
                    "citation_count": len(risk.citations),
                    "required_decision": self._required_decision(risk),
                }
            )
        return sorted(queue, key=lambda row: (row["priority"], row["risk_id"]))

    def _trace_spans(self, trace_id: str, risks: list[ProcurementRiskDeskItem]) -> list[dict[str, Any]]:
        return [
            {
                "span_id": f"{trace_id}.procurement-risk-desk.scan",
                "operation": "packet_category_scan",
                "status": "ok",
                "risk_count": len(risks),
                "evidence_gap_count": sum(len(risk.evidence_gaps) for risk in risks),
                "citation_count": sum(len(risk.citations) for risk in risks),
                "pattern": "trace_analysis",
            },
            {
                "span_id": f"{trace_id}.procurement-risk-desk.owner-routing",
                "operation": "owner_review_routing",
                "status": "blocked" if any(risk.status == "blocked" for risk in risks) else "ok",
                "risk_count": sum(risk.status != "monitor" for risk in risks),
                "evidence_gap_count": sum(len(risk.evidence_gaps) for risk in risks if risk.status != "monitor"),
                "citation_count": sum(len(risk.citations) for risk in risks if risk.status != "monitor"),
                "pattern": "human_in_the_loop",
            },
            {
                "span_id": f"{trace_id}.procurement-risk-desk.release-gate",
                "operation": "submission_release_gate",
                "status": "blocked" if any(risk.status == "blocked" for risk in risks) else "ready",
                "risk_count": sum(risk.severity in {"critical", "high"} for risk in risks),
                "evidence_gap_count": sum(len(risk.evidence_gaps) for risk in risks if risk.severity in {"critical", "high"}),
                "citation_count": sum(len(risk.citations) for risk in risks if risk.severity in {"critical", "high"}),
                "pattern": "governance",
            },
        ]

    def _governance_summary(self, risks: list[ProcurementRiskDeskItem]) -> dict[str, Any]:
        queue = self._human_review_queue(risks)
        blocked = [risk.risk_id for risk in risks if risk.status == "blocked"]
        approval_required = [risk.risk_id for risk in risks if risk.status in {"blocked", "needs_owner_review"}]
        return {
            "workflow_status": "blocked" if blocked else "ready_for_owner_review" if approval_required else "ready",
            "implemented_patterns": ["durable_workflows", "human_in_the_loop", "trace_analysis", "governance"],
            "approval_required_count": len(approval_required),
            "human_review_queue_count": len(queue),
            "blocked_risk_ids": blocked,
            "release_gate": "hold_submission" if blocked else "owner_review_required" if approval_required else "can_submit",
            "state_storage": "storage/procurement_risk_desk/*.json",
        }

    def _pack_payload(self, trace_id: str, risk_desk: ProcurementRiskDeskResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Procurement Risk Desk Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": risk_desk.summary,
            "risks": [risk.model_dump(mode="json") for risk in risk_desk.risks],
            "owner_routing": risk_desk.owner_routing,
            "workflow_stages": risk_desk.workflow_stages,
            "human_review_queue": risk_desk.human_review_queue,
            "trace_spans": risk_desk.trace_spans,
            "governance_summary": risk_desk.governance_summary,
            "packet_sources": risk_desk.packet_sources,
            "executive_notes": self._executive_notes(risk_desk),
            "local_proof_commands": risk_desk.local_proof_commands,
            "limitations": risk_desk.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Procurement Risk Desk Pack",
            "",
            "## Summary",
            "",
            f"- Risks: {summary['risk_count']}",
            f"- Critical: {summary['critical_count']}",
            f"- High: {summary['high_count']}",
            f"- Blocked: {summary['blocked_count']}",
            f"- Needs owner review: {summary['needs_owner_review_count']}",
            f"- Average risk score: {summary['average_risk_score']}",
            "",
            "## Risk Desk",
            "",
            "| ID | Category | Severity | Score | Status | Owner | Reviewer |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for risk in pack["risks"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(risk["risk_id"]),
                        self._md(risk["category"]),
                        self._md(risk["severity"]),
                        self._md(risk["risk_score"]),
                        self._md(risk["status"]),
                        self._md(risk["owner_role"]),
                        self._md(risk["reviewer_role"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Owner Routing", ""])
        for owner in pack["owner_routing"]:
            lines.append(
                f"- {owner['owner_role']}: {owner['risk_count']} risks, blocked={owner['blocked_count']}, "
                f"highest={owner['highest_severity']}, next={owner['next_action']}"
            )
        lines.extend(["", "## Governance Summary", ""])
        for key, value in pack["governance_summary"].items():
            lines.append(f"- {self._md(key)}: {self._md(value)}")
        lines.extend(["", "## Durable Workflow Gates", ""])
        self._append_dict_table(
            lines,
            pack["workflow_stages"],
            ["stage_id", "name", "status", "checkpoint_id", "resumable", "blocked_risks"],
        )
        lines.extend(["", "## Human Review Queue", ""])
        self._append_dict_table(
            lines,
            pack["human_review_queue"],
            ["risk_id", "owner_role", "reviewer_role", "priority", "approval_gate", "sla_hint"],
        )
        lines.extend(["", "## Trace Analysis", ""])
        self._append_dict_table(
            lines,
            pack["trace_spans"],
            ["span_id", "operation", "status", "risk_count", "evidence_gap_count", "citation_count"],
        )
        lines.extend(["", "## Detailed Risks", ""])
        for risk in pack["risks"]:
            lines.extend(
                [
                    f"### {risk['risk_id']} - {risk['title']}",
                    "",
                    f"- Category: {risk['category']}",
                    f"- Severity: {risk['severity']} ({risk['risk_score']})",
                    f"- Status: {risk['status']}",
                    f"- Owner: {risk['owner_role']}",
                    f"- Reviewer: {risk['reviewer_role']}",
                    f"- Due: {risk['due_hint']}",
                    f"- Rationale: {risk['rationale']}",
                    "",
                    "Signals:",
                ]
            )
            lines.extend(f"- {signal}" for signal in risk["source_signals"])
            lines.append("")
            lines.append("Recommended actions:")
            lines.extend(f"- [ ] {action}" for action in risk["recommended_actions"])
            lines.append("")
            lines.append("Evidence gaps:")
            lines.extend(f"- {gap}" for gap in (risk["evidence_gaps"] or ["None"]))
            lines.append("")
        lines.extend(["## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Risk Desk Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _risk_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "prd_legal_terms",
                "category": "legal",
                "title": "Legal terms and contract fallback risk",
                "terms": {"liability", "indemnity", "termination", "audit", "contract", "redline", "damages"},
                "contract_categories": {"liability", "indemnity", "termination", "audit_rights"},
                "procurement_categories": {"legal"},
                "priority_files": ["customer_contract_terms.md", "compliance_policy.md"],
                "query": "liability indemnity termination audit rights customer contract redline fallback",
                "owner_role": "Legal Counsel",
                "reviewer_role": "Legal Approver",
                "due_hint": "Before proposal redlines or final commercial submission",
                "base_score": 42,
            },
            {
                "id": "prd_pricing_commercial",
                "category": "pricing",
                "title": "Pricing, discount, and payment-term risk",
                "terms": {"pricing", "discount", "payment", "commercial", "net", "tier", "unlimited", "price"},
                "contract_categories": {"pricing_payment"},
                "procurement_categories": {"commercial"},
                "priority_files": ["pricing_notes.md", "customer_contract_terms.md"],
                "query": "pricing discount payment terms procurement exceptions commercial approval",
                "owner_role": "Sales Operations",
                "reviewer_role": "Commercial Approver",
                "due_hint": "Before best-and-final offer or price exception",
                "base_score": 40,
            },
            {
                "id": "prd_data_residency",
                "category": "data_residency",
                "title": "Data residency, region, and cross-border transfer risk",
                "terms": {"data residency", "region", "cross-border", "localization", "subprocessor", "eu", "united states"},
                "contract_categories": {"data_residency", "data_processing"},
                "procurement_categories": {"privacy", "security"},
                "priority_files": ["dpa_privacy_policy.md", "security_policy.md", "compliance_policy.md"],
                "query": "data residency region cross-border transfer subprocessors privacy DPA deployment region",
                "owner_role": "Privacy and Security",
                "reviewer_role": "Privacy Counsel",
                "due_hint": "Before answering residency or subprocessor questionnaire items",
                "base_score": 43,
            },
            {
                "id": "prd_insurance_liability",
                "category": "insurance",
                "title": "Insurance, liability, and coverage attestation risk",
                "terms": {"insurance", "coverage", "liability", "cyber", "certificate", "professional", "errors", "omissions"},
                "contract_categories": {"liability", "indemnity"},
                "procurement_categories": {"legal"},
                "priority_files": ["customer_contract_terms.md", "compliance_policy.md"],
                "query": "insurance coverage cyber liability certificate professional errors omissions contract",
                "owner_role": "Legal Operations",
                "reviewer_role": "Risk and Insurance Reviewer",
                "due_hint": "Before signing supplier onboarding or insurance schedules",
                "base_score": 38,
            },
            {
                "id": "prd_implementation_commitment",
                "category": "implementation",
                "title": "Implementation timeline and delivery commitment risk",
                "terms": {"implementation", "onboarding", "timeline", "rollout", "training", "integration", "migration", "go-live"},
                "contract_categories": {"sla_service_credits"},
                "procurement_categories": {"implementation", "support"},
                "priority_files": ["implementation_guide.md", "customer_success_onboarding.md", "sla_support_policy.md"],
                "query": "implementation timeline onboarding rollout training validation support SLA customer success",
                "owner_role": "Implementation Lead",
                "reviewer_role": "Delivery Owner",
                "due_hint": "Before committing dates, dependencies, or go-live milestones",
                "base_score": 34,
            },
        ]

    def _prioritize_citations(self, citations: list[Citation], spec: dict[str, Any]) -> list[Citation]:
        priority = set(spec.get("priority_files", []))
        if not priority:
            return citations
        preferred = [citation for citation in citations if citation.filename in priority]
        return (preferred + [citation for citation in citations if citation.filename not in priority])[:4]

    def _related_requirement_ids(self, spec: dict[str, Any], matrix: list[RequirementMatrixRow]) -> list[str]:
        return [
            row.requirement_id
            for row in matrix
            if self._contains(" ".join([row.category, row.requirement_text]), spec["terms"])
        ][:8]

    def _related_contract_clause_ids(self, spec: dict[str, Any], contract_risk: ContractRiskResponse | None) -> list[str]:
        if not contract_risk:
            return []
        return [
            clause.clause_id
            for clause in contract_risk.risky_clauses
            if clause.category in spec.get("contract_categories", set())
        ]

    def _actions(self, spec: dict[str, Any], status: str) -> list[str]:
        actions = [
            f"Assign {spec['owner_role']} to validate source evidence and customer-specific constraints.",
            f"Route final wording to {spec['reviewer_role']} before external submission.",
            "Attach retrieved citations or add a missing-evidence caveat to the response workspace.",
        ]
        if status == "blocked":
            actions.insert(0, "Block customer-facing commitments until an exception or approved evidence is attached.")
        return actions

    def _rationale(self, spec: dict[str, Any], severity: str, signals: list[str], evidence_gaps: list[str]) -> str:
        return (
            f"{spec['category']} is rated {severity} because the packet produced {len(signals)} risk signals "
            f"and {len(evidence_gaps)} evidence gaps for owner review."
        )

    def _packet_sources(self, analysis: AnalyzeResponse, contract_risk: ContractRiskResponse | None) -> list[str]:
        sources = ["RFP analysis", "requirement matrix", "review findings", "retrieved local evidence"]
        if analysis.pricing_mentions:
            sources.append("pricing mentions")
        if contract_risk:
            sources.append("contract risk analyzer")
        return sources

    def _highest_severity(self, risks: list[ProcurementRiskDeskItem]) -> str:
        order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        return max((risk.severity for risk in risks), key=lambda severity: order.get(severity, 0), default="low")

    def _owner_next_action(self, owner: str, rows: list[ProcurementRiskDeskItem]) -> str:
        if any(row.status == "blocked" for row in rows):
            return f"{owner} must clear blocked commitments or record an exception."
        return f"{owner} should review routed risks and confirm response wording."

    def _review_priority(self, risk: ProcurementRiskDeskItem) -> int:
        severity_rank = {"critical": 1, "high": 2, "medium": 3, "low": 4}
        return severity_rank.get(risk.severity, 4)

    def _approval_gate(self, risk: ProcurementRiskDeskItem) -> str:
        if risk.status == "blocked":
            return "submission_blocker"
        if risk.severity == "high":
            return "pre_submission_approval"
        if risk.severity == "medium":
            return "owner_attestation"
        return "monitor"

    def _required_decision(self, risk: ProcurementRiskDeskItem) -> str:
        if risk.status == "blocked":
            return "approve_exception_or_attach_evidence"
        if risk.status == "needs_owner_review":
            return "approve_wording_or_request_source"
        return "monitor_for_change"

    def _executive_notes(self, risk_desk: ProcurementRiskDeskResponse) -> list[str]:
        notes = [
            "Use this desk before procurement submission to prevent unsupported legal, commercial, residency, insurance, or delivery commitments.",
            f"Highest-risk categories: {', '.join(risk.category for risk in risk_desk.risks[:3])}.",
        ]
        if risk_desk.summary["blocked_count"]:
            notes.append("Blocked risk rows require owner-approved exception handling before external reuse.")
        return notes

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/procurement/risk-desk" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/procurement/risk-desk-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            "python scripts\\dashboard_smoke.py",
            (
                'rg "procurement/risk-desk|Procurement Risk Desk|procurement_risk_desk" '
                "app dashboard docs README.md tests scripts sample_data Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\procurement_risk_desk -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The desk is deterministic and local; it does not replace live legal, finance, privacy, risk, or delivery approvals.",
            "Insurance detection is based on packet text and contract-risk signals; it is not connected to a live certificate-of-insurance system.",
            "Owner routing is a portfolio workflow model and should be mapped to real enterprise roles before production use.",
            "External services remain optional; all risk desk outputs run with local sample data and mock provider behavior.",
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

    def _contains(self, value: str, terms: set[str]) -> bool:
        lowered = value.lower()
        return any(term in lowered for term in terms)

    def _clip(self, value: str, limit: int = 220) -> str:
        compact = re.sub(r"\s+", " ", value).strip()
        return compact if len(compact) <= limit else compact[: limit - 3].rstrip() + "..."

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    def _unique(self, values: list[str]) -> list[str]:
        return [value for value in dict.fromkeys(values) if value]

    def _append_dict_table(self, lines: list[str], rows: list[dict[str, Any]], fields: list[str]) -> None:
        if not rows:
            lines.append("No rows.")
            return
        lines.append("| " + " | ".join(fields) + " |")
        lines.append("| " + " | ".join("---" for _ in fields) + " |")
        for row in rows:
            lines.append("| " + " | ".join(self._md(row.get(field, "")) for field in fields) + " |")
