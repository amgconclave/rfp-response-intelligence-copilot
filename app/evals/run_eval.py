import argparse
import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.repositories.memory import repository
from app.services.container import get_container


async def _prepare_sample_corpus(sample_dir: Path) -> None:
    repository.reset()
    get_container.cache_clear()
    container = get_container()
    for path in sorted(sample_dir.glob("*")):
        if path.name == "eval_dataset.json" or path.suffix.lower() not in {".md", ".txt", ".pdf"}:
            continue
        document_type = "rfp" if "rfp" in path.name else "knowledge_base"
        await container.ingestion.ingest_path(
            path,
            document_type=document_type,
            source="sample_data",
            tags=["sample", document_type],
        )


async def _run(dataset_path: str, top_k: int) -> dict:
    settings = get_settings()
    sample_dir = settings.sample_data_dir
    await _prepare_sample_corpus(sample_dir)
    container = get_container()
    rfp_path = sample_dir / "acme_enterprise_rfp.md"
    analysis = container.analysis.analyze(rfp_path.read_text(encoding="utf-8"), "local-eval-analysis")
    metrics = await container.evaluation.run(dataset_path, "local-eval", top_k)
    return {
        "sample_documents_indexed": len(container.repo.documents),
        "requirements_detected": len(analysis.requirements),
        "evaluation": metrics.model_dump(mode="json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local deterministic RFP copilot eval.")
    parser.add_argument("--dataset", default="sample_data/eval_dataset.json")
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()
    result = asyncio.run(_run(args.dataset, args.top_k))
    evaluation = result["evaluation"]
    print("RFP Copilot Evaluation")
    print(f"Sample documents indexed: {result['sample_documents_indexed']}")
    print(f"Requirements detected: {result['requirements_detected']}")
    print(f"Number of eval questions: {evaluation['question_count']}")
    print(f"Retrieval precision at k: {evaluation['retrieval_precision_at_k']}")
    print(f"Citation coverage: {evaluation['citation_coverage']}")
    print(
        "Missing-evidence detection count: "
        f"{evaluation['missing_evidence_detection_count']}"
    )
    print(f"Average latency: {evaluation['average_latency_ms']} ms")
    print(f"Token usage: input={evaluation['input_tokens']} output={evaluation['output_tokens']}")
    print(f"Estimated cost: {evaluation['estimated_cost']}")
    print(f"Pass/fail summary: {'PASS' if evaluation['passed'] else 'FAIL'}")
    for detail in evaluation["details"]:
        cited = ", ".join(detail["cited_documents"]) or "none"
        print(f"- {detail['question']} | precision={detail['precision']} | cited={cited}")


if __name__ == "__main__":
    main()
