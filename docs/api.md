# API

Base URL: `http://127.0.0.1:8000`

Authenticated endpoints require `X-API-Key`. In local mode the default key is `local-demo-key`.

## Endpoints

### `POST /auth/demo-token`

Returns the local demo API key and header name.

### `GET /health`

Returns service status, provider mode, vector store mode, and version.

### `GET /ops/smoke-matrix`

Returns the Local Launch Smoke Matrix for core, enterprise, artifact-writing, and ops APIs. The matrix includes endpoint names, methods, expected status/result, sample curl commands, artifact expectations, auth notes, and a readiness summary.

```bash
curl -X GET "http://127.0.0.1:8000/ops/smoke-matrix" \
  -H "X-API-Key: local-demo-key"
```

The response includes `rows`, `readiness_summary`, and `trace_id`. `readiness_summary` includes total endpoints, protected endpoints, artifact-writing endpoints, local/mock readiness, recommended sequence, exact local verification commands, and optional provider notes.

### `POST /ops/launch-checklist`

Writes a Markdown and JSON Local Launch Checklist under `storage/launch_checklists/` by default. The checklist includes install/run commands, the API smoke matrix, the demo command, eval and red-team commands, generated artifact paths, troubleshooting, JD skills demonstrated, and five interviewer talking points.

```json
{
  "write_artifact": true
}
```

The response includes `artifact_path`, `json_artifact_path`, `markdown`, structured `checklist`, embedded `smoke_matrix`, and `trace_id`.

### `GET /ops/cost-governance`

Returns local cost and provider governance for the RFP workflow. The report includes provider readiness, current usage totals, token profile, deterministic workflow estimates, budget utilization, reviewer controls, local proof commands, limitations, and trace ID. Local/mock mode remains the default and does not require paid provider keys.

```bash
curl -X GET "http://127.0.0.1:8000/ops/cost-governance" \
  -H "X-API-Key: local-demo-key"
```

### `POST /ops/cost-governance`

Returns the same governance report with caller-supplied workflow assumptions.

```json
{
  "daily_rfp_count": 3,
  "questions_per_rfp": 12,
  "draft_sections_per_rfp": 5,
  "eval_runs_per_day": 1,
  "red_team_runs_per_day": 1,
  "daily_budget_usd": 25.0
}
```

### `POST /ops/cost-governance-pack`

Writes Markdown and JSON Cost Governance Pack artifacts under ignored `storage/cost_governance/` by default. The pack includes an executive budget summary, provider readiness, workflow estimates, reviewer controls, proof commands, and limitations.

```json
{
  "write_artifact": true
}
```

The response includes `artifact_path`, `json_artifact_path`, `markdown`, structured `pack`, embedded `governance`, and `trace_id`.

### `GET /ops/provider-resilience`

Returns the Provider Resilience Runbook for mock, OpenAI, and Azure OpenAI routes. It includes typed provider route readiness, missing environment variables, fallback route decisions, checkpointed state-machine states, traceable transitions, dependency-injection contract details, eval scenarios, operator runbook steps, trace spans, proof commands, limitations, and trace ID. It does not call external providers.

```bash
curl -X GET "http://127.0.0.1:8000/ops/provider-resilience" \
  -H "X-API-Key: local-demo-key"
```

### `POST /ops/provider-resilience-pack`

Writes Markdown and JSON Provider Resilience Runbook Pack artifacts under ignored `storage/provider_resilience/` by default. The pack documents the recommended provider route, mock fallback behavior, state transitions, dependency-injection contract, reviewer checklist, proof commands, and limitations.

```json
{
  "write_artifact": true
}
```

The response includes `artifact_path`, `json_artifact_path`, `markdown`, structured `pack`, embedded `resilience`, and `trace_id`.

### `GET /runtime/demo-readiness`

Returns local FastAPI and Streamlit runtime readiness for fresh-clone reviewers. It includes exact start commands, stop commands, expected ports, environment requirements, dependency checks, read-only localhost port checks, expected health/smoke URLs, RAG/eval/red-team commands, demo flow order, screenshot checklist placeholders, troubleshooting, recruiter/engineer explanation, known limitations, and trace ID. It does not kill processes or require OpenAI, Azure, live Qdrant, or any external service.

```bash
curl -X GET "http://127.0.0.1:8000/runtime/demo-readiness" \
  -H "X-API-Key: local-demo-key"
```

### `POST /runtime/demo-pack`

Writes Markdown and JSON Runtime Demo Server Pack artifacts under ignored `storage/runtime_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes exact start commands, stop commands, health checks, demo flow order, RAG/eval/red-team verification order, screenshot checklist placeholders, troubleshooting, recruiter/engineer explanation, known limitations, embedded readiness JSON, Markdown, JSON, and trace ID.

### `GET /ops/ci-doctor`

Returns the Local CI Doctor readiness report. It checks the pytest command, ruff command, standard eval command, red-team command, demo command, GitHub Actions workflow presence, Docker Compose presence, `.env.example`, README required sections, docs presence, generated artifact ignores, dependency files, local/mock provider notes, and a redacted secret scan summary. It does not execute shell commands or call external services.

```bash
curl -X GET "http://127.0.0.1:8000/ops/ci-doctor" \
  -H "X-API-Key: local-demo-key"
```

The response includes `status`, `score`, structured `checks`, `dependency_inventory`, `secret_scan`, exact `local_verification_commands`, `generated_at`, and `trace_id`.

### `POST /ops/audit-pack`

Writes Markdown and JSON Audit Pack artifacts under ignored `storage/audit_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes CI Doctor results, dependency inventory, secret scan summary, local verification commands, publish-safety checklist, remediation notes, recruiter/interviewer explanation, limitations, artifact paths, Markdown, JSON, and trace ID.

### `GET /api/contract-audit`

Returns an OpenAPI-derived API Contract Snapshot. It includes OpenAPI route and path counts, auth-protected endpoint count, endpoint inventory grouped by domain, docs/API coverage for important endpoints, dashboard smoke alignment, generated artifact endpoint coverage, demo flow endpoint coverage, RAG/eval/red-team endpoint coverage, missing docs warnings, deprecated/duplicate route warnings, and local-only limitations.

```bash
curl -X GET "http://127.0.0.1:8000/api/contract-audit" \
  -H "X-API-Key: local-demo-key"
```

The response uses `ApiContractAuditResponse` and includes `openapi_route_count`, `auth_protected_endpoint_count`, `endpoint_inventory`, `docs_api_coverage`, `dashboard_smoke_alignment`, `generated_artifact_endpoint_coverage`, `demo_flow_endpoint_coverage`, `rag_eval_red_team_endpoint_coverage`, warnings, limitations, and trace ID.

### `GET /rag/corpus-coverage`

Returns the RAG Corpus coverage view for the local fake enterprise corpus. It includes corpus metadata, document category coverage, eval coverage, citation/source coverage, red-team coverage, missing-evidence coverage, gaps, warnings, local proof commands, generated timestamp, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/rag/corpus-coverage" \
  -H "X-API-Key: local-demo-key"
```

### `POST /rag/eval-coverage-pack`

Runs deterministic local corpus coverage checks and writes Markdown/JSON artifacts under ignored `storage/rag_coverage/` by default.

```json
{
  "write_artifact": true
}
```

The pack covers the expanded implementation, DPA/privacy, SLA/support, AI governance/security, disaster recovery, and customer success/onboarding documents, plus eval coverage, red-team coverage, citation/source coverage, and missing-evidence coverage.

### `GET /evidence/freshness`

Returns the Evidence Freshness + Expiry Risk report. It scores non-RFP source documents by effective date, renewal date, policy owner, endpoint references, citation use, unsupported or absolute claim language, expiry status, risk drivers, and local proof commands.

```bash
curl -X GET "http://127.0.0.1:8000/evidence/freshness" \
  -H "X-API-Key: local-demo-key"
```

The local report uses deterministic sample metadata and falls back to document metadata or content labels for uploaded documents. It does not require a live GRC, policy management, legal, or CRM system.

### `POST /evidence/freshness-pack`

Writes Markdown and JSON Evidence Freshness + Expiry Risk Pack artifacts under ignored `storage/freshness_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes the source freshness matrix, renewal calendar, owner follow-ups, unsupported-claim flags, endpoint references, exact local proof commands, limitations, embedded freshness JSON, Markdown, JSON, and trace ID.

