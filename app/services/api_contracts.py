from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ApiContractAuditResponse,
    ApiContractCheck,
    ApiContractEndpoint,
    ArtifactInventoryResponse,
    DashboardSmokeResponse,
    ReviewerCollectionResponse,
    SmokeMatrixResponse,
)


class ApiContractService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def audit(
        self,
        trace_id: str,
        openapi_schema: dict[str, Any],
        smoke_matrix: SmokeMatrixResponse,
        dashboard_smoke: DashboardSmokeResponse,
        artifact_inventory: ArtifactInventoryResponse,
    ) -> ApiContractAuditResponse:
        endpoints = self._endpoints(openapi_schema, smoke_matrix)
        endpoint_inventory = self._group_by_domain(endpoints)
        important_paths = self._important_paths(endpoints)
        docs_check = self._docs_check(important_paths)
        dashboard_check = self._dashboard_check(dashboard_smoke, ["/api/contract-audit", "/api/reviewer-collection"])
        artifact_check = self._artifact_check(smoke_matrix, artifact_inventory)
        demo_check = self._demo_check()
        rag_check = self._rag_eval_red_team_check(endpoints)
        deprecated_warnings = self._deprecated_duplicate_warnings(openapi_schema)
        missing_docs_warnings = self._missing_docs_warnings(docs_check)
        failed_checks = [
            check
            for check in [docs_check, dashboard_check, artifact_check, demo_check, rag_check]
            if check.status != "pass"
        ]
        warning_count = len(missing_docs_warnings) + len(deprecated_warnings)
        score = max(0, 100 - 12 * len(failed_checks) - min(20, warning_count * 2))
        status = "pass" if not failed_checks and not deprecated_warnings else "needs_review"
        auth_count = sum(endpoint.auth_required for endpoint in endpoints)
        return ApiContractAuditResponse(
            title="API Contract Snapshot",
            status=status,
            score=score,
            openapi_route_count=len(endpoints),
            openapi_path_count=len(openapi_schema.get("paths", {})),
            auth_protected_endpoint_count=auth_count,
            public_endpoint_count=len(endpoints) - auth_count,
            important_endpoint_count=len(important_paths),
            endpoint_inventory=endpoint_inventory,
            docs_api_coverage=docs_check,
            dashboard_smoke_alignment=dashboard_check,
            generated_artifact_endpoint_coverage=artifact_check,
            demo_flow_endpoint_coverage=demo_check,
            rag_eval_red_team_endpoint_coverage=rag_check,
            missing_docs_warnings=missing_docs_warnings,
            deprecated_duplicate_route_warnings=deprecated_warnings,
            local_only_limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def reviewer_collection(
        self,
        trace_id: str,
        audit: ApiContractAuditResponse,
        write_artifact: bool = True,
    ) -> ReviewerCollectionResponse:
        collection = self._collection_payload(trace_id, audit)
        markdown = self._render_markdown(collection)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            collection_dir = self.settings.storage_dir / "api_contracts"
            collection_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = collection_dir / f"reviewer_collection_{safe_trace_id}.md"
            json_path = collection_dir / f"reviewer_collection_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            collection["artifact_paths"]["reviewer_collection_markdown"] = artifact_path
            collection["artifact_paths"]["reviewer_collection_json"] = json_artifact_path
            markdown = self._render_markdown(collection)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(collection, indent=2), encoding="utf-8")

        return ReviewerCollectionResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            collection=collection,
            contract_audit=audit,
            trace_id=trace_id,
        )

    def _endpoints(
        self,
        openapi_schema: dict[str, Any],
        smoke_matrix: SmokeMatrixResponse,
    ) -> list[ApiContractEndpoint]:
        smoke_by_key = {(row.method.upper(), row.path): row for row in smoke_matrix.rows}
        docs_api = self._read("docs/api.md")
        readme = self._read("README.md")
        dashboard = self._read("dashboard/app.py")
        endpoints: list[ApiContractEndpoint] = []
        for path, methods in sorted(openapi_schema.get("paths", {}).items()):
            for method, spec in sorted(methods.items()):
                upper_method = method.upper()
                smoke_row = smoke_by_key.get((upper_method, path))
                auth_required = bool(spec.get("security"))
                body = self._sample_body(path, smoke_row.sample_command if smoke_row else "")
                endpoint = ApiContractEndpoint(
                    method=upper_method,
                    path=path,
                    domain=self._domain(path),
                    operation_id=spec.get("operationId"),
                    summary=spec.get("summary") or (smoke_row.endpoint_name if smoke_row else self._title(path)),
                    expected_status=smoke_row.expected_status if smoke_row else 200,
                    auth_required=auth_required,
                    auth_notes="Requires X-API-Key." if auth_required else "No API key required.",
                    docs_api_covered=path in docs_api,
                    readme_covered=path in readme,
                    dashboard_referenced=path in dashboard,
                    smoke_matrix_covered=smoke_row is not None,
                    generates_artifact=bool(smoke_row and smoke_row.required_artifact_expectations),
                    artifact_expectations=smoke_row.required_artifact_expectations if smoke_row else [],
                    sample_curl=(
                        smoke_row.sample_command
                        if smoke_row
                        else self._curl(upper_method, path, body, auth_required)
                    ),
                    sample_powershell=self._powershell(upper_method, path, body, auth_required),
                )
                endpoints.append(endpoint)
        return endpoints

    def _group_by_domain(self, endpoints: list[ApiContractEndpoint]) -> dict[str, list[ApiContractEndpoint]]:
        grouped: dict[str, list[ApiContractEndpoint]] = {}
        for endpoint in endpoints:
            grouped.setdefault(endpoint.domain, []).append(endpoint)
        return dict(sorted(grouped.items()))

    def _important_paths(self, endpoints: list[ApiContractEndpoint]) -> list[str]:
        required = {
            "/api/contract-audit",
            "/api/reviewer-collection",
            "/auth/demo-token",
            "/health",
            "/documents/ingest",
            "/rfp/query",
            "/rfp/evaluate",
            "/rag/corpus-coverage",
            "/rag/eval-coverage-pack",
            "/rfp/submission-regression",
            "/rfp/demo-script",
            "/compliance/evidence-matrix",
            "/compliance/control-pack",
            "/procurement/question-risk",
            "/procurement/approval-pack",
            "/rfp/reviewer-collaboration",
            "/rfp/reviewer-collaboration-pack",
            "/bid/scenario-analysis",
            "/bid/roi-pack",
            "/rfp/objection-handling",
            "/rfp/objection-handling-pack",
            "/learning/win-loss",
            "/learning/win-loss-pack",
            "/ops/smoke-matrix",
            "/ops/launch-checklist",
            "/ui/dashboard-smoke",
            "/artifacts/inventory",
            "/reviewer/quickstart",
            "/reviewer/walkthrough-pack",
        }
        required.update(endpoint.path for endpoint in endpoints if endpoint.generates_artifact)
        return sorted(required & {endpoint.path for endpoint in endpoints})

    def _docs_check(self, important_paths: list[str]) -> ApiContractCheck:
        docs_api = self._read("docs/api.md")
        missing = [path for path in important_paths if path not in docs_api]
        return ApiContractCheck(
            name="docs/api important endpoint coverage",
            status="pass" if not missing else "warn",
            passed=len(important_paths) - len(missing),
            total=len(important_paths),
            missing_paths=missing,
            details={"source": str(Path("docs/api.md").resolve())},
        )

    def _dashboard_check(
        self,
        dashboard_smoke: DashboardSmokeResponse,
        required_paths: list[str],
    ) -> ApiContractCheck:
        endpoint_paths = {endpoint.path: endpoint for endpoint in dashboard_smoke.endpoint_references}
        missing = [
            path
            for path in required_paths
            if path not in endpoint_paths or endpoint_paths[path].status != "pass"
        ]
        warnings = [] if dashboard_smoke.status == "pass" else ["Dashboard Smoke is not passing."]
        return ApiContractCheck(
            name="dashboard smoke alignment",
            status="pass" if not missing and not warnings else "warn",
            passed=len(required_paths) - len(missing),
            total=len(required_paths),
            missing_paths=missing,
            warnings=warnings,
            details={
                "dashboard_smoke_status": dashboard_smoke.status,
                "dashboard_smoke_endpoint_count": dashboard_smoke.summary["endpoint_count"],
            },
        )

    def _artifact_check(
        self,
        smoke_matrix: SmokeMatrixResponse,
        artifact_inventory: ArtifactInventoryResponse,
    ) -> ApiContractCheck:
        artifact_rows = [row for row in smoke_matrix.rows if row.required_artifact_expectations]
        inventory_dirs = {Path(item.directory).name for item in artifact_inventory.directories}
        missing = []
        for row in artifact_rows:
            expected_dirs = {
                expectation.split("/", 2)[1].split("\\", 1)[0]
                for expectation in row.required_artifact_expectations
                if expectation.startswith("storage/")
            }
            if expected_dirs and not expected_dirs <= inventory_dirs:
                missing.append(row.path)
        return ApiContractCheck(
            name="generated artifact endpoint coverage",
            status="pass" if not missing else "warn",
            passed=len(artifact_rows) - len(missing),
            total=len(artifact_rows),
            missing_paths=missing,
            details={
                "artifact_inventory_directories": artifact_inventory.total_directories,
                "artifact_endpoint_count": len(artifact_rows),
            },
        )

    def _demo_check(self) -> ApiContractCheck:
        demo = self._read("app/demo.py")
        required = {
            "/api/contract-audit": "contract_audit",
            "/api/reviewer-collection": "reviewer_collection",
            "storage/api_contracts": "api_contracts",
            "/compliance/control-pack": "compliance_control_pack",
            "storage/compliance_packs": "compliance_packs",
            "/procurement/approval-pack": "procurement_approval_pack",
            "storage/procurement_packs": "procurement_packs",
            "/rfp/reviewer-collaboration-pack": "reviewer_collaboration_pack",
            "storage/review_boards": "review_boards",
            "/bid/roi-pack": "bid_roi_pack",
            "storage/bid_packs": "bid_packs",
            "/rfp/objection-handling-pack": "objection_pack",
            "storage/objection_packs": "objection_packs",
            "/learning/win-loss-pack": "win_loss_pack",
            "storage/win_loss_packs": "win_loss_packs",
        }
        missing = [path for path, token in required.items() if token not in demo]
        return ApiContractCheck(
            name="demo flow endpoint coverage",
            status="pass" if not missing else "warn",
            passed=len(required) - len(missing),
            total=len(required),
            missing_paths=missing,
            details={"source": str(Path("app/demo.py").resolve())},
        )

    def _rag_eval_red_team_check(self, endpoints: list[ApiContractEndpoint]) -> ApiContractCheck:
        available = {endpoint.path for endpoint in endpoints}
        required = {
            "/documents/ingest",
            "/rfp/query",
            "/rfp/review-answer",
            "/rfp/evaluate",
            "/rag/corpus-coverage",
            "/rag/eval-coverage-pack",
            "/rfp/submission-regression",
            "/rfp/demo-script",
        }
        missing = sorted(required - available)
        warnings = []
        if not Path("app/evals/run_red_team.py").exists():
            warnings.append("Red-team CLI runner is missing.")
        if not Path("sample_data/red_team_questions.json").exists():
            warnings.append("Red-team dataset is missing.")
        return ApiContractCheck(
            name="RAG/eval/red-team endpoint coverage",
            status="pass" if not missing and not warnings else "warn",
            passed=len(required) - len(missing),
            total=len(required),
            missing_paths=missing,
            warnings=warnings,
            details={
                "red_team_api_note": (
                    "Red-team verification is exposed through POST /rfp/submission-regression "
                    "and the app.evals.run_red_team CLI, not a standalone red-team HTTP route."
                ),
                "verification_order": self._rag_verification_order(),
            },
        )

    def _deprecated_duplicate_warnings(self, openapi_schema: dict[str, Any]) -> list[str]:
        warnings: list[str] = []
        seen_operation_ids: dict[str, str] = {}
        seen_paths: set[tuple[str, str]] = set()
        for path, methods in openapi_schema.get("paths", {}).items():
            for method, spec in methods.items():
                key = (method.upper(), path)
                if key in seen_paths:
                    warnings.append(f"Duplicate route detected: {method.upper()} {path}")
                seen_paths.add(key)
                if spec.get("deprecated"):
                    warnings.append(f"Deprecated OpenAPI route: {method.upper()} {path}")
                operation_id = spec.get("operationId")
                if operation_id:
                    prior = seen_operation_ids.get(operation_id)
                    current = f"{method.upper()} {path}"
                    if prior:
                        warnings.append(f"Duplicate operationId {operation_id}: {prior} and {current}")
                    seen_operation_ids[operation_id] = current
        return warnings

    def _missing_docs_warnings(self, docs_check: ApiContractCheck) -> list[str]:
        if not docs_check.missing_paths:
            return []
        return [f"docs/api.md is missing important endpoint mention: {path}" for path in docs_check.missing_paths]

    def _collection_payload(self, trace_id: str, audit: ApiContractAuditResponse) -> dict[str, Any]:
        endpoint_inventory = {
            domain: [endpoint.model_dump(mode="json") for endpoint in endpoints]
            for domain, endpoints in audit.endpoint_inventory.items()
        }
        return {
            "trace_id": trace_id,
            "title": "Reviewer Collection Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "contract_audit_summary": {
                "status": audit.status,
                "score": audit.score,
                "openapi_route_count": audit.openapi_route_count,
                "auth_protected_endpoint_count": audit.auth_protected_endpoint_count,
                "important_endpoint_count": audit.important_endpoint_count,
                "storage_root": str((self.settings.storage_dir / "api_contracts").resolve()),
            },
            "demo_token_flow": self._demo_token_flow(),
            "endpoint_inventory_by_domain": endpoint_inventory,
            "generated_artifact_endpoints": self._artifact_endpoints(endpoint_inventory),
            "rag_eval_red_team_verification_order": self._rag_verification_order(),
            "reviewer_explanation": self._reviewer_explanation(),
            "auth_notes": [
                "Use POST /auth/demo-token to retrieve the local demo API key.",
                "Protected endpoints require the X-API-Key header.",
                "Default local key is local-demo-key unless API_KEY is overridden.",
            ],
            "expected_status_codes": {
                "public_health_and_token": 200,
                "protected_success": 200,
                "missing_or_invalid_api_key": 401,
                "bad_payload_or_missing_fixture": "400 or 404 depending on endpoint validation.",
            },
            "local_limitations": audit.local_only_limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, collection: dict[str, Any]) -> str:
        summary = collection["contract_audit_summary"]
        lines = [
            "# Reviewer Collection Pack",
            "",
            "## API Contract Snapshot",
            "",
            f"- Status: {summary['status']}",
            f"- Score: {summary['score']}",
            f"- OpenAPI routes: {summary['openapi_route_count']}",
            f"- Auth-protected routes: {summary['auth_protected_endpoint_count']}",
            f"- Important endpoints: {summary['important_endpoint_count']}",
            f"- Storage root: {summary['storage_root']}",
            "",
            "## Demo Token Flow",
            "",
        ]
        for command in collection["demo_token_flow"]:
            lines.append(f"```powershell\n{command}\n```" if command.startswith("$") else f"```bash\n{command}\n```")
        lines.extend(["", "## Endpoint Inventory Grouped By Domain", ""])
        for domain, endpoints in collection["endpoint_inventory_by_domain"].items():
            lines.extend([f"### {domain.title()}", ""])
            lines.append("| Method | Path | Expected | Auth | Artifacts |")
            lines.append("| --- | --- | ---: | --- | --- |")
            for endpoint in endpoints:
                artifacts = ", ".join(endpoint["artifact_expectations"]) or "None"
                auth = "X-API-Key" if endpoint["auth_required"] else "public"
                lines.append(
                    f"| {endpoint['method']} | {endpoint['path']} | "
                    f"{endpoint['expected_status']} | {auth} | {artifacts} |"
                )
            lines.append("")
        lines.extend(["## Sample Commands", ""])
        for endpoint in self._sample_collection_endpoints(collection):
            lines.extend(
                [
                    f"### {endpoint['method']} {endpoint['path']}",
                    "",
                    "```bash",
                    endpoint["sample_curl"],
                    "```",
                    "```powershell",
                    endpoint["sample_powershell"],
                    "```",
                ]
            )
        lines.extend(["", "## Generated Artifact Endpoints", ""])
        for endpoint in collection["generated_artifact_endpoints"]:
            artifacts = ", ".join(endpoint["artifact_expectations"])
            lines.append(f"- {endpoint['method']} {endpoint['path']}: {artifacts}")
        lines.extend(["", "## RAG/Eval/Red-Team Verification Order", ""])
        lines.extend(
            f"{index}. {item}"
            for index, item in enumerate(collection["rag_eval_red_team_verification_order"], start=1)
        )
        lines.extend(["", "## Recruiter and Engineer Explanation", ""])
        lines.append(f"- Recruiter: {collection['reviewer_explanation']['recruiter']}")
        lines.append(f"- Engineer: {collection['reviewer_explanation']['engineer']}")
        lines.extend(["", "## Auth Notes", ""])
        lines.extend(f"- {item}" for item in collection["auth_notes"])
        lines.extend(["", "## Local-Only Limitations", ""])
        lines.extend(f"- {item}" for item in collection["local_limitations"])
        if collection["artifact_paths"]:
            lines.extend(["", "## Reviewer Collection Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in collection["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _artifact_endpoints(self, grouped: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        endpoints = [
            endpoint
            for rows in grouped.values()
            for endpoint in rows
            if endpoint["generates_artifact"]
        ]
        return sorted(endpoints, key=lambda item: item["path"])

    def _sample_collection_endpoints(self, collection: dict[str, Any]) -> list[dict[str, Any]]:
        priority = {
            "/auth/demo-token",
            "/api/contract-audit",
            "/api/reviewer-collection",
            "/documents/ingest",
            "/rfp/query",
            "/rfp/evaluate",
            "/rfp/submission-regression",
        }
        endpoints = [
            endpoint
            for rows in collection["endpoint_inventory_by_domain"].values()
            for endpoint in rows
            if endpoint["path"] in priority
        ]
        return sorted(endpoints, key=lambda item: (item["path"] not in priority, item["path"]))

    def _demo_token_flow(self) -> list[str]:
        return [
            'curl -X POST "http://127.0.0.1:8000/auth/demo-token"',
            '$token = (Invoke-RestMethod -Method POST -Uri "http://127.0.0.1:8000/auth/demo-token").api_key',
            '$headers = @{"X-API-Key" = $token}',
            'curl -X GET "http://127.0.0.1:8000/api/contract-audit" -H "X-API-Key: local-demo-key"',
        ]

    def _rag_verification_order(self) -> list[str]:
        return [
            "POST /documents/ingest for the sample evidence corpus.",
            "POST /rfp/query for a cited RAG answer.",
            "POST /rfp/review-answer for unsupported-claim and citation checks.",
            "POST /rfp/evaluate or python -m app.evals.run_eval for standard eval metrics.",
            "GET /rag/corpus-coverage for corpus, citation, red-team, and missing-evidence coverage.",
            "POST /rag/eval-coverage-pack and inspect storage/rag_coverage/.",
            "python -m app.evals.run_red_team for explicit red-team prompts.",
            "POST /rfp/submission-regression for the in-process RAG/eval/red-team proof bundle.",
            "POST /api/reviewer-collection and inspect storage/api_contracts/.",
        ]

    def _reviewer_explanation(self) -> dict[str, str]:
        return {
            "recruiter": (
                "This pack proves the project has a broad, typed, locally runnable API surface with "
                "auth, RAG, eval, red-team, dashboard, and generated reviewer artifacts."
            ),
            "engineer": (
                "The contract audit derives inventory from FastAPI OpenAPI, then cross-checks docs/API, "
                "dashboard references, launch smoke rows, artifact producers, demo output, and local eval assets."
            ),
        }

    def _sample_body(self, path: str, smoke_command: str) -> str | None:
        if " -d " in smoke_command:
            return smoke_command.rsplit(" -d ", 1)[1].strip().strip("'")
        bodies = {
            "/api/reviewer-collection": "{}",
            "/rag/eval-coverage-pack": "{}",
            "/documents/ingest": '{"fixture_path":"sample_data/security_policy.md","document_type":"security"}',
            "/rfp/query": '{"question":"What SSO and encryption controls are supported?","top_k":4}',
            "/rfp/evaluate": '{"dataset_path":"sample_data/eval_dataset.json","top_k":4}',
            "/rfp/submission-regression": '{"top_k":4,"write_artifacts":true}',
            "/compliance/control-pack": '{"write_artifact":true}',
            "/procurement/approval-pack": '{"write_artifact":true}',
            "/rfp/reviewer-collaboration": "{}",
            "/rfp/reviewer-collaboration-pack": '{"write_artifact":true}',
            "/bid/roi-pack": '{"write_artifact":true}',
            "/rfp/objection-handling": '{"competitor_context":["Incumbent competitor is cheaper."],"top_k":4}',
            "/rfp/objection-handling-pack": '{"write_artifact":true}',
            "/learning/win-loss": '{"outcomes_fixture_path":"sample_data/rfp_outcomes.json","top_k_patterns":6}',
            "/learning/win-loss-pack": '{"write_artifact":true}',
        }
        no_body_paths = {"/health", "/documents", "/metrics/usage", "/audit/events"}
        return bodies.get(path, "{}" if path not in no_body_paths else None)

    def _curl(self, method: str, path: str, body: str | None, auth_required: bool) -> str:
        parts = [f'curl -X {method} "http://127.0.0.1:8000{path}"']
        if auth_required:
            parts.append('-H "X-API-Key: local-demo-key"')
        if body is not None and method != "GET":
            parts.append('-H "Content-Type: application/json"')
            parts.append(f"-d '{body}'")
        return " ".join(parts)

    def _powershell(self, method: str, path: str, body: str | None, auth_required: bool) -> str:
        parts = [f'Invoke-RestMethod -Method {method} -Uri "http://127.0.0.1:8000{path}"']
        if auth_required:
            parts.append('-Headers @{"X-API-Key" = "local-demo-key"}')
        if body is not None and method != "GET":
            escaped = body.replace("'", "''")
            parts.append(f"-ContentType 'application/json' -Body '{escaped}'")
        return " ".join(parts)

    def _domain(self, path: str) -> str:
        if path.startswith("/api/"):
            return "contract"
        if path.startswith("/auth") or path == "/health":
            return "core"
        if path.startswith("/documents"):
            return "documents"
        if path.startswith("/customers") or path.startswith("/rfp/response-memory"):
            return "customer_intelligence"
        if path.startswith("/rfp"):
            return "rfp_workflow"
        if path.startswith("/rag"):
            return "rag_coverage"
        if path.startswith("/compliance"):
            return "compliance"
        if path.startswith("/procurement"):
            return "procurement"
        if path.startswith("/bid"):
            return "bid"
        if path.startswith("/ops"):
            return "operations"
        if path.startswith("/ui"):
            return "dashboard"
        if path.startswith("/artifacts"):
            return "artifacts"
        return path.strip("/").split("/", 1)[0] or "root"

    def _title(self, path: str) -> str:
        return path.strip("/").replace("/", " ").replace("-", " ").title() or "Root"

    def _limitations(self) -> list[str]:
        return [
            "Contract audit is source/OpenAPI based; it does not execute every HTTP sample command.",
            "Generated storage/api_contracts artifacts are ignored by git and should be regenerated locally.",
            "Dashboard alignment is source-level and does not replace manual Streamlit screenshot review.",
            "Red-team has a CLI runner and submission-regression API path, not a standalone red-team HTTP route.",
            "OpenAI, Azure OpenAI, Azure AI Search, live Qdrant, CRM, legal, and calendar systems remain optional.",
        ]

    def _read(self, path: str) -> str:
        item = Path(path)
        return item.read_text(encoding="utf-8") if item.exists() else ""
