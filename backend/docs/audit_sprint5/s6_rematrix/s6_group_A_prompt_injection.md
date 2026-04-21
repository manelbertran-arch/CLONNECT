# S6 Re-matriz — Fase 3: Group A Prompt-Injection Analysis

**Fecha:** 2026-04-21
**Auditor:** Opus 4.6
**Branch:** `audit/s6-rematrix`
**Scope:** 41 pairs across 3 clusters (Recalling Block, Style Dimension, Budget Competition)

---

## Key Structural Finding: ARC1 × Recalling Block Accounting Gap

**ARC1 does NOT arbitrate within the recalling block.** All 7 sub-systems (#6 Memory, #7 Episodic, #8 DNA, #9 Conv State, #19 Frustration, #20 Context, #30 Commitment) concatenate freely into a single text blob via `_build_recalling_block()` (context.py:1335-1360).

The BudgetOrchestrator treats recalling as ONE section:
- Priority: HIGH (context.py:573)
- Cap: 400 tokens (section.py:46 `SECTION_CAPS["recalling"]`)
- Value: dynamic ≈ 0.80 (section.py:65)

**Budget charge:** `effective_tok = min(actual_tokens, cap_tokens)` (orchestrator.py:93). Content is NOT truncated for non-CRITICAL sections — only the budget charge is capped.

**Real-world impact:** An active lead's recalling block is typically 800-2000 chars (200-500 tokens), but can reach 3000-4000 chars (750-1000 tokens) with rich relationship data. ARC1 charges only 400 tokens regardless. This means:
1. Other sections see more budget headroom than reality.
2. The prompt is consistently over-budget by 100-600 tokens (5-15% of the 4000-token budget).
3. All competition between recalling sub-systems is completely unmitigated.

**Ordering within recalling block** (context.py:1353):
```
Position 1: relational_block    (RelationshipAdapter → #30 Commitment path)
Position 2: dna_context          (#8 DNA Engine)
Position 3: state_context        (#9 Conv State)
Position 4: episodic_context     (#7 Episodic, OFF)
Position 5: frustration_note     (#19 Frustration)
Position 6: context_notes_str    (#20 Context + Length Hints + Question Hints)
Position 7: memory_context       (#6 Memory, LAST — intentional high-attention position)
```

Per Liu et al. 2023 "Lost in the Middle" (cited at context.py:1351): positions 1 and 7 receive highest LLM attention. Positions 3-5 are the attention valley.

---

## Cluster 1: Recalling Block (21 pairs)

Systems: #6, #7, #8, #9, #19, #20, #30.
All write to the same ARC1 section. Zero internal budget mechanism.

### Structural interactions (always present when both systems ON)

#### R.1 — #6 Memory × #8 DNA Engine

| Field | Value |
|-------|-------|
| Type | **Tipo 2 (redundancia parcial)** |
| Severity | LOW |
| W8 ref | — (NEW post-Sprint 5) |
| Status | LIVE |

**Mechanism:** ARC2 memory `interest` type outputs "Intereses: yoga, meditación" (context.py:270-273). DNA `recurring_topics` outputs "Temas frecuentes: yoga, meditación" (dm_agent_context_integration.py:209-211). Relationship state also overlaps: ARC2 `relationship_state` type vs DNA `relationship_type` field.

**Partial mitigation:** `format_unified_lead_context()` (dm_agent_context_integration.py:309-312) deduplicates lead interests against DNA recurring_topics — but this operates WITHIN the DNA block only. It does NOT dedup against `memory_context`. Both independently appear in the recalling block.

**Position:** DNA at position 2, Memory at position 7 (highest attention). Memory wins the attention battle.

**Evidence:**
- ARC2 type labels: context.py:267-273
- DNA recurring topics: dm_agent_context_integration.py:209-211
- Intra-DNA dedup only: dm_agent_context_integration.py:308-312
- No cross-source dedup: context.py:1353 (pure concatenation)

---

#### R.2 — #6 Memory × #9 Conv State

| Field | Value |
|-------|-------|
| Type | **Tipo 2 (redundancia parcial) + Tipo 6 (complementariedad)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Both independently extract lead personal data:
- ARC2 `identity` memories: "nombre, edad, situación" (via nightly LLM extract)
- Conv State `SalesFunnelContext`: name, age, situation, goal (via real-time regex, conversation_state.py:315-373)

**Unique value:** Conv State provides sales phase instructions (conversation_state.py:85-130) — this data exists ONLY in state_context. Memory provides historical facts that state doesn't track. The overlap is limited to basic personal data.

**Evidence:**
- Conv State name extraction: conversation_state.py:345-356
- Conv State age extraction: conversation_state.py:327-341
- ARC2 identity type: context.py:267 (`_ARC2_TYPE_LABELS["identity"]`)
- No cross-dedup: context.py:1353

---

#### R.3 — #6 Memory × #30 Commitment Tracker

| Field | Value |
|-------|-------|
| Type | **Tipo 2 (redundancia)** |
| Severity | LOW |
| W8 ref | W8 2.10 — **PERSISTE** |
| Status | LIVE |

**Mechanism:** The same commitment appears via two independent paths:
1. ARC2 memory extracts "te paso el link mañana" as `intent_signal` fact → `memory_context` (position 7)
2. Commitment Tracker regex detects "te paso" pattern (commitment_tracker.py:40-41) → stores as pending → `get_pending_text()` (commitment_tracker.py:247-301) → RelationshipAdapter `commitment_text` param (context.py:1480) → `relational_block` (position 1)

**No cross-dedup:** Memory extraction (nightly LLM) and commitment detection (real-time regex) operate independently. Both are injected into the recalling block without mutual awareness.

**Evidence:**
- Commitment regex patterns: commitment_tracker.py:38-55
- ARC2 intent_signal type: context.py:275 (`_ARC2_TYPE_PRIORITY`)
- Commitment → RelationshipAdapter: context.py:1480 (`commitment_text=commitment_text`)
- RelationshipAdapter injection: relationship_adapter.py:311-317
- Recalling block concat: context.py:1353

---

#### R.4 — #8 DNA × #9 Conv State

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento implícito)** |
| Severity | MEDIUM |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** DNA and Conv State can send contradictory behavioral signals:
- DNA `_format_dna_for_prompt()` (dm_agent_context_integration.py:172-181): `FAMILIA → "NUNCA vender"`, `AMISTAD_CERCANA → "confianza alta"`
- Conv State `PHASE_INSTRUCTIONS` (conversation_state.py:104-110): `PROPUESTA → "Menciona el producto que encaja"`, `CIERRE → "Da el link de compra"`

