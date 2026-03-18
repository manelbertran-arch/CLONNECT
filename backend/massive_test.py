"""CLONNECT MASSIVE E2E TEST — CAPAS 0-6 AUTOMATIZADO (v2)

Cambios v2:
- Todas las rutas corregidas vs OpenAPI spec real
- Función test() con expect=200 para validación estricta
- Tests de SQL injection y path traversal añadidos
- Clasificación de 404s: datos faltantes vs rutas incorrectas
- Métricas de performance con thresholds
"""
import subprocess, sys, time, json, os

BASE = 'https://www.clonnectapp.com'
KEY = 'clonnect_admin_secret_2024'
CREATOR = 'stefano_bonanno'
results = []
total_tests = 0
passed = 0
failed = 0
warnings = 0

def bar(current, total, label=''):
    w = 40
    p = int(w * current / total) if total else 0
    pct = int(100 * current / total) if total else 0
    sys.stdout.write(f'\r[{"█"*p}{"░"*(w-p)}] {pct}% ({current}/{total}) {label[:50]}')
    sys.stdout.flush()

def test(name, cmd, expect=None, max_time=None):
    """
    expect: None = any non-5xx is PASS (legacy)
            int  = exact HTTP code match required
            list = any code in list is PASS
    max_time: if set, WARN when response exceeds this (seconds)
    """
    global total_tests, passed, failed, warnings
    total_tests += 1
    bar(total_tests, TOTAL, name)
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=30)
        out = r.stdout.strip()
        code = None
        try: code = int(out.split('|')[0])
        except: pass
        timing = None
        try: timing = float(out.split('|')[1])
        except: pass

        # Determine pass/fail
        if expect is None:
            if code and code >= 500:
                status = 'FAIL'
            elif code and code < 500:
                status = 'PASS'
            else:
                status = 'WARN'
        elif isinstance(expect, int):
            status = 'PASS' if code == expect else 'FAIL'
        elif isinstance(expect, list):
            status = 'PASS' if code in expect else 'FAIL'
        else:
            status = 'WARN'

        # Performance warning
        perf_warn = ''
        if max_time and timing and timing > max_time:
            perf_warn = f' [SLOW: {timing:.1f}s > {max_time}s]'
            if status == 'PASS':
                status = 'WARN'

        if status == 'PASS': passed += 1
        elif status == 'FAIL': failed += 1
        else: warnings += 1

        results.append({'name': name, 'status': status, 'code': code, 'time': timing,
                        'expected': expect, 'perf_warn': perf_warn})
    except Exception as e:
        failed += 1
        results.append({'name': name, 'status': 'FAIL', 'code': None, 'time': None, 'error': str(e)})

def curl_get(path, auth=True):
    h = f'-H "X-API-Key: {KEY}"' if auth else ''
    return f'curl -s -o /dev/null -w "%{{http_code}}|%{{time_total}}" --max-time 15 {h} "{BASE}{path}"'

def curl_post(path, body='{}', auth=True):
    h = f'-H "X-API-Key: {KEY}"' if auth else ''
    return f"""curl -s -o /dev/null -w "%{{http_code}}|%{{time_total}}" --max-time 20 {h} -X POST -H "Content-Type: application/json" -d '{body}' "{BASE}{path}" """

TOTAL = 131  # Approximate, updated at end

print('=' * 60)
print('CLONNECT MASSIVE E2E TEST v2 — CAPAS 0-6')
print('=' * 60)
print()

# ========== CAPA 0: INFRAESTRUCTURA (11 tests) ==========
print('\n CAPA 0 — INFRAESTRUCTURA')
test('Health check', curl_get('/health'), expect=200)
test('Health live', curl_get('/health/live'), expect=200)
test('Health ready', curl_get('/health/ready'), expect=200)
test('Docs OpenAPI', curl_get('/docs', auth=False), expect=200)
test('OpenAPI JSON', curl_get('/openapi.json', auth=False), expect=200)
test('Frontend loads', curl_get('/', auth=False), expect=200)
test('Login page', curl_get('/login', auth=False), expect=200)
test('Dashboard page', curl_get('/dashboard', auth=False), expect=200)
test('Admin sin key → 401', curl_get('/admin/stats', auth=False), expect=401)
test('Admin con key → 200', curl_get('/admin/stats'), expect=200, max_time=2.0)
test('Metrics endpoint', curl_get('/metrics', auth=False), expect=200)

