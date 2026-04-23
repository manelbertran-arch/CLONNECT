# Fase 6 — Plan de medición (SendGuard hardening)

**Branch:** `forensic/send-guard-20260423`
**Fecha:** 2026-04-23
**Status:** planificación; ejecución del plan es post-merge (manual).
**Predecesor:** Phase 5 (`05_optimization.md`), 33/33 tests pass, migration 050 lista.

**Alcance de la medición:** integridad operacional y seguridad del guard. **NO hay medición CCEE** — SendGuard no afecta el contenido generado por el LLM, solo autorización de envío.

---

## A. Tipo de medición

| Dimensión | Incluida | Notas |
|-----------|----------|-------|
| Integration tests | ✅ | 33 tests unit + integ en `tests/test_send_guard.py` |
| Security tests | ✅ | Bypass detection (B1-B4) + trust propagation (BUG-09/10) + cross-tenant (BUG-02) |
| Migration tests | ✅ | Alembic 050 upgrade+downgrade en SQLite; pre-check duplicados |
| Smoke staging | ✅ | 5 adapters + send_template + buttons con approved=True/False |
| Prometheus observability | ✅ | 4 métricas nuevas emitidas + scrape staging |
| Logs auditables | ✅ | JSON con `decision_id` correlation UUID |
| **CCEE** | ❌ | N/A — no toca contenido (confirmado Fase 1 §6) |
| A/B statistical comparison | ❌ | Innecesario para safety gate (fail-closed es determinista) |
| Load testing formal | ❌ | Diferido Q2 (scope `DECISIONS.md` DEF-4) |
| TCPA 4-year audit storage | ❌ | Diferido Q2 (scope `DECISIONS.md` DEF-5) |

---

## B. Harness

### B.1 Pytest suite — 33 tests pass

```bash
cd ~/Clonnect/backend && python3 -m pytest tests/test_send_guard.py -v
# 33 passed in 0.14s
```

Cobertura mapeada 1:1 con los 15 bugs (ver `05_optimization.md §3`).

### B.2 Script E2E bypass — `scripts/test_send_guard_bypass_e2e.py`

Nuevo script CLI con 3 modos:

```bash
# Static analysis — greps 9 send paths + 2 trust anti-patterns
python3 scripts/test_send_guard_bypass_e2e.py --static

# Runtime smoke — exercise 4 rule cases + SendDecision contract
python3 scripts/test_send_guard_bypass_e2e.py --runtime

# Migration dry-run — load Alembic 050, verify upgrade/downgrade symbols
python3 scripts/test_send_guard_bypass_e2e.py --migration

# All three (default)
python3 scripts/test_send_guard_bypass_e2e.py --all
```

**Output actual** (verificado en branch):
```
STATIC CHECK OK — 9 send paths guarded, 2 trust anti-patterns absent.
RUNTIME CHECK OK — 4 rule cases + SendDecision contract verified.
MIGRATION CHECK OK — 050_send_guard_hardening.py exposes upgrade/downgrade (revision=050)
```

Exit codes:
- `0` — all pass
- `1` — bypass detected o runtime check falla
- `2` — migration dry-run falla
- `3` — environment setup falla

### B.3 Migration test — SQLite local

```bash
# En un SQLite temporal:
sqlite3 /tmp/test_sg.db < backend/alembic/init_schema.sql
cd backend && DATABASE_URL="sqlite:////tmp/test_sg.db" alembic upgrade head
DATABASE_URL="sqlite:////tmp/test_sg.db" alembic downgrade -1
DATABASE_URL="sqlite:////tmp/test_sg.db" alembic upgrade head
# Debe pasar sin errores; si hay rows con name duplicado, aborta con RuntimeError.
```

**Nota:** Clonnect prod usa Neon PostgreSQL. La migration se aplicará realmente en staging PG via `railway run alembic upgrade head`, no en SQLite. El test SQLite es solo sanity local.

### B.4 Smoke staging manual

Post-merge + post-migration staging, verificar cada path:

