# Sprint 5 OFF-Components Audit — Extraction Fidelity vs Claude Code Patterns

**Branch:** `worker/s5-off-components-audit`
**Date:** 2026-04-20
**Auditor:** Worker S5-AUDIT
**CC Reference:** `/Users/manelbertranluque/instructkr-claude-code/` (local checkout)

---

## 1. DISTILL (ARC3 Phase 1 — USE_DISTILLED_DOC_D=false)

### A. ¿Se inspiró en un pattern concreto de Claude Code?

**NO directo.** Claude Code no tiene "system prompt distillation" — tiene *conversation compaction* (`/compact`).

CC compaction (src/commands/compact/compact.ts):
- Summariza **conversation history**, no el system prompt
- 9-section template preserving: user intents, technical concepts, file names, code snippets, errors, pending tasks
- Token threshold: autocompact when context > (model_window - 13,000 buffer)
- Post-compact restoration: 5 most-recent files + ~5 skills (50K token budget)
- Ratio: compresses ~200K conversation → ~20K summary (90% reduction)

Clonnect distill (services/style_distill_service.py):
- Summariza **Doc D (system persona prompt)**, no la conversación
- Target: ~5K → ~1.5K chars (70% reduction)
- Single prompt asking LLM to preserve voice, tics, examples, tone rules

**Veredicto:** Concepto inspirado por CC (reducir tokens sin perder fidelidad), pero aplicado a un objeto totalmente distinto (persona vs conversación). No es extracción — es adaptación de concepto.

### B. ¿La extracción del pattern fue fiel?

| Elemento CC | CC Implementación | Clonnect Implementación | Fiel? |
|---|---|---|---|
| Preservación selectiva | 9 secciones con prioridades | 4 categorías (voz, ejemplos, tono, forma) | ✅ Adaptado |
| Threshold antes de comprimir | 13K buffer tokens | MIN_DOC_D_CHARS=1500 (skip short) | ⚠️ Diferente |
| Ratio compresión | ~90% reduction | ~70% reduction (target 1500 chars) | ⚠️ Más agresivo que CC |
| Cache/persistencia | In-memory session summary | DB table creator_style_distill con hash + version | ✅ Más robusto |
| Fail-silent | Si compaction falla → keep full context | Si distill miss → keep full Doc D | ✅ Idéntico pattern |
| Restauración post-compact | 5 files + skills re-injected | N/A — no re-inject, solo reemplaza | ❌ Missing |

**CC NUNCA comprime el system prompt a <30%.** CC preserva 50K tokens de contexto post-compact. Clonnect comprime Doc D a 30% (1500/5000). Esto es significativamente más agresivo.

### C. ¿Bugs, placeholders, o lógica incompleta?

**Prompt de distillation (services/style_distill_service.py:47-74):**

```
PRESERVAR:
1. VOZ única (tics verbales, expresiones, tono)
2. EJEMPLOS concretos (3-5)
3. Reglas de tono (cold/warm/hot)
4. Restricciones de forma (emojis, puntuación)

ELIMINAR:
- Frases genéricas, redundancias, meta-comentarios, ejemplos similares
```

**Análisis forense del prompt:**
- ✅ Instruye preservar idiosincrasias personales (tics, expresiones)
- ✅ Pide mantener reglas situacionales (cold/warm/hot)
- ⚠️ Pide solo 3-5 ejemplos — un Doc D rico puede tener 10-15, perder la mitad afecta la diversidad de estilo
- ❌ NO instruye preservar longitud característica de respuestas (cuántos chars típicos). H mide indistinguibilidad, y la longitud es señal fuerte.
- ❌ NO instruye preservar patrones de apertura/cierre de mensaje. Ej: si la creadora siempre empieza con "Holaa" y termina con emoji 💛, perder eso impacta H directamente.

**Medición:** Composite -0.7 (tolerable), pero **H -10.0** y **S4 -6.8**. El prompt preserva *qué* dice la creadora pero pierde *cómo* estructura sus mensajes.

### D. ¿Re-implementación arreglaría?

**SÍ — con ajustes específicos:**