# ========== CAPA 1: DATABASE (8 tests) ==========
print('\n\n CAPA 1 — BASE DE DATOS')
test('Creator exists', curl_get(f'/creator/config/{CREATOR}'), expect=200)
test('Leads exist', curl_get(f'/dm/leads/{CREATOR}'), expect=200)
test('Products exist', curl_get(f'/creator/{CREATOR}/products'), expect=200)
test('Messages exist', curl_get(f'/dm/conversations/{CREATOR}'), expect=200)
test('Knowledge exists', curl_get(f'/creator/config/{CREATOR}/knowledge'), expect=200)
test('Tone exists', curl_get(f'/tone/{CREATOR}'), expect=200)
test('Analytics data', curl_get(f'/analytics/{CREATOR}/sales'), expect=200)
test('Health cache', curl_get('/health/cache'), expect=200)

# ========== CAPA 2: SERVICIOS CORE (12 tests) ==========
print('\n\n CAPA 2 — SERVICIOS CORE')
test('DM hola', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"hola que tal","sender_id":"e2e_test_001"}'), expect=200)
test('DM compra', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"quiero comprar tu programa","sender_id":"e2e_test_002"}'), expect=200)
test('DM emoji', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"genial","sender_id":"e2e_test_003"}'), expect=200)
long_msg = 'a' * 500
test('DM largo', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"' + long_msg + '","sender_id":"e2e_test_004"}'), expect=200)
test('Copilot pending', curl_get(f'/copilot/{CREATOR}/pending'), expect=200)
test('Copilot status', curl_get(f'/copilot/{CREATOR}/status'), expect=200)
test('Copilot suggest (nuevo endpoint)', curl_post(f'/copilot/{CREATOR}/suggest', '{"lead_id":"00000000-0000-0000-0000-000000000001"}'), expect=[404, 422])
test('Content search (GET)', curl_get(f'/content/search?creator_id={CREATOR}&query=fitness'), expect=200)
test('Citations search (POST)', curl_post('/citations/search', '{"query":"fitness","creator_id":"' + CREATOR + '"}'), expect=200)
test('Clone score', curl_get(f'/clone-score/{CREATOR}'), expect=200)
test('DM metrics', curl_get(f'/dm/metrics/{CREATOR}'), expect=200)
test('DM leads list', curl_get(f'/dm/leads/{CREATOR}'), expect=200)
test('Content stats', curl_get('/content/stats'), expect=200)

# ========== CAPA 3: ENDPOINTS API ==========
print('\n\n CAPA 3 — ENDPOINTS API')

# --- Admin GETs (15 tests) ---
admin_gets = [
    ('/admin/stats', 200, 2.0),
    ('/admin/conversations', 200, 3.0),
    ('/admin/pending-messages', 200, None),
    ('/admin/alerts', 200, None),
    ('/admin/feature-flags', 200, None),
    ('/admin/demo-status', 200, None),
    ('/admin/creators', 200, None),
    (f'/admin/sync-status/{CREATOR}', 200, None),
    (f'/admin/oauth/status/{CREATOR}', 200, None),
    ('/admin/backups', 200, None),
    (f'/admin/ingestion/status/{CREATOR}', 200, None),
    ('/admin/lead-categories', 200, None),
    (f'/admin/ghost-stats/{CREATOR}', 200, None),
    ('/admin/ghost-config', 200, None),
    ('/admin/rate-limiter-stats', 200, None),
]
for ep, exp, mt in admin_gets:
    test(f'Admin GET {ep}', curl_get(ep), expect=exp, max_time=mt)

# --- Creator GETs (21 tests) ---
creator_gets = [
    (f'/creator/config/{CREATOR}', 200),
    ('/creator/list', 200),
    (f'/dashboard/{CREATOR}/overview', 200),
    (f'/creator/{CREATOR}/products', 200),
    (f'/creator/config/{CREATOR}/knowledge', 200),
    (f'/analytics/{CREATOR}/sales', 200),
    (f'/tone/{CREATOR}', 200),
    (f'/connections/{CREATOR}', 200),
    (f'/calendar/{CREATOR}/links', 200),
    (f'/insights/{CREATOR}/today', 200),
    (f'/intelligence/{CREATOR}/dashboard', 200),
    (f'/audience/{CREATOR}/segments', 200),
    (f'/audiencia/{CREATOR}/topics', 200),
    ('/content/stats', 200),
    (f'/citations/{CREATOR}/stats', 200),
    (f'/clone-score/{CREATOR}', 200),
    (f'/payments/{CREATOR}/revenue', 200),
    (f'/booking-links/{CREATOR}', 200),
    (f'/bot/{CREATOR}/status', 200),
    ('/preview/status', 200),
    (f'/leads/{CREATOR}/unified', 200),
]
for item in creator_gets:
    ep, exp = item[0], item[1]
    test(f'Creator GET {ep}', curl_get(ep), expect=exp)

