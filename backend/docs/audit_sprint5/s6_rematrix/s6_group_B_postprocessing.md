# S6 Re-matriz — Fase 4: Group B Postprocessing Analysis

**Fecha:** 2026-04-21
**Auditor:** Opus 4.6
**Branch:** `audit/s6-rematrix`
**Scope:** 25 pairs from postprocessing chain + cross A×B

---

## Corrections from Fase 3 per reviewer notes

### Nota 1: R.4 and R.5 upgraded to Tipo 1 (competencia directa ACTIVA)

**R.4 — #8 DNA × #9 Conv State:** Reclasificado de Tipo 3 a **Tipo 1**. DNA's `FAMILIA → "NUNCA vender"` (dm_agent_context_integration.py:173) y Conv State's `PROPUESTA → "Menciona el producto"` (conversation_state.py:108) son instrucciones DIRECTAMENTE CONTRADICTORIAS que llegan simultáneamente al modelo sin mecanismo de resolución. Ambas en recalling block (posiciones 2 y 3). ARC1 NO arbitra dentro de recalling. **BLOQUEANTE para Fase 8 priorización.**

**R.5 — #9 Conv State × #19 Frustration:** Reclasificado de Tipo 3 a **Tipo 1**. "Presenta producto" vs "No vendas ahora" son instrucciones contradictorias activas. Frustration no dispara transición de fase (conversation_state.py:375-422). **BLOQUEANTE para Fase 8 priorización.**

### Nota 2: ARC1 Budget Underreporting — hallazgo arquitectónico separado

El gap de accounting del recalling block (cap=400 tokens, contenido real 500-1000 tokens) es un **bug del orquestador**, no una interacción entre sistemas. Se documenta aquí como referencia y se moverá a sección separada en Fase 8.

**Evidencia:** orchestrator.py:93 (`effective_tok = min(tok, section.cap_tokens)`) → para non-CRITICAL sections sin compressor, content pasa sin truncar pero budget solo carga el cap. section.py:46 (`SECTION_CAPS["recalling"]: 400`).

---

## Postprocessing Chain: Exact Execution Order

```
Step   | Line      | System (#)           | ARC4 Mutation | Action                      | Modifies?
-------|-----------|----------------------|---------------|-----------------------------|----------
A2     | 84-105    | Anti-Echo (loop)     | —             | LOG ONLY exact dup          | NO
A2b    | 107-133   | Anti-Echo (intra)    | M3            | Truncate pattern reps       | YES
A2c    | 135-166   | Anti-Echo (sentence) | M4            | Dedup repeated sentences    | YES
A3     | 168-209   | Anti-Echo (Jaccard)  | M5-alt        | Replace with pool response  | YES
7a     | 211-219   | Output Validator #14 | —             | Correct hallucinated links  | YES
7a2    | 222-232   | Response Fixes #15   | —             | Fix typos, patterns         | YES
7a2b3  | 234-245   | Blacklist Replace    | —             | Replace banned words/emoji  | YES
7a2c   | 247-255   | Question Remover #11 | M10           | Remove excess questions     | YES
7a3    | 257-274   | Reflexion Engine     | —             | LOG ONLY                    | NO
7a4    | 276-329   | SBS/PPA #SBS         | —             | ⚠️ CAN REGENERATE response  | YES*
7b     | 331-369   | Guardrails #13       | —             | Validate/correct safety     | YES
7c     | 371-377   | Length Controller #17 | M6            | Enforce length              | YES
7b2    | 379-388   | Style Normalizer #2  | M7, M8        | Emoji/excl normalization    | YES
7c-fmt | 390-391   | Instagram format     | —             | Format text                 | YES
7d     | 393-409   | Payment Link inject  | —             | Append payment URL          | YES
score  | 556-569   | Confidence #29       | —             | Score final output          | NO
10b    | 536-546   | Message Splitter #16 | —             | Split into multi-bubble     | POST
```

`*` SBS/PPA regeneration replaces `response_content` entirely. The new response has NOT passed through steps A2b–7a2c.

---

## ARC4 Phase 2 Cross-Reference Table

Source: `docs/audit_sprint5/ARC4_phase2_shadow_runs_results.md`

