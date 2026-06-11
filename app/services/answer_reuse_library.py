from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnswerReuseLibraryPackResponse,
    AnswerReuseLibraryResponse,
    AnswerReuseSnippet,
)
from app.models.domain import ApprovedResponseSnippet
from app.repositories.memory import InMemoryRepository
from app.vectorstores.embedding import tokenize


class AnswerReuseLibraryService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def library(
        self,
        trace_id: str,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
    ) -> AnswerReuseLibraryResponse:
        today = datetime.now(UTC).date()
        snippets = [
            self._governed_snippet(snippet, today)
            for snippet in self._accepted_snippets()
            if self._matches_filter(snippet, category, customer_profile_id)
        ]
        if not include_expired:
            snippets = [snippet for snippet in snippets if snippet.expiry_status != "expired"]
        summary = self._summary(snippets)
        return AnswerReuseLibraryResponse(
            title="Answer Reuse Library",
            status="ready" if summary["blocked_count"] == 0 else "needs_review",
            snippets=snippets,
            summary=summary,
            owner_queue=self._owner_queue(snippets),
            endpoint_references=self._endpoint_references(),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        library: AnswerReuseLibraryResponse | None = None,
        category: str | None = None,
        customer_profile_id: str | None = None,
        include_expired: bool = True,
        write_artifact: bool = True,
    ) -> AnswerReuseLibraryPackResponse:
        library = library or self.library(
            f"{trace_id}-library",
            category=category,
            customer_profile_id=customer_profile_id,
            include_expired=include_expired,
        )
        pack = self._pack_payload(trace_id, library)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "answer_reuse_library"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"answer_reuse_library_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"answer_reuse_library_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["answer_reuse_library_markdown"] = artifact_path
            pack["artifact_paths"]["answer_reuse_library_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return AnswerReuseLibraryPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            library=library,
            trace_id=trace_id,
        )

    def _governed_snippet(self, snippet: ApprovedResponseSnippet, today: date) -> AnswerReuseSnippet:
        expires_at = self._expiry(snippet)
        expiry_status = self._expiry_status(expires_at, today)
        lineage = [self._citation_lineage(ref, snippet) for ref in snippet.citations]
        missing_lineage = [item for item in lineage if item["lineage_status"] != "verified"]
        approval_status = snippet.approval_status or "accepted"
        reviewer_notes: list[str] = []
        if expiry_status in {"expired", "renewal_due"}:
            reviewer_notes.append(f"Owner review required because expiry status is {expiry_status}.")
        if missing_lineage:
            reviewer_notes.append("Citation lineage has missing or weak source support.")
        if approval_status != "accepted":
            reviewer_notes.append(f"Snippet approval status is {approval_status}.")
        decision = self._reuse_decision(approval_status, expiry_status, missing_lineage)
        confidence = self._confidence(decision, expiry_status, missing_lineage)
        return AnswerReuseSnippet(
            snippet_id=snippet.id,
            title=snippet.title,
            category=snippet.category,
            reusable_text=snippet.text,
            owner=snippet.owner or self._owner_for_category(snippet.category),
            expires_at=expires_at,
            expiry_status=expiry_status,
            approval_status=approval_status,
            reuse_decision=decision,
            confidence=confidence,
            tags=snippet.tags,
            customer_profile_ids=snippet.customer_profile_ids,
            citation_refs=snippet.citations,
            citation_lineage=lineage,
            source_files=sorted({item["filename"] for item in lineage if item["filename"]}),
            reviewer_notes=reviewer_notes,
        )

    def _citation_lineage(self, citation_ref: str, snippet: ApprovedResponseSnippet) -> dict[str, Any]:
        filename = citation_ref.split(":", 1)[0].strip()
        label = citation_ref.split(":", 1)[1].strip() if ":" in citation_ref else ""
        document = next((doc for doc in self.repo.documents.values() if doc.filename == filename), None)
        source_path = self.settings.sample_data_dir / filename
        source_text = self._repo_text(document.id) if document else self._path_text(source_path)
        source_found = bool(source_text)
        evidence_overlap = self._overlap_score(snippet, source_text)
        label_match = bool(label and label.lower() in source_text.lower())
        if source_found and (evidence_overlap >= 2 or label_match):
            status = "verified"
            risk = "low"
        elif source_found:
            status = "weak_support"
            risk = "medium"
        else:
            status = "missing_source"
            risk = "high"
        return {
            "citation_ref": citation_ref,
            "filename": filename,
            "section_label": label,
            "repository_document_id": document.id if document else None,
            "source_path": str(source_path) if source_path.exists() else None,
            "source_found": source_found,
            "section_label_match": label_match,
            "evidence_overlap": evidence_overlap,
            "lineage_status": status,
            "risk_level": risk,
        }

    def _summary(self, snippets: list[AnswerReuseSnippet]) -> dict[str, Any]:
        category_counts = Counter(snippet.category for snippet in snippets)
        owner_counts = Counter(snippet.owner for snippet in snippets)
        decision_counts = Counter(snippet.reuse_decision for snippet in snippets)
        expiry_counts = Counter(snippet.expiry_status for snippet in snippets)
        lineage_issues = sum(
            1
            for snippet in snippets
            for lineage in snippet.citation_lineage
            if lineage["lineage_status"] != "verified"
        )
        return {
            "snippet_count": len(snippets),
            "approved_count": decision_counts.get("approved_for_reuse", 0),
            "review_required_count": decision_counts.get("review_before_reuse", 0),
            "blocked_count": decision_counts.get("blocked", 0),
            "lineage_issue_count": lineage_issues,
            "category_counts": dict(sorted(category_counts.items())),
            "owner_counts": dict(sorted(owner_counts.items())),
            "expiry_status_counts": dict(sorted(expiry_counts.items())),
            "decision_counts": dict(sorted(decision_counts.items())),
        }

    def _owner_queue(self, snippets: list[AnswerReuseSnippet]) -> list[dict[str, Any]]:
        queue = []
        for snippet in snippets:
            if snippet.reuse_decision == "approved_for_reuse" and snippet.expiry_status == "current":
                continue
            queue.append(
                {
                    "snippet_id": snippet.snippet_id,
                    "title": snippet.title,
                    "owner": snippet.owner,
                    "category": snippet.category,
                    "status": snippet.reuse_decision,
                    "expires_at": snippet.expires_at,
                    "required_action": self._required_action(snippet),
                }
            )
        return sorted(queue, key=lambda item: (item["owner"], item["expires_at"], item["snippet_id"]))

    def _pack_payload(self, trace_id: str, library: AnswerReuseLibraryResponse) -> dict[str, Any]:
        return {
            "title": "Answer Reuse Library Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
            "library": library.model_dump(mode="json"),
            "governance_controls": [
                (
                    "Only snippets with accepted approval, current expiry, and verified citation lineage "
                    "are auto-approved."
                ),
                "Expired or weak-lineage snippets stay searchable but require owner review before copying into an RFP.",
                "All snippets retain source citation references, customer profile scope, and local proof commands.",
            ],
            "reviewer_checklist": [
                "Confirm owner and expiry before reuse in customer-facing language.",
                "Open cited source files and verify the snippet still matches current policy.",
                "Route weak lineage or expired snippets through security, compliance, legal, or commercial review.",
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        library = pack["library"]
        lines = [
            f"# {pack['title']}",
            "",
            f"- Generated at: {pack['generated_at']}",
            f"- Trace ID: {pack['trace_id']}",
            f"- Status: {library['status']}",
            f"- Snippets: {library['summary']['snippet_count']}",
            f"- Approved for reuse: {library['summary']['approved_count']}",
            f"- Review required: {library['summary']['review_required_count']}",
            "",
            "## Governed Snippets",
            "",
            "| ID | Title | Category | Owner | Expiry | Decision | Citations |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for snippet in library["snippets"]:
            lines.append(
                "| "
                f"{self._md(snippet['snippet_id'])} | "
                f"{self._md(snippet['title'])} | "
                f"{self._md(snippet['category'])} | "
                f"{self._md(snippet['owner'])} | "
                f"{self._md(snippet['expires_at'] + ' / ' + snippet['expiry_status'])} | "
                f"{self._md(snippet['reuse_decision'])} | "
                f"{self._md(', '.join(snippet['citation_refs']))} |"
            )
        lines.extend(["", "## Owner Queue", ""])
        if library["owner_queue"]:
            lines.extend(
                f"- {item['owner']}: {item['title']} - {item['required_action']}"
                for item in library["owner_queue"]
            )
        else:
            lines.append("- No owner actions required.")
        lines.extend(["", "## Citation Lineage", ""])
        for snippet in library["snippets"]:
            lines.append(f"### {snippet['title']}")
            for lineage in snippet["citation_lineage"]:
                lines.append(
                    f"- {lineage['citation_ref']}: {lineage['lineage_status']} "
                    f"(risk={lineage['risk_level']}, overlap={lineage['evidence_overlap']})"
                )
        lines.extend(["", "## Governance Controls", ""])
        lines.extend(f"- {item}" for item in pack["governance_controls"])
        lines.extend(["", "## Reviewer Checklist", ""])
        lines.extend(f"- [ ] {item}" for item in pack["reviewer_checklist"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"- `{command}`" for command in library["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in library["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Artifact Paths", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _accepted_snippets(self) -> list[ApprovedResponseSnippet]:
        path = self.settings.sample_data_dir / "approved_responses.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [ApprovedResponseSnippet(**item) for item in payload["snippets"]]

    def _matches_filter(
        self,
        snippet: ApprovedResponseSnippet,
        category: str | None,
        customer_profile_id: str | None,
    ) -> bool:
        if category and snippet.category != category:
            return False
        return (
            not customer_profile_id
            or customer_profile_id in snippet.customer_profile_ids
            or "all" in snippet.customer_profile_ids
        )

    def _expiry(self, snippet: ApprovedResponseSnippet) -> str:
        if snippet.expires_at:
            return snippet.expires_at
        defaults = {
            "security": "2027-12-31",
            "compliance": "2027-09-30",
            "implementation": "2027-06-30",
            "pricing": "2027-03-31",
        }
        return defaults.get(snippet.category, "2027-12-31")

    def _expiry_status(self, expires_at: str, today: date) -> str:
        try:
            expires = date.fromisoformat(expires_at)
        except ValueError:
            return "invalid_expiry"
        days = (expires - today).days
        if days < 0:
            return "expired"
        if days <= 30:
            return "renewal_due"
        if days <= 60:
            return "renewal_watch"
        return "current"

    def _reuse_decision(
        self,
        approval_status: str,
        expiry_status: str,
        missing_lineage: list[dict[str, Any]],
    ) -> str:
        if approval_status not in {"accepted", "approved"} or expiry_status in {"expired", "invalid_expiry"}:
            return "blocked"
        if expiry_status in {"renewal_due", "renewal_watch"} or missing_lineage:
            return "review_before_reuse"
        return "approved_for_reuse"

    def _confidence(
        self,
        decision: str,
        expiry_status: str,
        missing_lineage: list[dict[str, Any]],
    ) -> float:
        score = 0.92
        if decision == "review_before_reuse":
            score -= 0.18
        if decision == "blocked":
            score -= 0.42
        if expiry_status in {"renewal_due", "renewal_watch"}:
            score -= 0.08
        score -= min(0.24, len(missing_lineage) * 0.08)
        return round(max(0.2, score), 2)

    def _overlap_score(self, snippet: ApprovedResponseSnippet, source_text: str) -> int:
        if not source_text:
            return 0
        snippet_tokens = {
            token
            for token in tokenize(" ".join([snippet.title, snippet.text, *snippet.tags]))
            if len(token) > 3
        }
        source_tokens = {token for token in tokenize(source_text) if len(token) > 3}
        return len(snippet_tokens & source_tokens)

    def _repo_text(self, document_id: str) -> str:
        chunks = [chunk.text for chunk in self.repo.chunks.values() if chunk.document_id == document_id]
        return "\n".join(chunks)

    def _path_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _owner_for_category(self, category: str) -> str:
        return {
            "security": "security",
            "compliance": "compliance",
            "pricing": "commercial",
            "implementation": "solutions",
        }.get(category, "sales-ops")

    def _required_action(self, snippet: AnswerReuseSnippet) -> str:
        if snippet.expiry_status == "expired":
            return "Renew or retire snippet before reuse."
        if snippet.expiry_status in {"renewal_due", "renewal_watch"}:
            return "Owner to confirm policy is still current."
        if any(item["lineage_status"] != "verified" for item in snippet.citation_lineage):
            return "Attach stronger source evidence or update citation reference."
        if snippet.approval_status != "accepted":
            return "Approve snippet or keep blocked."
        return "Reviewer acknowledgement required before customer reuse."

    def _endpoint_references(self) -> list[dict[str, Any]]:
        return [
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-library",
                "purpose": "Return governed accepted-answer snippets with owner, expiry, and citation lineage.",
            },
            {
                "method": "POST",
                "path": "/rfp/answer-reuse-library-pack",
                "purpose": "Write Markdown/JSON governed reuse library artifacts.",
                "expected_artifacts": ["storage/answer_reuse_library/*.md", "storage/answer_reuse_library/*.json"],
            },
            {
                "method": "POST",
                "path": "/rfp/response-memory/search",
                "purpose": "Search approved snippets before applying governance decision.",
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-library" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/rfp/answer-reuse-library-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "answer-reuse-library|Answer Reuse Library|answer_reuse_library" '
                "app dashboard docs README.md tests sample_data Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\answer_reuse_library -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The library is built from local sample accepted-answer fixtures, not an external CMS.",
            "Citation lineage validates against local repository documents and sample source files only.",
            "Owner and expiry governance are deterministic demo controls that can be replaced with a workflow system.",
        ]

    def _md(self, value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
