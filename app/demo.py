import asyncio
from collections import Counter

from app.main import create_app
from app.models.api import PortfolioInterviewPackRequest, SubmissionRegressionRequest
from app.services.container import get_container

SAMPLE_DOCS = [
    ("sample_data/acme_enterprise_rfp.md", "rfp"),
    ("sample_data/prior_proposal.md", "proposal"),
    ("sample_data/product_overview.md", "product"),
    ("sample_data/security_policy.md", "security"),
    ("sample_data/compliance_policy.md", "compliance"),
    ("sample_data/pricing_notes.md", "pricing"),
    ("sample_data/implementation_guide.md", "implementation"),
    ("sample_data/dpa_privacy_policy.md", "privacy"),
    ("sample_data/sla_support_policy.md", "support"),
    ("sample_data/ai_governance_security.md", "security"),
    ("sample_data/disaster_recovery_plan.md", "disaster_recovery"),
    ("sample_data/customer_success_onboarding.md", "customer_success"),
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
    matrix = container.workbench.create_requirement_matrix(analysis)
    customer_fit = container.customer_intelligence.customer_fit(
        "regulated_healthcare",
        "demo-customer-fit",
        analysis=analysis,
        requirement_matrix=matrix,
    )
    memory_matches = container.customer_intelligence.search_response_memory(
        "SSO encryption SOC 2 implementation pricing",
        "demo-response-memory",
        customer_profile_id="regulated_healthcare",
        top_k=3,
    )
    answer_reuse_library = container.answer_reuse_library.library(
        "demo-answer-reuse-library",
        customer_profile_id="regulated_healthcare",
    )
    answer_reuse_library_pack = container.answer_reuse_library.pack(
        "demo-answer-reuse-library-pack",
        answer_reuse_library,
        write_artifact=True,
    )
    answer_reuse_drift = container.answer_reuse_drift.drift_report(
        "demo-answer-reuse-drift",
        customer_profile_id="regulated_healthcare",
    )
    answer_reuse_drift_pack = container.answer_reuse_drift.pack(
        "demo-answer-reuse-drift-pack",
        answer_reuse_drift,
        write_artifact=True,
    )
    answer_reuse_approval = container.answer_reuse_approval.ledger(
        "demo-answer-reuse-approval",
        customer_profile_id="regulated_healthcare",
    )
    answer_reuse_approval_pack = container.answer_reuse_approval.pack(
        "demo-answer-reuse-approval-pack",
        answer_reuse_approval,
        write_artifact=True,
    )
    export = container.workbench.export_package(
        analysis,
        draft,
        "demo-export",
        customer_fit=customer_fit,
        response_memory_matches=memory_matches,
    )
    answer_review = container.review_board.review_answer(
        answer.question,
        answer.answer_text,
        answer.citations,
        answer.missing_evidence,
        answer.token_usage,
        "demo-answer-review",
    )
    package_review = container.review_board.review_package(
        trace_id="demo-package-review",
        requirement_matrix=matrix,
        draft_response=draft,
        export_payload=export.package,
    )
    action_plan, action_summary = container.action_plan.create_action_plan(
        trace_id="demo-action-plan",
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        review_findings=package_review.findings,
    )
    handoff = container.action_plan.export_handoff_board(
        trace_id="demo-handoff",
        tasks=action_plan,
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        review_findings=package_review.findings,
    )
    evaluation = await container.evaluation.run("sample_data/eval_dataset.json", "demo-eval")
    documents_loaded = len(container.repo.documents)
    regression = await container.submission_regression.run(
        container,
        trace_id="demo-submission-regression",
    )
    red_team = regression.red_team_summary
    scorecard = container.deal_readiness.create_scorecard(
        trace_id="demo-readiness",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=package_review.findings,
        customer_fit=customer_fit,
        action_plan=action_plan,
        eval_metrics=evaluation,
    )
    executive_report = container.deal_readiness.export_executive_report(
        trace_id="demo-executive-risk",
        scorecard=scorecard,
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=package_review.findings,
        customer_fit=customer_fit,
        action_plan=action_plan,
        eval_metrics=evaluation,
        red_team_summary=red_team,
    )
    readiness_pack = container.deal_readiness.create_score_pack(
        trace_id="demo-proposal-readiness-score-pack",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=package_review.findings,
        customer_fit=customer_fit,
        action_plan=action_plan,
        eval_metrics=evaluation,
        draft_response=draft,
        red_team_summary=red_team,
        readiness_scorecard=scorecard,
        executive_report=executive_report,
    )
    revised_analysis = container.analysis.analyze(
        (container.settings.sample_data_dir / "acme_enterprise_rfp_addendum.md").read_text(encoding="utf-8"),
        "demo-amendment-revised",
    )
    amendment_impact = container.amendment_impact.analyze_impact(
        trace_id="demo-amendment-impact",
        baseline_analysis=analysis,
        revised_analysis=revised_analysis,
        requirement_matrix=matrix,
        draft_response=draft,
        readiness_scorecard=scorecard,
        review_findings=package_review.findings,
        amendment_label="Addendum 1",
    )
    amendment_impact_pack = container.amendment_impact.pack(
        trace_id="demo-amendment-impact-pack",
        impact=amendment_impact,
        write_artifact=True,
    )
    win_strategy = container.win_strategy.create_win_strategy(
        trace_id="demo-win-strategy",
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
        readiness_scorecard=scorecard,
        response_memory_matches=memory_matches,
        action_plan=action_plan,
        review_findings=package_review.findings,
        competitor_context=[
            "Incumbent competitor may bundle workflow tooling and offer a discount during procurement.",
        ],
    )
    pricing_memo = container.win_strategy.export_pricing_risk_memo(
        trace_id="demo-pricing-risk-memo",
        win_strategy=win_strategy,
        analysis=analysis,
        requirement_matrix=matrix,
        customer_fit=customer_fit,
    )
    contract_text = (container.settings.sample_data_dir / "customer_contract_terms.md").read_text(encoding="utf-8")
    if not any(doc.filename == "customer_contract_terms.md" for doc in container.repo.documents.values()):
        await container.ingestion.ingest_path(
            "sample_data/customer_contract_terms.md",
            document_type="contract",
            source="sample_data",
        )
    contract_risk = container.contract_risk.analyze(
        contract_text,
        "demo-contract-risk",
        customer_profile_id="regulated_healthcare",
    )
    negotiation_brief = container.contract_risk.export_negotiation_brief(
        trace_id="demo-negotiation-brief",
        contract_risk=contract_risk,
        win_strategy=win_strategy,
        pricing_memo=pricing_memo,
    )
    evidence_gaps, evidence_gap_summary = container.evidence_gap.create_gap_plan(
        trace_id="demo-evidence-gaps",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=package_review.findings,
        red_team_summary=red_team,
        readiness_scorecard=scorecard,
        win_strategy=win_strategy,
        contract_risk=contract_risk,
        action_plan=action_plan,
    )
    source_request_pack = container.evidence_gap.export_source_request_pack(
        trace_id="demo-source-request-pack",
        gaps=evidence_gaps,
        analysis=analysis,
        red_team_summary=red_team,
        readiness_scorecard=scorecard,
        win_strategy=win_strategy,
        contract_risk=contract_risk,
    )
    leadership_brief = container.leadership_brief.export_brief(
        trace_id="demo-leadership-brief",
        documents_ingested=documents_loaded,
        analysis=analysis,
        requirement_matrix=matrix,
        draft_response=draft,
        answers=[answer],
        export_payload=export.package,
        export_artifact_path=export.artifact_path,
        export_json_artifact_path=export.json_artifact_path,
        review_findings=package_review.findings,
        review_passed=package_review.passed,
        customer_fit=customer_fit,
        response_memory_matches=memory_matches,
        action_plan=action_plan,
        handoff_board=handoff.board,
        handoff_artifact_path=handoff.artifact_path,
        handoff_json_artifact_path=handoff.json_artifact_path,
        readiness_scorecard=scorecard,
        executive_report=executive_report,
        eval_metrics=evaluation,
        red_team_summary=red_team,
    )
    timeline_plan = container.timeline_orchestration.create_plan(
        trace_id="demo-timeline-plan",
        analysis=analysis,
        requirement_matrix=matrix,
        action_plan=action_plan,
        evidence_gaps=evidence_gaps,
        contract_risk=contract_risk,
        win_strategy=win_strategy,
        readiness_scorecard=scorecard,
        source_request_pack=source_request_pack.pack,
        leadership_brief=leadership_brief.brief,
        review_findings=package_review.findings,
        red_team_summary=red_team,
    )
    submission_calendar = container.timeline_orchestration.export_submission_calendar_pack(
        trace_id="demo-submission-calendar",
        plan=timeline_plan,
        analysis=analysis,
        source_request_pack=source_request_pack.pack,
        leadership_brief=leadership_brief.brief,
    )
    submission_decision = container.submission_decision.create_decision(
        trace_id="demo-submission-decision",
        requirement_matrix=matrix,
        draft_response=draft,
        answers=[answer],
        review_findings=package_review.findings,
        review_passed=package_review.passed,
        action_plan=action_plan,
        readiness_scorecard=scorecard,
        eval_metrics=evaluation,
        red_team_summary=red_team,
        win_strategy=win_strategy,
        contract_risk=contract_risk,
        evidence_gaps=evidence_gaps,
        source_request_pack=source_request_pack.pack,
        timeline_plan=timeline_plan,
        leadership_brief=leadership_brief.brief,
        metrics=container.metrics.totals(),
        artifact_links={
            "export_package": {
                "artifact_path": export.artifact_path,
                "json_artifact_path": export.json_artifact_path,
            },
            "source_request_pack": {
                "artifact_path": source_request_pack.artifact_path,
                "json_artifact_path": source_request_pack.json_artifact_path,
            },
            "submission_calendar": {
                "artifact_path": submission_calendar.artifact_path,
                "json_artifact_path": submission_calendar.json_artifact_path,
            },
            "leadership_brief": {
                "artifact_path": leadership_brief.artifact_path,
                "json_artifact_path": leadership_brief.json_artifact_path,
            },
        },
    )
    executive_submission_memo = container.submission_decision.export_memo(
        trace_id="demo-executive-submission-memo",
        decision=submission_decision,
    )
    demo_script = container.demo_script.generate("demo-script", regression)
    launch_checklist = container.launch_checklist.launch_checklist("demo-launch-checklist")
    cost_governance = container.cost_governance.report("demo-cost-governance")
    cost_governance_pack = container.cost_governance.pack(
        "demo-cost-governance-pack",
        cost_governance,
        write_artifact=True,
    )
    provider_resilience = container.provider_resilience.resilience("demo-provider-resilience")
    provider_resilience_pack = container.provider_resilience.pack(
        "demo-provider-resilience-pack",
        provider_resilience,
        write_artifact=True,
    )
    portfolio_evidence = container.portfolio.evidence_index("demo-portfolio-evidence")
    interview_pack = await container.portfolio.generate_interview_pack(
        container,
        "demo-portfolio-interview-pack",
        PortfolioInterviewPackRequest(
            regression_request=SubmissionRegressionRequest(write_artifacts=False),
            write_artifact=True,
        ),
    )
    reviewer_quickstart = container.reviewer.quickstart("demo-reviewer-quickstart")
    walkthrough_pack = container.reviewer.walkthrough_pack("demo-reviewer-walkthrough-pack")
    release_smoke = container.launch_checklist.smoke_matrix("demo-release-smoke")
    release_gate = container.release.quality_gate(release_smoke, "demo-release-gate")
    release_pack_artifact, release_pack_json, _, _ = container.release.publish_pack(
        release_gate,
        release_smoke,
        "demo-release-pack",
        write_artifact=True,
    )
    ci_doctor = container.ci_doctor.ci_doctor("demo-ci-doctor")
    audit_pack = container.ci_doctor.audit_pack("demo-audit-pack", doctor=ci_doctor)
    artifact_inventory = container.artifact_inventory.inventory("demo-artifact-inventory")
    readme_checklist = container.artifact_inventory.readme_checklist("demo-readme-checklist")
    dashboard_smoke = container.ui_verification.dashboard_smoke("demo-dashboard-smoke")
    contract_audit = container.api_contracts.audit(
        "demo-api-contract-audit",
        create_app().openapi(),
        release_smoke,
        dashboard_smoke,
        artifact_inventory,
    )
    reviewer_collection = container.api_contracts.reviewer_collection("demo-reviewer-collection", contract_audit)
    ui_verification_pack = container.ui_verification.verification_pack("demo-ui-verification-pack")
    final_audit = container.final_handoff.final_audit(
        "demo-final-audit",
        release_smoke,
        artifact_inventory,
        dashboard_smoke,
    )
    final_pack_artifact, final_pack_json, _, _ = container.final_handoff.final_pack(
        "demo-final-pack",
        final_audit,
        release_smoke,
        artifact_inventory,
        dashboard_smoke,
        write_artifact=True,
    )
    verification_evidence = container.verification_evidence.evidence(
        "demo-verification-evidence",
        release_gate,
        final_audit,
        dashboard_smoke,
        artifact_inventory,
    )
    verification_evidence_pack = container.verification_evidence.pack(
        "demo-verification-evidence-pack",
        verification_evidence,
        write_artifact=True,
    )
    git_readiness = container.git_readiness.readiness("demo-git-readiness")
    git_push_plan = container.git_readiness.push_plan("demo-git-push-plan", write_artifact=True)
    runtime_readiness = container.runtime_demo.readiness("demo-runtime-readiness")
    runtime_pack = container.runtime_demo.demo_pack("demo-runtime-pack", write_artifact=True)
    rag_coverage = container.corpus_coverage.corpus_coverage("demo-rag-corpus-coverage")
    rag_coverage_pack = container.corpus_coverage.eval_coverage_pack("demo-rag-coverage-pack", write_artifact=True)
    evidence_freshness = container.evidence_freshness.freshness_report("demo-evidence-freshness")
    evidence_freshness_pack = container.evidence_freshness.freshness_pack(
        "demo-evidence-freshness-pack",
        evidence_freshness,
        write_artifact=True,
    )
    evidence_conflicts = container.evidence_conflicts.conflict_report("demo-evidence-conflicts")
    evidence_conflict_pack = container.evidence_conflicts.conflict_pack(
        "demo-evidence-conflict-pack",
        evidence_conflicts,
        write_artifact=True,
    )
    citation_lineage = container.citation_lineage.audit(
        "demo-citation-lineage",
        answers=[answer],
        drafts=[draft],
        export_payloads=[export.package],
    )
    citation_lineage_pack = container.citation_lineage.lineage_pack(
        "demo-citation-lineage-pack",
        citation_lineage,
        write_artifact=True,
    )
    source_trust = container.source_trust.trust_gate(
        "demo-source-trust",
        evidence_freshness,
        evidence_conflicts,
        citation_lineage,
    )
    source_trust_pack = container.source_trust.trust_pack(
        "demo-source-trust-pack",
        source_trust,
        write_artifact=True,
    )
    governed_retrieval = await container.governed_retrieval.preview(
        "demo-governed-retrieval",
        "What disaster recovery, uptime, SSO, encryption, and audit controls are supported?",
        source_trust,
        top_k=6,
    )
    governed_retrieval_pack = container.governed_retrieval.pack(
        "demo-governed-retrieval-pack",
        governed_retrieval,
        write_artifact=True,
    )
    compliance_matrix = container.compliance.evidence_matrix(
        "demo-compliance-evidence-matrix",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=package_review.findings,
    )
    compliance_control_pack = container.compliance.control_pack(
        "demo-compliance-control-pack",
        compliance_matrix,
        write_artifact=True,
    )
    privacy_retention = container.privacy_retention.guardrails("demo-privacy-retention")
    privacy_retention_pack = container.privacy_retention.retention_pack(
        "demo-privacy-retention-pack",
        privacy_retention,
        write_artifact=True,
    )
    model_risk = container.model_risk.register("demo-model-risk")
    model_risk_pack = container.model_risk.risk_pack(
        "demo-model-risk-pack",
        model_risk,
        write_artifact=True,
    )
    procurement_question_risk = await container.procurement.question_risk(
        "demo-procurement-question-risk",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=package_review.findings,
    )
    procurement_approval_pack = container.procurement.approval_pack(
        "demo-procurement-approval-pack",
        procurement_question_risk,
        write_artifact=True,
    )
    buyer_intelligence = container.buyer_intelligence.workflow(
        trace_id="demo-buyer-intelligence",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=package_review.findings,
        cost_governance=cost_governance,
        source_trust=source_trust,
        model_risk=model_risk,
        procurement_risk=procurement_question_risk,
    )
    buyer_intelligence_pack = container.buyer_intelligence.pack(
        "demo-buyer-intelligence-pack",
        buyer_intelligence,
        write_artifact=True,
    )
    buyer_workflow_replay = container.buyer_intelligence.replay(
        "demo-buyer-workflow-replay",
        buyer_intelligence,
    )
    buyer_workflow_replay_pack = container.buyer_intelligence.replay_pack(
        "demo-buyer-workflow-replay-pack",
        buyer_workflow_replay,
        write_artifact=True,
    )
    approval_simulation = container.approval_simulation.simulate(
        trace_id="demo-approval-simulation",
        workflow=buyer_intelligence,
        requested_by="demo_proposal_manager",
    )
    approval_simulation_pack = container.approval_simulation.pack(
        "demo-approval-simulation-pack",
        approval_simulation,
        write_artifact=True,
    )
    agent_council = container.proposal_agent_council.council(
        trace_id="demo-agent-council",
        workflow=buyer_intelligence,
        cost_governance=cost_governance,
        source_trust=source_trust,
        model_risk=model_risk,
        procurement_risk=procurement_question_risk,
    )
    agent_council_pack = container.proposal_agent_council.pack(
        "demo-agent-council-pack",
        agent_council,
        write_artifact=True,
    )
    decision_provenance = container.decision_provenance.provenance(
        trace_id="demo-decision-provenance",
        workflow=buyer_intelligence,
        replay=buyer_workflow_replay,
        council=agent_council,
        cost_governance=cost_governance,
        source_trust=source_trust,
        model_risk=model_risk,
        procurement_risk=procurement_question_risk,
    )
    decision_provenance_pack = container.decision_provenance.pack(
        "demo-decision-provenance-pack",
        decision_provenance,
        write_artifact=True,
    )
    buyer_structured_contracts = container.buyer_contracts.audit(
        trace_id="demo-buyer-structured-contracts",
        workflow=buyer_intelligence,
        replay=buyer_workflow_replay,
        council=agent_council,
        provenance=decision_provenance,
    )
    buyer_structured_contracts_pack = container.buyer_contracts.pack(
        "demo-buyer-structured-contracts-pack",
        buyer_structured_contracts,
        write_artifact=True,
    )
    submission_certification = container.submission_certification.certify(
        trace_id="demo-submission-certification",
        workflow=buyer_intelligence,
        replay=buyer_workflow_replay,
        council=agent_council,
        provenance=decision_provenance,
        contract_audit=buyer_structured_contracts,
    )
    submission_certification_pack = container.submission_certification.pack(
        "demo-submission-certification-pack",
        submission_certification,
        write_artifact=True,
    )
    procurement_risk_desk = await container.procurement_risk_desk.risk_desk(
        "demo-procurement-risk-desk",
        analysis=analysis,
        requirement_matrix=matrix,
        review_findings=package_review.findings,
        contract_risk=contract_risk,
        win_strategy=win_strategy,
        procurement_risk=procurement_question_risk,
    )
    procurement_risk_desk_pack = container.procurement_risk_desk.risk_desk_pack(
        "demo-procurement-risk-desk-pack",
        procurement_risk_desk,
        write_artifact=True,
    )
    reviewer_collaboration = container.reviewer_collaboration.create_board(
        trace_id="demo-reviewer-collaboration",
        requirement_matrix=matrix,
        draft_response=draft,
        review_findings=package_review.findings,
        review_passed=package_review.passed,
        action_plan=action_plan,
        evidence_gaps=evidence_gaps,
        contract_risk=contract_risk,
        submission_decision=submission_decision,
    )
    reviewer_collaboration_pack = container.reviewer_collaboration.collaboration_pack(
        "demo-reviewer-collaboration-pack",
        reviewer_collaboration,
        write_artifact=True,
    )
    reviewer_workflow = container.reviewer_workflow.build_workflow(
        "demo-reviewer-workflow",
        reviewer_collaboration,
    )
    reviewer_workflow_pack = container.reviewer_workflow.workflow_pack(
        "demo-reviewer-workflow-pack",
        reviewer_collaboration,
        reviewer_workflow,
        write_artifact=True,
    )
    reviewer_signoff = container.reviewer_signoff.ledger(
        "demo-reviewer-signoff-ledger",
        reviewer_collaboration,
        reviewer_workflow,
    )
    reviewer_signoff_pack = container.reviewer_signoff.pack(
        "demo-reviewer-signoff-pack",
        reviewer_collaboration,
        reviewer_workflow,
        reviewer_signoff,
        write_artifact=True,
    )
    exception_register = container.submission_exceptions.create_register(
        trace_id="demo-exception-register",
        submission_decision=submission_decision,
        reviewer_collaboration=reviewer_collaboration,
    )
    exception_pack = container.submission_exceptions.exception_pack(
        "demo-exception-pack",
        exception_register,
        write_artifact=True,
    )
    bid_scenario_analysis = container.bid_simulator.scenario_analysis(
        trace_id="demo-bid-scenario-analysis",
        requirement_matrix=matrix,
        customer_profiles=container.customer_intelligence.list_profiles(),
        readiness_scorecard=scorecard,
        win_strategy=win_strategy,
        submission_decision=submission_decision,
        evidence_gaps=evidence_gaps,
        contract_risk=contract_risk,
        timeline_plan=timeline_plan,
        procurement_risk=procurement_question_risk,
    )
    bid_roi_pack = container.bid_simulator.export_roi_pack(
        "demo-bid-roi-pack",
        bid_scenario_analysis,
        write_artifact=True,
    )
    objection_handling = await container.objection_handling.objection_handling(
        trace_id="demo-objection-handling",
        analysis=analysis,
        requirement_matrix=matrix,
        win_strategy=win_strategy,
        response_memory_matches=memory_matches,
        review_findings=package_review.findings,
        competitor_context=[
            "Incumbent competitor may bundle workflow tooling and offer a 25% discount during procurement.",
        ],
        pricing_notes=[
            "Use standard tiers; route discounts, price matching, payment terms, and custom packaging for approval.",
        ],
        top_k=4,
    )
    objection_pack = container.objection_handling.handling_pack(
        "demo-objection-pack",
        objection_handling,
        write_artifact=True,
    )
    win_loss_learning = container.win_loss_learning.learn(
        trace_id="demo-win-loss-learning",
        analysis=analysis,
        requirement_matrix=matrix,
        win_strategy=win_strategy,
        eval_metrics=evaluation,
    )
    win_loss_pack = container.win_loss_learning.strategy_pack(
        "demo-win-loss-pack",
        win_loss_learning,
        write_artifact=True,
    )
    retrieval_experiments = await container.retrieval_experiments.compare(
        trace_id="demo-retrieval-experiments",
        dataset_path="sample_data/eval_dataset.json",
        outcomes_fixture_path="sample_data/rfp_outcomes.json",
        top_k=4,
    )
    retrieval_experiment_pack = await container.retrieval_experiments.experiment_pack(
        trace_id="demo-retrieval-experiment-pack",
        comparison=retrieval_experiments,
        write_artifact=True,
    )
    win_loss_policy = container.win_loss_policy.activation_plan(
        trace_id="demo-win-loss-policy",
        learning=win_loss_learning,
        retrieval_experiment=retrieval_experiments,
        activation_mode="shadow_eval",
    )
    win_loss_policy_pack = container.win_loss_policy.policy_pack(
        trace_id="demo-win-loss-policy-pack",
        activation_plan=win_loss_policy,
        write_artifact=True,
    )
    proposal_observability = container.proposal_observability.report(
        trace_id="demo-proposal-observability",
        workflow=buyer_intelligence,
        replay=buyer_workflow_replay,
        council=agent_council,
        provenance=decision_provenance,
        retrieval_experiment=retrieval_experiments,
        cost_governance=cost_governance,
        usage_metrics=container.metrics.list_metrics(),
        audit_events=container.audit.list_events(),
    )
    proposal_observability_pack = container.proposal_observability.pack(
        "demo-proposal-observability-pack",
        proposal_observability,
        write_artifact=True,
    )
    proposal_quality_benchmark = container.proposal_benchmark.benchmark(
        trace_id="demo-proposal-quality-benchmark",
        certification=submission_certification,
        observability=proposal_observability,
        provider_resilience=provider_resilience,
    )
    proposal_quality_benchmark_pack = container.proposal_benchmark.pack(
        "demo-proposal-quality-benchmark-pack",
        proposal_quality_benchmark,
        write_artifact=True,
    )
    owner_counts = Counter(task.owner_role for task in action_plan)

    print("RFP Response Intelligence Copilot demo")
    print(f"Documents loaded: {documents_loaded}")
    print(f"Requirements extracted: {len(analysis.requirements)}")
    print(f"Matrix rows: {len(matrix)}")
    print(f"Evidence-backed rows: {sum(1 for row in matrix if row.status == 'evidence_found')}")
    print(f"Blocked rows: {sum(1 for row in matrix if row.status == 'blocked')}")
    print(f"Customer profile: {customer_fit.customer_profile.name}")
    print(f"Customer fit score: {customer_fit.fit_score}")
    print(f"Customer fit risks: {len(customer_fit.profile_risks)}")
    print(f"Response memory matches: {', '.join(match.title for match in memory_matches)}")
    print(
        "Answer reuse library: "
        f"status={answer_reuse_library.status} "
        f"snippets={answer_reuse_library.summary['snippet_count']} "
        f"approved={answer_reuse_library.summary['approved_count']} "
        f"review={answer_reuse_library.summary['review_required_count']}"
    )
    print(f"Answer Reuse Library Pack: {answer_reuse_library_pack.artifact_path}")
    print(f"Answer Reuse Library Pack JSON: {answer_reuse_library_pack.json_artifact_path}")
    print("Answer reuse library directory: storage/answer_reuse_library")
    print(
        "Answer reuse drift: "
        f"status={answer_reuse_drift.status} "
        f"average_score={answer_reuse_drift.summary['average_drift_score']} "
        f"owner_review={answer_reuse_drift.summary['owner_review_count']} "
        f"rewrite={answer_reuse_drift.summary['rewrite_count']}"
    )
    print(f"Answer Reuse Drift Pack: {answer_reuse_drift_pack.artifact_path}")
    print(f"Answer Reuse Drift Pack JSON: {answer_reuse_drift_pack.json_artifact_path}")
    print("Answer reuse drift directory: storage/answer_reuse_drift")
    print(
        "Answer reuse approval: "
        f"status={answer_reuse_approval.status} "
        f"records={answer_reuse_approval.summary['record_count']} "
        f"pending={answer_reuse_approval.summary['pending_count']} "
        f"blocked={answer_reuse_approval.summary['blocked_count']}"
    )
    print(f"Answer Reuse Approval Pack: {answer_reuse_approval_pack.artifact_path}")
    print(f"Answer Reuse Approval Pack JSON: {answer_reuse_approval_pack.json_artifact_path}")
    print("Answer reuse approval directory: storage/answer_reuse_approvals")
    print(f"Answer confidence: {answer.confidence}")
    print(f"Citations: {', '.join(c.filename for c in answer.citations)}")
    print(f"Draft sections: {len(draft.sections)}")
    print(f"Export artifact: {export.artifact_path}")
    print(f"Export summary: {export.package['executive_summary']}")
    print(f"Answer review pass: {answer_review.passed} findings={len(answer_review.findings)}")
    print(f"Package review pass: {package_review.passed} findings={len(package_review.findings)}")
    print(f"Action plan tasks by owner: {dict(sorted(owner_counts.items()))}")
    print(f"Action plan blocked tasks: {action_summary['blocked_tasks']}")
    print(f"Handoff artifact: {handoff.artifact_path}")
    print(f"Readiness score: {scorecard.readiness_score} ({scorecard.readiness_level})")
    print(f"Executive risk report: {executive_report.artifact_path}")
    print(f"Proposal readiness score pack: {readiness_pack.artifact_path}")
    print(
        "Amendment impact: "
        f"status={amendment_impact.status} "
        f"changes={amendment_impact.summary['change_count']} "
        f"blocking={amendment_impact.summary['blocking_change_count']} "
        f"gate={amendment_impact.readiness_impact['submission_gate']}"
    )
    print(f"Amendment Impact Pack: {amendment_impact_pack.artifact_path}")
    print(f"Amendment Impact Pack JSON: {amendment_impact_pack.json_artifact_path}")
    print("Amendment impact directory: storage/amendment_impact")
    print(
        "Win score: "
        f"{win_strategy.win_score} ({win_strategy.win_level}) "
        f"competitor_risk={win_strategy.competitor_risk_profile['risk_level']} "
        f"pricing_risk={win_strategy.pricing_risk['risk_level']}"
    )
    print(f"Pricing memo artifact: {pricing_memo.artifact_path}")
    print(f"Contract risk score: {contract_risk.risk_score} ({contract_risk.status})")
    print(f"Contract risky clauses: {len(contract_risk.risky_clauses)}")
    print(f"Negotiation brief artifact: {negotiation_brief.artifact_path}")
    print(
        "Evidence gap count: "
        f"{evidence_gap_summary['gap_count']} "
        f"high severity count={evidence_gap_summary['high_severity_count']}"
    )
    print(f"Source request artifact: {source_request_pack.artifact_path}")
    print(f"Leadership brief: {leadership_brief.artifact_path}")
    print(f"Timeline milestone count: {timeline_plan.summary['milestone_count']}")
    print(f"Timeline blocked count: {timeline_plan.summary['blocked_count']}")
    print(f"Submission calendar artifact: {submission_calendar.artifact_path}")
    print(f"Submission decision: {submission_decision.decision} score={submission_decision.score}")
    print(f"Executive submission memo: {executive_submission_memo.artifact_path}")
    print(f"Submission regression pass: {regression.passed}")
    print(f"Submission regression failed checks: {regression.failed_checks}")
    print(f"Generated demo script: {demo_script.artifact_path}")
    print(
        "Launch readiness: "
        f"{launch_checklist.smoke_matrix.readiness_summary.readiness_level} "
        f"endpoints={launch_checklist.smoke_matrix.readiness_summary.total_endpoints}"
    )
    print(f"Launch checklist artifact: {launch_checklist.artifact_path}")
    print(
        "Cost governance: "
        f"status={cost_governance.governance_status} "
        f"provider={cost_governance.provider_readiness['provider_mode']} "
        f"daily_cost={cost_governance.budget_summary['daily_estimated_cost']}"
    )
    print(f"Cost Governance Pack: {cost_governance_pack.artifact_path}")
    print(f"Cost Governance Pack JSON: {cost_governance_pack.json_artifact_path}")
    print(
        "Provider resilience: "
        f"status={provider_resilience.status} "
        f"active={provider_resilience.active_provider_mode} "
        f"recommended={provider_resilience.recommended_route_id} "
        f"fallback={provider_resilience.summary['fallback_required']}"
    )
    print(f"Provider Resilience Pack: {provider_resilience_pack.artifact_path}")
    print(f"Provider Resilience Pack JSON: {provider_resilience_pack.json_artifact_path}")
    print(
        "Portfolio evidence score: "
        f"{portfolio_evidence.evidence_score} "
        f"covered={portfolio_evidence.covered_skill_count}/{portfolio_evidence.total_skill_count}"
    )
    print(f"Portfolio interview pack: {interview_pack.artifact_path}")
    print(
        "Reviewer quickstart: "
        f"{reviewer_quickstart.status} "
        f"endpoints={len(reviewer_quickstart.endpoint_walkthrough_order)} "
        f"artifacts={len(reviewer_quickstart.artifact_proof_map)}"
    )
    print(f"Walkthrough Pack: {walkthrough_pack.artifact_path}")
    print(f"Release gate status: {release_gate.status} score={release_gate.score}")
    print(f"Release publish pack: {release_pack_artifact}")
    print(f"Release publish pack JSON: {release_pack_json}")
    print(f"CI Doctor status: {ci_doctor.status} score={ci_doctor.score}")
    print(f"Audit Pack artifact: {audit_pack.artifact_path}")
    print(f"Audit Pack JSON: {audit_pack.json_artifact_path}")
    print(f"Artifact inventory count: {artifact_inventory.total_directories}")
    print(f"README Checklist artifact: {readme_checklist.artifact_path}")
    print(
        "Dashboard Smoke status: "
        f"{dashboard_smoke.status} views={dashboard_smoke.summary['views_present']}/"
        f"{dashboard_smoke.summary['view_count']} endpoints="
        f"{dashboard_smoke.summary['endpoints_referenced']}/{dashboard_smoke.summary['endpoint_count']}"
    )
    print(
        "API Contract status: "
        f"{contract_audit.status} score={contract_audit.score} "
        f"openapi_routes={contract_audit.openapi_route_count} "
        f"auth_protected={contract_audit.auth_protected_endpoint_count}"
    )
    print(f"Reviewer Collection Pack: {reviewer_collection.artifact_path}")
    print(f"Reviewer Collection Pack JSON: {reviewer_collection.json_artifact_path}")
    print(f"UI Verification Pack: {ui_verification_pack.artifact_path}")
    print(f"UI Verification Pack JSON: {ui_verification_pack.json_artifact_path}")
    print(f"Final audit status: {final_audit.status} score={final_audit.score}")
    print(f"Final Handoff Pack: {final_pack_artifact}")
    print(f"Final Handoff Pack JSON: {final_pack_json}")
    print(
        "Git readiness status: "
        f"{git_readiness.status} branch={git_readiness.current_branch} "
        f"changed={git_readiness.working_tree_summary['changed']}"
    )
    print(f"Git Push Readiness Pack: {git_push_plan.artifact_path}")
    print(f"Git Push Readiness Pack JSON: {git_push_plan.json_artifact_path}")
    print(
        "Runtime Demo readiness: "
        f"{runtime_readiness.status} ports="
        f"{sum(check['listening'] for check in runtime_readiness.process_port_checks)}"
    )
    print(f"Runtime Demo Server Pack: {runtime_pack.artifact_path}")
    print(f"Runtime Demo Server Pack JSON: {runtime_pack.json_artifact_path}")
    print(
        "RAG corpus coverage: "
        f"{rag_coverage.status} score={rag_coverage.score} "
        f"docs={rag_coverage.corpus_metadata['sample_document_count']}"
    )
    print(f"RAG Eval Coverage Pack: {rag_coverage_pack.artifact_path}")
    print(f"RAG Eval Coverage Pack JSON: {rag_coverage_pack.json_artifact_path}")
    print(
        "Evidence freshness: "
        f"avg={evidence_freshness.summary['average_freshness_score']} "
        f"sources={evidence_freshness.summary['source_count']} "
        f"expired={evidence_freshness.summary['expired_count']} "
        f"flags={evidence_freshness.summary['unsupported_claim_count']}"
    )
    print(f"Evidence Freshness Pack: {evidence_freshness_pack.artifact_path}")
    print(f"Evidence Freshness Pack JSON: {evidence_freshness_pack.json_artifact_path}")
    print("Freshness packs directory: storage/freshness_packs")
    print(
        "Evidence conflicts: "
        f"conflicts={evidence_conflicts.summary['conflict_count']} "
        f"blocked={evidence_conflicts.summary['blocking_conflict_count']} "
        f"needs_review={evidence_conflicts.summary['needs_review_count']}"
    )
    print(f"Evidence Conflict Resolver Pack: {evidence_conflict_pack.artifact_path}")
    print(f"Evidence Conflict Resolver Pack JSON: {evidence_conflict_pack.json_artifact_path}")
    print("Conflict packs directory: storage/conflict_packs")
    print(
        "Citation lineage: "
        f"score={citation_lineage.score} "
        f"citations={citation_lineage.summary['citation_count']} "
        f"verified={citation_lineage.summary['verified_count']} "
        f"issues={citation_lineage.summary['blocking_issue_count']}"
    )
    print(f"Citation Lineage Pack: {citation_lineage_pack.artifact_path}")
    print(f"Citation Lineage Pack JSON: {citation_lineage_pack.json_artifact_path}")
    print("Citation lineage directory: storage/citation_lineage")
    print(
        "Source trust gate: "
        f"status={source_trust.status} "
        f"avg={source_trust.summary['average_trust_score']} "
        f"approved={source_trust.summary['approved_count']} "
        f"blocked={source_trust.summary['blocked_count']}"
    )
    print(f"Source Trust Pack: {source_trust_pack.artifact_path}")
    print(f"Source Trust Pack JSON: {source_trust_pack.json_artifact_path}")
    print("Source trust directory: storage/source_trust")
    print(
        "Governed retrieval: "
        f"status={governed_retrieval.status} "
        f"allowed={governed_retrieval.summary['allowed_count']} "
        f"approval_required={governed_retrieval.summary['approval_required_count']} "
        f"blocked={governed_retrieval.summary['blocked_or_suppressed_count']}"
    )
    print(f"Governed Retrieval Pack: {governed_retrieval_pack.artifact_path}")
    print(f"Governed Retrieval Pack JSON: {governed_retrieval_pack.json_artifact_path}")
    print("Governed retrieval directory: storage/governed_retrieval")
    print(
        "Buyer intelligence workflow: "
        f"status={buyer_intelligence.workflow_status} "
        f"approvals={len(buyer_intelligence.human_approval_queue)} "
        f"gates={len(buyer_intelligence.governance_gates)}"
    )
    print(f"Buyer Intelligence Pack: {buyer_intelligence_pack.artifact_path}")
    print(f"Buyer Intelligence Pack JSON: {buyer_intelligence_pack.json_artifact_path}")
    print(f"Buyer Intelligence State: {buyer_intelligence_pack.state_artifact_path}")
    print(
        "Buyer Workflow Replay: "
        f"{buyer_workflow_replay.status} transitions={buyer_workflow_replay.transition_count} "
        f"checkpoint={buyer_workflow_replay.checkpoint_validation['status']}"
    )
    print(f"Buyer Workflow Replay Pack: {buyer_workflow_replay_pack.artifact_path}")
    print(f"Buyer Workflow Replay Pack JSON: {buyer_workflow_replay_pack.json_artifact_path}")
    print("Buyer intelligence directory: storage/buyer_intelligence")
    print(
        "Approval simulation: "
        f"status={approval_simulation.status} "
        f"workflow={approval_simulation.simulated_workflow_status} "
        f"decisions={len(approval_simulation.decision_records)} "
        f"unresolved={approval_simulation.unresolved_approval_count}"
    )
    print(f"Approval Simulation Pack: {approval_simulation_pack.artifact_path}")
    print(f"Approval Simulation Pack JSON: {approval_simulation_pack.json_artifact_path}")
    print(f"Approval Simulation State: {approval_simulation_pack.state_artifact_path}")
    print("Approval simulation directory: storage/approval_simulations")
    print(
        "Proposal agent council: "
        f"status={agent_council.status} "
        f"agents={len(agent_council.agents)} "
        f"handoffs={len(agent_council.handoffs)} "
        f"tokens={agent_council.budget_ledger['total_token_estimate']}"
    )
    print(f"Proposal Agent Council Pack: {agent_council_pack.artifact_path}")
    print(f"Proposal Agent Council Pack JSON: {agent_council_pack.json_artifact_path}")
    print(f"Proposal Agent Council Transcript: {agent_council_pack.transcript_artifact_path}")
    print("Agent council directory: storage/agent_council")
    print(
        "Decision provenance: "
        f"status={decision_provenance.status} "
        f"nodes={decision_provenance.summary['node_count']} "
        f"edges={decision_provenance.summary['edge_count']}"
    )
    print(f"Decision Provenance Pack: {decision_provenance_pack.artifact_path}")
    print(f"Decision Provenance Pack JSON: {decision_provenance_pack.json_artifact_path}")
    print("Decision provenance directory: storage/decision_provenance")
    print(
        "Buyer structured contracts: "
        f"status={buyer_structured_contracts.status} "
        f"score={buyer_structured_contracts.score} "
        f"checks={len(buyer_structured_contracts.checks)} "
        f"roles={len(buyer_structured_contracts.role_contracts)}"
    )
    print(f"Buyer Structured Contract Pack: {buyer_structured_contracts_pack.artifact_path}")
    print(f"Buyer Structured Contract Pack JSON: {buyer_structured_contracts_pack.json_artifact_path}")
    print("Buyer contracts directory: storage/buyer_contracts")
    print(
        "Submission certification: "
        f"status={submission_certification.status} "
        f"score={submission_certification.readiness_score} "
        f"gates={len(submission_certification.gates)} "
        f"reviews={len(submission_certification.reviewer_queue)}"
    )
    print(f"Submission Certification Pack: {submission_certification_pack.artifact_path}")
    print(f"Submission Certification Pack JSON: {submission_certification_pack.json_artifact_path}")
    print("Submission certification directory: storage/submission_certifications")
    print(
        "Proposal quality benchmark: "
        f"status={proposal_quality_benchmark.status} "
        f"score={proposal_quality_benchmark.score} "
        f"scenarios={proposal_quality_benchmark.scenario_count} "
        f"warnings={proposal_quality_benchmark.warning_count}"
    )
    print(f"Proposal Quality Benchmark Pack: {proposal_quality_benchmark_pack.artifact_path}")
    print(f"Proposal Quality Benchmark Pack JSON: {proposal_quality_benchmark_pack.json_artifact_path}")
    print("Proposal benchmark directory: storage/proposal_benchmarks")
    print(
        "Compliance control coverage: "
        f"{compliance_matrix.coverage_summary['coverage_ratio']} "
        f"families={compliance_matrix.coverage_summary['control_family_count']} "
        f"unsupported={compliance_matrix.coverage_summary['unsupported_claim_count']}"
    )
    print(f"Compliance Control Mapping Pack: {compliance_control_pack.artifact_path}")
    print(f"Compliance Control Mapping Pack JSON: {compliance_control_pack.json_artifact_path}")
    print("Compliance packs directory: storage/compliance_packs")
    print(
        "Privacy retention guardrails: "
        f"surfaces={privacy_retention.summary['surface_count']} "
        f"high_risk={privacy_retention.summary['high_risk_surface_count']} "
        f"missing_controls={privacy_retention.summary['missing_control_count']}"
    )
    print(f"Privacy Retention Guardrail Pack: {privacy_retention_pack.artifact_path}")
    print(f"Privacy Retention Guardrail Pack JSON: {privacy_retention_pack.json_artifact_path}")
    print("Privacy packs directory: storage/privacy_packs")
    print(
        "Model risk register: "
        f"status={model_risk.register_status} "
        f"risks={model_risk.summary['risk_count']} "
        f"needs_review={model_risk.summary['needs_review_count']}"
    )
    print(f"Model Risk Register Pack: {model_risk_pack.artifact_path}")
    print(f"Model Risk Register Pack JSON: {model_risk_pack.json_artifact_path}")
    print("Model risk directory: storage/model_risk")
    print(
        "Procurement question risk: "
        f"questions={procurement_question_risk.coverage_summary['question_count']} "
        f"coverage={procurement_question_risk.coverage_summary['coverage_ratio']} "
        f"blocked={procurement_question_risk.approval_summary['blocked_count']} "
        f"approvals={procurement_question_risk.approval_summary['approvals_required_count']}"
    )
    print(f"Procurement Approval Workflow Pack: {procurement_approval_pack.artifact_path}")
    print(f"Procurement Approval Workflow Pack JSON: {procurement_approval_pack.json_artifact_path}")
    print("Procurement packs directory: storage/procurement_packs")
    print(
        "Procurement Risk Desk: "
        f"risks={procurement_risk_desk.summary['risk_count']} "
        f"blocked={procurement_risk_desk.summary['blocked_count']} "
        f"avg={procurement_risk_desk.summary['average_risk_score']} "
        f"governance={procurement_risk_desk.governance_summary['workflow_status']} "
        f"review_queue={procurement_risk_desk.governance_summary['human_review_queue_count']}"
    )
    print(f"Procurement Risk Desk Pack: {procurement_risk_desk_pack.artifact_path}")
    print(f"Procurement Risk Desk Pack JSON: {procurement_risk_desk_pack.json_artifact_path}")
    print("Procurement risk desk directory: storage/procurement_risk_desk")
    print(
        "Reviewer collaboration: "
        f"status={reviewer_collaboration.board_status} "
        f"assignments={len(reviewer_collaboration.assignments)} "
        f"comments={len(reviewer_collaboration.decision_comments)} "
        f"redlines={reviewer_collaboration.redline_summary['redline_count']}"
    )
    print(f"Reviewer Collaboration Pack: {reviewer_collaboration_pack.artifact_path}")
    print(f"Reviewer Collaboration Pack JSON: {reviewer_collaboration_pack.json_artifact_path}")
    print(
        "Reviewer workflow: "
        f"status={reviewer_workflow.workflow_status} "
        f"state={reviewer_workflow.current_state} "
        f"checkpoints={len(reviewer_workflow.checkpoints)} "
        f"transitions={len(reviewer_workflow.transitions)}"
    )
    print(f"Reviewer Workflow Pack: {reviewer_workflow_pack.artifact_path}")
    print(f"Reviewer Workflow Pack JSON: {reviewer_workflow_pack.json_artifact_path}")
    print("Review boards directory: storage/review_boards")
    print(
        "Reviewer signoff ledger: "
        f"status={reviewer_signoff.ledger_status} "
        f"records={reviewer_signoff.summary['record_count']} "
        f"blocked={reviewer_signoff.summary['blocked_count']} "
        f"queue={len(reviewer_signoff.human_review_queue)}"
    )
    print(f"Reviewer Signoff Pack: {reviewer_signoff_pack.artifact_path}")
    print(f"Reviewer Signoff Pack JSON: {reviewer_signoff_pack.json_artifact_path}")
    print("Reviewer signoff directory: storage/reviewer_signoffs")
    print(
        "Submission exceptions: "
        f"status={exception_register.register_status} "
        f"exceptions={exception_register.summary['exception_count']} "
        f"requires_approval={exception_register.summary['requires_approval_count']}"
    )
    print(f"Submission Exception Pack: {exception_pack.artifact_path}")
    print(f"Submission Exception Pack JSON: {exception_pack.json_artifact_path}")
    print("Exception registers directory: storage/exception_registers")
    print(
        "Bid/No-Bid scenario analysis: "
        f"scenarios={len(bid_scenario_analysis.scenarios)} "
        f"recommended={bid_scenario_analysis.recommended_scenario_id} "
        f"best risk-adjusted ROI={bid_scenario_analysis.coverage_summary['best_risk_adjusted_roi']}"
    )
    print(f"ROI Impact Pack: {bid_roi_pack.artifact_path}")
    print(f"ROI Impact Pack JSON: {bid_roi_pack.json_artifact_path}")
    print("Bid packs directory: storage/bid_packs")
    print(
        "Objection handling: "
        f"objections={objection_handling.coverage_summary['objection_count']} "
        f"coverage={objection_handling.coverage_summary['coverage_ratio']} "
        f"confidence={objection_handling.confidence_summary['average_confidence']} "
        f"blocked={objection_handling.coverage_summary['blocked_count']}"
    )
    print(f"Competitive Objection Handling Pack: {objection_pack.artifact_path}")
    print(f"Competitive Objection Handling Pack JSON: {objection_pack.json_artifact_path}")
    print("Objection packs directory: storage/objection_packs")
    print(
        "Win/Loss learning: "
        f"outcomes={win_loss_learning.outcome_count} "
        f"win_rate={win_loss_learning.win_rate} "
        f"win_patterns={len(win_loss_learning.winning_evidence_patterns)} "
        f"loss_patterns={len(win_loss_learning.losing_risk_patterns)}"
    )
    print(f"Win/Loss Strategy Pack: {win_loss_pack.artifact_path}")
    print(f"Win/Loss Strategy Pack JSON: {win_loss_pack.json_artifact_path}")
    print("Win/Loss packs directory: storage/win_loss_packs")
    print(
        "Win/Loss policy activation: "
        f"status={win_loss_policy.status} "
        f"rules={len(win_loss_policy.policy_rules)} "
        f"checkpoints={len(win_loss_policy.checkpoints)} "
        f"owners={len(win_loss_policy.owner_review_queue)}"
    )
    print(f"Win/Loss Policy Pack: {win_loss_policy_pack.artifact_path}")
    print(f"Win/Loss Policy Pack JSON: {win_loss_policy_pack.json_artifact_path}")
    print("Win/Loss policy directory: storage/win_loss_policy")
    print(
        "Retrieval experiments: "
        f"status={retrieval_experiments.status} "
        f"recommended={retrieval_experiments.recommended_policy_id} "
        f"policies={retrieval_experiments.summary['policy_count']} "
        f"questions={retrieval_experiments.summary['question_count']}"
    )
    print(f"Retrieval Experiment Pack: {retrieval_experiment_pack.artifact_path}")
    print(f"Retrieval Experiment Pack JSON: {retrieval_experiment_pack.json_artifact_path}")
    print("Retrieval experiments directory: storage/retrieval_experiments")
    print(
        "Proposal observability: "
        f"status={proposal_observability.status} "
        f"spans={proposal_observability.summary['trace_span_count']} "
        f"diagnostics={proposal_observability.summary['retrieval_diagnostic_count']} "
        f"human_review={proposal_observability.summary['human_review_signal_count']}"
    )
    print(f"Proposal Observability Pack: {proposal_observability_pack.artifact_path}")
    print(f"Proposal Observability Pack JSON: {proposal_observability_pack.json_artifact_path}")
    print("Proposal observability directory: storage/proposal_observability")
    print(
        "Verification evidence: "
        f"status={verification_evidence.status} "
        f"score={verification_evidence.score} "
        f"recorded={verification_evidence.summary['recorded_command_count']}/"
        f"{verification_evidence.summary['required_command_count']}"
    )
    print(f"Verification Evidence Pack: {verification_evidence_pack.artifact_path}")
    print(f"Verification Evidence Pack JSON: {verification_evidence_pack.json_artifact_path}")
    print("Verification evidence directory: storage/verification_evidence")
    print(f"Eval pass: {evaluation.passed}")
    print(f"Retrieval precision@k: {evaluation.retrieval_precision_at_k}")
    print(f"Citation coverage: {evaluation.citation_coverage}")
    print(
        "Red-team pass: "
        f"{red_team['passed']} missing={red_team['missing_evidence_detection_count']}/"
        f"{red_team['expected_missing_evidence']}"
    )
    print(
        "Final demo summary: "
        f"docs={documents_loaded} requirements={len(analysis.requirements)} "
        f"coverage={scorecard.evidence_coverage} citations={leadership_brief.brief['metrics']['citations']} "
        f"fit={customer_fit.fit_score} tasks={len(action_plan)} "
        f"answer_reuse={answer_reuse_library.status}/{answer_reuse_library.summary['snippet_count']} "
        f"answer_reuse_library={answer_reuse_library_pack.artifact_path} "
        f"answer_reuse_drift={answer_reuse_drift.status}/{answer_reuse_drift.summary['average_drift_score']} "
        f"answer_reuse_drift_pack={answer_reuse_drift_pack.artifact_path} "
        f"answer_reuse_approval={answer_reuse_approval.status}/{answer_reuse_approval.summary['record_count']} "
        f"answer_reuse_approval_pack={answer_reuse_approval_pack.artifact_path} "
        f"readiness={scorecard.readiness_score}/{scorecard.readiness_level} "
        f"readiness_pack={readiness_pack.artifact_path} "
        f"amendment_impact={amendment_impact.status}/{amendment_impact.summary['change_count']} "
        f"amendment_impact_pack={amendment_impact_pack.artifact_path} "
        f"win score={win_strategy.win_score}/{win_strategy.win_level} "
        f"pricing_memo={pricing_memo.artifact_path} "
        f"contract_risk={contract_risk.risk_score}/{contract_risk.status} "
        f"negotiation_brief={negotiation_brief.artifact_path} "
        f"gap count={evidence_gap_summary['gap_count']} "
        f"source_request_pack={source_request_pack.artifact_path} "
        f"milestone count={timeline_plan.summary['milestone_count']} "
        f"submission_calendar={submission_calendar.artifact_path} "
        f"submission_decision={submission_decision.decision}/{submission_decision.score} "
        f"submission_memo={executive_submission_memo.artifact_path} "
        f"launch readiness={launch_checklist.smoke_matrix.readiness_summary.readiness_level} "
        f"launch_checklist={launch_checklist.artifact_path} "
        f"cost_governance={cost_governance.governance_status}/"
        f"{cost_governance.budget_summary['daily_estimated_cost']} "
        f"cost_governance_pack={cost_governance_pack.artifact_path} "
        f"provider_resilience={provider_resilience.status}/{provider_resilience.recommended_route_id} "
        f"provider_resilience_pack={provider_resilience_pack.artifact_path} "
        f"evidence score={portfolio_evidence.evidence_score} "
        f"interview_pack={interview_pack.artifact_path} "
        f"reviewer_quickstart={reviewer_quickstart.status}/"
        f"{len(reviewer_quickstart.endpoint_walkthrough_order)} "
        f"walkthrough_pack={walkthrough_pack.artifact_path} "
        f"release_gate={release_gate.status}/{release_gate.score} "
        f"publish_pack={release_pack_artifact} "
        f"ci_doctor={ci_doctor.status}/{ci_doctor.score} "
        f"audit_pack={audit_pack.artifact_path} "
        f"artifact_inventory={artifact_inventory.total_directories} "
        f"readme_checklist={readme_checklist.artifact_path} "
        f"dashboard smoke={dashboard_smoke.status} "
        f"api_contract={contract_audit.status}/{contract_audit.openapi_route_count} "
        f"api_contracts={reviewer_collection.artifact_path} "
        f"ui_verification={ui_verification_pack.artifact_path} "
        f"final_audit={final_audit.status}/{final_audit.score} "
        f"final_handoff={final_pack_artifact} "
        f"git_readiness={git_readiness.status} "
        f"git_push_plan={git_push_plan.artifact_path} "
        f"runtime_demo={runtime_readiness.status} "
        f"runtime_pack={runtime_pack.artifact_path} "
        f"rag_coverage={rag_coverage.status}/{rag_coverage.score} "
        f"rag_coverage_pack={rag_coverage_pack.artifact_path} "
        f"freshness={evidence_freshness.summary['average_freshness_score']} "
        f"freshness_packs={evidence_freshness_pack.artifact_path} "
        f"conflicts={evidence_conflicts.summary['conflict_count']} "
        f"conflict_packs={evidence_conflict_pack.artifact_path} "
        f"citation_lineage={citation_lineage.score}/{citation_lineage.summary['citation_count']} "
        f"citation_lineage_pack={citation_lineage_pack.artifact_path} "
        f"source_trust={source_trust.status}/{source_trust.summary['average_trust_score']} "
        f"source_trust_pack={source_trust_pack.artifact_path} "
        f"governed_retrieval={governed_retrieval.status}/{governed_retrieval.summary['allowed_count']} "
        f"governed_retrieval_pack={governed_retrieval_pack.artifact_path} "
        f"buyer_intelligence={buyer_intelligence.workflow_status}/"
        f"{len(buyer_intelligence.human_approval_queue)} "
        f"buyer_intelligence_pack={buyer_intelligence_pack.artifact_path} "
        f"buyer_replay={buyer_workflow_replay.status}/{buyer_workflow_replay.transition_count} "
        f"buyer_replay_pack={buyer_workflow_replay_pack.artifact_path} "
        f"approval_simulation={approval_simulation.status}/{approval_simulation.unresolved_approval_count} "
        f"approval_simulation_pack={approval_simulation_pack.artifact_path} "
        f"agent_council={agent_council.status}/{len(agent_council.agents)} "
        f"agent_council_pack={agent_council_pack.artifact_path} "
        f"decision_provenance={decision_provenance.status}/{decision_provenance.summary['node_count']} "
        f"decision_provenance_pack={decision_provenance_pack.artifact_path} "
        f"buyer_contracts={buyer_structured_contracts.status}/{buyer_structured_contracts.score} "
        f"buyer_contracts_pack={buyer_structured_contracts_pack.artifact_path} "
        f"submission_certification={submission_certification.status}/{submission_certification.readiness_score} "
        f"submission_certification_pack={submission_certification_pack.artifact_path} "
        f"quality_benchmark={proposal_quality_benchmark.status}/{proposal_quality_benchmark.score} "
        f"quality_benchmark_pack={proposal_quality_benchmark_pack.artifact_path} "
        f"control coverage={compliance_matrix.coverage_summary['coverage_ratio']} "
        f"compliance_packs={compliance_control_pack.artifact_path} "
        f"privacy_retention={privacy_retention.summary['high_risk_surface_count']}/"
        f"{privacy_retention.summary['surface_count']} "
        f"privacy_packs={privacy_retention_pack.artifact_path} "
        f"model_risk={model_risk.register_status}/{model_risk.summary['risk_count']} "
        f"model_risk_pack={model_risk_pack.artifact_path} "
        f"procurement question risk={procurement_question_risk.coverage_summary['coverage_ratio']} "
        f"procurement_packs={procurement_approval_pack.artifact_path} "
        f"procurement_risk_desk={procurement_risk_desk.summary['average_risk_score']} "
        f"procurement_risk_desk_pack={procurement_risk_desk_pack.artifact_path} "
        f"reviewer_collaboration={reviewer_collaboration.board_status}/"
        f"{len(reviewer_collaboration.assignments)} "
        f"reviewer_workflow={reviewer_workflow.workflow_status}/"
        f"{reviewer_workflow.current_state} "
        f"review_boards={reviewer_collaboration_pack.artifact_path} "
        f"reviewer_workflow_pack={reviewer_workflow_pack.artifact_path} "
        f"reviewer_signoff={reviewer_signoff.ledger_status}/"
        f"{reviewer_signoff.summary['record_count']} "
        f"reviewer_signoff_pack={reviewer_signoff_pack.artifact_path} "
        f"exceptions={exception_register.register_status}/"
        f"{exception_register.summary['exception_count']} "
        f"exception_pack={exception_pack.artifact_path} "
        f"bid_scenarios={len(bid_scenario_analysis.scenarios)} "
        f"bid_packs={bid_roi_pack.artifact_path} "
        f"objection_handling={objection_handling.coverage_summary['coverage_ratio']} "
        f"objection_packs={objection_pack.artifact_path} "
        f"win_loss={win_loss_learning.win_rate}/{win_loss_learning.outcome_count} "
        f"win_loss_packs={win_loss_pack.artifact_path} "
        f"win_loss_policy={win_loss_policy.status}/{len(win_loss_policy.policy_rules)} "
        f"win_loss_policy_pack={win_loss_policy_pack.artifact_path} "
        f"retrieval_experiments={retrieval_experiments.recommended_policy_id}/{retrieval_experiments.status} "
        f"retrieval_experiment_pack={retrieval_experiment_pack.artifact_path} "
        f"proposal_observability={proposal_observability.status}/"
        f"{proposal_observability.summary['trace_span_count']} "
        f"proposal_observability_pack={proposal_observability_pack.artifact_path} "
        f"verification_evidence={verification_evidence.status}/{verification_evidence.score} "
        f"verification_evidence_pack={verification_evidence_pack.artifact_path} "
        f"red_team={red_team['passed']} brief={leadership_brief.artifact_path}"
    )


if __name__ == "__main__":
    asyncio.run(main())
