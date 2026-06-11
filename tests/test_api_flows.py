from pathlib import Path

from tests.conftest import ingest_corpus, ingest_sample


def test_health_and_auth(client, auth_headers):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["provider_mode"] == "mock"

    token = client.post("/auth/demo-token")
    assert token.status_code == 200
    assert token.json()["api_key"] == "test-key"

    unauthorized = client.get("/documents")
    assert unauthorized.status_code == 401

    authorized = client.get("/documents", headers=auth_headers)
    assert authorized.status_code == 200


def test_ingestion_and_document_listing(client, auth_headers):
    result = ingest_sample(client, auth_headers, "product_overview.md")
    assert result["document"]["filename"] == "product_overview.md"
    assert result["chunk_count"] >= 1

    documents = client.get("/documents", headers=auth_headers).json()
    assert len(documents) == 1
    assert documents[0]["document_type"] == "knowledge_base"


def test_rfp_analysis_extracts_business_fields(client, auth_headers):
    text = Path("sample_data/acme_enterprise_rfp.md").read_text(encoding="utf-8")
    response = client.post("/rfp/analyze", headers=auth_headers, json={"text": text})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["requirements"]) >= 8
    assert "July 18, 2026" in payload["deadlines"]
    assert payload["security_questions"]
    assert payload["compliance_asks"]
    assert payload["pricing_mentions"]


def test_query_returns_cited_answer_and_metrics(client, auth_headers):
    ingest_corpus(client, auth_headers)
    response = client.post(
        "/rfp/query",
        headers=auth_headers,
        json={"question": "What SSO and encryption controls are supported?", "top_k": 4},
    )
    assert response.status_code == 200
    answer = response.json()
    assert answer["citations"]
    assert answer["confidence"] >= 0.45
    assert not answer["missing_evidence"]
    assert any(citation["filename"] == "security_policy.md" for citation in answer["citations"])
    assert answer["trace_id"]

    usage = client.get("/metrics/usage", headers=auth_headers).json()
    assert usage["totals"]["request_count"] >= 1
    assert usage["totals"]["input_tokens"] > 0


def test_missing_evidence_is_flagged(client, auth_headers):
    ingest_corpus(client, auth_headers)
    response = client.post(
        "/rfp/query",
        headers=auth_headers,
        json={
            "question": "Does the product include quantum-resistant satellite telemetry controls?",
            "top_k": 4,
        },
    )
    assert response.status_code == 200
    answer = response.json()
    assert answer["citations"] == []
    assert answer["missing_evidence"]
    assert answer["confidence"] < 0.3

    review_response = client.post(
        "/rfp/review-answer",
        headers=auth_headers,
        json={
            "question": answer["question"],
            "answer_text": "Yes, quantum-resistant satellite telemetry controls are fully supported.",
            "citations": answer["citations"],
            "missing_evidence": answer["missing_evidence"],
            "token_usage": answer["token_usage"],
        },
    )
    assert review_response.status_code == 200
    review = review_response.json()
    categories = {finding["category"] for finding in review["findings"]}
    assert not review["passed"]
    assert "unsupported_claim" in categories
    assert "weak_citation" in categories


