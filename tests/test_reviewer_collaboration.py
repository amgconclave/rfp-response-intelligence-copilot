from pathlib import Path

from tests.conftest import ingest_corpus


def test_reviewer_collaboration_board_and_pack(client, auth_headers):
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
    risky_matrix = [dict(row) for row in matrix]
    risky_matrix[0]["status"] = "blocked"
    risky_matrix[0]["risk_level"] = "high"
    risky_matrix[0]["evidence_refs"] = []
    risky_matrix[0]["missing_evidence"] = ["No approved reviewer evidence attached."]

    review = client.post(
        "/rfp/review-package",
        headers=auth_headers,
        json={"requirement_matrix": risky_matrix},
    ).json()
    action_plan = client.post(
        "/rfp/action-plan",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "requirement_matrix": risky_matrix,
            "review_findings": review["findings"],
        },
    ).json()
    contract_text = Path("sample_data/customer_contract_terms.md").read_text(encoding="utf-8")
    contract_risk = client.post(
        "/rfp/contract-risk",
        headers=auth_headers,
        json={"text": contract_text, "customer_profile_id": "regulated_healthcare"},
    ).json()
    gaps = client.post(
        "/rfp/evidence-gaps",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "review_findings": review["findings"],
            "contract_risk": contract_risk,
            "action_plan": action_plan["tasks"],
        },
    ).json()["gaps"]

    response = client.post(
        "/rfp/reviewer-collaboration",
        headers=auth_headers,
        json={
            "analysis": analysis,
            "matrix": risky_matrix,
            "review_findings": review["findings"],
            "review_passed": review["passed"],
            "action_plan": action_plan["tasks"],
            "evidence_gaps": gaps,
            "contract_risk": contract_risk,
        },
    )

    assert response.status_code == 200
    board = response.json()
    assert board["title"] == "Reviewer Collaboration Board"
    assert board["board_status"] in {"blocked", "needs_review", "pending_review", "approved"}
    assert board["assignments"]
    assert board["decision_comments"]
    assert board["approval_summary"]["assignment_count"] == len(board["assignments"])
    assert board["approval_summary"]["blocked_count"] >= 1
    assert board["redline_summary"]["redline_count"] >= 1
    assert board["redline_summary"]["requires_legal_approval"] is True
    assert any(item["reviewer_role"] == "legal" for item in board["assignments"])
    assert any(comment["category"] == "redline" for comment in board["decision_comments"])
    assert any("reviewer-collaboration-pack" in command for command in board["local_proof_commands"])

    pack_response = client.post(
        "/rfp/reviewer-collaboration-pack",
        headers=auth_headers,
        json={"collaboration": board, "write_artifact": True},
    )
    assert pack_response.status_code == 200
    pack = pack_response.json()
    artifact_path = Path(pack["artifact_path"])
    json_artifact_path = Path(pack["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "review_boards" in str(artifact_path)
    assert "Reviewer Collaboration Pack" in pack["markdown"]
    assert "## Reviewer Assignments" in pack["markdown"]
    assert "## Decision Comments" in pack["markdown"]
    assert "## Redline Summary" in pack["markdown"]
    assert pack["pack"]["approval_summary"]["blocked_count"] >= 1


def test_reviewer_collaboration_in_smoke_inventory_and_dashboard(client, auth_headers):
    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"] for row in smoke["rows"]}
    assert "/rfp/reviewer-collaboration" in paths
    assert "/rfp/reviewer-collaboration-pack" in paths
    assert any(
        "storage/review_boards" in expectation
        for row in smoke["rows"]
        for expectation in row["required_artifact_expectations"]
    )

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "review_boards" in {item["key"] for item in inventory["directories"]}

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Reviewer Collaboration" for view in dashboard_smoke["expected_views"])
    assert any(
        endpoint["path"] == "/rfp/reviewer-collaboration-pack"
        for endpoint in dashboard_smoke["endpoint_references"]
    )
