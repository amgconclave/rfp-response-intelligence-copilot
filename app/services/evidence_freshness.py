from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, date, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    EvidenceFreshnessPackResponse,
    EvidenceFreshnessResponse,
    EvidenceFreshnessSource,
)
from app.repositories.memory import InMemoryRepository


class EvidenceFreshnessService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def freshness_report(self, trace_id: str) -> EvidenceFreshnessResponse:
        today = datetime.now(UTC).date()
        sources = [
            self._source_freshness(document, today)
            for document in sorted(
                self.repo.documents.values(),
                key=lambda item: (item.document_type, item.filename),
            )
            if document.document_type != "rfp"
        ]
        return EvidenceFreshnessResponse(
            title="Evidence Freshness + Expiry Risk",
            generated_at=datetime.now(UTC).isoformat(),
            sources=sources,
            summary=self._summary(sources),
            unsupported_claims=self._unsupported_claims(sources),
            renewal_calendar=self._renewal_calendar(sources),
            owner_followups=self._owner_followups(sources),
            endpoint_references=self._endpoint_references(sources),
            local_proof_commands=self._local_proof_commands(),
            limitations=self._limitations(),
            trace_id=trace_id,
        )

    def freshness_pack(
        self,
        trace_id: str,
        freshness: EvidenceFreshnessResponse,
        write_artifact: bool = True,
    ) -> EvidenceFreshnessPackResponse:
        pack = self._pack_payload(trace_id, freshness)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            pack_dir = self.settings.storage_dir / "freshness_packs"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"evidence_freshness_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"evidence_freshness_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["freshness_pack_markdown"] = artifact_path
            pack["artifact_paths"]["freshness_pack_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
        return EvidenceFreshnessPackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            freshness=freshness,
            trace_id=trace_id,
        )

    def _source_freshness(self, document: Any, today: date) -> EvidenceFreshnessSource:
        text = self._document_text(document.id)
        catalog = self._catalog().get(document.filename, {})
        policy_owner = self._first_string(
            document.metadata.get("policy_owner"),
            self._metadata_match(text, "Policy owner"),
            catalog.get("policy_owner"),
            self._owner_for_type(document.document_type),
        )
        effective = self._parse_date(
            self._first_string(
                document.metadata.get("effective_date"),
                self._metadata_match(text, "Effective date"),
                catalog.get("effective_date"),
            )
        )
        renewal = self._parse_date(
            self._first_string(
                document.metadata.get("renewal_date"),
                self._metadata_match(text, "Renewal date"),
                catalog.get("renewal_date"),
            )
        )
        age_days = (today - effective).days if effective else None
        days_until_renewal = (renewal - today).days if renewal else None
        flags = self._unsupported_flags(document.filename, text)
        citation_count = self._citation_count(document.filename, text)
        endpoints = self._endpoints_for(document.document_type, document.filename)
        score, status, level, drivers = self._score(
            age_days=age_days,
            days_until_renewal=days_until_renewal,
            policy_owner=policy_owner,
            unsupported_flags=flags,
            citation_count=citation_count,
        )
        chunks = [chunk for chunk in self.repo.chunks.values() if chunk.document_id == document.id]
        return EvidenceFreshnessSource(
            document_id=document.id,
            filename=document.filename,
            document_type=document.document_type,
            policy_owner=policy_owner,
            effective_date=effective.isoformat() if effective else None,
            renewal_date=renewal.isoformat() if renewal else None,
            age_days=age_days,
            days_until_renewal=days_until_renewal,
            expiry_status=status,
            freshness_score=score,
            risk_level=level,
            risk_drivers=drivers,
            unsupported_claim_flags=flags,
            endpoint_references=endpoints,
            citation_use_count=citation_count,
            chunk_count=len(chunks),
            source_path=document.metadata.get("path"),
        )

    def _score(
        self,
        age_days: int | None,
        days_until_renewal: int | None,
        policy_owner: str,
        unsupported_flags: list[str],
        citation_count: int,
    ) -> tuple[int, str, str, list[str]]:
        risk = 0
        drivers: list[str] = []
        if age_days is None:
            risk += 15
            drivers.append("Missing effective date metadata.")
        elif age_days > 365:
            risk += 25
            drivers.append("Evidence is more than 365 days old.")
        elif age_days > 180:
            risk += 15
            drivers.append("Evidence is more than 180 days old.")
        elif age_days > 90:
            risk += 7
            drivers.append("Evidence is more than 90 days old.")

        if days_until_renewal is None:
            expiry_status = "missing_renewal"
            risk += 20
            drivers.append("Missing renewal date metadata.")
        elif days_until_renewal < 0:
            expiry_status = "expired"
            risk += 35
            drivers.append("Renewal date has passed.")
        elif days_until_renewal <= 30:
            expiry_status = "renewal_due"
            risk += 25
            drivers.append("Renewal due within 30 days.")
        elif days_until_renewal <= 60:
            expiry_status = "renewal_watch"
            risk += 15
            drivers.append("Renewal due within 60 days.")
        else:
            expiry_status = "current"

        if not policy_owner or policy_owner == "unassigned":
            risk += 10
            drivers.append("Policy owner is unassigned.")
        if unsupported_flags:
            risk += min(24, len(unsupported_flags) * 8)
            drivers.append("Unsupported or absolute claim language needs reviewer approval.")
        if citation_count == 0:
            risk += 5
            drivers.append("No endpoint citation use was detected for this source.")

        score = max(0, min(100, 100 - risk))
        if risk >= 70:
            level = "critical"
        elif risk >= 50:
            level = "high"
        elif risk >= 25:
            level = "medium"
        else:
            level = "low"
        return score, expiry_status, level, drivers

    def _summary(self, sources: list[EvidenceFreshnessSource]) -> dict[str, Any]:
        risk_counts = Counter(source.risk_level for source in sources)
        status_counts = Counter(source.expiry_status for source in sources)
        owner_counts = Counter(source.policy_owner for source in sources)
        unsupported_count = sum(len(source.unsupported_claim_flags) for source in sources)
        average_score = round(sum(source.freshness_score for source in sources) / len(sources), 2) if sources else 0
        return {
            "source_count": len(sources),
            "average_freshness_score": average_score,
            "expired_count": status_counts.get("expired", 0),
            "renewal_due_count": status_counts.get("renewal_due", 0) + status_counts.get("renewal_watch", 0),
            "missing_renewal_count": status_counts.get("missing_renewal", 0),
            "unsupported_claim_count": unsupported_count,
            "high_or_critical_risk_count": sum(
                count for level, count in risk_counts.items() if level in {"high", "critical"}
            ),
            "risk_counts": dict(sorted(risk_counts.items())),
            "expiry_status_counts": dict(sorted(status_counts.items())),
            "owner_counts": dict(sorted(owner_counts.items())),
            "endpoint_count": len({endpoint for source in sources for endpoint in source.endpoint_references}),
        }

    def _unsupported_claims(self, sources: list[EvidenceFreshnessSource]) -> list[dict[str, Any]]:
        return [
            {
                "filename": source.filename,
                "owner": source.policy_owner,
                "risk_level": source.risk_level,
                "claim": flag,
                "recommended_action": "Renew the source, qualify the language, or route explicit owner approval.",
            }
            for source in sources
            for flag in source.unsupported_claim_flags
        ]

    def _renewal_calendar(self, sources: list[EvidenceFreshnessSource]) -> list[dict[str, Any]]:
        dated = [
            source
            for source in sources
            if source.renewal_date is not None
        ]
        return [
            {
                "filename": source.filename,
                "policy_owner": source.policy_owner,
                "renewal_date": source.renewal_date,
                "days_until_renewal": source.days_until_renewal,
                "expiry_status": source.expiry_status,
                "risk_level": source.risk_level,
            }
            for source in sorted(
                dated,
                key=lambda item: item.days_until_renewal if item.days_until_renewal is not None else 99999,
            )
        ]

    def _owner_followups(self, sources: list[EvidenceFreshnessSource]) -> list[dict[str, Any]]:
        followups = []
        for source in sources:
            if source.risk_level == "low" and source.expiry_status == "current" and not source.unsupported_claim_flags:
                continue
            followups.append(
                {
                    "owner": source.policy_owner,
                    "filename": source.filename,
                    "risk_level": source.risk_level,
                    "expiry_status": source.expiry_status,
                    "action": self._owner_action(source),
                    "risk_drivers": source.risk_drivers,
                }
            )
        return followups

    def _endpoint_references(self, sources: list[EvidenceFreshnessSource]) -> list[dict[str, Any]]:
        rows = []
        for source in sources:
            for endpoint in source.endpoint_references:
                rows.append(
                    {
                        "endpoint": endpoint,
                        "filename": source.filename,
                        "policy_owner": source.policy_owner,
                        "freshness_score": source.freshness_score,
                        "risk_level": source.risk_level,
                    }
                )
        return sorted(rows, key=lambda item: (item["endpoint"], item["filename"]))

    def _pack_payload(self, trace_id: str, freshness: EvidenceFreshnessResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "Evidence Freshness + Expiry Risk Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": freshness.summary,
            "sources": [source.model_dump(mode="json") for source in freshness.sources],
            "renewal_calendar": freshness.renewal_calendar,
            "unsupported_claims": freshness.unsupported_claims,
            "owner_followups": freshness.owner_followups,
            "endpoint_references": freshness.endpoint_references,
            "local_proof_commands": freshness.local_proof_commands,
            "limitations": freshness.limitations,
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        summary = pack["summary"]
        lines = [
            "# Evidence Freshness + Expiry Risk Pack",
            "",
            "## Summary",
            "",
            f"- Sources scored: {summary['source_count']}",
            f"- Average freshness score: {summary['average_freshness_score']}",
            f"- Expired sources: {summary['expired_count']}",
            f"- Renewal due/watch sources: {summary['renewal_due_count']}",
            f"- Unsupported claim flags: {summary['unsupported_claim_count']}",
            f"- High or critical risk sources: {summary['high_or_critical_risk_count']}",
            "",
            "## Source Freshness Matrix",
            "",
            "| Source | Type | Owner | Effective | Renewal | Status | Score | Risk | Flags | Endpoints |",
            "| --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- |",
        ]
        for source in pack["sources"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._md(source["filename"]),
                        self._md(source["document_type"]),
                        self._md(source["policy_owner"]),
                        self._md(source["effective_date"] or "missing"),
                        self._md(source["renewal_date"] or "missing"),
                        self._md(source["expiry_status"]),
                        self._md(source["freshness_score"]),
                        self._md(source["risk_level"]),
                        self._md("; ".join(source["unsupported_claim_flags"]) or "None"),
                        self._md(", ".join(source["endpoint_references"]) or "None"),
                    ]
                )
                + " |"
            )
        lines.extend(["", "## Renewal Calendar", ""])
        if pack["renewal_calendar"]:
            lines.append("| Source | Owner | Renewal | Days | Status | Risk |")
            lines.append("| --- | --- | --- | ---: | --- | --- |")
            for item in pack["renewal_calendar"]:
                lines.append(
                    f"| {self._md(item['filename'])} | {self._md(item['policy_owner'])} | "
                    f"{self._md(item['renewal_date'])} | {self._md(item['days_until_renewal'])} | "
                    f"{self._md(item['expiry_status'])} | {self._md(item['risk_level'])} |"
                )
        else:
            lines.append("- No renewal dates found.")
        lines.extend(["", "## Unsupported Claims", ""])
        if pack["unsupported_claims"]:
            lines.extend(
                f"- {claim['filename']} / {claim['owner']}: {claim['claim']} Action: {claim['recommended_action']}"
                for claim in pack["unsupported_claims"]
            )
        else:
            lines.append("- None")
        lines.extend(["", "## Owner Follow-ups", ""])
        if pack["owner_followups"]:
            for item in pack["owner_followups"]:
                lines.append(
                    f"- {item['owner']} owns {item['filename']} ({item['risk_level']}, "
                    f"{item['expiry_status']}): {item['action']}"
                )
        else:
            lines.append("- None")
        lines.extend(["", "## Endpoint References", ""])
        for item in pack["endpoint_references"]:
            lines.append(
                f"- {item['endpoint']}: {item['filename']} "
                f"({item['risk_level']}, score {item['freshness_score']})"
            )
        lines.extend(["", "## Local Proof Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_proof_commands"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## Freshness Pack Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _document_text(self, document_id: str) -> str:
        chunks = [chunk.text for chunk in self.repo.chunks.values() if chunk.document_id == document_id]
        return "\n\n".join(chunks)

    def _metadata_match(self, text: str, label: str) -> str | None:
        pattern = rf"(?im)^\s*(?:{re.escape(label)}|{label.lower().replace(' ', '_')})\s*:\s*(.+?)\s*$"
        match = re.search(pattern, text)
        return match.group(1).strip() if match else None

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        for candidate in re.findall(r"\d{4}-\d{2}-\d{2}", value):
            try:
                return date.fromisoformat(candidate)
            except ValueError:
                continue
        return None

    def _first_string(self, *values: object) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "unassigned"

    def _unsupported_flags(self, filename: str, text: str) -> list[str]:
        lowered = text.lower()
        checks = [
            (
                ("99.99", "zero data loss", "active-active"),
                "Disaster recovery language includes absolute uptime, failover, or zero-data-loss terms.",
            ),
            (
                ("uptime guarantee", "contractual uptime"),
                "Availability language requires order-form qualification before customer use.",
            ),
            (
                ("soc 2 type ii",),
                "SOC 2 Type II claim requires an actual report or auditor evidence before reuse.",
            ),
            (
                ("customer-managed key", "customer managed key"),
                "Customer-managed key commitments need explicit key-management evidence.",
            ),
            (
                ("only in the united states", "eu-only", "no cross-border"),
                "Data residency exclusivity claims need customer-specific hosting proof.",
            ),
        ]
        flags = [
            message
            for terms, message in checks
            if any(term in lowered for term in terms)
        ]
        if filename == "prior_proposal.md" and "previously proposed" in lowered:
            flags.append("Prior proposal language may be stale and must be revalidated for the current RFP.")
        return list(dict.fromkeys(flags))

    def _citation_count(self, filename: str, text: str) -> int:
        haystack = f"{filename} {text}".lower()
        endpoint_terms = {
            "/rfp/query": ["sso", "encryption", "pricing", "implementation"],
            "/compliance/evidence-matrix": ["soc 2", "gdpr", "dpa", "audit", "disaster", "sla", "subprocessor"],
            "/procurement/question-risk": ["uptime", "subprocessor", "support", "pricing", "audit"],
            "/rfp/contract-risk": ["liability", "data residency", "sla", "contract", "indemnity"],
            "/rfp/win-strategy": ["pricing", "implementation", "support", "security"],
        }
        return sum(1 for terms in endpoint_terms.values() if any(term in haystack for term in terms))

    def _endpoints_for(self, document_type: str, filename: str) -> list[str]:
        by_type = {
            "security": ["/rfp/query", "/compliance/evidence-matrix", "/procurement/question-risk"],
            "compliance": ["/compliance/evidence-matrix", "/procurement/question-risk"],
            "privacy": ["/compliance/evidence-matrix", "/procurement/question-risk", "/rfp/contract-risk"],
            "support": ["/compliance/evidence-matrix", "/procurement/question-risk", "/rfp/contract-risk"],
            "disaster_recovery": ["/compliance/evidence-matrix", "/procurement/question-risk"],
            "pricing": ["/rfp/win-strategy", "/rfp/pricing-risk-memo", "/bid/scenario-analysis"],
            "implementation": ["/rfp/timeline-plan", "/rfp/leadership-brief", "/rfp/query"],
            "customer_success": ["/rfp/timeline-plan", "/rfp/leadership-brief"],
            "product": ["/rfp/query", "/rfp/draft-response", "/rfp/objection-handling"],
            "proposal": ["/rfp/response-memory/search", "/rfp/draft-response"],
            "contract": ["/rfp/contract-risk", "/rfp/negotiation-brief", "/procurement/question-risk"],
        }
        endpoints = by_type.get(document_type, ["/documents", "/rfp/query"])
        catalog_endpoints = self._catalog().get(filename, {}).get("endpoint_references", [])
        return sorted(set(endpoints + list(catalog_endpoints)))

    def _owner_for_type(self, document_type: str) -> str:
        return {
            "security": "security",
            "compliance": "legal",
            "privacy": "legal",
            "support": "customer_success",
            "disaster_recovery": "engineering",
            "pricing": "finance",
            "implementation": "solutions",
            "customer_success": "customer_success",
            "product": "product",
            "proposal": "proposal_owner",
            "contract": "legal",
        }.get(document_type, "proposal_owner")

    def _owner_action(self, source: EvidenceFreshnessSource) -> str:
        if source.expiry_status == "expired":
            return "Renew the source before citing it in customer-facing responses."
        if source.expiry_status in {"renewal_due", "renewal_watch"}:
            return "Schedule owner review and refresh policy metadata before submission."
        if source.unsupported_claim_flags:
            return "Approve qualified wording or replace with fresher evidence."
        if source.expiry_status == "missing_renewal":
            return "Add renewal metadata and owner review cadence."
        return "Reviewer signoff only."

    def _local_proof_commands(self) -> list[str]:
        return [
            'curl -X GET "http://127.0.0.1:8000/evidence/freshness" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/evidence/freshness-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            "python -m pytest -q",
            "python -m ruff check .",
            (
                'rg "evidence/freshness|freshness_packs|Evidence Freshness|expiry risk|renewal" '
                "app dashboard docs README.md tests sample_data Makefile"
            ),
            (
                "Get-ChildItem -Recurse -File storage\\freshness_packs -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _limitations(self) -> list[str]:
        return [
            "Freshness scoring uses local document metadata, sample catalog dates, and deterministic text scans.",
            "It does not connect to a live GRC, policy management, legal, CRM, or contract repository.",
            "Unsupported-claim flags are conservative and should be resolved by source owners before submission.",
            "Renewal status is based on the local machine date at runtime and should be regenerated for reviews.",
        ]

    def _md(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()

    def _catalog(self) -> dict[str, dict[str, Any]]:
        return {
            "security_policy.md": {
                "policy_owner": "security",
                "effective_date": "2026-01-15",
                "renewal_date": "2026-07-15",
            },
            "compliance_policy.md": {
                "policy_owner": "legal",
                "effective_date": "2025-11-01",
                "renewal_date": "2026-06-30",
            },
            "dpa_privacy_policy.md": {
                "policy_owner": "legal",
                "effective_date": "2025-09-15",
                "renewal_date": "2026-05-31",
            },
            "sla_support_policy.md": {
                "policy_owner": "customer_success",
                "effective_date": "2026-02-01",
                "renewal_date": "2026-08-01",
            },
            "ai_governance_security.md": {
                "policy_owner": "product",
                "effective_date": "2026-03-01",
                "renewal_date": "2026-09-01",
            },
            "disaster_recovery_plan.md": {
                "policy_owner": "engineering",
                "effective_date": "2025-08-01",
                "renewal_date": "2026-04-30",
            },
            "customer_contract_terms.md": {
                "policy_owner": "legal",
                "effective_date": "2025-12-01",
                "renewal_date": "2026-06-15",
            },
            "pricing_notes.md": {
                "policy_owner": "finance",
                "effective_date": "2026-01-01",
                "renewal_date": "2026-07-01",
            },
            "implementation_guide.md": {
                "policy_owner": "solutions",
                "effective_date": "2026-02-15",
                "renewal_date": "2026-08-15",
            },
            "product_overview.md": {
                "policy_owner": "product",
                "effective_date": "2026-04-01",
                "renewal_date": "2026-10-01",
            },
            "prior_proposal.md": {
                "policy_owner": "proposal_owner",
                "effective_date": "2025-06-01",
                "renewal_date": "2026-06-01",
            },
            "customer_success_onboarding.md": {
                "policy_owner": "customer_success",
                "effective_date": "2026-01-20",
                "renewal_date": "2026-07-20",
            },
        }
