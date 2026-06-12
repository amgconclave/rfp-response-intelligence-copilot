from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import ProposalObservabilityResponse, TraceExportPackResponse, TraceExportResponse


class TraceExportService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def export(
        self,
        trace_id: str,
        observability: ProposalObservabilityResponse,
        dataset_path: str,
        outcomes_fixture_path: str,
        top_k: int,
    ) -> TraceExportResponse:
        spans = self._spans(observability)
        diagnostics = self._diagnostic_manifest(observability)
        governance_summary = self._governance_summary(observability, spans)
        status = self._status(spans, governance_summary)
        return TraceExportResponse(
            title="Proposal Trace Export",
            status=status,
            generated_at=datetime.now(UTC).isoformat(),
            span_count=len(spans),
            exported_spans=spans,
            jsonl_preview=[json.dumps(span, sort_keys=True) for span in spans[:5]],
            eval_dataset_manifest={
                "dataset_path": dataset_path,
                "outcomes_fixture_path": outcomes_fixture_path,
                "top_k": top_k,
                "retrieval_policy_count": observability.experiment_comparison.get("policy_count", 0),
                "eval_question_count": observability.experiment_comparison.get("question_count", 0),
                "recommended_policy_id": observability.experiment_comparison.get("recommended_policy_id"),
            },
            retrieval_diagnostics=diagnostics,
            experiment_comparison=observability.experiment_comparison,
            governance_summary=governance_summary,
            human_review_queue=self._human_review_queue(observability),
            provider_summary=observability.provider_and_cost_signals,
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        trace_export: TraceExportResponse,
        write_artifact: bool = True,
    ) -> TraceExportPackResponse:
        pack = self._pack_payload(trace_id, trace_export)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        jsonl_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "trace_exports"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = self._slug(trace_id)
            markdown_path = pack_dir / f"proposal_trace_export_{safe_trace_id}.md"
            json_path = pack_dir / f"proposal_trace_export_{safe_trace_id}.json"
            jsonl_path = pack_dir / f"proposal_trace_spans_{safe_trace_id}.jsonl"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            jsonl_artifact_path = str(jsonl_path.resolve())
            pack["artifact_paths"]["trace_export_markdown"] = artifact_path
            pack["artifact_paths"]["trace_export_json"] = json_artifact_path
            pack["artifact_paths"]["trace_export_jsonl"] = jsonl_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
            jsonl_path.write_text(
                "\n".join(json.dumps(span, sort_keys=True) for span in trace_export.exported_spans) + "\n",
                encoding="utf-8",
            )

        return TraceExportPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            jsonl_artifact_path=jsonl_artifact_path,
            markdown=markdown,
            pack=pack,
            trace_export=trace_export,
            trace_id=trace_id,
        )

    def _spans(self, observability: ProposalObservabilityResponse) -> list[dict[str, Any]]:
        spans = []
        for sequence, row in enumerate(observability.trace_map, start=1):
            spans.append(
                {
                    "span_id": row["span_id"],
                    "trace_id": row["trace_id"],
                    "parent_trace_id": observability.trace_id,
                    "sequence": sequence,
                    "name": row["trace_type"],
                    "kind": self._kind(row["trace_type"]),
                    "status": row["status"],
                    "owner_role": row["owner_role"],
                    "source_endpoint": row["source"],
                    "evidence": row["evidence"],
                    "attributes": {
                        "proposal_domain": "rfp_response",
                        "local_export": True,
                        "governance_relevant": row["status"] in {"blocked", "needs_review", "open"},
                    },
                }
            )
        return spans

    def _diagnostic_manifest(self, observability: ProposalObservabilityResponse) -> dict[str, Any]:
        diagnostics = observability.retrieval_diagnostics
        policies = Counter(row.get("policy_id", "unknown") for row in diagnostics)
        return {
            "diagnostic_count": len(diagnostics),
            "unsupported_risk_count": sum(1 for row in diagnostics if row.get("unsupported_risk")),
            "citation_miss_count": sum(1 for row in diagnostics if not row.get("citation_hit")),
            "guardrail_trigger_count": sum(len(row.get("guardrails_triggered", [])) for row in diagnostics),
            "policy_counts": dict(sorted(policies.items())),
            "diagnostic_rows": diagnostics[:20],
        }

    def _governance_summary(
        self,
        observability: ProposalObservabilityResponse,
        spans: list[dict[str, Any]],
    ) -> dict[str, Any]:
        statuses = Counter(span["status"] for span in spans)
        finding_statuses = Counter(row["status"] for row in observability.governance_findings)
        return {
            "trace_status_counts": dict(sorted(statuses.items())),
            "governance_finding_count": len(observability.governance_findings),
            "governance_status_counts": dict(sorted(finding_statuses.items())),
            "human_review_signal_count": len(observability.human_review_signals),
            "blocked_span_count": statuses.get("blocked", 0),
            "needs_review_span_count": statuses.get("needs_review", 0),
            "radar_patterns_used": [
                "trace analysis",
                "retrieval diagnostics",
                "experiment comparison",
                "governance",
                "human-in-the-loop",
            ],
        }

    def _human_review_queue(self, observability: ProposalObservabilityResponse) -> list[dict[str, Any]]:
        return [
            {
                "review_id": row["signal_id"],
                "owner_role": row["owner_role"],
                "status": row["status"],
                "priority": row["priority"],
                "decision_area": row["decision_area"],
                "required_before": row["required_before"],
                "source": "proposal_observability",
            }
            for row in observability.human_review_signals
        ]

    def _status(self, spans: list[dict[str, Any]], governance_summary: dict[str, Any]) -> str:
        if not spans:
            return "empty_trace_export"
        if governance_summary["blocked_span_count"]:
            return "exported_with_blockers"
        if governance_summary["human_review_signal_count"] or governance_summary["governance_finding_count"]:
            return "exported_with_review_items"
        return "ready_for_offline_analysis"

    def _pack_payload(self, trace_id: str, trace_export: TraceExportResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Proposal Trace Export Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "trace_export": trace_export.model_dump(mode="json"),
            "reviewer_controls": [
                "Inspect JSONL spans for blocked or needs_review statuses before proposal submission.",
                "Compare retrieval diagnostics with the recommended policy before changing RAG defaults.",
                "Keep this export local unless customer data retention and privacy review are complete.",
                "Regenerate after changing buyer workflow, retrieval experiments, governance gates, or providers.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        trace_export = pack["trace_export"]
        governance = trace_export["governance_summary"]
        diagnostics = trace_export["retrieval_diagnostics"]
        dataset = trace_export["eval_dataset_manifest"]
        lines = [
            "# Proposal Trace Export Pack",
            "",
            "## Summary",
            "",
            f"- Status: {trace_export['status']}",
            f"- Spans: {trace_export['span_count']}",
            f"- Human review signals: {governance['human_review_signal_count']}",
            f"- Governance findings: {governance['governance_finding_count']}",
            f"- Diagnostics: {diagnostics['diagnostic_count']}",
            f"- Dataset: {self._md(dataset['dataset_path'])}",
            f"- Recommended policy: {self._md(dataset['recommended_policy_id'])}",
            "",
            "## JSONL Preview",
            "",
            "```jsonl",
            *trace_export["jsonl_preview"],
            "```",
            "",
            "## Retrieval Diagnostics",
            "",
            f"- Unsupported risk: {diagnostics['unsupported_risk_count']}",
            f"- Citation misses: {diagnostics['citation_miss_count']}",
            f"- Guardrail triggers: {diagnostics['guardrail_trigger_count']}",
            "",
            "## Human Review Queue",
            "",
        ]
        if trace_export["human_review_queue"]:
            for row in trace_export["human_review_queue"][:20]:
                lines.append(
                    f"- {row['review_id']} ({row['priority']}/{row['status']}): "
                    f"{self._md(row['owner_role'])} before {self._md(row['required_before'])}"
                )
        else:
            lines.append("- No open human-review queue items.")
        lines.extend(["", "## Reviewer Controls", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_controls"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in trace_export["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {self._md(item)}" for item in trace_export["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Generated Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/ops/trace-export", "purpose": "View JSONL-ready trace export."},
            {"method": "POST", "path": "/ops/trace-export-pack", "purpose": "Write trace export artifacts."},
            {"method": "GET", "path": "/ops/proposal-observability", "purpose": "Source observability report."},
            {"method": "POST", "path": "/rag/retrieval-experiments", "purpose": "Source retrieval diagnostics."},
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/ops/trace-export" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/ops/trace-export-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            (
                "Get-ChildItem -Recurse -File storage\\trace_exports -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "JSONL spans are local control-plane records and are not sent to Phoenix, OpenTelemetry, or cloud tracing.",
            "Retrieval diagnostics come from bundled sample eval fixtures and deterministic local retrieval.",
            "Human-review queue entries are workflow artifacts, not live ticket assignments.",
            "OpenAI, Azure OpenAI, and external observability backends remain optional.",
        ]

    def _kind(self, trace_type: str) -> str:
        if trace_type.startswith("retrieval"):
            return "retrieval"
        if trace_type in {"workflow_stage", "workflow_transition"}:
            return "workflow"
        if trace_type == "agent_turn":
            return "agent"
        if trace_type == "provenance_node":
            return "provenance"
        return "internal"

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower() or "local"

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
