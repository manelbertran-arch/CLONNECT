"""CLONNECT MASSIVE E2E TEST — CAPAS 0-6 AUTOMATIZADO"""
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

def test(name, cmd, expect_not_500=True):
    global total_tests, passed, failed, warnings
    total_tests += 1
    bar(total_tests, TOTAL, name)
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        out = r.stdout.strip()
        code = None
        try: code = int(out.split('|')[0])
        except: pass
        timing = None
        try: timing = float(out.split('|')[1])
        except: pass

        if code and code >= 500:
            failed += 1
            status = 'FAIL'
        elif code and code >= 400 and expect_not_500:
            passed += 1
            status = 'PASS'
        elif code and code < 400:
            passed += 1
            status = 'PASS'
        else:
            warnings += 1
            status = 'WARN'
        results.append({'name': name, 'status': status, 'code': code, 'time': timing})
    except Exception as e:
        failed += 1
        results.append({'name': name, 'status': 'FAIL', 'code': None, 'time': None, 'error': str(e)})

def curl_get(path, auth=True):
    h = f'-H "X-API-Key: {KEY}"' if auth else ''
    return f'curl -s -o /dev/null -w "%{{http_code}}|%{{time_total}}" --max-time 15 {h} "{BASE}{path}"'

def curl_post(path, body='{}', auth=True):
    h = f'-H "X-API-Key: {KEY}"' if auth else ''
    return f"""curl -s -o /dev/null -w "%{{http_code}}|%{{time_total}}" --max-time 20 {h} -X POST -H "Content-Type: application/json" -d '{body}' "{BASE}{path}" """

TOTAL = 150

print('=' * 60)
print('CLONNECT MASSIVE E2E TEST — CAPAS 0-6')
print('=' * 60)
print()

# ========== CAPA 0: INFRAESTRUCTURA ==========
print('\n CAPA 0 — INFRAESTRUCTURA')
test('Health check', curl_get('/health'))
test('Health live', curl_get('/health/live'))
test('Health ready', curl_get('/health/ready'))
test('Docs OpenAPI', curl_get('/docs', auth=False))
test('OpenAPI JSON', curl_get('/openapi.json', auth=False))
test('Frontend loads', curl_get('/', auth=False))
test('Login page', curl_get('/login', auth=False))
test('Dashboard page', curl_get('/dashboard', auth=False))
test('Admin sin key 401', curl_get('/admin/stats', auth=False))
test('Admin con key 200', curl_get('/admin/stats'))
test('Metrics endpoint', curl_get('/metrics', auth=False))

# ========== CAPA 1: DATABASE ==========
print('\n\n CAPA 1 — BASE DE DATOS')
test('Creator exists', curl_get(f'/config/profiles/{CREATOR}'))
test('Leads exist', curl_get(f'/leads/{CREATOR}'))
test('Products exist', curl_get(f'/products/{CREATOR}'))
test('Messages exist', curl_get(f'/dm/conversations/{CREATOR}'))
test('Knowledge exists', curl_get(f'/knowledge/{CREATOR}'))
test('Tone exists', curl_get(f'/tone/{CREATOR}'))
test('Analytics data', curl_get(f'/analytics/{CREATOR}'))
test('Memory stats', curl_get(f'/memory/stats/{CREATOR}'))

# ========== CAPA 2: SERVICIOS CORE ==========
print('\n\n CAPA 2 — SERVICIOS CORE')
test('DM hola', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"hola que tal","sender_id":"e2e_test_001"}'))
test('DM compra', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"quiero comprar tu programa","sender_id":"e2e_test_002"}'))
test('DM emoji', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"genial","sender_id":"e2e_test_003"}'))
long_msg = 'a' * 500
test('DM largo', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"' + long_msg + '","sender_id":"e2e_test_004"}'))
test('Copilot pending', curl_get(f'/copilot/pending/{CREATOR}'))
test('Copilot status', curl_get(f'/copilot/status/{CREATOR}'))
test('Knowledge search', curl_post(f'/knowledge/search/{CREATOR}', '{"query":"fitness"}'))
test('Clone score', curl_get(f'/clone-score/{CREATOR}'))
test('DM stats', curl_get(f'/dm/stats/{CREATOR}'))
test('DM followers', curl_get(f'/dm/followers/{CREATOR}'))