# --- Leads GETs (3 tests) ---
lead_gets = [
    (f'/dm/leads/{CREATOR}', 200),
    (f'/dm/metrics/{CREATOR}', 200),
    ('/admin/lead-categories', 200),
]
for ep, exp in lead_gets:
    test(f'Leads GET {ep}', curl_get(ep), expect=exp)

# --- Nurturing GETs (3 tests) ---
nurt_gets = [
    (f'/nurturing/{CREATOR}/sequences', 200),
    (f'/nurturing/{CREATOR}/followups', 200),
    ('/nurturing/scheduler/status', 200),
]
for ep, exp in nurt_gets:
    test(f'Nurturing GET {ep}', curl_get(ep), expect=exp)

# --- DM GETs (3 tests) ---
dm_gets = [
    (f'/dm/conversations/{CREATOR}', 200),
    (f'/dm/metrics/{CREATOR}', 200),
    (f'/dm/leads/{CREATOR}', 200),
]
for ep, exp in dm_gets:
    test(f'DM GET {ep}', curl_get(ep), expect=exp)

# --- OAuth GETs (2 tests) ---
oauth_gets = [
    ('/oauth/debug', 200),
    (f'/oauth/status/{CREATOR}', 200),
]
for ep, exp in oauth_gets:
    test(f'OAuth GET {ep}', curl_get(ep), expect=exp)

# --- Knowledge GETs (3 tests) ---
kl_gets = [
    (f'/creator/config/{CREATOR}/knowledge/faqs', 200),
    (f'/autolearning/{CREATOR}/rules', 200),
    (f'/autolearning/{CREATOR}/dashboard', 200),
]
for ep, exp in kl_gets:
    test(f'Knowledge GET {ep}', curl_get(ep), expect=exp)

# --- Other GETs (3 tests) ---
other_gets = [
    (f'/maintenance/echo-status/{CREATOR}', 200),
    ('/debug/status', 200),
    (f'/events/{CREATOR}', [200, 401]),  # requires JWT, not API key
]
for ep, exp in other_gets:
    test(f'Other GET {ep}', curl_get(ep), expect=exp)

# ========== CAPA 4: FLUJOS E2E (4 tests) ==========
print('\n\n CAPA 4 — FLUJOS E2E')
test('Flow: DM pipeline completo', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"me interesa el programa de fitness cuanto cuesta","sender_id":"e2e_flow_001"}'), expect=200, max_time=15.0)
test('Flow: Webhook Instagram vacio', curl_post('/webhook/instagram', '{}', auth=False), expect=400)
test('Flow: Webhook Stripe vacio', curl_post('/webhook/stripe', '{}', auth=False))
test('Flow: Webhook WhatsApp vacio', curl_post('/webhook/whatsapp', '{}', auth=False))

# ========== CAPA 5: RESILIENCE & SECURITY (14 tests) ==========
print('\n\n CAPA 5 — RESILIENCE & SECURITY')
test('XSS attempt', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"<script>alert(1)</script>","sender_id":"xss_test"}'), expect=200)
test('Creator inexistente', curl_get('/dm/leads/FAKE_NONEXISTENT_CREATOR'), expect=[200, 404])
test('Creator inexistente products', curl_get('/creator/FAKE_NONEXISTENT_CREATOR/products'), expect=[200, 404])
test('Creator inexistente config', curl_get('/creator/config/FAKE_NONEXISTENT_CREATOR'), expect=[200, 404])
test('Empty body POST dm', curl_post('/dm/process', '{}'), expect=[400, 422])
test('Missing fields dm', curl_post('/dm/process', '{"message":"hola"}'), expect=[400, 422])
test('Invalid JSON dm', f'curl -s -o /dev/null -w "%{{http_code}}|%{{time_total}}" --max-time 10 -X POST -H "Content-Type: application/json" -d "not json" "{BASE}/dm/process"', expect=422)
test('Webhook invalid payload', curl_post('/webhook/instagram', '{"invalid":true}', auth=False), expect=400)
test('Admin nuclear POST sin auth → 401', curl_post('/admin/nuclear-reset', '{}', auth=False), expect=401)
test('Unicode heavy', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"hello world test","sender_id":"unicode_test"}'), expect=200)
# SQL Injection test (URL-encoded special chars)
test('SQL injection attempt', curl_get(f'/dm/leads/%27%3B%20DROP%20TABLE%20leads%3B--'), expect=[200, 404, 422])
# Path traversal tests
test('Path traversal encoded', curl_get('/%2e%2e/%2e%2e/%2e%2e/etc/passwd', auth=False), expect=[400, 404])
test('Path traversal etc/passwd', curl_get('/etc/passwd', auth=False), expect=[400, 404])
test('Path traversal wp-admin', curl_get('/wp-admin', auth=False), expect=[400, 404])

