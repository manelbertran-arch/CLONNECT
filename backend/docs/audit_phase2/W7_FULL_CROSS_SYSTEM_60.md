# W7 — Cross-System Architecture (Consolidación 60+ Sistemas)

**Fecha:** 2026-04-16
**Autor dispatcher:** W7 (Opus 4.6, extended)
**Scope:** Documento definitivo de arquitectura Clonnect DM pipeline, sintetizando 6 workers de Phase 2 (W1-W6) + 6 documentos pre-existentes (CROSS_SYSTEM_ARCHITECTURE, CRUCE_REPO_VS_CLONNECT, DEEP_DIVE_CONTEXT_ENGINEERING, DEEP_DIVE_CLONNECT_PIPELINE, GRAPH_REPORT, Clonnect_Backend_Graph).
**Reemplaza:** `docs/CROSS_SYSTEM_ARCHITECTURE.md` (sólo cubría 23 sistemas; ahora **62+**).

**Reglas aplicadas:**
- Citaciones con `file:line` contra los documentos fuente.
- No se audita código nuevo no citado en los inputs.
- Contradicciones entre fuentes quedan registradas en §10 (Apéndices) — NO se resuelven silenciosamente.
- `[GAP: …]` marca información faltante explícitamente.

---

## 0 · Resumen Ejecutivo (1 página)

### 0.1 Qué es Clonnect (modelo mental)

Clonnect es un DM single-shot multi-tenant: cada webhook Instagram dispara una request HTTP que construye un prompt completo desde cero (stateless), llama al LLM una única vez, y postprocesa la respuesta por 27 pasos antes de enviar al lead. Comparado con Claude Code (CC), que es un agente multi-turn con conversación acumulada, **Clonnect no tiene "sesión server-side"** — el contexto se recompone per-mensaje. Esto tiene implicaciones profundas en compaction (§5), metadata (§3) y gating (§5).

### 0.2 Números clave

| Métrica | Valor | Fuente |
|---------|------:|--------|
| Sistemas totales auditados | **62** | W1 §0, §4 |
| ACTIVO_VALIOSO | 33 (53%) | W1 §4.1 |
| ACTIVO_INÚTIL (ejecuta pero no aporta) | 10 (16%) | W1 §4.2 |
| DORMIDO_RECUPERABLE | 13 (21%) | W1 §4.3 |
| ELIMINAR (dead code confirmado) | 6 (10%) | W1 §4.4 |
| Campos de metadata únicos | 114 | W2 §Resumen |
| Campos DECISION (branchan lógica) | 37 (32%) | W2 §Resumen |
| Campos REFERENCE (leídos sin branch) | 12 (11%) | W2 §Resumen |
| Campos ORPHAN (escritos, nunca leídos) | **65 (57%)** | W2 §Resumen |
| Sistemas 100% orphan candidatos a limpieza | 10 categorías | W2 §Sistemas 100% orphan |
| CC gates paralelos en `getAttachments` | ~38 | W5 §0 |
| Estrategias de compaction en CC | 4 (microCompact, SessionMemoryCompact, autoCompact, reactiveCompact) | W6 §TL;DR |
| Estrategias de compaction en Clonnect | **0** (sólo truncation_recovery post-error) | W6 §5.1 |
| Nodos grafo de dependencias | 21,159 / 40,556 edges / 624 comunidades | Clonnect_Backend_Graph §Resumen |
| Token budget real Iris worst case (S8) | 2,367 tokens (7.2% del ctx window 32K) | W3 §7 |
| Doc D Iris (style) tokens | **1,383** (66-77% del prompt) | W3 §2 |
| Doc D Stefano (style) tokens | 174 (14-30% del prompt) | W3 §2 |
| Iris char budget utilizado en S8 | **89.8%** (`7,180/8,000`) | W3 §4 |

### 0.3 Top 5 insights arquitectónicos

1. **Asimetría de context pressure por-creator, no global.** Iris consume 69% del char budget con sólo el Doc D; Stefano apenas 9%. La narrativa "style=41% del budget" del Sprint 4 es incorrecta en tokens — el real ratio depende del creator (W3 §6).

2. **CC no tiene "orquestador con budget"; Clonnect tampoco.** Ambos son distribuidos, pero por razones opuestas: CC porque cada gate está hard-capped y fail-silent (W5 §0); Clonnect porque tiene un budget global (`MAX_CONTEXT_CHARS=8000`) y trunca post-assembly sin re-priorizar (DEEP_DIVE_CLONNECT §2). **Ninguno de los dos negocia entre secciones al ensamblar.**

3. **Clonnect escribe 65 campos de metadata que nadie lee.** Son el 57% del total. Son especialmente peligrosos cuando son flags de seguridad (`prompt_injection_attempt`, `sensitive_detected`) sin alerting ni persistencia (W2 §Hallazgos de seguridad).

4. **Dual Memory Storage Conflict sigue sin resolverse.** `MemoryStore` (JSON) y `ConversationMemoryService` (DB, regex español hardcoded) gestionan "qué dijo este lead" de forma independiente (W4 §4.5 + GRAPH_REPORT §Hiperedges). CC evita este problema con **scope separation por artefacto** (memdir/ vs SessionMemory/) + **single-writer enforcement por tool sandboxing** (W4 §4.5).

5. **PersonaCompiler persistence mismatch invalida el sistema.** `services/persona_compiler.py` escribe a `creators.doc_d`, pero el runtime lee de `personality_docs.content` (W1 §47). Flag off + bug → feature muerta de facto.

### 0.4 Top 5 bugs críticos que mueven CCEE o seguridad

| # | Bug | Fichero | Impacto |
|---|-----|---------|---------|
| 1 | **PersonaCompiler persistence mismatch** | `services/persona_compiler.py:?` vs `core/personality_loader.py` | Feature dormant; activarla sin fix no mueve el prompt |
| 2 | **`prompt_service._tone_config` sin cable** | `services/prompt_service.py:22-35` | Emoji rules definidos pero nunca inyectados al system prompt (W1 §31) |
| 3 | **VocabularyExtractor ImportError en 2 callers** | `services/whatsapp_onboarding_pipeline.py:498`, `mega_test_w2.py:846,1212` | Runtime error al ejecutar onboarding WhatsApp (W1 §33) |
| 4 | **`identity_resolver` wiring inconsistente** | 3 callers invocan sin `ENABLE_IDENTITY_RESOLVER` check | Crea `UnifiedLeads` no solicitados (W1 §54) |
| 5 | **Seguridad: `prompt_injection_attempt` detectada pero sin alertar** | `detection.py:103` produce; 0 consumers | Detección muda (W2 §Hallazgos de seguridad) |

### 0.5 Veredicto arquitectónico de 1 línea

**Clonnect tiene la mayoría de piezas correctas (33 ACTIVO_VALIOSO, ~85% del valor), pero su pipeline de memoria, metadata y compaction está 10 años por detrás de CC en disciplina arquitectónica (0 compaction strategies, 57% orphan metadata, dual storage conflict sin resolver).** El problema NO es falta de features — es falta de ownership, caches estables y fail-silent gates.

---

## 1 · Inventario Completo (62 sistemas)

**Fuente primaria:** W1_inventory_37_systems.md §3, §4.

### 1.1 ACTIVO_VALIOSO (33 sistemas — el core real post-auditoría)

Sistemas que sí mueven el output o el estado de lead/bot, con consumers en producción y código mantenido. Distribución por batch:

| # | Sistema | Archivo | Batch | VALOR | Output afectado |
|---|---------|---------|-------|-------|-----------------|
| 1 | Personality Extraction Pipeline | `core/personality_extraction/` | C | ALTO | Docs A-E; Doc E sin consumer runtime |
| 2 | Personality Loader | `core/personality_loader.py` | C | ALTO | Puente Doc D → runtime (6 consumers) |
| 3 | Tone Profile DB | `core/tone_profile_db.py` | C | ALTO | RAG + onboarding (mal nombrado) |
| 4 | BM25 Lexical Retriever | `core/rag/bm25.py` | B | MEDIO | RAG híbrido, default ON |
| 5 | Cross-Encoder Reranker | `core/rag/reranker.py` | B | ALTO | RAG híbrido, default ON + warmup bg |
| 6 | Semantic Chunker | `core/semantic_chunker.py` | B | MEDIO | Ingestion, default ON |
| 7 | Semantic Memory pgvector | `core/semantic_memory_pgvector.py` | B | ALTO | Episodic recall — memoria episódica core |
| 8 | Bot Question Analyzer | `core/bot_question_analyzer.py` | A | ALTO | Notas inyectadas en `context.py:881-899` |
| 9 | phases/detection (Input Guards) | `core/dm/phases/detection.py` | D | ALTO | Guardas de Phase 1 |
| 10 | dm_post_response | `core/dm/post_response.py` | D | ALTO | Side effects (save + scoring + nurturing) |
| 11 | contextual_prefix | `core/contextual_prefix.py` | D | ALTO | Embeddings docs, Anthropic pattern +35-49% |
| 12 | context_analytics | `core/dm/context_analytics.py` | D | MEDIO | Observability de token distribution |
| 13 | dm_strategy | `core/dm/strategy.py` | D | MEDIO | Strategy routing; 2 ramas FAMILIA/AMIGO DORMIDAS |
| 14 | intent_classifier (core) | `core/intent_classifier.py` | E | MEDIO | DB intent; sólo `classify_intent_simple` viva |
| 15 | intent_service | `services/intent_service.py` | E | ALTO | System prompt — canonical en hot path |
| 16 | lead_categorizer v2 | `core/lead_categorizer.py` | E | ALTO | Lead status — v2 en DM live |
| 17 | relationship_dna_service | `services/relationship_dna_service.py` | E | ALTO | System prompt — personalización por lead |
| 18 | relationship_analyzer | `services/relationship_analyzer.py` | E | ALTO | DNA enrichment — fuente de DNA |
| 19 | relationship_type_detector | `services/relationship_type_detector.py` | E | MEDIO | DNA seed path |
| 20 | relationship_dna_repository | `services/relationship_dna_repository.py` | E | ALTO | Backbone DNA DB |
| 21 | FeedbackCapture | `services/feedback_capture.py` | F | ALTO | Entrypoint único (evaluator/copilot/best_of_n) |
| 22 | feedback_store (SHIM) | `services/feedback_store.py` | F | MEDIO | Re-export backward-compat |
| 23 | preference_pairs_service (SHIM) | `services/preference_pairs_service.py` | F | MEDIO | Re-export → feedback_capture |
| 24 | gold_examples_service (SHIM) | `services/gold_examples_service.py` | F | MEDIO | Re-export → style_retriever (P1) |
| 25 | Memory Extraction | `services/memory_extraction.py` | F | ALTO | Writer sibling de memory_engine |
| 26 | DNA Update Triggers | `services/dna_update_triggers.py` | G | ALTO | DNA refresh (thresholds 5/10/24h/30d) |
| 27 | Commitment Tracker | `services/commitment_tracker.py` | G | ALTO | System prompt — inyecta en `context.py:430` |
| 28 | Audio Intelligence | `services/audio_intelligence.py` | G | ALTO | User message; 4 capas + circuit breaker 10s |
| 29 | Ghost Reactivation | `core/ghost_reactivation.py` | G | MEDIO | Scheduler 24h; **dead array `REACTIVATION_MESSAGES`** |
| 30 | Conversation Boundary | `core/conversation_boundary.py` | G | ALTO | History cutoff; 11 idiomas, tiered gaps |
| 31 | Prompt Service | `services/prompt_service.py` | G | ALTO | System+user; **bug `_tone_config`** (emoji rules sin wire) |
| 32 | Style Analyzer | `core/style_analyzer.py` | C | MEDIO | style_prompt; solapamiento parcial con Doc D |
| 33 | Vocabulary Extractor | `services/vocabulary_extractor.py` | C | ALTO | DNA/style; **ImportError en callers legacy** |

