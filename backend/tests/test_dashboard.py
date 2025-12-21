"""Dashboard endpoint tests"""

def test_dashboard_overview(client, creator_id):
    response = client.get(f"/dashboard/{creator_id}/overview")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_dashboard_overview_invalid_creator(client):
    response = client.get("/dashboard/nonexistent_12345/overview")
    assert response.status_code in [200, 404]
