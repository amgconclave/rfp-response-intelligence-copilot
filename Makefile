PYTHON ?= python
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
DASHBOARD_PORT ?= 8501

.PHONY: install install-dev api dev dashboard eval red-team rag-coverage rag-coverage-pack compliance-matrix compliance-pack privacy-guardrails privacy-pack model-risk model-risk-pack freshness freshness-pack conflicts conflict-pack citation-lineage citation-lineage-pack source-trust source-trust-pack buyer-intelligence buyer-intelligence-pack buyer-replay buyer-replay-pack buyer-contracts buyer-contracts-pack decision-provenance decision-provenance-pack submission-certification submission-certification-pack proposal-observability proposal-observability-pack verification-evidence verification-evidence-pack procurement-risk procurement-pack reviewer-collaboration reviewer-collaboration-pack reviewer-signoff reviewer-signoff-pack exception-register exception-pack answer-reuse answer-reuse-pack answer-reuse-drift answer-reuse-drift-pack readiness-pack bid-scenarios bid-roi-pack objection-handling objection-pack win-loss win-loss-pack smoke checklist cost-governance cost-governance-pack provider-resilience provider-resilience-pack runtime-check runtime-pack start-demo ci-doctor audit-pack api-contract reviewer-collection ui-smoke ui-verification artifact-inventory readme-checklist release-gate release-pack git-readiness git-push-plan portfolio reviewer final-audit final-pack test lint demo brief decision docker-up docker-down

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

api:
	$(PYTHON) -m uvicorn app.main:app --reload --host $(API_HOST) --port $(API_PORT)

dev: api

dashboard:
	$(PYTHON) -m streamlit run dashboard/app.py --server.port $(DASHBOARD_PORT)

eval:
	$(PYTHON) -m app.evals.run_eval --dataset sample_data/eval_dataset.json --top-k 4

red-team:
	$(PYTHON) -m app.evals.run_red_team --dataset sample_data/red_team_questions.json --top-k 4

rag-coverage:
	$(PYTHON) -c "import httpx; c=httpx.get('http://127.0.0.1:8000/rag/corpus-coverage', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': c['status'], 'score': c['score'], 'docs': c['corpus_metadata']['sample_document_count']})"

rag-coverage-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/rag/eval-coverage-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

compliance-matrix:
	$(PYTHON) -c "import httpx; m=httpx.get('http://127.0.0.1:8000/compliance/evidence-matrix', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'coverage': m['coverage_summary']['coverage_ratio'], 'families': m['coverage_summary']['control_family_count'], 'flags': m['coverage_summary']['unsupported_claim_count']})"

compliance-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/compliance/control-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

privacy-guardrails:
	$(PYTHON) -c "import httpx; g=httpx.get('http://127.0.0.1:8000/privacy/retention-guardrails', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'surfaces': g['summary']['surface_count'], 'high_risk': g['summary']['high_risk_surface_count'], 'missing_controls': g['summary']['missing_control_count']})"

privacy-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/privacy/retention-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

model-risk:
	$(PYTHON) -c "import httpx; r=httpx.get('http://127.0.0.1:8000/governance/model-risk-register', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': r['register_status'], 'risks': r['summary']['risk_count'], 'review': r['summary']['needs_review_count']})"

model-risk-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/governance/model-risk-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

freshness:
	$(PYTHON) -c "import httpx; f=httpx.get('http://127.0.0.1:8000/evidence/freshness', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'avg_score': f['summary']['average_freshness_score'], 'sources': f['summary']['source_count'], 'expired': f['summary']['expired_count'], 'flags': f['summary']['unsupported_claim_count']})"

freshness-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/evidence/freshness-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

conflicts:
	$(PYTHON) -c "import httpx; c=httpx.get('http://127.0.0.1:8000/evidence/conflicts', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'conflicts': c['summary']['conflict_count'], 'blocked': c['summary']['blocking_conflict_count'], 'review': c['summary']['needs_review_count']})"

conflict-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/evidence/conflict-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

