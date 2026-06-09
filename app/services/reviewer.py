# ruff: noqa: E501

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ReviewerQuickstartResponse,
    ReviewerWalkthroughPackRequest,
    ReviewerWalkthroughPackResponse,
)


class ReviewerQuickstartService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def quickstart(self, trace_id: str) -> ReviewerQuickstartResponse:
        endpoint_order = self._endpoint_walkthrough_order()
        return ReviewerQuickstartResponse(
            title="Reviewer Quickstart + Recruiter Walkthrough Pack",
            status="ready_for_local_review" if self.settings.provider_mode == "mock" else "ready_with_provider_overrides",
            provider_mode=self.settings.provider_mode,
            vector_store_mode=self.settings.vector_store_mode,
            local_mock_default=self.settings.provider_mode == "mock",
            exact_local_setup_commands=[
                "python -m pip install -e .",
                "python -m pip install -e \".[dev]\"",
                "python -m uvicorn app.main:app --reload",
                "python -m streamlit run dashboard/app.py",
                (
                    'curl -X GET "http://127.0.0.1:8000/reviewer/quickstart" '
                    '-H "X-API-Key: local-demo-key"'
                ),
                (
                    'curl -X POST "http://127.0.0.1:8000/reviewer/walkthrough-pack" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
                ),
            ],
            one_command_demo="python -m app.demo",
            verification_commands=self._verification_commands(),
            endpoint_walkthrough_order=endpoint_order,
            rag_rfp_workflow_walkthrough=self._rag_rfp_workflow(),
            artifact_proof_map=self._artifact_proof_map(),
            expected_outputs=self._expected_outputs(endpoint_order),
            troubleshooting=self._troubleshooting(),
            role_specific_reviewer_notes=self._role_notes(),
            proof_tour=self._proof_tour(),
            github_readme_blurb=(
                "Reviewer Quickstart: run `python -m app.demo`, then inspect `GET /reviewer/quickstart` "
                "and `POST /reviewer/walkthrough-pack` for a local/mock proof tour covering setup commands, "
                "API sequence, RAG/RFP workflow, generated artifacts, evals, red-team behavior, and reviewer notes."
            ),
            trace_id=trace_id,
        )

    def walkthrough_pack(
        self,
        trace_id: str,
        request: ReviewerWalkthroughPackRequest | None = None,
    ) -> ReviewerWalkthroughPackResponse:
        payload = request or ReviewerWalkthroughPackRequest()
        quickstart = self.quickstart(f"{trace_id}-quickstart")
        pack = self._pack_payload(trace_id, quickstart)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if payload.write_artifact:
            pack_dir = self.settings.storage_dir / "reviewer_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"reviewer_walkthrough_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"reviewer_walkthrough_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["walkthrough_pack_markdown"] = artifact_path
            pack["artifact_paths"]["walkthrough_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ReviewerWalkthroughPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            quickstart=quickstart,
            trace_id=trace_id,
        )

    def _verification_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python -m app.demo",
            (
                'rg "reviewer/quickstart|reviewer/walkthrough-pack|Reviewer Quickstart|'
                'Walkthrough Pack|reviewer_packs|proof tour" app dashboard docs README.md tests sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\reviewer_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _endpoint_walkthrough_order(self) -> list[dict[str, Any]]:
        return [
            self._endpoint("Core status", "GET", "/health", "Confirm mock/local provider and vector modes.", False),
            self._endpoint("Demo token", "POST", "/auth/demo-token", "Fetch the local API key header value.", False),
            self._endpoint("Reviewer quickstart", "GET", "/reviewer/quickstart", "Load this structured runbook.", True),
            self._endpoint("Ingest evidence", "POST", "/documents/ingest", "Index sample RFP, security, compliance, product, proposal, and pricing documents.", True),
            self._endpoint("Analyze RFP", "POST", "/rfp/analyze", "Extract requirements, deadlines, compliance asks, pricing mentions, risks, and missing information.", True),
            self._endpoint("Requirement matrix", "POST", "/rfp/requirement-matrix", "Turn requirements into owner/risk/status/evidence rows.", True),
            self._endpoint("Cited RAG question", "POST", "/rfp/query", "Ask a grounded SSO/encryption question and inspect citations.", True),
            self._endpoint("Draft response", "POST", "/rfp/draft-response", "Generate sectioned draft copy with citations and assumptions.", True),
            self._endpoint("Review package", "POST", "/rfp/review-package", "Run groundedness and missing-evidence checks.", True),
            self._endpoint("Evidence gaps", "POST", "/rfp/evidence-gaps", "Convert missing evidence into prioritized closure work.", True),
            self._endpoint("Source request pack", "POST", "/rfp/source-request-pack", "Write Markdown/JSON source-request artifacts.", True),
            self._endpoint("Readiness scorecard", "POST", "/rfp/readiness-scorecard", "Score submission readiness with blockers and owner bottlenecks.", True),
            self._endpoint("Submission regression", "POST", "/rfp/submission-regression", "Run deterministic eval/red-team/workflow readiness checks.", True),
            self._endpoint("Portfolio evidence", "GET", "/portfolio/evidence-index", "Map implemented skills to endpoints, services, tests, and artifacts.", True),
            self._endpoint("Walkthrough Pack", "POST", "/reviewer/walkthrough-pack", "Write recruiter and engineer walkthrough Markdown/JSON.", True),
        ]

    def _endpoint(
        self,
        name: str,
        method: str,
        path: str,
        reviewer_goal: str,
        requires_api_key: bool,
    ) -> dict[str, Any]:
        command = f'curl -X {method} "http://127.0.0.1:8000{path}"'
        if requires_api_key:
            command += ' -H "X-API-Key: local-demo-key"'
        if method == "POST" and path != "/auth/demo-token":
            command += ' -H "Content-Type: application/json" -d "{}"'
        return {
            "name": name,
            "method": method,
            "path": path,
            "reviewer_goal": reviewer_goal,
            "requires_api_key": requires_api_key,
            "sample_command": command,
        }

    def _rag_rfp_workflow(self) -> list[dict[str, Any]]:
        return [
            {
                "step": "Load sample corpus",
                "proof": "Six local fixtures under sample_data/ cover RFP, prior proposal, product, security, compliance, and pricing evidence.",
                "implementation": ["app/services/ingestion.py", "app/repositories/memory.py", "app/vectorstores/factory.py"],
            },
            {
                "step": "Retrieve grounded evidence",
                "proof": "Queries return citations with document id, chunk id, filename, snippet, and score.",
                "implementation": ["app/services/retrieval.py", "app/services/draft_generation.py", "tests/test_api_flows.py"],
            },
            {
                "step": "Detect unsupported claims",
                "proof": "Red-team questions with no local evidence produce missing_evidence and review findings instead of confident false claims.",
                "implementation": ["app/evals/run_red_team.py", "sample_data/red_team_questions.json", "app/services/review_board.py"],
            },
            {
                "step": "Turn RFP analysis into execution artifacts",
                "proof": "Requirement matrix, draft, source request, timeline, leadership brief, and submission memo write Markdown/JSON artifacts.",
                "implementation": ["app/services/workbench.py", "app/services/evidence_gap.py", "app/services/timeline_orchestration.py"],
            },
            {
                "step": "Verify with tests and evals",
                "proof": "pytest, ruff, standard eval, red-team eval, demo, and rg checks form the reviewer acceptance gate.",
                "implementation": ["tests/", "app/evals/run_eval.py", "app/demo.py", "Makefile"],
            },
        ]

    def _artifact_proof_map(self) -> dict[str, Any]:
        roots = {
            "reviewer_packs": self.settings.storage_dir / "reviewer_packs",
            "exports": self.settings.storage_dir / "exports",
            "source_requests": self.settings.storage_dir / "source_requests",
            "submission_calendars": self.settings.storage_dir / "submission_calendars",
            "submission_memos": self.settings.storage_dir / "submission_memos",
            "leadership_briefs": self.settings.storage_dir / "leadership_briefs",
            "demo_scripts": self.settings.storage_dir / "demo_scripts",
            "portfolio_packs": self.settings.storage_dir / "portfolio_packs",
            "launch_checklists": self.settings.storage_dir / "launch_checklists",
            "release_packs": self.settings.storage_dir / "release_packs",
        }
        return {
            name: {
                "path": str(path.resolve()),
                "proof": proof,
                "inspect_command": f"Get-ChildItem -Recurse -File {path} -ErrorAction SilentlyContinue | Select-Object FullName,Length,LastWriteTime",
            }
            for name, path, proof in [
                ("reviewer_packs", roots["reviewer_packs"], "Reviewer Quickstart Walkthrough Pack Markdown and JSON."),
                ("exports", roots["exports"], "RFP response package with requirement matrix, draft, citations, and customer fit."),
                ("source_requests", roots["source_requests"], "Evidence-gap closure requests and owner tasks."),
                ("submission_calendars", roots["submission_calendars"], "Timeline milestones, dependencies, readiness gates, and calendar entries."),
                ("submission_memos", roots["submission_memos"], "Go/no-go decision memo with blockers, exceptions, approvals, and verification commands."),
                ("leadership_briefs", roots["leadership_briefs"], "Consolidated portfolio leadership brief with metrics and artifact links."),
                ("demo_scripts", roots["demo_scripts"], "Interview demo script with commands, outputs, and talking points."),
                ("portfolio_packs", roots["portfolio_packs"], "Portfolio evidence index and interview pack."),
                ("launch_checklists", roots["launch_checklists"], "API smoke matrix and local launch checklist."),
                ("release_packs", roots["release_packs"], "Release Candidate GitHub Publish Pack."),
            ]
        }

    def _expected_outputs(self, endpoint_order: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "quickstart_status": "ready_for_local_review",
            "endpoint_count": len(endpoint_order),
            "demo_prints": [
                "Documents loaded",
                "Requirements extracted",
                "Citations",
                "Submission regression pass",
                "Portfolio interview pack",
                "Reviewer quickstart",
                "Walkthrough Pack",
                "Final demo summary",
            ],
            "artifact_files": [
                "storage/reviewer_packs/reviewer_walkthrough_pack_*.md",
                "storage/reviewer_packs/reviewer_walkthrough_pack_*.json",
            ],
            "eval_expectations": {
                "standard_eval": "Pass/fail summary: PASS",
                "red_team": "Pass/fail summary: PASS",
                "pytest": "all tests pass",
                "ruff": "All checks passed",
            },
        }

    def _troubleshooting(self) -> list[dict[str, str]]:
        return [
            {
                "symptom": "Protected endpoints return 401",
                "fix": "Use `X-API-Key: local-demo-key`, or call `POST /auth/demo-token` to confirm the configured key.",
            },
            {
                "symptom": "No citations or weak answers",
                "fix": "Run `python -m app.demo` or ingest all six sample documents before querying.",
            },
            {
                "symptom": "Walkthrough Pack path is empty",
                "fix": "Post `{\"write_artifact\": true}` to `/reviewer/walkthrough-pack` and inspect `storage/reviewer_packs/`.",
            },
            {
                "symptom": "Cloud provider or Qdrant errors",
                "fix": "Keep `PROVIDER_MODE=mock`; local review does not require paid OpenAI, Azure OpenAI, or a live Qdrant service.",
            },
            {
                "symptom": "Dashboard does not load reviewer content",
                "fix": "Start the API with `python -m uvicorn app.main:app --reload`, then run `python -m streamlit run dashboard/app.py`.",
            },
        ]

    def _role_notes(self) -> dict[str, list[str]]:
        return {
            "recruiter": [
                "Start with `python -m app.demo` and the Walkthrough Pack Markdown; it explains the product story without needing cloud keys.",
                "Look for generated artifact paths under `storage/reviewer_packs/`, `storage/portfolio_packs/`, and `storage/demo_scripts/`.",
                "The README blurb is suitable for a GitHub project summary or screening notes.",
            ],
            "engineering_reviewer": [
                "Inspect FastAPI route contracts in `app/api/routes.py`, Pydantic models in `app/models/api.py`, and service composition in `app/services/container.py`.",
                "Follow the proof tour from ingestion to retrieval, citations, review findings, source requests, evals, and artifacts.",
                "Run pytest, ruff, standard eval, red-team eval, demo, and the rg proof command before judging readiness.",
            ],
            "product_or_sales_leader": [
                "Review the RFP workflow as a practical response-team operating model: requirements, evidence, owners, risks, timelines, and go/no-go.",
                "Open generated Markdown artifacts first; JSON files are there for machine-readable proof.",
                "Limitations are explicit: mock/local by default, fake customer data, small sample fixtures, optional cloud adapters.",
            ],
        }

    def _proof_tour(self) -> list[str]:
        return [
            "Start the proof tour with `GET /reviewer/quickstart` to see setup, one-command demo, endpoint order, RAG/RFP flow, artifacts, expected outputs, troubleshooting, and role notes.",
            "Run `python -m app.demo` to generate real local artifacts and print reviewer quickstart status/count plus Walkthrough Pack path.",
            "Open `storage/reviewer_packs/reviewer_walkthrough_pack_*.md` for the recruiter-friendly story and engineer deep-dive path.",
            "Run the standard eval and red-team eval to prove both grounded retrieval and missing-evidence behavior.",
            "Use the Streamlit `Reviewer Quickstart` tab for the same API-backed flow without hand-writing curl commands.",
        ]

    def _pack_payload(self, trace_id: str, quickstart: ReviewerQuickstartResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Reviewer Quickstart Walkthrough Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "reviewer_quickstart_status": quickstart.status,
            "recruiter_friendly_story": [
                "This project is a local-first RFP Response Intelligence Copilot: it turns approved enterprise evidence into cited answers, response drafts, risk reviews, source requests, timelines, and submission decisions.",
                "A reviewer can run it without paid API keys. Mock/local mode still exercises real FastAPI routes, services, dashboard calls, tests, evals, red-team checks, and artifact generation.",
                "The portfolio value is visible in minutes: one command prints the workflow, and this pack points to the exact endpoints, files, commands, and generated proof artifacts.",
            ],
            "engineer_deep_dive_path": [
                "Read `app/services/container.py` to see dependency wiring.",
                "Read `app/api/routes.py` around `/reviewer/quickstart`, `/reviewer/walkthrough-pack`, `/rfp/query`, `/rfp/submission-regression`, and `/portfolio/interview-pack`.",
                "Trace retrieval through `app/services/ingestion.py`, `app/services/retrieval.py`, `app/vectorstores/factory.py`, and `app/services/draft_generation.py`.",
                "Trace safety through `app/services/review_board.py`, `app/services/evidence_gap.py`, `app/evals/run_eval.py`, and `app/evals/run_red_team.py`.",
                "Trace reviewer UX through `dashboard/app.py`, `app/demo.py`, `tests/test_api_flows.py`, and this generated Markdown/JSON pack.",
            ],
            "command_checklist": quickstart.exact_local_setup_commands + quickstart.verification_commands,
            "api_rag_proof_tour": quickstart.proof_tour,
            "endpoint_walkthrough_order": quickstart.endpoint_walkthrough_order,
            "rag_rfp_workflow_walkthrough": quickstart.rag_rfp_workflow_walkthrough,
            "artifacts_to_inspect": quickstart.artifact_proof_map,
            "expected_outputs": quickstart.expected_outputs,
            "limitations": [
                "Local/mock provider behavior is deterministic and intentionally small; it proves architecture and workflow, not production-scale retrieval quality.",
                "Sample customer profiles, approved snippets, contract terms, and RFP data are fake and stored under `sample_data/`.",
                "OpenAI, Azure OpenAI, Qdrant, Azure AI Search, CRM, legal, and calendar integrations are optional extension points rather than required local dependencies.",
                "The dashboard is an API client; generated artifact files remain under ignored `storage/` and are not committed.",
            ],
            "role_specific_reviewer_notes": quickstart.role_specific_reviewer_notes,
            "github_readme_blurb": quickstart.github_readme_blurb,
            "storage_snapshot": self._storage_snapshot(),
            "artifact_paths": {},
        }

    def _storage_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for path in sorted(self.settings.storage_dir.glob("*")):
            if not path.is_dir():
                continue
            files = sorted(
                (item for item in path.glob("*") if item.is_file()),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            snapshot[path.name] = {
                "path": str(path.resolve()),
                "file_count": len(files),
                "latest_files": [str(item.resolve()) for item in files[:5]],
            }
        return snapshot

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        lines = [
            "# Reviewer Quickstart Walkthrough Pack",
            "",
            "## Recruiter-Friendly Story",
            "",
            *[f"- {item}" for item in pack["recruiter_friendly_story"]],
            "",
            "## Engineer Deep-Dive Path",
            "",
            *[f"- {item}" for item in pack["engineer_deep_dive_path"]],
            "",
            "## Command Checklist",
            "",
        ]
        lines.extend(f"```bash\n{command}\n```" for command in pack["command_checklist"])
        lines.extend(["", "## API/RAG Proof Tour", ""])
        lines.extend(f"- {item}" for item in pack["api_rag_proof_tour"])
        lines.extend(["", "## Endpoint Walkthrough Order", ""])
        lines.append("| Order | Endpoint | Reviewer goal |")
        lines.append("| --- | --- | --- |")
        for index, endpoint in enumerate(pack["endpoint_walkthrough_order"], start=1):
            lines.append(
                f"| {index} | {endpoint['method']} {endpoint['path']} | {endpoint['reviewer_goal']} |"
            )
        lines.extend(["", "## RAG/RFP Workflow Walkthrough", ""])
        for item in pack["rag_rfp_workflow_walkthrough"]:
            lines.append(f"- {item['step']}: {item['proof']} Implementation: {', '.join(item['implementation'])}")
        lines.extend(["", "## Artifacts to Inspect", ""])
        for label, details in pack["artifacts_to_inspect"].items():
            lines.append(f"- {label}: {details['path']} - {details['proof']}")
        if pack["artifact_paths"]:
            lines.extend(["", "## Walkthrough Pack Artifacts", ""])
            for label, path in pack["artifact_paths"].items():
                lines.append(f"- {label}: {path}")
        lines.extend(["", "## Expected Outputs", ""])
        lines.append(f"- Quickstart status: {pack['expected_outputs']['quickstart_status']}")
        lines.append(f"- Endpoint count: {pack['expected_outputs']['endpoint_count']}")
        lines.append(f"- Demo prints: {', '.join(pack['expected_outputs']['demo_prints'])}")
        lines.extend(["", "## GitHub README Blurb", "", pack["github_readme_blurb"], ""])
        lines.extend(["## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        lines.extend(["", "## Role-Specific Reviewer Notes", ""])
        for role, notes in pack["role_specific_reviewer_notes"].items():
            lines.append(f"### {role.replace('_', ' ').title()}")
            lines.extend(f"- {note}" for note in notes)
        return "\n".join(lines).strip() + "\n"
