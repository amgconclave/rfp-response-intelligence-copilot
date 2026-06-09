from pathlib import Path

from app.core.config import get_settings
from app.services.runtime_demo import RuntimeDemoService


def test_runtime_demo_readiness_returns_local_commands(client, auth_headers):
    response = client.get("/runtime/demo-readiness", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Runtime Demo Server Readiness"
    assert payload["status"] in {"ready", "ready_ports_already_in_use", "needs_install_or_files"}
    assert payload["provider_mode"] == "mock"
    assert payload["storage_runtime_pack_dir"].endswith("runtime_packs")
    assert any("uvicorn app.main:app" in command for command in payload["local_run_commands"])
    assert any("streamlit run dashboard/app.py" in command for command in payload["local_run_commands"])
    assert any(command == "python scripts\\runtime_check.py" for command in payload["rag_eval_red_team_commands"])
    assert any(item["port"] == 8000 for item in payload["expected_ports"])
    assert any(item["port"] == 8501 for item in payload["expected_ports"])
    assert all(
        check["process_action"] == "No process was stopped or modified."
        for check in payload["process_port_checks"]
    )
    assert any(item["name"] == "PROVIDER_MODE" for item in payload["env_requirements"])
    assert any(check["package"] == "streamlit" and check["required"] for check in payload["dependency_checks"])
    assert any("OpenAI" in item for item in payload["known_limitations"])


def test_runtime_demo_pack_writes_markdown_and_json(client, auth_headers):
    response = client.post("/runtime/demo-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    payload = response.json()
    artifact_path = Path(payload["artifact_path"])
    json_artifact_path = Path(payload["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "runtime_packs" in str(artifact_path)
    assert "Runtime Demo Server Pack" in payload["markdown"]
    assert "## Exact Start Commands" in payload["markdown"]
    assert "## RAG/Eval/Red-Team Verification Order" in payload["markdown"]
    assert payload["pack"]["health_checks"]
    assert payload["pack"]["screenshot_checklist_placeholders"]
    assert payload["readiness"]["trace_id"].endswith("-readiness")


def test_runtime_demo_is_in_smoke_dashboard_and_inventory(client, auth_headers):
    client.post("/runtime/demo-pack", headers=auth_headers, json={"write_artifact": True})

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    smoke_paths = {row["path"] for row in smoke["rows"]}
    assert {"/runtime/demo-readiness", "/runtime/demo-pack"} <= smoke_paths
    assert any(
        "storage/runtime_packs" in expectation
        for row in smoke["rows"]
        for expectation in row["required_artifact_expectations"]
    )

    dashboard = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard["status"] == "pass"
    assert any(view["label"] == "Runtime Demo" for view in dashboard["expected_views"])
    assert any(endpoint["path"] == "/runtime/demo-pack" for endpoint in dashboard["endpoint_references"])

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    runtime_item = next(item for item in inventory["directories"] if item["key"] == "runtime_packs")
    assert runtime_item["file_count"] >= 2
    assert runtime_item["producer_endpoint"] == "POST /runtime/demo-pack"


def test_runtime_demo_service_script_payload_is_source_only():
    readiness = RuntimeDemoService(get_settings()).readiness("unit-runtime-check")

    assert readiness.trace_id == "unit-runtime-check"
    assert "python scripts\\runtime_check.py" in readiness.rag_eval_red_team_commands
    assert any(command.startswith("Press Ctrl+C") for command in readiness.stop_commands)
    assert all(check["check_type"] == "read_only_tcp_connect" for check in readiness.process_port_checks)
