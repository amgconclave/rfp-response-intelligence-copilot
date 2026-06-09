from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    ComplianceEvidenceSource,
    PrivacyGuardrailSurface,
    PrivacyRetentionGuardrailResponse,
    PrivacyRetentionPackResponse,
)
from app.repositories.memory import InMemoryRepository
from app.vectorstores.embedding import tokenize


class PrivacyRetentionGuardrailService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def guardrails(self, trace_id: str) -> PrivacyRetentionGuardrailResponse:
        surfaces = [self._surface(spec) for spec in self._surface_specs()]
        risk_counts = Counter(surface.risk_level for surface in surfaces)
        missing_control_count = sum(len(surface.missing_controls) for surface in surfaces)
        retention_actions = self._retention_actions(surfaces)
        summary = {
            "surface_count": len(surfaces),
            "high_risk_surface_count": risk_counts.get("high", 0),
            "medium_risk_surface_count": risk_counts.get("medium", 0),
            "low_risk_surface_count": risk_counts.get("low", 0),
            "missing_control_count": missing_control_count,
            "retention_action_count": len(retention_actions),
            "policy_source_count": len({source.filename for surface in surfaces for source in surface.policy_evidence}),
            "external_provider_optional": self.settings.provider_mode == "mock",
        }
        return PrivacyRetentionGuardrailResponse(
            title="Privacy + Retention Guardrail Matrix",
            generated_at=datetime.now(UTC).isoformat(),
            surfaces=surfaces,
            summary=summary,
            retention_actions=retention_actions,
            prompt_logging_guidance=self._prompt_logging_guidance(surfaces),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def retention_pack(
        self,
        trace_id: str,
        guardrails: PrivacyRetentionGuardrailResponse,
        write_artifact: bool = True,
    ) -> PrivacyRetentionPackResponse:
        pack = self._pack_payload(trace_id, guardrails)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "privacy_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"privacy_retention_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"privacy_retention_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["privacy_retention_markdown"] = artifact_path
            pack["artifact_paths"]["privacy_retention_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return PrivacyRetentionPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            guardrails=guardrails,
            trace_id=trace_id,
        )

    def _surface(self, spec: dict[str, Any]) -> PrivacyGuardrailSurface:
        evidence = self._policy_evidence(spec)
        evidence_text = " ".join(
            f"{source.filename} {source.snippet} {' '.join(source.matched_terms)}"
            for source in evidence
        ).lower()
        missing_controls = [
            control
            for control in spec["required_controls"]
            if not any(term in evidence_text for term in self._control_terms(control))
        ]
        risk_score = self._risk_score(spec, evidence, missing_controls)
        risk_level = "high" if risk_score >= 70 else "medium" if risk_score >= 40 else "low"
        return PrivacyGuardrailSurface(
            surface_id=spec["surface_id"],
            surface_name=spec["surface_name"],
            data_categories=spec["data_categories"],
            policy_evidence=evidence,
            risk_level=risk_level,
            risk_score=risk_score,
            retention_posture=self._retention_posture(spec, evidence, missing_controls),
            reviewer_owner=spec["reviewer_owner"],
            required_controls=spec["required_controls"],
            missing_controls=missing_controls,
            redaction_rules=spec["redaction_rules"],
            endpoint_references=spec["endpoint_references"],
        )

    def _policy_evidence(self, spec: dict[str, Any]) -> list[ComplianceEvidenceSource]:
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
            score = min(1.0, 0.3 + 0.1 * len(matched_terms) + (0.18 if filename_match else 0.08 if type_match else 0))
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

    def _snippet(self, text: str, matched_terms: list[str], limit: int = 320) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", compact) if sentence.strip()]
        term_set = set(tokenize(" ".join(matched_terms)))
        best = max(
            sentences,
            key=lambda sentence: len(term_set.intersection(tokenize(sentence))),
            default=compact,
        )
        return best[:limit].strip() + ("..." if len(best) > limit else "")

    def _risk_score(
        self,
        spec: dict[str, Any],
        evidence: list[ComplianceEvidenceSource],
        missing_controls: list[str],
    ) -> int:
        score = spec["base_risk"] + 12 * len(missing_controls)
        if not evidence:
            score += 18
        if self.settings.provider_mode != "mock" and spec["surface_id"] in {"provider_prompts", "prompt_logs"}:
            score += 12
        return max(0, min(100, score))

    def _retention_posture(
        self,
        spec: dict[str, Any],
        evidence: list[ComplianceEvidenceSource],
        missing_controls: list[str],
    ) -> str:
        if "retention window" in missing_controls:
            return "Define explicit retention window before production use."
        if not evidence:
            return "Blocked until local DPA/privacy evidence is ingested."
        if spec["surface_id"] == "provider_prompts" and self.settings.provider_mode == "mock":
            return "Local mock mode keeps provider prompt data on the workstation."
        return spec["retention_posture"]

    def _retention_actions(self, surfaces: list[PrivacyGuardrailSurface]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for surface in surfaces:
            if surface.risk_level == "high" or surface.missing_controls:
                actions.append(
                    {
                        "surface_id": surface.surface_id,
                        "owner": surface.reviewer_owner,
                        "priority": "high" if surface.risk_level == "high" else "medium",
                        "action": f"Close privacy controls for {surface.surface_name}.",
                        "missing_controls": surface.missing_controls,
                        "retention_posture": surface.retention_posture,
                    }
                )
        return actions

    def _prompt_logging_guidance(self, surfaces: list[PrivacyGuardrailSurface]) -> list[str]:
        provider = next(surface for surface in surfaces if surface.surface_id == "provider_prompts")
        logs = next(surface for surface in surfaces if surface.surface_id == "prompt_logs")
        return [
            "Do not put unnecessary personal data, business emails, or customer-specific secrets into prompts.",
            "Keep local/mock provider mode as the default verification path; cloud provider routing remains optional.",
            f"Provider prompt surface risk is {provider.risk_level}; {provider.retention_posture}",
            f"Prompt/log audit surface risk is {logs.risk_level}; {logs.retention_posture}",
            "Generated artifacts are local proof outputs and should remain ignored by git until manually reviewed.",
        ]

    def _pack_payload(
        self,
        trace_id: str,
        guardrails: PrivacyRetentionGuardrailResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Privacy Retention Guardrail Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": guardrails.summary,
            "surfaces": [surface.model_dump(mode="json") for surface in guardrails.surfaces],
            "retention_actions": guardrails.retention_actions,
            "prompt_logging_guidance": guardrails.prompt_logging_guidance,
            "local_proof_commands": guardrails.local_proof_commands,
            "limitations": guardrails.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Privacy Retention Guardrail Pack",
            "",
            "## Summary",
            "",
            f"- Surfaces: {summary['surface_count']}",
            f"- High risk surfaces: {summary['high_risk_surface_count']}",
            f"- Missing controls: {summary['missing_control_count']}",
            f"- Retention actions: {summary['retention_action_count']}",
            f"- Policy sources: {summary['policy_source_count']}",
            "",
            "## Surface Matrix",
            "",
            "| Surface | Risk | Score | Owner | Retention posture | Missing controls |",
            "| --- | --- | ---: | --- | --- | --- |",
        ]
        for surface in pack["surfaces"]:
            lines.append(
                "| {surface} | {risk} | {score} | {owner} | {posture} | {missing} |".format(
                    surface=self._md(surface["surface_name"]),
                    risk=surface["risk_level"],
                    score=surface["risk_score"],
                    owner=self._md(surface["reviewer_owner"]),
                    posture=self._md(surface["retention_posture"]),
                    missing=self._md(", ".join(surface["missing_controls"]) or "none"),
                )
            )
        lines.extend(["", "## Policy Evidence", ""])
        for surface in pack["surfaces"]:
            lines.append(f"### {surface['surface_name']}")
            if not surface["policy_evidence"]:
                lines.append("- No local policy evidence mapped.")
            for source in surface["policy_evidence"]:
                lines.append(
                    f"- `{source['filename']}` ({source['score']}): {self._md(source['snippet'])}"
                )
            lines.append("")
        lines.extend(["## Retention Actions", ""])
        for action in pack["retention_actions"]:
            lines.append(
                f"- {action['priority']}: {action['owner']} - {action['action']} "
                f"({', '.join(action['missing_controls']) or action['retention_posture']})"
            )
        lines.extend(["", "## Prompt And Logging Guidance", ""])
        for item in pack["prompt_logging_guidance"]:
            lines.append(f"- {self._md(item)}")
        lines.extend(["", "## Local Proof Commands", ""])
        for command in pack["local_proof_commands"]:
            lines.append(f"```powershell\n{command}\n```")
        lines.extend(["", "## Limitations", ""])
        for item in pack["limitations"]:
            lines.append(f"- {self._md(item)}")
        return "\n".join(lines).strip() + "\n"

    def _control_terms(self, control: str) -> list[str]:
        return {
            "data minimization": ["unnecessary personal data", "not store unnecessary", "data processing"],
            "retention window": ["retention", "retention windows", "retention policy"],
            "deletion workflow": ["deletion", "delete", "deletion procedures"],
            "access review": ["api-key", "access reviews", "least-privilege", "role-based"],
            "source tagging": ["source tagging", "source documents", "source tagging"],
            "provider choice": ["provider choices", "provider mode", "azure openai", "model provider"],
            "human approval": ["human reviewers", "reviewer signoff", "approval"],
            "git ignore": ["ignored by git", "generated artifact directories ignored"],
        }.get(control, [control])

    def _surface_specs(self) -> list[dict[str, Any]]:
        common_terms = [
            "personal data",
            "retention",
            "deletion",
            "privacy",
            "data processing",
            "api-key",
            "provider",
            "source tagging",
            "audit",
            "generated artifact",
            "unnecessary personal data",
        ]
        return [
            {
                "surface_id": "provider_prompts",
                "surface_name": "Provider prompts and completions",
                "data_categories": ["RFP text", "customer metadata", "business contact data"],
                "base_risk": 42,
                "reviewer_owner": "Legal Privacy Reviewer",
                "required_controls": ["data minimization", "provider choice", "human approval"],
                "redaction_rules": ["Remove work emails and personal names unless required for the RFP answer."],
                "retention_posture": (
                    "Cloud provider use requires documented provider choice and customer order-form terms."
                ),
                "endpoint_references": ["/rfp/query", "/rfp/draft-response", "/rfp/evaluate"],
                "priority_files": ["dpa_privacy_policy.md", "compliance_policy.md", "ai_governance_security.md"],
                "document_types": ["privacy", "compliance", "security"],
                "evidence_terms": common_terms + ["model provider", "human reviewers"],
            },
            {
                "surface_id": "prompt_logs",
                "surface_name": "Audit events, metrics, and prompt logs",
                "data_categories": ["trace IDs", "usage metrics", "approval actions"],
                "base_risk": 36,
                "reviewer_owner": "Security Architect",
                "required_controls": ["data minimization", "retention window", "access review"],
                "redaction_rules": ["Never log secrets, full contract terms, or unsupported customer commitments."],
                "retention_posture": (
                    "Keep trace and audit logs local for the demo; define production retention windows."
                ),
                "endpoint_references": ["/audit/events", "/metrics/usage", "/ops/audit-pack"],
                "priority_files": ["compliance_policy.md", "implementation_guide.md"],
                "document_types": ["compliance", "knowledge_base"],
                "evidence_terms": common_terms + ["audit events", "access reviews"],
            },
            {
                "surface_id": "vector_metadata",
                "surface_name": "Vector chunks and source metadata",
                "data_categories": ["source snippets", "document metadata", "customer packet content"],
                "base_risk": 34,
                "reviewer_owner": "Data Platform Owner",
                "required_controls": ["source tagging", "retention window", "deletion workflow"],
                "redaction_rules": [
                    "Tag source type and avoid embedding unnecessary personal data in metadata fields."
                ],
                "retention_posture": (
                    "Local vector state follows the configured storage directory and deletion procedure."
                ),
                "endpoint_references": ["/documents/ingest", "/documents", "/rag/corpus-coverage"],
                "priority_files": ["dpa_privacy_policy.md", "compliance_policy.md"],
                "document_types": ["privacy", "compliance"],
                "evidence_terms": common_terms + ["vector metadata", "source documents"],
            },
            {
                "surface_id": "generated_artifacts",
                "surface_name": "Generated response and reviewer artifacts",
                "data_categories": ["draft answers", "review comments", "approval notes", "risk packs"],
                "base_risk": 31,
                "reviewer_owner": "Proposal Operations",
                "required_controls": ["git ignore", "human approval", "deletion workflow"],
                "redaction_rules": ["Review generated Markdown/JSON artifacts before sharing or committing."],
                "retention_posture": "Artifacts are written under local storage and ignored by git for manual review.",
                "endpoint_references": [
                    "/rfp/export-package",
                    "/rfp/reviewer-collaboration-pack",
                    "/artifacts/inventory",
                ],
                "priority_files": ["dpa_privacy_policy.md", "ai_governance_security.md"],
                "document_types": ["privacy", "security"],
                "evidence_terms": common_terms + ["generated artifact directories ignored", "reviewer signoff"],
            },
            {
                "surface_id": "eval_datasets",
                "surface_name": "Evaluation and red-team datasets",
                "data_categories": ["eval questions", "expected evidence", "missing-evidence probes"],
                "base_risk": 26,
                "reviewer_owner": "AI Governance Reviewer",
                "required_controls": ["data minimization", "human approval", "source tagging"],
                "redaction_rules": ["Use synthetic/local eval rows unless production customer data is approved."],
                "retention_posture": "Sample eval datasets stay local and synthetic by default.",
                "endpoint_references": ["/rfp/evaluate", "/rag/eval-coverage-pack"],
                "priority_files": ["ai_governance_security.md", "compliance_policy.md"],
                "document_types": ["security", "compliance"],
                "evidence_terms": common_terms + ["evaluation datasets", "human reviewers"],
            },
            {
                "surface_id": "document_uploads",
                "surface_name": "Uploaded RFP packets and source documents",
                "data_categories": ["uploaded PDFs", "security questionnaires", "contract metadata"],
                "base_risk": 38,
                "reviewer_owner": "Customer Success Lead",
                "required_controls": ["retention window", "deletion workflow", "access review"],
                "redaction_rules": ["Confirm customer permission before uploading real RFP packets."],
                "retention_posture": (
                    "Production deployments should document retention, deletion, and export procedures."
                ),
                "endpoint_references": ["/documents/ingest-upload", "/documents/ingest"],
                "priority_files": ["dpa_privacy_policy.md", "implementation_guide.md"],
                "document_types": ["privacy", "knowledge_base"],
                "evidence_terms": common_terms + ["uploaded", "export procedures"],
            },
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/privacy/retention-guardrails" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/privacy/retention-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "privacy/retention-guardrails|privacy/retention-pack|Privacy Retention|'
                'privacy_packs" app dashboard docs README.md tests Makefile'
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "This is a deterministic local guardrail matrix, not legal advice or a DLP scanner.",
            (
                "The service maps local policy evidence already ingested into memory; "
                "production should add tenant scoping."
            ),
            "Retention actions are recommendations and do not delete files or alter vector indexes automatically.",
            "External provider controls remain optional; mock mode is the default verification path.",
        ]

    def _md(self, value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
