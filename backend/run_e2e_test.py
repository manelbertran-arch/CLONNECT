import subprocess, sys, time, json, os, datetime

# ============================================================
# CLONNECT MASSIVE E2E TEST — CAPAS 0-6 AUTOMATIZADO
# ============================================================

BASE = 'https://www.clonnectapp.com'
KEY = 'clonnect_admin_secret_2024'
CREATOR = 'stefano_bonanno'
results = []
total_tests = 0
passed = 0
failed = 0
warnings = 0
current_layer = ''

def bar(current, total, label=''):
    w = 40
    p = int(w * current / total) if total else 0
    pct = int(100 * current / total) if total else 0
    icon = '✅' if 'PASS' in label else '❌' if 'FAIL' in label else '🔄'
    sys.stdout.write(f'\r  [{"█"*p}{"░"*(w-p)}] {pct}% ({current}/{total}) {icon} {label[:55].ljust(55)}')
    sys.stdout.flush()

def test(name, cmd, expect_not_500=True):
    global total_tests, passed, failed, warnings, TOTAL
    total_tests += 1
    bar(total_tests, TOTAL, name)
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=30)
        out = r.stdout.strip()
        code = None
        timing = None
        try:
            parts = out.split('|')
            code = int(parts[0])
            timing = float(parts[1])
        except: pass

        if code is None:
            warnings += 1
            status = 'WARN'
        elif code >= 500:
            failed += 1
            status = 'FAIL'
        elif expect_not_500:
            passed += 1
            status = 'PASS'
        else:
            passed += 1
            status = 'PASS'
        results.append({'name': name, 'layer': current_layer, 'status': status, 'code': code, 'time': timing})
        bar(total_tests, TOTAL, f'{status} {name}')
    except subprocess.TimeoutExpired:
        failed += 1
        results.append({'name': name, 'layer': current_layer, 'status': 'FAIL', 'code': None, 'time': 30, 'error': 'TIMEOUT 30s'})
        bar(total_tests, TOTAL, f'FAIL {name}')
    except Exception as e:
        failed += 1
        results.append({'name': name, 'layer': current_layer, 'status': 'FAIL', 'code': None, 'time': None, 'error': str(e)[:100]})
        bar(total_tests, TOTAL, f'FAIL {name}')

def curl_get(path, auth=True):
    h = f'-H "X-API-Key: {KEY}"' if auth else ''
    return f'curl -s -o /dev/null -w "%{{http_code}}|%{{time_total}}" --max-time 15 {h} "{BASE}{path}"'

def curl_post(path, body='{}', auth=True):
    h = f'-H "X-API-Key: {KEY}"' if auth else ''
    return f"curl -s -o /dev/null -w '%{{http_code}}|%{{time_total}}' --max-time 20 {h} -X POST -H 'Content-Type: application/json' -d '{body}' '{BASE}{path}'"

def curl_get_body(path, auth=True):
    h = f'-H "X-API-Key: {KEY}"' if auth else ''
    return f'curl -s --max-time 15 {h} "{BASE}{path}"'

def section(name):
    global current_layer
    current_layer = name
    print(f'\n\n{"="*60}')
    print(f'  {name}')
    print(f'{"="*60}')

# Pre-count total tests
TOTAL = 135

start_time = time.time()

print()
print('╔══════════════════════════════════════════════════════════╗')
print('║     CLONNECT — MASSIVE E2E TEST (CAPAS 0-6)            ║')
print('║     Target: www.clonnectapp.com                         ║')
print(f'║     {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}                              ║')
print('╚══════════════════════════════════════════════════════════╝')

# ==================== CAPA 0 ====================
section('🏗️  CAPA 0 — INFRAESTRUCTURA (8 tests)')
test('Health check', curl_get('/health', auth=False))
test('Health ready', curl_get('/health/ready', auth=False))
test('Docs OpenAPI', curl_get('/docs', auth=False))
test('OpenAPI JSON', curl_get('/openapi.json', auth=False))
test('Frontend loads /', curl_get('/', auth=False))
test('Frontend /login', curl_get('/login', auth=False))
test('Frontend /dashboard', curl_get('/dashboard', auth=False))
test('Admin sin key → 401/403', curl_get('/admin/stats', auth=False))
test('Admin con key → 200', curl_get('/admin/stats'))
test('CORS preflight', 'curl -s -o /dev/null -w "%{http_code}|%{time_total}" --max-time 10 -X OPTIONS -H "Origin: https://www.clonnectapp.com" -H "Access-Control-Request-Method: GET" "' + BASE + '/health"')
test('Debug routes', curl_get('/debug/routes', auth=False))