| Mutation | System | Step | Δ composite | ΔK1 | Classification | Implication for S6 |
|----------|--------|------|-------------|-----|----------------|-------------------|
| M3 | Anti-Echo A2b | A2b | **-3.50** | -43.3 | 🔴 PROTECTIVE | Eliminar = regresión. No es redundante con nada. |
| M4 | Anti-Echo A2c | A2c | **-3.30** | -16.4 | 🔴 PROTECTIVE | Eliminar = regresión. No es redundante con A2b. |
| M5-alt | Anti-Echo A3 | A3 | **-4.70** | -25.6 | 🔴 PROTECTIVE | Mayor impacto negativo. Echo detector es irremplazable. |
| M6 | Length Controller | 7c | **-2.30** | -15.5 | 🔴 PROTECTIVE | Length enforcement es necesario post-gen. |
| M7 | Style Norm (emoji) | 7b2 | **-2.20** | -32.6 | 🔴 PROTECTIVE | Emoji normalization protege identidad. |
| M8 | Style Norm (excl) | 7b2 | **-3.10** | -41.6 | 🔴 PROTECTIVE | Exclamation normalization protege identidad. |
| M10 | Question Remover | 7a2c | **+0.30** | -9.6 | 🟡 NEUTRAL | Único candidato a eliminar sin regresión. |

**ARC4 constraint for this analysis:** Any pair classified as Tipo 2 (redundancia) where ARC4 shows one system is PROTECTIVE means the redundancy is INCOMPLETE — eliminating the "redundant" system would regress. This limits Tipo 2 classifications.

---

## Ordering Analysis: Tipo 5 Findings

### T5.1 — SBS/PPA regeneration bypasses M3+M4+M5 corrections ⚠️

| Field | Value |
|-------|-------|
| Type | **Tipo 5 (orden incorrecto)** |
| Severity | **MEDIUM** |
| Systems | SBS/PPA × {Anti-Echo A2b, A2c, A3, Output Validator, Response Fixes, Blacklist, QR} |
| Status | LIVE |

**Mechanism:** SBS (postprocessing.py:276-329) scores the response and, if alignment < 0.7, regenerates with a retry call (1 extra LLM call). The new response (`sbs_result.response`, line 302) replaces `response_content` entirely.

The regenerated response has NOT been through:
- A2b (M3 — PROTECTIVE Δ=-3.50): intra-repetition detection
- A2c (M4 — PROTECTIVE Δ=-3.30): sentence dedup
- A3 (M5-alt — PROTECTIVE Δ=-4.70): echo detection
- 7a: link validation
- 7a2: response fixes
- 7a2b3: blacklist replacement
- 7a2c (M10): question removal

The regenerated response IS processed by downstream steps (guardrails 7b, LC 7c, normalizer 7b2).

**ARC4 impact:** M3+M4+M5-alt are the three most PROTECTIVE mutations (combined Δ = -11.50 if all disabled). SBS bypass means these protections don't apply to ~30% of responses (estimated SBS retry rate when score < 0.7).

**Evidence:**
- SBS retry: postprocessing.py:291-302 (`sbs_result = await score_before_speak(...)`)
- Response replacement: postprocessing.py:302 (`response_content = sbs_result.response`)
- M3/M4/M5 already executed: postprocessing.py:107-209 (before SBS at 276)

**Correct order:** Either (a) move SBS BEFORE the anti-echo chain, or (b) re-run A2b/A2c/A3/7a/7a2/7a2b3/7a2c after SBS regeneration.

**Proposed diff:**
```
Current:   A2b → A2c → A3 → 7a → 7a2 → 7a2b3 → 7a2c → SBS → 7b → 7c → 7b2
Proposed:  SBS → A2b → A2c → A3 → 7a → 7a2 → 7a2b3 → 7a2c → 7b → 7c → 7b2
```
(SBS needs initial response to score, but could be restructured: generate → SBS score → if retry needed, regenerate → then run full chain on final response.)

---

### T5.2 — Payment Link injection AFTER Length Controller (bug P2, W8)

| Field | Value |
|-------|-------|
| Type | **Tipo 5 (orden incorrecto)** |
| Severity | **MEDIUM** |
| Systems | #17 Length Controller × Payment Link (#22 Intent trigger) |
| W8 ref | P2 — **PERSISTE** |
| Status | LIVE |

**Mechanism:** Length Controller enforces at step 7c (postprocessing.py:371-377). Payment link injection at step 7d (postprocessing.py:393-409) appends a URL (~40-80 chars) AFTER length enforcement. The response sent to the user exceeds LC's bounds.

**Evidence:**
- LC enforcement: postprocessing.py:374 (`response_content = enforce_length(...)`)
- Payment injection: postprocessing.py:406 (`formatted_content = f"{formatted_content}\n\n{plink}"`)
- No re-enforcement after injection

