from pathlib import Path

from tests.conftest import ingest_corpus


def test_governed_retrieval_endpoint_applies_source_trust_policy(client, auth_headers):
    ingest_corpus(client, auth_headers)
    payload = {
        "question": "What disaster recovery, uptime, SSO, encryption, and audit controls are supported?",
        "top_k": 6,
        "include_suppressed": True,
    }

    response = client.post("/evidence/governed-retrieval", headers=auth_headers, json=payload)

    assert response.status_code == 200
    governed = response.json()
    assert governed["title"] == "Governed Retrieval Preview"
    assert governed["status"] in {"pass", "needs_review", "blocked"}
    assert governed["summary"]["candidate_count"] >= 1
    assert governed["policy_trace"]
    assert {"retrieve_candidates", "join_source_trust", "apply_retrieval_policy"} <= {
        span["name"] for span in governed["policy_trace"]
    }
    assert any(item["retrieval_policy"] in {"block", "suppress", "review_before_use"} for item in governed["results"])
    assert governed["reviewer_queue"]
    assert all("citation" in item for item in governed["results"])


def test_governed_retrieval_pack_artifacts_and_smoke_wiring(client, auth_headers):
    pack_response = client.post(
        "/evidence/governed-retrieval-pack",
        headers=auth_headers,
        json={
            "question": "What disaster recovery, uptime, SSO, encryption, and audit controls are supported?",
            "top_k": 6,
            "write_artifact": True,
        },
    )

    assert pack_response.status_code == 200
    pack = pack_response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "governed_retrieval" in pack["artifact_path"]
    assert "Governed Retrieval Pack" in pack["markdown"]
    assert pack["governed_retrieval"]["summary"]["candidate_count"] >= 1
    assert pack["pack"]["policy_trace"]

    smoke_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    assert smoke_response.status_code == 200
    smoke = smoke_response.json()
    governed_view = next(view for view in smoke["expected_views"] if view["label"] == "Governed Retrieval")
    assert governed_view["status"] == "pass"
    assert governed_view["artifact_root"] == "governed_retrieval"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/evidence/governed-retrieval"]["status"] == "pass"
    assert endpoint_paths["/evidence/governed-retrieval-pack"]["status"] == "pass"

    launch_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    assert launch_response.status_code == 200
    launch = launch_response.json()
    paths = {row["path"]: row for row in launch["rows"]}
    assert "/evidence/governed-retrieval" in paths
    assert "storage/governed_retrieval/*.md" in paths["/evidence/governed-retrieval-pack"][
        "required_artifact_expectations"
    ]

    inventory_response = client.get("/artifacts/inventory", headers=auth_headers)
    assert inventory_response.status_code == 200
    inventory = inventory_response.json()
    directories = {Path(item["directory"]).name: item for item in inventory["directories"]}
    assert "governed_retrieval" in directories
    assert directories["governed_retrieval"]["producer_endpoint"] == "POST /evidence/governed-retrieval-pack"