### `GET /evidence/conflicts`

Returns the Evidence Conflict Resolver report. It scans the local evidence corpus for source-precedence, scope, and ambiguity conflicts such as demo-only pricing versus enterprise scope, local-demo subprocessors versus optional cloud providers, DR targets versus absolute SLA language, and local API-key auth versus production SSO.

```bash
curl -X GET "http://127.0.0.1:8000/evidence/conflicts" \
  -H "X-API-Key: local-demo-key"
```

The response includes cited claims, conflict severity, reviewer owner, blocked/needs-review status, resolution guidance, endpoint impact, reviewer queue, proof commands, limitations, and trace ID.

### `POST /evidence/conflict-pack`

Writes Markdown and JSON Evidence Conflict Resolver Pack artifacts under ignored `storage/conflict_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes a conflict matrix, cited resolutions, reviewer queue, endpoint references, exact local proof commands, limitations, artifact paths, embedded conflict JSON, Markdown, JSON, and trace ID.

### `GET /evidence/citation-lineage`

Returns the Citation Lineage + Integrity Audit. It generates representative local answer and draft citations from the sample corpus, then verifies each citation back to the in-memory repository document and chunk IDs. It flags missing references, stale snippets, filename mismatches, weak citation scores, generated regulated or absolute claim language, owner follow-ups, endpoint impact, local proof commands, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/evidence/citation-lineage" \
  -H "X-API-Key: local-demo-key"
```

The default path is local/mock and self-contained. It auto-loads the sample corpus when needed and does not require OpenAI, Azure, Qdrant, or an external document repository.

### `POST /evidence/citation-lineage-pack`

Writes Markdown and JSON Citation Lineage + Integrity Pack artifacts under ignored `storage/citation_lineage/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes the citation lineage matrix, stale/missing citation lists, generated-claim flags, owner follow-ups, endpoint references, exact proof commands, limitations, Markdown, JSON, and trace ID.

### `GET /evidence/source-trust`

Returns the Source Trust Gate report. It combines Evidence Freshness, Evidence Conflict Resolver, and Citation Lineage signals into source-level trust scores, reuse decisions, retrieval policies, reviewer queues, endpoint impact, proof commands, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/evidence/source-trust" \
  -H "X-API-Key: local-demo-key"
```

The default path auto-loads the local sample corpus and uses deterministic rules. It recommends retrieval policy updates but does not mutate a live vector index or external policy system.

### `POST /evidence/source-trust-pack`

Writes Markdown and JSON Source Trust Gate artifacts under ignored `storage/source_trust/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes the source trust matrix, reviewer queue, retrieval policy updates, endpoint references, local proof commands, limitations, embedded source-trust JSON, Markdown, JSON, and trace ID.

### `POST /evidence/governed-retrieval`

Returns a Governed Retrieval Preview for a buyer/RFP question. It retrieves candidate citations, joins Source Trust Gate decisions, applies retrieval policies, returns allowed citations, blocked or suppressed rows, human-review queue items, trace-analysis spans, proof commands, limitations, and trace ID.

```json
{
  "question": "What disaster recovery, uptime, SSO, encryption, and audit controls are supported?",
  "top_k": 6,
  "include_suppressed": false
}
```

The default path is deterministic and local/mock. It previews governance before generation and does not mutate the vector index or call external approval systems.

### `POST /evidence/governed-retrieval-pack`

Writes Markdown and JSON Governed Retrieval artifacts under ignored `storage/governed_retrieval/` by default.

```json
{
  "question": "What disaster recovery, uptime, SSO, encryption, and audit controls are supported?",
  "top_k": 6,
  "write_artifact": true
}
```

The pack includes governed retrieval results, allowed citations, blocked/suppressed rows, reviewer decisions, trace spans, local proof commands, limitations, embedded governed-retrieval JSON, Markdown, JSON, and trace ID.

### `GET /proposal/buyer-intelligence`

Returns the Buyer-Grade Proposal Intelligence workflow. It composes deterministic local signals from requirement analysis, review findings, source trust, model risk, procurement question risk, and cost governance into durable workflow stages, a human approval queue, governance gates, provider routes, shared state, trace analysis, proof commands, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/proposal/buyer-intelligence" \
  -H "X-API-Key: local-demo-key"
```

The default path auto-loads local sample evidence and stays in mock/local mode unless optional provider environment variables are configured elsewhere.

### `POST /proposal/buyer-intelligence-pack`

Writes Markdown, JSON, and durable local workflow state JSON artifacts under ignored `storage/buyer_intelligence/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes buyer-facing workflow checkpoints, restart keys, human-in-the-loop approvals, governance gates, provider-flexibility guidance, local trace analysis, executive controls, proof commands, limitations, embedded workflow JSON, Markdown, JSON, state JSON, and trace ID.

### `GET /proposal/buyer-intelligence-replay`

Returns the Buyer Workflow Replay and Transition Audit. It derives ordered state-machine transitions from the buyer workflow, including conditional route decisions, checkpoint keys, trace references, checkpoint validation, replay summary, eval-friendly assertions, proof commands, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/proposal/buyer-intelligence-replay" \
  -H "X-API-Key: local-demo-key"
```

### `POST /proposal/buyer-intelligence-replay-pack`

Writes Markdown and JSON replay artifacts under ignored `storage/buyer_intelligence/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes the replay transition table, conditional routing decisions, checkpoint validation, eval scenarios, reviewer controls, local proof commands, limitations, embedded replay JSON, Markdown, JSON, and trace ID.

### `GET /proposal/buyer-contracts`

Returns the Buyer Structured Output Contract Audit. It validates the buyer workflow, replay, agent council, and decision provenance as Pydantic structured outputs, then reports role contracts for sales, presales, compliance, procurement, and proposal management, schema snapshots, dependency-injection notes, eval assertions, proof commands, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/proposal/buyer-contracts" \
  -H "X-API-Key: local-demo-key"
```

The audit is deterministic and local. It does not call OpenAI, Azure OpenAI, CRM, GRC, or procurement systems.

### `POST /proposal/buyer-contracts-pack`

Writes Markdown and JSON structured-output contract artifacts under ignored `storage/buyer_contracts/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes output contract inventories, compact schema snapshots, role coverage, contract checks, eval assertions, reviewer controls, local proof commands, limitations, embedded audit JSON, Markdown, JSON, and trace ID.

### `GET /proposal/agent-council`

Returns the Proposal Agent Council. It composes the buyer workflow, source trust, model risk, cost governance, and procurement question risk into deterministic sales, presales, compliance, procurement, and proposal-manager turns with shared state, governed tool access, handoffs, token budget estimates, eval scenarios, proof commands, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/proposal/agent-council" \
  -H "X-API-Key: local-demo-key"
```

The council is a local governance transcript and does not call autonomous agents or external model providers.

### `POST /proposal/agent-council-pack`

Writes Markdown, JSON, and transcript JSON artifacts under ignored `storage/agent_council/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes the role-based transcript, shared state, cross-functional handoffs, tool governance policy, budget ledger, eval scenarios, reviewer controls, proof commands, limitations, embedded council JSON, Markdown, JSON, transcript JSON, and trace ID.

### `GET /proposal/decision-provenance`

Returns the Proposal Decision Provenance Graph. It composes buyer workflow replay, agent council turns, human handoffs, governance gates, provider/cost policy, source trust, model-risk policy, procurement approvals, typed graph nodes, traceable graph edges, decision controls, eval assertions, proof commands, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/proposal/decision-provenance" \
  -H "X-API-Key: local-demo-key"
```

The graph is deterministic local provenance and does not call external tracing, CRM, procurement, GRC, or model providers.

### `POST /proposal/decision-provenance-pack`

Writes Markdown and JSON artifacts under ignored `storage/decision_provenance/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes the typed provenance graph, node and edge tables, decision controls, eval assertions, reviewer controls, proof commands, limitations, embedded provenance JSON, Markdown, JSON, and trace ID.

### `GET /proposal/submission-certification`

Returns the Proposal Submission Certification Gate. It consolidates the buyer workflow, checkpoint replay, agent council, decision provenance graph, and structured contract audit into typed final gates, reviewer queue items, checkpointed certification transitions, injected dependency metadata, eval assertions, proof commands, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/proposal/submission-certification" \
  -H "X-API-Key: local-demo-key"
```

