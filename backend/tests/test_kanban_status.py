# backend/tests/test_kanban_status.py
# Tests the Kanban drag & drop status update flow

from fastapi.testclient import TestClient
from api.main import app
import time

client = TestClient(app)

CREATOR_ID = "manel_kanban_test"


def test_kanban_status_update_with_uuid():
    """
    Test the complete Kanban drag & drop flow:
    1. Create a lead (gets a UUID)
    2. Verify initial status in /dm/conversations
    3. Update status via PUT /dm/follower/{creator_id}/{uuid}/status
    4. Verify status persisted in /dm/conversations
    """
    test_suffix = str(int(time.time()))

    # Step 1: Create a lead
    create_payload = {
        "name": f"Kanban Test {test_suffix}",
        "platform": "instagram",
        "email": f"kanban_{test_suffix}@example.com",
    }

    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json=create_payload)
    assert resp.status_code == 200, f"Create failed: {resp.text}"

    data = resp.json()
    lead = data.get("lead", data)
    lead_id = lead.get("id") or lead.get("follower_id")
    assert lead_id, f"No lead ID in response: {data}"

    print(f"\n=== STEP 1: CREATE LEAD ===")
    print(f"Lead ID (UUID): {lead_id}")

    # Step 2: Verify initial status in /dm/conversations
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200, f"Get conversations failed: {resp.text}"

    conv_data = resp.json()
    conversations = conv_data.get("conversations", [])

    our_lead = None
    for c in conversations:
        if c.get("id") == lead_id or c.get("follower_id") == lead_id:
            our_lead = c
            break

    print(f"\n=== STEP 2: INITIAL STATUS ===")
    print(f"Lead in conversations: {our_lead}")

    assert our_lead is not None, f"Lead {lead_id} not found in conversations"
    initial_status = our_lead.get("lead_status", "new")
    print(f"Initial lead_status: {initial_status}")

    # Step 3: Update status to "hot" using UUID
    # This simulates drag & drop from "new" to "hot" column
    update_resp = client.put(
        f"/dm/follower/{CREATOR_ID}/{lead_id}/status",
        json={"status": "hot"}
    )
    assert update_resp.status_code == 200, f"Status update failed: {update_resp.text}"

    update_data = update_resp.json()
    print(f"\n=== STEP 3: STATUS UPDATE RESPONSE ===")
    print(f"Update response: {update_data}")

    assert update_data.get("new_status") == "hot", \
        f"Expected new_status=hot, got {update_data.get('new_status')}"

    # Step 4: Verify status persisted in /dm/conversations
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200, f"Get conversations after update failed: {resp.text}"

    conv_data = resp.json()
    conversations = conv_data.get("conversations", [])

    our_lead_after = None
    for c in conversations:
        if c.get("id") == lead_id or c.get("follower_id") == lead_id:
            our_lead_after = c
            break

    print(f"\n=== STEP 4: STATUS AFTER UPDATE ===")
    print(f"Lead in conversations after update: {our_lead_after}")

    assert our_lead_after is not None, f"Lead {lead_id} not found after update"

    # The key assertion: lead_status should now be "hot"
    new_status = our_lead_after.get("lead_status")
    print(f"New lead_status: {new_status}")

    assert new_status == "hot", \
        f"FAIL: lead_status should be 'hot' but got '{new_status}'"

    # Also verify purchase_intent was updated
    new_intent = our_lead_after.get("purchase_intent")
    assert new_intent == 0.7, \
        f"Expected purchase_intent=0.7 for 'hot' status, got {new_intent}"

    print("\n=== ALL TESTS PASSED ===")
    print("Kanban drag & drop status update works correctly:")
    print("1. Lead created with UUID ✓")
    print("2. Initial status retrieved from /dm/conversations ✓")
    print("3. Status updated via PUT /dm/follower/{uuid}/status ✓")
    print("4. Status persisted and visible in /dm/conversations ✓")


def test_status_update_with_platform_user_id():
    """
    Test that status update also works with platform_user_id (legacy support)
    """
    test_suffix = str(int(time.time()))

    # Create a lead
    create_payload = {
        "name": f"Legacy Test {test_suffix}",
        "platform": "telegram",
    }

    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json=create_payload)
    assert resp.status_code == 200

    data = resp.json()
    lead = data.get("lead", data)
    # Get the follower_id (platform_user_id) from the response
    follower_id = lead.get("follower_id") or lead.get("platform_user_id")
    assert follower_id, f"No follower_id in response: {data}"

    print(f"\n=== LEGACY TEST: Using follower_id ===")
    print(f"follower_id: {follower_id}")

    # Update status using follower_id instead of UUID
    update_resp = client.put(
        f"/dm/follower/{CREATOR_ID}/{follower_id}/status",
        json={"status": "warm"}
    )
    assert update_resp.status_code == 200, f"Status update failed: {update_resp.text}"

    print(f"Update response: {update_resp.json()}")
    print("Legacy platform_user_id lookup also works ✓")
