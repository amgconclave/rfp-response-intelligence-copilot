from pathlib import Path


def test_submission_certification_exposes_typed_gates_transitions_and_eval_assertions(client, auth_headers):
    response = client.get("/proposal/submission-certification", headers=auth_headers)

    assert response.status_code == 200
    certification = response.json()
    assert certification["title"] == "Proposal Submission Certification Gate"
    assert certification["status"] in {"certified", "certified_with_exceptions", "blocked"}
    assert certification["recommendation"]
    assert certification["readiness_score"] >= 0
    assert certification["injected_dependencies"]["external_provider_required"] is False
    assert certification["injected_dependencies"]["service"] == "ProposalSubmissionCertificationService"
    assert certification["source_artifacts"]["workflow_id"]
    assert certification["source_artifacts"]["contract_status"] == "pass"
    assert {gate["gate_id"] for gate in certification["gates"]} >= {
        "gate-structured-output-contracts",
        "gate-checkpoint-replay",
        "gate-human-approval-queue",
        "gate-provenance-integrity",
        "gate-provider-optionality",
    }
    assert [item["sequence"] for item in certification["transitions"]] == list(
        range(1, len(certification["transitions"]) + 1)
    )
    assert all(item["checkpoint_key"] for item in certification["transitions"])
    assert all(assertion["passed"] for assertion in certification["eval_assertions"])
    assert any(
        "/proposal/submission-certification-pack" in command
        for command in certification["local_proof_commands"]
    )

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.submission_certification_viewed" for event in audit["events"])


def test_submission_certification_pack_writes_artifacts_and_is_indexed(client, auth_headers):
    response = client.post(
        "/proposal/submission-certification-pack",
        headers=auth_headers,
        json={"write_artifact": True},
    )

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "submission_certifications" in pack["artifact_path"]
    assert "Proposal Submission Certification Pack" in pack["markdown"]
    assert pack["certification"]["source_artifacts"]["contract_status"] == "pass"

    smoke = client.get("/ops/smoke-matrix", headers=auth_headers).json()
    paths = {row["path"]: row for row in smoke["rows"]}
    assert "/proposal/submission-certification" in paths
    assert "/proposal/submission-certification-pack" in paths
    assert "storage/submission_certifications/*.json" in paths["/proposal/submission-certification-pack"][
        "required_artifact_expectations"
    ]

    dashboard_smoke = client.get("/ui/dashboard-smoke", headers=auth_headers).json()
    assert dashboard_smoke["status"] == "pass"
    assert any(view["label"] == "Submission Certification" for view in dashboard_smoke["expected_views"])
    endpoint_paths = {endpoint["path"] for endpoint in dashboard_smoke["endpoint_references"]}
    assert {
        "/proposal/submission-certification",
        "/proposal/submission-certification-pack",
    } <= endpoint_paths

    inventory = client.get("/artifacts/inventory", headers=auth_headers).json()
    assert "submission_certifications" in {item["key"] for item in inventory["directories"]}

    contract = client.get("/api/contract-audit", headers=auth_headers).json()
    proposal_endpoints = {endpoint["path"] for endpoint in contract["endpoint_inventory"]["proposal"]}
    assert {
        "/proposal/submission-certification",
        "/proposal/submission-certification-pack",
    } <= proposal_endpoints
    assert "/proposal/submission-certification-pack" not in contract["generated_artifact_endpoint_coverage"][
        "missing_paths"
    ]

    audit = client.get("/audit/events", headers=auth_headers).json()
    assert any(event["action"] == "proposal.submission_certification_pack_generated" for event in audit["events"])