The certification is deterministic and local-only; it does not submit proposals or call external approval, CRM, procurement, GRC, OpenAI, or Azure services.

### `POST /proposal/submission-certification-pack`

Writes Markdown and JSON artifacts under ignored `storage/submission_certifications/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes certification gates, state transitions, reviewer queue, eval assertions, reviewer controls, proof commands, limitations, embedded certification JSON, Markdown, JSON, and trace ID.

### `GET /compliance/evidence-matrix`

Returns the Compliance Evidence Matrix and Control Mapping view. It maps regulated-enterprise asks to control families, linked RFP requirements, policy snippets, confidence, owners, status, missing-evidence warnings, unsupported-claim flags, reviewer notes, local proof commands, coverage summary, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/compliance/evidence-matrix" \
  -H "X-API-Key: local-demo-key"
```

Control families include access control/SSO, encryption/key management, privacy/DPA/subprocessors, audit logging, AI governance/model claims, SLA/support, disaster recovery/BCP, and data residency/export.

### `POST /compliance/control-pack`

Writes Markdown and JSON Control Mapping Pack artifacts under ignored `storage/compliance_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes control coverage, source snippets, unsupported claims, gaps, owner actions, reviewer notes, exact local proof commands, limitations, embedded evidence matrix JSON, Markdown, JSON, and trace ID.

### `GET /privacy/retention-guardrails`

Returns the Privacy + Retention Guardrail Matrix. It maps provider prompts, audit/logging, vector metadata, generated artifacts, eval datasets, and document uploads to local privacy evidence, data categories, retention posture, missing controls, redaction rules, reviewer owners, endpoint references, prompt/logging guidance, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/privacy/retention-guardrails" \
  -H "X-API-Key: local-demo-key"
```

The default path is local/mock. It does not call external providers or delete local storage; it creates reviewer-ready recommendations from the ingested sample privacy, compliance, implementation, and AI governance evidence.

### `POST /privacy/retention-pack`

Writes Markdown and JSON Privacy Retention Guardrail Pack artifacts under ignored `storage/privacy_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes the surface matrix, policy evidence snippets, retention actions, prompt/logging guidance, exact local proof commands, limitations, embedded guardrail JSON, Markdown, JSON, and trace ID.

### `GET /governance/model-risk-register`

Returns the local Model Risk Register. It maps groundedness, provider change, prompt privacy, eval coverage, cost/latency, and human approval risks to local policy evidence, mitigation controls, eval gates, red-team gates, reviewer owners, release gates, limitations, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/governance/model-risk-register" \
  -H "X-API-Key: local-demo-key"
```

The default path is deterministic and local/mock. It does not call external model-risk, GRC, ticketing, OpenAI, or Azure systems.

### `POST /governance/model-risk-pack`

Writes Markdown and JSON Model Risk Register Pack artifacts under ignored `storage/model_risk/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes the risk register, mapped evidence snippets, release gates, reviewer queue, proof commands, limitations, embedded register JSON, Markdown, JSON, and trace ID.

### `GET /procurement/question-risk`

Returns the Procurement Q&A question risk catalog. It simulates security architecture, privacy/DPA, SLA/support, disaster recovery, AI governance/model claims, pricing/commercial, implementation timeline, and out-of-scope/adversarial unsupported-claim buyer questions. Each item includes category, risk level, required reviewer role, approval status, evidence support, unsupported-claim flag, citations, snippets, approved response memory matches, reviewer checklist, escalation owner, evidence gaps, review findings, and coverage summary.

```bash
curl -X GET "http://127.0.0.1:8000/procurement/question-risk" \
  -H "X-API-Key: local-demo-key"
```

### `POST /procurement/approval-pack`

Writes Markdown and JSON Procurement Q&A Approval Workflow Pack artifacts under ignored `storage/procurement_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes high-risk questions, approved/blocked draft answers, reviewer checklist, escalation owners, evidence gaps, exact local proof commands, limitations, embedded question risk JSON, Markdown, JSON, and trace ID.

### `GET /procurement/risk-desk`

Returns the Procurement Risk Desk packet view for legal, pricing, data residency, insurance, and implementation risk. Each row includes severity, risk score, status, owner role, reviewer role, due hint, packet signals, recommended actions, evidence gaps, related requirement IDs, related contract clause IDs, citations/snippets, owner routing, proof commands, and limitations. The response also includes durable workflow checkpoints, a human-review queue, trace spans, and a governance summary so procurement risks can be resumed, approved, or blocked before submission.

```bash
curl -X GET "http://127.0.0.1:8000/procurement/risk-desk" \
  -H "X-API-Key: local-demo-key"
```

### `POST /procurement/risk-desk-pack`

Writes Markdown and JSON Procurement Risk Desk Pack artifacts under ignored `storage/procurement_risk_desk/` by default. The pack is built from the local RFP packet, requirement matrix, review findings, contract-risk analyzer, pricing strategy signals, procurement Q&A approvals, and retrieved citations.

```json
{
  "write_artifact": true
}
```

The pack includes owner routing, durable workflow gates, human-review queue, trace analysis, detailed desk risks, executive notes, packet sources, proof commands, limitations, embedded risk desk JSON, Markdown, JSON, and trace ID.

### `GET /bid/scenario-analysis`

Returns the Bid/No-Bid Scenario Simulator with four deterministic executive scenarios: pursue, pursue with conditions, no-bid due to compliance/evidence risk, and no-bid due to commercial/timeline risk. Each scenario includes deal value, pursuit effort, pursuit cost, win probability, gross margin, risk-adjusted revenue, risk-adjusted gross profit, risk-adjusted ROI, blockers, required reviewers, evidence readiness, timeline pressure, decision recommendation, customer profile, assumptions, and coverage summary.

```bash
curl -X GET "http://127.0.0.1:8000/bid/scenario-analysis" \
  -H "X-API-Key: local-demo-key"
```

### `POST /bid/roi-pack`

Writes Markdown and JSON ROI Impact Pack artifacts under ignored `storage/bid_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes an executive decision memo, scenario comparison table, ROI math, blockers, follow-up owners, proof commands, limitations, embedded scenario analysis JSON, Markdown, JSON, and trace ID.

### `POST /learning/win-loss`

Ingests fake local post-RFP outcomes from `sample_data/rfp_outcomes.json` by default and returns a deterministic Win/Loss Learning Loop analysis. The response includes outcome count, win rate, winning evidence patterns, losing risk patterns, retrieval recommendations, eval/red-team recommendations, response guidance updates, owner actions, proof commands, limitations, and trace ID.

```bash
curl -X POST "http://127.0.0.1:8000/learning/win-loss" \
  -H "X-API-Key: local-demo-key" \
  -H "Content-Type: application/json" \
  -d "{}"
```

Optional body fields include `outcomes_fixture_path`, inline `outcomes`, `analysis`, `matrix`, `win_strategy`, `eval_metrics`, and `top_k_patterns`.

### `POST /learning/win-loss-pack`

Writes Markdown and JSON Win/Loss Learning Strategy Pack artifacts under ignored `storage/win_loss_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes an executive summary, winning evidence pattern table, loss guardrails, retrieval updates, eval updates, response guidance updates, owner action plan, proof commands, limitations, embedded learning response JSON, Markdown, JSON, and trace ID.

### `POST /learning/win-loss-policy`

Builds a local Win/Loss Policy Activation Plan from the learning response and retrieval experiment comparison. The response uses typed contracts and a traceable state machine with policy rules, checkpoints, owner review queue, rollback plan, governance summary, proof commands, limitations, and trace ID. It does not mutate live retrieval defaults.

```bash
curl -X POST "http://127.0.0.1:8000/learning/win-loss-policy" \
  -H "X-API-Key: local-demo-key" \
  -H "Content-Type: application/json" \
  -d "{}"
```

Optional body fields include `learning_response`, `retrieval_experiment`, `activation_mode`, `dataset_path`, `outcomes_fixture_path`, `top_k`, and `policy_ids`.

### `POST /learning/win-loss-policy-pack`

