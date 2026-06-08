import re

from app.models.api import AnalyzeResponse
from app.models.domain import RfpRequirement
from app.repositories.memory import InMemoryRepository


class RfpAnalysisService:
    def __init__(self, repo: InMemoryRepository) -> None:
        self.repo = repo

    def analyze(self, text: str, trace_id: str) -> AnalyzeResponse:
        requirements: list[RfpRequirement] = []
        deadlines: list[str] = []
        compliance_asks: list[str] = []
        security_questions: list[str] = []
        pricing_mentions: list[str] = []
        risks: list[str] = []
        missing_information: list[str] = []

        lines = [line.strip("-* \t") for line in text.splitlines() if line.strip()]
        due_dates = re.findall(
            r"(?:due|deadline|submit by|response by)(?:\s+is|\s*:)?\s+([A-Za-z]+ \d{1,2}, \d{4})",
            text,
            re.I,
        )
        deadlines.extend(item.strip() for item in due_dates)

        for line in lines:
            lower = line.lower()
            if any(key in lower for key in ["must", "shall", "required", "requirement", "provide"]):
                category = self._category(lower)
                priority = "high" if any(key in lower for key in ["must", "shall", "required"]) else "medium"
                req = RfpRequirement(category=category, text=line, priority=priority)
                requirements.append(req)
                self.repo.requirements[req.id] = req
            if any(key in lower for key in ["soc 2", "gdpr", "iso", "compliance", "audit"]):
                compliance_asks.append(line)
            if any(key in lower for key in ["security", "encryption", "sso", "data retention", "incident"]):
                security_questions.append(line)
            if any(key in lower for key in ["pricing", "price", "implementation fee", "packaging"]):
                pricing_mentions.append(line)
            if any(key in lower for key in ["penalty", "risk", "must not", "cannot", "data residency"]):
                risks.append(line)

        if not pricing_mentions:
            missing_information.append("Pricing or packaging expectations were not explicit in the RFP text.")
        if not deadlines:
            missing_information.append("Submission deadline was not found.")
        if len(requirements) < 3:
            missing_information.append("Few explicit requirements were detected; review the RFP manually.")

        return AnalyzeResponse(
            requirements=requirements,
            deadlines=deadlines,
            compliance_asks=compliance_asks,
            security_questions=security_questions,
            pricing_mentions=pricing_mentions,
            risks=risks,
            missing_information=missing_information,
            trace_id=trace_id,
        )

    def _category(self, lower: str) -> str:
        if "security" in lower or "encryption" in lower or "sso" in lower:
            return "security"
        if "pricing" in lower or "price" in lower or "packaging" in lower:
            return "pricing"
        if "soc 2" in lower or "gdpr" in lower or "compliance" in lower:
            return "compliance"
        if "implementation" in lower or "integration" in lower:
            return "implementation"
        return "functional"