def test_draft_response_has_required_sections(client, auth_headers):
    ingest_corpus(client, auth_headers)
    analyze = client.post(
        "/rfp/analyze",
        headers=auth_headers,
        json={"fixture_path": "sample_data/acme_enterprise_rfp.md"},
    )
    assert analyze.status_code == 200

    response = client.post(
        "/rfp/draft-response",
        headers=auth_headers,
        json={
            "section_names": [
                "Executive Summary",
                "Technical Response",
                "Security Response",
                "Compliance Response",
            ],
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    draft = response.json()
    assert len(draft["sections"]) >= 4
    assert draft["citations"]
    assert draft["assumptions"]


def test_requirement_matrix_and_export_package(client, auth_headers):
    ingest_corpus(client, auth_headers)
    analyze = client.post(
        "/rfp/analyze",
        headers=auth_headers,
        json={"fixture_path": "sample_data/acme_enterprise_rfp.md"},
    )
    assert analyze.status_code == 200
    analysis = analyze.json()

    matrix_response = client.post(
        "/rfp/requirement-matrix",
        headers=auth_headers,
        json={"analyzed_payload": analysis},
    )
    assert matrix_response.status_code == 200
    matrix = matrix_response.json()["matrix"]
    assert len(matrix) == len(analysis["requirements"])
    assert {row["status"] for row in matrix} <= {
        "not_started",
        "evidence_found",
        "needs_review",
        "blocked",
    }
    assert any(row["evidence_refs"] for row in matrix)

    draft = client.post(
        "/rfp/draft-response",
        headers=auth_headers,
        json={"section_names": ["Executive Summary", "Security Response"], "top_k": 5},
    ).json()
    export_response = client.post(
        "/rfp/export-package",
        headers=auth_headers,
        json={"analyzed_payload": analysis, "draft_response": draft},
    )
    assert export_response.status_code == 200
    export = export_response.json()
    assert export["artifact_path"]
    assert Path(export["artifact_path"]).exists()
    assert Path(export["json_artifact_path"]).exists()
    assert export["package"]["executive_summary"]["requirement_count"] == len(matrix)
    assert "## Requirement Matrix" in export["markdown"]

    risky_matrix = [dict(matrix[0])]
    risky_matrix[0]["status"] = "blocked"
    risky_matrix[0]["risk_level"] = "high"
    risky_matrix[0]["evidence_refs"] = []
    risky_matrix[0]["missing_evidence"] = ["No explicit support evidence attached."]
    review_response = client.post(
        "/rfp/review-package",
        headers=auth_headers,
        json={"requirement_matrix": risky_matrix, "draft_response": draft, "export_payload": export["package"]},
    )
    assert review_response.status_code == 200
    review = review_response.json()
    assert review["requirement_matrix"]
    assert "finding_count" in review["summary"]
    assert any(
        finding["category"] in {"missing_evidence", "high_risk_requirement"}
        for finding in review["findings"]
    )

    action_response = client.post(
        "/rfp/action-plan",
        headers=auth_headers,
        json={
            "analyzed_payload": analysis,
            "requirement_matrix": risky_matrix,
            "review_findings": review["findings"],
            "customer_profile_id": "regulated_healthcare",
        },
    )
    assert action_response.status_code == 200
    action_plan = action_response.json()
    assert action_plan["tasks"]
    assert action_plan["summary"]["blocked_tasks"] >= 1
    assert {task["owner_role"] for task in action_plan["tasks"]} <= {
        "sales",
        "solutions",
        "security",
        "legal",
        "product",
        "engineering",
    }
    assert any(task["status"] == "blocked" for task in action_plan["tasks"])

    handoff_response = client.post(
        "/rfp/handoff-board",
        headers=auth_headers,
        json={
            "analyzed_payload": analysis,
            "requirement_matrix": risky_matrix,
            "review_findings": review["findings"],
            "customer_profile_id": "regulated_healthcare",
            "action_plan": action_plan["tasks"],
        },
    )
    assert handoff_response.status_code == 200
    handoff = handoff_response.json()
    assert handoff["artifact_path"]
    assert Path(handoff["artifact_path"]).exists()
    assert Path(handoff["json_artifact_path"]).exists()
    assert "storage" in handoff["artifact_path"]
    assert "handoffs" in handoff["artifact_path"]
    assert "## Next Meeting Agenda" in handoff["markdown"]
    assert handoff["board"]["blocked_items"]
    assert handoff["board"]["missing_evidence"]

    readiness_response = client.post(
        "/rfp/readiness-scorecard",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "review_findings": review["findings"],
            "customer_fit": action_plan.get("customer_fit"),
            "action_plan": action_plan["tasks"],
        },
    )
    assert readiness_response.status_code == 200
    scorecard = readiness_response.json()
    assert scorecard["readiness_score"] < 85
    assert scorecard["readiness_level"] in {"mostly_ready", "at_risk", "not_ready"}
    assert scorecard["blockers"]
    assert scorecard["owner_bottlenecks"]
    assert scorecard["score_trace"]
    assert scorecard["score_trace"][-1]["component"] == "final_readiness_score"
    assert scorecard["approval_workflow"]
    assert any(item["human_review_required"] for item in scorecard["approval_workflow"])
    assert scorecard["human_review_queue"]
    assert "human_in_the_loop_exception_gate" in scorecard["governance_summary"]["controls"]

    report_response = client.post(
        "/rfp/executive-risk-report",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "review_findings": review["findings"],
            "action_plan": action_plan["tasks"],
            "red_team_summary": {"passed": True, "missing_evidence_detection_count": 2},
        },
    )
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["artifact_path"]
    assert Path(report["artifact_path"]).exists()
    assert Path(report["json_artifact_path"]).exists()
    assert "reports" in report["artifact_path"]
    assert "## Submission Recommendation" in report["markdown"]
    assert "submission_recommendation" in report["report"]

    readiness_pack_response = client.post(
        "/rfp/proposal-readiness-score-pack",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "draft_response": draft,
            "review_findings": review["findings"],
            "action_plan": action_plan["tasks"],
            "readiness_scorecard": scorecard,
            "executive_report": report,
            "red_team_summary": {"passed": True, "missing_evidence_detection_count": 2},
            "write_artifact": True,
        },
    )
    assert readiness_pack_response.status_code == 200
    readiness_pack = readiness_pack_response.json()
    assert readiness_pack["artifact_path"]
    assert readiness_pack["json_artifact_path"]
    assert Path(readiness_pack["artifact_path"]).exists()
    assert Path(readiness_pack["json_artifact_path"]).exists()
    assert "readiness_packs" in readiness_pack["artifact_path"]
    assert readiness_pack["pack"]["section_completeness"]["sections"]
    assert readiness_pack["pack"]["evidence_coverage"]["uncovered_requirement_count"] >= 1
    assert readiness_pack["pack"]["compliance_risk"]["risk_level"] in {"low", "medium", "high", "critical"}
    assert readiness_pack["pack"]["reviewer_bottlenecks"]
    assert readiness_pack["pack"]["score_trace_analysis"]["largest_deductions"]
    assert readiness_pack["pack"]["durable_approval_workflow"]
    assert readiness_pack["pack"]["human_review_queue"]
    assert "POST /rfp/proposal-readiness-score-pack" in readiness_pack["markdown"]
    assert "## Durable Approval Workflow" in readiness_pack["markdown"]

    contract_text = Path("sample_data/customer_contract_terms.md").read_text(encoding="utf-8")
    contract_risk = client.post(
        "/rfp/contract-risk",
        headers=auth_headers,
        json={"text": contract_text, "customer_profile_id": "regulated_healthcare"},
    ).json()
    gaps_response = client.post(
        "/rfp/evidence-gaps",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "review_findings": review["findings"],
            "readiness_scorecard": scorecard,
            "contract_risk": contract_risk,
            "action_plan": action_plan["tasks"],
            "red_team_summary": {"passed": True, "missing_evidence_detection_count": 2},
        },
    )
    assert gaps_response.status_code == 200
    gaps = gaps_response.json()
    assert gaps["summary"]["gap_count"] >= 1
    assert gaps["summary"]["high_severity_count"] >= 1
    assert gaps["gaps"][0]["priority_rank"] == 1
    assert gaps["gaps"][0]["closure_acceptance_criteria"]
    assert any("source_signals" in gap and gap["source_signals"] for gap in gaps["gaps"])

    pack_response = client.post(
        "/rfp/source-request-pack",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "review_findings": review["findings"],
            "readiness_scorecard": scorecard,
            "contract_risk": contract_risk,
            "action_plan": action_plan["tasks"],
            "evidence_gaps": gaps["gaps"],
            "write_artifact": True,
        },
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "source_requests" in pack["artifact_path"]
    assert "## Source Request Emails and Tasks" in pack["markdown"]
    assert pack["pack"]["owner_matrix"]
    assert pack["pack"]["source_request_emails_tasks"]
    assert len(pack["pack"]["interviewer_talking_points"]) == 5

    timeline_response = client.post(
        "/rfp/timeline-plan",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "review_findings": review["findings"],
            "readiness_scorecard": scorecard,
            "contract_risk": contract_risk,
            "action_plan": action_plan["tasks"],
            "evidence_gaps": gaps["gaps"],
            "source_request_pack": pack["pack"],
            "red_team_summary": {"passed": True, "missing_evidence_detection_count": 2},
        },
    )
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()
    assert timeline["summary"]["milestone_count"] >= 6
    assert timeline["summary"]["blocked_count"] >= 1
    assert timeline["milestones"] == sorted(timeline["milestones"], key=lambda item: item["due_date"])
    assert timeline["dependencies"]
    assert timeline["readiness_gates"]
    assert timeline["calendar_entries"]

    calendar_response = client.post(
        "/rfp/submission-calendar-pack",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "review_findings": review["findings"],
            "readiness_scorecard": scorecard,
            "contract_risk": contract_risk,
            "action_plan": action_plan["tasks"],
            "evidence_gaps": gaps["gaps"],
            "source_request_pack": pack["pack"],
            "timeline_plan": timeline,
            "write_artifact": True,
        },
    )
    assert calendar_response.status_code == 200
    calendar_pack = calendar_response.json()
    assert calendar_pack["artifact_path"]
    assert calendar_pack["json_artifact_path"]
    assert Path(calendar_pack["artifact_path"]).exists()
    assert Path(calendar_pack["json_artifact_path"]).exists()
    assert "submission_calendars" in calendar_pack["artifact_path"]
    assert "## Milestone Calendar" in calendar_pack["markdown"]
    assert calendar_pack["pack"]["owner_matrix"]
    assert len(calendar_pack["pack"]["interviewer_talking_points"]) == 5

    decision_response = client.post(
        "/rfp/submission-decision",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "draft_response": draft,
            "review_findings": review["findings"],
            "review_passed": review["passed"],
            "readiness_scorecard": scorecard,
            "contract_risk": contract_risk,
            "action_plan": action_plan["tasks"],
            "evidence_gaps": gaps["gaps"],
            "source_request_pack": pack["pack"],
            "timeline_plan": timeline,
            "source_request_artifact_path": pack["artifact_path"],
            "source_request_json_artifact_path": pack["json_artifact_path"],
            "submission_calendar_artifact_path": calendar_pack["artifact_path"],
            "submission_calendar_json_artifact_path": calendar_pack["json_artifact_path"],
        },
    )
    assert decision_response.status_code == 200
    decision = decision_response.json()
    assert decision["decision"] in {"submit", "submit_with_exceptions", "do_not_submit"}
    assert decision["score"] >= 0
    assert decision["blocking_issues"]
    assert decision["approvals_required"]
    assert decision["local_verification_commands"]

    memo_response = client.post(
        "/rfp/executive-submission-memo",
        headers=auth_headers,
        json={"submission_decision": decision, "write_artifact": True},
    )
    assert memo_response.status_code == 200
    memo = memo_response.json()
    assert memo["artifact_path"]
    assert memo["json_artifact_path"]
    assert Path(memo["artifact_path"]).exists()
    assert Path(memo["json_artifact_path"]).exists()
    assert "submission_memos" in memo["artifact_path"]
    assert "## Go/No-Go Summary" in memo["markdown"]
    assert "go_no_go_summary" in memo["memo"]

    brief_response = client.post(
        "/rfp/leadership-brief",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "draft_response": draft,
            "export_payload": export["package"],
            "export_artifact_path": export["artifact_path"],
            "export_json_artifact_path": export["json_artifact_path"],
            "review_findings": review["findings"],
            "review_passed": review["passed"],
            "customer_profile_id": "regulated_healthcare",
            "action_plan": action_plan["tasks"],
            "handoff_board": handoff["board"],
            "handoff_artifact_path": handoff["artifact_path"],
            "handoff_json_artifact_path": handoff["json_artifact_path"],
            "readiness_scorecard": scorecard,
            "executive_report": report,
            "red_team_summary": {"passed": True, "missing_evidence_detection_count": 2},
        },
    )
    assert brief_response.status_code == 200
    brief = brief_response.json()
    assert brief["artifact_path"]
    assert Path(brief["artifact_path"]).exists()
    assert Path(brief["json_artifact_path"]).exists()
    assert "leadership_briefs" in brief["artifact_path"]
    assert "## Local Artifact Links" in brief["markdown"]
    assert "Recommended Next Meeting Agenda" in brief["markdown"]
    assert brief["brief"]["metrics"]["docs_ingested"] >= 6
    assert brief["brief"]["metrics"]["requirements"] == len(analysis["requirements"])
    assert brief["brief"]["metrics"]["red_team_pass"] is True
    assert brief["brief"]["metrics"]["readiness_score"] == scorecard["readiness_score"]
    assert brief["brief"]["artifact_links"]["export_package"]["artifact_path"] == export["artifact_path"]
    assert brief["brief"]["artifact_links"]["executive_report"]["artifact_path"] == report["artifact_path"]
    assert brief["brief"]["recommended_next_meeting_agenda"]


