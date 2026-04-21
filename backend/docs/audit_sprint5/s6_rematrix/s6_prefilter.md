# S6 Re-matriz — Fase 2: Pre-filtrado de pares

**Fecha:** 2026-04-21
**Auditor:** Opus 4.6
**Branch:** `audit/s6-rematrix`
**Scope:** 30 sistemas → 435 pares posibles

---

## Bugs de producción W8 baseline (preservados para Fase 8)

Estos 3 bugs fueron detectados en W8 Fase C (18-abr) y NO habían sido vistos en audits B.2a/B.2b. Se revalidarán en Fase 8.

| # | Bug | Sistemas | Evidencia W8 | Estado estimado post-Sprint 5 |
|---|-----|---------|-------------|-------------------------------|
| **P1** | 🔴 Debounce race condition | Copilot debounce (copilot/messaging.py:249-365) | Creator reply at T+19s, debounce regenera at T+20s, sobrescribe sugerencia | SIGUE VIVO — no hay commit que lo toque |
| **P2** | 🟡 Payment Link viola length bounds | Length Controller × postprocessing (postprocessing.py:393-409) | Payment link appended DESPUÉS de length enforcement | SIGUE VIVO — misma línea, mismo patrón |
| **P3** | 🟡 Intent override media_share ignorado | Media Placeholder × Intent Service (detection.py:143 → IntentService) | intent_override="media_share" no consumido por IntentService | SIGUE VIVO — no hay commit que propague override |

---

## Pares MISMO SISTEMA (descartados)

| Par | Sistema A | Sistema B | Razón | Evidencia |
|-----|-----------|-----------|-------|-----------|
| #8 × #24 | DNA Engine (`relationship_dna_service.py` + `relationship_dna_repository.py`) | DNA Triggers (`dna_update_triggers.py`) | Comparten `relationship_dna_repository.py`. #8 lee DNA para inyectar al prompt, #24 escribe DNA al recibir un mensaje. Mismo subsistema DNA, facetas read/write. | repository importado en ambos: context.py:832,982 y dna_update_triggers.py |
| #3 × #18 | Pool Matcher (detection, `response_variator_v2.py:try_pool_response()`) | Response Variator v2 (scope dice "postproc side") | #18 "postproc side" no existe como sistema separado. `response_variator_v2.py` NO se importa en `postprocessing.py`. La variación post-generación se hace por otros sistemas (echo fallback, blacklist). Pool Matcher y Variator son el mismo servicio. | `grep -rn "response_variator" postprocessing.py` → 0 results |

**Total pares MISMO SISTEMA: 2**

---

## Nota metodológica: #2 Style Normalizer

El scope asigna #2 Style Normalizer al GRUPO A (prompt-injection). Sin embargo, `normalize_style()` se ejecuta en `postprocessing.py:382-388` como paso post-generación. NO inyecta al prompt. Lee `baseline_metrics` y `bot_natural_rates` del perfil creator para ajustar emoji y exclamación DESPUÉS de la generación LLM.

Para el análisis de pares, trato #2 como sistema híbrido: sus interacciones con Grupo A son por datos compartidos (baselines), sus interacciones con Grupo B son por cadena secuencial.

---

## Estado ON/OFF de los 30 sistemas (prod, 21-abr-2026)