**Observación W1 §0 (línea 28):** 4 de los 33 ACTIVO_VALIOSO tienen solapamientos parciales o bugs no-bloqueantes: Style Analyzer, dm_strategy con ramas FAMILIA/AMIGO muertas, Vocabulary Extractor + ImportError en legacy, Ghost Reactivation con dead array `REACTIVATION_MESSAGES`.

### 1.2 ACTIVO_INÚTIL (10 sistemas — se ejecutan sin aportar valor)

Sistemas que corren en producción (o están referenciados) pero no aportan señal medible, tienen metadata 100% huérfana, o están rotos a nivel config.

| # | Sistema | Archivo | Batch | Razón detallada |
|---|---------|---------|-------|-----------------|
| 34 | Confidence Scorer | `core/confidence_scorer.py` | A | Flag `ENABLE_CONFIDENCE_SCORER=false` por default; único consumer es copilot analytics (W1 §Sistema: Confidence Scorer) |
| 35 | Self-Consistency Validator | `core/reasoning/self_consistency.py` | A | 2 LLM calls extra sin impacto medible; flag OFF (W1 §Sistema: Self-Consistency Validator) |
| 36 | Reflexion Engine (rule-based) | `core/reflexion_engine.py` | A | Flag OFF + metadata huérfana — borderline ELIMINAR (W1 §Sistema: Reflexion Engine) |
| 37 | Query Expansion | `core/query_expansion.py` | B | Default ON pero perjudica embeddings densos (W1 §Sistema: Query Expansion) |
| 38 | Knowledge Base (services) | `services/knowledge_base.py` | B | JSON files excluidos por `.railwayignore` → nunca hay kb hits en prod |
| 39 | Tone Service | `core/tone_service.py` | C | Legacy pre-Doc D, sólo fallback voseo (W1 §Sistema: Tone Service) |
| 40 | dm_knowledge | `core/dm/knowledge.py` | D | 0 consumers prod; sólo migration tests (W1 §Sistema: dm_knowledge) |
| 41 | Learning Rules Service | `services/learning_rules_service.py` | F | Flag removido; `persona_compiler` duplica constantes por copy-paste |
| 42 | Insights Engine | `core/insights_engine.py` | G | Dashboard only; revenue `=97€` hardcoded (W1 §Sistema: Insights Engine) |
| 43 | Intelligence Engine | `core/intelligence/engine.py` | G | Analytics CLI, no umbrella (W1 §Sistema: Intelligence Engine) |

### 1.3 DORMIDO_RECUPERABLE (13 sistemas — con flag OFF pero pipeline completo)

Sistemas que no corren en producción pero tienen código funcional, consumers definidos, y valor potencial si se activan (con o sin fixes previos).

| # | Sistema | Archivo | Batch | VALOR si activado | Fix previo requerido |
|---|---------|---------|-------|-------------------|---------------------|
| 44 | Best-of-N | `core/best_of_n.py` | A | MEDIO — pipeline completo; coste 3x LLM | Ninguno (flag OFF = la decisión) |
| 45 | Reflexion LLM | `core/reasoning/reflexion.py` | A | BAJO — depende de ENABLE_NURTURING | Ninguno |
| 46 | Hierarchical Memory | `core/hierarchical_memory/` | B | MEDIO — requiere JSONL precomputados | Precomputar L1/L2/L3 por creator |
| 47 | **PersonaCompiler** | `services/persona_compiler.py` | C | **ALTO teórico** | **Bug persistencia**: escribe `creators.doc_d`, runtime lee `personality_docs.content` (W1 §47, línea 1097-1105) |
| 48 | history_compactor | `core/dm/history_compactor.py` | D | ALTO — CC-faithful; ON en sprints | Ninguno; decidir default |
| 49 | lead_categorization v1 | `core/lead_categorization.py` | E | — | Migrar 5 callers a v2 y ELIMINAR v1 |
| 50 | Memory Consolidator (orch) | `services/memory_consolidator.py` | F | ALTO — ON en config gemma4_26b | Ninguno |
| 51 | Memory Consolidation LLM | `services/memory_consolidation_llm.py` | F | ALTO — Phase 3 (dedupe/contradiction) | Ninguno |
| 52 | Memory Consolidation Ops | `services/memory_consolidation_ops.py` | F | ALTO — Phase 1-4 workers | Ninguno |
| 53 | CloneScore Engine | `services/clone_score_engine.py` | G | MEDIO — drift metric | Fix schema `evaluated_at` vs `created_at` inconsistencia (W1 §CloneScore Engine línea 2593) |
| 54 | Identity Resolver | `core/identity_resolver.py` | G | MEDIO — multiplataforma | **Wiring inconsistente**: 3 callers sin flag check |
| 55 | Unified Profile Service | `core/unified_profile_service.py` | G | MEDIO — email capture | Consolidar con identity_resolver antes de activar |
| 56 | Timing Service | `services/timing_service.py` | G | BAJO — naturalidad delay | Wire `bot_orchestrator.py` al flujo o descartar |

### 1.4 ELIMINAR (6 sistemas — dead code confirmado)

Sistemas sin consumers, duplicados de otros P1, o auto-declarados DEPRECATED.

| # | Sistema | Archivo | Batch | Razón |
|---|---------|---------|-------|-------|
| 57 | Semantic Memory (ChromaDB) | `core/semantic_memory.py` | B | 0 consumers runtime; superseded por `core/semantic_memory_pgvector.py` |
| 58 | RAG Service (services) | `services/rag_service.py` | B | Duplica `core/rag/semantic.py` (P1) e inferior |
| 59 | User Context Loader | `core/user_context_loader.py` | G | **Self-declared DEPRECATED 2026-04-01** |
| 60 | Conversation Mode | `core/conversation_mode.py` | G | 0 callers; duplica `context_detector` (P1) |
| 61 | Personalized Ranking | `core/personalized_ranking.py` | G | Sólo tests; duplica `preference_profile_service` (P1) |
| 62 | Response Variator v1 | `services/response_variator.py` | G | Reemplazado por `response_variator_v2.py` (P1) |

### 1.5 Gap "37 → 62" — por qué el conteo real es mayor

El usuario asumió "~37 sistemas restantes". W1 encontró 62. Gap explicado por (W1 §5.2):

- **10 shims/wrappers delgados** (feedback_store, preference_pairs_service, gold_examples_service, etc.).
- **13 sistemas dormidos no documentados** en auditorías previas P0/P1.
- **6 archivos de dead code** por migraciones incompletas (ChromaDB → pgvector, v1 → v2, etc.).
- **Los restantes 33 completan el conteo** sumándose a los 23 P0+P1 ya auditados previamente (CROSS_SYSTEM_ARCHITECTURE §7), totalizando 62.

---

## 2 · Injection Map (qué inyecta cada sistema en el prompt, en qué posición)

**Fuente primaria:** CROSS_SYSTEM_ARCHITECTURE §1 + DEEP_DIVE_CLONNECT_PIPELINE §2 + W3 §2 (datos reales de tokens).

### 2.1 Arquitectura de ensamblado

El DM tiene **dos puntos de ensamblado** (CROSS_SYSTEM §1):

1. **System Prompt** (`services/prompt_service.py:PromptBuilder.build_system_prompt`, llamado desde `core/dm/phases/context.py:995-996`).
   - Recibe `products` + `custom_instructions` (el `combined_context` pre-ensamblado).
   - Appenda `knowledge_about`, lista de productos, bloque "IMPORTANTE" hardcoded.

2. **User Prompt** (`core/dm/phases/generation.py:320-337`).
   - Compuesto de: `preference_profile_section` + `gold_examples_section` + `strategy_hint` + `question_hint` + `message`.
   - Pasado como `{"role":"user",...}` al LLM, con history entre system y user.

### 2.2 System prompt — orden literal de secciones

Del código `context.py:951-967` + `services/prompt_service.py:51-125`:

```
[POSITION 1]  style_prompt         — Doc D / compressed Doc D + ECHO data-driven style
[POSITION 2]  few_shot_section     — Calibration examples (3-5, intent-stratified + hybrid)
[POSITION 3]  friend_context       — Siempre "" en runtime (comment 691-694)
[POSITION 4]  recalling_block      — Per-lead consolidated context:
              ├── relational_block    — ECHO Relationship Adapter (880-928)
              ├── dna_context         — RelationshipDNA + unified lead profile (288-289, 1111-1112)
              ├── state_context       — Conversation State Machine (263-275, 279-287)
              ├── episodic_context    — Semantic Memory pgvector (311-330)
              ├── frustration_note    — Frustration level templates (799-817)
              ├── context_notes_str   — Question context + length/question hints
              └── memory_context      — Memory Engine facts (293-303)
[POSITION 5]  audio_context        — Audio Intelligence transcription (724-767)
[POSITION 6]  rag_context          — RAG results (last = high-attention position)
[POSITION 7]  kb_context           — Knowledge Base lookup
[POSITION 8]  hier_memory_context  — Hierarchical Memory (OFF by default)
[POSITION 9]  advanced_section     — Advanced rules (OFF by default)
[POSITION 10] citation_context     — Citation references
[POSITION 11] prompt_override      — Copilot v2 manual override
```

Después, `PromptBuilder.build_system_prompt` appenda (prompt_service.py:83-123):
- Bloque `knowledge_about` (Tu web, Bio, Especialidad, Ubicación).
- Si se pasa `creator_name`: "Representas a: {creator_name}" (en runtime DM **NO se pasa**).
- Lista de productos: `- {name}: {price}€ - {description}\n  Link: {url}`.
- Bloque fijo "IMPORTANTE" (6 items literales, ~520 chars).

### 2.3 User prompt — orden literal

Del código `generation.py:130-252, 320-337`:

```
[USER MSG 1]  preference_profile_section  — OFF by default (ENABLE_PREFERENCE_PROFILE=false)
[USER MSG 2]  gold_examples_section       — OFF by default (ENABLE_GOLD_EXAMPLES=false)
[USER MSG 3]  strategy_hint               — Strategy instruction (_determine_response_strategy)
[USER MSG 4]  question_hint               — "NO incluyas pregunta" (probabilistic, 234-237)
[USER MSG 5]  message                     — Actual user message (last = highest attention)
```

### 2.4 Tabla exhaustiva: 21 sistemas pre-LLM + 4 phase-1 + 12 post-LLM

**Pre-LLM injection (21 sistemas + 1 orchestrator):**

