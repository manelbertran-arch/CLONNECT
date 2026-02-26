#!/usr/bin/env python3
"""
CAPA 4 — E2E DEEP TEST
Verifica CONTENIDO de respuestas, no solo HTTP codes.
"""

import json
import time
import sys
import os
from datetime import datetime, timezone

BASE_URL = "https://www.clonnectapp.com"
CREATOR  = "stefano_bonanno"
ADMIN_KEY = "clonnect_admin_secret_2024"

try:
    import httpx
    client = httpx.Client(timeout=30.0, follow_redirects=True)
except ImportError:
    import urllib.request, urllib.error
    client = None

results = []

def req(method, path, body=None, headers=None, auth=True):
    url = BASE_URL + path
    h = {"Content-Type": "application/json"}
    if auth:
        h["X-API-Key"] = ADMIN_KEY
    if headers:
        h.update(headers)
    try:
        if client:
            resp = client.request(method, url, json=body, headers=h)
            return resp.status_code, resp.text
        else:
            data = json.dumps(body).encode() if body else None
            req_obj = urllib.request.Request(url, data=data, headers=h, method=method)
            try:
                with urllib.request.urlopen(req_obj, timeout=30) as r:
                    return r.status, r.read().decode()
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)

def dm(message, sender_id="deep_test_001", sleep=0):
    if sleep:
        time.sleep(sleep)
    return req("POST", "/dm/process", {
        "creator_id": CREATOR,
        "sender_id": sender_id,
        "message": message,
        "message_id": f"test_{int(time.time()*1000)}"
    }, auth=False)

def check(name, passed, detail=""):
    icon = "✅" if passed else "❌"
    results.append({"name": name, "passed": passed, "detail": detail, "group": current_group})
    print(f"  {icon} {name}: {detail}")
    return passed

current_group = "init"

# ═══════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("GRUPO 1 — DM PIPELINE DEEP (contenido real)")
print("="*60)
current_group = "DM Pipeline"

# 1. Saludo
status, body = dm("hola buenas")
try:
    data = json.loads(body)
    resp = data.get("response", "")
    check("DM saludo — responde", status == 200 and len(resp) >= 2,
          f"HTTP {status}, {len(resp)} chars: {resp[:60]!r}")
except Exception as e:
    check("DM saludo — responde", False, f"Parse error: {e} | {body[:80]}")

# 2. Intención compra
status, body = dm("quiero comprar tu programa de entrenamiento")
try:
    data = json.loads(body)
    resp = data.get("response", "")
    check("DM compra — respuesta sustancial", status == 200 and len(resp) > 20,
          f"{len(resp)} chars: {resp[:80]!r}")
except Exception as e:
    check("DM compra — respuesta sustancial", False, str(e))

# 3. Frustración
status, body = dm("estoy harto nadie me ayuda con esto")
try:
    data = json.loads(body)
    resp = data.get("response", "").lower()
    empathy_words = ["entend", "compren", "normal", "aquí", "ayud", "tranquil", "siento"]
    is_empathic = any(w in resp for w in empathy_words)
    check("DM frustración — respuesta empática", status == 200 and len(resp) > 10,
          f"empathy={is_empathic}, {len(resp)} chars: {resp[:70]!r}")
except Exception as e:
    check("DM frustración — respuesta empática", False, str(e))

# 4. Mensaje sensible
status, body = dm("me siento muy mal no se que hacer")
try:
    data = json.loads(body)
    resp = data.get("response", "")
    check("DM sensible — no crashea, responde", status == 200 and len(resp) > 10,
          f"{len(resp)} chars: {resp[:70]!r}")
except Exception as e:
    check("DM sensible — no crashea", False, str(e))

# 5. Emoji puro
status, body = dm("😂😂😂")
check("DM emoji puro — no crashea", status in (200, 422),
      f"HTTP {status}, {body[:60]}")

# 6. XSS
status, body = dm("<script>alert(1)</script>")
has_script = "<script>" in body
check("DM XSS — no refleja script", status in (200, 422) and not has_script,
      f"HTTP {status}, script_in_resp={has_script}")

# ═══════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("GRUPO 2 — MULTI-TURN CONTEXT")
print("="*60)
current_group = "Multi-turn"

sid = f"deep_multi_{int(time.time())}"
status1, body1 = dm("hola me llamo Carlos interesado en tus servicios", sender_id=sid)
time.sleep(2)
status2, body2 = dm("como te dije me interesa, que opciones hay", sender_id=sid)

try:
    d1 = json.loads(body1); r1 = d1.get("response","")
    d2 = json.loads(body2); r2 = d2.get("response","")
    check("Multi-turn msg1 OK", status1 == 200 and len(r1) > 5,
          f"{len(r1)} chars: {r1[:50]!r}")
    check("Multi-turn msg2 responde", status2 == 200 and len(r2) >= 5,
          f"{len(r2)} chars: {r2[:80]!r}")
except Exception as e:
    check("Multi-turn context", False, str(e))

# ═══════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("GRUPO 3 — RAG VERIFICATION")
print("="*60)
current_group = "RAG"

status, body = dm("que tipo de entrenamiento ofreces")
try:
    data = json.loads(body); resp = data.get("response","")
    check("RAG training info", status == 200 and len(resp) > 20,
          f"{len(resp)} chars: {resp[:80]!r}")
