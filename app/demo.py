import asyncio

from app.services.container import get_container

SAMPLE_DOCS = [
    ("sample_data/acme_enterprise_rfp.md", "rfp"),
    ("sample_data/prior_proposal.md", "proposal"),
    ("sample_data/product_overview.md", "product"),
    ("sample_data/security_policy.md", "security"),
    ("sample_data/compliance_policy.md", "compliance"),
    ("sample_data/pricing_notes.md", "pricing"),
]


async def load_samples() -> None:
    container = get_container()
    for path, doc_type in SAMPLE_DOCS:
        already_loaded = any(
            doc.metadata.get("path", "").endswith(path.replace("/", "\\"))
            for doc in container.repo.documents.values()
        )
        if already_loaded:
            continue
        await container.ingestion.ingest_path(path, document_type=doc_type, source="sample_data")


async def main() -> None:
    container = get_container()
    await load_samples()
    rfp_text = container.ingestion.get_text(
        next(doc.id for doc in container.repo.documents.values() if doc.filename == "acme_enterprise_rfp.md")
    )
    analysis = container.analysis.analyze(rfp_text, "demo-analysis")
    answer = await container.generation.answer_question(
        "What SSO and encryption controls are supported?",
        "demo-query",
    )
    draft = await container.generation.draft_response("demo-draft")
    evaluation = await container.evaluation.run("sample_data/eval_dataset.json", "demo-eval")

    print("RFP Response Intelligence Copilot demo")
    print(f"Documents loaded: {len(container.repo.documents)}")
    print(f"Requirements extracted: {len(analysis.requirements)}")
    print(f"Answer confidence: {answer.confidence}")
    print(f"Citations: {', '.join(c.filename for c in answer.citations)}")
    print(f"Draft sections: {len(draft.sections)}")
    print(f"Eval pass: {evaluation.passed}")
    print(f"Retrieval precision@k: {evaluation.retrieval_precision_at_k}")
    print(f"Citation coverage: {evaluation.citation_coverage}")


if __name__ == "__main__":
    asyncio.run(main())
