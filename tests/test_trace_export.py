from pathlib import Path


def test_trace_export_returns_jsonl_ready_spans_and_governance(client, auth_headers):
    response = client.get("/ops/trace-export", headers=auth_headers)

    assert response.status_code == 200
    export = response.json()
    assert export["title"] == "Proposal Trace Export"
    assert export["status"] in {
        "ready_for_offline_analysis",
        "exported_with_review_items",
        "exported_with_blockers",
    }
    assert export["span_count"] >= 10
    assert len(export["exported_spans"]) == export["span_count"]
    assert all(span["span_id"] and span["trace_id"] for span in export["exported_spans"])
    assert all(span["attributes"]["local_export"] is True for span in export["exported_spans"])
    assert export["eval_dataset_manifest"]["dataset_path"] == "sample_data/eval_dataset.json"
    assert export["retrieval_diagnostics"]["diagnostic_count"] >= 0
    assert "experiment comparison" in export["governance_summary"]["radar_patterns_used"]
    assert any("/ops/trace-export-pack" in command for command in export["local_proof_commands"])

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "ops.trace_export_viewed" for event in audit["events"])


def test_trace_export_pack_writes_markdown_json_and_jsonl(client, auth_headers):
    response = client.post("/ops/trace-export-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert pack["jsonl_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    jsonl_path = Path(pack["jsonl_artifact_path"])
    assert jsonl_path.exists()
    assert "trace_exports" in pack["artifact_path"]
    assert "Proposal Trace Export Pack" in pack["markdown"]
    assert len(jsonl_path.read_text(encoding="utf-8").strip().splitlines()) == pack["trace_export"]["span_count"]

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/ops/trace-export" in paths
    assert "/ops/trace-export-pack" in paths
    assert "storage/trace_exports/*.jsonl" in paths["/ops/trace-export-pack"]["required_artifact_expectations"]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {"/ops/trace-export", "/ops/trace-export-pack"} <= endpoint_paths
    assert any(view["label"] == "Trace Export" for view in dashboard_smoke["expected_views"])

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "trace_exports" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    operations_paths = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["operations"]}
    assert {"/ops/trace-export", "/ops/trace-export-pack"} <= operations_paths
    assert "/ops/trace-export-pack" not in contract["generated_artifact_endpoint_coverage"]["missing_paths"]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "ops.trace_export_pack_generated" for event in audit["events"])
