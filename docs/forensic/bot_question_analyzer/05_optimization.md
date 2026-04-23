# Bot Question Analyzer — Optimización (refactor zero-hardcoding)

**Fecha:** 2026-04-23 (PR iterado)
**Archivos modificados:**
- `backend/core/bot_question_analyzer.py` (330 → 418 LOC, bajo el límite 500)
- `backend/core/dm/phases/context.py` L803 (1 línea cambiada — propaga `agent.creator_id`)
- `backend/tests/unit/test_dm_agent_bot_question.py` (36 → 198 LOC, 7 → 15 tests)

**Archivos eliminados:**
- `backend/data/vocab/affirmation_vocab.json` — **eliminado**. Viola zero hardcoding.

---

## 1. Principio arquitectural: zero hardcoding lingüístico

Consistente con los demás sistemas data-derived del pipeline:

| Sistema | Fuente de datos | Consumo |
|---------|-----------------|---------|
| negation reducer | `vocab_meta.blacklist_phrases` | runtime per creator |
| pool auto-extraction | `response_pools` mined | runtime per creator |
| code-switching | langdetect runtime | per mensaje |
| intent-stratified few-shot | mined per (creator, intent) | runtime |
| **Bot Question Analyzer (este PR)** | **`vocab_meta.affirmations`** | **runtime per creator** |

El módulo **nunca** contiene listas preasignadas de palabras por idioma. Todo lo lingüístico se descubre, nada se preasigna.

## 2. Cambios versus el PR anterior

| Aspecto | PR #82 v1 (retirada) | PR #82 v2 (actual) |
|---------|---------------------|---------------------|
| JSON estático `data/vocab/affirmation_vocab.json` | ✅ presente (~70 palabras ES/CA/IT/EN + 9 emojis) | ❌ **eliminado** |
| `_EMBEDDED_AFFIRMATION_WORDS` frozenset literal | ✅ mantenido como fallback | ❌ **eliminado** |
| `AFFIRMATION_WORDS` export backward-compat | ✅ alias al embedded | ❌ **eliminado** (nadie lo importaba en prod) |
| `_load_vocab(creator_id)` propio | ✅ (JSON → embedded) | ❌ reemplazado por reuse |
| Fallback cuando creator sin vocab_meta | ES+CA+IT+EN+emoji listas literales | **solo emojis Unicode convencionales** |
| Fuente de afirmaciones mined | JSON (fake mined) | `services.calibration_loader._load_creator_vocab()` → `personality_docs.vocab_meta.content.affirmations` |
| Métrica Prometheus source label | ❌ | ✅ `vocab_source.{mined,fallback,empty}` |
| Callsite context.py L803 | `is_short_affirmation(message)` | `is_short_affirmation(message, agent.creator_id)` |

## 3. Arquitectura del vocab data-derived

```
┌────────────────────────────────────────────────────────────────────┐
│  personality_docs (DB) — doc_type='vocab_meta'                     │
│  Shape del JSON en content:                                        │
│    {                                                               │
│      "blacklist_words": [...],     (existente)                     │
│      "approved_terms":  [...],     (existente)                     │
│      "blacklist_emojis": [...],    (existente)                     │
│      "approved_emojis":  [...],    (existente)                     │
│      "blacklist_phrases": [...],   (existente)                     │
│      "affirmations": [...]         ← NUEVA KEY consumida por BQA  │
│    }                                                               │
└──────────────────┬─────────────────────────────────────────────────┘
                   │
                   ▼ services.calibration_loader._load_creator_vocab()
                   │  (cache módulo, DB → on-disk fallback)
                   │
                   ▼ core.bot_question_analyzer._load_affirmation_vocab()
                   │  (reusa loader existente + lee key "affirmations")
                   │
                   ▼ is_short_affirmation(msg, creator_id)
                      │
                      ├─ vocab mined presente → _match_against(msg, mined_vocab)
                      │                         + _METRICS["vocab_source.mined"]
                      │
                      └─ vocab vacío o sin creator_id → fallback universal
                                                 (emojis Unicode únicamente)
                                                 + _METRICS["vocab_source.{fallback,empty}"]
```

**Decision trace:**

| Caso | creator_id | vocab mined | Behavior | Metric |
|------|------------|-------------|----------|--------|
| A | `None` | — | solo emoji match | `vocab_source.fallback` |
| B | `"iris"` | DB down / load failed | solo emoji match | `vocab_source.fallback` (via exception path) |
| C | `"stefano"` | `{blacklist_words: [...]}` (sin `affirmations` key) | solo emoji match | `vocab_source.empty` |
| D | `"iris"` | `{affirmations: ["si","vale",...]}` | match contra mined + emoji backstop | `vocab_source.mined` |

## 4. Fallback universal mínimo

**NO hay listas de palabras por idioma en el fallback.** El único backstop son 9 emojis Unicode con semántica convencional cross-cultural:

