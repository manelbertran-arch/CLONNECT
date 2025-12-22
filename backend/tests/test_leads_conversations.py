# backend/tests/test_leads_conversations.py
# Tests the full flow: create lead -> update lead -> verify /dm/conversations returns email/phone/notes

from fastapi.testclient import TestClient
from api.main import app
import time

client = TestClient(app)

CREATOR_ID = "manel_conv_test"


def test_full_lead_flow_with_conversations():
    """
    Test the complete flow:
    1. Create a lead with email/phone/notes
    2. Verify /dm/conversations returns these fields
    3. Update the lead with new email/phone/notes
    4. Verify /dm/conversations returns the updated fields
    """
    # Unique identifier to avoid conflicts
    test_suffix = str(int(time.time()))

    # Step 1: Create a lead with email/phone/notes
    create_payload = {
        "name": f"Conv Test {test_suffix}",
        "platform": "instagram",
        "email": f"create_{test_suffix}@example.com",
        "phone": "+34111111111",
        "notes": f"Created notes {test_suffix}",
    }

    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json=create_payload)
    assert resp.status_code == 200, f"Create failed: {resp.text}"

    data = resp.json()
    lead = data.get("lead", data)
    lead_id = lead.get("id") or lead.get("follower_id")
    assert lead_id, f"No lead ID in response: {data}"

    print(f"\n=== CREATE RESPONSE ===")
    print(f"Lead ID: {lead_id}")
    print(f"Lead data: {lead}")

    # Verify create response has email/phone/notes
    assert lead.get("email") == create_payload["email"], \
        f"Create response email mismatch: {lead.get('email')} != {create_payload['email']}"
    assert lead.get("phone") == create_payload["phone"], \
        f"Create response phone mismatch: {lead.get('phone')} != {create_payload['phone']}"
    assert lead.get("notes") == create_payload["notes"], \
        f"Create response notes mismatch: {lead.get('notes')} != {create_payload['notes']}"

    # Step 2: Verify /dm/conversations returns these fields
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200, f"Get conversations failed: {resp.text}"

    conv_data = resp.json()
    conversations = conv_data.get("conversations", [])

    print(f"\n=== CONVERSATIONS AFTER CREATE ===")
    print(f"Total conversations: {len(conversations)}")

    # Find our lead in conversations
    our_lead = None
    for c in conversations:
        # Match by ID or follower_id
        if c.get("id") == lead_id or c.get("follower_id") == lead_id:
            our_lead = c
            break

    print(f"Our lead in conversations: {our_lead}")

    assert our_lead is not None, \
        f"Lead {lead_id} not found in conversations. Available: {[c.get('id') or c.get('follower_id') for c in conversations]}"

    # Verify email/phone/notes in conversations response
    assert our_lead.get("email") == create_payload["email"], \
        f"Conversations email after create: {our_lead.get('email')} != {create_payload['email']}"
    assert our_lead.get("phone") == create_payload["phone"], \
        f"Conversations phone after create: {our_lead.get('phone')} != {create_payload['phone']}"
    assert our_lead.get("notes") == create_payload["notes"], \
        f"Conversations notes after create: {our_lead.get('notes')} != {create_payload['notes']}"

    # Step 3: Update the lead with new email/phone/notes
    update_payload = {
        "name": f"Conv Test Updated {test_suffix}",
        "email": f"updated_{test_suffix}@example.com",
        "phone": "+34222222222",
        "notes": f"Updated notes {test_suffix}",
    }

    resp = client.put(f"/dm/leads/{CREATOR_ID}/{lead_id}", json=update_payload)
    assert resp.status_code == 200, f"Update failed: {resp.text}"

    update_data = resp.json()
    updated_lead = update_data.get("lead", update_data)

    print(f"\n=== UPDATE RESPONSE ===")
    print(f"Updated lead: {updated_lead}")

    # Verify update response has new email/phone/notes
    assert updated_lead.get("email") == update_payload["email"], \
        f"Update response email mismatch: {updated_lead.get('email')} != {update_payload['email']}"
    assert updated_lead.get("phone") == update_payload["phone"], \
        f"Update response phone mismatch: {updated_lead.get('phone')} != {update_payload['phone']}"
    assert updated_lead.get("notes") == update_payload["notes"], \
        f"Update response notes mismatch: {updated_lead.get('notes')} != {update_payload['notes']}"

    # Step 4: Verify /dm/conversations returns the UPDATED fields
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200, f"Get conversations after update failed: {resp.text}"

    conv_data = resp.json()
    conversations = conv_data.get("conversations", [])

    print(f"\n=== CONVERSATIONS AFTER UPDATE ===")
    print(f"Total conversations: {len(conversations)}")

    # Find our updated lead
    our_updated_lead = None
    for c in conversations:
        if c.get("id") == lead_id or c.get("follower_id") == lead_id:
            our_updated_lead = c
            break

    print(f"Our lead in conversations after update: {our_updated_lead}")

    assert our_updated_lead is not None, \
        f"Updated lead {lead_id} not found in conversations"

    # THIS IS THE CRITICAL CHECK - verify /dm/conversations has the UPDATED values
    assert our_updated_lead.get("email") == update_payload["email"], \
        f"FAIL: Conversations email after update: {our_updated_lead.get('email')} != {update_payload['email']}"
    assert our_updated_lead.get("phone") == update_payload["phone"], \
        f"FAIL: Conversations phone after update: {our_updated_lead.get('phone')} != {update_payload['phone']}"
    assert our_updated_lead.get("notes") == update_payload["notes"], \
        f"FAIL: Conversations notes after update: {our_updated_lead.get('notes')} != {update_payload['notes']}"

    print("\n=== ALL TESTS PASSED ===")
    print("The full flow works correctly:")
    print("1. Create lead with email/phone/notes ✓")
    print("2. /dm/conversations returns created values ✓")
    print("3. Update lead with new email/phone/notes ✓")
    print("4. /dm/conversations returns updated values ✓")
