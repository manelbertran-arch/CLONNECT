# backend/tests/test_pipeline_scoring.py
# Tests for the pipeline scoring and auto-transition logic

from fastapi.testclient import TestClient
from api.main import app
import time

client = TestClient(app)

CREATOR_ID = "manel_pipeline_test"


def test_pipeline_score_new_lead():
    """New leads should have pipeline_score=25"""
    test_suffix = str(int(time.time()))

    # Create a new lead
    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json={
        "name": f"Pipeline Test New {test_suffix}",
        "platform": "instagram",
    })
    assert resp.status_code == 200

    # Fetch conversations
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200

    data = resp.json()
    conversations = data.get("conversations", [])

    # Find our lead
    our_lead = None
    for c in conversations:
        if f"Pipeline Test New {test_suffix}" in (c.get("name") or ""):
            our_lead = c
            break

    assert our_lead is not None, f"Lead not found"

    print(f"\n=== NEW LEAD ===")
    print(f"lead_status: {our_lead.get('lead_status')}")
    print(f"pipeline_score: {our_lead.get('pipeline_score')}")
    print(f"purchase_intent: {our_lead.get('purchase_intent')}")
    print(f"purchase_intent_score: {our_lead.get('purchase_intent_score')}")

    # Verify
    assert our_lead.get("lead_status") == "new", f"Expected status 'new', got {our_lead.get('lead_status')}"
    assert our_lead.get("pipeline_score") == 25, f"Expected pipeline_score=25, got {our_lead.get('pipeline_score')}"


def test_pipeline_score_active_lead():
    """Active leads should have pipeline_score=50"""
    test_suffix = str(int(time.time()))

    # Create a lead
    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json={
        "name": f"Pipeline Test Active {test_suffix}",
        "platform": "instagram",
    })
    assert resp.status_code == 200
    lead = resp.json().get("lead", resp.json())
    lead_id = lead.get("id") or lead.get("follower_id")

    # Update to active
    resp = client.put(f"/dm/follower/{CREATOR_ID}/{lead_id}/status", json={"status": "warm"})
    assert resp.status_code == 200

    # Fetch conversations
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200

    conversations = resp.json().get("conversations", [])
    our_lead = next((c for c in conversations if c.get("id") == lead_id or c.get("follower_id") == lead_id), None)

    print(f"\n=== ACTIVE LEAD ===")
    print(f"lead_status: {our_lead.get('lead_status')}")
    print(f"pipeline_score: {our_lead.get('pipeline_score')}")

    assert our_lead is not None
    assert our_lead.get("lead_status") == "active", f"Expected 'active', got {our_lead.get('lead_status')}"
    assert our_lead.get("pipeline_score") == 50, f"Expected 50, got {our_lead.get('pipeline_score')}"


def test_pipeline_score_hot_lead():
    """Hot leads should have pipeline_score=75"""
    test_suffix = str(int(time.time()))

    # Create a lead
    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json={
        "name": f"Pipeline Test Hot {test_suffix}",
        "platform": "instagram",
    })
    assert resp.status_code == 200
    lead = resp.json().get("lead", resp.json())
    lead_id = lead.get("id") or lead.get("follower_id")

    # Update to hot
    resp = client.put(f"/dm/follower/{CREATOR_ID}/{lead_id}/status", json={"status": "hot"})
    assert resp.status_code == 200

    # Fetch conversations
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200

    conversations = resp.json().get("conversations", [])
    our_lead = next((c for c in conversations if c.get("id") == lead_id or c.get("follower_id") == lead_id), None)

    print(f"\n=== HOT LEAD ===")
    print(f"lead_status: {our_lead.get('lead_status')}")
    print(f"pipeline_score: {our_lead.get('pipeline_score')}")

    assert our_lead is not None
    assert our_lead.get("lead_status") == "hot", f"Expected 'hot', got {our_lead.get('lead_status')}"
    assert our_lead.get("pipeline_score") == 75, f"Expected 75, got {our_lead.get('pipeline_score')}"