**Conflict scenario:** Lead classified as FAMILIA in DNA (because creator's real family member) but conv state advances to PROPUESTA (message count triggers, conversation_state.py:399-400). DNA says "NUNCA vender", state says "present product".

**Partial mitigation:** When `has_doc_d=True` (which is the normal case for configured creators), RelationshipAdapter enters data-only mode (relationship_adapter.py:284-287) — tone/style instructions from the adapter are suppressed. But DNA block itself still carries relationship hints via `_format_dna_for_prompt()` line 182 (`hint = rel_hints.get(rel_type, ...)`), and Conv State still has full phase instructions.

**No resolution mechanism:** The LLM receives both signals in recalling (positions 2 and 3, adjacent) without priority annotation.

**Evidence:**
- DNA FAMILIA hint: dm_agent_context_integration.py:173 (`"NUNCA vender"`)
- State PROPUESTA: conversation_state.py:104-110 (`"Menciona el producto"`)
- has_doc_d data-only: relationship_adapter.py:284-287
- DNA hint still present: dm_agent_context_integration.py:181-182

---

#### R.5 — #9 Conv State × #19 Frustration

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento implícito)** |
| Severity | MEDIUM |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Conv State phase instructions and frustration note can directly contradict:
- State PROPUESTA/CIERRE: "Menciona el producto", "Da el link de compra" (conversation_state.py:104-120)
- Frustration level 2+: "No vendas ahora" (context.py:1372-1376)

**Conflict scenario:** Lead says something frustrated during PROPUESTA phase. Conv State won't transition away from PROPUESTA (frustration is not a transition trigger — conversation_state.py:375-422 only transitions on intent/message-count, not emotion). The LLM receives "sell" + "don't sell" simultaneously.

**De facto resolution:** Frustration's explicit "No vendas ahora" is a stronger signal than phase instructions' implicit "Menciona el producto", so frustration likely wins in practice. But this is an undocumented assumption about LLM behavior, not a formal mechanism.

**Position:** State at position 3 (attention valley), Frustration at position 5 (also valley). Neither has a positional advantage.

**Evidence:**
- Frustration no-sell: context.py:1375 (`"No vendas ahora"`)
- PROPUESTA sell: conversation_state.py:108 (`"Menciona el producto"`)
- No frustration-based transitions: conversation_state.py:375-422

---

#### R.6 — #9 Conv State × #30 Commitment