Writes Markdown and JSON Win/Loss Policy Activation Pack artifacts under ignored `storage/win_loss_policy/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes activation status, recommended policy, source-boost and gap-guardrail rules, state transitions, eval/red-team checkpoints, owner approvals, rollback triggers, proof commands, limitations, embedded activation plan JSON, Markdown, JSON, and trace ID.

### `POST /rag/retrieval-experiments`

Runs a deterministic local comparison of retrieval policies over `sample_data/eval_dataset.json` by default. The comparison includes baseline vector retrieval, win/loss source boosting, loss-gap guardrails, and a balanced governed policy. It returns policy scores, per-question retrieval diagnostics, local trace spans, governance decision, proof commands, limitations, and the recommended shadow-eval policy.

```bash
curl -X POST "http://127.0.0.1:8000/rag/retrieval-experiments" \
  -H "X-API-Key: local-demo-key" \
  -H "Content-Type: application/json" \
  -d "{}"
```

Optional body fields include `dataset_path`, `outcomes_fixture_path`, `top_k`, and `policy_ids`.

### `POST /rag/retrieval-experiment-pack`

Writes Markdown and JSON Retrieval Experiment Comparison Pack artifacts under ignored `storage/retrieval_experiments/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes an executive summary, policy comparison table, question diagnostics, local trace spans, governance recommendation, proof commands, limitations, embedded comparison JSON, Markdown, JSON, and trace ID.

### `GET /ops/proposal-observability`

Returns a local proposal observability control plane that aggregates buyer workflow checkpoints, replay transitions, agent council turns, decision provenance nodes, retrieval experiment trace spans, retrieval diagnostics, provider/cost posture, governance findings, and human-review signals.

```bash
curl -X GET "http://127.0.0.1:8000/ops/proposal-observability" \
  -H "X-API-Key: local-demo-key"
```

### `POST /ops/proposal-observability-pack`

Writes Markdown and JSON Proposal Observability Pack artifacts under ignored `storage/proposal_observability/` by default.

```json
{
  "dataset_path": "sample_data/eval_dataset.json",
  "outcomes_fixture_path": "sample_data/rfp_outcomes.json",
  "top_k": 4,
  "write_artifact": true
}
```

The pack includes the trace map, risky retrieval diagnostics, experiment comparison, provider and cost signals, governance findings, human-review signals, proof commands, limitations, embedded observability JSON, Markdown, JSON, and trace ID.

### `POST /api/reviewer-collection`

Writes a Markdown and JSON Reviewer Collection Pack under ignored `storage/api_contracts/` by default. The collection includes endpoint inventory grouped by domain, sample curl and PowerShell commands with `X-API-Key`, demo-token flow, expected status codes, auth notes, generated artifact endpoints, RAG/eval/red-team verification order, recruiter and engineer explanation, local-only limitations, embedded API Contract Snapshot, Markdown, JSON, and trace ID.

```json
{
  "write_artifact": true
}
```

Use this pair when the API is already running:

```bash
curl -X GET "http://127.0.0.1:8000/api/contract-audit" -H "X-API-Key: local-demo-key"
curl -X POST "http://127.0.0.1:8000/api/reviewer-collection" -H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"
```

### `GET /ui/dashboard-smoke`

Returns Dashboard Smoke source-level checks for the Streamlit dashboard without launching a browser. It verifies expected tab/view labels, endpoint references, generated artifact tabs, local run commands, and limitations.

```bash
curl -X GET "http://127.0.0.1:8000/ui/dashboard-smoke" \
  -H "X-API-Key: local-demo-key"
```

The response includes `status`, `summary`, `expected_views`, `endpoint_references`, `generated_artifact_tabs`, `local_run_commands`, `limitations`, `checks`, and `trace_id`.

### `POST /ui/verification-pack`

Writes Markdown and JSON UI Verification Pack artifacts under ignored `storage/ui_verification/` by default.

```json
{
  "write_artifact": true
}
```

The UI Verification Pack includes dashboard smoke results, the Streamlit run command, API run command, reviewer checklist, screenshot placeholders, troubleshooting, limitations, Markdown, JSON, and trace ID.

### `GET /artifacts/inventory`

Returns the Artifact Inventory for generated local demo artifacts. Each row includes artifact directory, latest files, producer endpoint, producer command, ignored status, reviewer purpose, freshness notes, and file counts.

```bash
curl -X GET "http://127.0.0.1:8000/artifacts/inventory" \
  -H "X-API-Key: local-demo-key"
```

The response includes `storage_root`, `ignored_status`, `total_directories`, `total_files`, `directories`, `local_commands`, `reviewer_proof_checklist`, and `trace_id`.

### `POST /artifacts/readme-checklist`

Writes Markdown and JSON README Checklist artifacts under ignored `storage/artifact_indexes/` by default.

```json
{
  "write_artifact": true
}
```

The README Checklist Pack includes Artifact Inventory, README badge suggestions, README checklist suggestions, local commands, reviewer proof checklist, cleanup/regeneration notes, Markdown, JSON, and trace ID.

### `GET /release/quality-gate`

Returns the Release Candidate Quality Gate for GitHub publishing. The gate is deterministic and local-only: it checks repository files, docs, tests, eval/red-team/demo commands, CI presence, API smoke coverage, artifact coverage, runtime mode, and publish readiness without calling paid OpenAI, Azure, or Qdrant services.

```bash
curl -X GET "http://127.0.0.1:8000/release/quality-gate" \
  -H "X-API-Key: local-demo-key"
```

The response includes `status`, `score`, `blockers`, `warnings`, `verification_checklist`, `coverage`, `artifact_coverage`, `runtime_notes`, `publish_readiness`, and `trace_id`. Coverage includes CI, docs, tests, standard eval, red-team, demo, API endpoint count, release endpoint presence, artifact endpoint count, and local-only runtime notes.

### `POST /release/publish-pack`

Writes Markdown and JSON GitHub Publish Pack artifacts under ignored `storage/release_packs/` by default.

```json
{
  "write_artifact": true
}
```

The pack includes release summary, setup/demo commands, verification commands, expected outputs, endpoint inventory, artifact inventory, screenshot/manual verification placeholders, GitHub repo checklist, commit/push readiness notes, recruiter review notes, known limitations, embedded quality gate details, Markdown, JSON, and trace ID.

### `GET /ops/verification-evidence`

Returns the local Verification Evidence Ledger. It rolls up the required acceptance commands (`pytest`, `ruff`, standard eval, red-team eval, dashboard smoke, and demo), Release Candidate gate, Final Handoff audit, dashboard smoke, artifact inventory, reviewer signoff rows, proof commands, limitations, and trace ID. The endpoint does not execute shell commands.

### `POST /ops/verification-evidence`

Returns the same ledger with optional reviewer-supplied `command_results` so observed terminal summaries can be captured after local verification.

```bash
curl -X POST "http://127.0.0.1:8000/ops/verification-evidence" \
  -H "X-API-Key: local-demo-key" \
  -H "Content-Type: application/json" \
  -d '{"command_results":[{"command_id":"pytest","status":"pass","observed_output":"all tests passed"}]}'
```

### `POST /ops/verification-evidence-pack`

Writes Markdown and JSON Verification Evidence Pack artifacts under ignored `storage/verification_evidence/` by default. The pack captures command evidence rows, release/final/dashboard/artifact snapshots, reviewer controls, local proof commands, limitations, and artifact paths.

### `GET /reviewer/quickstart`

Returns the Reviewer Quickstart runbook for a GitHub reviewer. It is local/mock by default and includes exact setup commands, one-command demo, verification commands, endpoint walkthrough order, RAG/RFP workflow walkthrough, artifact proof map, expected outputs, troubleshooting, role-specific reviewer notes, proof tour, GitHub README blurb, and trace ID.

```bash
curl -X GET "http://127.0.0.1:8000/reviewer/quickstart" \
  -H "X-API-Key: local-demo-key"
```

The response includes `status`, `provider_mode`, `vector_store_mode`, `exact_local_setup_commands`, `one_command_demo`, `verification_commands`, `endpoint_walkthrough_order`, `rag_rfp_workflow_walkthrough`, `artifact_proof_map`, `expected_outputs`, `troubleshooting`, `role_specific_reviewer_notes`, `proof_tour`, `github_readme_blurb`, and `trace_id`.

