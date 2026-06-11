from pathlib import Path


def test_source_trust_gate_returns_retrieval_policies_and_reviewer_queue(client, auth_headers):
    response = client.get("/evidence/source-trust", headers=auth_headers)

    assert response.status_code == 200
    trust = response.json()
    assert trust["title"] == "Source Trust Gate"
    assert trust["status"] in {"pass", "needs_review", "blocked"}
    assert trust["summary"]["source_count"] >= 10
    assert trust["summary"]["approval_required_count"] >= 1
    assert trust["sources"]
    assert any(source["retrieval_policy"] in {"block", "suppress", "review_before_use"} for source in trust["sources"])
    assert any(source["trust_decision"] == "blocked_until_owner_review" for source in trust["sources"])
    assert trust["reviewer_queue"]
    assert trust["retrieval_policy_updates"]
    assert any("/evidence/source-trust-pack" in command for command in trust["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "evidence.source_trust_viewed" for event in audit["events"])


def test_source_trust_pack_writes_artifacts_and_dashboard_smoke_tracks_it(client, auth_headers):
    response = client.post("/evidence/source-trust-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "source_trust" in pack["artifact_path"]
    assert "Source Trust Gate Pack" in pack["markdown"]
    assert pack["source_trust"]["summary"]["source_count"] >= 10
    assert pack["pack"]["retrieval_policy_updates"]

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert smoke["status"] == "pass"
    assert any(view["label"] == "Source Trust Gate" for view in smoke["expected_views"])
    assert any(endpoint["path"] == "/evidence/source-trust-pack" for endpoint in smoke["endpoint_references"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "evidence.source_trust_pack_generated" for event in audit["events"])
