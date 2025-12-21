"""Test configuration"""
import pytest
import os

os.environ["DATABASE_URL"] = ""
os.environ["TESTING"] = "true"

from fastapi.testclient import TestClient
from api.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def creator_id():
    return "manel"