| # | Sistema | Flag ON/OFF | Notas |
|---|---------|-------------|-------|
| 1 | Doc D comprimido | **OFF** (USE_COMPRESSED_DOC_D=false) | Doc D raw se inyecta completo |
| 2 | Style Normalizer | **ON** (ENABLE_STYLE_NORMALIZER=true) | |
| 3 | Pool Matcher | **ON** (pool_matching flag) | |
| 4 | RAG Semantic | **ON** | |
| 5 | RAG Reranker | **ON** (ENABLE_RERANKING=true) | Requiere sentence_transformers (no en .venv local) |
| 6 | Memory Engine | **ON** (ENABLE_LEAD_MEMORIES_READ=true, ARC2) | ARC2 read cutover activo |
| 7 | Episodic Memory | **OFF** (ENABLE_EPISODIC_MEMORY=false) | |
| 8 | DNA Engine | **ON** (DNA_AUTO_CREATE=true, DNA_AUTO_ANALYZE=true) | |
| 9 | Conversation State | **ON** (ENABLE_CONVERSATION_STATE=true) | |
| 10 | Calibration Loader | **ON** (ENABLE_FEW_SHOT=true) | |
| 11 | Question Remover | **ON** (question_removal flag) | |
| 12 | Anti-Echo | **ON** (A2/A2b/A2c/A3 habilitados) | M3/M4/M5 shadow flags pueden desactivar individualmente |
| 13 | Guardrails | **ON** (guardrails flag) | |
| 14 | Output Validator | **ON** (output_validation flag) | |
| 15 | Response Fixes | **ON** (response_fixes flag) | |
| 16 | Message Splitter | **ON** | Llamado post-postprocessing |
| 17 | Length Controller | **ON** | |
| 18 | Response Variator v2 | MISMO SISTEMA con #3 | |
| 19 | Frustration Detection | **ON** (frustration_detection flag) | |
| 20 | Context Detection | **ON** (context_detection flag) | |
| 21 | Sensitive Detection | **ON** (sensitive_detection flag) | |
| 22 | Intent Service | **ON** | Ejecutado en context.py (no detection.py) |
| 23 | Relationship Scorer | **ON** (ENABLE_RELATIONSHIP_DETECTION=true) | |
| 24 | DNA Triggers | MISMO SISTEMA con #8 | |
| 25 | Creator Style Loader | **ON** | Siempre activo, carga Doc D |
| 26 | FeedbackCapture | **ON** (ENABLE_EVALUATOR_FEEDBACK=true) | |
| 27 | PersonaCompiler | **OFF** (ENABLE_PERSONA_COMPILER=false) | |
| 28 | StyleRetriever | **OFF** (ENABLE_GOLD_EXAMPLES=false) | |
| 29 | Confidence Scorer | **ON** (postprocessing.py:559) | |
| 30 | Commitment Tracker | **ON** (ENABLE_COMMITMENT_TRACKING=true) | |

---

## Mapa de inyección al prompt (context.py assembly)

Para entender qué pares compiten, mapeo qué sección del prompt escribe cada sistema:

**Sección `style` (CRITICAL priority, value 1.00):**
- #1 Doc D → `agent.style_prompt` (context.py:1518)
- #25 Creator Style Loader → provee el style_prompt que #1 usa

**Sección `few_shots` (CRITICAL priority, value 0.95):**
- #10 Calibration Loader → `get_few_shot_section()` (context.py:1275)
- #28 StyleRetriever → gold examples (OFF, inyectaría vía system_prompt_override si ON)

**Sección `recalling` (HIGH priority, dynamic value):**
- #6 Memory Engine → `memory_context` (context.py:867-885)
- #7 Episodic Memory → `episodic_context` (context.py:904, OFF)
- #8 DNA Engine → `dna_context` (context.py:860)
- #9 Conversation State → `state_context` (context.py:842)
- #19 Frustration → `_frustration_note` (context.py:1366-1381)
- #20 Context Detector → `_context_notes_str` (context.py:1386-1390)
- #30 Commitment Tracker → via Relationship Adapter → `relational_block` (context.py:1480-1487)
- Length Hints → appended a `_context_notes_str` (context.py:1420)
- Question Hints → appended a `_context_notes_str` (context.py:1436)

**Sección `rag` (HIGH priority, dynamic value):**
- #4 RAG Semantic → `rag_context` (context.py:1153)
- #5 RAG Reranker → modifica rag_results antes de formatear (integrado en search flow)

**Sección `hier_memory` (LOW priority):**
- Hierarchical Memory (OFF)

**Secciones menores:** kb (Knowledge Base), audio, citation, advanced (OFF), override.

---

## Cadena postprocessing (orden de ejecución)

Orden exacto en `postprocessing.py`:

