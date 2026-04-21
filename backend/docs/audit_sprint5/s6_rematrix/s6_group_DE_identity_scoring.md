# S6 Re-matriz — Fase 6: Groups D+E Identity Pipeline + Scoring Analysis

**Fecha:** 2026-04-21
**Auditor:** Opus 4.6
**Branch:** `audit/s6-rematrix`
**Scope:** 7 new pairs + cross-references from Fase 3/4. Group D: #25 Creator Style Loader, #26 FeedbackCapture, #27 PersonaCompiler, #28 StyleRetriever. Group E: #29 Confidence Scorer.

---

## Identity Architecture: Persona Pipeline Chain (NOTA 4)

The clone's identity flows through a layered pipeline where each system reads/writes creator data at different frequencies:

```
OFFLINE (batch/scheduler)                        ONLINE (per-request)
========================                        ====================

  #26 FeedbackCapture ──┐
  (copilot actions,      │
   evaluator scores,     │    ┌── personality_docs ──── #25 Creator Style Loader ──→ style section
   preference pairs)     ├──→ │      (DB table)              (Priority 1: Doc D)       (CRITICAL, 1.00)
                         │    │                                                          context.py:570
  #27 PersonaCompiler ──┘    │
  (LLM evidence→Doc D,       │
   OFF by default)            │
                              │
  #26 FeedbackCapture ──┐    │
  (auto-creates gold    ├──→ gold_examples ──── #28 StyleRetriever ──→ generation.py
   examples when          │      (DB table)        (OFF by default)       gold_examples_section
   lo_enviarias ≥ 4)     │                                                generation.py:245-282
                          │
  #10 Calibration ────────────── calibration_data ──→ few_shots section
  (mined few-shots,              (separate pipeline)    (CRITICAL, 0.95)
   independent of above)                                context.py:571
```

### What each system does specifically

| # | System | Frequency | Reads | Writes | Status |
|---|--------|-----------|-------|--------|--------|
| **#25** Creator Style Loader | Per-request | `personality_docs` table (Doc D), legacy sources (fallback) | `agent.style_prompt` | **ON** |
| **#26** FeedbackCapture | Real-time + batch | Copilot actions, evaluator forms | `preference_pairs`, `evaluator_feedback`, `gold_examples` tables | **ON** |
| **#27** PersonaCompiler | Weekly scheduler | `preference_pairs`, `evaluator_feedback`, current Doc D | Updated Doc D → `personality_docs` | **OFF** (default) |
| **#28** StyleRetriever | Per-request (if ON) | `gold_examples` table (pgvector similarity) | `gold_examples_section` string | **OFF** (default) |
| **#10** Calibration | Per-request | Calibration data (separate mining pipeline) | `few_shot_section` string | **ON** |

### Redundancy analysis

**Functional overlap between identity systems:**