| Field | Value |
|-------|-------|
| Type | **Tipo 2 (redundancia parcial) + Tipo 3 (acoplamiento menor)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Conv State tracks `link_sent=True` (conversation_state.py:429-430) and generates reminder "Ya enviaste el link de compra" (conversation_state.py:441-442). Commitment Tracker might simultaneously have "te paso el link" as a pending item if not marked fulfilled.

**Conflict:** State says "you already sent the link", commitment says "you have a pending delivery: send link". LLM receives contradictory info about the same action.

**Root cause:** Commitment fulfillment detection (commitment_tracker.py:303-335 `mark_fulfilled()`) requires explicit API call — it doesn't auto-detect from state tracking.

**Evidence:**
- State link tracking: conversation_state.py:428-430
- State reminder: conversation_state.py:441-442
- Commitment pending text: commitment_tracker.py:247-301

---

### Contradictory signal pairs (conditional on input)

#### R.7 — #6 Memory × #19 Frustration

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad) con riesgo Tipo 3** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Memory provides historical facts ("le interesa comprar el curso"), frustration provides current emotional state ("lead frustrado, no vendas"). Complementary in isolation. Conditionally contradictory when memory has purchase-intent signals that conflict with frustration's "no vendas".

**Position advantage:** Memory at position 7 (highest attention), frustration at position 5 (attention valley). In a conflict, the LLM pays more attention to memory.

---

#### R.8 — #8 DNA × #19 Frustration

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento implícito leve)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** DNA warmth/trust signals (dm_agent_context_integration.py:169-187: `trust_score=0.8`, `AMISTAD_CERCANA`) encourage warm, informal tone. Frustration note says "lead frustrado — no vendas, prioriza resolver" (context.py:1372-1381). These aren't contradictory (you can be warm while problem-solving) but pull tone in different directions (informal vs careful).

---

#### R.9 — #19 Frustration × #30 Commitment

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento condicional)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Frustration says "no vendas ahora" (context.py:1375). Commitment says "IMPORTANTE: menciona o cumple estos compromisos" (relationship_adapter.py:315-317). If a pending commitment is sales-related ("te paso el link del curso"), the LLM must choose between fulfilling the commitment (sales action) or respecting frustration (no sales).

---

### Complementary pairs (low-risk)

These pairs share the recalling block but provide complementary, non-conflicting data. Listed for completeness.

| Pair | Systems | Type | Evidence |
|------|---------|------|----------|
| R.10 | #6 Memory × #20 Context | Tipo 6 | Historical facts + current situational context. No overlap. context.py:1353 |
| R.11 | #8 DNA × #20 Context | Tipo 6 | Relationship style + current context signals. context.py:1353 |
| R.12 | #8 DNA × #30 Commitment | Tipo 6 | Relationship context + pending actions. dm_agent_context_integration.py:149-237, commitment_tracker.py:247-301 |
| R.13 | #9 Conv State × #20 Context | Tipo 6 | Sales phase + situational signals. conversation_state.py:85-130, context.py:1384-1390 |
| R.14 | #19 Frustration × #20 Context | Tipo 6 | Emotional + situational detection. Both from detection phase, non-overlapping. context.py:1362-1390 |
| R.15 | #20 Context × #30 Commitment | Tipo 6 | Situational signals + pending actions. No conflict mechanism. |

### DORMANT pairs (#7 Episodic OFF)

#7 Episodic Memory is OFF (`ENABLE_EPISODIC_MEMORY=false`, context.py:12). These 6 pairs would activate if re-enabled.

| Pair | Systems | Projected Type | Key Risk |
|------|---------|---------------|----------|
| R.16 | #6 Memory × #7 Episodic | **Tipo 2 + Tipo 4** | W8 bugs 2.1, 2.2, 4.1 would RESURFACE. No cross-source dedup between ARC2 facts and episodic snippets. `_episodic_search()` (context.py:179-184) deduplicates against recent_history but NOT against ARC2 memories. |
| R.17 | #7 Episodic × #8 DNA | Tipo 2 + Tipo 4 | Episodic raw snippets overlap with DNA recurring_topics. Recalling block grows by ~750 chars. |
| R.18 | #7 Episodic × #9 Conv State | Tipo 2 | Lead personal data (name, goal) could appear in both. Low-risk. |
| R.19 | #7 Episodic × #19 Frustration | Tipo 6 | Past context + current emotion. Complementary. |
| R.20 | #7 Episodic × #20 Context | Tipo 6 | Past snippets + current context. Complementary. |
| R.21 | #7 Episodic × #30 Commitment | Tipo 6 | Past snippets + pending actions. Low overlap. |

