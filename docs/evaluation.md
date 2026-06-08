# Evaluation

The local evaluation suite measures whether the copilot retrieves the right enterprise evidence and refuses unsupported claims.

## Dataset

`sample_data/eval_dataset.json` contains representative RFP questions, expected evidence documents, answer themes, and a missing-evidence case.

## Metrics

- Retrieval precision@k: expected evidence documents found in the cited documents.
- Citation coverage: share of questions that returned at least one citation.
- Missing-evidence detection count: unsupported questions correctly flagged.
- Average latency: wall-clock latency per eval question.
- Input/output tokens: provider-reported or mock-estimated token usage.
- Estimated cost: calculated from configured per-1K token costs.

## Command

```bash
python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4
```

The command indexes sample documents, analyzes the sample RFP, runs the eval dataset, and prints a human-readable summary with retrieval, citation, latency, token, and cost metrics.

## API Evaluation

The `/rfp/evaluate` endpoint evaluates the current ingested corpus. For a clean local API session, ingest the sample documents first through `/documents/ingest` or the Streamlit dashboard.

## Pass Criteria

The built-in evaluator marks a run as passed when retrieval precision is at least `0.45`, citation coverage is at least `0.70`, and at least one expected missing-evidence question is flagged.
