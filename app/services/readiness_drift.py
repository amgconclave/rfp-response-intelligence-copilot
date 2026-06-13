from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ProposalReadinessDriftFinding,
    ProposalReadinessDriftPackResponse,
    ProposalReadinessDriftResponse,
    ProposalReadinessDriftTransition,
    ProposalReadinessScorePackResponse,
)


class ProposalReadinessDriftService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def compare(
        self,
        trace_id: str,
        current_pack: ProposalReadinessScorePackResponse,
        baseline_snapshot: dict[str, Any] | None = None,
        score_drop_warn: int = 5,
        score_drop_block: int = 12,
        completeness_drop_warn: int = 5,
        evidence_drop_warn: float = 0.08,
        reviewer_queue_growth_warn: int = 2,
    ) -> ProposalReadinessDriftResponse:
        baseline = self._normalize_snapshot(baseline_snapshot or self._default_baseline_snapshot())
        current = self._snapshot_from_pack(current_pack)
        findings = self._findings(
            trace_id,
            baseline,
            current,
            score_drop_warn,
            score_drop_block,
            completeness_drop_warn,
            evidence_drop_warn,
            reviewer_queue_growth_warn,
        )
        severity_counts = Counter(finding.severity for finding in findings)
        status = self._status(findings)
        current_state = self._current_state(status)
        workflow = self._workflow(current_state, findings)
        summary = {
            "status": status,
            "current_state": current_state,
            "finding_count": len(findings),
            "critical_count": severity_counts.get("critical", 0),
            "high_count": severity_counts.get("high", 0),
            "medium_count": severity_counts.get("medium", 0),
            "low_count": severity_counts.get("low", 0),
            "score_delta": round(current["readiness_score"] - baseline["readiness_score"], 3),
            "section_completeness_delta": round(
                current["section_completeness_score"] - baseline["section_completeness_score"],
                3,
            ),
            "evidence_coverage_delta": round(
                current["evidence_coverage"] - baseline["evidence_coverage"],
                3,
            ),
            "reviewer_queue_delta": (
                current["human_review_queue_count"] - baseline["human_review_queue_count"]
            ),
            "release_gate": "blocked" if status == "blocked" else "human_review" if findings else "pass",
            "patterns_implemented": [
                "typed_contracts",
                "structured_outputs",
                "conditional_routing",
                "traceable_node_transitions",
            ],
        }
        return ProposalReadinessDriftResponse(
            title="Proposal Readiness Drift Monitor",
            status=status,
            current_state=current_state,
            summary=summary,
            baseline_snapshot=baseline,
            current_snapshot=current,
            drift_findings=findings,
            reviewer_routes=self._reviewer_routes(findings),
            workflow=workflow,
            trace_spans=self._trace_spans(trace_id, findings, workflow),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        current_pack: ProposalReadinessScorePackResponse,
        drift: ProposalReadinessDriftResponse | None = None,
        baseline_snapshot: dict[str, Any] | None = None,
        score_drop_warn: int = 5,
        score_drop_block: int = 12,
        completeness_drop_warn: int = 5,
        evidence_drop_warn: float = 0.08,
        reviewer_queue_growth_warn: int = 2,
        write_artifact: bool = True,
    ) -> ProposalReadinessDriftPackResponse:
        drift = drift or self.compare(
            f"{trace_id}-drift",
            current_pack,
            baseline_snapshot=baseline_snapshot,
            score_drop_warn=score_drop_warn,
            score_drop_block=score_drop_block,
            completeness_drop_warn=completeness_drop_warn,
            evidence_drop_warn=evidence_drop_warn,
            reviewer_queue_growth_warn=reviewer_queue_growth_warn,
        )
        payload = {
            "title": "Proposal Readiness Drift Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
            "drift": drift.model_dump(mode="json"),
            "current_readiness_pack": {
                "status": current_pack.status,
                "readiness_score": current_pack.readiness_score,
                "readiness_level": current_pack.readiness_level,
                "artifact_path": current_pack.artifact_path,
                "json_artifact_path": current_pack.json_artifact_path,
            },
            "governance_controls": [
                "Treat readiness regressions as release-gate evidence, not advisory dashboard noise.",
                "Require owner disposition for high or critical drift before executive submission review.",
                "Keep baseline and current snapshots with trace spans for reviewer replay.",
            ],
            "reviewer_checklist": [
                "Confirm baseline snapshot came from an approved proposal state.",
                "Review drift findings by severity and owner route.",
                "Run standard eval, red-team, dashboard smoke, and demo commands before clearing drift.",
            ],
            "artifact_paths": {},
        }
        markdown = self._render_markdown(payload)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "readiness_drift"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"proposal_readiness_drift_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_readiness_drift_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            payload["artifact_paths"] = {
                "proposal_readiness_drift_markdown": artifact_path,
                "proposal_readiness_drift_json": json_artifact_path,
            }
            markdown = self._render_markdown(payload)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return ProposalReadinessDriftPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=payload,
            drift=drift,
            current_pack=current_pack,
            trace_id=trace_id,
        )

    def _snapshot_from_pack(self, pack: ProposalReadinessScorePackResponse) -> dict[str, Any]:
        payload = pack.pack
        executive = payload.get("executive_readiness_artifacts", {}).get("executive_summary", {})
        compliance = payload.get("compliance_risk", {})
        section = payload.get("section_completeness", {})
        evidence = payload.get("evidence_coverage", {})
        scorecard = payload.get("readiness_scorecard", {})
        reviewer_bottlenecks = payload.get("reviewer_bottlenecks", [])
        human_queue = payload.get("human_review_queue", [])
        return self._normalize_snapshot(
            {
                "snapshot_id": f"current:{pack.trace_id}",
                "snapshot_source": "proposal_readiness_score_pack",
                "readiness_score": pack.readiness_score,
                "readiness_level": pack.readiness_level,
                "pack_status": pack.status,
                "section_completeness_score": executive.get(
                    "section_completeness_score",
                    section.get("average_score", 0),
                ),
                "section_status": section.get("status", "unknown"),
                "evidence_coverage": executive.get(
                    "evidence_coverage",
                    evidence.get("overall_coverage", scorecard.get("evidence_coverage", 0)),
                ),
                "uncovered_requirement_count": evidence.get("uncovered_requirement_count", 0),
                "compliance_risk_level": executive.get(
                    "compliance_risk_level",
                    compliance.get("risk_level", "unknown"),
                ),
                "compliance_risk_score": compliance.get("risk_score", 0),
                "reviewer_bottleneck_count": executive.get(
                    "reviewer_bottleneck_count",
                    len(reviewer_bottlenecks),
                ),
                "reviewer_escalation_count": sum(
                    1 for item in reviewer_bottlenecks if item.get("escalation_required")
                ),
                "human_review_queue_count": len(human_queue),
                "blocker_count": len(scorecard.get("blockers", [])),
                "artifact_path": pack.artifact_path,
                "json_artifact_path": pack.json_artifact_path,
            }
        )

    def _default_baseline_snapshot(self) -> dict[str, Any]:
        return {
            "snapshot_id": "approved-baseline:local-demo",
            "snapshot_source": "local_default_approved_state",
            "readiness_score": 90,
            "readiness_level": "ready",
            "pack_status": "ready_for_executive_review",
            "section_completeness_score": 90,
            "section_status": "pass",
            "evidence_coverage": 0.9,
            "uncovered_requirement_count": 0,
            "compliance_risk_level": "low",
            "compliance_risk_score": 15,
            "reviewer_bottleneck_count": 0,
            "reviewer_escalation_count": 0,
            "human_review_queue_count": 0,
            "blocker_count": 0,
        }

    def _normalize_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "snapshot_id": str(snapshot.get("snapshot_id") or "readiness-snapshot"),
            "snapshot_source": str(snapshot.get("snapshot_source") or "request"),
            "readiness_score": self._int_value(snapshot.get("readiness_score"), 0),
            "readiness_level": str(snapshot.get("readiness_level") or "unknown"),
            "pack_status": str(snapshot.get("pack_status") or snapshot.get("status") or "unknown"),
            "section_completeness_score": self._int_value(
                snapshot.get("section_completeness_score"),
                0,
            ),
            "section_status": str(snapshot.get("section_status") or "unknown"),
            "evidence_coverage": self._float_value(snapshot.get("evidence_coverage"), 0.0),
            "uncovered_requirement_count": self._int_value(
                snapshot.get("uncovered_requirement_count"),
                0,
            ),
            "compliance_risk_level": str(snapshot.get("compliance_risk_level") or "unknown"),
            "compliance_risk_score": self._int_value(snapshot.get("compliance_risk_score"), 0),
            "reviewer_bottleneck_count": self._int_value(
                snapshot.get("reviewer_bottleneck_count"),
                0,
            ),
            "reviewer_escalation_count": self._int_value(
                snapshot.get("reviewer_escalation_count"),
                0,
            ),
            "human_review_queue_count": self._int_value(snapshot.get("human_review_queue_count"), 0),
            "blocker_count": self._int_value(snapshot.get("blocker_count"), 0),
        }
        if snapshot.get("artifact_path"):
            normalized["artifact_path"] = snapshot["artifact_path"]
        if snapshot.get("json_artifact_path"):
            normalized["json_artifact_path"] = snapshot["json_artifact_path"]
        return normalized

    def _findings(
        self,
        trace_id: str,
        baseline: dict[str, Any],
        current: dict[str, Any],
        score_drop_warn: int,
        score_drop_block: int,
        completeness_drop_warn: int,
        evidence_drop_warn: float,
        reviewer_queue_growth_warn: int,
    ) -> list[ProposalReadinessDriftFinding]:
        findings: list[ProposalReadinessDriftFinding] = []
        score_delta = current["readiness_score"] - baseline["readiness_score"]
        if score_delta <= -score_drop_warn:
            severity = "critical" if score_delta <= -score_drop_block else "high"
            findings.append(
                self._finding(
                    trace_id,
                    len(findings) + 1,
                    "readiness_score",
                    baseline["readiness_score"],
                    current["readiness_score"],
                    score_delta,
                    severity,
                    "proposal_manager",
                    "block_submission" if severity == "critical" else "owner_review",
                    "Investigate readiness score regression before executive signoff.",
                    {"thresholds": {"warn": score_drop_warn, "block": score_drop_block}},
                )
            )

        completeness_delta = (
            current["section_completeness_score"] - baseline["section_completeness_score"]
        )
        if completeness_delta <= -completeness_drop_warn:
            findings.append(
                self._finding(
                    trace_id,
                    len(findings) + 1,
                    "section_completeness",
                    baseline["section_completeness_score"],
                    current["section_completeness_score"],
                    completeness_delta,
                    "high",
                    "proposal_manager",
                    "owner_review",
                    "Refresh incomplete sections and attach evidence acceptance criteria.",
                    {"current_section_status": current["section_status"]},
                )
            )

        evidence_delta = current["evidence_coverage"] - baseline["evidence_coverage"]
        if evidence_delta <= -evidence_drop_warn or current["uncovered_requirement_count"] > 0:
            severity = "high" if evidence_delta <= -evidence_drop_warn else "medium"
            findings.append(
                self._finding(
                    trace_id,
                    len(findings) + 1,
                    "evidence_coverage",
                    baseline["evidence_coverage"],
                    current["evidence_coverage"],
                    round(evidence_delta, 3),
                    severity,
                    "solutions_engineering",
                    "evidence_refresh",
                    "Close uncovered requirements or document explicit missing-evidence exceptions.",
                    {
                        "uncovered_requirement_count": current["uncovered_requirement_count"],
                        "threshold": evidence_drop_warn,
                    },
                )
            )

        baseline_risk = self._risk_rank(baseline["compliance_risk_level"])
        current_risk = self._risk_rank(current["compliance_risk_level"])
        if current_risk > baseline_risk:
            severity = "critical" if current["compliance_risk_level"] == "critical" else "high"
            findings.append(
                self._finding(
                    trace_id,
                    len(findings) + 1,
                    "compliance_risk",
                    baseline["compliance_risk_level"],
                    current["compliance_risk_level"],
                    current_risk - baseline_risk,
                    severity,
                    "security_legal",
                    "block_submission" if severity == "critical" else "compliance_review",
                    "Route risk increase to security/legal owners with exception criteria.",
                    {"risk_score": current["compliance_risk_score"]},
                )
            )

        queue_delta = current["human_review_queue_count"] - baseline["human_review_queue_count"]
        if queue_delta >= reviewer_queue_growth_warn or current["reviewer_escalation_count"] > 0:
            findings.append(
                self._finding(
                    trace_id,
                    len(findings) + 1,
                    "reviewer_bottlenecks",
                    baseline["human_review_queue_count"],
                    current["human_review_queue_count"],
                    queue_delta,
                    "medium",
                    "proposal_operations",
                    "expedite_review",
                    "Rebalance reviewer workload and escalate blocked signoffs in the readiness standup.",
                    {
                        "reviewer_bottleneck_count": current["reviewer_bottleneck_count"],
                        "reviewer_escalation_count": current["reviewer_escalation_count"],
                    },
                )
            )

        if current["blocker_count"] > baseline["blocker_count"]:
            findings.append(
                self._finding(
                    trace_id,
                    len(findings) + 1,
                    "blocker_growth",
                    baseline["blocker_count"],
                    current["blocker_count"],
                    current["blocker_count"] - baseline["blocker_count"],
                    "high",
                    "proposal_manager",
                    "blocker_triage",
                    "Disposition new blockers before package release or attach executive exception notes.",
                    {},
                )
            )
        return findings

    def _finding(
        self,
        trace_id: str,
        sequence: int,
        signal: str,
        baseline_value: float | int | str | None,
        current_value: float | int | str | None,
        delta: float | int | None,
        severity: str,
        owner_role: str,
        route_decision: str,
        recommended_action: str,
        evidence: dict[str, Any],
    ) -> ProposalReadinessDriftFinding:
        finding_id = f"readiness-drift-{sequence:02d}-{signal}"
        transitions = self._transition_trace(trace_id, finding_id, severity, route_decision)
        return ProposalReadinessDriftFinding(
            finding_id=finding_id,
            signal=signal,
            baseline_value=baseline_value,
            current_value=current_value,
            delta=delta,
            severity=severity,
            owner_role=owner_role,
            route_decision=route_decision,
            recommended_action=recommended_action,
            transition_trace=transitions,
            evidence=evidence,
        )

    def _transition_trace(
        self,
        trace_id: str,
        finding_id: str,
        severity: str,
        route_decision: str,
    ) -> list[ProposalReadinessDriftTransition]:
        routing_state = "executive_exception_gate" if severity == "critical" else "owner_review_queue"
        return [
            ProposalReadinessDriftTransition(
                transition_id=f"{trace_id}:{finding_id}:snapshot",
                sequence=1,
                from_state=None,
                to_state="snapshot_loaded",
                status="pass",
                decision="compare_against_baseline",
                checkpoint_key="load_baseline_and_current_readiness",
                trace_note="Baseline and current readiness snapshots normalized into typed fields.",
            ),
            ProposalReadinessDriftTransition(
                transition_id=f"{trace_id}:{finding_id}:route",
                sequence=2,
                from_state="snapshot_loaded",
                to_state=routing_state,
                status="blocked" if severity == "critical" else "review",
                decision=route_decision,
                checkpoint_key=f"route_{severity}_drift",
                trace_note=f"Conditional routing selected {routing_state} for {severity} drift.",
            ),
        ]

    def _status(self, findings: list[ProposalReadinessDriftFinding]) -> str:
        if any(finding.severity == "critical" for finding in findings):
            return "blocked"
        if any(finding.severity in {"high", "medium"} for finding in findings):
            return "needs_review"
        return "stable"

    def _current_state(self, status: str) -> str:
        if status == "blocked":
            return "executive_exception_gate"
        if status == "needs_review":
            return "owner_review_queue"
        return "ready_baseline_intact"

    def _workflow(
        self,
        current_state: str,
        findings: list[ProposalReadinessDriftFinding],
    ) -> dict[str, Any]:
        states = [
            {"state": "snapshot_loaded", "status": "complete"},
            {"state": "drift_scored", "status": "complete"},
            {
                "state": "owner_review_queue",
                "status": "active" if current_state == "owner_review_queue" else "skipped",
            },
            {
                "state": "executive_exception_gate",
                "status": "active" if current_state == "executive_exception_gate" else "skipped",
            },
            {
                "state": "ready_baseline_intact",
                "status": "active" if current_state == "ready_baseline_intact" else "pending",
            },
        ]
        transitions = [
            {
                "from_state": "snapshot_loaded",
                "to_state": "drift_scored",
                "condition": "baseline and current snapshots normalized",
                "decision": "score_drift",
            },
            {
                "from_state": "drift_scored",
                "to_state": current_state,
                "condition": self._workflow_condition(findings),
                "decision": "conditional_readiness_routing",
            },
        ]
        return {
            "pattern": "state_machine_workflow_with_conditional_routing",
            "current_state": current_state,
            "states": states,
            "transitions": transitions,
            "checkpoint_count": len(states),
            "finding_count": len(findings),
        }

    def _workflow_condition(self, findings: list[ProposalReadinessDriftFinding]) -> str:
        if any(finding.severity == "critical" for finding in findings):
            return "critical drift blocks release without executive exception"
        if findings:
            return "non-critical drift requires owner review before release"
        return "no drift findings above configured thresholds"

    def _reviewer_routes(
        self,
        findings: list[ProposalReadinessDriftFinding],
    ) -> list[dict[str, Any]]:
        return [
            {
                "route_id": f"route-{finding.finding_id}",
                "owner_role": finding.owner_role,
                "severity": finding.severity,
                "route_decision": finding.route_decision,
                "status": "blocked" if finding.severity == "critical" else "open",
                "required_action": finding.recommended_action,
                "related_signal": finding.signal,
            }
            for finding in findings
        ]

    def _trace_spans(
        self,
        trace_id: str,
        findings: list[ProposalReadinessDriftFinding],
        workflow: dict[str, Any],
    ) -> list[dict[str, Any]]:
        spans = [
            {
                "span_id": f"{trace_id}:snapshot",
                "name": "normalize_readiness_snapshots",
                "status": "pass",
                "pattern": "typed_contracts",
            },
            {
                "span_id": f"{trace_id}:workflow",
                "name": "route_readiness_drift_workflow",
                "status": workflow["current_state"],
                "pattern": "traceable_node_transitions",
                "checkpoint_count": workflow["checkpoint_count"],
            },
        ]
        spans.extend(
            {
                "span_id": f"{trace_id}:{finding.finding_id}",
                "name": "readiness_drift_finding",
                "status": finding.severity,
                "signal": finding.signal,
                "owner_role": finding.owner_role,
                "route_decision": finding.route_decision,
            }
            for finding in findings
        )
        return spans

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {
                "method": "POST",
                "path": "/rfp/proposal-readiness-drift",
                "purpose": "Compare current readiness against an approved baseline snapshot.",
            },
            {
                "method": "POST",
                "path": "/rfp/proposal-readiness-drift-pack",
                "purpose": "Write Markdown/JSON readiness drift artifacts.",
                "expected_artifacts": ["storage/readiness_drift/*.md", "storage/readiness_drift/*.json"],
            },
            {
                "method": "POST",
                "path": "/rfp/proposal-readiness-score-pack",
                "purpose": "Produces the current structured readiness pack consumed by drift monitoring.",
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/proposal-readiness-drift-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "proposal-readiness-drift|Proposal Readiness Drift|readiness_drift" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\readiness_drift -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
            "python -m pytest -q",
            "python -m ruff check .",
        ]

    def _limitations(self) -> list[str]:
        return [
            "Baseline snapshots are local structured inputs or deterministic demo defaults, not CRM records.",
            "Drift routing is decision support and does not replace legal, security, or executive approval.",
            "The monitor compares readiness signals; it does not call external providers or mutate score rules.",
        ]

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        drift = pack["drift"]
        summary = drift["summary"]
        lines = [
            f"# {pack['title']}",
            "",
            f"- Generated at: {pack['generated_at']}",
            f"- Trace ID: {pack['trace_id']}",
            f"- Status: {drift['status']}",
            f"- Current state: {drift['current_state']}",
            f"- Findings: {summary['finding_count']}",
            f"- Score delta: {summary['score_delta']}",
            f"- Evidence coverage delta: {summary['evidence_coverage_delta']}",
            "",
            "## Drift Findings",
            "",
            "| Finding | Signal | Severity | Baseline | Current | Delta | Owner | Route |",
            "| --- | --- | --- | --- | --- | ---: | --- | --- |",
        ]
        if drift["drift_findings"]:
            for finding in drift["drift_findings"]:
                lines.append(
                    "| "
                    f"{self._md(finding['finding_id'])} | "
                    f"{self._md(finding['signal'])} | "
                    f"{finding['severity']} | "
                    f"{self._md(finding['baseline_value'])} | "
                    f"{self._md(finding['current_value'])} | "
                    f"{self._md(finding['delta'])} | "
                    f"{self._md(finding['owner_role'])} | "
                    f"{self._md(finding['route_decision'])} |"
                )
        else:
            lines.append("| None | baseline_intact | low | current | current | 0 | proposal_manager | pass |")
        lines.extend(["", "## Reviewer Routes", ""])
        if drift["reviewer_routes"]:
            lines.extend(
                "- {owner_role} / {related_signal}: {required_action}".format(**route)
                for route in drift["reviewer_routes"]
            )
        else:
            lines.append("- No owner review required.")
        lines.extend(["", "## Workflow", ""])
        lines.append(f"- Pattern: {drift['workflow']['pattern']}")
        lines.append(f"- Current state: {drift['workflow']['current_state']}")
        for transition in drift["workflow"]["transitions"]:
            lines.append(
                "- {from_state} -> {to_state}: {decision} ({condition})".format(**transition)
            )
        lines.extend(["", "## Baseline Snapshot", ""])
        lines.extend(f"- {key}: {self._md(value)}" for key, value in drift["baseline_snapshot"].items())
        lines.extend(["", "## Current Snapshot", ""])
        lines.extend(f"- {key}: {self._md(value)}" for key, value in drift["current_snapshot"].items())
        lines.extend(["", "## Governance Controls", ""])
        lines.extend(f"- {item}" for item in pack["governance_controls"])
        lines.extend(["", "## Reviewer Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_checklist"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"- `{command}`" for command in drift["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in drift["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifact Paths", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _risk_rank(self, risk_level: str) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(risk_level, 0)

    def _int_value(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _float_value(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _md(self, value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