**W8 regression risk:** Re-enabling episodic without adding cross-source dedup against ARC2 would recreate the triple memory injection (W8 4.1). Recommendation: if episodic is re-enabled, implement cross-source dedup in `_build_recalling_block()` BEFORE activation.

---

### Cross-recalling pairs (recalling system × external system)

#### X.1 — #8 DNA × #23 Relationship Scorer (pre-filter A.11)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento implícito)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** DNA stores `relationship_type` persistently in RelationshipDNA table. Scorer computes `relationship_score` and `category` fresh each request from user messages + lead facts + days span (context.py:1200-1206). These are independent calculations that can diverge.

**Impact path:** DNA text in recalling says "Relación: DESCONOCIDO" while scorer might set `is_friend=True` (category=PERSONAL, score>0.8). Product suppression via `is_friend` (context.py:1221) applies, but DNA block in recalling still shows the relationship as new.

**Evidence:**
- DNA relationship_type: dm_agent_context_integration.py:167
- Scorer calculation: context.py:1200-1206
- is_friend from scorer: context.py:1221

---

#### X.2 — #6 Memory × #23 Relationship Scorer (pre-filter M.15)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento directo — fragile parsing)** |
| Severity | MEDIUM |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Scorer parses `memory_context` as raw text to extract lead facts (context.py:1169-1185). It iterates over `memory_context.split('\n')`, skips headers, strips markers, and passes lines as `{"fact_type": "general", "fact_text": line}` to the scorer.

**Fragility:** The parsing expects plain-text lines with `- •` bullet markers and `(hace N días)` time markers. ARC2 format uses `<memoria tipo="...">content</memoria>` XML tags (context.py:278-329). The scorer regex doesn't strip XML tags — it passes them through as part of the fact text. This works accidentally (scorer checks for personal markers like "madre", "amigo" inside the full line including tags) but any format change to memory output would break silently.

**Evidence:**
- Scorer parsing: context.py:1169-1185 (regex on raw text)
- ARC2 format: context.py:316-317 (`<memoria tipo="...">Label: content</memoria>`)
- No tag-aware parsing: context.py:1176-1185

---

## Cluster 2: Style Dimension (12 pairs)

Systems: #1 Doc D, #2 Style Normalizer, #8 DNA, #10 Calibration, #25 Creator Style Loader, #27 PersonaCompiler, #28 StyleRetriever.
These all affect the output's style/voice dimension.

### Identity signal interactions

#### S.1 — #1 Doc D × #8 DNA (pre-filter A.1)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento implícito) — Tipo 1 mitigado por ARC1** |
| Severity | LOW |
| W8 ref | W8 1.1 |
| Status | LIVE |

**ARC1 resolution:** Doc D is in `style` section (CRITICAL, context.py:570). DNA is inside `recalling` section (HIGH, context.py:573). These are SEPARATE ARC1 sections — no budget competition. Both are included (CRITICAL always included; recalling HIGH with value 0.80 easily fits budget).

**Mechanism:** Doc D defines creator's overall persona and communication style. DNA `_format_dna_for_prompt()` (dm_agent_context_integration.py:149-237) adds per-lead relationship hints including tone, vocabulary, and golden examples. Both tell the LLM "how to write" but from different angles (creator identity vs lead-specific adaptation).

**Mitigation:** When `has_doc_d=True`, RelationshipAdapter enters data-only mode (relationship_adapter.py:284-287). This prevents the adapter from injecting tone/style instructions that would duplicate Doc D. DNA block's `_format_dna_for_prompt()` still includes relationship hints but these are per-lead adaptations, not identity signals — CLAUDE.md's identity preservation principle applies to Doc D compression, not to per-lead adaptation.

**W8 delta:** W8 classified as Tipo 1 (competencia directa). Post-ARC1, downgraded to Tipo 3 — they're in different budget sections, and has_doc_d data-only mode reduces the conflict surface.

**Evidence:**
- Doc D → style section: context.py:570 (`Priority.CRITICAL, 1.00`)
- DNA → recalling section: context.py:573 (inside recalling block)
- has_doc_d mode: relationship_adapter.py:284-287

---

#### S.2 — #1 Doc D × #10 Calibration (pre-filter A.2)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento implícito)** |
| Severity | MEDIUM |
| W8 ref | W8 3.1 |
| Status | LIVE |

**ARC1 resolution:** Both CRITICAL — Doc D in `style` (context.py:570), Calibration in `few_shots` (context.py:571). Both always included. No budget competition.

**Mechanism:** Doc D says "write like this (description)". Few-shot examples say "write like this (demonstrations)". If calibration data is stale or misaligned with current Doc D, the LLM receives contradictory style signals.

