# backend/tests/test_nurturing_runner.py
# Tests for POST /nurturing/{creator_id}/run endpoint

import os
import json
import time
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from api.main import app
from core.nurturing import get_nurturing_manager

client = TestClient(app)


def _get_creator_id():
    """Generate unique creator ID per test run"""
    return f"runner_{int(time.time() * 1000)}"


def _get_followups_path(creator_id: str) -> str:
    return f"data/nurturing/{creator_id}_followups.json"


def _cleanup(creator_id: str):
    """Remove test data and clear cache"""
    path = _get_followups_path(creator_id)
    if os.path.exists(path):
        os.remove(path)
    # Clear the cache
    manager = get_nurturing_manager()
    if creator_id in manager._cache:
        del manager._cache[creator_id]


def _create_test_followups(creator_id: str, count: int = 3, due: bool = True):
    """Create test followups directly in JSON file"""
    os.makedirs("data/nurturing", exist_ok=True)

    now = datetime.now()
    followups = []

    for i in range(count):
        if due:
            scheduled = now - timedelta(hours=i + 1)
        else:
            scheduled = now + timedelta(hours=i + 24)

        followups.append({
            "id": f"{creator_id}_follower_{i}_interest_cold_{i}_{int(time.time())}",
            "creator_id": creator_id,
            "follower_id": f"ig_test_user_{i}",
            "sequence_type": "interest_cold",
            "step": i,
            "scheduled_at": scheduled.isoformat(),
            "message_template": f"Test message {i} for {{product_name}}",
            "status": "pending",
            "created_at": now.isoformat(),
            "sent_at": None,
            "metadata": {"product_name": "Test Product"}
        })

    path = _get_followups_path(creator_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(followups, f, indent=2)

    # Clear cache to force reload
    manager = get_nurturing_manager()
    if creator_id in manager._cache:
        del manager._cache[creator_id]

    return followups


def test_run_endpoint_exists_in_openapi():
    """Verify /nurturing/{creator_id}/run exists in OpenAPI"""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert "/nurturing/{creator_id}/run" in paths, "Endpoint not found in OpenAPI"
    assert "post" in paths["/nurturing/{creator_id}/run"], "POST method not found"


def test_dry_run_returns_items_without_changing_stats():
    """dry_run=true should return items but NOT change stats"""
    creator_id = _get_creator_id()
    _cleanup(creator_id)

    # Create 3 due followups
    _create_test_followups(creator_id, count=3, due=True)

    # Get stats before
    resp_before = client.get(f"/nurturing/{creator_id}/stats")
    assert resp_before.status_code == 200
    stats_before = resp_before.json()
    pending_before = stats_before.get("pending", 0)
    sent_before = stats_before.get("sent", 0)

    assert pending_before == 3, f"Expected 3 pending, got {pending_before}"

    # Run with dry_run=true
    resp = client.post(f"/nurturing/{creator_id}/run?dry_run=true&force_due=true")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    assert data["dry_run"] is True
    assert data["would_process"] == 3
    assert len(data["items"]) == 3

    # Verify item structure
    item = data["items"][0]
    assert "followup_id" in item
    assert "follower_id" in item
    assert "sequence_type" in item
    assert "step" in item
    assert "scheduled_at" in item
    assert "message_preview" in item
    assert "channel_guess" in item
    assert item["channel_guess"] == "instagram"

    # Stats should NOT change
    resp_after = client.get(f"/nurturing/{creator_id}/stats")
    stats_after = resp_after.json()
    assert stats_after.get("pending", 0) == pending_before, "pending changed after dry_run!"
    assert stats_after.get("sent", 0) == sent_before, "sent changed after dry_run!"

    _cleanup(creator_id)


def test_run_with_force_due_marks_as_sent():
    """dry_run=false with force_due=true should process and update stats"""
    creator_id = _get_creator_id()
    _cleanup(creator_id)

    # Create 2 future followups (not due yet)
    _create_test_followups(creator_id, count=2, due=False)

    # Get stats before
    resp_before = client.get(f"/nurturing/{creator_id}/stats")
    stats_before = resp_before.json()
    pending_before = stats_before.get("pending", 0)
    sent_before = stats_before.get("sent", 0)

    assert pending_before == 2, f"Expected 2 pending, got {pending_before}"

    # Run with force_due=true and dry_run=false
    resp = client.post(f"/nurturing/{creator_id}/run?dry_run=false&force_due=true")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    assert data["dry_run"] is False
    assert data["processed"] == 2
    assert data["simulated"] == 2  # No real tokens
    assert data["sent"] == 0
    assert len(data["errors"]) == 0

    # Stats SHOULD change
    resp_after = client.get(f"/nurturing/{creator_id}/stats")
    stats_after = resp_after.json()

    assert stats_after.get("pending", 0) == 0, f"pending should be 0, got {stats_after.get('pending')}"
    assert stats_after.get("sent", 0) == sent_before + 2, f"sent should increase by 2"

    _cleanup(creator_id)


def test_due_only_filters_by_scheduled_at():
    """due_only=true should only process followups with scheduled_at <= now"""
    creator_id = _get_creator_id()
    _cleanup(creator_id)

    # Create 2 due followups
    _create_test_followups(creator_id, count=2, due=True)

    # Add 2 more that are NOT due
    path = _get_followups_path(creator_id)
    with open(path, 'r') as f:
        existing = json.load(f)

    now = datetime.now()
    for i in range(2):
        existing.append({
            "id": f"{creator_id}_future_{i}_{int(time.time())}",
            "creator_id": creator_id,
            "follower_id": f"tg_future_user_{i}",
            "sequence_type": "objection_price",
            "step": 0,
            "scheduled_at": (now + timedelta(hours=48)).isoformat(),
            "message_template": "Future message",
            "status": "pending",
            "created_at": now.isoformat(),
            "sent_at": None,
            "metadata": {}
        })

    with open(path, 'w') as f:
        json.dump(existing, f, indent=2)

    # Clear cache
    manager = get_nurturing_manager()
    if creator_id in manager._cache:
        del manager._cache[creator_id]

    # Run with due_only=true (default)
    resp = client.post(f"/nurturing/{creator_id}/run?dry_run=true&due_only=true")
    assert resp.status_code == 200

    data = resp.json()
    assert data["would_process"] == 2, f"Expected 2 due, got {data['would_process']}"

    _cleanup(creator_id)


def test_limit_parameter():
    """limit parameter should cap processed followups"""
    creator_id = _get_creator_id()
    _cleanup(creator_id)

    # Create 5 due followups
    _create_test_followups(creator_id, count=5, due=True)

    # Run with limit=2
    resp = client.post(f"/nurturing/{creator_id}/run?dry_run=true&force_due=true&limit=2")
    assert resp.status_code == 200

    data = resp.json()
    assert data["would_process"] == 2, f"Expected 2 (limited), got {data['would_process']}"

    _cleanup(creator_id)


def test_by_sequence_breakdown():
    """Response should include by_sequence breakdown"""
    creator_id = _get_creator_id()
    _cleanup(creator_id)

    # Create followups of different types
    os.makedirs("data/nurturing", exist_ok=True)
    now = datetime.now()
    past = now - timedelta(hours=1)

    followups = [
        {
            "id": f"{creator_id}_ic_0",
            "creator_id": creator_id,
            "follower_id": "ig_user_1",
            "sequence_type": "interest_cold",
            "step": 0,
            "scheduled_at": past.isoformat(),
            "message_template": "Interest cold msg",
            "status": "pending",
            "created_at": now.isoformat(),
            "sent_at": None,
            "metadata": {}
        },
        {
            "id": f"{creator_id}_op_0",
            "creator_id": creator_id,
            "follower_id": "tg_user_2",
            "sequence_type": "objection_price",
            "step": 0,
            "scheduled_at": past.isoformat(),
            "message_template": "Price objection msg",
            "status": "pending",
            "created_at": now.isoformat(),
            "sent_at": None,
            "metadata": {}
        }
    ]

    path = _get_followups_path(creator_id)
    with open(path, 'w') as f:
        json.dump(followups, f, indent=2)

    # Clear cache
    manager = get_nurturing_manager()
    if creator_id in manager._cache:
        del manager._cache[creator_id]

    # Run
    resp = client.post(f"/nurturing/{creator_id}/run?dry_run=false&force_due=true")
    assert resp.status_code == 200

    data = resp.json()
    assert "by_sequence" in data
    assert "interest_cold" in data["by_sequence"]
    assert "objection_price" in data["by_sequence"]
    assert data["by_sequence"]["interest_cold"]["simulated"] == 1
    assert data["by_sequence"]["objection_price"]["simulated"] == 1

    _cleanup(creator_id)
