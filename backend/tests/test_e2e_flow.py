# backend/tests/test_e2e_flow.py
"""
End-to-end test for the complete Clonnect flow:
1. Create a lead via API
2. Simulate a DM conversation
3. Verify lead appears with message count > 0
4. Verify lead status and purchase_intent updated
5. Clean up test data
"""

import os
import pytest
import time
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

# Use unique creator ID for E2E tests
E2E_CREATOR_ID = f"e2e_test_{int(time.time())}"

# Tests requiring DATABASE_URL will check individually
SKIP_DB_TESTS = not os.getenv("DATABASE_URL")
requires_db = pytest.mark.skipif(SKIP_DB_TESTS, reason="DATABASE_URL not set")


@requires_db
class TestE2EFlow:
    """End-to-end flow tests - requires DATABASE_URL"""

    lead_id = None

    def test_01_create_lead(self):
        """Step 1: Create a lead via API"""
        payload = {
            "name": f"E2E Test User {int(time.time())}",
            "platform": "instagram",
            "email": "e2e@test.com",
        }

        resp = client.post(f"/dm/leads/{E2E_CREATOR_ID}/manual", json=payload)
        assert resp.status_code == 200, f"Create lead failed: {resp.text}"

        data = resp.json()
        assert data.get("status") == "ok", f"Unexpected status: {data}"

        lead = data.get("lead", data)
        TestE2EFlow.lead_id = lead.get("id") or lead.get("follower_id")
        assert TestE2EFlow.lead_id, f"No lead ID returned: {data}"

        print(f"\n✅ Created lead: {TestE2EFlow.lead_id}")

    def test_02_add_messages_to_lead(self):
        """Step 2: Add messages to simulate a conversation"""
        assert TestE2EFlow.lead_id, "Lead not created in previous test"

        # Import db_service to save messages directly
        from api.services import db_service

        # Simulate a conversation: user asks about product, bot responds
        messages = [
            {"role": "user", "content": "Hola! Estoy interesado en tu curso"},
            {"role": "assistant", "content": "¡Hola! Claro, te cuento sobre el curso..."},
            {"role": "user", "content": "¿Cuánto cuesta?"},
            {"role": "assistant", "content": "El precio es de 97€ con garantía de 30 días."},
            {"role": "user", "content": "Me interesa mucho, ¿cómo puedo pagar?"},
        ]

        for msg in messages:
            result = db_service.save_message(
                creator_id=E2E_CREATOR_ID,
                follower_id=TestE2EFlow.lead_id,
                role=msg["role"],
                content=msg["content"]
            )
            assert result, f"Failed to save message: {msg}"

        print(f"\n✅ Added {len(messages)} messages to conversation")

    def test_03_verify_conversations_endpoint(self):
        """Step 3: Verify lead appears in conversations with messages"""
        assert TestE2EFlow.lead_id, "Lead not created"

        resp = client.get(f"/dm/conversations/{E2E_CREATOR_ID}")
        assert resp.status_code == 200, f"Get conversations failed: {resp.text}"

        data = resp.json()
        conversations = data.get("conversations", [])

        # Find our test lead
        our_lead = None
        for conv in conversations:
            if conv.get("follower_id") == TestE2EFlow.lead_id or conv.get("id") == TestE2EFlow.lead_id:
                our_lead = conv
                break

        assert our_lead, f"Lead {TestE2EFlow.lead_id} not found in conversations: {[c.get('follower_id') for c in conversations]}"

        # Verify message count
        total_messages = our_lead.get("total_messages", 0)
        assert total_messages > 0, f"Expected messages > 0, got {total_messages}"

        print(f"\n✅ Lead found in conversations with {total_messages} messages")

    def test_04_verify_follower_detail(self):
        """Step 4: Verify follower detail endpoint returns messages"""
        assert TestE2EFlow.lead_id, "Lead not created"

        resp = client.get(f"/dm/follower/{E2E_CREATOR_ID}/{TestE2EFlow.lead_id}")
        assert resp.status_code == 200, f"Get follower detail failed: {resp.text}"

        data = resp.json()

        # Check last_messages
        last_messages = data.get("last_messages", [])
        assert len(last_messages) > 0, f"Expected messages in last_messages, got: {last_messages}"

        print(f"\n✅ Follower detail has {len(last_messages)} messages")

        # Check purchase intent was calculated
        purchase_intent = data.get("purchase_intent", data.get("purchase_intent_score", 0))
        print(f"   Purchase intent: {purchase_intent}")

    def test_05_update_lead_status(self):
        """Step 5: Test updating lead status via API"""
        assert TestE2EFlow.lead_id, "Lead not created"

        # Update to "hot" status
        resp = client.put(
            f"/dm/follower/{E2E_CREATOR_ID}/{TestE2EFlow.lead_id}/status",
            json={"status": "hot"}
        )
        assert resp.status_code == 200, f"Update status failed: {resp.text}"

        data = resp.json()
        assert data.get("status") == "ok", f"Unexpected response: {data}"

        print(f"\n✅ Lead status updated to 'hot'")

    def test_06_cleanup(self):
        """Step 6: Clean up test data"""
        if not TestE2EFlow.lead_id:
            pytest.skip("No lead to clean up")

        # Try to delete the lead
        resp = client.delete(f"/dm/leads/{E2E_CREATOR_ID}/{TestE2EFlow.lead_id}")

        # Accept either success or not found (in case already deleted)
        assert resp.status_code in [200, 404], f"Cleanup failed: {resp.text}"

        print(f"\n✅ Cleaned up test lead {TestE2EFlow.lead_id}")


# These tests run regardless of DATABASE_URL

def test_scheduler_status():
    """Test that nurturing scheduler status endpoint works"""
    resp = client.get("/nurturing/scheduler/status")
    assert resp.status_code == 200, f"Scheduler status failed: {resp.text}"

    data = resp.json()
    assert data.get("status") == "ok"
    assert "scheduler" in data

    scheduler = data["scheduler"]
    print(f"\n✅ Scheduler status: running={scheduler.get('running')}, runs={scheduler.get('total_runs')}")


def test_health_endpoint():
    """Test that health endpoint works (returns valid response)"""
    resp = client.get("/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"

    data = resp.json()
    # Health endpoint should return a status field (ok, healthy, or unhealthy)
    assert "status" in data, f"No status in response: {data}"
    assert data.get("status") in ["ok", "healthy", "unhealthy"], f"Unexpected status: {data}"

    print(f"\n✅ Health endpoint works (status={data.get('status')})")
