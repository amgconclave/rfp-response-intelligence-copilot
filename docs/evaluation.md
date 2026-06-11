# Evaluation

The evaluation suite proves that the copilot retrieves the right approved evidence, cites its answers, and flags unsupported questions instead of inventing content. The project is designed for local/mock review, so evaluation must be deterministic and runnable from a fresh clone.

## Standard Dataset

`sample_data/eval_dataset.json` contains representative RFP questions, expected evidence documents, answer themes, and missing-evidence cases. The standard evaluator ingests the sample corpus, analyzes the sample RFP, asks the dataset questions, and prints precision, citation, latency, token, and cost metrics.

```bash
python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4
```

## Standard Metrics

- Retrieval precision@k: expected evidence documents found in cited documents.
- Citation coverage: share of questions that returned at least one citation.
- Missing-evidence detection count: unsupported questions correctly marked as missing evidence.
- Average latency: wall-clock latency per question.
- Input and output tokens: provider-reported or mock-estimated token usage.
- Estimated cost: configured per-1K-token cost calculation.

The built-in standard evaluator passes when retrieval precision is at least `0.45`, citation coverage is at least `0.70`, and at least one expected missing-evidence question is flagged.

## Red-Team Dataset

`sample_data/red_team_questions.json` contains adversarial and unsupported prompts. The red-team runner focuses on refusal quality, weak evidence detection, and whether unsupported claims remain flagged as missing-evidence.

```bash
python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4
```

The red-team run is expected to print `Pass/fail summary: PASS` when unsupported questions are detected and risky answer patterns stay within configured limits.

## API Evaluation

The `/rfp/evaluate` endpoint evaluates the current ingested corpus. For a clean local API session, ingest the sample documents first through `/documents/ingest`, `python -m app.demo`, or the Streamlit dashboard.

The v0.2 API also exposes proof-oriented coverage endpoints:

- `GET /rag/corpus-coverage`: summarizes corpus coverage by source, topic, and evidence readiness.
- `POST /rag/eval-coverage-pack`: writes a RAG Eval Coverage Pack under `storage/rag_coverage/`.
- `GET /proposal/agent-council`: returns local multi-role council eval scenarios for role coverage, turn order, tool governance, and handoff routing.
- `POST /proposal/agent-council-pack`: writes the Proposal Agent Council Pack under `storage/agent_council/`.
- `POST /proposal/approval-simulation`: returns local HITL approval simulation assertions for queue coverage, checkpoint keys, human-gate impact, and reject/block behavior.
- `POST /proposal/approval-simulation-pack`: writes the Proposal Approval Simulation Pack under `storage/approval_simulations/`.
- `GET /proposal/decision-provenance`: returns graph-level eval assertions for node/edge integrity, checkpoint pass-through, and council eval pass-through.
- `POST /proposal/decision-provenance-pack`: writes the Proposal Decision Provenance Pack under `storage/decision_provenance/`.
- `GET /proposal/submission-certification`: returns final certification gate assertions, checkpointed transitions, and reviewer routing checks.
- `POST /proposal/submission-certification-pack`: writes the Proposal Submission Certification Pack under `storage/submission_certifications/`.
- `GET /ops/proposal-observability`: returns trace analysis, retrieval diagnostics, experiment comparison, provider posture, governance findings, and HITL signals.
- `POST /ops/proposal-observability-pack`: writes the Proposal Observability Pack under `storage/proposal_observability/`.
- `GET /handoff/final-audit`: returns the README Consistency final audit.
- `POST /handoff/final-pack`: writes the Final Handoff Pack under `storage/final_handoff/`.
- `GET /ops/verification-evidence`: returns the local Verification Evidence Ledger for pytest, ruff, eval, red-team, dashboard smoke, demo, release gate, final audit, artifact inventory, and reviewer signoff.
- `POST /ops/verification-evidence-pack`: writes the Verification Evidence Pack under `storage/verification_evidence/`.

## Final Audit Coverage

`FinalHandoffService` is the last evaluation layer. It compares README claims, API docs, architecture notes, evaluation docs, demo output, script names, dashboard smoke coverage, generated artifact docs, RAG proof, red-team proof, local/mock limitations, and Azure optional notes.

The README Consistency audit expects architecture/evaluation coverage for Final Handoff behavior, including `FinalHandoffService`, README Consistency, Final Handoff, and `storage/final_handoff`. A passing audit means the portfolio description, endpoint list, artifact paths, and verification commands agree with the code.

## Dashboard Smoke

`scripts/dashboard_smoke.py` verifies the API paths that the Streamlit workbench depends on, including final handoff endpoints. It is intentionally API-level so it stays stable in CI and local terminal checks.

```bash
python scripts/dashboard_smoke.py
```

## Runtime Demo

`python -m app.demo` is the end-to-end reviewer script. It ingests sample docs, builds matrices and packs, runs readiness and release checks, writes generated artifacts, prints final audit status, and confirms the deterministic standard and red-team evals.

Expected final proof points include:

- Standard eval prints `Pass/fail summary: PASS`.
- Red-team eval prints `Pass/fail summary: PASS`.
- Dashboard Smoke reports `pass`.
- Proposal Agent Council eval scenarios all pass and the pack is written under `storage/agent_council/`.
- Proposal Decision Provenance eval assertions all pass and the graph pack is written under `storage/decision_provenance/`.
- Proposal Observability report includes local trace spans, retrieval diagnostics, governance findings, and the pack is written under `storage/proposal_observability/`.
- Final audit status reports `pass`.
- Final Handoff Pack is written under `storage/final_handoff/`.
- Verification Evidence Pack is written under `storage/verification_evidence/`.

## Local And Cloud Notes

RAG quality is measured against the bundled sample corpus, not a private production knowledge base. The default local/mock path uses `MockLLMProvider`, which keeps answer generation deterministic for tests, demos, and missing-evidence checks. Azure remains optional: there is No Azure dependency for local evaluation, and Azure OpenAI or Azure AI Search can be added later without changing the local proof workflow.

## Verification Order

Run the same sequence used for release readiness:

```bash
python -m ruff check .
python -m pytest -q
python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4
python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4
python scripts/dashboard_smoke.py
python -m app.demo
```