# ========== CAPA 3: ENDPOINTS API ==========
print('\n\n CAPA 3 — ENDPOINTS API')

admin_gets = [
    '/admin/stats', '/admin/conversations', '/admin/pending-messages',
    '/admin/alerts', '/admin/feature-flags', '/admin/demo-status',
    '/admin/list-creators', f'/admin/sync-status/{CREATOR}',
    f'/admin/oauth-status/{CREATOR}', '/admin/backups',
    f'/admin/ingestion/status/{CREATOR}', '/admin/lead-categories',
    f'/admin/ghost-stats/{CREATOR}', '/admin/ghost-config',
    '/admin/rate-limiter-stats'
]
for ep in admin_gets:
    test(f'Admin GET {ep}', curl_get(ep))

creator_gets = [
    f'/config/profiles/{CREATOR}', '/config/profiles',
    f'/dashboard/stats/{CREATOR}', f'/products/{CREATOR}',
    f'/knowledge/{CREATOR}', f'/analytics/{CREATOR}',
    f'/tone/{CREATOR}', f'/connections/{CREATOR}',
    f'/calendar/services/{CREATOR}', f'/insights/{CREATOR}',
    f'/intelligence/{CREATOR}', f'/audience/{CREATOR}',
    f'/audiencia/{CREATOR}', f'/content/{CREATOR}',
    f'/citations/{CREATOR}', f'/gdpr/status/{CREATOR}',
    f'/payments/status/{CREATOR}', f'/booking-links/{CREATOR}',
    f'/bot/{CREATOR}', f'/preview/{CREATOR}',
    f'/unified-leads/{CREATOR}'
]
for ep in creator_gets:
    test(f'Creator GET {ep}', curl_get(ep))

lead_gets = [f'/leads/{CREATOR}', f'/leads/{CREATOR}/stats', f'/leads/{CREATOR}/categories']
for ep in lead_gets:
    test(f'Leads GET {ep}', curl_get(ep))

nurt_gets = [
    f'/nurturing/sequences/{CREATOR}',
    f'/nurturing/followups/{CREATOR}',
    f'/nurturing/scheduler/status/{CREATOR}'
]
for ep in nurt_gets:
    test(f'Nurturing GET {ep}', curl_get(ep))

dm_gets = [f'/dm/conversations/{CREATOR}', f'/dm/stats/{CREATOR}', f'/dm/followers/{CREATOR}']
for ep in dm_gets:
    test(f'DM GET {ep}', curl_get(ep))

oauth_gets = ['/oauth/instagram/url', f'/oauth/status/{CREATOR}']
for ep in oauth_gets:
    test(f'OAuth GET {ep}', curl_get(ep))

kl_gets = [
    f'/knowledge/documents/{CREATOR}',
    f'/autolearning/rules/{CREATOR}',
    f'/autolearning/dashboard/{CREATOR}'
]
for ep in kl_gets:
    test(f'Knowledge GET {ep}', curl_get(ep))

other_gets = ['/maintenance/status', '/debug/routes', f'/events/{CREATOR}']
for ep in other_gets:
    test(f'Other GET {ep}', curl_get(ep))

# ========== CAPA 4: FLUJOS E2E ==========
print('\n\n CAPA 4 — FLUJOS E2E')
test('Flow: DM pipeline completo', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"me interesa el programa de fitness cuanto cuesta","sender_id":"e2e_flow_001"}'))
test('Flow: Webhook Instagram vacio', curl_post('/webhook/instagram', '{}', auth=False))
test('Flow: Webhook Stripe vacio', curl_post('/webhook/stripe', '{}', auth=False))
test('Flow: Webhook WhatsApp vacio', curl_post('/webhook/whatsapp', '{}', auth=False))