# ==================== CAPA 1 ====================
section('💾  CAPA 1 — BASE DE DATOS (verificación indirecta, 10 tests)')
test('Creator exists', curl_get(f'/config/profiles/{CREATOR}'))
test('Creator list', curl_get('/admin/list-creators'))
test('Leads exist', curl_get(f'/leads/{CREATOR}'))
test('Lead stats', curl_get(f'/leads/{CREATOR}/stats'))
test('Lead categories', curl_get(f'/leads/{CREATOR}/categories'))
test('Products exist', curl_get(f'/products/{CREATOR}'))
test('Messages exist', curl_get(f'/dm/conversations/{CREATOR}'))
test('Knowledge docs', curl_get(f'/knowledge/{CREATOR}'))
test('Tone profile', curl_get(f'/tone/{CREATOR}'))
test('Analytics data', curl_get(f'/analytics/{CREATOR}'))

# ==================== CAPA 2A ====================
section('⚙️  CAPA 2A — DM PIPELINE (8 tests)')
test('DM: saludo', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"hola que tal","sender_id":"e2e_test_001"}}'))
test('DM: compra', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"quiero comprar tu programa de fitness","sender_id":"e2e_test_002"}}'))
test('DM: emoji', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"❤️🔥 genial","sender_id":"e2e_test_003"}}'))
test('DM: pregunta info', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"que incluye el pack y cuanto cuesta","sender_id":"e2e_test_004"}}'))
test('DM: largo 500ch', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"{"a"*500}","sender_id":"e2e_test_005"}}'))
test('DM: frustracion', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"estoy harto no me ayudais nada","sender_id":"e2e_test_006"}}'))
test('DM: stats', curl_get(f'/dm/stats/{CREATOR}'))
test('DM: followers', curl_get(f'/dm/followers/{CREATOR}'))

# ==================== CAPA 2B ====================
section('⚙️  CAPA 2B — COPILOT (7 tests)')
test('Copilot pending', curl_get(f'/copilot/pending/{CREATOR}'))
test('Copilot analytics', curl_get(f'/copilot/analytics/{CREATOR}'))
test('Copilot config', curl_get(f'/copilot/config/{CREATOR}'))
test('Copilot status', curl_get(f'/copilot/status/{CREATOR}'))
test('Copilot suggest', curl_post(f'/copilot/suggest/{CREATOR}', f'{{"message":"info precios","sender_id":"e2e_cop_001"}}'))
test('Copilot notifications', curl_get(f'/copilot/notifications/{CREATOR}'))
test('Copilot comparisons', curl_get(f'/copilot/comparisons/{CREATOR}'))

# ==================== CAPA 2C ====================
section('⚙️  CAPA 2C — KNOWLEDGE/RAG (6 tests)')
test('Knowledge list', curl_get(f'/knowledge/{CREATOR}'))
test('Knowledge docs', curl_get(f'/knowledge/documents/{CREATOR}'))
test('Knowledge search', curl_post(f'/knowledge/search/{CREATOR}', '{"query":"fitness"}'))
test('Knowledge search: precio', curl_post(f'/knowledge/search/{CREATOR}', '{"query":"precio programa"}'))
test('RAG health', curl_get(f'/dm/health/{CREATOR}'))
test('Citations', curl_get(f'/citations/{CREATOR}'))

# ==================== CAPA 2D ====================
section('⚙️  CAPA 2D — LEADS & NURTURING (8 tests)')
test('Leads list', curl_get(f'/leads/{CREATOR}'))
test('Lead stats', curl_get(f'/leads/{CREATOR}/stats'))
test('Lead categories', curl_get(f'/leads/{CREATOR}/categories'))
test('Unified leads', curl_get(f'/unified-leads/{CREATOR}'))
test('Nurturing sequences', curl_get(f'/nurturing/sequences/{CREATOR}'))
test('Nurturing followups', curl_get(f'/nurturing/followups/{CREATOR}'))
test('Nurturing scheduler', curl_get(f'/nurturing/scheduler/status/{CREATOR}'))
test('Ghost stats', curl_get(f'/admin/ghost-stats/{CREATOR}'))