### `POST /reviewer/walkthrough-pack`

Writes Markdown and JSON Walkthrough Pack artifacts under ignored `storage/reviewer_packs/` by default.

```json
{
  "write_artifact": true
}
```

The Walkthrough Pack includes a recruiter-friendly story, engineer deep-dive path, command checklist, API/RAG proof tour, endpoint order, RAG/RFP workflow walkthrough, artifacts to inspect, expected outputs, limitations, role-specific reviewer notes, GitHub README blurb, storage snapshot, Markdown, JSON, and trace ID.

### `GET /handoff/final-audit`

Returns the README Consistency final audit. The audit checks README endpoint mentions, docs/API coverage, architecture/evaluation coverage, demo output claims, required scripts, Dashboard Smoke script presence, generated artifact directory docs, RAG/eval/red-team/local mock limitation clarity, and Azure optional notes.

```bash
curl -X GET "http://127.0.0.1:8000/handoff/final-audit" \
  -H "X-API-Key: local-demo-key"
```

The response uses `FinalAuditResponse` and includes `status`, `score`, structured `checks`, `summary`, `endpoint_inventory`, `artifact_inventory`, exact `local_verification_commands`, `limitations`, `generated_at`, and `trace_id`.

### `POST /handoff/final-pack`

Writes Markdown and JSON Final Handoff artifacts under ignored `storage/final_handoff/` by default.

```json
{
  "write_artifact": true
}
```

The response uses `FinalPackResponse` and includes `artifact_path`, `json_artifact_path`, `markdown`, structured `pack`, embedded `final_audit`, and `trace_id`. The pack includes final audit results, exact clone/run commands, end-to-end verification order, endpoint inventory summary, artifact inventory summary, dashboard smoke summary, RAG/eval proof summary, recruiter-facing final README blurb, limitations, Markdown, and JSON.

### `POST /documents/ingest`

Ingests a local fixture path.

```json
{
  "fixture_path": "sample_data/security_policy.md",
  "document_type": "knowledge_base",
  "source": "sample_data",
  "tags": ["security"]
}
```

### `GET /documents`

Lists processed documents.

### `POST /rfp/analyze`

Analyzes text, an ingested RFP document ID, or a fixture path.

```json
{
  "fixture_path": "sample_data/acme_enterprise_rfp.md"
}
```

### `POST /rfp/query`

Answers a question using cited source evidence.

```json
{
  "question": "What SSO and encryption controls are supported?",
  "top_k": 4
}
```

### `POST /rfp/draft-response`

Generates response sections grounded in retrieved citations.

```json
{
  "section_names": [
    "Executive Summary",
    "Technical Response",
    "Security Response",
    "Compliance Response"
  ],
  "top_k": 5
}
```

### `POST /rfp/requirement-matrix`

Builds a deterministic local workbench matrix from an analyzed RFP payload or an ingested RFP document ID. Each row includes `requirement_id`, `category`, `requirement_text`, `priority`, `owner_role`, `status`, `risk_level`, `evidence_refs`, `suggested_response`, and `missing_evidence`.

```json
{
  "analyzed_payload": {
    "requirements": [],
    "deadlines": [],
    "trace_id": "analysis-trace"
  }
}
```

Statuses are `not_started`, `evidence_found`, `needs_review`, and `blocked`.

### `GET /customers/profiles`

Lists local fake customer profiles used for customer-specific fit and response memory demos.

```json
{
  "profiles": [
    {
      "id": "regulated_healthcare",
      "industry": "healthcare",
      "region": "United States",
      "security_priorities": ["PHI protection", "SSO and MFA"],
      "compliance_frameworks": ["HIPAA", "SOC 2 Type II"],
      "buyer_personas": ["Chief Information Security Officer"],
      "risk_tolerance": "low"
    }
  ]
}
```

### `POST /rfp/customer-fit`

Maps analyzed requirements or requirement matrix rows to one selected customer profile. The response includes `fit_score`, `profile_risks`, `recommended_positioning`, `requirements_to_emphasize`, and `requirements_needing_review`.

```json
{
  "customer_profile_id": "regulated_healthcare",
  "analyzed_payload": {},
  "requirement_matrix": []
}
```

### `POST /rfp/response-memory/search`

Searches local approved response snippets from `sample_data/approved_responses.json`. Results include reusable text, tags, citations, applicable profile IDs, and confidence.

```json
{
  "query": "SSO encryption SOC 2 controls",
  "category": "security",
  "customer_profile_id": "regulated_healthcare",
  "top_k": 5
}
```

### `POST /rfp/answer-reuse-library`

Builds the governed Answer Reuse Library from accepted local snippets. The response includes owner, expiry, approval status, reuse decision, confidence, citation lineage, owner queue, endpoint references, proof commands, and limitations.

```json
{
  "category": "security",
  "customer_profile_id": "regulated_healthcare",
  "include_expired": true
}
```

### `POST /rfp/answer-reuse-library-pack`

Writes a Markdown and JSON Answer Reuse Library Pack under `storage/answer_reuse_library/`. The pack converts accepted answers into governed reusable snippets with reviewer checklist, owner queue, expiry state, source files, and citation lineage.

```json
{
  "category": "security",
  "customer_profile_id": "regulated_healthcare",
  "write_artifact": true
}
```

### `POST /rfp/answer-reuse-drift`

Checks governed reusable snippets against their cited source text and returns drift findings with source overlap, stale claim terms, owner routing, checkpoint keys, and a replayable state-machine transition trace.

```json
{
  "category": "security",
  "customer_profile_id": "regulated_healthcare",
  "include_expired": true,
  "min_source_overlap": 4
}
```

### `POST /rfp/answer-reuse-drift-pack`

Writes a Markdown and JSON Answer Reuse Drift Pack under `storage/answer_reuse_drift/`. The pack documents reusable-answer drift status, owner queues, checkpointed workflow states, proof commands, and limitations.

```json
{
  "category": "security",
  "customer_profile_id": "regulated_healthcare",
  "min_source_overlap": 4,
  "write_artifact": true
}
```

### `POST /rfp/answer-reuse-approval-ledger`

Turns reusable-answer drift findings into durable local approval records. The response includes approval decisions, required approvers, human review queue, checkpointed transitions, trace spans, governance policy, proof commands, and limitations.

```json
{
  "category": "security",
  "customer_profile_id": "regulated_healthcare",
  "requested_by": "proposal_manager",
  "approver_overrides": {
    "resp_sso_001": "approve"
  }
}
```

### `POST /rfp/answer-reuse-approval-pack`

Writes a Markdown and JSON Answer Reuse Approval Pack under `storage/answer_reuse_approvals/`. The pack documents human-in-the-loop approval gates, owner checkpoints, trace spans, and final reusable-answer decisions.

```json
{
  "customer_profile_id": "regulated_healthcare",
  "write_artifact": true
}
```

### `POST /rfp/export-package`

Creates an interview-ready response package from an analyzed RFP payload or ingested RFP document ID plus an optional draft response. By default, artifacts are written under `storage/exports/` and the response also includes Markdown and structured JSON.

```json
{
  "analyzed_payload": {},
  "draft_response": {},
  "customer_profile_id": "regulated_healthcare",
  "include_response_memory": true,
  "write_artifact": true
}
```

The package includes executive summary, requirement matrix, optional customer fit, optional approved response memory matches, drafted sections, citations, risks, missing evidence, and eval/usage summary.

### `POST /rfp/review-answer`

Reviews one answer for unsupported claims, weak citations, missing evidence, and cost/latency warnings.

```json
{
  "question": "Can we guarantee FedRAMP High next month?",
  "answer_text": "Yes, FedRAMP High is guaranteed.",
  "citations": [],
  "missing_evidence": [],
  "token_usage": {
    "input_tokens": 18,
    "output_tokens": 8,
    "estimated_cost": 0
  }
}
```

The response includes `findings`, `passed`, `summary`, and `trace_id`. Findings include `finding_id`, `severity`, `category`, `message`, `related_requirement_id`, `related_question`, `citation_refs`, and `recommendation`.

Review categories are `unsupported_claim`, `weak_citation`, `missing_evidence`, `high_risk_requirement`, and `cost_latency_warning`.

### `POST /rfp/review-package`