citation-lineage:
	$(PYTHON) -c "import httpx; c=httpx.get('http://127.0.0.1:8000/evidence/citation-lineage', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'score': c['score'], 'citations': c['summary']['citation_count'], 'verified': c['summary']['verified_count'], 'issues': c['summary']['blocking_issue_count']})"

citation-lineage-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/evidence/citation-lineage-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

source-trust:
	$(PYTHON) -c "import httpx; t=httpx.get('http://127.0.0.1:8000/evidence/source-trust', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': t['status'], 'avg_score': t['summary']['average_trust_score'], 'approved': t['summary']['approved_count'], 'blocked': t['summary']['blocked_count']})"

source-trust-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/evidence/source-trust-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

buyer-intelligence:
	$(PYTHON) -c "import httpx; w=httpx.get('http://127.0.0.1:8000/proposal/buyer-intelligence', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': w['workflow_status'], 'stages': len(w['workflow_stages']), 'approvals': len(w['human_approval_queue'])})"

buyer-intelligence-pack:
	$(PYTHON) -c "import httpx; p=httpx.post('http://127.0.0.1:8000/proposal/buyer-intelligence-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'artifact': p['artifact_path'], 'state': p['state_artifact_path']})"

buyer-replay:
	$(PYTHON) -c "import httpx; r=httpx.get('http://127.0.0.1:8000/proposal/buyer-intelligence-replay', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': r['status'], 'transitions': r['transition_count'], 'checkpoint': r['checkpoint_validation']['status']})"

buyer-replay-pack:
	$(PYTHON) -c "import httpx; p=httpx.post('http://127.0.0.1:8000/proposal/buyer-intelligence-replay-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'artifact': p['artifact_path'], 'json': p['json_artifact_path']})"

buyer-contracts:
	$(PYTHON) -c "import httpx; c=httpx.get('http://127.0.0.1:8000/proposal/buyer-contracts', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': c['status'], 'score': c['score'], 'checks': len(c['checks']), 'roles': len(c['role_contracts'])})"

buyer-contracts-pack:
	$(PYTHON) -c "import httpx; p=httpx.post('http://127.0.0.1:8000/proposal/buyer-contracts-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'artifact': p['artifact_path'], 'json': p['json_artifact_path']})"

decision-provenance:
	$(PYTHON) -c "import httpx; p=httpx.get('http://127.0.0.1:8000/proposal/decision-provenance', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': p['status'], 'nodes': p['summary']['node_count'], 'edges': p['summary']['edge_count']})"

decision-provenance-pack:
	$(PYTHON) -c "import httpx; p=httpx.post('http://127.0.0.1:8000/proposal/decision-provenance-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'artifact': p['artifact_path'], 'json': p['json_artifact_path']})"

submission-certification:
	$(PYTHON) -c "import httpx; c=httpx.get('http://127.0.0.1:8000/proposal/submission-certification', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': c['status'], 'score': c['readiness_score'], 'gates': len(c['gates']), 'reviews': len(c['reviewer_queue'])})"

submission-certification-pack:
	$(PYTHON) -c "import httpx; p=httpx.post('http://127.0.0.1:8000/proposal/submission-certification-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'artifact': p['artifact_path'], 'json': p['json_artifact_path']})"

procurement-risk:
	$(PYTHON) -c "import httpx; r=httpx.get('http://127.0.0.1:8000/procurement/question-risk', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'questions': r['coverage_summary']['question_count'], 'coverage': r['coverage_summary']['coverage_ratio'], 'blocked': r['approval_summary']['blocked_count']})"

procurement-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/procurement/approval-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

reviewer-collaboration:
	$(PYTHON) -c "import httpx; b=httpx.post('http://127.0.0.1:8000/rfp/reviewer-collaboration', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'status': b['board_status'], 'assignments': len(b['assignments']), 'comments': len(b['decision_comments']), 'redlines': b['redline_summary']['redline_count']})"

reviewer-collaboration-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/rfp/reviewer-collaboration-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

