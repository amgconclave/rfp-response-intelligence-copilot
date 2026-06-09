from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.models.api import (
    RagCorpusCoverageResponse,
    RagCoverageCheck,
    RagEvalCoveragePackResponse,
)
from app.repositories.memory import InMemoryRepository


class CorpusCoverageService:
    def __init__(self, repo: InMemoryRepository, settings: Settings) -> None:
        self.repo = repo
        self.settings = settings

    def corpus_coverage(self, trace_id: str) -> RagCorpusCoverageResponse:
        docs = self._corpus_docs()
        eval_questions = self._dataset_questions("eval_dataset.json")
        red_team_questions = self._dataset_questions("red_team_questions.json")
        doc_categories = self._doc_category_check(docs)
        eval_coverage = self._eval_coverage_check(eval_questions)
        citation_coverage = self._citation_source_check(docs, eval_questions)
        red_team_coverage = self._red_team_check(red_team_questions)
        missing_coverage = self._missing_evidence_check(eval_questions, red_team_questions)
        checks = [
            doc_categories,
            eval_coverage,
            citation_coverage,
            red_team_coverage,
            missing_coverage,
        ]
        gaps = sorted({gap for check in checks for gap in check.missing})
        warnings = sorted({warning for check in checks for warning in check.warnings})
        failed = [check for check in checks if check.status == "fail"]
        warn = [check for check in checks if check.status == "warn"]
        score = max(0, 100 - 14 * len(failed) - 5 * len(warn) - min(12, len(warnings) * 2))
        status = "pass" if not failed and not warn else ("warn" if not failed else "fail")
        return RagCorpusCoverageResponse(
            title="RAG Corpus Coverage",
            status=status,
            score=score,
            corpus_metadata=self._corpus_metadata(docs),
            doc_category_coverage=doc_categories,
            eval_coverage=eval_coverage,
            citation_source_coverage=citation_coverage,
            red_team_coverage=red_team_coverage,
            missing_evidence_coverage=missing_coverage,
            gaps=gaps,
            warnings=warnings,
            local_commands=self._local_commands(),
            generated_at=datetime.now(UTC).isoformat(),
            trace_id=trace_id,
        )

    def eval_coverage_pack(self, trace_id: str, write_artifact: bool = True) -> RagEvalCoveragePackResponse:
        coverage = self.corpus_coverage(f"{trace_id}-coverage")
        pack = self._pack_payload(trace_id, coverage)
        markdown = self._render_markdown(pack)
        artifact_path: str | None = None
        json_artifact_path: str | None = None

        if write_artifact:
            pack_dir = self.settings.storage_dir / "rag_coverage"
            pack_dir.mkdir(parents=True, exist_ok=True)
            safe_trace_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", trace_id).strip("-") or "local"
            markdown_path = pack_dir / f"rag_eval_coverage_pack_{safe_trace_id}.md"
            json_path = pack_dir / f"rag_eval_coverage_pack_{safe_trace_id}.json"
            artifact_path = str(markdown_path.resolve())
            json_artifact_path = str(json_path.resolve())
            pack["artifact_paths"]["rag_coverage_markdown"] = artifact_path
            pack["artifact_paths"]["rag_coverage_json"] = json_artifact_path
            markdown = self._render_markdown(pack)
            markdown_path.write_text(markdown, encoding="utf-8")
            json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")

        return RagEvalCoveragePackResponse(
            artifact_path=artifact_path,
            json_artifact_path=json_artifact_path,
            markdown=markdown,
            pack=pack,
            coverage=coverage,
            trace_id=trace_id,
        )

    def _corpus_docs(self) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for path in sorted(self.settings.sample_data_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            docs.append(
                {
                    "filename": path.name,
                    "path": str(path.resolve()),
                    "category": self._category(path.name, text),
                    "word_count": len(text.split()),
                    "heading_count": sum(1 for line in text.splitlines() if line.startswith("#")),
                    "required_enterprise_pack_doc": path.name in self._required_pack_files(),
                    "indexed_in_current_repo": any(doc.filename == path.name for doc in self.repo.documents.values()),
                }
            )
        return docs

    def _dataset_questions(self, filename: str) -> list[dict[str, Any]]:
        path = self.settings.sample_data_dir / filename
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("questions", []))

    def _doc_category_check(self, docs: list[dict[str, Any]]) -> RagCoverageCheck:
        category_to_docs: dict[str, list[str]] = {}
        for doc in docs:
            category_to_docs.setdefault(doc["category"], []).append(doc["filename"])
        required = self._required_categories()
        missing = sorted(category for category in required if category not in category_to_docs)
        required_docs = self._required_pack_files()
        doc_names = {doc["filename"] for doc in docs}
        missing_files = sorted(filename for filename in required_docs if filename not in doc_names)
        warnings = []
        if len(docs) < 12:
            warnings.append("Sample corpus has fewer than 12 Markdown source documents.")
        return RagCoverageCheck(
            name="doc category coverage",
            status="pass" if not missing and not missing_files else "fail",
            passed=len(required) - len(missing),
            total=len(required),
            coverage=self._ratio(len(required) - len(missing), len(required)),
            missing=missing + missing_files,
            warnings=warnings,
            details={
                "categories": category_to_docs,
                "required_enterprise_pack_files": sorted(required_docs),
                "document_count": len(docs),
            },
        )

    def _eval_coverage_check(self, questions: list[dict[str, Any]]) -> RagCoverageCheck:
        required_categories = self._required_categories()
        covered = self._categories_from_expected_docs(questions)
        missing = sorted(required_categories - covered)
        missing_expected_docs = [
            item["question"]
            for item in questions
            if not item.get("expected_evidence_documents") and not item.get("expect_missing_evidence")
        ]
        warnings = []
        if len(questions) < 10:
            warnings.append("Eval dataset has fewer than 10 questions.")
        return RagCoverageCheck(
            name="eval coverage",
            status="pass" if not missing and not missing_expected_docs else "warn",
            passed=len(required_categories) - len(missing),
            total=len(required_categories),
            coverage=self._ratio(len(required_categories) - len(missing), len(required_categories)),
            missing=missing,
            warnings=warnings
            + [
                f"Eval question lacks expected docs or missing-evidence flag: {question}"
                for question in missing_expected_docs
            ],
            details={
                "question_count": len(questions),
                "covered_categories": sorted(covered),
                "missing_evidence_eval_cases": sum(1 for item in questions if item.get("expect_missing_evidence")),
            },
        )

    def _citation_source_check(
        self,
        docs: list[dict[str, Any]],
        questions: list[dict[str, Any]],
    ) -> RagCoverageCheck:
        doc_names = {doc["filename"] for doc in docs}
        expected_docs = {
            filename
            for item in questions
            for filename in item.get("expected_evidence_documents", [])
        }
        missing_sources = sorted(expected_docs - doc_names)
        cited_pack_docs = expected_docs.intersection(self._required_pack_files())
        missing_pack_source_coverage = sorted(self._required_pack_files() - cited_pack_docs)
        warnings = [
            f"Required enterprise doc has no eval citation expectation: {filename}"
            for filename in missing_pack_source_coverage
        ]
        total = max(1, len(expected_docs))
        passed = len(expected_docs) - len(missing_sources)
        return RagCoverageCheck(
            name="citation/source coverage",
            status="pass" if not missing_sources and not missing_pack_source_coverage else "warn",
            passed=passed,
            total=total,
            coverage=self._ratio(passed, total),
            missing=missing_sources,
            warnings=warnings,
            details={
                "expected_source_documents": sorted(expected_docs),
                "required_pack_sources_with_eval_expectations": sorted(cited_pack_docs),
                "source_document_count": len(doc_names),
            },
        )

    def _red_team_check(self, questions: list[dict[str, Any]]) -> RagCoverageCheck:
        required_risk_types = {
            "unsupported_claim",
            "out_of_scope",
            "ambiguous_commercial",
            "unsupported_compliance",
            "unsupported_sla_dr_claim",
            "adversarial_ai_governance",
            "unsupported_privacy_subprocessor_claim",
            "grounded_control",
        }
        risk_types = {item.get("risk_type", "unknown") for item in questions}
        missing = sorted(required_risk_types - risk_types)
        warnings = []
        if len(questions) < 8:
            warnings.append("Red-team dataset has fewer than 8 questions.")
        return RagCoverageCheck(
            name="red-team coverage",
            status="pass" if not missing else "warn",
            passed=len(required_risk_types) - len(missing),
            total=len(required_risk_types),
            coverage=self._ratio(len(required_risk_types) - len(missing), len(required_risk_types)),
            missing=missing,
            warnings=warnings,
            details={
                "question_count": len(questions),
                "risk_type_counts": dict(Counter(item.get("risk_type", "unknown") for item in questions)),
                "expected_review_categories": sorted(
                    {
                        category
                        for item in questions
                        for category in item.get("expected_review_categories", [])
                    }
                ),
            },
        )

    def _missing_evidence_check(
        self,
        eval_questions: list[dict[str, Any]],
        red_team_questions: list[dict[str, Any]],
    ) -> RagCoverageCheck:
        eval_missing = [item for item in eval_questions if item.get("expect_missing_evidence")]
        red_missing = [item for item in red_team_questions if item.get("expect_missing_evidence")]
        adversarial = [
            item
            for item in red_missing
            if item.get("risk_type") in {"adversarial_ai_governance", "unsupported_sla_dr_claim"}
        ]
        missing = []
        if len(eval_missing) < 2:
            missing.append("at least two standard eval missing-evidence cases")
        if len(red_missing) < 2:
            missing.append("at least two red-team missing-evidence cases")
        if len(adversarial) < 2:
            missing.append("at least two adversarial red-team missing-evidence cases")
        total = 3
        passed = total - len(missing)
        return RagCoverageCheck(
            name="missing-evidence coverage",
            status="pass" if not missing else "fail",
            passed=passed,
            total=total,
            coverage=self._ratio(passed, total),
            missing=missing,
            details={
                "standard_eval_missing_evidence_cases": len(eval_missing),
                "red_team_missing_evidence_cases": len(red_missing),
                "adversarial_missing_evidence_cases": len(adversarial),
                "missing_evidence_questions": [item["question"] for item in eval_missing + red_missing],
            },
        )

    def _corpus_metadata(self, docs: list[dict[str, Any]]) -> dict[str, Any]:
        categories = Counter(doc["category"] for doc in docs)
        indexed = [doc.filename for doc in self.repo.documents.values()]
        return {
            "sample_data_dir": str(self.settings.sample_data_dir.resolve()),
            "storage_rag_coverage_dir": str((self.settings.storage_dir / "rag_coverage").resolve()),
            "sample_document_count": len(docs),
            "sample_word_count": sum(doc["word_count"] for doc in docs),
            "category_counts": dict(sorted(categories.items())),
            "required_enterprise_pack_doc_count": sum(doc["required_enterprise_pack_doc"] for doc in docs),
            "currently_indexed_document_count": len(indexed),
            "currently_indexed_filenames": sorted(indexed),
            "documents": docs,
        }

    def _pack_payload(self, trace_id: str, coverage: RagCorpusCoverageResponse) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "title": "RAG Eval Coverage Pack",
            "generated_at": datetime.now(UTC).isoformat(),
            "coverage": coverage.model_dump(mode="json"),
            "deterministic_checks": [
                coverage.doc_category_coverage.model_dump(mode="json"),
                coverage.eval_coverage.model_dump(mode="json"),
                coverage.citation_source_coverage.model_dump(mode="json"),
                coverage.red_team_coverage.model_dump(mode="json"),
                coverage.missing_evidence_coverage.model_dump(mode="json"),
            ],
            "reviewer_summary": [
                (
                    "Expanded fake enterprise corpus covers implementation, DPA/privacy, SLA/support, "
                    "AI governance/security, disaster recovery, and customer success/onboarding."
                ),
                "Eval cases require citations from the new corpus and include standard missing-evidence prompts.",
                (
                    "Red-team cases include unsupported commitments, adversarial AI governance, "
                    "privacy subprocessor claims, and grounded controls."
                ),
                "Coverage checks are deterministic source inspections and do not require paid model providers.",
            ],
            "local_commands": self._local_commands(),
            "limitations": [
                (
                    "Coverage checks inspect local files and expected evidence metadata; they do not prove "
                    "semantic answer quality by themselves."
                ),
                "Generated storage/rag_coverage artifacts are ignored by git and should be regenerated locally.",
                (
                    "Sample corpus is fake and compact for portfolio review; production would connect "
                    "real customer source systems."
                ),
            ],
            "artifact_paths": {},
        }

    def _render_markdown(self, pack: dict[str, Any]) -> str:
        coverage = pack["coverage"]
        lines = [
            "# RAG Eval Coverage Pack",
            "",
            "## Corpus Coverage Summary",
            "",
            f"- Status: {coverage['status']}",
            f"- Score: {coverage['score']}",
            f"- Sample documents: {coverage['corpus_metadata']['sample_document_count']}",
            f"- Required enterprise pack docs: {coverage['corpus_metadata']['required_enterprise_pack_doc_count']}",
            f"- Storage: {coverage['corpus_metadata']['storage_rag_coverage_dir']}",
            "",
            "## Deterministic Checks",
            "",
            "| Check | Status | Coverage | Missing | Warnings |",
            "| --- | --- | ---: | --- | --- |",
        ]
        for check in pack["deterministic_checks"]:
            missing = ", ".join(check["missing"]) or "None"
            warnings = ", ".join(check["warnings"]) or "None"
            lines.append(
                f"| {check['name']} | {check['status']} | {check['coverage']} | {missing} | {warnings} |"
            )
        lines.extend(["", "## Document Categories", ""])
        for category, docs in coverage["doc_category_coverage"]["details"]["categories"].items():
            lines.append(f"- {category}: {', '.join(docs)}")
        lines.extend(["", "## Missing Evidence Questions", ""])
        for question in coverage["missing_evidence_coverage"]["details"]["missing_evidence_questions"]:
            lines.append(f"- {question}")
        lines.extend(["", "## Reviewer Summary", ""])
        lines.extend(f"- {item}" for item in pack["reviewer_summary"])
        lines.extend(["", "## Local Commands", ""])
        lines.extend(f"```powershell\n{command}\n```" for command in pack["local_commands"])
        lines.extend(["", "## Gaps and Warnings", ""])
        lines.extend(f"- Gap: {item}" for item in coverage["gaps"] or ["None"])
        lines.extend(f"- Warning: {item}" for item in coverage["warnings"] or ["None"])
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in pack["limitations"])
        if pack["artifact_paths"]:
            lines.extend(["", "## RAG Coverage Artifacts", ""])
            lines.extend(f"- {label}: {path}" for label, path in pack["artifact_paths"].items())
        return "\n".join(lines).strip() + "\n"

    def _categories_from_expected_docs(self, questions: list[dict[str, Any]]) -> set[str]:
        categories: set[str] = set()
        for item in questions:
            for filename in item.get("expected_evidence_documents", []):
                categories.add(self._category(filename, ""))
        return categories

    def _category(self, filename: str, text: str) -> str:
        explicit = {
            "implementation_guide.md": "implementation",
            "dpa_privacy_policy.md": "privacy_dpa",
            "sla_support_policy.md": "sla_support",
            "ai_governance_security.md": "ai_governance_security",
            "disaster_recovery_plan.md": "disaster_recovery",
            "customer_success_onboarding.md": "customer_success_onboarding",
            "customer_contract_terms.md": "contract_legal",
            "acme_enterprise_rfp.md": "rfp",
            "prior_proposal.md": "proposal",
            "product_overview.md": "product",
            "security_policy.md": "security",
            "compliance_policy.md": "compliance",
            "pricing_notes.md": "pricing",
        }
        if filename in explicit:
            return explicit[filename]
        lowered = f"{filename} {text}".lower()
        mapping = [
            ("implementation", ["implementation_guide", "implementation guide", "rollout", "go-live"]),
            ("privacy_dpa", ["dpa", "privacy", "subprocessor", "processor"]),
            ("sla_support", ["sla", "support policy", "severity", "uptime"]),
            ("ai_governance_security", ["ai_governance", "ai governance", "model governance", "human review"]),
            ("disaster_recovery", ["disaster", "recovery", "rto", "rpo"]),
            ("customer_success_onboarding", ["customer_success", "onboarding", "customer success"]),
            ("rfp", ["rfp"]),
            ("proposal", ["proposal"]),
            ("product", ["product"]),
            ("security", ["security", "sso", "encryption"]),
            ("compliance", ["compliance", "soc 2", "hipaa"]),
            ("pricing", ["pricing", "discount", "subscription"]),
            ("contract_legal", ["contract", "terms", "dpa"]),
        ]
        for category, needles in mapping:
            if any(needle in lowered for needle in needles):
                return category
        return "knowledge_base"

    def _required_categories(self) -> set[str]:
        return {
            "implementation",
            "privacy_dpa",
            "sla_support",
            "ai_governance_security",
            "disaster_recovery",
            "customer_success_onboarding",
        }

    def _required_pack_files(self) -> set[str]:
        return {
            "implementation_guide.md",
            "dpa_privacy_policy.md",
            "sla_support_policy.md",
            "ai_governance_security.md",
            "disaster_recovery_plan.md",
            "customer_success_onboarding.md",
        }

    def _local_commands(self) -> list[str]:
        return [
            "python -m pytest -q",
            "python -m ruff check .",
            "python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4",
            "python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4",
            'curl -X GET "http://127.0.0.1:8000/rag/corpus-coverage" -H "X-API-Key: local-demo-key"',
            (
                'curl -X POST "http://127.0.0.1:8000/rag/eval-coverage-pack" '
                '-H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"'
            ),
            (
                'rg "rag/corpus-coverage|rag/eval-coverage-pack|RAG Corpus|rag_coverage|'
                'corpus coverage|eval coverage" app dashboard docs README.md tests scripts sample_data Makefile'
            ),
            (
                "Get-ChildItem -Recurse -File storage\\rag_coverage -ErrorAction SilentlyContinue | "
                "Select-Object FullName,Length,LastWriteTime"
            ),
        ]

    def _ratio(self, passed: int, total: int) -> float:
        return round(passed / total, 3) if total else 0.0
