# Fase 4 — Papers, blogs técnicos y repos OSS (state of the art 2024-2026)

**Fecha:** 2026-04-23
**Branch:** `forensic/send-guard-20260423`
**Scope:** evidencia externa para decisiones técnicas de Phase 5 (SendDecision, async, AUDIT_ONLY, UNIQUE constraint, audit logging, fail-closed tradeoffs).
**Criterio de selección:** prioridad a production-engineering blogs aplicados y repos con track record (>500 stars, activos en últimos 6 meses) sobre papers teóricos.

---

## 1. Fuentes seleccionadas

### 1.1 Papers / blogs técnicos (5)

| # | Fuente | Publicación | Año | Scope principal | URL |
|---|--------|-------------|-----|-----------------|-----|
| P1 | **Patterns of Failure in Modern Authorization** — Cerbos Engineering Blog | Cerbos.dev (OWASP Snowfroc '25 + API Days AuthCon '25) | 2025 | Fallback, caching, decisión en presencia de fallo | [cerbos.dev](https://www.cerbos.dev/blog/authorization-failure-patterns) |
| P2 | **Understanding "Failed Open" and "Fail Closed" in Software Engineering** — AuthZed | AuthZed Blog (SpiceDB maintainers) | 2025 | Fail-closed como default para authz security-paramount | [authzed.com](https://authzed.com/blog/fail-open) |
| P3 | **Raising exceptions or returning error objects in Python** — Luke Plant | lukeplant.me.uk | 2024 | `str \| VerifyFailed \| VerifyExpired` pattern (sum types) | [lukeplant.me.uk](https://lukeplant.me.uk/blog/posts/raising-exceptions-or-returning-error-objects-in-python/) |
| P4 | **TCPA Compliance in 2025: A Complete Guide** — Secure Privacy | secureprivacy.ai | 2025 | Audit log retention 4 years, consent record fields | [secureprivacy.ai](https://secureprivacy.ai/blog/telephone-consumer-protection-act-compliance-tcpa-2025-full-guide) |
| P5 | **Designing Authorization for Production AI Agents: The Decision Gateway Pattern** — V. Peri, Advisor360° | Medium | 2025 | Gateway como chokepoint único, allowlist, "tool unavailable" structured response | [medium.com](https://medium.com/advisor360-com/designing-authorization-for-production-ai-agents-the-decision-gateway-pattern-59582093ccb8) |

### 1.2 Repos OSS (3) — todos >500 stars, releases recientes

| # | Repo | Stars | Último release | Relevancia | URL |
|---|------|-------|----------------|------------|-----|
| R1 | **open-policy-agent/opa** | 11.6k | v1.15.2 (2026-04-08) | Referencia industrial para policy engine + decision logs + audit | [github.com/open-policy-agent/opa](https://github.com/open-policy-agent/opa) |
| R2 | **cerbos/cerbos** (core) + `cerbos-sdk-python` | 4.3k (core) | 2026 active | Python SDK con async + non-async modes; `is_allowed` / `plan_resources` API uniforme | [github.com/cerbos/cerbos](https://github.com/cerbos/cerbos) |
| R3 | **casbin/pycasbin** + **pycasbin/fastapi-authz** | 1.8k (pycasbin core) | Async support desde 1.23.0 | Precedente para migración sync → async (`AsyncEnforcer`) manteniendo la API sync | [github.com/casbin/pycasbin](https://github.com/casbin/pycasbin) |

**También consultados** (no incluidos como fuentes principales pero citados):
- Istio dry-run annotation docs ([istio.io/latest/docs/tasks/security/authorization/authz-dry-run](https://istio.io/latest/docs/tasks/security/authorization/authz-dry-run/))
- AWS Multi-tenant PostgreSQL prescriptive guidance ([AWS SaaS docs](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/welcome.html))
- Ezyang *Idiomatic algebraic data types in Python with dataclasses and Union* (2020, aún canónico)

---

## 2. Tabla aplicable: fuente → hallazgo → bug validado/refutado → cita textual

| Fuente | Hallazgo aplicable a Phase 5 | Bugs afectados | Cita textual (<15 palabras) |
|--------|------------------------------|---------------|---------------------------|
| **Istio dry-run** | Anotación `istio.io/dry-run: "true"` + log `shadow denied, matched policy [name]` + métrica Prometheus `authz_dry_run_action` | **valida SEND_GUARD_AUDIT_ONLY flag + métrica Prometheus** (plan Fase 5 completo) | "shadow denied, matched policy ns[foo]-policy[deny-path-headers]-rule[0]" |
| **Istio dry-run** | "Dry-run allows understanding the effect of an authorization policy before applying it to production traffic" | **valida default=false** para AUDIT_ONLY (enforce es el default; shadow es opt-in) | "test an authorization policy with real production traffic without enforcing it" |
| **P1 Cerbos** | "Local caching of authorization decisions, fallback policies for when central services are unavailable" | **matiza BUG-04** (pool exhaustion): la recomendación industria es caching + fallback, no solo async — considerar añadir un local cache TTL de decisiones para reducir load | "local caching of authorization decisions, fallback policies" |
| **P1 Cerbos** | "Conservative default-deny policies" + "authorization never becomes a single point of failure" | **valida fail-closed de send_guard** (correcto por diseño); refuerza rechazar cualquier propuesta fail-open | "conservative default deny policies" |
| **P2 AuthZed** | "A fail-closed state ensures that, in the event of an error, access is denied" | **valida** que `SendBlocked` en presencia de excepción DB es correcto; **refuta** añadir retry/fallback que permita envío si el guard falla | "fail-closed state ensures...access is denied, maintaining the integrity" |
| **P2 AuthZed** | "Fail-closed is preferred in scenarios where security is paramount, such as...sensitive data handling" | **valida BUG-04 fix Opción B** (async sin fail-open): si pool se exhausta, bloquear es correcto | "preferred in scenarios where security is paramount" |
| **P2 AuthZed + Sivo** | Hybrid approach: "allow fail-open for 48h window, then hard shutdown if unresolved" | **NO aplicable a send_guard** (apagarlo = incidente legal por diseño); documentar en DECISIONS.md que no se adopta | "allow fail-open behavior for a limited window (say, 48 hours)" — rechazada |
| **P3 Luke Plant** | Pattern `def email_from_token(...) -> str \| VerifyFailed \| VerifyExpired` con mypy exhaustiveness | **valida BUG-11 fix `SendDecision` dataclass**; refuta alternativa "solo boolean" | "type signature...str \| VerifyFailed \| VerifyExpired" |
| **P3 Luke Plant** | "Those objects can't be accidentally converted into success values" | **valida BUG-11**: C1/C2/C4 `return False` es ambiguo con fallos network; SendDecision es "differently shaped" | "can't be accidentally converted into success values" |
| **P3 Luke Plant** | "Raise exceptions...immediately forcing calling code into...try/except dance" | **refuta mantener `raise SendBlocked` como único mecanismo**; valida **combinación** exc + dataclass (raise en capa de policy, wrap en dataclass en capa de adapter) | "forcing the calling code into a special control flow structure" |
| **P4 TCPA 2025** | "Businesses must keep detailed logs of when, how, and from where consent was given" con timestamp + IP | **valida BUG-06 fix** (logs JSON estructurados con campos `creator_id`, `caller`, `decision`, `reason`, `timestamp`) | "detailed logs of when, how, and from where consent was given" |
| **P4 TCPA 2025** | "Consent records stored for at least four years to prove compliance" | **valida retention policy** para logs del guard (recomendación: ship a durable audit log, no solo Railway stdout) | "Store consent records for at least four years" |
| **P4 TCPA 2025** | "Businesses generally must honor revocations within 10 business days" (desde 2025-04-11) | **valida BUG-09/10 fix**: retry queue + multiplexer NO deben hardcodear `approved=True` (revocación must be honored en retry) | "must honor revocations within 10 business days" |
| **P4 TCPA 2025** | "FCC one-to-one consent rule: each brand must independently collect and verify consent" (vacated 2025 pero concept vive) | **valida criticidad BUG-02** (cross-tenant leak): un creator NO puede heredar consent de otro "homónimo" | "each brand must independently collect and verify consent" |
| **P5 Decision Gateway Pattern** | "Single chokepoint for all agent-tool interactions where you can enforce authentication and authorization...create detailed audit logs in one place" | **valida la tesis central de send_guard** (un solo punto que todos los envíos atraviesan); **valida BUG-01/05/07/08 fix** (eliminar paths paralelos) | "single chokepoint for all agent-tool interactions" |
| **P5 Decision Gateway Pattern** | "Structured 'tool unavailable' response that makes the failure explicit but safe" | **valida BUG-11 `SendDecision`**: cada bloqueo emite estructura clara con `blocked=True` + `reason` | "structured 'tool unavailable' response...explicit but safe" |
| **R1 OPA** | Decision log estructurado + `decision_id` + policy version en cada evaluación | **valida BUG-06**: el log debe incluir `decision_id` (uuid por llamada) + `rule_applied` (R1/R2/R3/R4) para trazabilidad | — (implementado en código OPA) |
| **R2 Cerbos Python SDK** | SDK expone `is_allowed` (single check) + `plan_resources` (query plan) tanto en modo async como sync | **valida BUG-04 fix Opción B**: exponer `check_send_permission_async` junto con `check_send_permission`. Mantener backward compat | "async and non-async modes" |
| **R2 Cerbos Python SDK** | Métodos retornan decision object, no exception → pattern `decision.is_allowed` | **refuerza BUG-11**: el contrato moderno es "decision object", no "raise". Migrar callsites | — |
| **R3 Casbin PyCasbin** | "Async is now supported by Pycasbin >= 1.23.0" con `AsyncEnforcer` paralela al Enforcer sync | **valida BUG-04 estrategia de migración** (async-first canonical + sync wrapper) sin forzar breaking change en callsites existentes | "Async is now supported by Pycasbin >= 1.23.0" |
| **Ezyang (canónico 2020)** | "Combine dataclasses into algebraic data types (ADTs) using Union types, isinstance for pattern matching" + `assert_never` mypy exhaustiveness | **valida BUG-11**: `SendDecision = Allowed \| Blocked` como Union de dataclasses frozen | "combine them into algebraic data types...using Union types" |
| **AWS multi-tenant postgres** | Shared-table con `tenant_id` column NO implica name unique; recomienda Row-Level Security (RLS) + UNIQUE composite (`tenant_id`, `name`) | **matiza BUG-02 fix**: si Clonnect fuera multi-org, la UNIQUE debería ser `(tenant_id, name)`; como es single-tenant-per-row, `UNIQUE(name)` es suficiente | "single database and schema...tenant identifier column such as tenant_id" |
| **Logto multi-tenant blog** | "Integrity constraint errors are not suppressed by RLS...can leak existence of record" | **matiza BUG-02**: añadir UNIQUE constraint puede filtrar existencia en mensajes de error. Mitigación: usar `.one_or_none()` y manejar `IntegrityError` en create path, no en read path (send_guard es read-only) | "Integrity constraint errors are not suppressed by RLS" |
| **FastAPI discussion #10450** | "SQLAlchemy QueuePool limit exceeded...connections not being properly closed" | **valida BUG-04 severidad ALTA**: el pattern sync-in-async es conocido como causante #1 de pool exhaustion | "QueuePool limit being exceeded while using DB as a dependency" |
| **FastAPI docs async patterns** | "session dependency must be async generator with try/finally ensuring `await session.close()`" | **refuerza BUG-04 fix**: el `check_send_permission_async` debe envolver `try/finally close()` dentro de `to_thread` o usar `AsyncSession` nativa | "yield wrapped in try...finally block to ensure await session.close()" |

---

## 3. Aplicación al diseño Phase 5 (mapping decision → fuente)

### 3.1 Decisión D1 — `SendDecision` dataclass uniforme (fix BUG-11)

**Diseño**:
```python
from dataclasses import dataclass
from typing import Literal, Optional, Union

@dataclass(frozen=True)
class Allowed:
    creator_id: str
    caller: str
    rule: Literal["R1", "R3"]  # approved OR autopilot_premium
    decision_id: str  # uuid for audit trace

@dataclass(frozen=True)
class Blocked:
    creator_id: str
    caller: str
    rule: Literal["R2", "R4"]  # not_found OR insufficient_flags
    reason: str
    decision_id: str

SendDecision = Union[Allowed, Blocked]
```

**Validado por:** P3 Luke Plant (sum types pattern, no ambiguity), P5 Decision Gateway (structured response), R1 OPA (decision_id for audit), Ezyang (ADTs via Union).

**Refutado/matizado:** P3 no recomienda eliminar exceptions — **compromiso**: el módulo interno mantiene `raise SendBlocked` (backward compat con los 6 callsites existentes); adicionalmente expone `check_send_decision(...) -> SendDecision` que los nuevos callers pueden preferir. Migración gradual.

### 3.2 Decisión D2 — `check_send_permission_async` (fix BUG-04)

**Diseño**:
```python
async def check_send_permission_async(
    creator_id: str, *, approved: bool = False, caller: str
) -> None:  # raises SendBlocked
    from asyncio import to_thread
    await to_thread(check_send_permission, creator_id, approved=approved, caller=caller)
```

**Validado por:** R3 Casbin PyCasbin (`AsyncEnforcer` paralelo desde 1.23.0), R2 Cerbos SDK (async + non-async coexistence), FastAPI discussion (pool exhaustion root cause = sync-in-async).

**Matiz P1 Cerbos:** podría considerarse **añadir un cache local TTL** (e.g. 5s) sobre `(creator_id, flag_snapshot)` para reducir DB load en paths alta-frecuencia. **Decisión Phase 5:** NO añadir cache (scope limitado + cache introduce complexity + race window más amplio). Registrar como futuro trabajo en `DECISIONS.md`.

### 3.3 Decisión D3 — Flag `SEND_GUARD_AUDIT_ONLY` (shadow mode)

**Diseño**:
```python
import os
SEND_GUARD_AUDIT_ONLY = os.getenv("SEND_GUARD_AUDIT_ONLY", "false").lower() == "true"

# En el branch R4 (block):
if SEND_GUARD_AUDIT_ONLY:
    logger.warning(
        f"[SEND_GUARD_SHADOW] Would have blocked creator={creator_id} "
        f"caller={caller} rule=R4 — AUDIT_ONLY mode, allowing"
    )
    SEND_GUARD_SHADOW_BLOCKED.labels(rule="R4", caller=caller).inc()
    return  # ALLOW in shadow mode
# Else, real enforcement
raise SendBlocked(...)
```

**Validado por:** Istio dry-run annotation (`shadow denied, matched policy [name]` + Prometheus `authz_dry_run_action`). Default=false asegura que sin configurar, comportamiento es enforce (safety-first).

**Aplicabilidad en Clonnect:** permitir a CI/test scoped ejecutar sin bloquear + permitir deploy-test en staging antes de activar enforce en un nuevo adapter (útil si añadimos el guard al bypass B2 webhook autopilot y queremos observar sin bloquear durante 24-48h para caracterizar volumen).

**No aplicable:** el hybrid "fail-open por 48h" de AuthZed/Sivo — constraint del task confirma que apagar el guard = incidente legal. Rechazado.

### 3.4 Decisión D4 — `UNIQUE` constraint en `Creator.name` + `.one_or_none()` (fix BUG-02)

**Diseño:** Alembic migration:
```sql
-- 040_creator_name_unique.py
ALTER TABLE creators ADD CONSTRAINT creators_name_key UNIQUE (name);
```

+ cambio L54:
```python
creator = session.query(Creator).filter_by(name=creator_id).one_or_none()
```

**Validado por:** AWS multi-tenant PG guidance (UNIQUE + RLS para tenant-isolation). Refuerza **matiz** Logto: el UNIQUE puede filtrar existencia via IntegrityError, pero esto aplica a INSERT paths, NO al read-only `.one_or_none()` de send_guard. Safe.

**Pre-migration task:** script idempotente que detecte duplicados actuales (`SELECT name, count(*) FROM creators GROUP BY name HAVING count(*) > 1`) y aborta si existen. Esto ya es parte del Phase 5 plan.

### 3.5 Decisión D5 — Logs JSON estructurados (fix BUG-06)

**Diseño:**
```python
logger.info(
    "send_guard_decision",
    extra={
        "decision_id": str(uuid.uuid4()),
        "creator_id": creator_id,
        "caller": caller,
        "decision": "allowed" | "blocked",
        "rule": "R1" | "R2" | "R3" | "R4",
        "reason": "approved" | "autopilot_premium" | "creator_not_found" | "insufficient_flags",
        "copilot_mode": creator.copilot_mode if creator else None,
        "autopilot_premium_enabled": creator.autopilot_premium_enabled if creator else None,
        "latency_ms": latency_ms,
        "timestamp": utcnow_iso(),
    }
)
```

Requiere un `JsonFormatter` configurado en Railway (actualmente Clonnect loggea string — Phase 5 añade el formatter).

**Validado por:** P4 TCPA (timestamp + fields, 4-year retention), R1 OPA (decision_id structured), P5 Decision Gateway (detailed audit logs centralized).

### 3.6 Decisión D6 — Métricas Prometheus

**Diseño:**
```python
from prometheus_client import Counter

SEND_GUARD_DECISION = Counter(
    "send_guard_decision_total",
    "Send guard decisions by rule/outcome",
    ["decision", "rule", "caller"]
)
SEND_GUARD_BYPASS_DETECTED = Counter(
    "send_guard_bypass_detected_total",
    "Send attempts without passing through check_send_permission",
    ["source"]
)
```

`bypass_detected` se incrementa desde un wrapper puesto en cada path que históricamente bypassa (BUG-01/05/07/08) para observar residuos. También útil para test-suite verify post-fix.

**Validado por:** R1 OPA (decision_logs + metrics), Istio dry-run (Prometheus tags `authz_dry_run_action`).

### 3.7 Decisión D7 — Fail-closed en DB failure

**Pregunta:** si la DB está caída cuando el guard se ejecuta, ¿permitir o denegar?

**Diseño actual (pre-Phase 5):** cualquier exception en L52-L54 (SessionLocal/query) propaga → callsite captura según política propia (C1/C4: retorna False; C2: retry queue; C3: dict con error; C5/C6: propaga). **Inconsistente** (ver BUG-11).

**Diseño Phase 5:** el módulo `send_guard` **mantiene fail-closed** — cualquier excepción no-SendBlocked se envuelve en un `SendBlocked(f"guard_internal_error: {e}")` y se loggea `critical`. Los callsites tratan `SendBlocked` uniformemente (tras migración a `SendDecision`, ven `Blocked` dataclass con `rule="R5"` internal error).

**Validado por:** P1 Cerbos "authorization never becomes a single point of failure while still providing strong security guarantees" (interpretado como "guard es fail-closed incluso si el módulo mismo falla"), P2 AuthZed "any unexpected result as a denial...is the fail-closed approach".

**Rechazado:** hybrid timeout fail-open de Sivo (mismo motivo que D3: apagar = incidente legal).

---

## 4. Patrones industriales NO adoptados y por qué

| Patrón encontrado | Fuente | Por qué NO se adopta |
|-------------------|--------|----------------------|
| Fail-open window 48h | AuthZed / Sivo | Constraint explícito del task: apagar = incidente legal. Send_guard nunca fail-open. |
| Local cache TTL de decisiones | P1 Cerbos | Complejidad + race window más amplio + fuera del scope Phase 5. Registrar en DECISIONS.md para Q2. |
| RLS (Row-Level Security) multi-tenant | AWS/Logto | Clonnect es single-tenant-per-creator; RLS no aplicable al modelo actual. |
| Traefik ForwardAuth / reverse proxy | MCP OAuth Gateway | Clonnect es monolito FastAPI; overkill añadir un proxy solo para send_guard. |
| Migración completa a OPA/Cerbos como motor de policy | R1/R2 | Ambos son excelentes pero requieren stack externo (servicio + sidecar). Send_guard tiene 2 reglas — OPA sería over-engineering. Mantener Python in-process. |
| Decision Gateway centralizado MCP-style | P5 | Relevante para agent architectures con N-tools; send_guard es 1 regla + 6 adapters — no justifica gateway pattern full-blown. |

---

## 5. Referencias rápidas para Phase 5 (citables en commit messages / PR description)

- **P2 AuthZed**: "A fail-closed state ensures that, in the event of an error, access is denied" → justifica rechazo de cualquier fallback path.
- **P3 Luke Plant**: "Those objects can't be accidentally converted into success values" → justifica `SendDecision` frozen dataclass.
- **P4 TCPA 2025**: "Businesses generally must honor revocations within 10 business days" → justifica eliminar `approved=True` hardcoded en retry (BUG-09/10).
- **R3 Casbin**: "Async is now supported by Pycasbin >= 1.23.0" → precedente de migración async-first sync-wrapper.
- **Istio dry-run**: "shadow denied, matched policy [name]" → pattern para log de AUDIT_ONLY.

---

## Resumen ejecutivo Fase 4

- **5 fuentes primarias** (Cerbos, AuthZed, Luke Plant, TCPA 2025, Decision Gateway Pattern) + **3 repos OSS** (OPA 11.6k⭐, Cerbos 4.3k⭐, PyCasbin 1.8k⭐) + **fuentes auxiliares** (Istio dry-run, AWS multi-tenant).
- **D1 `SendDecision` dataclass** ✅ validado por P3 + P5 + R1 + Ezyang. Fix BUG-11.
- **D2 `check_send_permission_async`** ✅ validado por R3 + R2 + FastAPI discussion. Fix BUG-04 con sync wrapper backward-compat.
- **D3 `SEND_GUARD_AUDIT_ONLY` flag** ✅ validado por Istio dry-run + P5. Default=false (shadow opt-in). Fail-open window rechazado por constraint legal.
- **D4 `UNIQUE(Creator.name)`** ✅ validado por AWS multi-tenant + matiz Logto (safe en read path). Fix BUG-02.
- **D5 logs JSON estructurados** ✅ validado por P4 TCPA + R1 OPA. Fix BUG-06.
- **D6 métricas Prometheus** ✅ validado por R1 OPA + Istio. Fix BUG-06 + observabilidad bypass.
- **D7 fail-closed ante DB failure** ✅ validado por P1 Cerbos + P2 AuthZed. Guard interno siempre retorna Blocked bajo excepción.
- **Patrones rechazados documentados**: fail-open window, cache TTL, RLS, OPA migración, Decision Gateway full, todos con razón explícita.

**STOP Fase 4.** Aguardo confirmación para proceder a Fase 5 (implementación: 15 bugs fixed, SendDecision uniforme, async canonical, AUDIT_ONLY flag, métricas, tests 20+).

---

### Sources

- [Patterns of Failure in Modern Authorization — Cerbos](https://www.cerbos.dev/blog/authorization-failure-patterns)
- [Understanding "Failed Open" and "Fail Closed" — AuthZed](https://authzed.com/blog/fail-open)
- [Raising exceptions or returning error objects in Python — Luke Plant](https://lukeplant.me.uk/blog/posts/raising-exceptions-or-returning-error-objects-in-python/)
- [TCPA Compliance 2025 Guide — Secure Privacy](https://secureprivacy.ai/blog/telephone-consumer-protection-act-compliance-tcpa-2025-full-guide)
- [Designing Authorization for Production AI Agents — V. Peri / Advisor360°](https://medium.com/advisor360-com/designing-authorization-for-production-ai-agents-the-decision-gateway-pattern-59582093ccb8)
- [Istio Authorization Policy Dry Run](https://istio.io/latest/docs/tasks/security/authorization/authz-dry-run/)
- [open-policy-agent/opa](https://github.com/open-policy-agent/opa)
- [cerbos/cerbos](https://github.com/cerbos/cerbos)
- [casbin/pycasbin](https://github.com/casbin/pycasbin)
- [AWS Multi-tenant PostgreSQL prescriptive guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/saas-multitenant-managed-postgresql/welcome.html)
- [Logto multi-tenancy PostgreSQL blog](https://blog.logto.io/implement-multi-tenancy)
- [FastAPI SQLAlchemy pool exhaustion discussion #10450](https://github.com/fastapi/fastapi/discussions/10450)
- [Ezyang — Idiomatic algebraic data types in Python with dataclasses and Union](https://blog.ezyang.com/2020/10/idiomatic-algebraic-data-types-in-python-with-dataclasses-and-union/)
