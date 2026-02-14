#!/usr/bin/env python3
"""
Test script for Stripe webhook E2E flow (SPEC-011).

Simulates a Stripe checkout.session.completed webhook locally
to verify the full payment flow:
  1. Webhook receives event
  2. Purchase recorded (JSON + SalesTracker)
  3. Follower memory updated (is_customer=true)
  4. Lead status updated to 'cliente' in PostgreSQL
  5. Nurturing sequences cancelled

Usage:
    # Against local server (default):
    python scripts/test_stripe_webhook.py

    # Against production:
    python scripts/test_stripe_webhook.py --url https://www.clonnectapp.com

    # Dry run (just print the payload):
    python scripts/test_stripe_webhook.py --dry-run

NOTE: This does NOT call real Stripe APIs. It simulates the webhook
payload that Stripe would send after a successful checkout.
"""

import argparse
import json
import sys
import time
import requests


def build_stripe_checkout_payload(
    creator_id: str = "test_creator",
    follower_id: str = "test_follower_stripe",
    product_id: str = "prod_test_001",
    product_name: str = "Test Product",
    amount_cents: int = 4900,
    currency: str = "eur",
    customer_email: str = "test@example.com",
    customer_name: str = "Test User",
) -> dict:
    """Build a simulated Stripe checkout.session.completed payload."""
    return {
        "id": f"evt_test_{int(time.time())}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": f"cs_test_{int(time.time())}",
                "object": "checkout.session",
                "amount_total": amount_cents,
                "currency": currency,
                "status": "complete",
                "payment_status": "paid",
                "customer_details": {
                    "email": customer_email,
                    "name": customer_name,
                },
                "metadata": {
                    "creator_id": creator_id,
                    "follower_id": follower_id,
                    "product_id": product_id,
                    "product_name": product_name,
                },
            }
        },
    }


def send_webhook(url: str, payload: dict) -> dict:
    """Send webhook payload and return response."""
    resp = requests.post(
        url,
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    return {
        "status_code": resp.status_code,
        "body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
    }


def main():
    parser = argparse.ArgumentParser(description="Test Stripe webhook E2E flow")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of the API")
    parser.add_argument("--creator", default="test_creator", help="Creator ID to use")
    parser.add_argument("--follower", default="test_follower_stripe", help="Follower ID to use")
    parser.add_argument("--dry-run", action="store_true", help="Just print payload, don't send")
    args = parser.parse_args()

    webhook_url = f"{args.url.rstrip('/')}/webhook/stripe"
    payload = build_stripe_checkout_payload(
        creator_id=args.creator,
        follower_id=args.follower,
    )

    print("=" * 60)
    print("STRIPE WEBHOOK E2E TEST (SPEC-011)")
    print("=" * 60)
    print(f"\nTarget: {webhook_url}")
    print(f"Creator: {args.creator}")
    print(f"Follower: {args.follower}")
    print(f"\nPayload:\n{json.dumps(payload, indent=2)}")

    if args.dry_run:
        print("\n[DRY RUN] Payload printed above. No request sent.")
        return

    print(f"\nSending POST to {webhook_url}...")
    try:
        result = send_webhook(webhook_url, payload)
        print(f"\nResponse status: {result['status_code']}")
        print(f"Response body:   {json.dumps(result['body'], indent=2)}")

        if result["status_code"] == 200:
            print("\n[PASS] Webhook accepted successfully.")
            print("\nVerification checklist:")
            print("  [ ] Check logs for: 'Stripe purchase recorded'")
            print("  [ ] Check logs for: 'Follower ... marked as customer'")
            print("  [ ] Check logs for: 'Lead ... status updated to cliente'")
            print("  [ ] Check logs for: 'Cancelled nurturing for new customer'")
            print(f"  [ ] Check follower JSON: data/followers/{args.creator}/{args.follower}.json")
            print(f"  [ ] Check DB: SELECT status FROM leads WHERE follower_id = '{args.follower}'")
        else:
            print(f"\n[FAIL] Unexpected status code: {result['status_code']}")

    except requests.ConnectionError:
        print(f"\n[ERROR] Could not connect to {webhook_url}")
        print("        Is the server running? Try: uvicorn api.main:app")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
