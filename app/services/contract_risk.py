from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings
from app.models.api import ContractRiskClause, ContractRiskResponse, NegotiationBriefResponse
from app.repositories.memory import InMemoryRepository
from app.vectorstores.embedding import tokenize


@dataclass(frozen=True)
class CategoryRule:
    label: str
    terms: tuple[str, ...]
    risky_terms: tuple[str, ...]
    owner: str
    redline: str
    fallback: str
    evidence_query: str


class ContractRiskService:
    CATEGORY_RULES: dict[str, CategoryRule] = {
        "liability": CategoryRule(
            label="Liability",
            terms=("liability", "damages", "consequential", "indirect", "cap"),
            risky_terms=("unlimited liability", "consequential damages", "indirect damages", "liability cap"),
            owner="legal",
            redline=(
                "Cap aggregate liability at fees paid in the prior 12 months and exclude consequential, "
                "punitive, special, and indirect damages except for narrow, mutually agreed carve-outs."
            ),
            fallback="Use a super-cap only for confidentiality, data protection, and IP claims with named limits.",
            evidence_query="security compliance audit traceability controls",
        ),
        "data_processing": CategoryRule(
            label="Data Processing",
            terms=("data processing", "dpa", "personal data", "subprocessor", "gdpr", "retention"),
            risky_terms=("personal data", "subprocessor", "gdpr", "retention", "delete"),
            owner="legal",
            redline=(
                "Tie data-processing duties to the vendor DPA, documented subprocessors, retention policy, "
                "and deletion workflow instead of open-ended customer instructions."
            ),
            fallback="Commit to a DPA and subprocessor review before production rather than bespoke terms in the MSA.",
            evidence_query="GDPR DPA subprocessors retention deletion workflow",
        ),
        "security_obligations": CategoryRule(
            label="Security Obligations",
            terms=("security", "encryption", "sso", "incident", "vulnerability", "penetration"),
            risky_terms=("24 hours", "penetration", "critical vulnerability", "customer security policy"),
            owner="security",
            redline=(
                "Limit security obligations to documented platform controls, mutually agreed incident timelines, "
                "and production-ready policies approved by security."
            ),
            fallback="Offer a security addendum and evidence review call rather than accepting all buyer policies.",
            evidence_query="SSO encryption TLS AES-256 incident response audit events",
        ),
        "sla_service_credits": CategoryRule(
            label="SLA and Service Credits",
            terms=("sla", "uptime", "service credit", "availability", "maintenance"),
            risky_terms=("99.99", "service credits", "uncapped credits", "monthly fees", "downtime"),
            owner="solutions",
            redline=(
                "Align uptime and service credits to the contracted production tier, exclude planned maintenance, "
                "and make credits the sole remedy for availability failures."
            ),
            fallback="Offer enhanced support review or a tiered SLA only after implementation scope is confirmed.",
            evidence_query="implementation support production tier audit usage metrics",
        ),
        "audit_rights": CategoryRule(
            label="Audit Rights",
            terms=("audit", "inspect", "records", "onsite", "questionnaire"),
            risky_terms=("onsite audit", "any time", "inspect", "records", "third party audit"),
            owner="security",
            redline=(
                "Replace broad onsite audit rights with annual evidence packages, SOC 2 reports where available, "
                "and scoped questionnaires under confidentiality."
            ),
            fallback="Permit a mutually scheduled remote review for material security concerns.",
            evidence_query="SOC 2 evidence audit events usage metrics source citations",
        ),
        "termination": CategoryRule(
            label="Termination",
            terms=("terminate", "termination", "convenience", "refund", "wind-down"),
            risky_terms=("for convenience", "immediate termination", "refund", "without cause"),
            owner="legal",
            redline=(
                "Require notice and cure periods for breach, remove unilateral convenience termination after kickoff, "
                "and limit refunds to prepaid unused fees where applicable."
            ),
            fallback="Allow convenience termination at renewal or after a defined pilot period.",
            evidence_query="implementation plan pilot subscription commercial terms",
        ),
        "indemnity": CategoryRule(
            label="Indemnity",
            terms=("indemnify", "indemnity", "defend", "hold harmless", "third-party claim"),
            risky_terms=("hold harmless", "all claims", "defend", "customer data", "regulatory fines"),
            owner="legal",
            redline=(
                "Limit indemnity to third-party IP infringement caused by the platform and customer-owned data breach "
                "claims caused by vendor breach of agreed security obligations."
            ),
            fallback="Use mutual indemnities with control of defense, notice, mitigation, and liability-cap alignment.",
            evidence_query="security controls access reviews data protection compliance",
        ),
        "data_residency": CategoryRule(
            label="Data Residency",
            terms=("data residency", "region", "eu", "united states", "localization", "cross-border"),
            risky_terms=("store only", "no cross-border", "eu only", "data localization", "region"),
            owner="security",
            redline=(
                "Commit only to documented deployment regions and approved subprocessors; require a scoped review "
                "before promising strict localization."
            ),
            fallback="Offer regional deployment planning and data-flow documentation as a pre-production action.",
            evidence_query="data residency model provider choices deployment region subprocessors",
        ),
        "ai_data_use": CategoryRule(
            label="AI and Data Use",
            terms=("ai", "model", "training", "prompt", "customer data", "llm"),
            risky_terms=("train models", "no ai", "customer data", "prompt", "model provider"),
            owner="product",
            redline=(
                "State that customer content is used only to provide the contracted service and is not used to train "
                "foundation models in the local demo without explicit written approval."
            ),
            fallback="Add a human-review and provider-choice appendix for production AI processing.",
            evidence_query="model provider choices prompts logs vector metadata personal data",
        ),
        "pricing_payment": CategoryRule(
            label="Pricing and Payment",
            terms=("payment", "invoice", "pricing", "discount", "most favored", "tax", "net"),
            risky_terms=("net 90", "most favored", "price match", "unlimited users", "withhold payment"),
            owner="finance",
            redline=(
                "Use standard payment terms, remove most-favored-customer and unilateral withholding language, "
                "and route discounts or custom packaging for approval."
            ),
            fallback="Offer a pilot or volume-discount review instead of open-ended price matching.",
            evidence_query="pricing packaging tiers usage assumptions payment discount approval",
        ),
    }

    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def analyze(self, text: str, trace_id: str, customer_profile_id: str | None = None) -> ContractRiskResponse:
        clauses = self._detect_clauses(text)
        risky_clauses = [clause for clause in clauses if clause.risk_score >= 30]
        category_counts = dict(sorted(Counter(clause.category for clause in risky_clauses).items()))
        cited_points = self._dedupe_proof_points(
            point for clause in risky_clauses for point in clause.proof_points
        )[:10]
        warnings = list(
            dict.fromkeys(warning for clause in risky_clauses for warning in clause.missing_evidence)
        )
        score = self._portfolio_score(risky_clauses)
        return ContractRiskResponse(
            risk_score=score,
            status=self._status(score),
            risky_clauses=risky_clauses,
            category_counts=category_counts,
            suggested_redlines=[
                {
                    "clause_id": clause.clause_id,
                    "category": clause.category,
                    "suggested_redline": clause.suggested_redline,
                }
                for clause in risky_clauses
            ],
            fallback_positions=[
                {
                    "clause_id": clause.clause_id,
                    "category": clause.category,
                    "fallback_position": clause.fallback_position,
                }
                for clause in risky_clauses
            ],
            cited_proof_points=cited_points,
            owner_actions=self._owner_actions(risky_clauses),
            assumptions=self._assumptions(customer_profile_id, bool(cited_points)),
            missing_evidence_warnings=warnings,
            trace_id=trace_id,
        )

    def export_negotiation_brief(
        self,
        trace_id: str,
        contract_risk: ContractRiskResponse,
        win_strategy: Any | None = None,
        pricing_memo: Any | None = None,
        write_artifact: bool = True,
    ) -> NegotiationBriefResponse:
        brief = {
            "trace_id": trace_id,
            "contract_risk_summary": {
                "risk_score": contract_risk.risk_score,
                "status": contract_risk.status,
                "category_counts": contract_risk.category_counts,
                "missing_evidence_warnings": contract_risk.missing_evidence_warnings,
            },
            "win_strategy_context": self._win_context(win_strategy),
            "pricing_context": self._pricing_context(pricing_memo, win_strategy),
            "clause_redlines": [clause.model_dump(mode="json") for clause in contract_risk.risky_clauses],
            "owner_actions": contract_risk.owner_actions,
            "cited_proof_points": contract_risk.cited_proof_points,
            "assumptions": contract_risk.assumptions,
            "local_commands": [
                "python -m uvicorn app.main:app --reload",
                "streamlit run dashboard/app.py",
                "python -m app.demo",
                "python -m pytest -q",
                "python -m ruff check .",
                "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
                "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/contract-risk" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" '
                    '-d "{\\"fixture_path\\":\\"sample_data/customer_contract_terms.md\\"}"'
                ),
                (
                    'curl -X POST "http://127.0.0.1:8000/rfp/negotiation-brief" '
                    '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" '
                    '-d "{\\"fixture_path\\":\\"sample_data/customer_contract_terms.md\\"}"'
                ),
            ],
            "jd_skills_demonstrated": [
                "Post-shortlist legal/procurement workflow modeled as deterministic FastAPI services.",
                "Contract clause risk scoring grounded in local product, security, compliance, and pricing evidence.",
                "Typed API contracts, artifact export, dashboard workflow, and focused regression tests.",
                "Negotiation guidance that separates redline, fallback, owner action, and missing-evidence warnings.",
                "Fully local/mock implementation with no external legal system or Azure dependency.",
            ],
            "interviewer_talking_points": [
                "This extends the RFP copilot after shortlist, where legal and procurement risk can slow the deal.",
                "The analyzer does not give legal advice; it routes deterministic risk signals to the right owners.",
                "Every proposed position tries to cite internal proof before suggesting a negotiation posture.",
                "Missing evidence is made explicit so teams avoid accepting unsupported customer obligations.",
                (
                    "The brief is reproducible from local sample data, endpoints, dashboard controls, tests, "
                    "and demo output."
                ),
            ],
        }
        markdown = self._render_brief_markdown(brief)
        artifact_path: str | None = None
        json_artifact_path: str | None = None
        if write_artifact:
            brief_dir = self.settings.storage_dir / "negotiation_briefs"
            brief_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = brief_dir / f"negotiation_brief_{safe_trace_id}.md"
            json_path = brief_dir / f"negotiation_brief_{safe_trace_id}.json"
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(brief, indent=2), encoding="utf-8")
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
        return NegotiationBriefResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            brief=brief,
            trace_id=trace_id,
        )

    def _detect_clauses(self, text: str) -> list[ContractRiskClause]:
        clauses = []
        for index, raw_clause in enumerate(self._split_clauses(text), start=1):
            category, matched_terms, score = self._classify_clause(raw_clause)
            if category is None:
                continue
            rule = self.CATEGORY_RULES[category]
            proof_points = self._proof_points(category, rule.evidence_query)
            missing = []
            if not proof_points:
                missing.append(f"No internal proof point found for {rule.label} clause {index}.")
            title = self._title_for_clause(raw_clause, rule.label)
            clauses.append(
                ContractRiskClause(
                    clause_id=f"clause_{index:02d}_{category}",
                    category=category,
                    title=title,
                    clause_text=self._clip(raw_clause, 700),
                    risk_level=self._clause_level(score),
                    risk_score=min(100, score),
                    detected_terms=matched_terms,
                    rationale=self._rationale(rule, matched_terms, score),
                    suggested_redline=rule.redline,
                    fallback_position=rule.fallback,
                    proof_points=proof_points[:3],
                    missing_evidence=missing,
                )
            )
        return sorted(clauses, key=lambda clause: (-clause.risk_score, clause.category, clause.clause_id))

    def _split_clauses(self, text: str) -> list[str]:
        sections: list[str] = []
        current: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"^(#{1,3}\s+|\d+[\).]\s+|[A-Z][A-Za-z /&-]{3,}:)", stripped) and current:
                sections.append(" ".join(current))
                current = [stripped]
            else:
                current.append(stripped)
        if current:
            sections.append(" ".join(current))
        if len(sections) <= 1:
            sections = [part.strip() for part in re.split(r"(?<=[.;])\s+(?=[A-Z])", text) if part.strip()]
        return [section for section in sections if len(section) >= 30]

    def _classify_clause(self, text: str) -> tuple[str | None, list[str], int]:
        lowered = text.lower()
        best_category: str | None = None
        best_terms: list[str] = []
        best_score = 0
        for category, rule in self.CATEGORY_RULES.items():
            matched = [term for term in (*rule.terms, *rule.risky_terms) if term in lowered]
            if not matched:
                continue
            base = 18 + len(set(matched)) * 7
            base += sum(9 for term in rule.risky_terms if term in lowered)
            base += 12 if any(term in lowered for term in ("unlimited", "uncapped", "sole discretion")) else 0
            base += 8 if any(term in lowered for term in ("shall", "must", "required")) else 0
            if base > best_score:
                best_category = category
                best_terms = list(dict.fromkeys(matched))
                best_score = base
        return best_category, best_terms, min(100, best_score)

    def _proof_points(self, category: str, query: str) -> list[dict[str, Any]]:
        query_tokens = self._signal_tokens(query)
        points = []
        for chunk in self.repo.chunks.values():
            document = self.repo.documents.get(chunk.document_id)
            if not document or document.document_type == "rfp":
                continue
            score = len(query_tokens & self._signal_tokens(chunk.text)) + self._document_weight(document.document_type)
            if score < 3:
                continue
            filename = chunk.metadata.get("filename", document.filename)
            points.append(
                {
                    "category": category,
                    "source": filename,
                    "citations": [filename],
                    "source_snippet": self._clip(chunk.text, 320),
                    "confidence": round(min(0.95, 0.42 + score / 18), 2),
                }
            )
        if not points:
            points.extend(self._fallback_proof_points(category, query_tokens))
        return sorted(points, key=lambda point: (-float(point["confidence"]), point["source"]))[:4]

    def _fallback_proof_points(self, category: str, query_tokens: set[str]) -> list[dict[str, Any]]:
        fallback_files = [
            ("security", self.settings.sample_data_dir / "security_policy.md"),
            ("compliance", self.settings.sample_data_dir / "compliance_policy.md"),
            ("pricing", self.settings.sample_data_dir / "pricing_notes.md"),
            ("product", self.settings.sample_data_dir / "product_overview.md"),
        ]
        points = []
        for document_type, path in fallback_files:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            score = len(query_tokens & self._signal_tokens(text)) + self._document_weight(document_type)
            if score < 4:
                continue
            points.append(
                {
                    "category": category,
                    "source": path.name,
                    "citations": [path.name],
                    "source_snippet": self._clip(text, 320),
                    "confidence": round(min(0.88, 0.38 + score / 20), 2),
                }
            )
        return points

    def _portfolio_score(self, clauses: list[ContractRiskClause]) -> int:
        if not clauses:
            return 12
        top_scores = [clause.risk_score for clause in clauses[:8]]
        avg_top = sum(top_scores) / len(top_scores)
        breadth = min(18, len({clause.category for clause in clauses}) * 3)
        critical = min(18, sum(1 for clause in clauses if clause.risk_level == "critical") * 6)
        missing = min(10, sum(1 for clause in clauses if clause.missing_evidence) * 3)
        return max(0, min(100, int(round(avg_top * 0.72 + breadth + critical + missing))))

    def _owner_actions(self, clauses: list[ContractRiskClause]) -> list[dict[str, Any]]:
        grouped: dict[str, list[str]] = {}
        for clause in clauses:
            owner = self.CATEGORY_RULES[clause.category].owner
            grouped.setdefault(owner, []).append(
                f"Review {clause.clause_id} ({self.CATEGORY_RULES[clause.category].label}) and approve redline."
            )
            if clause.missing_evidence:
                grouped.setdefault(owner, []).append(f"Attach proof or document exception for {clause.clause_id}.")
        if clauses:
            grouped.setdefault("sales", []).append(
                "Align negotiation posture with account strategy before customer call."
            )
        return [
            {"owner": owner, "actions": list(dict.fromkeys(actions))[:5]}
            for owner, actions in sorted(grouped.items())
            if actions
        ]

    def _assumptions(self, customer_profile_id: str | None, has_proof: bool) -> list[str]:
        assumptions = [
            "This is deterministic contract-risk triage, not legal advice.",
            "No external legal system, CRM, procurement platform, or Azure dependency was used.",
            "Risk is scored from local contract language and local product/security/compliance/pricing evidence.",
        ]
        if customer_profile_id:
            assumptions.append(f"Customer context was limited to local profile id: {customer_profile_id}.")
        if has_proof:
            assumptions.append("Cited proof points are limited to local ingested or sample documents.")
        return assumptions

    def _win_context(self, win_strategy: Any | None) -> dict[str, Any] | None:
        if win_strategy is None:
            return None
        return {
            "win_score": win_strategy.win_score,
            "win_level": win_strategy.win_level,
            "recommended_response_posture": win_strategy.recommended_response_posture,
            "red_flags": win_strategy.red_flags[:6],
        }

    def _pricing_context(self, pricing_memo: Any | None, win_strategy: Any | None) -> dict[str, Any] | None:
        if pricing_memo is not None:
            memo = pricing_memo.memo
            return {
                "source": "pricing_memo",
                "win_score": memo.get("win_score"),
                "win_level": memo.get("win_level"),
                "pricing_assumptions": memo.get("pricing_assumptions", []),
                "discount_packaging_risks": memo.get("discount_packaging_risks", []),
            }
        if win_strategy is not None:
            return {
                "source": "win_strategy",
                "pricing_risk": win_strategy.pricing_risk,
            }
        return None

    def _render_brief_markdown(self, brief: dict[str, Any]) -> str:
        summary = brief["contract_risk_summary"]
        lines = [
            "# Contract Redline Risk Analyzer + Negotiation Brief",
            "",
            "## Contract Risk Summary",
            "",
            f"- Risk score: {summary['risk_score']}",
            f"- Status: {summary['status']}",
            f"- Category counts: {summary['category_counts']}",
            "",
            "## Win Strategy and Pricing Context",
            "",
            f"- Win strategy: {brief['win_strategy_context'] or 'Not supplied'}",
            f"- Pricing context: {brief['pricing_context'] or 'Not supplied'}",
            "",
            "## Clause-by-Clause Redlines",
            "",
        ]
        if brief["clause_redlines"]:
            lines.extend(
                [
                    "| Clause | Category | Risk | Suggested redline | Fallback |",
                    "| --- | --- | --- | --- | --- |",
                ]
            )
            for clause in brief["clause_redlines"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            self._md_cell(clause["clause_id"]),
                            self._md_cell(clause["category"]),
                            self._md_cell(f"{clause['risk_level']} ({clause['risk_score']})"),
                            self._md_cell(clause["suggested_redline"]),
                            self._md_cell(clause["fallback_position"]),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("- No risky clauses detected.")
        lines.extend(["", "## Owner Actions", ""])
        for item in brief["owner_actions"] or [{"owner": "legal", "actions": ["No contract risks require action."]}]:
            lines.append(f"- {item['owner']}: {'; '.join(item['actions'])}")
        lines.extend(["", "## Cited Proof Points", ""])
        if brief["cited_proof_points"]:
            lines.extend(["| Source | Category | Snippet |", "| --- | --- | --- |"])
            for point in brief["cited_proof_points"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            self._md_cell(point["source"]),
                            self._md_cell(point["category"]),
                            self._md_cell(point["source_snippet"]),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("- No proof points found.")
        lines.extend(["", "## Missing Evidence Warnings", ""])
        self._append_list(lines, summary["missing_evidence_warnings"])
        lines.extend(["", "## Exact Local Commands", ""])
        lines.extend(f"```bash\n{command}\n```" for command in brief["local_commands"])
        lines.extend(["", "## JD Skills Demonstrated", ""])
        self._append_list(lines, brief["jd_skills_demonstrated"])
        lines.extend(["", "## Five Interviewer Talking Points", ""])
        self._append_list(lines, brief["interviewer_talking_points"])
        return "\n".join(lines).strip() + "\n"

    def _dedupe_proof_points(self, points: Any) -> list[dict[str, Any]]:
        deduped = []
        seen = set()
        for point in points:
            key = (point.get("source"), point.get("source_snippet"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(point)
        return deduped

    def _rationale(self, rule: CategoryRule, matched_terms: list[str], score: int) -> str:
        terms = ", ".join(matched_terms[:5])
        return f"{rule.label} risk detected from terms ({terms}) with directional score {score}."

    def _title_for_clause(self, text: str, fallback: str) -> str:
        cleaned = re.sub(r"^#+\s*", "", text).strip()
        title = cleaned.split(". ")[0].split(":")[0]
        if len(title) > 80:
            return fallback
        return title or fallback

    def _clause_level(self, score: int) -> str:
        if score >= 82:
            return "critical"
        if score >= 64:
            return "high"
        if score >= 42:
            return "medium"
        return "low"

    def _status(self, score: int) -> str:
        if score >= 82:
            return "critical"
        if score >= 64:
            return "high_risk"
        if score >= 40:
            return "needs_legal_review"
        return "standard_review"

    def _document_weight(self, document_type: str) -> int:
        return {"security": 4, "compliance": 4, "pricing": 3, "proposal": 2, "product": 2}.get(document_type, 1)

    def _signal_tokens(self, text: str) -> set[str]:
        stop_words = {"and", "are", "can", "for", "from", "must", "shall", "should", "the", "this", "with"}
        return {token for token in tokenize(text) if len(token) > 2 and token not in stop_words}

    def _clip(self, text: str, limit: int = 360) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    def _append_list(self, lines: list[str], items: list[Any]) -> None:
        if not items:
            lines.append("- None")
            return
        lines.extend(f"- {item}" for item in items)

    def _md_cell(self, value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").strip()
