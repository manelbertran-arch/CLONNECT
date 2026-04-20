# S5 OFF-Components Decision Matrix — Cross-Reference Audit

**Branch:** `worker/s5-crossref`
**Date:** 2026-04-20
**Source audit:** commit `52986d00` (worker/s5-off-components-audit)

---

## 1. Executive Summary

- **Compaction:** UUID bug CONFIRMED — 0 shadow rows because slug "iris_bertran" fails `UUID()` parse at `context.py:649`. Fix: 15 lines, copy `dual_write.py` pattern. **ACTIVAR_TRAS_FIX.**
- **Distill:** H -10.0 and S4 -6.8 confirmed by CCEE v5. CC NEVER compresses identity signals (system prompt). Concept doesn't apply to persona domain. **ESPERAR_FT.**
- **TypedMeta:** 20% integration confirmed. Infrastructure solid. No regression possible when OFF. **ESPERAR_COMPLETAR.**

---

## 2. Tabla Maestra

| Componente | Gap medido? | Viola principio? | Tipo | Claim CC verif? | Effort fix | Prioridad FT | Recomendación |
|---|---|---|---|---|---|---|---|
| **Compaction** | No (bug bloqueó medición) | No | Transformation (CC-faithful) | SÍ (7-step fiel) | 30min | antes | **ACTIVAR_TRAS_FIX** |
| **Distill** | Sí: H -10.0, S4 -6.8 | No formal, pero viola principio CC implícito | Transformation (NO CC pattern) | SÍ (CC nunca comprime identity) | 4h prompt v2 (efecto incierto) | después | **ESPERAR_FT** |
| **TypedMeta** | N/A (no afecta pipeline) | No | Observability | SÍ (CC telemetría ~igual) | 20-30h completar | después | **ESPERAR_COMPLETAR** |

---

## 3. CRUCE 0 — Bug UUID Compaction (PRIORIDAD MÁXIMA)

### Veredicto: BUG CONFIRMADO ✅

**Evidencia empírica:**

**A. ¿Realmente intenta UUID(slug)?**

`core/dm/phases/context.py:648-652`:
```python
try:
    creator_uuid = UUID(str(creator_id_str))     # ← line 649
except (ValueError, AttributeError, TypeError):
    logger.debug("[ARC3-SHADOW] invalid creator_id, skipping log")
    return                                         # ← line 652, SIEMPRE sale aquí
```

Call chain completa:
1. `context.py:1516`: `creator_id=agent.creator_id` → slug (CLAUDE.md: "creator_id is a slug")
2. `context.py:766`: `asyncio.create_task(_run_compactor_shadow(inp, ...))` → `inp.creator_id` = slug
3. `context.py:711`: `_log_shadow_compactor_sync(inp.creator_id, ...)` → `creator_id_str` = slug
4. `context.py:649`: `UUID("iris_bertran")` → `ValueError` → `return` at 652

**B. Pattern fix existente:**

`services/dual_write.py:98-121` — `_resolve_creator_uuid()`:
```python
async def _resolve_creator_uuid(creator_id: str) -> Optional[str]:
    try:
        _uuid.UUID(creator_id)        # Try UUID first
        return creator_id
    except (ValueError, AttributeError):
        pass
    def _lookup():                     # Fall back to DB lookup
        row = session.execute(
            text("SELECT id FROM creators WHERE name = :name LIMIT 1"),
            {"name": creator_id},
        ).fetchone()
        return str(row[0]) if row else None
    return await asyncio.to_thread(_lookup)
```

**C. DB query:** No puedo consultar Railway prod DB (protocolo: no tocar Railway). Sin embargo, la evidencia de código es determinista: `UUID("iris_bertran")` SIEMPRE lanza ValueError. Es imposible que haya rows.

**D. Fix propuesto (no aplicado):**

Reestructurar `_log_shadow_compactor_sync` para usar una sola session (ya la crea en línea 656):

```python
def _log_shadow_compactor_sync(creator_id_str, ...):
    import json
    from uuid import UUID
    from sqlalchemy import text as sa_text

    # Resolve creator_id: UUID or slug → UUID (pattern: dual_write.py:98-121)
    creator_uuid = None
    try:
        creator_uuid = UUID(str(creator_id_str))
    except (ValueError, AttributeError, TypeError):
        pass

    try:
        from api.database import SessionLocal
        db = SessionLocal()
        try:
            # Slug → UUID resolution (single session for lookup + insert)
            if creator_uuid is None:
                row = db.execute(
                    sa_text("SELECT id FROM creators WHERE name = :name LIMIT 1"),
                    {"name": creator_id_str}
                ).fetchone()
                if not row:
                    logger.debug("[ARC3-SHADOW] unknown creator=%s, skip", creator_id_str)
                    return
                creator_uuid = row[0]

            db.execute(sa_text("""
                INSERT INTO context_compactor_shadow_log (...)
                VALUES (...)
            """), {"creator_id": str(creator_uuid), ...})
            db.commit()
        finally:
            db.close()
    except Exception as _db_err:
        logger.debug("[ARC3-SHADOW] DB log failed (non-fatal): %s", _db_err)
```