```python
_UNIVERSAL_AFFIRMATION_EMOJI = frozenset({
    "👍", "👌", "🙌", "✅", "💪", "💯", "👏", "🙏", "🤙",
})
```

**Justificación:** Unicode glyphs no son "vocab por idioma" — son caracteres con significado convencional compartido por la mayoría de culturas que usan digital comms. Si se estimara hardcoding inaceptable, pueden moverse también a `vocab_meta.approved_emojis` en iteración futura.

**Consecuencia operacional:** si un creador no tiene `vocab_meta.affirmations` poblado y el lead responde con "si" / "vale" / "ok" en texto, `is_short_affirmation` devuelve False → `context.py:803` no entra al bloque de detection → `context.py:1396` no inyecta nota. El pipeline sigue funcionando normal, simplemente sin el boost del analyzer. Es degradación graceful, no error.

## 5. Dependencia externa (blocker para activación)

**Este PR no implementa el mining de afirmaciones.** El worker responsable debe poblar `personality_docs.vocab_meta.content.affirmations` con tokens mined del corpus del creator.

### Especificación del worker de mining (fuera de este PR)

```
Input:   DMs + posts + comentarios del creator
Algoritmo:
  1. Filtrar mensajes del lead con length ≤ 15 chars.
  2. En cada conversación, identificar pares (pregunta_bot, respuesta_lead_corta).
  3. Extraer tokens de alta frecuencia en respuestas_lead_corta post-pregunta.
  4. Filtrar con langdetect para validar que el token es afirmativo (no
     pregunta de vuelta, no negación) — usar clasificación sentimental.
  5. Deduplicar, dedup de minúsculas, ordenar por frecuencia.
Output:  list[str] — top-N tokens descubiertos.
Destino: UPSERT personality_docs donde (creator_id, doc_type='vocab_meta').
         Merge con el resto de keys del vocab_meta.
Trigger: onboarding inicial de creator + re-run periódico (semanal) si hay
         nuevos DMs ingeridos.
```

Opciones de implementación:
- Extender `scripts/bootstrap_vocab_metadata.py` con un nuevo parser.
- Crear `services/affirmation_miner.py` dedicado.
- Integrar en el pipeline de `services.creator_auto_provisioner` (cuando se onboard un nuevo creator).

## 6. Métricas Prometheus (observabilidad)

```
bot_question_analyzer_vocab_source{source="mined"}     # vocab_meta hit
bot_question_analyzer_vocab_source{source="empty"}     # creator sin affirmations key
bot_question_analyzer_vocab_source{source="fallback"}  # sin creator_id (edge)

bot_question_analyzer_affirmation{outcome="mined"}          # match via vocab mined
bot_question_analyzer_affirmation{outcome="fallback_emoji"} # match via emoji universal
bot_question_analyzer_affirmation{outcome="punct_only"}     # rejected (BUG-2 guard)
bot_question_analyzer_affirmation{outcome="whitespace"}     # rejected (BUG-1 guard)
bot_question_analyzer_affirmation{outcome="too_long"}       # rejected (>30 chars)
bot_question_analyzer_affirmation{outcome="null"}           # rejected (None/"")

bot_question_analyzer_analyze{type="purchase|payment|booking|interest|information|confirmation|unknown"}
```

Exposición: `get_metrics()` devuelve el `Counter` serializable. Si/cuando se añada `/metrics` endpoint Prometheus, es drop-in. Meanwhile, `logger.info("[BQA_METRICS] %s", get_metrics())` periódicamente da visibilidad grep-based en Railway logs.

**Alertas recomendadas tras activar flag en prod:**
- `vocab_source.mined` debe dominar (≥80% del tráfico con creator_id válido).
- `vocab_source.empty > 0` = creator sin bootstrap → acción requerida.
- Si `affirmation.fallback_emoji / vocab_source.mined > 0.2` → el mining no captura alargamientos/informales del creator → re-run miner.

## 7. Bugs resueltos

| Bug | Severidad | Fix |
|-----|-----------|-----|
| BUG-1 | HIGH | `"   "` → False (guard post-strip) |
| BUG-2 | HIGH | `_PUNCT_ONLY_RE` rechaza `"??"`, `"..."`, `"!!!"` |
| BUG-3 | MED | Emojis afirmación universales en fallback |
| BUG-4 | MED | `_normalize_elongation()` cross-linguistic (no lista) |
| BUG-5 | MED | **Eliminado hardcoding completo** — vocab desde DB |
| BUG-8 | HIGH | Test flag import desde `core.dm.phases.context` |
| BUG-9 | LOW | Singleton lock + double-checked |
| BUG-12 | MED | 15 tests cubriendo vocab_meta paths + fallback + BC |
| BUG-6 (diff) | — | Sin enforcement explicit — si vocab mined incluye "ok" y llega "ok ok", se acepta; reviewer debe decidir si es issue real post-medición |
| BUG-7 | — | Mismo caso que v1: validación empírica en medición |
| BUG-10 | — | Documentado en test |
| BUG-11 | — | Fuera de scope |