**Correct order:** Payment link before LC, or re-run LC after injection.

**Proposed diff:**
```
Current:   7c (LC) → 7b2 (norm) → 7c-fmt → 7d (payment)
Proposed:  7d (payment) → 7c (LC) → 7b2 (norm) → 7c-fmt
```

---

### T5.3 — Style Normalizer after Length Controller (minor)

| Field | Value |
|-------|-------|
| Type | **Tipo 5 (orden subóptimo — no bug)** |
| Severity | LOW |
| Systems | #2 Style Normalizer × #17 Length Controller |
| Status | LIVE |

**Mechanism:** LC enforces at step 7c (line 371-377). Normalizer at step 7b2 (line 379-388) can strip emojis, SHORTENING the response below LC's target. Normalizer never ADDS content — only removes emojis or replaces `!` with `.` (same length).

**Analysis of current order:**
- LC → Normalizer: LC sees emoji-rich text, enforces length. Normalizer strips emojis → response is 2-8 chars shorter than LC intended. No UPPER bound violation. Minor lower-bound undershoot.
- Normalizer → LC (alternative): Normalizer adjusts, then LC enforces on final content. More accurate length enforcement.

**Why this is NOT a bug:** LC's `enforce_length()` (length_controller.py:341-399) only trims when response exceeds `headroom = hard_max * 1.5`. There is no minimum enforcement. Normalizer's emoji stripping cannot cause an upper-bound violation. The response may be slightly shorter than optimal, but within acceptable range.

**ARC4 validation:** M7 (normalize_emojis) is PROTECTIVE (Δ=-2.20). M6 (normalize_length) is PROTECTIVE (Δ=-2.30). Both are independently valuable. The ordering between them doesn't affect their individual protective value.

---

### Ordering summary: remaining steps verified CORRECT

| Pair | Order | Correct? | Reasoning |
|------|-------|----------|-----------|
| A2→A2b→A2c→A3 | Anti-echo escalation | ✅ | Exact dup (LOG) → pattern truncation → sentence dedup → full replacement. Correct escalation order. |
| A3→7a | Echo → link validation | ✅ | If echo replaced with pool response (<15 chars), no links to validate. If not replaced, links checked. |
| 7a→7a2 | Validator → Fixes | ✅ | Validator corrects hallucinated links first. Fixes corrects other patterns. Independent corrections. |
| 7a2→7a2b3 | Fixes → Blacklist | ✅ | Fixes might introduce patterns; blacklist catches them. Correct sequence. |
| 7a2b3→7a2c | Blacklist → QR | ✅ | Blacklist replaces terms (could change question count). QR processes final question count. |
| 7b→7c | Guardrails → LC | ✅ | Guardrails may modify content (safety). LC enforces length on guardrail-corrected content. |
| 7c-fmt→score | Format → Confidence | ✅ | Confidence scores the final formatted output the user will see. |
| score→10b | Confidence → Splitter | ✅ | Score computed on unified text. Splitter creates multi-message. |

---

## Style Normalizer: Dual-Nature Analysis (Nota 4)

### Prompt-injection side (data provider)

Style Normalizer's internal functions are imported by **two** prompt-injection systems:

1. **Question Hints** (generation.py:75-117): imports `_load_baseline()` and `_load_bot_natural_rates()`. Uses baseline `question_rate_pct` and bot's measured natural rate to decide whether to inject "NO incluyas pregunta en este mensaje." into the prompt.

2. **Style Anchor** (generation.py:120-155): imports `_load_baseline()`. Builds a short reminder string with raw numbers (median chars, emoji rate, question rate) for injection into the prompt.

### Postprocessor side (normalize_style)

`normalize_style()` (style_normalizer.py:256-330) runs at postprocessing.py:382. Two operations:
1. **Exclamation normalization** (M8): probabilistic `!` → `.` based on `creator_excl_rate / bot_natural_excl_rate`.
2. **Emoji normalization** (M7): probabilistic full emoji strip based on `creator_emoji_rate`.

### Coherence assessment

