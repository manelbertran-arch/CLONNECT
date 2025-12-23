# backend/tests/test_db_messages.py
# Tests that /dm/conversations reads message counts from PostgreSQL (not JSON)

import os
import pytest
from fastapi.testclient import TestClient
from api.main import app
import time

client = TestClient(app)

CREATOR_ID = "manel_db_test"

# Skip tests if no DATABASE_URL
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set - PostgreSQL tests skipped"
)


def test_conversations_reads_messages_from_db():
    """
    Test that /dm/conversations reads message counts from PostgreSQL:
    1. Create a lead
    2. Add messages via db_service.save_message()
    3. Verify /dm/conversations returns correct total_messages and last_messages
    """
    test_suffix = str(int(time.time()))

    # Step 1: Create a lead
    create_payload = {
        "name": f"DB Msg Test {test_suffix}",
        "platform": "instagram",
    }

    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json=create_payload)
    assert resp.status_code == 200, f"Create failed: {resp.text}"

    data = resp.json()
    lead = data.get("lead", data)
    lead_id = lead.get("id") or lead.get("follower_id")
    assert lead_id, f"No lead ID in response: {data}"

    print(f"\n=== CREATED LEAD: {lead_id} ===")

    # Step 2: Add messages directly to PostgreSQL
    from api.services import db_service

    # Save 3 user messages and 2 assistant messages
    messages_to_save = [
        ("user", "Hola, me interesa el producto"),
        ("assistant", "Hola! Claro, te cuento sobre el producto"),
        ("user", "Cual es el precio?"),
        ("assistant", "El precio es 99 EUR"),
        ("user", "Perfecto, lo quiero comprar"),
    ]

    import asyncio
    loop = asyncio.new_event_loop()

    for role, content in messages_to_save:
        result = loop.run_until_complete(
            db_service.save_message(lead_id, role, content, None)
        )
        print(f"Saved message: role={role}, result={result}")

    loop.close()

    # Step 3: Verify /dm/conversations returns correct counts
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200, f"Get conversations failed: {resp.text}"

    conv_data = resp.json()
    conversations = conv_data.get("conversations", [])

    # Find our lead
    our_lead = None
    for c in conversations:
        if c.get("id") == lead_id or c.get("follower_id") == lead_id:
            our_lead = c
            break

    assert our_lead is not None, f"Lead {lead_id} not found in conversations"

    print(f"\n=== CONVERSATIONS RESPONSE ===")
    print(f"total_messages: {our_lead.get('total_messages')}")
    print(f"last_messages: {our_lead.get('last_messages')}")

    # Verify message count (should be 3 user messages)
    assert our_lead.get("total_messages") == 3, \
        f"Expected 3 user messages, got {our_lead.get('total_messages')}"

    # Verify last_messages contains our messages from DB
    last_msgs = our_lead.get("last_messages", [])
    assert len(last_msgs) > 0, "last_messages should not be empty"

    # Check that messages have content from DB
    has_db_content = any(
        "producto" in msg.get("content", "").lower() or
        "precio" in msg.get("content", "").lower()
        for msg in last_msgs
    )
    assert has_db_content, \
        f"last_messages should contain DB content, got: {last_msgs}"

    print("\n=== TEST PASSED ===")
    print("PostgreSQL message integration verified:")
    print(f"- total_messages correctly reads from DB: {our_lead.get('total_messages')}")
    print(f"- last_messages correctly reads from DB: {len(last_msgs)} messages")
