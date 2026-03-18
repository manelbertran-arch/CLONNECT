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
import sys
from datetime import datetime

import requests

BASE = "https://www.clonnectapp.com"
ADMIN_KEY = "clonnect_admin_secret_2024"
TIMEOUT = 15

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
            status = 0
            body = ""
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

    print("=" * 60)
    total_pass = sum(1 for r in results if r["passed"])
    print(f"Resultado: {total_pass}/{len(results)} passed")
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