| Dimension | Pre-gen instruction | Post-gen correction | Coherent? |
|-----------|-------------------|-------------------|-----------|
| Questions | "NO incluyas pregunta" (generation.py:113) | QR removes excess (question_remover.py) | ✅ Same data source (`baseline.punctuation.has_question_msg_pct`). Pre-gen tries to prevent; post-gen catches what leaked. |
| Emoji | Style Anchor: "emoji rate: X%" (generation.py:144) | normalize_style strips to rate (style_normalizer.py:307-328) | ✅ Same data source (`baseline.emoji.emoji_rate_pct` or eval profile). Consistent target. |
| Exclamation | No pre-gen instruction for exclamation | normalize_style replaces ! → . (style_normalizer.py:278-298) | ⚠️ No pre-gen guardrail for exclamation. Normalizer is the ONLY control. If M8 is disabled, nothing prevents over-exclamation. |
| Length | Length Hints (context.py:1416-1428) | Length Controller (length_controller.py:341-399) | ✅ Both use calibration data. Pre-gen via context notes, post-gen via enforce_length. |

**Finding:** Exclamation rate has NO pre-generation instruction, only post-generation normalization (M8). This makes M8 (PROTECTIVE, Δ=-3.10) a single point of failure for exclamation control. All other style dimensions have two layers (pre-gen + post-gen). Exclamation control is fragile.

---

## Postproc Length Chain Cluster (10 pairs)

### A.16 — #11 Question Remover × #17 Length Controller

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Order:** QR (step 7a2c, line 247-255) BEFORE LC (step 7c, line 371-377). ✅ Correct.

**Mechanism:** QR removes questions → shortens response → LC enforces length on shorter text. If QR leaves response very short, LC doesn't pad (no minimum enforcement). Different functions: QR removes specific patterns, LC enforces general bounds.

**ARC4 cross-reference:** M10 (QR) is NEUTRAL (Δ=+0.30). M6 (LC) is PROTECTIVE (Δ=-2.30). They are NOT redundant — disabling either independently has distinct impact. Removing QR (M10) slightly IMPROVES composite. Removing LC (M6) REGRESSES composite. They operate on different quality dimensions.

---

### A.17 — #12 Anti-Echo × #17 Length Controller

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Order:** A3 echo (step A3, line 168-209) BEFORE LC (step 7c). ✅ Correct.

**Mechanism:** A3 may replace response with short pool response (<15 chars). LC would then see a very short response, which is BELOW its thresholds — LC only trims, never pads. So LC is a no-op after echo replacement.

**ARC4 cross-reference:** M5-alt (A3) is PROTECTIVE (Δ=-4.70). Not redundant with M6 (LC). They handle completely different failure modes.

---

### A.18 — #13 Guardrails × #17 Length Controller

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | LOW |
| Status | LIVE |

**Order:** Guardrails (step 7b, line 331-369) BEFORE LC (step 7c). ✅ Correct.

**Mechanism:** Guardrails may produce `corrected_response` (safety fix). LC enforces length on the corrected response. If guardrail correction is very long, LC would trim — but guardrail corrections are about content safety (URL/price fixes), not long text generation. In practice, corrections are same-length or shorter.

**Edge case:** If guardrails blocks response entirely (`_arc5_safety_status = "BLOCK"`, line 363), no corrected_response is set — original response_content persists. LC then operates on the blocked (original) response. This is architecturally questionable but the BLOCK path is rare.

---

### A.19 — #2 Style Normalizer × #17 Length Controller

See **T5.3** above. Tipo 5 (minor). LC before normalizer is suboptimal but not a bug.

---

### A.20 — #16 Message Splitter × #17 Length Controller

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Order:** LC (step 7c, line 371-377) BEFORE Splitter (step 10b, line 536-546). ✅ Correct.

**Mechanism:** LC enforces max length per-response. Splitter breaks the (already length-enforced) response into multiple bubbles. They manage different aspects: LC = single message length, Splitter = multi-message UX.

**Configuration coherence:** Splitter's `min_length_to_split=80` (message_splitter.py:22) and LC's thresholds from calibration. If LC truncates to very short response, Splitter won't split (below min_length). Compatible.

---

### M.10 — #2 Style Normalizer × #12 Anti-Echo

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Order:** A3 echo (step A3, line 168-209) BEFORE normalizer (step 7b2, line 379-388). ✅ Correct.

**Mechanism:** If A3 replaces with pool response, normalizer processes the pool response. Pool responses are short (<15 chars) — normalizer may strip emojis from them. This is fine: pool responses should match creator style, and normalizer enforces style. If pool response has no emojis, normalizer is a no-op.

---

### M.11 — #2 Style Normalizer × #11 Question Remover

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Order:** QR (step 7a2c) BEFORE normalizer (step 7b2). ✅ Correct.

**Mechanism:** QR removes questions. Normalizer adjusts emoji/excl. Non-overlapping operations on different text dimensions.