def test_customer_profiles_fit_and_response_memory(client, auth_headers):
    ingest_corpus(client, auth_headers)
    profiles_response = client.get("/customers/profiles", headers=auth_headers)
    assert profiles_response.status_code == 200
    profiles = profiles_response.json()["profiles"]
    assert len(profiles) == 3
    profile_ids = {profile["id"] for profile in profiles}
    assert {"regulated_healthcare", "fintech", "public_sector"} == profile_ids

    analysis = client.post(
        "/rfp/analyze",
        headers=auth_headers,
        json={"fixture_path": "sample_data/acme_enterprise_rfp.md"},
    ).json()
    matrix = client.post(
        "/rfp/requirement-matrix",
        headers=auth_headers,
        json={"analyzed_payload": analysis},
    ).json()["matrix"]
    fit_response = client.post(
        "/rfp/customer-fit",
        headers=auth_headers,
        json={
            "customer_profile_id": "regulated_healthcare",
            "analyzed_payload": analysis,
            "requirement_matrix": matrix,
        },
    )
    assert fit_response.status_code == 200
    fit = fit_response.json()
    assert fit["fit_score"] > 40
    assert fit["customer_profile"]["industry"] == "healthcare"
    assert fit["recommended_positioning"]
    assert fit["requirements_to_emphasize"]
    assert "trace_id" in fit

    memory_response = client.post(
        "/rfp/response-memory/search",
        headers=auth_headers,
        json={
            "query": "SSO encryption SOC 2 audit controls",
            "category": "security",
            "customer_profile_id": "regulated_healthcare",
            "top_k": 3,
        },
    )
    assert memory_response.status_code == 200
    matches = memory_response.json()["matches"]
    assert matches
    assert matches[0]["confidence"] >= 0.4
    assert matches[0]["tags"]
    assert matches[0]["citations"]

    draft = client.post(
        "/rfp/draft-response",
        headers=auth_headers,
        json={"section_names": ["Executive Summary", "Security Response"], "top_k": 5},
    ).json()
    export_response = client.post(
        "/rfp/export-package",
        headers=auth_headers,
        json={
            "analyzed_payload": analysis,
            "draft_response": draft,
            "customer_profile_id": "regulated_healthcare",
            "include_response_memory": True,
            "write_artifact": False,
        },
    )
    assert export_response.status_code == 200
    export = export_response.json()
    assert export["package"]["customer_fit"]["customer_profile"]["id"] == "regulated_healthcare"
    assert export["package"]["response_memory_matches"]
    assert "## Customer Fit" in export["markdown"]
    assert "## Approved Response Memory" in export["markdown"]


