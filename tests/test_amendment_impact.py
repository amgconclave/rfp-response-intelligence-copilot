from pathlib import Path


def test_amendment_impact_default_sample_routes_changes(client, auth_headers):
    response = client.post("/rfp/amendment-impact", headers=auth_headers, json={})

    assert response.status_code == 200
    impact = response.json()
    assert impact["title"] == "RFP Amendment Impact Analysis"
    assert impact["status"] in {"blocked_pending_amendment_review", "review_required"}
    assert impact["summary"]["added_count"] >= 3
    assert impact["summary"]["changed_count"] >= 1
    assert impact["summary"]["blocking_change_count"] >= 1
    assert impact["readiness_impact"]["readiness_delta"] < 0
    assert impact["owner_review_queue"]
    assert impact["draft_update_plan"]
    assert impact["workflow"]["transitions"]
    assert any(route["target_state"] == "route_owner_review" for route in impact["workflow"]["conditional_routes"])
    assert any(change["reviewer_role"] == "legal_reviewer" for change in impact["requirement_changes"])
    assert any(change["reviewer_role"] == "security_reviewer" for change in impact["requirement_changes"])


def test_amendment_impact_pack_writes_artifacts(client, auth_headers):
    response = client.post("/rfp/amendment-impact-pack", headers=auth_headers, json={"write_artifact": True})

    assert response.status_code == 200
    pack = response.json()
    assert pack["artifact_path"]
    assert pack["json_artifact_path"]
    assert Path(pack["artifact_path"]).exists()
    assert Path(pack["json_artifact_path"]).exists()
    assert "RFP Amendment Impact Pack" in pack["markdown"]
    assert pack["pack"]["artifact_map"]["dashboard_tab"] == "Amendment Impact"
    assert pack["impact"]["summary"]["change_count"] == pack["pack"]["impact"]["summary"]["change_count"]


def test_amendment_impact_accepts_custom_text(client, auth_headers):
    baseline = """
    # RFP
    The response deadline is July 18, 2026.
    - The vendor must support SSO through SAML 2.0.
    - Pricing must describe implementation fees.
    """
    revised = """
    # RFP Addendum
    The revised response deadline is July 10, 2026.
    - The vendor must support SSO through SAML 2.0 and OIDC.
    - Pricing must describe implementation fees and a three-year total cost of ownership model.
    - The vendor must provide incident response notification commitments within 24 hours.
    """

    response = client.post(
        "/rfp/amendment-impact",
        headers=auth_headers,
        json={"baseline_text": baseline, "revised_text": revised, "amendment_label": "Custom Addendum"},
    )

    assert response.status_code == 200
    impact = response.json()
    assert impact["amendment_label"] == "Custom Addendum"
    assert impact["summary"]["deadline_changed"] is True
    assert impact["summary"]["added_count"] >= 1
    assert impact["summary"]["changed_count"] >= 1
    assert any(
        "incident response" in (change["revised_text"] or "").lower()
        for change in impact["requirement_changes"]
    )


def test_dashboard_smoke_includes_amendment_impact(client, auth_headers):
    response = client.get("/ui/dashboard-smoke", headers=auth_headers)

    assert response.status_code == 200
    smoke = response.json()
    view = next(item for item in smoke["expected_views"] if item["label"] == "Amendment Impact")
    assert view["status"] == "pass"
    assert "/rfp/amendment-impact" in view["endpoint_paths"]
    assert any(tab["artifact_root"] == "storage/amendment_impact" for tab in smoke["generated_artifact_tabs"])