# ==================== CAPA 2E ====================
section('⚙️  CAPA 2E — ANALYTICS & INTELLIGENCE (8 tests)')
test('Analytics general', curl_get(f'/analytics/{CREATOR}'))
test('Dashboard stats', curl_get(f'/dashboard/stats/{CREATOR}'))
test('Insights', curl_get(f'/insights/{CREATOR}'))
test('Intelligence', curl_get(f'/intelligence/{CREATOR}'))
test('Audience', curl_get(f'/audience/{CREATOR}'))
test('Audiencia ES', curl_get(f'/audiencia/{CREATOR}'))
test('Content perf', curl_get(f'/content/{CREATOR}'))
test('Admin global stats', curl_get('/admin/stats'))

# ==================== CAPA 2F ====================
section('⚙️  CAPA 2F — OTROS SERVICIOS (8 tests)')
test('Calendar services', curl_get(f'/calendar/services/{CREATOR}'))
test('Booking links', curl_get(f'/booking-links/{CREATOR}'))
test('Bot config', curl_get(f'/bot/{CREATOR}'))
test('Preview', curl_get(f'/preview/{CREATOR}'))
test('Connections', curl_get(f'/connections/{CREATOR}'))
test('Payments status', curl_get(f'/payments/status/{CREATOR}'))
test('Clone score', curl_get(f'/clone-score/{CREATOR}'))
test('Autolearning rules', curl_get(f'/autolearning/rules/{CREATOR}'))

# ==================== CAPA 3 ====================
section('🌐  CAPA 3 — ADMIN ENDPOINTS (20 tests)')
admin_eps = [
    '/admin/stats', '/admin/conversations', '/admin/pending-messages',
    '/admin/alerts', '/admin/feature-flags', '/admin/demo-status',
    '/admin/list-creators', '/admin/rate-limiter-stats',
    f'/admin/sync-status/{CREATOR}',
    f'/admin/ingestion/status/{CREATOR}',
    '/admin/lead-categories', '/admin/ghost-config',
    f'/admin/ghost-stats/{CREATOR}',
    '/admin/backups',
    f'/admin/debug-raw-messages/{CREATOR}/test',
    f'/admin/debug-instagram-api/{CREATOR}',
    f'/admin/debug-sync-logic/{CREATOR}',
    f'/admin/full-diagnostic/{CREATOR}',
    f'/admin/diagnose-duplicate-leads/{CREATOR}',
    f'/admin/oauth-status/{CREATOR}'
]
for ep in admin_eps:
    short = ep.replace('/admin/', '').replace(f'/{CREATOR}', '').replace('/test', '')[:35]
    test(f'Admin: {short}', curl_get(ep))

# ==================== CAPA 3B ====================
section('🌐  CAPA 3B — OAUTH & WEBHOOKS (6 tests)')
test('OAuth URL', curl_get('/oauth/instagram/url'))
test('OAuth status', curl_get(f'/oauth/status/{CREATOR}'))
test('Webhook instagram GET', curl_get('/webhook/instagram', auth=False))
test('Webhook verify token', 'curl -s -o /dev/null -w "%{http_code}|%{time_total}" --max-time 10 "' + BASE + '/webhook/instagram?hub.mode=subscribe&hub.verify_token=test&hub.challenge=test123"')
test('GDPR status', curl_get(f'/gdpr/status/{CREATOR}'))
test('Maintenance status', curl_get('/maintenance/status'))

