from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    ContractRiskResponse,
    DealReadinessScorecardResponse,
    SourceRequestPackResponse,
    WinStrategyResponse,
)
from app.models.domain import EvidenceGap, RequirementMatrixRow, ReviewFinding, StakeholderTask


class EvidenceGapService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_gap_plan(
        self,
        trace_id: str,
        analysis: AnalyzeResponse | None = None,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        review_findings: list[ReviewFinding] | None = None,
        red_team_summary: dict[str, Any] | None = None,
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        win_strategy: WinStrategyResponse | None = None,
        contract_risk: ContractRiskResponse | None = None,
        action_plan: list[StakeholderTask] | None = None,
    ) -> tuple[list[EvidenceGap], dict[str, Any]]:
        matrix = requirement_matrix or []
        findings = review_findings or []
        tasks = action_plan or []
        seeds: list[dict[str, Any]] = []
        for row in matrix:
            if row.missing_evidence or not row.evidence_refs or row.status == "blocked" or row.risk_level == "high":
                seeds.append(self._seed_from_row(row, analysis))
        seeds.extend(self._seeds_from_analysis(analysis))
        seeds.extend(self._seeds_from_findings(findings, matrix, analysis))
        seeds.extend(self._seeds_from_red_team(red_team_summary, analysis))
        seeds.extend(self._seeds_from_readiness(readiness_scorecard, matrix, analysis))
        seeds.extend(self._seeds_from_win_strategy(win_strategy, matrix, analysis))
        seeds.extend(self._seeds_from_contract_risk(contract_risk, analysis))
        seeds.extend(self._seeds_from_tasks(tasks, matrix, analysis))

        merged = self._merge_seeds(seeds)
        ranked = sorted(
            merged,
            key=lambda item: (
                -self._severity_weight(item["severity"]),
                -len(item["source_signals"]),
                -len(item["red_team_risks"]),
                item["owner_team"],
                item["title"],
            ),
        )
        gaps = [
            EvidenceGap(
                gap_id=f"gap_{index:02d}_{self._slug(seed['title'])}",
                priority_rank=index,
                title=seed["title"],
                severity=seed["severity"],
                owner_team=seed["owner_team"],
                missing_source_type=seed["missing_source_type"],
                impacted_sections=seed["impacted_sections"],
                requirement_ids=seed["requirement_ids"],
                contract_clause_ids=seed["contract_clause_ids"],
                due_date_recommendation=seed["due_date_recommendation"],
                suggested_sme_or_source_request=seed["suggested_sme_or_source_request"],
                related_citations=seed["related_citations"],
                red_team_risks=seed["red_team_risks"],
                closure_acceptance_criteria=seed["closure_acceptance_criteria"],
                source_signals=seed["source_signals"],
            )
            for index, seed in enumerate(ranked, start=1)
        ]
        return gaps, self._summary(gaps, matrix, findings, red_team_summary, readiness_scorecard, contract_risk)

    def export_source_request_pack(
        self,
        trace_id: str,
        gaps: list[EvidenceGap],
        analysis: AnalyzeResponse | None = None,
        red_team_summary: dict[str, Any] | None = None,
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        win_strategy: WinStrategyResponse | None = None,
        contract_risk: ContractRiskResponse | None = None,
        write_artifact: bool = True,
    ) -> SourceRequestPackResponse:
        pack = {
            "trace_id": trace_id,
            "summary": self._pack_summary(gaps, analysis, readiness_scorecard, contract_risk),
            "prioritized_gaps": [gap.model_dump(mode="json") for gap in gaps],
            "source_request_emails_tasks": self._source_request_tasks(gaps),
            "owner_matrix": self._owner_matrix(gaps),
            "acceptance_criteria": self._acceptance_criteria(gaps),
            "impacted_response_sections": self._impacted_sections(gaps),
            "red_team_risks": self._red_team_risks(gaps, red_team_summary),
            "readiness_context": self._readiness_context(readiness_scorecard),
            "win_strategy_context": self._win_context(win_strategy),
            "contract_risk_context": self._contract_context(contract_risk),
            "local_commands": [
                "python -m uvicorn app.main:app --reload",
                "streamlit run dashboard/app.py",
                "python -m app.demo",
                "python -m pytest -q",
                "python -m ruff check .",
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/evidence-gaps" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/source-request-pack" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
            ],
            "jd_skills_demonstrated": [
                "Evidence remediation workflow that turns RAG gaps into owner-routed source requests.",
                "Deterministic FastAPI service composition across analysis, review, readiness, win, and contract risk.",
                "Typed local artifact generation for security, legal, sales, and presales coordination.",
                "Red-team and missing-evidence signals converted into closure criteria instead of hidden warnings.",
                "Fully local/mock implementation with reproducible tests, evals, and demo commands.",
            ],
            "interviewer_talking_points": [
                "The copilot now drives missing-evidence closure instead of only drafting responses.",
                (
                    "Gap ranking blends requirement risk, review findings, red-team misses, readiness blockers, "
                    "and contract risk."
                ),
                (
                    "Every source request has an owner, expected artifact type, due recommendation, "
                    "and acceptance criteria."
                ),
                (
                    "The source request pack is local Markdown/JSON, so no email, CRM, SharePoint, "
                    "or Azure dependency is needed."
                ),
                (
                    "The workflow is useful for presales standups because it shows what must be attached "
                    "before submission."
                ),
            ],
        }
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            request_dir = self.settings.storage_dir / "source_requests"
            request_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = request_dir / f"source_request_pack_{safe_trace_id}.md"
            json_path = request_dir / f"source_request_pack_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return SourceRequestPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            trace_id=trace_id,
        )

    def _seed_from_row(self, row: RequirementMatrixRow, analysis: AnalyzeResponse | None) -> dict[str, Any]:
        missing = row.missing_evidence or ["No approved local evidence is attached to this requirement."]
        title = f"Close {row.category} evidence for {row.requirement_id}"
        return self._seed(
            title=title,
            severity=self._row_severity(row),
            owner_team=self._owner_for_row(row),
            missing_source_type=self._source_type(row.category, row.requirement_text),
            impacted_sections=[self._section_for_category(row.category)],
            requirement_ids=[row.requirement_id],
            due_date_recommendation=self._due_recommendation(self._row_severity(row), analysis),
            suggested_sme_or_source_request=self._source_request_for_row(row),
            related_citations=row.evidence_refs,
            closure_acceptance_criteria=self._criteria_for_row(row),
            source_signals=[f"Matrix row {row.requirement_id}: {item}" for item in missing],
        )

    def _seeds_from_analysis(self, analysis: AnalyzeResponse | None) -> list[dict[str, Any]]:
        if not analysis:
            return []
        return [
            self._seed(
                title=f"Resolve RFP analysis missing information: {self._clip(item, 64)}",
                severity="medium",
                owner_team="solutions",
                missing_source_type="rfp_clarification",
                impacted_sections=["Executive Summary", "Assumptions"],
                due_date_recommendation=self._due_recommendation("medium", analysis),
                suggested_sme_or_source_request=(
                    "Ask the account owner to confirm the buyer expectation or document an explicit assumption."
                ),
                closure_acceptance_criteria=[
                    "Buyer clarification or internal assumption is attached to the response package.",
                    "Assumption is reflected in the draft and reviewed by the proposal owner.",
                ],
                source_signals=[f"RFP analysis missing information: {item}"],
            )
            for item in analysis.missing_information
        ]

    def _seeds_from_findings(
        self,
        findings: list[ReviewFinding],
        matrix: list[RequirementMatrixRow],
        analysis: AnalyzeResponse | None,
    ) -> list[dict[str, Any]]:
        rows = {row.requirement_id: row for row in matrix}
        seeds = []
        for finding in findings:
            if finding.category not in {
                "missing_evidence",
                "unsupported_claim",
                "high_risk_requirement",
                "weak_citation",
            } and finding.severity not in {"critical", "high"}:
                continue
            row = rows.get(finding.related_requirement_id or "")
            category = row.category if row else self._category_from_text(finding.message)
            owner = self._owner_for_finding(finding, row)
            seeds.append(
                self._seed(
                    title=self._finding_title(finding, row),
                    severity=finding.severity,
                    owner_team=owner,
                    missing_source_type=self._source_type(category, finding.message),
                    impacted_sections=[self._section_for_category(category)],
                    requirement_ids=[finding.related_requirement_id] if finding.related_requirement_id else [],
                    due_date_recommendation=self._due_recommendation(finding.severity, analysis),
                    suggested_sme_or_source_request=(
                        f"Ask {owner} to provide approved evidence or exception language for: {finding.message}"
                    ),
                    related_citations=finding.citation_refs,
                    closure_acceptance_criteria=[
                        "Review-board finding is resolved or explicitly accepted as an exception.",
                        "Final response language is backed by citations or removes the unsupported claim.",
                    ],
                    source_signals=[
                        f"Review finding {finding.finding_id}: {finding.category} / {finding.message}",
                        f"Review recommendation: {finding.recommendation}",
                    ],
                )
            )
        return seeds

    def _seeds_from_red_team(
        self,
        red_team_summary: dict[str, Any] | None,
        analysis: AnalyzeResponse | None,
    ) -> list[dict[str, Any]]:
        if not red_team_summary:
            return []
        seeds = []
        for index, detail in enumerate(red_team_summary.get("details", []), start=1):
            if not detail.get("missing_evidence_detected") and detail.get("passed", True):
                continue
            question = str(detail.get("question", f"red-team question {index}"))
            risk_type = str(detail.get("risk_type", "missing_evidence"))
            seeds.append(
                self._seed(
                    title=f"Close red-team evidence gap: {self._clip(question, 72)}",
                    severity="high" if detail.get("missing_evidence_detected") else "medium",
                    owner_team=self._owner_for_text(question),
                    missing_source_type=self._source_type(risk_type, question),
                    impacted_sections=[self._section_for_category(self._category_from_text(question))],
                    due_date_recommendation=self._due_recommendation("high", analysis),
                    suggested_sme_or_source_request=(
                        "Ask the accountable SME to provide an approved source or confirm the response must decline."
                    ),
                    red_team_risks=[question],
                    closure_acceptance_criteria=[
                        "Adversarial question produces either cited support or a clear missing-evidence refusal.",
                        "Review categories match the expected red-team risk before final submission.",
                    ],
                    source_signals=[f"Red-team {risk_type}: {question}"],
                )
            )
        if not seeds and red_team_summary.get("missing_evidence_detection_count", 0):
            seeds.append(
                self._seed(
                    title="Review red-team missing-evidence detections",
                    severity="high",
                    owner_team="security",
                    missing_source_type="red_team_evidence_review",
                    impacted_sections=["Security Response", "Compliance Response"],
                    due_date_recommendation=self._due_recommendation("high", analysis),
                    suggested_sme_or_source_request="Review red-team output and attach approved source decisions.",
                    red_team_risks=["Red-team summary reported missing-evidence detections."],
                    closure_acceptance_criteria=[
                        "Each red-team missing-evidence detection is mapped to cited proof, refusal, or exception.",
                    ],
                    source_signals=[f"Red-team summary: {red_team_summary}"],
                )
            )
        return seeds

    def _seeds_from_readiness(
        self,
        readiness: DealReadinessScorecardResponse | None,
        matrix: list[RequirementMatrixRow],
        analysis: AnalyzeResponse | None,
    ) -> list[dict[str, Any]]:
        if not readiness:
            return []
        rows = {row.requirement_id: row for row in matrix}
        seeds = []
        for blocker in readiness.blockers:
            row = next((candidate for req_id, candidate in rows.items() if req_id in blocker), None)
            if row:
                seeds.append(
                    self._seed(
                        title=f"Resolve readiness blocker for {row.requirement_id}",
                        severity="high",
                        owner_team=self._owner_for_row(row),
                        missing_source_type=self._source_type(row.category, row.requirement_text),
                        impacted_sections=[self._section_for_category(row.category)],
                        requirement_ids=[row.requirement_id],
                        due_date_recommendation=self._due_recommendation("high", analysis),
                        suggested_sme_or_source_request=(
                            f"Ask {self._owner_for_row(row)} to close readiness blocker: {blocker}"
                        ),
                        related_citations=row.evidence_refs,
                        closure_acceptance_criteria=[
                            "Readiness blocker no longer appears in the scorecard.",
                            "Evidence coverage improves or an executive exception is recorded.",
                        ],
                        source_signals=[f"Readiness blocker: {blocker}"],
                    )
                )
            elif "missing evidence" in blocker.lower() or readiness.readiness_level != "ready":
                seeds.append(
                    self._seed(
                        title=f"Resolve readiness blocker: {self._clip(blocker, 72)}",
                        severity="high" if readiness.readiness_score < 70 else "medium",
                        owner_team="solutions",
                        missing_source_type="readiness_exception_or_evidence",
                        impacted_sections=["Executive Summary", "Assumptions"],
                        due_date_recommendation=self._due_recommendation("high", analysis),
                        suggested_sme_or_source_request=(
                            "Assign the proposal owner to map this blocker to an owner, source, or exception."
                        ),
                        closure_acceptance_criteria=[
                            "Readiness scorecard is regenerated and blocker is removed or explicitly approved.",
                        ],
                        source_signals=[f"Readiness blocker: {blocker}"],
                    )
                )
        return seeds

    def _seeds_from_win_strategy(
        self,
        strategy: WinStrategyResponse | None,
        matrix: list[RequirementMatrixRow],
        analysis: AnalyzeResponse | None,
    ) -> list[dict[str, Any]]:
        if not strategy:
            return []
        rows = {row.requirement_id: row for row in matrix}
        seeds = []
        for flag in strategy.red_flags:
            row = next((candidate for req_id, candidate in rows.items() if req_id in flag), None)
            category = row.category if row else self._category_from_text(flag)
            seeds.append(
                self._seed(
                    title=f"Close win-strategy red flag: {self._clip(flag, 72)}",
                    severity="high" if strategy.win_score < 70 else "medium",
                    owner_team=self._owner_for_row(row) if row else self._owner_for_text(flag),
                    missing_source_type=self._source_type(category, flag),
                    impacted_sections=[self._section_for_category(category)],
                    requirement_ids=[row.requirement_id] if row else [],
                    due_date_recommendation=self._due_recommendation("high", analysis),
                    suggested_sme_or_source_request=(
                        "Attach proof or approval so the competitive posture does not rely on unsupported claims."
                    ),
                    related_citations=row.evidence_refs if row else [],
                    closure_acceptance_criteria=[
                        "Win-strategy red flag is resolved, downgraded, or included in leadership exception notes.",
                        "Competitive response language cites approved proof points.",
                    ],
                    source_signals=[f"Win-strategy red flag: {flag}"],
                )
            )
        for action in strategy.next_actions_by_owner:
            owner = str(action.get("owner", "solutions"))
            for item in action.get("actions", [])[:2]:
                if any(gap_signal in item.lower() for gap_signal in ["resolve", "approve", "evidence", "red flag"]):
                    seeds.append(
                        self._seed(
                            title=f"Source request from win strategy: {self._clip(str(item), 72)}",
                            severity="medium",
                            owner_team=owner,
                            missing_source_type=self._source_type(owner, str(item)),
                            impacted_sections=["Executive Summary"],
                            due_date_recommendation=self._due_recommendation("medium", analysis),
                            suggested_sme_or_source_request=str(item),
                            closure_acceptance_criteria=[
                                "Owner action is marked complete or converted into an approved exception.",
                            ],
                            source_signals=[f"Win-strategy owner action: {item}"],
                        )
                    )
        return seeds

    def _seeds_from_contract_risk(
        self,
        risk: ContractRiskResponse | None,
        analysis: AnalyzeResponse | None,
    ) -> list[dict[str, Any]]:
        if not risk:
            return []
        seeds = []
        for clause in risk.risky_clauses:
            if not clause.missing_evidence and clause.risk_level not in {"critical", "high"}:
                continue
            owner = self._owner_for_contract_category(clause.category)
            seeds.append(
                self._seed(
                    title=f"Close contract evidence for {clause.clause_id}",
                    severity=clause.risk_level,
                    owner_team=owner,
                    missing_source_type=self._source_type(clause.category, clause.clause_text),
                    impacted_sections=[f"Contract: {clause.title}", "Negotiation Brief"],
                    contract_clause_ids=[clause.clause_id],
                    due_date_recommendation=self._due_recommendation(clause.risk_level, analysis),
                    suggested_sme_or_source_request=(
                        f"Ask {owner} to provide source support or approve fallback: {clause.fallback_position}"
                    ),
                    related_citations=[
                        citation
                        for point in clause.proof_points
                        for citation in point.get("citations", [])
                    ],
                    closure_acceptance_criteria=[
                        "Clause redline or fallback is approved by the accountable owner.",
                        "Proof point is attached, or missing evidence is documented as a negotiation exception.",
                    ],
                    source_signals=[
                        *[f"Contract clause missing evidence: {item}" for item in clause.missing_evidence],
                        f"Contract clause risk: {clause.rationale}",
                    ],
                )
            )
        for warning in risk.missing_evidence_warnings:
            seeds.append(
                self._seed(
                    title=f"Resolve contract missing evidence: {self._clip(warning, 72)}",
                    severity="high",
                    owner_team="legal",
                    missing_source_type="legal_or_security_approval",
                    impacted_sections=["Negotiation Brief"],
                    due_date_recommendation=self._due_recommendation("high", analysis),
                    suggested_sme_or_source_request=(
                        "Ask legal/security to attach proof or document fallback language for this warning."
                    ),
                    closure_acceptance_criteria=[
                        "Warning is linked to a clause-level proof point, redline, fallback, or exception owner.",
                    ],
                    source_signals=[f"Contract missing evidence warning: {warning}"],
                )
            )
        return seeds

    def _seeds_from_tasks(
        self,
        tasks: list[StakeholderTask],
        matrix: list[RequirementMatrixRow],
        analysis: AnalyzeResponse | None,
    ) -> list[dict[str, Any]]:
        rows = {row.requirement_id: row for row in matrix}
        seeds = []
        for task in tasks:
            if task.status not in {"blocked", "needs_review"}:
                continue
            row = rows.get(task.source_requirement_id or "")
            category = row.category if row else self._category_from_text(task.description)
            seeds.append(
                self._seed(
                    title=f"Close action-plan task: {self._clip(task.title, 72)}",
                    severity="high" if task.priority == "high" or task.status == "blocked" else "medium",
                    owner_team=task.owner_role,
                    missing_source_type=self._source_type(category, task.description),
                    impacted_sections=[self._section_for_category(category)],
                    requirement_ids=[task.source_requirement_id] if task.source_requirement_id else [],
                    due_date_recommendation=task.due_hint or self._due_recommendation(task.priority, analysis),
                    suggested_sme_or_source_request=task.description,
                    related_citations=task.evidence_refs,
                    closure_acceptance_criteria=[
                        "Action-plan task is moved out of blocked/needs_review.",
                        "Evidence refs are attached or exception approval is recorded.",
                    ],
                    source_signals=[f"Action-plan task {task.task_id}: {task.status} / {task.description}"],
                )
            )
        return seeds

    def _merge_seeds(self, seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for seed in seeds:
            key = self._merge_key(seed)
            if key not in merged:
                merged[key] = seed
                continue
            current = merged[key]
            if self._severity_weight(seed["severity"]) > self._severity_weight(current["severity"]):
                current["severity"] = seed["severity"]
                current["due_date_recommendation"] = seed["due_date_recommendation"]
            for field in [
                "impacted_sections",
                "requirement_ids",
                "contract_clause_ids",
                "related_citations",
                "red_team_risks",
                "closure_acceptance_criteria",
                "source_signals",
            ]:
                current[field] = self._unique([*current[field], *seed[field]])
            if len(seed["suggested_sme_or_source_request"]) > len(current["suggested_sme_or_source_request"]):
                current["suggested_sme_or_source_request"] = seed["suggested_sme_or_source_request"]
        return list(merged.values())

    def _seed(
        self,
        title: str,
        severity: str,
        owner_team: str,
        missing_source_type: str,
        impacted_sections: list[str],
        due_date_recommendation: str,
        suggested_sme_or_source_request: str,
        requirement_ids: list[str] | None = None,
        contract_clause_ids: list[str] | None = None,
        related_citations: list[str] | None = None,
        red_team_risks: list[str] | None = None,
        closure_acceptance_criteria: list[str] | None = None,
        source_signals: list[str] | None = None,
    ) -> dict[str, Any]:
        criteria = closure_acceptance_criteria or []
        criteria.extend(
            [
                "Attached source is approved for external customer use.",
                "Final response section includes either a citation-backed answer or explicit exception language.",
            ]
        )
        return {
            "title": title,
            "severity": self._normalize_severity(severity),
            "owner_team": self._owner_slug(owner_team),
            "missing_source_type": missing_source_type,
            "impacted_sections": self._unique(impacted_sections),
            "requirement_ids": self._unique(requirement_ids or []),
            "contract_clause_ids": self._unique(contract_clause_ids or []),
            "due_date_recommendation": due_date_recommendation,
            "suggested_sme_or_source_request": suggested_sme_or_source_request,
            "related_citations": self._unique(related_citations or []),
            "red_team_risks": self._unique(red_team_risks or []),
            "closure_acceptance_criteria": self._unique(criteria),
            "source_signals": self._unique(source_signals or []),
        }

    def _summary(
        self,
        gaps: list[EvidenceGap],
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
        red_team_summary: dict[str, Any] | None,
        readiness: DealReadinessScorecardResponse | None,
        contract_risk: ContractRiskResponse | None,
    ) -> dict[str, Any]:
        severity_counts = Counter(gap.severity for gap in gaps)
        owner_counts = Counter(gap.owner_team for gap in gaps)
        source_counts = Counter(gap.missing_source_type for gap in gaps)
        return {
            "gap_count": len(gaps),
            "high_severity_count": severity_counts.get("critical", 0) + severity_counts.get("high", 0),
            "severity_counts": dict(sorted(severity_counts.items())),
            "owner_counts": dict(sorted(owner_counts.items())),
            "missing_source_type_counts": dict(sorted(source_counts.items())),
            "matrix_rows": len(matrix),
            "review_findings": len(findings),
            "red_team_passed": red_team_summary.get("passed") if red_team_summary else None,
            "readiness_score": readiness.readiness_score if readiness else None,
            "readiness_level": readiness.readiness_level if readiness else None,
            "contract_risk_score": contract_risk.risk_score if contract_risk else None,
            "top_gap_titles": [gap.title for gap in gaps[:5]],
        }

    def _pack_summary(
        self,
        gaps: list[EvidenceGap],
        analysis: AnalyzeResponse | None,
        readiness: DealReadinessScorecardResponse | None,
        contract_risk: ContractRiskResponse | None,
    ) -> dict[str, Any]:
        severity_counts = Counter(gap.severity for gap in gaps)
        return {
            "gap_count": len(gaps),
            "high_severity_count": severity_counts.get("critical", 0) + severity_counts.get("high", 0),
            "deadline_references": analysis.deadlines if analysis else [],
            "readiness_level": readiness.readiness_level if readiness else None,
            "readiness_score": readiness.readiness_score if readiness else None,
            "contract_status": contract_risk.status if contract_risk else None,
            "owners": dict(sorted(Counter(gap.owner_team for gap in gaps).items())),
        }

    def _source_request_tasks(self, gaps: list[EvidenceGap]) -> list[dict[str, Any]]:
        tasks = []
        for gap in gaps:
            tasks.append(
                {
                    "subject": f"[RFP Evidence Request] {gap.title}",
                    "owner_team": gap.owner_team,
                    "severity": gap.severity,
                    "due": gap.due_date_recommendation,
                    "message": (
                        f"Please provide {gap.missing_source_type} for {', '.join(gap.impacted_sections)}. "
                        f"Request: {gap.suggested_sme_or_source_request}"
                    ),
                    "acceptance_criteria": gap.closure_acceptance_criteria,
                    "requirement_ids": gap.requirement_ids,
                    "contract_clause_ids": gap.contract_clause_ids,
                }
            )
        return tasks

    def _owner_matrix(self, gaps: list[EvidenceGap]) -> list[dict[str, Any]]:
        grouped: dict[str, list[EvidenceGap]] = {}
        for gap in gaps:
            grouped.setdefault(gap.owner_team, []).append(gap)
        return [
            {
                "owner_team": owner,
                "gap_count": len(items),
                "high_severity_count": sum(1 for gap in items if gap.severity in {"critical", "high"}),
                "missing_source_types": sorted({gap.missing_source_type for gap in items}),
                "top_due_recommendation": items[0].due_date_recommendation,
                "top_gap": items[0].title,
            }
            for owner, items in sorted(grouped.items())
        ]

    def _acceptance_criteria(self, gaps: list[EvidenceGap]) -> list[dict[str, Any]]:
        return [
            {
                "gap_id": gap.gap_id,
                "title": gap.title,
                "criteria": gap.closure_acceptance_criteria,
            }
            for gap in gaps
        ]

    def _impacted_sections(self, gaps: list[EvidenceGap]) -> list[dict[str, Any]]:
        section_map: dict[str, list[str]] = {}
        for gap in gaps:
            for section in gap.impacted_sections:
                section_map.setdefault(section, []).append(gap.gap_id)
        return [
            {"section": section, "gap_ids": gap_ids, "gap_count": len(gap_ids)}
            for section, gap_ids in sorted(section_map.items())
        ]

    def _red_team_risks(
        self,
        gaps: list[EvidenceGap],
        red_team_summary: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        risks = [
            {"gap_id": gap.gap_id, "risk": risk}
            for gap in gaps
            for risk in gap.red_team_risks
        ]
        if red_team_summary:
            risks.append(
                {
                    "gap_id": None,
                    "risk": (
                        "Red-team summary: "
                        f"passed={red_team_summary.get('passed')} "
                        f"missing={red_team_summary.get('missing_evidence_detection_count')}/"
                        f"{red_team_summary.get('expected_missing_evidence')}"
                    ),
                }
            )
        return risks

    def _readiness_context(self, readiness: DealReadinessScorecardResponse | None) -> dict[str, Any] | None:
        if readiness is None:
            return None
        return {
            "readiness_score": readiness.readiness_score,
            "readiness_level": readiness.readiness_level,
            "blockers": readiness.blockers,
            "recommended_next_actions": readiness.recommended_next_actions,
        }

    def _win_context(self, strategy: WinStrategyResponse | None) -> dict[str, Any] | None:
        if strategy is None:
            return None
        return {
            "win_score": strategy.win_score,
            "win_level": strategy.win_level,
            "recommended_response_posture": strategy.recommended_response_posture,
            "red_flags": strategy.red_flags,
        }

    def _contract_context(self, risk: ContractRiskResponse | None) -> dict[str, Any] | None:
        if risk is None:
            return None
        return {
            "risk_score": risk.risk_score,
            "status": risk.status,
            "missing_evidence_warnings": risk.missing_evidence_warnings,
            "category_counts": risk.category_counts,
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Evidence Gap Remediation Planner + Source Request Pack",
            "",
            "## Summary",
            "",
            f"- Gap count: {summary['gap_count']}",
            f"- High severity count: {summary['high_severity_count']}",
            f"- Readiness: {summary['readiness_score']} ({summary['readiness_level']})",
            f"- Contract status: {summary['contract_status']}",
            "",
            "## Prioritized Evidence Gaps",
            "",
            "| Rank | Gap | Severity | Owner | Source Type | Due | Impacted Sections |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for gap in pack["prioritized_gaps"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md_cell(gap["priority_rank"]),
                        self._md_cell(gap["title"]),
                        self._md_cell(gap["severity"]),
                        self._md_cell(gap["owner_team"]),
                        self._md_cell(gap["missing_source_type"]),
                        self._md_cell(gap["due_date_recommendation"]),
                        self._md_cell(", ".join(gap["impacted_sections"])),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Source Request Emails and Tasks", ""])
        for task in pack["source_request_emails_tasks"]:
            lines.extend(
                [
                    f"### {task['subject']}",
                    "",
                    f"- Owner: {task['owner_team']}",
                    f"- Severity: {task['severity']}",
                    f"- Due: {task['due']}",
                    f"- Message: {task['message']}",
                    "",
                    "Acceptance criteria:",
                ]
            )
            lines.extend(f"- {item}" for item in task["acceptance_criteria"])
            lines.append("")
        lines.extend(["## Owner Matrix", ""])
        if pack["owner_matrix"]:
            lines.extend(
                [
                    "| Owner | Gaps | High Severity | Source Types | Top Gap |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for owner in pack["owner_matrix"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            self._md_cell(owner["owner_team"]),
                            self._md_cell(owner["gap_count"]),
                            self._md_cell(owner["high_severity_count"]),
                            self._md_cell(", ".join(owner["missing_source_types"])),
                            self._md_cell(owner["top_gap"]),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Impacted Response Sections", ""])
        for section in pack["impacted_response_sections"]:
            lines.append(f"- {section['section']}: {section['gap_count']} gap(s)")
        lines.extend(["", "## Red-Team Risks", ""])
        if pack["red_team_risks"]:
            lines.extend(f"- {item['risk']}" for item in pack["red_team_risks"])
        else:
            lines.append("- None")
        lines.extend(["", "## Exact Local Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in pack["local_commands"])
        lines.extend(["", "## JD Skills Demonstrated", ""])
        lines.extend(f"- {item}" for item in pack["jd_skills_demonstrated"])
        lines.extend(["", "## Five Interviewer Talking Points", ""])
        lines.extend(f"- {item}" for item in pack["interviewer_talking_points"])
        return "\n".join(lines).strip() + "\n"

    def _merge_key(self, seed: dict[str, Any]) -> tuple[str, str]:
        if seed["requirement_ids"]:
            return "requirement", seed["requirement_ids"][0]
        if seed["contract_clause_ids"]:
            return "contract", seed["contract_clause_ids"][0]
        return seed["owner_team"], self._slug(seed["title"])[:56]

    def _row_severity(self, row: RequirementMatrixRow) -> str:
        if row.status == "blocked" or row.risk_level == "high":
            return "high"
        if row.priority == "high" or row.missing_evidence:
            return "medium"
        return "low"

    def _criteria_for_row(self, row: RequirementMatrixRow) -> list[str]:
        criteria = [
            f"{row.owner_role} confirms the response for {row.requirement_id} is accurate.",
            "Requirement matrix row has evidence_refs or documented exception approval.",
        ]
        if row.category in {"security", "compliance"}:
            criteria.append("Security/compliance evidence is approved for customer-facing use.")
        if row.category == "pricing":
            criteria.append("Sales or finance approval is attached for pricing assumptions.")
        return criteria

    def _source_request_for_row(self, row: RequirementMatrixRow) -> str:
        owner = self._owner_for_row(row)
        missing = "; ".join(row.missing_evidence) or "approved source evidence"
        return f"Ask {owner} to provide {self._source_type(row.category, row.requirement_text)} covering: {missing}"

    def _due_recommendation(self, severity: str, analysis: AnalyzeResponse | None) -> str:
        normalized = self._normalize_severity(severity)
        deadline = self._first_deadline(analysis)
        if deadline:
            offsets = {"critical": 7, "high": 5, "medium": 3, "low": 1}
            due_date = deadline - timedelta(days=offsets[normalized])
            return (
                f"{due_date.strftime('%B %d, %Y')} "
                f"({offsets[normalized]} days before submission deadline {deadline.strftime('%B %d, %Y')})"
            )
        return {
            "critical": "same business day",
            "high": "within 2 business days",
            "medium": "this week",
            "low": "before final submission review",
        }[normalized]

    def _first_deadline(self, analysis: AnalyzeResponse | None) -> datetime | None:
        if not analysis:
            return None
        for item in analysis.deadlines:
            try:
                return datetime.strptime(item, "%B %d, %Y")
            except ValueError:
                continue
        return None

    def _source_type(self, category: str, text: str) -> str:
        lowered = f"{category} {text}".lower()
        if any(term in lowered for term in ["price", "pricing", "discount", "commercial", "payment"]):
            return "pricing_approval_or_commercial_source"
        if any(term in lowered for term in ["contract", "liability", "dpa", "gdpr", "indemnity", "subprocessor"]):
            return "legal_approval_or_contract_source"
        if any(term in lowered for term in ["security", "sso", "encryption", "incident", "vulnerability", "audit"]):
            return "security_policy_or_control_evidence"
        if any(term in lowered for term in ["soc", "iso", "compliance", "fedramp"]):
            return "compliance_attestation_or_exception"
        if any(term in lowered for term in ["implementation", "integration", "rollout", "api", "migration"]):
            return "implementation_plan_or_sme_confirmation"
        if any(term in lowered for term in ["product", "feature", "dashboard", "workflow", "roadmap"]):
            return "product_documentation_or_pm_approval"
        if "red" in lowered:
            return "red_team_evidence_review"
        return "approved_source_or_sme_confirmation"

    def _section_for_category(self, category: str) -> str:
        normalized = category.lower()
        if normalized == "security":
            return "Security Response"
        if normalized == "compliance":
            return "Compliance Response"
        if normalized == "pricing":
            return "Pricing and Commercials"
        if normalized == "implementation":
            return "Implementation Plan"
        if normalized in {"legal", "contract", "liability", "data_processing", "indemnity"}:
            return "Contract Terms"
        return "Technical Response"

    def _category_from_text(self, text: str) -> str:
        lowered = text.lower()
        if any(term in lowered for term in ["security", "sso", "encryption", "incident", "fedramp"]):
            return "security"
        if any(term in lowered for term in ["soc", "gdpr", "dpa", "compliance", "subprocessor"]):
            return "compliance"
        if any(term in lowered for term in ["pricing", "price", "discount", "commercial"]):
            return "pricing"
        if any(term in lowered for term in ["implementation", "api", "integration", "rollout"]):
            return "implementation"
        if any(term in lowered for term in ["contract", "liability", "indemnity", "termination"]):
            return "legal"
        return "functional"

    def _owner_for_row(self, row: RequirementMatrixRow | None) -> str:
        if row is None:
            return "solutions"
        owner = row.owner_role.lower()
        if "security" in owner:
            return "security"
        if "compliance" in owner or "legal" in owner:
            return "legal"
        if "commercial" in owner or "sales" in owner:
            return "sales"
        if "implementation" in owner:
            return "solutions"
        if row.category == "functional":
            return "product"
        return owner.replace(" ", "_")

    def _owner_for_finding(self, finding: ReviewFinding, row: RequirementMatrixRow | None) -> str:
        if row is not None:
            return self._owner_for_row(row)
        return self._owner_for_text(f"{finding.category} {finding.message} {finding.recommendation}")

    def _owner_for_text(self, text: str) -> str:
        lowered = text.lower()
        if any(term in lowered for term in ["contract", "legal", "dpa", "gdpr", "liability", "indemnity"]):
            return "legal"
        if any(term in lowered for term in ["security", "encryption", "sso", "fedramp", "audit", "control"]):
            return "security"
        if any(term in lowered for term in ["pricing", "price", "discount", "commercial"]):
            return "sales"
        if any(term in lowered for term in ["feature", "dashboard", "workflow", "roadmap"]):
            return "product"
        return "solutions"

    def _owner_for_contract_category(self, category: str) -> str:
        if category in {"pricing_payment"}:
            return "finance"
        if category in {"security_obligations", "audit_rights", "data_residency"}:
            return "security"
        if category in {"ai_data_use"}:
            return "product"
        if category in {"sla_service_credits"}:
            return "solutions"
        return "legal"

    def _owner_slug(self, owner: str) -> str:
        lowered = owner.lower().replace(" ", "_")
        aliases = {
            "security_architect": "security",
            "compliance_lead": "legal",
            "commercial_owner": "sales",
            "implementation_lead": "solutions",
            "solutions_engineer": "solutions",
            "sales_leadership": "sales",
        }
        return aliases.get(lowered, lowered)

    def _finding_title(self, finding: ReviewFinding, row: RequirementMatrixRow | None) -> str:
        if row is not None:
            return f"Resolve {finding.category} finding for {row.requirement_id}"
        return f"Resolve review finding: {self._clip(finding.message, 72)}"

    def _normalize_severity(self, severity: str) -> str:
        lowered = severity.lower()
        if lowered in {"critical", "high", "medium", "low"}:
            return lowered
        if lowered in {"blocked", "not_ready"}:
            return "high"
        return "medium"

    def _severity_weight(self, severity: str) -> int:
        return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(self._normalize_severity(severity), 2)

    def _unique(self, items: list[str]) -> list[str]:
        return [item for item in dict.fromkeys(str(item) for item in items if str(item).strip())]

    def _slug(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
        return slug[:64] or "evidence_gap"

    def _clip(self, text: str, limit: int) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    def _md_cell(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
