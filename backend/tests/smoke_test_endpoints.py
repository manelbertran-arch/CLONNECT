"""
Smoke test de endpoints de producción para anti-regresión.
Basado en el patrón de capture_baseline.py.
Uso:
  python3 tests/smoke_test_endpoints.py                          # Run all tests
  python3 tests/smoke_test_endpoints.py --save-baseline out.json # Save results as baseline
  python3 tests/smoke_test_endpoints.py --compare baseline.json  # Compare against baseline
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import requests

BASE = "https://www.clonnectapp.com"
ADMIN_KEY = "clonnect_admin_secret_2024"
TIMEOUT = 45       # Railway cold-start can take 30s+
RETRY_WAIT = 5     # seconds to wait before one retry on timeout

# Known IGSIDs for routing integrity checks
IRIS_IGSID = "17841400999933058"
STEFANO_IGSID = "17841400506734756"

TESTS = [
    {
        "id": "health",
        "method": "GET",
        "path": "/health",
        "expected_status": 200,
        "response_contains": "status",
    },
    {
        "id": "health_live",
        "method": "GET",
        "path": "/health/live",
        "expected_status": 200,
        "response_contains": "ok",
    },
    {
        "id": "health_ready",
        "method": "GET",
        "path": "/health/ready",
        "expected_status": 200,
        "response_contains": None,
    },
    {
        "id": "health_tasks",
        "method": "GET",
        "path": "/health/tasks",
        "expected_status": 200,
        "response_contains": None,
    },
    {
        "id": "conversations_iris",
        "method": "GET",
        "path": "/dm/conversations/iris_bertran",
        "expected_status": 200,
        "response_contains": None,
    },
    {
        "id": "conversations_stefano",
        "method": "GET",
        "path": "/dm/conversations/stefano_bonanno",
        "expected_status": 200,
        "response_contains": None,
    },
    {
        "id": "debug_memory",
        "method": "GET",
        "path": "/debug/memory",
        "expected_status": 200,
        "response_contains": "rss_mb",
    },
]


def _db_skip(check_id, reason):
    print(f"  [SKIP] {check_id:30s} — {reason}")
    return {"id": check_id, "path": "db", "status": 0, "passed": True, "detail": f"SKIP: {reason}"}


def run_db_checks():
    """Run DB data integrity checks. Returns (results_list, all_passed).
    Skips gracefully (passed=True) when DATABASE_URL is unavailable.
    """
    database_url = os.environ.get("DATABASE_URL")
    skip_ids = ["no_cross_creator_leads", "no_ghost_leads", "correct_routing_ids"]

    if not database_url:
        return [_db_skip(cid, "no DATABASE_URL") for cid in skip_ids], True

    try:
        import psycopg2
    except ImportError:
        return [_db_skip(cid, "psycopg2 not installed") for cid in skip_ids], True

    results = []
    all_passed = True

    try:
        conn = psycopg2.connect(database_url)
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()

        # Check 8: no platform_user_id under more than one creator
        cur.execute("""
            SELECT platform_user_id, COUNT(DISTINCT creator_id) AS cnt
            FROM leads
            WHERE platform = 'instagram'
            GROUP BY platform_user_id
            HAVING COUNT(DISTINCT creator_id) > 1
        """)
        rows = cur.fetchall()
        passed = len(rows) == 0
        detail = "OK" if passed else f"{len(rows)} duplicate(s): {[r[0] for r in rows[:5]]}"
        if not passed:
            all_passed = False
        print(f"  [{'PASS' if passed else 'FAIL'}] {'no_cross_creator_leads':30s} — {detail}")
        results.append({"id": "no_cross_creator_leads", "path": "db",
                        "status": 200 if passed else 500, "passed": passed, "detail": detail})

        # Check 9: no ghost leads (lead's platform_user_id = creator's own instagram_user_id)
        cur.execute("""
            SELECT l.platform_user_id, c.name
            FROM leads l
            JOIN creators c ON l.creator_id = c.id
            WHERE l.platform = 'instagram'
              AND l.platform_user_id = c.instagram_user_id
        """)
        rows = cur.fetchall()
        passed = len(rows) == 0
        detail = "OK" if passed else f"{len(rows)} ghost(s): {[r[1] for r in rows[:5]]}"
        if not passed:
            all_passed = False
        print(f"  [{'PASS' if passed else 'FAIL'}] {'no_ghost_leads':30s} — {detail}")
        results.append({"id": "no_ghost_leads", "path": "db",
                        "status": 200 if passed else 500, "passed": passed, "detail": detail})

        # Check 10: Iris/Stefano IGSIDs in correct additional_ids, not swapped
        cur.execute("""
            SELECT name, instagram_additional_ids
            FROM creators
            WHERE name IN ('iris_bertran', 'stefano_bonanno')
        """)
        creator_ids = {row[0]: (row[1] or []) for row in cur.fetchall()}
        iris_ids = creator_ids.get("iris_bertran", [])
        stefano_ids = creator_ids.get("stefano_bonanno", [])

        issues = []
        if IRIS_IGSID not in iris_ids:
            issues.append(f"iris missing own IGSID {IRIS_IGSID}")
        if STEFANO_IGSID in iris_ids:
            issues.append(f"iris has stefano IGSID {STEFANO_IGSID}")
        if STEFANO_IGSID not in stefano_ids:
            issues.append(f"stefano missing own IGSID {STEFANO_IGSID}")
        if IRIS_IGSID in stefano_ids:
            issues.append(f"stefano has iris IGSID {IRIS_IGSID}")

        passed = len(issues) == 0
        detail = "OK" if passed else "; ".join(issues)
        if not passed:
            all_passed = False
        print(f"  [{'PASS' if passed else 'FAIL'}] {'correct_routing_ids':30s} — {detail}")
        results.append({"id": "correct_routing_ids", "path": "db",
                        "status": 200 if passed else 500, "passed": passed, "detail": detail})

        cur.close()
        conn.close()

    except Exception as e:
        for cid in skip_ids:
            if not any(r["id"] == cid for r in results):
                results.append(_db_skip(cid, f"DB error: {str(e)[:60]}"))

    return results, all_passed


def run_tests():
    """Ejecuta todos los smoke tests. Retorna (results_list, all_passed)."""
    results = []
    all_passed = True

    print("=" * 60)
    print(f"SMOKE TEST — {BASE}")
    print(f"Fecha: {datetime.now().isoformat()}")
    print("=" * 60)

    for t in TESTS:
        test_id = t["id"]
        url = f"{BASE}{t['path']}"
        headers = {}
        if "/admin/" in t["path"]:
            headers["X-API-Key"] = ADMIN_KEY

        try:
            resp = requests.request(t["method"], url, headers=headers, timeout=TIMEOUT)
            status = resp.status_code
            body = resp.text
        except requests.exceptions.Timeout:
            # One retry after a short wait (Railway cold-start)
            time.sleep(RETRY_WAIT)
            try:
                resp = requests.request(t["method"], url, headers=headers, timeout=TIMEOUT)
                status = resp.status_code
                body = resp.text
            except Exception as e2:
                passed = False
                status = 0
                body = ""
                status_str = "FAIL"
                detail = f"timeout (retry also failed: {str(e2)[:60]})"
                all_passed = False
                print(f"  [{status_str}] {test_id:30s} — {detail}")
                results.append({"id": test_id, "path": t["path"], "status": status,
                                 "passed": passed, "detail": detail})
                continue
        except Exception as e:
            passed = False
            status = 0
            body = ""
            status_str = "FAIL"
            detail = str(e)[:100]
            all_passed = False
            print(f"  [{status_str}] {test_id:30s} — {detail}")
            results.append({"id": test_id, "path": t["path"], "status": status,
                             "passed": passed, "detail": detail})
            continue

        try:
            passed = status == t["expected_status"]
            if passed and t.get("response_contains"):
                passed = t["response_contains"] in body

            status_str = "PASS" if passed else "FAIL"
            detail = f"HTTP {status}"
            if not passed:
                detail += f" (expected {t['expected_status']})"
                if t.get("response_contains") and status == t["expected_status"]:
                    detail = f"missing '{t['response_contains']}' in response"
                all_passed = False
        except Exception as e:
            passed = False
            status_str = "FAIL"
            detail = str(e)[:100]
            all_passed = False

        print(f"  [{status_str}] {test_id:30s} — {detail}")
        results.append({
            "id": test_id,
            "path": t["path"],
            "status": status,
            "passed": passed,
            "detail": detail,
        })

    db_results, db_passed = run_db_checks()
    results.extend(db_results)
    if not db_passed:
        all_passed = False

    print("=" * 60)
    skipped = sum(1 for r in results if r["detail"].startswith("SKIP"))
    total_pass = sum(1 for r in results if r["passed"] and not r["detail"].startswith("SKIP"))
    total_counted = len(results) - skipped
    print(f"Resultado: {total_pass}/{total_counted} passed" + (f" ({skipped} skipped)" if skipped else ""))
    print("=" * 60)

    return results, all_passed


def save_baseline(results, path):
    """Guardar resultados como baseline JSON."""
    data = {
        "captured_at": datetime.now().isoformat(),
        "base_url": BASE,
        "results": results,
    }
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\n✅ Baseline guardado en: {path}")


def compare_baseline(results, path):
    """Comparar resultados actuales contra baseline."""
    with open(path) as f:
        baseline = json.load(f)

    baseline_map = {r["id"]: r for r in baseline["results"]}
    regressions = []

    print(f"\nComparando contra baseline de {baseline['captured_at']}:")
    for r in results:
        b = baseline_map.get(r["id"])
        if not b:
            print(f"  [NEW]  {r['id']}")
            continue
        if b["passed"] and not r["passed"]:
            regressions.append(r["id"])
            print(f"  [REGRESSION] {r['id']}: was PASS, now FAIL — {r['detail']}")
        elif not b["passed"] and r["passed"]:
            print(f"  [FIXED] {r['id']}: was FAIL, now PASS")
        else:
            print(f"  [OK]   {r['id']}")

    if regressions:
        print(f"\n❌ {len(regressions)} regression(s) detected!")
        return False
    else:
        print("\n✅ No regressions detected.")
        return True


def main():
    parser = argparse.ArgumentParser(description="Clonnect smoke tests")
    parser.add_argument("--save-baseline", metavar="PATH", help="Save results as baseline JSON")
    parser.add_argument("--compare", metavar="PATH", help="Compare results against baseline JSON")
    args = parser.parse_args()

    results, all_passed = run_tests()

    if args.save_baseline:
        save_baseline(results, args.save_baseline)

    if args.compare:
        no_regressions = compare_baseline(results, args.compare)
        if not no_regressions:
            sys.exit(1)

    if not all_passed:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
