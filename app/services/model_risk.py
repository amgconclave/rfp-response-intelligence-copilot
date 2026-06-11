from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ComplianceEvidenceSource,
    ModelRiskPackResponse,
    ModelRiskRegisterItem,
    ModelRiskRegisterResponse,
)
from app.repositories.memory import InMemoryRepository
from app.vectorstores.embedding import tokenize


class ModelRiskRegisterService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def register(self, trace_id: str) -> ModelRiskRegisterResponse:
        risks = [self._risk_item(spec) for spec in self._risk_specs()]
        severity_counts = Counter(risk.severity for risk in risks)
        status_counts = Counter(risk.status for risk in risks)
        control_counts = [len(risk.mitigation_controls) + len(risk.evidence_sources) for risk in risks]
        summary = {
            "risk_count": len(risks),
            "open_risk_count": sum(risk.status != "approved" for risk in risks),
            "high_or_critical_count": severity_counts.get("high", 0) + severity_counts.get("critical", 0),
            "blocked_count": status_counts.get("blocked", 0),
            "needs_review_count": status_counts.get("needs_review", 0),
            "approved_count": status_counts.get("approved", 0),
            "provider_mode": self.settings.provider_mode,
            "local_mock_default": self.settings.provider_mode == "mock",
            "average_control_coverage": round(sum(control_counts) / max(1, len(control_counts)), 2),
        }
        release_gates = self._release_gates(risks)
        return ModelRiskRegisterResponse(
            title="Model Risk Register",
            generated_at=datetime.now(UTC).isoformat(),
            provider_mode=self.settings.provider_mode,
            register_status=self._register_status(summary, release_gates),
            risks=risks,
            summary=summary,
            release_gates=release_gates,
            reviewer_queue=self._reviewer_queue(risks),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def risk_pack(
        self,
        trace_id: str,
        register: ModelRiskRegisterResponse,
        write_artifact: bool = True,
    ) -> ModelRiskPackResponse:
        pack = self._pack_payload(trace_id, register)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "model_risk"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"model_risk_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"model_risk_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["model_risk_markdown"] = artifact_path
            pack["artifact_paths"]["model_risk_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ModelRiskPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            risk_register=register,
            trace_id=trace_id,
        )

    def _risk_item(self, spec: dict[str, Any]) -> ModelRiskRegisterItem:
        evidence = self._evidence(spec)
        status = self._status(spec, evidence)
        return ModelRiskRegisterItem(
            risk_id=spec["risk_id"],
            title=spec["title"],
            risk_category=spec["risk_category"],
            severity=spec["severity"],
            likelihood=spec["likelihood"],
            status=status,
            reviewer_owner=spec["reviewer_owner"],
            description=spec["description"],
            mitigation_controls=spec["mitigation_controls"],
            evidence_sources=evidence,
            eval_gate=spec["eval_gate"],
            red_team_gate=spec["red_team_gate"],
            endpoint_references=spec["endpoint_references"],
            required_actions=self._required_actions(spec, evidence, status),
        )

    def _evidence(self, spec: dict[str, Any]) -> list[ComplianceEvidenceSource]:
        sources: list[ComplianceEvidenceSource] = []
        for chunk in self.repo.chunks.values():
            document = self.repo.documents.get(chunk.document_id)
            if not document or document.document_type == "rfp":
                continue
            matched_terms = self._matched_terms(spec["evidence_terms"], chunk.text)
            filename_match = document.filename in spec.get("priority_files", [])
            type_match = document.document_type in spec.get("document_types", [])
            if len(matched_terms) < 2 and not (matched_terms and (filename_match or type_match)):
                continue
            score = min(1.0, 0.34 + 0.09 * len(matched_terms) + (0.18 if filename_match else 0.08 if type_match else 0))
            sources.append(
                ComplianceEvidenceSource(
                    document_id=document.id,
                    chunk_id=chunk.id,
                    filename=document.filename,
                    document_type=document.document_type,
                    snippet=self._snippet(chunk.text, matched_terms),
                    matched_terms=matched_terms,
                    score=round(score, 2),
                )
            )
        return sorted(sources, key=lambda item: (-item.score, item.filename, item.snippet))[:3]

    def _matched_terms(self, terms: list[str], text: str) -> list[str]:
        lowered = text.lower()
        return [term for term in terms if term.lower() in lowered]

    def _snippet(self, text: str, matched_terms: list[str], limit: int = 300) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", compact) if sentence.strip()]
        term_set = set(tokenize(" ".join(matched_terms)))
        best = max(
            sentences,
            key=lambda sentence: len(term_set.intersection(tokenize(sentence))),
            default=compact,
        )
        return best[:limit].strip() + ("..." if len(best) > limit else "")

    def _status(self, spec: dict[str, Any], evidence: list[ComplianceEvidenceSource]) -> str:
        if spec["severity"] == "critical" and not evidence:
            return "blocked"
        if spec["cloud_only"] and self.settings.provider_mode == "mock":
            return "approved"
        if len(evidence) >= spec["min_evidence"]:
            return "approved" if spec["severity"] in {"medium", "low"} else "needs_review"
        return "needs_review"

    def _required_actions(
        self,
        spec: dict[str, Any],
        evidence: list[ComplianceEvidenceSource],
        status: str,
    ) -> list[str]:
        actions: list[str] = []
        if len(evidence) < spec["min_evidence"]:
            actions.append("Attach additional approved policy evidence before production use.")
        if spec["cloud_only"] and self.settings.provider_mode == "mock":
            actions.append("Keep this control documented as optional until a cloud provider is enabled.")
        if status != "approved":
            actions.append(f"{spec['reviewer_owner']} must sign off before external RFP submission.")
        actions.extend(spec.get("required_actions", []))
        return actions

    def _release_gates(self, risks: list[ModelRiskRegisterItem]) -> list[dict[str, Any]]:
        return [
            {
                "gate_id": "eval_quality_gate",
                "status": "pass",
                "owner": "AI Governance Reviewer",
                "evidence": "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "risk_ids": [
                    risk.risk_id
                    for risk in risks
                    if "eval" in risk.risk_category or "retrieval" in risk.risk_category
                ],
            },
            {
                "gate_id": "red_team_missing_evidence_gate",
                "status": "pass",
                "owner": "Security Architect",
                "evidence": "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                "risk_ids": [risk.risk_id for risk in risks if risk.red_team_gate != "not_applicable"],
            },
            {
                "gate_id": "provider_change_gate",
                "status": "pass" if self.settings.provider_mode == "mock" else "needs_review",
                "owner": "Platform Owner",
                "evidence": f"PROVIDER_MODE={self.settings.provider_mode}",
                "risk_ids": [risk.risk_id for risk in risks if "provider" in risk.risk_category],
            },
            {
                "gate_id": "human_approval_gate",
                "status": "needs_review" if any(risk.status != "approved" for risk in risks) else "pass",
                "owner": "Proposal Manager",
                "evidence": "Reviewer Collaboration, Submission Decision, and Exception Register artifacts.",
                "risk_ids": [risk.risk_id for risk in risks if risk.status != "approved"],
            },
        ]

    def _register_status(self, summary: dict[str, Any], gates: list[dict[str, Any]]) -> str:
        if summary["blocked_count"]:
            return "blocked"
        if any(gate["status"] == "needs_review" for gate in gates) or summary["needs_review_count"]:
            return "needs_review"
        return "approved"

    def _reviewer_queue(self, risks: list[ModelRiskRegisterItem]) -> list[dict[str, Any]]:
        grouped: dict[str, list[ModelRiskRegisterItem]] = {}
        for risk in risks:
            if risk.status == "approved":
                continue
            grouped.setdefault(risk.reviewer_owner, []).append(risk)
        queue = []
        for owner, owner_risks in sorted(grouped.items()):
            queue.append(
                {
                    "reviewer_owner": owner,
                    "risk_count": len(owner_risks),
                    "highest_severity": self._highest_severity(owner_risks),
                    "risk_ids": [risk.risk_id for risk in owner_risks],
                    "next_action": "Approve mitigations, attach missing evidence, or document a submission exception.",
                }
            )
        return queue

    def _highest_severity(self, risks: list[ModelRiskRegisterItem]) -> str:
        order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        return max((risk.severity for risk in risks), key=lambda value: order.get(value, 0), default="low")

    def _pack_payload(
        self,
        trace_id: str,
        register: ModelRiskRegisterResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Model Risk Register Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "provider_mode": register.provider_mode,
            "register_status": register.register_status,
            "summary": register.summary,
            "risks": [risk.model_dump(mode="json") for risk in register.risks],
            "release_gates": register.release_gates,
            "reviewer_queue": register.reviewer_queue,
            "local_proof_commands": register.local_proof_commands,
            "limitations": register.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Model Risk Register Pack",
            "",
            "## Summary",
            "",
            f"- Status: {pack['register_status']}",
            f"- Provider mode: {pack['provider_mode']}",
            f"- Risks: {summary['risk_count']}",
            f"- High or critical: {summary['high_or_critical_count']}",
            f"- Needs review: {summary['needs_review_count']}",
            f"- Blocked: {summary['blocked_count']}",
            "",
            "## Risk Register",
            "",
            "| Risk | Category | Severity | Status | Owner | Eval gate | Red-team gate |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for risk in pack["risks"]:
            lines.append(
                "| {risk} | {category} | {severity} | {status} | {owner} | {eval_gate} | {red_team_gate} |".format(
                    risk=self._md(risk["title"]),
                    category=self._md(risk["risk_category"]),
                    severity=risk["severity"],
                    status=risk["status"],
                    owner=self._md(risk["reviewer_owner"]),
                    eval_gate=self._md(risk["eval_gate"]),
                    red_team_gate=self._md(risk["red_team_gate"]),
                )
            )
        lines.extend(["", "## Evidence And Actions", ""])
        for risk in pack["risks"]:
            lines.append(f"### {risk['risk_id']}: {risk['title']}")
            lines.append(f"- Description: {self._md(risk['description'])}")
            lines.append(f"- Controls: {self._md(', '.join(risk['mitigation_controls']))}")
            lines.append(f"- Endpoints: {self._md(', '.join(risk['endpoint_references']))}")
            if risk["evidence_sources"]:
                for source in risk["evidence_sources"]:
                    lines.append(
                        f"- Evidence `{source['filename']}` ({source['score']}): "
                        f"{self._md(source['snippet'])}"
                    )
            else:
                lines.append("- Evidence: No local evidence mapped.")
            for action in risk["required_actions"]:
                lines.append(f"- Action: {self._md(action)}")
            lines.append("")
        lines.extend(["## Release Gates", ""])
        for gate in pack["release_gates"]:
            lines.append(
                f"- {gate['gate_id']}: {gate['status']} - {self._md(gate['evidence'])} "
                f"(owner: {gate['owner']})"
            )
        lines.extend(["", "## Reviewer Queue", ""])
        if not pack["reviewer_queue"]:
            lines.append("- No reviewer queue items remain open.")
        for item in pack["reviewer_queue"]:
            lines.append(
                f"- {item['reviewer_owner']}: {item['risk_count']} risk(s), "
                f"highest={item['highest_severity']}, ids={', '.join(item['risk_ids'])}"
            )
        lines.extend(["", "## Local Proof Commands", ""])
        for command in pack["local_proof_commands"]:
            lines.append(f"```powershell\n{command}\n```")
        lines.extend(["", "## Limitations", ""])
        for item in pack["limitations"]:
            lines.append(f"- {self._md(item)}")
        if pack["artifact_paths"]:
            lines.extend(["", "## Model Risk Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _risk_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "risk_id": "model_risk_01_groundedness",
                "title": "Ungrounded or unsupported RFP answer",
                "risk_category": "retrieval_grounding",
                "severity": "high",
                "likelihood": "medium",
                "reviewer_owner": "AI Governance Reviewer",
                "description": (
                    "Generated answers may overstate product, compliance, or roadmap claims without approved "
                    "source evidence."
                ),
                "mitigation_controls": ["citation coverage", "missing-evidence refusal", "review-board findings"],
                "eval_gate": "standard_eval_pass_required",
                "red_team_gate": "missing_evidence_detection_required",
                "endpoint_references": ["/rfp/query", "/rfp/review-answer", "/rfp/evaluate"],
                "priority_files": ["ai_governance_security.md", "compliance_policy.md"],
                "document_types": ["security", "compliance"],
                "evidence_terms": ["citations", "evidence", "grounded", "human reviewers", "missing evidence"],
                "min_evidence": 1,
                "cloud_only": False,
                "required_actions": ["Run review-package before export or submission decisions."],
            },
            {
                "risk_id": "model_risk_02_provider_change",
                "title": "Cloud provider routing changes data handling obligations",
                "risk_category": "provider_governance",
                "severity": "high",
                "likelihood": "low",
                "reviewer_owner": "Platform Owner",
                "description": (
                    "Switching from mock to OpenAI or Azure OpenAI can alter prompt retention, logging, "
                    "and approval requirements."
                ),
                "mitigation_controls": [
                    "provider mode config",
                    "optional adapter boundary",
                    "privacy retention guardrails",
                ],
                "eval_gate": "same_dataset_must_pass_after_provider_change",
                "red_team_gate": "red_team_must_pass_after_provider_change",
                "endpoint_references": ["/health", "/ops/cost-governance", "/privacy/retention-guardrails"],
                "priority_files": ["ai_governance_security.md", "dpa_privacy_policy.md"],
                "document_types": ["security", "privacy"],
                "evidence_terms": ["provider", "azure openai", "openai", "prompt", "approval", "data handling"],
                "min_evidence": 1,
                "cloud_only": True,
            },
            {
                "risk_id": "model_risk_03_prompt_privacy",
                "title": "Sensitive customer content in prompts, logs, or generated artifacts",
                "risk_category": "privacy_retention",
                "severity": "high",
                "likelihood": "medium",
                "reviewer_owner": "Legal Privacy Reviewer",
                "description": (
                    "RFP packets can include customer, contract, and business contact data that should be "
                    "minimized and retained intentionally."
                ),
                "mitigation_controls": ["redaction guidance", "retention posture", "local artifact ignore rules"],
                "eval_gate": "privacy_pack_review_required",
                "red_team_gate": "not_applicable",
                "endpoint_references": [
                    "/privacy/retention-guardrails",
                    "/privacy/retention-pack",
                    "/artifacts/inventory",
                ],
                "priority_files": ["dpa_privacy_policy.md", "compliance_policy.md"],
                "document_types": ["privacy", "compliance"],
                "evidence_terms": ["privacy", "personal data", "retention", "deletion", "generated artifact"],
                "min_evidence": 2,
                "cloud_only": False,
            },
            {
                "risk_id": "model_risk_04_evaluation_blind_spots",
                "title": "Small local eval set misses production failure modes",
                "risk_category": "eval_coverage",
                "severity": "medium",
                "likelihood": "medium",
                "reviewer_owner": "AI Governance Reviewer",
                "description": (
                    "The deterministic sample evals prove local behavior but do not represent every customer "
                    "domain or production corpus."
                ),
                "mitigation_controls": [
                    "corpus coverage pack",
                    "red-team dataset",
                    "win/loss learning recommendations",
                ],
                "eval_gate": "eval_and_corpus_coverage_pack_required",
                "red_team_gate": "red_team_dataset_required",
                "endpoint_references": ["/rag/corpus-coverage", "/rag/eval-coverage-pack", "/learning/win-loss"],
                "priority_files": ["ai_governance_security.md", "prior_proposal.md"],
                "document_types": ["security", "proposal"],
                "evidence_terms": ["evaluation", "red-team", "missing-evidence", "quality", "approved"],
                "min_evidence": 1,
                "cloud_only": False,
                "required_actions": ["Expand eval rows when adding new verticals, products, or compliance claims."],
            },
            {
                "risk_id": "model_risk_05_cost_and_latency",
                "title": "Provider cost, token, and latency budget overrun",
                "risk_category": "cost_latency",
                "severity": "medium",
                "likelihood": "medium",
                "reviewer_owner": "Proposal Operations",
                "description": (
                    "RFP workflows can fan out across query, draft, eval, and review calls, increasing usage "
                    "cost and latency."
                ),
                "mitigation_controls": ["token usage telemetry", "cost governance pack", "top-k tuning"],
                "eval_gate": "cost_governance_review_required",
                "red_team_gate": "not_applicable",
                "endpoint_references": ["/metrics/usage", "/ops/cost-governance", "/ops/cost-governance-pack"],
                "priority_files": ["pricing_notes.md", "implementation_guide.md"],
                "document_types": ["pricing", "implementation"],
                "evidence_terms": ["cost", "token", "pricing", "latency", "workflow"],
                "min_evidence": 1,
                "cloud_only": False,
            },
            {
                "risk_id": "model_risk_06_human_approval",
                "title": "AI draft submitted without required human approval",
                "risk_category": "human_approval",
                "severity": "critical",
                "likelihood": "low",
                "reviewer_owner": "Proposal Manager",
                "description": (
                    "Generated responses and exceptions must remain drafts until accountable reviewers approve "
                    "claims, redlines, and caveats."
                ),
                "mitigation_controls": ["reviewer collaboration", "submission decision", "exception register"],
                "eval_gate": "submission_decision_required",
                "red_team_gate": "red_team_blockers_must_be_closed",
                "endpoint_references": [
                    "/rfp/reviewer-collaboration",
                    "/rfp/submission-decision",
                    "/rfp/exception-register",
                ],
                "priority_files": ["ai_governance_security.md", "compliance_policy.md"],
                "document_types": ["security", "compliance"],
                "evidence_terms": ["human reviewers", "approval", "reviewer", "drafts", "signoff"],
                "min_evidence": 1,
                "cloud_only": False,
                "required_actions": ["Record reviewer status before executive submission memo generation."],
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/governance/model-risk-register" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/governance/model-risk-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            (
                'rg "governance/model-risk|Model Risk Register|model_risk" '
                "app dashboard docs README.md tests Makefile"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            (
                "This is a deterministic local model-risk register, not a substitute for a production model "
                "risk management program."
            ),
            (
                "Evidence is mapped from the ingested sample corpus; production use should add tenant, "
                "data-classification, and approval records."
            ),
            (
                "Release gates reference local verification commands and do not call external GRC, ticketing, "
                "or approval systems."
            ),
            "OpenAI and Azure OpenAI remain optional provider paths; mock mode is the default local verification path.",
        ]

    def _md(self, value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
