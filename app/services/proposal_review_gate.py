from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ProposalAssuranceBundleResponse,
    ProposalObservabilityResponse,
    ProposalReviewGateCriterion,
    ProposalReviewGatePackResponse,
    ProposalReviewGateResponse,
)


class ProposalReviewGateService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def gate(
        self,
        trace_id: str,
        assurance: ProposalAssuranceBundleResponse,
        observability: ProposalObservabilityResponse,
    ) -> ProposalReviewGateResponse:
        criteria = self._criteria(assurance, observability)
        transitions = self._state_transitions(trace_id, criteria)
        delegations = self._task_delegations(criteria, assurance, observability)
        assertions = self._eval_assertions(criteria, transitions, assurance, observability)
        score = self._score(criteria, assertions)
        return ProposalReviewGateResponse(
            title="Proposal Intelligence Review Gate",
            gate_id=f"proposal-review-gate-{self._slug(trace_id)}",
            status=self._status(criteria, assertions, score),
            score=score,
            generated_at=datetime.now(UTC).isoformat(),
            injected_dependencies=self._injected_dependencies(),
            summary=self._summary(criteria, delegations, assertions, assurance, observability),
            criteria=criteria,
            state_transitions=transitions,
            task_delegations=delegations,
            eval_assertions=assertions,
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        review_gate: ProposalReviewGateResponse,
        write_artifact: bool = True,
    ) -> ProposalReviewGatePackResponse:
        pack = self._pack_payload(trace_id, review_gate)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "proposal_review_gates"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_review_gate_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_review_gate_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["proposal_review_gate_markdown"] = artifact_path
            pack["artifact_paths"]["proposal_review_gate_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return ProposalReviewGatePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            review_gate=review_gate,
            trace_id=trace_id,
        )

    def _criteria(
        self,
        assurance: ProposalAssuranceBundleResponse,
        observability: ProposalObservabilityResponse,
    ) -> list[ProposalReviewGateCriterion]:
        return [
            self._criterion(
                "gate-sales-commercial-posture",
                "Sales Lead",
                "Win strategy, commercial posture, and buyer-facing caveats are reviewed.",
                [
                    "/proposal/agent-council",
                    "/proposal/assurance-bundle",
                    "/rfp/pricing-risk-memo",
                ],
                self._signals_for(observability, ["sales", "commercial", "pricing"]),
                assurance,
                observability,
            ),
            self._criterion(
                "gate-presales-evidence-readiness",
                "Presales Architect",
                "Technical answers have retrievable evidence, citations, and checkpointed handoffs.",
                [
                    "/proposal/buyer-intelligence",
                    "/proposal/buyer-contracts",
                    "/ops/proposal-observability",
                ],
                self._signals_for(observability, ["presales", "technical", "source", "retrieval", "evidence"]),
                assurance,
                observability,
            ),
            self._criterion(
                "gate-compliance-governance",
                "Compliance Reviewer",
                "Security, privacy, model-risk, and source-trust gates are cleared or owner-routed.",
                [
                    "/governance/model-risk-register",
                    "/evidence/source-trust",
                    "/proposal/decision-provenance",
                ],
                self._signals_for(observability, ["compliance", "privacy", "model", "source", "governance"]),
                assurance,
                observability,
            ),
            self._criterion(
                "gate-procurement-approval",
                "Procurement Lead",
                "Buyer Q&A, contract exceptions, and procurement approvals are visible before submission.",
                [
                    "/procurement/question-risk",
                    "/procurement/risk-desk",
                    "/proposal/assurance-bundle",
                ],
                self._signals_for(observability, ["procurement", "contract", "buyer", "commercial"]),
                assurance,
                observability,
            ),
        ]

    def _criterion(
        self,
        criterion_id: str,
        owner_role: str,
        decision_area: str,
        required_evidence: list[str],
        review_signals: list[dict[str, Any]],
        assurance: ProposalAssuranceBundleResponse,
        observability: ProposalObservabilityResponse,
    ) -> ProposalReviewGateCriterion:
        related_manifest = [
            item.source_endpoint
            for item in assurance.artifact_manifest
            if item.source_endpoint in required_evidence or self._owner_matches(item.owner_role, owner_role)
        ]
        observed_evidence = sorted(set(related_manifest + [signal["signal_id"] for signal in review_signals[:4]]))
        governance_findings = self._findings_for(observability, owner_role)
        blocking = any(
            item.blocking and self._owner_matches(item.owner_role, owner_role)
            for item in assurance.artifact_manifest
        )
        open_actions = [
            signal["decision_area"] for signal in review_signals[:4]
        ] + [finding["required_action"] for finding in governance_findings[:3]]
        status = "blocked" if blocking else "needs_review" if open_actions else "pass"
        score = max(0, 100 - len(open_actions) * 8 - (35 if blocking else 0))
        delegated_to = sorted(
            {
                str(signal["owner_role"])
                for signal in review_signals
                if signal.get("owner_role") and signal.get("owner_role") != "n/a"
            }
            | {owner_role}
        )
        return ProposalReviewGateCriterion(
            criterion_id=criterion_id,
            owner_role=owner_role,
            decision_area=decision_area,
            status=status,
            score=score,
            required_evidence=required_evidence,
            observed_evidence=observed_evidence,
            open_actions=open_actions or ["No open action for this role in the current local run."],
            delegated_to=delegated_to,
            endpoint_refs=required_evidence,
        )

    def _signals_for(self, observability: ProposalObservabilityResponse, keywords: list[str]) -> list[dict[str, Any]]:
        rows = []
        for signal in observability.human_review_signals:
            haystack = " ".join(
                str(signal.get(key, ""))
                for key in ("owner_role", "decision_area", "signal_type", "signal_id", "status")
            ).lower()
            if any(keyword in haystack for keyword in keywords):
                rows.append(signal)
        return rows

    def _findings_for(self, observability: ProposalObservabilityResponse, owner_role: str) -> list[dict[str, Any]]:
        owner_tokens = {token for token in owner_role.lower().replace("/", " ").split() if token}
        rows = []
        for finding in observability.governance_findings:
            haystack = str(finding.get("owner_role", "")).lower()
            if owner_tokens & set(haystack.replace("/", " ").split()):
                rows.append(finding)
        return rows

    def _owner_matches(self, observed: str, expected: str) -> bool:
        observed_tokens = set(observed.lower().replace("/", " ").split())
        expected_tokens = set(expected.lower().replace("/", " ").split())
        return bool(observed_tokens & expected_tokens)

    def _state_transitions(
        self,
        trace_id: str,
        criteria: list[ProposalReviewGateCriterion],
    ) -> list[dict[str, Any]]:
        transitions = []
        prior_state = "review_gate_started"
        for sequence, criterion in enumerate(criteria, start=1):
            next_state = f"review_{self._slug(criterion.owner_role)}"
            transitions.append(
                {
                    "transition_id": f"review-gate-transition-{sequence:02d}",
                    "sequence": sequence,
                    "from_state": prior_state,
                    "to_state": next_state,
                    "condition": criterion.status,
                    "decision": "hold_for_owner" if criterion.status != "pass" else "accept",
                    "checkpoint_key": f"{self._slug(trace_id)}:{sequence:02d}:{next_state}",
                    "criterion_id": criterion.criterion_id,
                    "owner_role": criterion.owner_role,
                }
            )
            prior_state = next_state
        return transitions

    def _task_delegations(
        self,
        criteria: list[ProposalReviewGateCriterion],
        assurance: ProposalAssuranceBundleResponse,
        observability: ProposalObservabilityResponse,
    ) -> list[dict[str, Any]]:
        delegated = []
        assurance_queue = {
            f"{item['item_id']}:{item['owner_role']}"
            for item in assurance.reviewer_queue
        }
        for criterion in criteria:
            delegated.append(
                {
                    "delegation_id": f"delegation-{self._slug(criterion.owner_role)}",
                    "owner_role": criterion.owner_role,
                    "status": criterion.status,
                    "task_count": len(criterion.open_actions),
                    "required_before": "customer-facing RFP submission",
                    "source_criteria": criterion.criterion_id,
                    "delegated_to": criterion.delegated_to,
                    "related_assurance_queue_items": sorted(
                        item for item in assurance_queue if self._slug(criterion.owner_role) in self._slug(item)
                    ),
                    "observability_signal_count": len(
                        self._signals_for(observability, criterion.owner_role.lower().split())
                    ),
                }
            )
        return delegated

    def _eval_assertions(
        self,
        criteria: list[ProposalReviewGateCriterion],
        transitions: list[dict[str, Any]],
        assurance: ProposalAssuranceBundleResponse,
        observability: ProposalObservabilityResponse,
    ) -> list[dict[str, Any]]:
        roles = {criterion.owner_role for criterion in criteria}
        required_roles = {"Sales Lead", "Presales Architect", "Compliance Reviewer", "Procurement Lead"}
        return [
            {
                "assertion_id": "review-gate-required-roles",
                "assertion": "sales, presales, compliance, and procurement criteria are present",
                "expected": sorted(required_roles),
                "observed": sorted(roles),
                "passed": required_roles <= roles,
            },
            {
                "assertion_id": "review-gate-structured-evidence",
                "assertion": "each role criterion carries endpoint evidence and observed local evidence",
                "expected": len(criteria),
                "observed": sum(bool(row.endpoint_refs and row.observed_evidence) for row in criteria),
                "passed": all(row.endpoint_refs and row.observed_evidence for row in criteria),
            },
            {
                "assertion_id": "review-gate-checkpointed-transitions",
                "assertion": "every role criterion has a traceable checkpoint transition",
                "expected": len(criteria),
                "observed": sum(bool(row.get("checkpoint_key")) for row in transitions),
                "passed": len(transitions) == len(criteria) and all(row.get("checkpoint_key") for row in transitions),
            },
            {
                "assertion_id": "review-gate-assurance-source-ready",
                "assertion": "source assurance is high enough for reviewer gating",
                "expected": "score >= 80",
                "observed": assurance.score,
                "passed": assurance.score >= 80,
            },
            {
                "assertion_id": "review-gate-observability-source-ready",
                "assertion": "observability has trace, governance, and human-review inputs",
                "expected": "trace spans and review signals",
                "observed": observability.summary,
                "passed": observability.summary.get("trace_span_count", 0) >= 20
                and observability.summary.get("human_review_signal_count", 0) > 0,
            },
            {
                "assertion_id": "review-gate-provider-optional",
                "assertion": "review gate does not require OpenAI or Azure OpenAI credentials",
                "expected": False,
                "observed": self.settings.provider_mode != "mock",
                "passed": self.settings.provider_mode == "mock",
            },
        ]

    def _score(self, criteria: list[ProposalReviewGateCriterion], assertions: list[dict[str, Any]]) -> int:
        criterion_score = sum(criterion.score for criterion in criteria) / len(criteria) if criteria else 0
        assertion_score = (
            100 * sum(assertion["passed"] for assertion in assertions) / len(assertions)
            if assertions
            else 0
        )
        blocked_penalty = 20 * sum(criterion.status == "blocked" for criterion in criteria)
        return max(0, round(criterion_score * 0.6 + assertion_score * 0.4 - blocked_penalty))

    def _status(
        self,
        criteria: list[ProposalReviewGateCriterion],
        assertions: list[dict[str, Any]],
        score: int,
    ) -> str:
        if any(criterion.status == "blocked" for criterion in criteria) or any(not row["passed"] for row in assertions):
            return "blocked_by_review_gate"
        if any(criterion.status == "needs_review" for criterion in criteria) or score < 90:
            return "requires_role_review"
        return "ready_for_buyer_review"

    def _summary(
        self,
        criteria: list[ProposalReviewGateCriterion],
        delegations: list[dict[str, Any]],
        assertions: list[dict[str, Any]],
        assurance: ProposalAssuranceBundleResponse,
        observability: ProposalObservabilityResponse,
    ) -> dict[str, Any]:
        statuses = Counter(criterion.status for criterion in criteria)
        return {
            "criterion_count": len(criteria),
            "status_counts": dict(sorted(statuses.items())),
            "open_action_count": sum(len(criterion.open_actions) for criterion in criteria),
            "delegation_count": len(delegations),
            "eval_assertion_count": len(assertions),
            "eval_assertions_passed": sum(assertion["passed"] for assertion in assertions),
            "source_assurance_status": assurance.status,
            "source_assurance_score": assurance.score,
            "source_observability_status": observability.status,
            "source_trace_span_count": observability.summary.get("trace_span_count", 0),
            "radar_patterns_used": [
                "typed contracts",
                "structured outputs",
                "dependency injection",
                "eval-friendly design",
                "role crews",
                "task delegation",
                "checkpointing",
                "traceable node transitions",
            ],
        }

    def _injected_dependencies(self) -> dict[str, Any]:
        return {
            "service": "ProposalReviewGateService",
            "settings_provider_mode": self.settings.provider_mode,
            "settings_vector_store_mode": self.settings.vector_store_mode,
            "storage_dir": str(self.settings.storage_dir),
            "external_provider_required": False,
        }

    def _pack_payload(self, trace_id: str, review_gate: ProposalReviewGateResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Intelligence Review Gate Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "review_gate": review_gate.model_dump(mode="json"),
            "reviewer_controls": [
                "Clear non-pass role criteria before customer-facing RFP submission.",
                "Use the delegated owner rows as local handoff tasks; do not treat them as automated approvals.",
                (
                    "Regenerate after changing buyer workflow, assurance, observability, source trust, "
                    "or procurement policy."
                ),
                (
                    "Keep provider mode local/mock unless governance owners explicitly approve optional "
                    "external providers."
                ),
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        gate = pack["review_gate"]
        summary = gate["summary"]
        lines = [
            "# Proposal Intelligence Review Gate Pack",
            "",
            "## Summary",
            "",
            f"- Status: {gate['status']}",
            f"- Score: {gate['score']}",
            f"- Criteria: {summary['criterion_count']}",
            f"- Open actions: {summary['open_action_count']}",
            f"- Eval assertions: {summary['eval_assertions_passed']}/{summary['eval_assertion_count']}",
            f"- Provider mode: {gate['injected_dependencies']['settings_provider_mode']}",
            "",
            "## Role Criteria",
            "",
            "| Criterion | Owner | Status | Score | Endpoints |",
            "| --- | --- | --- | ---: | --- |",
        ]
        for criterion in gate["criteria"]:
            lines.append(
                f"| {criterion['criterion_id']} | {self._md(criterion['owner_role'])} | "
                f"{criterion['status']} | {criterion['score']} | "
                f"{self._md(', '.join(criterion['endpoint_refs']))} |"
            )
        lines.extend(["", "## Task Delegations", ""])
        for row in gate["task_delegations"]:
            delegated = ", ".join(row["delegated_to"])
            lines.append(
                f"- {row['delegation_id']} ({row['status']}): {self._md(delegated)} "
                f"before {self._md(row['required_before'])}"
            )
        lines.extend(["", "## State Transitions", ""])
        lines.append("| Seq | From | To | Decision | Checkpoint |")
        lines.append("| ---: | --- | --- | --- | --- |")
        for transition in gate["state_transitions"]:
            lines.append(
                f"| {transition['sequence']} | {self._md(transition['from_state'])} | "
                f"{self._md(transition['to_state'])} | {transition['decision']} | "
                f"`{self._md(transition['checkpoint_key'])}` |"
            )
        lines.extend(["", "## Eval Assertions", ""])
        for assertion in gate["eval_assertions"]:
            result = "pass" if assertion["passed"] else "fail"
            lines.append(f"- {assertion['assertion_id']} ({result}): {self._md(assertion['assertion'])}")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in gate["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in gate["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/proposal/review-gate", "purpose": "View role-based review gate."},
            {"method": "POST", "path": "/proposal/review-gate-pack", "purpose": "Write review gate artifacts."},
            {"method": "GET", "path": "/proposal/assurance-bundle", "purpose": "Source assurance controls."},
            {"method": "GET", "path": "/ops/proposal-observability", "purpose": "Source trace and HITL signals."},
            {"method": "GET", "path": "/proposal/agent-council", "purpose": "Source role crew handoffs."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/proposal/review-gate" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/proposal/review-gate-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "proposal/review-gate|Proposal Intelligence Review Gate|proposal_review_gates" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\proposal_review_gates -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The review gate aggregates local structured outputs; it is not a live approval or ticketing system.",
            (
                "Role criteria are deterministic controls over sample/local evidence and must be reconciled "
                "with real owners."
            ),
            "Task delegations are local handoff records and do not write to CRM, Slack, procurement, or GRC tools.",
            (
                "OpenAI, Azure OpenAI, Azure AI Search, and external procurement systems remain optional "
                "and are not called."
            ),
        ]

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