**CLAUDE.md identity principle:** Both Doc D and few-shots are identity-defining signals that MUST NOT be compressed or rewritten (CLAUDE.md rule). This means both are guaranteed to be present at full fidelity. The risk is not compression but COHERENCE between the two identity signals.

**Coherence guarantee:** Calibration few-shots come from `get_few_shot_section()` which loads from the creator's calibration data (context.py:1275-1281). These are mined from the creator's real conversations. If the mining pipeline and Doc D are both derived from the same creator data, they're naturally aligned. Misalignment risk is when Doc D is manually edited without re-mining calibration.

**Evidence:**
- Doc D → CRITICAL: context.py:570
- Few-shots → CRITICAL: context.py:571
- Both identity signals: CLAUDE.md rule on identity preservation
- Calibration loading: context.py:1268-1285

---

#### S.3 — #1 Doc D × #25 Creator Style Loader (pre-filter A.3)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (dependency coupling)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** #25 is the upstream provider: it loads the Doc D text from DB and sets `agent.style_prompt`. #1 is the consumer: `_assemble_context_new()` reads `inp.style_prompt` (context.py:570, which is `agent.style_prompt` per context.py:1518). If #25 fails or loads stale data, #1 operates with wrong/empty style prompt.

**This is a dependency, not a competition.** Standard supplier→consumer coupling. Failure mode is well-handled: if `agent.style_prompt` is empty, the section is skipped (context.py:559 `if not content: return None`).

---

#### S.4 — #1 Doc D × #2 Style Normalizer (pre-filter A.4)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento por datos compartidos)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Doc D defines baseline emoji/exclamation rates as part of the creator persona. Style Normalizer (postprocessing.py:382-388) reads `baseline_metrics` and `bot_natural_rates` to enforce those baselines after LLM generation. If Doc D is updated (e.g., via PersonaCompiler) without re-mining baselines, the normalizer enforces outdated rates.

**Cross-phase:** Doc D is prompt-injection phase, Style Normalizer is postprocessing phase. They don't compete for prompt space — they operate on different dimensions (input vs output).

**Evidence:**
- Style Normalizer: postprocessing.py:382-388
- Baseline metrics: loaded from creator profile in style_normalizer.py

---

### DORMANT style pairs

#### S.5 — #10 Calibration × #28 StyleRetriever (pre-filter A.15)

| Field | Value |
|-------|-------|
| Type | **Tipo 2 (redundancia) — DORMANT** |
| Severity | — |
| W8 ref | W8 2.6 |
| Status | #28 OFF (ENABLE_GOLD_EXAMPLES=false) |

**If both ON:** Dual few-shot injection without mutual exclusion. Calibration injects in `few_shots` section (SYSTEM prompt). StyleRetriever would inject gold examples via `system_prompt_override` in USER message. No guard prevents both from running. W8 bug 2.6 would resurface.

---

#### S.6 — #25 Creator Style Loader × #27 PersonaCompiler (pre-filter A.23)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (dependency) — DORMANT** |
| Severity | — |
| W8 ref | W8 3.11 |
| Status | #27 OFF (ENABLE_PERSONA_COMPILER=false) |

**If both ON:** PersonaCompiler writes `[PERSONA_COMPILER:*]` sections into Doc D (batch process). Creator Style Loader reads Doc D. If compiler produces malformed output, it corrupts the Doc D that Style Loader serves.

---

#### S.7 — #1 Doc D × #27 PersonaCompiler (pre-filter M.7)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (dependency) — DORMANT** |
| Severity | — |
| Status | #27 OFF |

Compiler updates Doc D sections. If compiler error, Doc D is corrupted. Same dependency chain as S.6.

---

#### S.8 — #1 Doc D × #28 StyleRetriever (pre-filter B.3)

| Field | Value |
|-------|-------|
| Type | **Tipo 2 (redundancia potencial) — DORMANT** |
| Severity | — |
| Status | #28 OFF |

If both ON: gold examples should align with Doc D voice. Stale gold examples would contradict current Doc D.

---

### Cross-phase style pairs

#### S.9 — #2 Style Normalizer × #8 DNA (pre-filter M.8)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (cadena indirecta)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** DNA warmth/emoji signals → LLM generates emoji-heavy response → Style Normalizer strips emojis to baseline rate. The normalizer undoes what DNA encouraged. This isn't a bug — normalizer's purpose is to enforce creator baselines regardless of per-lead adaptation. But it means DNA's per-lead emoji modulation is partially nullified.

