from pathlib import Path


def test_proposal_review_gate_exposes_role_criteria_delegations_and_eval_assertions(client, auth_headers):
    response = client.get("/proposal/review-gate", headers=auth_headers)

    assert response.status_code == 200
    gate = response.json()
    assert gate["title"] == "Proposal Intelligence Review Gate"
    assert gate["status"] in {
        "ready_for_buyer_review",
        "requires_role_review",
        "blocked_by_review_gate",
    }
    assert gate["score"] >= 40
    assert gate["injected_dependencies"]["external_provider_required"] is False
    assert gate["summary"]["criterion_count"] == 4
    assert {
        "typed contracts",
        "structured outputs",
        "dependency injection",
        "eval-friendly design",
        "role crews",
        "task delegation",
        "checkpointing",
    } <= set(gate["summary"]["radar_patterns_used"])
    assert {criterion["owner_role"] for criterion in gate["criteria"]} == {
        "Sales Lead",
        "Presales Architect",
        "Compliance Reviewer",
        "Procurement Lead",
    }
    assert all(criterion["endpoint_refs"] for criterion in gate["criteria"])
    assert len(gate["state_transitions"]) == len(gate["criteria"])
    assert all(transition["checkpoint_key"] for transition in gate["state_transitions"])
    assert len(gate["task_delegations"]) == len(gate["criteria"])
    assert all(assertion["passed"] for assertion in gate["eval_assertions"])
    assert any("/proposal/review-gate-pack" in command for command in gate["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.review_gate_viewed" for event in audit["events"])


def test_proposal_review_gate_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post("/proposal/review-gate-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "proposal_review_gates" in pack["artifact_path"]
    assert "Proposal Intelligence Review Gate Pack" in pack["markdown"]
    assert pack["review_gate"]["summary"]["criterion_count"] == 4

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/review-gate" in paths
    assert "/proposal/review-gate-pack" in paths
    assert "storage/proposal_review_gates/*.json" in paths["/proposal/review-gate-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Review Gate" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/review-gate", "/proposal/review-gate-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "proposal_review_gates" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/review-gate", "/proposal/review-gate-pack"} <= proposal_endpoints
    assert "/proposal/review-gate-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.review_gate_pack_generated" for event in audit["events"])