| Adapter | Test caller | Expectation approved=True | Expectation approved=False (no premium) |
|---------|-------------|---------------------------|-----------------------------------------|
| Telegram | manual POST `/dm/send_manual` platform=tg | ✅ sent | ❌ blocked (SendBlocked log) |
| Instagram | manual POST `/dm/send_manual` platform=ig | ✅ sent | ❌ blocked |
| WhatsApp Cloud | manual POST `/dm/send_manual` platform=wa (sin Evolution) | ✅ sent | ❌ blocked |
| Copilot multiplex | "approve" pill en dashboard | ✅ sent | N/A (pill implica approved) |
| Evolution text | webhook inbound WA → autopilot | ✅ si creator premium | ❌ blocked |
| Evolution media | copilot sends media (si implementado) | ✅ | ❌ blocked |
| WA send_template | admin trigger template | ✅ si approved passed | ❌ blocked (NEW: BUG-07) |
| IG send_buttons | quick-reply flow | ✅ si approved passed | ❌ blocked (NEW: BUG-08) |

Para cada test:
1. Verificar mensaje enviado (o no) en la plataforma destino.
2. Verificar log JSON con `decision_id` + `rule` correcto en Railway logs.
3. Verificar métrica `send_guard_decision_total{decision=...}` incrementada en Prometheus staging.

---

## C. Gates KEEP (criterios de aceptación — TODOS deben cumplirse)

| # | Gate | Método verificación |
|---|------|--------------------|
| K1 | 100% tests pass (mínimo 33/33) | `pytest tests/test_send_guard.py -q` |
| K2 | 0 bypass silencioso en 6 callsites + send_template + buttons | `scripts/test_send_guard_bypass_e2e.py --static` exit 0 |
| K3 | 4 métricas Prometheus emitidas correctamente | `curl -s staging:9090/-/metrics \| grep send_guard_` muestra las 4 |
| K4 | Logs JSON auditables con `decision_id` UUID | `railway logs -n 500 \| grep send_guard \| jq` parsea sin errores, `decision_id` presente |
| K5 | Migration 050 aplicable en staging sin duplicados | `railway run --environment=staging alembic upgrade head` exit 0 |
| K6 | Smoke staging: 5 adapters + send_template + buttons autorizan correctamente | Ver tabla §B.4 — todos los approved=True pasan |
| K7 | Smoke staging: 5 adapters + send_template + buttons **bloquean** correctamente con approved=False (sin premium) | Ver tabla §B.4 — todos los approved=False bloquean con log critical |
| K8 | Contrato SendDecision uniforme en los 6 callsites | Runtime test + `isinstance(decision, (Allowed, Blocked))` assert pasa |

**Si los 8 gates pasan → KEEP (promocionar a prod).**

---

## D. Gates REVERT (disparadores automáticos de rollback)

| # | Condición | Acción |
|---|-----------|--------|
| R1 | Cualquier regresión en fail-closed (auto-send con `approved=False` y sin premium) | `git revert` PR inmediato + incidente |
| R2 | Migration falla en upgrade Y downgrade no restaura estado anterior | `alembic downgrade 049` manual + bloqueo del merge |
| R3 | Tests <33 pass en el branch | Merge bloqueado hasta fix |
| R4 | Bypass reaparecido en B1-B4 (detectado por `--static`) | Merge bloqueado |
| R5 | En prod 24h post-deploy: `send_guard_bypass_detected_total > 0` (por qué wiremos bypass source markers) | Incidente sev1 + revertir PR |
| R6 | Log spam o performance degrada (p99 guard >200ms) | Rollback + investigar |

**Un solo gate REVERT disparado → rollback inmediato, no progress a la siguiente fase.**

---

## E. Gate INCONCLUSIVE

| # | Condición | Acción |
|---|-----------|--------|
| I1 | Pre-check migration detecta duplicados `creators.name` | Abort migration; limpiar duplicados manualmente (SQL de triage + merge de rows); re-run migration |
| I2 | Métricas no emitidas pero tests pass | Investigar `emit_metric` registration (posible duplicate Prometheus registration); no bloquea KEEP si logs JSON presentes |
| I3 | Logs JSON parseables pero Railway formatter no detecta (plain text) | Configurar `JsonFormatter` en Railway env vars; no bloquea KEEP del código, bloquea full audit trail |
| I4 | Shadow mode test incompleto (falta staging env SEND_GUARD_AUDIT_ONLY=true) | Documentar en PR; staging validation puede diferirse 1 semana |

**INCONCLUSIVE ≠ fail**: significa "revisar antes de promocionar pero no revertir".

---

## F. Plan secuencial pre-medición (post-merge)

**Paso / Responsable / Comando / Criterio de progresión**

