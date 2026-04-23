# SendGuard Phase 5 — Decisions & deferred work

**Branch:** `forensic/send-guard-20260423`
**Fecha:** 2026-04-23
**Scope:** hardening del sistema `send_guard` (ver `01_description.md` para descripción general y `03_bugs.md` para el catálogo de 15 bugs).

Este doc fija **decisiones arquitectónicas** tomadas en Phase 5 y registra qué
trabajo queda **fuera del scope** (para evitar alcance creep y documentar el
compromiso con el usuario).

---

## 1. Decisiones adoptadas

| # | Decisión | Fuente validadora | Implementación |
|---|----------|-------------------|----------------|
| D1 | `SendDecision` dataclass (Allowed \| Blocked) con `decision_id` UUID y `rule` literal | Luke Plant + Advisor360° Decision Gateway + Ezyang ADTs | `core/send_guard_decision.py` (nuevo) |
| D2 | `check_send_permission_async` vía `asyncio.to_thread` (no AsyncSession nativa) | Casbin `AsyncEnforcer` pattern + FastAPI SQLAlchemy pool guidance | `core/send_guard.py` L~210 |
| D3 | `SEND_GUARD_AUDIT_ONLY` env var (default `"false"`) para shadow mode | Istio `istio.io/dry-run` pattern | `core/send_guard.py::_shadow_mode_enabled` |
| D4 | `.one_or_none()` + `UNIQUE(creators.name)` constraint vía Alembic 050 | AWS multi-tenant PG + Logto caveat (safe read path) | `alembic/versions/050_send_guard_hardening.py` |
| D5 | Logs estructurados con `extra={"send_guard": {...}}` (decision_id, creator_id, caller, rule, reason, latency_ms) | TCPA 2025 (4-year retention) + OPA decision log | `core/send_guard.py::_emit_log` |
| D6 | 4 métricas Prometheus: `send_guard_decision_total`, `send_guard_bypass_detected_total`, `send_guard_shadow_blocked_total`, `send_guard_latency_seconds` | OPA + Istio `authz_dry_run_action` | `core/observability/metrics.py` bloque nuevo |
| D7 | Fail-closed ante cualquier excepción del módulo (pool exhaustion, ImportError, duplicados) → `SendBlocked` con `rule="R5"` | Cerbos "never single point of failure" + AuthZed "unexpected result as denial" | `core/send_guard.py::_fail_closed` |
| D8 | `caller` kwarg **obligatorio** (no default) | BUG-13 | Firma `check_send_permission(creator_id, *, approved=False, caller)` |
| D9 | `check_send_permission` sigue `raise SendBlocked` (compat con 6 callsites existentes) pero reutiliza el nuevo `_evaluate()` como backbone | Compromiso P3 Luke Plant (exceptions + sum types coexisten) | Ambas APIs en `core/send_guard.py` |
| D10 | `SendGuard` class (dead code L83-87 legacy) eliminada | BUG-15 | Removido en Phase 5 |
| D11 | Copilot multiplex propaga `approved` downstream en vez de hardcodear `True` | BUG-10 + TCPA 10-day revocation | `core/copilot/messaging.py:167` |
| D12 | Retry queue pasa `approved=False` para que el guard re-valide flags actuales | BUG-09 + TCPA 10-day revocation | `services/meta_retry_queue.py:184` |
| D13 | 4 bypass paths instrumentados con guard explícito (BUG-01/05/07/08) | Phase 3 + P5 Decision Gateway | 4 callsites nuevos con `caller="..."` |
| D14 | Backfill `copilot_mode` NULL → TRUE antes de aplicar NOT NULL | BUG-03 + conservador | Alembic 050 upgrade() |

---

## 2. Patrones industriales NO adoptados

| Patrón | Por qué se rechazó | Fuente |
|--------|---------------------|--------|
| Fail-open con ventana de 48h si el guard falla | Constraint explícito: apagar el guard = incidente legal | AuthZed/Sivo |
| Caché TTL local de decisiones | Race window adicional, scope Phase 5 limitado, valor marginal dado que R1 (approved) ya es O(0) DB | Cerbos |
| Motor OPA/Cerbos externo como servicio | 2 reglas no justifican stack adicional + sidecar ops | OPA/Cerbos OSS |
| Row-Level Security multi-tenant en `creators` | Clonnect es single-tenant-per-creator; RLS es una complejidad sin beneficio | AWS multi-tenant |
| Decision Gateway full MCP-style | 1 regla × 6 adapters no justifica gateway refactor; el guard ya **es** el único chokepoint | Advisor360° |

---

## 3. Fuera de scope (deferred work)

### Q2-2026 candidates