def test_win_strategy_endpoint_returns_cited_proof_points(client, auth_headers):
    ingest_corpus(client, auth_headers)
    analysis = client.post(
        "/rfp/analyze",
        headers=auth_headers,
        json={"fixture_path": "sample_data/acme_enterprise_rfp.md"},
    ).json()
    matrix = client.post(
        "/rfp/requirement-matrix",
        headers=auth_headers,
        json={"analyzed_payload": analysis},
    ).json()["matrix"]

    response = client.post(
        "/rfp/win-strategy",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": matrix,
            "customer_profile_id": "regulated_healthcare",
            "competitor_context": ["Incumbent competitor may bundle workflow tooling."],
        },
    )
    assert response.status_code == 200
    strategy = response.json()
    assert 0 <= strategy["win_score"] <= 100
    assert strategy["win_level"] in {"strong", "competitive", "at_risk", "unlikely_without_changes"}
    assert strategy["competitor_risk_profile"]["risk_level"] in {"medium", "high"}
    assert strategy["pricing_risk"]["risk_level"] in {"medium", "high"}
    assert strategy["recommended_response_posture"]
    assert strategy["proof_points"]
    assert any(point["citations"] and point["source_snippet"] for point in strategy["proof_points"])
    assert strategy["compliance_security_differentiators"]
    assert strategy["next_actions_by_owner"]