Reviews a requirement matrix, draft response, answer payloads, and/or export package. If the request includes `analyzed_payload` or `rfp_document_id`, the API can create the requirement matrix and draft/export payload locally before review.

```json
{
  "analyzed_payload": {},
  "draft_response": {},
  "write_artifact": false
}
```

The response includes the review report, the reviewed requirement matrix, optional export package JSON, and optional artifact path.

### `POST /rfp/reviewer-collaboration`

Creates a local reviewer collaboration board with named reviewer assignments, decision comments, approval statuses, reviewer queue, and a redline summary. The endpoint accepts the same workflow signals used elsewhere: analyzed payload, requirement matrix, draft response, review findings, action plan, evidence gaps, contract risk, and submission decision. If called with `{}`, it uses the local sample RFP and contract terms.

```json
{
  "analysis": {},
  "matrix": [],
  "draft_response": {},
  "review_findings": [],
  "action_plan": [],
  "evidence_gaps": [],
  "contract_risk": {},
  "review_passed": false
}
```

The response includes `board_status`, `assignments`, `decision_comments`, `approval_summary`, `redline_summary`, `reviewer_queue`, local proof commands, limitations, and `trace_id`.

### `POST /rfp/reviewer-collaboration-pack`

Writes the reviewer collaboration board as Markdown and JSON under `storage/review_boards/`.

```json
{
  "write_artifact": true
}
```

The pack is intended for local review-board artifacts: owner assignments, approval status, decision comments, contract/draft redlines, proof commands, and known limitations.

### `POST /rfp/reviewer-workflow`

Builds a deterministic reviewer workflow replay from a collaboration board. The workflow uses typed checkpoints and traceable transitions for intake, role routing, decision-comment triage, redline gate, approval gate, and final release or blocker-resolution state. If called with `{}`, it derives the local sample RFP collaboration board first.

```json
{
  "collaboration": {}
}
```

The response includes `workflow_status`, `current_state`, `checkpoints`, `transitions`, `approval_path`, replay notes, local proof commands, limitations, and `trace_id`.

### `POST /rfp/reviewer-workflow-pack`

Writes the reviewer workflow replay as Markdown and JSON under `storage/review_boards/`.

```json
{
  "write_artifact": true
}
```

The pack is intended for local review-board governance: checkpoint status, blocked state, transition trace notes, approval path, replay notes, proof commands, and known limitations.

### `POST /rfp/reviewer-signoff-ledger`

Builds a local reviewer signoff readiness ledger from a collaboration board and workflow replay. The ledger captures each reviewer role, outstanding blockers, decision-comment references, policy gates, human review queue items, and a transition log. It supports optional `signoff_overrides` for explicit local review inputs, but it does not claim those are real external approvals.

```json
{
  "collaboration": {},
  "workflow": {},
  "signoff_overrides": [
    {
      "reviewer_role": "sales",
      "approval_status": "approved",
      "signed_by": "Ava Sales Lead",
      "evidence_note": "Sales reviewed the local submission context."
    }
  ]
}
```

The response includes `ledger_status`, `records`, `summary`, `workflow_snapshot`, `governance_gates`, `human_review_queue`, `transition_log`, proof commands, limitations, and `trace_id`.

### `POST /rfp/reviewer-signoff-pack`

Writes the reviewer signoff ledger as Markdown and JSON under `storage/reviewer_signoffs/`.

```json
{
  "write_artifact": true
}
```

The pack is intended for local review-board evidence: signoff readiness, durable workflow replay context, named policy gates, outstanding owner actions, transition history, proof commands, and limitations.

### `POST /rfp/exception-register`

Creates a local submission exception register from a submission decision plus optional reviewer collaboration board. If called with `{}`, the endpoint derives sample RFP signals locally. Each exception has a waiver type, severity, owner, approver, expiry date, required evidence, linked requirements/artifacts, risk acceptance text, and escalation path.

```json
{
  "submission_decision": {},
  "reviewer_collaboration": {}
}
```

The response includes `register_status`, `exceptions`, `summary`, `approval_queue`, endpoint references, proof commands, limitations, and `trace_id`.

### `POST /rfp/exception-pack`

Writes the submission exception register as Markdown and JSON under `storage/exception_registers/`.

```json
{
  "write_artifact": true
}
```

The pack is intended for local approval review of unresolved blockers, conditional exceptions, reviewer comments, and redline waivers.

### `POST /rfp/action-plan`

Creates deterministic stakeholder tasks from analyzed requirements, a requirement matrix, customer profile or customer fit, and review findings. Owner roles are `sales`, `solutions`, `security`, `legal`, `product`, and `engineering`.

```json
{
  "analyzed_payload": {},
  "requirement_matrix": [],
  "customer_profile_id": "regulated_healthcare",
  "customer_fit": {},
  "review_findings": []
}
```

Each task includes `task_id`, `owner_role`, `title`, `description`, `priority`, `due_hint`, `source_requirement_id`, `risk_level`, `status`, and `evidence_refs`. The summary includes task counts by owner, status, and priority.

### `POST /rfp/handoff-board`

Exports a cross-functional handoff board as Markdown and JSON under `storage/handoffs/` by default. The board includes the action plan, blocked items, high-risk requirements, customer-fit notes, missing evidence, review findings, and next meeting agenda.

```json
{
  "analyzed_payload": {},
  "requirement_matrix": [],
  "customer_profile_id": "regulated_healthcare",
  "review_findings": [],
  "action_plan": [],
  "write_artifact": true
}
```

The response includes `artifact_path`, `json_artifact_path`, `markdown`, `board`, and `trace_id`.

### `POST /rfp/readiness-scorecard`

Creates a deterministic local deal readiness scorecard from any combination of analyzed RFP payload, requirement matrix, review findings, customer fit, stakeholder action plan, and optional standard eval metrics. If `analysis` is provided without `matrix`, the API creates a requirement matrix locally before scoring.

```json
{
  "analysis": {},
  "matrix": [],
  "review_findings": [],
  "customer_fit": {},
  "action_plan": [],
  "eval_metrics": {}
}
```

The response includes `readiness_score` from 0 to 100, `readiness_level`, `blockers`, `evidence_coverage`, `review_risk_count`, `customer_fit_score`, `owner_bottlenecks`, `score_trace`, `approval_workflow`, `human_review_queue`, `governance_summary`, `recommended_next_actions`, and `trace_id`.

Scoring is deterministic. It starts at 100 and applies fixed penalties for blocked rows, high-risk rows, missing evidence, evidence coverage gaps, high-severity review findings, low customer fit, concentrated owner bottlenecks, failed evals, and low eval citation coverage. The score trace explains each deduction, while the approval workflow exposes durable checkpoint IDs and human-in-the-loop exception gates for local reviewer replay.

### `POST /rfp/executive-risk-report`

Writes a leadership-ready Markdown/JSON risk report under `storage/reports/` by default. It accepts the same inputs as the readiness scorecard plus an optional `red_team_summary` object and `write_artifact` flag.

```json
{
  "analysis": {},
  "matrix": [],
  "review_findings": [],
  "customer_fit": {},
  "action_plan": [],
  "eval_metrics": {},
  "red_team_summary": {
    "passed": true,
    "missing_evidence_detection_count": 3
  },
  "write_artifact": true
}
```

The report includes readiness score and level, top blockers, evidence coverage, missing-evidence count, owner bottlenecks, customer fit, red-team summary, review-risk summary, action-plan summary, and `submission_recommendation`.

The response includes `artifact_path`, `json_artifact_path`, `markdown`, `report`, and `trace_id`.

### `POST /rfp/proposal-readiness-score-pack`

Writes Markdown/JSON Proposal Readiness Score Pack artifacts under `storage/readiness_packs/` by default. It accepts the same inputs as `/rfp/executive-risk-report` plus an optional `draft_response`, precomputed `readiness_scorecard`, and precomputed `executive_report`.

```json
{
  "analysis": {},
  "matrix": [],
  "draft_response": {},
  "review_findings": [],
  "action_plan": [],
  "eval_metrics": {},
  "red_team_summary": {
    "passed": true
  },
  "write_artifact": true
}
```

The pack includes the base readiness scorecard, section completeness by proposal section, evidence coverage by category, compliance/security/privacy risk, reviewer bottleneck routing, score trace analysis, durable approval workflow checkpoints, human-review queue items, governance controls, executive artifact links, endpoint references, local proof commands, limitations, Markdown, JSON, and trace ID.

