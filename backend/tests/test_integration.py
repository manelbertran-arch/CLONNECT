"""Integration tests for frontend-backend compatibility"""
import pytest
import os

os.environ["DATABASE_URL"] = ""
os.environ["TESTING"] = "true"

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

class TestDashboardCompatibility:
    def test_overview_has_both_formats(self):
        response = client.get("/dashboard/manel/overview")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "bot_active" in data or "botActive" in data

class TestLeadsCompatibility:
    def test_leads_returns_list(self):
        response = client.get("/dm/leads/manel")
        assert response.status_code == 200
        data = response.json()
        assert "leads" in data
        assert isinstance(data["leads"], list)

class TestProductsCompatibility:
    def test_products_returns_list(self):
        response = client.get("/creator/manel/products")
        assert response.status_code == 200
        data = response.json()
        assert "products" in data

class TestResponseAdapter:
    def test_camel_case_conversion(self):
        from api.utils.response_adapter import to_camel_case, add_camel_case_aliases
        assert to_camel_case("bot_active") == "botActive"
        assert to_camel_case("total_leads") == "totalLeads"
        data = {"bot_active": True, "total_leads": 5}
        adapted = add_camel_case_aliases(data)
        assert "botActive" in adapted
        assert "totalLeads" in adapted