1. **Prompt v2:** Agregar instrucciones explícitas de preservar:
   - Longitud típica de respuesta (en chars/palabras)
   - Patrones de apertura y cierre
   - Frecuencia y posición de emojis (no solo cuáles, sino dónde)
   - Ratio pregunta/afirmación
2. **Ratio menos agresivo:** Target 2500 chars en vez de 1500 (50% vs 70% compression). CC nunca comprime al 30%.
3. **Ejemplos completos:** Pedir 6-8 ejemplos, no 3-5.

**Esfuerzo:** ~4h (prompt v2 + re-generate cache + CCEE preflight)

---

## 2. COMPACTION (ARC3 Phase 2 — USE_COMPACTION=false, shadow ON)

### A. ¿Se inspiró en un pattern concreto de Claude Code?

**SÍ — pattern directo y bien identificado.**

CC compaction (src/services/compact/compact.ts + autoCompact.ts):
- 3 caminos: session memory → reactive → traditional
- Microcompact: strip images, delete tool IDs (pre-summarization optimization)
- 7-step algorithm con ratio caps por sección
- Token budget: model_window - 13K buffer
- Post-compact: re-inject 5 files + skills (50K tokens)

Clonnect compactor (core/generation/compactor.py):
- 7-step algorithm (§2.3.4): whitelist → budget → try-as-is → distill → ratios → aggressive → assemble
- Ratio caps: style_prompt 35%, lead_facts 15%, lead_memories 20%, rag_hits 15%, message_history 10%, few_shots 5%
- Whitelist: system_instructions, guardrails, persona_identity, current_user_msg, tone_directive
- Budget: MAX_CONTEXT_CHARS=8000 (configurable)

**Fuente CC citada:** El algorithm 7-step es fiel al pattern de CC compact.

### B. ¿La extracción del pattern fue fiel?

| Elemento CC | CC Implementación | Clonnect Implementación | Fiel? |
|---|---|---|---|
| Algorithm multi-step | 3 paths → microcompact → summarize | 7-step: whitelist → budget → try-as-is → distill → ratios → aggressive → assemble | ✅ |
| Ratio caps por sección | Implicit in token budget reservation | Explicit: 35/15/20/15/10/5 | ✅ Más explícito |
| Whitelist (never truncate) | system prompt, plan, recent files | system_instructions, guardrails, persona_identity, current_user_msg, tone_directive | ✅ |
| Truncation boundaries | paragraph → sentence → word | truncate_preserving_structure() | ✅ Idéntico |
| Shadow mode | N/A (CC compacts live) | Shadow log table con compaction_applied, reason, sections_truncated | ✅ Más cauteloso |
| Pre-summarization opt | Microcompact (strip images, tool IDs) | N/A — no equivalent | ❌ Missing |
| Post-compact restoration | Re-inject 5 files + skills | N/A — no equivalent | ❌ Missing |

**Extracción: 5/7 elementos fieles.** Missing microcompact y post-compact restoration.

### C. ¿Bugs, placeholders, o lógica incompleta?

**BUG CRÍTICO CONFIRMADO: Shadow log siempre tiene 0 rows.**

**Root cause:** `core/dm/phases/context.py:649`

```python
def _log_shadow_compactor_sync(creator_id_str, ...):
    try:
        creator_uuid = UUID(str(creator_id_str))  # ← SIEMPRE FALLA
    except (ValueError, AttributeError, TypeError):
        logger.debug("[ARC3-SHADOW] invalid creator_id, skipping log")
        return  # ← SIEMPRE SALE AQUÍ
```

`creator_id` en Clonnect es SIEMPRE un slug ("iris_bertran"), NUNCA un UUID. La llamada `UUID("iris_bertran")` siempre lanza `ValueError`, que se captura silenciosamente (nivel DEBUG), y la función retorna sin escribir nada a la DB.

