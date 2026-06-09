# Architecture

## Objective

The RFP Response Intelligence Copilot helps sales and presales teams turn approved enterprise source material into grounded RFP/RFI answers, reviewer-ready artifacts, and final submission decisions. The system is local-first for portfolio review: it runs with deterministic mock AI by default, keeps generated artifacts under ignored `storage/`, and documents every major claim with repeatable commands.

## Runtime Components

- FastAPI app: authenticated JSON API for ingestion, retrieval, answering, drafting, analysis, evaluation, release checks, artifact generation, and final handoff.
- Service layer: explicit business services behind `ServiceContainer`, so API routes stay thin and workflow logic remains testable.
- Provider layer: `BaseLLMProvider` supports deterministic `MockLLMProvider` locally plus optional OpenAI and Azure OpenAI adapters.
- Vector layer: `BaseVectorStore` supports local fallback search and the Qdrant adapter surface for production-like vector retrieval.
- Repository layer: in-memory local state for tests and demos, with audit and usage records persisted as JSONL under `storage/`.
- Dashboard: Streamlit workbench that exercises the API workflows and mirrors the reviewer story.
- CLI scripts: deterministic standard eval, red-team eval, dashboard smoke, runtime check, and demo flows.

## Core Workflow

1. A client sends `X-API-Key`.
2. `TraceIdMiddleware` creates or propagates `X-Trace-Id`.
3. Routes delegate through `ServiceContainer`.
4. Ingestion parses approved sample documents, chunks text, stores metadata, and indexes retrieval vectors.
5. Retrieval ranks evidence, applies relevance gates, and returns citations with snippets and scores.
6. Generation, analysis, or artifact services transform the evidence into a typed API response.
7. Metrics and audit events are written for traceability.
8. Generated Markdown/JSON artifacts are written under ignored `storage/` directories.

## Service Map

- `DocumentIngestionService`: parses PDF/TXT/Markdown, chunks content, stores metadata, and indexes vectors.
- `RetrievalService`: searches the vector store, gates weak matches, and returns cited evidence.
- `RfpAnalysisService`: extracts requirements, risks, deadlines, compliance asks, pricing mentions, and missing information.
- `DraftGenerationService`: answers questions and drafts response sections with citations and confidence.
- `EvaluationService`: measures retrieval precision, citation coverage, missing-evidence detection, latency, tokens, and cost.
- `CustomerIntelligenceService`: scores customer profile fit and account-specific response posture.
- `RequirementMatrixService` behavior: requirement rows flow through API/domain models and export workflows.
- `ReviewBoardService`: produces reviewer findings and red-team style concerns for response quality.
- `ActionPlanService`: turns requirements, gaps, and review findings into stakeholder tasks.
- `DealReadinessService`: scores launch readiness, executive risk, and blockers.
- `WinStrategyService`: simulates competitor posture, pricing risk, and pursuit strategy.
- `ContractRiskService`: identifies risky customer terms and writes negotiation briefs.
- `EvidenceGapService`: produces source request packs for unsupported claims.
- `TimelineOrchestrationService`: creates proposal milestones and submission calendar packs.
- `SubmissionDecisionService`: builds final go/no-go scores and executive memos.
- `LeadershipBriefService`: consolidates portfolio-level readouts for recruiters and stakeholders.
- `RuntimeDemoService`: writes a Runtime Demo Server Pack for local verification.
- `CorpusCoverageService`: proves RAG corpus coverage and eval coverage artifacts.
- `ComplianceService`: maps regulated-enterprise controls to evidence.
- `ProcurementService`: simulates procurement question risk and approval workflow artifacts.
- `BidSimulatorService`: runs bid/no-bid scenarios with risk-adjusted ROI math.
- `PortfolioService`: builds the Portfolio Evidence index and interview pack.
- `ReviewerService`: generates reviewer quickstart and walkthrough packs.
- `ApiContractsService`: snapshots OpenAPI routes and reviewer collection artifacts.
- `ReleaseService`: creates release candidate quality gates and GitHub publish packs.
- `ArtifactInventoryService`: indexes generated artifact directories and README checklist artifacts.
- `UiVerificationService`: verifies dashboard wiring and writes UI verification packs.
- `GitReadinessService`: checks local git status, remote, auth posture, and publish readiness.
- `FinalHandoffService`: runs the README Consistency final audit and writes the Final Handoff Pack.

## Final Handoff

The final release layer is intentionally explicit. `FinalHandoffService` checks that README claims, API docs, architecture/evaluation docs, demo output, scripts, dashboard smoke coverage, generated artifact directories, local/mock limitations, RAG eval proof, red-team proof, and Azure optional notes agree with the code.

The API exposes:

- `GET /handoff/final-audit`: returns the README Consistency final audit.
- `POST /handoff/final-pack`: writes Markdown/JSON Final Handoff artifacts under `storage/final_handoff/`.

The Final Handoff Pack includes exact clone/run commands, verification order, endpoint inventory, artifact inventory, dashboard smoke summary, RAG/eval/red-team proof, local/mock limitations, Azure optional notes, and a recruiter-facing README blurb.

## Generated Artifacts

Generated files are not committed. They are reproducible outputs from local API calls and scripts:

- `storage/exports/`
- `storage/handoffs/`
- `storage/pricing_memos/`
- `storage/source_requests/`
- `storage/submission_calendars/`
- `storage/leadership_briefs/`
- `storage/demo_scripts/`
- `storage/launch_checklists/`
- `storage/runtime_packs/`
- `storage/rag_coverage/`
- `storage/compliance_packs/`
- `storage/procurement_packs/`
- `storage/bid_packs/`
- `storage/portfolio_packs/`
- `storage/reviewer_packs/`
- `storage/api_contracts/`
- `storage/release_packs/`
- `storage/artifact_indexes/`
- `storage/ui_verification/`
- `storage/final_handoff/`

## Local-First And Provider Boundaries

Fresh clones use local/mock behavior by default. `MockLLMProvider` keeps tests and demos deterministic, makes missing-evidence behavior repeatable, and avoids requiring paid model credentials for review. Azure remains optional: there is No Azure dependency for local usage, while Azure OpenAI and Azure AI Search remain documented deployment choices when a production team wants managed model and search services.

## Quality Gates

The v0.2 release expects these checks before publishing:

- `python -m ruff check .`
- `python -m pytest -q`
- `python -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4`
- `python -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4`
- `python scripts/dashboard_smoke.py`
- `python -m app.demo`
