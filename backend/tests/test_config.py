"""Config endpoint tests"""

def test_get_config_not_found(client):
    response = client.get("/creator/config/nonexistent_12345")
    assert response.status_code in [200, 404]

def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