**Evidencia:**
- CLAUDE.md documenta: "`creator_id` is a **slug** (e.g. `"iris_bertran"`), NOT a UUID"
- `agent.creator_id` = slug (core/dm/agent.py:117)
- `inp.creator_id` = slug (context.py:457)
- `_log_shadow_compactor_sync` recibe `inp.creator_id` = slug (context.py:711)
- `services/dual_write.py` tiene `_resolve_creator_uuid()` que resuelve slug→UUID correctamente — pero shadow logger NO usa esta función

**Impacto:** Phase 2 shadow NUNCA ha logueado un solo dato. Las decisiones de Phase 3 (activar compaction sí/no) se iban a tomar con 0 datos. La tabla existe, el schema es correcto, el algorithm funciona, pero el logger silenciosamente descarta todo.

**Issue secundario: asyncio.create_task sin tracking**

```python
# context.py:766 — fire-and-forget
asyncio.create_task(
    _run_compactor_shadow(inp, actual_combined_chars=len(result[0]))
)
return result
```

En FastAPI/uvicorn, el event loop persiste entre requests, así que el task sí se ejecuta. Pero el task falla silenciosamente por el UUID parsing bug antes de llegar al DB write. Si se arregla el UUID bug, el task debería funcionar.

**Issue terciario: _build_compactor_sections whitelist**

```python
# context.py:625 — ALL sections created with is_whitelist=False
SectionSpec(name=name, content=content or "", priority=priority, is_whitelist=False)
```

El whitelist de compactor.py (PROMPT_WHITELIST) nunca se usa porque ninguna sección se crea con `is_whitelist=True`. Esto es Phase 3 infrastructure pero introduce riesgo: cuando se active, las secciones "never truncate" sí serán truncadas.

### D. ¿Re-implementación arreglaría?

**SÍ — fix de 2 líneas resuelve el bug principal:**

```python
# Fix: resolver slug→UUID antes del INSERT
from api.database import SessionLocal
from sqlalchemy import text as _sql
db = SessionLocal()
try:
    row = db.execute(
        _sql("SELECT id FROM creators WHERE name = :name LIMIT 1"),
        {"name": creator_id_str}
    ).fetchone()
    if not row:
        return
    creator_uuid = row[0]
finally:
    db.close()
```

**Esfuerzo:** ~1h (fix UUID resolution + test + deploy). Después: esperar 48-72h de datos shadow para evaluar Phase 3.

---

## 3. TYPED METADATA (ARC5 — USE_TYPED_METADATA=false)

### A. ¿Se inspiró en un pattern concreto de Claude Code?

**SÍ — telemetría tipada con protección PII.**

CC telemetry (src/services/analytics/index.ts):
- `logEvent(name, metadata)` — 24+ event types con metadata tipada
- PII protection: marker types `AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS`
- `stripProtoFields()` sanitiza antes de enviar a Datadog
- MCP tool names redactados (`mcp__*` → `mcp_tool`)
- NO usa Zod para telemetría (Zod solo para tool params / MCP validation)

Clonnect typed metadata (core/metadata/):
- Pydantic BaseModel con Field validators (bounds, literals)
- `emit_metric(name, value, **labels)` — 23 metrics declaradas
- `write_metadata()` / `read_metadata()` con validación runtime
- Legacy fallback: si validación falla → return empty (fail-open)
- Contract enforcement CI script (scripts/ci/contract_enforcement.py)

### B. ¿La extracción del pattern fue fiel?

| Elemento CC | CC Implementación | Clonnect Implementación | Fiel? |
|---|---|---|---|
| Typed event metadata | Marker types + manual casting | Pydantic BaseModel con Field validators | ✅ Más estricto |
| PII protection | Marker types + stripProtoFields | N/A — no PII sanitization | ❌ Missing |
| Central emit point | logEvent() | emit_metric() | ✅ |
| Fail-open | Queued until sink attached | Log + return empty on error | ✅ |
| Schema validation | NO Zod for telemetry | YES Pydantic runtime validation | ✅ Más estricto |
| Contract enforcement | N/A | CI script with 4 checks | ✅ Extra |
| Metric registry | N/A (log events, not metrics) | 23 Prometheus metrics declared | ✅ Diferente pero válido |

**Extracción: 5/7 elementos fieles.** Clonnect es MÁS estricto que CC (Pydantic vs marker types).

