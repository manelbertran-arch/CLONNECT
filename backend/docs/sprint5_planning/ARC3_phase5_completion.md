# ARC3 Phase 5 — Completion Summary

**Sprint:** 5 / Track 2 / ARC3
**Fecha:** 2026-04-19
**Estado:** ✅ Phase 5 COMPLETE — ARC3 CERRADO (todas las phases implementadas o documentadas)
**Branch:** feature/arc3-phase5-runbook

---

## 1. Sprint Summary ARC3

ARC3 resuelve el problema central de gestión de context budget en Clonnect: sin compactación, cuando el prompt excede MAX_CONTEXT_CHARS=8000, la única estrategia era truncar Doc D mecánicamente, causando -10.5 puntos CCEE (evidencia QW2).

### Phases completadas

| Phase | Contenido | Estado | Branch mergeado |
|-------|-----------|--------|-----------------|
| **Phase 1** | StyleDistillCache — tabla `creator_style_distill`, servicio distillation, batch script, flag `USE_DISTILLED_DOC_D` | ✅ Mergeado | feature/arc3-phase1-wiring |
| **Phase 2** | PromptSliceCompactor shadow mode — `core/generation/compactor.py`, shadow log table, integración en context.py, flag `ENABLE_COMPACTOR_SHADOW` | ✅ Mergeado | feature/arc3-phase1-wiring |
| **Phase 3** | Live rollout con sticky hashing, ramp-up Stefano→Iris | ⏳ PENDING live rollout (fase activa siguiente) | — |
| **Phase 4** | CircuitBreaker — TTLCache backend, MAX_CONSECUTIVE_FAILURES=3, fallback responses, alerting, flag `ENABLE_CIRCUIT_BREAKER` | ✅ Mergeado | feature/arc3-phase4+arc5-phase4 |
| **Phase 5** | Runbooks operacionales + completion doc (este fichero) | ✅ Esta branch | feature/arc3-phase5-runbook |

---

## 2. Estado actual en producción

### Feature flags ARC3

| Flag | Env var | Default | Estado prod |
|------|---------|---------|-------------|
| `USE_DISTILLED_DOC_D` | `USE_DISTILLED_DOC_D` | `false` | OFF — pendiente CCEE validation |
| `ENABLE_COMPACTOR_SHADOW` | `ENABLE_COMPACTOR_SHADOW` | `true` | ON — acumulando shadow data |
| `USE_COMPACTION` | `USE_COMPACTION` | `false` | OFF — pendiente gate < 15% |
| `ENABLE_CIRCUIT_BREAKER` | `ENABLE_CIRCUIT_BREAKER` | `true` | ON — activo como safety net |

### Tablas DB creadas en ARC3

| Tabla | Propósito | Phase |
|-------|-----------|-------|
| `creator_style_distill` | Cache de Doc D distillados por creator × hash × prompt_version | Phase 1 |
| `context_compactor_shadow_log` | Log de decisiones del compactor (shadow mode) | Phase 2 |

### CircuitBreaker: ya activo y validado

El CircuitBreaker está operativo en producción desde el merge de Phase 4:
- Backend: TTLCache en memoria (no Redis — decisión de implementación vs diseño original)
- Integración: `core/dm/phases/generation.py:477-503`
- Estado: ENABLE_CIRCUIT_BREAKER=true (default ON)
- Referencia: diseño en `docs/sprint5_planning/ARC3_phase4_circuit_breaker.md`

### StyleDistillCache: shadow, no activo en prod

Distillations generadas y cacheadas en `creator_style_distill` pero `USE_DISTILLED_DOC_D=false`. El runtime aún usa Doc D completo. Activación requiere CCEE gate (ΔCCEE_composite ≥ -3).

### PromptSliceCompactor: shadow mode activo

`ENABLE_COMPACTOR_SHADOW=true` → el compactor corre en paralelo y loguea a `context_compactor_shadow_log` sin alterar el prompt real. Gate para Phase 3: compaction_pct < 15% sobre 1000+ turns.

---

## 3. Deliverables Phase 5

### Runbooks creados

| Fichero | Contenido | Líneas aprox |
|---------|-----------|-------------|
| `docs/runbooks/compaction_tuning.md` | Ajuste de ratios per-creator, interpretación shadow log, deploy gradual, troubleshooting | ~220 |
| `docs/runbooks/circuit_breaker_ops.md` | Diagnóstico trips, reset manual, failure taxonomy, tuning MAX_FAILURES | ~230 |
| `docs/runbooks/distill_cache_management.md` | Cuándo re-distillar, comandos batch, prompt versioning, invalidar cache, monitoreo | ~220 |
| `docs/sprint5_planning/ARC3_phase5_completion.md` | Este fichero — cierre oficial ARC3 Phase 5 | ~160 |

**Total Phase 5:** 4 ficheros MD, ~830 líneas, 0 líneas de código Python modificadas.

---

## 4. Pendientes conocidos

### Phase 3 — Live rollout (prioridad alta)

**Qué falta:**
1. Validar CCEE para USE_DISTILLED_DOC_D: correr CCEE v5.3 full vs distilled para Iris y Stefano → reportar delta
2. Verificar gate shadow: `python3.11 scripts/analyze_compactor_shadow.py` → confirmar < 15%
3. Implementar sticky hashing en `services/context.py` (hash(lead_id) % 100 < rollout_pct)
4. Activar rollout gradual según calendario:
   - Día 1: Stefano 10%
   - Día 3: Stefano 50% + Iris 10%
   - Día 7: 100% todos

