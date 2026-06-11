from pathlib import Path


def test_access_policy_exposes_roles_permissions_trace_and_hitl(client, auth_headers):
    response = client.get("/governance/access-policy", headers=auth_headers)

    assert response.status_code == 200
    policy = response.json()
    assert policy["title"] == "Role-Based Access Policy Review"
    assert policy["status"] in {"pass", "needs_human_access_review", "needs_provider_access_review", "blocked"}
    assert policy["summary"]["role_count"] >= 7
    assert policy["summary"]["endpoint_policy_count"] >= 8
    assert policy["summary"]["approval_required_endpoint_count"] >= 4
    assert set(policy["summary"]["implemented_patterns"]) >= {
        "governance",
        "human-in-the-loop",
        "provider flexibility",
        "trace analysis",
    }
    assert {role["role"] for role in policy["roles"]} >= {
        "Sales Lead",
        "Presales Architect",
        "Compliance Reviewer",
        "Procurement Lead",
        "Platform Owner",
    }
    assert any(row["path"] == "/ops/provider-resilience" for row in policy["endpoint_permissions"])
    assert any(row["artifact_root"] == "storage/access_policy" for row in policy["artifact_permissions"])
    assert policy["trace_spans"]
    assert all(assertion["passed"] for assertion in policy["eval_assertions"])
    assert any("/governance/access-policy-pack" in command for command in policy["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "governance.access_policy_viewed" for event in audit["events"])


def test_access_policy_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post("/governance/access-policy-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "access_policy" in pack["artifact_path"]
    assert "Role-Based Access Policy Pack" in pack["markdown"]
    assert pack["policy"]["summary"]["endpoint_policy_count"] >= 8

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/governance/access-policy" in paths
    assert "/governance/access-policy-pack" in paths
    assert "storage/access_policy/*.json" in paths["/governance/access-policy-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Access Policy" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/governance/access-policy", "/governance/access-policy-pack"} <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "access_policy" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    governance_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["governance"]}
    assert {"/governance/access-policy", "/governance/access-policy-pack"} <= governance_endpoints
    assert "/governance/access-policy-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "governance.access_policy_pack_generated" for event in audit["events"])