def test_pipeline_score_customer():
    """Customer leads should have pipeline_score=100"""
    test_suffix = str(int(time.time()))

    # Create a lead
    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json={
        "name": f"Pipeline Test Customer {test_suffix}",
        "platform": "instagram",
    })
    assert resp.status_code == 200
    lead = resp.json().get("lead", resp.json())
    lead_id = lead.get("id") or lead.get("follower_id")

    # Update to customer
    resp = client.put(f"/dm/follower/{CREATOR_ID}/{lead_id}/status", json={"status": "customer"})
    assert resp.status_code == 200

    # Fetch conversations
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200

    conversations = resp.json().get("conversations", [])
    our_lead = next((c for c in conversations if c.get("id") == lead_id or c.get("follower_id") == lead_id), None)

    print(f"\n=== CUSTOMER LEAD ===")
    print(f"lead_status: {our_lead.get('lead_status')}")
    print(f"pipeline_score: {our_lead.get('pipeline_score')}")

    assert our_lead is not None
    assert our_lead.get("lead_status") == "customer", f"Expected 'customer', got {our_lead.get('lead_status')}"
    assert our_lead.get("pipeline_score") == 100, f"Expected 100, got {our_lead.get('pipeline_score')}"


def test_purchase_intent_score_included():
    """Verify purchase_intent_score is included in response"""
    test_suffix = str(int(time.time()))

    # Create a lead
    resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json={
        "name": f"Intent Test {test_suffix}",
        "platform": "instagram",
    })
    assert resp.status_code == 200

    # Fetch conversations
    resp = client.get(f"/dm/conversations/{CREATOR_ID}")
    assert resp.status_code == 200

    conversations = resp.json().get("conversations", [])
    our_lead = next((c for c in conversations if f"Intent Test {test_suffix}" in (c.get("name") or "")), None)

    print(f"\n=== INTENT SCORES ===")
    print(f"purchase_intent: {our_lead.get('purchase_intent')}")
    print(f"purchase_intent_score: {our_lead.get('purchase_intent_score')}")

    assert our_lead is not None
    # purchase_intent_score should exist
    assert "purchase_intent_score" in our_lead, "purchase_intent_score field missing"
    # Should be an integer 0-100
    intent_score = our_lead.get("purchase_intent_score")
    assert isinstance(intent_score, (int, float)), f"Expected int/float, got {type(intent_score)}"
    assert 0 <= intent_score <= 100, f"Expected 0-100, got {intent_score}"


def test_pipeline_flow_summary():
    """Summary test showing the full pipeline flow"""
    test_suffix = str(int(time.time()))

    # Create leads for each status
    statuses = [
        ("cold", "new", 25),
        ("warm", "active", 50),
        ("hot", "hot", 75),
        ("customer", "customer", 100),
    ]

    print("\n" + "=" * 60)
    print("PIPELINE SCORING SUMMARY")
    print("=" * 60)
    print(f"{'API Status':<12} {'DB Status':<12} {'Pipeline Score':<15}")
    print("-" * 60)

    for api_status, expected_db_status, expected_score in statuses:
        # Create lead
        resp = client.post(f"/dm/leads/{CREATOR_ID}/manual", json={
            "name": f"Summary Test {api_status} {test_suffix}",
            "platform": "instagram",
        })
        lead = resp.json().get("lead", resp.json())
        lead_id = lead.get("id") or lead.get("follower_id")

        # Update status
        if api_status != "cold":  # new leads start as cold/new
            client.put(f"/dm/follower/{CREATOR_ID}/{lead_id}/status", json={"status": api_status})

        # Fetch
        resp = client.get(f"/dm/conversations/{CREATOR_ID}")
        conversations = resp.json().get("conversations", [])
        our_lead = next((c for c in conversations if c.get("id") == lead_id or c.get("follower_id") == lead_id), None)

        actual_status = our_lead.get("lead_status") if our_lead else "?"
        actual_score = our_lead.get("pipeline_score") if our_lead else "?"

        print(f"{api_status:<12} {actual_status:<12} {actual_score:<15}")

        # Verify
        if our_lead:
            assert actual_status == expected_db_status, f"Status mismatch for {api_status}"
            assert actual_score == expected_score, f"Score mismatch for {api_status}"

    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
