"""
CLONNECT — Functional Audit against Production API
Tests every endpoint group for reachability after monolith decomposition.

Usage: python scripts/functional_audit.py
"""
import json
import time
import sys
import os
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

# ─── Config ──────────────────────────────────────────────────────────────
BASE = os.getenv("API_BASE", "https://www.clonnectapp.com")
ADMIN_KEY = os.getenv("ADMIN_KEY", "clonnect_admin_secret_2024")
CREATOR = os.getenv("TEST_CREATOR", "stefano_bonanno")
TIMEOUT = 15  # seconds
REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "1.2"))  # seconds between requests (rate limit safe)

# ─── Helpers ─────────────────────────────────────────────────────────────
_last_request_time = 0.0

def _req(method, path, headers=None, body=None, timeout=TIMEOUT):
    """Make HTTP request, return (status_code, body_dict_or_str, elapsed_ms)."""
    global _last_request_time
    # Rate limit: wait between requests to avoid server rate limiting
    elapsed_since_last = time.time() - _last_request_time
    if elapsed_since_last < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed_since_last)
    _last_request_time = time.time()

    url = f"{BASE}{path}"
    hdrs = headers or {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        hdrs.setdefault("Content-Type", "application/json")
    req = Request(url, data=data, headers=hdrs, method=method)
    t0 = time.time()
    try:
        resp = urlopen(req, timeout=timeout)
        raw = resp.read().decode("utf-8", errors="replace")
        elapsed = int((time.time() - t0) * 1000)
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw[:500]
        return resp.status, parsed, elapsed
    except HTTPError as e:
        elapsed = int((time.time() - t0) * 1000)
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return e.code, parsed, elapsed
    except URLError as e:
        elapsed = int((time.time() - t0) * 1000)
        return 0, f"URLError: {e.reason}", elapsed
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        return 0, f"Error: {e}", elapsed

def GET(path, **kw):
    return _req("GET", path, **kw)

def POST(path, **kw):
    return _req("POST", path, **kw)

def PUT(path, **kw):
    return _req("PUT", path, **kw)

def DELETE(path, **kw):
    return _req("DELETE", path, **kw)

def admin_headers():
    return {"X-API-Key": ADMIN_KEY}

# ─── Result tracking ────────────────────────────────────────────────────
results = {
    "audit_date": datetime.now(timezone.utc).isoformat(),
    "base_url": BASE,
    "test_creator": CREATOR,
    "groups": {},
    "summary": {},
    "e2e_flows": {},
}

def test_group(name, tests):
    """Run a group of endpoint tests. Each test: (method, path, expect_range, headers, body)."""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    group_results = []
    passed = 0
    failed = 0
    for t in tests:
        method = t[0]
        path = t[1]
        expect_min = t[2] if len(t) > 2 else 200
        expect_max = t[3] if len(t) > 3 else 499
        hdrs = t[4] if len(t) > 4 else None
        body = t[5] if len(t) > 5 else None

        status, resp_body, elapsed = _req(method, path, headers=hdrs, body=body)

        ok = expect_min <= status <= expect_max
        icon = "OK" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        # Truncate response for logging
        resp_str = str(resp_body)[:200] if resp_body else ""
        print(f"  [{icon}] {method:6s} {path:55s} -> {status} ({elapsed}ms)")
        if not ok:
            print(f"         Expected {expect_min}-{expect_max}, got {status}: {resp_str}")

        group_results.append({
            "method": method,
            "path": path,
            "status": status,
            "elapsed_ms": elapsed,
            "ok": ok,
            "expected_range": [expect_min, expect_max],
        })

    results["groups"][name] = {
        "passed": passed,
        "failed": failed,
        "total": len(tests),
        "tests": group_results,
    }
    print(f"  --- {name}: {passed}/{len(tests)} passed ---")
    return passed, failed


# ════════════════════════════════════════════════════════════════════════
# GROUP 1: PUBLIC ENDPOINTS (no auth)
# ════════════════════════════════════════════════════════════════════════
PUBLIC = [
    ("GET", "/health"),
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/"),
    ("GET", "/api"),
    ("GET", "/privacy"),
    ("GET", "/terms"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 2: ADMIN ENDPOINTS (require X-API-Key)
# ════════════════════════════════════════════════════════════════════════
ADMIN_AUTH_CHECK = [
    # Without key → expect 401/403
    ("GET", "/admin/stats", 401, 403, None),
    ("GET", "/admin/creators", 401, 403, None),
    ("GET", "/admin/feature-flags", 401, 403, None),
]

ADMIN = [
    ("GET", "/admin/stats", 200, 499, admin_headers()),
    ("GET", "/admin/creators", 200, 499, admin_headers()),
    ("GET", "/admin/feature-flags", 200, 499, admin_headers()),
    ("GET", "/admin/conversations", 200, 499, admin_headers()),
    ("GET", "/admin/pending-messages", 200, 499, admin_headers()),
    ("GET", "/admin/alerts", 200, 499, admin_headers()),
    ("GET", "/admin/demo-status", 200, 499, admin_headers()),
    ("GET", "/admin/rate-limiter-stats", 200, 499, admin_headers()),
    ("GET", f"/admin/oauth/status/{CREATOR}", 200, 499, admin_headers()),
    ("GET", f"/admin/debug-raw-messages/{CREATOR}/test_user", 200, 499, admin_headers()),
    ("GET", f"/admin/debug-instagram-api/{CREATOR}", 200, 499, admin_headers()),
    ("GET", f"/admin/full-diagnostic/{CREATOR}", 200, 499, admin_headers()),
    ("GET", f"/admin/ghost-stats/{CREATOR}", 200, 499, admin_headers()),
    ("GET", "/admin/lead-categories", 200, 499, admin_headers()),
    ("GET", f"/admin/ingestion/status/{CREATOR}", 200, 499, admin_headers()),
    ("GET", "/admin/backups", 200, 499, admin_headers()),
    ("GET", f"/admin/diagnose-duplicate-leads/{CREATOR}", 200, 499, admin_headers()),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 3: NURTURING SCHEDULER (admin auth)
# ════════════════════════════════════════════════════════════════════════
NURTURING_ADMIN = [
    ("GET", "/nurturing/scheduler/status", 200, 499, admin_headers()),
    ("GET", "/nurturing/reconciliation/status", 200, 499, admin_headers()),
    ("GET", "/nurturing/reconciliation/health", 200, 499, admin_headers()),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 4: CREATOR-FACING (read-only GETs with admin key as proxy)
# ════════════════════════════════════════════════════════════════════════
CREATOR_FACING = [
    # Dashboard
    ("GET", f"/dashboard/{CREATOR}/overview"),
    # Config
    ("GET", f"/creator/config/{CREATOR}", 200, 499, admin_headers()),
    # Products
    ("GET", f"/creator/{CREATOR}/products", 200, 499, admin_headers()),
    # Payments
    ("GET", f"/payments/{CREATOR}/revenue"),
    ("GET", f"/payments/{CREATOR}/purchases"),
    # Calendar
    ("GET", f"/calendar/{CREATOR}/bookings", 200, 499, admin_headers()),
    ("GET", f"/calendar/{CREATOR}/links", 200, 499, admin_headers()),
    ("GET", f"/calendar/{CREATOR}/stats", 200, 499, admin_headers()),
    # Knowledge
    ("GET", f"/creator/config/{CREATOR}/knowledge"),
    ("GET", f"/creator/config/{CREATOR}/knowledge/faqs"),
    ("GET", f"/creator/config/{CREATOR}/knowledge/about"),
    # Analytics
    ("GET", f"/analytics/{CREATOR}/sales"),
    # Intelligence
    ("GET", f"/intelligence/{CREATOR}/dashboard"),
    ("GET", f"/intelligence/{CREATOR}/predictions"),
    ("GET", f"/intelligence/{CREATOR}/recommendations"),
    # Leads
    ("GET", f"/dm/leads/{CREATOR}", 200, 499, admin_headers()),
    ("GET", f"/dm/leads/{CREATOR}/escalations", 200, 499, admin_headers()),
    # Nurturing
    ("GET", f"/nurturing/{CREATOR}/sequences", 200, 499, admin_headers()),
    ("GET", f"/nurturing/{CREATOR}/followups", 200, 499, admin_headers()),
    ("GET", f"/nurturing/{CREATOR}/stats", 200, 499, admin_headers()),
    # Copilot
    ("GET", f"/copilot/{CREATOR}/status", 200, 499, admin_headers()),
    ("GET", f"/copilot/{CREATOR}/pending", 200, 499, admin_headers()),
    ("GET", f"/copilot/{CREATOR}/stats", 200, 499, admin_headers()),
    ("GET", f"/copilot/{CREATOR}/notifications", 200, 499, admin_headers()),
    ("GET", f"/copilot/{CREATOR}/history", 200, 499, admin_headers()),
    # Tone
    ("GET", f"/tone/{CREATOR}"),
    ("GET", "/tone/profiles"),
    # Clone Score
    ("GET", f"/clone-score/{CREATOR}"),
    ("GET", f"/clone-score/{CREATOR}/history"),
    # Audience
    ("GET", f"/audience/{CREATOR}/segments"),
    ("GET", f"/audience/{CREATOR}/aggregated"),
    # Insights
    ("GET", f"/insights/{CREATOR}/today"),
    ("GET", f"/insights/{CREATOR}/weekly"),
    ("GET", f"/insights/{CREATOR}/metrics"),
    # Audiencia
    ("GET", f"/audiencia/{CREATOR}/topics"),
    ("GET", f"/audiencia/{CREATOR}/passions"),
    ("GET", f"/audiencia/{CREATOR}/perception"),
    # Unified Leads
    ("GET", f"/leads/{CREATOR}/unified"),
    # Events
    ("GET", f"/events/{CREATOR}"),
    # Bot
    ("GET", f"/bot/{CREATOR}/status"),
    # Memory
    ("GET", f"/memory/{CREATOR}/test_lead"),
    # Autolearning
    ("GET", f"/autolearning/{CREATOR}/rules"),
    ("GET", f"/autolearning/{CREATOR}/dashboard"),
    ("GET", f"/autolearning/{CREATOR}/stats"),
    ("GET", f"/autolearning/{CREATOR}/gold-examples"),
    # Metrics
    ("GET", f"/metrics/dashboard/{CREATOR}"),
    ("GET", f"/metrics/health/{CREATOR}"),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 5: CONNECTIONS & OAUTH
# ════════════════════════════════════════════════════════════════════════
CONNECTIONS_OAUTH = [
    ("GET", f"/connections/{CREATOR}"),
    ("GET", f"/oauth/status/{CREATOR}"),
    ("GET", "/oauth/debug"),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 6: ONBOARDING
# ════════════════════════════════════════════════════════════════════════
ONBOARDING = [
    ("GET", f"/onboarding/{CREATOR}/status"),
    ("GET", f"/onboarding/{CREATOR}/visual-status"),
    ("GET", f"/onboarding/progress/{CREATOR}"),
    ("GET", f"/verification/{CREATOR}"),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 7: INGESTION V2
# ════════════════════════════════════════════════════════════════════════
INGESTION = [
    ("GET", "/ingestion/v2/debug/scraper-test"),
    ("GET", f"/ingestion/v2/data-status/{CREATOR}"),
    ("GET", f"/ingestion/v2/instagram/{CREATOR}/status"),
    ("GET", f"/ingestion/v2/youtube/{CREATOR}/status"),
    ("GET", f"/ingestion/v2/verify/{CREATOR}"),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 8: CONTENT & CITATIONS
# ════════════════════════════════════════════════════════════════════════
CONTENT = [
    ("GET", "/content/debug"),
    ("GET", "/content/stats"),
    ("GET", f"/citations/{CREATOR}/stats"),
    ("GET", f"/citations/{CREATOR}/posts-preview"),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 9: DM & CONVERSATIONS
# ════════════════════════════════════════════════════════════════════════
DM = [
    ("GET", f"/dm/conversations/{CREATOR}", 200, 499, admin_headers()),
    ("GET", f"/dm/debug/{CREATOR}"),
    ("GET", f"/dm/metrics/{CREATOR}"),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 10: WEBHOOKS (just verify endpoint exists; 4xx OK)
# ════════════════════════════════════════════════════════════════════════
WEBHOOKS = [
    # Instagram webhook GET = verification challenge → will return 200 or 400
    ("GET", "/webhook/instagram", 200, 499),
    ("GET", "/instagram/webhook", 200, 499),
    # WhatsApp webhook GET = verification → 200 or 400
    ("GET", "/webhook/whatsapp", 200, 499),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 11: TELEGRAM
# ════════════════════════════════════════════════════════════════════════
TELEGRAM = [
    ("GET", "/telegram/status"),
    ("GET", "/telegram/bots"),
    ("GET", "/telegram/registered-bots"),
    ("GET", "/telegram/diagnose"),
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 12: BOOKING & PREVIEW & DEBUG & GDPR & MAINTENANCE
# ════════════════════════════════════════════════════════════════════════
MISC = [
    ("GET", f"/booking-links/{CREATOR}"),
    ("GET", f"/booking/availability/{CREATOR}"),
    ("GET", "/preview/status"),
    ("GET", "/debug/database"),
    ("GET", f"/debug/products/{CREATOR}"),
    ("GET", "/debug/full-diagnosis"),
    ("GET", f"/debug/agent-config/{CREATOR}"),
    ("GET", f"/debug/system-prompt/{CREATOR}"),
    ("GET", f"/gdpr/{CREATOR}/consent/test_follower"),
    ("GET", f"/maintenance/profile-picture-stats/{CREATOR}"),
    ("GET", f"/maintenance/leads-without-photo/{CREATOR}"),
    ("GET", f"/maintenance/dismissed-leads/{CREATOR}"),
    ("GET", "/maintenance/db-indexes"),
    ("GET", f"/maintenance/echo-status/{CREATOR}"),
    ("GET", f"/instagram/status/{CREATOR}"),
    ("GET", "/instagram/creators"),
    ("GET", f"/instagram/icebreakers/{CREATOR}"),
    ("GET", "/ai", 200, 499),  # May not exist
    ("POST", "/audio/transcribe", 400, 499),  # No file → 422 expected
]

# ════════════════════════════════════════════════════════════════════════
# GROUP 13: AUTH ENDPOINTS
# ════════════════════════════════════════════════════════════════════════
AUTH = [
    # Login with wrong creds → 401
    ("POST", "/auth/login", 400, 499, None, {"email": "test@test.com", "password": "wrong"}),
    # Register validation error → 422
    ("POST", "/auth/register", 400, 499, None, {"email": "", "password": ""}),
    # Keys (admin)
    ("GET", "/auth/keys", 200, 499, admin_headers()),
]


# ════════════════════════════════════════════════════════════════════════
# E2E FLOWS
# ════════════════════════════════════════════════════════════════════════
def e2e_flow_1_instagram_webhook():
    """Flow 1: Instagram webhook verification challenge."""
    print("\n  [E2E-1] Instagram Webhook Verification")
    s, b, ms = GET("/instagram/webhook?hub.mode=subscribe&hub.challenge=TEST123&hub.verify_token=clonnect_verify_2024")
    # Should echo the challenge back or return 403 if token mismatch
    ok = s in (200, 403)
    print(f"    Status: {s} ({ms}ms) - {'OK' if ok else 'FAIL'}")
    return {"name": "instagram_webhook_verification", "status": s, "ok": ok, "elapsed_ms": ms}

def e2e_flow_2_leads_crud():
    """Flow 2: Read leads for creator."""
    print("\n  [E2E-2] Leads Read Flow")
    s, b, ms = GET(f"/dm/leads/{CREATOR}", headers=admin_headers())
    ok = 200 <= s <= 299
    count = "?"
    if isinstance(b, dict):
        count = b.get("total", b.get("count", len(b.get("leads", []))))
    print(f"    GET leads: {s} ({ms}ms), count={count} - {'OK' if ok else 'FAIL'}")
    return {"name": "leads_read", "status": s, "ok": ok, "elapsed_ms": ms, "lead_count": count}

def e2e_flow_3_products():
    """Flow 3: Read products for creator."""
    print("\n  [E2E-3] Products Read Flow")
    s, b, ms = GET(f"/creator/{CREATOR}/products", headers=admin_headers())
    ok = 200 <= s <= 299
    count = "?"
    if isinstance(b, dict):
        count = len(b.get("products", []))
    elif isinstance(b, list):
        count = len(b)
    print(f"    GET products: {s} ({ms}ms), count={count} - {'OK' if ok else 'FAIL'}")
    return {"name": "products_read", "status": s, "ok": ok, "elapsed_ms": ms, "product_count": count}

def e2e_flow_4_copilot():
    """Flow 4: Copilot status + pending."""
    print("\n  [E2E-4] Copilot Status Flow")
    s1, b1, ms1 = GET(f"/copilot/{CREATOR}/status", headers=admin_headers())
    s2, b2, ms2 = GET(f"/copilot/{CREATOR}/pending", headers=admin_headers())
    ok = (200 <= s1 <= 299) and (200 <= s2 <= 299)
    print(f"    Status: {s1} ({ms1}ms), Pending: {s2} ({ms2}ms) - {'OK' if ok else 'FAIL'}")
    return {"name": "copilot_flow", "status_code": s1, "pending_code": s2, "ok": ok, "elapsed_ms": ms1 + ms2}

def e2e_flow_5_oauth_status():
    """Flow 5: OAuth connection status for creator."""
    print("\n  [E2E-5] OAuth & Connections Status")
    s1, b1, ms1 = GET(f"/connections/{CREATOR}")
    s2, b2, ms2 = GET(f"/oauth/status/{CREATOR}")
    ok = (200 <= s1 <= 499) and (200 <= s2 <= 499)
    print(f"    Connections: {s1} ({ms1}ms), OAuth: {s2} ({ms2}ms) - {'OK' if ok else 'FAIL'}")
    return {"name": "oauth_connections", "connections_code": s1, "oauth_code": s2, "ok": ok, "elapsed_ms": ms1 + ms2}


# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════
def main():
    print(f"\n{'#'*60}")
    print(f"  CLONNECT FUNCTIONAL AUDIT")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print(f"  Base: {BASE}")
    print(f"  Creator: {CREATOR}")
    print(f"{'#'*60}")

    total_passed = 0
    total_failed = 0

    groups = [
        ("1. Public Endpoints", PUBLIC),
        ("2. Admin Auth Denied (no key)", ADMIN_AUTH_CHECK),
        ("3. Admin Endpoints", ADMIN),
        ("4. Nurturing Scheduler (admin)", NURTURING_ADMIN),
        ("5. Creator-Facing Endpoints", CREATOR_FACING),
        ("6. Connections & OAuth", CONNECTIONS_OAUTH),
        ("7. Onboarding", ONBOARDING),
        ("8. Ingestion V2", INGESTION),
        ("9. Content & Citations", CONTENT),
        ("10. DM & Conversations", DM),
        ("11. Webhooks (existence)", WEBHOOKS),
        ("12. Telegram", TELEGRAM),
        ("13. Misc (Booking, Preview, Debug, GDPR, Maintenance)", MISC),
        ("14. Auth Endpoints", AUTH),
    ]

    for name, tests in groups:
        p, f = test_group(name, tests)
        total_passed += p
        total_failed += f

    # E2E Flows
    print(f"\n{'='*60}")
    print(f"  END-TO-END FLOWS")
    print(f"{'='*60}")
    e2e_results = []
    for flow_fn in [e2e_flow_1_instagram_webhook, e2e_flow_2_leads_crud,
                     e2e_flow_3_products, e2e_flow_4_copilot, e2e_flow_5_oauth_status]:
        try:
            r = flow_fn()
            e2e_results.append(r)
        except Exception as e:
            print(f"    FLOW ERROR: {e}")
            e2e_results.append({"name": flow_fn.__name__, "ok": False, "error": str(e)})

    e2e_passed = sum(1 for r in e2e_results if r.get("ok"))
    e2e_total = len(e2e_results)
    results["e2e_flows"] = {"results": e2e_results, "passed": e2e_passed, "total": e2e_total}

    # Summary
    results["summary"] = {
        "endpoint_tests_passed": total_passed,
        "endpoint_tests_failed": total_failed,
        "endpoint_tests_total": total_passed + total_failed,
        "e2e_passed": e2e_passed,
        "e2e_total": e2e_total,
        "overall_pass_rate": f"{(total_passed + e2e_passed) / (total_passed + total_failed + e2e_total) * 100:.1f}%",
    }

    print(f"\n{'#'*60}")
    print(f"  AUDIT SUMMARY")
    print(f"{'#'*60}")
    print(f"  Endpoint tests: {total_passed}/{total_passed + total_failed} passed")
    print(f"  E2E flows:      {e2e_passed}/{e2e_total} passed")
    print(f"  Overall rate:   {results['summary']['overall_pass_rate']}")
    if total_failed > 0:
        print(f"\n  FAILURES:")
        for gname, gdata in results["groups"].items():
            for t in gdata["tests"]:
                if not t["ok"]:
                    print(f"    [{gname}] {t['method']} {t['path']} -> {t['status']}")
    print()

    # Save
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                            "FUNCTIONAL_AUDIT_RESULTS.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  Results saved to {out_path}")
    return 0 if total_failed == 0 and e2e_passed == e2e_total else 1

if __name__ == "__main__":
    sys.exit(main())