reviewer-signoff:
	$(PYTHON) -c "import httpx; l=httpx.post('http://127.0.0.1:8000/rfp/reviewer-signoff-ledger', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'status': l['ledger_status'], 'records': l['summary']['record_count'], 'blocked': l['summary']['blocked_count'], 'queue': len(l['human_review_queue'])})"

reviewer-signoff-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/rfp/reviewer-signoff-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

exception-register:
	$(PYTHON) -c "import httpx; r=httpx.post('http://127.0.0.1:8000/rfp/exception-register', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'status': r['register_status'], 'exceptions': r['summary']['exception_count'], 'requires_approval': r['summary']['requires_approval_count']})"

exception-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/rfp/exception-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

answer-reuse:
	$(PYTHON) -c "import httpx; r=httpx.post('http://127.0.0.1:8000/rfp/answer-reuse-library', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'status': r['status'], 'snippets': r['summary']['snippet_count'], 'approved': r['summary']['approved_count'], 'review': r['summary']['review_required_count']})"

answer-reuse-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/rfp/answer-reuse-library-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

answer-reuse-drift:
	$(PYTHON) -c "import httpx; r=httpx.post('http://127.0.0.1:8000/rfp/answer-reuse-drift', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'status': r['status'], 'snippets': r['summary']['snippet_count'], 'score': r['summary']['average_drift_score'], 'review': r['summary']['owner_review_count']})"

answer-reuse-drift-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/rfp/answer-reuse-drift-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

readiness-pack:
	$(PYTHON) -c "import httpx; h={'X-API-Key':'local-demo-key'}; a=httpx.post('http://127.0.0.1:8000/rfp/analyze', headers=h, json={'fixture_path':'sample_data/acme_enterprise_rfp.md'}, timeout=30).json(); m=httpx.post('http://127.0.0.1:8000/rfp/requirement-matrix', headers=h, json={'analyzed_payload':a}, timeout=30).json()['matrix']; print(httpx.post('http://127.0.0.1:8000/rfp/proposal-readiness-score-pack', headers=h, json={'analysis':a,'matrix':m,'write_artifact':True}, timeout=30).json()['artifact_path'])"

bid-scenarios:
	$(PYTHON) -c "import httpx; r=httpx.get('http://127.0.0.1:8000/bid/scenario-analysis', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'scenarios': r['coverage_summary']['scenario_count'], 'recommended': r['recommended_scenario_id'], 'best_roi': r['coverage_summary']['best_risk_adjusted_roi']})"

bid-roi-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/bid/roi-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

objection-handling:
	$(PYTHON) -c "import httpx; r=httpx.post('http://127.0.0.1:8000/rfp/objection-handling', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'objections': r['coverage_summary']['objection_count'], 'coverage': r['coverage_summary']['coverage_ratio'], 'confidence': r['confidence_summary']['average_confidence']})"

objection-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/rfp/objection-handling-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

win-loss:
	$(PYTHON) -c "import httpx; r=httpx.post('http://127.0.0.1:8000/learning/win-loss', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json(); print({'outcomes': r['outcome_count'], 'win_rate': r['win_rate'], 'win_patterns': len(r['winning_evidence_patterns']), 'loss_patterns': len(r['losing_risk_patterns'])})"

win-loss-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/learning/win-loss-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

smoke:
	$(PYTHON) -c "import httpx; print(httpx.get('http://127.0.0.1:8000/ops/smoke-matrix', headers={'X-API-Key': 'local-demo-key'}, timeout=20).json()['readiness_summary'])"

checklist:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/ops/launch-checklist', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

cost-governance:
	$(PYTHON) -c "import httpx; g=httpx.get('http://127.0.0.1:8000/ops/cost-governance', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': g['governance_status'], 'provider': g['provider_readiness']['provider_mode'], 'daily_cost': g['budget_summary']['daily_estimated_cost']})"

cost-governance-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/ops/cost-governance-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

provider-resilience:
	$(PYTHON) -c "import httpx; r=httpx.get('http://127.0.0.1:8000/ops/provider-resilience', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': r['status'], 'active': r['active_provider_mode'], 'recommended': r['recommended_route_id'], 'fallback': r['summary']['fallback_required']})"

