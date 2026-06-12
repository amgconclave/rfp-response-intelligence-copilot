from pathlib import Path


def test_proposal_assurance_bundle_exposes_checksums_transitions_and_eval_assertions(client, auth_headers):
    response = client.get("/proposal/assurance-bundle", headers=auth_headers)

    assert response.status_code == 200
    assurance = response.json()
    assert assurance["title"] == "Proposal Assurance Bundle"
    assert assurance["status"] in {
        "ready_for_buyer_review",
        "ready_with_review_items",
        "blocked_by_assurance",
    }
    assert assurance["score"] >= 80
    assert assurance["injected_dependencies"]["external_provider_required"] is False
    assert assurance["control_summary"]["artifact_count"] >= 9
    assert {
        "typed contracts",
        "structured outputs",
        "dependency injection",
        "eval-friendly design",
        "checkpointing",
    } <= set(assurance["control_summary"]["radar_patterns_used"])
    assert {item["source_type"] for item in assurance["artifact_manifest"]} >= {
        "durable_workflow",
        "typed_contract",
        "role_crew",
        "decision_graph",
        "quality_benchmark",
        "provider_route",
    }
    assert all(len(item["checksum"]) == 64 for item in assurance["artifact_manifest"])
    assert len({item["checksum"] for item in assurance["artifact_manifest"]}) == len(
        assurance["artifact_manifest"]
    )
    assert len(assurance["state_transitions"]) == len(assurance["artifact_manifest"])
    assert all(transition["checkpoint_key"] for transition in assurance["state_transitions"])
    assert all(assertion["passed"] for assertion in assurance["eval_assertions"])
    assert any("/proposal/assurance-bundle-pack" in command for command in assurance["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.assurance_bundle_viewed" for event in audit["events"])


def test_proposal_assurance_bundle_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post("/proposal/assurance-bundle-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "proposal_assurance" in pack["artifact_path"]
    assert "Proposal Assurance Bundle Pack" in pack["markdown"]
    assert pack["assurance"]["control_summary"]["artifact_count"] >= 9

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/assurance-bundle" in paths
    assert "/proposal/assurance-bundle-pack" in paths
    assert "storage/proposal_assurance/*.json" in paths["/proposal/assurance-bundle-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/assurance-bundle", "/proposal/assurance-bundle-pack"} <= endpoint_paths
    assert any("/proposal/assurance-bundle" in view["endpoint_paths"] for view in dashboard_smoke["expected_views"])

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "proposal_assurance" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/assurance-bundle", "/proposal/assurance-bundle-pack"} <= proposal_endpoints
    assert "/proposal/assurance-bundle-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.assurance_bundle_pack_generated" for event in audit["events"])