**Effort:** ~30min (15 líneas cambio, 1 session, copy pattern existente, test + deploy)

---

## 4. CRUCE 1 — Audit vs Mediciones CCEE

### 1.1 Distill (H -10.0, S4 -6.8)

**Datos v5 (fuente: `docs/audit_sprint5/distill_AB_final_results.md`):**

| Dimensión | OFF | ON | Δ | Audit claim | Consistente? |
|---|---|---|---|---|---|
| S1 Style Fidelity | 72.3 | 75.7 | **+3.4** | "mejora" | ✅ ALTA |
| S2 Response Quality | 47.0 | 47.6 | +0.6 | (no claim) | — |
| S3 Strategic Alignment | 64.6 | 62.1 | -2.5 | (no claim) | — |
| S4 Adaptation | 66.9 | 60.1 | **-6.8** | "regresión notable" | ✅ ALTA |
| H Indistinguishability | 72.0 | 62.0 | **-10.0** | "regresión notable" | ✅ ALTA |
| Composite v5 | 66.4 | 65.7 | -0.7 | "tolerable" | ✅ ALTA |

**Raw JSON runs (50×3, `distill_AB_ON_20260420_1155.json`):**
- Run 1: H2 cosine=0.519 (ON) vs Run 3 OFF: H2 cosine=~0.40
- H2 vector analysis: bot_vector diverge significativamente en features 0, 4, 6 (probablemente message length, emoji rate, response structure)

**Audit claim "prompt no preserva estructura mensajes":**

El prompt v1 (`style_distill_service.py:47-74`) instruye preservar:
1. ✅ Voz (tics, expresiones, tono)
2. ✅ Ejemplos (3-5 representativos)
3. ✅ Reglas situacionales (cold/warm/hot)
4. ⚠️ "Restricciones de forma" — genérico, no específico

**NO instruye preservar:** longitud típica de respuesta, patrones apertura/cierre, posición de emojis, ratio pregunta/afirmación.

**Fenómeno paradoja S1↑ / H↓:** El distill CONCENTRA instrucciones estilísticas → modelo sigue estilo más fielmente (S1↑) pero pierde patrones ESTRUCTURALES sutiles que hacen las respuestas indistinguibles de las humanas (H↓). El distill captura el QUÉ del estilo pero pierde el CÓMO.

**Consistencia:** ALTA. Claims del audit son 100% consistentes con datos medidos.

### 1.2 Compaction

Bug UUID confirmado → **sin datos de shadow log → sin evidencia cruzada posible.**

Declaro: "Bug bloqueó toda medición. Phase 3 activation gate ('1000 shadow turns con compaction rate <15%') se construiría sobre 0 datos. Decisiones Phase 3 están suspendidas hasta fix."

### 1.3 TypedMeta

Audit dice "integración 20%". Verificación via call sites:

| Sistema | emit_metric? | typed_metadata? | Evidencia |
|---|---|---|---|
| Budget (ARC1) | ✅ 5 calls | ❌ | `core/dm/budget/metrics.py:41-55` |
| Detection | ❌ | ✅ (flag ON) | `core/dm/phases/detection.py:99-115` |
| Generation | ❌ | ✅ (flag ON) | `core/dm/phases/generation.py:163-192` |
| Post-gen | ❌ | ✅ (flag ON) | `core/dm/phases/postprocessing.py:326-331` |
| ARC2 Memory | ✅ dual_write counters | ❌ | `services/dual_write.py` |
| Scoring/RAG/DocD | ❌ | ❌ | — |

**Cobertura: ~20% typed, ~10% emit_metric.** Claim del audit: CONFIRMADO.

---

## 5. CRUCE 2 — Audit vs Principios Arquitectónicos

### 2.1 Distill prompt v2 — ¿Viola zero-hardcoding?

**Principio** (DECISIONS.md:809-824):
> "Every threshold, fallback list, and default must come from the creator's mined data profile."
> "If data doesn't exist → skip + log warning. Never invent a default number."

El prompt v2 propuesto agregaría instrucciones como "preservar longitud típica de respuesta" y "preservar patrones apertura/cierre". Estas son instrucciones a NIVEL CATEGORÍA ("preserva X") no a NIVEL VALOR ("usa 35% emojis").