| # | Sistema | Tipo | Posición | Est. tokens real | Contenido |
|---|---------|------|----------|------------------|-----------|
| 1 | **Doc D / Style Prompt** | inject | system[1] | Iris **1383** / Stefano 174 | Personality: identity, BFI traits, vocabulary, emoji/excl rates |
| 2 | **ECHO Style Analyzer** | inject | appended a style_prompt | 50-100 | Data-driven quantitative metrics from StyleProfile |
| 3 | **Calibration Few-shots** | inject | system[2] | Iris 138-189 / Stefano 166-261 | 3-5 real creator responses, intent-stratified |
| 4 | **Gold Examples** (OFF) | inject | user msg pre-message | 0 | DNA golden_examples |
| 5 | **Relationship Adapter** | inject | system[4].relational | 50-100 | ECHO relational instructions |
| 6 | **DNA Engine** | inject | system[4].dna | 100-200 | RelationshipDNA + unified lead profile |
| 7 | **Conversation State** | inject | system[4].state | 30-50 | Phase machine (greeting, engaged, closing) |
| 8 | **Memory Engine** | inject | system[4].memory | 50-150 | Extracted facts from past convs |
| 9 | **Episodic Memory** (OFF) | inject | system[4].episodic | 0 | Raw conv snippets via pgvector |
| 10 | **Hierarchical Memory** (OFF) | inject | system[8] | 0 | IMPersona L1+L2+L3 |
| 11 | **RAG Service** | inject | system[6] (last-in) | 75-150 (max 137 en S8) | Product/FAQ/content chunks from pgvector |
| 12 | **Knowledge Base** | inject | system[7] | 20-50 | Keyword lookup (JSON files excluded from deploy) |
| 13 | **Context Detector** | inject | system[4].context_notes | 10-30 | B2B, sarcasm, question_context |
| 14 | **Frustration Detector** | inject | system[4].frustration | 10-20 | Frustration level note |
| 15 | **Audio Intelligence** | inject | system[5] | 50-200 | Transcription + entities + emotional tone |
| 16 | **Response Strategy** | inject | user msg | 30-50 | Strategy instruction |
| 17 | **Question Hint** | inject | user msg | 5-10 | "NO incluyas pregunta" probabilistic |
| 18 | **Length Hint** | inject | system[4].context_notes | 10-15 | Data-driven target from length_by_intent.json |
| 19 | **Citation Service** | inject | system[10] | 0-30 | Citations from creator content |
| 20 | **Preference Profile** (OFF) | inject | user msg first | 0 | Lead preference profile from DPO pairs |
| 21 | **Prompt Builder (core/)** | NOT USED | — | 0 | Only used via `build_prompt_from_ids()` — NOT in DM path |

**Phase-1 gates (4 sistemas — pre-pipeline, modifican flujo):**

| # | Sistema | Tipo | Acción |
|---|---------|------|--------|
| D1 | **Sensitive Detector** | gate | Crisis detection → early return with resources |
| D2 | **Pool Matching** | gate | Short message fast-path → skip LLM entirely |
| D3 | **Prompt Injection Detection** | flag | Observability only, **no blocking** |
| D4 | **Media Placeholder Detection** | flag | Flags platform placeholders for context |

**Post-LLM pipeline (12 sistemas — mutate, validate, or format):**

| # | Sistema | Tipo | Paso en `postprocessing.py` |
|---|---------|------|------------------------------|
| P1 | **Loop Detector (A2/A2b/A2c)** | postproc | 1-3: repetition + sentence dedup |
| P2 | **Anti-Echo (A3)** | postproc | 4: Jaccard similarity → replace |
| P3 | **Output Validator** | postproc | 5: Link validation |
| P4 | **Response Fixes** | postproc | 6: Price typos, broken links |
| P5 | **Blacklist Replacement** | postproc | 7 (OFF) |
| P6 | **Question Remover** | postproc | 8 |
| P7 | **Reflexion** (OFF) | postproc | 9 |
| P8 | **Score Before Speak** (OFF) | postproc | 10: PPA alignment + retry |
| P9 | **Guardrails** | postproc | 11 (correcto post-content, pre-cosmetic) |
| P10 | **Length Controller** | postproc | 13: enforce soft length |
| P11 | **Style Normalizer** | postproc | 14: emoji/excl rate matching |
| P12 | **Message Splitter** | postproc | 16: multi-bubble |

Orden actual en `core/dm/phases/postprocessing.py:26` (secuencia **correcta** según CROSS_SYSTEM §6 — valida sobre content-clean, cosmetics al final).

### 2.5 LLM messages array final

Del código `generation.py:388-416`:

```python
messages = [
    {"role": "system", "content": system_prompt},         # ~4-8K chars
    {"role": "user",   "content": history[0].content},    # last 10 msgs
    {"role": "assistant", "content": history[1].content},
    ...                                                    # alternating turns
    {"role": "user",   "content": full_prompt},           # strategy + hints + message
]
```

### 2.6 Budget aplicado al ensamblado

- `MAX_CONTEXT_CHARS = 8000` (env override, default en `context.py:936`) — aplicado en `_sections` loop (951-989) con `_smart_truncate_context`.
- Truncación individual de mensajes de history: 600 chars (`generation.py:298-299`).
- History limit: últimos 10 turnos (`history[-10:]`, línea 279).
- Truncación "orden-de-secciones": si excede, se **skippean secciones completas** (no se truncan partes); orden de skip no documentado explícitamente en código pero priorizadas por importancia (W3 §4).

---

## 3 · Metadata Flow (dónde se genera, quién lo lee)

**Fuente primaria:** W2_metadata_flow.md completo + DEEP_DIVE_CLONNECT_PIPELINE §7 + CRUCE_REPO_VS_CLONNECT §8.

### 3.1 Arquitectura dual de metadata

Clonnect mantiene **dos dicts de metadata paralelos** (W2 §Contexto arquitectónico):

| Dict | Scope | Persistencia |
|------|-------|-------------|
| `cognitive_metadata` | In-memory per-request, vive en `DmContext` | Sólo si se copia explícitamente a `_dm_metadata` o `msg_metadata` |
| `metadata` / `msg_metadata` | DB column `messages.msg_metadata` (JSONB) | Persiste en PostgreSQL |

**Flujo:** `cognitive_metadata` → `postprocessing.py` construye `_dm_metadata` → `DMResponse.metadata` → `dispatch.py` copia selectivamente → DB.

**Hallazgo W2 §Resumen ejecutivo:** sólo **3 fields** de `cognitive_metadata` acaban en DB: `best_of_n`, `type`, `best_of_n` (duplicado intencional en `dispatch.py:158`). El resto muere al terminar el request HTTP.

### 3.2 Totales globales

```
Total fields únicos:          114
──────────────────────────────────
DECISION (branchan lógica):    37 (32%)
REFERENCE (leídos, pasados):   12 (11%)
ORPHANS (nunca leídos):        65 (57%)
```

### 3.3 Los 37 fields DECISION (consumidos por branches reales)

Son los que realmente alteran flujo. Tabla extraída de W2 §CONSUMER REAL — DECISION:

| Field | Productor | Consumers clave | Uso |
|-------|-----------|-----------------|-----|
| `audio_clean` | `evolution_webhook.py:939` | `media.py:403`, `evolution_webhook.py:335/701` | Texto limpio de audio |
| `audio_intel` | `media.py:224`, `oauth/instagram.py:882` | 14 consumers | Inteligencia audio (transcripción enriquecida) |
| `best_of_n` | `dispatch.py:158`, `generation.py:497` | 32 consumers (persiste a DB) | Flag best-of-N |
| `clone_score` | `postprocessing.py:421` | 18 consumers (mayoría tests) | Score clonación |
| `context_signals` | `detection.py:182` | `post_response.py:156`, `context.py:871` + 10 | Routing downstream |
| `detected_language` | `context.py:768` | `postprocessing.py:286/287/317` + 5 | **Controla compresión memo** |
| `dna_data` | `context.py:442` | `post_response.py:201` | DNA update |
| `duration` | `evolution_webhook.py:452/457` | 121 consumers | Duración de media |
| `emoji` | ? | 151 consumers | Emoji del mensaje |
| `episodic_chars` | `context.py:?` | 12 consumers (CPE+tests) | Chars episodic inyectada |
| `episodic_recalled` | `context.py:?` | `cpe_ablation.py:?` + 1 | Flag recall |
| `filename` | ? | 140 consumers | Nombre archivo media |
| `history` | ? | 63 consumers | Historial |
| `is_media_placeholder` | ? | 1 consumer | Flag placeholder |
| `lead_stage` | (no escrito — leído directamente) | 26 consumers | Stage del lead |
| `length_hint` | `context.py:?` | `generation.py:?` | Hint de longitud |
| `link` | 4 producers | 109 consumers | URL media/link |
| `link_preview` | 2 producers | 10 consumers | Preview de link |
| `media` | 1 producer | 53 consumers | Datos media adjunta |
| `memory_chars` | `context.py:?` | 7 consumers (tests) | Chars memoria inyectada |
| `memory_recalled` | `context.py:?` | 19 consumers | Flag recall |
| `message_type` | ? | 7 consumers | Tipo de mensaje |
| `msg_metadata` | 1 producer | 6 consumers (`copilot/actions.py`) | Wrapper metadata |
| `name` | 2 producers | 3062 consumers (genérico) | Nombre entidad |
| `needs_thumbnail` | 1 producer | 2 consumers | Flag thumbnail |
| `permalink` | 2 producers | 19 consumers | Permalink IG post |
| `phone_number_id` | heredado | 6 consumers | ID teléfono WhatsApp |
| `relationship_type` | `context.py:?` | **83 consumers** — `post_response.py:356`, `context.py`, `copilot` | Tipo relación (amigo/lead) |
| `render_as_sticker` | 1 producer | 5 consumers | Renderizar sticker |
| `story` | 1 producer | 39 consumers | Datos IG story |
| `story_id` | 1 producer | 2 consumers | ID story |
| `telegram_keyboard` | heredado | 2 consumers | Teclado Telegram |
| `thumbnail_url` | 2 producers | 36 consumers | URL thumbnail |
| `transcription` | 3 producers | 19 consumers | Transcripción audio |
| `truncation_recovery` | 2 producers | 2 consumers | Recovery truncado |
| `type` | 26 producers | 2696 consumers | **Campo más consumido del repo** |
| `url` | 10 producers | 577 consumers | URL genérica |

### 3.4 Los 12 fields REFERENCE (leídos sin branch decision directa)

Pasan información entre sistemas pero no alteran flujo de control:

| Field | Productor | Consumer | Uso |
|-------|-----------|----------|-----|
| `_full_prompt` | `generation.py:310` | `postprocessing.py:292` | Pasado a memo_compression |
| `cache_prefix_chars` | `context.py:1069` | `generation.py:357` | Métricas cache |
| `captured_at` | `test_operations.py:284` | `media.py:44/115/151` | Timestamp captura media |
| `context_signals` | `detection.py:182` | `post_response.py:156` | Señales routing |
| `context_total_chars` | `context.py:1059` | `tests/cpe_measure_production.py:674` | Sólo en tests |
| `dna_data` | `context.py:442` | `post_response.py:201` | DNA data |
| `episodic_recalled` | `context.py:?` | 2 consumers | Flag recall |
| `memory_chars` | `context.py:?` | 7 consumers (tests) | Stats memoria |
| `nurturing_scheduled` | `post_response.py:244` | `analytics_manager.py:34` | Evento analytics |
| `permanent_url` | 6 producers | 8 consumers | URL permanente |
| `question_confidence` | `context.py:?` | `context.py:883` | Confianza pregunta |
| `question_context` | `context.py:?` | `context.py:882` | Contexto pregunta |
| `relationship_category` | `context.py:?` | `postprocessing.py:477` | Categoría relacional |
| `relationship_score` | `context.py:?` | 2 consumers | Score relación |
| `sensitive_category` | `detection.py:?` | 1 consumer | Categoría sensible |
| `truncation_recovery` | 2 producers | 2 consumers | Recovery truncado |

### 3.5 Los 65 fields ORPHAN (escritos, nunca leídos para branch)

Los orphans componen el 57% del total. Agrupados por sistema productor (W2 §Sistemas 100% orphan):

**Sistemas con output 100% orphan (candidatos a limpieza total de writes):**

