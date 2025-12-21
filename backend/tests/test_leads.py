"""Leads endpoint tests"""

def test_get_leads(client, creator_id):
    response = client.get(f"/dm/leads/{creator_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "leads" in data

def test_get_leads_empty(client):
    response = client.get("/dm/leads/nonexistent_12345")
    assert response.status_code == 200