**Veredicto:** No viola zero-hardcoding. Las instrucciones son meta-guidance sobre qué categorías preservar del Doc D; los valores reales siguen proviniendo del contenido de Doc D.

### 2.2 Compaction UUID fix — ¿Viola algún principio?

**Veredicto:** No. Copy-paste de pattern existente (`dual_write.py:98-121`). Zero lógica nueva. Cero thresholds. Bug fix puro.

### 2.3 ¿Distill/Compaction modifica Doc D en post-processing?

**Principio implícito:** Personalidad definida por few-shot + Doc D + FT. Post-processing no debe alterar identidad.

- Distill: transforma Doc D **INPUT** (pre-processing, no post). No es violación técnica, pero crea derivado de señal identitaria.
- Compaction: trunca **SECTIONS** del prompt (pre-processing). No altera Doc D directamente.

**Veredicto:** Sin violaciones de post-processing. Pero distill tiene riesgo arquitectónico: crea derivado de identidad cuya fidelidad es inherentemente incierta.

---

## 6. CRUCE 3 — Observability vs Transformation

### Hipótesis original
> "CC extracciones funcionan para observability, fallan para transformation con modelo base."

### Evidencia

| Sprint | Componente | Tipo | CC-faithful? | Resultado | Fuente |
|---|---|---|---|---|---|
| S2 | History compactor (importance scoring) | Transform | **NO** (añadido sobre CC) | **REGRESIÓN** S1 -10.9 | DECISIONS.md:641-657 |
| S2 | History compactor (revert to recency) | Transform | **SÍ** | **RECUPERADO** | DECISIONS.md:648-649 |
| S5 | Distill Doc D | Transform | **NO** (CC nunca comprime identity) | **REGRESIÓN** H -10.0 | distill_AB_final_results.md |
| S5 | Compaction (Phase 2 shadow) | Transform | **SÍ** (7-step fiel) | **BLOQUEADO** (UUID bug) | context.py:649 |
| S5 | ARC4 Mutations | Transform | N/A (rule-based, no CC equiv) | 6/7 **PROTECTIVO** | ARC4_per_mutation_ccee_impact.md |
| S5 | TypedMeta (ARC5) | Observability | **SÍ** (CC telemetría similar) | **OK** (solo incompleto) | core/metadata/ |
| S5 | ARC2 Lead Memories | Observability+Transform | Parcial | K1 regression (25→50 post-fix) | ARC2_implementation_audit.md |

### Hipótesis refinada

La evidencia no soporta la hipótesis binaria "observ funciona, transform falla". Soporta una más específica:

> **CC patterns fieles funcionan o no causan regresión. Deviaciones del pattern CC (añadir lógica propia, aplicar a dominio distinto) regresionan.**

Evidencia clave:
1. Sprint 2 importance scoring (desviación de CC recency) → regresó -10.9 en S1
2. Sprint 2 reversion a CC recency → recuperó
3. Sprint 5 Distill (concepto CC aplicado a dominio wrong: identity vs conversation) → regresó H -10
4. Sprint 5 Compaction (CC-faithful 7-step, but bugged) → desconocido
5. ARC4 Mutations (no CC pattern, surgical rule-based) → funcionan

### Aprendizaje arquitectónico

**PRINCIPIO: CC nunca comprime señales identitarias (system prompt). Solo comprime señales temporales (conversation history).**

En CC (`compact.ts`):
- System prompt: PRESERVADO 100%, nunca tocado (ref: compact.ts:634 "PLUS ~20-40K for system prompt")
- Conversation: comprimida agresivamente (13% retention)
- Post-compact: 50K tokens de archivos/skills RE-INYECTADOS

En Clonnect, Doc D es la señal identitaria equivalente al system prompt de CC. Comprimirlo al 30% viola el principio implícito de CC de NUNCA tocar la identidad.

**Corolario:** Distill prompt v2 (mejorar el prompt de compresión) probablemente NO resuelve el problema fundamental: la compresión de señales identitarias es inherentemente lossy para features sutiles (H). Mejorar el prompt puede reducir la regresión pero no eliminarla.

**Recomendación:** Aplazar distill a post-FT. Con fine-tuning, el modelo ya internalizó los patrones de estilo → Doc D puede ser más corto sin pérdida porque el modelo no depende exclusivamente de in-context learning para estilo.

---

## 7. CRUCE 4 — CC Repo Ground Truth

**Acceso:** ✅ Repo CC local en `/Users/manelbertranluque/instructkr-claude-code/`

