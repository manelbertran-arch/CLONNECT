# Pipeline DM — Inventario Consolidado 2026-04-23

**Propósito:** Fuente de verdad para decidir qué sistemas forensicar, optimizar, apagar, o activar.
**Scope:** Sistemas PIPELINE_DM_HOT y PIPELINE_DM_CONDITIONAL únicamente. Background jobs excluidos.
**Metodología:** Fases 1-3 (extracción docs + verificación código + cruce Railway). Ver sesión 2026-04-23.
**Branch:** `inventory/pipeline-dm-consolidated`
**Railway mirror:** `config/env_prod_mirror_20260422.sh` (68 vars, estado post-P4 LIVE)
**Baseline CCEE:** `docs/measurements/baseline_post_p4_live_v52_20260422.md` (v4=68.0, v5=67.7, σ=0.43)

**"Optimizado"** = ha pasado las 4 fases: (1) doc forense, (2) análisis metodológico, (3) bugs documentados y fixeados, (4) medición CCEE con delta vs baseline documentado. Si falta cualquiera → NO.

---

## Tabla maestra

| # | Sistema | Qué hace | Optimizado | Estado prod |
|---|---------|----------|:----------:|:-----------:|
| 1 | **Doc D (Personality Profile)** | Carga el perfil completo del creator (Doc D) desde `personality_docs`. Es el ~60-70% del prompt. Señal de identidad crítica — no comprimir. | SÍ | ON |
| 2 | **Intent Service (canonical)** | Clasifica el intent del mensaje (PURCHASE, INTEREST_STRONG, CASUAL, etc.) usando `services.IntentClassifier` + LLM fallback. Fuente única post-PR #77. | SÍ | ON |
| 3 | **Sensitive Detection** | Detecta contenido de crisis (autolesión, menores, emergencias) en Phase 1. Short-circuit inmediato si positivo. fail-closed. | SÍ | ON |
| 4 | **Pool Matcher / Response Variator** | Detecta mensajes cortos/rutinarios y los resuelve con respuestas del pool del creator sin llamar al LLM. Fast-path Phase 1. | SÍ | ON |
| 5 | **Context Detection** | Detecta señales contextuales del mensaje (B2B, nombre, objección, meta-mensaje, corrección). Enriquece el prompt con notas de contexto. | SÍ | ON |
| 6 | **Frustration Detection** | Detecta frustración en el mensaje (NONE/MILD/SEVERE). Modifica tono de respuesta y suprime preguntas de venta si frustrado. | SÍ | ON |
| 7 | **Conversation State** | Clasifica la fase conversacional (presentación → interés → objeciones → cierre). Determina qué sección del pipeline de venta ejecutar. | SÍ | ON |
| 8 | **DNA Engine (analyze)** | Lee el perfil DNA del lead (warmth, trust, engagement, sales_readiness) desde la tabla `relationship_dna`. Inyecta señales relacionales en el prompt. | SÍ | ON |
| 9 | **DNA Triggers** | Orquesta la actualización async del DNA del lead post-respuesta. Incluye dedup y cap de threads para proteger pool DB. | SÍ | ON |
| 10 | **Calibration Loader** | Carga always-on los baselines del creator (emoji_rate, exclamation_rate, vocab) para informar Style Normalizer y otros sistemas. | SÍ | ON |
| 11 | **RAG Semantic** | Recupera fragmentos relevantes del knowledge base del creator (pgvector + BM25 hybrid) para responder preguntas de producto. | SÍ | ON |
| 12 | **RAG Reranker** | Cross-encoder que re-ordena los resultados RAG por relevancia antes de inyectar en el prompt. Self-hosted (sentence-transformers). | SÍ | ON |
| 13 | **Memory Engine (ARC2)** | Lee hechos extraídos del lead (nombre real, gustos, compromisos previos) desde `lead_memories`. Posición más alta en Recalling block. | SÍ | ON |
| 14 | **Episodic Memory** | Lee snippets de conversaciones anteriores relevantes (pgvector similarity). Complementa Memory Engine con contexto narrativo. | SÍ | ON |
| 15 | **Semantic Memory pgvector** | Almacena y recupera memoria episódica en pgvector. Backend de Episodic Memory. | SÍ | ON |
| 16 | **Relationship Scorer** | Clasifica el tipo de relación lead-creator (TRANSACTIONAL / PERSONAL). Si PERSONAL, suprime productos del prompt. | SÍ | ON |
| 17 | **ARC1 BudgetOrchestrator** | Ensambla el prompt respetando el budget de tokens (MAX_CONTEXT_CHARS=8000). Greedy packing por prioridad de sección. | SÍ | ON |
| 18 | **Anti-Echo chain (M3/M4/M5)** | Detecta y reemplaza respuestas que repiten el mensaje del lead (echo). 3 capas: A2b (semántico), A2c (jaccard), A3 (pool fallback). | SÍ | ON |
| 19 | **Style Normalizer** | Post-generación: ajusta emoji y exclamación al baseline del creator (no sobrepasar su tasa natural). | SÍ | ON |
| 20 | **Length Controller** | Post-generación: fuerza límite de caracteres (≤1000 Instagram). Trunca si necesario. | SÍ | ON |
| 21 | **Question Remover** | Post-generación: elimina preguntas redundantes o en exceso para mantener el tono natural del creator. | SÍ | ON |
| 22 | **Guardrails** | Post-generación: valida seguridad de la respuesta (off-topic redirect, contenido prohibido). | SÍ | ON |
| 23 | **History Compactor (USE_COMPACTION)** | Compacta el historial de conversación para reducir tokens sin perder contexto relevante. Shadow-validated Sprint 5. | SÍ | ON |
| 24 | **SalesIntentResolver (P4)** | Arbitra entre las 4 señales de venta (DNA, Conv State, Frustration, Scorer) y produce una directiva unificada (SELL / NO_SELL / SOFT). Resuelve los 3 Tipo 1 BLOQUEANTE pre-P4. | SÍ | ON |
| 25 | **Copilot / DM Agent** | Modo copilot: sugiere respuesta al creator en lugar de enviar automáticamente. W8-B2a auditado, bugs críticos fixeados. | SÍ | ON |
| 26 | **dm_strategy** | Routing de estrategia conversacional. Selecciona rama de generación según relationship_type y fase. 2 ramas FAMILIA/AMIGO dormidas. | NO | ON |
| 27 | **contextual_prefix** | Añade prefijo contextual al embedding de documentos para mejorar precisión RAG (Anthropic pattern, +35-49%). | NO | ON |
| 28 | **Bot Question Analyzer** | Detecta si el mensaje es una pregunta directa y anota el tipo de pregunta para informar RAG routing. | NO | ON |
| 29 | **Tone Profile DB** | Carga el perfil de tono del creator (formal/casual, warmth level). Mal nombrado — es RAG + onboarding, no solo tono. | NO | ON |
| 30 | **context_analytics** | Observabilidad de distribución de tokens en el prompt ensamblado. No afecta output directamente — logging. | NO | ON |
| 31 | **SendGuard** | Barrera final antes de enviar: verifica que la respuesta cumple criterios mínimos. | NO | ON |
| 32 | **Output Validator** | Sistema vaciado (commit 1b3bc213): solo queda `validate_links()`. Detecta URLs alucinadas en la respuesta. | SÍ | OFF |
| 33 | **Lead Categorizer v2** | Clasifica al lead en 5 niveles de funnel (NUEVO/INTERESADO/CALIENTE/CLIENTE/FANTASMA). Redundante con Conv State #7 — causa intrínseca. | SÍ | OFF |
| 34 | **Relationship Adapter (ECHO)** | Modo comportamental completo: ajusta temperature, max_tokens y tono por categoría de lead. Conflicto identidad con Doc D pre-FT. | SÍ | OFF |
| 35 | **Gold Examples (StyleRetriever)** | Inyecta few-shot ejemplos de respuestas reales del creator (pgvector similarity). Δ=-0.70 por bugs P1 + dual injection sin guard. | SÍ | OFF |
| 36 | **Length Hints** | Inyecta hint de longitud target en el prompt ("Responde ultra-breve"). Bisect midió regresión 8.30→7.23. Conflicto con Style Anchor (W8 5.2). | SÍ | OFF |
| 37 | **DNA Engine (create)** | Crea nuevos perfiles DNA para leads sin historial. OFF para proteger pool DB (CLAUDE.md pool_size=12). ANALYZE=ON, CREATE=OFF. | NO | OFF |
| 38 | **Few-Shot injection (ENABLE_FEW_SHOT)** | Inyecta ejemplos de calibración del creator en el prompt (sección SYSTEM). W8-B2a auditado pero sin CCEE delta para este flag. | NO | OFF |
| 39 | **Query Expansion** | Expande la query RAG con sinónimos/variaciones antes de buscar. W8-B2a: HIBERNAR — redundante con BM25+embeddings, diccionario 50% Iris-specific. | NO | OFF |
| 40 | **Question Hints** | Inyecta hint de formato de pregunta en el prompt. W8-C: "🟢 DESBLOQUEADO — sin competencia", pero nunca reactivado en Railway. Sin CCEE. | NO | OFF |
| 41 | **Style Anchor (ENABLE_STYLE_ANALYZER)** | Inyecta anchor de longitud de estilo del creator en el prompt ("mensajes ~180 chars"). W8-C: conflicto 5.2 con Length Hints si ambos activos. | NO | OFF |
| 42 | **SBS / PPA** | Quality gate post-generación: score alignment con persona del creator, regenera si < 0.7. T5.1 bypass (saltaba anti-echo) enmascaró valor real. | NO | OFF |
| 43 | **Commitment Tracker** | Detecta compromisos pendientes del creator con el lead ("te mando el precio mañana") y los inyecta en Recalling. W8: tangencial, sin CCEE. | NO | OFF |
| 44 | **BM25 Hybrid** | Fallback lexical para RAG cuando embeddings fallan. W8-B2a auditado (batch 3) pero sin clasificación post-audit documentada. | NO | OFF |
| 45 | **Response Fixes** | Post-generación: correcciones ortográficas/patrón. Bugs fixeados Sprint 3 (db5f145f), pero sin CCEE delta con flag ON post-fix. | NO | OFF |
| 46 | **Message Splitter** | Divide respuestas largas en múltiples burbujas de WhatsApp/Instagram. dbf0cd11 precautorio. Sin forensic doc ni CCEE. | NO | OFF |
| 47 | **Best-of-N** | Genera 3 candidatos a distintas temperaturas y selecciona el mejor. W8-C Tipo 1 BLOQUEANTE (scoring ciego a postprocessing). | NO | OFF |
| 48 | **Confidence Scorer** | Asigna score de confianza a la respuesta final. Logging-only, sin impacto comportamental. Sin forensic doc. | NO | OFF |
| 49 | **Blacklist Replacement** | Reemplaza términos prohibidos y emojis del Doc D con equivalentes aprobados. Nunca medido (S6 OFF.5). | NO | OFF |
| 50 | **Preference Profile** | Perfil experimental de preferencias del usuario. Sin forensic ni CCEE. | NO | OFF |