def test_pricing_risk_memo_exports_high_risk_competitor_scenario(client, auth_headers):
    ingest_corpus(client, auth_headers)
    analysis = client.post(
        "/rfp/analyze",
        headers=auth_headers,
        json={"fixture_path": "sample_data/acme_enterprise_rfp.md"},
    ).json()
    matrix = client.post(
        "/rfp/requirement-matrix",
        headers=auth_headers,
        json={"analyzed_payload": analysis},
    ).json()["matrix"]
    risky_matrix = []
    for row in matrix:
        updated = dict(row)
        if updated["category"] == "pricing":
            updated["status"] = "blocked"
            updated["risk_level"] = "high"
            updated["evidence_refs"] = []
            updated["missing_evidence"] = ["No approved discount or packaging exception attached."]
        risky_matrix.append(updated)

    memo_response = client.post(
        "/rfp/pricing-risk-memo",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "customer_profile_id": "regulated_healthcare",
            "competitor_context": [
                "Incumbent competitor is cheaper, bundled, and offering a 25% discount with price match pressure.",
            ],
            "pricing_notes": [
                "Any volume discount, custom enterprise tier, usage overage, or payment term needs approval.",
            ],
            "write_artifact": True,
        },
    )
    assert memo_response.status_code == 200
    memo = memo_response.json()
    assert memo["artifact_path"]
    assert memo["json_artifact_path"]
    assert Path(memo["artifact_path"]).exists()
    assert Path(memo["json_artifact_path"]).exists()
    assert "pricing_memos" in memo["artifact_path"]
    assert memo["memo"]["win_score"] < 70
    assert memo["memo"]["discount_packaging_risks"]
    assert memo["memo"]["cited_proof_points"]
    assert len(memo["memo"]["interviewer_talking_points"]) == 5
    assert "## Discount and Packaging Risks" in memo["markdown"]
    assert "## JD Skills Demonstrated" in memo["markdown"]


