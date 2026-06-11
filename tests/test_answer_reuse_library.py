from pathlib import Path

from tests.conftest import ingest_corpus


def test_answer_reuse_library_service_builds_governed_snippets(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/rfp/answer-reuse-library",
        headers=auth_headers,
        json={"customer_profile_id": "regulated_healthcare"},
    )

    assert response.status_code == 200
    library = response.json()
    assert library["title"] == "Answer Reuse Library"
    assert library["summary"]["snippet_count"] >= 4
    assert library["summary"]["approved_count"] >= 1
    assert library["status"] in {"ready", "needs_review"}
    assert library["endpoint_references"]
    assert any("/rfp/answer-reuse-library-pack" in command for command in library["local_proof_commands"])

    first = library["snippets"][0]
    assert first["owner"]
    assert first["expires_at"]
    assert first["reuse_decision"] in {"approved_for_reuse", "review_before_reuse", "blocked"}
    assert first["citation_lineage"]
    assert first["citation_lineage"][0]["source_found"]


def test_answer_reuse_library_pack_writes_artifacts(client, auth_headers):
    ingest_corpus(client, auth_headers)

    response = client.post(
        "/rfp/answer-reuse-library-pack",
        headers=auth_headers,
        json={"category": "security", "write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "answer_reuse_library" in pack["artifact_path"]
    assert "Answer Reuse Library Pack" in pack["markdown"]
    assert "Citation Lineage" in pack["markdown"]
    assert pack["pack"]["governance_controls"]
    assert pack["library"]["summary"]["snippet_count"] >= 3


def test_answer_reuse_library_dashboard_contract_and_inventory_wiring(client, auth_headers):
    pack_response = client.post(
        "/rfp/answer-reuse-library-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )
    assert pack_response.status_code == 200

    smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    answer_view = next(view for view in smoke["expected_views"] if view["label"] == "Answer Reuse Library")
    assert answer_view["status"] == "pass"
    assert answer_view["artifact_root"] == "answer_reuse_library"
    endpoint_paths = {endpoint["path"]: endpoint for endpoint in smoke["endpoint_references"]}
    assert endpoint_paths["/rfp/answer-reuse-library"]["status"] == "pass"
    assert endpoint_paths["/rfp/answer-reuse-library-pack"]["status"] == "pass"

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    directories = {item["key"]: item for item in inventory["directories"]}
    assert "answer_reuse_library" in directories
    assert directories["answer_reuse_library"]["producer_endpoint"] == "POST /rfp/answer-reuse-library-pack"

    launch = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    launch_paths = {row["path"]: row for row in launch["rows"]}
    assert "storage/answer_reuse_library/*.md" in launch_paths["/rfp/answer-reuse-library-pack"][
        "required_artifact_expectations"
    ]

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    rfp_paths = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["rfp_workflow"]}
    assert {"/rfp/answer-reuse-library", "/rfp/answer-reuse-library-pack"} <= rfp_paths
    assert "/rfp/answer-reuse-library-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]
