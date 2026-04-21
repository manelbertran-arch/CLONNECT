# S6 Re-matriz — Fase 5: Group C Detection + Cross C×A Analysis

**Fecha:** 2026-04-21
**Auditor:** Opus 4.6
**Branch:** `audit/s6-rematrix`
**Scope:** 8 new pairs + 12 cross-references from Fase 3. Group C systems: #19 Frustration, #20 Context, #21 Sensitive, #22 Intent, #23 Relationship Scorer.

---

## Architectural Overview: Detection Phase Timing and Independence

The 5 Group C systems execute in TWO different pipeline phases with NO inter-detector dependencies:

```
PHASE 1 (detection.py:85-336) — Sequential guards
  ├── Guard 3: #21 Sensitive Detection (line 174-250)     ← short-circuits if crisis
  ├── Guard 4a: #19 Frustration Detection (line 252-265)  ← enriches metadata
  ├── Guard 4b: #20 Context Detection (line 267-278)      ← enriches metadata
  │         └── internally calls classify_intent_simple()  ← lightweight intent (NO LLM)
  └── Guard 5: #3 Pool Matcher (line 280-333)             ← fast-path short-circuit

PHASE 2-3 (context.py:788-1400) — Context assembly
  ├── Step 2: #22 Intent Classification (line 797)         ← full classifier (pattern + LLM)
  ├── Parallel IO: follower + DNA + Conv State (line 825-862)
  ├── Memory recall: ARC2 + Memory Engine (line 863-912)
  ├── RAG routing: driven by #22 intent (line 1050-1152)
  └── Step: #23 Relationship Scorer (line 1155-1222)       ← after all memory loaded
```

**Key structural property:** Within each phase, detectors do NOT read each other's outputs. Every detector reads the same raw inputs (message, history) independently. Cross-system interactions happen only DOWNSTREAM when multiple detector outputs are consumed by the same system (recalling block, budget orchestrator, prompt assembly).

---

## Key Structural Finding: Dual Intent Classification

**Two independent intent classifiers run on the same message in different phases:**

| Classifier | Location | Phase | Method | Downstream consumers |
|-----------|----------|-------|--------|---------------------|
| `classify_intent_simple()` | orchestration.py:61 | Phase 1 (detection) | Keyword patterns ONLY | Context Detection's `interest_level`, `objection_type` → context_notes in recalling |
| `agent.intent_classifier.classify()` | context.py:797 | Phase 2-3 (context) | Patterns + LLM fallback | RAG routing (context.py:1082), few-shot selection (context.py:1280), budget value_score (section.py:76-79) |

**Divergence scenarios:**
- Simple says `"other"` (no keyword match), full says `"interest_strong"` (LLM detected nuanced interest) → LLM sees no interest_level note in recalling BUT gets product RAG injected
- Simple says `"interest_strong"` (keyword "comprar" matched), full says `"question_general"` (LLM determined it's a general question) → LLM sees "Interest(strong)" in recalling BUT gets no product RAG results

**No reconciliation:** Context detection's `interest_level` is never updated with the full classifier's result. Both outputs coexist independently.

**Evidence:**
- Simple classifier call: orchestration.py:61 (`intent_str = classify_intent_simple(message)`)
- Simple classifier definition: intent_classifier.py:330 (keyword patterns only)
- Full classifier call: context.py:797 (`intent = agent.intent_classifier.classify(message)`)
- Context detection stores simple result: orchestration.py:72-73 (`ctx.intent = intent_map.get(intent_str, Intent.OTHER)`)
- Full result drives RAG: context.py:1082 (`intent_value in _PRODUCT_INTENTS`)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento implícito — dual classification)** |
| Severity | **MEDIUM** |
| Status | LIVE |

---

## Intent Service as Pivot: Cascade Analysis (NOTA 2)

### Timing

