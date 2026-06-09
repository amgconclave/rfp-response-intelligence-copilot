from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import GitPushPlanResponse, GitReadinessResponse


class GitReadinessService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = Path.cwd()

    def readiness(self, trace_id: str) -> GitReadinessResponse:
        repo = self._git(["rev-parse", "--is-inside-work-tree"])
        repo_detected = repo.returncode == 0 and repo.stdout.strip() == "true"
        repo_root = self._repo_root() if repo_detected else None
        branch = self._branch() if repo_detected else None
        status_entries = self._status_entries(repo_detected)
        tracked_count = self._tracked_count(repo_detected)
        groups = self._changed_file_groups(status_entries)
        generated_dirs = self._generated_artifact_directories(repo_detected)
        suspicious = self._suspicious_large_generated_files(status_entries)
        github_actions = self._github_actions()
        readme_final_handoff = self._readme_final_handoff()
        env_example_present = Path(".env.example").exists()
        working_tree_summary = self._working_tree_summary(status_entries, tracked_count)
        recommended_commit_groups = self._recommended_commit_groups(groups)
        blockers = []
        if not repo_detected:
            blockers.append("Git repository was not detected.")
        if not github_actions["workflow_present"]:
            blockers.append("Required GitHub Actions workflow is missing.")
        if not readme_final_handoff["has_final_handoff_mention"]:
            blockers.append("README does not mention the final handoff/reviewer path.")
        if not env_example_present:
            blockers.append(".env.example is missing.")
        if suspicious:
            blockers.append("Suspicious large or generated files need review before commit.")
        status = "blocked" if blockers else ("review_dirty_worktree" if working_tree_summary["dirty"] else "ready")
        return GitReadinessResponse(
            title="GitHub Push Readiness + Branch Hygiene",
            status=status,
            git_repo_detected=repo_detected,
            repo_root=repo_root,
            current_branch=branch,
            working_tree_summary=working_tree_summary,
            generated_artifact_directories=generated_dirs,
            changed_file_groups=groups,
            suspicious_large_generated_files=suspicious,
            github_actions=github_actions,
            readme_final_handoff=readme_final_handoff,
            env_example_present=env_example_present,
            dirty_worktree_guidance=self._dirty_worktree_guidance(working_tree_summary, blockers),
            recommended_commit_groups=recommended_commit_groups,
            local_review_commands=self._local_review_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def push_plan(self, trace_id: str, write_artifact: bool = True) -> GitPushPlanResponse:
        readiness = self.readiness(f"{trace_id}-readiness")
        pack = self._pack_payload(trace_id, readiness)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "git_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"github_push_readiness_{safe_trace_id}.md"
            json_path = pack_dir / f"github_push_readiness_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["git_push_plan_markdown"] = artifact_path
            pack["artifact_paths"]["git_push_plan_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return GitPushPlanResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            readiness=readiness,
            trace_id=trace_id,
        )

    def _git(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )

    def _repo_root(self) -> str | None:
        result = self._git(["rev-parse", "--show-toplevel"])
        return result.stdout.strip() or None if result.returncode == 0 else None

    def _branch(self) -> str | None:
        result = self._git(["branch", "--show-current"])
        branch = result.stdout.strip()
        return branch or "detached_HEAD" if result.returncode == 0 else None

    def _status_entries(self, repo_detected: bool) -> list[dict[str, Any]]:
        if not repo_detected:
            return []
        result = self._git(["status", "--porcelain=v1", "-uall", "--ignored"])
        entries: list[dict[str, Any]] = []
        for line in result.stdout.splitlines():
            if not line:
                continue
            status = line[:2]
            path = line[3:] if len(line) > 3 else ""
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            entries.append(
                {
                    "status": status,
                    "path": path.replace("\\", "/"),
                    "category": self._status_category(status),
                }
            )
        return entries

    def _status_category(self, status: str) -> str:
        if status == "??":
            return "untracked"
        if status == "!!":
            return "ignored"
        if "D" in status:
            return "deleted"
        if "A" in status:
            return "added"
        if "M" in status:
            return "modified"
        if "R" in status:
            return "renamed"
        return "changed"

    def _tracked_count(self, repo_detected: bool) -> int:
        if not repo_detected:
            return 0
        result = self._git(["ls-files"])
        return len([line for line in result.stdout.splitlines() if line.strip()]) if result.returncode == 0 else 0

    def _working_tree_summary(self, entries: list[dict[str, Any]], tracked_count: int) -> dict[str, Any]:
        counts = {
            "tracked": tracked_count,
            "modified": 0,
            "added": 0,
            "deleted": 0,
            "renamed": 0,
            "untracked": 0,
            "ignored": 0,
            "changed": 0,
        }
        for entry in entries:
            category = entry["category"]
            counts[category] = counts.get(category, 0) + 1
            if category != "ignored":
                counts["changed"] += 1
        changed_entries = [entry for entry in entries if entry["category"] != "ignored"]
        ignored_entries = [entry for entry in entries if entry["category"] == "ignored"]
        return {
            **counts,
            "dirty": bool(changed_entries),
            "changed_paths_sample": [entry["path"] for entry in changed_entries[:30]],
            "ignored_paths_sample": [entry["path"] for entry in ignored_entries[:20]],
        }

    def _changed_file_groups(self, entries: list[dict[str, Any]]) -> dict[str, list[str]]:
        changed = [entry["path"] for entry in entries if entry["category"] != "ignored"]
        groups = {
            "source_files_changed": [],
            "doc_files_changed": [],
            "test_files_changed": [],
            "dashboard_files_changed": [],
            "script_files_changed": [],
            "sample_data_changed": [],
            "config_files_changed": [],
            "generated_or_storage_changed": [],
            "other_files_changed": [],
        }
        for path in changed:
            suffix = Path(path).suffix.lower()
            if path.startswith("app/"):
                groups["source_files_changed"].append(path)
            elif path.startswith("docs/") or path == "README.md":
                groups["doc_files_changed"].append(path)
            elif path.startswith("tests/"):
                groups["test_files_changed"].append(path)
            elif path.startswith("dashboard/"):
                groups["dashboard_files_changed"].append(path)
            elif path.startswith("scripts/"):
                groups["script_files_changed"].append(path)
            elif path.startswith("sample_data/"):
                groups["sample_data_changed"].append(path)
            elif path.startswith("storage/") or self._looks_generated(path):
                groups["generated_or_storage_changed"].append(path)
            elif suffix in {".toml", ".yml", ".yaml", ".ini", ".cfg"} or path in {"Makefile", ".env.example"}:
                groups["config_files_changed"].append(path)
            else:
                groups["other_files_changed"].append(path)
        return groups

    def _generated_artifact_directories(self, repo_detected: bool) -> list[dict[str, Any]]:
        names = [
            "exports",
            "handoffs",
            "reports",
            "pricing_memos",
            "negotiation_briefs",
            "source_requests",
            "submission_calendars",
            "submission_memos",
            "leadership_briefs",
            "demo_scripts",
            "launch_checklists",
            "audit_packs",
            "portfolio_packs",
            "reviewer_packs",
            "release_packs",
            "ui_verification",
            "artifact_indexes",
            "final_handoff",
            "git_packs",
        ]
        directories: list[dict[str, Any]] = []
        for name in names:
            path = self.settings.storage_dir / name
            ignored = self._check_ignored(path) if repo_detected else False
            files = sorted(path.glob("*")) if path.exists() else []
            directories.append(
                {
                    "key": name,
                    "path": str(path.resolve()),
                    "exists": path.exists(),
                    "file_count": len([item for item in files if item.is_file()]),
                    "ignored": ignored,
                    "recommendation": "keep_ignored_do_not_commit",
                }
            )
        return directories

    def _check_ignored(self, path: Path) -> bool:
        resolved = path.resolve()
        root = self.root.resolve()
        if not resolved.is_relative_to(root):
            return True
        result = self._git(["check-ignore", str(path)])
        return result.returncode == 0

    def _suspicious_large_generated_files(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = [entry["path"] for entry in entries if entry["category"] != "ignored"]
        suspicious: list[dict[str, Any]] = []
        for path_text in candidates:
            path = Path(path_text)
            if not path.exists() or not path.is_file():
                continue
            size = path.stat().st_size
            reasons = []
            if size >= 1_000_000:
                reasons.append("large_file_over_1mb")
            if path_text.startswith("storage/") or self._looks_generated(path_text):
                reasons.append("generated_or_artifact_path")
            if path.suffix.lower() in {".zip", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".sqlite", ".db"}:
                reasons.append("binary_or_heavy_artifact_extension")
            if reasons:
                suspicious.append(
                    {
                        "path": path_text,
                        "size_bytes": size,
                        "reasons": reasons,
                        "recommendation": "review_before_commit; keep generated outputs ignored",
                    }
                )
        return sorted(suspicious, key=lambda item: item["size_bytes"], reverse=True)[:25]

    def _looks_generated(self, path: str) -> bool:
        return any(
            marker in path
            for marker in [
                "__pycache__/",
                ".pytest_cache/",
                ".ruff_cache/",
                ".mypy_cache/",
                ".egg-info/",
                "dist/",
                "build/",
            ]
        )

    def _github_actions(self) -> dict[str, Any]:
        workflow_dir = Path(".github/workflows")
        workflows = sorted(str(path).replace("\\", "/") for path in workflow_dir.glob("*.y*ml"))
        ci_present = any("ci" in Path(path).stem.lower() for path in workflows)
        return {
            "workflow_dir": str(workflow_dir.resolve()),
            "workflow_present": bool(workflows),
            "ci_workflow_present": ci_present,
            "workflow_files": workflows,
            "required_for_publish": True,
        }

    def _readme_final_handoff(self) -> dict[str, Any]:
        readme = Path("README.md")
        if not readme.exists():
            return {
                "readme_present": False,
                "has_final_handoff_mention": False,
                "matched_terms": [],
            }
        text = readme.read_text(encoding="utf-8").lower()
        terms = ["final handoff", "reviewer quickstart", "release candidate", "publish pack", "github"]
        matches = [term for term in terms if term in text]
        return {
            "readme_present": True,
            "has_final_handoff_mention": "final handoff" in matches or "reviewer quickstart" in matches,
            "matched_terms": matches,
        }

    def _dirty_worktree_guidance(self, summary: dict[str, Any], blockers: list[str]) -> list[str]:
        guidance = [
            "Review only with non-destructive commands; do not stage, commit, push, reset, checkout, clean, or delete.",
            "Inspect git status --porcelain=v1 -uall before deciding commit boundaries.",
            "Keep storage/ artifacts and cache/build outputs out of commits.",
        ]
        if summary["dirty"]:
            guidance.append(
                "Dirty worktree detected; group code, docs, tests, dashboard, scripts, "
                "and sample-data changes into intentional commits."
            )
        if blockers:
            guidance.append("Resolve blocker checks before publishing to GitHub: " + "; ".join(blockers))
        return guidance

    def _recommended_commit_groups(self, groups: dict[str, list[str]]) -> list[dict[str, Any]]:
        specs = [
            ("api-services", "API and service implementation", groups["source_files_changed"]),
            ("dashboard", "Streamlit dashboard wiring", groups["dashboard_files_changed"]),
            ("tests", "Tests and verification scripts", groups["test_files_changed"] + groups["script_files_changed"]),
            ("docs", "README and documentation updates", groups["doc_files_changed"]),
            (
                "sample-config",
                "Sample data and config updates",
                groups["sample_data_changed"] + groups["config_files_changed"],
            ),
        ]
        commits = []
        for commit_id, title, files in specs:
            if not files:
                continue
            commits.append(
                {
                    "group_id": commit_id,
                    "title": title,
                    "file_count": len(files),
                    "paths": files[:40],
                    "suggested_message": f"{title.lower()} for GitHub push readiness",
                }
            )
        generated = groups["generated_or_storage_changed"]
        if generated:
            commits.append(
                {
                    "group_id": "do-not-commit-generated",
                    "title": "Do not commit generated artifacts",
                    "file_count": len(generated),
                    "paths": generated[:40],
                    "suggested_message": "Do not commit; keep ignored or regenerate locally",
                }
            )
        return commits

    def _local_review_commands(self) -> list[str]:
        return [
            "git status --porcelain=v1 -uall",
            "git branch --show-current",
            "git rev-parse --is-inside-work-tree",
            "git ls-files",
            "git check-ignore storage/git_packs",
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python scripts\\dashboard_smoke.py",
            "python -m app.demo",
            (
                'rg "git/readiness|git/push-plan|GitHub Push Readiness|git_packs|'
                'Branch Hygiene|Git Readiness" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\git_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "This feature never stages, commits, pushes, resets, checks out, cleans, deletes, or calls GitHub APIs.",
            "Readiness is based on local git metadata and source-file checks, not remote branch protection rules.",
            "Large/generated file detection is heuristic and should be reviewed by a human before committing.",
            "Generated storage/git_packs artifacts are ignored and should be regenerated locally by reviewers.",
        ]

    def _pack_payload(self, trace_id: str, readiness: GitReadinessResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "GitHub Push Readiness + Branch Hygiene Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "readiness": readiness.model_dump(mode="json"),
            "non_destructive_review_commands": self._local_review_commands(),
            "suggested_commit_grouping": readiness.recommended_commit_groups,
            "do_not_commit_generated_artifacts": [
                "storage/ and storage/git_packs/ are local reviewer artifacts and stay ignored.",
                "Do not commit .pytest_cache/, .ruff_cache/, __pycache__/, build/, dist/, or egg-info outputs.",
                "Regenerate ignored artifacts with python -m app.demo or POST /git/push-plan.",
            ],
            "pre_push_verification_checklist": [
                "Run pytest, ruff, standard eval, red-team eval, dashboard smoke, and demo.",
                "Open GET /git/readiness and confirm status is ready or review_dirty_worktree with understood changes.",
                "Open POST /git/push-plan output and confirm generated artifacts remain ignored.",
                "Review README for final handoff, reviewer quickstart, and local-only limitations.",
                "Confirm .env.example exists and no secrets are present in changed files.",
            ],
            "repo_limitations": readiness.limitations,
            "recruiter_github_readme_publish_blurb": (
                "GitHub Push Readiness + Branch Hygiene adds local-only git inspection, branch hygiene, "
                "commit grouping, generated-artifact guardrails, and reviewer push-plan artifacts without "
                "calling GitHub or requiring cloud services."
            ),
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        readiness = pack["readiness"]
        summary = readiness["working_tree_summary"]
        lines = [
            "# GitHub Push Readiness + Branch Hygiene Pack",
            "",
            "## Readiness Summary",
            "",
            f"- Status: {readiness['status']}",
            f"- Git repo detected: {readiness['git_repo_detected']}",
            f"- Current branch: {readiness['current_branch']}",
            f"- Changed files: {summary['changed']}",
            f"- Untracked files: {summary['untracked']}",
            f"- Ignored files shown by git: {summary['ignored']}",
            f"- GitHub Actions workflow present: {readiness['github_actions']['workflow_present']}",
            f"- README final handoff mention: {readiness['readme_final_handoff']['has_final_handoff_mention']}",
            f"- .env.example present: {readiness['env_example_present']}",
            "",
            "## Non-Destructive Review Commands",
            "",
        ]
        lines.extend(f"```bash\n{command}\n```" for command in pack["non_destructive_review_commands"])
        lines.extend(["", "## Suggested Commit Grouping", ""])
        for group in pack["suggested_commit_grouping"] or [{"title": "No changed files detected", "paths": []}]:
            lines.append(f"### {group['title']}")
            lines.append(f"- Files: {group.get('file_count', 0)}")
            if group.get("suggested_message"):
                lines.append(f"- Suggested message: {group['suggested_message']}")
            for path in group.get("paths", [])[:20]:
                lines.append(f"- {path}")
            lines.append("")
        lines.extend(["## Do Not Commit Generated Artifacts", ""])
        lines.extend(f"- {item}" for item in pack["do_not_commit_generated_artifacts"])
        lines.extend(["", "## Generated Artifact Directories", ""])
        lines.append("| Directory | Files | Ignored | Recommendation |")
        lines.append("| --- | ---: | --- | --- |")
        for directory in readiness["generated_artifact_directories"]:
            lines.append(
                f"| {directory['key']} | {directory['file_count']} | "
                f"{directory['ignored']} | {directory['recommendation']} |"
            )
        lines.extend(["", "## Pre-Push Verification Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["pre_push_verification_checklist"])
        lines.extend(["", "## Repo Limitations", ""])
        lines.extend(f"- {item}" for item in pack["repo_limitations"])
        lines.extend(["", "## Recruiter / GitHub README Publish Blurb", ""])
        lines.append(pack["recruiter_github_readme_publish_blurb"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Git Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"