### C. ¿Bugs, placeholders, o lógica incompleta?

**No hay bugs, pero hay gaps de cobertura significativos:**

1. **ScoringMetadata nunca se popula** — scoring ocurre en services layer, scores no accesibles en postprocessing
2. **detected_intent siempre "other"** — intent se resuelve en context phase, no detection
3. **Token counts = 0** — Gemini provider no retorna breakdown per-call
4. **emit_metric() solo wired a budget** — las 3 fases DM (detection, generation, post-gen) NO llaman emit_metric()

**Cobertura actual:**

| Sistema | Typed Meta | emit_metric | Status |
|---|---|---|---|
| Detection | ✅ (flag=true) | ❌ | PARCIAL |
| Generation | ✅ (flag=true) | ❌ | PARCIAL |
| Post-gen | ✅ (flag=true) | ❌ | PARCIAL |
| Budget (ARC1) | ❌ | ✅ (5 calls) | PARCIAL |
| Scoring | ❌ | ❌ | VACÍO |
| Doc D | ❌ | ❌ | VACÍO |
| RAG | ❌ | ❌ | VACÍO |
| Memory (ARC2) | ❌ | ✅ (dual_write counters) | PARCIAL |

**Cobertura estimada: ~20% typed, ~10% emit_metric, ~5% ambos.**

### D. ¿Re-implementación arreglaría?

**NO — el concepto es correcto, falta completar.**

No es un problema de extracción infiel o bug. Es un tema de completitud:
- Infrastructure layer: 100% (modelos, serdes, CI, registry)
- Integration layer: ~20% (solo 3 de 8+ sistemas)
- Observability layer: 0% (no dashboards)

**Recomendación:** ESPERAR. Activar cuando Phase 2 complete scoring pipeline + Phase 4 dashboards. No hay regresión al mantener OFF — solo se pierde granularidad de observabilidad.

**Esfuerzo para activar:** ~20-30h (scoring refactor + dashboard + shadow testing)

---

## Tabla Resumen

| Componente | CC Pattern? | Extracción fiel? | Bug implementación? | Root Cause regresión | Recomendación |
|---|---|---|---|---|---|
| **Distill** | Adaptación (no directo) | 5/7 ⚠️ | No bugs, prompt débil | Compresión 70% demasiado agresiva, prompt no preserva estructura | **RE_IMPLEMENTAR_PROMPT_V2** |
| **Compaction** | Directo y fiel | 5/7 ✅ | **BUG CRÍTICO:** UUID parsing falla con slug → 0 rows | Shadow log vacío, no hay datos para Phase 3 | **ACTIVAR_TRAS_FIX** |
| **Typed Meta** | Fiel (más estricto que CC) | 5/7 ✅ | Sin bugs, cobertura 20% | N/A — no afecta pipeline, solo observabilidad | **ESPERAR_COMPLETAR** |

---

## Acciones Priorizadas

### P0 — Fix inmediato (1h)
1. **Fix shadow log UUID resolution** en `core/dm/phases/context.py:649`
   - Reemplazar `UUID(creator_id_str)` con lookup `SELECT id FROM creators WHERE name = :name`
   - Equivalente a `_resolve_creator_uuid()` de `services/dual_write.py:98-121`
   - Después: verificar que rows aparecen en `context_compactor_shadow_log`

### P1 — Fix corto (4h)
2. **Prompt distill v2** en `services/style_distill_service.py:47-74`
   - Agregar: preservar longitud típica, patrones apertura/cierre, posición emojis
   - Target chars: subir de 1500 a 2500 (50% compression vs 70%)
   - Re-generate cache para iris_bertran
   - CCEE preflight para medir H y S4

### P2 — Completar (20-30h, post-sprint)
3. **ARC5 Phase 2 completion:** Wire scoring metadata, fix detected_intent, add token counts
4. **ARC5 Phase 4:** Grafana dashboards

### Diferir
5. Compaction microcompact equivalent (CC pattern) — bajo ROI para 8K char budget
6. Post-compact restoration (CC pattern) — solo relevante con budget > 20K tokens
