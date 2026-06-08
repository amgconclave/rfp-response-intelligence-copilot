def test_demo_token_and_health(client):
    token_response = client.post("/auth/demo-token")
    assert token_response.status_code == 200
    assert token_response.json()["api_key"] == "test-key"

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["provider_mode"] == "mock"


def test_api_key_required_for_protected_routes(client):
    response = client.get("/documents")
    assert response.status_code == 401
