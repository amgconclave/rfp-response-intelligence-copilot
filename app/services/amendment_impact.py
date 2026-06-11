from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    DealReadinessScorecardResponse,
    RfpAmendmentImpactPackResponse,
    RfpAmendmentImpactResponse,
)
from app.models.domain import DraftResponse, RequirementMatrixRow, ReviewFinding, RfpRequirement


class RfpAmendmentImpactService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def analyze_impact(
        self,
        trace_id: str,
        baseline_analysis: AnalyzeResponse,
        revised_analysis: AnalyzeResponse,
        requirement_matrix: list[RequirementMatrixRow] | None = None,
        draft_response: DraftResponse | None = None,
        readiness_scorecard: DealReadinessScorecardResponse | None = None,
        review_findings: list[ReviewFinding] | None = None,
        amendment_label: str = "Addendum 1",
    ) -> RfpAmendmentImpactResponse:
        matrix = requirement_matrix or []
        findings = review_findings or []
        changes = self._requirement_changes(baseline_analysis.requirements, revised_analysis.requirements, matrix)
        summary = self._summary(changes, baseline_analysis, revised_analysis, findings)
        readiness_impact = self._readiness_impact(changes, readiness_scorecard)
        workflow = self._workflow(changes, summary, readiness_impact)
        owner_queue = self._owner_review_queue(changes, workflow)
        draft_plan = self._draft_update_plan(changes, draft_response)
        status = self._status(summary, readiness_impact)
        generated_at = datetime.now(UTC).isoformat()
        return RfpAmendmentImpactResponse(
            title="RFP Amendment Impact Analysis",
            amendment_label=amendment_label,
            status=status,
            summary=summary,
            requirement_changes=changes,
            readiness_impact=readiness_impact,
            draft_update_plan=draft_plan,
            owner_review_queue=owner_queue,
            workflow=workflow,
            trace_spans=self._trace_spans(changes, workflow),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_commands(),
            limitations=self._limitations(),
            generated_at=generated_at,
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        impact: RfpAmendmentImpactResponse,
        write_artifact: bool = True,
    ) -> RfpAmendmentImpactPackResponse:
        pack = {
            "trace_id": trace_id,
            "title": "RFP Amendment Impact Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "impact": impact.model_dump(mode="json"),
            "executive_summary": self._executive_summary(impact),
            "reviewer_playbook": self._reviewer_playbook(impact),
            "artifact_map": {
                "markdown_root": "storage/amendment_impact",
                "json_root": "storage/amendment_impact",
                "dashboard_tab": "Amendment Impact",
                "api_endpoints": ["/rfp/amendment-impact", "/rfp/amendment-impact-pack"],
            },
            "jd_skills_demonstrated": [
                "Typed structured outputs for RFP addendum impact analysis.",
                "State-machine workflow with conditional reviewer routing and traceable transitions.",
                "Local-first governance artifact generation with no external LLM or workflow dependency.",
                "Readiness score impact analysis connected to matrix, draft, and reviewer bottlenecks.",
            ],
            "local_proof_commands": impact.local_proof_commands,
            "limitations": impact.limitations,
        }
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "amendment_impact"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"rfp_amendment_impact_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"rfp_amendment_impact_pack_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return RfpAmendmentImpactPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            impact=impact,
            trace_id=trace_id,
        )

    def _requirement_changes(
        self,
        baseline: list[RfpRequirement],
        revised: list[RfpRequirement],
        matrix: list[RequirementMatrixRow],
    ) -> list[dict[str, Any]]:
        matrix_by_text = {self._signature(row.requirement_text): row for row in matrix}
        matched_baseline: set[int] = set()
        changes: list[dict[str, Any]] = []
        for revised_index, revised_req in enumerate(revised, start=1):
            baseline_index, score = self._best_match(revised_req, baseline, matched_baseline)
            if baseline_index is None or score < 0.42:
                changes.append(self._change("added", None, revised_req, revised_index, score, matrix_by_text))
                continue
            matched_baseline.add(baseline_index)
            baseline_req = baseline[baseline_index]
            if (
                score < 0.82
                or self._category_changed(baseline_req, revised_req)
                or baseline_req.priority != revised_req.priority
            ):
                changes.append(
                    self._change("changed", baseline_req, revised_req, revised_index, score, matrix_by_text)
                )

        for baseline_index, baseline_req in enumerate(baseline):
            if baseline_index not in matched_baseline:
                changes.append(self._change("removed", baseline_req, None, baseline_index + 1, 0.0, matrix_by_text))

        return sorted(
            changes,
            key=lambda item: (
                self._change_sort(item["change_type"]),
                -self._severity_weight(item["risk_level"]),
                item["owner_role"],
                item["change_id"],
            ),
        )

    def _change(
        self,
        change_type: str,
        baseline: RfpRequirement | None,
        revised: RfpRequirement | None,
        sequence: int,
        match_score: float,
        matrix_by_text: dict[str, RequirementMatrixRow],
    ) -> dict[str, Any]:
        req = revised or baseline
        assert req is not None
        category = req.category
        owner_role = self._owner_for_category(category, req.text)
        risk_level = self._risk_level(change_type, req)
        existing_row = matrix_by_text.get(self._signature(baseline.text if baseline else req.text))
        impact_reasons = self._impact_reasons(change_type, baseline, revised, existing_row)
        change_id = f"amend_{sequence:02d}_{change_type}_{self._slug(category)}"
        return {
            "change_id": change_id,
            "change_type": change_type,
            "baseline_requirement_id": baseline.id if baseline else None,
            "revised_requirement_id": revised.id if revised else None,
            "category": category,
            "priority": req.priority,
            "owner_role": owner_role,
            "reviewer_role": self._reviewer_for_change(category, req.text, change_type),
            "risk_level": risk_level,
            "match_score": round(match_score, 2),
            "baseline_text": baseline.text if baseline else None,
            "revised_text": revised.text if revised else None,
            "matrix_status": existing_row.status if existing_row else None,
            "evidence_refs": existing_row.evidence_refs if existing_row else list(req.evidence_refs),
            "missing_evidence": existing_row.missing_evidence if existing_row else self._missing_evidence(req),
            "impact_reasons": impact_reasons,
            "recommended_action": self._recommended_action(change_type, req, risk_level),
            "checkpoint_key": f"amendment-impact.{change_id}",
        }

    def _summary(
        self,
        changes: list[dict[str, Any]],
        baseline_analysis: AnalyzeResponse,
        revised_analysis: AnalyzeResponse,
        findings: list[ReviewFinding],
    ) -> dict[str, Any]:
        by_type = Counter(change["change_type"] for change in changes)
        by_owner = Counter(change["owner_role"] for change in changes)
        by_risk = Counter(change["risk_level"] for change in changes)
        deadline_changed = baseline_analysis.deadlines != revised_analysis.deadlines
        blocking_count = sum(
            1
            for change in changes
            if change["risk_level"] in {"critical", "high"} and change["change_type"] in {"added", "changed"}
        )
        return {
            "baseline_requirement_count": len(baseline_analysis.requirements),
            "revised_requirement_count": len(revised_analysis.requirements),
            "change_count": len(changes),
            "added_count": by_type.get("added", 0),
            "changed_count": by_type.get("changed", 0),
            "removed_count": by_type.get("removed", 0),
            "deadline_changed": deadline_changed,
            "baseline_deadlines": baseline_analysis.deadlines,
            "revised_deadlines": revised_analysis.deadlines,
            "blocking_change_count": blocking_count,
            "review_finding_count": len(findings),
            "owner_counts": dict(sorted(by_owner.items())),
            "risk_counts": dict(sorted(by_risk.items())),
        }

    def _readiness_impact(
        self,
        changes: list[dict[str, Any]],
        readiness_scorecard: DealReadinessScorecardResponse | None,
    ) -> dict[str, Any]:
        baseline_score = readiness_scorecard.readiness_score if readiness_scorecard else 82
        deductions = []
        for change in changes:
            points = self._deduction_points(change)
            if points:
                deductions.append(
                    {
                        "change_id": change["change_id"],
                        "points": points,
                        "reason": "; ".join(change["impact_reasons"][:2]),
                        "owner_role": change["owner_role"],
                    }
                )
        total_deduction = min(35, sum(item["points"] for item in deductions))
        projected = max(0, baseline_score - total_deduction)
        return {
            "baseline_readiness_score": baseline_score,
            "projected_readiness_score": projected,
            "readiness_delta": projected - baseline_score,
            "deductions": deductions,
            "projected_readiness_level": self._readiness_level(projected),
            "submission_gate": (
                "blocked" if projected < 70 or any(item["points"] >= 8 for item in deductions) else "review"
            ),
            "blockers": [
                change["recommended_action"]
                for change in changes
                if change["risk_level"] in {"critical", "high"} and change["change_type"] != "removed"
            ][:8],
        }

    def _workflow(
        self,
        changes: list[dict[str, Any]],
        summary: dict[str, Any],
        readiness_impact: dict[str, Any],
    ) -> dict[str, Any]:
        states = [
            {
                "state": "capture_baseline",
                "status": "complete",
                "checkpoint_key": "amendment-impact.capture-baseline",
                "owner": "proposal_manager",
            },
            {
                "state": "compare_amendment",
                "status": "complete",
                "checkpoint_key": "amendment-impact.compare",
                "owner": "solutions",
            },
            {
                "state": "route_owner_review",
                "status": "blocked" if summary["blocking_change_count"] else "ready",
                "checkpoint_key": "amendment-impact.route-review",
                "owner": "proposal_manager",
            },
            {
                "state": "update_draft_and_evidence",
                "status": "blocked" if self._needs_evidence(changes) else "ready",
                "checkpoint_key": "amendment-impact.update-draft",
                "owner": "solutions",
            },
            {
                "state": "readiness_gate",
                "status": readiness_impact["submission_gate"],
                "checkpoint_key": "amendment-impact.readiness-gate",
                "owner": "proposal_manager",
            },
        ]
        transitions = []
        for sequence, (current, next_state) in enumerate(zip(states, states[1:], strict=False), start=1):
            transitions.append(
                {
                    "sequence": sequence,
                    "from_state": current["state"],
                    "to_state": next_state["state"],
                    "decision": self._transition_decision(next_state, summary, readiness_impact),
                    "status": next_state["status"],
                    "checkpoint_key": next_state["checkpoint_key"],
                }
            )
        return {
            "workflow_id": "rfp-amendment-impact-v1",
            "states": states,
            "transitions": transitions,
            "conditional_routes": self._conditional_routes(changes, summary, readiness_impact),
        }

    def _owner_review_queue(self, changes: list[dict[str, Any]], workflow: dict[str, Any]) -> list[dict[str, Any]]:
        queue = []
        for change in changes:
            if change["change_type"] == "removed" and change["risk_level"] == "low":
                continue
            queue.append(
                {
                    "queue_id": f"review_{change['change_id']}",
                    "owner_role": change["owner_role"],
                    "reviewer_role": change["reviewer_role"],
                    "priority": change["risk_level"],
                    "change_type": change["change_type"],
                    "change_id": change["change_id"],
                    "checkpoint_key": change["checkpoint_key"],
                    "next_action": change["recommended_action"],
                    "workflow_state": "route_owner_review",
                }
            )
        queue.sort(key=lambda item: (-self._severity_weight(item["priority"]), item["owner_role"], item["change_id"]))
        route_state = next((state for state in workflow["states"] if state["state"] == "route_owner_review"), None)
        if route_state:
            for item in queue:
                item["workflow_status"] = route_state["status"]
        return queue

    def _draft_update_plan(
        self,
        changes: list[dict[str, Any]],
        draft_response: DraftResponse | None,
    ) -> list[dict[str, Any]]:
        section_map = {
            "security": "Security Response",
            "compliance": "Compliance Response",
            "pricing": "Pricing Response",
            "implementation": "Implementation Plan",
            "functional": "Technical Response",
        }
        existing_sections = (
            {section.title.lower(): section for section in draft_response.sections} if draft_response else {}
        )
        plan = []
        for category, grouped in self._group_by_category(changes).items():
            if not grouped:
                continue
            section = section_map.get(category, "Technical Response")
            section_exists = section.lower() in existing_sections
            plan.append(
                {
                    "section": section,
                    "category": category,
                    "change_ids": [change["change_id"] for change in grouped],
                    "status": "revise_existing_section" if section_exists else "create_or_expand_section",
                    "required_updates": [change["recommended_action"] for change in grouped],
                    "evidence_needed": sorted(
                        {
                            item
                            for change in grouped
                            for item in change["missing_evidence"]
                        }
                    )[:8],
                }
            )
        return plan

    def _trace_spans(self, changes: list[dict[str, Any]], workflow: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "span_id": "amendment-impact.compare",
                "name": "Compare baseline and revised RFP requirements",
                "status": "ok",
                "metadata": {"change_count": len(changes)},
            },
            {
                "span_id": "amendment-impact.route",
                "name": "Route changes through reviewer workflow",
                "status": "ok",
                "metadata": {
                    "transition_count": len(workflow["transitions"]),
                    "conditional_route_count": len(workflow["conditional_routes"]),
                },
            },
        ]

    def _executive_summary(self, impact: RfpAmendmentImpactResponse) -> dict[str, Any]:
        return {
            "status": impact.status,
            "change_count": impact.summary["change_count"],
            "blocking_change_count": impact.summary["blocking_change_count"],
            "readiness_delta": impact.readiness_impact["readiness_delta"],
            "submission_gate": impact.readiness_impact["submission_gate"],
            "top_owner_counts": impact.summary["owner_counts"],
        }

    def _reviewer_playbook(self, impact: RfpAmendmentImpactResponse) -> list[dict[str, Any]]:
        return [
            {
                "step": 1,
                "owner": "proposal_manager",
                "action": "Review blocking addendum changes and confirm response deadline.",
            },
            {
                "step": 2,
                "owner": "solutions",
                "action": "Update affected draft sections and attach new evidence.",
            },
            {
                "step": 3,
                "owner": "security_legal_commercial",
                "action": "Approve routed owner queue items before the readiness gate.",
            },
            {
                "step": 4,
                "owner": "proposal_manager",
                "action": (
                    "Re-run readiness gate; current projection is "
                    f"{impact.readiness_impact['projected_readiness_score']}."
                ),
            },
        ]

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        impact = pack["impact"]
        lines = [
            "# RFP Amendment Impact Pack",
            "",
            f"- Status: {impact['status']}",
            f"- Amendment: {impact['amendment_label']}",
            f"- Change count: {impact['summary']['change_count']}",
            f"- Blocking changes: {impact['summary']['blocking_change_count']}",
            f"- Readiness delta: {impact['readiness_impact']['readiness_delta']}",
            f"- Submission gate: {impact['readiness_impact']['submission_gate']}",
            "",
            "## Requirement Changes",
            "",
            "| Change | Type | Risk | Owner | Reviewer | Action |",
            "|---|---|---|---|---|---|",
        ]
        for change in impact["requirement_changes"]:
            lines.append(
                "| "
                f"{change['change_id']} | {change['change_type']} | {change['risk_level']} | "
                f"{change['owner_role']} | {change['reviewer_role']} | {self._md(change['recommended_action'])} |"
            )
        lines.extend(["", "## Owner Review Queue", ""])
        for item in impact["owner_review_queue"]:
            lines.append(
                f"- {item['reviewer_role']} / {item['priority']}: {item['next_action']} "
                f"({item['checkpoint_key']})"
            )
        lines.extend(["", "## Workflow Transitions", ""])
        for transition in impact["workflow"]["transitions"]:
            lines.append(
                f"- {transition['from_state']} -> {transition['to_state']}: "
                f"{transition['decision']} ({transition['status']})"
            )
        lines.extend(["", "## Draft Update Plan", ""])
        for item in impact["draft_update_plan"]:
            lines.append(f"- {item['section']}: {item['status']} for {', '.join(item['change_ids'])}")
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"- `{command}`" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        return "\n".join(lines) + "\n"

    def _best_match(
        self,
        revised_req: RfpRequirement,
        baseline: list[RfpRequirement],
        matched_baseline: set[int],
    ) -> tuple[int | None, float]:
        best_index: int | None = None
        best_score = 0.0
        revised_tokens = self._tokens(revised_req.text)
        for index, baseline_req in enumerate(baseline):
            if index in matched_baseline:
                continue
            baseline_tokens = self._tokens(baseline_req.text)
            if not baseline_tokens or not revised_tokens:
                continue
            overlap = len(baseline_tokens & revised_tokens)
            union = len(baseline_tokens | revised_tokens)
            score = overlap / union
            if baseline_req.category == revised_req.category:
                score += 0.08
            if score > best_score:
                best_score = score
                best_index = index
        return best_index, min(best_score, 1.0)

    def _tokens(self, text: str) -> set[str]:
        stopwords = {
            "the",
            "and",
            "or",
            "a",
            "an",
            "to",
            "for",
            "of",
            "with",
            "on",
            "in",
            "by",
            "from",
            "must",
            "shall",
            "should",
            "provide",
            "vendor",
            "solution",
            "platform",
            "system",
        }
        return {
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if len(token) > 2 and token not in stopwords
        }

    def _signature(self, text: str) -> str:
        return " ".join(sorted(self._tokens(text)))

    def _slug(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "change"

    def _category_changed(self, baseline: RfpRequirement, revised: RfpRequirement) -> bool:
        return baseline.category != revised.category

    def _owner_for_category(self, category: str, text: str) -> str:
        lower = text.lower()
        if category == "security" or any(term in lower for term in ["incident", "encryption", "sso"]):
            return "security"
        if category == "compliance" or any(term in lower for term in ["gdpr", "data residency", "soc 2", "iso"]):
            return "legal"
        if category == "pricing" or "tco" in lower or "renewal" in lower:
            return "sales"
        if category == "implementation":
            return "solutions"
        return "product"

    def _reviewer_for_change(self, category: str, text: str, change_type: str) -> str:
        lower = text.lower()
        if change_type == "removed":
            return "proposal_manager"
        if category == "security" or "incident" in lower:
            return "security_reviewer"
        if category == "compliance" or any(term in lower for term in ["gdpr", "data residency", "soc 2", "iso"]):
            return "legal_reviewer"
        if category == "pricing" or any(term in lower for term in ["tco", "renewal", "price"]):
            return "commercial_reviewer"
        return "solutions_reviewer"

    def _risk_level(self, change_type: str, req: RfpRequirement) -> str:
        lower = req.text.lower()
        if change_type == "removed":
            return "medium" if req.priority == "high" else "low"
        if any(term in lower for term in ["data residency", "incident", "soc 2", "gdpr", "pricing", "tco"]):
            return "high"
        if req.category in {"security", "compliance", "pricing"} or req.priority == "high":
            return "high"
        return "medium"

    def _impact_reasons(
        self,
        change_type: str,
        baseline: RfpRequirement | None,
        revised: RfpRequirement | None,
        existing_row: RequirementMatrixRow | None,
    ) -> list[str]:
        reasons = [f"Requirement was {change_type} by the amended RFP."]
        if baseline and revised and baseline.text != revised.text:
            reasons.append("Existing draft and matrix row need review because requirement wording changed.")
        if revised and revised.priority == "high":
            reasons.append("High-priority requirement requires owner review before submission.")
        if existing_row and (existing_row.missing_evidence or not existing_row.evidence_refs):
            reasons.append("Current matrix does not have complete evidence coverage.")
        if revised and revised.category in {"security", "compliance", "pricing"}:
            reasons.append(f"{revised.category.title()} changes can affect risk, contract, or pricing posture.")
        return reasons

    def _recommended_action(self, change_type: str, req: RfpRequirement, risk_level: str) -> str:
        if change_type == "added":
            return f"Add response coverage, citations, and reviewer approval for the new {req.category} requirement."
        if change_type == "changed":
            return f"Revise the affected {req.category} answer and re-check evidence against the amended wording."
        return (
            f"Confirm whether the removed {req.category} requirement can be dropped from draft, "
            "matrix, and review queue."
        )

    def _missing_evidence(self, req: RfpRequirement) -> list[str]:
        if req.evidence_refs:
            return []
        return [f"Attach approved evidence for amended {req.category} requirement before final submission."]

    def _deduction_points(self, change: dict[str, Any]) -> int:
        if change["change_type"] == "removed":
            return 1 if change["risk_level"] == "medium" else 0
        base = {"critical": 10, "high": 7, "medium": 4, "low": 1}.get(change["risk_level"], 2)
        if change["change_type"] == "changed":
            return max(2, base - 2)
        return base

    def _readiness_level(self, score: int) -> str:
        if score >= 90:
            return "ready"
        if score >= 75:
            return "mostly_ready"
        if score >= 60:
            return "at_risk"
        return "blocked"

    def _status(self, summary: dict[str, Any], readiness_impact: dict[str, Any]) -> str:
        if summary["blocking_change_count"] or readiness_impact["submission_gate"] == "blocked":
            return "blocked_pending_amendment_review"
        if summary["change_count"]:
            return "review_required"
        return "no_material_change"

    def _needs_evidence(self, changes: list[dict[str, Any]]) -> bool:
        return any(change["missing_evidence"] for change in changes if change["change_type"] != "removed")

    def _transition_decision(
        self,
        next_state: dict[str, Any],
        summary: dict[str, Any],
        readiness_impact: dict[str, Any],
    ) -> str:
        if next_state["state"] == "route_owner_review":
            return f"route {summary['blocking_change_count']} blocking change(s) to owners"
        if next_state["state"] == "readiness_gate":
            return f"projected readiness is {readiness_impact['projected_readiness_score']}"
        return "continue deterministic amendment workflow"

    def _conditional_routes(
        self,
        changes: list[dict[str, Any]],
        summary: dict[str, Any],
        readiness_impact: dict[str, Any],
    ) -> list[dict[str, Any]]:
        routes = []
        for owner, count in summary["owner_counts"].items():
            routes.append(
                {
                    "route_id": f"route_{owner}",
                    "condition": f"{count} amended requirement change(s) owned by {owner}",
                    "target_state": "route_owner_review",
                    "reviewer_role": self._route_reviewer(owner),
                }
            )
        if readiness_impact["submission_gate"] == "blocked":
            routes.append(
                {
                    "route_id": "route_submission_hold",
                    "condition": "Projected readiness is below the submission threshold or high-risk changes remain.",
                    "target_state": "readiness_gate",
                    "reviewer_role": "executive_sponsor",
                }
            )
        if not changes:
            routes.append(
                {
                    "route_id": "route_no_material_change",
                    "condition": "No changed, added, or removed requirements detected.",
                    "target_state": "readiness_gate",
                    "reviewer_role": "proposal_manager",
                }
            )
        return routes

    def _route_reviewer(self, owner: str) -> str:
        return {
            "security": "security_reviewer",
            "legal": "legal_reviewer",
            "sales": "commercial_reviewer",
            "solutions": "solutions_reviewer",
            "product": "product_reviewer",
        }.get(owner, "proposal_manager")

    def _group_by_category(self, changes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for change in changes:
            grouped.setdefault(change["category"], []).append(change)
        return grouped

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "POST", "path": "/rfp/amendment-impact", "purpose": "Analyze amended RFP impact."},
            {"method": "POST", "path": "/rfp/amendment-impact-pack", "purpose": "Write Markdown/JSON impact pack."},
            {"method": "POST", "path": "/rfp/requirement-matrix", "purpose": "Baseline matrix for evidence impact."},
            {"method": "POST", "path": "/rfp/proposal-readiness-score-pack", "purpose": "Readiness reference."},
        ]

    def _local_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.demo",
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/amendment-impact" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/amendment-impact-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Requirement matching is deterministic token overlap, not a semantic model call.",
            "Reviewer routing is local workflow guidance and does not represent real external approvals.",
            "The sample addendum is synthetic portfolio data for repeatable local verification.",
            (
                "External document repositories, legal systems, and proposal automation tools remain optional "
                "integrations."
            ),
        ]

    def _change_sort(self, change_type: str) -> int:
        return {"added": 0, "changed": 1, "removed": 2}.get(change_type, 9)

    def _severity_weight(self, risk_level: str) -> int:
        return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(risk_level, 0)

    def _md(self, value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