**Evidence:**
- DNA emojis: dm_agent_context_integration.py:199-200
- Normalizer enforcement: postprocessing.py:382-388

---

#### S.10 — #2 Style Normalizer × #10 Calibration (pre-filter M.9)

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad por datos compartidos)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

Both read from the same creator profile data source (baseline_metrics). Calibration uses it for few-shot selection, Normalizer uses it for rate enforcement. Shared data source, no conflict.

---

#### S.11 — #25 Creator Style Loader × #2 Style Normalizer (pre-filter B.31)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (cadena de datos)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

Style Loader provides the baselines that Normalizer reads. Same coupling as S.4 but through a different path. Subsume under S.4.

---

#### S.12 — #27 PersonaCompiler × #2 Style Normalizer (pre-filter B.33)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (cadena larga) — DORMANT** |
| Severity | — |
| Status | #27 OFF |

If PersonaCompiler changes Doc D → baselines change → Normalizer targets change. Three-step dependency chain.

---

## Cluster 3: Budget Competition (8 pairs)

These pairs involve top-level ARC1 sections competing for the 4000-token budget.
Competition is EXPLICIT and BY DESIGN — ARC1's greedy packing resolves it.

### CRITICAL vs non-CRITICAL (budget resolution clear)

#### B.1 — #1 Doc D (style) vs #4 RAG (rag) — pre-filter M.1

| Field | Value |
|-------|-------|
| Type | **Tipo 1 mitigado por ARC1** |
| Severity | NEGLIGIBLE |
| W8 ref | — |
| Status | LIVE |

**ARC1 resolution:** style=CRITICAL (always included, Pass 1). rag=HIGH (competes in Pass 2). If budget is tight, RAG is dropped while Doc D stays. This is by design — identity signals must not be sacrificed for RAG content.

**Budget math:** After CRITICAL sections (style:800 + few_shots:350 + override:variable), remaining ≈ 2850+ tokens. RAG cap=350 easily fits. Competition is theoretical under normal conditions.

---

#### B.2 — #1 Doc D (style) vs #6 Memory (recalling) — pre-filter M.2

| Field | Value |
|-------|-------|
| Type | **Tipo 1 mitigado por ARC1** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

Same as B.1. style=CRITICAL, recalling=HIGH. Doc D always wins. Budget math: recalling cap=400 fits after CRITICAL allocation.

---

#### B.3 — #1 Doc D (style) vs #7 Episodic (within recalling) — pre-filter M.3

| Field | Value |
|-------|-------|
| Type | **Tipo 1 mitigado por ARC1 — DORMANT** |
| Severity | — |
| Status | #7 OFF |

Same mechanism as B.2. Episodic is inside recalling section. DORMANT.

---

#### B.4 — #1 Doc D (style) vs #9 Conv State (within recalling) — pre-filter M.4

| Field | Value |
|-------|-------|
| Type | **Tipo 1 mitigado por ARC1** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

Same mechanism. Conv State is inside recalling section. Doc D always wins budget competition.

---

### Non-CRITICAL vs non-CRITICAL (intent-driven resolution)

#### B.5 — #4 RAG (rag) vs #6 Memory (recalling) — pre-filter M.13

| Field | Value |
|-------|-------|
| Type | **Tipo 1 (competencia por budget)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**ARC1 resolution (greedy by value/cost):**
- RAG: cap=350, value=dynamic (section.py:66 `0.75 if rag_signal else 0.30`, modified by intent: purchase×1.2, casual×0.5)
- Recalling: cap=400, value=dynamic (section.py:65 `0.80`)

**Scenarios:**
- `purchase_intent`: RAG value=0.75×1.2=0.90 > recalling 0.80 → RAG wins
- `casual`: RAG value=0.75×0.5=0.375 < recalling 0.80 → Recalling wins
- Default: RAG value=0.75, recalling value=0.80 → Recalling wins (marginally)

**Budget accounting gap:** Recalling charges 400 tokens but actual content may be 500-1000 tokens. RAG charges 350 tokens which is typically accurate. This gives recalling an unfair advantage — it gets included at a lower perceived cost.

**Evidence:**
- RAG value scoring: section.py:66, 76-79
- Recalling value scoring: section.py:65
- Greedy packing: orchestrator.py:58-70
- Budget cap vs reality: section.py:46 (`SECTION_CAPS["recalling"]: 400`) vs actual 500-1000 tokens

---

#### B.6 — #4 RAG (rag) vs #10 Calibration (few_shots) — pre-filter M.14

| Field | Value |
|-------|-------|
| Type | **Tipo 1 mitigado por ARC1** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