### `POST /rfp/win-strategy`

Creates a deterministic competitive win strategy simulation from local RFP analysis, requirement matrix rows, customer fit, readiness scorecard, response memory, action-plan tasks, review findings, competitor context, and pricing notes. If the request is `{}` in local demo mode, the endpoint analyzes the sample RFP and uses the default regulated healthcare profile.

```json
{
  "analysis": {},
  "matrix": [],
  "customer_profile_id": "regulated_healthcare",
  "readiness_scorecard": {},
  "response_memory_matches": [],
  "action_plan": [],
  "review_findings": [],
  "competitor_context": [
    "Incumbent competitor may bundle workflow tooling and offer a discount."
  ],
  "pricing_notes": [
    "Route volume discounts, custom packaging, and public-sector terms for approval."
  ]
}
```

The response includes `win_score`, `win_level`, `competitor_risk_profile`, `pricing_risk`, `compliance_security_differentiators`, cited `proof_points` with source snippets, `recommended_response_posture`, `red_flags`, `assumptions`, owner-specific `next_actions_by_owner`, and `trace_id`.

### `POST /rfp/pricing-risk-memo`

Writes a Markdown and JSON pricing risk memo under `storage/pricing_memos/` by default. The endpoint accepts the same inputs as `/rfp/win-strategy` plus an optional precomputed `win_strategy` response and `write_artifact` flag.

```json
{
  "analysis": {},
  "matrix": [],
  "customer_profile_id": "regulated_healthcare",
  "competitor_context": [
    "Incumbent competitor is cheaper, bundled, and offering a 25% discount."
  ],
  "pricing_notes": [
    "Any volume discount or custom enterprise tier needs approval."
  ],
  "write_artifact": true
}
```

The memo includes pricing assumptions, discount/packaging risks, compliance blockers, competitor framing, cited proof points, leadership recommendation, exact local commands, JD skills demonstrated, and five interviewer talking points. The response includes `artifact_path`, `json_artifact_path`, `markdown`, `memo`, and `trace_id`.

### `POST /rfp/objection-handling`

Generates deterministic, cited objection responses for competitor, pricing, security, compliance, and implementation concerns. If called with `{}` in local demo mode, the endpoint analyzes the sample RFP, builds the requirement matrix, creates win-strategy context, and retrieves local evidence from the ingested/sample corpus.

```json
{
  "analysis": {},
  "matrix": [],
  "customer_profile_id": "regulated_healthcare",
  "competitor_context": [
    "Incumbent competitor is cheaper and bundling workflow tooling."
  ],
  "pricing_notes": [
    "Route discounts, payment terms, and custom packaging for approval."
  ],
  "objection_notes": [
    "Customer asks why they should not choose the cheaper bundled competitor."
  ],
  "top_k": 4
}
```

The response includes objection records by `concern_type`, buyer objection text, competitor angle, response posture, cited response, confidence, risk level, approval status, required reviewer role, citations, source snippets, missing evidence, recommended follow-ups, workflow checkpoint keys, route decisions, replayable state transitions, eval assertions, endpoint references, local proof commands, and limitations.

### `POST /rfp/objection-handling-pack`

Writes Markdown and JSON Competitive Objection Handling Pack artifacts under `storage/objection_packs/` by default. The endpoint accepts the same inputs as `/rfp/objection-handling` plus an optional precomputed `objection_handling` response and `write_artifact` flag.

```json
{
  "competitor_context": [
    "Incumbent competitor is cheaper and bundling workflow tooling."
  ],
  "write_artifact": true
}
```

The pack includes a summary, all cited objection responses, high-risk objections, reviewer workflow, workflow transition replay, checkpoint keys, route decisions, eval assertions, endpoint references, proof commands, limitations, and artifact paths.

### `POST /rfp/contract-risk`

Analyzes customer contract or procurement terms from pasted `text`, an ingested `contract_document_id`, or a local `fixture_path`. The deterministic analyzer flags liability, data processing, security obligations, SLA/service credits, audit rights, termination, indemnity, data residency, AI/data use, and pricing/payment risks.

```json
{
  "fixture_path": "sample_data/customer_contract_terms.md",
  "customer_profile_id": "regulated_healthcare"
}
```

The response includes `risk_score`, `status`, risky clauses, category counts, suggested redlines, fallback positions, cited internal proof points with source snippets, owner actions, assumptions, missing-evidence warnings, and `trace_id`.

### `POST /rfp/negotiation-brief`

Writes a Markdown and JSON Contract Redline Risk Analyzer + Negotiation Brief under `storage/negotiation_briefs/` by default. The endpoint can accept a precomputed `contract_risk` response or compute one from `text`, `contract_document_id`, or `fixture_path`. Optional `win_strategy` and `pricing_memo` payloads are folded into the negotiation context when supplied.

```json
{
  "fixture_path": "sample_data/customer_contract_terms.md",
  "customer_profile_id": "regulated_healthcare",
  "write_artifact": true
}
```

The brief includes contract risk summary, win strategy/pricing context, clause-by-clause redlines, owner actions, cited proof points, assumptions, exact local commands, JD skills demonstrated, and five interviewer talking points. The response includes `artifact_path`, `json_artifact_path`, `markdown`, `brief`, and `trace_id`.

### `POST /rfp/evidence-gaps`

Returns a prioritized Evidence Gap Remediation Planner from any combination of RFP analysis, requirement matrix, review findings, red-team summary, readiness scorecard, win strategy, contract risk, and action-plan tasks. If called with `{}` in local demo mode, it analyzes the sample RFP and sample contract terms.

```json
{
  "analysis": {},
  "matrix": [],
  "review_findings": [],
  "red_team_summary": {
    "passed": false,
    "missing_evidence_detection_count": 2
  },
  "readiness_scorecard": {},
  "win_strategy": {},
  "contract_risk": {},
  "action_plan": []
}
```

Each gap includes `gap_id`, `priority_rank`, impacted RFP/contract sections, `missing_source_type`, `owner_team`, `severity`, `due_date_recommendation`, suggested SME/source request, related citations, red-team risks, source signals, and closure acceptance criteria.

### `POST /rfp/source-request-pack`

Writes Markdown and JSON under `storage/source_requests/` by default. The endpoint accepts the same inputs as `/rfp/evidence-gaps` plus optional precomputed `evidence_gaps` and `write_artifact`.

```json
{
  "analysis": {},
  "matrix": [],
  "review_findings": [],
  "contract_risk": {},
  "evidence_gaps": [],
  "write_artifact": true
}
```

The source request pack includes source request emails/tasks, owner matrix, acceptance criteria, impacted response sections, red-team risks, readiness/win/contract context, exact local commands, JD skills demonstrated, and five interviewer talking points. The response includes `artifact_path`, `json_artifact_path`, `markdown`, `pack`, and `trace_id`.

### `POST /rfp/timeline-plan`

Creates a deterministic Proposal Timeline Orchestrator plan from RFP deadlines, requirement matrix rows, stakeholder tasks, evidence gaps, contract risk, win strategy, readiness scorecard, source request pack, leadership brief, review findings, and red-team summary. If called with `{}` in local demo mode, it analyzes the sample RFP and composes local signals without calling Google Calendar, Microsoft Graph, Azure, CRM, or external workflow tools.

```json
{
  "analysis": {},
  "matrix": [],
  "action_plan": [],
  "evidence_gaps": [],
  "contract_risk": {},
  "win_strategy": {},
  "readiness_scorecard": {},
  "source_request_pack": {},
  "leadership_brief": {}
}
```

The response includes ordered `milestones`, `owner_assignments`, dependency edges, `risk_buffers`, `blocked_items`, `readiness_gates`, `escalation_triggers`, local `calendar_entries`, summary counts, and trace ID.

### `POST /rfp/submission-calendar-pack`

Writes a Markdown and JSON Submission Calendar Pack under `storage/submission_calendars/` by default. The endpoint accepts the same inputs as `/rfp/timeline-plan` plus an optional precomputed `timeline_plan` and `write_artifact` flag.

```json
{
  "analysis": {},
  "matrix": [],
  "timeline_plan": {},
  "write_artifact": true
}
```

