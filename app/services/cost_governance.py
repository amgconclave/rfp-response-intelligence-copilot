from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import CostGovernancePackResponse, CostGovernanceResponse
from app.models.domain import UsageMetric
from app.services.metrics import MetricsService


class CostGovernanceService:
    def __init__(self, settings: Settings, metrics: MetricsService) -> None:
        self.settings = settings
        self.metrics = metrics

    def report(
        self,
        trace_id: str,
        daily_rfp_count: int = 3,
        questions_per_rfp: int = 12,
        draft_sections_per_rfp: int = 5,
        eval_runs_per_day: int = 1,
        red_team_runs_per_day: int = 1,
        daily_budget_usd: float = 25.0,
    ) -> CostGovernanceResponse:
        usage_metrics = self.metrics.list_metrics(limit=200)
        token_profile = self._token_profile(usage_metrics)
        workflow_estimates = self._workflow_estimates(
            token_profile,
            daily_rfp_count,
            questions_per_rfp,
            draft_sections_per_rfp,
            eval_runs_per_day,
            red_team_runs_per_day,
        )
        daily_estimated_cost = round(sum(item["estimated_cost"] for item in workflow_estimates), 6)
        governance_status = self._governance_status(daily_estimated_cost, daily_budget_usd)
        budget_summary = {
            "daily_budget_usd": round(daily_budget_usd, 6),
            "daily_estimated_cost": daily_estimated_cost,
            "budget_remaining_usd": round(daily_budget_usd - daily_estimated_cost, 6),
            "budget_utilization": round(daily_estimated_cost / daily_budget_usd, 4) if daily_budget_usd else 1.0,
            "monthly_estimated_cost_22_business_days": round(daily_estimated_cost * 22, 6),
            "current_usage_totals": self.metrics.totals(),
        }
        provider_readiness = self._provider_readiness()
        controls = self._controls(governance_status, provider_readiness, budget_summary)

        return CostGovernanceResponse(
            title="Cost and Provider Governance",
            governance_status=governance_status,
            provider_readiness=provider_readiness,
            token_profile=token_profile,
            workflow_estimates=workflow_estimates,
            budget_summary=budget_summary,
            reviewer_controls=controls,
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        report: CostGovernanceResponse | None = None,
        write_artifact: bool = True,
    ) -> CostGovernancePackResponse:
        governance = report or self.report(f"{trace_id}-report")
        pack = self._pack_payload(trace_id, governance)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "cost_governance"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"cost_governance_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"cost_governance_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["cost_governance_markdown"] = artifact_path
            pack["artifact_paths"]["cost_governance_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return CostGovernancePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            governance=governance,
            trace_id=trace_id,
        )

    def _token_profile(self, usage_metrics: list[UsageMetric]) -> dict[str, Any]:
        if usage_metrics:
            avg_input = round(sum(metric.input_tokens for metric in usage_metrics) / len(usage_metrics), 2)
            avg_output = round(sum(metric.output_tokens for metric in usage_metrics) / len(usage_metrics), 2)
            avg_latency = round(sum(metric.latency_ms for metric in usage_metrics) / len(usage_metrics), 2)
            sample_size = len(usage_metrics)
            source = "observed_usage_metrics"
        else:
            avg_input = 1200.0
            avg_output = 350.0
            avg_latency = 500.0
            sample_size = 0
            source = "deterministic_local_default"
        return {
            "source": source,
            "sample_size": sample_size,
            "average_input_tokens": avg_input,
            "average_output_tokens": avg_output,
            "average_latency_ms": avg_latency,
            "input_cost_per_1k": self.settings.estimated_input_cost_per_1k,
            "output_cost_per_1k": self.settings.estimated_output_cost_per_1k,
            "provider_mode": self.settings.provider_mode,
            "model": self._active_model(),
        }

    def _workflow_estimates(
        self,
        token_profile: dict[str, Any],
        daily_rfp_count: int,
        questions_per_rfp: int,
        draft_sections_per_rfp: int,
        eval_runs_per_day: int,
        red_team_runs_per_day: int,
    ) -> list[dict[str, Any]]:
        query_count = max(daily_rfp_count, 0) * max(questions_per_rfp, 0)
        draft_count = max(daily_rfp_count, 0) * max(draft_sections_per_rfp, 0)
        eval_question_count = max(eval_runs_per_day, 0) * 12
        red_team_question_count = max(red_team_runs_per_day, 0) * 4
        return [
            self._estimate("cited_rfp_questions", query_count, 1.0, token_profile),
            self._estimate("draft_sections", draft_count, 1.6, token_profile),
            self._estimate("standard_eval_questions", eval_question_count, 1.1, token_profile),
            self._estimate("red_team_questions", red_team_question_count, 1.0, token_profile),
            self._estimate("artifact_pack_generation", max(daily_rfp_count, 0) * 8, 0.35, token_profile),
        ]

    def _estimate(
        self,
        workflow_name: str,
        requests: int,
        multiplier: float,
        token_profile: dict[str, Any],
    ) -> dict[str, Any]:
        input_tokens = int(round(requests * token_profile["average_input_tokens"] * multiplier))
        output_tokens = int(round(requests * token_profile["average_output_tokens"] * multiplier))
        estimated_cost = round(
            input_tokens / 1000 * self.settings.estimated_input_cost_per_1k
            + output_tokens / 1000 * self.settings.estimated_output_cost_per_1k,
            6,
        )
        return {
            "workflow_name": workflow_name,
            "request_count": requests,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": estimated_cost,
            "estimated_latency_ms": round(requests * token_profile["average_latency_ms"] * multiplier, 2),
        }

    def _provider_readiness(self) -> dict[str, Any]:
        openai_ready = bool(self.settings.openai_api_key)
        azure_ready = bool(
            self.settings.azure_openai_endpoint
            and self.settings.azure_openai_api_key
            and self.settings.azure_openai_deployment
        )
        external_mode = self.settings.provider_mode.lower() in {"openai", "azure_openai", "azure"}
        missing: list[str] = []
        if self.settings.provider_mode.lower() == "openai" and not openai_ready:
            missing.append("OPENAI_API_KEY")
        if self.settings.provider_mode.lower() in {"azure_openai", "azure"} and not azure_ready:
            for name, value in [
                ("AZURE_OPENAI_ENDPOINT", self.settings.azure_openai_endpoint),
                ("AZURE_OPENAI_API_KEY", self.settings.azure_openai_api_key),
                ("AZURE_OPENAI_DEPLOYMENT", self.settings.azure_openai_deployment),
            ]:
                if not value:
                    missing.append(name)
        return {
            "provider_mode": self.settings.provider_mode,
            "active_model": self._active_model(),
            "local_mock_ready": self.settings.provider_mode == "mock",
            "external_provider_requested": external_mode,
            "openai_configured": openai_ready,
            "azure_openai_configured": azure_ready,
            "vector_store_mode": self.settings.vector_store_mode,
            "missing_required_env": missing,
            "estimated_cost_rates_configured": (
                self.settings.estimated_input_cost_per_1k > 0
                or self.settings.estimated_output_cost_per_1k > 0
            ),
        }

    def _active_model(self) -> str:
        if self.settings.provider_mode.lower() == "mock":
            return "mock-local"
        if self.settings.provider_mode.lower() == "openai":
            return self.settings.openai_model
        if self.settings.provider_mode.lower() in {"azure_openai", "azure"}:
            return self.settings.azure_openai_deployment or "azure-openai-not-configured"
        return self.settings.provider_mode

    def _governance_status(self, daily_estimated_cost: float, daily_budget_usd: float) -> str:
        if daily_budget_usd <= 0:
            return "blocked_no_budget"
        utilization = daily_estimated_cost / daily_budget_usd
        if utilization >= 1.0:
            return "over_budget"
        if utilization >= 0.8:
            return "watch"
        return "ready"

    def _controls(
        self,
        governance_status: str,
        provider_readiness: dict[str, Any],
        budget_summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        controls = [
            {
                "control_id": "default-local-mock",
                "owner": "platform",
                "status": "pass" if provider_readiness["local_mock_ready"] else "review",
                "control": (
                    "Keep PROVIDER_MODE=mock for portfolio demos and CI unless cloud-provider verification "
                    "is explicit."
                ),
            },
            {
                "control_id": "provider-env-gate",
                "owner": "platform",
                "status": "pass" if not provider_readiness["missing_required_env"] else "blocked",
                "control": "Require provider credentials before enabling OpenAI or Azure OpenAI mode.",
            },
            {
                "control_id": "cost-rate-config",
                "owner": "finance",
                "status": "pass" if provider_readiness["estimated_cost_rates_configured"] else "review",
                "control": "Set estimated input/output prices when running non-mock providers.",
            },
            {
                "control_id": "daily-budget-threshold",
                "owner": "sales-ops",
                "status": "pass" if governance_status == "ready" else "review",
                "control": (
                    "Review daily workflow volume when budget utilization reaches "
                    f"{budget_summary['budget_utilization']}."
                ),
            },
            {
                "control_id": "artifact-proof",
                "owner": "solution-engineering",
                "status": "pass",
                "control": (
                    "Regenerate cost_governance artifacts after changing provider mode, prices, "
                    "or workflow volume."
                ),
            },
        ]
        return controls

    def _pack_payload(self, trace_id: str, governance: CostGovernanceResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Cost Governance Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "governance": governance.model_dump(mode="json"),
            "executive_summary": {
                "status": governance.governance_status,
                "provider_mode": governance.provider_readiness["provider_mode"],
                "daily_estimated_cost": governance.budget_summary["daily_estimated_cost"],
                "monthly_estimated_cost_22_business_days": governance.budget_summary[
                    "monthly_estimated_cost_22_business_days"
                ],
                "budget_utilization": governance.budget_summary["budget_utilization"],
            },
            "reviewer_checklist": [
                "Confirm local demos keep PROVIDER_MODE=mock by default.",
                "Confirm any OpenAI or Azure OpenAI run has credentials and explicit estimated price settings.",
                "Compare /metrics/usage totals against this cost forecast after a demo or eval run.",
                "Inspect workflow estimates before scaling to many RFPs per day.",
                "Regenerate this pack under storage/cost_governance/ before a cloud-provider demo.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        governance = pack["governance"]
        budget = governance["budget_summary"]
        provider = governance["provider_readiness"]
        lines = [
            "# Cost Governance Pack",
            "",
            "## Executive Summary",
            "",
            f"- Status: {pack['executive_summary']['status']}",
            f"- Provider mode: {provider['provider_mode']}",
            f"- Active model: {provider['active_model']}",
            f"- Daily estimated cost: {budget['daily_estimated_cost']}",
            f"- Budget utilization: {budget['budget_utilization']}",
            f"- Monthly estimate: {budget['monthly_estimated_cost_22_business_days']}",
            "",
            "## Provider Readiness",
            "",
        ]
        for key, value in provider.items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Workflow Estimates", ""])
        lines.append("| Workflow | Requests | Input tokens | Output tokens | Cost | Latency ms |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for item in governance["workflow_estimates"]:
            lines.append(
                f"| {item['workflow_name']} | {item['request_count']} | {item['input_tokens']} | "
                f"{item['output_tokens']} | {item['estimated_cost']} | {item['estimated_latency_ms']} |"
            )
        lines.extend(["", "## Reviewer Controls", ""])
        for control in governance["reviewer_controls"]:
            lines.append(f"- {control['control_id']} ({control['status']}): {control['control']}")
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in governance["local_proof_commands"])
        lines.extend(["", "## Reviewer Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_checklist"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in governance["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Cost Governance Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _local_proof_commands(self) -> list[str]:
        return [
            "python -m app.demo",
            (
                'curl -X GET "http://127.0.0.1:8000/ops/cost-governance" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/ops/cost-governance-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "Get-Content storage\\usage_metrics.jsonl -ErrorAction SilentlyContinue | Select-Object -Last 5",
            "Get-ChildItem -Recurse -File storage\\cost_governance -ErrorAction SilentlyContinue",
        ]

    def _limitations(self) -> list[str]:
        return [
            "Cost estimates are deterministic forecasts, not provider invoices.",
            "Mock mode normally reports zero estimated cost unless local price settings are supplied.",
            "Provider readiness checks validate environment configuration presence, not live provider connectivity.",
            "Workflow volumes are operator assumptions and should be replaced with real production telemetry.",
        ]