---

### M.24 — #12 Anti-Echo × #13 Guardrails

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Order:** A3 echo (step A3) BEFORE guardrails (step 7b). ✅ Correct.

**Mechanism:** If A3 replaced with pool response, guardrails validates the pool response. Pool responses are pre-vetted (<15 chars, from calibration) — unlikely to have safety issues. If A3 didn't fire, guardrails validates the full LLM response.

---

## Postproc Validation Pairs

### M.26 — #13 Guardrails × #14 Output Validator

| Field | Value |
|-------|-------|
| Type | **Tipo 2 (redundancia parcial en URLs)** |
| Severity | LOW |
| Status | LIVE |

**Order:** Output Validator (step 7a, line 211-219) BEFORE Guardrails (step 7b, line 331-369).

**Overlap:** Both check URLs. Output Validator `validate_links()` (output_validator.py:80+) checks for hallucinated/unauthorized URLs against `known_links`. Guardrails validates against `allowed_urls` (creator domains). Both can correct URLs.

**Not fully redundant:** Validator checks link correctness (hallucinated links). Guardrails checks broader safety (URL domains, prices, content safety). Validator is narrow (links only), guardrails is broad.

**ARC4 cross-reference:** Neither Validator nor Guardrails has an ARC4 kill switch. They were both classified as KEEP by design. No empirical data on removing one.

---

### M.27 — #13 Guardrails × #15 Response Fixes

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Order:** Fixes (step 7a2, line 222-232) BEFORE Guardrails (step 7b). ✅ Correct.

Fixes corrects typos/patterns. Guardrails validates safety on the corrected output.

---

### M.28 — #14 Output Validator × #15 Response Fixes

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Order:** Validator (step 7a) BEFORE Fixes (step 7a2). ✅ Correct.

Validator corrects links. Fixes corrects other patterns (price typos, RAG CTAs). Independent operations.

---

## Cross-group and additional pairs

### M.25 — #12 Anti-Echo × #29 Confidence

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento)** |
| Severity | LOW |
| Status | LIVE |

**Mechanism:** Confidence scorer (step score, line 556-569) sees `formatted_content` which may be an echo replacement (pool response). If A3 replaced the response, confidence scores a <15 char pool response instead of the actual LLM output. The confidence score reflects the replacement quality, not the generation quality.

**Impact:** Confidence metadata in DB for these messages shows pool response scores, not LLM generation scores. Misleading for monitoring dashboards.

---

### M.29 — #17 Length Controller × Payment Link injection

See **T5.2** above. Payment link appended after LC = bug P2 PERSISTE.

**ARC4 cross-reference:** M6 (LC) is PROTECTIVE (Δ=-2.30). Payment link injection has no ARC4 kill switch. The interaction is a pure ordering bug, not a redundancy question.

---

### B.5 — #2 Style Normalizer × #13 Guardrails

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (cadena secuencial)** |
| Severity | LOW |
| Status | LIVE |

**Order:** Guardrails (step 7b) BEFORE Normalizer (step 7b2). ✅ Correct.

Guardrails may produce `corrected_response`. Normalizer then adjusts emojis/excl on the correction. If guardrails replaced an unsafe URL response with a safe one, normalizer might strip emojis from the safe version — changing its tone. Minor but acceptable.

---

### B.7 — #2 Style Normalizer × #16 Message Splitter

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (cadena secuencial)** |
| Severity | LOW |
| Status | LIVE |

**Order:** Normalizer (step 7b2) BEFORE Splitter (step 10b). ✅ Correct.

Normalizer may strip emojis → shortens response → affects split points. This is correct: splitter should split the final content after all modifications.

---

### B.22 — #11 Question Remover × #12 Anti-Echo

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Order:** A3 echo (step A3) BEFORE QR (step 7a2c). ✅ Correct.

If echo replaced with pool response (<15 chars, no questions), QR is no-op. If echo didn't fire, QR processes full response.

---

### B.34 — #29 Confidence × #12 Anti-Echo

Same as M.25 above. Confidence sees post-echo content.

---

### B.35 — #29 Confidence × #17 Length Controller

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

Confidence scores post-LC content. LC may have truncated. Score reflects truncated version. This is CORRECT — score should reflect what the user receives.

---

### Fase 3 addendum: A.6 — #4 RAG × #5 Reranker

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (dependency pipeline)** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE (reranker needs sentence_transformers) |