The pack includes a milestone calendar, owner matrix, dependencies and risk buffers, blocked items, readiness gates, escalation triggers, local calendar-friendly entries, exact local commands, JD skills demonstrated, and five interviewer talking points. The response includes `artifact_path`, `json_artifact_path`, `markdown`, `pack`, and `trace_id`.

### `POST /rfp/submission-decision`

Creates the final deterministic Proposal Quality Gate for sales leadership. It consolidates readiness score, review-board findings, eval/red-team summaries, win strategy, contract risk, evidence gaps, source request pack, timeline plan, draft sections, citations, owner status, artifact links, and metrics. If called with `{}` in local demo mode, the endpoint analyzes the sample RFP and composes local fallback inputs.

```json
{
  "analysis": {},
  "matrix": [],
  "draft_response": {},
  "review_findings": [],
  "readiness_scorecard": {},
  "win_strategy": {},
  "contract_risk": {},
  "evidence_gaps": [],
  "source_request_pack": {},
  "timeline_plan": {}
}
```

The response includes `decision` (`submit`, `submit_with_exceptions`, or `do_not_submit`), `score`, `blocking_issues`, `exception_list`, `approvals_required`, `owner_actions`, `artifact_links`, `rationale`, `local_verification_commands`, `summary`, and `trace_id`.

### `POST /rfp/executive-submission-memo`

Writes Markdown and JSON under `storage/submission_memos/` by default. It accepts the same inputs as `/rfp/submission-decision`, or a precomputed `submission_decision`, plus `write_artifact`.

```json
{
  "submission_decision": {},
  "write_artifact": true
}
```

The memo includes go/no-go summary, risks/exceptions, evidence posture, owner sign-offs, timeline readiness, artifact links, local commands, JD skills demonstrated, and five interviewer talking points. The response includes `artifact_path`, `json_artifact_path`, `markdown`, `memo`, and `trace_id`.

### `POST /rfp/leadership-brief`

Writes a consolidated portfolio demo and RFP leadership brief under `storage/leadership_briefs/` by default. The endpoint can accept completed local artifacts or run missing deterministic steps from an RFP document, analysis, or matrix.

```json
{
  "analysis": {},
  "matrix": [],
  "draft_response": {},
  "export_payload": {},
  "export_artifact_path": "storage/exports/rfp_export_demo.md",
  "review_findings": [],
  "review_passed": true,
  "customer_profile_id": "regulated_healthcare",
  "action_plan": [],
  "handoff_board": {},
  "readiness_scorecard": {},
  "executive_report": {},
  "red_team_summary": {
    "passed": true
  },
  "write_artifact": true
}
```

The brief includes `metrics` for docs ingested, requirements, evidence coverage, citation count, red-team pass, customer fit score, task counts, readiness score, and readiness level. It also includes `artifact_links` for RFP analysis, matrix, draft, export, review, red-team, customer fit, response memory, action plan, handoff, readiness, and executive report artifacts, plus a recommended next meeting agenda.

The response includes `artifact_path`, `json_artifact_path`, `markdown`, `brief`, and `trace_id`.

### `POST /rfp/submission-regression`

Runs the deterministic local submission readiness regression gate. The service composes existing in-process services rather than shelling out: sample ingestion, RFP analysis, requirement matrix coverage, cited Q&A, missing-evidence behavior, draft generation, answer/package review, customer fit, response memory, action plan, handoff board, standard eval, red-team checks, readiness scorecard, executive risk report, leadership brief, submission decision memo, metrics, and audit signals.

```json
{
  "rfp_fixture_path": "sample_data/acme_enterprise_rfp.md",
  "eval_dataset_path": "sample_data/eval_dataset.json",
  "red_team_dataset_path": "sample_data/red_team_questions.json",
  "customer_profile_id": "regulated_healthcare",
  "top_k": 4,
  "write_artifacts": true
}
```

The response includes:

- `passed`: whether all named regression checks passed.
- `checks`: named checks with `passed`, `evidence_count`, and deterministic details.
- `evidence_counts`: document, requirement, matrix, citation, review, task, eval, red-team, readiness, metric, and audit counts.
- `failed_checks`: names of any failed checks.
- `warnings`: non-failing readiness caveats, such as detected missing-evidence risk.
- `artifact_paths`: export, handoff, executive report, leadership brief, and submission memo Markdown/JSON paths.
- `eval_summary`: the standard `EvaluationMetrics` object.
- `red_team_summary`: deterministic red-team pass/fail and finding details.
- `interview_ready_summary`: concise summary suitable for demo narration.

### `POST /rfp/demo-script`

Writes a Markdown and JSON interview/demo script under `storage/demo_scripts/`. If no regression payload is supplied, the endpoint runs a fresh submission regression first.

```json
{
  "run_regression": true,
  "regression_request": {
    "top_k": 4,
    "customer_profile_id": "regulated_healthcare",
    "write_artifacts": true
  },
  "write_artifact": true
}
```

To generate a script from an already returned regression response:

```json
{
  "regression": {},
  "run_regression": false,
  "write_artifact": true
}
```

The script includes business pain, architecture walk-through, exact local commands, endpoints exercised, sample outputs and metrics, JD skills demonstrated, five interviewer talking points, artifact paths, Markdown, JSON, and trace ID.

### `GET /portfolio/evidence-index`

Returns the structured Portfolio Evidence index. Each skill row maps a recruiter/interviewer JD skill to implemented features, endpoints, service files, tests/evals, generated artifacts, demo commands, and local proof paths.

The response includes `evidence_score`, `covered_skill_count`, `total_skill_count`, `skills`, `proof_commands`, `artifact_roots`, `limitations`, and `trace_id`. It covers RAG/Qdrant/FAISS, document ingestion, citations and missing evidence, draft generation, eval/red-team, compliance mapping, Procurement Q&A approval workflow, requirement matrix, review board, action plan, handoff, readiness/risk, win/pricing/contract risk, source requests, timeline/submission calendar, go/no-go submission decision, launch checklist, observability, metrics, audit, API auth, and the portfolio pack itself.

### `POST /portfolio/interview-pack`

Writes a Markdown and JSON Interview Pack under `storage/portfolio_packs/`. By default it runs the local submission regression first so the pack includes current eval and red-team metrics.

```json
{
  "run_regression": true,
  "regression_request": {
    "top_k": 4,
    "write_artifacts": true
  },
  "write_artifact": true
}
```

The pack includes a 3-minute demo script, 8-10 technical talking points, architecture walk-through, failure/missing-evidence story, local verification commands, metrics/eval summary, artifact inventory, resume/GitHub README bullets, Markdown, JSON, and trace ID.

### Reviewer Quickstart Curl Pair

Use this pair when the API is already running and a reviewer wants the fastest proof tour:

```bash
curl -X GET "http://127.0.0.1:8000/reviewer/quickstart" -H "X-API-Key: local-demo-key"
curl -X POST "http://127.0.0.1:8000/reviewer/walkthrough-pack" -H "X-API-Key: local-demo-key" -H "Content-Type: application/json" -d "{}"
```

### `POST /rfp/evaluate`

Runs the eval dataset against the current corpus.

```json
{
  "dataset_path": "sample_data/eval_dataset.json",
  "top_k": 4
}
```

### `GET /metrics/usage`

Returns recent usage metrics and totals.

### `GET /audit/events`

Returns recent audit events.

### `GET /git/readiness`

Returns local GitHub Push Readiness and Branch Hygiene checks: repository detection, current branch, tracked/untracked/modified/ignored counts, generated artifact directories that should stay ignored, changed source/doc/test/dashboard groups, suspicious large/generated files, GitHub Actions workflow presence, README final handoff mention, `.env.example` presence, dirty-worktree guidance, recommended commit groups, commands, and limitations.

### `POST /git/push-plan`

Writes Markdown/JSON under ignored `storage/git_packs/` with non-destructive review commands, suggested commit grouping, do-not-commit generated artifact notes, pre-push verification checklist, repo limitations, and a recruiter/GitHub README publish blurb. It never stages, commits, pushes, resets, checks out, cleans, deletes, or calls GitHub APIs.

## Error Handling

Unsupported questions return low confidence and a `missing_evidence` warning rather than inventing unsupported claims. Authentication failures return `401`.
