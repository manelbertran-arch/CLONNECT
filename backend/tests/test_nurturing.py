# backend/tests/test_nurturing.py
# Tests for the nurturing sequences API

from fastapi.testclient import TestClient
from api.main import app
import time
import os
import json

client = TestClient(app)

CREATOR_ID = "manel_nurturing_test"


def cleanup_test_data():
    """Clean up test data files"""
    config_path = f"data/nurturing/{CREATOR_ID}_sequences.json"
    followups_path = f"data/nurturing/{CREATOR_ID}_followups.json"
    for path in [config_path, followups_path]:
        if os.path.exists(path):
            os.remove(path)


def test_get_sequences_returns_all_default_sequences():
    """Test that GET /sequences returns all default nurturing sequences"""
    cleanup_test_data()

    resp = client.get(f"/nurturing/{CREATOR_ID}/sequences")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    assert "sequences" in data

    sequences = data["sequences"]
    print(f"\n=== GET SEQUENCES ===")
    print(f"Total sequences: {len(sequences)}")

    # Should have all 12 default sequences (8 original + 4 scarcity/urgency)
    expected_types = [
        "interest_cold", "objection_price", "objection_time",
        "objection_doubt", "objection_later", "abandoned",
        "re_engagement", "post_purchase",
        "discount_urgency", "spots_limited", "offer_expiring", "flash_sale"
    ]

    actual_types = [s["type"] for s in sequences]
    for expected in expected_types:
        assert expected in actual_types, f"Missing sequence type: {expected}"

    # Each sequence should have required fields
    for seq in sequences:
        print(f"  - {seq['type']}: is_active={seq.get('is_active')}, steps={len(seq.get('steps', []))}")
        assert "id" in seq
        assert "type" in seq
        assert "name" in seq
        assert "is_active" in seq
        assert "steps" in seq
        assert "enrolled_count" in seq
        assert "sent_count" in seq
        assert isinstance(seq["is_active"], bool)
        assert isinstance(seq["steps"], list)

    print("All default sequences present with correct structure")


def test_toggle_sequence():
    """Test toggling a sequence on/off"""
    cleanup_test_data()

    # Get initial state
    resp = client.get(f"/nurturing/{CREATOR_ID}/sequences")
    sequences = resp.json()["sequences"]
    seq = next(s for s in sequences if s["type"] == "interest_cold")
    initial_active = seq["is_active"]

    print(f"\n=== TOGGLE SEQUENCE ===")
    print(f"Initial is_active: {initial_active}")

    # Toggle
    resp = client.post(f"/nurturing/{CREATOR_ID}/sequences/interest_cold/toggle")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    assert data["is_active"] == (not initial_active)
    print(f"After toggle: is_active={data['is_active']}")

    # Verify persistence
    resp = client.get(f"/nurturing/{CREATOR_ID}/sequences")
    sequences = resp.json()["sequences"]
    seq = next(s for s in sequences if s["type"] == "interest_cold")
    assert seq["is_active"] == (not initial_active), "Toggle did not persist"
    print(f"Verified in GET: is_active={seq['is_active']}")

    # Toggle back
    resp = client.post(f"/nurturing/{CREATOR_ID}/sequences/interest_cold/toggle")
    assert resp.status_code == 200
    assert resp.json()["is_active"] == initial_active
    print(f"Toggled back: is_active={resp.json()['is_active']}")


def test_update_sequence_steps():
    """Test updating sequence steps"""
    cleanup_test_data()

    print(f"\n=== UPDATE SEQUENCE STEPS ===")

    # Get initial steps
    resp = client.get(f"/nurturing/{CREATOR_ID}/sequences")
    sequences = resp.json()["sequences"]
    seq = next(s for s in sequences if s["type"] == "abandoned")
    initial_steps = seq["steps"]
    print(f"Initial steps: {len(initial_steps)}")

    # Update with new steps
    new_steps = [
        {"delay_hours": 2, "message": "Hey! Saw you were interested. Any questions?"},
        {"delay_hours": 24, "message": "Just checking in - still interested?"},
        {"delay_hours": 72, "message": "Last chance - offer expires soon!"},
    ]

    resp = client.put(
        f"/nurturing/{CREATOR_ID}/sequences/abandoned",
        json={"steps": new_steps}
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["steps"]) == 3
    print(f"Updated to {len(data['steps'])} steps")

    # Verify persistence
    resp = client.get(f"/nurturing/{CREATOR_ID}/sequences")
    sequences = resp.json()["sequences"]
    seq = next(s for s in sequences if s["type"] == "abandoned")

    assert len(seq["steps"]) == 3
    assert seq["steps"][0]["delay_hours"] == 2
    assert seq["steps"][1]["delay_hours"] == 24
    assert seq["steps"][2]["delay_hours"] == 72
    print("Steps persisted correctly")


