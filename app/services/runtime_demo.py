from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import shutil
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import RuntimeDemoPackResponse, RuntimeDemoReadinessResponse


class RuntimeDemoService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def readiness(self, trace_id: str) -> RuntimeDemoReadinessResponse:
        dependencies = self._dependency_checks()
        ports = self._process_port_checks()
        blockers = [
            check["package"]
            for check in dependencies
            if check["required"] and not check["installed"]
        ]
        missing_paths = [
            path
            for path in [
                "app/main.py",
                "dashboard/app.py",
                "sample_data/eval_dataset.json",
                "sample_data/red_team_questions.json",
                "scripts/dashboard_smoke.py",
            ]
            if not Path(path).exists()
        ]
        port_warnings = [
            check["service"]
            for check in ports
            if check["listening"]
        ]
        status = "ready"
        if blockers or missing_paths:
            status = "needs_install_or_files"
        elif port_warnings:
            status = "ready_ports_already_in_use"

        return RuntimeDemoReadinessResponse(
            title="Runtime Demo Server Readiness",
            status=status,
            provider_mode=self.settings.provider_mode,
            vector_store_mode=self.settings.vector_store_mode,
            local_run_commands=self._local_run_commands(),
            stop_commands=self._stop_commands(),
            expected_ports=self._expected_ports(),
            env_requirements=self._env_requirements(),
            dependency_checks=dependencies,
            process_port_checks=ports,
            expected_health_urls=self._expected_health_urls(),
            rag_eval_red_team_commands=self._rag_eval_red_team_commands(),
            demo_flow_order=self._demo_flow_order(),
            screenshot_checklist=self._screenshot_checklist(),
            troubleshooting=self._troubleshooting(),
            recruiter_engineer_explanation=self._recruiter_engineer_explanation(),
            known_limitations=self._known_limitations(),
            storage_runtime_pack_dir=str((self.settings.storage_dir / "runtime_packs").resolve()),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def demo_pack(self, trace_id: str, write_artifact: bool = True) -> RuntimeDemoPackResponse:
        readiness = self.readiness(f"{trace_id}-readiness")
        pack = self._pack_payload(trace_id, readiness)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "runtime_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"runtime_demo_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"runtime_demo_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["runtime_demo_markdown"] = artifact_path
            pack["artifact_paths"]["runtime_demo_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return RuntimeDemoPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            readiness=readiness,
            trace_id=trace_id,
        )

    def _pack_payload(
        self,
        trace_id: str,
        readiness: RuntimeDemoReadinessResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Runtime Demo Server Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "readiness": readiness.model_dump(mode="json"),
            "exact_start_commands": readiness.local_run_commands,
            "exact_stop_commands": readiness.stop_commands,
            "health_checks": readiness.expected_health_urls,
            "demo_flow_order": readiness.demo_flow_order,
            "rag_eval_red_team_verification_order": readiness.rag_eval_red_team_commands,
            "screenshot_checklist_placeholders": readiness.screenshot_checklist,
            "troubleshooting": readiness.troubleshooting,
            "recruiter_engineer_explanation": readiness.recruiter_engineer_explanation,
            "known_limitations": readiness.known_limitations,
            "artifact_paths": {},
        }

    def _dependency_checks(self) -> list[dict[str, Any]]:
        specs = [
            ("python", "Python executable", True, sys.executable),
            ("fastapi", "FastAPI app runtime", True, None),
            ("uvicorn", "ASGI server for the API", True, None),
            ("streamlit", "Dashboard runtime", True, None),
            ("httpx", "Dashboard/API client and smoke helpers", True, None),
            ("pydantic", "Typed request/response models", True, None),
            ("pytest", "Local test gate", True, None),
            ("ruff", "Local lint gate", True, None),
            ("rg", "Search/proof command", False, shutil.which("rg")),
        ]
        checks: list[dict[str, Any]] = []
        for package, purpose, required, executable in specs:
            if package == "python":
                installed = True
                source = executable
            elif package == "rg":
                installed = executable is not None
                source = executable
            else:
                spec = importlib.util.find_spec(package)
                installed = spec is not None
                source = getattr(spec, "origin", None) if spec else None
            checks.append(
                {
                    "package": package,
                    "purpose": purpose,
                    "required": required,
                    "installed": installed,
                    "source": source,
                    "install_hint": 'python -m pip install -e ".[dev]"' if required and not installed else "",
                }
            )
        return checks

    def _process_port_checks(self) -> list[dict[str, Any]]:
        return [self._port_check("FastAPI", "127.0.0.1", 8000), self._port_check("Streamlit", "127.0.0.1", 8501)]

    def _port_check(self, service: str, host: str, port: int) -> dict[str, Any]:
        listening = False
        error = ""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            try:
                listening = sock.connect_ex((host, port)) == 0
            except OSError as exc:
                error = str(exc)
        return {
            "service": service,
            "host": host,
            "port": port,
            "listening": listening,
            "check_type": "read_only_tcp_connect",
            "process_action": "No process was stopped or modified.",
            "notes": (
                f"{service} appears to be accepting TCP connections."
                if listening
                else f"{service} port is currently free or no local listener responded."
            ),
            "error": error,
        }

    def _expected_ports(self) -> list[dict[str, Any]]:
        return [
            {
                "service": "FastAPI",
                "host": "127.0.0.1",
                "port": 8000,
                "url": "http://127.0.0.1:8000",
                "command": "python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000",
            },
            {
                "service": "Streamlit",
                "host": "127.0.0.1",
                "port": 8501,
                "url": "http://127.0.0.1:8501",
                "command": "python -m streamlit run dashboard/app.py --server.port 8501",
            },
        ]

    def _env_requirements(self) -> list[dict[str, Any]]:
        return [
            self._env("API_KEY", self.settings.api_key, "local-demo-key", "FastAPI protected endpoint key."),
            self._env("PROVIDER_MODE", self.settings.provider_mode, "mock", "Mock LLM mode; no external API key."),
            self._env(
                "VECTOR_STORE_MODE",
                self.settings.vector_store_mode,
                "qdrant",
                "Adapter mode with local fallback; live Qdrant is optional.",
            ),
            self._env("RFP_API_URL", os.getenv("RFP_API_URL", ""), "http://127.0.0.1:8000", "Dashboard API URL."),
            self._env("STORAGE_DIR", str(self.settings.storage_dir), "storage", "Ignored local artifact root."),
        ]

    def _env(self, name: str, actual: str, default: str, purpose: str) -> dict[str, Any]:
        return {
            "name": name,
            "current_value": actual or "(unset)",
            "recommended_local_value": default,
            "required_for_local_mock": name in {"API_KEY", "PROVIDER_MODE", "VECTOR_STORE_MODE"},
            "purpose": purpose,
        }

    def _local_run_commands(self) -> list[str]:
        return [
            'python -m pip install -e ".[dev]"',
            "python scripts\\runtime_check.py",
            "python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000",
            "python -m streamlit run dashboard/app.py --server.port 8501",
            'curl -X GET "http://127.0.0.1:8000/health"',
            'curl -X POST "http://127.0.0.1:8000/auth/demo-token"',
            (
                'curl -X GET "http://127.0.0.1:8000/runtime/demo-readiness" '
                '-H "X-API-Key: local-demo-key"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/runtime/demo-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.demo",
        ]

    def _stop_commands(self) -> list[str]:
        return [
            "Press Ctrl+C in the FastAPI terminal.",
            "Press Ctrl+C in the Streamlit terminal.",
            "PowerShell manual stop if you started scripts\\start_demo.ps1: Stop-Process -Id <PID>",
            "Do not kill unrelated processes; inspect the PID and command line first.",
        ]

    def _expected_health_urls(self) -> list[dict[str, Any]]:
        return [
            {
                "label": "API health",
                "url": "http://127.0.0.1:8000/health",
                "expected": "200 JSON with status=ok, provider_mode=mock, vector_store_mode.",
            },
            {
                "label": "FastAPI docs",
                "url": "http://127.0.0.1:8000/docs",
                "expected": "Interactive OpenAPI docs load locally.",
            },
            {
                "label": "Runtime readiness",
                "url": "http://127.0.0.1:8000/runtime/demo-readiness",
                "expected": "200 JSON when X-API-Key is supplied.",
            },
            {
                "label": "Streamlit dashboard",
                "url": "http://127.0.0.1:8501",
                "expected": "Dashboard opens with Runtime Demo tab available.",
            },
        ]

    def _rag_eval_red_team_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python scripts\\dashboard_smoke.py",
            "python scripts\\runtime_check.py",
            "python -m app.demo",
            (
                'rg "runtime/demo-readiness|runtime/demo-pack|Runtime Demo|runtime_packs|'
                'runtime_check|start_demo" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\runtime_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _demo_flow_order(self) -> list[str]:
        return [
            "Install dev dependencies.",
            "Run python scripts\\runtime_check.py before starting servers.",
            "Start FastAPI on 127.0.0.1:8000.",
            "Start Streamlit on 127.0.0.1:8501.",
            "Open /health and /docs.",
            "Load the dashboard Runtime Demo tab.",
            "Generate Runtime Demo Server Pack under storage/runtime_packs/.",
            "Run pytest, ruff, standard eval, red-team eval, dashboard smoke, and python -m app.demo.",
            "Inspect generated Markdown/JSON artifacts and capture screenshots.",
        ]

    def _screenshot_checklist(self) -> list[dict[str, str]]:
        return [
            {
                "label": "API docs runtime endpoints",
                "placeholder": "Screenshot /docs showing /runtime/demo-readiness and /runtime/demo-pack.",
            },
            {
                "label": "Dashboard Runtime Demo tab",
                "placeholder": "Screenshot readiness status, commands, ports, and artifact path.",
            },
            {
                "label": "Terminal runtime_check",
                "placeholder": "Screenshot python scripts\\runtime_check.py PASS/READY output.",
            },
            {
                "label": "Generated runtime pack",
                "placeholder": "Screenshot storage/runtime_packs Markdown opened locally.",
            },
        ]

    def _troubleshooting(self) -> list[dict[str, str]]:
        return [
            {
                "symptom": "FastAPI port 8000 is already in use.",
                "fix": "Use the existing server if it is this app, or start with --port 8001 and set RFP_API_URL.",
            },
            {
                "symptom": "Streamlit cannot connect to API.",
                "fix": "Confirm /health works and set RFP_API_URL=http://127.0.0.1:8000 before starting Streamlit.",
            },
            {
                "symptom": "401 from runtime endpoints.",
                "fix": "Use POST /auth/demo-token or send X-API-Key=local-demo-key.",
            },
            {
                "symptom": "Import or command missing.",
                "fix": 'Run python -m pip install -e ".[dev]" from the repo root.',
            },
            {
                "symptom": "Cloud provider key errors.",
                "fix": "Set PROVIDER_MODE=mock for local review; OpenAI and Azure keys are optional.",
            },
        ]

    def _recruiter_engineer_explanation(self) -> dict[str, str]:
        return {
            "recruiter": (
                "The Runtime Demo Server Pack removes guesswork for reviewers: it lists exact local install, "
                "start, stop, health, eval, red-team, dashboard, and artifact inspection commands."
            ),
            "engineer": (
                "Readiness is deterministic and local-only. It inspects imports, expected files, environment "
                "defaults, and read-only localhost port state without killing processes or requiring external APIs."
            ),
        }

    def _known_limitations(self) -> list[str]:
        return [
            "Readiness checks do not launch the API or Streamlit server.",
            "Port checks only test whether localhost accepts a TCP connection; they do not identify or kill owners.",
            "Generated storage/runtime_packs artifacts are ignored by git and should be regenerated locally.",
            "OpenAI, Azure OpenAI, Azure AI Search, and live Qdrant are optional and not required for local review.",
            f"Runtime check was produced on {platform.system()} with Python {platform.python_version()}.",
        ]

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        readiness = pack["readiness"]
        lines = [
            "# Runtime Demo Server Pack",
            "",
            "## Runtime Readiness",
            "",
            f"- Status: {readiness['status']}",
            f"- Provider mode: {readiness['provider_mode']}",
            f"- Vector store mode: {readiness['vector_store_mode']}",
            f"- Runtime pack dir: {readiness['storage_runtime_pack_dir']}",
            "",
            "## Exact Start Commands",
            "",
        ]
        lines.extend(f"```powershell\n{command}\n```" for command in pack["exact_start_commands"])
        lines.extend(["", "## Exact Stop Commands", ""])
        lines.extend(f"- {command}" for command in pack["exact_stop_commands"])
        lines.extend(["", "## Expected Ports", ""])
        lines.append("| Service | Host | Port | URL | Status |")
        lines.append("| --- | --- | ---: | --- | --- |")
        port_status = {check["service"]: check for check in readiness["process_port_checks"]}
        for item in readiness["expected_ports"]:
            check = port_status.get(item["service"], {})
            status = "listening" if check.get("listening") else "not listening"
            lines.append(f"| {item['service']} | {item['host']} | {item['port']} | {item['url']} | {status} |")
        lines.extend(["", "## Environment Requirements", ""])
        lines.append("| Name | Current | Recommended | Purpose |")
        lines.append("| --- | --- | --- | --- |")
        for item in readiness["env_requirements"]:
            lines.append(
                f"| {item['name']} | {item['current_value']} | "
                f"{item['recommended_local_value']} | {item['purpose']} |"
            )
        lines.extend(["", "## Dependency Checks", ""])
        lines.append("| Package | Required | Installed | Purpose |")
        lines.append("| --- | --- | --- | --- |")
        for item in readiness["dependency_checks"]:
            lines.append(f"| {item['package']} | {item['required']} | {item['installed']} | {item['purpose']} |")
        lines.extend(["", "## Health Checks", ""])
        lines.extend(f"- {item['label']}: {item['url']} - {item['expected']}" for item in pack["health_checks"])
        lines.extend(["", "## Demo Flow Order", ""])
        lines.extend(f"{index}. {item}" for index, item in enumerate(pack["demo_flow_order"], start=1))
        lines.extend(["", "## RAG/Eval/Red-Team Verification Order", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["rag_eval_red_team_verification_order"])
        lines.extend(["", "## Screenshot Checklist Placeholders", ""])
        lines.extend(
            f"- [ ] {item['label']}: {item['placeholder']}"
            for item in pack["screenshot_checklist_placeholders"]
        )
        lines.extend(["", "## Troubleshooting", ""])
        lines.extend(f"- {item['symptom']}: {item['fix']}" for item in pack["troubleshooting"])
        lines.extend(["", "## Recruiter and Engineer Explanation", ""])
        lines.append(f"- Recruiter: {pack['recruiter_engineer_explanation']['recruiter']}")
        lines.append(f"- Engineer: {pack['recruiter_engineer_explanation']['engineer']}")
        lines.extend(["", "## Known Limitations", ""])
        lines.extend(f"- {item}" for item in pack["known_limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Runtime Demo Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"