def test_contract_risk_and_negotiation_brief_endpoints(client, auth_headers):
    ingest_corpus(client, auth_headers)
    contract_text = Path("sample_data/customer_contract_terms.md").read_text(encoding="utf-8")

    risk_response = client.post(
        "/rfp/contract-risk",
        headers=auth_headers,
        json={"text": contract_text, "customer_profile_id": "regulated_healthcare"},
    )
    assert risk_response.status_code == 200
    risk = risk_response.json()
    assert risk["risk_score"] >= 60
    assert risk["status"] in {"high_risk", "critical"}
    assert risk["risky_clauses"]
    assert risk["category_counts"]["pricing_payment"] == 1
    assert risk["suggested_redlines"]
    assert risk["fallback_positions"]
    assert risk["cited_proof_points"]
    assert any(clause["category"] == "data_processing" for clause in risk["risky_clauses"])
    assert any(action["owner"] == "legal" for action in risk["owner_actions"])

    brief_response = client.post(
        "/rfp/negotiation-brief",
        headers=auth_headers,
        json={"contract_risk": risk, "write_artifact": True},
    )
    assert brief_response.status_code == 200
    brief = brief_response.json()
    assert brief["artifact_path"]
    assert brief["json_artifact_path"]
    assert Path(brief["artifact_path"]).exists()
    assert Path(brief["json_artifact_path"]).exists()
    assert "negotiation_briefs" in brief["artifact_path"]
    assert "## Clause-by-Clause Redlines" in brief["markdown"]
    assert "## Exact Local Commands" in brief["markdown"]
    assert brief["brief"]["contract_risk_summary"]["risk_score"] == risk["risk_score"]
    assert len(brief["brief"]["interviewer_talking_points"]) == 5


def test_evaluation_and_audit_events(client, auth_headers):
    ingest_corpus(client, auth_headers)
    response = client.post(
        "/rfp/evaluate",
        headers=auth_headers,
        json={"dataset_path": "sample_data/eval_dataset.json", "top_k": 4},
    )
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["question_count"] == 12
    assert metrics["citation_coverage"] >= 0.7
    assert metrics["missing_evidence_detection_count"] >= 1
    assert metrics["input_tokens"] > 0
    assert "estimated_cost" in metrics

    audit = client.get("/audit/events", headers=auth_headers).json()
    actions = {event["action"] for event in audit["events"]}
    assert "document.ingested" in actions
    assert "eval.completed" in actions