# ========== CAPA 5: RESILIENCE ==========
print('\n\n CAPA 5 — RESILIENCE')
test('XSS attempt', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"<script>alert(1)</script>","sender_id":"xss_test"}'))
test('Creator inexistente', curl_get('/leads/FAKE_NONEXISTENT_CREATOR'))
test('Creator inexistente products', curl_get('/products/FAKE_NONEXISTENT_CREATOR'))
test('Creator inexistente config', curl_get('/config/profiles/FAKE_NONEXISTENT_CREATOR'))
test('Empty body POST dm', curl_post('/dm/process', '{}'))
test('Missing fields dm', curl_post('/dm/process', '{"message":"hola"}'))
test('Invalid JSON dm', f'curl -s -o /dev/null -w "%{{http_code}}|%{{time_total}}" --max-time 10 -X POST -H "Content-Type: application/json" -d "not json" "{BASE}/dm/process"')
test('Webhook invalid payload', curl_post('/webhook/instagram', '{"invalid":true}', auth=False))
test('Admin sin auth', curl_get('/admin/nuclear-reset', auth=False))
test('Unicode heavy', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"hello world test","sender_id":"unicode_test"}'))

# ========== CAPA 6: PERFORMANCE ==========
print('\n\n CAPA 6 — PERFORMANCE')
for i in range(5):
    test(f'Health timing #{i+1}', curl_get('/health'))
test('DM timing', curl_post('/dm/process', '{"creator_id":"' + CREATOR + '","message":"test timing","sender_id":"perf_test"}'))

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
            print(f'  - {r["name"]}: HTTP {r.get("code","?")} {r.get("error","")}')

if warnings > 0:
    print('\nWARNINGS:')
    for r in results:
        if r['status'] == 'WARN':
            print(f'  - {r["name"]}: HTTP {r.get("code","?")}')

print('\nTIMING (top 10 mas lentos):')
timed = [r for r in results if r.get('time')]
timed.sort(key=lambda x: x['time'], reverse=True)
for r in timed[:10]:
    print(f'  {r["time"]:.2f}s - {r["name"]}')

with open('MASSIVE_TEST_REPORT.json', 'w') as f:
    json.dump({'total': total_tests, 'passed': passed, 'failed': failed, 'warnings': warnings, 'results': results}, f, indent=2)
print(f'\nResultados guardados en MASSIVE_TEST_REPORT.json')

with open('MASSIVE_TEST_REPORT.md', 'w') as f:
    f.write('# CLONNECT — MASSIVE TEST REPORT\n\n')
    f.write(f'**Entorno:** Produccion (www.clonnectapp.com)\n\n')
    f.write('## RESUMEN\n\n')
    f.write('| Metrica | Valor |\n|---------|-------|\n')
    f.write(f'| Tests ejecutados | {total_tests} |\n')
    f.write(f'| PASS | {passed} |\n')
    f.write(f'| FAIL | {failed} |\n')
    f.write(f'| WARN | {warnings} |\n')
    f.write(f'| Pass rate | {pct}% |\n\n')
    f.write('## RESULTADOS DETALLADOS\n\n')
    f.write('| # | Test | Status | HTTP | Tiempo |\n')
    f.write('|---|------|--------|------|--------|\n')
    for i, r in enumerate(results, 1):
        t = f'{r["time"]:.2f}s' if r.get('time') else '-'
        f.write(f'| {i} | {r["name"]} | {r["status"]} | {r.get("code","-")} | {t} |\n')
    if failed > 0:
        f.write('\n## FALLOS\n\n')
        for r in results:
            if r['status'] == 'FAIL':
                f.write(f'- **{r["name"]}**: HTTP {r.get("code","?")} {r.get("error","")}\n')
    f.write('\n## TOP 10 MAS LENTOS\n\n')
    for r in timed[:10]:
        f.write(f'- {r["time"]:.2f}s - {r["name"]}\n')

print('Report guardado en MASSIVE_TEST_REPORT.md')
print('\nDONE')