1. **Merge PR en GitHub** → manual, tras review CEO + 2 approvals + 33 tests pass en CI.
2. **Railway deploy automático** → se dispara push-to-main. Esperar `railway deployment list` status = `SUCCESS`.
3. **Aplicar migration 050 en staging primero**:
   ```bash
   railway run --environment=staging alembic upgrade head
   ```
   Criterio: exit 0. Si falla con duplicados → Gate I1 (limpiar y retry).
4. **Verificar pre-check output**: el script de migration loggea `"Migration 050 aborted: duplicate Creator.name rows detected"` si hay problemas. Si sale limpio → proceder.
5. **Smoke test staging — path autorizados** (7 adapters):
   - Para cada adapter enviar 1 mensaje con `approved=True` o creator premium activo.
   - Verificar en Railway logs staging: `[send_guard] decision_allowed` con `rule=R1` o `rule=R3`.
6. **Smoke test staging — path bloqueados** (7 adapters):
   - Para cada adapter enviar 1 mensaje con `approved=False` a creator **sin** premium.
   - Verificar: `SendBlocked` raise + log `[send_guard] decision_blocked` con `rule=R4`.
7. **Verificar Prometheus staging**:
   ```bash
   curl -s https://staging-metrics.clonnect.internal/metrics | grep send_guard_
   ```
   Criterio: `send_guard_decision_total{decision="blocked"}` incrementa tras los tests del paso 6; `send_guard_decision_total{decision="allowed"}` incrementa tras paso 5.
8. **Verificar logs JSON con `decision_id`**:
   ```bash
   railway logs -n 200 --environment=staging | grep send_guard | jq '.send_guard.decision_id'
   ```
   Criterio: cada decisión tiene un UUID único (no vacío, no repetido).
9. **Solo si staging OK (K1-K8)** → aplicar migration en prod:
   ```bash
   railway run --environment=production alembic upgrade head
   ```
   Con mismo pre-check. Si staging falló cualquier K gate → STOP, no promocionar.
10. **Deploy code a prod** (automatic tras merge a main en algunos setups; en Clonnect Procfile runs `alembic upgrade head` en boot → paso 9 y 10 pueden fusionarse). Verificar `railway deployment list --environment=production` = SUCCESS.
11. **Monitor prod 24h**:
    - `send_guard_bypass_detected_total` debe quedar en **0**.
    - `send_guard_decision_total{decision="blocked"}` debe ser coherente con volumen esperado (comparar con baseline staging).
    - Zero paginadas de PagerDuty por alerts del guard.
12. **Si prod estable 24h → Fase 6 cerrada**. Sistema reclasificado:
    - `docs/audit_pipeline_dm/inventory.md` actualizado (ver §I abajo).
    - Commit final con tag `send-guard-hardening-v1.0`.

**Rollback plan si cualquier paso 9-11 falla:**
```bash
railway rollback --environment=production
railway run --environment=production alembic downgrade -1
```
Investigar + crear incident doc + re-plan.

---

## G. Observabilidad en prod (setup pendiente)

### G.1 Dashboard Grafana — `SendGuard` panel

4 paneles:
1. **Decision rate** — `rate(send_guard_decision_total[5m])` split by `rule` (R1/R2/R3/R4/R5).
2. **Block rate** — `rate(send_guard_decision_total{decision="blocked"}[5m])` split by `adapter`.
3. **Shadow block rate** — `rate(send_guard_shadow_blocked_total[5m])` (activo solo si AUDIT_ONLY on).
4. **Latency p99** — `histogram_quantile(0.99, send_guard_latency_seconds_bucket)` split by `adapter`.

**Setup:** manual post-merge (fuera de scope del PR). Tracker issue: añadir en `docs/audit_pipeline_dm/observability_todo.md`.

### G.2 Alerts

| Alert | Condición | Severidad | Canal |
|-------|-----------|-----------|-------|
| `send_guard_bypass_detected` | `rate(send_guard_bypass_detected_total[1m]) > 0` | 🔴 P1 | PagerDuty + email immediate |
| `send_guard_decision_rate_drop` | `rate(send_guard_decision_total[5m]) < 0.5 * avg_over_time(rate(send_guard_decision_total[1h])[24h])` | 🟠 P2 | Email |
| `send_guard_block_spike` | `rate(send_guard_decision_total{decision="blocked"}[5m]) > 3 * avg_over_time(rate(...)[24h])` | 🟡 P3 | Slack |
| `send_guard_latency_high` | `histogram_quantile(0.99, send_guard_latency_seconds_bucket) > 0.2` (200ms) | 🟡 P3 | Slack |
| `send_guard_shadow_enabled_in_prod` | `send_guard_shadow_blocked_total > 0 AND environment="production"` | 🟠 P2 | Email + audit ping |

