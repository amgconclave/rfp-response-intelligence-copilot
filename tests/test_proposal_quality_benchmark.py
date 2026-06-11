from pathlib import Path


def test_proposal_quality_benchmark_exposes_scenarios_roles_and_eval_assertions(client, auth_headers):
    response = client.get("/proposal/quality-benchmark", headers=auth_headers)

    assert response.status_code == 200
    benchmark = response.json()
    assert benchmark["title"] == "Proposal Quality Benchmark"
    assert benchmark["status"] in {"pass", "pass_with_review_items", "fail"}
    assert benchmark["score"] >= 80
    assert benchmark["scenario_count"] >= 7
    assert benchmark["injected_dependencies"]["external_provider_required"] is False
    assert {scenario["category"] for scenario in benchmark["scenarios"]} >= {
        "typed_contracts",
        "checkpointing",
        "dependency_injection",
        "eval_friendly_design",
    }
    assert {row["owner_role"] for row in benchmark["role_scorecard"]} >= {
        "Platform Owner",
        "Proposal Manager",
        "AI Governance Reviewer",
    }
    assert all(transition["checkpoint_key"] for transition in benchmark["state_transitions"])
    assert all(assertion["passed"] for assertion in benchmark["eval_assertions"])
    assert any("/proposal/quality-benchmark-pack" in command for command in benchmark["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.quality_benchmark_viewed" for event in audit["events"])


def test_proposal_quality_benchmark_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post("/proposal/quality-benchmark-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "proposal_benchmarks" in pack["artifact_path"]
    assert "Proposal Quality Benchmark Pack" in pack["markdown"]
    assert pack["benchmark"]["score"] >= 80

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/quality-benchmark" in paths
    assert "/proposal/quality-benchmark-pack" in paths
    assert "storage/proposal_benchmarks/*.json" in paths["/proposal/quality-benchmark-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/proposal/quality-benchmark", "/proposal/quality-benchmark-pack"} <= endpoint_paths
    assert any(view["label"] == "Quality Benchmark" for view in dashboard_smoke["expected_views"])

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "proposal_benchmarks" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {"/proposal/quality-benchmark", "/proposal/quality-benchmark-pack"} <= proposal_endpoints
    assert "/proposal/quality-benchmark-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.quality_benchmark_pack_generated" for event in audit["events"])
