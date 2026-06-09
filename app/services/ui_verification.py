from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    DashboardSmokeCheck,
    DashboardSmokeEndpointReference,
    DashboardSmokeResponse,
    DashboardSmokeView,
    UIVerificationPackResponse,
)


class UIVerificationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def dashboard_smoke(self, trace_id: str) -> DashboardSmokeResponse:
        dashboard_path = Path("dashboard/app.py")
        routes_path = Path("app/api/routes.py")
        dashboard_source = self._read_text(dashboard_path)
        routes_source = self._read_text(routes_path)

        expected_views = [
            self._view(spec, dashboard_source)
            for spec in self._view_specs()
        ]
        endpoint_references = [
            self._endpoint(spec, dashboard_source, routes_source)
            for spec in self._endpoint_specs()
        ]
        generated_artifact_tabs = self._generated_artifact_tabs(expected_views)
        checks = self._checks(expected_views, endpoint_references, dashboard_path, routes_path)
        status = "pass" if all(check.status == "pass" for check in checks) else "fail"

        summary = {
            "view_count": len(expected_views),
            "views_present": sum(view.dashboard_source_present for view in expected_views),
            "endpoint_count": len(endpoint_references),
            "endpoints_referenced": sum(endpoint.dashboard_referenced for endpoint in endpoint_references),
            "routes_defined": sum(endpoint.route_defined for endpoint in endpoint_references),
            "generated_artifact_tab_count": len(generated_artifact_tabs),
            "failed_checks": [check.check_id for check in checks if check.status != "pass"],
            "dashboard_source": str(dashboard_path.resolve()),
            "routes_source": str(routes_path.resolve()),
            "storage_root": str(self.settings.storage_dir.resolve()),
        }
        return DashboardSmokeResponse(
            title="Dashboard Smoke + UI Verification",
            status=status,
            summary=summary,
            expected_views=expected_views,
            endpoint_references=endpoint_references,
            generated_artifact_tabs=generated_artifact_tabs,
            local_run_commands=self._local_run_commands(),
            limitations=self._limitations(),
            checks=checks,
            trace_id=trace_id,
        )

    def verification_pack(self, trace_id: str, write_artifact: bool = True) -> UIVerificationPackResponse:
        smoke = self.dashboard_smoke(f"{trace_id}-dashboard-smoke")
        pack = self._pack_payload(trace_id, smoke)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "ui_verification"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"ui_verification_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"ui_verification_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["ui_verification_markdown"] = artifact_path
            pack["artifact_paths"]["ui_verification_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return UIVerificationPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            dashboard_smoke=smoke,
            trace_id=trace_id,
        )

    def _view(self, spec: dict[str, Any], dashboard_source: str) -> DashboardSmokeView:
        present = spec["label"] in dashboard_source
        return DashboardSmokeView(
            label=spec["label"],
            status="pass" if present else "fail",
            dashboard_source_present=present,
            endpoint_paths=spec.get("endpoint_paths", []),
            generated_artifact_tab=spec.get("generated_artifact_tab", False),
            artifact_root=spec.get("artifact_root"),
        )

    def _endpoint(
        self,
        spec: dict[str, Any],
        dashboard_source: str,
        routes_source: str,
    ) -> DashboardSmokeEndpointReference:
        dashboard_referenced = spec["path"] in dashboard_source
        route_defined = f'"{spec["path"]}"' in routes_source
        status = "pass" if dashboard_referenced and route_defined else "fail"
        return DashboardSmokeEndpointReference(
            method=spec["method"],
            path=spec["path"],
            status=status,
            dashboard_referenced=dashboard_referenced,
            route_defined=route_defined,
            purpose=spec["purpose"],
            expected_artifacts=spec.get("expected_artifacts", []),
        )

    def _checks(
        self,
        expected_views: list[DashboardSmokeView],
        endpoint_references: list[DashboardSmokeEndpointReference],
        dashboard_path: Path,
        routes_path: Path,
    ) -> list[DashboardSmokeCheck]:
        checks: list[DashboardSmokeCheck] = []
        for view in expected_views:
            checks.append(
                DashboardSmokeCheck(
                    check_id=f"view-{self._slug(view.label)}",
                    category="dashboard_view",
                    label=view.label,
                    status=view.status,
                    expected="Dashboard tab label is present in dashboard/app.py.",
                    evidence="present" if view.dashboard_source_present else "missing",
                    source_path=str(dashboard_path.resolve()),
                    notes=view.endpoint_paths,
                )
            )
        for endpoint in endpoint_references:
            checks.append(
                DashboardSmokeCheck(
                    check_id=f"endpoint-{self._slug(endpoint.path)}",
                    category="endpoint_reference",
                    label=f"{endpoint.method} {endpoint.path}",
                    status=endpoint.status,
                    expected="Dashboard references the endpoint and FastAPI route defines it.",
                    evidence=(
                        f"dashboard_referenced={endpoint.dashboard_referenced}; "
                        f"route_defined={endpoint.route_defined}"
                    ),
                    source_path=str(routes_path.resolve()),
                    notes=endpoint.expected_artifacts,
                )
            )
        return checks

    def _generated_artifact_tabs(self, expected_views: list[DashboardSmokeView]) -> list[dict[str, Any]]:
        tabs: list[dict[str, Any]] = []
        for view in expected_views:
            if not view.generated_artifact_tab:
                continue
            root = view.artifact_root or ""
            path = self.settings.storage_dir / root if root else self.settings.storage_dir
            tabs.append(
                {
                    "label": view.label,
                    "artifact_root": f"storage/{root}" if root else "storage/",
                    "absolute_path": str(path.resolve()),
                    "dashboard_source_present": view.dashboard_source_present,
                    "endpoint_paths": view.endpoint_paths,
                }
            )
        return tabs

    def _pack_payload(self, trace_id: str, smoke: DashboardSmokeResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "UI Verification Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "dashboard_smoke": smoke.model_dump(mode="json"),
            "streamlit_run_command": "python -m streamlit run dashboard/app.py",
            "api_run_command": "python -m uvicorn app.main:app --reload",
            "reviewer_checklist": [
                "Run python scripts\\dashboard_smoke.py and confirm PASS.",
                "Start the API with python -m uvicorn app.main:app --reload.",
                "Start Streamlit with python -m streamlit run dashboard/app.py.",
                "Open the UI Verification tab and load dashboard smoke.",
                "Generate this UI Verification Pack and inspect storage/ui_verification/.",
                (
                    "Capture screenshots for the UI Verification, Reviewer Quickstart, Release Pack, "
                    "and Artifact Inventory tabs."
                ),
            ],
            "screenshot_placeholders": [
                {
                    "label": "UI Verification tab",
                    "expected": "Dashboard Smoke status, checked views, checked endpoints, commands, limitations.",
                },
                {
                    "label": "Reviewer Quickstart tab",
                    "expected": "Endpoint walkthrough order, proof tour, generated Walkthrough Pack path.",
                },
                {
                    "label": "API Contract tab",
                    "expected": "OpenAPI route counts, docs/dashboard/artifact checks, and Reviewer Collection path.",
                },
                {
                    "label": "Runtime Demo tab",
                    "expected": "Readiness status, FastAPI/Streamlit ports, run commands, and Runtime Demo Pack path.",
                },
                {
                    "label": "Release Pack tab",
                    "expected": "Release gate status, verification commands, generated Publish Pack path.",
                },
                {
                    "label": "Artifact Inventory tab",
                    "expected": "Ignored storage directories and latest generated artifact files.",
                },
            ],
            "troubleshooting": [
                {
                    "symptom": "Dashboard Smoke fails a view check.",
                    "fix": (
                        "Confirm the expected tab label is still present in dashboard/app.py "
                        "or update the smoke spec."
                    ),
                },
                {
                    "symptom": "Dashboard Smoke fails an endpoint check.",
                    "fix": "Confirm dashboard/app.py references the endpoint and app/api/routes.py defines the route.",
                },
                {
                    "symptom": "UI Verification Pack is missing from storage.",
                    "fix": "Run POST /ui/verification-pack with write_artifact=true or python -m app.demo.",
                },
                {
                    "symptom": "Streamlit cannot connect to the API.",
                    "fix": "Start python -m uvicorn app.main:app --reload and confirm RFP_API_URL points at http://127.0.0.1:8000.",
                },
            ],
            "limitations": smoke.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        smoke = pack["dashboard_smoke"]
        summary = smoke["summary"]
        lines = [
            "# UI Verification Pack",
            "",
            "## Dashboard Smoke",
            "",
            f"- Status: {smoke['status']}",
            f"- Views present: {summary['views_present']}/{summary['view_count']}",
            f"- Endpoints referenced: {summary['endpoints_referenced']}/{summary['endpoint_count']}",
            f"- Routes defined: {summary['routes_defined']}/{summary['endpoint_count']}",
            f"- Generated artifact tabs: {summary['generated_artifact_tab_count']}",
            "",
            "## Streamlit Run Command",
            "",
            f"```bash\n{pack['streamlit_run_command']}\n```",
            "",
            "## API Run Command",
            "",
            f"```bash\n{pack['api_run_command']}\n```",
            "",
            "## Checked Views",
            "",
            "| View | Status | Endpoints | Artifact Root |",
            "| --- | --- | --- | --- |",
        ]
        for view in smoke["expected_views"]:
            endpoints = ", ".join(view["endpoint_paths"]) or "None"
            artifact = view["artifact_root"] or "None"
            lines.append(f"| {view['label']} | {view['status']} | {endpoints} | {artifact} |")
        lines.extend(["", "## Checked Endpoints", ""])
        lines.append("| Method | Path | Status | Dashboard | Route | Purpose |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for endpoint in smoke["endpoint_references"]:
            lines.append(
                f"| {endpoint['method']} | {endpoint['path']} | {endpoint['status']} | "
                f"{endpoint['dashboard_referenced']} | {endpoint['route_defined']} | {endpoint['purpose']} |"
            )
        lines.extend(["", "## Reviewer Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_checklist"])
        lines.extend(["", "## Screenshot Placeholders", ""])
        lines.extend(f"- [ ] {item['label']}: {item['expected']}" for item in pack["screenshot_placeholders"])
        lines.extend(["", "## Troubleshooting", ""])
        lines.extend(f"- {item['symptom']}: {item['fix']}" for item in pack["troubleshooting"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## UI Verification Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _slug(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    def _view_specs(self) -> list[dict[str, Any]]:
        return [
            {"label": "Ingest Documents", "endpoint_paths": ["/documents/ingest", "/documents"]},
            {"label": "Analyze RFP", "endpoint_paths": ["/rfp/analyze"]},
            {"label": "Ask Questions", "endpoint_paths": ["/rfp/query"]},
            {"label": "Draft Response", "endpoint_paths": ["/rfp/draft-response"]},
            {
                "label": "Requirement Matrix / Export",
                "endpoint_paths": ["/rfp/requirement-matrix", "/rfp/export-package"],
            },
            {
                "label": "Customer Fit / Response Memory",
                "endpoint_paths": ["/rfp/customer-fit", "/rfp/response-memory/search"],
            },
            {"label": "Action Plan / Handoff Board", "endpoint_paths": ["/rfp/action-plan", "/rfp/handoff-board"]},
            {"label": "Review Board / Red Team", "endpoint_paths": ["/rfp/review-answer", "/rfp/review-package"]},
            {
                "label": "Reviewer Collaboration",
                "endpoint_paths": ["/rfp/reviewer-collaboration", "/rfp/reviewer-collaboration-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "review_boards",
            },
            {
                "label": "Submission Exceptions",
                "endpoint_paths": ["/rfp/exception-register", "/rfp/exception-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "exception_registers",
            },
            {"label": "Evaluation and Metrics", "endpoint_paths": ["/rfp/evaluate", "/metrics/usage"]},
            {"label": "Audit Events", "endpoint_paths": ["/audit/events"]},
            {
                "label": "Deal Readiness / Executive Report",
                "endpoint_paths": ["/rfp/readiness-scorecard", "/rfp/executive-risk-report"],
            },
            {
                "label": "Win Strategy / Pricing Memo",
                "endpoint_paths": ["/rfp/win-strategy", "/rfp/pricing-risk-memo"],
            },
            {
                "label": "Contract Risk / Negotiation Brief",
                "endpoint_paths": ["/rfp/contract-risk", "/rfp/negotiation-brief"],
            },
            {
                "label": "Evidence Gaps / Source Requests",
                "endpoint_paths": ["/rfp/evidence-gaps", "/rfp/source-request-pack"],
            },
            {
                "label": "Timeline / Submission Calendar",
                "endpoint_paths": ["/rfp/timeline-plan", "/rfp/submission-calendar-pack"],
            },
            {
                "label": "Submission Decision",
                "endpoint_paths": ["/rfp/submission-decision", "/rfp/executive-submission-memo"],
            },
            {
                "label": "Leadership Brief",
                "endpoint_paths": ["/rfp/leadership-brief"],
                "generated_artifact_tab": True,
                "artifact_root": "leadership_briefs",
            },
            {
                "label": "Regression / Demo Script",
                "endpoint_paths": ["/rfp/submission-regression", "/rfp/demo-script"],
                "generated_artifact_tab": True,
                "artifact_root": "demo_scripts",
            },
            {
                "label": "Launch Checklist",
                "endpoint_paths": ["/ops/smoke-matrix", "/ops/launch-checklist"],
                "generated_artifact_tab": True,
                "artifact_root": "launch_checklists",
            },
            {
                "label": "Portfolio Pack",
                "endpoint_paths": ["/portfolio/evidence-index", "/portfolio/interview-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "portfolio_packs",
            },
            {
                "label": "Release Pack",
                "endpoint_paths": ["/release/quality-gate", "/release/publish-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "release_packs",
            },
            {
                "label": "CI Doctor / Audit Pack",
                "endpoint_paths": ["/ops/ci-doctor", "/ops/audit-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "audit_packs",
            },
            {
                "label": "Reviewer Quickstart",
                "endpoint_paths": ["/reviewer/quickstart", "/reviewer/walkthrough-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "reviewer_packs",
            },
            {
                "label": "API Contract",
                "endpoint_paths": ["/api/contract-audit", "/api/reviewer-collection"],
                "generated_artifact_tab": True,
                "artifact_root": "api_contracts",
            },
            {
                "label": "Artifact Inventory",
                "endpoint_paths": ["/artifacts/inventory", "/artifacts/readme-checklist"],
                "generated_artifact_tab": True,
                "artifact_root": "artifact_indexes",
            },
            {
                "label": "UI Verification",
                "endpoint_paths": ["/ui/dashboard-smoke", "/ui/verification-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "ui_verification",
            },
            {
                "label": "Final Handoff",
                "endpoint_paths": ["/handoff/final-audit", "/handoff/final-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "final_handoff",
            },
            {
                "label": "Git Readiness",
                "endpoint_paths": ["/git/readiness", "/git/push-plan"],
                "generated_artifact_tab": True,
                "artifact_root": "git_packs",
            },
            {
                "label": "Runtime Demo",
                "endpoint_paths": ["/runtime/demo-readiness", "/runtime/demo-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "runtime_packs",
            },
            {
                "label": "RAG Corpus",
                "endpoint_paths": ["/rag/corpus-coverage", "/rag/eval-coverage-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "rag_coverage",
            },
            {
                "label": "Compliance Evidence",
                "endpoint_paths": ["/compliance/evidence-matrix", "/compliance/control-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "compliance_packs",
            },
            {
                "label": "Privacy Retention",
                "endpoint_paths": ["/privacy/retention-guardrails", "/privacy/retention-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "privacy_packs",
            },
            {
                "label": "Procurement Q&A",
                "endpoint_paths": ["/procurement/question-risk", "/procurement/approval-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "procurement_packs",
            },
            {
                "label": "Bid/No-Bid ROI",
                "endpoint_paths": ["/bid/scenario-analysis", "/bid/roi-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "bid_packs",
            },
            {
                "label": "Objection Handling Pack",
                "endpoint_paths": ["/rfp/objection-handling", "/rfp/objection-handling-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "objection_packs",
            },
            {
                "label": "Win/Loss Learning",
                "endpoint_paths": ["/learning/win-loss", "/learning/win-loss-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "win_loss_packs",
            },
            {
                "label": "Evidence Freshness",
                "endpoint_paths": ["/evidence/freshness", "/evidence/freshness-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "freshness_packs",
            },
            {
                "label": "Evidence Conflicts",
                "endpoint_paths": ["/evidence/conflicts", "/evidence/conflict-pack"],
                "generated_artifact_tab": True,
                "artifact_root": "conflict_packs",
            },
        ]

    def _endpoint_specs(self) -> list[dict[str, Any]]:
        return [
            {"method": "GET", "path": "/health", "purpose": "Sidebar API availability check."},
            {"method": "POST", "path": "/auth/demo-token", "purpose": "Sidebar local key loader."},
            {
                "method": "GET",
                "path": "/ui/dashboard-smoke",
                "purpose": "Structured source-level dashboard smoke checks.",
            },
            {
                "method": "POST",
                "path": "/ui/verification-pack",
                "purpose": "Writes Markdown/JSON UI verification pack.",
                "expected_artifacts": ["storage/ui_verification/*.md", "storage/ui_verification/*.json"],
            },
            {"method": "GET", "path": "/reviewer/quickstart", "purpose": "Reviewer workflow tab."},
            {"method": "POST", "path": "/reviewer/walkthrough-pack", "purpose": "Reviewer generated Walkthrough Pack."},
            {
                "method": "POST",
                "path": "/rfp/reviewer-collaboration",
                "purpose": "Reviewer Collaboration tab board view.",
            },
            {
                "method": "POST",
                "path": "/rfp/reviewer-collaboration-pack",
                "purpose": "Reviewer Collaboration generated pack.",
                "expected_artifacts": ["storage/review_boards/*.md", "storage/review_boards/*.json"],
            },
            {
                "method": "POST",
                "path": "/rfp/exception-register",
                "purpose": "Submission Exceptions tab register view.",
            },
            {
                "method": "POST",
                "path": "/rfp/exception-pack",
                "purpose": "Submission Exceptions generated register pack.",
                "expected_artifacts": ["storage/exception_registers/*.md", "storage/exception_registers/*.json"],
            },
            {"method": "GET", "path": "/api/contract-audit", "purpose": "API Contract tab audit snapshot."},
            {
                "method": "POST",
                "path": "/api/reviewer-collection",
                "purpose": "API Contract generated reviewer collection.",
                "expected_artifacts": ["storage/api_contracts/*.md", "storage/api_contracts/*.json"],
            },
            {"method": "GET", "path": "/release/quality-gate", "purpose": "Release Pack tab gate."},
            {"method": "POST", "path": "/release/publish-pack", "purpose": "Release Pack generated artifact."},
            {"method": "GET", "path": "/artifacts/inventory", "purpose": "Artifact Inventory tab."},
            {
                "method": "POST",
                "path": "/artifacts/readme-checklist",
                "purpose": "Artifact Inventory generated README checklist.",
            },
            {"method": "GET", "path": "/ops/smoke-matrix", "purpose": "Launch Checklist smoke matrix."},
            {"method": "POST", "path": "/ops/launch-checklist", "purpose": "Launch Checklist generated artifact."},
            {"method": "GET", "path": "/handoff/final-audit", "purpose": "Final Handoff tab audit."},
            {
                "method": "POST",
                "path": "/handoff/final-pack",
                "purpose": "Final Handoff generated artifact.",
                "expected_artifacts": ["storage/final_handoff/*.md", "storage/final_handoff/*.json"],
            },
            {"method": "GET", "path": "/git/readiness", "purpose": "Git Readiness tab local branch hygiene checks."},
            {
                "method": "POST",
                "path": "/git/push-plan",
                "purpose": "Git Readiness generated Branch Hygiene Pack.",
                "expected_artifacts": ["storage/git_packs/*.md", "storage/git_packs/*.json"],
            },
            {
                "method": "GET",
                "path": "/runtime/demo-readiness",
                "purpose": "Runtime Demo tab local FastAPI/Streamlit readiness.",
            },
            {
                "method": "POST",
                "path": "/runtime/demo-pack",
                "purpose": "Runtime Demo generated server pack.",
                "expected_artifacts": ["storage/runtime_packs/*.md", "storage/runtime_packs/*.json"],
            },
            {"method": "GET", "path": "/rag/corpus-coverage", "purpose": "RAG Corpus tab coverage view."},
            {
                "method": "POST",
                "path": "/rag/eval-coverage-pack",
                "purpose": "RAG Corpus generated eval coverage pack.",
                "expected_artifacts": ["storage/rag_coverage/*.md", "storage/rag_coverage/*.json"],
            },
            {
                "method": "GET",
                "path": "/compliance/evidence-matrix",
                "purpose": "Compliance Evidence tab matrix view.",
            },
            {
                "method": "POST",
                "path": "/compliance/control-pack",
                "purpose": "Compliance Evidence generated control mapping pack.",
                "expected_artifacts": ["storage/compliance_packs/*.md", "storage/compliance_packs/*.json"],
            },
            {
                "method": "GET",
                "path": "/privacy/retention-guardrails",
                "purpose": "Privacy Retention tab guardrail matrix.",
            },
            {
                "method": "POST",
                "path": "/privacy/retention-pack",
                "purpose": "Privacy Retention generated guardrail pack.",
                "expected_artifacts": ["storage/privacy_packs/*.md", "storage/privacy_packs/*.json"],
            },
            {
                "method": "GET",
                "path": "/procurement/question-risk",
                "purpose": "Procurement Q&A tab risk simulator view.",
            },
            {
                "method": "POST",
                "path": "/procurement/approval-pack",
                "purpose": "Procurement Q&A generated approval workflow pack.",
                "expected_artifacts": ["storage/procurement_packs/*.md", "storage/procurement_packs/*.json"],
            },
            {
                "method": "GET",
                "path": "/bid/scenario-analysis",
                "purpose": "Bid/No-Bid ROI tab scenario simulator view.",
            },
            {
                "method": "POST",
                "path": "/bid/roi-pack",
                "purpose": "Bid/No-Bid ROI generated impact pack.",
                "expected_artifacts": ["storage/bid_packs/*.md", "storage/bid_packs/*.json"],
            },
            {
                "method": "POST",
                "path": "/rfp/objection-handling",
                "purpose": "Objection Handling tab cited response catalog.",
            },
            {
                "method": "POST",
                "path": "/rfp/objection-handling-pack",
                "purpose": "Objection Handling generated reviewer pack.",
                "expected_artifacts": ["storage/objection_packs/*.md", "storage/objection_packs/*.json"],
            },
            {
                "method": "POST",
                "path": "/learning/win-loss",
                "purpose": "Win/Loss Learning tab outcome ingestion and recommendation analysis.",
            },
            {
                "method": "POST",
                "path": "/learning/win-loss-pack",
                "purpose": "Win/Loss Learning generated strategy pack.",
                "expected_artifacts": ["storage/win_loss_packs/*.md", "storage/win_loss_packs/*.json"],
            },
            {
                "method": "GET",
                "path": "/evidence/freshness",
                "purpose": "Evidence Freshness tab source age, renewal, owner, endpoint, and claim-risk view.",
            },
            {
                "method": "POST",
                "path": "/evidence/freshness-pack",
                "purpose": "Evidence Freshness generated expiry risk pack.",
                "expected_artifacts": ["storage/freshness_packs/*.md", "storage/freshness_packs/*.json"],
            },
            {
                "method": "GET",
                "path": "/evidence/conflicts",
                "purpose": "Evidence Conflicts tab source-precedence and ambiguity resolver view.",
            },
            {
                "method": "POST",
                "path": "/evidence/conflict-pack",
                "purpose": "Evidence Conflicts generated resolver pack.",
                "expected_artifacts": ["storage/conflict_packs/*.md", "storage/conflict_packs/*.json"],
            },
        ]

    def _local_run_commands(self) -> list[str]:
        return [
            "python scripts\\dashboard_smoke.py",
            "python -m uvicorn app.main:app --reload",
            "python -m streamlit run dashboard/app.py",
            (
                'curl -X GET "http://127.0.0.1:8000/ui/dashboard-smoke" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/ui/verification-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.demo",
            (
                'curl -X GET "http://127.0.0.1:8000/git/readiness" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/git/push-plan" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X GET "http://127.0.0.1:8000/api/contract-audit" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/api/reviewer-collection" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python scripts\\runtime_check.py",
            (
                'curl -X GET "http://127.0.0.1:8000/runtime/demo-readiness" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/runtime/demo-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X GET "http://127.0.0.1:8000/rag/corpus-coverage" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rag/eval-coverage-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X GET "http://127.0.0.1:8000/compliance/evidence-matrix" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/compliance/control-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X GET "http://127.0.0.1:8000/procurement/question-risk" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/procurement/approval-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X GET "http://127.0.0.1:8000/bid/scenario-analysis" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/bid/roi-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/learning/win-loss-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X GET "http://127.0.0.1:8000/evidence/freshness" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/evidence/freshness-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X GET "http://127.0.0.1:8000/evidence/conflicts" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/evidence/conflict-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            (
                "Dashboard Smoke verifies source wiring and expected labels; it does not launch "
                "Streamlit or take screenshots."
            ),
            "Endpoint checks confirm route strings and dashboard references, not live HTTP behavior.",
            "Screenshot placeholders remain manual so GitHub reviewers can capture their local run.",
            "Generated storage/ui_verification artifacts are ignored by git and should be regenerated locally.",
            (
                "The default path is local/mock and does not validate optional OpenAI, Azure OpenAI, "
                "Azure AI Search, or live Qdrant adapters."
            ),
        ]