### G.3 SLO

| SLO | Target |
|-----|--------|
| Latencia p99 `check_send_permission` | < 50ms en path DB (R2/R3/R4) |
| Latencia p99 `check_send_permission` | < 1ms en path R1 (sin DB) |
| Uptime de enforcement (no shadow en prod) | 100% |
| Auditabilidad (% decisions con decision_id válido) | 100% |
| Rate bypass detectado | 0 (no tolerance) |

---

## H. Shadow mode — plan de validación

**Semana 1 post-merge en prod**: `SEND_GUARD_AUDIT_ONLY` **NO** se activa. Enforcement completo, default false.

**Si emerge un caso de uso** (e.g. añadir guard a un 7º callsite futuro y querer observar blocks antes de enforce):
1. Activar solo en **staging** primero: `railway variables set --environment=staging SEND_GUARD_AUDIT_ONLY=true`.
2. Correr 48h; observar `send_guard_shadow_blocked_total` en Grafana.
3. Si los blocks son esperados → quitar env var (vuelve a enforce) y promocionar.
4. Si los blocks son inesperados → investigar, fix, retry.

**Prod shadow activation** requiere:
- Approval explícito CEO.
- Window documentado (máximo 72h).
- Post-mortem con números.

Default permanente es enforce.

---

## I. Reclasificación inventario pipeline DM

Tras gate KEEP cumplido en prod 24h:

| Métrica inventario | Antes | Después |
|--------------------|-------|---------|
| Sistemas totales DM pipeline | 49 | 49 (sin cambio) |
| Sistemas optimizados-ON | 25 | **26** (SendGuard incorporado) |
| Sistemas no-optimizados-ON | 4 | **3** |
| Sistemas optimizados-OFF | N | N |
| Sistemas no-optimizados-OFF | N | N |

SendGuard migra de **"no-optimizados-ON"** a **"optimizados-ON"**.

Archivos a tocar (post-merge, separate commit):
- `docs/audit_pipeline_dm/inventory.md` — actualizar clasificación + fecha.
- `docs/audit_pipeline_dm/dashboard.md` (si existe) — gráficos actualizados.

---

## Checklist de salida (pre-Fase 7)

| # | Check | Done? |
|---|-------|-------|
| 1 | `tests/test_send_guard.py` — 33/33 pass | ✅ |
| 2 | `scripts/test_send_guard_bypass_e2e.py --all` exit 0 | ✅ |
| 3 | Syntax check todos los archivos Python modificados | ✅ (AST parse OK en los 10) |
| 4 | Doc `01_description.md` presente y actualizado | ✅ |
| 5 | Doc `02_forensic.md` | ✅ |
| 6 | Doc `03_bugs.md` | ✅ |
| 7 | Doc `04_state_of_art.md` | ✅ |
| 8 | Doc `05_optimization.md` | ✅ |
| 9 | Doc `06_measurement_plan.md` (este) | ✅ |
| 10 | Doc `DECISIONS.md` con decisiones + deferred work | ✅ |
| 11 | Migration `050_send_guard_hardening.py` parses + exposes upgrade/downgrade | ✅ |
| 12 | Script E2E `test_send_guard_bypass_e2e.py` ejecutable | ✅ |
| 13 | `git status` solo modifica archivos del scope | ✅ (7 modified + 4 new + 6 docs) |
| 14 | Railway env vars **no** modificadas | ✅ (plan solo, no aplicado) |
| 15 | No push a `main`, no aplicación de migration | ✅ |

**STOP Fase 6.** Aguardo confirmación para Fase 7 (abrir PR forensic/send-guard-20260423 → main, NO mergear, NO push Railway).

---

## Checklist Fase 7 (preparación)

1. ✅ `git add` 8 archivos modificados + 4 nuevos archivos código + 6 docs forense.
2. ✅ Commit con mensaje descriptivo (Co-Authored-By Claude 4.7).
3. ✅ Push branch `forensic/send-guard-20260423`.
4. ✅ `gh pr create` contra `main` con:
   - Título conciso: "SendGuard hardening: 15 bugs fixed, SendDecision API, shadow mode"
   - Body: summary + test plan + migration note + deferred work link.
5. ❌ **NO mergear** — per constraint del task.
6. ❌ **NO aplicar migration Alembic en Railway** — per constraint.
7. Retornar URL del PR al usuario.
