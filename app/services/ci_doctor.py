from __future__ import annotations

import json
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AuditPackResponse,
    CiDoctorCheck,
    CiDoctorResponse,
    DependencyInventory,
    SecretScanFinding,
    SecretScanSummary,
)


class CiDoctorService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repo_root = Path.cwd()

    def ci_doctor(self, trace_id: str) -> CiDoctorResponse:
        dependency_inventory = self.dependency_inventory()
        secret_scan = self.secret_scan()
        checks = self._checks(secret_scan)
        failed = [check for check in checks if check.status == "fail"]
        warnings = [check for check in checks if check.status == "warn"]
        score = self._score(checks)
        status = "blocked" if failed else "ready_with_warnings" if warnings else "ready"
        return CiDoctorResponse(
            title="Local CI Doctor + Dependency/Secrets Audit",
            status=status,
            score=score,
            checks=checks,
            summary={
                "total_checks": len(checks),
                "passed": sum(1 for check in checks if check.status == "pass"),
                "warnings": len(warnings),
                "failures": len(failed),
                "local_mock_default": self.settings.provider_mode == "mock",
                "provider_mode": self.settings.provider_mode,
                "vector_store_mode": self.settings.vector_store_mode,
                "secret_findings": secret_scan.finding_count,
                "dependency_files": len(dependency_inventory.dependency_files),
                "audit_pack_path": str((self.settings.storage_dir / "audit_packs").resolve()),
            },
            dependency_inventory=dependency_inventory,
            secret_scan=secret_scan,
            local_verification_commands=self._verification_commands(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def audit_pack(
        self,
        trace_id: str,
        write_artifact: bool = True,
        doctor: CiDoctorResponse | None = None,
    ) -> AuditPackResponse:
        doctor = doctor or self.ci_doctor(f"{trace_id}-doctor")
        pack = self._audit_pack_payload(trace_id, doctor)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "audit_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"local_ci_audit_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"local_ci_audit_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["audit_pack_markdown"] = artifact_path
            pack["artifact_paths"]["audit_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return AuditPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            ci_doctor=doctor,
            trace_id=trace_id,
        )

    def dependency_inventory(self) -> DependencyInventory:
        dependency_files: list[dict[str, Any]] = []
        runtime_dependencies: list[str] = []
        dev_dependencies: list[str] = []
        optional_extras: dict[str, list[str]] = {}
        notes = [
            "OpenAI, Azure OpenAI, Azure AI Search, and Qdrant client integrations are optional adapters.",
            "Default local verification uses PROVIDER_MODE=mock and does not require paid services.",
        ]

        pyproject = self.repo_root / "pyproject.toml"
        if pyproject.exists():
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project = data.get("project", {})
            runtime_dependencies = list(project.get("dependencies", []))
            optional_extras = {
                name: list(values)
                for name, values in project.get("optional-dependencies", {}).items()
            }
            dev_dependencies = optional_extras.get("dev", [])
            dependency_files.append(
                {
                    "path": "pyproject.toml",
                    "present": True,
                    "runtime_count": len(runtime_dependencies),
                    "optional_extra_count": len(optional_extras),
                }
            )

        for path in ["Dockerfile", "docker-compose.yml", ".env.example", "Makefile"]:
            item = self.repo_root / path
            dependency_files.append(
                {
                    "path": path,
                    "present": item.exists(),
                    "size_bytes": item.stat().st_size if item.exists() else 0,
                }
            )

        return DependencyInventory(
            dependency_files=dependency_files,
            runtime_dependencies=runtime_dependencies,
            dev_dependencies=dev_dependencies,
            optional_extras=optional_extras,
            notes=notes,
        )

    def secret_scan(self) -> SecretScanSummary:
        patterns = {
            "openai_api_key": re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
            "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----"),
            "azure_or_generic_secret": re.compile(
                r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*[\"']?([A-Za-z0-9_./+=-]{24,})"
            ),
            "cloud_connection_string": re.compile(r"(?i)\b(AccountKey|SharedAccessKey)=([A-Za-z0-9+/=]{24,})"),
        }
        skipped_dirs = [
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "build",
            "dist",
            "node_modules",
            "rfp_response_intelligence_copilot.egg-info",
            "storage",
            "venv",
        ]
        scan_suffixes = {
            ".env",
            ".example",
            ".json",
            ".md",
            ".py",
            ".toml",
            ".txt",
            ".yaml",
            ".yml",
        }
        findings: list[SecretScanFinding] = []
        files_scanned = 0
        for path in sorted(self.repo_root.rglob("*")):
            if not path.is_file() or self._is_skipped(path, skipped_dirs):
                continue
            if path.name not in {"Dockerfile", "Makefile"} and path.suffix.lower() not in scan_suffixes:
                continue
            if path.stat().st_size > 1_000_000:
                continue
            files_scanned += 1
            relative = path.relative_to(self.repo_root).as_posix()
            for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if self._allowed_placeholder_line(relative, line):
                    continue
                for pattern_id, pattern in patterns.items():
                    for match in pattern.finditer(line):
                        findings.append(
                            SecretScanFinding(
                                path=relative,
                                line=line_number,
                                pattern_id=pattern_id,
                                severity="high" if pattern_id in {"private_key_block", "openai_api_key"} else "medium",
                                redacted_match=self._redact(match.group(0)),
                            )
                        )

        return SecretScanSummary(
            files_scanned=files_scanned,
            skipped_dirs=skipped_dirs,
            finding_count=len(findings),
            findings=findings[:25],
            patterns=list(patterns),
            notes=[
                "Scan is pattern-based and redacted; it is a local publish-safety signal, not a full DLP system.",
                "Generated storage artifacts are skipped because storage/ is ignored by git.",
            ],
        )

    def _checks(self, secret_scan: SecretScanSummary) -> list[CiDoctorCheck]:
        checks = [
            self._path_check(
                "pytest_command",
                "Pytest command",
                "ci",
                ["tests", "pyproject.toml"],
                "python -m pytest -q",
                {"expected": "All tests pass locally and in GitHub Actions."},
            ),
            self._path_check(
                "ruff_command",
                "Ruff command",
                "ci",
                ["pyproject.toml"],
                "python -m ruff check .",
                {"expected": "All checks passed."},
            ),
            self._path_check(
                "eval_command",
                "Standard eval command",
                "evaluation",
                ["app/evals/run_eval.py", "sample_data/eval_dataset.json"],
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            ),
            self._path_check(
                "red_team_command",
                "Red-team command",
                "evaluation",
                ["app/evals/run_red_team.py", "sample_data/red_team_questions.json"],
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            ),
            self._path_check(
                "demo_command",
                "Demo command",
                "demo",
                ["app/demo.py", "sample_data/acme_enterprise_rfp.md"],
                "python -m app.demo",
            ),
            self._path_check(
                "github_actions",
                "GitHub Actions workflow presence",
                "ci",
                [".github/workflows/ci.yml"],
                "GitHub Actions workflow",
            ),
            self._path_check(
                "docker_compose",
                "Docker Compose presence",
                "runtime",
                ["Dockerfile", "docker-compose.yml"],
                "docker compose up --build",
            ),
            self._path_check(
                "env_example",
                ".env.example presence",
                "configuration",
                [".env.example"],
                None,
                {"expected_keys": self._env_example_keys()},
            ),
            self._content_check(
                "readme_sections",
                "README required sections",
                "docs",
                "README.md",
                ["30-Second Demo", "Architecture", "Local Commands", "API Snapshot", "Docker Compose", "Configuration"],
            ),
            self._path_check(
                "docs_presence",
                "Docs presence",
                "docs",
                ["docs/api.md", "docs/architecture.md", "docs/evaluation.md"],
            ),
            self._gitignore_check(),
            self._path_check(
                "dependency_files",
                "Dependency files",
                "dependencies",
                ["pyproject.toml", "Dockerfile", "docker-compose.yml"],
                None,
                {"dependency_files": [item["path"] for item in self.dependency_inventory().dependency_files]},
            ),
            self._content_check(
                "local_mock_provider_notes",
                "Local/mock provider notes",
                "configuration",
                "README.md",
                ["PROVIDER_MODE=mock", "OpenAI", "Azure", "Qdrant"],
            ),
            self._secret_check(secret_scan),
        ]
        return checks

    def _path_check(
        self,
        check_id: str,
        name: str,
        category: str,
        paths: list[str],
        command: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> CiDoctorCheck:
        missing = [path for path in paths if not (self.repo_root / path).exists()]
        return CiDoctorCheck(
            check_id=check_id,
            name=name,
            category=category,
            status="fail" if missing else "pass",
            command=command,
            evidence_paths=paths,
            missing_paths=missing,
            details=details or {},
            remediation=[f"Add or restore {path}." for path in missing],
        )

    def _content_check(
        self,
        check_id: str,
        name: str,
        category: str,
        path: str,
        required_terms: list[str],
    ) -> CiDoctorCheck:
        full_path = self.repo_root / path
        text = full_path.read_text(encoding="utf-8") if full_path.exists() else ""
        missing = [term for term in required_terms if term not in text]
        return CiDoctorCheck(
            check_id=check_id,
            name=name,
            category=category,
            status="fail" if not full_path.exists() else "warn" if missing else "pass",
            evidence_paths=[path],
            missing_paths=[] if full_path.exists() else [path],
            details={"required_terms": required_terms, "missing_terms": missing},
            remediation=[f"Document {term} in {path}." for term in missing],
        )

    def _gitignore_check(self) -> CiDoctorCheck:
        gitignore = self.repo_root / ".gitignore"
        text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        required = ["storage/", ".env", ".env.local", ".pytest_cache/", ".ruff_cache/"]
        missing = [item for item in required if item not in text]
        return CiDoctorCheck(
            check_id="generated_artifact_ignores",
            name="Generated artifact ignores",
            category="publish_safety",
            status="fail" if missing else "pass",
            evidence_paths=[".gitignore"],
            missing_paths=[] if gitignore.exists() else [".gitignore"],
            details={"required_ignores": required, "missing_ignores": missing},
            remediation=[f"Add {item} to .gitignore." for item in missing],
        )

    def _secret_check(self, secret_scan: SecretScanSummary) -> CiDoctorCheck:
        status = "fail" if secret_scan.finding_count else "pass"
        return CiDoctorCheck(
            check_id="secret_scan",
            name="Suspicious secret-pattern scan summary",
            category="publish_safety",
            status=status,
            evidence_paths=[],
            details=secret_scan.model_dump(mode="json"),
            remediation=[
                "Remove real secrets from tracked files and rotate exposed credentials before publishing.",
                "Keep generated artifacts under ignored storage/ paths.",
            ]
            if secret_scan.finding_count
            else [],
        )

    def _env_example_keys(self) -> list[str]:
        path = self.repo_root / ".env.example"
        if not path.exists():
            return []
        keys = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                keys.append(line.split("=", 1)[0].strip())
        return keys

    def _verification_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python -m app.demo",
            (
                'rg "ops/ci-doctor|ops/audit-pack|CI Doctor|Audit Pack|audit_packs|secret scan" '
                "app dashboard docs README.md tests sample_data Makefile"
            ),
            r"Get-ChildItem -Recurse -File storage\audit_packs -ErrorAction SilentlyContinue | "
            "Select-Object FullName,Length,LastWriteTime",
        ]

    def _audit_pack_payload(self, trace_id: str, doctor: CiDoctorResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Local CI Doctor + Dependency/Secrets Audit Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "ci_doctor": doctor.model_dump(mode="json"),
            "dependency_inventory": doctor.dependency_inventory.model_dump(mode="json"),
            "secret_scan_summary": doctor.secret_scan.model_dump(mode="json"),
            "local_verification_commands": doctor.local_verification_commands,
            "publish_safety_checklist": [
                {
                    "item": "Run pytest, ruff, eval, red-team eval, demo, CI Doctor, and Audit Pack locally.",
                    "status": "ready" if doctor.status != "blocked" else "review",
                },
                {
                    "item": "Confirm storage/ artifacts, .env files, caches, and build outputs are ignored.",
                    "status": self._check_status(doctor, "generated_artifact_ignores"),
                },
                {
                    "item": "Review redacted secret scan findings before pushing to GitHub.",
                    "status": "ready" if doctor.secret_scan.finding_count == 0 else "review",
                },
                {
                    "item": "Keep PROVIDER_MODE=mock for local portfolio verification.",
                    "status": self._check_status(doctor, "local_mock_provider_notes"),
                },
                {
                    "item": "Commit code/docs/tests only; regenerate audit packs locally as reviewer evidence.",
                    "status": "ready",
                },
            ],
            "remediation_notes": self._remediation_notes(doctor),
            "recruiter_interviewer_explanation": [
                "CI Doctor is a local, deterministic readiness endpoint for CI/docs/tests/env/Docker/dependencies.",
                "Audit Pack writes Markdown and JSON evidence under ignored storage/audit_packs for reviewer handoff.",
                (
                    "The secret scan is intentionally redacted and pattern-based so the repo can be checked "
                    "before publish."
                ),
                "OpenAI, Azure, and Qdrant adapters are optional; the default demo path is local/mock.",
            ],
            "limitations": [
                "CI Doctor does not execute shell commands; it verifies that the commands and required assets exist.",
                (
                    "The secret scan is heuristic and should be paired with normal repository hygiene before "
                    "production use."
                ),
                (
                    "Dependency inventory reads declared dependency files only; it does not resolve transitive "
                    "package trees."
                ),
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        doctor = pack["ci_doctor"]
        lines = [
            "# Local CI Doctor + Dependency/Secrets Audit Pack",
            "",
            "## CI Doctor Summary",
            "",
            f"- Status: {doctor['status']}",
            f"- Score: {doctor['score']}",
            f"- Checks: {doctor['summary']['passed']} pass, {doctor['summary']['warnings']} warn, "
            f"{doctor['summary']['failures']} fail",
            f"- Secret scan findings: {doctor['secret_scan']['finding_count']}",
            "",
            "## Checks",
            "",
            "| Check | Category | Status | Command | Remediation |",
            "| --- | --- | --- | --- | --- |",
        ]
        for check in doctor["checks"]:
            remediation = "; ".join(check["remediation"]) or "None"
            command = check["command"] or "N/A"
            lines.append(
                f"| {check['name']} | {check['category']} | {check['status']} | `{command}` | {remediation} |"
            )
        lines.extend(["", "## Dependency Inventory", ""])
        for item in pack["dependency_inventory"]["dependency_files"]:
            lines.append(f"- {item['path']}: {'present' if item['present'] else 'missing'}")
        lines.append(f"- Runtime dependencies: {len(pack['dependency_inventory']['runtime_dependencies'])}")
        lines.append(f"- Dev dependencies: {len(pack['dependency_inventory']['dev_dependencies'])}")
        lines.extend(["", "## Secret Scan Summary", ""])
        secret_scan = pack["secret_scan_summary"]
        lines.append(f"- Files scanned: {secret_scan['files_scanned']}")
        lines.append(f"- Finding count: {secret_scan['finding_count']}")
        if secret_scan["findings"]:
            for finding in secret_scan["findings"]:
                lines.append(
                    f"- {finding['severity']} {finding['pattern_id']} at "
                    f"{finding['path']}:{finding['line']} ({finding['redacted_match']})"
                )
        else:
            lines.append("- No suspicious secret-pattern findings.")
        lines.extend(["", "## Local Verification Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in pack["local_verification_commands"])
        lines.extend(["", "## Publish-Safety Checklist", ""])
        lines.extend(f"- [{item['status']}] {item['item']}" for item in pack["publish_safety_checklist"])
        lines.extend(["", "## Remediation Notes", ""])
        lines.extend(f"- {item}" for item in pack["remediation_notes"])
        lines.extend(["", "## Recruiter/Interviewer Explanation", ""])
        lines.extend(f"- {item}" for item in pack["recruiter_interviewer_explanation"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Audit Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _remediation_notes(self, doctor: CiDoctorResponse) -> list[str]:
        notes = []
        for check in doctor.checks:
            if check.status != "pass":
                notes.extend(check.remediation or [f"Review {check.name}."])
        if not notes:
            notes.append("No blocker remediation detected by CI Doctor.")
        return notes

    def _check_status(self, doctor: CiDoctorResponse, check_id: str) -> str:
        for check in doctor.checks:
            if check.check_id == check_id:
                return "ready" if check.status == "pass" else "review"
        return "review"

    def _score(self, checks: list[CiDoctorCheck]) -> int:
        score = 100
        score -= 12 * sum(1 for check in checks if check.status == "fail")
        score -= 4 * sum(1 for check in checks if check.status == "warn")
        return max(0, min(100, score))

    def _is_skipped(self, path: Path, skipped_dirs: list[str]) -> bool:
        parts = set(path.relative_to(self.repo_root).parts)
        return any(part in parts for part in skipped_dirs)

    def _allowed_placeholder_line(self, relative: str, line: str) -> bool:
        lower = line.lower()
        if relative == ".env.example":
            return True
        if "self.settings." in lower or "settings." in lower:
            return True
        return any(placeholder in lower for placeholder in ["local-demo-key", "test-key", "placeholder", "example"])

    def _redact(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) <= 10:
            return "***"
        return f"{cleaned[:4]}...{cleaned[-4:]}"