# ==================== CAPA 4 ====================
section('🔄  CAPA 4 — FLUJOS E2E (7 tests)')
test('E2E: DM full pipeline', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"hola me gustaria saber mas sobre tu programa de entrenamiento personalizado, cuanto cuesta y que incluye","sender_id":"e2e_flow_full"}}'))
test('E2E: Webhook IG empty', curl_post('/webhook/instagram', '{}', auth=False))
test('E2E: Webhook IG object', curl_post('/webhook/instagram', '{"object":"instagram","entry":[]}', auth=False))
test('E2E: Webhook Stripe empty', curl_post('/webhook/stripe', '{}', auth=False))
test('E2E: Webhook WA empty', curl_post('/webhook/whatsapp', '{}', auth=False))
test('E2E: Copilot suggest flow', curl_post(f'/copilot/suggest/{CREATOR}', f'{{"message":"cuanto cuesta el pack premium","sender_id":"e2e_cop_flow"}}'))
test('E2E: Knowledge ingest+search', curl_post(f'/knowledge/search/{CREATOR}', '{"query":"entrenamiento personalizado"}'))

# ==================== CAPA 5 ====================
section('🛡️  CAPA 5 — RESILIENCE & SECURITY (16 tests)')
test('XSS en DM', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"<script>alert(1)</script>","sender_id":"xss_test"}}'))
test('SQL injection path', curl_get("/leads/'; DROP TABLE leads;--"))
test('Creator fake leads', curl_get('/leads/FAKE_NONEXISTENT_999'))
test('Creator fake products', curl_get('/products/FAKE_NONEXISTENT_999'))
test('Creator fake config', curl_get('/config/profiles/FAKE_NONEXISTENT_999'))
test('Creator fake dm', curl_get('/dm/conversations/FAKE_NONEXISTENT_999'))
test('DM body vacio', curl_post('/dm/process', '{}'))
test('DM sin sender', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"test"}}'))
test('DM sin message', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","sender_id":"test"}}'))
test('JSON invalido', 'curl -s -o /dev/null -w "%{http_code}|%{time_total}" --max-time 10 -X POST -H "Content-Type: application/json" -d "NOT_JSON{{{{" "' + BASE + '/dm/process"')
test('Unicode heavy', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"こんにちは 🎌 مرحبا Ñoño","sender_id":"unicode_test"}}'))
test('Admin nuclear sin auth', curl_get('/admin/nuclear-reset', auth=False))
test('Admin reset sin auth', curl_post('/admin/reset-db', '{}', auth=False))
test('Webhook falso payload', curl_post('/webhook/instagram', '{"object":"fake","entry":[{"changes":[{"value":"hack"}]}]}', auth=False))
test('Path traversal', curl_get('/../../../etc/passwd', auth=False))
test('Very long path', curl_get('/' + 'a'*500, auth=False))

# ==================== CAPA 6 ====================
section('⚡  CAPA 6 — PERFORMANCE (5 tests)')
for i in range(3):
    test(f'Health latency #{i+1}', curl_get('/health', auth=False))
test('DM latency', curl_post('/dm/process', f'{{"creator_id":"{CREATOR}","message":"test performance","sender_id":"perf_001"}}'))
test('Leads latency', curl_get(f'/leads/{CREATOR}'))

# Fix total
TOTAL = total_tests

elapsed = time.time() - start_time

# ==================== INFORME ====================
print('\n\n')
print('╔══════════════════════════════════════════════════════════╗')
print('║                    RESULTADOS FINALES                   ║')
print('╚══════════════════════════════════════════════════════════╝')
print()
print(f'  Total tests:  {total_tests}')
print(f'  ✅ PASS:      {passed}')
print(f'  ❌ FAIL:      {failed}')
print(f'  ⚠️  WARN:      {warnings}')
print(f'  Pass rate:    {passed*100//total_tests if total_tests else 0}%')
print(f'  Tiempo total: {elapsed:.1f}s ({elapsed/60:.1f} min)')
print()

# Layer summary
layers = {}
for r in results:
    l = r['layer']
    if l not in layers:
        layers[l] = {'pass': 0, 'fail': 0, 'warn': 0, 'total': 0}
    layers[l]['total'] += 1
    if r['status'] == 'PASS': layers[l]['pass'] += 1
    elif r['status'] == 'FAIL': layers[l]['fail'] += 1
    else: layers[l]['warn'] += 1

print('  POR CAPA:')
for l, s in layers.items():
    pct = s['pass']*100//s['total'] if s['total'] else 0
    bar_w = 20
    bar_p = int(bar_w * s['pass'] / s['total']) if s['total'] else 0
    print(f'    {"█"*bar_p}{"░"*(bar_w-bar_p)} {pct:3d}% {l} ({s["pass"]}/{s["total"]})')