few_shots=CRITICAL (always included). RAG=HIGH (competes in Pass 2). No real competition.

---

#### B.7 — #4 RAG (rag) vs #7 Episodic (within recalling) — pre-filter B.8

| Field | Value |
|-------|-------|
| Type | **Tipo 1 mitigado por ARC1 — DORMANT** |
| Status | #7 OFF |

If episodic were ON, it would be inside the recalling section. RAG vs recalling competition same as B.5.

---

#### B.8 — #4 RAG (rag) vs #8 DNA (within recalling) — pre-filter B.9

| Field | Value |
|-------|-------|
| Type | **Tipo 1 mitigado por ARC1** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

DNA is inside recalling section. RAG vs recalling competition same as B.5. Resolved by intent-driven value scoring.

---

## Additional Group A pairs (not in main clusters)

### Detection→Prompt pairs

#### G.1 — #22 Intent × #10 Calibration (pre-filter A.21)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento directo)** |
| Severity | MEDIUM |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Intent classification drives few-shot example selection. `get_few_shot_section()` receives `detected_intent=intent_value` (context.py:1280). The function uses intent for stratified example selection (intent-matched examples preferred). If intent is misclassified, the LLM receives irrelevant few-shot examples.

**Impact:** Bad few-shot examples degrade style fidelity (S1) by showing the LLM wrong patterns. This is a single-point-of-failure coupling.

---

#### G.2 — #22 Intent × #4 RAG Semantic (pre-filter A.22)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento directo)** |
| Severity | MEDIUM |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Intent determines RAG signal routing (context.py:1066-1096). `_rag_signal` is built from `intent_value`. If intent says "product_inquiry" but the actual message is casual, RAG searches product KB and injects irrelevant product info.

---

#### G.3 — #1 Doc D × #17 Length Controller (pre-filter A.5)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento implícito)** |
| Severity | LOW |
| W8 ref | W8 3.4 |
| Status | LIVE |

**Mechanism:** Doc D may embed length preferences ("mensajes cortos", "respuestas breves"). Length Controller enforces its own config from `length_by_intent.json`. If they disagree, Length Controller wins (executes in postprocessing, step 7c).

---

#### G.4 — #1 Doc D × #11 Question Remover (pre-filter M.5)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (contradirección estilística)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Doc D may encourage engagement questions ("siempre pregunta algo para mantener la conversación"). Question Remover (postprocessing.py step 7a2c) removes questions exceeding the creator's `question_rate`. If Doc D encourages more questions than the mined baseline allows, QR removes what Doc D promoted.

---

#### G.5 — #1 Doc D × #12 Anti-Echo (pre-filter M.6)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (voice alignment risk)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Echo detector's A3 stage replaces echo responses with `short_response_pool` items from calibration (postprocessing.py:168-209). These pool responses should match Doc D voice. If pool is not aligned with Doc D, replacement breaks character.

---

#### G.6 — #10 Calibration × #12 Anti-Echo (pre-filter A.13)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (dependency)** |
| Severity | MEDIUM |
| W8 ref | W8 3.5 |
| Status | LIVE |

**Mechanism:** Echo detector A3 (postprocessing.py:168-209) uses `short_response_pool` from calibration. If calibration profile has no `short_response_pool` (empty or missing), echo replacement silently fails — the echoed response passes through. This is a hard dependency with no fallback.

**Evidence:**
- A3 echo detector: postprocessing.py:168-209 (reads `calibration.short_response_pool`)
- Calibration loading: from creator's calibration data

---

#### G.7 — #10 Calibration × #11 Question Remover (pre-filter A.14)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (dependency)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Question Remover reads `question_rate` from calibration profile. If calibration is missing question_rate, QR is effectively disabled for that creator.

---

#### G.8 — #29 Confidence × #11 Question Remover (pre-filter A.25)

| Field | Value |
|-------|-------|
| Type | **Tipo 5 (orden incorrecto — parcial)** |
| Severity | LOW |
| W8 ref | W8 1.2 (parcial) |
| Status | LIVE |

**Mechanism:** Confidence scorer (postprocessing.py:559) runs AFTER QR (step 7a2c). It evaluates the response without removed questions. If QR fails to remove an excessive question, confidence doesn't detect it — the score doesn't penalize question count.

---

#### G.9 — #23 Relationship × #4 RAG (pre-filter M.36)