def test_get_stats():
    """Test getting nurturing stats"""
    cleanup_test_data()

    print(f"\n=== GET STATS ===")

    resp = client.get(f"/nurturing/{CREATOR_ID}/stats")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    assert "total" in data
    assert "pending" in data
    assert "sent" in data
    assert "cancelled" in data
    assert "active_sequences" in data
    assert "by_sequence" in data

    print(f"Stats: total={data['total']}, pending={data['pending']}, sent={data['sent']}")
    print(f"Active sequences: {data['active_sequences']}")

    # Active sequences should be 0 by default (all inactive - user must enable)
    assert data["active_sequences"] == 0, f"Expected 0 active, got {data['active_sequences']}"

    # Toggle one on and check again
    client.post(f"/nurturing/{CREATOR_ID}/sequences/interest_cold/toggle")
    resp = client.get(f"/nurturing/{CREATOR_ID}/stats")
    assert resp.json()["active_sequences"] == 1
    print("After toggling one on: active_sequences=1")


def test_get_enrolled_followers():
    """Test getting enrolled followers for a sequence"""
    cleanup_test_data()

    print(f"\n=== GET ENROLLED FOLLOWERS ===")

    resp = client.get(f"/nurturing/{CREATOR_ID}/sequences/interest_cold/enrolled")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    assert "enrolled" in data
    assert "count" in data
    assert isinstance(data["enrolled"], list)

    print(f"Enrolled count: {data['count']}")
    # Initially should be 0
    assert data["count"] == 0


def test_cancel_nurturing():
    """Test cancelling nurturing for a follower"""
    cleanup_test_data()

    print(f"\n=== CANCEL NURTURING ===")

    # Test the cancel endpoint (even with no followups, it should work)
    resp = client.delete(f"/nurturing/{CREATOR_ID}/cancel/test_follower_123")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    assert "cancelled" in data

    print(f"Cancelled: {data['cancelled']} followups")


def test_full_integration_flow():
    """Test the complete nurturing flow"""
    cleanup_test_data()

    print(f"\n" + "=" * 60)
    print("NURTURING INTEGRATION TEST")
    print("=" * 60)

    # 1. Get all sequences
    resp = client.get(f"/nurturing/{CREATOR_ID}/sequences")
    assert resp.status_code == 200
    sequences = resp.json()["sequences"]
    print(f"\n1. Retrieved {len(sequences)} sequences")

    # 2. Toggle a sequence ON (default is inactive/False)
    resp = client.post(f"/nurturing/{CREATOR_ID}/sequences/post_purchase/toggle")
    assert resp.status_code == 200
    assert resp.json()["is_active"] == True
    print("2. Toggled post_purchase ON")

    # 2b. Toggle it OFF again
    resp = client.post(f"/nurturing/{CREATOR_ID}/sequences/post_purchase/toggle")
    assert resp.status_code == 200
    assert resp.json()["is_active"] == False
    print("2b. Toggled post_purchase OFF")

    # 3. Update sequence steps
    resp = client.put(
        f"/nurturing/{CREATOR_ID}/sequences/re_engagement",
        json={"steps": [
            {"delay_hours": 48, "message": "We miss you! Come back for a special offer."},
            {"delay_hours": 168, "message": "Last chance to reconnect - 20% off just for you!"},
        ]}
    )
    assert resp.status_code == 200
    print("3. Updated re_engagement with 2 custom steps")

    # 4. Get stats
    resp = client.get(f"/nurturing/{CREATOR_ID}/stats")
    assert resp.status_code == 200
    stats = resp.json()
    print(f"4. Stats: {stats['active_sequences']} active sequences")

    # 5. Verify changes persisted
    resp = client.get(f"/nurturing/{CREATOR_ID}/sequences")
    sequences = resp.json()["sequences"]

    post_purchase = next(s for s in sequences if s["type"] == "post_purchase")
    assert post_purchase["is_active"] == False
    print("5. Verified post_purchase is_active=False")

    re_engagement = next(s for s in sequences if s["type"] == "re_engagement")
    assert len(re_engagement["steps"]) == 2
    assert re_engagement["steps"][0]["delay_hours"] == 48
    print("6. Verified re_engagement has custom steps")

    print("\n" + "=" * 60)
    print("ALL INTEGRATION TESTS PASSED")
    print("=" * 60)

    cleanup_test_data()


if __name__ == "__main__":
    test_get_sequences_returns_all_default_sequences()
    test_toggle_sequence()
    test_update_sequence_steps()
    test_get_stats()
    test_get_enrolled_followers()
    test_cancel_nurturing()
    test_full_integration_flow()