| Claim audit | CC fuente | Verificado? | Nota |
|---|---|---|---|
| "CC no tiene system prompt distillation" | compact.ts solo comprime conversation. Grep "distill" → solo memdir (memory logs, no system prompt). | ✅ VERIFICADO | |
| "CC compresión nunca baja de 50%" | Ambiguo. Total context post-compact ~50% (summary 20K + restored 50K + system 30K = 100K / 200K). Pero conversation-only retention = ~13%. | ⚠️ PARCIALMENTE CORRECTO | Claim aplica a total context, no a conversation |
| "CC 7-step algorithm" | No existe 7-step literal en CC. CC tiene 3-path (session memory → reactive → traditional) con microcompact pre-pass. | ❌ INCORRECTO | Clonnect 7-step es diseño propio inspirado en CC, no extracción literal |
| "CC uses pure recency" | sessionMemoryCompact.ts:372, confirmado en DECISIONS.md:653 | ✅ VERIFICADO | |
| "CC post-compact restoration" | compact.ts:122-130: POST_COMPACT_TOKEN_BUDGET=50,000, POST_COMPACT_MAX_FILES_TO_RESTORE=5 | ✅ VERIFICADO | Clonnect no tiene equivalente |
| "CC autocompact threshold: window - 13K buffer" | autoCompact.ts:62: AUTOCOMPACT_BUFFER_TOKENS=13,000 | ✅ VERIFICADO | |
| "CC typed telemetry" | analytics/index.ts: logEvent() con marker types, no Zod. ~24 event types para compact solo. | ✅ VERIFICADO | Clonnect Pydantic es más estricto |

**Recalibración de confianza:**
- Claims sobre CC compaction/recency: ALTA confianza
- Claim "CC nunca baja de 50%": MEDIA (aplica a total, no a conversación aislada)
- Claim "7-step fiel a CC": BAJA (es diseño propio inspirado, no extracción)

---

## 8. Plan Acción Priorizado

### Esta semana (pre-FT)

| # | Acción | Componente | Effort | Impacto |
|---|---|---|---|---|
| **1** | Fix UUID slug→UUID en `_log_shadow_compactor_sync` | Compaction | 30min | Desbloquea medición shadow para Phase 3 gate |
| **2** | Deploy fix a Railway, esperar 48-72h de datos | Compaction | 0h (deploy) + espera | Datos reales para decidir Phase 3 |
| **3** | Analizar shadow data: ¿qué % de requests necesitan compaction? | Compaction | 1h | Gate: si <15% → compaction innecesaria |

### Post-FT

| # | Acción | Componente | Effort | Condición |
|---|---|---|---|---|
| **4** | Re-evaluar distill con modelo fine-tuned | Distill | 4h CCEE | Solo si FT mejora S1 base |
| **5** | Si distill sigue regresando H post-FT → ABANDONAR | Distill | 0h | Evidencia de que FT no resuelve |
| **6** | Completar ARC5 Phase 2 (scoring pipeline + emit_metric) | TypedMeta | 20-30h | Cuando haya capacidad de desarrollo |
| **7** | ARC5 Phase 4 (Grafana dashboards) | TypedMeta | 10h | Después de Phase 2 |

### Abandonar

| Acción | Componente | Razón |
|---|---|---|
| Distill prompt v2 AHORA | Distill | Principio CC: no comprimir identity signals. Prompt v2 reduce regresión pero no la elimina. |
| Activar USE_COMPACTION sin shadow data | Compaction | Gate "1000 turns <15% compaction rate" no cumplido por 0 datos |

---

## 9. Aprendizaje Arquitectónico

### PRINCIPIO PROPUESTO: "Identity Signal Preservation"

> Las señales que definen la identidad del clon (Doc D, few-shots, vocabulary profile) no deben ser comprimidas por LLM. Claude Code preserva su system prompt al 100% y solo comprime conversation history (señales temporales). Clonnect debe seguir el mismo principio.

**Evidencia acumulada:**
1. QW2 compressed Doc D → regresión -10.69 composite (DECISIONS.md, abril 2026)
2. Sprint 5 Distill → regresión H -10.0, S4 -6.8 (distill_AB_final_results.md)
3. Sprint 2 importance scoring → regresión S1 -10.9 (eliminó style examples = identity signals)
4. CC `/compact` → NUNCA toca system prompt (compact.ts verified)

**Excepción:** Post fine-tuning, el modelo habrá internalizado patrones de identidad. En ese punto, Doc D puede ser más corto porque sirve como RECORDATORIO, no como FUENTE ÚNICA de estilo. Distill podría funcionar post-FT.

**Implicación para compaction:** La compaction de `style_prompt` section (ratio cap 35%) sí es compresión de identity signal. Si el shadow log muestra que style_prompt es la sección más frecuentemente truncada, reconsiderar el ratio o excluir style_prompt de truncation.
