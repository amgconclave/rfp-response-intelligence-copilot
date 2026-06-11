from pathlib import Path


def test_decision_provenance_exposes_typed_graph_controls_and_eval_assertions(client, auth_headers):
    response = client.get("/proposal/decision-provenance", headers=auth_headers)

    assert response.status_code == 200
    provenance = response.json()
    assert provenance["title"] == "Proposal Decision Provenance Graph"
    assert provenance["status"] in {
        "ready_for_audit_review",
        "needs_human_review",
        "blocked_by_policy",
        "blocked_by_governance",
    }
    assert provenance["summary"]["node_count"] == len(provenance["nodes"])
    assert provenance["summary"]["edge_count"] == len(provenance["edges"])
    node_ids = {node["node_id"] for node in provenance["nodes"]}
    assert {node["node_type"] for node in provenance["nodes"]} >= {
        "workflow_stage",
        "agent_turn",
        "handoff",
        "governance_gate",
        "provider_policy",
        "eval_checkpoint",
    }
    assert all(edge["from_node_id"] in node_ids and edge["to_node_id"] in node_ids for edge in provenance["edges"])
    assert all(assertion["passed"] for assertion in provenance["eval_assertions"])
    assert any(control["control_id"] == "control-source-trust" for control in provenance["decision_controls"])
    assert any("/proposal/decision-provenance-pack" in command for command in provenance["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.decision_provenance_viewed" for event in audit["events"])


def test_decision_provenance_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post(
        "/proposal/decision-provenance-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "decision_provenance" in pack["artifact_path"]
    assert "Proposal Decision Provenance Pack" in pack["markdown"]
    assert "Provenance Nodes" in pack["markdown"]
    assert pack["pack"]["provenance"]["summary"]["node_count"] == len(pack["provenance"]["nodes"])

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/decision-provenance" in paths
    assert "/proposal/decision-provenance-pack" in paths
    assert "storage/decision_provenance/*.json" in paths["/proposal/decision-provenance-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Decision Provenance" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/decision-provenance", "/proposal/decision-provenance-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "decision_provenance" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/decision-provenance", "/proposal/decision-provenance-pack"} <= proposal_endpoints
    assert "/proposal/decision-provenance-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.decision_provenance_pack_generated" for event in audit["events"])