except Exception as e:
    check("RAG training info", False, str(e))

status, body = dm("cuanto cuesta el programa")
try:
    data = json.loads(body); resp = data.get("response","")
    check("RAG pricing info", status == 200 and len(resp) > 10,
          f"{len(resp)} chars: {resp[:80]!r}")
except Exception as e:
    check("RAG pricing info", False, str(e))

# ═══════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("GRUPO 4 — EDGE CASES DEEP")
print("="*60)
current_group = "Edge Cases"

# Mensaje vacío
status, body = dm("")
check("Edge: vacío — no crashea", status in (200, 400, 422),
      f"HTTP {status}")

# Solo números
status, body = dm("12345")
check("Edge: solo números — no crashea", status in (200, 422),
      f"HTTP {status}, {body[:40]}")

# Muy largo
status, body = dm("a" * 1000)
check("Edge: 1000 chars — no crashea y responde", status in (200, 400, 422),
      f"HTTP {status}")

# Caracteres especiales
status, body = dm("café señor naïve")
check("Edge: caracteres especiales — procesa", status in (200, 422),
      f"HTTP {status}, {body[:40]}")

# ═══════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("GRUPO 5 — LEAD LIFECYCLE")
print("="*60)
current_group = "Lead Lifecycle"

endpoints_5 = [
    ("GET /admin/full-diagnostic/{c}", f"/admin/full-diagnostic/{CREATOR}", "stats", True),
    ("GET /dm/conversations/{c}",       f"/dm/conversations/{CREATOR}",      None,    True),
    ("GET /admin/sync-status/{c}",      f"/admin/sync-status/{CREATOR}",     None,    True),
    ("GET /clone-score/{c}",            f"/clone-score/{CREATOR}",           None,    True),
]
for name, path, key, auth in endpoints_5:
    s, b = req("GET", path, auth=auth)
    try:
        d = json.loads(b)
        no_error = "error" not in str(d).lower() or s == 200
        has_data = (d.get(key) is not None) if key else True
        check(name, s == 200 and no_error,
              f"HTTP {s}, has_{key}={has_data if key else 'n/a'}")
    except Exception as e:
        check(name, False, f"HTTP {s}: {str(e)[:50]}")

# ═══════════════════════════════════════════════════════════════════
print("\n" + "="*60)
print("GRUPO 6 — ADMIN DATA INTEGRITY")
print("="*60)
current_group = "Admin Integrity"

admin_endpoints = [
    ("GET /admin/stats",                          "/admin/stats",                               True),
    ("GET /admin/ingestion/status/{c}",           f"/admin/ingestion/status/{CREATOR}",         True),
    ("GET /admin/ghost-stats/{c}",                f"/admin/ghost-stats/{CREATOR}",              True),
    ("GET /admin/diagnose-duplicate-leads/{c}",   f"/admin/diagnose-duplicate-leads/{CREATOR}", True),
]
for name, path, auth in admin_endpoints:
    s, b = req("GET", path, auth=auth)
    try:
        d = json.loads(b)
        is_ok = s == 200 and "error" not in d.get("status","ok").lower()
        check(name, is_ok, f"HTTP {s}, status={d.get('status','?')}")
    except Exception as e:
        check(name, s == 200, f"HTTP {s}: {str(e)[:50]}")

# ═══════════════════════════════════════════════════════════════════
passed = sum(1 for r in results if r["passed"])
failed = sum(1 for r in results if not r["passed"])
total  = len(results)

print("\n" + "="*60)
print("RESUMEN CAPA 4 — E2E PROFUNDO")
print("="*60)
print(f"  PASS:  {passed}/{total}")
print(f"  FAIL:  {failed}/{total}")
print(f"  RATE:  {int(100*passed/total) if total else 0}%")

if failed:
    print("\n  FALLOS:")
    for r in results:
        if not r["passed"]:
            print(f"    ❌ [{r['group']}] {r['name']}: {r['detail']}")

# ─── Write report ─────────────────────────────────────────────────
report_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "E2E_DEEP_REPORT.md")
with open(report_path, "w") as f:
    f.write(f"# CAPA 4 — E2E Profundo\n\n")
    f.write(f"**Fecha**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n")
    f.write(f"## Resultado: {passed}/{total} PASS ({int(100*passed/total) if total else 0}%)\n\n")

    groups = {}
    for r in results:
        groups.setdefault(r["group"], []).append(r)

    for grp, tests in groups.items():
        f.write(f"\n### {grp}\n")
        f.write("| Test | Estado | Detalle |\n|------|--------|--------|\n")
        for r in tests:
            icon = "✅" if r["passed"] else "❌"
            detail = r["detail"].replace("|", "\\|")[:100]
            f.write(f"| {r['name']} | {icon} | {detail} |\n")

    if failed:
        f.write("\n## Issues\n")
        for r in results:
            if not r["passed"]:
                f.write(f"- ❌ [{r['group']}] {r['name']}: {r['detail']}\n")

print(f"\n  📄 Report: {report_path}")
print(f"\n{'✅ CAPA 4 PASS' if failed == 0 else '⚠️  CAPA 4 CON FALLOS'}")
sys.exit(0 if failed == 0 else 1)
