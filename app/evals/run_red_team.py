import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.evals.run_eval import _prepare_sample_corpus
from app.repositories.memory import repository
from app.services.container import get_container


async def _run(dataset_path: str, top_k: int) -> dict:
    settings = get_settings()
    await _prepare_sample_corpus(settings.sample_data_dir)
    container = get_container()
    path = Path(dataset_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    dataset = json.loads(path.read_text(encoding="utf-8"))
    details = []
    missing_detection_count = 0
    review_finding_count = 0

    for index, item in enumerate(dataset["questions"], start=1):
        trace_id = f"red-team-{index}-{uuid4().hex[:8]}"
        answer = await container.generation.answer_question(item["question"], trace_id, top_k)
        report = container.review_board.review_answer(
            item["question"],
            answer.answer_text,
            answer.citations,
            answer.missing_evidence,
            answer.token_usage,
            trace_id,
        )
        actual_categories = {finding.category for finding in report.findings}
        expected_categories = set(item.get("expected_review_categories", []))
        detected_missing = bool(answer.missing_evidence) or "missing_evidence" in actual_categories
        if item.get("expect_missing_evidence") and detected_missing:
            missing_detection_count += 1
        review_finding_count += len(report.findings)
        category_pass = expected_categories.issubset(actual_categories)
        missing_pass = not item.get("expect_missing_evidence") or detected_missing
        details.append(
            {
                "question": item["question"],
                "risk_type": item.get("risk_type", "unknown"),
                "citation_count": len(answer.citations),
                "missing_evidence_detected": detected_missing,
                "review_ready": report.passed,
                "review_categories": sorted(actual_categories),
                "finding_count": len(report.findings),
                "passed": category_pass and missing_pass,
            }
        )

    expected_missing = sum(1 for item in dataset["questions"] if item.get("expect_missing_evidence"))
    passed = all(detail["passed"] for detail in details)
    repository.reset()
    get_container.cache_clear()
    return {
        "question_count": len(dataset["questions"]),
        "expected_missing_evidence": expected_missing,
        "missing_evidence_detection_count": missing_detection_count,
        "review_finding_count": review_finding_count,
        "passed": passed,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local red-team checks for RFP answer groundedness.")
    parser.add_argument("--dataset", default="sample_data/red_team_questions.json")
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()
    result = asyncio.run(_run(args.dataset, args.top_k))
    print("RFP Copilot Red-Team Evaluation")
    print(f"Number of red-team questions: {result['question_count']}")
    print(f"Expected missing-evidence cases: {result['expected_missing_evidence']}")
    print(f"Missing-evidence detections: {result['missing_evidence_detection_count']}")
    print(f"Review findings: {result['review_finding_count']}")
    print(f"Pass/fail summary: {'PASS' if result['passed'] else 'FAIL'}")
    for detail in result["details"]:
        categories = ", ".join(detail["review_categories"]) or "none"
        print(
            f"- {detail['risk_type']}: citations={detail['citation_count']} "
            f"missing={detail['missing_evidence_detected']} categories={categories}"
        )


if __name__ == "__main__":
    main()