| # | Trabajo | Razón diferido | Precondición |
|---|---------|----------------|--------------|
| DEF-1 | Migrar callsites sync → async usando `check_send_permission_async` | Validar async-first en staging primero; 6 callsites requieren auditoría de cada `async def` context | Phase 5 debe estar en main 2 semanas sin regresiones |
| DEF-2 | Refactor estructural `whatsapp_webhook.py` autopilot (unificar con C4) | Scope Phase 5 limitado a añadir guard; el refactor full es un hotfix separado | Hotfix en branch aparte cuando se confirme volumen de blocks |
| DEF-3 | Migrar los 6 callsites a `SendDecision` (uso de Allowed/Blocked en lugar de try/except) | Compat con código existente; migración gradual evita regresiones | Tests completos + adopt on new callsites primero |
| DEF-4 | Native `AsyncSession` de SQLAlchemy 2.x | Requiere cambios en `api/database.py` que están restringidos por CLAUDE.md | User approval + benchmark que confirme beneficio vs complejidad |
| DEF-5 | Durable audit log externo (e.g. ship logs a BigQuery/S3) | TCPA 4-year retention requiere storage persistente — Railway stdout no cumple | Decisión arquitectónica de dónde almacenar logs compliance |
| DEF-6 | Alert en `send_guard_decision_total{decision="blocked"}` spike | Después de tener baseline de volumen en producción | Baseline de 14 días post-deploy |

### No-goals explícitos

- **NO se apaga el guard nunca** (constraint legal; solo `SEND_GUARD_AUDIT_ONLY` permite shadow, que aún evalúa y loggea).
- **NO se toca** `core/instagram_modules/webhook.py`, `api/routers/oauth/instagram.py`, `core/task_scheduler.py` (warning CLAUDE.md).
- **NO se aplica** la migración 050 en Railway desde este PR (correrá manualmente en staging primero). El PR incluye el archivo Alembic pero el deploy no lo aplica hasta decisión explícita.

---

## 4. Validación

### Tests añadidos

- `backend/tests/test_send_guard.py` — **33 tests, 100% pass** (target original 25+).
  - 9 unit_rules (R1..R5 + BUG-03 + BUG-13 + BUG-14)
  - 3 unit_async (R1/R2 + event-loop non-blocking)
  - 6 unit_decision (Allowed/Blocked contract + R5 DB-fail)
  - 2 unit_shadow (enforce default + AUDIT_ONLY pass)
  - 3 callsites_contract (grep-level assertions)
  - 4 bypass_regression (B1..B4)
  - 2 trust_propagation (BUG-09, BUG-10)
  - 1 tenant_isolation (BUG-02 duplicate Creator.name)
  - 3 symmetry (SendDecision sum type + frozen + dead-code removed)

### Backward compat

- Los 6 callsites productivos **no requieren cambios** para seguir funcionando
  (todos pasan `caller=` como kwarg explícito ya). El cambio a keyword-only
  (`*, approved, caller`) es compatible.

### Safety-critical preservada

- R1 (approved) sigue siendo short-circuit.
- R2 (no creator) sigue bloqueando.
- R3 ahora es estrictamente `copilot_mode is False AND autopilot_premium_enabled is True`
  (**más estricto**, no menos — corrige BUG-03).
- R4 (default) sigue bloqueando.
- R5 (nuevo) añade cobertura fail-closed para excepciones internas que antes
  propagaban y eran tratadas inconsistentemente por los callsites.

### Shadow mode seguridad

- `SEND_GUARD_AUDIT_ONLY=true` solo se activa vía env var. Default `"false"`.
- En shadow mode el guard evalúa, loggea, emite métrica `send_guard_shadow_blocked_total`,
  y retorna True (no raise). Ningún callsite ve diferencia funcional — pero
  operaciones pueden observar en Grafana cuántos blocks habría habido.
- **No es una "kill-switch"**: incluso en shadow mode el log `critical` se emite.

---

## 5. Archivos modificados (diff summary)

| Archivo | LOC final | Δ git | Tipo |
|---------|-----------|-------|------|
| `core/send_guard.py` | 307 | +312 / -58 | refactor (R1-R5 + async + shadow + JSON logs + metrics, kill dead class) |
| `core/send_guard_decision.py` | 119 | new | SendDecision sum type + `check_send_decision[_async]` |
| `core/observability/metrics.py` | 290 | +18 | 4 specs registered |
| `core/copilot/messaging.py` | 401 | +21 / -1 | propagate approved (BUG-10) |
| `core/whatsapp/handler.py` | 486 | +13 | send_template guard (BUG-07) |
| `core/instagram_modules/message_sender.py` | 134 | +16 / -2 | send_message_with_buttons guard (BUG-08) |
| `api/routers/messaging_webhooks/whatsapp_webhook.py` | 377 | +23 | autopilot guard (BUG-01 CRITICAL) |
| `api/routers/dm/processing.py` | 346 | +25 / -1 | manual WA Cloud guard (BUG-05) |
| `services/meta_retry_queue.py` | 229 | +10 / -1 | approved=True → approved=False (BUG-09) |
| `alembic/versions/050_send_guard_hardening.py` | 84 | new | migration: UNIQUE + copilot_mode NOT NULL |
| `tests/test_send_guard.py` | 538 | new | 33 tests, 100% pass |

**Git diff stat**: 8 modified + 3 new files — 376 insertions, 62 deletions for existing files.
All modified files respect the 500-LOC constraint (largest: `whatsapp/handler.py` at 486).
