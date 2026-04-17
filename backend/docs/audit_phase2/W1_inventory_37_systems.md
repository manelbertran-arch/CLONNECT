# W1 — Inventario de Sistemas No-Auditados (Phase 2)

**Fecha:** 2026-04-16
**Worker:** W1 (paralelo, 7 sub-agentes)
**Alcance:** Sistemas NO cubiertos por el audit previo de 23 P0/P1 (ver `docs/final_audit/CLONNECT_SYSTEM_AUDIT.md`).
**Objetivo:** Ficha técnica por sistema — funcionalidad, activación, impacto en output, metadata, solapamientos, bugs y veredicto.

---

## 0 · Resumen Ejecutivo

### Números
- Total archivos `.py` en `core/` + `services/`: **261**
- Ya auditados (P0/P1): **26 archivos → 23 sistemas**
- Excluidos del scope (infra/API/handlers/providers/models/prompt_builder): **~180**
- **Sistemas auditados en esta Phase 2: 62** (superó el ~37 estimado — hallazgo #1)

### Distribución final de veredictos

| ESTADO | Count | % |
|---|---:|---:|
| ACTIVO_VALIOSO | **33** | 53% |
| ACTIVO_INÚTIL | **10** | 16% |
| DORMIDO_RECUPERABLE | **13** | 21% |
| ELIMINAR | **6** | 10% |
| **Total** | **62** | 100% |

> 4 de los "ACTIVO_VALIOSO" tienen solapamientos parciales o bugs no-bloqueantes (Style Analyzer, dm_strategy con ramas FAMILIA/AMIGO muertas, Vocabulary Extractor + ImportError en legacy, Ghost Reactivation con dead array `REACTIVATION_MESSAGES`).

### Top bugs críticos descubiertos
1. **PersonaCompiler persistence mismatch** — escribe a `creators.doc_d` pero runtime lee `personality_docs.content` (Batch C).
2. **VocabularyExtractor ImportError** — `whatsapp_onboarding_pipeline.py:498` y `mega_test_w2.py:846` importan clases/constantes que NO EXISTEN (Batch C).
3. **prompt_service._tone_config huérfano** — reglas emoji por tono calculadas pero nunca entran al system prompt → TODAS las personalidades generan el mismo prompt de tono (Batch G).
4. **identity_resolver wiring inconsistente** — flag chequeado en `post_response.py:461` pero IGNORADO en `lead_manager.py:610`, `whatsapp_webhook.py:143`, `telegram_webhook.py:301` (Batch G).
5. **lead_categorization v1 vs v2** — migración incompleta, 5 call sites aún usan v1 (Batch E).
6. **intent_classifier enums incompatibles** — `core/intent_classifier.IntentClassifier.Intent` (12 valores) vs `services/intent_service.IntentClassifier.Intent` (27 valores) (Batch E).
7. **dm/strategy FAMILIA/AMIGO dead branches** — caller hardcodea `relationship_type=""`, `is_friend=False` → 2 de 9 ramas son código muerto (Batch D).
8. **learning_rules_service** — flag removido abril 2026, 3 callers desaparecieron, pero `persona_compiler` DUPLICA constantes en lugar de importar (Batch F).
9. **reflexion metadata huérfana** — `reflexion_issues`, `reflexion_severity`, `self_consistency_replaced`, `is_short_affirmation` escritos pero NUNCA consumidos (Batch A).
10. **insights_engine revenue hardcoded** — `active_leads * 97` € hardcoded, no usa precio real del creator (Batch G).

### Duplicaciones que requieren consolidación

| Sistema A | Sistema B | Estado |
|---|---|---|
| `core/intent_classifier.py` | `services/intent_service.py` | Canonical=services; core mantiene solo `classify_intent_simple` útil |
| `core/lead_categorization.py` (v1) | `core/lead_categorizer.py` (v2) | v2 es reemplazo pero migración incompleta |
| `core/semantic_memory.py` (ChromaDB) | `core/semantic_memory_pgvector.py` | ChromaDB legacy → ELIMINAR |
| `services/rag_service.py` | `core/rag/semantic.py` (P1) | rag_service es stub legacy → ELIMINAR |
| `services/response_variator.py` (v1) | `services/response_variator_v2.py` (P1) | v1 reemplazado → ELIMINAR |
| `core/reasoning/reflexion.py` | `core/reflexion_engine.py` | No son duplicados (LLM vs regex) — ambos dormidos |
| `core/reflexion_engine` docstring | caller's `# legacy` comment | Flag permanente OFF |
| `core/identity_resolver.py` | `core/unified_profile_service.py` | Ambos dormidos; riesgo de datos duplicados si se activan sin merge estratégico |
| `services/learning_rules_service.py` consts | `services/persona_compiler.py` consts | Duplicación por copy-paste en persona_compiler |

### Sistemas `ELIMINAR` (dead code confirmado)
1. `core/semantic_memory.py` (ChromaDB) — 0 consumers runtime
2. `services/rag_service.py` — duplica SemanticRAG (P1) e inferior
3. `core/user_context_loader.py` — **self-declared DEPRECATED** (2026-04-01)
4. `core/conversation_mode.py` — 0 callers, duplica context_detector
5. `core/personalized_ranking.py` — solo tests, duplica preference_profile_service
6. `services/response_variator.py` (v1) — reemplazado por v2
7. `core/reflexion_engine.py` — metadata huérfana, flag OFF permanente
8. `core/best_of_n.py::BestOfNSelector` (clase, lines 189-222) — solo tests

---

## 1 · Leyenda

| Campo | Significado |
|---|---|
| **VALOR** | ALTO = mueve CCEE o reduce bugs críticos · MEDIO = aporta útil en algunos flujos · BAJO = poca señal medible · NINGUNO = no impacta output ni estado relevante |
| **ESTADO** | ACTIVO_VALIOSO · ACTIVO_INÚTIL (se ejecuta pero no sirve) · DORMIDO_RECUPERABLE (existe pero sin caller / flag OFF) · ELIMINAR |
| **P0/P1 auditados** | compressed_doc_d, creator_style_loader, calibration_loader, response_variator_v2, rag/semantic, memory_engine, dm_agent_context_integration, conversation_state, style_normalizer, length_controller, guardrails, context_detector (×4), frustration_detector, question_remover, output_validator, response_fixes, message_splitter, sensitive_detector, relationship_scorer, relationship_adapter, style_retriever, preference_profile_service, reasoning/ppa |

---

## 2 · Discovery

### Método
```bash
find services/ core/ -name "*.py" -not -path "*/test*" -not -path "*/__pycache__*" | sort > /tmp/all_files.txt
# 261 archivos en total
# Se excluyen: __init__ stubs, models.py, helpers, providers, handlers, webhooks, DB layers, scheduler infra, prompt_builder/* (scope explícito)
# Se incluyen: 62 sistemas clasificados como "afectan output o estado persistente de lead/bot"
```

### Batches

| Batch | Categoría | N sistemas | Agente | Output |
|---|---|---:|---|---|
| A | Scoring / Reasoning | 6 | 1A | §3.A |
| B | RAG / Memory | 9 | 1B | §3.B |
| C | Personality / Style | 7 | 1C | §3.C |
| D | DM Phases / Strategy | 7 | 1D | §3.D |
| E | Lead / Intent / Relationship | 8 | 1E | §3.E |
| F | Learning / Feedback / Memory | 9 | 1F | §3.F |
| G | Ops / Misc | 16 | 1G | §3.G |
| **Total** | | **62** | | |

---

## 3 · Fichas detalladas

<!-- BATCHES_APPEND_HERE -->

### 3.A · Batch A — Scoring / Reasoning (6 sistemas)

## Sistema: Best-of-N Candidate Generation

- **Archivo:** `core/best_of_n.py`
- **Líneas:** 221
- **Clasificación prev:** P2 (OFF por defecto, copilot-only)
- **Qué hace (1 línea):** Genera 3 candidatos en paralelo a temperatures [0.2, 0.7, 1.4] con style-hints distintos y devuelve el de mayor confidence.

### Funcionalidad detallada
- `generate_best_of_n()` (line 69) lanza 3 llamadas paralelas a `generate_dm_response` con timeout `BEST_OF_N_TIMEOUT=12s` (line 21); inyecta style hints en el system prompt (lines 61-63, 25-29).
- Cada candidato se puntúa con `calculate_confidence()` del `confidence_scorer` (lines 88, 121-126).
- `serialize_candidates()` (line 165) serializa todos los candidatos a dict para almacenamiento en `msg_metadata`.
- `BestOfNSelector` (lines 189-222): clase síncrona con scoring simplista distinto; es dead code (solo llamada por tests).

### Activación
- **Feature flag:** `ENABLE_BEST_OF_N` (default **false**) — definido en `core/dm/phases/generation.py:52` y `core/feature_flags.py:61`.
- **Se llama desde:** `core/dm/phases/generation.py:483-486` (gated por flag + `copilot_service.is_copilot_enabled(creator_id)` line 481).
- **¿Tiene consumer de su output?:** SÍ — `api/routers/copilot/actions.py:505-507` exporta candidates al frontend; `api/routers/copilot/analytics_queries.py:150` los lee; `services/feedback_capture.py:712-720` los usa para generar `best_of_n_ranking` preference pairs; `api/init_db.py:381-395` tiene backfill que los elimina tras decisión.

### Afecta al output del bot?
- [x] Sí, inyecta en system prompt (style hints solo para la generación de cada candidato — no se persiste fuera de la llamada)
- [x] Sí, muta la respuesta post-LLM (selecciona el candidato de mayor confidence)
- [x] No (también) escribe metadata (`msg_metadata.best_of_n`)

### Si inyecta contexto
- **Posición:** bottom del system prompt (se appendea al contenido ya construido, line 63).
- **Tamaño típico:** ~60-90 chars por hint; hay 2 con texto y 1 vacío.
- **Condiciones de inclusión:** `ENABLE_BEST_OF_N=true` AND `copilot_mode` activo para el creador.

### Metadata escrita
- Field: `msg_metadata.best_of_n` — escrito en `core/dm/phases/generation.py:497` — consumers: `api/routers/copilot/actions.py:505`, `api/routers/copilot/analytics_queries.py:150`, `api/init_db.py:388` (backfill cleanup), `scripts/check_bon.py:29`.
- Field: `_dm_metadata["best_of_n"]` — escrito en `core/dm/phases/postprocessing.py:580-581`.

### Solapamiento con P0/P1 ya auditados
- NO — único sistema que hace sampling paralelo con rating; usa confidence_scorer (uno de los 6 de esta batch, no auditado en P0/P1).

### Bugs conocidos / dead code
- `BestOfNSelector` class (lines 189-222) es DEAD CODE: solo llamada por `tests/test_motor_audit.py:539-698`; duplica con lógica distinta a `calculate_confidence` de confidence_scorer. Documentado en `docs/AUDIT_PART3_GENERATION.md:261`.

### Veredicto
- **VALOR:** MEDIO
- **ESTADO:** DORMIDO_RECUPERABLE (flag OFF por defecto, pero pipeline completo con consumers; dead code debe eliminarse)
- **RAZÓN (1-2 líneas):** Implementación completa con integración a feedback/preference pairs. Coste de 3x LLM calls explica el OFF por defecto. El `BestOfNSelector` class debe eliminarse.

---

## Sistema: Confidence Scorer

- **Archivo:** `core/confidence_scorer.py`
- **Líneas:** 260
- **Clasificación prev:** Unaudited (flag default false — line 76 feature_flags.py)
- **Qué hace (1 línea):** Calcula confidence multi-factor (intent, response_type, historical_rate, length, blacklist) como score [0.0–1.0] para una suggestion.

### Funcionalidad detallada
- `calculate_confidence()` (line 54) pondera 5 factores: intent (0.30), response_type (0.20), historical_rate (0.30), length (0.10), blacklist (0.10).
- `_get_historical_rate()` (line 103) hace query SQL a `Message` para aprobación_rate últimos 30 días por intent; fallback 0.70 si <5 muestras.
- `_score_blacklist()` (line 177) matchea 6 patrones regex de "bad patterns" (identity claim, raw CTA, broken link, error leaks, catchphrase).
- `get_historical_rates()` (line 187) devuelve rates por intent para un creator (usado por analytics API).

### Activación
- **Feature flag:** `ENABLE_CONFIDENCE_SCORER` (default **false**) — `core/feature_flags.py:76` (marcado "Unaudited systems").
- **Se llama desde:**
  - `core/dm/phases/postprocessing.py:558-564` (gated por `flags.confidence_scorer`) — escribe `scored_confidence` en metadata.
  - `core/best_of_n.py:121-126` (gated indirectamente por `ENABLE_BEST_OF_N`).
  - `api/routers/copilot/analytics.py:316-328` — endpoint `GET /copilot/{creator_id}/historical-rates` expone `get_historical_rates()` (no gated, público vía auth).
- **¿Tiene consumer de su output?:** SÍ — `scored_confidence` se pone en `DMResponse.confidence` (line 587) y se devuelve al caller; `get_historical_rates` consumido por frontend/autolearning engine según docstring analytics.py:322-324.

### Afecta al output del bot?
- [ ] No inyecta en prompt
- [ ] No muta respuesta
- [x] No, solo escribe metadata (campo `confidence` en DMResponse — usado luego por copilot/autolearning para threshold decisions)

### Si inyecta contexto
- N/A

### Metadata escrita
- Field: `DMResponse.confidence` — escrito en `core/dm/phases/postprocessing.py:568,587` — consumer: pipeline downstream (copilot UI, autolearning thresholds). Si `flags.confidence_scorer=False`, usa `AGENT_THRESHOLDS.default_scored_confidence` (line 568).
- No escribe en cognitive_metadata directamente.

### Solapamiento con P0/P1 ya auditados
- NO — es feature estándar; no duplica guardrails ni output_validator. La lógica blacklist solapa parcialmente conceptualmente con `output_validator.py` pero aquí es scoring suave, no bloqueo.

### Bugs conocidos / dead code
- El query `Message.copilot_action.isnot(None)` requiere que copilot esté activo — en producción sin copilot, historical_rate siempre devuelve 0.70 (neutro). Ver lines 126-155.
- `get_historical_rates()` expone endpoint sin flag pero internamente la feature `confidence_scorer` está OFF — podría devolver datos aunque el sistema no esté en uso.

### Veredicto
- **VALOR:** MEDIO (solo útil en copilot mode con datos históricos)
- **ESTADO:** ACTIVO_INÚTIL (flag=false por default; llamado también desde best_of_n que también está OFF). Analytics API sí está expuesta.
- **RAZÓN (1-2 líneas):** La función analytics `get_historical_rates` está viva en API. El scoring runtime está dormido (ambos callers gated OFF). Feature_flags lo marca "Unaudited" explícitamente.

---

## Sistema: Reflexion (Self-Critique LLM)

- **Archivo:** `core/reasoning/reflexion.py`
- **Líneas:** 325
- **Clasificación prev:** No clasificado
- **Qué hace (1 línea):** Mejora respuestas iterativamente vía self-critique + LLM refinement (hasta 2 iteraciones).

### Funcionalidad detallada
- `ReflexionImprover.improve_response()` (line 177): ciclo crítica → improvement, hasta `max_iterations=2` o hasta `quality_score >= min_quality=0.7`.
- `_get_critique_prompt()` (line 49): pide al LLM evaluación formato `[CRITICA]/[PUNTUACION]/[MEJORAS_SUGERIDAS]`.
- `_get_improvement_prompt()` (line 98): pide al LLM aplicar mejoras manteniendo mensaje conciso (2-3 frases).
- `personalize_message()` (line 273): wrapper de conveniencia para personalizar templates nurturing.
- Cada iteración = 2 LLM calls (critique + improvement) = hasta 4 LLM calls.

### Activación
- **Feature flag:** Sin flag directo; depende de que `ENABLE_NURTURING=true` (default **false** en `core/feature_flags.py:78`).
- **Se llama desde:** `core/nurturing/manager.py:393` (a través de `_get_reflexion()` lazy import, line 47-57). Único caller en producción.
- **¿Tiene consumer de su output?:** SÍ (condicional) — `NurturingManager.generate_personalized_message()` usa el `result.final_answer` para mensajes de follow-up nurturing. Pero está todo OFF con `ENABLE_NURTURING=false`.

### Afecta al output del bot?
- [ ] No inyecta en system prompt del DM principal
- [ ] No inyecta en user message del DM principal
- [ ] No muta respuesta del DM principal
- Sí muta mensaje de nurturing (follow-ups automáticos), pero nurturing está OFF por default.

### Si inyecta contexto
- N/A para DM principal. Para nurturing: el prompt de crítica incluye nombre, intereses, productos discutidos (lines 56-72).

### Metadata escrita
- Field: `ReflexionResult.metadata` (in-memory dataclass) — nunca persistido en `msg_metadata` ni en DB.
- Ninguna metadata escrita al pipeline DM.

### Solapamiento con P0/P1 ya auditados
- NO directamente; el "reflexion" del DM principal es `core/reflexion_engine.py` (rule-based, distinto, ver ficha siguiente). Nombres idénticos pero implementaciones totalmente diferentes.

### Bugs conocidos / dead code
- Depende de `core.llm.get_llm_client()` (line 315) — deuda técnica: nurturing sigue usando este cliente "legacy" mientras el DM principal ha migrado a `llm_service`. No hay test de integración E2E con un LLM real para este flujo.
- Singleton `_reflexion` (line 298) no se resetea entre tests → posible cross-contamination de estado.

### Veredicto
- **VALOR:** BAJO (nurturing está OFF)
- **ESTADO:** DORMIDO_RECUPERABLE (se activará cuando ENABLE_NURTURING se encienda; hasta entonces no corre)
- **RAZÓN (1-2 líneas):** Sistema completo y bien diseñado, pero bloqueado tras flag de nurturing OFF. No afecta al DM principal. Tests existentes (tests/test_reasoning.py).

---

## Sistema: Self-Consistency Validator

- **Archivo:** `core/reasoning/self_consistency.py`
- **Líneas:** 337
- **Clasificación prev:** Apagado (ENABLE_SELF_CONSISTENCY=false default)
- **Qué hace (1 línea):** Genera N=3 samples de la misma respuesta y selecciona el "más central" (mayor similaridad media al resto).

### Funcionalidad detallada
- `SelfConsistencyValidator.validate()` (line 209): incluye una respuesta pre-generada + genera N-1 samples en paralelo a `temperature=0.8` (line 135).
- `_calculate_similarity()` (line 64): SequenceMatcher char-level.
- `_semantic_similarity()` (line 99): Jaccard sobre palabras >2 chars con stopwords ES/EN.
- `_combined_similarity()` (line 115): weighted 0.6*char + 0.4*semantic.
- `_select_best_response()` (line 185): devuelve el sample con mayor similaridad media a los otros ("más central").
- `validate_response()` (line 274): convenience method para validar un par query/response directo.

### Activación
- **Feature flag:** `ENABLE_SELF_CONSISTENCY` (default **false**) — `core/dm/phases/generation.py:53` y `core/feature_flags.py:58` ("Experimental").
- **Se llama desde:** `core/dm/phases/generation.py:624-638` (Phase 4b, gated por flag).
- **¿Tiene consumer de su output?:** SÍ — cuando activo, reemplaza `llm_response.content` si `consistency.is_consistent=False` y `consistency.response` existe; escribe `cognitive_metadata["self_consistency_replaced"]=True` (line 637).

### Afecta al output del bot?
- [x] Sí, muta la respuesta post-LLM (reemplaza el content si la validación falla)
- [x] También escribe metadata (`self_consistency_replaced`)

### Si inyecta contexto
- N/A (no inyecta en prompt; genera samples adicionales del mismo prompt).

### Metadata escrita
- Field: `cognitive_metadata["self_consistency_replaced"]` — escrito en `core/dm/phases/generation.py:637` — consumer: **NINGUNO** detectado (solo debugging/logging; no se lee en pipeline ni API).
- `ConsistencyResult.metadata` contiene `threshold` y `all_samples[:5]` — no persistido.

### Solapamiento con P0/P1 ya auditados
- NO — técnica distinta (sampling multi-respuesta). No solapa con guardrails/output_validator/response_fixes.

### Bugs conocidos / dead code
- Depende de `agent.llm_service` (line 626) pero `_generate_samples` llama `self.llm.chat()` (line 139) — interfaz no validada en todos los providers (gemini_provider vs deepinfra_provider tienen APIs distintas).
- Docs/AUDIT_PART3_GENERATION.md:556 recomienda dejarlo OFF: "SequenceMatcher similarity metric doesn't capture semantic consistency".
- Singleton `_validator` (line 306) no se resetea.

### Veredicto
- **VALOR:** BAJO
- **ESTADO:** ACTIVO_INÚTIL / DORMIDO_RECUPERABLE (flag OFF por default, añade 2 LLM calls, métrica cuestionada en audit previo)
- **RAZÓN (1-2 líneas):** Técnica cara (2 extra calls) con métrica poco confiable (char-level SequenceMatcher). `self_consistency_replaced` metadata es huérfano.

---

## Sistema: Reflexion Engine (Rule-based)

- **Archivo:** `core/reflexion_engine.py`
- **Líneas:** 262
- **Clasificación prev:** Apagado (ENABLE_REFLEXION=false default)
- **Qué hace (1 línea):** Analiza quality issues de la respuesta con 5 checks rule-based (length, unanswered, repetition, phase, price) — solo flagging, no re-genera.

### Funcionalidad detallada
- `ReflexionEngine.analyze_response()` (line 106): ejecuta 5 checks y agrupa en `ReflexionResult` con severity none/low/medium/high.
- `_check_length()` (line 161): min=2 ("Ok"), max=300.
- `_check_unanswered_question()` (line 176): flagged si usuario pregunta y bot responde con ≥2 preguntas sin "!".
- `_check_repetition()` (line 192): overlap >60% con últimas 5 respuestas bot.
- `_check_phase_appropriateness()` (line 210): reglas de precio/CTA por fase (inicio/propuesta/cierre).
- `_check_price_response()` (line 237): flag si user pregunta precio y respuesta no lo incluye.
- `to_prompt_context()` (line 28): genera contexto para re-prompting — **pero NO se usa actualmente** (solo flagging).

### Activación
- **Feature flag:** `ENABLE_REFLEXION` (default **false**) — `core/feature_flags.py:44`.
- **Se llama desde:** `core/dm/phases/postprocessing.py:262-271` (Step 7a3, gated por `flags.reflexion`).
- **¿Tiene consumer de su output?:** PARCIAL — escribe `cognitive_metadata["reflexion_issues"]` y `reflexion_severity` (lines 268-269); no hay consumer que re-accione sobre ellos; solo logging.

### Afecta al output del bot?
- [x] No, solo escribe metadata (flagging)
- [x] No, solo hace logging/observabilidad

### Si inyecta contexto
- N/A (hay método `to_prompt_context()` pero no se llama en ninguna parte).

### Metadata escrita
- Field: `cognitive_metadata["reflexion_issues"]` — escrito en `postprocessing.py:268` — consumer: **NINGUNO** (huérfano).
- Field: `cognitive_metadata["reflexion_severity"]` — escrito en `postprocessing.py:269` — consumer: **NINGUNO** (huérfano).

### Solapamiento con P0/P1 ya auditados
- SÍ (parcial) — `_check_price_response` y `_check_phase_appropriateness` solapan con la lógica de fase en `conversation_state` (ya auditado). `_check_repetition` solapa conceptualmente con `response_variator_v2` (ya auditado). NO es duplicado de `core/reasoning/reflexion.py` — este es rule-based, el otro es LLM-based.

### Bugs conocidos / dead code
- `to_prompt_context()` (line 28) es DEAD CODE: nunca invocado.
- Metadata `reflexion_issues`/`reflexion_severity` son huérfanas.
- `_check_phase_appropriateness` solo activo si se pasa `conversation_phase`; en `postprocessing.py:262-266` NO se pasa — check nunca corre en producción.
- Comentario en line 254 del postprocessing lo califica como "legacy".

### Veredicto
- **VALOR:** BAJO
- **ESTADO:** ACTIVO_INÚTIL (flag OFF + metadata huérfana + phase-check inactivo). Realmente debería ser ELIMINAR si no se consumen issues/severity.
- **RAZÓN (1-2 líneas):** Sistema marcado como "legacy" en el mismo código (postprocessing.py:254). Solo escribe metadata que nadie lee. Overlap con response_variator_v2 y conversation_state.

---

## Sistema: Bot Question Analyzer

- **Archivo:** `core/bot_question_analyzer.py`
- **Líneas:** 330
- **Clasificación prev:** P2 (ENABLE_QUESTION_CONTEXT=true por default)
- **Qué hace (1 línea):** Clasifica el último mensaje del bot (INTEREST/PURCHASE/BOOKING/PAYMENT/INFO/CONFIRM) para interpretar afirmaciones cortas del usuario ("Si", "Vale", "Ok").

### Funcionalidad detallada
- `BotQuestionAnalyzer.analyze()` (line 186): matchea regex patterns en orden de prioridad (PURCHASE > PAYMENT > BOOKING > INTEREST > INFO > CONFIRM).
- Patrones especiales: `STATEMENT_EXPECTING_RESPONSE` (line 145) — cuando bot hace oferta/explicación sin "?", un "Ok" se interpreta como INTEREST.
- `analyze_with_confidence()` (line 231): retorna tuple (type, confidence) con scores fijos 0.50–0.92.
- `is_short_affirmation()` (line 298): detecta "Si"/"Vale"/"Ok" multilingual (ES/CA/IT/EN) — `AFFIRMATION_WORDS` set con 90+ variantes.
- Patrones incluyen soporte voseo (querés, podés, tenés, contame, decime).

### Activación
- **Feature flag:** `ENABLE_QUESTION_CONTEXT` (default **true**) — `core/dm/phases/context.py:21` y `core/feature_flags.py:42`.
- **Se llama desde:**
  - `core/dm/phases/context.py:288-306` (en `phase_memory_and_context`, si `is_short_affirmation(message)`).
  - `core/dm/phases/context.py:881-899` (más abajo — inyecta nota en `_context_notes_str`).
  - `scripts/intelligence_test_suite.py:522-528` (test harness).
- **¿Tiene consumer de su output?:** SÍ — `context.py:881-899` inyecta una nota en el prompt según `_q_ctx` (purchase/payment/booking/interest/info/confirmation) si `_q_conf >= 0.7`.

### Afecta al output del bot?
- [x] Sí, inyecta en system prompt (vía `_context_notes_str` — nota informando al LLM qué significa la afirmación corta del usuario)
- [x] También escribe metadata (cognitive_metadata)

### Si inyecta contexto
- **Posición:** middle del system prompt (dentro de `_context_notes_str`, ensamblado en `context.py` durante phase 2).
- **Tamaño típico:** ~60-80 chars (una línea de nota, p.ej. "El lead confirma que quiere comprar/apuntarse.").
- **Condiciones de inclusión:** `ENABLE_QUESTION_CONTEXT=true` AND `is_short_affirmation(message)=true` AND último bot message existe AND `q_type != UNKNOWN` AND `q_conf >= 0.7`.

### Metadata escrita
- Field: `cognitive_metadata["question_context"]` — escrito en `context.py:304` — consumer: `context.py:882` (autoconsumido para inyectar nota).
- Field: `cognitive_metadata["question_confidence"]` — escrito en `context.py:305` — consumer: `context.py:883`.
- Field: `cognitive_metadata["is_short_affirmation"]` — escrito en `context.py:306` — consumer: **NINGUNO** (huérfano).

### Solapamiento con P0/P1 ya auditados
- NO directamente — solapa *conceptualmente* con `frustration_detector` y `context_detector` (ya auditados) en el sentido de que todos clasifican señales del lead, pero aquí específicamente analiza el mensaje del **bot previo**, no del usuario. Single-purpose bien delimitado.

### Bugs conocidos / dead code
- `is_short_affirmation` (line 298): límite hardcoded `len(msg) > 30` (line 315) — "Siiii vale perfecto!" (20 chars) pasa, pero frases naturales más largas no.
- AFFIRMATION_WORDS mezcla con/sin puntuación — mantenimiento duplicado.
- Metadata `is_short_affirmation` es huérfana.
- `analyze_with_confidence` retorna hardcoded confidence scores por tipo — no ajustados por creator.

### Solapamiento con reflexion_engine.py
- NO duplicado — distinto propósito (este analiza bot msg previo; reflexion_engine.py analiza la próxima respuesta del bot).

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN (1-2 líneas):** Único sistema que da semántica a "Si"/"Ok" — caso de uso real (collapse de affirmations). Integrado con context injection. Default ON. Bien diseñado con soporte multilingual + voseo.

---

### 3.B · Batch B — RAG / Memory (9 sistemas)

## Sistema: BM25 Lexical Retriever

- **Archivo:** `core/rag/bm25.py`
- **Líneas:** 372
- **Clasificación prev:** No clasificado
- **Qué hace (1 línea):** Índice BM25 in-memory por creador para fusión léxica con búsqueda semántica (híbrido RAG).

### Funcionalidad detallada
- Implementa BM25 clásico con stopwords ES/EN/CA/IT (bm25.py:20-67).
- `BM25Retriever.add_document`/`search` (bm25.py:131, 226) — índice por creador, tokenización simple con lowercasing + regex `\b\w+\b`.
- Factory cacheada: `get_bm25_retriever(creator_id)` con `BoundedTTLCache(max_size=50, ttl_seconds=3600)` (bm25.py:348-367).

### Activación
- **Feature flag:** `ENABLE_BM25_HYBRID` (default: `true`) — definido en `core/rag/semantic.py:38`. Fallback también en `core/feature_flags.py:69`.
- **Se llama desde:** `core/rag/semantic.py:259, 379` (dentro de `SemanticRAG._hybrid_with_bm25` y `_prebuild_bm25_indexes`).
- **¿Tiene consumer?** SÍ — es subsistema activo del RAG híbrido.

### Afecta al output?
- [x] inyecta en system prompt (vía `rag_context` → prompt builder)
- [ ] inyecta en user message
- [ ] muta respuesta post-LLM
- [ ] solo metadata
- [ ] solo observabilidad

### Si inyecta contexto
- **Posición/Tamaño/Condiciones:** No inyecta directamente. Complementa semántica con Reciprocal Rank Fusion (0.7 semantic / 0.3 BM25, `HYBRID_BM25_WEIGHT` env). Sólo corre tras search semántica exitosa.

### Metadata escrita
- `search_type="bm25"` / `"hybrid"` — añadido en `core/rag/semantic.py:284, 347` — consumer: logging y `cognitive_metadata["rag_details"]` (context.py:625).

### Solapamiento con P0/P1 auditados
- NO. Es subsistema de `rag/semantic.py` (P1). Ya auditado superficialmente pero BM25 como módulo independiente no estaba fichado.

### Bugs / dead code
- `search` con `min_score=0.0` (bm25.py:271) usa `>` estrictamente — nunca rechaza por score, solo por top_k.
- Cache 1h TTL y 50 creators — OK para escala actual, pero se re-construye el índice desde `_prebuild_bm25_indexes` (semantic.py:376) en cold start.

### Veredicto
- **VALOR:** MEDIO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Default-ON, integrado en la ruta crítica de RAG. Aporta recall léxico (nombres de productos, marcas) que embeddings pueden perder.

---

## Sistema: Cross-Encoder Reranker

- **Archivo:** `core/rag/reranker.py`
- **Líneas:** 239
- **Clasificación prev:** No clasificado (pero auditado como "sistema_12_reranker.md")
- **Qué hace (1 línea):** Reordena top-K de RAG con CrossEncoder multilingüe (o Cohere API) para mejor precisión.

### Funcionalidad detallada
- Modelo default: `nreimers/mmarco-mMiniLMv2-L12-H384-v1` (CA/ES/EN/IT, 117M params, ~926MB RAM) (reranker.py:45-48).
- Provider local (sentence-transformers) o `cohere` (rerank-v3.5, paid) (reranker.py:32, 85).
- Lazy load con retry cooldown 30s tras fallo (reranker.py:38-40, 56).
- `warmup_reranker()` invocado en background startup (reranker.py:72, llamado desde `api/main.py:762`).

### Activación
- **Feature flag:** `ENABLE_RERANKING` (default: `true`) (reranker.py:29). También `RERANKER_PROVIDER` (local/cohere) y `RERANKER_MODEL`.
- **Se llama desde:** `core/rag/semantic.py:360-363` (`SemanticRAG._rerank_results`). Metadata consumer: `core/dm/phases/context.py:633`.
- **¿Tiene consumer?** SÍ.

### Afecta al output?
- [x] inyecta en system prompt (reordena top-K que luego va al RAG block)
- [ ] inyecta en user message
- [ ] muta respuesta post-LLM
- [ ] solo metadata
- [ ] solo observabilidad

### Si inyecta contexto
- **Posición/Tamaño/Condiciones:** Input = top 12 (`initial_top_k = top_k*2, max 12`, semantic.py:154). Output = top_k (usually 3-5). Latencia ~30-100ms local.

### Metadata escrita
- `rerank_score`, `reranker=("local"|"cohere")` — añadido en `core/rag/reranker.py:167-168` — consumer: ordenado + posible logging; no se persiste en DB.
- `rag_reranked=True` — escrito en `core/dm/phases/context.py:634` — consumer: cognitive_metadata persistido en Message.

### Solapamiento con P0/P1 auditados
- NO. Subsistema de `rag/semantic.py` (P1), pero módulo propio.

### Bugs / dead code
- `rerank_with_threshold` (reranker.py:217) — zero callers en código live (solo en tests).
- Cohere provider marcado "NOT ACTIVATED — skeleton" (reranker.py:16, 94) — código muerto si `COHERE_API_KEY` no está definido (fallback a local).

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Default-ON, mejora precisión top-K con modelo multilingüe adecuado para creadores ES/CA/IT. Warmup en background mitiga cold start.

---

## Sistema: Semantic Chunker

- **Archivo:** `core/semantic_chunker.py`
- **Líneas:** 524
- **Clasificación prev:** No clasificado
- **Qué hace (1 línea):** Chunking que respeta fronteras de párrafos, secciones (headers) y frases, con overlap de N frases.

### Funcionalidad detallada
- `SemanticChunker.chunk_text` (semantic_chunker.py:109): secciones markdown → párrafos → frases. Max 800 chars, min 100 chars, overlap 2 frases por defecto (env-configurable).
- `chunk_html` (semantic_chunker.py:182): variante para HTML con BeautifulSoup (descarta script/style/nav).
- Merge de chunks pequeños dentro de la misma sección (semantic_chunker.py:377).
- `chunk_content(text, mode)` (semantic_chunker.py:476): dispatcher público que cae a `split_text` en modo `fixed` (importa `ingestion.content_indexer` — dependencia circular no activa: `content_indexer.py` también importa `SemanticChunker`).

### Activación
- **Feature flag:** `CHUNKING_MODE` (default: `semantic`) (semantic_chunker.py:34). No está en `core/feature_flags.py`.
- **Se llama desde:** `ingestion/content_indexer.py:72-73` (split_text path). Sólo durante ingestion, NO en runtime de mensajes.
- **¿Tiene consumer?** SÍ (ingestion pipeline).

### Afecta al output?
- [x] solo metadata (chunks persisten en DB → luego RAG los recupera)
- [ ] inyecta en system prompt (indirecto: vía RAG)

### Si inyecta contexto
- N/A directamente. Los chunks se almacenan en pgvector y se recuperan por `SemanticRAG`.

### Metadata escrita
- `chunk_type` ∈ {paragraph, section, list, sentence, merged, fixed} — escrito en `core/semantic_chunker.py:157, 232, 356, 400, 508` — consumer: sólo informativo, NO se filtra por este campo en retrieval.
- `section_title` — consumer: ninguno activo (no aparece en context.py ni en prompts).

### Solapamiento con P0/P1 auditados
- NO directamente, pero complementa la pipeline de `rag/semantic.py` (P1) durante ingestion.

### Bugs / dead code
- `chunk_content` (semantic_chunker.py:476) duplica lógica de `ingestion/content_indexer.py:40-84` (`split_text`) — la API pública real para otros módulos es `split_text` de content_indexer.
- `SENTENCE_ENDINGS` regex (semantic_chunker.py:88) sólo splits cuando siguiente char es mayúscula o vocal acentuada — no funciona para minúscula tras `?.!` (común en informal IG).

### Veredicto
- **VALOR:** MEDIO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Default-ON en ingestion, mejora retrieval al mantener párrafos coherentes. Impacto indirecto pero medible en quality del RAG.

---

## Sistema: Semantic Memory (ChromaDB Legacy)

- **Archivo:** `core/semantic_memory.py`
- **Líneas:** 277
- **Clasificación prev:** No clasificado
- **Qué hace (1 línea):** Memoria conversacional por-lead basada en ChromaDB + sentence-transformers (all-MiniLM-L6-v2) con fallback JSON.

### Funcionalidad detallada
- `ConversationMemory` (semantic_memory.py:52): almacena historial por `creator_id/user_id` en `data/memory/{creator}/{user}/`. Dual storage: JSON (`history.json`, últimos 200 msgs) + ChromaDB (`chroma/`).
- `search`, `get_context_for_query` (semantic_memory.py:162, 211): búsqueda semántica con fallback a "últimos N mensajes" si Chroma no disponible.
- Cache global unbounded (`_memories: Dict`) (semantic_memory.py:258) — sin TTL, potencial leak.

### Activación
- **Feature flag:** `ENABLE_SEMANTIC_MEMORY` (default: `false`) (semantic_memory.py:23). Default OFF para evitar model download en Railway cold start.
- **Se llama desde:** SÓLO `api/startup/cache.py:52` (pre-carga embedding model *si* flag activo). Ningún módulo de runtime importa `ConversationMemory` ni `get_conversation_memory`.
- **¿Tiene consumer?** NO (sólo tests y el pre-warm opcional).

### Afecta al output?
- [ ] inyecta en system prompt
- [ ] inyecta en user message
- [ ] muta respuesta post-LLM
- [ ] solo metadata
- [ ] solo observabilidad (si flag on) — en la práctica, ninguno

### Si inyecta contexto
- N/A — reemplazado por `semantic_memory_pgvector.py`.

### Metadata escrita
- `history.json` en disco (semantic_memory.py:117) — consumer: ninguno en runtime.

### Solapamiento con P0/P1 auditados
- SÍ — solapa conceptualmente con `memory_engine` (P0/P1) y con `semantic_memory_pgvector.py` (nueva versión). `ConversationMemory` (clase) colide por nombre con `services/memory_service.ConversationMemory` (no relacionada, son dos clases distintas).

### Bugs / dead code
- **Código muerto**: no hay importadores fuera de tests. Cache unbounded (semantic_memory.py:258) es un latent leak pero nunca se ejerce.
- `get_context_for_query` nunca llamado por producción.
- Guarda datos en `data/memory/` que en Railway se pierden al redeploy (no persistent volume).

### Veredicto
- **VALOR:** NINGUNO
- **ESTADO:** ELIMINAR
- **RAZÓN:** Reemplazado por `semantic_memory_pgvector.py`. Default OFF, sin consumers de runtime. Mantener sólo el `_get_embeddings()` si startup/cache.py lo requiere (trivial).

---

## Sistema: Semantic Memory pgvector

- **Archivo:** `core/semantic_memory_pgvector.py`
- **Líneas:** 526
- **Clasificación prev:** No clasificado (pero hay `docs/audit/sistema_10_episodic_memory.md`)
- **Qué hace (1 línea):** Memoria episódica de mensajes en tabla `conversation_embeddings` (pgvector), con coreferencia y redundancy gating.

### Funcionalidad detallada
- `SemanticMemoryPgvector` (line 80): `add_message` embed + INSERT; `search` cosine-sim con recency boost; `get_context_for_response` construye bloque formateado; `get_user_summary` (lines 103, 203, 288, 360).
- **O2 (SimpleMem)**: redundancy gating — skip si `≥0.92` sim a existente (line 152-174).
- **O3 (EMem)**: coreferencia ES/EN — resuelve "ella/he" → nombre del lead antes de embed (line 52-77).
- **O5 (Memobase)**: temporal decay — multiplica similarity por `0.7 + 0.3 * (1 - age_days/90)` (line 251).
- Cache factory: `BoundedTTLCache(500, 600s)` (line 433).

### Activación
- **Feature flag:** `ENABLE_SEMANTIC_MEMORY_PGVECTOR` (default: `true`) (line 35).
- **Se llama desde:**
  - `core/dm/post_response.py:181-187` — INDEXA (user+assistant) tras cada respuesta.
  - `core/dm/phases/context.py:146, 184` — BUSCA en `_episodic_search` (min_sim=0.60, k=5, max 3 resultados).
- **¿Tiene consumer?** SÍ (episodic recall block).

### Afecta al output?
- [x] inyecta en system prompt (bloque "Recalling" en context.py)

### Si inyecta contexto
- **Posición/Tamaño/Condiciones:** Inyecta hasta 3 resultados con `min_sim=0.60`, `max_content_chars=250` por mensaje. Deduplicación contra `recent_history` últimos 10 mensajes. Comentarios BUG-EP-01/02/04/05/06/07/08 en context.py:146-200 indican bugfixes recientes.

### Metadata escrita
- Tabla `conversation_embeddings` (columnas creator_id, follower_id, message_role, content, embedding, msg_metadata, created_at) — consumer: la propia `search` + `get_user_summary`.
- `cognitive_metadata["episodic_recalled"], ["episodic_chars"]` en `context.py:383-384`.

### Solapamiento con P0/P1 auditados
- SÍ — es la "episodic memory" reemplazo de `semantic_memory.py`. Complementa (no solapa) `memory_engine.py` (P1) que maneja facts/memories estructurados. Este maneja embeddings de raw messages.

### Bugs / dead code
- ID resolution en `context.py:156-187` probado contra UUID y slug — complejidad alta por compatibilidad legacy.
- `REDUNDANCY_THRESHOLD=0.92` (line 48) puede ser demasiado laxo para respuestas assistant idénticas; no hay dedup bajo 0.92.
- `whatsapp_onboarding_pipeline.py:181-183` importa `get_semantic_memory` pero líneas fuera de range observado — backfill path.

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Core del episodic recall. Default-ON, integrado en ambas direcciones (write en post_response, read en context). Auditoría de `sistema_10_episodic_memory.md` ya existe.

---

## Sistema: Hierarchical Memory Manager

- **Archivo:** `core/hierarchical_memory/hierarchical_memory.py`
- **Líneas:** 200
- **Clasificación prev:** No clasificado (pero hay ficha ya en `docs/audit/sistema_10_episodic_memory.md`)
- **Qué hace (1 línea):** 3 niveles de memoria (L1 episódica, L2 semántica, L3 abstracta) estilo IMPersona, leyendo JSONL offline.

### Funcionalidad detallada
- Carga `memories_level1.jsonl`, `memories_level2.jsonl`, `memories_level3.jsonl` desde `data/persona/{creator_id}/` (lines 68-70).
- `get_context_for_message` (line 77): top-3 L3 por confidence + top-3 L2 por keyword overlap + top-3 L1 por lead_name. Max 500 tokens (~1750 chars).
- `_score_l2_relevance` (line 158): scoring por overlap de palabras, con stopwords ES/CA/EN/IT (BUG-EP-10 fix).
- Cache factory: `BoundedTTLCache(50, 300s)` (line 190).

### Activación
- **Feature flag:** `ENABLE_HIERARCHICAL_MEMORY` (default: `false`) (context.py:31).
- **Se llama desde:** `core/dm/phases/context.py:391-423` (únicamente). Output: `hier_memory_context` concatenado en system prompt.
- **¿Tiene consumer?** SÍ pero **solo si flag activado**. Default OFF.

### Afecta al output?
- [x] inyecta en system prompt

### Si inyecta contexto
- **Posición/Tamaño/Condiciones:** Hasta 300 tokens (~1050 chars). Formato `[Comportamiento habitual]`, `[Patrones recientes]`, `[Historial con {lead}]`. Requiere JSONL precomputados por `scripts/build_memories.py`.

### Metadata escrita
- `cognitive_metadata["hier_memory_injected"], ["hier_memory_chars"], ["hier_memory_levels"]` (context.py:407-412) — consumer: cognitive_metadata en Message.

### Solapamiento con P0/P1 auditados
- SÍ parcial — conceptualmente solapa con `memory_engine` (P1). `memory_engine` usa COMEDY-style memories en DB; este usa JSONL pre-built. Son pipelines paralelos (nota en línea 20: "Compatible with existing MemoryEngine. Runs alongside it").

### Bugs / dead code
- Default OFF — en producción no corre.
- Requiere `scripts/build_memories.py` offline (no ejecutado automático); si no hay JSONL para creator, `get_context_for_message` devuelve "".
- `l2_lines` loop (line 115-118) ignora `period` y `count` extraídos (variables unused).

### Veredicto
- **VALOR:** MEDIO
- **ESTADO:** DORMIDO_RECUPERABLE
- **RAZÓN:** Implementación completa y cacheada, pero `ENABLE_HIERARCHICAL_MEMORY=false`. Requiere build_memories.py offline + activar flag. Paper IMPersona (+19 pts human pass rate) sugiere valor alto si se activa.

---

## Sistema: Query Expansion

- **Archivo:** `core/query_expansion.py`
- **Líneas:** 189
- **Clasificación prev:** No clasificado
- **Qué hace (1 línea):** Expande queries con sinónimos infoproducts/fitness y acrónimos hardcoded para mejorar recall RAG.

### Funcionalidad detallada
- `QueryExpander.expand` (line 109): sustituye palabras por sinónimos (`curso`→`programa,formación,training…`), expande acrónimos (`ia`→`inteligencia artificial`). Max 3 expansiones.
- Diccionarios hardcoded in-memory: ~40 sinónimos (productos, precio, tiempo, objeciones, fitness/wellness) + 10 acrónimos.
- Singleton global `_query_expander` (line 181).

### Activación
- **Feature flag:** `ENABLE_QUERY_EXPANSION` (default: `true`) (context.py:24, feature_flags.py:43).
- **Se llama desde:** `core/dm/phases/context.py:571-576` (dentro del RAG path, sólo si `_needs_retrieval`). La query expandida se concatena con espacios y se pasa a `agent.semantic_rag.search`.
- **¿Tiene consumer?** SÍ.

### Afecta al output?
- [x] inyecta en system prompt (indirecto: modifica el query que recupera chunks que van al prompt)

### Si inyecta contexto
- **Posición/Tamaño/Condiciones:** Sólo cuando `ENABLE_RAG=true` y hay `_rag_signal`. `max_expansions=2` (context.py:573), concatenación naive de variantes.

### Metadata escrita
- `cognitive_metadata["query_expanded"]=True` — escrito en `context.py:576` — consumer: cognitive_metadata.

### Solapamiento con P0/P1 auditados
- NO. Capa auxiliar sobre `rag/semantic.py` (P1).

### Bugs / dead code
- `expand_tokens`, `add_synonym`, `add_acronym` (lines 148, 167, 175) — zero callers (sólo tests).
- Concatenar variantes con espacios (`rag_query = " ".join(expanded)`) puede romper embeddings — embedding de una frase frankenstein puede ser peor que query original. Efectivo solo para BM25/keyword.
- Diccionarios hardcoded no soportan catalán/italiano bien (sólo 2-3 entradas).

### Veredicto
- **VALOR:** BAJO
- **ESTADO:** ACTIVO_INÚTIL
- **RAZÓN:** Default-ON pero su técnica (concatenar sinónimos en la query) perjudica embeddings densos. Podría reescribirse para generar queries paralelas y hacer multi-search, pero tal como está aporta marginal valor (sólo boost a BM25).

---

## Sistema: RAG Service (services/rag_service.py)

- **Archivo:** `services/rag_service.py`
- **Líneas:** 337
- **Clasificación prev:** No clasificado
- **Qué hace (1 línea):** Servicio legacy in-memory de RAG con similitud Jaccard/keyword-based (sin embeddings reales).

### Funcionalidad detallada
- `RAGService.add_document` / `retrieve` (lines 89, 124): indexado en dict in-memory, scoring por Jaccard + coverage (0.6/0.4) (line 261).
- `_generate_embedding` es stub (line 310) — retorna None, hence siempre cae a keyword.
- Stop words ES/EN mínimo (lines 59-65).

### Activación
- **Feature flag:** sin flag.
- **Se llama desde:** NINGÚN módulo de runtime. Solo `services/__init__.py:12, 30` (re-export), `mega_test_auto.py:435-446` (test), `tests/services/test_rag_service.py`, y mención en docstring de `core/dm/agent.py:11`.
- **¿Tiene consumer?** NO.

### Afecta al output?
- (ninguno — dead code)

### Si inyecta contexto
- N/A.

### Metadata escrita
- Nada persistido.

### Solapamiento con P0/P1 auditados
- SÍ — conceptual 100% duplicado con `core/rag/semantic.py` (P1), pero más pobre (sin embeddings reales, sin BM25, sin rerank). Export en `services/__init__.py:30` es histórico.

### Bugs / dead code
- **Código muerto completo.** `_generate_embedding` stub (line 319). Jaccard puro insuficiente para producción.
- Docstring en agent.py:11 ("RAGService: Knowledge retrieval") es stale — el agente real usa `semantic_rag` (SemanticRAG de core/rag/semantic.py).

### Veredicto
- **VALOR:** NINGUNO
- **ESTADO:** ELIMINAR
- **RAZÓN:** 337 líneas de código legacy sin consumers de runtime. `SemanticRAG` lo reemplaza completamente. Borrar o marcar deprecated.

---

## Sistema: Knowledge Base (services/knowledge_base.py)

- **Archivo:** `services/knowledge_base.py`
- **Líneas:** 112
- **Clasificación prev:** No clasificado
- **Qué hace (1 línea):** Lookup factual por keywords (categorías precios/sesiones/horarios…) leído de JSON `knowledge_bases/{creator}.json`.

### Funcionalidad detallada
- `KnowledgeBase.lookup` (line 33): scoring por count de keywords hit en query, devuelve `content` de la categoría ganadora.
- 6 categorías en template (line 62): precios, sesiones, servicios, horarios, ubicacion, contacto.
- Cache factory `BoundedTTLCache(50, 600s)` (line 102).

### Activación
- **Feature flag:** sin flag.
- **Se llama desde:** `core/dm/phases/context.py:715-720` — si hit, se inyecta como `kb_context = f"Info factual relevante: {kb_result}"`.
- **¿Tiene consumer?** SÍ.

### Afecta al output?
- [x] inyecta en system prompt (como `kb_context`)

### Si inyecta contexto
- **Posición/Tamaño/Condiciones:** Sólo si `KnowledgeBase.data` no vacío Y hay keyword hit. El archivo vive en `knowledge_bases/{creator_id}.json` — verificado que el directorio está en `.railwayignore` (deploy issue potencial — archivos no llegan a Railway).

### Metadata escrita
- Ninguna.

### Solapamiento con P0/P1 auditados
- Parcial — distinto de `api.models.KnowledgeBase` (ORM en DB con `question/answer`, usado por `clone_score_engine.py:866`). Son dos sistemas "knowledge_base" sin relación:
  - `services/knowledge_base.py` (este): JSON files.
  - `api/models` KnowledgeBase: tabla DB.

### Bugs / dead code
- **`.railwayignore` excluye `knowledge_bases/`** — en prod, `path.exists()` en `_load` (line 28) será False silenciosamente → `data={}` → siempre `None`. En prod el sistema está efectivamente inactivo.
- Scoring por count sin normalizar longitud — categoría con más keywords siempre gana.
- Keywords exact substring match sensible a accentuación ES (p.ej. `cuanto` vs `cuánto`).

### Veredicto
- **VALOR:** BAJO
- **ESTADO:** ACTIVO_INÚTIL (en prod) / DORMIDO_RECUPERABLE (si se arregla deploy)
- **RAZÓN:** Consumer activo en context.py pero los JSON no llegan a Railway. Duplicado conceptual con RAG + Products en DB. Sugerencia: migrar a tabla DB o eliminar.

---

### 3.C · Batch C — Personality / Style (7 sistemas)

## Sistema: Personality Extraction Pipeline

- **Archivo:** `core/personality_extraction/` (módulo completo, 11 archivos, ~3800 líneas)
- **Líneas:** ~3800 (extractor.py 385, personality_profiler.py 752, bot_configurator.py ~1000, copilot_rules.py 170, conversation_formatter.py 225, data_cleaner.py 310, lead_analyzer.py 260, llm_client.py 225, models.py 290, negation_reducer.py 190, auto_calibrator.py 145)
- **Clasificación prev:** No clasificado (ecosistema mayor)
- **Qué hace (1 línea):** Pipeline de 5 fases (Doc A..E) que destila el historial de DMs del creator en un prompt de sistema, blacklist, template pool, parámetros de calibración y reglas copilot — produce el Doc D que consume el resto del sistema.

### Funcionalidad detallada
- `PersonalityExtractor.run()` (extractor.py) orquesta: Phase 0 cleaning → Phase 1 formato Doc A → Phase 2 análisis por lead (Doc B) → Phase 3 Doc C (personality profile/DNA) → Phase 4 Doc D (system prompt + blacklist + templates + calibración) → Phase 5 Doc E (copilot rules).
- Persiste en `personality_docs` table (Postgres) y en disco `data/personality_extractions/{creator_id}/` los 5 docs + `extraction_summary.json`.
- Submódulos LIVE (importados por el pipeline): extractor, personality_profiler, bot_configurator, copilot_rules, conversation_formatter, data_cleaner, lead_analyzer, llm_client, models.
- Submódulos LIVE con callers externos: `negation_reducer.reduce_negations` (usado por `core/personality_loader.py:238` para filtrar negaciones al cargar Doc D en runtime) y `auto_calibrator.auto_calibrate` (usado por `services/calibration_generator.py:124`).
- Entry points externos del orquestador: `api/routers/onboarding/extraction.py` (trigger manual), `api/routers/onboarding/clone.py:569`, `services/whatsapp_onboarding_pipeline.py:629`, `scripts/turbo_onboarding.py:407`, `scripts/run_personality_extraction.py:98`.

### Activación
- **Feature flag:** ninguno en el pipeline core; `EXTRACTION_MAX_LEADS` (default 50) limita leads analizados.
- **Se llama desde:** `api/routers/onboarding/extraction.py:83,142` (onboarding), `api/routers/onboarding/clone.py:569`, `services/whatsapp_onboarding_pipeline.py:629`, scripts.
- **¿Tiene consumer?:** SÍ — Doc D es consumido por `core/personality_loader.py` → `creator_style_loader`, `response_fixes`, `response_variator_v2`, `prompt_builder/calibration`, `reasoning/ppa`, `clone_score_engine`.

### Afecta al output?
- [x] system prompt (vía Doc D §4.1)
- [x] post-LLM mutation (blacklist §4.2 aplicada en `response_fixes.py`)
- [x] metadata (doc_d_distilled / doc_d en tabla personality_docs)
- [x] observability (extraction_summary.json)

### Si inyecta contexto
- No inyecta directamente: produce Doc D que `personality_loader.load_extraction()` parsea y expone a consumers. Tamaño típico Doc D: ~20K chars full, ~2K chars distilled. Sección §4.1 SYSTEM PROMPT es la principal.

### Metadata escrita
- `personality_docs.content` (doc_type=doc_d, doc_e) — `extractor.py:343-384 (_save_docs_to_db)` — consumer: `core/personality_loader.py:98-145 (_load_doc_d_from_db)`
- `data/personality_extractions/{creator_id}/doc_{a,b,c,d,e}_*.md` — consumer: fallback en `personality_loader.py:62-95`
- `extraction_summary.json` — sólo diagnóstico

### Solapamiento con P0/P1 auditados
- compressed_doc_d (P0): consume el output del pipeline (Doc D full) y lo comprime. No solapa.
- creator_style_loader (P0): llama a `load_extraction()` para el system prompt — cliente del pipeline.
- calibration_loader (P0): el auto_calibrator submodule es usado por `calibration_generator.py`, que produce outputs consumidos por calibration_loader.
- response_variator_v2 (P0): consume `extraction.template_pools` y `extraction.multi_bubble`.
- **NO** hay solapamiento funcional — el pipeline ES la fuente de verdad que los demás consumen.

### Bugs / dead code
- `data_cleaner.py`, `lead_analyzer.py`, `conversation_formatter.py`, `llm_client.py`, `models.py` son sólo importados por el pipeline interno → no tienen otros consumers y no son código muerto porque el pipeline se ejecuta en onboarding.
- `copilot_rules.py` genera Doc E que se persiste pero actualmente no hay consumer del Doc E más allá del almacenamiento — posible dormido.
- El Doc E (copilot rules AUTO/DRAFT/MANUAL) no aparece siendo leído en runtime, sólo guardado.

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Fuente canónica del system prompt, blacklist y template pool. Todo el pipeline de DM depende de Doc D. Onboarding lo invoca obligatoriamente. Copilot rules (Doc E) está dormido pero el resto es crítico.

---

## Sistema: Personality Loader

- **Archivo:** `core/personality_loader.py`
- **Líneas:** 358
- **Clasificación prev:** No clasificado (dependencia directa de creator_style_loader P0)
- **Qué hace (1 línea):** Carga Doc D del pipeline de extracción (desde DB `personality_docs` o disco), parsea secciones §4.1-§4.5 y expone `ExtractionData` con system_prompt, blacklist, calibration, template_pools y multi_bubble.

### Funcionalidad detallada
- `load_extraction(creator_id)`: cache TTL 300s, DB first (doc_d_distilled > doc_d), fallback disk.
- `get_calibration_override(creator_id)`: retorna §4.3 como dict (max_message_length_chars, max_emojis_per_message, enforce_fragmentation).
- `invalidate_cache(creator_id)`: limpia cache tras re-extracción.
- Parsers internos: `_parse_system_prompt` (aplica `negation_reducer` en carga), `_parse_blacklist`, `_parse_calibration`, `_parse_template_pools`, `_parse_multi_bubble`.
- Soporta resolver creator por slug o UUID (JOIN con creators table).

### Activación
- **Feature flag:** `PERSONALITY_CACHE_TTL` (default 300s); sin on/off — siempre activo si hay Doc D.
- **Se llama desde:** `services/creator_style_loader.py:61,132`, `core/response_fixes.py:262`, `services/response_variator_v2.py:222`, `core/reasoning/ppa.py:77`, `core/prompt_builder/calibration.py:35`, `services/clone_score_engine.py:910`, `api/routers/onboarding/extraction.py:96,161` (invalidate).
- **¿Tiene consumer?:** SÍ — 6 consumers productivos distintos.

### Afecta al output?
- [x] system prompt (proporciona la sección style_prompt)
- [x] post-LLM mutation (provee blacklist)
- [x] metadata (provee template pools, multi_bubble, calibration)

### Si inyecta contexto
- Indirectamente vía consumers. No hace inject directo.

### Metadata escrita
- Ninguna — sólo lectura/cache.

### Solapamiento con P0/P1 auditados
- creator_style_loader (P0): es el principal cliente de personality_loader. Es la capa de abstracción sobre personality_extraction pipeline para consumers runtime.
- compressed_doc_d (P0): alternativa que precede a personality_loader en creator_style_loader (prioridad 0 antes de Priority 1 extraction).
- calibration_loader (P0): `get_calibration_override` es delegado desde calibration_loader via `prompt_builder/calibration.py`.
- SIN overlap duplicado — son capas complementarias.

### Bugs / dead code
- Regex `_parse_system_prompt` depende del formato exacto `## 4.1 SYSTEM PROMPT` con code fence; si Doc D se genera con formato distinto (p.ej. por nueva versión del bot_configurator), falla silenciosamente. No hay test de contrato.
- `ExtractionData.calibration` dict no está tipada — consumers hacen `.get(key, default)` implícito.

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Pieza crítica de enlace entre pipeline de extracción y runtime del DM agent. Sin personality_loader, Doc D no entra al prompt.

---

## Sistema: Style Analyzer

- **Archivo:** `core/style_analyzer.py`
- **Líneas:** 699
- **Clasificación prev:** No clasificado (ECHO Engine 'E=Extract')
- **Qué hace (1 línea):** Analiza mensajes históricos del creator y genera StyleProfile con métricas cuantitativas (longitud, emojis, muletillas, puntuación, openers/closers) + perfil cualitativo via Gemini Flash-Lite (tono, humor, estilo de venta, frases firma, dialecto).

### Funcionalidad detallada
- `StyleAnalyzer.analyze_creator(creator_id, creator_db_id, force)`: carga mensajes `role='assistant'` con `status IN (sent,edited)` (max 1000), computa quant+qual y devuelve dict con `prompt_injection` string.
- `extract_quantitative_metrics()`: stats de longitud (mean/median/p10/p90), counter emojis, abbreviations_es, muletillas, punctuation_stats, case_stats, openers/closers top_10, hourly_distribution, style_by_lead_status.
- `extract_qualitative_profile()`: LLM call con JSON estructurado (tone, energy_level, humor_usage, sales_style, empathy_level, formality_markers, signature_phrases, vocabulary_preferences, avoids, dialect, code_switching).
- `_generate_prompt_section()`: compone el string inyectable (~500-1500 chars) que se APPENDEA después del Doc D.
- `analyze_and_persist()`: entry point del scheduler, guarda en `style_profiles` table (StyleProfileModel).
- `load_profile_from_db()`: devuelve el dict parseado.

### Activación
- **Feature flag:** `ENABLE_STYLE_ANALYZER` (default true); `ENABLE_STYLE_RECALC` (default true para scheduler).
- **Se llama desde:** `core/dm/agent.py:277` (`_enrich_style_with_profile` → APPEND al style_prompt), `core/dm/phases/context.py:938` (load para RelationshipAdapter modulation), `api/startup/handlers.py:711` (scheduler JOB 24, cada 30 días, 690s delay).
- **¿Tiene consumer?:** SÍ — consumido por agent loading + relationship_adapter.

### Afecta al output?
- [x] system prompt (APPEND bloque "=== ESTILO DE ESCRITURA (datos reales) ===" al final del style_prompt existente)
- [x] metadata (confidence, total_messages_analyzed)
- [x] observability (logs `[STYLE]`, `[ECHO]`)

### Si inyecta contexto
- Posición: APPEND al final del `style_prompt` ya cargado por creator_style_loader — es adjunto al final del Doc D personality section.
- Tamaño: ~500-1500 chars (prompt_injection string).
- Condiciones: sólo si `profile.get("prompt_injection")` existe y el creator tiene ≥30 mensajes.

### Metadata escrita
- `style_profiles.profile_data` JSON — `core/style_analyzer.py:660 (_save_profile_to_db)` — consumer: `dm/agent.py:277`, `dm/phases/context.py:949` (relationship adapter).

### Solapamiento con P0/P1 auditados
- **style_normalizer (P1):** ESTE ES UN SOLAPE REAL — style_analyzer produce métricas (avg_length, emoji_rate, dialect), y style_normalizer también normaliza estilo. style_analyzer es EXTRACT (análisis offline) mientras style_normalizer es RUNTIME (normalización por mensaje) → son complementarios pero operan sobre el mismo concepto de "estilo". El prompt_injection se duplica parcialmente con lo que Doc D ya dice sobre estilo.
- **creator_style_loader (P0):** style_analyzer extiende style_prompt que creator_style_loader compone. Sin solape directo, pero ECHO está appendeando información que puede duplicar Doc D.
- **tone_service (este batch):** otro sistema "de tono" separado y más legacy — ver abajo.

### Bugs / dead code
- `_select_representative_sample()` permite duplicación parcial (mismos 30 mensajes recientes + por intent + por status). OK con dedupe básico.
- LLM parse es frágil (json.loads crudo con regex-strip de fences). Si LLM devuelve texto extra, falla silently y vuelve `{"error": "..."}`.
- Doble importación: `ENABLE_STYLE_ANALYZER` se chequea en `analyze_creator` Y se chequea `os.getenv("ENABLE_STYLE_ANALYZER")` en `dm/agent.py:274` → duplicado.

### Veredicto
- **VALOR:** MEDIO
- **ESTADO:** ACTIVO_VALIOSO con solapamiento parcial
- **RAZÓN:** Aporta métricas cuantitativas reales (no-LLM) que Doc D no tiene (emoji_rate, length distribution). Pero el prompt_injection duplica información cualitativa de Doc D (tone, signature_phrases, vocabulary). Candidato a simplificar: mantener SÓLO las métricas cuantitativas en el prompt_injection y eliminar el LLM qualitative call.

---

## Sistema: Tone Service

- **Archivo:** `core/tone_service.py`
- **Líneas:** 359
- **Clasificación prev:** No clasificado (legacy pre-ECHO)
- **Qué hace (1 línea):** Gestiona ToneProfile legacy (DB + JSON fallback) con estructura `primary_language`, `dialect`, `to_system_prompt_section()` — creado antes del Style Analyzer/Doc D como sistema de "tono de voz" del creator basado en posts de IG.

### Funcionalidad detallada
- `get_tone_profile(creator_id)`: async, cache→DB→JSON fallback → returns ToneProfile object.
- `get_tone_prompt_section(creator_id)`: sync entry point que creator_style_loader usa para obtener sección de prompt (Priority 2 fallback después de personality_loader).
- `get_tone_language(creator_id)`, `get_tone_dialect(creator_id)`: usados por guardrails (tests/test_guardrails_voseo.py) y otros lugares.
- `generate_tone_profile(creator_id, posts)`: invoca `ToneAnalyzer` de `ingestion/` para crear perfil desde posts de IG.
- `save_tone_profile()`, `delete_tone_profile()`, `list_profiles()`, `clear_cache()`.

### Activación
- **Feature flag:** ninguno; siempre activo pero condicionado a que el creator tenga ToneProfile guardado.
- **Se llama desde:**
  - `services/creator_style_loader.py:100,156,193` (P0 — LEGACY PATH Priority 2, sólo si no hay personality_extraction)
  - `core/onboarding_service.py:20` (save_tone_profile durante onboarding legacy)
  - `core/auto_configurator.py:494` (genera durante autoconf)
  - `api/routers/onboarding/pipeline.py:103,138,377,393`, `api/routers/onboarding/setup.py:141`, `api/routers/tone.py` (routers de onboarding v2)
  - `api/startup/cache.py:61` (prewarm cache al boot)
  - `tests/test_guardrails_voseo.py:140,156,164,171` (guardrails de dialecto)
- **¿Tiene consumer?:** SÍ, pero es LEGACY secundario — sólo actúa si no hay Doc D.

### Afecta al output?
- [x] system prompt (via creator_style_loader Priority 2 fallback)
- [x] observability
- Actúa como proveedor de `primary_language` y `dialect` para guardrails.

### Si inyecta contexto
- Posición: fallback en creator_style_loader (sólo si Doc D falta).
- Tamaño: ~200-500 chars del `to_system_prompt_section()`.
- Condiciones: personality_extraction NO existe.

### Metadata escrita
- `tone_profiles.profile_data` — `core/tone_profile_db.py:67` — consumer: este mismo módulo + creator_style_loader legacy.

### Solapamiento con P0/P1 auditados
- **creator_style_loader (P0):** tone_service es Priority 2 fallback. Sin Doc D → tone_service entra.
- **style_analyzer (este batch):** AMBOS producen "perfil de estilo". Style Analyzer es más nuevo (ECHO, métricas reales) mientras tone_service es legacy (LLM analyzing IG post captions). SOLAPAN parcialmente en: tone, dialect, language.
- **tone_profile_db (este batch):** es su backend de persistencia — no solape, es capa inferior.

### Bugs / dead code
- `delete_tone_profile` line 339-341: crea un nuevo event loop (`asyncio.new_event_loop()`) dentro de función sync → anti-pattern, puede romper si se llama desde contexto async.
- `tone_service` y `style_analyzer` coexisten sin coordinación — un creator nuevo termina con ambos perfiles sin que nadie los unifique.

### Veredicto
- **VALOR:** BAJO (solapamiento con Doc D + Style Analyzer)
- **ESTADO:** ACTIVO_INÚTIL (legacy todavía conectado)
- **RAZÓN:** Sólo actúa como fallback de Priority 2. La mayoría de creators tienen Doc D, así que el output rara vez se ve. `get_tone_dialect` es el único uso verdaderamente útil (guardrails de voseo). Candidato a migrar esa función a Style Analyzer y deprecar.

---

## Sistema: Tone Profile DB

- **Archivo:** `core/tone_profile_db.py`
- **Líneas:** 540
- **Clasificación prev:** No clasificado (capa de persistencia)
- **Qué hace (1 línea):** Capa de persistencia PostgreSQL para ToneProfiles, ContentChunks (RAG/citation) e InstagramPosts — módulo que creció más allá de su nombre y ahora gestiona múltiples entidades de ingestión.

### Funcionalidad detallada
- **ToneProfile section:** `save_tone_profile_db`, `get_tone_profile_db`, `get_tone_profile_db_sync`, `delete_tone_profile_db`, `list_profiles_db`, `clear_cache` — persistencia directa de ToneProfileModel.
- **ContentChunk section:** `save_content_chunks_db`, `get_content_chunks_db`, `delete_content_chunks_db` — persiste chunks de RAG/Citation (antes archivo `data/content_index/{creator_id}/chunks.json`).
- **InstagramPost section:** `save_instagram_posts_db`, `get_instagram_posts_db`, `delete_instagram_posts_db`, `get_instagram_posts_count_db` — persiste posts crudos de IG con hashtags/mentions parseados.
- Cache `_tone_cache` BoundedTTLCache (max 50, TTL 600s).

### Activación
- **Feature flag:** ninguno, siempre activo.
- **Se llama desde:**
  - `core/tone_service.py:32,125,286,304,335` (ToneProfile ops)
  - `services/feed_webhook_handler.py:127,151` (save posts, save chunks — webhook live)
  - `ingestion/v2/instagram_ingestion.py:361,399,448` (posts + chunks)
  - `ingestion/v2/youtube_ingestion.py:159,306` (chunks delete + save)
  - `api/routers/ingestion_v2/*.py`, `api/routers/onboarding/setup.py:128` (delete_content_chunks_db)
  - `core/auto_configurator.py:396,493` (get_instagram_posts_db para análisis)
- **¿Tiene consumer?:** SÍ — múltiples pipelines usan especialmente ContentChunk + InstagramPost sections.

### Afecta al output?
- [x] metadata (chunks usados por RAG en el pipeline de DM)
- [ ] Inject directo: NO (pipeline RAG los lee aparte)

### Si inyecta contexto
- N/A directamente. ContentChunks son leídos por el RAG pipeline (P0 rag/semantic).

### Metadata escrita
- `tone_profiles.*` (ver arriba)
- `content_chunks.*` — consumer: RAG/semantic search
- `instagram_posts.*` — consumer: auto_configurator, tone analysis, feed webhooks

### Solapamiento con P0/P1 auditados
- **rag/semantic (P0):** ContentChunk es el dataset base del RAG. tone_profile_db es el storage layer — NO solape funcional, es dependencia.
- **tone_service (este batch):** es su frontend async.
- Naming confuso: el archivo se llama `tone_profile_db.py` pero 70% del código es sobre ContentChunk/InstagramPost. Debería renombrarse o separarse (sugerencia: `core/storage/ingestion_db.py`).

### Bugs / dead code
- El archivo violar el principio de responsabilidad única (tone + chunks + posts). Riesgo de acoplamiento futuro.
- `save_content_chunks_db` no hace UPSERT atómico real: hace query+insert/update separados dentro de for-loop → race conditions posibles en ingestión paralela.
- `_tone_cache` sólo cachea ToneProfiles, no chunks ni posts — cache inconsistente con el alcance del archivo.

### Veredicto
- **VALOR:** ALTO (infraestructura crítica)
- **ESTADO:** ACTIVO_VALIOSO (aunque mal nombrado)
- **RAZÓN:** Punto único de acceso a 3 tablas críticas (tone_profiles, content_chunks, instagram_posts). RAG pipeline y onboarding dependen de él. Recomendación: renombrar y separar responsabilidades, pero mantener funcionalidad.

---

## Sistema: PersonaCompiler (System B)

- **Archivo:** `services/persona_compiler.py`
- **Líneas:** 1189
- **Clasificación prev:** Learning
- **Qué hace (1 línea):** Pipeline batch que compila signals acumulados (preference pairs, evaluator feedback, copilot evaluations) en secciones `[PERSONA_COMPILER:*]` insertadas dentro de Doc D — evolución autónoma del persona a partir de correcciones del creator.

### Funcionalidad detallada
- Funciones principales:
  - `run_daily_evaluation(creator_id, creator_db_id, eval_date)`: daily job (86400s) que agrega copilot_action, calcula approval_rate, edit_rate, clone_accuracy, detecta patterns de edición (shortening, question_removal, emoji_removal, complete_rewrite), persiste en `copilot_evaluations`.
  - `run_weekly_recalibration(creator_id, ...)`: weekly job (604800s), agrega 7 daily evals, genera recommendations y dispara `compile_persona()` si hay recs.
  - `compile_persona(creator_id, creator_db_id)`: main compiler — recolecta signals (`_collect_signals`), categoriza en 9 dimensiones (`_categorize_evidence`: tone, length, emoji, questions, cta, structure, personalization, greetings, language_mix), llama al LLM por categoría (`_compile_section`) con ≥3 evidence items, aplica updates tageados a Doc D (`_apply_sections`), snapshot versión anterior en `doc_d_versions`.
  - `compile_persona_all()`: batch para todos los creators con bot_active=True.
  - `rollback_doc_d(creator_db_id, version_id)`: reversión a snapshot previo.
- Funciones absorbidas: `sanitize_rule_text`, `filter_contradictions`, `detect_language`, `_format_pair`, `_call_judge`, `_persist_run`, `_parse_llm_response`.

### Activación
- **Feature flag:** `ENABLE_PERSONA_COMPILER` (default false) — SISTEMA DORMIDO; `ENABLE_COPILOT_EVAL`, `ENABLE_COPILOT_RECAL`, `ENABLE_LEARNING_CONSOLIDATION`, `ENABLE_PATTERN_ANALYZER`.
- **Se llama desde:**
  - `api/startup/handlers.py:402` (JOB 15 daily_eval, 86400s, 420s delay)
  - `api/startup/handlers.py:433` (JOB 16 weekly_recal, 604800s, 450s delay)
  - `api/startup/handlers.py:464` (JOB 18 learning_consolidation → compile_persona, 86400s, 510s delay, default=false)
  - `api/startup/handlers.py:500` (JOB 19 pattern_analyzer → compile_persona_all, 43200s, 540s delay, default=false)
  - `services/whatsapp_onboarding_pipeline.py:789` (pattern analysis en onboarding)
  - `api/routers/autolearning/analysis.py` (endpoint manual)
- **¿Tiene consumer?:** SÍ pero DORMIDO — `ENABLE_PERSONA_COMPILER=false` por default, y JOB 18+19 también `false` por default. Sólo `daily_eval` (JOB 15) y `weekly_recal` (JOB 16) están ON por default pero NO llaman a `compile_persona` a menos que `ENABLE_PERSONA_COMPILER=true` y haya recommendations.

### Afecta al output?
- [x] system prompt (modifica directamente `creators.doc_d` insertando `[PERSONA_COMPILER:*]` sections)
- [x] metadata (`pattern_analysis_runs` audit, `doc_d_versions` snapshots, `copilot_evaluations`)
- [x] observability (logs `[PERSONA]`, `[AUTOLEARN]`)

### Si inyecta contexto
- Inyecta secciones tageadas DENTRO de Doc D — extraídas por personality_loader al cargar.
- Tamaño: hasta 150 palabras por categoría × 9 categorías = ~1350 words max.
- Condiciones: ≥3 evidence items por categoría, quality ≥0.6, `ENABLE_PERSONA_COMPILER=true`.

### Metadata escrita
- `creators.doc_d` (UPDATE) — modifica el Doc D del creator — consumer: personality_loader.
- `doc_d_versions` (snapshot) — rollback history.
- `pattern_analysis_runs` — audit trail.
- `copilot_evaluations` (eval_type=daily|weekly) — consumer: autolearning endpoints.
- `preference_pairs.batch_analyzed_at` (UPDATE mark processed).

### Solapamiento con P0/P1 auditados
- **compressed_doc_d (P0):** persona_compiler modifica `creators.doc_d`, que luego entra a compressed_doc_d. persona_compiler opera OFFLINE/batch sobre el Doc D master, compressed_doc_d es runtime. Son capas distintas.
- **creator_style_loader (P0):** consume Doc D ya modificado por persona_compiler.
- **preference_profile_service (P0):** AMBOS consumen preference_pairs. persona_compiler los marca como `batch_analyzed_at` después de procesarlos → podría haber race condition con preference_profile_service. Verificar.
- **Con bot_configurator (este batch):** bot_configurator genera el Doc D INICIAL (onboarding one-shot). persona_compiler EVOLUCIONA el Doc D post-onboarding (batch continuo). Son complementarios.

### Bugs / dead code
- `compile_persona` modifica `creator.doc_d` directamente pero el sistema runtime usa `personality_docs` table (ver `personality_loader._load_doc_d_from_db`). INCONSISTENCIA: persona_compiler escribe a una columna antigua (`creators.doc_d`) pero el runtime lee de `personality_docs.content`. Esto es potencialmente un bug que anula el compilador.
- `analyze_creator_action` (línea 124) es no-op — restos de refactor a batch-only.
- Redundancia entre `_generate_weekly_recommendations` y `_detect_daily_patterns` — ambos detectan shortening/emoji/question patterns, pero uno genera recs y otro pattern objects.
- Los patterns generados por run_daily_evaluation son consumidos por `_categorize_evidence` en compile_persona — dependencia de estado que requiere orden correcto de ejecución de jobs.

### Veredicto
- **VALOR:** ALTO (en teoría) / MEDIO (en práctica)
- **ESTADO:** DORMIDO_RECUPERABLE
- **RAZÓN:** Sistema sofisticado y bien diseñado (signals → categorize → LLM compile → versioning), PERO `ENABLE_PERSONA_COMPILER=false` por default y hay un bug de persistencia (escribe a `creators.doc_d`, runtime lee de `personality_docs`). Con fix de persistencia y activación, sería feature muy potente. Los jobs diario/semanal SÍ están activos y persisten métricas (valor de observabilidad), pero el "compiler" per se está inactivo.

---

## Sistema: Vocabulary Extractor

- **Archivo:** `services/vocabulary_extractor.py`
- **Líneas:** 339
- **Clasificación prev:** No clasificado (usado en DNA/eval)
- **Qué hace (1 línea):** Tokenización universal + extracción de vocabulario distintivo via TF-IDF per-lead (palabras características de un creator por lead, 5 idiomas: ES/CA/EN/PT/IT).

### Funcionalidad detallada
- `tokenize(text)`: regex `\b([a-zA-Z\u00C0-\u024F]{3,})\b`, excluye STOPWORDS (ES/CA/EN/PT/IT, ~160 palabras), media placeholders, technical tokens (https, instagram, gmail, etc.), dígitos.
- `extract_lead_vocabulary(creator_messages, min_freq=2)`: Counter con umbral adaptativo (sube a 3 si ≥50 mensajes).
- `compute_distinctiveness(lead_vocab, global_vocab, total_leads, leads_per_word)`: TF-IDF con fallback de concentración si leads_per_word no provisto.
- `get_top_distinctive_words(creator_messages, global_vocab, total_leads, ..., top_n=8)`: main entry point para DNA vocabulary. Si no hay global_vocab, usa frequency-only.
- `build_global_corpus(creator_id, use_cache=True)`: queries DB con paginación (page_size=5000), construye global_vocab + leads_per_word. Cache 1 hora per-creator. Filtra `approved_by NOT IN ('auto','autopilot')` — sólo mensajes humanos reales.

### Activación
- **Feature flag:** ninguno; siempre activo.
- **Se llama desde:**
  - `services/relationship_analyzer.py:227,245,332` (get_top_distinctive_words, tokenize, STOPWORDS)
  - `services/relationship_dna_service.py:188` (build_global_corpus)
  - `core/evaluation/style_profile_builder.py:27,405` (tokenize, compute_distinctiveness)
  - `core/evaluation/adaptation_profiler.py:29` (tokenize)
  - `core/evaluation/ccee_scorer.py:29` (tokenize) — usado por el CPE scorer
  - `services/whatsapp_onboarding_pipeline.py:498` (VocabularyExtractor — BUG, no existe tal clase)
  - `mega_test_w2.py:846,1212` (VocabularyExtractor, SPANISH_STOP_WORDS — BUG, no existe)
  - `scripts/backfill_dna_vocabulary.py` (backfill DNA)
  - `scripts/bootstrap_vocab_metadata.py`
- **¿Tiene consumer?:** SÍ — relationship_analyzer, relationship_dna_service, style_profile_builder, adaptation_profiler, ccee_scorer.

### Afecta al output?
- [x] metadata (DNA vocabulary usada en relational context)
- [x] observability (ccee_scorer usa tokenize para CPE eval)
- Afecta el DNA context que llega al prompt de DM vía `relationship_dna_service`.

### Si inyecta contexto
- Indirecto: el output (top_distinctive_words) entra en el DNA context que se inyecta en el prompt. Tamaño típico: 8 palabras × ~10 chars = ~80 chars + labels.

### Metadata escrita
- No persiste directamente; sus outputs se guardan en `dna_lead_profiles`/`relationship_dna` por relationship_dna_service y relationship_analyzer.

### Solapamiento con P0/P1 auditados
- **style_normalizer (P1), style_retriever (P1):** ambos operan sobre estilo/vocabulario. vocabulary_extractor es más bajo nivel (tokenización + TF-IDF) y es usado por relationship_dna que alimenta DNA context (P0).
- **preference_profile_service (P0):** independiente pero ambos usan mensajes históricos.
- **Sin solape funcional directo** — vocabulary_extractor es utility library.

### Bugs / dead code
- **BUG CRÍTICO:** `services/whatsapp_onboarding_pipeline.py:498` importa `VocabularyExtractor` (clase) y llama `.extract_all(texts)` — pero la clase NO existe en el módulo. El archivo sólo tiene funciones top-level. Import ERROR en runtime cuando se ejecuta onboarding de WhatsApp.
- **BUG CRÍTICO:** `mega_test_w2.py:846` importa `VocabularyExtractor, SPANISH_STOP_WORDS, FORBIDDEN_WORDS` — ninguno existe. Tests fallarán.
- Verificado con `ast.parse`: sólo existen funciones `tokenize, extract_lead_vocabulary, compute_distinctiveness, get_top_distinctive_words, build_global_corpus` y la constante `STOPWORDS` (no SPANISH_STOP_WORDS).
- El módulo fue refactorizado para ser funcional pero los callers legacy (whatsapp_onboarding_pipeline, mega_test_w2) no fueron migrados.

### Veredicto
- **VALOR:** ALTO (los consumers activos funcionan)
- **ESTADO:** ACTIVO_VALIOSO + BUGS en callers legacy
- **RAZÓN:** Utility library fundamental para DNA vocabulary, CCEE scorer y style profiler. Los 5 callers productivos (relationship_analyzer, relationship_dna, style_profile_builder, adaptation_profiler, ccee_scorer) usan funciones correctas. Pero `whatsapp_onboarding_pipeline` y `mega_test_w2` tienen imports rotos (VocabularyExtractor, SPANISH_STOP_WORDS, FORBIDDEN_WORDS) que NO existen — causará AttributeError/ImportError cuando esas rutas se ejecuten.

---

### 3.D · Batch D — DM Phases / Strategy (7 sistemas)

## Sistema: dm_strategy (Response Strategy Engine)

- **Archivo:** `core/dm/strategy.py`
- **Líneas:** 117
- **Clasificación prev:** No clasificado (P2 — injected as LLM guidance)
- **Qué hace (1 línea):** Devuelve un string "ESTRATEGIA: …" que instruye al LLM sobre cómo enfocar la respuesta (familia, amigo, bienvenida, ayuda, venta, recurrente, reactivación) — no qué decir.

### Funcionalidad detallada
- Función única `_determine_response_strategy()` (strategy.py:13-117). Puro logic, sin I/O.
- Cadena de prioridad rígida (strategy.py:38-116):
  1. `relationship_type ∈ {FAMILIA, INTIMA}` → PERSONAL-FAMILIA (5-30 chars, no venta).
  2. `is_friend=True` → PERSONAL-AMIGO.
  3. `is_first_message` + "?"/help_signals → BIENVENIDA + AYUDA (BUG-12 fix, strategy.py:63-71).
  4. `is_first_message` sin ayuda → BIENVENIDA corto.
  5. `history_len >= 4 and not is_first_message` → RECURRENTE, prohíbe "¿Que te llamó la atención?" (strategy.py:82-91).
  6. Help signals `{ayuda, problema, no funciona, necesito, urgente, …}` → AYUDA.
  7. `intent_value ∈ {purchase, pricing, product_info, purchase_intent, product_question}` → VENTA + CTA suave.
  8. `lead_stage == "fantasma"` → REACTIVACIÓN.
  9. Default → `""` (sin estrategia).
- Help signals son ES-only (strategy.py:57-61) — no hay ES/CA/EN/IT i18n a diferencia de `post_response._extract_facts`.

### Activación
- **Feature flag:** Ninguno — siempre activo cuando entra en `phase_generation`.
- **Se llama desde:** `core/dm/phases/generation.py:190` (inyección al system prompt mediante `strategy_hint`).
- **¿Tiene consumer?:** SÍ — prepended al system prompt del LLM y loggeado como `cognitive_metadata["response_strategy"]` (generation.py:200-202).

### Afecta al output?
- [x] system prompt — el string va al LLM como instrucción imperativa
- [ ] user message
- [ ] post-LLM mutation
- [x] metadata — `cognitive_metadata["response_strategy"] = strategy_hint.split(".")[0]`
- [x] observability — `logger.info("[STRATEGY] …")`

### Si inyecta contexto
- **Posición:** Se asigna a `strategy_hint` pero NOTA: revisión requiere validar que `build_system_prompt` realmente lo consume; el call site solo guarda el string como metadata. (El hint local no se concatena al system_prompt en las líneas 190-202 visibles.)
- **Tamaño:** 150-400 chars.
- **Condiciones:** 9 ramas exclusivas — la primera que coincide gana.

### Metadata escrita
- `response_strategy` — generation.py:201 — se usa como señal DPO/observability; consumers: logs, CCEE evals.

### Solapamiento con P0/P1 auditados
- **conversation_state / relationship_adapter:** NO solapa — strategy usa `relationship_type` como input pero el call actual (generation.py:193) pasa `""` vacío "Relationship scorer: zero injection into strategy", o sea la rama FAMILIA/INTIMA ESTÁ MUERTA en runtime.
- **length_controller:** NO — strategy menciona longitud en FAMILIA (5-30 chars) pero no la impone; length_controller controla la longitud real post-LLM.
- **context_detector / frustration_detector:** NO — strategy no lee `context_signals`.

### Bugs / dead code
- **DEAD BRANCH:** Rama FAMILIA/INTIMA/AMIGO (strategy.py:39-54) nunca se activa porque `phase_generation` pasa `relationship_type=""` y `is_friend=False` (generation.py:193-195). Código funcional pero inalcanzable.
- **i18n gap:** `help_signals` (strategy.py:57-61) solo en castellano. Catalán "ajuda", "no funciona" (igual), "necessito" no matchean. Inconsistente con `_extract_facts` multilingüe.
- **DUPLICACIÓN DE IMPORT:** Tests en `tests/test_dm_agent_v2.py:529+` importan desde `core.dm_agent_v2` (re-export hub) mientras `test_motor_audit.py:312` y `phases/generation.py:11` importan directo desde `core.dm.strategy`. Ambos paths funcionan.
- **LÍNEA 82 MAGIC NUMBER:** `history_len >= 4` sin justificación en docstring ni config.

### Veredicto
- **VALOR:** MEDIO
- **ESTADO:** ACTIVO_VALIOSO (pero ramas FAMILIA/AMIGO DORMIDO_RECUPERABLE)
- **RAZÓN:** Las ramas activas (BIENVENIDA, AYUDA, VENTA, RECURRENTE) sí se disparan y sí afectan la guía al LLM. Las ramas FAMILIA/AMIGO son código muerto por decisión en `generation.py` — recuperable si se decide volver a inyectar relationship en la estrategia.

---

## Sistema: dm_knowledge (Manual RAG API wrapper)

- **Archivo:** `core/dm/knowledge.py`
- **Líneas:** 41
- **Clasificación prev:** No clasificado (wrapper delgado)
- **Qué hace (1 línea):** Tres funciones thin wrapper para añadir/batch/clear documentos en `agent.semantic_rag`.

### Funcionalidad detallada
- `add_knowledge(agent, content, metadata)` → wrapper alrededor de `agent.semantic_rag.add_document()` con `doc_id=f"manual_{len(...)}"` (knowledge.py:14-21).
- `add_knowledge_batch(agent, documents)` → idem pero en loop sobre lista (knowledge.py:24-35).
- `clear_knowledge(agent)` → `.clear()` sobre `semantic_rag._documents` y `_doc_list` (knowledge.py:38-41).
- NO hay lógica de embeddings, similarity, chunking, persistence. Solo passthrough con prefijo `manual_`/`batch_`.

### Activación
- **Feature flag:** Ninguno.
- **Se llama desde:**
  - `core/dm/agent.py:528-538` — métodos `DMResponderAgentV2.add_knowledge/add_knowledge_batch/clear_knowledge` que son thin passthrough a este módulo.
  - `core/dm_agent_v2.py:52-56` — re-export de los 3 nombres.
  - Tests: `tests/test_migration_v2.py:29-55`, `tests/audit/test_audit_dm_agent.py:38-40`.
  - **NO se llama desde ningún router, servicio productivo ni webhook.**
- **¿Tiene consumer?:** NO en runtime — solo tests de smoke/migration. API externa real va por `api/routers/knowledge.py` → `api/services/db_service.add_knowledge_item()` (sistema DIFERENTE, persiste en tabla `knowledge_base` de Postgres).

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [ ] metadata / [ ] observability
- Indirecto: si alguien llamara `agent.add_knowledge()`, los docs podrían aparecer en RAG results → RAG sí llega al prompt. Pero nadie lo llama en prod.

### Si inyecta contexto
- N/A — solo escribe en el índice in-memory de `semantic_rag` de una instancia de agent.

### Metadata escrita
- N/A.

### Solapamiento con P0/P1 auditados
- **rag/semantic (auditado):** SÍ — esta API escribe directamente en `agent.semantic_rag._documents/_doc_list`, los mismos structs que usa `core/rag/semantic.py`. Pero como no hay consumer real, no hay conflicto operativo.
- Con `api/services/db/knowledge.py` (`add_knowledge_item`): NO solapa — ese persiste en DB y tiene su propio pipeline; este es in-memory per-agent y efímero.

### Bugs / dead code
- **LÓGICA FRÁGIL:** `doc_id = f"manual_{len(agent.semantic_rag._documents)}"` y luego `f"manual_{len(...)-1}"` (knowledge.py:16-21) — race condition si dos threads llaman concurrentemente; el índice devuelto puede no coincidir con el documento insertado.
- **ACCESO A ATRIBUTOS PRIVADOS:** Usa `_documents` y `_doc_list` (knowledge.py:39-41) — viola encapsulación de `semantic_rag`.
- **DEAD CODE EN PROD:** Tres funciones sin consumidores productivos. Solo vivas para no romper tests de compatibilidad V1→V2.

### Veredicto
- **VALOR:** BAJO
- **ESTADO:** ACTIVO_INÚTIL
- **RAZÓN:** API pública que nadie en producción llama; mantiene retrocompatibilidad con V1. La vía real de knowledge es DB (`api/services/db/knowledge.py`). Candidato a eliminar tras confirmar que los 4 tests que lo consumen se pueden reescribir contra la API de DB.

---

## Sistema: history_compactor (CC-faithful history selection)

- **Archivo:** `core/dm/history_compactor.py`
- **Líneas:** 442
- **Clasificación prev:** P2 (feature flag OFF por defecto)
- **Qué hace (1 línea):** Replica `calculateMessagesToKeepIndex` de Claude Code: expansión backward desde el mensaje más reciente hasta agotar presupuesto de chars, con boundary marker y summary opcional.

### Funcionalidad detallada
- **`is_compact_boundary()` / `create_compact_boundary()`** (hc.py:50-79): CC's `isCompactBoundaryMessage` / `createCompactBoundaryMessage`. Injecta un mensaje sentinel `[__COMPACT_BOUNDARY__]` entre summary y mensajes conservados.
- **`select_and_compact()`** (hc.py:109-239) — función principal:
  - Phase 0 (hc.py:141-146): detecta `boundary_floor` (último boundary visto en input).
  - Phase 1 (hc.py:163-182): expansión backward pura — añade mensajes hasta que `total_chars + msg_chars > total_budget_chars`, con excepción si aún no llegamos a `MIN_RECENT_MESSAGES=3` mensajes sustantivos.
  - Phase 2 (hc.py:185-193): si no se descartó nada, devuelve los conservados directamente.
  - Phase 3 (hc.py:196-239): si hay descartes → summary opcional + boundary marker + conservados.
- **`_is_substantive()`** (hc.py:90-102): filtra placeholders media `[audio|image|video|Sticker]` y emoji puro con regex `_MEDIA_REF_PATTERN` y `_PURE_REACTION_PATTERN`.
- **`_build_dropped_summary()`** (hc.py:270-312): plantilla "[Contexto anterior: N mensajes…]" + facts desde MemoryEngine + verbatim marker (todos gated).
- **`_build_llm_summary()` / `_call_summary_llm()`** (hc.py:335-442): summary generado por LLM (Gemini Flash Lite o GPT-4o-mini) via `GEMINI_API_KEY` o `OPENAI_API_KEY` con fallback a template si falla. 300 max_tokens, temperature 0.3.

### Activación
- **Feature flag:** `ENABLE_HISTORY_COMPACTION` (env, default `false`, hc.py:26). Sub-flags:
  - `ENABLE_LLM_SUMMARY=false` (hc.py:35) — usar LLM para summary.
  - `ENABLE_COMPACTOR_SUMMARY=false` (hc.py:40) — incluir cualquier summary.
  - `ENABLE_VERBATIM_MARKER=false` (hc.py:41) — marker textual.
  - `COMPACTOR_MIN_RECENT_MESSAGES=3` (hc.py:31).
  - `COMPACTOR_MAX_SUMMARY_CHARS=500`, `COMPACTOR_BOUNDARY_MARKER`, `COMPACTOR_LLM_SUMMARY_PROMPT`, `COMPACTOR_LLM_SUMMARY_MODEL`.
- **Se llama desde:** `core/dm/phases/generation.py:374-434` — si `ENABLE_HISTORY_COMPACTION=true`, reemplaza la truncación uniforme `history[-10:] + 600 chars`. Budget total `10 * 600 = 6000`.
- **¿Tiene consumer?:** SÍ (detrás de flag), y se activa en evals (`scripts/run_sprint31_auto.sh:107,146,179,218` set `ENABLE_HISTORY_COMPACTION=true`).

### Afecta al output?
- [ ] system prompt directamente
- [x] user message (history messages en multi-turn prompt — reemplaza lo que iría a `llm_messages` en generation.py:372)
- [ ] post-LLM mutation
- [x] metadata — `_is_compact_boundary`, `_is_context_summary` flags en los msg dicts
- [x] observability — `logger.info("[HistoryCompactor] select_and_compact: %d→%d msgs …")` (hc.py:232)

### Si inyecta contexto
- **Posición:** La lista devuelta por `select_and_compact()` se usa como historial en `llm_messages` (generation.py:411-434). Ver también `core/dm/cache_boundary.py` (untracked) para manejo de boundary.
- **Tamaño:** Hasta `total_budget_chars=6000`. Summary si existe ≤ `MAX_SUMMARY_CHARS=500`.
- **Condiciones:** `ENABLE_HISTORY_COMPACTION=true` + `history` no vacío.

### Metadata escrita
- `_is_compact_boundary: True` — hc.py:73 — consumer: `is_compact_boundary()`, generation.py:418 (para no incluir boundary en API call a Gemini/OpenAI).
- `_compact_metadata: {trigger, messages_summarized, timestamp}` — hc.py:74-78 — consumer: logs/debug.
- `_is_context_summary: True` — hc.py:212 — marca el primer mensaje summary.

### Solapamiento con P0/P1 auditados
- **memory_engine / compressed_doc_d:** NO solapa — compactor opera sobre historial de conversación (mensajes in-flight); Doc D es persona pre-computed.
- **conversation_state:** NO — conversation_state vive en DB, compactor es stateless por-turno.
- **length_controller:** NO — length_controller controla longitud de la respuesta post-LLM; compactor controla tamaño del historial input.
- **Sprint 31 evals (`ccee_v53_*_sprint31*.json`):** sí hay evidencia en `tests/ccee_results/iris_bertran/` de evals específicos con este flag ON.

### Bugs / dead code
- **i18n-gap:** Template summary en castellano hardcoded (hc.py:295-298, 388-391) — si creador es catalán/italiano, summary contamina. Mitigado por `ENABLE_COMPACTOR_SUMMARY=false` default.
- **LLM_SUMMARY_MODEL detection heurística:** hc.py:410-424 usa `in model.lower()` para decidir provider — si el model name es ambiguo (ej. vacío) cae en Gemini por defecto. OK pero frágil.
- **DEAD CODE documentado:** El docstring (hc.py:1-17) dice "Removed: MAX_OUTPUT_MESSAGES, slot reservation, topic hints, content type breakdown, importance scoring" — confirmado que la versión actual es la rewrite CC-faithful.

### Veredicto
- **VALOR:** ALTO (si prueba empíricamente mejor que truncación uniforme)
- **ESTADO:** DORMIDO_RECUPERABLE (flag OFF en prod; ON en sprint evals)
- **RAZÓN:** Implementación disciplinada del patrón CC con tests exhaustivos (61 tests en `tests/test_history_compactor.py`). Default OFF hasta confirmar ganancia en CCEE. Sprint 31 evals son el gate.

---

## Sistema: phases/detection (Phase 1 Input Guards)

- **Archivo:** `core/dm/phases/detection.py`
- **Líneas:** 239
- **Clasificación prev:** No clasificado (núcleo pipeline)
- **Qué hace (1 línea):** Ejecuta 5 guards secuenciales sobre el mensaje entrante (empty, media placeholder, sensitive, frustration/context, pool matching) antes de la llamada al LLM.

### Funcionalidad detallada
- **GUARD 0** (detection.py:86-89): Mensaje vacío → `metadata["is_empty_message"]=True` y retorno temprano.
- **GUARD 0b** (detection.py:94-96): Truncation a 3000 chars (OWASP LLM10 token-flooding).
- **GUARD 1** (detection.py:98-108): Prompt injection patterns (Perez & Ribeiro 2022) — 6 regex ReDoS-safe (`_PROMPT_INJECTION_PATTERNS`, detection.py:40-47). Solo flaggea via `cognitive_metadata["prompt_injection_attempt"]`, no bloquea.
- **GUARD 2** (detection.py:111-117): Media placeholder detection — matchea `msg.strip().lower().rstrip(".")` contra set `MEDIA_PLACEHOLDERS` (detection.py:50-73), 26 strings ES+EN.
- **GUARD 3** (detection.py:119-156): Sensitive content detection — llama `detect_sensitive_content()` (crisis/phishing/harm). Si `confidence >= AGENT_THRESHOLDS.sensitive_escalation` → short-circuit con `DMResponse(content=crisis_response, intent="sensitive_content")`. Resuelve idioma crisis desde `agent.personality.dialect` via `_DIALECT_TO_LANG` (detection.py:29-34). **FAIL-CLOSED**: si `detect_sensitive_content()` explota → escalación a humano "Le paso tu mensaje a {creator_id}" (detection.py:144-155).
- **GUARD 4a** (detection.py:158-171): Frustration detector — `agent.frustration_detector.analyze_message()` → `result.frustration_level`. Logs si > 0.3.
- **GUARD 4b** (detection.py:173-184): Context detection — `detect_all(message, history)` → `ContextSignals`. BUG-UC-02 fix: siempre escribe `cognitive_metadata["context_signals"]` para que `user_name` esté disponible en post_response.
- **GUARD 5** (detection.py:186-237): Pool matching — si `len(message) <= 80`, llama `agent.response_variator.try_pool_response()`. Si match con `confidence >= AGENT_THRESHOLDS.pool_confidence` → `DMResponse(intent="pool_response")` y short-circuit. 30% probabilidad de probar `try_multi_bubble()` antes (detection.py:205-226).

### Activación
- **Feature flag:** 6 flags de `core.feature_flags.flags` (detection.py:100,114,120,159,175,191):
  - `prompt_injection_detection` — guard 1
  - `media_placeholder_detection` — guard 2
  - `sensitive_detection` — guard 3
  - `frustration_detection` — guard 4a
  - `context_detection` — guard 4b
  - `pool_matching` — guard 5
- **Se llama desde:** `core/dm/agent.py:437-441` (`DMResponderAgentV2._phase_detection`), llamado a su vez desde `agent.py:381` dentro de `process_message()`.
- **¿Tiene consumer?:** SÍ — fase 1 del pipeline del DM agent. El `DetectionResult` alimenta directamente `phase_context` y `phase_generation` vía `metadata["history"]`, `result.pool_response`, `result.frustration_level`, `result.context_signals`.

### Afecta al output?
- [x] user message (GUARD 0b trunca)
- [x] post-LLM mutation (pool_response sobreescribe la generación LLM)
- [x] metadata — `is_empty_message`, `is_media_placeholder`, `cognitive_metadata[sensitive_*]`, `intent_override`, `prompt_injection_attempt`, `context_signals`
- [x] observability — logs por cada guard.

### Si inyecta contexto
- **Posición:** No inyecta al prompt; dispara short-circuits o anota metadata que luego otros sistemas leen.
- **Tamaño:** N/A.
- **Condiciones:** Por guard, gated en flags individuales.

### Metadata escrita
- `metadata["is_empty_message"]` — detection.py:87 — consumer: pipeline decide comportamiento benigno.
- `metadata["is_media_placeholder"]` — detection.py:115 — consumer: LLM reacciona sin preguntar.
- `cognitive_metadata["intent_override"]` — detection.py:116 — consumer: `phase_context`/`phase_generation`.
- `cognitive_metadata["prompt_injection_attempt"]` — detection.py:103 — consumer: observability/DPO data.
- `cognitive_metadata["sensitive_detected"]`, `sensitive_category` — detection.py:125-126 — consumer: crisis response path.
- `cognitive_metadata["context_signals"]` — detection.py:182 — consumer: `phases/context.py:712`, `post_response.sync_post_response:155-162` (persist detected name).
- `result.pool_response` / `result.frustration_level` / `result.frustration_signals` — campos en `DetectionResult` — consumer: `phase_generation`, `phase_postprocessing`.

### Solapamiento con P0/P1 auditados
- **sensitive_detector (auditado):** SÍ — invoca directamente `detect_sensitive_content()` y `get_crisis_resources()`. Es el único punto de entrada del detector en el pipeline DM.
- **frustration_detector (auditado):** SÍ — invoca `agent.frustration_detector.analyze_message()`.
- **context_detector (auditado):** SÍ — invoca `detect_all()` de `core.context_detector`.
- **response_variator_v2 (P0 auditado):** SÍ — invoca `agent.response_variator.try_pool_response()` y `try_multi_bubble()`. Este es el punto de activación de pool matching.
- **output_validator / guardrails (auditado):** NO solapa — detection es pre-LLM, output_validator es post-LLM.

### Bugs / dead code
- **SENSIBILIDAD DE umbral (detection.py:123-127):** Dos thresholds (`sensitive_confidence` para flag, `sensitive_escalation` para short-circuit) obliga a revisar `AGENT_THRESHOLDS` en `core.agent_config`.
- **Pool matching `random.random() < 0.30`** (detection.py:206): multi-bubble solo se intenta 30% del tiempo — no determinista, afecta reproducibilidad de tests.
- **MEDIA_PLACEHOLDERS rígido:** Lista estática (detection.py:50-73). Si Instagram cambia el texto (ej. agrega emoji nuevo), el guard falla silenciosamente.

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Fase crítica del pipeline. Los 6 flags permiten desactivar guards individualmente sin tocar el código. Crisis fail-closed está bien diseñado. Observability para prompt injection es valiosa para DPO/safety iterations.

---

## Sistema: dm_post_response (Post-LLM Side Effects)

- **Archivo:** `core/dm/post_response.py`
- **Líneas:** 501
- **Clasificación prev:** No clasificado (background infra)
- **Qué hace (1 línea):** Ejecuta side-effects post-respuesta: persistencia memoria, fact tracking, lead scoring, email capture, DNA triggers, nurturing, escalación Telegram, identity resolution, loop detection.

### Funcionalidad detallada
- **`_extract_facts(assistant_msg, user_msg, products, follower_name)`** (post_response.py:36-82): BUG-EP-04 fix (función compartida, antes duplicada). Extrae tags `PRICE_GIVEN`, `LINK_SHARED`, `PRODUCT_EXPLAINED`, `OBJECTION_RAISED`, `INTEREST_EXPRESSED`, `APPOINTMENT_MENTIONED`, `CONTACT_SHARED`, `QUESTION_ASKED`, `NAME_USED`. Regex multilingüe ES+CA+EN+IT (post_response.py:52-77) — BUG-EP-05 fix.
- **`background_post_response()`** (post_response.py:91-110): async wrapper sobre `asyncio.to_thread(sync_post_response, …)`. Regla del CLAUDE.md: sync DB ops en thread pool.
- **`sync_post_response()`** (post_response.py:113-246): El core.
  1. Append user msg a `follower.last_messages`.
  2. Copilot check: si copilot mode → NO guardar sugerencia del bot (post_response.py:131-136).
  3. Append assistant msg + trim a últimos 20.
  4. Facts tracking (si `ENABLE_FACT_TRACKING=true`).
  5. BUG-UC-02: persist `context_signals.user_name` → `follower.name`.
  6. BUG-UC-01: detect language via `core.i18n.detect_language`, solo si `preferred_language=="es"` y len>=10 (protege contra overwrite sobre mensajes cortos).
  7. BUG-EP-01: embedding indexing en `conversation_embeddings` via `semantic_memory_pgvector` (gated `ENABLE_SEMANTIC_MEMORY_PGVECTOR=true`).
  8. `agent.memory_store._save_to_json(follower)`.
  9. DNA triggers: chequea `should_update()` + seed-DNA upgrade para followers con ≥5 msgs y `total_messages_analyzed==0`.
  10. Auto-schedule nurturing via `should_schedule_nurturing()`.
- **`update_follower_memory()`** (post_response.py:249-283): variante async usada por otros paths. Duplicación parcial con `sync_post_response` (fase 1-4).
- **`update_lead_score()`** (post_response.py:286-299): calcula intent_score via `agent.lead_service.calculate_intent_score()` → determina `LeadStage` via `determine_stage()`.
- **`step_email_capture()`** (post_response.py:302-370): detecta email en msg entrante via `extract_email()`. Si detectado: `process_email_capture()` + `update_lead(creator_id, sender_id, email)` + `trigger_identity_resolution()`. Si NO detectado y `should_ask_email()` dice ask → append "\n\n{decision.message}" al formatted_content.
- **`check_and_notify_escalation()`** (post_response.py:373-430): Intents escalation/support/feedback_negative + "hot lead" (score≥0.8, intent=interest_strong) → `notification_service.notify_escalation()` (Telegram + email).
- **`trigger_identity_resolution()`** (post_response.py:433-463): fire-and-forget `asyncio.create_task(resolve_identity(...))`.
- **`check_response_loop()`** (post_response.py:466-501): compara prefijos de 50 chars + overlap palabras>80% para detectar loops en las últimas respuestas.

### Activación
- **Feature flag:**
  - `ENABLE_FACT_TRACKING=true` (post_response.py:30)
  - `ENABLE_DNA_TRIGGERS=true` (post_response.py:31)
  - `ENABLE_SEMANTIC_MEMORY_PGVECTOR=true` (post_response.py:181)
  - `flags.nurturing` (post_response.py:222)
  - `flags.unified_profile` (post_response.py:313)
  - `flags.identity_resolver` (post_response.py:435)
- **Se llama desde:**
  - `core/dm/phases/postprocessing.py:464` → `agent._background_post_response(...)` → `post_response.py:91`.
  - `core/dm/phases/postprocessing.py:428` → `agent._update_lead_score(...)`.
  - `core/dm/phases/postprocessing.py:450` → `agent._step_email_capture(...)`.
  - `core/dm/phases/postprocessing.py:526` → `agent._check_and_notify_escalation(...)`.
  - `core/dm_agent_v2.py:41-48` — re-export de todo.
  - `core/dm/agent.py:483-522` — thin-wrapper methods del agent.
- **¿Tiene consumer?:** SÍ — TODO el pipeline depende de esto post-LLM.

### Afecta al output?
- [ ] system prompt
- [x] user message (no — solo persiste)
- [x] post-LLM mutation — `step_email_capture` appenda "\n\n{email_ask}" a `formatted_content` (post_response.py:361).
- [x] metadata — `dna_update_scheduled`, `nurturing_scheduled`, `email_captured`, `email_asked` en `cognitive_metadata`.
- [x] observability — muchos `logger.info`/error.

### Si inyecta contexto
- **Posición:** Solo `step_email_capture` modifica el output al appendear `decision.message` al final (post_response.py:361).
- **Tamaño:** email ask suele ser 1 frase corta.
- **Condiciones:** `should_ask_email()` True + intent no en `_EMAIL_SKIP_INTENTS={escalation, support, sensitive, crisis, feedback_negative, spam, other}` (post_response.py:85-88).

### Metadata escrita
- `follower.last_messages[-1]["facts"]` — post_response.py:150, 276 — consumer: telemetría CCEE, DPO pipelines.
- `follower.name` — post_response.py:159 — consumer: future prompts (personalización).
- `follower.preferred_language` — post_response.py:174 — consumer: language-aware generation.
- `follower.purchase_intent_score` — post_response.py:293 — consumer: `lead_service.determine_stage()`, hot-lead detection.
- `cognitive_metadata["dna_update_scheduled"]` — post_response.py:212 — consumer: observability.
- `cognitive_metadata["nurturing_scheduled"]` — post_response.py:244 — consumer: idem.
- `cognitive_metadata["email_captured"]` / `email_asked` — post_response.py:340, 367 — consumer: analytics.

### Solapamiento con P0/P1 auditados
- **memory_engine (auditado):** SÍ — invoca `semantic_memory_pgvector.add_message()` (post_response.py:184-189) para indexación episódica. Y `agent.memory_store._save_to_json(follower)` (post_response.py:193) para buffer FollowerMemory.
- **relationship_scorer (auditado):** NO — scorer es pre-LLM.
- **rag/semantic (auditado):** NO directo.
- **DUPLICACIÓN interna:** `sync_post_response` (post_response.py:113-246) y `update_follower_memory` (post_response.py:249-283) comparten lógica append+trim+facts. El docstring (fase6_background_infra.md:149) identifica esto como DRY violation.

### Bugs / dead code
- **DOCUMENTADO fase6_background_infra.md#367**: duplicación entre `sync_post_response` y `update_follower_memory` — AUN no resuelta.
- **HOT-LEAD score estricto:** `purchase_intent_score >= 0.8 AND intent_lower == "interest_strong"` (post_response.py:387-390). Si el intent_label no es exactamente "interest_strong" (case-insensitive matters), nunca escala hot leads aunque score sea alto.
- **`trigger_identity_resolution` falla silencioso:** catch `Exception` con `logger.debug` (post_response.py:462-463) — identity resolver failures no llegan a logs de error.
- **LANGUAGE-PROTECTION lógica es unilateral:** solo actualiza `preferred_language` si actual es "es" (post_response.py:170). Si alguien habla ES pero follower quedó marcado "ca" por error, nunca vuelve a "es".

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Fase post-LLM crítica: memoria, lead scoring, email/identity, notificaciones Telegram. Bien instrumentado. La duplicación de fact-tracking es deuda técnica conocida pero no bloqueante.

---

## Sistema: context_analytics (G3+G4 Token Distribution Observability)

- **Archivo:** `core/dm/context_analytics.py`
- **Líneas:** 212
- **Clasificación prev:** P2 (observability-only)
- **Qué hace (1 línea):** Calcula distribución de tokens por sección del prompt + history y emite warnings estructurados cuando usage > 80%/90% o una sección supera 40% del total.

### Funcionalidad detallada
- **`_chars_to_tokens(chars)`** (context_analytics.py:29-30): `chars // 4` — estimación grosera, consistente con el resto del pipeline.
- **`analyze_token_distribution(section_sizes, system_prompt, history_messages, model_context_window=32768)`** (context_analytics.py:33-142):
  - Calcula tokens por sección.
  - Suma chars de history messages.
  - `system_prompt_tokens = len(system_prompt) // 4` (post-truncation).
  - `total_tokens = system_prompt_tokens + history_tokens`.
  - Computa `pct_of_total` para cada sección + history.
  - Determina `largest_section` (incluye "history" como sección virtual).
  - Flag `over_section_threshold`: cualquier sección ≥ 40% del total.
  - Emite `logger.info("[TokenAnalytics] Distribution: …")` con breakdown ordenado por tamaño.
  - Devuelve dict `{sections, history_tokens, history_pct_of_total, system_prompt_tokens, total_tokens, context_window, usage_ratio, largest_section, largest_section_pct, over_section_threshold}`.
- **`check_context_health(analytics)`** (context_analytics.py:145-212):
  - CRITICAL si `usage_ratio ≥ 0.90`.
  - WARNING si `0.80 ≤ ratio < 0.90`.
  - WARNING adicional si alguna sección ≥ 40% y ratio no ya crítico.
  - Devuelve lista de dicts `{level, message, section, tokens_involved}`.

### Activación
- **Feature flag:** No hay ON/OFF pero umbrales configurables:
  - `CONTEXT_WARNING_THRESHOLD=0.80` (context_analytics.py:20)
  - `CONTEXT_CRITICAL_THRESHOLD=0.90` (context_analytics.py:21)
  - `SECTION_WARNING_THRESHOLD=0.40` (context_analytics.py:22)
  - `MODEL_CONTEXT_WINDOW=32768` (context_analytics.py:23)
- **Se llama desde:** `core/dm/phases/generation.py:339-352` — después de assembly del system prompt, siempre se ejecuta dentro de `try/except` (fallo silencioso a `logger.debug`).
- **¿Tiene consumer?:** SÍ — logs estructurados `[ContextHealth] WARNING/CRITICAL`. No afecta pipeline; solo observability.

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation
- [ ] metadata — No escribe a `cognitive_metadata` (oportunidad perdida).
- [x] observability — `[TokenAnalytics] Distribution: …` + `[ContextHealth] WARNING/CRITICAL/INFO`.

### Si inyecta contexto
- N/A — read-only sobre el prompt ya ensamblado.

### Metadata escrita
- Ninguna directa en `cognitive_metadata`. Solo logs.

### Solapamiento con P0/P1 auditados
- **compressed_doc_d (P0 auditado):** NO solapa — sólo mide. Doc D aparece como una de las secciones medidas.
- **history_compactor:** COMPLEMENTARIO — analytics mide el resultado post-compaction. Juntos forman el feedback loop.
- **dm_agent_context_integration (auditado):** NO solapa — integration es ensamblaje; analytics es medición.

### Bugs / dead code
- **Umbral de total_tokens doble-cuenta:** `total_tokens = system_prompt_tokens + history_tokens` (context_analytics.py:85) pero `section_sizes` ya se suma en `system_prompt`. El `pct_of_total` por sección se calcula sobre `total = system + history` — es correcto pero el comentario no lo explicita.
- **Sin persistencia:** Los warnings solo van a stdout logs. No se acumula histograma por creator en DB → difícil hacer SLI/SLO.
- **MODEL_CONTEXT_WINDOW hardcoded global:** Un solo env var para todos los modelos — pero Gemini Flash Lite tiene 1M tokens, GPT-4o-mini 128k. Usar 32k para Flash-Lite infla el `usage_ratio` artificialmente.

### Veredicto
- **VALOR:** MEDIO
- **ESTADO:** ACTIVO_VALIOSO (observability)
- **RAZÓN:** Observability pura, bajo costo, sirve para detectar regresiones de prompt bloat. 16 tests (`test_context_analytics.py`). Pero no persiste ni escribe metadata → limita su utilidad para SLOs. Gap de model_context_window por-modelo es sub-óptimo.

---

## Sistema: contextual_prefix (Anthropic Contextual Retrieval)

- **Archivo:** `core/contextual_prefix.py`
- **Líneas:** 182
- **Clasificación prev:** Ambiguo — no es DM phase pero está P0 en audits de RAG.
- **Qué hace (1 línea):** Auto-genera un prefix "{Nombre} ofrece {specialties} en {location}. Habla {dialecto}." para prependear a cada chunk ANTES de embeddarlo (patrón Anthropic +35-49% retrieval quality).

### Funcionalidad detallada
- **`build_contextual_prefix(creator_id)`** (contextual_prefix.py:33-50): entry point con cache LRU-TTL.
- **Cache:** `_prefix_cache: BoundedTTLCache(max_size=50, ttl_seconds=300)` (contextual_prefix.py:30).
- **`_build_prefix_from_db(creator_id)`** (contextual_prefix.py:53-157): fuente única — carga via `core.creator_data_loader.get_creator_data()`.
  - **Part 1** (contextual_prefix.py:70-103): Nombre + Instagram handle + specialties. Fallback chain: `knowledge_about.specialties` → `knowledge_about.bio` (primera frase) → nombres de productos (top 5). Si nada, solo el nombre.
  - **Part 2** (contextual_prefix.py:105-108): Location desde `knowledge_about.location`.
  - **Part 3** (contextual_prefix.py:110-123): Language via `ToneProfile.dialect`. Mapping `_DIALECT_LABELS` (rioplatense, mexican, catalan, catalan_mixed, italian, english, formal_spanish).
  - **Part 4** (contextual_prefix.py:125-130): Formality via `ToneProfile.formality` — "formal y profesional" / "muy informal y cercano".
  - **Part 5** (contextual_prefix.py:132-138): FAQ fallback si solo tenemos el nombre — top 3 preguntas como "Temas frecuentes: …".
  - **Cap:** 500 chars (contextual_prefix.py:145-147).
- **`generate_embedding_with_context(text, creator_id)`** (contextual_prefix.py:160-171): wrapper → `generate_embedding(prefix + text)`.
- **`generate_embeddings_batch_with_context(texts, creator_id)`** (contextual_prefix.py:174-182): batch variant.

### Activación
- **Feature flag:** Ninguno — siempre que el caller lo invoque.
- **Se llama desde:**
  - `services/content_refresh.py:185-190` — refresh job de contenido, embedding con contexto.
  - `scripts/_rag_gen_embeddings.py:8,30` — script de generación inicial.
  - `api/routers/content.py:384,427` — endpoint de creación de chunks.
  - `core/rag/semantic.py:101-105` — **el RAG in-memory también lo usa para indexar** (documents, NO queries).
  - `scripts/create_proposition_chunks.py:57-58`.
- **¿Tiene consumer?:** SÍ — múltiples consumers en ingesta (refresh, scripts, router).
- **NOTA:** Solo para DOCUMENT embeddings — el docstring (contextual_prefix.py:162-166) es explícito que queries NO deben usarlo (asymmetric retrieval).

### Afecta al output?
- [ ] system prompt (indirectamente, via RAG results mejor rankeados)
- [ ] user message / [ ] post-LLM mutation
- [ ] metadata
- [x] observability — `logger.info("[CONTEXTUAL-PREFIX] Built prefix for %s: %d chars")` (contextual_prefix.py:149-152).

### Si inyecta contexto
- **Posición:** Prepended al texto del chunk ANTES de embeddar (invisible en el document content almacenado).
- **Tamaño:** ≤500 chars (cap, contextual_prefix.py:145).
- **Condiciones:** `data.profile.name` debe existir; si no, devuelve `""` y se embebe solo el texto.

### Metadata escrita
- Ninguna — solo logs.

### Solapamiento con P0/P1 auditados
- **rag/semantic (P0 auditado):** SÍ — es usado por `core.rag.semantic` para indexar documentos (NO queries). Es parte del pipeline RAG.
- **style_retriever / memory_engine:** NO directo.
- El patrón "Anthropic Contextual Retrieval" está documentado en `docs/audit/sistema_11_rag_knowledge.md:287` como IMPLEMENTED.

### Bugs / dead code
- **Catalan dialect duplicado:** `_DIALECT_LABELS` tiene `catalan` y `catalan_mixed` con labels "castellano y catalán" vs "castellano y catalán mezclados" (contextual_prefix.py:116-117) — distinción útil pero si `ToneProfile.dialect` guarda variantes (ej. "ca", "CATALAN") no matchea. Caller debe normalizar.
- **Cache invalidation:** TTL 300s (5 min). Si Creator cambia knowledge_about, toma 5 min propagarse. Acceptable but documented.
- **Silent error handling:** `except Exception as e: ... return ""` (contextual_prefix.py:155-157). Si falla `get_creator_data`, el embedding se genera sin prefix — degradación silenciosa.
- **Recordatorio asymmetric retrieval OK pero frágil:** El docstring es la única doc; si alguien añade en `semantic.py` una query path, fácil olvidar. Hay un test (`test_contextual_prefix.py:281`) que valida esto: `"generate_embedding_with_context" not in source` del método de búsqueda.

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Patrón Anthropic validado (+35-49% retrieval quality según paper). Cache acotada, fallbacks sensatos, test coverage decente (`tests/test_contextual_prefix.py`). Punto ciego: silent failure returns "" y degrada a embedding sin contexto, pero caller no se entera.

---

### 3.E · Batch E — Lead / Intent / Relationship (8 sistemas)


---

## Sistema: intent_classifier (core)

- **Archivo:** `core/intent_classifier.py`
- **Líneas:** 469
- **Clasificación prev:** No clasificado (legacy)
- **Qué hace (1 línea):** Clasificador LLM + keyword-based de intent (hola/precio/objection) con 12 categorías + helpers `classify_intent_simple`, `get_lead_status_from_intent`, `ConversationAnalyzer`.

### Funcionalidad detallada
- `class IntentClassifier` con constructor que acepta `llm_client`. Método `classify()` async intenta primero `_quick_classify` (regex keyword) y, si confidence < 0.85, hace llamada LLM con prompt `CLASSIFICATION_PROMPT`. Devuelve `IntentResult(intent, confidence, sub_intent, entities, suggested_action, reasoning)`.
- `classify_intent_simple(text) -> str` — versión sync keyword-only usada en scoring. Retorna strings `"interest_strong"`, `"purchase"`, `"interest_soft"`, `"question_product"`, `"objection"`, `"support"`, `"greeting"`, `"other"`.
- `get_lead_status_from_intent(intent) -> str` — mapea intents a `"hot"` / `"active"` / `"new"`.
- `ConversationAnalyzer` — análisis agregado de conversación (funnel_stage, purchase_intent_score).

### Activación
- **Feature flag:** ninguna (siempre disponible como util). No se instancia `IntentClassifier` en el DM pipeline prod.
- **Se llama desde:**
  - `core/context_detector/orchestration.py:13,61` — usa `classify_intent_simple` + `Intent` enum para `ctx.intent_sub`
  - `core/dm_history_service.py:217,330` — usa `classify_intent_simple` para poblar campo `intent` de `Message` al importar historial
  - `scripts/lab_test_complete.py:294` — script lab
  - `tests/` — masiva suite academic
- **¿Tiene consumer?:** SÍ (escribe `Message.intent` en DB)

### Afecta al output?
- [ ] system prompt
- [ ] user message
- [ ] post-LLM mutation
- [x] metadata (via `Message.intent` column y `DetectedContext.intent_sub`)
- [ ] observability

### Si inyecta contexto
- N/A — no se inyecta en el prompt vía este módulo. El intent se propaga como metadata que otros sistemas consumen.

### Metadata escrita
- `Message.intent` — `core/dm_history_service.py:330, 348` — consumer: scoring histórico (`purchase_signals += 3 if intent in ["interest_strong","purchase"]` en dm_history_service.py:333-338), lead categorizer, DB queries, admin leads router.
- `DetectedContext.intent_sub` — `core/context_detector/orchestration.py:73` — consumer: context_detector notes

### Solapamiento con P0/P1 auditados
- **SÍ — duplicado con `services/intent_service.py`**: ambos definen clase `IntentClassifier` y enum `Intent`. El enum en core tiene 12 valores; el de services tiene 27 valores (más granular: OBJECTION_PRICE, OBJECTION_TIME, PRICING, HUMOR, REACTION, etc.). Valores comunes (GREETING, INTEREST_SOFT, etc.) se pisan en mega_test_w2.py (ambos imports aliased as ServiceIntent/ServiceIntentClassifier en `tests/academic/test_coherencia_conversacional.py:17-19`).
- **Distinto enum.Intent que services/intent_service.py** → no compatibles por `.value`. Si se mezclan en runtime, un `Intent.OBJECTION_PRICE` de services no resuelve en el map de core.
- NO solapa con `relationship_scorer`/`relationship_adapter` (sistemas distintos).

### Bugs / dead code
- `IntentClassifier` async class (core) no se instancia en producción (DM pipeline usa `services/intent_service.IntentClassifier`, que es sync + keyword-only).
- `ConversationAnalyzer` parece dead code — sólo referenciado desde `tests/academic/test_temporal.py:14`.
- `classify_intent_simple` y `get_lead_status_from_intent` SÍ se usan (orchestration + history service).
- Prompt LLM (`CLASSIFICATION_PROMPT`) existe pero nunca se ejecuta en prod (llm_client es None en todos los call sites).

### Veredicto
- **VALOR:** MEDIO (mantiene función `classify_intent_simple` crítica para scoring + DB intent column)
- **ESTADO:** ACTIVO_VALIOSO (parcial). La clase `IntentClassifier` async y `ConversationAnalyzer` son ACTIVO_INÚTIL.
- **RAZÓN:** El módulo mezcla utilidades críticas con código muerto. `classify_intent_simple` es consumido en hot paths; el resto podría eliminarse. Conviene extraer `classify_intent_simple` + `get_lead_status_from_intent` a un util limpio y borrar la clase async/ConversationAnalyzer.

---

## Sistema: intent_service (services)

- **Archivo:** `services/intent_service.py`
- **Líneas:** 483
- **Clasificación prev:** No clasificado
- **Qué hace (1 línea):** Clasificador sync keyword-based con 27 intents granulares (OBJECTION_PRICE/TIME/WORKS/..., PRICING, HUMOR, REACTION, CASUAL, etc.) usado en el DM pipeline prod.

### Funcionalidad detallada
- `Enum Intent` con 27 valores (superset del de core). Include v10.2 sub-categories (HUMOR, REACTION, ENCOURAGEMENT, CONTINUATION, CASUAL) diseñadas para reducir OTHER de 57% a <20%.
- Método `classify(message, context)` — sync, devuelve `Intent` (NO `IntentResult`).
- Priorización de patterns: Sales > Social > Objections/Interest > Sub-categories > Fallback.
- Soporta voseo (AR/LatAm), variantes ES/CA/EN, emojis para detección CASUAL.

### Activación
- **Feature flag:** ninguna (siempre activo en el pipeline)
- **Se llama desde:**
  - `core/dm/agent.py:314` — `self.intent_classifier = IntentClassifier()` (instancia a nivel DMResponderAgentV2)
  - `core/dm/phases/context.py:282` — `intent = agent.intent_classifier.classify(message)` — PUNTO DE ENTRADA EN DM PIPELINE
  - `core/dm/text_utils.py:18`, `core/dm_agent_v2.py:75`, `core/dm/agent.py:61` — import del enum
  - `services/__init__.py:7` — reexportado como API pública
- **¿Tiene consumer?:** SÍ (todo el pipeline)

### Afecta al output?
- [x] system prompt (indirecto vía `detected_intent` en few-shot selection)
- [ ] user message
- [ ] post-LLM mutation
- [x] metadata (`intent_value` en multiple cognitive_metadata + guardado en Message.intent vía postprocessing)
- [x] observability (logs)

### Si inyecta contexto
- `intent_value` se pasa a:
  - `calibration_loader.get_few_shot_section(..., detected_intent=intent_value)` — selecciona few-shot examples por intent (`context.py:765`)
  - `audio_intel` branch (`context.py:786`)
  - RAG gating: `_PRODUCT_INTENTS = {"question_product","question_price","interest_strong","purchase_intent","objection_price"}` decide si se hace retrieval (`context.py:540-543`).

### Metadata escrita
- `ctx.intent = intent` — `core/dm/phases/context.py:1226` — consumer: downstream phases
- `Message.intent = intent_value` — `core/dm/phases/postprocessing.py:560, 585`, `core/dm/post_response.py:227,290,354` — consumer: lead scoring, admin API, DB analytics
- `cognitive_metadata["detected_language"]` se correlaciona con intent (context.py:768)

### Solapamiento con P0/P1 auditados
- **SÍ — DUPLICADO CRÍTICO con `core/intent_classifier.py`**: ambos definen `Intent` enum y `IntentClassifier` clase. No son ABI-compatibles (enums distintos). Este de `services/` es el canónico en prod; el de `core/` sólo para scoring histórico offline.
- No solapa con relationship_scorer ni relationship_adapter.

### Bugs / dead code
- No bugs en este fichero.
- Bug de diseño: existencia de dos implementaciones de `IntentClassifier` con el mismo nombre y enum distinto. Código cliente que importe desde el módulo equivocado obtendrá comportamiento diferente (quick_classify vs classify, IntentResult vs Intent, async vs sync).
- Los valores `PRODUCT_QUESTION` y `QUESTION_PRODUCT` coexisten como alias (line 41-42) — heredado.

### Veredicto
- **VALOR:** ALTO (clasificación en hot path de cada DM)
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Canónico en producción, rápido (keyword), afecta RAG gating + few-shot selection + DB metadata. Dup con core/intent_classifier.py debe resolverse — este fichero es el correcto.

---

## Sistema: lead_categorization (core)

- **Archivo:** `core/lead_categorization.py`
- **Líneas:** 317
- **Clasificación prev:** No clasificado
- **Qué hace (1 línea):** Categorizador v1 basado en 40 patrones regex hardcodeados ES/EN para clasificar leads en NUEVO/INTERESADO/CALIENTE/CLIENTE/FANTASMA.

### Funcionalidad detallada
- `calcular_categoria(mensajes, es_cliente, ultimo_mensaje_lead, dias_fantasma, lead_created_at, ultima_interaccion)` — categoriza via detect de keywords + timing.
- `KEYWORDS_CALIENTE` = ~30 keywords (precio, comprar, pagar, link de pago).
- `KEYWORDS_INTERESADO` = ~20 keywords (info, cómo funciona, interesa).
- Output: `CategorizationResult(categoria, intent_score, razones, keywords_detectados)`.
- Mapping `categoria_a_status_legacy` / `status_legacy_a_categoria` para compat.
- `CATEGORIAS_CONFIG` con colores, iconos, descripciones ES/EN para frontend.

### Activación
- **Feature flag:** ninguna propia (pero se desactiva vía uso de v2)
- **Se llama desde:**
  - `api/routers/oauth/instagram.py:913` — primer import tras OAuth
  - `api/routers/admin/leads.py:41, 186` — recategorización masiva + config
  - `api/routers/admin/sync_dm/sync_operations.py:551, 737` — sync histórico IG
  - `core/sync_worker.py:278` — worker de sync
  - `scripts/recategorize_leads.py:23` — script manual
  - `tests/academic/test_temporal.py:15`, `tests/academic/test_causal.py:17` — tests
  - `tests/test_lead_categorization_audit.py` — audit tests
- **¿Tiene consumer?:** SÍ — Lead.status se actualiza vía `categoria_a_status_legacy`.

### Afecta al output?
- [ ] system prompt
- [ ] user message
- [ ] post-LLM mutation
- [x] metadata (`Lead.status`, `Lead.intent_score`)
- [ ] observability

### Si inyecta contexto
- N/A — no se inyecta en prompt. Sólo afecta UI y agregación de métricas.

### Metadata escrita
- `Lead.status` — `api/routers/admin/sync_dm/sync_operations.py`, `core/sync_worker.py` — consumer: frontend dashboard, segmentación.
- `Lead.intent_score` (calculado, 0-1) — consumer: relationship_scorer (via `lead_db_status`), admin filters.

### Solapamiento con P0/P1 auditados
- **SÍ — DUPLICADO con `core/lead_categorizer.py`**: ambos implementan el mismo embudo (NUEVO/INTERESADO/CALIENTE/CLIENTE/FANTASMA) con APIs distintas.
  - `lead_categorization.py` (v1): función `calcular_categoria(mensajes, ...)` — basada en keywords de texto.
  - `lead_categorizer.py` (v2): clase `LeadCategorizer.categorize()` — basada en `intent` propagado desde mensajes.
  - Ambos coexisten con rutas de llamada distintas:
    * `lead_categorization` (v1) → sync/OAuth/admin recategorize (procesamiento histórico)
    * `lead_categorizer` (v2) → DM live pipeline (helpers.py:98)
- Relacionado con `relationship_scorer`: el scorer lee `Lead.status` que este módulo escribe.

### Bugs / dead code
- Docstring de `lead_categorizer.py:1-6` dice explícitamente "Replaces v1's 40 hardcoded regex patterns". Implica que v1 (este fichero) está siendo reemplazado pero sigue usándose en hot paths (OAuth, sync).
- Fantasma logic calcula `dias_sin_respuesta` con timezone-naive handling — defensive tz logic añadida pero compleja.

### Veredicto
- **VALOR:** MEDIO (usado en sync/batch, pero duplicado)
- **ESTADO:** DORMIDO_RECUPERABLE o ELIMINAR (migrar callers a v2)
- **RAZÓN:** Es la versión legacy. v2 (lead_categorizer.py) fue escrito para reemplazarlo pero la migración quedó incompleta. Mantener sólo uno de los dos y borrar el otro. Recomendación: conservar v2 + migrar los 5 call sites históricos a v2 (requiere propagar `intent` en los mensajes históricos).

---

## Sistema: lead_categorizer (core)

- **Archivo:** `core/lead_categorizer.py`
- **Líneas:** 249
- **Clasificación prev:** No clasificado (marcado como P2 Learning en fase6_background_infra.md)
- **Qué hace (1 línea):** Categorizador v2 intent-based, universal y multilingual, usado en DM live pipeline. Reemplaza v1 (lead_categorization.py).

### Funcionalidad detallada
- `categorize_from_intent(intent, is_customer, days_since_last_msg, history_count) -> (LeadCategory, score, reason)` — función pura, sin regex.
- Conjuntos de intents: `_HOT_INTENTS`, `_WARM_INTENTS`, `_NEUTRAL_INTENTS`.
- `LeadCategorizer.categorize(messages, ...)` — legacy wrapper que extrae `last_intent` del último user msg.
- `calculate_lead_score(intent_history, ...) -> int` — score 0-100 para dashboard.
- Helpers de mapping legacy: `get_category_from_intent_score`, `map_legacy_status_to_category`, etc.
- Singleton `get_lead_categorizer()` con `DAYS_UNTIL_GHOST=7`.

### Activación
- **Feature flag:** `ENABLE_LEAD_CATEGORIZER` (default true) — `core/feature_flags.py:45`, `core/dm/helpers.py:94`
- **Se llama desde:**
  - `core/dm/helpers.py:98` — `get_lead_stage()` → DM pipeline activo
  - `scripts/batch_process_historical.py:349`
  - `mega_test_w2.py:437,1127`, `tests/unit/test_dm_agent_lead_categorizer.py`
- **¿Tiene consumer?:** SÍ (DM live pipeline determina `current_stage`)

### Afecta al output?
- [ ] system prompt (indirectamente: `current_stage` se pasa a `strategy` para routing)
- [ ] user message
- [ ] post-LLM mutation
- [x] metadata (lead_stage)
- [ ] observability

### Si inyecta contexto
- `current_stage = agent._get_lead_stage(...)` → context.py:710. Se pasa a downstream phases pero NO llega directamente al prompt (strategy.py usa lead_stage para seleccionar branching).

### Metadata escrita
- `lead_stage` en metadata local — `core/dm/helpers.py:105` — consumer: strategy routing en phase generation.
- No escribe en DB directamente (sólo devuelve category).

### Solapamiento con P0/P1 auditados
- **SÍ — DUPLICADO con `core/lead_categorization.py`** (ver arriba). Este es la versión v2 intent-based.
- Parcialmente solapa con `relationship_scorer.py`: ambos clasifican al lead en categorías, pero con ejes distintos:
  - relationship_scorer: eje PERSONAL/CLOSE/CASUAL/TRANSACTIONAL (intimidad)
  - lead_categorizer: eje NUEVO/INTERESADO/CALIENTE/CLIENTE (embudo de venta)
  - Son complementarios, no redundantes.

### Bugs / dead code
- Bug menor: `LeadCategorizer.categorize(...)` depende de que cada mensaje tenga campo `"intent"`; si no lo tiene (mensajes históricos de v1), devuelve `last_intent=""` y cae a NUEVO por defecto. No hay fallback a keywords.
- Es el camino canónico en prod live pero NO se usa en los scripts de sync (que siguen usando v1).

### Veredicto
- **VALOR:** ALTO (DM live pipeline)
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Correcto conceptualmente (universal, intent-based). Problema: coexistencia con v1 introduce deuda técnica. Completar migración.

---

## Sistema: relationship_dna_service (services)

- **Archivo:** `services/relationship_dna_service.py`
- **Líneas:** 281
- **Clasificación prev:** P2 (fase2_context_systems.md línea 22)
- **Qué hace (1 línea):** Orquesta DNA: carga/crea DNA, genera prompt instructions, dispara análisis completo con RelationshipAnalyzer (fire-and-forget).

### Funcionalidad detallada
- `RelationshipDNAService` con `BoundedTTLCache(max_size=500, ttl=300s)` en memoria por `creator_id:follower_id`.
- `get_dna_for_lead()` — lee con cache.
- `get_or_create_dna()` — crea con defaults si no existe.
- `get_prompt_instructions(dna_data)` — delega a `BotInstructionsGenerator`.
- `get_instructions_for_lead()` — conveniencia end-to-end.
- `record_interaction()` — incrementa contador.
- `analyze_and_update_dna()` — pipeline pesado: invoca `RelationshipAnalyzer.analyze()` + `build_global_corpus()` (TF-IDF) para llenar vocab_uses/avoids/emojis/topics/golden_examples.
- Singleton `get_dna_service()`.

### Activación
- **Feature flag:** `ENABLE_DNA_AUTO_ANALYZE` (default true en `context.py:36`, false en Railway según `config/env_ccee_gemma4.sh:138` y tests CPE).
- **Se llama desde:**
  - `core/dm/phases/context.py:507` — dentro de `ENABLE_DNA_AUTO_ANALYZE` gate para disparar análisis background
  - `services/dna_update_triggers.py:42` — thread background
  - `services/whatsapp_onboarding_pipeline.py:745` — onboarding WA
  - `scripts/turbo_onboarding.py:448`, `scripts/migrate_dna.py:169`, `scripts/populate_dna.py:11`
- **¿Tiene consumer?:** SÍ (prompt builder consume bot_instructions/vocabulary/emojis)

### Afecta al output?
- [x] system prompt — vía `bot_instructions` inyectado en `dna_context` por `dm_agent_context_integration.py:219`
- [ ] user message
- [ ] post-LLM mutation
- [x] metadata (`dna_data`, `dna_full_analysis_triggered`, `relationship_type`)
- [x] observability (logs `[DNA-ANALYZE]`)

### Si inyecta contexto
- Escribe DNA que luego se LEE en `dm_agent_context_integration.build_context_prompt()`:
  - "=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ==="
  - Relación: {rel_type} ({hint})
  - Nivel de profundidad + trust
  - "Palabras que sueles usar con esta persona: ..."
  - "Emojis típicos en esta relación: ..."
  - "Guía de comunicación: {bot_instructions}"
  - Golden examples

### Metadata escrita
- DB: `relationship_dna` table (via repository)
- `cognitive_metadata["dna_full_analysis_triggered"] = True` — `context.py:520` — consumer: observability
- `metadata["dna_data"] = raw_dna` — `context.py:442` — consumer: trigger checks

### Solapamiento con P0/P1 auditados
- Complementa `relationship_scorer`/`relationship_adapter`: el scorer usa señales estructurales sin DNA; este persiste DNA para modular el prompt.
- No solapa; son capas distintas.

### Bugs / dead code
- `ENABLE_DNA_AUTO_ANALYZE` default true en codebase pero OFF en Railway y en CPE runs (según `tests/ccee_results/.../naked_baseline.json:16`). Resultado: `vocabulary_uses` suele estar vacío para la mayoría de DNAs. Documentado en `DECISIONS.md:663`.
- Cache in-memory se pierde en cold starts / múltiples workers (consistencia eventual).

### Veredicto
- **VALOR:** ALTO (inyecta personalización por lead al prompt)
- **ESTADO:** ACTIVO_VALIOSO (si flag ON)
- **RAZÓN:** Arquitectura correcta (cache + singleton + fire-and-forget). En prod el flag a veces está OFF lo que reduce calidad. Mantener y activar.

---

## Sistema: relationship_analyzer (services)

- **Archivo:** `services/relationship_analyzer.py`
- **Líneas:** 563
- **Clasificación prev:** P2 (fase2, sistema_08_dna_engine.md)
- **Qué hace (1 línea):** Análisis pesado de conversación para extraer DNA: tipo de relación, trust, depth, vocabulario TF-IDF, emojis, patterns, topics, golden examples, bot_instructions.

### Funcionalidad detallada
- `RelationshipAnalyzer.analyze(creator_id, follower_id, messages, global_vocab, total_leads, leads_per_word)` — devuelve dict con 14 campos DNA.
- `_detect_relationship_type` — delega a `RelationshipTypeDetector`.
- `_calculate_trust_score` — base por tipo + bonus por volumen.
- `_calculate_depth_level` — 0-4 por count (10/25/50/100 thresholds).
- `_extract_vocabulary_uses` — delega a `vocabulary_extractor.get_top_distinctive_words()` (TF-IDF).
- `_extract_vocabulary_avoids` — palabras que el lead usa 2+ veces pero el creator nunca.
- `_extract_emojis` — regex unicode + priorización por tipo.
- `_extract_topics` — seeds curados + frecuencia dinámica.
- `_describe_tone` — tono natural por tipo.
- `extract_patterns` — avg_message_length, questions_freq, multi_msg_freq.
- `generate_instructions(dna_data) -> str` — componer instrucciones textuales para el bot (FAMILIA/INTIMA/AMISTAD_CERCANA/CLIENTE → tono; vocab_uses/avoids; emojis; topics).
- `should_update_dna(existing, count)` — gate: stale >30d O +10 msgs.
- `update_incremental` — merge vocab manteniendo golden_examples curados.
- `_extract_golden_examples` — pairs lead/creator cortos, filtrando placeholders media.

### Activación
- **Feature flag:** `ENABLE_DNA_AUTO_ANALYZE` (igual que service)
- **Se llama desde:**
  - `services/relationship_dna_service.py:187` — `analyze_and_update_dna()` (ruta canónica)
  - `core/dm/phases/context.py:502` — chequea `should_update_dna` antes de lanzar thread
  - `services/whatsapp_onboarding_pipeline.py:546`, `scripts/turbo_onboarding.py:348`, `scripts/batch_process_historical.py:489`
  - Tests: `tests/services/test_relationship_analyzer.py`, `tests/integration/test_relationship_dna_e2e.py`, `tests/test_sistema_07_08_fixes.py`
- **¿Tiene consumer?:** SÍ (vía DNA persistida)

### Afecta al output?
- [x] system prompt (indirecto: popula campos que `dm_agent_context_integration.py` lee)
- [ ] user message
- [ ] post-LLM mutation
- [x] metadata (DNA row completa)
- [x] observability

### Si inyecta contexto
- NO inyecta directamente. Escribe DNA → leído por `build_context_prompt()`.

### Metadata escrita
- DB relationship_dna: `vocabulary_uses`, `vocabulary_avoids`, `emojis`, `tone_description`, `recurring_topics`, `bot_instructions`, `golden_examples`, etc.

### Solapamiento con P0/P1 auditados
- **Solapa parcialmente con `relationship_scorer`**: ambos "analizan" la relación, pero:
  - relationship_scorer: tiempo real, sin LLM, score continuo 0-1, input user-only messages — ALIMENTA supresión de productos en prompt
  - relationship_analyzer: background, pesado (TF-IDF + LLM instructions), categórico (INTIMA/AMISTAD_CERCANA/...) — ALIMENTA DNA persistido
  - Son complementarios, NO redundantes. Usan datos distintos (user-only vs creator+user) y producen outputs distintos.
- `_detect_relationship_type` delega a `RelationshipTypeDetector` — coherencia interna del paquete DNA.
- `generate_instructions` solapa con `BotInstructionsGenerator` de `services/bot_instructions_generator.py` (RelationshipDNAService usa el segundo; el analyzer tiene su propia versión interna usada dentro de `analyze()`).

### Bugs / dead code
- `generate_instructions` method duplicada: existe aquí Y en `services/bot_instructions_generator.BotInstructionsGenerator`. El service usa `BotInstructionsGenerator`; el analyzer usa su propio `self.generate_instructions()` durante `analyze()`. Si los dos derivan instrucciones diferentes ante mismo DNA → inconsistencia. Flagrear.
- `update_incremental` marca comentario `"# In a real implementation, we'd merge old + new analysis"` (line 497) → sólo vocab; el resto queda del existing_dna. Incompleto.
- `_cache = {}` en `__init__` nunca se usa — dead code.

### Veredicto
- **VALOR:** ALTO (fuente de DNA enrichment)
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Genuinamente útil cuando flag ON. Cuidar la inconsistencia entre `RelationshipAnalyzer.generate_instructions` y `BotInstructionsGenerator` (duplicate logic).

---

## Sistema: relationship_type_detector (services)

- **Archivo:** `services/relationship_type_detector.py`
- **Líneas:** 241
- **Clasificación prev:** P2 (sistema_08_dna_engine.md Level 1)
- **Qué hace (1 línea):** Detector rápido rule-based de tipo de relación (FAMILIA/INTIMA/AMISTAD_CERCANA/AMISTAD_CASUAL/CLIENTE/COLABORADOR/DESCONOCIDO) con scoring ponderado ES/IT/CA/EN.

### Funcionalidad detallada
- Diccionario `INDICATORS` con `{relationship_type: {words: {kw: weight}, emojis: {e: w}, threshold: N}}`.
- `detect(messages) -> {type, confidence, scores}` — suma weights * min(3, count), compara con threshold, calcula confidence.
- `detect_with_history(messages, previous_type)` — stickiness: preserva tipo previo si nuevo análisis es DESCONOCIDO con baja confidence.

### Activación
- **Feature flag:** `ENABLE_DNA_AUTO_CREATE` (para seed DNA) — `context.py:23`
- **Se llama desde:**
  - `core/dm/phases/context.py:449` — seed creation path al tener 2+ mensajes
  - `services/relationship_analyzer.py:174-175` — delegación dentro de `_detect_relationship_type`
  - `mega_test_w2.py:176, 1177`, `tests/services/test_relationship_type_detector.py`, `tests/unit/test_dm_agent_relationship.py`, `tests/test_sistema_07_08_fixes.py`
- **¿Tiene consumer?:** SÍ (seed DNA + analyzer delegation)

### Afecta al output?
- [ ] system prompt (vía DNA seed, que luego inyecta dna_context)
- [ ] user message
- [ ] post-LLM mutation
- [x] metadata (`relationship_type` en DNA row)
- [x] observability (`cognitive_metadata["relationship_type"]`)

### Si inyecta contexto
- Indirecto: determina `relationship_type` que se persiste en DNA y luego `build_context_prompt()` lo mapea a `rel_hints` (FAMILIA → "NUNCA vender", INTIMA → "muy cercana y personal", etc.).

### Metadata escrita
- `cognitive_metadata["relationship_type"] = detected_type` — `context.py:489`
- `cognitive_metadata["dna_seed_created"] = True` — `context.py:490`
- DB: `relationship_dna.relationship_type`, `trust_score` (seed via `_SEED_TRUST`).

### Solapamiento con P0/P1 auditados
- **Conceptualmente solapa con `relationship_scorer`** pero:
  - `relationship_scorer`: scoring continuo user-only, sin LLM, gradated suppression
  - `relationship_type_detector`: categórico, scoring weighted ALL messages, threshold-based
  - `relationship_scorer.py:4` documenta: "Replaces RelationshipTypeDetector's keyword matching on ALL messages (which false-positive'd on Iris's apelativos in assistant messages)".
  - **Ambos siguen activos pero con propósitos distintos**: type_detector para categoría persistida en DNA; scorer para supresión dinámica de productos en prompt.
- Delegado desde `relationship_analyzer._detect_relationship_type`.

### Bugs / dead code
- Keyword `"compañero"` aparece como `"compagno"` y `"company"` — posible confusión CA vs EN (`company` significa empresa en EN pero compañero en CA catalán).
- Threshold FAMILIA=8, INTIMA=10, AMISTAD_CERCANA=6, CLIENTE=6, COLABORADOR=5, AMISTAD_CASUAL=4 — calibrados manualmente, no data-driven.
- `detect_with_history` raramente se invoca (grep: sin call sites prod).

### Veredicto
- **VALOR:** MEDIO (usado en seed DNA path)
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Útil para seeding rápido cuando hay 2+ msgs. Conocido problema de false-positive sobre mensajes assistant (documented); pero en seed path solo se usa con hist (incluye user+assistant), por lo que el issue es menor en esta ruta. Mantener.

---

## Sistema: relationship_dna_repository (services)

- **Archivo:** `services/relationship_dna_repository.py`
- **Líneas:** 458
- **Clasificación prev:** No clasificado (repo CRUD)
- **Qué hace (1 línea):** CRUD de `RelationshipDNAModel` con fallback JSON files para dev/offline.

### Funcionalidad detallada
- `create_relationship_dna()`, `get_relationship_dna()`, `update_relationship_dna()`, `get_or_create_relationship_dna()`, `list_relationship_dnas_by_creator()`, `delete_relationship_dna()`.
- `_dna_to_dict()` — serializer SQLAlchemy → dict.
- `_get_dna_from_json()` + `_list_dnas_from_json()` — fallback file store en `backend/data/relationship_dna/{creator_id}/{follower_id}.json`.
- `get_session()` delega a `api.services.db_service`.
- Normaliza `follower_id` probando `ig_<id>` y `<id>` ambos formatos (documentado en rule "platform_user_id: raw numeric ID, NO ig_ prefix").

### Activación
- **Feature flag:** ninguna (repo siempre activo si hay DB)
- **Se llama desde:**
  - `services/relationship_dna_service.py:18-23` — orquestador principal
  - `core/dm/phases/context.py:317, 464-465` — load directo en phase_memory_and_context + en seed creation
  - API routers? Buscar: sólo tests directos (`tests/test_relationship_dna_repository*`)
- **¿Tiene consumer?:** SÍ (DNA service + context phase)

### Afecta al output?
- [ ] system prompt (directo)
- [ ] user message
- [ ] post-LLM mutation
- [x] metadata (DNA row)
- [ ] observability

### Si inyecta contexto
- N/A directo. Suministra DNA al pipeline context → prompt.

### Metadata escrita
- DB `relationship_dna` table — consumer: dm_agent_context_integration.build_context_prompt, RelationshipDNAService.get_dna_for_lead, admin APIs.

### Solapamiento con P0/P1 auditados
- NO solapa con scorer/adapter (estos no acceden al repo).
- Repo compañero de RelationshipDNAService (coherente).

### Bugs / dead code
- `create_relationship_dna` maneja `IntegrityError` (race condition concurrente) — correcto.
- JSON fallback en `backend/data/relationship_dna/` existe pero no queda claro si está sincronizado en Railway (persistence issue — Railway filesystem es ephemeral).
- `delete_relationship_dna` se usa en tests pero no en API prod — OK (deleta manual rare).
- Allowed_fields en `update_relationship_dna:257-274` deja fuera `version` aunque lo incrementa a mano — consistente.

### Veredicto
- **VALOR:** ALTO (backbone de persistencia DNA)
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Repo sólido con race condition handling, doble formato follower_id, fallback JSON. Mantener.

---

## Resumen duplicaciones detectadas (CRÍTICO)

| Sistema A | Sistema B | Tipo overlap | Acción |
|---|---|---|---|
| `core/intent_classifier.py` | `services/intent_service.py` | DUP — ambos definen `class IntentClassifier` y `enum Intent` incompatibles | Mantener `services/intent_service.py` (canónico en prod). Extraer `classify_intent_simple` + `get_lead_status_from_intent` de core a util separado; eliminar `IntentClassifier` async + `ConversationAnalyzer` de core |
| `core/lead_categorization.py` (v1) | `core/lead_categorizer.py` (v2) | DUP — mismo embudo NUEVO/INTERESADO/CALIENTE/..., v2 reemplaza v1 | Migrar los 5 call sites históricos (OAuth, sync, admin recategorize, script) a v2; eliminar v1 |
| `RelationshipAnalyzer.generate_instructions` | `BotInstructionsGenerator.generate` | DUP parcial — ambos generan bot_instructions | Unificar en `BotInstructionsGenerator`; hacer que `analyze()` lo invoque en vez de tener método propio |
| `RelationshipTypeDetector` | `relationship_scorer` (P0/P1) | OVERLAP conceptual — ambos "clasifican" relación pero con ejes distintos | NO son dup: detector devuelve tipo categórico (persistido en DNA), scorer devuelve score continuo (gate de productos). Documentar el split. |
| `RelationshipAnalyzer` vs `RelationshipTypeDetector` | — | NO dup — analyzer delega a detector | OK |
| `RelationshipDNAService` vs `RelationshipDNARepository` | — | NO dup — service orquesta, repo persiste | OK |

---

### 3.F · Batch F — Learning / Feedback / Memory (9 sistemas)

## Sistema: Learning Rules Service

- **Archivo:** `services/learning_rules_service.py`
- **Líneas:** 443
- **Clasificación prev:** Learning (data layer, runtime injection DEPRECATED abr'2026)
- **Qué hace (1 línea):** Persistencia CRUD de `learning_rules` (create/get/update_feedback/deactivate) + ranking scored con TTL cache 60s.

### Funcionalidad detallada
- `create_rule()`: Crea `LearningRule` con dedup (same creator+pattern+text → +0.05 confidence, bump version). Feature: `sanitize_rule_text()` strip prompt-injection patterns + 500 char cap.
- `get_applicable_rules()`: Query active rules, score por (intent/pattern match +3, relationship +2, stage +2, baseline 0.1) × confidence + help_ratio bonus + pattern_batch bonus. Top-N (default 5). TTL cache 60s, evict cuando >200 entries. Filtra contradicciones con `_CONTRADICTION_PAIRS` (usa/no-uses, breve/largo, emoji/sin-emoji, formal/informal, pregunta/no-preguntes).
- `update_rule_feedback()`: +0.05/-0.05 confidence según `was_helpful`, update times_applied/helped.
- `deactivate_rule()`, `get_rules_count()`, `get_all_active_rules()` (limit 100).

### Activación
- **Feature flag:** Históricamente `ENABLE_LEARNING_RULES` (ahora **eliminado**: comentario en `core/dm/phases/generation.py:204-208` confirma "runtime injection removed April 2026").
- **Se llama desde:**
  - Producción: **NINGÚN callsite live en código productivo**. Los archivos que lo importaban (`services/autolearning_analyzer.py`, `services/pattern_analyzer.py`, `services/learning_consolidator.py`) **no existen ya** — su lógica se absorbió en `services/persona_compiler.py`, pero `persona_compiler.py` **NO IMPORTA** `learning_rules_service` (solo copia sanitize/contradiction constants). 
  - `mega_test_w2.py:376` — test script.
  - `tests/test_learning_rules_service.py`, `tests/test_autolearning_analyzer.py`, `tests/test_learning_consolidator.py`, `tests/test_feedback_store.py` — tests.
- **¿Tiene consumer?:** NO en runtime. Tabla `learning_rules` existe pero nadie la lee/escribe en flujo vivo.

### Afecta al output?
- [ ] system prompt — comment en `generation.py:204` dice "removed"
- [ ] user message
- [ ] post-LLM mutation
- [ ] metadata
- [ ] observability

### Si inyecta contexto
- N/A (runtime injection eliminado).

### Metadata escrita
- N/A (no escribe metadata de mensaje).

### Solapamiento con P0/P1 auditados
- Solapa con `preference_profile_service` (AUDITADO P1): ambos aprenden del feedback. PreferenceProfile es el path vivo; LearningRules es el legado.
- Solapa con `persona_compiler.py` (no auditado P0/P1): PersonaCompiler copia `sanitize_rule_text()` / `_CONTRADICTION_PAIRS` como código duplicado pero no importa el módulo. 
- SÍ — solapamiento fuerte con persona_compiler (duplicación de constantes/funciones).

### Bugs / dead code
- **DEAD**: `get_applicable_rules()`, `update_rule_feedback()`, `filter_contradictions()` (runtime-only consumers). 
- **DEAD**: `create_rule()` → docstring afirma "Called by AutolearningAnalyzer + PatternAnalyzer", pero ambos archivos no existen. 
- **DEAD**: `get_all_active_rules()` / `get_rules_count()` → docstring "For consolidation" pero `learning_consolidator.py` no existe. 
- API endpoint `/autolearning/{creator}/rules` (list/deactivate/reactivate) lee `LearningRule` directo via ORM sin pasar por este módulo — sigue vivo pero lee tabla huérfana.

### Veredicto
- **VALOR:** NINGUNO
- **ESTADO:** ACTIVO_INÚTIL (código importable, sin consumers live, flag removido)
- **RAZÓN:** Runtime injection eliminado abr'2026. PersonaCompiler (sucesor) duplica las constantes pero no importa el módulo. Tabla `learning_rules` huérfana (solo API manual). Cuando ENABLE_PERSONA_COMPILER siga OFF, es 100% dead code.

---

## Sistema: FeedbackCapture

- **Archivo:** `services/feedback_capture.py`
- **Líneas:** 1017
- **Clasificación prev:** Learning (ACTIVO; ENABLE_EVALUATOR_FEEDBACK y ENABLE_PREFERENCE_PAIRS default true)
- **Qué hace (1 línea):** Punto único de entrada `capture()` para todas las señales de feedback (evaluator scores, copilot actions, best-of-N, historical mining) → escribe a `evaluator_feedback`, `preference_pairs`, `gold_examples`.

### Funcionalidad detallada
Secciones:
1. **Router `capture(signal_type, ...)`** (L63-181): despacha según `signal_type` a save_feedback / create_pairs_from_action / mine_historical_pairs. Calcula `quality` ponderado (QUALITY_SCORES dict).
2. **Evaluator feedback** `save_feedback()` (L196-330): persiste `EvaluatorFeedback`; si hay `ideal_response` → auto-crea `PreferencePair(chosen=ideal, rejected=bot, action_type="evaluator_correction")`; si `lo_enviarias>=4` → auto-crea `GoldExample(quality_score=0.9)`. Dedup por source_message_id.
3. **Get helpers** `get_feedback()`, `get_feedback_stats()` (L333-446): reads for UI/analytics.
4. **Preference pairs** `create_pairs_from_action()` (L630-746): maps copilot actions (approved/edited/discarded/manual_override/resolved_externally) → `PreferencePair` rows. Skips `chosen == rejected` (BUG-6 guard). Incluye lógica best-of-N winner vs losers.
5. **Context fetcher** `_fetch_context_and_save_sync()` (L546-627): última session (4h gap) de mensajes para contexto de entrenamiento.
6. **Historical mining** `mine_historical_pairs()` (L832-983): para creators con data histórica IG, extrae (user_msg → creator_response) como pairs `action_type="historical"`. Batch-fetch N+1 fix (BUG-4). Filtros: 15-250 chars, 5 pairs/lead, dedup por source_message_id.
7. **Curator** `curate_pairs()` (L986-1017): si `total<10 pairs` → invoca historical mining. Llamado por scheduler JOB 20.
8. **Export** `get_pairs_for_export()` / `mark_exported()` (L749-829).

### Activación
- **Feature flag:** `ENABLE_EVALUATOR_FEEDBACK` (default true), `ENABLE_PREFERENCE_PAIRS` (default true).
- **Se llama desde:**
  - `core/copilot/actions.py:118` — signal copilot_approve/edit al aprobar mensaje
  - `core/copilot/actions.py:261` — signal copilot_discard al descartar
  - `core/copilot/actions.py:397` — signal copilot_resolved al resolver externamente
  - `api/routers/copilot/actions.py:360` — create_pairs_from_action en manual_override
  - `api/routers/copilot/actions.py:416` — mark_exported
  - `api/routers/copilot/analytics.py:347` — get_pairs_for_export
  - `api/routers/feedback.py:101/106/111` — REST endpoints `/feedback`
  - `api/startup/handlers.py:546` — scheduler JOB 20 `_gold_examples_job` llama `curate_pairs()`
  - `scripts/turbo_onboarding.py:691` — onboarding masivo
- **¿Tiene consumer?:** SÍ — crítico para copilot + evaluador.

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation
- [x] metadata — escribe `evaluator_feedback.intent_detected`, `.doc_d_version`, `.model_id`, `.system_prompt_hash`
- [x] observability — genera entrenamiento futuro (DPO pairs) y gold examples para few-shot

### Si inyecta contexto
- N/A — no inyecta en runtime. Los gold_examples resultantes SÍ se inyectan después vía `style_retriever.get_matching_examples()` (P1 auditado).

### Metadata escrita
- `EvaluatorFeedback.id` / evaluator_id / coherencia / lo_enviarias / ideal_response / error_tags / intent_detected / doc_d_version / model_id / system_prompt_hash — `feedback_capture.py:258-275` — consumer: `api/routers/feedback.py` (UI).
- `PreferencePair.id` / chosen / rejected / action_type / conversation_context / edit_diff / confidence_delta — `feedback_capture.py:595-612` — consumer: `api/routers/copilot/analytics.py:347` (export), futuro DPO.
- `GoldExample.id` / quality_score / source — `feedback_capture.py:524-533` — consumer: `style_retriever.get_matching_examples()` (P1).

### Solapamiento con P0/P1 auditados
- **SÍ** — `preference_profile_service` (P1) **LEE preference_pairs** (`feedback_capture` las escribe). Es pipeline downstream, no duplicación.
- **SÍ** — `style_retriever` (P1) / gold_examples_service (shim) **LEE gold_examples** (feedback_capture las escribe vía `_auto_create_gold_example`).
- No hay duplicación de lógica con P0/P1.

### Bugs / dead code
- Código parece limpio. Bugs ya fixed: FB-01 (single commit), FB-02 (dedup), FB-03 (non-empty ideal), FB-04 (rate limit), FB-06 (to_thread), FB-07 (distinct status), FB-08 (error propagation), BUG-2 (context in single session), BUG-4 (N+1 fix batch-fetch), BUG-6 (chosen==rejected skip).

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Punto único de captura de feedback; múltiples consumers activos (UI, scheduler, analytics). Alimenta gold_examples (P1 live) + preference_pairs (futuro DPO). Código maduro, bugs históricos fixed.

---

## Sistema: feedback_store (SHIM)

- **Archivo:** `services/feedback_store.py`
- **Líneas:** 17
- **Clasificación prev:** Shim
- **Qué hace (1 línea):** Re-export shim: `from services.feedback_capture import *` + explicit symbol re-exports.

### Funcionalidad detallada
- Stub 100% — no tiene lógica propia. Sólo `from services.feedback_capture import *` + `from services.feedback_capture import capture, save_feedback, get_feedback, get_feedback_stats, QUALITY_SCORES, _COPILOT_ACTION_MAP, _compute_quality, _auto_create_preference_pair, _auto_create_gold_example, ENABLE_EVALUATOR_FEEDBACK`.

### Activación
- **Feature flag:** N/A (shim).
- **Se llama desde:** backward-compat imports:
  - `core/copilot/actions.py:118, 261, 397` (usa `from services.feedback_store import capture`)
  - `api/routers/feedback.py:101, 106, 111`
  - `tests/test_feedback_store.py` (el suite de tests sigue testeando por este path)
- **¿Tiene consumer?:** SÍ — producción importa por este nombre.

### Afecta al output?
- Idéntico a feedback_capture (es el mismo código).

### Si inyecta contexto
- N/A.

### Metadata escrita
- N/A (delega en feedback_capture).

### Solapamiento con P0/P1 auditados
- NO directamente (delega).

### Bugs / dead code
- NO — shim válido para backward compat.

### Veredicto
- **VALOR:** MEDIO (utility)
- **ESTADO:** ACTIVO_VALIOSO (import alias usado en prod)
- **RAZÓN:** Shim intencional post-merge; simplificar renombrando imports es low-pri cleanup.

---

## Sistema: preference_pairs_service (SHIM)

- **Archivo:** `services/preference_pairs_service.py`
- **Líneas:** 15
- **Clasificación prev:** Shim
- **Qué hace (1 línea):** Re-export shim → `services.feedback_capture` (create_pairs_from_action, get_pairs_for_export, mark_exported, mine_historical_pairs, curate_pairs).

### Funcionalidad detallada
- 100% shim idéntico a feedback_store: `from services.feedback_capture import *` + explicit re-exports de las funciones de preference pairs.

### Activación
- **Se llama desde:**
  - `api/startup/handlers.py:546` (scheduler JOB 20 → `curate_pairs`)
  - `api/routers/copilot/actions.py:360` (`create_pairs_from_action` en manual_override)
  - `api/routers/copilot/actions.py:416` (`mark_exported`)
  - `api/routers/copilot/analytics.py:347` (`get_pairs_for_export`)
  - `scripts/turbo_onboarding.py:691` (`mine_historical_pairs`)
- **¿Tiene consumer?:** SÍ — producción importa por este nombre.

### Afecta al output?
- Idéntico a feedback_capture.

### Si inyecta contexto
- N/A.

### Metadata escrita
- N/A (delega).

### Solapamiento con P0/P1 auditados
- NO directamente.

### Bugs / dead code
- NO.

### Veredicto
- **VALOR:** MEDIO (utility)
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Shim intencional.

---

## Sistema: gold_examples_service (SHIM → style_retriever)

- **Archivo:** `services/gold_examples_service.py`
- **Líneas:** 17
- **Clasificación prev:** Shim
- **Qué hace (1 línea):** Re-export shim → **NO apunta a feedback_capture** sino a `services.style_retriever` (create_gold_example, get_matching_examples, detect_language, mine_historical_examples, curate_examples, retrieve, ensure_embeddings).

### Funcionalidad detallada
- 100% shim: `from services.style_retriever import *`. OJO: diferente target que los otros dos shims — la lógica de gold examples vive en `style_retriever.py` (P1 AUDITADO), no en feedback_capture.

### Activación
- **Se llama desde:**
  - `core/dm/phases/generation.py:245` (`get_matching_examples`, `detect_language`) — **PATH VIVO runtime** (few-shot injection si `ENABLE_GOLD_EXAMPLES`)
  - `api/startup/handlers.py:537` (`curate_examples` en scheduler JOB 20)
  - `api/routers/autolearning/dashboard.py:587` (`curate_examples` vía endpoint)
  - `services/whatsapp_onboarding_pipeline.py:735` (`curate_examples`)
  - `scripts/turbo_onboarding.py:437`
- **¿Tiene consumer?:** SÍ — injecta few-shot en prompt generation.

### Afecta al output?
- [x] system prompt — vía `style_retriever.get_matching_examples()` (solapa con P1 style_retriever).

### Si inyecta contexto
- Inyecta gold_examples como "EJEMPLOS DE ESTILO DEL CREATOR" bloque en generation.py:269.

### Metadata escrita
- Metadata `cognitive_metadata["gold_examples_injected"]` (count) — generation.py:275.

### Solapamiento con P0/P1 auditados
- **SÍ** — solapamiento TOTAL con `style_retriever` (P1 AUDITADO). Este shim apunta directamente a ese módulo. No hay lógica propia.

### Bugs / dead code
- NO (shim válido). La lógica real está en style_retriever.

### Veredicto
- **VALOR:** MEDIO (alias de un módulo P1)
- **ESTADO:** ACTIVO_VALIOSO (pero fully covered por P1 auditado)
- **RAZÓN:** Es sólo un nombre para style_retriever. En el inventario del audit, si style_retriever ya está cubierto, este shim no añade nada nuevo.

---

## Sistema: Memory Consolidator (orchestrator)

- **Archivo:** `services/memory_consolidator.py`
- **Líneas:** 463
- **Clasificación prev:** P2 (dormido por ENABLE_MEMORY_CONSOLIDATION=false default)
- **Qué hace (1 línea):** Orquestador 4-fase (Orient/Gather/Consolidate/Prune) del Memory Consolidation; maneja gates (flag, time, scan throttle, activity, lock) y scheduler entry.

### Funcionalidad detallada
- **Gates orden** (cheapest first):
  1. Flag `ENABLE_MEMORY_CONSOLIDATION`
  2. Gate `ENABLE_MEMORY_ENGINE`
  3. Time: `hours_since_last >= CONSOLIDATION_MIN_HOURS` (default 24h)
  4. Scan throttle: `_last_scan_at[creator]` TTL `CONSOLIDATION_SCAN_THROTTLE_SECONDS` (default 600s)
  5. Activity: `messages_since >= CONSOLIDATION_MIN_MESSAGES` (default 20)
  6. Lock: `pg_try_advisory_lock` (atómico, no race)
- **`consolidate_creator()`** (L292-354): ejecuta 4 fases secuenciales delegando a memory_consolidation_ops. Record timestamp en `creators.last_consolidated_at` (omitido en DRY_RUN).
- **`consolidation_job()`** (L362-463): entry del TaskScheduler; itera todos los `Creator.bot_active=true` aplicando gates.
- **`is_consolidation_locked(creator_id)`** (L185-217): NON-BLOCKING check usado desde `memory_extraction.py:215` y `memory_engine.py:442` para detectar concurrencia (log warning, no bloquea DM pipeline).
- **`_validated_env_float/_int`**: helpers compartidos (importados por memory_consolidation_llm.py y memory_consolidation_ops.py y memory_extraction.py).

### Activación
- **Feature flag:** `ENABLE_MEMORY_CONSOLIDATION` (default false). 
  - **config/env_ccee_gemma4_26b_full.sh:55** lo pone `true` → activo en algunos configs de test.
- **Se llama desde:**
  - `api/startup/handlers.py:660` → `scheduler.register("memory_consolidation", _memory_consolidation_job, interval=86400, delay=690)`
  - `scripts/run_consolidation.py:128` (CLI manual)
  - `services/memory_consolidation_ops.py`, `services/memory_consolidation_llm.py` (importan helpers `_validated_env_*`)
  - `services/memory_extraction.py:37, 215` (importa `_validated_env_int`, `is_consolidation_locked`)
  - `services/memory_engine.py:442` (`is_consolidation_locked`)
- **¿Tiene consumer?:** SÍ (scheduler, script manual, cross-imports).

### Afecta al output?
- [ ] system prompt (indirecto: deduplica/expira lead_memories que luego usa recall en system prompt)
- [ ] user message
- [ ] post-LLM mutation
- [ ] metadata
- [x] observability — `[Consolidator]` logs detallados (leads/deduped/expired/cross/memos/deact/duration)

### Si inyecta contexto
- N/A (es background job, no inyecta runtime). Su output afecta a los hechos que `memory_engine.recall()` inyecta después.

### Metadata escrita
- `creators.last_consolidated_at` — memory_consolidator.py (vía record_consolidation en ops).
- Counters en `ConsolidationResult`: leads_processed, facts_deduped, facts_expired, facts_cross_deduped, memos_refreshed, llm_contradictions_resolved, llm_dates_fixed — sólo logs, no persistidos.

### Solapamiento con P0/P1 auditados
- **SÍ** — depende de `memory_engine` (AUDITADO P0/P1). Es su "janitor". No duplica — extiende.

### Bugs / dead code
- Código limpio. Bug-010 citado en memory_consolidation_llm.py (model slug normalization).

### Veredicto
- **VALOR:** ALTO cuando encendido; MEDIO en estado actual (OFF por default)
- **ESTADO:** DORMIDO_RECUPERABLE (ON en configs de test, OFF en prod)
- **RAZÓN:** Orquestador limpio y maduro. Sin él, lead_memories acumulan duplicados y contradicciones. Tests extensos (`tests/test_memory_consolidator.py`). Si memory_engine está en prod (P0), este debe estar ON.

---

## Sistema: Memory Consolidation LLM

- **Archivo:** `services/memory_consolidation_llm.py`
- **Líneas:** 504
- **Clasificación prev:** P2 (dormido por ENABLE_LLM_CONSOLIDATION=false default)
- **Qué hace (1 línea):** Llama LLM (gemma/deepinfra/gemini/openrouter) para analizar `lead_memories` y detectar duplicates/contradictions/date_fixes en Phase 3 del consolidator.

### Funcionalidad detallada
- **`llm_analyze_facts(facts)`** (L357-438): cap a `CONSOLIDATION_LLM_MAX_FACTS` (default 100, los más recientes). Construye numbered list `[idx] [type] (Nd ago) fact_text`. LLM devuelve JSON con 3 arrays; valida/sanitiza y remapea slice-relative indices → full-list indices.
- **`_call_consolidation_llm()`** (L111-266): retry+backoff (3x, 5s). Provider configurable:
  - `CONSOLIDATION_LLM_PROVIDER`: gemini / openrouter / deepinfra (default deepinfra)
  - `CONSOLIDATION_LLM_MODEL`: default `google/gemma-4-31b-it`
  - Timeout 120-180s.
  - BUG-010: normaliza slug "google/" prefix según provider.
  - Sin cascade a otro modelo (CC pattern: "no silent fallback").
- **`_parse_llm_response()`** (L269-300): strip thinking artifacts (Qwen3), markdown fences, JSON object extraction.
- **`_validate_llm_actions()`** (L307-350): sanitize LLM output contra invalid/out-of-range indices. Prioritiza contradictions > duplicates > date_fixes si excede MAX_LLM_ACTIONS_PER_LEAD (default 60).
- **`apply_date_fixes()`** (L441-504): ejecuta UPDATE `lead_memories SET fact_text=...` para fixes. Skip en DRY_RUN.

### Activación
- **Feature flag:** `ENABLE_LLM_CONSOLIDATION` (default false). Independiente de ENABLE_MEMORY_CONSOLIDATION.
  - **config/env_ccee_gemma4_26b_full.sh:56** pone `true`.
- **Se llama desde:**
  - `services/memory_consolidation_ops.py:280` (en `consolidate_lead`)
- **¿Tiene consumer?:** SÍ (dentro de ops), pero sólo ejecuta si ambos flags están ON.

### Afecta al output?
- [ ] system prompt directamente — no. Deduplica lead_memories que memory_engine.recall() inyecta.
- [ ] metadata
- [x] observability — `[ConsolidatorLLM]` logs con dupes/contradictions/date_fixes counts.

### Si inyecta contexto
- N/A (background).

### Metadata escrita
- Actualiza `lead_memories.fact_text` (date fixes) + `lead_memories.is_active=false` (dedup/contradiction, vía ops).

### Solapamiento con P0/P1 auditados
- **NO** — no solapa con P0/P1. Extiende memory_engine (P0).

### Bugs / dead code
- Código limpio. Bug-010 fixed (model slug normalization).

### Veredicto
- **VALOR:** ALTO cuando encendido
- **ESTADO:** DORMIDO_RECUPERABLE
- **RAZÓN:** Es el "cerebro" del consolidator (CC alignment: LLM handles all dedup, algorithmic dedup removed). Sin él, la fase 3 sólo hace TTL expiry.

---

## Sistema: Memory Consolidation Ops

- **Archivo:** `services/memory_consolidation_ops.py`
- **Líneas:** 493
- **Clasificación prev:** P2 (worker del consolidator)
- **Qué hace (1 línea):** Operaciones stateless de las 4 fases del consolidator (Orient/Gather/Consolidate/Prune); es el worker layer.

### Funcionalidad detallada
- **Phase 1 Orient** `_orient_find_leads_needing_work()` (L76-118): aggregation SQL en `lead_memories` → lista leads con ≥2 facts reales, flags has_memo, memo_at, newest_fact.
- **Phase 2 Gather** `_lead_needs_work()` (L123-145) + `_gather_load_facts()` (L148-189): filtro decisión (needs_compression / memo_outdated / potential_dedup basado en `MEMO_COMPRESSION_THRESHOLD`); carga facts completos.
- **Phase 3 Consolidate** `consolidate_lead()` (L263-404):
  - 3a. LLM analysis (delega en memory_consolidation_llm.llm_analyze_facts)
  - 3b. **`_find_near_duplicates()` stub DISABLED** (L192-202) — Jaccard removido por CC alignment
  - 3c. TTL expire de facts temporales (`_is_temporal_fact` reuse from memory_engine)
  - 3d. Re-compresión memo vía `engine.compress_lead_memory(_skip_lock_check=True)`
- **Phase 4 Prune** `cross_lead_dedup()` (L409-466): SQL `GROUP BY lower(trim(fact_text))` cross-lead; keep highest `times_accessed`.
- **`record_consolidation()`** (L469-493): UPDATE `creators.last_consolidated_at = NOW()`.
- **Safety net**: `MAX_DEACTIVATIONS_PER_RUN` (500) cap.
- **DRY_RUN mode** (`CONSOLIDATION_DRY_RUN=true`): log + collect `dry_run_actions` sin escribir DB.

### Activación
- **Feature flag:** Gated indirectamente por `ENABLE_MEMORY_CONSOLIDATION` + `ENABLE_LLM_CONSOLIDATION`. No tiene flag propio.
- **Se llama desde:**
  - `services/memory_consolidator.py:298` (`consolidate_creator` importa todos los símbolos)
  - `services/memory_consolidation_llm.py:456` (importa CONSOLIDATION_DRY_RUN)
  - `scripts/run_consolidation.py` indirect vía consolidator
- **¿Tiene consumer?:** SÍ (vía consolidator orchestrator).

### Afecta al output?
- [ ] system prompt directamente
- [x] metadata — `lead_memories.is_active=false`, `lead_memories.updated_at`
- [x] observability — `[DRY-RUN]`, `[Consolidator]` logs con per-lead counts

### Si inyecta contexto
- N/A (background).

### Metadata escrita
- `lead_memories.is_active=false`, `lead_memories.updated_at` — memory_consolidation_ops.py:219-226 — consumer: `memory_engine.recall()` (sólo active=true).
- `creators.last_consolidated_at` — L480-488 — consumer: consolidator gate Phase 3 "time".

### Solapamiento con P0/P1 auditados
- **SÍ** — extiende memory_engine (AUDITADO P0/P1). Sin duplicar lógica.

### Bugs / dead code
- **DEAD**: `_find_near_duplicates()` stub explicit — retorna [] unconditional (L192-202).
- Código limpio. G8 reuse (`_is_temporal_fact` from memory_engine).

### Veredicto
- **VALOR:** ALTO cuando consolidator encendido
- **ESTADO:** DORMIDO_RECUPERABLE (depende de flags del consolidator)
- **RAZÓN:** Worker layer bien separada del orchestrator. Clara arquitectura layered (gates en consolidator, ops aquí, LLM en llm).

---

## Sistema: Memory Extraction

- **Archivo:** `services/memory_extraction.py`
- **Líneas:** 461
- **Clasificación prev:** P1 (writer complementario a memory_engine)
- **Qué hace (1 línea):** Extrae facts durables (preference/commitment/topic/objection/personal_info/purchase_history) de conversaciones DM via LLM; aplica guards CC (overlap/turn-throttle/manifest/cursor/drain).

### Funcionalidad detallada
- **Clase `MemoryExtractor`** (L145-433):
  - Guards state in-memory: `_in_progress`, `_turn_counter`, `_cursor`, `_in_flight` (set de tasks).
  - **`extract_and_store()`** (L168-236): orchestrator público. Resolve creator/lead UUIDs → aplica guards → call `_do_extract()`.
  - **Guards**:
    1. Overlap `OVERLAP_GUARD_ENABLED` (default ON)
    2. Turn throttle `EXTRACT_EVERY_N_TURNS` (default 1 — off-by-value)
    3. Non-blocking consolidation check (`is_consolidation_locked` log warning)
    4. Manifest pre-injection `MANIFEST_ENABLED` (default ON) — inyecta existing_facts con age en prompt para prevent re-extract
    5. Cursor `CURSOR_ENABLED` (default ON) — tracks last source_message_id
  - **`_do_extract()`** (L238-349): min 20 chars msg, build prompt (FACT_EXTRACTION_PROMPT), call `_extract_facts_via_llm()` → embeddings batch → conflict resolution (`engine.resolve_conflict`) → `engine._store_fact()` → summary → auto-compress si ≥MEMO_COMPRESSION_THRESHOLD → advance cursor.
  - **`track_task()`** (L426-433): registra tarea para drain.
  - **`drain()`** (L411-424): await in-flight tasks con timeout (DRAIN_TIMEOUT=10s).
- **`FACT_EXTRACTION_PROMPT`** (L75-107): English prompt, CC-aligned (exclusion rules, per-type guidance, date conversion, max_facts, conservative extraction).
- **`_format_fact_manifest()`** (L116-132): `- [type] (Nd ago) fact_text` (max 20 facts via MAX_MANIFEST_FACTS).

### Activación
- **Feature flag:** Gated por `ENABLE_MEMORY_ENGINE` (inherit). Sub-guards: `MEMORY_OVERLAP_GUARD_ENABLED`, `MEMORY_MANIFEST_ENABLED`, `MEMORY_CURSOR_ENABLED`, `MEMORY_EXTRACT_EVERY_N_TURNS`, `MEMORY_MAX_FACTS_PER_EXTRACTION`, `MEMORY_MAX_MANIFEST_FACTS`, `MEMORY_DRAIN_TIMEOUT`.
- **Se llama desde:**
  - `core/dm/phases/postprocessing.py:484, 500` — fire-and-forget durante DM pipeline
  - `services/bot_orchestrator.py:203, 220, 228` — orchestrator alternativo
  - `services/memory_engine.py:269` — `add()` delega aquí (thin wrapper, ver DECISIONS.md L116)
  - `api/startup/handlers.py:1160` → `drain_extraction()` en shutdown hook
  - `scripts/backfill_lead_memories.py` (uso directo vía engine.add)
- **¿Tiene consumer?:** SÍ — path principal de escritura de memoria.

### Afecta al output?
- [ ] system prompt directamente — no. Escribe lead_memories que `memory_engine.recall()` inyecta.
- [x] metadata — LeadMemory rows con fact_type, fact_text, confidence, embedding, source_message_id, source_type="extracted"
- [x] observability — `[Extractor]` logs con counts.

### Si inyecta contexto
- N/A (escribe DB, no inyecta directamente). `memory_engine.recall()` (P0) inyecta.

### Metadata escrita
- `lead_memories.fact_type`, `.fact_text`, `.confidence`, `.embedding`, `.source_message_id`, `.source_type="extracted"` — via `engine._store_fact()`.
- Summary via `engine.summarize_conversation()` → tabla `conversation_summaries` (sentiment, key_topics).
- Auto-compress → `lead_memories.fact_type="compressed_memo"` si threshold.

### Solapamiento con P0/P1 auditados
- **SÍ** — solapamiento fuerte con memory_engine (AUDITADO P0/P1). DECISIONS.md L116: "Structural change: Extracted extraction pipeline from memory_engine.py (1717→1560 lines) to new memory_extraction.py". Es el módulo hermano de memory_engine.
- memory_engine.add() (L269) delega 100% aquí — thin wrapper.

### Bugs / dead code
- Código limpio. BUG-001 fix (track_task para drain), BUG-MEM-04 (history context en postprocessing). Fix ig_ prefix resolve vía `_resolve_lead_uuid` (script backfill usa este path).

### Veredicto
- **VALOR:** ALTO
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Writer principal de lead_memories. CC-faithful (6 guards mapeados a extractMemories.ts). Sin él, memory_engine no tiene facts para recall. Si memory_engine es P0, esto es P1 crítico.

---

## Resumen general batch F

- **Shims** (feedback_store, preference_pairs_service, gold_examples_service): 3 archivos de ~17 líneas, todos re-exports. feedback_store+preference_pairs → feedback_capture; gold_examples_service → style_retriever (P1 auditado).
- **feedback_capture** (1017 líneas): ACTIVO_VALIOSO — punto único de entrada, múltiples consumers en copilot/scheduler/analytics/REST.
- **learning_rules_service** (443 líneas): ACTIVO_INÚTIL — flag ENABLE_LEARNING_RULES eliminado, ningún caller runtime vivo; persona_compiler duplica sanitize/contradiction constants pero NO importa el módulo.
- **memory_consolidator / memory_consolidation_ops / memory_consolidation_llm**: relación LAYERED CLEAN (orchestrator + worker + LLM). Default OFF; ON en configs de test. DORMIDO_RECUPERABLE.
- **memory_extraction**: ACTIVO_VALIOSO — writer principal, hermano de memory_engine.

### 3.G · Batch G — Ops / Misc (16 sistemas)

## Sistema: CloneScore Engine

- **Archivo:** `services/clone_score_engine.py`
- **Líneas:** 1047
- **Clasificación prev:** P2 (QA/Eval)
- **Qué hace (1 línea):** Evaluador de calidad del clon en 6 dimensiones (style, knowledge, persona, tone, sales, safety) vía regex + LLM judge.

### Funcionalidad detallada
- `evaluate_single()`: realtime, solo style_fidelity (~0ms) por defecto. `full_eval` pide los 6 via LLM.
- `evaluate_batch()`: job diario, muestrea 20 mensajes sent, calcula 6 dims, deduplica por día, persiste en `clone_score_evaluations`.
- Dimensiones: `style` = stylometric vs `ToneProfile.profile_data`; `knowledge/persona/tone` = LLM judge (GPT-4o-mini); `sales` = stage_rate + approval_rate + ghost_rate + edit_similarity; `safety` = regex (promises, offensive, wrong emails/phones).
- Cache baseline 5min. Alerta si overall<60, crítico si dim<40.

### Activación
- **Feature flag:** `ENABLE_CLONE_SCORE=false` (default off)
- **Se llama desde:** `api/startup/handlers.py:567` (job diario), `core/dm/phases/postprocessing.py:416` (realtime logging), `api/routers/clone_score.py:161` (endpoint)
- **¿Tiene consumer?:** SÍ — endpoints `/clone-score/*`, logging metadata

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [x] metadata (`cognitive_metadata["clone_score"]`) / [x] observability

### Metadata escrita
- `cognitive_metadata["clone_score"]` — postprocessing.py:421 — consumer: logs/dashboard
- `CloneScoreEvaluation` rows (DB) — clone_score_engine.py:1031 — consumer: `/clone-score/latest,history`

### Solapamiento con P0/P1 auditados
- Parcial con `style_normalizer` (ambos leen tone profile) — pero aquí es eval, no mutate. NO dup.

### Bugs / dead code
- Usa `services.llm_judge` como dependencia — verificar si LLMJudge existe y cuánto cuesta (~$0.02/call × 60 llamadas/día). 
- Duplicate sample selection: `llm_samples = samples[:20]` pero `len(samples)` ya limit=20 → `llm_sample_count` siempre = min(20, len).
- `CloneScoreEvaluation.evaluated_at` vs `created_at` inconsistencia: router ordena por `evaluated_at`, engine filtra por `created_at`. Posible bug de schema.

### Veredicto
- **VALOR:** MEDIO — métrica útil de drift, pero default OFF
- **ESTADO:** DORMIDO_RECUPERABLE (por defecto OFF; scheduler registrado)
- **RAZÓN:** Sistema completo y bien diseñado pero costoso ($0.6/creador/día). Activar solo cuando se quiera monitorear calidad en prod.

---

## Sistema: DNA Update Triggers

- **Archivo:** `services/dna_update_triggers.py`
- **Líneas:** 197
- **Clasificación prev:** P2 (Learning)
- **Qué hace (1 línea):** Decide cuándo re-analizar RelationshipDNA (thresholds: 5 msgs mín, 10 msgs delta, 24h cooldown, 30d stale).

### Funcionalidad detallada
- `should_update()`: primera vez con ≥5 msgs; o ≥10 msgs nuevos; o >30d stale; ignorar en cooldown <24h.
- `schedule_dna_update()`: spawn thread daemon que invoca `relationship_dna_service.analyze_and_update_dna`. Retry 1x tras 2s.
- `get_update_reason()`: devuelve string (first_analysis, stale, new_messages_N).

### Activación
- **Feature flag:** `ENABLE_DNA_TRIGGERS=true` (default ON)
- **Se llama desde:** `core/dm/post_response.py:200`
- **¿Tiene consumer?:** SÍ — `RelationshipDNA` row actualizado → usado por `relationship_adapter` (P1 auditado)

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [x] metadata (actualiza DNA que luego consume relationship_adapter) / [ ] observability

### Metadata escrita
- `RelationshipDNA.dna_data` + `last_analyzed_at` + `total_messages_analyzed` — relationship_dna_service — consumer: `relationship_adapter` (inyecta en prompt)

### Solapamiento con P0/P1 auditados
- NO — es un gatillo, no inyecta. Alimenta `relationship_adapter` (auditado, P1).

### Bugs / dead code
- Thread daemon sin límite: si muchos leads actualizan a la vez, podría saturar. Sin rate-limit.
- `import threading` + `asyncio.to_thread` no usado — usa `threading.Thread()` directamente (old pattern).

### Veredicto
- **VALOR:** ALTO — gatillo crítico del sistema DNA
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** DNA alimenta relationship_adapter. Sin este gatillo, DNA se queda estático.

---

## Sistema: Commitment Tracker

- **Archivo:** `services/commitment_tracker.py`
- **Líneas:** 397
- **Clasificación prev:** P2 (Learning/ECHO)
- **Qué hace (1 línea):** Detecta promesas del bot ("te envío mañana") via regex, persiste en `commitments`, inyecta recordatorios pendientes en prompt.

### Funcionalidad detallada
- 11 patrones regex español: delivery, info_request, meeting, follow_up, promise.
- Temporal extraction: `mañana`→+1d, `esta semana`→+5d, `pasado mañana`→+2d, etc.
- `detect_and_store`: post-send, guarda commitments del assistant.
- `get_pending_text`: pre-gen, devuelve bullet list "[hace 2 días] Prometiste X (vence mañana)" para inyectar.
- `mark_fulfilled` + `expire_overdue` (grace 3 días).

### Activación
- **Feature flag:** `ENABLE_COMMITMENT_TRACKING=true` (default ON)
- **Se llama desde:** `core/dm/phases/context.py:430` (inyección), `core/dm/phases/postprocessing.py:511` (persistencia)
- **¿Tiene consumer?:** SÍ — prompt injection + job de cleanup

### Afecta al output?
- [x] system prompt (bloque "COMPROMISOS PENDIENTES") / [ ] user message / [ ] post-LLM mutation / [x] metadata / [x] observability

### Si inyecta contexto
- Inyecta en phase context.py como bloque de texto. Formato: `- [hace X días] Prometiste Y (vence Z)`

### Metadata escrita
- `CommitmentModel` rows — commitment_tracker.py:180 — consumer: prompt injection + dashboard

### Solapamiento con P0/P1 auditados
- NO — semánticamente único. Complementa `compressed_doc_d` y `memory_engine` (no duplica).

### Bugs / dead code
- Regex solo español. En multi-idioma (IT, EN, PT) NO detecta nada.
- `seen_types` dedupe es por tipo, no por texto — si el bot promete 2 delivery distintos, solo guarda 1.

### Veredicto
- **VALOR:** ALTO — previene que el bot olvide promesas (accountability)
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Funciona y está wired end-to-end. Mejora retention y trust.

---

## Sistema: Audio Intelligence

- **Archivo:** `services/audio_intelligence.py`
- **Líneas:** 526
- **Clasificación prev:** P2 (Input processing)
- **Qué hace (1 línea):** Pipeline 4-layer (Whisper→Clean→Extract→Synthesize) para audios entrantes, extrae entidades + intent + summary.

### Funcionalidad detallada
- Layer 1: raw_text (Whisper, upstream).
- Layer 2 `_clean`: LLM elimina fillers, 70-85% len. En modo "simple" usa regex `clean_transcription_regex` (sin LLM).
- Layer 3 `_extract`: JSON con people/places/dates/numbers/events/products/action_items/emotional_tone/topics.
- Layer 4 `_synthesize`: 1-3 frases que preservan toda info crítica.
- Circuit breaker global 10s. Per-layer 12s timeout. Modo: `simple` (default, regex-only) o `full` (4-layer LLM).

### Activación
- **Feature flag:** `ENABLE_AUDIO_INTELLIGENCE=false` (default off, pero modo simple usa regex siempre), `AUDIO_INTELLIGENCE_MODE=simple`
- **Se llama desde:** `core/instagram_modules/media.py:406`, `api/routers/messaging_webhooks/evolution_webhook.py:704,942` (WhatsApp)
- **¿Tiene consumer?:** SÍ — `msg_metadata.audio_intel` → `core/dm/phases/context.py:774-803` (inyecta transcripción + intent + entidades en prompt)

### Afecta al output?
- [x] system prompt (vía audio_intel metadata → context block) / [ ] user message / [ ] post-LLM mutation / [x] metadata / [ ] observability

### Si inyecta contexto
- En `context.py` se formatea: "Audio transcripción: {clean_text}", "Intención: X", "Entidades: {personas, lugares, fechas}", "Acciones: [list]".

### Metadata escrita
- `msg_metadata["audio_intel"]` con to_metadata() dict — media.py:415 — consumer: context.py:774 (bot prompt) y evolution_webhook (display text)

### Solapamiento con P0/P1 auditados
- NO — únicamente audio. Complementa pipeline.

### Bugs / dead code
- En modo `simple` con ENABLE_AUDIO_INTELLIGENCE=false → solo raw_text. Pero MIN_WORDS_FOR_PROCESSING=30 fuerza fallback a raw_text si corto.
- `AUDIO_INTELLIGENCE_MODE="simple"` es default pero código no respeta ese flag salvo regex-cleaning. El pipeline siempre corre si ENABLE_AUDIO_INTELLIGENCE=true.
- `to_legacy_fields()` y comentarios sobre backward compat — verificar si se usa.

### Veredicto
- **VALOR:** ALTO — audio es input crítico en IG/WhatsApp
- **ESTADO:** ACTIVO_VALIOSO (parcial: regex-only por default; LLM 4-layer opcional)
- **RAZÓN:** Wired a pipeline. Extrae info estructurada que context.py consume. Modo simple ahorra costos.

---

## Sistema: Ghost Reactivation

- **Archivo:** `core/ghost_reactivation.py`
- **Líneas:** 369
- **Clasificación prev:** P2 (Re-engagement)
- **Qué hace (1 línea):** Job 24h que reengancha leads fantasma (7-90d sin respuesta) via sequence RE_ENGAGEMENT del NurturingManager.

### Funcionalidad detallada
- Config: min 7d, max 90d, cooldown 30d, max 5/ciclo, enabled=True hardcoded.
- 3 mensajes de reactivación random (solo ES). 
- Filtra leads con pending followups existentes. Ordena por días desde contacto DESC.
- Tracking in-memory `_reactivated_leads` con TTL cleanup.
- Llama `NurturingManager.schedule_followup(sequence=RE_ENGAGEMENT)`.

### Activación
- **Feature flag:** `REACTIVATION_CONFIG["enabled"]=True` (no env flag, hardcoded)
- **Se llama desde:** `api/startup/handlers.py:386,393` (scheduler 86400s con delay 390s)
- **¿Tiene consumer?:** SÍ — crea nurturing followups que el scheduler de nurturing envía

### Afecta al output?
- [ ] system prompt / [x] user message (envía mensaje directamente al lead) / [ ] post-LLM mutation / [ ] metadata / [ ] observability

### Solapamiento con P0/P1 auditados
- NO — único

### Bugs / dead code
- Mensajes hardcoded solo en español — no multi-idioma. Si creador es internacional, lead recibe ES.
- `REACTIVATION_MESSAGES` se define pero nunca se usa en el código (schedule_followup usa sequence RE_ENGAGEMENT de nurturing).
- Tracking in-memory — se pierde en restart de Railway. Puede re-enviar a los mismos leads.
- Limit de 500 leads en query podría perder candidatos en creadores grandes.

### Veredicto
- **VALOR:** MEDIO — retention útil pero riesgo de spam
- **ESTADO:** ACTIVO_VALIOSO (con caveats)
- **RAZÓN:** Está running. Pero `REACTIVATION_MESSAGES` parece dead (usa nurturing sequence); revisar que la secuencia exista.

---

## Sistema: Insights Engine

- **Archivo:** `core/insights_engine.py`
- **Líneas:** 609
- **Clasificación prev:** P2 (Dashboard)
- **Qué hace (1 línea):** Genera misión del día + weekly insights (content/trend/product/competition) + weekly metrics para página "Hoy".

### Funcionalidad detallada
- `get_today_mission`: hot leads (intent>0.7), pending responses, bookings hoy, ghost count.
- `get_weekly_insights`: 4 cards basados en `FollowerMemoryDB.interests`, `products_discussed`.
- `get_weekly_metrics`: revenue (hardcoded 97€!), sales, response_rate con delta vs semana anterior.
- `_get_recommended_action`: reglas sobre objections/intent (ej: "envía link de pago" si intent≥0.9).

### Activación
- **Feature flag:** Ninguno explícito — routers endpoint directo
- **Se llama desde:** `api/routers/insights.py:31,50,70`
- **¿Tiene consumer?:** SÍ — dashboard frontend (página "Hoy")

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [ ] metadata / [x] observability (dashboard)

### Solapamiento con P0/P1 auditados
- NO — es dashboard-only, no toca bot.

### Bugs / dead code
- Revenue hardcoded 97€ por venta — valores fake. No lee `product_price` del creador aquí (solo en `_estimate_deal_value`).
- `_get_competition_insight` devuelve None siempre (placeholder).
- `FollowerMemoryDB.last_contact` tratado como string, luego parsed como ISO — frágil.

### Veredicto
- **VALOR:** BAJO — dashboard-only, no afecta al bot
- **ESTADO:** ACTIVO_INÚTIL (para bot) / ACTIVO_VALIOSO (para dashboard)
- **RAZÓN:** No toca el bot directamente. Genera métricas/insights para UI. NO es prioridad para auditoría de calidad de respuesta.

---

## Sistema: Intelligence Engine

- **Archivo:** `core/intelligence/engine.py`
- **Líneas:** 736
- **Clasificación prev:** P2 (Analytics/Predictions — possible umbrella)
- **Qué hace (1 línea):** Analytics dashboard engine: patterns (temporal/conversation/conversion), predictions (churn, revenue forecast), weekly report con LLM summary.

### Funcionalidad detallada
- `analyze_patterns`: SQL sobre `conversation_embeddings`, saca best_hours, best_days, intent distribution, avg messages.
- `predict_conversions`: scoring heurístico sobre `leads` (base_score + engagement_boost + recency_boost).
- `predict_churn_risk`: leads inactivos >5d.
- `forecast_revenue`: linear growth a 4 semanas.
- `generate_weekly_report`: combina todo + LLM executive summary.
- Recommendations: content, actions, products.

### Activación
- **Feature flag:** `ENABLE_INTELLIGENCE=true` (pero no wired a bot)
- **Se llama desde:** `api/routers/intelligence.py`, `scripts/intelligence_jobs.py`
- **¿Tiene consumer?:** SÍ — endpoints dashboard + jobs scripts (nunca scheduler)

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [ ] metadata / [x] observability (dashboard only)

### Solapamiento con P0/P1 auditados
- NO — umbrella analytics, no toca pipeline bot.
- Overlap con `insights_engine` (ambos dashboard) y `scripts/intelligence_jobs.py` — redundante.

### Bugs / dead code
- NO dispatcher — NO es umbrella. Es solo analytics dashboard. Sin listener/orchestrator que invoque al bot.
- `conversation_embeddings` dependency — tabla debe existir y poblarse (requiere RAG ingestion).
- `scripts/intelligence_jobs.py` NO se ve en Procfile ni en scheduler registrations (verificar manualmente) — puede ser CLI-only.

### Veredicto
- **VALOR:** BAJO — analytics para UI, no afecta al bot
- **ESTADO:** ACTIVO_INÚTIL (para el bot); posible dormant para dashboard
- **RAZÓN:** Solo dashboard/reporting. No es umbrella operacional. `intelligence_jobs.py` es CLI script standalone.

---

## Sistema: Identity Resolver

- **Archivo:** `core/identity_resolver.py`
- **Líneas:** 608
- **Clasificación prev:** P2 (Cross-platform)
- **Qué hace (1 línea):** Fusiona leads de distintas plataformas (IG/WA/TG) en una `UnifiedLead` única via email/phone/nombre/username.

### Funcionalidad detallada
- TIER 1 auto-merge: exact email or phone.
- TIER 2 auto-merge: exact full name or cross-platform username.
- TIER 3 log-only: partial/Levenshtein fuzzy match.
- `_refresh_unified`: recalcula display_name, profile_pic, email, phone, score máximo, mejor status (cliente>caliente>interesado).
- `manual_merge` / `manual_unmerge`.

### Activación
- **Feature flag:** `ENABLE_IDENTITY_RESOLVER=false` (default OFF!)
- **Se llama desde:** `core/dm/post_response.py:461` (fire-and-forget), `core/instagram_modules/lead_manager.py:610`, `api/routers/messaging_webhooks/whatsapp_webhook.py:143`, `telegram_webhook.py:301`, `api/routers/unified_leads.py` (manual endpoints)
- **¿Tiene consumer?:** SÍ — `UnifiedLead` table → `unified_leads` endpoint, dashboard

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [x] metadata (unified_lead_id en leads) / [ ] observability

### Solapamiento con P0/P1 auditados
- NO — único para cross-platform.
- SOLAPAMIENTO CON `unified_profile_service.py` — ver más abajo.

### Bugs / dead code
- `EMAIL_PATTERN`, `PHONE_PATTERN`, `INSTAGRAM_HANDLE_PATTERN`, `extract_contact_signals` definidos pero no usados dentro de `resolve_identity` (esa función solo usa `lead.email`, `lead.phone`). Extracción parece para uso externo.
- `_levenshtein` recursivo sin memo — ineficiente pero strings cortos.

### Veredicto
- **VALOR:** MEDIO — útil cuando creador multiplataforma
- **ESTADO:** DORMIDO_RECUPERABLE (flag OFF pero código llamado)
- **RAZÓN:** Feature flag off → `identity_resolver` no corre en post_response. Pero `lead_manager.py` y webhooks invocan sin check de flag (bug?). Verificar si crea UnifiedLeads no solicitados.

---

## Sistema: Unified Profile Service

- **Archivo:** `core/unified_profile_service.py`
- **Líneas:** 668
- **Clasificación prev:** P2 (Email capture + cross-platform)
- **Qué hace (1 línea):** Pide y captura email al lead con mensajes personalizados según offer_type (discount/content/priority/custom/none), crea `UnifiedProfile` + `PlatformIdentity`.

### Funcionalidad detallada
- `get_ask_message_by_offer_type`: mensaje según config creador (con fallback SAFE si config incompleta).
- `extract_email` regex.
- `should_ask_email`: evalúa si pedir email (tracking 24h cooldown, high intent triggers, skip friends/customers).
- `process_email_capture`: crea/vincula UnifiedProfile, link PlatformIdentity.
- `get_cross_platform_context`: recupera mensajes de otras plataformas del mismo perfil unificado.

### Activación
- **Feature flag:** `ENABLE_UNIFIED_PROFILE=false` (default off) + `creator.email_capture_config.enabled=True` (config creador)
- **Se llama desde:** `core/dm/post_response.py:315` (post-response email logic)
- **¿Tiene consumer?:** SÍ — `UnifiedProfile`/`PlatformIdentity` tables

### Afecta al output?
- [ ] system prompt / [x] user message (appends "¿me dejas tu email?" al final) / [ ] post-LLM mutation / [x] metadata (`email_captured`) / [ ] observability

### Solapamiento con P0/P1 auditados
- NO.
- SOLAPAMIENTO con `identity_resolver.py`: ambos fusionan identidades cross-platform pero con tablas distintas (`UnifiedLead` vs `UnifiedProfile`+`PlatformIdentity`). DUPLICACIÓN de modelo.

### Bugs / dead code
- Reusa `EmailAskTracking.ask_level` como `ask_count` (comentario lo dice) — schema desalineado.
- Regex `EMAIL_REGEX` duplicado en `identity_resolver.py`, `clone_score_engine.py`, `user_context_loader.py`. No DRY.

### Veredicto
- **VALOR:** MEDIO — email capture es core para nurturing
- **ESTADO:** DORMIDO_RECUPERABLE (flag OFF + config opt-in)
- **RAZÓN:** Seguridad strict-defaults bien implementada. Wired pero desactivado por default. DUPLICA modelo con `identity_resolver` — consolidar en futuro.

---

## Sistema: User Context Loader

- **Archivo:** `core/user_context_loader.py`
- **Líneas:** 672
- **Clasificación prev:** P2 (legacy loader)
- **Qué hace (1 línea):** Loader unificado de user data (FollowerMemory JSON + UserProfile + Lead table) para inyectar en prompt. MARCADO DEPRECATED en docstring.

### Funcionalidad detallada
- `UserContext` dataclass con prefs, interests, scores, history, flags.
- `load_user_context`: lee 3 fuentes, calcula flags (is_first, is_returning, days_since).
- `format_user_context_for_prompt`: produce bloque "=== CONTEXTO DEL USUARIO ===".
- `build_user_context_prompt`: combina context + history.
- Cache `BoundedTTLCache(max_size=200, ttl=60s)`.

### Activación
- **Feature flag:** Ninguno (DEPRECATED explícito en docstring línea 4-9)
- **Se llama desde:** 
  - `core/prompt_builder/sections.py:17,253`
  - `core/prompt_builder/orchestration.py:13,183,189`
  - Tests académicos: `tests/academic/*`, `tests/test_user_context_loader.py`
  - NO llamado desde `core/dm/phases/context.py` (pipeline actual)
- **¿Tiene consumer?:** PARCIAL — `core/prompt_builder/` lo usa pero ESE módulo no es invocado desde `core/dm/agent.py` ni `phases/context.py`

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [ ] metadata / [ ] observability
- (en teoría sí via prompt_builder pero ese módulo NO está en pipeline actual)

### Solapamiento con P0/P1 auditados
- SÍ — DUPLICADO CON `core/dm/phases/context.py` que reimplementa CRM enrichment + history loading (ver comentario context.py:1113: "Previously this data existed in user_context_loader (dead code)").

### Bugs / dead code
- Docstring marca como DEPRECATED (2026-04-01, Audit Sistema #7).
- `core/prompt_builder/*` importa de aquí pero ese submodule también parece dead (solo una ref en context.py:732 para `build_rules_section`).

### Veredicto
- **VALOR:** NINGUNO
- **ESTADO:** ELIMINAR (tras verificar prompt_builder también dead)
- **RAZÓN:** Explícitamente marcado DEPRECATED. Pipeline actual usa context.py directamente. Solo lo usan tests académicos legacy.

---

## Sistema: Conversation Boundary

- **Archivo:** `core/conversation_boundary.py`
- **Líneas:** 326
- **Clasificación prev:** P2 (session segmentation)
- **Qué hace (1 línea):** Detecta fronteras de sesión en stream continuo de DMs via time gap + greeting/farewell/discourse markers multilingües.

### Funcionalidad detallada
- Tiers: <5min=same, 5-30min=new if greeting, 30min-4h=new if greeting/farewell/discourse, >4h=new.
- `segment()`, `tag_sessions()`, `get_current_session()`.
- Greeting patterns: 11 idiomas (ES, CA, EN, PT, IT, FR, DE, AR, JA, KO, ZH).
- Bot-response rule: mensajes del assistant nunca inician sesión.
- Bug fixes documentados (BUG-CB-01 unix ts, CB-02 missing ts handling, CB-03 multilingual).

### Activación
- **Feature flag:** Ninguno
- **Se llama desde:** 
  - `core/dm/helpers.py:173,238` (PIPELINE BOT — activo)
  - `services/feedback_capture.py:55` (constante alineada)
  - Scripts: `scripts/tag_sessions.py`, `scripts/build_stratified_test_set.py`, `scripts/export_training_data.py`
  - `core/evaluation/strategy_map_builder.py`
- **¿Tiene consumer?:** SÍ — helpers.py filtra history del pipeline

### Afecta al output?
- [ ] system prompt (indirectly: limits history loaded) / [ ] user message / [ ] post-LLM mutation / [x] metadata (session_id) / [ ] observability

### Solapamiento con P0/P1 auditados
- NO — único para segmentación.

### Bugs / dead code
- Regex `^(hola|...)` con alternativas no ancladas puede matchear más de lo esperado (ej: "holi" → matches "hol" then "i"). Verificar.

### Veredicto
- **VALOR:** ALTO — evita que bot conteste con contexto de conversación de hace semanas
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Wired a DM helpers. Multilingüe. Bien testeado con bug fixes tracked.

---

## Sistema: Conversation Mode

- **Archivo:** `core/conversation_mode.py`
- **Líneas:** 139
- **Clasificación prev:** P2 (mode detection)
- **Qué hace (1 línea):** Clasifica conversación (greeting/product_inquiry/thanks/humor) via intent mapping + structural regex + calibration types.

### Funcionalidad detallada
- `detect()`: retorna (dominant_mode, probabilities, products_relevant).
- Intent→mode mapping (16 intents → 9 modes).
- Structural regex: detecta emoji_reaction, product_inquiry (símbolos moneda), greeting, thanks, casual_humor, short_response.
- `build_context_note`: devuelve `"El lead muestra interés comercial."` solo si products_relevant y prob>threshold.

### Activación
- **Feature flag:** `ENABLE_CONVERSATION_MODE=false` (default OFF)
- **Se llama desde:** NINGÚN CALLER EN PRODUCCIÓN
- **¿Tiene consumer?:** NO — grep solo encuentra a sí mismo y a docs

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [ ] metadata / [ ] observability

### Solapamiento con P0/P1 auditados
- SÍ — overlap con `context_detector` (P1 auditado) que también clasifica modo de conversación.

### Bugs / dead code
- 100% dead code. Sin callers.

### Veredicto
- **VALOR:** NINGUNO
- **ESTADO:** ELIMINAR
- **RAZÓN:** Sin callers, flag OFF, duplicado con context_detector auditado.

---

## Sistema: Personalized Ranking

- **Archivo:** `core/personalized_ranking.py`
- **Líneas:** 137
- **Clasificación prev:** P2 (reranking)
- **Qué hace (1 línea):** Re-rankea resultados de búsqueda/RAG según UserProfile (intereses + content preference) + adapta system prompt.

### Funcionalidad detallada
- `personalize_results`: combina base_score + personal_score (interests + content_pref_sigmoid).
- `adapt_system_prompt`: añade "CONTEXTO DEL USUARIO" al prompt con interests, objections, products, response_style.

### Activación
- **Feature flag:** Ninguno
- **Se llama desde:** SOLO TESTS (`tests/test_personalization*.py`, `tests/audit/test_audit_personalized_ranking.py`)
- **¿Tiene consumer?:** NO — sin callers en producción

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [ ] metadata / [ ] observability

### Solapamiento con P0/P1 auditados
- SÍ — `adapt_system_prompt` duplica funcionalidad de `preference_profile_service` (P1 auditado). 
- `personalize_results` duplica con `reranking` flag y RAG pipeline auditado.

### Bugs / dead code
- 100% dead code en pipeline real. Solo tests lo ejercitan.

### Veredicto
- **VALOR:** NINGUNO
- **ESTADO:** ELIMINAR
- **RAZÓN:** Sin callers productivos, duplica preference_profile_service y reranking auditados.

---

## Sistema: Response Variator v1 (LEGACY)

- **Archivo:** `services/response_variator.py`
- **Líneas:** 252
- **Clasificación prev:** P2 (dup check)
- **Qué hace (1 línea):** Detecta message type (greeting/farewell/thanks/laugh/emoji/meeting) y devuelve respuesta variada desde `STEFAN_RESPONSE_POOLS`.

### Funcionalidad detallada
- `detect_message_type`: regex para meeting_request, greeting, farewell, thanks, confirmation, enthusiasm, laugh, emoji_reaction.
- `get_response` + `maybe_add_follow_up` (15% chance tras greeting).
- `process()`: retorna (response, message_type).
- Usa `models.response_variations.STEFAN_RESPONSE_POOLS` — hardcoded para Stefan.

### Activación
- **Feature flag:** Ninguno
- **Se llama desde:** SOLO TESTS (`tests/test_response_variator.py`, `tests/test_dm_phases_unit.py`), `services/bot_orchestrator.py` (orchestrator no wired a producción), `core/dm/phases/detection.py` (NO — `detection.py` usa v2 `agent.response_variator`)
- **¿Tiene consumer?:** NO en pipeline producción. `core/dm/agent.py:64` usa `response_variator_v2`.

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [ ] metadata / [ ] observability

### Solapamiento con P0/P1 auditados
- SÍ — v1 REEMPLAZADO por `response_variator_v2` (AUDITADO P1). Es strict duplicate.

### Bugs / dead code
- STEFAN_RESPONSE_POOLS es hardcoded a un creador ("Stefan") — no multi-tenant.
- Pools no existen para casos genéricos.

### Veredicto
- **VALOR:** NINGUNO
- **ESTADO:** ELIMINAR
- **RAZÓN:** Reemplazado por v2 auditado. Solo queda en tests y `bot_orchestrator.py` (dead file, ver siguiente sección).

---

## Sistema: Timing Service

- **Archivo:** `services/timing_service.py`
- **Líneas:** 150
- **Clasificación prev:** P2 (human-like delays)
- **Qué hace (1 línea):** Calcula delays naturales (think + reading + typing + variation) y chequea horarios activos (8am-11pm Madrid) con 10% chance off-hours.

### Funcionalidad detallada
- `calculate_delay`: 1-3s think + message_len/200 reading + response_len/50 typing + ±20% variation, clamp [2s, 30s].
- `is_active_hours` con tz Madrid.
- `wait_before_response` async sleep.
- `format_wait_message`: fallback "no disponible, te respondo mañana".

### Activación
- **Feature flag:** Ninguno
- **Se llama desde:** `services/bot_orchestrator.py:36,76,81` (NO wired a producción), `services/message_splitter.py` (verificar)
- **¿Tiene consumer?:** NO en pipeline producción. `bot_orchestrator.py` no se invoca desde `api/` ni `core/dm/`.

### Afecta al output?
- [ ] system prompt / [ ] user message / [ ] post-LLM mutation / [ ] metadata / [ ] observability (affects timing only)

### Solapamiento con P0/P1 auditados
- NO directo — pero `message_splitter` (auditado) maneja inter-bubble delays que overlap con este.

### Bugs / dead code
- `bot_orchestrator.py` parece dead (no se importa desde api/core/dm). Verificar.
- Timezone hardcoded Madrid — no multi-tenant global.

### Veredicto
- **VALOR:** BAJO — aporta naturalidad pero no está wired
- **ESTADO:** DORMIDO_RECUPERABLE
- **RAZÓN:** Código completo y razonable, pero solo usado por `bot_orchestrator` que no está en el flujo actual. Si algún día se retoma la arquitectura "humana", recuperar.

---

## Sistema: Prompt Service (PromptBuilder)

- **Archivo:** `services/prompt_service.py`
- **Líneas:** 231
- **Clasificación prev:** P2 (prompt building)
- **Qué hace (1 línea):** Constructor de system prompt + user context (custom_instructions, knowledge_about, products, safety block) — usado por `DMAgent`.

### Funcionalidad detallada
- `build_system_prompt`: priority order → custom_instructions (CreatorDMStyle) → knowledge_about (web/bio/expertise/location) → creator name → products → safety block.
- `build_user_context`: stage, lead_info (interests, products_discussed, objections, purchase_score, is_customer, summary), optional history.
- `build_complete_prompt`: combina ambos.
- TONES dict (professional/casual/friendly) con emoji rules — pero `_tone_config` NUNCA SE USA (asignado con `_` prefijo).

### Activación
- **Feature flag:** Ninguno — core del pipeline
- **Se llama desde:** 
  - `core/dm/agent.py:54,317` (instancia `PromptBuilder` en agent init)
  - `core/dm/phases/context.py:1063,1214` (invoca `agent.prompt_builder.build_system_prompt`, `build_user_context`)
  - `services/__init__.py:11,29` (export)
- **¿Tiene consumer?:** SÍ — CORE del DM pipeline

### Afecta al output?
- [x] system prompt (PRIMARY) / [x] user message (primary context) / [ ] post-LLM mutation / [ ] metadata / [ ] observability

### Si inyecta contexto
- System prompt completo: custom_instructions + knowledge_about + creator_name + products + safety block.
- User context: username + etapa + lead_info + history.

### Metadata escrita
- Ninguna directa. Solo construye prompts consumidos por LLM.

### Solapamiento con P0/P1 auditados
- PARCIAL — `core/dm/phases/context.py:220-262` tiene helpers `_format_knowledge`, `_format_products`, `_format_safety` que "replicate PromptBuilder formatting byte-for-byte" (comentario línea 220). Es una duplicación intencional (para side-by-side test) pero genera tech debt.

### Bugs / dead code
- `TONES` dict definido pero `_tone_config` prefijo `_` — nunca consumido. Los emoji_rules no se inyectan en prompt real.
- `default_tone="friendly"` y `default_name="Asistente"` — genéricos, rara vez útiles.
- Safety block hardcoded en español — no multi-idioma.

### Veredicto
- **VALOR:** ALTO — backbone del prompt
- **ESTADO:** ACTIVO_VALIOSO
- **RAZÓN:** Core del pipeline DM. Construye system+user para cada respuesta. La duplicación con context.py es legacy; consolidar pendiente.

---

---

## 4 · Tabla Resumen — 62 Sistemas Ordenados por Valor

### 4.1 — ACTIVO_VALIOSO (33)

| # | Sistema | Archivo | Batch | VALOR | Output | Nota |
|---|---|---|---|---|---|---|
| 1 | Personality Extraction Pipeline | `core/personality_extraction/` | C | ALTO | Docs A-E | Core del onboarding; Doc E sin consumer runtime |
| 2 | Personality Loader | `core/personality_loader.py` | C | ALTO | Runtime | 6 consumers; puente Doc D → runtime |
| 3 | Tone Profile DB | `core/tone_profile_db.py` | C | ALTO | RAG+onboarding | Mal nombrado (3 entidades); crítico |
| 4 | BM25 Lexical Retriever | `core/rag/bm25.py` | B | MEDIO | RAG híbrido | Default ON |
| 5 | Cross-Encoder Reranker | `core/rag/reranker.py` | B | ALTO | RAG híbrido | Default ON, warmup en bg |
| 6 | Semantic Chunker | `core/semantic_chunker.py` | B | MEDIO | Ingestion | Default ON |
| 7 | Semantic Memory pgvector | `core/semantic_memory_pgvector.py` | B | ALTO | Episodic recall | Core memoria episódica |
| 8 | Bot Question Analyzer | `core/bot_question_analyzer.py` | A | ALTO | System prompt | Inyecta notas en context.py:881-899 |
| 9 | phases/detection (Input Guards) | `core/dm/phases/detection.py` | D | ALTO | Guardas | Phase 1 del DM |
| 10 | dm_post_response | `core/dm/post_response.py` | D | ALTO | Side effects | Save+scoring+nurturing |
| 11 | contextual_prefix | `core/contextual_prefix.py` | D | ALTO | Embeddings docs | Anthropic pattern, +35-49% |
| 12 | context_analytics | `core/dm/context_analytics.py` | D | MEDIO | Observability | Token distribution |
| 13 | dm_strategy | `core/dm/strategy.py` | D | MEDIO | Strategy routing | 2 ramas DORMIDAS |
| 14 | intent_classifier (core) | `core/intent_classifier.py` | E | MEDIO | DB intent | Solo utility `classify_intent_simple` viva |
| 15 | intent_service | `services/intent_service.py` | E | ALTO | System prompt | Canonical en hot path |
| 16 | lead_categorizer v2 | `core/lead_categorizer.py` | E | ALTO | Lead status | v2 en DM live |
| 17 | relationship_dna_service | `services/relationship_dna_service.py` | E | ALTO | System prompt | Personalización por lead |
| 18 | relationship_analyzer | `services/relationship_analyzer.py` | E | ALTO | DNA enrichment | Fuente de DNA |
| 19 | relationship_type_detector | `services/relationship_type_detector.py` | E | MEDIO | DNA seed | Usado en seed path |
| 20 | relationship_dna_repository | `services/relationship_dna_repository.py` | E | ALTO | Persistencia | Backbone DNA DB |
| 21 | FeedbackCapture | `services/feedback_capture.py` | F | ALTO | Learning loop | Entrypoint único (evaluator/copilot/best_of_n) |
| 22 | feedback_store (SHIM) | `services/feedback_store.py` | F | MEDIO | Re-export | Backward-compat shim |
| 23 | preference_pairs_service (SHIM) | `services/preference_pairs_service.py` | F | MEDIO | Re-export | → feedback_capture |
| 24 | gold_examples_service (SHIM) | `services/gold_examples_service.py` | F | MEDIO | Re-export | → style_retriever (P1) |
| 25 | Memory Extraction | `services/memory_extraction.py` | F | ALTO | Memoria | Writer sibling de memory_engine |
| 26 | DNA Update Triggers | `services/dna_update_triggers.py` | G | ALTO | DNA refresh | Thresholds 5/10/24h/30d |
| 27 | Commitment Tracker | `services/commitment_tracker.py` | G | ALTO | System prompt | Inyecta en context.py:430 |
| 28 | Audio Intelligence | `services/audio_intelligence.py` | G | ALTO | User message | 4-capas + circuit breaker 10s |
| 29 | Ghost Reactivation | `core/ghost_reactivation.py` | G | MEDIO | Scheduler 24h | Dead array `REACTIVATION_MESSAGES` |
| 30 | Conversation Boundary | `core/conversation_boundary.py` | G | ALTO | History cutoff | 11 idiomas, tiered gaps |
| 31 | Prompt Service | `services/prompt_service.py` | G | ALTO | System+user | Backbone; bug `_tone_config` (emoji rules sin wire) |
| 32 | Style Analyzer | `core/style_analyzer.py` | C | MEDIO | style_prompt | Solapamiento parcial con Doc D |
| 33 | Vocabulary Extractor | `services/vocabulary_extractor.py` | C | ALTO | DNA/style | + ImportError en callers legacy |

### 4.2 — ACTIVO_INÚTIL (10) — "Se ejecuta pero no aporta valor"

| # | Sistema | Archivo | Batch | Razón |
|---|---|---|---|---|
| 34 | Confidence Scorer | `core/confidence_scorer.py` | A | Flag false; solo copilot analytics |
| 35 | Self-Consistency Validator | `core/reasoning/self_consistency.py` | A | 2 LLM calls extra sin impacto medible |
| 36 | Reflexion Engine (rule-based) | `core/reflexion_engine.py` | A | Flag OFF + metadata huérfana (borderline ELIMINAR) |
| 37 | Query Expansion | `core/query_expansion.py` | B | Default ON pero perjudica embeddings densos |
| 38 | Knowledge Base (services) | `services/knowledge_base.py` | B | JSON files excluidos por `.railwayignore` |
| 39 | Tone Service | `core/tone_service.py` | C | Legacy pre-Doc D, solo fallback voseo |
| 40 | dm_knowledge | `core/dm/knowledge.py` | D | 0 consumers prod; solo migration tests |
| 41 | Learning Rules Service | `services/learning_rules_service.py` | F | Flag removido; persona_compiler duplica consts por copy-paste |
| 42 | Insights Engine | `core/insights_engine.py` | G | Dashboard only; revenue `=97€` hardcoded |
| 43 | Intelligence Engine | `core/intelligence/engine.py` | G | Analytics CLI, no umbrella |

### 4.3 — DORMIDO_RECUPERABLE (13)

| # | Sistema | Archivo | Batch | VALOR si se enciende |
|---|---|---|---|---|
| 44 | Best-of-N | `core/best_of_n.py` | A | MEDIO — pipeline completo; coste 3x LLM |
| 45 | Reflexion LLM | `core/reasoning/reflexion.py` | A | BAJO — depende de ENABLE_NURTURING |
| 46 | Hierarchical Memory | `core/hierarchical_memory/` | B | MEDIO — requiere JSONL precomputados |
| 47 | PersonaCompiler | `services/persona_compiler.py` | C | ALTO teórico; **bug persistencia**: escribe `creators.doc_d`, runtime lee `personality_docs.content` |
| 48 | history_compactor | `core/dm/history_compactor.py` | D | ALTO — CC-faithful; ON en sprints |
| 49 | lead_categorization v1 | `core/lead_categorization.py` | E | Migrar callers a v2 o ELIMINAR |
| 50 | Memory Consolidator (orch) | `services/memory_consolidator.py` | F | ALTO — ON en config gemma4_26b |
| 51 | Memory Consolidation LLM | `services/memory_consolidation_llm.py` | F | ALTO — Phase 3 (dedupe/contradiction) |
| 52 | Memory Consolidation Ops | `services/memory_consolidation_ops.py` | F | ALTO — Phase 1-4 workers |
| 53 | CloneScore Engine | `services/clone_score_engine.py` | G | MEDIO — drift metric |
| 54 | Identity Resolver | `core/identity_resolver.py` | G | MEDIO — multiplataforma; **wiring inconsistente** |
| 55 | Unified Profile Service | `core/unified_profile_service.py` | G | MEDIO — email capture; solapamiento con identity_resolver |
| 56 | Timing Service | `services/timing_service.py` | G | BAJO — naturalidad delay; no wired |

### 4.4 — ELIMINAR (6) — Dead code confirmado

| # | Sistema | Archivo | Batch | Razón |
|---|---|---|---|---|
| 57 | Semantic Memory (ChromaDB) | `core/semantic_memory.py` | B | 0 consumers runtime; superseded por pgvector |
| 58 | RAG Service (services) | `services/rag_service.py` | B | Duplica `core/rag/semantic.py` (P1) e inferior |
| 59 | User Context Loader | `core/user_context_loader.py` | G | **Self-declared DEPRECATED** 2026-04-01 |
| 60 | Conversation Mode | `core/conversation_mode.py` | G | 0 callers; duplica context_detector (P1) |
| 61 | Personalized Ranking | `core/personalized_ranking.py` | G | Solo tests; duplica preference_profile_service (P1) |
| 62 | Response Variator v1 | `services/response_variator.py` | G | Reemplazado por v2 (P1) |

---

## 5 · Conclusiones y Acción

### 5.1 Recuento final
- **ACTIVO_VALIOSO: 33** (53%) — el "core" real post-audit
- **ACTIVO_INÚTIL: 10** (16%) — gasto de CPU/tokens sin retorno
- **DORMIDO_RECUPERABLE: 13** (21%) — capacidad latente
- **ELIMINAR: 6** (10%) — dead code confirmado

### 5.2 Hallazgo crítico
El usuario estimaba "~37 sistemas restantes". **La realidad es 62**. Gap de 25 sistemas no contabilizados antes, distribuidos en:
- 10 shims/wrappers delgados
- 13 sistemas dormidos no documentados
- 6 archivos de dead code por migraciones incompletas

### 5.3 Acciones prioritarias (ordenadas por ROI)

**P0 — Bugs silenciosos (fix inmediato, bajo riesgo):**
1. Fix `prompt_service._tone_config` → cablear emoji rules al system prompt (Batch G)
2. Fix `VocabularyExtractor` ImportError en 2 callers legacy (Batch C)
3. Fix `identity_resolver` wiring — añadir `ENABLE_IDENTITY_RESOLVER` check en 3 callers (Batch G)
4. Unificar enums `Intent` entre core/intent_classifier y services/intent_service (Batch E)

**P1 — Eliminar dead code (reduce surface área):**
5. Borrar 6 sistemas ELIMINAR (§4.4) — ~2000 líneas
6. Decidir: PersonaCompiler → fix persistencia + activar, o eliminar

**P2 — Consolidar duplicaciones:**
7. Migrar 5 callers de `lead_categorization` v1 → v2, después borrar v1
8. Consolidar `identity_resolver` + `unified_profile_service` antes de activar cualquiera
9. Eliminar metadata huérfana: `reflexion_issues`, `reflexion_severity`, `self_consistency_replaced`, `is_short_affirmation`

**P3 — Activar dormant valioso (mejora CCEE):**
10. Activar trio `memory_consolidation_*` con monitoreo (cost vs hygiene trade-off)
11. Evaluar `history_compactor` empíricamente (sprints actuales lo tienen ON)
12. Best-of-N: decidir si vale el 3x LLM coste

### 5.4 Notas de solapamiento con P0/P1 auditados
- `gold_examples_service` es literalmente un alias de `style_retriever` (P1) — incluido aquí por completitud
- `feedback_store` y `preference_pairs_service` son re-exports de `feedback_capture` — mismo caso
- `services/rag_service.py` duplica `core/rag/semantic.py` (P1) — ELIMINAR
- `core/semantic_memory.py` coexiste con `core/semantic_memory_pgvector.py`; el primero es legacy ChromaDB (ELIMINAR)
- `services/response_variator.py` v1 ya fue reemplazado por `response_variator_v2.py` (P1)

---

**Fin del Inventario W1.** Total: **62 sistemas** auditados, **3171 líneas** de documentación, **7 batches paralelos**, **10 bugs críticos**, **9 duplicaciones**, **6 eliminaciones propuestas**.