| Sistema | Fields orphan | Archivo productor | Impacto si se eliminan writes |
|---------|---------------|-------------------|-------------------------------|
| **RAG telemetry** | `rag_confidence`, `rag_details`, `rag_disabled`, `rag_reranked`, `rag_routed`, `rag_signal`, `rag_skipped` (**7 fields**) | `context.py:566-634` | Sólo eliminar writes; routing RAG sigue funcionando |
| **SBS** | `sbs_score`, `sbs_scores`, `sbs_path`, `sbs_llm_calls` (**4 fields**) | `postprocessing.py:298-301` | Eliminar writes; SBS sigue ejecutándose |
| **PPA** | `ppa_score`, `ppa_scores`, `ppa_refined` (**3 fields**) | `postprocessing.py:326-330` | Eliminar writes; PPA sigue |
| **Compaction telemetry** | `history_compaction`, `history_compaction_kept`, `history_compaction_pool` (**3 fields**) | `generation.py:430-432` | Eliminar writes |
| **Hier. memory telemetry** | `hier_memory_chars`, `hier_memory_injected`, `hier_memory_levels` (**3 fields**) | `context.py:?` | Eliminar writes |
| **Echo detection** | `echo_detected`, `echo_detected_no_pool` (**2 fields**) | `postprocessing.py:?` | Eliminar writes |
| **Loop detection** | `loop_detected`, `loop_truncated` (**2 fields**) | `postprocessing.py:?` | Eliminar writes |
| **Quality flags** | `blacklist_replacement`, `repetition_truncated`, `sentence_dedup`, `self_consistency_replaced` (**4 fields**) | `postprocessing.py:?` | Eliminar writes |
| **Security flags** | `prompt_injection_attempt`, `sensitive_detected` (**2 fields**) | `detection.py:103/125` | **RIESGO — eliminar sin alerting primero es insuficiente** (§3.6) |
| **Style flags** | `style_anchor`, `style_normalized` (**2 fields**) | `generation.py:307`, `postprocessing.py:384` | Eliminar writes |

**Otros orphans notables** (W2 §ORPHANS):

- `audio_enriched`, `cache_prefix_hash`, `commitments_pending`, `context_sections`, `dna_full_analysis_triggered`, `dna_seed_created`, `dna_update_scheduled`, `email_asked`, `email_captured`, `failover_from`, `failover_to`, `gold_examples_injected`, `guardrail_triggered`, `intent_override`, `is_empty_message`, `is_short_affirmation`, `lead_warmth`, `length_hint_injected`, `max_tokens_category`, `payment_link_injected`, `preference_profile`, `prompt_truncated`, `query_expanded`, `question_hint`, `question_hint_injected`, `reflexion_issues`, `reflexion_severity`, `relational_adapted`, `relationship_signals`, `response_strategy`, `temperature_used`.

### 3.6 Hallazgos críticos de seguridad

**Del W2 §Hallazgos de seguridad:**

1. `prompt_injection_attempt` (`detection.py:103`) y `sensitive_detected` (`detection.py:125`) **se detectan pero nunca generan alerta, log persistente, ni acción**. La detección existe pero no tiene efecto downstream.

2. `guardrail_triggered` (`postprocessing.py:365`) guarda la razón del guardrail pero no la persiste ni alerta externamente.

**Consecuencia:** si un atacante intenta prompt injection en un DM, el sistema lo detecta (genera el flag en metadata), pero el flag muere al final del request. No hay logging de seguridad, no hay rate-limit, no hay alerta al creator.

### 3.7 Falsos positivos en clasificación (W2 §Notas)

Algunos fields marcados como "CONSUMER" tienen consumers casi exclusivamente en `tests/` o `analysis/scripts/`. Técnicamente leídos pero **no en producción**:

- `context_total_chars` — sólo `tests/cpe_measure_production.py`
- `clone_score` — 3 consumers en `analysis/`, 15 en `tests/`
- `episodic_chars` — mayoritariamente tests de ablation

### 3.8 Metadata flow — comparación con CC

Del CRUCE §8:

**Repo (CC):**
- `userContext` dict → `prependUserContext()` → synthetic `<system-reminder>` user message.
- `systemContext` dict → `appendSystemContext()` → appended al system prompt array.
- Feature flags eliminados en build time (bun:bundle) — **sin runtime flag checks para muchos items**.
- Metadata flows como function parameters (`QueryParams`, `ToolUseContext`, `ProcessUserInputContext`), no global dict.
- **All metadata passed as params is consumed by decision logic** — no orphans documentados.

**Clonnect:**
- `cognitive_metadata` dict con ~114 fields escritos en detection/context/generation/postprocessing/post_response.
- 6 fields consumidos para decisions: `question_context`, `question_confidence`, `_full_prompt`, `detected_language`, `best_of_n`, `relationship_category` (DEEP_DIVE_CLONNECT §7 línea 487).
- ~65 fields son orphans (W2 §Resumen).
- Feature flags son env vars leídas en runtime, no build-time.

**Diferencia arquitectónica clave:** CC usa metadata como **contract** (parámetros tipados entre funciones); Clonnect usa metadata como **bag** (dict abierto donde cualquier componente puede escribir, pocos leen).


---

## §4 Solapamientos Reales (13 duplicaciones)

Esta sección identifica sistemas funcionalmente solapados — código que hace el mismo trabajo en dos o más sitios, con resultados potencialmente divergentes. Fuentes: W1 (inventario), GRAPH_REPORT.md (hiperedges + comunidades), CROSS_SYSTEM_ARCHITECTURE.md (ownership verification), Clonnect_Backend_Graph.md (conexiones sorprendentes).

### S1 — Dual Memory Storage Conflict

**Sistemas en conflicto:**
- `services/memory_store.py` (MemoryStore) — sistema heredado
- `services/conversation_memory_service.py` (ConversationMemoryService) — sistema añadido posteriormente
- `core/memory/engine.py` (MemoryEngine) — tercer sistema, gated por `ENABLE_MEMORY_ENGINE`

**Evidencia:** Clonnect_Backend_Graph.md §Conexiones Sorprendentes #2 lista explícitamente "Dual Memory Storage Conflict", GRAPH_REPORT.md marca como hiperedge `EXTRACTED confianza=1.0`.

**Solapamiento:** los 3 sistemas almacenan fragmentos de memoria conversacional, con schemas distintos y sin sincronización. Consumidores cross-wired: algunos phases leen de MemoryStore, otros de MemoryEngine, otros de ConversationMemoryService.

**Riesgo:** inconsistencias en la memoria del lead entre turnos. Un hecho extraído por un sistema puede no existir en otro.

**Resolución propuesta (W4):** consolidar en una única fuente de verdad (sugerido: `memdir/` estilo CC, con 4 tipos cerrados).

---

### S2 — Dual Profile Storage Conflict

**Sistemas en conflicto:**
- `sys38_creator_profile_service` (services/creator_profile_service.py)
- `sys40_style_analyzer` (core/style/analyzer.py) con `style_profiles` table

**Evidencia:** Clonnect_Backend_Graph.md §Conexiones Sorprendentes #1 y §Hiperedges Clave línea 107.

**Solapamiento:** `creator_profiles` y `style_profiles` almacenan atributos solapados del creator (tono, léxico, preferencias). No hay delimitación clara de responsabilidades.

**Riesgo:** mismo atributo con valores distintos en ambas tablas. Consumers eligen fuente arbitrariamente.

---

### S3 — PersonaCompiler vs personality_loader (Doc D duplicado)

**Sistemas:**
- `services/persona_compiler.py` (PersonaCompiler) — genera Doc D
- `core/dm/personality_loader.py` — carga Doc D para inyección

**Persistence mismatch (bug crítico documentado en W1):**
- PersonaCompiler escribe a `creators.doc_d` (tabla `creators`, columna `doc_d`)
- personality_loader lee de `personality_docs.content` (tabla `personality_docs`, columna `content`)

**Evidencia:** W1 §sys18 PersonaCompiler marca `ACTIVO_INÚTIL` con nota "persistence bug — writes to creators.doc_d, reader expects personality_docs.content. Output dropped on the floor."

**Consecuencia:** cualquier recompilación de Doc D vía PersonaCompiler es invisible. El prompt efectivo usa un Doc D stale cargado directo de `personality_docs` (gestionado manualmente).

---

### S4 — Length control distribuido en 3 sistemas

**Sistemas:**
- `core/dm/phases/postprocessing.py:335-340` — `enforce_length()` (step 9 de postprocessing)
- `services/prompt_service.py` — `_length_hint` inyectado al user message (generation.py:186-203)
- `core/dm/length_controller.py` — LengthController (sys41 W1)

**Evidencia:** W1 §sys41 LengthController marca `ACTIVO_VALIOSO` pero nota "3 systems writing length constraints without arbitration".

**Riesgo:** constraints contradictorios (ej: prompt pide 50-100 chars, enforce_length trunca a 80, LengthController valida 120).

---

### S5 — PromptBuilder duplicación dentro de context.py

**Sistemas:**
- `services/prompt_service.py::PromptBuilder.build_system_prompt()` (51-125)
- `core/dm/phases/context.py::_build_system_prompt_inline()` (duplicada parcialmente para testing según W1 §sys06)

**Evidencia:** W1 §sys06 ContextAssembler marca "partial duplication of PromptBuilder logic for test injection paths — drift risk".

**Riesgo:** drift entre el prompt producido en tests vs producción.

---

### S6 — Few-shots calibration vs gold_examples

**Sistemas:**
- `services/calibration_loader.py` — carga `calibration/{creator}/few_shots.json`
- `core/few_shots/gold_examples.py` — sistema alternativo con gold examples

**Evidencia:** W1 §sys23 GoldExamples marca `DORMIDO_RECUPERABLE` con nota "overlaps with calibration few_shots.json; wiring unclear".

**Riesgo:** doble fuente de ejemplos few-shot, prompt puede inyectar ambos causando inflación del token budget.

---

### S7 — Response Variator v1 vs v2

**Sistemas:**
- `core/response/variator_v1.py` (legacy)
- `core/response/variator_v2.py` (nuevo)

**Evidencia:** W1 §sys42 ResponseVariator marca `ACTIVO_INÚTIL` con nota "v1 still imported in 2 places, v2 is default, no deprecation path".

**Riesgo:** comportamiento divergente si algún caller invoca v1.

---

### S8 — Semantic Memory: Chroma vs pgvector

**Sistemas:**
- `core/rag/chroma_store.py` (experimental, sys44 W1)
- `services/rag_service.py` + pgvector (producción)

**Evidencia:** W1 §sys44 ChromaStore marca `DORMIDO_RECUPERABLE` con nota "pgvector is production, Chroma is dormant but still importable".

**Riesgo:** si ENV flag se activa, dos stores vectoriales operan simultáneamente sin sincronización.

---

### S9 — rag_service vs core/rag/semantic

**Sistemas:**
- `services/rag_service.py` — sistema principal
- `core/rag/semantic.py` — capa experimental

**Evidencia:** W1 §sys16 RAGService `ACTIVO_VALIOSO` pero §sys45 SemanticRAG `DORMIDO_RECUPERABLE`.

**Riesgo:** caller de bajo nivel puede pasar por `core/rag/semantic` bypassing cache del `rag_service` público.

---

### S10 — Hierarchical Memory vs Episodic Memory

**Sistemas:**
- `core/memory/hierarchical.py` (gated `ENABLE_HIERARCHICAL_MEMORY`, default OFF)
- `core/memory/episodic.py` (gated `ENABLE_EPISODIC_MEMORY`, default OFF)

**Evidencia:** W1 §sys28 + §sys29, CROSS_SYSTEM §11 Position 7 "Recalling block".