**Kill switch disponible:** `USE_COMPACTION=false` revierte inmediatamente.

**Documentación de rollout:** cuando empiece, loguear en `docs/sprint5_planning/ARC3_phase3_rollout_log.md`.

### CCEE validation pendiente

- CCEE comparativo Doc D full vs distilled_short para Iris (20 scenarios × 2 modelos)
- CCEE comparativo para Stefano
- Gate: ΔCCEE_composite ≥ -3 por creator × modelo
- Resultado documentado en `docs/sprint5_planning/ARC3_phase1_distill_validation.md`

### Prometheus metrics — pendiente wiring completo

El metric `compaction_applied_total` está declarado en `core/observability/metrics.py:71` pero no está emitido explícitamente desde el compactor. Las siguientes métricas están **pendientes de wiring**:

| Métrica | Estado |
|---------|--------|
| `compaction_applied_total` | Declarada, no emitida |
| `distill_cache_hit_rate` | Inferible del shadow log SQL, no en Prometheus |
| `circuit_breaker_trips_total` | No declarada aún |
| `doc_d_truncation_rate` | No declarada aún |

Para completar el observability ARC3, crear un ticket de seguimiento.

### creator_runtime_config.compaction_ratios

Override per-creator de ratios de compactación está documentado en el runbook pero la columna `compaction_ratios` no existe aún en `creator_runtime_config`. Cuando se añada, el compactor ya está preparado para recibirlos (ver `PromptSliceCompactor.__init__` — parámetro `ratios`).

---

## 5. Acciones post-Sprint 5

### Cuándo activar USE_DISTILLED_DOC_D en prod

1. Completar CCEE validation (§4 arriba)
2. Si gate pasa (ΔCCEE ≥ -3): `railway variables --set USE_DISTILLED_DOC_D=true`
3. Monitorear cache hit rate (target > 95%) durante 48h
4. Si hit rate < 95%: ejecutar `python3.11 scripts/distill_style_prompts.py` para poblar cache

### Cuándo activar USE_COMPACTION

1. Shadow data: al menos 1000 turns en `context_compactor_shadow_log`
2. Gate compaction_pct < 15%: `python3.11 scripts/analyze_compactor_shadow.py`
3. CCEE distillation validado (porque compaction llama a distillation en runtime)
4. Sticky hash implementado en context.py
5. Rollout gradual según calendario Phase 3

### Monitoreo semanal recomendado

```bash
# Viernes tarde: revisión semanal ARC3
python3.11 scripts/analyze_compactor_shadow.py --hours 168  # 7 días

railway logs -n 500 | grep "CircuitBreaker.*TRIP" | wc -l  # trip count semana

# SQL: freshness de distillations
SELECT c.name, NOW() - d.created_at AS age FROM creator_style_distill d
JOIN creators c ON c.id = d.creator_id ORDER BY age DESC;
```

---

## 6. Integración con otros ARCs

### ARC3 → ARC1 (Budget Orchestrator)

- **ARC1 preferible pero no bloqueante** (§6.1 del diseño)
- Actualmente ARC3 opera standalone con `MAX_CONTEXT_CHARS=8000` hard-coded
- Cuando ARC1 llegue a producción: PromptSliceCompactor recibirá el budget dinámico de BudgetOrchestrator en lugar del hard-coded
- Cambio mínimo: pasar `budget_chars` desde ARC1 al instanciar `PromptSliceCompactor`

### ARC3 → ARC2 (Memory)

- ARC3 trata `lead_memories` como cualquier otra sección (ratio 0.20)
- ARC2 expone memories ya rankeadas por relevance → compactor trunca desde el final (menos relevantes)
- Sin conflicto activo

### ARC3 → ARC5 (Observability)

- ARC5 dashboards de Grafana necesitan métricas ARC3 (pendiente wiring §4)
- Shadow log `context_compactor_shadow_log` ya tiene datos para SQL-based dashboards mientras Prometheus no esté completo

---

## ARC3 — Acceptance Checklist

Del post-sprint checklist (ARC3 §10.3):

- [ ] 3 creators con distilled version validada (ΔCCEE ≥ -3) — **PENDING CCEE run**
- [ ] PromptSliceCompactor en prod al 100% de leads — **PENDING Phase 3 rollout**
- [ ] CircuitBreaker deployed y validado en staging — **✅ En producción (Phase 4)**
- [ ] Doc D truncation rate ≤ 2% medido 7 días post-rollout — **PENDING Phase 3**
- [ ] S3 recovery ≥ 65 (scoring-batch scenarios) — **PENDING Phase 3**
- [ ] Iris CCEE composite ≥ 70 (no regresión) — **PENDING Phase 3**
- [ ] Dashboards + alertas en producción — **PARTIAL (Grafana setup en runbook, métricas pendientes)**
- [ ] Runbook publicado — **✅ Este PR**
- [ ] Retrospectiva documentada — **PENDING tras Phase 3 completion**

---

## Responsables y contacto

| Componente | Owner |
|------------|-------|
| StyleDistillCache | Manel (validación CCEE gate) |
| PromptSliceCompactor live rollout | Manel (aprobación por step) |
| CircuitBreaker ops | On-call eng (ver `circuit_breaker_ops.md`) |
| Prometheus wiring pendiente | Siguiente sprint |