## 8. Backward compat — detalle del BC break intencional

| Símbolo | v1 PR | v2 PR (este) | BC impact |
|---------|-------|--------------|-----------|
| `QuestionType` | ✅ | ✅ | Idéntico |
| `BotQuestionAnalyzer` class + métodos | ✅ | ✅ | Idéntico |
| `get_bot_question_analyzer()` | ✅ | ✅ | Idéntico |
| `is_short_affirmation(message)` | ✅ compat | ✅ compat (creator_id opcional) | Identical externo |
| `is_short_affirmation(message, creator_id="...")` | ✅ nuevo | ✅ mismo | Identical externo |
| **`AFFIRMATION_WORDS`** | ✅ exportado | ❌ **eliminado** | BC break intencional |
| `get_metrics()` | ✅ nuevo | ✅ mismo + `vocab_source.*` labels | Additive |
| `reset_metrics()` | ❌ | ✅ nuevo (test helper) | Additive |

**BC break `AFFIRMATION_WORDS` — verificación:**
- `grep -rn "AFFIRMATION_WORDS" --include="*.py"` → 0 matches en prod/tests externos.
- Sólo el test interno `test_13_no_static_vocab_exports` lo referencia, y es un negative test (assert no existe).
- Conclusión: eliminación limpia, cero impacto en importers live.

**Callsite prod (`core/dm/phases/context.py:803`):** 1 línea modificada para propagar `agent.creator_id`. Sin este cambio, el analyzer en prod caería siempre a fallback universal (solo emojis detectados), degradando el valor del sistema. Callsite L1396 intacto (inyección depende de metadata, no necesita creator_id).

## 9. Tests — 15 casos cubriendo paths vocab_meta + fallback + BC

```
test_01 flag exists (core.dm.phases.context)
test_02 singleton thread-safe
test_03 analyze 7 QuestionType semantics universales
test_04 mined vocab from vocab_meta                      ← path principal
test_05 mined + elongation normalization (cross-linguistic)
test_06 mined multi-token ≤3 palabras
test_07 fallback None creator_id → solo emoji            ← zero hardcoding
test_08 fallback empty vocab_meta                        ← pre-bootstrap state
test_09 fallback DB failure → degrada, no crash
test_10 edge cases universales (BUG-1, BUG-2)
test_11 Prometheus source metric 3 labels
test_12 callsite backward compat (legacy 1-arg)
test_13 NO static vocab exports (assert AFFIRMATION_WORDS eliminado)
test_14 confidence threshold 0.7
test_15 statement → INTEREST
```

**Resultado:** 15/15 passed en 0.09s. Audit tests externos (`tests/audit/test_audit_bot_question_analyzer.py`): 5/5 passed.

## 10. Verificación CLAUDE.md

| Check | Resultado |
|-------|-----------|
| AST parse de 3 archivos modificados (module + context + test) | ✅ Passes |
| `pytest tests/unit/test_dm_agent_bot_question.py` | ✅ 15/15 PASS (0.09s) |
| `pytest tests/audit/test_audit_bot_question_analyzer.py` | ✅ 5/5 PASS (0.02s) |
| Callsite prod simulation con 3 estados (None / empty / mined) | ✅ Los 3 escenarios coherentes |
| LOC module ≤ 500 | ✅ 418 |
| Callsite `context.py:803` propaga `agent.creator_id` | ✅ |
| Zero archivos JSON estáticos con vocab por idioma | ✅ |
| Zero listas `{'si','sí','vale',...}` hardcoded en módulo | ✅ |
| `_UNIVERSAL_AFFIRMATION_EMOJI` restringido a ≤15 glyphs universales | ✅ (9 glyphs) |

## 11. Resumen ejecutivo

- **Zero hardcoding lingüístico.** JSON estático eliminado. Vocab viene 100% de `personality_docs.vocab_meta.affirmations` (per-creator, mined).
- **Fallback universal mínimo:** solo emojis Unicode convencionales (9 glyphs). Sin listas por idioma.
- **Reuse de infraestructura existente:** `services.calibration_loader._load_creator_vocab()` ya trae DB→disk fallback + cache → cero duplicación.
- **Callsite actualizado** para propagar `creator_id` a `is_short_affirmation`.
- **Métricas Prometheus** con label `source={mined,fallback,empty}` para monitorear cobertura del mining.
- **Degradación graceful:** si vocab_meta no está poblado, el analyzer no crashea — simplemente no detecta palabras (solo emojis), el pipeline sigue normal.
- **Blocker para activación:** `personality_docs.vocab_meta.affirmations` debe estar poblado para Iris y Stefano antes del arm B del A/B CCEE.
- **BC break intencional:** `AFFIRMATION_WORDS` eliminado (0 importers en prod, verificado con grep).

---

**STOP Phase 5 refactor.**
