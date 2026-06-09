# ruff: noqa: E501

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    AnalyzeResponse,
    ComplianceControlMapping,
    ComplianceEvidenceMatrixResponse,
    ComplianceEvidenceSource,
    ComplianceRequirementLink,
    ControlPackResponse,
)
from app.models.domain import RequirementMatrixRow, ReviewFinding
from app.repositories.memory import InMemoryRepository
from app.vectorstores.embedding import tokenize


class ComplianceControlMappingService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def evidence_matrix(
        self,
        trace_id: str,
        analysis: AnalyzeResponse,
        requirement_matrix: list[RequirementMatrixRow],
        review_findings: list[ReviewFinding] | None = None,
    ) -> ComplianceEvidenceMatrixResponse:
        findings = review_findings or []
        mappings = [
            self._mapping(spec, analysis, requirement_matrix, findings)
            for spec in self._control_specs()
        ]
        unsupported_claims = self._unsupported_claims(mappings, findings)
        owner_followups = self._owner_followups(mappings)
        return ComplianceEvidenceMatrixResponse(
            title="Compliance Evidence Matrix + Control Mapping",
            control_mappings=mappings,
            coverage_summary=self._coverage_summary(mappings),
            unsupported_claims=unsupported_claims,
            owner_followups=owner_followups,
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def control_pack(
        self,
        trace_id: str,
        matrix: ComplianceEvidenceMatrixResponse,
        write_artifact: bool = True,
    ) -> ControlPackResponse:
        pack = self._pack_payload(trace_id, matrix)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "compliance_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"control_mapping_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"control_mapping_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["control_pack_markdown"] = artifact_path
            pack["artifact_paths"]["control_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return ControlPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            matrix=matrix,
            trace_id=trace_id,
        )

    def _mapping(
        self,
        spec: dict[str, Any],
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
        findings: list[ReviewFinding],
    ) -> ComplianceControlMapping:
        requirements = self._requirement_links(spec, analysis, matrix)
        source_docs = self._source_docs(spec)
        unsupported = self._claim_flags(spec, source_docs, findings)
        missing = self._missing_warnings(spec, requirements, source_docs, unsupported)
        confidence = self._confidence(spec, requirements, source_docs, unsupported)
        status = self._status(confidence, missing, unsupported)
        return ComplianceControlMapping(
            control_id=spec["control_id"],
            control_family=spec["family"],
            title=spec["title"],
            requirement_links=requirements,
            source_docs=source_docs,
            policy_sources=sorted({source.filename for source in source_docs}),
            confidence=confidence,
            owner=spec["owner"],
            status=status,
            missing_evidence_warnings=missing,
            unsupported_claim_flags=unsupported,
            reviewer_notes=self._reviewer_notes(spec, status, unsupported),
            local_proof_commands=self._family_proof_commands(spec),
        )

    def _requirement_links(
        self,
        spec: dict[str, Any],
        analysis: AnalyzeResponse,
        matrix: list[RequirementMatrixRow],
    ) -> list[ComplianceRequirementLink]:
        rows_by_id = {row.requirement_id: row for row in matrix}
        linked: list[ComplianceRequirementLink] = []
        for requirement in analysis.requirements:
            text = requirement.text.lower()
            if not any(term in text for term in spec["requirement_terms"]):
                continue
            row = rows_by_id.get(requirement.id)
            linked.append(
                ComplianceRequirementLink(
                    requirement_id=requirement.id,
                    requirement_text=requirement.text,
                    category=requirement.category,
                    priority=requirement.priority,
                    matrix_status=row.status if row else None,
                    risk_level=row.risk_level if row else None,
                )
            )
        return linked

    def _source_docs(self, spec: dict[str, Any]) -> list[ComplianceEvidenceSource]:
        source_docs: list[ComplianceEvidenceSource] = []
        for chunk in self.repo.chunks.values():
            document = self.repo.documents.get(chunk.document_id)
            if not document or document.document_type == "rfp":
                continue
            matched_terms = self._matched_terms(spec["evidence_terms"], chunk.text)
            filename_match = document.filename in spec.get("priority_files", [])
            type_match = document.document_type in spec.get("document_types", [])
            if len(matched_terms) < 2 and not (matched_terms and (filename_match or type_match)):
                continue
            score = min(1.0, 0.28 + 0.12 * len(matched_terms) + (0.18 if filename_match else 0))
            source_docs.append(
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
        return sorted(source_docs, key=lambda source: (-source.score, source.filename, source.snippet))[:4]

    def _matched_terms(self, terms: list[str], text: str) -> list[str]:
        lowered = text.lower()
        return [term for term in terms if term.lower() in lowered]

    def _snippet(self, text: str, matched_terms: list[str], limit: int = 360) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", compact) if sentence.strip()]
        term_set = set(tokenize(" ".join(matched_terms)))
        best = max(
            sentences,
            key=lambda sentence: len(term_set.intersection(tokenize(sentence))),
            default=compact,
        )
        return best[:limit].strip() + ("..." if len(best) > limit else "")

    def _claim_flags(
        self,
        spec: dict[str, Any],
        sources: list[ComplianceEvidenceSource],
        findings: list[ReviewFinding],
    ) -> list[str]:
        evidence_text = " ".join(
            f"{source.filename} {source.snippet} {' '.join(source.matched_terms)}"
            for source in sources
        ).lower()
        flags = []
        for claim in spec.get("unsupported_claim_checks", []):
            required_terms = claim["requires_any"]
            if not any(term in evidence_text for term in required_terms):
                flags.append(claim["message"])
        for finding in findings:
            if finding.category == "unsupported_claim" and any(
                term in f"{finding.message} {finding.recommendation}".lower()
                for term in spec["requirement_terms"] + spec["evidence_terms"]
            ):
                flags.append(f"Review board unsupported claim: {finding.message}")
        return self._unique(flags)

    def _missing_warnings(
        self,
        spec: dict[str, Any],
        requirements: list[ComplianceRequirementLink],
        sources: list[ComplianceEvidenceSource],
        unsupported: list[str],
    ) -> list[str]:
        warnings = []
        if not requirements:
            warnings.append("No extracted RFP requirement currently maps to this control family.")
        if not sources:
            warnings.append(f"No approved local evidence snippet found for {spec['family']}.")
        present_files = {source.filename for source in sources}
        missing_priority = [filename for filename in spec.get("priority_files", []) if filename not in present_files]
        if missing_priority:
            warnings.append("Priority evidence not found in mapped snippets: " + ", ".join(missing_priority[:3]))
        if unsupported:
            warnings.append("Unsupported customer-facing claims require exception wording or owner approval.")
        return self._unique(warnings)

    def _confidence(
        self,
        spec: dict[str, Any],
        requirements: list[ComplianceRequirementLink],
        sources: list[ComplianceEvidenceSource],
        unsupported: list[str],
    ) -> float:
        evidence_score = min(0.52, sum(source.score for source in sources[:3]) / 5)
        requirement_score = 0.22 if requirements else 0
        priority_files = set(spec.get("priority_files", []))
        priority_score = 0.18 if priority_files and priority_files.intersection({source.filename for source in sources}) else 0
        penalty = min(0.35, 0.1 * len(unsupported))
        return round(max(0.05, min(0.98, 0.12 + evidence_score + requirement_score + priority_score - penalty)), 2)

    def _status(self, confidence: float, warnings: list[str], unsupported: list[str]) -> str:
        if unsupported:
            return "needs_exception_review"
        if confidence >= 0.72 and not warnings:
            return "mapped"
        if confidence >= 0.55:
            return "needs_review"
        return "gap"

    def _coverage_summary(self, mappings: list[ComplianceControlMapping]) -> dict[str, Any]:
        statuses = Counter(mapping.status for mapping in mappings)
        owners = Counter(mapping.owner for mapping in mappings)
        covered = sum(
            1
            for mapping in mappings
            if mapping.status in {"mapped", "needs_review", "needs_exception_review"}
        )
        unsupported_count = sum(len(mapping.unsupported_claim_flags) for mapping in mappings)
        missing_count = sum(len(mapping.missing_evidence_warnings) for mapping in mappings)
        return {
            "control_family_count": len(mappings),
            "mapped_or_reviewable_count": covered,
            "coverage_ratio": round(covered / len(mappings), 2) if mappings else 0,
            "status_counts": dict(sorted(statuses.items())),
            "owner_counts": dict(sorted(owners.items())),
            "unsupported_claim_count": unsupported_count,
            "missing_evidence_warning_count": missing_count,
            "families": [mapping.control_family for mapping in mappings],
        }

    def _unsupported_claims(
        self,
        mappings: list[ComplianceControlMapping],
        findings: list[ReviewFinding],
    ) -> list[dict[str, Any]]:
        claims = [
            {
                "control_id": mapping.control_id,
                "control_family": mapping.control_family,
                "owner": mapping.owner,
                "claim": claim,
                "recommended_action": "Use qualified language, attach proof, or route an explicit exception.",
            }
            for mapping in mappings
            for claim in mapping.unsupported_claim_flags
        ]
        claims.extend(
            {
                "control_id": None,
                "control_family": "review_board",
                "owner": "proposal_owner",
                "claim": finding.message,
                "recommended_action": finding.recommendation,
            }
            for finding in findings
            if finding.category == "unsupported_claim"
        )
        return claims

    def _owner_followups(self, mappings: list[ComplianceControlMapping]) -> list[dict[str, Any]]:
        followups = []
        for mapping in mappings:
            if mapping.status == "mapped" and not mapping.unsupported_claim_flags:
                continue
            followups.append(
                {
                    "owner": mapping.owner,
                    "control_id": mapping.control_id,
                    "control_family": mapping.control_family,
                    "status": mapping.status,
                    "action": self._owner_action(mapping),
                    "missing_evidence_warnings": mapping.missing_evidence_warnings,
                    "unsupported_claim_flags": mapping.unsupported_claim_flags,
                }
            )
        return followups

    def _owner_action(self, mapping: ComplianceControlMapping) -> str:
        if mapping.unsupported_claim_flags:
            return "Approve exception wording or provide concrete evidence before the claim is used externally."
        if mapping.missing_evidence_warnings:
            return "Attach the missing policy, report, runbook, or reviewer approval to the control pack."
        return "Reviewer signoff only."

    def _pack_payload(
        self,
        trace_id: str,
        matrix: ComplianceEvidenceMatrixResponse,
    ) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Compliance Evidence Matrix + Control Mapping Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "control_coverage": matrix.coverage_summary,
            "control_mappings": [mapping.model_dump(mode="json") for mapping in matrix.control_mappings],
            "unsupported_claims": matrix.unsupported_claims,
            "gaps": [
                {
                    "control_id": mapping.control_id,
                    "control_family": mapping.control_family,
                    "warnings": mapping.missing_evidence_warnings,
                }
                for mapping in matrix.control_mappings
                if mapping.missing_evidence_warnings
            ],
            "owner_actions": matrix.owner_followups,
            "reviewer_notes": [
                note
                for mapping in matrix.control_mappings
                for note in mapping.reviewer_notes
            ],
            "local_proof_commands": matrix.local_proof_commands,
            "limitations": matrix.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        coverage = pack["control_coverage"]
        lines = [
            "# Compliance Evidence Matrix + Control Mapping Pack",
            "",
            "## Control Coverage",
            "",
            f"- Control families: {coverage['control_family_count']}",
            f"- Mapped or reviewable: {coverage['mapped_or_reviewable_count']}",
            f"- Coverage ratio: {coverage['coverage_ratio']}",
            f"- Unsupported claim flags: {coverage['unsupported_claim_count']}",
            f"- Missing-evidence warnings: {coverage['missing_evidence_warning_count']}",
            "",
            "## Control Mapping Matrix",
            "",
            "| Control | Family | Status | Confidence | Owner | Requirements | Sources | Flags |",
            "| --- | --- | --- | ---: | --- | --- | --- | --- |",
        ]
        for mapping in pack["control_mappings"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(mapping["control_id"]),
                        self._md(mapping["control_family"]),
                        self._md(mapping["status"]),
                        self._md(mapping["confidence"]),
                        self._md(mapping["owner"]),
                        self._md(", ".join(link["requirement_id"] for link in mapping["requirement_links"]) or "None"),
                        self._md(", ".join(mapping["policy_sources"]) or "None"),
                        self._md("; ".join(mapping["unsupported_claim_flags"]) or "None"),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Source Snippets", ""])
        for mapping in pack["control_mappings"]:
            lines.extend([f"### {mapping['control_family']}", ""])
            if mapping["source_docs"]:
                for source in mapping["source_docs"]:
                    lines.append(
                        f"- {source['filename']} ({source['document_type']}, score {source['score']}): "
                        f"{source['snippet']}"
                    )
            else:
                lines.append("- No approved local evidence snippet mapped.")
            lines.append("")
        lines.extend(["## Unsupported Claims", ""])
        if pack["unsupported_claims"]:
            lines.extend(
                f"- {claim['control_family']} / {claim['owner']}: {claim['claim']} Action: {claim['recommended_action']}"
                for claim in pack["unsupported_claims"]
            )
        else:
            lines.append("- None")
        lines.extend(["", "## Gaps and Owner Actions", ""])
        if pack["owner_actions"]:
            for action in pack["owner_actions"]:
                lines.extend(
                    [
                        f"### {action['control_id']} - {action['owner']}",
                        "",
                        f"- Status: {action['status']}",
                        f"- Action: {action['action']}",
                    ]
                )
                lines.extend(f"- Warning: {warning}" for warning in action["missing_evidence_warnings"])
                lines.extend(f"- Unsupported: {flag}" for flag in action["unsupported_claim_flags"])
                lines.append("")
        else:
            lines.append("- None")
        lines.extend(["## Reviewer Notes", ""])
        lines.extend(f"- {note}" for note in pack["reviewer_notes"])
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Control Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _reviewer_notes(self, spec: dict[str, Any], status: str, unsupported: list[str]) -> list[str]:
        notes = [
            f"Review {spec['family']} against mapped snippets before copying language into an RFP.",
            f"Owner {spec['owner']} must approve customer-specific commitments.",
        ]
        if status == "gap":
            notes.append("Treat this as a gap until a concrete policy, report, runbook, or exception is attached.")
        if unsupported:
            notes.append("Unsupported-claim flags are intentionally conservative for regulated-enterprise review.")
        return notes

    def _family_proof_commands(self, spec: dict[str, Any]) -> list[str]:
        terms = "|".join([spec["family"], *spec["priority_files"]])
        return [
            f'rg "{terms}" sample_data app docs README.md',
            'curl -X GET "http://127.0.0.1:8000/compliance/evidence-matrix" -H "X-API-Key: local-demo-key"',
        ]

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/compliance/evidence-matrix" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/compliance/control-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            "python scripts\\dashboard_smoke.py",
            (
                'rg "compliance/evidence-matrix|compliance/control-pack|Compliance Evidence|'
                'Control Mapping|compliance_packs|control coverage" '
                "app dashboard docs README.md tests scripts sample_data Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\compliance_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "The matrix is deterministic and local; it is not a substitute for a formal SOC 2, ISO, HIPAA, or GDPR audit.",
            "Mapped evidence is based on local sample documents and ingested chunks, not live GRC, IAM, cloud, or legal systems.",
            "Unsupported-claim flags are conservative and should be resolved with customer-specific evidence or exception language.",
            "Control coverage summarizes source-backed response readiness, not operating effectiveness over time.",
        ]

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    def _unique(self, values: list[str]) -> list[str]:
        return [value for value in dict.fromkeys(values) if value]

    def _control_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "control_id": "AC-SSO-001",
                "family": "access control/SSO",
                "title": "Enterprise identity and protected API access",
                "owner": "security",
                "requirement_terms": ["sso", "saml", "oidc", "user actions"],
                "evidence_terms": ["sso", "saml 2.0", "oidc", "api key", "least-privilege", "reviewer workflows"],
                "priority_files": ["security_policy.md", "ai_governance_security.md"],
                "document_types": ["security"],
                "unsupported_claim_checks": [
                    {
                        "requires_any": ["saml 2.0", "oidc"],
                        "message": "Do not claim enterprise SSO support unless SAML 2.0 or OIDC evidence is attached.",
                    }
                ],
            },
            {
                "control_id": "CRYPTO-KEY-002",
                "family": "encryption/key management",
                "title": "Encryption in transit, at rest, and hosting key boundaries",
                "owner": "security",
                "requirement_terms": ["encrypt", "aes-256", "tls", "key"],
                "evidence_terms": ["tls 1.2", "aes-256", "encrypted", "encryption", "managed encryption controls", "key"],
                "priority_files": ["security_policy.md"],
                "document_types": ["security"],
                "unsupported_claim_checks": [
                    {
                        "requires_any": ["managed encryption controls", "key"],
                        "message": "Customer-managed key commitments need explicit key-management evidence beyond general encryption wording.",
                    }
                ],
            },
            {
                "control_id": "PRIV-DPA-003",
                "family": "privacy/DPA/subprocessors",
                "title": "DPA, processing roles, retention, deletion, subprocessors, and privacy guardrails",
                "owner": "legal",
                "requirement_terms": ["gdpr", "subprocessor", "privacy", "data retention", "delete"],
                "evidence_terms": ["dpa", "data processing", "subprocessors", "retention", "deletion", "personal data", "processor"],
                "priority_files": ["dpa_privacy_policy.md", "compliance_policy.md"],
                "document_types": ["privacy", "compliance"],
                "unsupported_claim_checks": [
                    {
                        "requires_any": ["customer-approved subprocessor list", "subprocessors list", "subprocessors"],
                        "message": "Do not claim a final approved subprocessor list without customer/order-form evidence.",
                    }
                ],
            },
            {
                "control_id": "AUDIT-LOG-004",
                "family": "audit logging",
                "title": "Traceable audit events for generated responses and review decisions",
                "owner": "security",
                "requirement_terms": ["log", "audit", "traceable", "provider choices"],
                "evidence_terms": ["audit events", "trace id", "provider choices", "approval-relevant", "usage metrics"],
                "priority_files": ["security_policy.md", "compliance_policy.md", "ai_governance_security.md"],
                "document_types": ["security", "compliance"],
                "unsupported_claim_checks": [],
            },
            {
                "control_id": "AI-GOV-005",
                "family": "AI governance/model claims",
                "title": "Grounded generation, model provider approval, and human review",
                "owner": "product",
                "requirement_terms": ["unsupported claims", "generated answers", "model", "ai"],
                "evidence_terms": ["ground", "approved source documents", "missing evidence", "model provider", "drafts", "reviewer signoff"],
                "priority_files": ["ai_governance_security.md", "dpa_privacy_policy.md"],
                "document_types": ["security", "privacy"],
                "unsupported_claim_checks": [
                    {
                        "requires_any": ["does not send prompts", "requires configured credentials", "written approval", "never used to train"],
                        "message": "Model no-training or provider-use claims need provider terms, approval, or DPA evidence.",
                    }
                ],
            },
            {
                "control_id": "SLA-SUP-006",
                "family": "SLA/support",
                "title": "Support tiers, response targets, and uptime claim boundaries",
                "owner": "customer_success",
                "requirement_terms": ["sla", "support", "uptime", "availability", "response target"],
                "evidence_terms": ["support tiers", "severity 1", "4 business hours", "availability", "uptime guarantee", "response target"],
                "priority_files": ["sla_support_policy.md"],
                "document_types": ["support"],
                "unsupported_claim_checks": [
                    {
                        "requires_any": ["does not provide a contractual uptime guarantee", "production availability targets"],
                        "message": "Do not claim unconditional uptime or 99.99% availability; local evidence only supports qualified support targets.",
                    }
                ],
            },
            {
                "control_id": "DR-BCP-007",
                "family": "disaster recovery/BCP",
                "title": "RTO/RPO posture, backups, recovery procedure, and DR limitations",
                "owner": "engineering",
                "requirement_terms": ["disaster", "recovery", "bcp", "rto", "rpo", "backup"],
                "evidence_terms": ["rto", "rpo", "backup", "recovery procedure", "tabletop", "zero data loss", "active-active"],
                "priority_files": ["disaster_recovery_plan.md"],
                "document_types": ["disaster_recovery"],
                "unsupported_claim_checks": [
                    {
                        "requires_any": ["does not guarantee zero data loss", "24 hour rto", "4 hour rpo"],
                        "message": "Do not claim zero data loss or active-active failover; the DR plan explicitly limits those claims.",
                    }
                ],
            },
            {
                "control_id": "DATA-RES-008",
                "family": "data residency/export",
                "title": "Data region review, cross-border transfer limits, deletion, and export procedures",
                "owner": "legal",
                "requirement_terms": ["data residency", "export", "region", "cross-border", "localization"],
                "evidence_terms": ["data-region review", "data residency", "export procedures", "cross-border", "united states", "european union"],
                "priority_files": ["dpa_privacy_policy.md", "compliance_policy.md", "customer_contract_terms.md"],
                "document_types": ["privacy", "compliance", "contract"],
                "unsupported_claim_checks": [
                    {
                        "requires_any": ["does not claim", "data-region review", "policy does not claim"],
                        "message": "Do not guarantee EU-only storage or no cross-border transfers without customer-specific hosting proof.",
                    }
                ],
            },
        ]