---

## Sub-listados

### 1 — Optimizados ON (mantener) — 25 sistemas

Sistemas con forensic + methodology + bugs fixeados + CCEE delta, actualmente en producción:

Doc D, Intent Service (canonical), Sensitive Detection, Pool Matcher, Context Detection, Frustration Detection, Conversation State, DNA Engine (analyze), DNA Triggers, Calibration Loader, RAG Semantic, RAG Reranker, Memory Engine (ARC2), Episodic Memory, Semantic Memory pgvector, Relationship Scorer, ARC1 BudgetOrchestrator, Anti-Echo chain (M3/M4/M5), Style Normalizer, Length Controller, Question Remover, Guardrails, History Compactor, SalesIntentResolver (P4), Copilot / DM Agent

---

### 2 — Optimizados OFF — 6 sistemas ← **clave para próximos sprints**

Sistemas con forensic + CCEE delta documentado, actualmente OFF con decisión documentada:

| Sistema | CCEE Δ | Decisión | Acción |
|---------|--------|----------|--------|
| **Output Validator** | sistema vaciado (1b3bc213) | OFF — solo `validate_links()` | Mantener OFF o reimplementar si hay necesidad |
| **Lead Categorizer v2** | −0.30 (S6 OFF.3) | MANTENER OFF — causa intrínseca (redundante Conv State) | No reactivar |
| **Relationship Adapter (ECHO)** | −0.40 (S6 OFF.1) | MANTENER OFF hasta post-FT — conflicto Doc D identidad | Revalidar post-fine-tuning |
| **Gold Examples (StyleRetriever)** | −0.70 (S6 OFF.2) | **REVALIDAR** tras fix guard exclusión mutua vs #10 Creator Style | Fix guard → CCEE |
| **Length Hints** | regresión bisect `de7c319a` | OFF — conflicto W8-C 5.2 con Style Anchor | Solo activar sin Style Anchor, medir CCEE |
| **DNA Engine (create)** | sin CCEE delta (protección DB) | OFF — pool_size=12 CLAUDE.md | Reactivar con cap/semáforo (W8-B2a top-5 #3) |

> **Nota:** "Optimizados OFF" no significa todos candidatos a reactivar — significa que sabemos exactamente por qué están OFF. Los accionables para reactivación son Gold Examples (fix + CCEE) y DNA create (cap + CCEE).

---

### 3 — No optimizados ON — 6 sistemas (pendientes forensicar)

Sistemas activos en producción sin metodología completa. Riesgo latente — podrían estar aportando o restando sin que lo midamos:

| Sistema | Riesgo | Prioridad forensic |
|---------|--------|-------------------|
| **dm_strategy** | 2 ramas FAMILIA/AMIGO dormidas, routing no medido | MEDIA |
| **contextual_prefix** | +35-49% RAG según docs pero sin CCEE aislado | MEDIA |
| **Bot Question Analyzer** | Anota tipo de pregunta, impacto en RAG routing desconocido | BAJA |
| **Tone Profile DB** | Mal nombrado, scope real incierto | BAJA |
| **context_analytics** | Logging-only — probablemente no impacta output | MUY BAJA |
| **SendGuard** | Barrera final — sin forensic doc sobre criterios | MEDIA |

---

### 4 — No optimizados OFF — 13 sistemas (pendientes forense + decisión)

Sistemas OFF sin metodología completa. Algunos pueden aportar valor, otros pueden ser dead weight. Sin evidencia para decidir:

| Sistema | Por qué OFF | Acción sugerida |
|---------|------------|-----------------|
| **Few-Shot injection** | dbf0cd11 precautorio, W8 auditado sin CCEE | CCEE 50×3 con flag ON |
| **Query Expansion** | W8-B2a HIBERNAR recomendado, sin CCEE delta | Confirmar con CCEE A/B |
| **Question Hints** | dbf0cd11, W8-C desbloqueado — **contradicción abierta** | CCEE 50×3 (W8-C dice GO) |
| **Style Anchor** | dbf0cd11, conflicto 5.2 con Length Hints | Fix conflicto → CCEE |
| **SBS / PPA** | T5.1 bypass enmascaró valor, S6 REVALIDAR | Fix T5.1 ordering → CCEE |
| **Commitment Tracker** | W8 "tangencial", sin CCEE | CCEE 50×3 si se activa |
| **BM25 Hybrid** | dbf0cd11, W8 batch 3 auditado sin decisión clara | Verificar W8-B2a batch docs |
| **Response Fixes** | dbf0cd11, bugs fixed pero sin CCEE post-fix | CCEE 50×3 con flag ON |
| **Message Splitter** | dbf0cd11, sin forensic | Forensic primero |
| **Best-of-N** | W8-C Tipo 1 BLOQUEANTE (scoring vs postprocessing) | Fix architectural antes |
| **Confidence Scorer** | Sin forensic ni CCEE, logging-only | Forensic — ¿afecta output? |
| **Blacklist Replacement** | Nunca medido (S6 OFF.5) | Incluir en próximo CCEE batch |
| **Preference Profile** | Sin forensic ni CCEE | Forensic primero |

---

## Resumen numérico

| Categoría | Count |
|-----------|-------|
| Optimizados ON (mantener) | **25** |
| Optimizados OFF (decisión documentada) | **6** |
| No optimizados ON (riesgo latente) | **6** |
| No optimizados OFF (pendientes decisión) | **13** |
| **Total pipeline DM** | **50** |

---

## Sistemas excluidos del scope

Background jobs, CLI tools, y dead code catalogados en Fases 1-3 pero fuera del pipeline DM por-mensaje:
- Memory Consolidator (ARC2 nightly), LLM Consolidation, Nightly Extract Deep
- FeedbackCapture, PersonaCompiler, Semantic Chunker
- Bot Orchestrator (async/memory, no hot path), TimingService
- Chain of Thought (archivo no existe — dead code)
- Intelligence Engine (analytics CLI)

---

## Próximos pasos sugeridos (basados en baseline v52 J6=35, B2=28.5, C3=21)

Los 3 hallazgos críticos del baseline (J6 Q&A Consistency, B2 Persona Fidelity, C3 Contextual Reasoning) apuntan a memoria y perfil del creator como áreas de mayor impacto:

1. **Prioridad 1 — Memoria episódica/semántica** (ataca J6 + C3): Semantic Memory pgvector (ON, pendiente optimizar aisladamente), Episodic Memory (ON, no medido aislado), Memory Engine (ON, ARC2 completo pero J6 sigue bajo)
2. **Prioridad 2 — Creator profile** (ataca B2): DNA Engine create (OFF por pool — fix cap → reactivar), DNA analyze (ON, medir impacto aislado en B2)
3. **Prioridad 3 — Quality gate** (ataca los 3): SBS/PPA (OFF, fix T5.1 ordering → CCEE — candidato más prometedor de los no-optimizados OFF)
4. **Quick wins** (sin grandes fijos): Question Hints (W8-C dice GO, CCEE 50×3 bajo coste), Response Fixes (bugs fixed, CCEE 50×3 bajo coste)

---

*Generado 2026-04-23. Fuentes: W1_inventory_37_systems, W7_FULL_CROSS_SYSTEM_60, W8_C_compatibility_matrix, s6_rematrix (7 docs), audit/sistema_* (21 docs), env_prod_mirror_20260422.sh, baseline_post_p4_live_v52_20260422. Para actualizar: re-ejecutar Fases 1-3 y regenerar tabla maestra.*