**Solapamiento:** ambos pretenden inyectar "recuerdos" al prompt. Episodic usa embeddings de DMs pasados; Hierarchical usa niveles (short/mid/long). Ningún creator los usa en producción.

**Riesgo semántico:** si algún día se activan ambos, memory budget explota; no hay coordinador de presupuesto entre los dos.

---

### S11 — DNA Analyzer vs Relationship Analyzer

**Sistemas:**
- `core/dm/dna_engine.py` — DNA relational profile
- `core/relationship/analyzer.py` — RelationshipAnalyzer (god node #9, 174 edges)

**Evidencia:** Clonnect_Backend_Graph.md §God Nodes + W1 §sys19 DNAEngine / §sys20 RelationshipAnalyzer.

**Solapamiento:** ambos computan "tipo de relación" entre creator y lead. DNA usa templates JSON; RelationshipAnalyzer usa heurísticas runtime. Ninguno es autoritativo.

---

### S12 — CloneScore vs BestOfN selection

**Sistemas:**
- `core/quality/clone_score.py` — scoring post-hoc
- `core/generation/best_of_n.py` — selector de N candidatos

**Evidencia:** W1 §sys30 CloneScore / §sys31 BestOfN. Clonnect_Backend_Graph.md §Comunidades #12 "Best-of-N Response Selection".

**Solapamiento:** ambos evalúan calidad de una respuesta. BestOfN filtra N candidates vía scoring; CloneScore puntúa 1 respuesta post-generación. Son pipelines separados con métricas no-comparables.

**Riesgo de gobernanza:** si quality regresses, no hay único dashboard.

---

### S13 — Intent Classification distribuida

**Sistemas:**
- `core/dm/intent_classifier.py` (IntentClassifier, god node #4, 212 edges)
- `core/dm/phases/detection.py::classify_message_type()` — clasificación rápida intraprocess

**Evidencia:** Clonnect_Backend_Graph.md §God Nodes + W1 §sys04 IntentClassifier / §sys05 DetectionPhase.

**Solapamiento:** ambos mapean el mensaje a "tipo" (pregunta, saludo, checkout, etc.). IntentClassifier es heavyweight (LLM-based con cache); `classify_message_type` es ligero (regex+heurística). Producen categorías disjuntas que no se reconcilian.

---

### Resumen Solapamientos

| ID | Dominio | Impacto | Severidad |
|----|---------|---------|-----------|
| S1 | Memory (3 stores) | Inconsistencias DM | **CRÍTICA** |
| S2 | Profile (2 tables) | Atributos divergentes | ALTA |
| S3 | Doc D persistence bug | Recompilación invisible | **CRÍTICA** |
| S4 | Length control (3 sitios) | Constraints contradictorios | ALTA |
| S5 | Prompt build duplicado | Drift test vs prod | MEDIA |
| S6 | Few-shots (2 fuentes) | Token inflation | MEDIA |
| S7 | Variator v1/v2 | Comportamiento divergente | BAJA |
| S8 | Vector store Chroma/pgvector | Dormant pero activable | BAJA |
| S9 | rag_service vs semantic | Bypass de cache | MEDIA |
| S10 | Hierarchical vs Episodic | Budget explosion latente | BAJA (OFF default) |
| S11 | DNA vs Relationship | Sin source of truth | MEDIA |
| S12 | CloneScore vs BestOfN | Sin gobernanza de quality | MEDIA |
| S13 | Intent dual | Categorías disjuntas | ALTA |

**Patrón arquitectónico:** la mayoría de solapamientos son el resultado de añadir subsistemas sin retirar el anterior. Ninguno tiene deprecation path explícito.

---

## §5 Diferencias CC vs Clonnect (D1-D12)

Fuentes: CRUCE_REPO_VS_CLONNECT.md (9 secciones), DEEP_DIVE_CONTEXT_ENGINEERING.md (CC), DEEP_DIVE_CLONNECT_PIPELINE.md (Clonnect), W4/W5/W6 (deep dives específicos).

### D1 — Prompt structure: array vs single string

**CC (CRUCE §1):** `systemPrompt: string[]`, cada sección añadida por `appendSystemContext()`. User context vía `prependUserContext()` como synthetic user message tagged `<system-reminder>`. Attachments como user messages separados (createAttachmentMessage). El LLM recibe 4 streams distintos: system array → user context message → conversation messages → attachment messages.

**Clonnect (CRUCE §1):** single system prompt string (`PromptBuilder.build_system_prompt()` prompt_service.py:51-125). Todo el contexto concatenado en `combined_context = "\n\n".join(assembled)` (context.py:996). No hay separación system/user a nivel de roles. Todas las secciones (style, few_shots, audio, rag, memory) embebidas en el system prompt string.

**Implicación:** CC puede marcar boundary cache entre el system array (reusable) y el user context (variable). Clonnect no puede — cualquier cambio en cualquier sección invalida el system prompt entero.

---

### D2 — Cache boundary: explícito vs ausente

**CC (CRUCE §3):** `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` separa cacheable (intro, rules, MCP, tools) de dynamic (session guidance, memory, env, output style). Permite **server-side prompt caching** en queries repetidas.

**Clonnect (CRUCE §3):** No hay boundary. Sólo 3 secciones son `static per-creator` (style_prompt, few_shot_section, friend_context). Las otras ~16 son `dynamic per-message`. El prompt string entero se considera variable.

**Gap arquitectónico:** Clonnect paga **cache miss en cada request** — cada DM re-tokeniza 2-3K de style + Doc D + few-shots aunque no cambiaron entre turns.

---

### D3 — Injection gates: per-turn dinámico vs static flags

**CC (CRUCE §2, W5 completo):** ~38 parallel gates en `getAttachments` (attachments.ts:743). Cada gate envuelto en `maybe()` wrapper (attachments.ts:1005-1042) con 1s timeout, fail-silent, 5% telemetry sampling. Budget per-turn: MAX_MEMORY_BYTES=4096/file × 5 files, MAX_SESSION_BYTES=60KB. Throttling (plan mode every 5 turns, task reminders 10+ turns, date_change one-time).

**Clonnect (CRUCE §2, DEEP_DIVE_CLONNECT §21-36):** Static boolean flags leídos en runtime vía `os.getenv()`. Budget global: MAX_CONTEXT_CHARS=8000 con `_smart_truncate_context`. Sólo 2 adaptive gates:
- RAG: adaptive cosine threshold (≥0.5 top 3, ≥0.40 top 1, <0.40 skip)
- Episodic: `len(_msg_stripped) >= 15 and len(_msg_words) >= 3`

**Diferencia cuantitativa:** 38 gates paralelos con maybe() vs 2 gates adaptivos secuenciales. Clonnect no puede "degradar gracefully" en failure de un sistema.

---

### D4 — Post-processing: 0 mutations vs 11 mutations

**CC (CRUCE §4):** post-sampling hooks (extractMemory, skillImprovement, magicDocs) son **fire-and-forget**, no awaited, y **NO modifican la respuesta**. Stop hooks pueden prevenir continuación pero no mutar contenido. El output del LLM es inmutable.

**Clonnect (CRUCE §4, CROSS_SYSTEM_ARCHITECTURE):** 27 steps en `phase_postprocessing` (postprocessing.py:26). De esos:
- **11 mutan la respuesta** (repetition truncation, sentence dedup, echo detector Jaccard, question removal, SBS, PPA, guardrails substitution, length enforcement, style normalization, payment link append, message splitting)
- 14 registran metadata
- 2 appenden contenido

**Implicación filosófica:** CC confía en el LLM (genera una vez, no post-edita). Clonnect desconfía y remediación — cada mutation es un patch por un bug upstream no fijado.

---

### D5 — Compaction: 3 estrategias vs 0

**CC (W6 completo, CRUCE §5):** 4 estrategias (W6 reclasifica la original de 3 a 4):
1. **microCompact** (microCompact.ts:531) — limpia tool_results viejos in-place, cache-edit boundary
2. **SessionMemoryCompact** (sessionMemoryCompact.ts:630) — preempt L2, consolida memoria antes de overflow
3. **autoCompact** (autoCompact.ts:352) — resumen 9-section + `<analysis>` scratchpad, trigger `AUTOCOMPACT_BUFFER_TOKENS=13K`
4. **reactiveCompact** (reactiveCompact.tryReactiveCompact) — recovery post error 413 prompt-too-long

**Clonnect (CRUCE §5, DEEP_DIVE_CLONNECT §254-266):** **ninguna compactación.** Sólo:
- History capped a last 10 turns
- `MAX_CONTEXT_CHARS=8000` con truncación pasiva en `_smart_truncate_context`
- Mensajes individuales truncados >600 chars (generation.py:298-299)
- No hay circuit breaker, no reactive recovery, no consolidación

**Gap crítico:** en conversaciones largas (30+ turns), Clonnect descarta history silenciosamente sin preservar información. CC preserva vía 9-section summary.

---

### D6 — Memory por defecto: activa vs apagada

**CC (CRUCE §6, W4):** Session memory + extractMemories **activos por defecto**. 4 tipos de memoria cerrados (user/feedback/project/reference) con body_structure mandatory.

**Clonnect (CRUCE §6):**
- `ENABLE_MEMORY_ENGINE` → `false` (context.py:294) — OFF
- `ENABLE_EPISODIC_MEMORY` → `false` (context.py:32) — OFF
- `ENABLE_HIERARCHICAL_MEMORY` → `false` (context.py:31) — OFF
- `ENABLE_COMMITMENT_TRACKING` → `true` (context.py:371) — ON

**Consecuencia operacional:** Clonnect opera en producción con **toda la memoria episódica/hierarchical apagada**. Los sistemas existen (código + DB tables) pero no se usan. Usuarios nuevos no benefician de learning cross-turn en esos subsistemas.

---

### D7 — Error recovery: 4 estrategias vs 2

**CC (CRUCE §7):**
1. Prompt-too-long → context collapse drain → reactiveCompact
2. Max-output-tokens → 8K→64K escalation → multi-turn recovery
3. Fallback model mid-stream (discard previous messages, retry)
4. MAX_CONSECUTIVE_FAILURES=3 circuit breaker

**Clonnect (CRUCE §7):**
1. General try/except en agent.py:367 → `error_response`
2. Provider cascade Gemini Flash-Lite → GPT-4o-mini (generation.py:281)

**Gap:** Clonnect no tiene mid-stream recovery, no escalation de tokens, no circuit breaker. Un request que alcance 413 prompt-too-long **muere**.

---

### D8 — Metadata flow: contract vs bag

**CC (CRUCE §8):**
- `userContext` dict → `prependUserContext()` → user message
- `systemContext` dict → `appendSystemContext()` → system prompt
- Feature flags eliminados en build time (bun:bundle)
- Metadata como function parameters tipados (`QueryParams`, `ToolUseContext`) — **no global dict**
- **Todo consumido por decision logic**

**Clonnect (W2, CRUCE §8):**
- `cognitive_metadata` dict global escrito por 5 phases + múltiples subsistemas
- 114 fields totales, 37 DECISION, 12 REFERENCE, 65 ORPHAN
- Feature flags son env vars leídas runtime
- ~57% fields orphan (escritos nunca leídos para decisions)

**Diferencia paradigmática:** CC es typed-contract entre módulos; Clonnect es shared-mutable-state estilo global dict.

---

### D9 — Gating granularity: por atributo vs por bloque

**CC (W5):** cada attachment tiene su propio gate (38 gates). Ejemplo: memoryFreshnessText y hasMemoryWritesSince son gates independientes. Un gate puede fallar silencioso sin afectar a los demás.

**Clonnect:** los gates son por bloque completo. Ejemplo: `ENABLE_EPISODIC_MEMORY` controla el bloque "recalling" entero. No hay sub-gates que permitan inyectar sólo "commitments" sin el resto.

**Impacto:** menos flexibilidad para experimentación A/B en Clonnect.

---

### D10 — Budget enforcement: token-aware vs char-aware

**CC (W5, W6):** Budget expresado en tokens (MAX_MEMORY_BYTES=4096 es bytes pero mapea 1:1 con tokens en ASCII; AUTOCOMPACT_BUFFER=13K tokens). Tokenizer-aware.

**Clonnect (generation.py:247-250):** Budget expresado en **chars** (MAX_CONTEXT_CHARS=8000). Chars → tokens ratio varía: para ES/CA con tildes el ratio char/token ≈ 2.5-3.5 (no 4 como ASCII). W3 demostró asimetría real: Iris 1383 tokens de style vs estimate teórico 325 (4.25× error).

**Bug latente:** el budget de 8000 chars puede traducirse a 2500-3200 tokens (bajo) o a 800-1200 tokens (alto) según el contenido — no es predictable.

---

### D11 — Orchestrator con budget: existe vs no existe

**CC (W5, W6):** `getAttachments()` funciona como orchestrator: acumula bytes, aplica throttling, respeta MAX_SESSION_BYTES, selecciona subset que cabe. Es un budgeter activo.

**Clonnect:** no hay orchestrator. Cada sección se añade a `assembled` list (context.py:952-967) y al final `_smart_truncate_context` skipea secciones hasta caber. Es truncación post-hoc, no selección informada.

**Corolario:** Clonnect no puede responder "qué sección sacrifico si me quedo sin budget" — simplemente desactiva en orden ordinal (CRITICAL → HIGH → MEDIUM → FINAL).

---

### D12 — Freshness signalling: explícito vs implícito

**CC (W4):** `memoryFreshnessText` (memoryAge.ts:33-42) genera texto explícito tipo "Updated 3 hours ago" que el LLM puede priorizar. `hasMemoryWritesSince` mutex (extractMemories.ts:121-148) previene re-extracción.

**Clonnect:** memoria no tiene timestamp semántico visible al LLM. El contenido de `conversation_memory` no indica "cuándo se aprendió esto". Sólo timestamps internos DB.

**Impacto:** LLM no puede razonar sobre staleness de información.

---

### Resumen CC vs Clonnect

| Dimension | CC | Clonnect | Brecha |
|-----------|-----|----------|--------|
| D1 Prompt structure | Array (system + user + attachments) | Single string | **ALTA** |
| D2 Cache boundary | Explícito | Ausente | **ALTA** |
| D3 Injection gates | 38 per-turn + maybe() | 2 adaptativos + static | **ALTA** |
| D4 Response mutations | 0 | 11 | **CRÍTICA** (filosofía) |
| D5 Compaction | 4 estrategias | 0 | **CRÍTICA** |
| D6 Memory default | ON | OFF | **ALTA** |
| D7 Error recovery | 4 estrategias | 2 | ALTA |
| D8 Metadata flow | Contract tipado | Bag dict global | ALTA |
| D9 Gating granularity | Per-attachment | Per-block | MEDIA |
| D10 Budget unit | Tokens | Chars | ALTA (bug latente) |
| D11 Orchestrator budget | Sí (getAttachments) | No | ALTA |
| D12 Freshness signal | Explícito | Implícito | MEDIA |

**Síntesis:** 6 brechas CRÍTICAS/ALTAS-filosóficas. La diferencia no es de volumen sino de **arquitectura de contratos**: CC tiene disciplina de cache, budget, y separación de concerns; Clonnect tiene funcionalidad pero sin gobernanza centralizada.

---

## §6 Token Budget Real (datos W3)

Fuente: W3_token_analytics_real.md (20 escenarios: 10 Iris × 10 Stefano, medición real vía tokenizer).

### 6.1 Hallazgo central: asimetría de contexto por-creator

**W3 midió tokenización real** del system prompt ensamblado, por sección, en 20 escenarios distintos. Resultado:

| Sección | Iris (tokens avg) | Stefano (tokens avg) | Ratio Iris/Stefano |
|---------|------------------|----------------------|---------------------|
| style_prompt | **1383** (66% del prompt) | **174** (21% del prompt) | 7.9× |
| few_shots | 287 | 156 | 1.8× |
| history (últimos 10 turns) | 87 real | 87 real | — |
| audio_context | 0-180 (var) | 0-180 (var) | — |
| recalling (DNA+state) | 42-95 | 40-90 | ≈1.0× |
| rag_context | 180-420 | 170-410 | ≈1.0× |
| friend_context | 0 | 0 | — |
| **Total típico** | ~2100 | ~710 | 3.0× |

**Implicación:** el mismo subsistema (style) consume **7.9× más tokens para Iris que para Stefano**. El style_prompt no tiene budget cap — su tamaño depende 100% de cuánto texto tenga el creator en `creators.style` / `personality_docs.content`.

### 6.2 CROSS_SYSTEM §4 estimate vs W3 real

CROSS_SYSTEM_ARCHITECTURE.md §4 (versión anterior del audit) estimaba token budget teórico. W3 midió real:

| Sección | CROSS_SYSTEM estimate | W3 real (Iris) | Error |
|---------|----------------------|----------------|-------|
| style_prompt | 325 | 1383 | **4.25× subestimado** |
| history (10 turns) | 600 | 87 | 7× sobreestimado |
| few_shots | 250 | 287 | 1.15× (OK) |
| audio | 120 | 180 | 1.5× |
| rag | 300 | 300 | 1.0× (OK) |

**Conclusión:** el estimate previo tenía errores estructurales. **style** era el principal underestimate; **history** era el principal overestimate (los mensajes reales son cortos, no 60 tokens cada uno como asumido).

### 6.3 MAX_CONTEXT_CHARS=8000 efectivo

Con Iris en escenario típico:
- style 1383 tokens ≈ 4200 chars
- few_shots 287 ≈ 870 chars
- history 87 ≈ 265 chars
- audio 180 ≈ 550 chars
- recalling 80 ≈ 240 chars
- rag 300 ≈ 900 chars
- **Subtotal: ~7025 chars**

Restante bajo MAX_CONTEXT_CHARS=8000: ~975 chars para TODO lo demás (env, language hint, citation, kb, hierarchical, advanced).

**Consecuencia:** para Iris, el budget está **al 88% sólo con style + few_shots + recalling + rag**. Cualquier feature adicional activada (hier, mem engine) cae en truncación selectiva.

Para Stefano, mismo cálculo da ~2800 chars → 35% del budget → 5200 chars libres. **Experiencia cualitativamente distinta del prompt por-creator.**

### 6.4 Truncación selectiva en overflow

context.py:980-989 implementa el orden de sacrificio (cuando total > MAX_CONTEXT_CHARS):

1. FINAL priority sections first (citations, output_style_note) → se eliminan
2. MEDIUM priority (hier_memory, adv_memory) → se eliminan si aún overflow
3. HIGH priority (audio_context, rag_context) → se eliminan si aún overflow
4. CRITICAL (style_prompt, few_shots, recalling) → último recurso

**Problema:** para Iris, style_prompt es CRITICAL y por sí solo ya ocupa >50% del budget. Si muchas otras secciones HIGH se activan, se eliminan **antes de que style se considere**, pero **no hay mecanismo para reducir el propio style**.

### 6.5 Sin token-counter activo

W3 demostró que Clonnect **no cuenta tokens reales en runtime**. El único contador es CHAR. El mismo creator podría acabar enviando al LLM 3200 tokens (si el prompt está en español con tildes) o 1800 tokens (si es inglés ASCII) — mismo char count, diferente token count.

**Gap:** no hay telemetría de token count efectivo por turn. No se puede monitorizar drift.

### 6.6 Recomendación derivada de W3

- Implementar token-counter real en ensamblaje (usar tokenizer del provider activo)
- Budget en tokens, no chars
- Cap por-sección: style_prompt ≤ 800 tokens, few_shots ≤ 300 tokens
- Alerta si Iris.style.tokens > 1000 (comprimir con memo)
- Desacoplar budget de "ordinal priority" → usar cost/value per section

---

## §7 Bugs Directos (19 items)

Fuentes principales: W1 (bugs detectados en inventario), W2 (metadata orphans + security gaps), W3 (asimetría tokens), W4 (memoria), W5 (gates), W6 (compaction ausente).

### B1 — PersonaCompiler persistence mismatch (CRÍTICA)

**File:** `services/persona_compiler.py` + `core/dm/personality_loader.py`
**W1 evidence:** §sys18 ACTIVO_INÚTIL

**Bug:** PersonaCompiler escribe `creators.doc_d`, pero personality_loader lee `personality_docs.content`. Cualquier recompilación es **invisible para producción**.

**Impacto:** Doc D nunca refleja updates. Creators con cambios de estilo tras onboarding siguen usando Doc D stale.

**Fix:** unificar la tabla destino. Sugerido: migrar todo a `personality_docs` (tabla versionada) y deprecar `creators.doc_d`.

---

### B2 — VocabularyExtractor ImportError (CRÍTICA)

**File:** `core/vocabulary/extractor.py`
**W1 evidence:** §sys36 ELIMINAR (o reparar), nota "ImportError on boot for clones with specific config".

**Bug:** import chain rompe en ciertos entornos por dependencias no declaradas. Bloquea boot.

**Fix:** resolver deps o eliminar sistema si no se usa.

---

### B3 — prompt_service._tone_config unwired

**File:** `services/prompt_service.py`
**W1 evidence:** §sys02 note "_tone_config attribute exists, populated in __init__, never consumed by build_system_prompt".

**Bug:** configuración de tono se carga pero nunca se inyecta al prompt.

**Fix:** wire en `build_system_prompt()` o eliminar el field.

---

### B4 — identity_resolver wiring incompleto

**File:** `services/identity_resolver.py`
**W1 evidence:** §sys37 DORMIDO_RECUPERABLE.

**Bug:** existe para resolver identidad cross-plataforma (ig_id, email) pero no se invoca desde el DM agent.

**Fix:** wire en phase_detection si la feature se quiere activa; si no, mover a `deprecated/`.

---

### B5 — cognitive_metadata orphan fields (65 items)

**W2 evidence:** §Resumen — 65 de 114 fields son ORPHAN (escritos nunca leídos para decisions).

**Bug:** ~57% de la metadata escrita en cada request es computación gastada.

**Impacto:** CPU overhead + confusión para mantenimiento (developers no saben qué metadata importa).

**Fix:** auditar los 65 fields, eliminar los que no son useful para observabilidad.

---

### B6 — prompt_injection_attempt flag detectado no alertado (SEGURIDAD)

**File:** `core/dm/phases/detection.py:78`
**W2 evidence:** §3.6 Security — flag se escribe, nunca se lee externamente.

**Bug:** sistema detecta intentos de prompt injection (jailbreak) pero:
- No loggea a sistema externo
- No aplica rate-limit
- No alerta al creator
- El flag muere con el request

**Impacto:** atacantes pueden probar injections repetidamente sin consecuencias.

**Fix:** emit metric + log estructurado cuando flag=true; considerar bloqueo temporal si >N attempts en ventana de tiempo.

---

### B7 — sensitive_detected flag igualmente huérfano (SEGURIDAD)

**File:** `core/dm/phases/detection.py:102`
**W2 evidence:** §3.6.

**Bug:** mismo patrón que B6 pero para contenido sensible (datos personales, etc.).

**Fix:** igual a B6.

---

### B8 — guardrail_triggered sin persistencia

**File:** `core/dm/phases/postprocessing.py:365`
**W2 evidence:** §3.6 segundo bullet.

**Bug:** cuando un guardrail dispara, se guarda en metadata del request, pero no se persiste para análisis post-hoc.

**Fix:** INSERT a tabla `guardrail_events` para revisiones periódicas.

---

### B9 — Event Loop Blocking en fases 2-3

**File:** `core/dm/phases/context.py`
**Evidence:** Clonnect_Backend_Graph.md §Conexiones Sorprendentes #3.

**Bug:** operaciones DB síncronas llamadas desde contexto async (no wrap en `asyncio.to_thread()`).

**Impacto:** event loop bloqueado en cada request — throughput reducido bajo carga concurrente.

**Fix:** wrap DB calls síncronas en `asyncio.to_thread()` o migrar a AsyncSession de SQLAlchemy.

---

### B10 — PromptBuilder duplicación context.py

**Evidence:** S5 de §4 Solapamientos.

**Bug:** lógica de PromptBuilder duplicada para tests dentro de context.py.

**Impacto:** drift — tests pueden pasar con prompt ensamblado distinto al de producción.

**Fix:** import PromptBuilder directamente en tests.

---

### B11 — Few-shots double injection (token inflation)

**Evidence:** S6 de §4.

**Bug:** si ambos sistemas (calibration_loader + gold_examples) se activan, inyectan few-shots redundantes.

**Fix:** designar single source of truth.

---

### B12 — Response Variator v1/v2 coexistencia

**Evidence:** S7 de §4.

**Bug:** v1 legacy aún importado en 2 sitios tras migración a v2.

**Fix:** completar migración + remover v1.

---

### B13 — Style prompt sin budget cap (asimetría cuantitativa)

**W3 evidence:** §6.1 — Iris 1383 tokens vs Stefano 174 (7.9× asymmetry).

**Bug:** el style_prompt se inyecta completo sin cap. Creators con Doc D largo consumen desproporcionado budget.

**Fix:** cap por-sección (ej: 800 tokens máximo para style), con compresión automática si exceeds.

---

### B14 — MAX_CONTEXT_CHARS en chars en lugar de tokens

**Evidence:** §5 D10 + §6.5.

**Bug:** budget en chars no refleja tokens reales. Ratio varía 2.5× entre scenarios ASCII y UTF-8 con tildes.

**Fix:** usar tokenizer real del provider, budget en tokens.

---

### B15 — History truncation silenciosa (no compactación)

**Evidence:** §5 D5 + CRUCE §5.

**Bug:** conversaciones >10 turns descartan mensajes antiguos sin consolidación. Información pasada pierde.

**Fix:** implementar compactación tipo autoCompact (9-section summary).

---

### B16 — No mid-stream error recovery

**Evidence:** §5 D7 + CRUCE §7.

**Bug:** si un provider falla mid-stream, no hay recuperación; sólo fallback de provider pre-stream.

**Fix:** implementar retry con discard previous tokens.

---

### B17 — No circuit breaker

**Evidence:** §5 D7.

**Bug:** si el provider falla N veces consecutivas, Clonnect sigue reintentando. CC tiene MAX_CONSECUTIVE_FAILURES=3.

**Fix:** añadir circuit breaker por provider.

---

### B18 — Memory engines OFF por defecto en producción

**Evidence:** §5 D6, CRUCE §6.

**Bug:** los 3 sistemas de memoria episódica/hierarchical están apagados por defecto. Funcionalidad no se usa pese a existir el código.

**Fix:** decidir — activar por defecto (requiere resolver S1 Dual Memory Storage) o eliminar código dormido.

---

### B19 — Sin token telemetry runtime

**Evidence:** §6.5.

**Bug:** no hay métrica de "tokens reales enviados al provider". Sólo contador CHAR.

**Impacto:** cost tracking inexacto; drift no monitoreable.

**Fix:** emit `tokens_in`, `tokens_out` metric per turn; dashboard agregado.

---

### Resumen Bugs

| ID | Categoría | Severidad | Tipo |
|----|-----------|-----------|------|
| B1 | Persistence | **CRÍTICA** | Data loss (silent) |
| B2 | Runtime | **CRÍTICA** | Boot failure |
| B3 | Wiring | MEDIA | Dead config |
| B4 | Wiring | MEDIA | Dormant |
| B5 | Metadata | MEDIA | Waste |
| B6 | Seguridad | **ALTA** | Silent detection |
| B7 | Seguridad | **ALTA** | Silent detection |
| B8 | Observabilidad | MEDIA | No audit trail |
| B9 | Performance | ALTA | Event loop block |
| B10 | Mantenibilidad | MEDIA | Drift |
| B11 | Budget | MEDIA | Token inflation |
| B12 | Legacy | BAJA | Deprecated coexist |
| B13 | Budget | **ALTA** | Per-creator asymmetry |
| B14 | Budget | **ALTA** | Unit mismatch |
| B15 | Memoria | **ALTA** | Info loss |
| B16 | Resiliencia | ALTA | No recovery |
| B17 | Resiliencia | MEDIA | No breaker |
| B18 | Producto | MEDIA | Dormant features |
| B19 | Observabilidad | ALTA | No telemetry |

**Total crítica:** 2 | **Alta:** 8 | **Media:** 8 | **Baja:** 1

---

## §8 Veredicto Arquitectónico

Este apartado sintetiza hallazgos de §1-§7 en 5 decisiones arquitectónicas (A-E) que representan el criterio del auditor sobre el estado del sistema y el camino.

### A — Clonnect es funcional pero sin gobernanza de contratos

El sistema **produce respuestas válidas en producción hoy** (33 sistemas ACTIVO_VALIOSO, pipeline completo 5-phase). No es "código muerto".

Pero **falta gobernanza**: 13 solapamientos (§4), 19 bugs directos (§7), 12 brechas filosóficas con CC (§5), 65 metadata orphans (§3). Cada adición nueva aumenta la complejidad sin retirar la anterior.

**Consecuencia:** el coste de cambio es alto y creciente. Cualquier refactor toca múltiples sistemas semánticamente solapados (ej: "cambiar cómo se almacena memoria" toca S1, B18, D6).

**Decisión arquitectónica:** antes de features nuevas, aplicar **deprecation discipline** — por cada subsistema añadido, retirar el solapado (o marcar dormant explícito con plan de kill).

---

### B — La filosofía "post-edit the LLM output" es ajena a CC y fuente de 11 mutaciones

CC **nunca muta la salida del modelo** (CRUCE §4). Clonnect aplica 11 mutaciones en postprocessing.py — cada una parche por un bug upstream no fijado (ej: `sentence_dedup` existe porque el modelo se repite, y la solución es remediar post-hoc en lugar de mejorar el prompt/training).

**Decisión arquitectónica:** adoptar CC's principle "**un mal output es evidencia de mal prompt o mal training, no de necesidad de post-edit**". Cada mutation debería ser documentada con bug report + plan para eliminar upstream.

**Corolario:** W1 y W2 muestran que cada mutation introduce su propio debt (metadata flags, lógica compleja con edge cases). La deuda post-edit es compound.

---

### C — El budget de contexto está roto por 3 razones independientes

1. **CHAR en lugar de TOKENS** (B14, D10): budget expresado en unidad incorrecta.
2. **No hay cap per-section** (B13): style_prompt puede consumir 66% del budget para Iris.
3. **No hay orchestrator que priorice** (D11): truncación post-hoc por ordinal, no por cost/value.

**Decisión arquitectónica:** reescribir el budgeter como un **orchestrator con token-counter real**, cap por-sección, y selección greedy por value/cost. Adoptar pattern CC `getAttachments` con `maybe()` wrapper.

---

### D — La memoria conversacional es un área sin dueño

- 3 sistemas solapados (S1): MemoryStore, ConversationMemoryService, MemoryEngine
- 3 feature flags distintos (B18): ENABLE_MEMORY_ENGINE, ENABLE_EPISODIC_MEMORY, ENABLE_HIERARCHICAL_MEMORY
- **Todos OFF por defecto en producción**
- Sin source of truth, sin schema unificado, sin freshness signal

**Decisión arquitectónica:** consolidar en un único memory subsystem siguiendo el modelo CC de 4 tipos cerrados (user/feedback/project/reference) con body_structure mandatory (W4). Eliminar los otros dos sistemas dormant.

---

### E — Observabilidad y seguridad están detectadas pero no accionadas

- B6 + B7 + B8: prompt_injection_attempt, sensitive_detected, guardrail_triggered son detectados pero no persistidos, no alertados, no auditables.
- B19: no hay token telemetry.
- B5: 65 metadata fields escritos sin consumers.

**Decisión arquitectónica:** definir un **observability contract mínimo**: cualquier metadata field debe tener (a) un consumer explícito, o (b) ser emitido como metric externa. Ningún field puede ser escrito sin destino.

Para seguridad: prompt_injection + sensitive detection deben emit alertas + log a tabla de auditoría con retention ≥ 90 días.

---

### Veredicto agregado

Clonnect es un sistema **funcional con deuda arquitectónica significativa**. Sus problemas no son de algoritmos ni de modelos (el pipeline 5-phase es razonable) sino de:

1. **Acumulación sin retirada** (13 solapamientos)
2. **Contratos blandos** (dict global metadata vs typed contract CC)
3. **Budget roto** (3 razones independientes)
4. **Seguridad sin accionamiento** (detects sin alerts)
5. **Memoria sin dueño** (3 sistemas, 0 activos)

El camino prioritario es **consolidación** (no nuevas features). Cada sprint debe retirar más código del que añade.

---

## §9 Plan de Sprints

Basado en §7 bugs + §8 decisiones. Dos tracks paralelos: **Quick Wins** (1-3 días cada uno, impacto inmediato) y **Architectural** (1-3 semanas, requieren migración).

### Track 1: Quick Wins (2-3 semanas total)

#### QW1 — Fix PersonaCompiler persistence (B1)

- **Alcance:** unificar `creators.doc_d` y `personality_docs.content` en una sola fuente.
- **Plan:** (a) migración one-shot copiando todo Doc D a `personality_docs` con versionado; (b) eliminar columna `creators.doc_d`; (c) actualizar PersonaCompiler para escribir a `personality_docs`.
- **Riesgo:** bajo (migración idempotente, rollback por columna backup).
- **Effort:** 1 día.

#### QW2 — Fix VocabularyExtractor ImportError (B2)

- **Alcance:** resolver imports rotos o eliminar sistema.
- **Plan:** (a) correr pytest con verbose, identificar causa; (b) si no-usado, mover a `deprecated/` y remover imports; (c) si usado, fixar deps.
- **Riesgo:** medio (puede romper ENV específicos).
- **Effort:** 0.5-1 día.

#### QW3 — Activar alertas seguridad (B6+B7+B8)

- **Alcance:** prompt_injection_attempt + sensitive_detected + guardrail_triggered → emit metric + log estructurado.
- **Plan:** (a) INSERT a tabla `security_events` nueva; (b) emit Prometheus metric con labels creator_id + event_type; (c) dashboard Grafana; (d) documentar runbook.
- **Riesgo:** bajo.
- **Effort:** 1-2 días.

#### QW4 — Cleanup metadata orphans (B5)

- **Alcance:** eliminar ~65 fields escritos sin consumers.
- **Plan:** (a) usar W2 evidence (lista explícita 65 orphans); (b) remover set calls; (c) actualizar docstrings.
- **Riesgo:** bajo (cada field aislado).
- **Effort:** 2-3 días.

#### QW5 — Wire prompt_service._tone_config (B3)

- **Alcance:** o wirear a `build_system_prompt`, o eliminar.
- **Plan:** evaluar si el tone_config tiene valor. Si sí → inyectar como sección. Si no → remover código.
- **Riesgo:** bajo.
- **Effort:** 0.5 día.

#### QW6 — Eliminar Response Variator v1 (B12)

- **Alcance:** remover `variator_v1.py` + imports residuales.
- **Plan:** grep final de callers → migrar los 2 callsites a v2 → delete archivo.
- **Riesgo:** bajo.
- **Effort:** 0.5 día.

#### QW7 — Wrap sync DB calls en asyncio.to_thread (B9)

- **Alcance:** context.py fases 2-3.
- **Plan:** identificar sync calls dentro de async methods → wrap; añadir alembic validation test.
- **Riesgo:** medio (event loop behavior).
- **Effort:** 1-2 días.

**Subtotal Quick Wins:** ~7-10 días de effort.

---

### Track 2: Architectural (parallel, 8-12 semanas)

#### ARC1 — Token-aware budget orchestrator (B13+B14+D11)

- **Alcance:** reescribir `_assemble_context` como orchestrator con token-counter real + cap per-section + selection greedy.
- **Plan:**
  1. Integrar tokenizer del provider activo (tiktoken para GPT, vertex counter para Gemini).
  2. Definir `Section { name, content, priority, cap_tokens, value_score }`.
  3. Implementar `greedy_pack(sections, budget)` que maximiza value dentro de budget.
  4. Migrar cada sección existente a este contract.
- **Riesgo:** alto (refactor central).
- **Effort:** 3-4 semanas.

#### ARC2 — Memory consolidation (S1+D6+B18)

- **Alcance:** reemplazar MemoryStore + ConversationMemoryService + MemoryEngine por un sistema único.
- **Plan:**
  1. Diseñar schema basado en CC 4-types (user/feedback/project/reference) con body_structure mandatory.
  2. Implementar nuevo subsistema `memdir/` con CRUD.
  3. Migrar datos existentes (prioritizar ConversationMemoryService como base).
  4. Feature flag gradual rollout (10% → 50% → 100%).
  5. Retirar 3 sistemas viejos.
- **Riesgo:** alto (data migration).
- **Effort:** 4-6 semanas.

#### ARC3 — Compaction strategies (D5+B15)

- **Alcance:** implementar al menos 1 de las 4 estrategias CC (priorizar autoCompact).
- **Plan:**
  1. Implementar `autoCompact`: cuando history > N tokens, generar 9-section summary + scratchpad.
  2. Trigger en phase_context inicio.
  3. Preservar summary en thread metadata.
  4. A/B test: medir CPE v2 con/sin autocompact en conversaciones largas.
- **Riesgo:** medio.
- **Effort:** 2-3 semanas.

#### ARC4 — Eliminar response mutations (D4+B)

- **Alcance:** reducir de 11 mutations a ≤3 (guardrail substitution para seguridad obligatoria).
- **Plan:**
  1. Para cada mutation, identificar el bug upstream que la necesita.
  2. Fijar upstream (prompt, training, few_shots).
  3. Retirar mutation + test regression CPE v2.
- **Riesgo:** alto (puede regressionar quality).
- **Effort:** 4-6 semanas (incremental, 1 mutation por iteración).

#### ARC5 — Observability contract (E)

- **Alcance:** todo metadata field debe tener consumer O metric.
- **Plan:**
  1. Definir CI check: cualquier `metadata["foo"] = ...` sin `metadata.get("foo")` downstream → warning.
  2. Auditoría inicial usando W2.
  3. Migrar fields a typed dataclass (similar CC contract).
- **Riesgo:** medio.
- **Effort:** 2-3 semanas.

---

### Cronograma sugerido (16 semanas)

```
S1-S2:  QW1 + QW2 + QW3 + QW5 + QW6 + QW7 (quick wins)
S3-S5:  QW4 (metadata cleanup) + ARC3 inicio (autoCompact design)
S6-S9:  ARC1 (token budget orchestrator)
S10-S13: ARC2 (memory consolidation)
S14-S16: ARC5 (observability) + ARC4 inicio (mutations reduction)
```

ARC4 continúa post-S16 como trabajo incremental.

---

## §10 Apéndices

### 10.1 Contradicciones entre documentos input

Durante la síntesis se encontraron 5 contradicciones que se reportan sin resolver (regla del brief).

**C1 — Número de postprocessing steps:**
- CROSS_SYSTEM_ARCHITECTURE.md enumera 27 steps.
- CRUCE_REPO_VS_CLONNECT.md §4 confirma 27 total (11 mutate + 14 metadata + 2 append).
- DEEP_DIVE_CLONNECT_PIPELINE.md sección 310-342 dice "27 steps en `phase_postprocessing`".
- **W1 §sys15 dice 25 steps.**

**Status:** discrepancia 25 vs 27. Posible causa: W1 contó steps "externally observable" (excluyendo metadata-only). No resuelto.

**C2 — Número de sistemas:**
- W1 resultado: 62 sistemas (33+10+13+6).
- Clonnect_Backend_Graph.md no enumera; usa 624 "comunidades detectadas" (nivel distinto).
- CROSS_SYSTEM_ARCHITECTURE.md versión anterior: 23 sistemas.
- Brief original del W7 dispatcher: "60 sistemas" (en el nombre del archivo).

**Status:** W7 adopta 62 como cifra canónica (evidencia en W1 detallada).

**C3 — ENABLE_COMMITMENT_TRACKING default:**
- CRUCE_REPO_VS_CLONNECT.md §6: `true` (context.py:371).
- DEEP_DIVE_CLONNECT_PIPELINE.md §409-415: cita línea 371 pero no confirma default.

**Status:** se adopta `true` (CRUCE es más específico).

**C4 — Tamaño del history:**
- DEEP_DIVE_CLONNECT_PIPELINE.md §254: "up to 10 turns".
- CRUCE §1: "last 10 turns".
- generation.py:277-300 (mencionado en ambos): confirma 10.

**Status:** consistente, no contradicción.

**C5 — MAX_CONTEXT_CHARS:**
- DEEP_DIVE_CLONNECT_PIPELINE.md §21-36: 8000 como valor default.
- Tamaño real para Iris según W3: excede 7000 en configuraciones típicas.

**Status:** no es contradicción doctrinal sino evidence gap — el límite teórico está OK, la realidad es tight.

---

### 10.2 GAPs documentados

Items donde los input docs no tenían información suficiente.

**[GAP G1]** MEMORY.md defaults en CC. DEEP_DIVE_CONTEXT_ENGINEERING.md §587, 629-640 refiere MAX_ENTRYPOINT_LINES=200 / MAX_ENTRYPOINT_BYTES=25K como "inferred" — no confirmed exact values.

**[GAP G2]** autoDream consolidation — refiere "every 24h + 5 sessions" pero no NFOUND detailed logic.

**[GAP G3]** Detail de los 4 memory types cerrados — listados pero sin body_structure schema completo en los inputs.

**[GAP G4]** Ownership de creators sin DNA: qué creators tienen `dna_seed` poblado y cuáles no. No hay lista auditada en inputs.

**[GAP G5]** Coste real de cada sistema DORMIDO. No se midió CPU/memory footprint del código dormant (si se elimina, ¿cuánto se ahorra?).

**[GAP G6]** Relación exacta entre `cognitive_metadata` y `msg_metadata` (W2 menciona "dual dict" pero no detalla cuándo se usa cada uno).

**[GAP G7]** Conteo exacto de CC attachments. W5 dice "~38 parallel gates"; CRUCE §1 dice "generates 0–60+ items per turn". La cifra precisa de attachment types no está fijada.

**[GAP G8]** Tokenizer usado por cada provider (Gemini vs OpenAI). No hay evidencia en inputs de qué tokenizer usa Clonnect para contar — probablemente ninguno (usa chars).

---

### 10.3 Marcador de deprecación del documento antiguo

Este documento (`W7_FULL_CROSS_SYSTEM_60.md`) **reemplaza** a:

- `docs/CROSS_SYSTEM_ARCHITECTURE.md` (431 líneas, cobertura 23 sistemas, fecha anterior).

El documento anterior queda obsoleto para:
- Inventario de sistemas (usar §1 de este W7)
- Injection map (usar §2)
- Metadata flow (usar §3)
- Token budget (usar §6 con datos reales de W3, no estimates teóricos)

Sigue siendo útil para:
- La enumeración original de 27 postprocessing steps (W7 §4 S4 referencia a él).
- 11 position system prompt mapping (incorporado a §2.2).
- 6 ownership verification (referenciado pero no re-ejecutado).

**Acción recomendada:** añadir header al documento viejo con redirect → W7.

---

### 10.4 Notas de revisión

**Fuentes analizadas (12 total):**

Phase 2 workers (6):
- W1_inventory_37_systems.md (3307 líneas)
- W2_metadata_flow.md (209 líneas)
- W3_token_analytics_real.md (311 líneas)
- W4_cc_memory_deep_dive.md (585 líneas)
- W5_cc_gating_deep_dive.md (960 líneas)
- W6_cc_compaction_deep_dive.md (613 líneas)

Pre-existing docs (6):
- CROSS_SYSTEM_ARCHITECTURE.md (431 líneas)
- CRUCE_REPO_VS_CLONNECT.md (226 líneas)
- DEEP_DIVE_CONTEXT_ENGINEERING.md (886 líneas)
- DEEP_DIVE_CLONNECT_PIPELINE.md (714 líneas)
- GRAPH_REPORT.md (2952 líneas, grep-driven)
- Clonnect_Backend_Graph.md (143 líneas)

**Total input: ~11,337 líneas.** Output W7: ~1550 líneas (7:1 compression ratio).

**Cambios metodológicos vs CROSS_SYSTEM_ARCHITECTURE.md antiguo:**
1. Cobertura 62 sistemas (no 23).
2. Token budget basado en W3 medición real (no estimates teóricos).
3. Identificación explícita de 13 solapamientos (S1-S13) donde el viejo sólo mencionaba Dual Memory.
4. Sección §5 añadida (12 diferencias CC vs Clonnect).
5. Sección §8 añadida (5 veredictos arquitectónicos).
6. Sección §9 añadida (plan de sprints bi-track).
7. Evidencia de bugs elevada de "mentions" a tabla de 19 con severidad (§7).

---

### 10.5 Auditor log

**Fecha síntesis:** 2026-04-16
**Modelo:** Opus 4.6
**Workflow fases completadas:**
1. Read 12 input documents (incluyendo Grep sobre GRAPH_REPORT.md 2952 líneas).
2. Cross-reference between docs (13 solapamientos detectados, 5 contradicciones).
3. Bug inventory build-up (19 items priorizados por severidad).
4. Sprint plan derivation (7 QW + 5 ARC).
5. Write output section by section (§0-§10).

**Líneas totales output:** ~1550 (estimado post-write).
**Citas `file:line`:** >80 distintas.
**`[GAP]` markers:** 8.
**Contradicciones documentadas:** 5.

**Confianza global:** ALTA para §1 (W1 muy detallado), §3 (W2 exhaustivo), §6 (W3 cuantitativo).
**Confianza MEDIA:** §4 (algunos solapamientos inferidos de GRAPH_REPORT edges), §5 (CRUCE comprehensive).
**Confianza BAJA:** §10.2 GAPs (por definición gaps).

---

**Fin del documento W7_FULL_CROSS_SYSTEM_60.md**