provider-resilience-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/ops/provider-resilience-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

proposal-observability:
	$(PYTHON) -c "import httpx; o=httpx.get('http://127.0.0.1:8000/ops/proposal-observability', headers={'X-API-Key': 'local-demo-key'}, timeout=60).json(); print({'status': o['status'], 'spans': o['summary']['trace_span_count'], 'diagnostics': o['summary']['retrieval_diagnostic_count'], 'human_review': o['summary']['human_review_signal_count']})"

proposal-observability-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/ops/proposal-observability-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=60).json()['artifact_path'])"

verification-evidence:
	$(PYTHON) -c "import httpx; e=httpx.get('http://127.0.0.1:8000/ops/verification-evidence', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': e['status'], 'score': e['score'], 'recorded': e['summary']['recorded_command_count'], 'commands': e['summary']['required_command_count']})"

verification-evidence-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/ops/verification-evidence-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

runtime-check:
	$(PYTHON) scripts\runtime_check.py

runtime-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/runtime/demo-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

start-demo:
	powershell -ExecutionPolicy Bypass -File scripts\start_demo.ps1

ci-doctor:
	$(PYTHON) -c "import httpx; d=httpx.get('http://127.0.0.1:8000/ops/ci-doctor', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': d['status'], 'score': d['score'], 'secret_findings': d['secret_scan']['finding_count']})"

audit-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/ops/audit-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

api-contract:
	$(PYTHON) -c "import httpx; a=httpx.get('http://127.0.0.1:8000/api/contract-audit', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': a['status'], 'routes': a['openapi_route_count'], 'auth': a['auth_protected_endpoint_count']})"

reviewer-collection:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/api/reviewer-collection', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

ui-smoke:
	$(PYTHON) scripts\dashboard_smoke.py

ui-verification:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/ui/verification-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

artifact-inventory:
	$(PYTHON) -c "import httpx; inv=httpx.get('http://127.0.0.1:8000/artifacts/inventory', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'directories': inv['total_directories'], 'files': inv['total_files'], 'ignored': inv['ignored_status']})"

readme-checklist:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/artifacts/readme-checklist', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

release-gate:
	$(PYTHON) -c "import httpx; gate=httpx.get('http://127.0.0.1:8000/release/quality-gate', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': gate['status'], 'score': gate['score'], 'blockers': gate['blockers'], 'warnings': gate['warnings']})"

release-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/release/publish-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

git-readiness:
	$(PYTHON) -c "import httpx; r=httpx.get('http://127.0.0.1:8000/git/readiness', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': r['status'], 'branch': r['current_branch'], 'changed': r['working_tree_summary']['changed']})"

git-push-plan:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/git/push-plan', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

portfolio:
	$(PYTHON) -m app.demo
	$(PYTHON) -c "from pathlib import Path; print(Path('storage/portfolio_packs').resolve())"

reviewer:
	$(PYTHON) -c "import httpx; q=httpx.get('http://127.0.0.1:8000/reviewer/quickstart', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': q['status'], 'endpoints': len(q['endpoint_walkthrough_order']), 'artifacts': len(q['artifact_proof_map'])})"
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/reviewer/walkthrough-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

final-audit:
	$(PYTHON) -c "import httpx; a=httpx.get('http://127.0.0.1:8000/handoff/final-audit', headers={'X-API-Key': 'local-demo-key'}, timeout=30).json(); print({'status': a['status'], 'score': a['score'], 'failed': a['summary']['failed_checks']})"

final-pack:
	$(PYTHON) -c "import httpx; print(httpx.post('http://127.0.0.1:8000/handoff/final-pack', headers={'X-API-Key': 'local-demo-key'}, json={}, timeout=30).json()['artifact_path'])"

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check .

demo:
	$(PYTHON) -m app.demo

brief: demo

decision: demo
	$(PYTHON) -c "from pathlib import Path; print(Path('storage/submission_memos').resolve())"

docker-up:
	docker compose up --build

docker-down:
	docker compose down
