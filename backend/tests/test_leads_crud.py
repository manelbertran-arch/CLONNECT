# backend/tests/test_leads_crud.py

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

CREATOR_ID = "manel_test_crud"


def test_create_lead_full_data():
    payload = {
        "name": "Lead Test",
        "platform": "instagram",
        "email": "leadtest@example.com",
        "phone": "+34123456789",
        "notes": "Notas de prueba CRUD",
    }

    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json=payload)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    # Ajusta a la forma REAL de tu respuesta. Ejemplos:
    #  - {"status": "ok", "lead": {...}}
    #  - o directamente el lead {...}

    lead = data.get("lead", data)
    assert lead["full_name"] == "Lead Test"
    # email/phone/notes are returned as top-level fields
    assert lead["email"] == payload["email"]
    assert lead["phone"] == payload["phone"]
    assert lead["notes"] == payload["notes"]

    # Guarda el id para el siguiente test (id for PostgreSQL, follower_id for JSON fallback)
    global CREATED_LEAD_ID
    CREATED_LEAD_ID = lead.get("id") or lead.get("follower_id")


def test_update_lead_full_data():
    # usa el id del test anterior
    global CREATED_LEAD_ID

    update_payload = {
        "name": "Lead Test Updated",
        "email": "leadtestupdated@example.com",
        "phone": "+34987654321",
        "notes": "Notas actualizadas",
    }

    resp = client.put(
        f"/dm/leads/{CREATOR_ID}/{CREATED_LEAD_ID}",
        json=update_payload,
    )
    assert resp.status_code == 200, resp.text

    data = resp.json()
    lead = data.get("lead", data)

    assert lead["full_name"] == "Lead Test Updated"
    # email/phone/notes are returned as top-level fields
    assert lead["email"] == update_payload["email"]
    assert lead["phone"] == update_payload["phone"]
    assert lead["notes"] == update_payload["notes"]


def test_get_leads_includes_new_lead():
    import os
    # Skip this test if no DATABASE_URL (JSON fallback doesn't support listing)
    if not os.getenv("DATABASE_URL"):
        import pytest
        pytest.skip("Listing leads requires PostgreSQL (DATABASE_URL)")

    resp = client.get(f"/dm/leads/{CREATOR_ID}")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    # Ajusta a la forma de tu respuesta: puede ser lista directa o {"leads": [...]}
    leads = data.get("leads", data)

    full_names = [l.get("full_name") or l.get("name") for l in leads]
    assert "Lead Test Updated" in full_names
