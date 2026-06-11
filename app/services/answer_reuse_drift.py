from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnswerReuseDriftFinding,
    AnswerReuseDriftPackResponse,
    AnswerReuseDriftResponse,
    AnswerReuseDriftTransition,
    AnswerReuseSnippet,
)
from app.services.answer_reuse_library import AnswerReuseLibraryService
from app.vectorstores.embedding import tokenize


class AnswerReuseDriftService:
    def __init__(self, settings: Settings, answer_reuse_library: AnswerReuseLibraryService) -> None:
        self.settings = settings
        self.answer_reuse_library = answer_reuse_library

    def drift_report(
        self,
        trace_id: str,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
        min_source_overlap: int = 4,
    ) -> AnswerReuseDriftResponse:
        library = self.answer_reuse_library.library(
            f"{trace_id}-library",
            category=category,
            customer_profile_id=customer_profile_id,
            include_expired=include_expired,
        )
        findings = [self._finding(snippet, min_source_overlap) for snippet in library.snippets]
        summary = self._summary(findings)
        return AnswerReuseDriftResponse(
            title="Answer Reuse Drift Monitor",
            status="ready" if summary["rewrite_count"] == 0 else "needs_owner_review",
            findings=findings,
            summary=summary,
            owner_queue=self._owner_queue(findings),
            workflow=self._workflow(summary),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        drift_report: AnswerReuseDriftResponse | None = None,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
        min_source_overlap: int = 4,
        write_artifact: bool = True,
    ) -> AnswerReuseDriftPackResponse:
        drift_report = drift_report or self.drift_report(
            f"{trace_id}-drift",
            category=category,
            customer_profile_id=customer_profile_id,
            include_expired=include_expired,
            min_source_overlap=min_source_overlap,
        )
        pack = self._pack_payload(trace_id, drift_report)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "answer_reuse_drift"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"answer_reuse_drift_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"answer_reuse_drift_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["answer_reuse_drift_markdown"] = artifact_path
            pack["artifact_paths"]["answer_reuse_drift_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return AnswerReuseDriftPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            drift_report=drift_report,
            trace_id=trace_id,
        )

    def _finding(self, snippet: AnswerReuseSnippet, min_source_overlap: int) -> AnswerReuseDriftFinding:
        source_text = self._source_text(snippet)
        source_overlap = self._source_overlap(snippet, source_text)
        missing_terms = self._missing_terms(snippet, source_text)
        stale_claim_terms = self._stale_claim_terms(snippet, source_text)
        citation_status = self._citation_status(snippet)
        drift_score = self._drift_score(
            snippet,
            citation_status,
            source_overlap,
            min_source_overlap,
            missing_terms,
            stale_claim_terms,
        )
        drift_status = self._drift_status(snippet, drift_score, citation_status, missing_terms, stale_claim_terms)
        trace = self._transition_trace(snippet, drift_status, citation_status, drift_score)
        return AnswerReuseDriftFinding(
            snippet_id=snippet.snippet_id,
            title=snippet.title,
            category=snippet.category,
            owner=snippet.owner,
            drift_status=drift_status,
            drift_score=drift_score,
            reuse_decision=snippet.reuse_decision,
            expiry_status=snippet.expiry_status,
            citation_status=citation_status,
            source_overlap=source_overlap,
            source_files=snippet.source_files,
            missing_terms=missing_terms,
            stale_claim_terms=stale_claim_terms,
            reviewer_action=self._reviewer_action(drift_status, snippet.owner),
            workflow_state=trace[-1].to_state,
            transition_trace=trace,
            evidence={
                "citation_refs": snippet.citation_refs,
                "lineage_statuses": [item["lineage_status"] for item in snippet.citation_lineage],
                "source_text_present": bool(source_text),
                "min_source_overlap": min_source_overlap,
            },
        )

    def _source_text(self, snippet: AnswerReuseSnippet) -> str:
        parts: list[str] = []
        for lineage in snippet.citation_lineage:
            source_path = lineage.get("source_path")
            if source_path:
                path = Path(source_path)
                if path.exists():
                    parts.append(path.read_text(encoding="utf-8"))
                    continue
            filename = lineage.get("filename")
            if filename:
                path = self.settings.sample_data_dir / filename
                if path.exists():
                    parts.append(path.read_text(encoding="utf-8"))
        return "\n".join(parts)

    def _source_overlap(self, snippet: AnswerReuseSnippet, source_text: str) -> int:
        snippet_terms = self._important_terms(f"{snippet.title} {snippet.reusable_text} {' '.join(snippet.tags)}")
        source_terms = set(tokenize(source_text.lower()))
        return len(snippet_terms & source_terms)

    def _missing_terms(self, snippet: AnswerReuseSnippet, source_text: str) -> list[str]:
        source_terms = set(tokenize(source_text.lower()))
        terms = self._important_terms(f"{snippet.reusable_text} {' '.join(snippet.tags)}")
        missing = sorted(term for term in terms if term not in source_terms)
        return missing[:8]

    def _stale_claim_terms(self, snippet: AnswerReuseSnippet, source_text: str) -> list[str]:
        source_lower = source_text.lower()
        text_lower = snippet.reusable_text.lower()
        risky_phrases = [
            "guarantee",
            "fedramp high",
            "all deployments",
            "next month",
            "unlimited",
            "free",
            "100%",
            "public-sector terms",
            "payment-processing constraints",
            "role-based access controls",
            "enforced mfa",
        ]
        return sorted(phrase for phrase in risky_phrases if phrase in text_lower and phrase not in source_lower)

    def _important_terms(self, text: str) -> set[str]:
        stopwords = {
            "with",
            "that",
            "this",
            "from",
            "through",
            "before",
            "after",
            "customer",
            "customers",
            "support",
            "supports",
            "response",
            "review",
            "reviewed",
            "reviewers",
            "policy",
            "terms",
            "required",
            "requires",
            "including",
            "include",
            "includes",
            "provided",
            "provide",
            "platform",
            "final",
            "submission",
        }
        return {token for token in tokenize(text.lower()) if len(token) > 3 and token not in stopwords}

    def _citation_status(self, snippet: AnswerReuseSnippet) -> str:
        statuses = {item["lineage_status"] for item in snippet.citation_lineage}
        if not statuses:
            return "missing_citations"
        if statuses == {"verified"}:
            return "verified"
        if "missing_source" in statuses:
            return "missing_source"
        return "weak_support"

    def _drift_score(
        self,
        snippet: AnswerReuseSnippet,
        citation_status: str,
        source_overlap: int,
        min_source_overlap: int,
        missing_terms: list[str],
        stale_claim_terms: list[str],
    ) -> int:
        score = 100
        if snippet.reuse_decision == "blocked":
            score -= 35
        if snippet.expiry_status in {"expired", "invalid_expiry"}:
            score -= 35
        elif snippet.expiry_status in {"renewal_due", "renewal_watch"}:
            score -= 12
        if citation_status == "missing_source":
            score -= 35
        elif citation_status == "weak_support":
            score -= 18
        elif citation_status == "missing_citations":
            score -= 30
        if source_overlap < min_source_overlap:
            score -= (min_source_overlap - source_overlap) * 6
        score -= min(24, len(missing_terms) * 3)
        score -= min(24, len(stale_claim_terms) * 8)
        return max(0, min(100, score))

    def _drift_status(
        self,
        snippet: AnswerReuseSnippet,
        drift_score: int,
        citation_status: str,
        missing_terms: list[str],
        stale_claim_terms: list[str],
    ) -> str:
        if (
            snippet.reuse_decision == "blocked"
            or drift_score < 55
            or citation_status in {"missing_source", "missing_citations"}
        ):
            return "retire_or_rewrite"
        if drift_score < 78 or stale_claim_terms:
            return "owner_review"
        if missing_terms:
            return "watch"
        return "stable"

    def _transition_trace(
        self,
        snippet: AnswerReuseSnippet,
        drift_status: str,
        citation_status: str,
        drift_score: int,
    ) -> list[AnswerReuseDriftTransition]:
        rows = [
            (None, "snippet_discovery", "accepted_snippet_loaded", "pass", "Loaded governed snippet."),
            (
                "snippet_discovery",
                "lineage_verification",
                citation_status,
                "pass" if citation_status == "verified" else "review",
                "Checked citation lineage from the Answer Reuse Library.",
            ),
            (
                "lineage_verification",
                "semantic_drift_scan",
                f"drift_score_{drift_score}",
                "pass" if drift_score >= 78 else "review",
                "Compared reusable text against cited local source text.",
            ),
            (
                "semantic_drift_scan",
                "owner_routing",
                drift_status,
                "pass" if drift_status in {"stable", "watch"} else "review",
                f"Routed to {snippet.owner} based on drift status.",
            ),
            (
                "owner_routing",
                "reuse_gate",
                self._gate_decision(drift_status),
                "pass" if drift_status == "stable" else "review",
                "Set final reuse gate for proposal copy/paste.",
            ),
        ]
        return [
            AnswerReuseDriftTransition(
                sequence=index,
                from_state=from_state,
                to_state=to_state,
                decision=decision,
                status=status,
                checkpoint_key=f"answer-reuse-drift:{snippet.snippet_id}:{to_state}",
                reason=reason,
            )
            for index, (from_state, to_state, decision, status, reason) in enumerate(rows, start=1)
        ]

    def _gate_decision(self, drift_status: str) -> str:
        return {
            "stable": "allow_reuse",
            "watch": "allow_with_monitoring",
            "owner_review": "require_owner_approval",
            "retire_or_rewrite": "block_reuse",
        }[drift_status]

    def _reviewer_action(self, drift_status: str, owner: str) -> str:
        actions = {
            "stable": "No action required beyond standard proposal review.",
            "watch": f"{owner} should confirm missing terms still reflect current source policy before broad reuse.",
            "owner_review": f"{owner} must approve or edit the snippet before customer-facing reuse.",
            "retire_or_rewrite": f"{owner} must retire or rewrite the snippet and attach current citations.",
        }
        return actions[drift_status]

    def _summary(self, findings: list[AnswerReuseDriftFinding]) -> dict[str, Any]:
        status_counts = Counter(finding.drift_status for finding in findings)
        owner_counts = Counter(finding.owner for finding in findings if finding.drift_status != "stable")
        average_score = round(sum(finding.drift_score for finding in findings) / len(findings), 1) if findings else 0
        return {
            "snippet_count": len(findings),
            "stable_count": status_counts.get("stable", 0),
            "watch_count": status_counts.get("watch", 0),
            "owner_review_count": status_counts.get("owner_review", 0),
            "rewrite_count": status_counts.get("retire_or_rewrite", 0),
            "average_drift_score": average_score,
            "owner_queue_count": sum(count for _, count in owner_counts.items()),
            "status_counts": dict(sorted(status_counts.items())),
            "owner_counts": dict(sorted(owner_counts.items())),
        }

    def _owner_queue(self, findings: list[AnswerReuseDriftFinding]) -> list[dict[str, Any]]:
        queue = [
            {
                "snippet_id": finding.snippet_id,
                "title": finding.title,
                "owner": finding.owner,
                "status": finding.drift_status,
                "drift_score": finding.drift_score,
                "required_action": finding.reviewer_action,
                "checkpoint_key": finding.transition_trace[-1].checkpoint_key,
            }
            for finding in findings
            if finding.drift_status != "stable"
        ]
        return sorted(queue, key=lambda item: (item["owner"], item["status"], item["snippet_id"]))

    def _workflow(self, summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "pattern": "state_machine_workflow",
            "states": [
                "snippet_discovery",
                "lineage_verification",
                "semantic_drift_scan",
                "owner_routing",
                "reuse_gate",
            ],
            "checkpointing": "Each snippet emits checkpoint keys in transition_trace.",
            "conditional_routing": {
                "stable": "allow_reuse",
                "watch": "allow_with_monitoring",
                "owner_review": "require_owner_approval",
                "retire_or_rewrite": "block_reuse",
            },
            "summary": summary,
        }

    def _pack_payload(self, trace_id: str, drift_report: AnswerReuseDriftResponse) -> dict[str, Any]:
        return {
            "title": "Answer Reuse Drift Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
            "drift_report": drift_report.model_dump(mode="json"),
            "governance_controls": [
                "Reusable answers are rescored against cited source text before broad reuse.",
                "Owner review is required when drift, source overlap, or stale claim terms exceed local thresholds.",
                "Traceable transitions and checkpoint keys make the reuse gate replayable for reviewers.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        report = pack["drift_report"]
        summary = report["summary"]
        lines = [
            f"# {pack['title']}",
            "",
            f"- Generated at: {pack['generated_at']}",
            f"- Trace ID: {pack['trace_id']}",
            f"- Status: {report['status']}",
            f"- Snippets checked: {summary['snippet_count']}",
            f"- Average drift score: {summary['average_drift_score']}",
            f"- Owner review: {summary['owner_review_count']}",
            f"- Rewrite/block: {summary['rewrite_count']}",
            "",
            "## Drift Findings",
            "",
            "| Snippet | Owner | Status | Score | Citation | Missing terms | Stale claim terms |",
            "| --- | --- | --- | ---: | --- | --- | --- |",
        ]
        for finding in report["findings"]:
            lines.append(
                "| "
                f"{self._md(finding['title'])} | "
                f"{self._md(finding['owner'])} | "
                f"{self._md(finding['drift_status'])} | "
                f"{finding['drift_score']} | "
                f"{self._md(finding['citation_status'])} | "
                f"{self._md(', '.join(finding['missing_terms']) or 'None')} | "
                f"{self._md(', '.join(finding['stale_claim_terms']) or 'None')} |"
            )
        lines.extend(["", "## Owner Queue", ""])
        if report["owner_queue"]:
            lines.extend(
                f"- {item['owner']}: {item['title']} ({item['status']}) - {item['required_action']}"
                for item in report["owner_queue"]
            )
        else:
            lines.append("- No owner actions required.")
        lines.extend(["", "## Workflow", ""])
        lines.extend(f"- {state}" for state in report["workflow"]["states"])
        lines.extend(["", "## Governance Controls", ""])
        lines.extend(f"- {item}" for item in pack["governance_controls"])
        lines.extend(["", "## Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in report["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in report["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-drift",
                "purpose": "Return governed drift findings for accepted answer snippets.",
            },
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-drift-pack",
                "purpose": "Write Markdown/JSON answer reuse drift artifacts.",
                "expected_artifacts": ["storage/answer_reuse_drift/*.md", "storage/answer_reuse_drift/*.json"],
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-drift" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-drift-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" '
                '-d "{\\"write_artifact\\":true}"'
            ),
            (
                'rg "answer-reuse-drift|Answer Reuse Drift|answer_reuse_drift" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\answer_reuse_drift -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Semantic drift is approximated with deterministic token and phrase checks against local fixtures.",
            "Owner routing is local-demo governance metadata, not an external approval workflow.",
            "A stable drift status does not replace final legal, security, or commercial review.",
        ]

    def _md(self, value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ")