| Field | Value |
|-------|-------|
| Type | **Tipo 5 (orden)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** RAG executes (context.py:~1100-1153) BEFORE Relationship Scorer sets `is_friend` (context.py:~1200-1221). If `is_friend=True`, products are suppressed from the prompt (`prompt_products = [] if inp.is_friend`). But RAG product results were already fetched and formatted. They're stripped at prompt assembly time (context.py:592), so the actual prompt is correct — but the RAG query and formatting work was wasted.

**Not a correctness bug.** Just token waste (RAG search + format for products that get stripped). The prompt itself is correct because product suppression happens at assembly time.

---

## W8 Baseline Comparison

| W8 Bug | Description | S6 Status | Change |
|--------|-------------|-----------|--------|
| W8 1.1 | Doc D × DNA competencia | **Downgraded** → Tipo 3, mitigated by ARC1 separate sections + has_doc_d data-only mode | Improved |
| W8 2.1 | Memory × Episodic redundancia | **DORMANT** — #7 OFF | Mitigated by disabling |
| W8 2.2 | Episodic duplicates | **DORMANT** — #7 OFF | Mitigated by disabling |
| W8 2.6 | Calibration × StyleRetriever dual injection | **DORMANT** — #28 OFF | Mitigated by disabling |
| W8 2.10 | Memory × Commitment redundancia | **PERSISTE** — same commitment via ARC2 + regex paths | Unchanged |
| W8 3.1 | Doc D × Calibration coherence | **PERSISTE** — both CRITICAL, no alignment guard | Unchanged |
| W8 3.4 | Doc D × Length Controller conflict | **PERSISTE** — LC always wins in postprocessing | Unchanged |
| W8 3.5 | Calibration × Anti-Echo dependency | **PERSISTE** — empty pool = silent echo pass-through | Unchanged |
| W8 3.11 | Style Loader × PersonaCompiler | **DORMANT** — #27 OFF | Mitigated by disabling |
| W8 4.1 | Triple memory injection | **DORMANT** — #7 OFF | Mitigated by disabling |

**New interactions found (not in W8):**
- **R.4**: #8 DNA × #9 Conv State contradictory signals (MEDIUM)
- **R.5**: #9 Conv State × #19 Frustration contradictory signals (MEDIUM)
- **X.2**: #6 Memory × #23 Scorer fragile parsing coupling (MEDIUM)
- **Budget accounting gap**: recalling cap=400 tokens vs actual 500-1000 tokens (structural)
- **G.1**: Intent → Calibration misclassification cascade (MEDIUM)
- **G.2**: Intent → RAG misrouting cascade (MEDIUM)

---

## Summary Statistics

| Category | Count |
|----------|-------|
| **Pairs analyzed** | 41 |
| **Tipo 1 (competencia directa)** | 0 (all downgraded to mitigated) |
| **Tipo 1 mitigado por ARC1** | 7 |
| **Tipo 2 (redundancia)** | 4 |
| **Tipo 3 (acoplamiento)** | 16 |
| **Tipo 5 (orden)** | 2 |
| **Tipo 6 (complementariedad)** | 7 |
| **DORMANT** | 10 |

| Severity | Count |
|----------|-------|
| MEDIUM | 6 (R.4, R.5, X.2, S.2, G.1, G.2) |
| LOW | 17 |
| NEGLIGIBLE | 8 |
| DORMANT | 10 |

### Top 6 findings (MEDIUM severity, actionable)

1. **R.4 — DNA × Conv State contradictory signals:** FAMILIA "NUNCA vender" vs PROPUESTA "presenta producto". No resolution mechanism.
2. **R.5 — Conv State × Frustration contradictory signals:** "Sell" vs "don't sell". No frustration-based phase transition.
3. **X.2 — Memory × Scorer fragile parsing:** Scorer regex-parses ARC2 XML output. Format change breaks silently.
4. **S.2 — Doc D × Calibration coherence:** Both CRITICAL identity signals, no alignment validation.
5. **G.1 — Intent → Calibration cascade:** Wrong intent → wrong few-shot examples → degraded style fidelity.
6. **G.2 — Intent → RAG cascade:** Wrong intent → wrong RAG signal → irrelevant product info injected.

### Structural finding (budget gap)

**Recalling block budget accounting gap:** ARC1 charges recalling at cap=400 tokens but content passes through at 500-1000 tokens. Budget utilization reported as ~60-80% but actual prompt may be 5-15% over budget. This doesn't cause errors (the prompt still works) but means the budget system under-reports actual cost.

---

*Fase 3 completada. 41 pairs analyzed across Recalling Block (21), Style Dimension (12), Budget Competition (8) clusters. 6 MEDIUM-severity findings, 4 persisting W8 bugs, 10 dormant pairs gated on feature flags.*