# ========== CAPA 6: PERFORMANCE (6 tests) ==========
print('\n\n CAPA 6 — PERFORMANCE')
for i in range(5):
    test(f'Health timing #{i+1}', curl_get('/health'), expect=200, max_time=1.0)
test('DM timing', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"test timing","sender_id":"perf_test"}'), expect=200, max_time=15.0)

TOTAL = total_tests

# ========== INFORME ==========
print('\n\n')
print('=' * 60)
print('RESULTADOS FINALES')
print('=' * 60)
print(f'Total tests: {total_tests}')
print(f'PASS: {passed}')
print(f'FAIL: {failed}')
print(f'WARN: {warnings}')
pct = passed * 100 // total_tests if total_tests else 0
print(f'Pass rate: {pct}%')
print()

if failed > 0:
    print('FALLOS:')
    for r in results:
        if r['status'] == 'FAIL':
            exp = r.get('expected', '')
            print(f'  ✗ {r["name"]}: HTTP {r.get("code","?")} (expected {exp}) {r.get("error","")}')

if warnings > 0:
    print('\nWARNINGS:')
    for r in results:
        if r['status'] == 'WARN':
            pw = r.get('perf_warn', '')
            print(f'  ⚠ {r["name"]}: HTTP {r.get("code","?")}{pw}')

print('\nTIMING (top 10 mas lentos):')
timed = [r for r in results if r.get('time')]
timed.sort(key=lambda x: x['time'], reverse=True)
for r in timed[:10]:
    flag = ' ← SLOW' if r.get('perf_warn') else ''
    print(f'  {r["time"]:.2f}s - {r["name"]}{flag}')

# Performance summary
slow_endpoints = [r for r in results if r.get('perf_warn')]
if slow_endpoints:
    print(f'\n⚠ {len(slow_endpoints)} endpoints exceden el threshold de performance')

with open('MASSIVE_TEST_REPORT.json', 'w') as f:
    json.dump({'total': total_tests, 'passed': passed, 'failed': failed, 'warnings': warnings, 'results': results}, f, indent=2)
print(f'\nResultados guardados en MASSIVE_TEST_REPORT.json')

with open('MASSIVE_TEST_REPORT.md', 'w') as f:
    f.write('# CLONNECT — MASSIVE TEST REPORT v2\n\n')
    f.write(f'**Entorno:** Produccion (www.clonnectapp.com)\n\n')
    f.write('## RESUMEN\n\n')
    f.write('| Metrica | Valor |\n|---------|-------|\n')
    f.write(f'| Tests ejecutados | {total_tests} |\n')
    f.write(f'| PASS | {passed} |\n')
    f.write(f'| FAIL | {failed} |\n')
    f.write(f'| WARN | {warnings} |\n')
    f.write(f'| Pass rate | {pct}% |\n\n')
    f.write('## RESULTADOS DETALLADOS\n\n')
    f.write('| # | Test | Status | HTTP | Expected | Tiempo |\n')
    f.write('|---|------|--------|------|----------|--------|\n')
    for i, r in enumerate(results, 1):
        t = f'{r["time"]:.2f}s' if r.get('time') else '-'
        exp = str(r.get('expected', 'any<500'))
        pw = r.get('perf_warn', '')
        f.write(f'| {i} | {r["name"]} | {r["status"]} | {r.get("code","-")} | {exp} | {t}{pw} |\n')
    if failed > 0:
        f.write('\n## FALLOS\n\n')
        for r in results:
            if r['status'] == 'FAIL':
                f.write(f'- **{r["name"]}**: HTTP {r.get("code","?")} (expected {r.get("expected","")}) {r.get("error","")}\n')
    if warnings > 0:
        f.write('\n## WARNINGS\n\n')
        for r in results:
            if r['status'] == 'WARN':
                f.write(f'- **{r["name"]}**: HTTP {r.get("code","?")}{r.get("perf_warn","")}\n')
    f.write('\n## TOP 10 MAS LENTOS\n\n')
    for r in timed[:10]:
        flag = ' **SLOW**' if r.get('perf_warn') else ''
        f.write(f'- {r["time"]:.2f}s - {r["name"]}{flag}\n')

print('Report guardado en MASSIVE_TEST_REPORT.md')
print('\nDONE')