| Step | Sistema | Acción | Modifica response_content |
|------|---------|--------|---------------------------|
| A2 | Anti-Echo (loop exact) | LOG ONLY | NO |
| A2b | Anti-Echo (intra-repetition) | Trunca repeticiones | SÍ |
| A2c | Anti-Echo (sentence dedup) | Dedup frases | SÍ |
| A3 | Anti-Echo (Jaccard echo) | Reemplaza con pool | SÍ |
| 7a | Output Validator (#14) | Corrige links | SÍ |
| 7a2 | Response Fixes (#15) | Typos, patrones | SÍ |
| 7a2b3 | Blacklist (via #10) | Reemplaza palabras/emoji | SÍ |
| 7a2c | Question Remover (#11) | Elimina preguntas | SÍ |
| 7a3 | Reflexion Engine | LOG ONLY | NO |
| 7a4 | SBS/PPA | Puede regenrar respuesta | SÍ (si score < 0.7) |
| 7b | Guardrails (#13) | Valida, puede corregir | SÍ |
| 7c | Length Controller (#17) | Enforce length | SÍ |
| 7b2 | Style Normalizer (#2) | Emoji, exclamación | SÍ |
| 7c-fmt | Instagram format | Format | SÍ |
| 7d | Payment Link inject | Append link | SÍ |
| score | Confidence Scorer (#29) | Score DESPUÉS de todo | NO (read-only) |

---

## Pares retenidos: ALTA prioridad

Pares donde ambos sistemas escriben a la misma sección/dimensión del prompt, o donde hay evidencia de conflicto directo W8.

| Par | Sistema A | Sistema B | Razón inclusión | W8 ref |
|-----|-----------|-----------|-----------------|--------|
| A.1 | #1 Doc D | #8 DNA Engine | Ambos inyectan instrucciones de tono/warmth. Doc D en `style`, DNA en `recalling`. LLM recibe doble instrucción si Relationship Adapter activo. | W8 1.1 |
| A.2 | #1 Doc D | #10 Calibration Loader | Doc D (CRITICAL) + few-shot (CRITICAL) compiten por atención del LLM. Ambos definen estilo. Few-shot puede contradecir Doc D si examples no alineados. | W8 3.1 |
| A.3 | #1 Doc D | #25 Creator Style Loader | #25 carga el Doc D para #1. Acoplamiento directo: si #25 falla o carga versión stale, #1 degrada. | — |
| A.4 | #1 Doc D | #2 Style Normalizer | Doc D define baselines cuantitativos (emoji_rate, exclamation_rate). #2 lee esos baselines para normalizar output. Si baselines cambian sin recalibrar #2, output diverge. | — |
| A.5 | #1 Doc D | #17 Length Controller | Doc D puede tener preferencia de longitud implícita. Length Controller tiene su propia config. Si contradicen, Length Controller gana (ejecuta último). | W8 3.4 |
| A.6 | #4 RAG Semantic | #5 RAG Reranker | Pipeline secuencial: #4 retrieves, #5 reranks. Reranker puede eliminar resultados relevantes o promover irrelevantes. | — |
| A.7 | #6 Memory × #7 Episodic | Memory Engine | Episodic Memory | Ambos inyectan datos de memoria del lead en `recalling`. Memory: facts extraídos. Episodic: snippets raw. Posible redundancia 2.1 + pollution 4.1. | W8 2.1, 2.2, 4.1 |
| A.8 | #6 Memory | #8 DNA Engine | Ambos en `recalling`. Memory provee facts, DNA provee relación. Bajo riesgo de conflicto semántico pero compiten por espacio en recalling. | — |
| A.9 | #6 Memory | #9 Conv State | Ambos en `recalling`. Memory: facts persistentes. State: fase conversacional actual. Complementarios pero compiten por chars. | — |
| A.10 | #6 Memory | #30 Commitment Tracker | Memory puede extraer commitments como facts. Commitment Tracker inyecta commitments via Relationship Adapter. Posible duplicación. | W8 2.10 |
| A.11 | #8 DNA | #23 Relationship Scorer | Scorer lee `memory_context` y history para calcular relationship score. DNA ya tiene `relationship_type`. Si divergen (scorer dice PERSONAL, DNA dice TRANSACTIONAL), señales contradictorias. | — |
| A.12 | #8 DNA | #9 Conv State | Ambos en `recalling`. DNA: relación lead-creator. State: fase conversacional. Podrían enviar señales contradictorias sobre tono apropiado. | — |
| A.13 | #10 Calibration | #12 Anti-Echo | Echo detector usa `short_response_pool` de calibration. Si pool vacío, echo detector no puede reemplazar → echo pasa. Dependencia directa. | W8 3.5 |
| A.14 | #10 Calibration | #11 Question Remover | Question Remover lee `question_rate` de calibration profile. Si calibration no tiene rate, remover deshabilitado para ese creator. | — |
| A.15 | #10 Calibration | #28 StyleRetriever | Si ambos ON, dual few-shot injection: calibration en SYSTEM prompt, gold examples en USER message. Sin mutual exclusion guard. | W8 2.6 |
| A.16 | #11 Question Remover | #17 Length Controller | Question Remover elimina contenido → acorta respuesta. Length Controller puede truncar después. Ambos afectan longitud. Si QR deja respuesta muy corta, LC no tiene margen. | — |
| A.17 | #12 Anti-Echo | #17 Length Controller | Echo replacement con pool response (short, <15 chars) → LC puede intentar alargar/truncar respuesta ya corta. | — |
| A.18 | #13 Guardrails | #17 Length Controller | Guardrails puede corregir respuesta (corrected_response). LC ejecuta después y puede truncar la corrección, anulando el fix de guardrails. | — |
| A.19 | #2 Style Normalizer | #17 Length Controller | LC ejecuta ANTES de normalizer (step 7c → 7b2). Normalizer puede añadir/quitar emojis, cambiando la longitud post-LC enforcement. Violación de length bounds. | W8 nuevo |
| A.20 | #16 Message Splitter | #17 Length Controller | Ambos gestionan longitud. LC enforce per-message limit, Splitter crea multi-bubble. LC ejecuta ANTES de Splitter. Compatible si same config. | W8 6.4 |
| A.21 | #22 Intent | #10 Calibration | Intent determina few-shot selection (`intent_value` pasado a `get_few_shot_section()`). Si intent incorrecto, examples irrelevantes. Acoplamiento directo. | — |
| A.22 | #22 Intent | #4 RAG Semantic | Intent determina RAG signal routing (context.py:1066-1096). `_rag_signal` basado en intent_value. Intent incorrecto → RAG busca en tipo equivocado. | — |
| A.23 | #25 Creator Style Loader | #27 PersonaCompiler | PersonaCompiler escribe secciones `[PERSONA_COMPILER:*]` en Doc D. Style Loader lee Doc D. Acoplamiento directo escritor→lector. | W8 3.11 |
| A.24 | #26 FeedbackCapture | #27 PersonaCompiler | FeedbackCapture almacena señales (preference pairs, copilot actions). PersonaCompiler las consume para compilar Doc D. Pipeline directo. | — |
| A.25 | #29 Confidence Scorer | #11 Question Remover | `calculate_confidence()` ejecuta en postprocessing.py:559 DESPUÉS de question removal (step 7a2c) y otros steps. PERO no penaliza preguntas que ya fueron removidas — si QR falla, confidence no detecta. | W8 1.2 (parcial) |

---

## Pares retenidos: MEDIA prioridad

Pares que comparten datos, metadata, o state aunque no inyecten en la misma sección directa.

| Par | Sistema A | Sistema B | Razón inclusión |
|-----|-----------|-----------|-----------------|
| M.1 | #1 Doc D | #4 RAG Semantic | Budget competition: `style` (CRITICAL) vs `rag` (HIGH). ARC1 puede truncar RAG para preservar Doc D. |
| M.2 | #1 Doc D | #6 Memory Engine | Budget competition: `style` vs `recalling`. ARC1 asigna prioridades distintas. |
| M.3 | #1 Doc D | #7 Episodic Memory | Budget: `style` vs episodic (dentro de `recalling`). Episodic OFF pero relevant si se activa. |
| M.4 | #1 Doc D | #9 Conv State | Budget: style vs state (dentro de recalling). |
| M.5 | #1 Doc D | #11 Question Remover | Doc D puede fomentar preguntas ("enganche"), QR las elimina. Contradirección estilística. |
| M.6 | #1 Doc D | #12 Anti-Echo | Echo fallback pool debe alinearse con voz Doc D. Si pool desalineado, echo replacement rompe estilo. |
| M.7 | #1 Doc D | #27 PersonaCompiler | PersonaCompiler actualiza Doc D secciones (batch). Si compiler error, corrompe Doc D. |
| M.8 | #2 Style Normalizer | #8 DNA Engine | DNA warmth → LLM genera más emojis → Normalizer los stripea a baseline. Cadena indirecta pero afecta misma dimensión (estilo). |
| M.9 | #2 Style Normalizer | #10 Calibration | Normalizer lee `baseline_metrics` que provienen del mismo perfil creator que Calibration. Shared data source. |
| M.10 | #2 Style Normalizer | #12 Anti-Echo | Normalizer (step 7b2) ejecuta DESPUÉS de echo replacement (A3). Si echo pool response tiene emojis, normalizer las ajusta. Ordering OK pero comportamiento puede sorprender. |
| M.11 | #2 Style Normalizer | #11 Question Remover | Ambos modifican response_content secuencialmente. QR (step 7a2c) antes de normalizer (step 7b2). Bajo riesgo de conflicto. |
| M.12 | #3 Pool Matcher | #10 Calibration | Pool Matcher lee few-shot pools y short responses de calibration. Dependencia directa (datos). |
| M.13 | #4 RAG × #6 Memory | RAG Semantic | Memory Engine | Budget competition: `rag` vs `recalling`. Ambos HIGH priority en BudgetOrchestrator. |
| M.14 | #4 RAG | #10 Calibration | Budget: `rag` (HIGH) vs `few_shots` (CRITICAL). Few-shot gana en budget squeeze. |
| M.15 | #6 Memory | #23 Relationship Scorer | Scorer parsea `memory_context` para extraer `lead_facts` (context.py:1169-1185). Si memory format cambia, scorer rompe. |
| M.16 | #7 Episodic | #8 DNA | Ambos en recalling. Episodic provee raw snippets, DNA provee relación. Compiten por chars en recalling block. |
| M.17 | #7 Episodic | #9 Conv State | Ambos en recalling. Si ambos ON, recalling se agranda. |
| M.18 | #7 Episodic | #30 Commitment | Episodic snippets y commitments ambos en recalling (indirectamente). |
| M.19 | #8 DNA | #30 Commitment | Commitment text alimenta Relationship Adapter que genera `relational_block`. DNA genera `dna_context`. Ambos en recalling, dimensión relacional. |
| M.20 | #9 Conv State | #19 Frustration | Frustration note y state context ambos en recalling. State dice "fase=negotiation", frustration dice "lead frustrado". Señales complementarias o contradictorias. |
| M.21 | #9 Conv State | #20 Context Detector | State y context notes ambos en recalling. Complementarios pero compiten por chars. |
| M.22 | #9 Conv State | #30 Commitment | State dice fase, commitments dicen promesas pendientes. Ambos en recalling. |
| M.23 | #11 QR | #29 Confidence | Confidence (step score) ejecuta DESPUÉS de QR. Si QR eliminó pregunta, confidence ve respuesta sin pregunta. OK si confidence no mide preguntas. |
| M.24 | #12 Anti-Echo | #13 Guardrails | Echo replacement (A3) ANTES de guardrails (7b). Si echo fallback contiene URL/price inválido, guardrails debería catch. Pero pool responses son cortas (<15 chars), risk bajo. |
| M.25 | #12 Anti-Echo | #29 Confidence | Confidence scorer ve la respuesta POST-echo-replacement. Si echo reemplazó, confidence score refleja el pool response, no el original. |
| M.26 | #13 Guardrails | #14 Output Validator | Ambos validan output. Guardrails: URL domains, prices, safety. Validator: link correctness. Solapamiento en links. |
| M.27 | #13 Guardrails | #15 Response Fixes | Fixes (step 7a2) ANTES de guardrails (7b). Fixes puede introducir o corregir patterns que guardrails evalúa. |
| M.28 | #14 Output Validator | #15 Response Fixes | Validator (7a) y Fixes (7a2) secuenciales. Validator corrige links, Fixes corrige otros patterns. Bajo risk overlap. |
| M.29 | #17 Length Controller | #30 Commitment | Payment link injection (step 7d) DESPUÉS de length controller (7c). Si commitment-related response + payment link, length violated. Análogo a bug P2. |
| M.30 | #19 Frustration | #6 Memory | Frustration note en recalling junto a memory facts. Si frustrado + memory "pidió info de producto", señales contradictorias. |
| M.31 | #19 Frustration | #8 DNA | Frustration note + DNA context en recalling. DNA dice "trust=0.8, warm", frustration dice "lead frustrado". |
| M.32 | #19 Frustration | #20 Context Detector | Ambos detectan señales del input message. Ambos alimentan recalling. Frustration: nivel numérico. Context: categorías (B2B, sarcasm, correction). Complementarios. |
| M.33 | #20 Context Detector | #6 Memory | Context notes + memory facts en recalling. Contexto actual + hechos pasados. |
| M.34 | #20 Context Detector | #8 DNA | Context notes + DNA en recalling. |
| M.35 | #22 Intent | #3 Pool Matcher | Intent classification (context phase) y pool matching (detection phase) son independientes. Pool matching usa message text directamente. Intent no modifica pool behavior. PERO ambos clasifican la misma cosa: tipo de mensaje. Potencial divergencia. |
| M.36 | #23 Relationship | #4 RAG | is_friend=True (score>0.8) → products stripped → RAG products irrelevantes pero ya inyectados. RAG corre ANTES de que is_friend se evalúe (context.py:1111 vs 1200). Token waste si friend. |
| M.37 | #25 Creator Style Loader | #28 StyleRetriever | Ambos cargan datos del creator. Style Loader: Doc D. StyleRetriever: gold examples. Shared source (creator_profiles). |
| M.38 | #25 Creator Style Loader | #10 Calibration | Ambos leen datos del creator: Style Loader (Doc D), Calibration (few-shot, baselines). Coherencia dependiente de pipeline de minería. |

---

## Pares retenidos: BAJA prioridad

Interacción plausible pero indirecta (cadena de 2+ pasos, diferentes fases sin datos compartidos directos).

| Par | Sistema A | Sistema B | Razón inclusión |
|-----|-----------|-----------|-----------------|
| B.1 | #1 Doc D | #3 Pool Matcher | Pool responses deberían alinearse con Doc D voice. Si pool desalineado, fast-path responses rompen estilo. Pero pool short-circuits — no interactúan en misma request. |
| B.2 | #1 Doc D | #13 Guardrails | Doc D puede mencionar productos/URLs. Guardrails valida URLs en response (no en Doc D). Indirecto. |
| B.3 | #1 Doc D | #28 StyleRetriever | Gold examples deberían alinearse con Doc D. Si gold stale, examples contradicen Doc D actual. |
| B.4 | #1 Doc D | #30 Commitment | Doc D voice + commitment text → Relationship Adapter genera relational_block. Indirecto. |
| B.5 | #2 Style Norm | #13 Guardrails | Normalizer después de guardrails. Si guardrails corrigió, normalizer puede alterar la corrección (emoji strip). |
| B.6 | #2 Style Norm | #15 Response Fixes | Fixes antes de normalizer. Fixes puede cambiar punctuation que normalizer evalúa. |
| B.7 | #2 Style Norm | #16 Message Splitter | Normalizer cambia longitud → afecta split points. Normalizer ejecuta antes que splitter (si splitter post-format). |
| B.8 | #4 RAG | #7 Episodic | Budget: RAG section vs episodic en recalling. Ambos HIGH/dynamic. Si ambos ON, budget squeeze. |
| B.9 | #4 RAG | #8 DNA | Budget: RAG vs DNA (recalling). Indirecto. |
| B.10 | #4 RAG | #13 Guardrails | RAG inyecta product info → LLM usa → guardrails valida URLs/prices en response. Cadena indirecta. |
| B.11 | #6 Memory | #7 Episodic | Triple memory injection (W8 4.1) + redundancia (W8 2.1). Memory facts + episodic snippets del mismo lead. | 
| B.12 | #6 Memory | #19 Frustration | Memory facts y frustration note en recalling. Complementarios, no conflictivos. |
| B.13 | #6 Memory | #20 Context Detector | Memory facts y context notes en recalling. Complementarios. |
| B.14 | #6 Memory | #27 PersonaCompiler | PersonaCompiler batch consume memory data (indirectamente vía feedback) para compilar Doc D. Cadena larga. |
| B.15 | #7 Episodic | #19 Frustration | Episodic + frustration ambos en recalling. Si ambos ON. |
| B.16 | #7 Episodic | #20 Context Detector | Episodic + context notes en recalling. |
| B.17 | #8 DNA | #19 Frustration | DNA + frustration en recalling. DNA dice "warm", frustration dice "frustrado". |
| B.18 | #8 DNA | #20 Context Detector | DNA + context notes en recalling. |
| B.19 | #9 Conv State | #6 Memory | State + memory en recalling. |
| B.20 | #9 Conv State | #23 Relationship | State define fase, Relationship define score. Ambos informan contexto relacional. State en recalling, scorer en metadata. |
| B.21 | #10 Calibration | #17 Length Controller | Calibration tiene length config? No directamente. Length Controller lee `length_by_intent.json` y message_type. Relación indirecta vía creator config. |
| B.22 | #11 QR | #12 Anti-Echo | Echo (A3) ANTES de QR (7a2c). Si echo no disparó, QR opera normal. Si echo reemplazó, QR opera sobre pool response (<15 chars, no tiene preguntas). No conflicto. |
| B.23 | #11 QR | #13 Guardrails | QR (7a2c) ANTES de guardrails (7b). QR elimina pregunta, guardrails valida response sin pregunta. Ordering OK. |
| B.24 | #14 Output Validator | #17 Length Controller | Validator (7a) ANTES de LC (7c). Validator corrige links → puede cambiar longitud → LC ajusta. |
| B.25 | #15 Response Fixes | #17 Length Controller | Fixes (7a2) ANTES de LC (7c). Fixes puede cambiar longitud. |
| B.26 | #19 Frustration | #22 Intent | Ambos analizan el mismo mensaje. Frustration: señales emocionales. Intent: tipo de mensaje. Independientes pero si frustración alta, intent puede ser mal clasificado (mensaje confuso). |
| B.27 | #19 Frustration | #23 Relationship | Frustración actual vs score relación histórico. No interactúan directamente. |
| B.28 | #20 Context Detector | #22 Intent | Context (Guard 4b) antes de Intent (context phase). Context detecta B2B/sarcasm. Intent clasifica tipo. Si sarcasmo, intent puede clasificar mal. |
| B.29 | #20 Context Detector | #23 Relationship | Context notes vs relationship score. Ambos informan contexto pero por diferentes vías. |
| B.30 | #22 Intent | #23 Relationship | Intent clasifica mensaje, Scorer clasifica relación. Independientes pero ambos alimentan context assembly. |
| B.31 | #25 Creator Style Loader | #2 Style Normalizer | Style Loader carga baselines que Normalizer lee. Misma fuente (creator_profiles). Coupling de datos (ya cubierto por A.4 Doc D × Normalizer). |
| B.32 | #26 FeedbackCapture | #28 StyleRetriever | FeedbackCapture almacena copilot_approve → alimenta gold_examples quality scoring. Cadena larga. |
| B.33 | #27 PersonaCompiler | #2 Style Normalizer | Si PersonaCompiler cambia Doc D → baselines cambian → Style Normalizer targets cambian. Cadena larga. |
| B.34 | #29 Confidence | #12 Anti-Echo | Confidence ve response post-echo. Si echo reemplazó, score del pool response. |
| B.35 | #29 Confidence | #17 Length Controller | Confidence ve response post-LC truncation. Score refleja versión truncada. |
| B.36 | #30 Commitment | #6 Memory | Commitment via Adapter + Memory facts. Ambos en recalling. Posible duplicación de compromiso. (Complementa A.10). |
| B.37 | #30 Commitment | #8 DNA | Commitment via Adapter + DNA en recalling. Ambos dimensión relacional. |
| B.38 | #30 Commitment | #9 Conv State | Commitment + State en recalling. Complementarios. |
| B.39 | #23 Relationship | #30 Commitment | Relationship score + commitments. Scorer no lee commitments directamente. |
| B.40 | #3 Pool Matcher | #22 Intent | Pool matching (detection phase) uses message text. Intent (context phase) classifies intent. Si pool match, intent phase no se ejecuta. No conflicto en misma request pero ambos "clasifican" el mensaje. |

---

## Resumen cuantitativo

| Categoría | Pares | % de 435 |
|-----------|-------|----------|
| **MISMO SISTEMA** | 2 | 0.5% |
| **Retenidos ALTA** | 25 | 5.7% |
| **Retenidos MEDIA** | 38 | 8.7% |
| **Retenidos BAJA** | 40 | 9.2% |
| **Total retenidos** | **103** | **23.7%** |
| **Descartados — dominios disjuntos** | 316 | 72.6% |
| **Descartados — MISMO SISTEMA** | 2 | 0.5% |
| **Descartados �� sistema OFF × sistema OFF** | 14 | 3.2% |
| **Total descartados** | **332** | **76.3%** |

### Distribución por tipo de descarte

| Razón descarte | Pares |
|----------------|-------|
| Dominios completamente disjuntos (fases distintas, sin datos compartidos) | 248 |
| Ninguno inyecta al prompt Y ninguno modifica output (Group D×E, E×E internos) | 42 |
| Pool matching short-circuit (cuando #3 actúa, los otros no ejecutan) | 26 |
| Ambos sistemas OFF → interacción teórica, no evaluable | 14 |
| MISMO SISTEMA | 2 |

### Distribución retenidos por grupo de origen

| Cross | Pares ALTA | MEDIA | BAJA | Total |
|-------|-----------|-------|------|-------|
| A×A | 7 | 4 | 1 | 12 |
| A×B | 6 | 7 | 4 | 17 |
| A×C | 2 | 7 | 8 | 17 |
| A×D | 3 | 3 | 3 | 9 |
| A×E | 1 | 2 | 3 | 6 |
| B×B | 3 | 6 | 6 | 15 |
| B×C | 0 | 0 | 2 | 2 |
| B×E | 1 | 2 | 3 | 6 |
| C×C | 0 | 1 | 5 | 6 |
| C×D | 0 | 0 | 2 | 2 |
| D×D | 2 | 1 | 0 | 3 |
| D×E | 0 | 1 | 1 | 2 |
| E×E | 0 | 0 | 0 | 0 |
| **Total** | **25** | **38** | **40** | **103** |

---

## Clusters densos para Fases 3-6

Los 103 pares se agrupan naturalmente en 7 clusters de interacción:

1. **Recalling Block** (21 pares): #6, #7, #8, #9, #19, #20, #30 — todos escriben a la misma sección `recalling`
2. **Style Dimension** (12 pares): #1, #2, #8, #10, #25, #27, #28 — todos afectan estilo del output
3. **Budget Competition** (8 pares): #1 vs {#4, #6, #7, #10} — secciones top-level compitiendo por ARC1 budget
4. **Postproc Length Chain** (10 pares): #2, #11, #12, #13, #16, #17 — secuenciales que afectan longitud
5. **Detection→Context** (10 pares): #19, #20, #22, #23 → {#4, #6, #8, #10} — señales de detección que alimentan ensamblaje
6. **Persona Pipeline** (4 pares): #25, #26, #27, #1 — pipeline offline de actualización de Doc D
7. **Confidence Scoring** (5 pares): #29 × {#11, #12, #13, #17, #25} — scorer que evalúa resultado de la cadena

---

## Priorización para Fases 3-6

| Fase | Scope | Pares ALTA | Total pares | Tiempo estimado |
|------|-------|-----------|-------------|----------------|
| Fase 3 (Grupo A prompt-injection) | Clusters 1, 2, 3 + cross A×A | 10 | ~35 | 2-3h |
| Fase 4 (Grupo B postprocessing) | Cluster 4 + cross B×B, A×B | 6 | ~25 | 1.5-2h |
| Fase 5 (Grupo C detection) | Cluster 5 + cross C×C, C×A | 2 | ~20 | 1-1.5h |
| Fase 6 (Grupos D+E) | Clusters 6, 7 + cross D×E | 4 | ~15 | 1-1.5h |

---

*Pre-filtrado completado. 103 pares retenidos de 435 posibles (24%). 2 pares descartados por MISMO SISTEMA, 332 por dominios disjuntos/OFF.*