| Dimension | Doc D (#1 via #25) | Calibration (#10) | StyleRetriever (#28) | PersonaCompiler (#27) |
|-----------|------|------|------|------|
| **How to write** | Yes (descriptions) | Yes (demonstrations) | Yes (demonstrations) | Modifies Doc D |
| **Source** | Manual authoring + personality extraction | Mining pipeline (creator's real convos) | FeedbackCapture gold examples | LLM rewrite of Doc D from evidence |
| **Format** | Narrative text | Message examples | Message examples | Narrative text |
| **Section** | `style` (CRITICAL) | `few_shots` (CRITICAL) | generation.py `gold_examples_section` | → Doc D → `style` (CRITICAL) |
| **Active** | ON | ON | **OFF** | **OFF** |

**Is the pipeline necessary or can it be simplified to "Doc D + loader"?**

With #27 and #28 both OFF, the current active pipeline IS already "Doc D + loader":
1. Creator Style Loader (#25) reads Doc D from `personality_docs` → `agent.style_prompt`
2. Calibration (#10) provides few-shot examples independently (separate data source)
3. Both inject as CRITICAL priority

PersonaCompiler (#27) and StyleRetriever (#28) would add:
- **PersonaCompiler:** Automated Doc D updates from feedback evidence (removes need for manual Doc D edits)
- **StyleRetriever:** Intent-matched gold examples alongside calibration few-shots (dual few-shot injection)

**Cross-ref with identity preservation principle (CLAUDE.md commit 61a37641):**

> "Do NOT compress, summarize, reorder by importance, or rewrite identity-defining signals [...] while the model is not fine-tuned on creator data."

PersonaCompiler REWRITES Doc D sections via LLM. This potentially violates the principle even though it's "updating with evidence" rather than "compressing." The LLM rewrite can inadvertently lose subtle identity nuances that the original manual authoring captured. **Recommendation:** PersonaCompiler should remain OFF until post-fine-tuning, consistent with the distill decision (USE_DISTILLED_DOC_D=false).

StyleRetriever provides gold examples that are direct copies of approved responses — no compression or rewriting involved. It does NOT violate the identity preservation principle. However, it creates dual few-shot injection with Calibration (W8 bug 2.6, see S.5 in Fase 3).

**Simplification verdict:** Current "Doc D + Calibration" architecture is correct and sufficient for base model. PersonaCompiler → post-FT only. StyleRetriever → needs mutual exclusion guard with Calibration before reactivation.

---

## FeedbackCapture (#26): Deep Analysis (NOTA 2)

### What it captures

| Signal type | Source | Trigger | DB table |
|-------------|--------|---------|----------|
| Copilot actions | copilot/actions.py:129,261,408 | approve/edit/discard/manual_override | preference_pairs, evaluator_feedback |
| Evaluator scores | copilot/actions.py (feedback flow) | Human rates coherencia, lo_enviarias | evaluator_feedback |
| Gold examples | Auto-created | `lo_enviarias ≥ 4` | gold_examples (feedback_capture.py:303-311) |
| Preference pairs | Auto-created | reject+approve in same thread | preference_pairs |
| Historical mining | Batch scheduler | Library < 10 pairs | preference_pairs (feedback_capture.py:986-1017) |

### Active consumers in the generation pipeline

| Consumer | Status | Reads what | Evidence |
|----------|--------|-----------|----------|
| **#27 PersonaCompiler** | **OFF** | preference_pairs, evaluator_feedback | persona_compiler.py:744-764 |
| **#28 StyleRetriever** | **OFF** | gold_examples | style_retriever.py:102-146 via gold_examples_service |
| **LearningRulesService** | **OFF** (part of PersonaCompiler pipeline) | preference_pairs | learning_rules_service.py |

### Verdict: DATA ACCUMULATOR, not ORPHAN

FeedbackCapture is NOT orphaned — it's a deliberate **data collection system whose consumers are deactivated.** The architecture is:

1. **Now:** Capture data continuously (FeedbackCapture ON) → accumulate in DB tables
2. **Later:** Activate consumers (PersonaCompiler, StyleRetriever) when ready → data is pre-populated

This is the correct pattern for a system preparing for post-FT activation. The data accumulates whether or not consumers are active.

**But: 3 concerns:**

1. **Storage growth:** Preference pairs and gold examples grow unbounded. No TTL or archival policy found. With copilot active, this could be thousands of rows over months.
2. **Data quality drift:** FeedbackCapture captures quality signals against the BASE model. Post-fine-tuning, the model behavior changes — old preference pairs may be misleading (comparing base model outputs to human corrections for a fine-tuned model).
3. **No consumer-readiness check:** Nothing validates whether accumulated data meets PersonaCompiler's `PERSONA_COMPILER_MIN_EVIDENCE=3` threshold or StyleRetriever's quality threshold. Data could be insufficient or skewed.

**Recommendation:**
- **Keep ON** — data accumulation is cheap and the pattern is correct
- **Add TTL policy** — archive preference pairs older than 90 days
- **Post-FT decision:** When PersonaCompiler is activated, use ONLY post-FT data (discard base model preference pairs that would train the wrong direction)
- **Document** in DECISIONS.md as deliberate "background data collector" architecture

---

## PersonaCompiler × StyleRetriever: Double-DORMANT Analysis (NOTA 3)

Both #27 and #28 are OFF. This analysis evaluates what happens if either or both are reactivated.

### Scenario A: PersonaCompiler ON only

**What would happen:**
- Weekly scheduler reads unprocessed preference pairs + evaluator feedback (persona_compiler.py:739-783)
- Evidence categorized into behavioral dimensions (tone, length, emoji, etc.) (persona_compiler.py:805-914)
- LLM generates updated Doc D sections (persona_compiler.py:931-956)
- Updated Doc D written to `personality_docs` table (persona_compiler.py:1244)
- Creator Style Loader reads updated Doc D on next request

**Risk:** LLM rewrite of Doc D may alter identity signals. Cross-ref with identity preservation principle → should NOT activate pre-FT.

**Interaction with active systems:**
- Doc D changes propagate to: Style Normalizer baselines (if baselines embedded in Doc D), Length Controller (if length hints in Doc D), all prompt-injection systems that read Doc D
- NO guard validates that the LLM-rewritten Doc D preserves critical identity markers
- Versioning exists (doc_d_versions table) but rollback is manual

### Scenario B: StyleRetriever ON only

**What would happen:**
- Per-request: generation.py:245-282 queries gold_examples table via pgvector similarity
- Intent-matched, language-filtered gold examples injected AFTER preference_profile but BEFORE user message
- Format: `=== EJEMPLOS DE ESTILO DEL CREATOR ===` + bullet list of examples

**Risk: Dual few-shot injection (W8 2.6)**
- Calibration (#10) injects few_shots section (CRITICAL, system prompt context.py:571)
- StyleRetriever would inject gold_examples section (generation.py:290, user message area)
- Both provide style demonstrations. No dedup between them.
- If same example appears in both: wasted tokens. If different examples: potential style contradiction.

**Would they conflict?**
- **Same data source?** No. Calibration reads from calibration pipeline (mined patterns). StyleRetriever reads from gold_examples (copilot-approved responses). Different sources.
- **Same injection point?** No. Calibration → system prompt (`few_shots` section). StyleRetriever → user message area (generation.py).
- **Functionally redundant?** PARTIALLY. Both provide "write like this" demonstrations. But Calibration examples are mined from historical data, gold examples are copilot-approved — the quality signal is different.

### Scenario C: Both ON

**What would happen:**
- PersonaCompiler updates Doc D weekly from feedback evidence
- StyleRetriever injects intent-matched gold examples per-request
- FeedbackCapture feeds both

**New interaction: PersonaCompiler changes Doc D → affects Style Normalizer baselines + Calibration coherence (S.2, Tipo 3 MEDIUM from Fase 3)**. This amplifies the Doc D × Calibration coherence risk because Doc D changes are now automated and unsupervised.

### Recommendation

| Action | Rationale |
|--------|-----------|
| **#27 PersonaCompiler: Keep OFF until post-FT** | Identity preservation principle. LLM rewrite of Doc D risks altering identity signals the base model can't reconstruct. |
| **#28 StyleRetriever: Reactivate only WITH mutual exclusion guard against Calibration** | W8 2.6 dual injection bug would resurface. Guard: if `ENABLE_GOLD_EXAMPLES=true`, reduce Calibration few-shot count by the number of gold examples injected, OR inject gold examples INTO the few_shots section (not as a separate block). |
| **Both ON: NOT recommended pre-FT** | PersonaCompiler would modify the Doc D that Calibration was mined against, breaking the coherence assumption (S.2). Only safe if mining pipeline re-runs after each PersonaCompiler update. |
| **Code elimination: NOT recommended** | Both systems will be needed post-FT. The code is dormant but not dead — it has tests, flag-gated, and FeedbackCapture is actively populating its data. |

---

## D×D Pair Analysis (5 pairs)

### D.1 — #25 Creator Style Loader × #27 PersonaCompiler (pre-filter A.23, deepens Fase 3 S.6)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (dependency coupling)** |
| Severity | — (DORMANT, #27 OFF) |
| W8 ref | W8 3.11 |
| Status | #27 OFF |

**Mechanism:** PersonaCompiler writes to `personality_docs` table (persona_compiler.py:1244, `_set_current_doc_d()`). Creator Style Loader reads from `personality_docs` table (personality_loader.py:98-145, `_load_doc_d_from_db()`). Standard writer→reader dependency through shared DB table.

**Failure mode if #27 ON:** PersonaCompiler's LLM rewrite produces malformed Doc D → Creator Style Loader serves corrupted identity → all downstream systems affected.

**Mitigation (exists):** PersonaCompiler snapshots current Doc D before modification (persona_compiler.py:1243, `_snapshot_doc_d()`). SHA256 dedup prevents duplicate writes within 24h (persona_compiler.py:1021-1037). But rollback from snapshot is manual.

**Evidence:**
- Writer: persona_compiler.py:1244 (`_set_current_doc_d()`)
- Reader: personality_loader.py:98-99 (`_load_doc_d_from_db()`) → `personality_docs` table
- Snapshot: persona_compiler.py:1243
- Dedup: persona_compiler.py:1021-1037

---

### D.2 — #26 FeedbackCapture × #27 PersonaCompiler (pre-filter A.24)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (data pipeline)** |
| Severity | — (DORMANT, #27 OFF) |
| Status | #27 OFF |

**Mechanism:** FeedbackCapture writes to `preference_pairs`, `evaluator_feedback` tables. PersonaCompiler reads unprocessed records: `batch_analyzed_at.is_(None)` filter (persona_compiler.py:744-752). After processing, PersonaCompiler marks records with `batch_analyzed_at` timestamp (persona_compiler.py:1249-1254).

**Pipeline correctness:** Clean producer→consumer pattern. FeedbackCapture writes, PersonaCompiler reads and marks processed. No race condition because PersonaCompiler runs weekly (scheduler) while FeedbackCapture writes real-time (fire-and-forget).

**Data staleness risk:** PersonaCompiler reads ALL unprocessed records since last run. If it's been OFF for months, first activation would process a large backlog of base-model feedback — potentially generating Doc D updates based on outdated quality signals.

---

### D.3 — #25 Creator Style Loader × #28 StyleRetriever (pre-filter M.37)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (shared data lineage)** |
| Severity | — (DORMANT, #28 OFF) |
| Status | #28 OFF |

**Mechanism:** Both read creator data from related but separate sources:
- Creator Style Loader: `personality_docs` → Doc D text (creator_style_loader.py:68-78)
- StyleRetriever: `gold_examples` → approved response messages (style_retriever.py:226-249)

**Shared lineage:** Both ultimately derive from the same creator's communication patterns. Doc D describes style narratively. Gold examples demonstrate style directly. If the creator's style evolves (e.g., post-FT), both sources should be updated simultaneously.

**Not a direct coupling** — they read different tables with different schemas. The risk is coherence drift: Doc D says "mensajes cortos" but gold examples are long → conflicting demonstrations. This is the same coherence risk as S.2 (Doc D × Calibration) but through a different path.

---

### D.4 — #26 FeedbackCapture × #28 StyleRetriever (pre-filter B.32)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (data pipeline)** |
| Severity | — (DORMANT, #28 OFF) |
| Status | #28 OFF |

**Mechanism:** FeedbackCapture auto-creates gold examples when evaluator rates `lo_enviarias ≥ 4` (feedback_capture.py:303-311). StyleRetriever queries `gold_examples` table with quality filter `quality_score >= 0.6` (style_retriever.py:226-249).

**Quality gate:** The `lo_enviarias ≥ 4` threshold is reasonably high (4/5 scale). Combined with StyleRetriever's `quality_score >= 0.6` filter, low-quality examples are filtered out at two levels.

**Pipeline correctness:** Clean producer→consumer. No race condition (FeedbackCapture writes real-time, StyleRetriever reads per-request). Embedding-based retrieval (pgvector) ensures intent-matched selection.

---

### D.5 — #27 PersonaCompiler × #28 StyleRetriever (double-DORMANT, NOTA 3)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (indirect coupling via Doc D coherence)** |
| Severity | — (DOUBLE-DORMANT) |
| Status | Both OFF |

**If both activated simultaneously:**

PersonaCompiler modifies Doc D sections based on feedback evidence. StyleRetriever provides gold examples that should match the Doc D voice. If PersonaCompiler changes Doc D tone (e.g., "use more emojis" based on preference pairs showing emoji-rich responses get higher scores), gold examples mined BEFORE the change still reflect the OLD tone.

**Coupling path:** PersonaCompiler → Doc D changes → Style Normalizer baselines recalibrate (partially) → but gold examples don't update → StyleRetriever serves stale examples that mismatch the new Doc D.

**Resolution:** Gold examples should be re-scored after each Doc D update. Currently no mechanism for this exists.

**Evidence:**
- PersonaCompiler writes Doc D: persona_compiler.py:1244
- StyleRetriever reads gold_examples: style_retriever.py:226-249
- No re-scoring trigger: no foreign key or event between `personality_docs` changes and `gold_examples` table

---

## D×A Cross: Shared Data Source

### D.6 — #25 Creator Style Loader × #10 Calibration (pre-filter M.38)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (shared data lineage) — Tipo 6 partial** |
| Severity | LOW |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Both read creator data but from DIFFERENT pipelines:
- Creator Style Loader: reads `personality_docs` (Doc D text) → `style` section (CRITICAL)
- Calibration: reads calibration data (mined few-shots, baselines) → `few_shots` section (CRITICAL)

**Shared lineage:** Both are derived from the same creator's real communication. Doc D is a narrative extraction. Calibration data is mined patterns and examples. The mining pipeline and Doc D authoring should be coherent — both should reflect the same creator voice.

**Coherence risk:** Same as S.2 (Fase 3, Tipo 3 MEDIUM). If Doc D is manually edited without re-mining calibration, or vice versa, the two CRITICAL sections send different style signals. This is the most impactful coherence risk in the identity pipeline.

**Evidence:**
- Style Loader: creator_style_loader.py:68-78 (`load_extraction()`)
- Calibration: context.py:1268-1285 (`get_few_shot_section()`)
- Both CRITICAL: context.py:570-571

---

## D→A and E→B Consumption Paths (NOTA 7)

### Group D → Group A (how offline identity systems feed the prompt)

| System | Consumer | Coupling type | Fragility | Active? |
|--------|----------|--------------|-----------|---------|
| **#25 Style Loader → style section** | context.py:570, `inp.style_prompt` | **EXPLICIT** | LOW — Priority.CRITICAL, always included, typed string | **YES** |
| **#27 Compiler → personality_docs → #25** | persona_compiler.py:1244 → personality_loader.py:98 | **EXPLICIT (2-hop)** | MODERATE — LLM rewrite may introduce errors, snapshot protects | **NO** (#27 OFF) |
| **#28 Retriever → generation.py** | generation.py:245-282, `gold_examples_section` | **EXPLICIT** | LOW — typed function, quality-filtered, flag-gated | **NO** (#28 OFF) |
| **#26 FeedbackCapture → #27/#28** | feedback_capture.py:303-311, persona_compiler.py:744-764 | **EXPLICIT (2-hop)** | LOW — DB producer/consumer, no format fragility | **Partial** (#26 ON, consumers OFF) |

### Group E → Group B (how scoring feeds postprocessing)

| System | Consumer | Coupling type | Fragility | Active? |
|--------|----------|--------------|-----------|---------|
| **#29 Confidence → message metadata** | postprocessing.py:571-580 | **EXPLICIT (logging)** | NONE — score stored, no behavioral impact | **Uncertain** (flag defaults to false) |

**Key observation:** Group D→A paths are all EXPLICIT and flag-gated. Zero IMPLICIT couplings. This is architecturally clean. Group E→B path is logging-only — Confidence Scorer has NO behavioral impact on the pipeline.

---

## Confidence Scorer (#29): Analysis (NOTA 5)

### Flag discrepancy

| Source | Status |
|--------|--------|
| Pre-filter (Fase 2) | Listed as ON: `#29 Confidence Scorer \| ON (postprocessing.py:559)` |
| feature_flags.py | `confidence_scorer: bool = field(default_factory=lambda: _flag("ENABLE_CONFIDENCE_SCORER", False))` |
| postprocessing.py:557 | Gated: `if flags.confidence_scorer:` |

**Verdict:** Default is OFF. Unless Railway env var `ENABLE_CONFIDENCE_SCORER=true` is set, the scorer does not execute. Pre-filter listing was potentially incorrect. **For this analysis, treat as CONDITIONALLY ON (behavior depends on Railway config).**

### What Confidence Scorer evaluates

| Signal | Weight | What it measures | Overlap with other systems? |
|--------|--------|-----------------|---------------------------|
| intent_confidence | 0.30 | Intent classification clarity | NO — unique signal |
| response_type | 0.20 | Generation method (pool/LLM/escalation/error) | NO — unique signal |
| historical_rate | 0.30 | Past approval rate for same intent (30 days) | PARTIAL — FeedbackCapture stores same data |
| length_quality | 0.10 | 20-200 chars ideal range | PARTIAL — Length Controller enforces length |
| blacklist_check | 0.10 | Identity claims, raw CTAs, error leaks | PARTIAL — Guardrails also checks patterns |

**Does Confidence evaluate anything another system already validates?**
- **Overlap with Length Controller (#17):** Both assess length. But LC ENFORCES (trims), Confidence SCORES (no action). Different roles.
- **Overlap with Guardrails (#13):** Both check for bad patterns. But Guardrails CORRECTS/BLOCKS, Confidence SCORES. Different roles.
- **Overlap with FeedbackCapture (#26):** Both track quality signals. FeedbackCapture stores human ratings, Confidence computes automated score. Different mechanisms, same dimension.

**Is the score used for decisions?** NO — currently logging/monitoring only (postprocessing.py:571-580). No downstream system reads `confidence_score` for gating, routing, or behavioral modification.

**Recommendation:** If Confidence Scorer is meant to be ON, it's harmless (read-only, no behavioral impact). If it's meant to be OFF, the postprocessing step is dead code behind a flag. Either way, no cross-system interaction risk. Clarify Railway flag status.

---

## Commitment Tracker × Memory Engine Dedup (NOTA 5, cross-ref Fase 3 R.3)

**Fase 3 finding R.3** documented that the same commitment appears via two independent paths:
1. ARC2 memory extracts "te paso el link mañana" as `intent_signal` fact → `memory_context` (recalling position 7)
2. Commitment Tracker regex detects "te paso" → `get_pending_text()` → RelationshipAdapter → `relational_block` (recalling position 1)

**Is there explicit dedup post-ARC2?**
NO. Confirmed:
- Commitment Tracker stores in its own table (separate from `arc2_lead_memories`)
- No foreign key or lookup between commitment records and ARC2 memories
- `_build_recalling_block()` (context.py:1353) concatenates both without cross-checking
- `mark_fulfilled()` (commitment_tracker.py:303-335) requires explicit API call — no auto-fulfillment from ARC2

**Can the redundancy R.3 be resolved here?**

Two options:
1. **Dedup in `_build_recalling_block()`:** Before concatenation, check if commitment text appears in memory_context. If yes, skip commitment injection. Simple but fragile (text matching across different formats).
2. **Dedup at source:** When ARC2 extracts an `intent_signal` commitment, auto-mark the Commitment Tracker record as fulfilled. Cleaner but requires cross-system awareness.

**Recommendation for Fase 8:** Option 2 (source-level dedup) is architecturally cleaner. ARC2 nightly extract should query Commitment Tracker for matching pending items and mark them fulfilled. This eliminates the recalling block redundancy without fragile text matching.

---

## Sell/Don't-Sell Fragmentation Check (NOTA 6)

Checked all Group D/E systems for additional sell-signal contributions:

| System | Contributes sell/don't-sell signal? | Details |
|--------|-------------------------------------|---------|
| #25 Creator Style Loader | **Indirect only** | Doc D may contain phrases like "nunca vendas a amigos" — but this is part of Doc D content, not a separate mechanism. Already covered by Doc D (#1) in the fragmentation matrix. |
| #26 FeedbackCapture | NO | Captures quality data, doesn't influence sell decisions |
| #27 PersonaCompiler | **Potential (if ON)** | Could rewrite Doc D to add/remove sales behavior rules based on feedback patterns. If evaluators consistently rate sales messages low, PersonaCompiler might add "avoid aggressive selling" to Doc D. This would be a FIFTH indirect sell-signal channel. |
| #28 StyleRetriever | NO | Provides style demonstrations, not behavioral directives |
| #29 Confidence Scorer | NO | Scores quality, doesn't influence content |
| #30 Commitment Tracker | **Indirect only** | Commitment "te paso el link" is sales-adjacent, but the instruction "cumple compromisos" is about reliability, not selling. Already in Fase 3 R.9. |

**Verdict:** No NEW sell/don't-sell signal found in Group D/E. PersonaCompiler (#27) COULD become a fifth channel if activated — it would modify Doc D which is the identity layer of sell behavior. But since it's OFF, no additional fragmentation evidence. The 4-mechanism / 3-Tipo-1 finding from Fases 3-5 stands.

---

## Cross-references from Fase 3/4 (Group D/E systems)

| ID | Pair | Fase | Classification | Notes for Fase 6 |
|----|------|------|---------------|-------------------|
| S.3 | #1 Doc D × #25 Style Loader | Fase 3 | Tipo 3 (dependency), LOW | Standard supplier→consumer. If #25 fails → empty style section. |
| S.5 | #10 Calibration × #28 StyleRetriever | Fase 3 | Tipo 2 (redundancy), DORMANT | W8 2.6 dual injection. Would resurface if #28 ON. |
| S.6 | #25 × #27 PersonaCompiler | Fase 3 | Tipo 3 (dependency), DORMANT | Deepened as D.1 in this Fase. |
| S.7 | #1 Doc D × #27 PersonaCompiler | Fase 3 | Tipo 3 (dependency), DORMANT | Compiler writes Doc D that #1 reads. Same chain as D.1. |
| S.8 | #1 Doc D × #28 StyleRetriever | Fase 3 | Tipo 2 (potential), DORMANT | Gold examples should match Doc D voice. |
| G.8 | #29 Confidence × #11 QR | Fase 3 | Tipo 5 (parcial), LOW | Confidence doesn't penalize questions post-QR. |
| M.25 | #12 Anti-Echo × #29 Confidence | Fase 4 | Tipo 3, LOW | Confidence scores pool replacement, not LLM output. |
| B.34 | #29 × #12 Anti-Echo | Fase 4 | Same as M.25 | |
| B.35 | #29 × #17 LC | Fase 4 | Tipo 6, NEGLIGIBLE | Confidence scores post-LC content. Correct. |
| R.3 | #6 Memory × #30 Commitment | Fase 3 | Tipo 2, LOW | W8 2.10 persists. Dedup analysis above. |

---

## Summary Statistics

| Category | Count (new) | Cross-ref | Total Fase 6 scope |
|----------|-------------|-----------|---------------------|
| **Pairs analyzed (new)** | 7 | 10 | 17 |
| **Tipo 1 (contradicción directa)** | 0 | — | 0 |
| **Tipo 2 (redundancia)** | 0 | 2 (S.5 DORMANT, R.3 LIVE) | 2 |
| **Tipo 3 (acoplamiento)** | 6 (D.1-D.5, D.6) | 4 (S.3, S.6, S.7, M.25) | 10 |
| **Tipo 5 (orden)** | 0 | 1 (G.8) | 1 |
| **Tipo 6 (complementariedad)** | 0 | 2 (D.6 partial, B.35) | 2 |
| **DORMANT** | 5 (D.1-D.5) | 4 (S.5, S.6, S.7, S.8) | 9 |

### Severity distribution (new findings only)

| Severity | Count | Findings |
|----------|-------|----------|
| **MEDIUM** | 0 | — |
| **LOW** | 1 | D.6 (Style Loader × Calibration shared lineage) |
| **DORMANT** | 5 | D.1-D.5 (all involve OFF systems) |
| **N/A** | 1 | Confidence Scorer (flag-dependent, logging only) |

### Top findings for Fase 8

1. **FeedbackCapture (#26): data accumulator, not orphan.** ON and capturing data. Consumers (PersonaCompiler, StyleRetriever) are OFF. Data accumulates in DB. Recommendation: keep ON, add TTL policy, discard base-model data post-FT.

2. **PersonaCompiler (#27): violates identity preservation principle if activated pre-FT.** LLM rewrite of Doc D risks altering identity signals. Keep OFF until post-FT. Consistent with USE_DISTILLED_DOC_D=false decision.

3. **StyleRetriever (#28): dual few-shot injection risk (W8 2.6).** If activated without mutual exclusion guard against Calibration, two sets of style demonstrations enter the prompt independently. Needs guard before reactivation.

4. **Commitment × Memory dedup (R.3/W8 2.10): resolvable.** ARC2 nightly extract should auto-mark fulfilled commitments. Source-level dedup eliminates recalling block redundancy without fragile text matching.

5. **Confidence Scorer (#29): flag discrepancy + logging-only.** Defaults to OFF in feature_flags.py. If ON in Railway, it's harmless (read-only). No behavioral impact on pipeline. Clarify flag status.

6. **Identity pipeline simplification: current "Doc D + Calibration" is correct.** The 4-system chain (FeedbackCapture→PersonaCompiler→Doc D→StyleRetriever) is a future architecture for post-FT automated identity updates. Pre-FT, only the first and last links are needed (FeedbackCapture for data collection, Creator Style Loader for serving).

7. **All D→A paths are EXPLICIT and flag-gated.** Zero implicit couplings in Group D. Architecturally clean.

---

*Fase 6 completada. 7 new pairs analyzed + 10 cross-references compiled. 0 MEDIUM findings — Group D/E is largely dormant or logging-only. Key architectural insight: identity pipeline is correctly structured for post-FT activation but must NOT be activated pre-FT (identity preservation principle). FeedbackCapture is a deliberate data accumulator, not an orphan.*