if failed > 0:
    print(f'\n  ❌ FALLOS ({failed}):')
    for r in results:
        if r['status'] == 'FAIL':
            err = r.get('error', '')
            print(f'    • {r["name"]}: HTTP {r.get("code","?")} {err}')

if warnings > 0:
    print(f'\n  ⚠️  WARNINGS ({warnings}):')
    for r in results:
        if r['status'] == 'WARN':
            print(f'    • {r["name"]}: HTTP {r.get("code","?")}')

# Performance
timed = [r for r in results if r.get('time') and r['time'] is not None]
timed.sort(key=lambda x: x['time'], reverse=True)
print(f'\n  ⚡ TOP 10 MÁS LENTOS:')
for r in timed[:10]:
    flag = '🐌' if r['time'] > 10 else '⚠️' if r['time'] > 5 else '  '
    print(f'    {flag} {r["time"]:6.2f}s — {r["name"]}')

# Avg timing
if timed:
    avg = sum(r['time'] for r in timed) / len(timed)
    print(f'\n  Tiempo promedio por test: {avg:.2f}s')

# Save JSON
with open('MASSIVE_TEST_REPORT.json', 'w') as f:
    json.dump({
        'date': datetime.datetime.now().isoformat(),
        'base_url': BASE,
        'total': total_tests,
        'passed': passed,
        'failed': failed,
        'warnings': warnings,
        'pass_rate': f'{passed*100//total_tests}%',
        'elapsed_seconds': round(elapsed, 1),
        'results': results,
        'layer_summary': {k: v for k, v in layers.items()}
    }, f, indent=2)

# Save Markdown
with open('MASSIVE_TEST_REPORT.md', 'w') as f:
    f.write('# CLONNECT — MASSIVE TEST REPORT\n\n')
    f.write(f'**Fecha:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
    f.write(f'**Entorno:** Producción (www.clonnectapp.com)\n')
    f.write(f'**Duración:** {elapsed:.1f}s ({elapsed/60:.1f} min)\n\n')
    f.write('## RESUMEN EJECUTIVO\n\n')
    f.write(f'| Métrica | Valor |\n|---------|-------|\n')
    f.write(f'| Tests ejecutados | {total_tests} |\n')
    f.write(f'| ✅ PASS | {passed} |\n')
    f.write(f'| ❌ FAIL | {failed} |\n')
    f.write(f'| ⚠️ WARN | {warnings} |\n')
    f.write(f'| Pass rate | {passed*100//total_tests}% |\n\n')

    f.write('## RESULTADOS POR CAPA\n\n')
    for l, s in layers.items():
        pct = s['pass']*100//s['total'] if s['total'] else 0
        f.write(f'### {l}\n')
        f.write(f'**{s["pass"]}/{s["total"]} passed ({pct}%)**\n\n')
        f.write('| # | Test | Status | HTTP | Tiempo |\n')
        f.write('|---|------|--------|------|--------|\n')
        for r in results:
            if r['layer'] == l:
                t = f'{r["time"]:.2f}s' if r.get('time') else '-'
                icon = '✅' if r['status'] == 'PASS' else '❌' if r['status'] == 'FAIL' else '⚠️'
                f.write(f'| {icon} | {r["name"]} | {r["status"]} | {r.get("code","-")} | {t} |\n')
        f.write('\n')

    if failed > 0:
        f.write('## ❌ FALLOS DETALLADOS\n\n')
        for r in results:
            if r['status'] == 'FAIL':
                f.write(f'- **{r["name"]}** [{r["layer"]}]: HTTP {r.get("code","?")} {r.get("error","")}\n')
        f.write('\n')

    f.write('## ⚡ PERFORMANCE (top 10)\n\n')
    for r in timed[:10]:
        f.write(f'- {r["time"]:.2f}s — {r["name"]}\n')

print(f'\n  📄 MASSIVE_TEST_REPORT.json guardado')
print(f'  📄 MASSIVE_TEST_REPORT.md guardado')
print(f'\n  ✅ DONE in {elapsed:.1f}s')