def test_rag_corpus_coverage_and_eval_pack(client, auth_headers):
    ingest_corpus(client, auth_headers)

    coverage_response = client.get("/rag/corpus-coverage", headers=auth_headers)
    assert coverage_response.status_code == 200
    coverage = coverage_response.json()
    assert coverage["title"] == "RAG Corpus Coverage"
    assert coverage["status"] == "pass"
    assert coverage["score"] >= 90
    assert coverage["corpus_metadata"]["sample_document_count"] >= 12
    assert coverage["corpus_metadata"]["required_enterprise_pack_doc_count"] == 6
    assert coverage["doc_category_coverage"]["coverage"] == 1.0
    assert coverage["eval_coverage"]["coverage"] == 1.0
    assert coverage["citation_source_coverage"]["coverage"] == 1.0
    assert coverage["red_team_coverage"]["coverage"] == 1.0
    assert coverage["missing_evidence_coverage"]["coverage"] == 1.0
    assert not coverage["gaps"]
    assert any(
        doc["filename"] == "implementation_guide.md" and doc["indexed_in_current_repo"]
        for doc in coverage["corpus_metadata"]["documents"]
    )

    pack_response = client.post("/rag/eval-coverage-pack", headers=auth_headers, json={"write_artifact": True})
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "rag_coverage" in pack["artifact_path"]
    assert "RAG Eval Coverage Pack" in pack["markdown"]
    assert "Document Categories" in pack["markdown"]
    assert pack["coverage"]["status"] == "pass"
    assert pack["pack"]["deterministic_checks"]


def test_submission_regression_and_demo_script_endpoints(client, auth_headers):
    regression_response = client.post(
        "/rfp/submission-regression",
        headers=auth_headers,
        json={"write_artifacts": True, "top_k": 4},
    )
    assert regression_response.status_code == 200
    regression = regression_response.json()
    assert regression["passed"]
    assert regression["failed_checks"] == []
    assert "missing-evidence" in " ".join(regression["warnings"])
    assert regression["artifact_paths"]["executive_report_markdown"]
    assert Path(regression["artifact_paths"]["executive_report_markdown"]).exists()
    missing_check = next(
        check for check in regression["checks"] if check["name"] == "cited_query_and_missing_evidence_behavior"
    )
    assert missing_check["passed"]
    assert missing_check["details"]["missing_evidence_items"] >= 1

    script_response = client.post(
        "/rfp/demo-script",
        headers=auth_headers,
        json={"regression": regression, "run_regression": False, "write_artifact": True},
    )
    assert script_response.status_code == 200
    script = script_response.json()
    assert script["artifact_path"]
    assert script["json_artifact_path"]
    assert Path(script["artifact_path"]).exists()
    assert "demo_scripts" in script["artifact_path"]
    assert "## Exact Local Commands" in script["markdown"]
    assert "POST /rfp/submission-regression" in script["markdown"]
    assert len(script["script"]["interviewer_talking_points"]) == 5