Intent (full classifier) runs at context.py:797, which is:
- **AFTER** Frustration (Phase 1 guard 4a), Context Detection (guard 4b), Sensitive (guard 3)
- **BEFORE** Relationship Scorer (context.py:1155), RAG routing (1050), few-shot selection (1280)

### Downstream cascade: what breaks if Intent is wrong

| Consumer | Coupling | Impact of wrong intent | Evidence |
|----------|---------|----------------------|----------|
| RAG routing (#4) | Set membership check on `_PRODUCT_INTENTS` | Wrong `_rag_signal` → wrong search type → irrelevant products or missed products | context.py:1082 |
| Few-shot selection (#10) | Function parameter `detected_intent` | Wrong intent → intent-mismatched examples → degraded S1 Style Fidelity | context.py:1280 |
| Budget value_score (RAG) | Intent multiplier in `compute_value_score` | `purchase_intent` × 1.2 vs `casual` × 0.5 → RAG priority wrong in budget packing | section.py:76-79 |
| Context Detection interest_level | Simple classifier (separate) | **Independent** — uses `classify_intent_simple()`, not full classifier | orchestration.py:61 |

### What does NOT read Intent output

| System | Reads intent? | Evidence |
|--------|--------------|----------|
| #19 Frustration | NO | detection.py:254 — reads `message` + `prev_messages` only |
| #20 Context Detection | NO (uses own simple classifier) | orchestration.py:61 |
| #21 Sensitive | NO | detection.py:177 — reads `message` only |
| #23 Relationship Scorer | NO | relationship_scorer.py:89-95 — reads `user_messages`, `lead_facts`, `days_span`, `lead_status` |
| #9 Conv State | NO | context.py:839-842 — reads `sender_id`, `creator_id` only |

### Cascade blast radius

**Full intent contamination: 3 downstream systems** (RAG, Calibration, budget value).
**Zero lateral contamination:** No other detector reads Intent output. The cascade is strictly forward (detection→assembly), never lateral (detection→detection).

Cross-reference: Fase 3 G.1 (Intent→Calibration, Tipo 3 MEDIUM) and G.2 (Intent→RAG, Tipo 3 MEDIUM) already documented these cascades individually. This analysis confirms the total blast radius is bounded.

---

## Relationship Scorer Deep Dive (NOTA 3)

### Relationship type classification overlap: DNA × Scorer (Tipo 2 DOUBLE, not triple)

Two systems classify the lead's relationship quality independently:

| System | Taxonomy | Source data | Update mechanism | Output location |
|--------|----------|-------------|-----------------|-----------------|
| **DNA Engine (#8)** | DESCONOCIDO, SEGUIDOR, CLIENTE, AMISTAD_CERCANA, FAMILIA | Messages + LLM analysis (DNA triggers) | On-message trigger, persistent in `relationship_dna` table | Text in recalling (position 2): hints like "NUNCA vender" |
| **Relationship Scorer (#23)** | TRANSACTIONAL, CASUAL, CLOSE, PERSONAL | USER messages + memory facts + `leads.status` + duration | Computed fresh per request, stateless | Boolean `is_friend` (context.py:1221) + metadata for logging |

**Cross-reference X.1 (Fase 3):** DNA stores `relationship_type` persistently. Scorer computes `category` fresh. These use DIFFERENT source data:
- DNA reads from the `relationship_dna` DB table (written by `dna_update_triggers.py`)
- Scorer reads from the `leads` table (`follower.status`, context.py:1195-1198) + memory_context + messages

**Why NOT a triple:** Context Detection does NOT classify relationship type — it classifies `interest_level` (strong/soft/none) and `sentiment` (positive/neutral). Conv State does NOT classify relationship — it classifies `sales_phase`. No third system computes relationship quality.

**However:** The DB field `leads.status` IS a third relationship signal — it's set by the lead scoring batch process (not by DNA or Scorer). Scorer reads it as its strongest single input (max 0.30 of 1.00, relationship_scorer.py:176-189). DNA does NOT read `leads.status`. So:
- `leads.status`: batch-curated by lead scoring or creator
- `relationship_dna.relationship_type`: trigger-updated by DNA
- Scorer `category`: computed from `leads.status` + memory + messages + duration

This is a **fan-in pattern** (two source tables feeding one computation), not a triple classification.

### Scorer × Frustration (#19): ¿ambos modifican is_friend?

**No.** Frustration does NOT modify `is_friend` or `suppress_products`. Their sell-suppression mechanisms are completely separate:
- **Scorer:** Boolean `suppress_products=True` when score > 0.8 → products REMOVED from prompt (context.py:1221)
- **Frustration:** Text "No vendas ahora" in recalling (context.py:1374) → LLM reads text instruction

When aligned (both suppress): complementary. When misaligned (scorer TRANSACTIONAL but frustration "no vendas"): products are in the prompt but text says don't sell. LLM gets mixed signals. See Sell/Don't-Sell Fragmentation section below.

### Scorer × Context Detection (#20): ¿ambos clasifican tono?

**No.** Context Detection classifies `sentiment` (positive/neutral) and `is_b2b` (boolean). Scorer classifies `category` (TRANSACTIONAL/CASUAL/CLOSE/PERSONAL). Different dimensions:
- Context: current message tone + factual observations
- Scorer: overall relationship quality from structural signals

No overlap. Tipo 6 (complementary).

### Scorer × Intent (#22): ¿ambos clasifican tipo de lead?

**No direct interaction.** Intent classifies message type (QUESTION_PRODUCT, GREETING, etc.). Scorer classifies relationship quality. Different dimensions. Scorer does NOT read intent output (relationship_scorer.py:89-95 takes `user_messages`, `lead_facts`, `days_span`, `lead_status` — no intent parameter).

**Indirect interaction via product decisions:** Intent drives RAG product retrieval (context.py:1082). Scorer drives product suppression (context.py:1221). If Intent says "product inquiry" → RAG fetches products, but Scorer says PERSONAL → products stripped at assembly time. The RAG work is wasted. Already flagged as G.9 (Tipo 5, LOW) in Fase 3.

---

## Sell/Don't-Sell Signal Fragmentation (cross-Fase compilation)

Four independent mechanisms affect the sell/don't-sell decision with NO unified arbitration:

| # | System | Signal | Mechanism | When active |
|---|--------|--------|-----------|-------------|
| 1 | DNA (#8) | "NUNCA vender" | Text hint in recalling (position 2) | `relationship_type` = FAMILIA |
| 2 | Conv State (#9) | "Menciona el producto" / "Da el link" | Text instruction in recalling (position 3) | phase = PROPUESTA / CIERRE |
| 3 | Frustration (#19) | "No vendas ahora" | Text instruction in recalling (position 5) | `frustration_level` ≥ 2 |
| 4 | Scorer (#23) | Products removed from prompt | Boolean `suppress_products` flag | `score` > 0.8 (PERSONAL) |

**Contradiction matrix:**

| | DNA "no vendas" | Conv State "vende" | Frustration "no vendas" | Scorer removes products |
|-|-|-|-|-|
| **DNA** | — | **R.4 Tipo 1 BLOQUEANTE** | Aligned (complementary) | Aligned (complementary) |
| **Conv State** | **R.4** | — | **R.5 Tipo 1 BLOQUEANTE** | **C.8 Tipo 1 MEDIUM** (new) |
| **Frustration** | Aligned | **R.5** | — | Aligned (complementary) |
| **Scorer** | Aligned | **C.8** (new) | Aligned | — |

**Root cause:** There is no single "should I sell?" decision point. Three mechanisms independently suppress selling (DNA text, Frustration text, Scorer boolean), and one promotes it (Conv State text). The LLM resolves the conflict ad-hoc based on which signal has higher positional attention.

**Architectural recommendation (for Fase 8):** Consolidate sell/don't-sell into a single arbitration function that receives all signals and produces ONE directive. Priority: Sensitive > Frustration ≥ DNA > Scorer > Conv State. Inject only the winning directive into recalling.

---

## C×C Pair Analysis (6 pairs)

### C.1 — #19 Frustration × #20 Context Detection (pre-filter M.32, deepens Fase 3 R.14)

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| W8 ref | — |
| Status | LIVE |

**Mechanism:** Both run in Phase 1 detection. Frustration detects emotional state (level 0-3). Context detects factual signals (B2B, correction, meta-message, interest_level, sentiment). Non-overlapping domains.

**Independence verified:** Frustration reads `message + prev_messages` (detection.py:256-260). Context reads `message + history` (detection.py:272). Neither reads the other's output.

**Both feed recalling block independently:** Frustration → `frustration_note` (position 5), Context → `context_notes_str` (position 6). No cross-contamination.

**Fase 3 R.14 upgrade:** R.14 was classified as Tipo 6 with minimal analysis. After deeper review, classification CONFIRMED — these are genuinely complementary with no overlap.

---

### C.2 — #19 Frustration × #22 Intent (pre-filter B.26)

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad) con edge case Tipo 3** |
| Severity | LOW |
| Status | LIVE |

**Mechanism:** Frustration and Intent analyze the same message independently for different dimensions:
- Frustration: emotional/behavioral signals (escalation patterns, caps, emoji, repeated questions)
- Intent: message type classification (product question, greeting, objection, etc.)

**Edge case (Tipo 3):** When a lead sends a frustrated message like "YA TE LO DIJE 3 VECES QUIERO COMPRAR", Frustration correctly detects high frustration (level 2-3). Intent may misclassify due to anger markers — `classify_intent_simple()` checks keywords ("comprar" → `interest_strong`) but the full classifier's LLM layer might see the anger and classify as `escalation` or `support` instead of `purchase_intent`. If intent says "escalation" instead of "purchase": RAG skips product retrieval, few-shot examples wrong.

**Impact:** Rare edge case. Frustration detection is robust to intent accuracy (doesn't read it). Intent accuracy may be slightly degraded by emotional messages but this is an inherent limitation of message classification, not a system interaction.

---

### C.3 — #19 Frustration × #23 Relationship Scorer (pre-filter B.27)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (acoplamiento por mecanismo separado)** |
| Severity | LOW |
| Status | LIVE |

**Mechanism:** Both affect the sell/don't-sell outcome but via completely separate mechanisms:
- Frustration: text "No vendas ahora" in recalling (context.py:1374). Active only when `frustration_level ≥ 2`.
- Scorer: `suppress_products=True` removes products from prompt (context.py:1221). Active only when `score > 0.8`.

**When aligned:** Both suppress → complementary, double protection.
**When misaligned:** Scorer TRANSACTIONAL (products visible) + Frustration "no vendas" → products in prompt but text says don't sell. LLM gets mixed signals between available data and behavioral instruction.

**Scorer never promotes selling.** It only removes or keeps products. The active sell-instruction comes from Conv State (PROPUESTA/CIERRE), not Scorer. So the real conflict is Conv State vs Frustration (R.5, Tipo 1 BLOQUEANTE), not Scorer vs Frustration.

**Evidence:**
- Frustration note: context.py:1372-1376
- Scorer suppress_products: relationship_scorer.py:135 (`suppress_products=(total > 0.8)`)
- Scorer NOT active for selling: context.py:1218-1222 (silent suppression only)

---

### C.4 — #20 Context Detection × #22 Intent (pre-filter B.28)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (dual classification divergence)** |
| Severity | **MEDIUM** |
| Status | LIVE |

**This pair instantiates the Dual Intent Classification structural finding.**

**Mechanism:** Context Detection internally calls `classify_intent_simple(message)` (orchestration.py:61) to compute `interest_level` and `objection_type`. The full Intent classifier runs separately at context.py:797. Both classifications feed downstream systems independently.

**Specific divergence impact:**
- Context Detection writes `interest_level="strong"` to context_notes → LLM sees "Interest(strong)" in recalling
- Full classifier says `"question_general"` → RAG does NOT fetch products (not in `_PRODUCT_INTENTS`)
- Result: LLM reads "strong interest" but has no product data to work with

The reverse:
- Context Detection writes `interest_level="none"` (simple classifier missed nuance)
- Full classifier says `"interest_strong"` → RAG fetches products
- Result: LLM sees product data but no interest signal in recalling — may not prioritize product discussion

**No reconciliation exists.** Context detection never re-runs after the full classifier. The two outputs permanently diverge.

**Evidence:**
- Simple classifier call: orchestration.py:61
- Full classifier call: context.py:797
- Interest level from simple: orchestration.py:76 (`ctx.interest_level = detect_interest_level(message, ctx.intent)`)
- RAG routing from full: context.py:1082 (`intent_value in _PRODUCT_INTENTS`)

---

### C.5 — #20 Context Detection × #23 Relationship Scorer (pre-filter B.29)

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad)** |
| Severity | NEGLIGIBLE |
| Status | LIVE |

**Mechanism:** Context detects current-message signals (B2B, correction, sentiment). Scorer computes relationship quality from structural data (messages, memory, duration, DB status). Non-overlapping:
- Context: "this message is from a B2B contact" (factual, current)
- Scorer: "this lead is CLOSE (score 0.65)" (structural, historical)

Neither reads the other's output. Scorer doesn't read `is_b2b`. Context doesn't read `relationship_score`.

---

### C.6 — #22 Intent × #23 Relationship Scorer (pre-filter B.30)

| Field | Value |
|-------|-------|
| Type | **Tipo 6 (complementariedad) con Tipo 5 parcial** |
| Severity | LOW |
| Status | LIVE |

**Mechanism:** Intent classifies message type. Scorer classifies relationship quality. Different dimensions, different data sources, no mutual dependency.

**Tipo 5 (timing) component:** Intent runs BEFORE Scorer (context.py:797 vs 1157). Intent drives RAG product retrieval (context.py:1082). Scorer drives product suppression (context.py:1221). If Scorer suppresses products, Intent's RAG work is wasted. But the final prompt is correct (products stripped at assembly). Already flagged as G.9 in Fase 3.

**Evidence:**
- Intent timing: context.py:797
- Scorer timing: context.py:1157
- Product suppression after RAG: context.py:1221 (is_friend) strips products gathered at ~1100-1152

---

## C×A Cross Analysis (2 new pairs)

### C.7 — #22 Intent × #3 Pool Matcher (pre-filter M.35)

| Field | Value |
|-------|-------|
| Type | **Tipo 3 (dual classification, disjoint execution)** |
| Severity | LOW |
| Status | LIVE |

**Mechanism:** Both "classify" the incoming message but for different purposes:
- Pool Matcher (detection.py:280-333): pattern-matches short messages (≤80 chars) against conversational categories (cancel, thanks, confirmation). If matched, short-circuits the pipeline — Intent never runs.
- Intent (context.py:797): classifies message type for RAG routing and few-shot selection. Only runs if Pool Matcher didn't fire.

**Mutual exclusion by design:** If Pool Matcher fires → `result.pool_response` set → pipeline returns (detection.py:332-333). Intent classification in Phase 2-3 never executes. If Pool Matcher doesn't fire → Intent runs normally.

**Edge case:** Pool Matcher classifies "Vale, me apunto" as `confirmation` (pool response). But the full intent classifier would have classified it as `interest_strong` → triggering product RAG. The pool response handles it conversationally instead of triggering the full pipeline. This is by design but means short confirmations of purchase interest get generic responses.

**Evidence:**
- Pool Matcher short-circuit: detection.py:332-333 (`return result`)
- Pool Matcher threshold: detection.py:286 (`len(message.strip()) <= 80`)
- Intent only in Phase 2-3: context.py:797

---

### C.8 — #9 Conv State × #23 Relationship Scorer (pre-filter B.20)

| Field | Value |
|-------|-------|
| Type | **Tipo 1 (señales contradictorias sin resolución)** |
| Severity | **MEDIUM** |
| Status | LIVE |

**Mechanism:** Conv State and Scorer can produce irreconcilable directives:
- Conv State PROPUESTA: "Menciona el producto que encaja con sus necesidades" (conversation_state.py:104-110) → text instruction in recalling (position 3)
- Scorer PERSONAL: `suppress_products=True` (score > 0.8) → ALL products removed from prompt (context.py:1221)

**Contradiction:** Conv State tells the LLM "present a product" but Scorer has removed all products from the context. The LLM receives an instruction it CANNOT follow — the referenced data doesn't exist in its prompt.

**LLM behavior when contradicted:** Either (a) hallucinate a product from training data (dangerous — wrong prices, non-existent offerings) or (b) ignore the instruction entirely (suboptimal — Conv State's sales progression stalls).

**No resolution mechanism:** Conv State does NOT check `is_friend`. Scorer does NOT override Conv State instructions. They operate on different data planes (text instruction vs data availability) without mutual awareness.

**Why MEDIUM not BLOQUEANTE:** Unlike R.4/R.5 where both contradictory signals are TEXT (LLM must resolve ambiguity), here the data removal mechanism (Scorer) is more robust — the LLM literally cannot sell products it doesn't see. The risk is hallucination, not ambiguous instruction-following. But hallucination of commercial info IS a business risk.

**Pattern:** This is the third instance of the Sell/Don't-Sell Fragmentation pattern (joins R.4 and R.5).

**Evidence:**
- Conv State PROPUESTA: conversation_state.py:104-110
- Scorer suppress_products: relationship_scorer.py:135, context.py:1221
- Product assembly: context.py:~592 (`prompt_products = [] if inp.is_friend`)
- No is_friend check in Conv State: conversation_state.py:375-422 (transitions only on intent/message-count)

---

## C→A Consumption Path Analysis (NOTA 4)

For each Group C detector: what Group A system consumes its output, and how fragile is the coupling?

| Detector | Consumer | Coupling type | Fragility | Evidence |
|----------|----------|--------------|-----------|----------|
| **#19 Frustration** → Recalling block | Text concatenation | **IMPLICIT** | HIGH — any format change to `frustration_note` silently changes LLM behavior. No structured handoff, no type safety. | context.py:1362-1381, 1353 |
| **#20 Context** → Recalling block | Text concatenation | **IMPLICIT** | HIGH — `context_notes` are free-text observations. Concatenated into `_context_notes_str` with length/question hints. Any change propagates silently. | context.py:1384-1390 |
| **#22 Intent** → RAG (#4) | Set membership check | **SEMI-EXPLICIT** | MODERATE — `intent_value in _PRODUCT_INTENTS` (context.py:1082). Adding new intent types requires updating the `_PRODUCT_INTENTS` set. Forgetting to update → new intents silently fall through. | context.py:1071-1074 |
| **#22 Intent** → Calibration (#10) | Function parameter | **EXPLICIT** | LOW — `detected_intent=intent_value` (context.py:1280). Typed parameter, clear API contract. | context.py:1280 |
| **#22 Intent** → Budget value | Multiplier lookup | **SEMI-EXPLICIT** | LOW — `compute_value_score("rag", cog)` uses intent multipliers (section.py:76-79). New intents fall to default multiplier (1.0). Graceful degradation. | section.py:59-81 |
| **#23 Scorer** → Product suppression | Boolean flag | **EXPLICIT** | LOW — `is_friend = _rel_score.suppress_products` (context.py:1221). Clear boolean, no parsing. | context.py:1218-1222 |
| **#23 Scorer** → cognitive_metadata | Direct assignment | **EXPLICIT** | NONE — logging only. Score and category stored for monitoring. | context.py:1207-1209 |
| **#21 Sensitive** → Pipeline exit | Early return | **EXPLICIT** | NONE — short-circuit returns DMResponse directly (detection.py:224-233). No downstream coupling when inactive. | detection.py:207-233 |

**Fragility ranking:**
1. **Most fragile:** Frustration → recalling, Context → recalling (text concatenation, zero type safety)
2. **Moderately fragile:** Intent → RAG (set membership, requires manual sync)
3. **Robust:** Intent → Calibration, Scorer → is_friend, Sensitive → short-circuit (typed interfaces)

---

## #21 Sensitive Detection: Isolated System

#21 Sensitive Detection has **ZERO cross-system interactions** in the retained pair matrix.

**Why:** Its architecture is fail-closed and binary:
- **When it triggers** (confidence ≥ escalation threshold): returns crisis response directly (detection.py:224-233). NO other system runs — Frustration, Context, Intent, Scorer, RAG, generation, postprocessing are all skipped.
- **When it doesn't trigger:** stores `sensitive_detected=False` in cognitive_metadata (detection.py:180-181). No downstream system reads this flag for behavioral decisions.

This is a clean "circuit-breaker" design. No interaction analysis needed.

---

## FeedbackCapture (#26) — Scope Exclusion (NOTA 6)

Confirmed: FeedbackCapture (#26) is Group D, scope Fase 6. No C×D pairs involving FeedbackCapture were found in the retained pair matrix. If C×D crosses emerge during Fase 6 analysis, they'll be documented there.

---

## Cross-reference: Fase 3 pairs involving Group C systems

These pairs were fully analyzed in Fase 3. Listed here for completeness — NOT re-analyzed.

| ID | Pair | Fase 3 classification | Severity | Notes for Fase 5 context |
|----|------|-----------------------|----------|--------------------------|
| R.4 | #8 DNA × #9 Conv State | **Tipo 1 BLOQUEANTE** (upgraded in Fase 4) | CRITICAL | Sell/don't-sell fragmentation instance #1 |
| R.5 | #9 Conv State × #19 Frustration | **Tipo 1 BLOQUEANTE** (upgraded in Fase 4) | CRITICAL | Sell/don't-sell fragmentation instance #2 |
| R.7 | #6 Memory × #19 Frustration | Tipo 6 + Tipo 3 risk | LOW | Complementary; memory at position 7 wins attention battle |
| R.8 | #8 DNA × #19 Frustration | Tipo 3 | LOW | Different tone pulls (warm vs careful) |
| R.9 | #19 Frustration × #30 Commitment | Tipo 3 | LOW | "No vendas" vs "cumple compromiso de ventas" |
| R.10 | #6 Memory × #20 Context | Tipo 6 | NEGLIGIBLE | Historical facts + current signals, complementary |
| R.11 | #8 DNA × #20 Context | Tipo 6 | NEGLIGIBLE | Relationship data + current signals, complementary |
| R.14 | #19 Frustration × #20 Context | Tipo 6 | NEGLIGIBLE | Deepened in this Fase as C.1, classification confirmed |
| R.15 | #20 Context × #30 Commitment | Tipo 6 | NEGLIGIBLE | Situational + pending actions, no conflict |
| G.1 | #22 Intent × #10 Calibration | Tipo 3 | MEDIUM | Intent cascade: wrong intent → wrong few-shots |
| G.2 | #22 Intent × #4 RAG | Tipo 3 | MEDIUM | Intent cascade: wrong intent → wrong RAG routing |
| G.9 | #23 Scorer × #4 RAG | Tipo 5 | LOW | RAG fetches products that Scorer strips. Correct but wasteful. |
| X.1 | #8 DNA × #23 Scorer | Tipo 3 | LOW | Dual relationship classification (DNA persistent, Scorer computed) |
| X.2 | #6 Memory × #23 Scorer | Tipo 3 | MEDIUM | Fragile regex parsing of ARC2 XML in context.py:1169-1185 |

---

## Summary Statistics

| Category | Count (new) | Fase 3 cross-ref | Total Fase 5 scope |
|----------|-------------|-------------------|--------------------|
| **Pairs analyzed (new)** | 8 | 14 | 22 |
| **Tipo 1 (contradicción directa)** | 1 (C.8) | 2 (R.4, R.5) | 3 |
| **Tipo 2 (redundancia)** | 0 | 0 | 0 |
| **Tipo 3 (acoplamiento)** | 3 (C.2, C.3, C.7) + 1 structural (dual intent) | 6 (G.1, G.2, R.7, R.8, R.9, X.1, X.2) | 10 |
| **Tipo 5 (orden)** | 0 | 1 (G.9) | 1 |
| **Tipo 6 (complementariedad)** | 4 (C.1, C.5, C.6, parte de C.2) | 5 (R.10, R.11, R.14, R.15) | 9 |

### Severity distribution (new findings only)

| Severity | Count | Findings |
|----------|-------|----------|
| **MEDIUM** | 2 | C.4 (dual intent divergence), C.8 (Conv State × Scorer sell contradiction) |
| **LOW** | 3 | C.2 (Frustration × Intent edge case), C.3 (Frustration × Scorer mechanisms), C.7 (Intent × Pool Matcher) |
| **NEGLIGIBLE** | 2 | C.1 (Frustration × Context), C.5 (Context × Scorer) |
| **STRUCTURAL** | 1 | Dual Intent Classification finding |

### Top findings for Fase 8

1. **Dual Intent Classification (structural, MEDIUM):** `classify_intent_simple()` in detection phase and `agent.intent_classifier.classify()` in context phase produce independent, potentially divergent intent classifications. Context Detection's `interest_level` uses the simple one; RAG/Calibration use the full one. No reconciliation.

2. **C.8 — Conv State × Scorer (Tipo 1, MEDIUM):** Third instance of Sell/Don't-Sell Fragmentation. Conv State says "present product" while Scorer removes all products from prompt. Instruction is impossible to follow → risk of product hallucination. Joins R.4 and R.5 as evidence for unified sell/don't-sell arbitration.

3. **Sell/Don't-Sell Fragmentation (architectural, compile):** 4 independent sell-related mechanisms (DNA text, Conv State text, Frustration text, Scorer boolean) with zero arbitration. 3 Tipo 1 interactions found across Fases 3-5 (R.4, R.5, C.8). **Strongest architectural finding of the audit so far.** Recommendation: single arbitration function.

4. **Intent cascade blast radius (bounded, MEDIUM):** If Intent is wrong, contamination is limited to RAG routing + few-shot selection + budget value_score (3 systems). No lateral contamination to other detectors. Forward-only cascade.

5. **C→A fragility gradient:** Frustration and Context notes are HIGH fragility (text concatenation). Intent→RAG is MODERATE (set membership). Intent→Calibration and Scorer→is_friend are LOW (typed interfaces).

### Systems confirmed clean

- **#21 Sensitive Detection:** Zero interactions when inactive, clean short-circuit when active. Properly isolated.
- **#19 × #20 (Frustration × Context):** Genuinely complementary, no overlap despite both feeding recalling.
- **#23 Scorer × #19 Frustration:** Aligned (both suppress selling), not contradictory.
- **#23 Scorer × #20 Context:** Different domains entirely, no overlap.

---

*Fase 5 completada. 8 new pairs analyzed + 14 Fase 3 cross-references compiled. 2 MEDIUM findings (dual intent, Conv State × Scorer). Key meta-finding: Sell/Don't-Sell Fragmentation is now confirmed across 3 Tipo 1 interactions (R.4, R.5, C.8) — strongest architectural recommendation of the audit.*
