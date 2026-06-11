from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    GovernedRetrievalPackResponse,
    GovernedRetrievalResponse,
    GovernedRetrievalResult,
    SourceTrustGateResponse,
    SourceTrustItem,
)
from app.models.domain import Citation
from app.services.retrieval import RetrievalService


class GovernedRetrievalService:
    def __init__(self, settings: Settings, retrieval: RetrievalService) -> None:
        self.settings = settings
        self.retrieval = retrieval

    async def preview(
        self,
        trace_id: str,
        question: str,
        source_trust: SourceTrustGateResponse,
        top_k: int = 6,
        include_suppressed: bool = False,
    ) -> GovernedRetrievalResponse:
        candidate_limit = max(top_k, top_k * 2)
        candidates = await self.retrieval.search(question, top_k=candidate_limit, min_score=0.0)
        trust_index = {source.filename: source for source in source_trust.sources}
        governed = [
            self._governed_result(citation, trust_index.get(citation.filename), index)
            for index, citation in enumerate(candidates, start=1)
        ]
        if not include_suppressed:
            governed = [item for item in governed if item.governance_action != "suppress"]
        governed = sorted(
            governed,
            key=lambda item: (
                0 if item.visible_to_generator else 1,
                -item.adjusted_score,
                item.filename,
            ),
        )[:candidate_limit]
        allowed = [item.citation for item in governed if item.visible_to_generator][:top_k]
        blocked = [item for item in governed if not item.visible_to_generator]
        summary = self._summary(governed, allowed, blocked, source_trust)
        return GovernedRetrievalResponse(
            title="Governed Retrieval Preview",
            question=question,
            status=self._status(summary),
            generated_at=datetime.now(UTC).isoformat(),
            top_k=top_k,
            include_suppressed=include_suppressed,
            results=governed,
            allowed_citations=allowed,
            blocked_results=blocked,
            reviewer_queue=self._reviewer_queue(governed),
            policy_trace=self._policy_trace(trace_id, candidates, governed, source_trust),
            summary=summary,
            local_proof_commands=self._local_proof_commands(question, top_k),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def pack(
        self,
        trace_id: str,
        governed_retrieval: GovernedRetrievalResponse,
        write_artifact: bool = True,
    ) -> GovernedRetrievalPackResponse:
        pack = self._pack_payload(trace_id, governed_retrieval)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "governed_retrieval"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"governed_retrieval_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"governed_retrieval_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["governed_retrieval_markdown"] = artifact_path
            pack["artifact_paths"]["governed_retrieval_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return GovernedRetrievalPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            governed_retrieval=governed_retrieval,
            trace_id=trace_id,
        )

    def _governed_result(
        self,
        citation: Citation,
        source_trust: SourceTrustItem | None,
        rank: int,
    ) -> GovernedRetrievalResult:
        if source_trust is None:
            policy = "review_before_use"
            decision = "unclassified_source"
            trust_score = 50
            owners = ["proposal_owner"]
            guardrails = ["Source is not present in Source Trust Gate output; require reviewer approval."]
        else:
            policy = source_trust.retrieval_policy
            decision = source_trust.trust_decision
            trust_score = source_trust.trust_score
            owners = source_trust.reviewer_owners
            guardrails = source_trust.guardrails
        action = self._action_for_policy(policy)
        adjusted = self._adjusted_score(citation.score, policy, trust_score)
        return GovernedRetrievalResult(
            result_id=f"governed-retrieval-{rank}",
            filename=citation.filename,
            chunk_id=citation.chunk_id,
            original_score=citation.score,
            adjusted_score=adjusted,
            retrieval_policy=policy,
            trust_decision=decision,
            trust_score=trust_score,
            governance_action=action,
            visible_to_generator=action in {"allow", "boost", "review_before_use"},
            approval_required=action in {"review_before_use", "suppress", "block"},
            reviewer_owners=owners,
            reason=self._reason(policy, decision),
            guardrails=guardrails[:6],
            citation=citation,
        )

    def _action_for_policy(self, policy: str) -> str:
        if policy == "boost":
            return "boost"
        if policy == "block":
            return "block"
        if policy == "suppress":
            return "suppress"
        if policy == "review_before_use":
            return "review_before_use"
        return "allow"

    def _adjusted_score(self, score: float, policy: str, trust_score: int) -> float:
        multiplier = {
            "boost": 1.18,
            "allow": 1.0,
            "review_before_use": 0.82,
            "suppress": 0.45,
            "block": 0.0,
        }.get(policy, 0.75)
        trust_factor = max(0.35, min(1.1, trust_score / 100))
        return round(min(1.0, score * multiplier * trust_factor), 4)

    def _reason(self, policy: str, decision: str) -> str:
        return {
            "boost": "Current trusted source can be preferred for grounded answer generation.",
            "allow": "Source can be used with normal citation checks.",
            "review_before_use": (
                "Source can be retrieved, but owner approval is required before final customer wording."
            ),
            "suppress": "Source is hidden from default generation unless a reviewer explicitly selects it.",
            "block": "Source is blocked from customer-facing generation until owner review clears it.",
        }.get(policy, f"Source trust decision is {decision}; apply reviewer judgment.")

    def _summary(
        self,
        governed: list[GovernedRetrievalResult],
        allowed: list[Citation],
        blocked: list[GovernedRetrievalResult],
        source_trust: SourceTrustGateResponse,
    ) -> dict[str, Any]:
        actions = self._counts(item.governance_action for item in governed)
        policies = self._counts(item.retrieval_policy for item in governed)
        return {
            "candidate_count": len(governed),
            "allowed_count": len(allowed),
            "blocked_or_suppressed_count": len(blocked),
            "approval_required_count": sum(1 for item in governed if item.approval_required),
            "action_counts": actions,
            "retrieval_policy_counts": policies,
            "source_trust_status": source_trust.status,
            "source_trust_blocked_count": source_trust.summary["blocked_count"],
            "source_trust_approval_required_count": source_trust.summary["approval_required_count"],
            "highest_adjusted_score": max((item.adjusted_score for item in governed), default=0),
        }

    def _status(self, summary: dict[str, Any]) -> str:
        if summary["allowed_count"] == 0:
            return "blocked"
        if summary["approval_required_count"] > 0 or summary["blocked_or_suppressed_count"] > 0:
            return "needs_review"
        return "pass"

    def _reviewer_queue(self, governed: list[GovernedRetrievalResult]) -> list[dict[str, Any]]:
        rows = []
        for item in governed:
            if not item.approval_required:
                continue
            rows.append(
                {
                    "result_id": item.result_id,
                    "filename": item.filename,
                    "policy": item.retrieval_policy,
                    "action": item.governance_action,
                    "owners": item.reviewer_owners,
                    "required_decision": self._required_decision(item),
                    "snippet": item.citation.snippet,
                }
            )
        return rows

    def _required_decision(self, item: GovernedRetrievalResult) -> str:
        if item.governance_action == "block":
            return "Renew or clear source-trust blockers before the citation can reach answer generation."
        if item.governance_action == "suppress":
            return "Reviewer must explicitly select this source and approve qualified wording."
        return "Owner approval is required before final export or customer-facing reuse."

    def _policy_trace(
        self,
        trace_id: str,
        candidates: list[Citation],
        governed: list[GovernedRetrievalResult],
        source_trust: SourceTrustGateResponse,
    ) -> list[dict[str, Any]]:
        return [
            {
                "span_id": f"{trace_id}-retrieve",
                "name": "retrieve_candidates",
                "input": {"candidate_limit": len(candidates)},
                "output": {"candidate_count": len(candidates), "filenames": [item.filename for item in candidates]},
            },
            {
                "span_id": f"{trace_id}-source-trust",
                "name": "join_source_trust",
                "input": {"source_trust_status": source_trust.status},
                "output": {
                    "source_count": source_trust.summary["source_count"],
                    "blocked_count": source_trust.summary["blocked_count"],
                    "approval_required_count": source_trust.summary["approval_required_count"],
                },
            },
            {
                "span_id": f"{trace_id}-policy",
                "name": "apply_retrieval_policy",
                "input": {"result_count": len(governed)},
                "output": {
                    "visible_count": sum(1 for item in governed if item.visible_to_generator),
                    "approval_required_count": sum(1 for item in governed if item.approval_required),
                    "action_counts": self._counts(item.governance_action for item in governed),
                },
            },
        ]

    def _pack_payload(self, trace_id: str, governed_retrieval: GovernedRetrievalResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Governed Retrieval Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "question": governed_retrieval.question,
            "status": governed_retrieval.status,
            "summary": governed_retrieval.summary,
            "results": [item.model_dump(mode="json") for item in governed_retrieval.results],
            "allowed_citations": [item.model_dump(mode="json") for item in governed_retrieval.allowed_citations],
            "reviewer_queue": governed_retrieval.reviewer_queue,
            "policy_trace": governed_retrieval.policy_trace,
            "local_proof_commands": governed_retrieval.local_proof_commands,
            "limitations": governed_retrieval.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Governed Retrieval Pack",
            "",
            f"- Question: {pack['question']}",
            f"- Status: {pack['status']}",
            f"- Allowed citations: {summary['allowed_count']}",
            f"- Approval required: {summary['approval_required_count']}",
            f"- Blocked or suppressed: {summary['blocked_or_suppressed_count']}",
            "",
            "## Governed Results",
            "",
            "| Result | Source | Policy | Action | Original | Adjusted | Owners | Reason |",
            "| --- | --- | --- | --- | ---: | ---: | --- | --- |",
        ]
        for item in pack["results"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(item["result_id"]),
                        self._md(item["filename"]),
                        self._md(item["retrieval_policy"]),
                        self._md(item["governance_action"]),
                        self._md(item["original_score"]),
                        self._md(item["adjusted_score"]),
                        self._md(", ".join(item["reviewer_owners"])),
                        self._md(item["reason"]),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Human Review Queue", ""])
        if pack["reviewer_queue"]:
            for item in pack["reviewer_queue"]:
                lines.append(
                    f"- {item['filename']} / {item['action']} / {', '.join(item['owners'])}: "
                    f"{item['required_decision']}"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Trace Analysis", ""])
        for span in pack["policy_trace"]:
            lines.append(f"- {span['name']}: {span['output']}")
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Governed Retrieval Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _local_proof_commands(self, question: str, top_k: int) -> list[str]:
        escaped = question.replace('"', '\\"')
        return [
            (
                'curl -X POST "http://127.0.0.1:8000/evidence/governed-retrieval" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" '
                f'-d "{{\\"question\\":\\"{escaped}\\",\\"top_k\\":{top_k}}}"'
            ),
            (
                'curl -X POST "http://127.0.0.1:8000/evidence/governed-retrieval-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" '
                f'-d "{{\\"question\\":\\"{escaped}\\",\\"top_k\\":{top_k},\\"write_artifact\\":true}}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'rg "governed-retrieval|Governed Retrieval|governed_retrieval" '
                "app dashboard docs README.md tests Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\governed_retrieval -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Governed retrieval is a deterministic local policy preview; it does not mutate the vector index.",
            "The default /rfp/query endpoint remains unchanged for backward-compatible local demos.",
            "Reviewer approvals are represented as local queue rows, not live GRC, ticketing, or CRM tasks.",
            "OpenAI and Azure providers remain optional because this policy runs before model invocation.",
        ]

    def _counts(self, values: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items()))

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