def test_portfolio_evidence_index_and_interview_pack(client, auth_headers):
    evidence_response = client.get("/portfolio/evidence-index", headers=auth_headers)

    assert evidence_response.status_code == 200
    evidence = evidence_response.json()
    assert evidence["title"] == "Portfolio Evidence Index"
    assert evidence["evidence_score"] >= 90
    assert evidence["covered_skill_count"] == evidence["total_skill_count"]
    skill_ids = {skill["skill_id"] for skill in evidence["skills"]}
    assert {
        "rag-vector-retrieval",
        "document-ingestion",
        "citations-missing-evidence",
        "eval-red-team",
        "portfolio-evidence-pack",
    }.issubset(skill_ids)
    assert any("/portfolio/evidence-index" in skill["endpoints"] for skill in evidence["skills"])
    assert any("python -m app.demo" in command for command in evidence["proof_commands"])
    assert "portfolio_packs" in evidence["artifact_roots"]

    pack_response = client.post(
        "/portfolio/interview-pack",
        headers=auth_headers,
        json={
            "run_regression": True,
            "regression_request": {"top_k": 4, "write_artifacts": False},
            "write_artifact": True,
        },
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "portfolio_packs" in pack["artifact_path"]
    assert "Portfolio Evidence" in pack["markdown"]
    assert "Interview Script Pack" in pack["markdown"]
    assert "evidence score" in pack["markdown"].lower()
    assert len(pack["pack"]["three_minute_demo_script"]) == 5
    assert 8 <= len(pack["pack"]["technical_talking_points"]) <= 10
    assert pack["pack"]["metrics_eval_summary"]["standard_eval"]["passed"] is True
    assert pack["pack"]["metrics_eval_summary"]["red_team"]["passed"] is True
    assert len(pack["pack"]["resume_github_readme_bullets"]) >= 3


def test_reviewer_quickstart_and_walkthrough_pack(client, auth_headers):
    quickstart_response = client.get("/reviewer/quickstart", headers=auth_headers)

    assert quickstart_response.status_code == 200
    quickstart = quickstart_response.json()
    assert quickstart["title"] == "Reviewer Quickstart + Recruiter Walkthrough Pack"
    assert quickstart["status"] == "ready_for_local_review"
    assert quickstart["one_command_demo"] == "python -m app.demo"
    assert any(command == "python -m pytest -q" for command in quickstart["verification_commands"])
    assert any("reviewer/quickstart" in command for command in quickstart["verification_commands"])
    assert any(row["path"] == "/reviewer/walkthrough-pack" for row in quickstart["endpoint_walkthrough_order"])
    assert "reviewer_packs" in quickstart["artifact_proof_map"]
    assert quickstart["expected_outputs"]["endpoint_count"] == len(quickstart["endpoint_walkthrough_order"])
    assert "proof tour" in " ".join(quickstart["proof_tour"]).lower()
    assert "recruiter" in quickstart["role_specific_reviewer_notes"]
    assert "Reviewer Quickstart" in quickstart["github_readme_blurb"]

    pack_response = client.post(
        "/reviewer/walkthrough-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "reviewer_packs" in pack["artifact_path"]
    assert "Reviewer Quickstart Walkthrough Pack" in pack["markdown"]
    assert "API/RAG Proof Tour" in pack["markdown"]
    assert "GitHub README Blurb" in pack["markdown"]
    assert pack["pack"]["recruiter_friendly_story"]
    assert pack["pack"]["engineer_deep_dive_path"]
    assert pack["pack"]["command_checklist"]
    assert pack["pack"]["api_rag_proof_tour"]
    assert pack["pack"]["artifacts_to_inspect"]["reviewer_packs"]["path"]
    assert pack["quickstart"]["status"] == quickstart["status"]


def test_artifact_inventory_and_readme_checklist_pack(client, auth_headers):
    launch_response = client.post(
        "/ops/launch-checklist",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert launch_response.status_code == 200
    assert Path(launch_response.json()["artifact_path"]).exists()

    inventory_response = client.get("/artifacts/inventory", headers=auth_headers)
    assert inventory_response.status_code == 200
    inventory = inventory_response.json()
    assert inventory["title"] == "Artifact Inventory"
    assert inventory["ignored_status"] == "ignored_by_gitignore_storage_rule"
    assert inventory["total_directories"] >= 16
    assert any(item["key"] == "launch_checklists" for item in inventory["directories"])
    launch_item = next(item for item in inventory["directories"] if item["key"] == "launch_checklists")
    assert launch_item["file_count"] >= 2
    assert launch_item["latest_files"]
    assert launch_item["producer_endpoint"] == "POST /ops/launch-checklist"
    assert "Regenerate" not in " ".join(launch_item["freshness_notes"])
    assert any("POST /artifacts/readme-checklist" in item["producer_endpoint"] for item in inventory["directories"])
    assert any("reviewer proof checklist" in item.lower() for item in inventory["reviewer_proof_checklist"])

    checklist_response = client.post(
        "/artifacts/readme-checklist",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert checklist_response.status_code == 200
    checklist = checklist_response.json()
    assert checklist["artifact_path"]
    assert checklist["json_artifact_path"]
    assert Path(checklist["artifact_path"]).exists()
    assert Path(checklist["json_artifact_path"]).exists()
    assert "artifact_indexes" in checklist["artifact_path"]
    assert "README Checklist" in checklist["markdown"]
    assert "Artifact Inventory" in checklist["markdown"]
    assert "reviewer proof checklist" in checklist["markdown"].lower()
    assert checklist["checklist"]["readme_badge_suggestions"]
    assert checklist["checklist"]["cleanup_regeneration_notes"]
