from pathlib import Path


def test_git_readiness_returns_branch_hygiene_summary(client, auth_headers):
    response = client.get("/git/readiness", headers=auth_headers)

    assert response.status_code == 200
    readiness = response.json()
    assert readiness["title"] == "GitHub Push Readiness + Branch Hygiene"
    assert readiness["git_repo_detected"] is True
    assert readiness["current_branch"]
    assert readiness["working_tree_summary"]["tracked"] >= 1
    assert "source_files_changed" in readiness["changed_file_groups"]
    assert any(item["key"] == "git_packs" for item in readiness["generated_artifact_directories"])
    git_pack_dir = next(item for item in readiness["generated_artifact_directories"] if item["key"] == "git_packs")
    assert git_pack_dir["ignored"] is True
    assert readiness["github_actions"]["workflow_present"] is True
    assert readiness["readme_final_handoff"]["readme_present"] is True
    assert readiness["env_example_present"] is True
    assert readiness["dirty_worktree_guidance"]
    assert any("git status --porcelain" in command for command in readiness["local_review_commands"])
    assert any("GitHub" in limitation or "stage" in limitation for limitation in readiness["limitations"])


def test_git_push_plan_writes_markdown_and_json_under_ignored_git_packs(client, auth_headers):
    response = client.post("/git/push-plan", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    payload = response.json()
    artifact_path = Path(payload["artifact_path"])
    json_artifact_path = Path(payload["json_artifact_path"])
    assert artifact_path.exists()
    assert json_artifact_path.exists()
    assert "git_packs" in str(artifact_path)
    assert "GitHub Push Readiness + Branch Hygiene Pack" in payload["markdown"]
    assert "## Non-Destructive Review Commands" in payload["markdown"]
    assert "## Do Not Commit Generated Artifacts" in payload["markdown"]
    assert payload["pack"]["artifact_paths"]["git_push_plan_markdown"] == str(artifact_path.resolve())
    assert payload["pack"]["pre_push_verification_checklist"]
    assert "recruiter_github_readme_publish_blurb" in payload["pack"]
    assert payload["readiness"]["generated_artifact_directories"]


def test_smoke_dashboard_and_inventory_include_git_readiness(client, auth_headers):
    smoke_response = client.get("/ops/smoke-matrix", headers=auth_headers)
    dashboard_response = client.get("/ui/dashboard-smoke", headers=auth_headers)
    inventory_response = client.get("/artifacts/inventory", headers=auth_headers)

    assert smoke_response.status_code == 200
    assert dashboard_response.status_code == 200
    assert inventory_response.status_code == 200

    smoke_paths = {row["path"] for row in smoke_response.json()["rows"]}
    assert "/git/readiness" in smoke_paths
    assert "/git/push-plan" in smoke_paths
    assert any(
        "storage/git_packs" in expectation
        for row in smoke_response.json()["rows"]
        for expectation in row["required_artifact_expectations"]
    )

    dashboard = dashboard_response.json()
    assert dashboard["status"] == "pass"
    assert any(view["label"] == "Git Readiness" for view in dashboard["expected_views"])
    assert any(endpoint["path"] == "/git/readiness" for endpoint in dashboard["endpoint_references"])
    assert any(endpoint["path"] == "/git/push-plan" for endpoint in dashboard["endpoint_references"])
    assert any(tab["artifact_root"] == "storage/git_packs" for tab in dashboard["generated_artifact_tabs"])

    inventory_keys = {item["key"] for item in inventory_response.json()["directories"]}
    assert "git_packs" in inventory_keys