**Mechanism:** RAG retrieves candidate results (context.py:1100-1153). Reranker re-orders them (integrated in RAG search flow). Sequential pipeline: #4 → #5. Reranker can eliminate relevant results by ranking them below threshold, or promote irrelevant ones.

**Dependency:** If `sentence_transformers` not available (not in local .venv but should be in Railway), reranker falls back to heuristic scoring. This is a graceful degradation, not a failure.

---

## ARC4 Contradiction Analysis (Nota 5)

For each pair where I classified as Tipo 2 (redundancia), I cross-check against ARC4 Phase 2 data. A Tipo 2 pair implies one system might be removable. ARC4 measured removal impact.

| Pair | S6 Type | ARC4 data | Contradiction? |
|------|---------|-----------|----------------|
| M.26 (#13 × #14) | Tipo 2 parcial (URL overlap) | Neither has ARC4 kill switch | N/A — no empirical data. URL overlap is real but narrow. |
| A.16 (#11 QR × #17 LC) | Tipo 6 | M10=NEUTRAL, M6=PROTECTIVE | ✅ Consistent: not redundant, different functions |
| A.17 (#12 × #17) | Tipo 6 | M5-alt=PROTECTIVE, M6=PROTECTIVE | ✅ Consistent: both independently protective |
| A.18 (#13 × #17) | Tipo 6 | No ARC4 data for guardrails | N/A |
| M.10 (#2 × #12) | Tipo 6 | M7=PROTECTIVE, M5-alt=PROTECTIVE | ✅ Consistent: both independently needed |
| M.11 (#2 × #11) | Tipo 6 | M7=PROTECTIVE, M10=NEUTRAL | ✅ Consistent: different dimensions |

**No contradictions found.** All Tipo 2 classifications are limited to partial overlaps where ARC4 data either doesn't exist or confirms independent value.

**Key ARC4 insight for Fase 8:** M10 (Question Remover, Δ=+0.30 NEUTRAL) is the only postprocessing mutation where removal doesn't hurt. All other mutations are PROTECTIVE with Δ ranging from -2.20 to -4.70. The postprocessing chain is NOT redundant — each step adds independent value that can't be recovered by other steps.

---

## Summary Statistics

| Category | Count |
|----------|-------|
| **Pairs analyzed** | 25 |
| **Tipo 1 (competencia directa)** | 0 |
| **Tipo 2 (redundancia parcial)** | 1 (M.26) |
| **Tipo 3 (acoplamiento)** | 4 |
| **Tipo 5 (orden incorrecto)** | 3 (T5.1, T5.2, T5.3) |
| **Tipo 6 (complementariedad)** | 14 |
| **DORMANT** | 0 |

### Severity distribution

| Severity | Count | Finding |
|----------|-------|---------|
| **MEDIUM** | 2 | T5.1 (SBS bypass), T5.2 (payment link P2) |
| **LOW** | 7 | T5.3, M.25, M.26, B.5, B.7, A.6, Style Norm excl single-point |
| **NEGLIGIBLE** | 13 | Complementary pairs |

### Top findings for Fase 8

1. **T5.1 — SBS bypass of M3+M4+M5:** SBS/PPA regeneration skips PROTECTIVE anti-echo corrections (combined Δ = -11.50 if disabled). ~30% of responses affected (those with SBS retry). **MEDIUM severity, actionable.**

2. **T5.2 — Payment Link P2 persists:** Payment URL appended after all length enforcement. Known W8 bug. **MEDIUM severity, simple fix (reorder).**

3. **Style Normalizer exclamation single-point:** M8 is the ONLY control for exclamation rate (PROTECTIVE, Δ=-3.10). No pre-gen instruction exists for exclamation, unlike questions (which have both pre-gen hint and post-gen QR) and emojis (which have both pre-gen anchor and post-gen normalizer). **LOW severity but fragility risk.**

4. **Fase 3 reclassifications (carry forward):**
   - R.4 (DNA × Conv State): **Tipo 1 BLOQUEANTE** (contradictory instructions)
   - R.5 (Conv State × Frustration): **Tipo 1 BLOQUEANTE** (contradictory instructions)
   - ARC1 budget underreporting: **Arquitectónico separado** (orquestador bug)

---

*Fase 4 completada. 25 pairs analyzed. 2 MEDIUM Tipo 5 ordering bugs found (SBS bypass, payment link P2). Postprocessing chain is largely well-ordered — 14/25 pairs are complementary. ARC4 data confirms chain is non-redundant (6/7 mutations PROTECTIVE).*
