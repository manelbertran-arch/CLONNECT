# ARC3 Phase 2: PromptSliceCompactor Shadow Mode

**Status:** IMPLEMENTED  
**Created:** 2026-04-19  
**Author:** Manel Bertran  
**Next Phase:** Phase 3 Live Activation (when compaction_rate < 15%)

---

## 1. Overview

ARC3 Phase 2 deploys **PromptSliceCompactor** in **shadow mode** — a parallel prompt compactor that decides how to fit context within a character budget, logs decisions to a database table, but **never alters the actual prompt**. This phase is 100% safe: zero output impact, zero user-visible changes.

### Why Shadow Mode?

Before Phase 3 live activation (which actually truncates prompts), we need to validate:
1. The algorithm packs sections correctly and compaction rate stays < 15%
2. The distillation heuristic (style_prompt > 40% remaining) triggers appropriately
3. Ratio caps don't over-truncate any section
4. The divergence between actual and shadow chars is negligible

All validation happens on production traffic, real creators, real leads.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ LLAMA Agent Decision Phase — phase_memory_and_context()        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                        _assemble_context()
                               │
                    ┌──────────┴──────────┐
                    │                     │
            (Legacy Path)         (Budget Orchestrator)
                    │                     │
                    ├─────────────────────┤
                    │  Combined Context   │ (8000 chars, default)
                    │  Length: N chars    │
                    └──────────┬──────────┘
                               │
                    [Fire-and-forget]
                    _run_compactor_shadow()
                               │
                    ┌──────────┴──────────┐
                    │                     │
            PromptSliceCompactor      Input sections:
              .pack(sections)        • style_prompt
                    │               • lead_facts
            PackResult:             • lead_memories
            • status                • rag_hits
            • compaction_applied    • message_history
            • sections_truncated    • few_shots
            • final_chars           • whitelist sections
                    │
         _log_shadow_compactor_sync()
                    │
         context_compactor_shadow_log table
                    │
         (No further blocking)
                    │
            Return to Agent
```

**Key invariants:**
- Shadow mode runs in `asyncio.create_task()` — fire-and-forget
- DB logging runs in `asyncio.to_thread()` — sync path doesn't block async context
- All shadow errors are caught and logged at `DEBUG`; never block the actual LLM call
- Feature flags gate both collection and activation

---

## 3. Algorithm Steps (§2.3.4 of ARC3_compaction.md)

The `PromptSliceCompactor.pack()` method follows 7 deterministic steps:

### Step 1: Compute Whitelist Cost
```python
whitelist_cost = sum(len(s.content) for s in sections if s.is_whitelist)
```
- Add all whitelisted section lengths
- If whitelist_cost > budget → **CIRCUIT_BREAK** (invalid state, logs warning)

### Step 2: Compute Remaining Budget
```python
remaining = budget - whitelist_cost
```
- All non-whitelist sections must fit in `remaining` budget

### Step 3: Try As-Is (No Compaction)
```python
current_cost = sum(len(s.content) for s in non_wl_sections)
if current_cost <= remaining:
    return PackResult(status="OK", compaction_applied=False)
```
- If all non-whitelist sections already fit, no compaction needed
- Return early with `reason="OK"`

### Step 4: Apply StyleDistillCache (if triggered)
```python
if style_prompt.len > remaining * 0.4:
    distilled = distill_service.get_or_generate(creator_id, doc_d)
    style_prompt = distilled
```
- Only triggered if style_prompt is the bottleneck (> 40% of remaining budget)
- Distillation is a lossy compression; reduces style_prompt from ~2000-3000 chars to ~500-800 chars
- If distill_service is None (Phase 2) or throws, compaction continues without distillation
- Sets `distill_applied=True` if successful

### Step 5: Apply Ratio Caps (per section)
```python
for section in non_wl:
    cap_chars = int(ratio * remaining)
    if len(section) > cap_chars:
        section = truncate_at_boundary(section, cap_chars)
        sections_truncated.append(section.name)
```
- Each section gets a hard cap based on its ratio from `DEFAULT_RATIOS`
- Uses `truncate_preserving_structure()` to cut at paragraph/sentence/word boundary
- Applied if `current_cost` still exceeds `remaining` after distillation

### Step 6: Aggressive Truncation by Reverse Priority
```python
for section in sorted(non_wl, key=lambda x: -x.priority):
    if current_cost <= remaining:
        break
    needed_reduction = current_cost - remaining
    section.content = section.content[:needed_reduction]  # hard cut
    sections_truncated.append(section.name)
```
- Last resort: process sections from **lowest priority to highest**
- Hard cut (no boundary preservation) if needed to fit budget
- Lowest-priority section loses content first

### Step 7: Assemble Final Result
```python
reason = "DISTILL_APPLIED" if distill_applied else (
    "RATIO_CAPS" if all_have_ratios else "AGGRESSIVE_TRUNC"
)
return PackResult(
    packed={name: content for all sections},
    status="OK",
    compaction_applied=bool(sections_truncated) or distill_applied,
    reason=reason,
    sections_truncated=sections_truncated,
    final_chars=sum(len for all sections)
)
```

---

## 4. DEFAULT_RATIOS Table

At MAX_CONTEXT_CHARS = 8000:

| Section | Ratio | Budget @ 8000 | Justification |
|---------|-------|---------------|---------------|
| **style_prompt** | 0.35 | 2800 chars | Doc D — defines style, tone, voice; ~1-2 pages |
| **lead_facts** | 0.15 | 1200 chars | Name, profile, DNA facts, ~200 words |
| **lead_memories** | 0.20 | 1600 chars | ARC2 memories (~5-10 memories × 150-200 chars) |
| **rag_hits** | 0.15 | 1200 chars | Top 3-5 RAG retrieval results, ~200 words |
| **message_history** | 0.10 | 800 chars | Last 5-10 turns (most recent context) |
| **few_shots** | 0.05 | 400 chars | 2-4 example Q&A pairs |

**Whitelist (never truncated):**
- `system_instructions` (~200 chars)
- `guardrails` (~150 chars)
- `persona_identity` (~100 chars)
- `current_user_msg` (variable; always kept whole)
- `tone_directive` (~80 chars)

**Total whitelist:** ~530 chars (approximate)  
**Available for non-whitelist:** ~7470 chars

---

## 5. PROMPT_WHITELIST Constants

Whitelisted sections are always preserved **without truncation**:

| Section | Approx Chars | Why Never Truncate |
|---------|--------------|-------------------|
| `system_instructions` | 200 | Core directive; truncation breaks LLM behavior |
| `guardrails` | 150 | Safety/compliance rules; must be complete |
| `persona_identity` | 100 | "You are X" — identity anchor cannot be partial |
| `current_user_msg` | variable | Latest user input; never truncate user's own message |
| `tone_directive` | 80 | Instruction on HOW to respond; truncation destroys meaning |

**Implementation:**
```python
PROMPT_WHITELIST = frozenset({
    "system_instructions",
    "guardrails",
    "persona_identity",
    "current_user_msg",
    "tone_directive",
})
```

When `SectionSpec(is_whitelist=True)` is passed to `pack()`:
1. Whitelist cost is computed and checked against budget (Step 1)
2. Whitelist sections are never in the `non_wl` pool used for truncation (Steps 3-6)
3. Whitelist sections are always included in final packed result (Step 7)

---

## 6. Feature Flags

### ENABLE_COMPACTOR_SHADOW (Default: TRUE)

**Purpose:** Gate shadow data collection  
**Type:** Safety flag  
**Value:** `os.getenv("ENABLE_COMPACTOR_SHADOW", "true").lower() == "true"`

When TRUE:
- Shadow compactor runs for every LLM call
- Logs decisions to `context_compactor_shadow_log` table
- Zero output impact — data is for analysis only

When FALSE:
- Shadow compactor does not run
- No `context_compactor_shadow_log` entries written
- Useful if table fills up or analysis is complete

**When to toggle:**
- Leave TRUE during Phase 2 (the entire shadow validation period)
- Set FALSE only when moving to Phase 3 live, if you want to stop collecting shadow data
- Or keep TRUE in Phase 3 to compare shadow vs. actual (for debugging)

---

### USE_COMPACTION (Default: FALSE)

**Purpose:** Activate Phase 3 live compaction  
**Type:** Kill switch  
**Value:** `os.getenv("USE_COMPACTION", "false").lower() == "true"`

When FALSE:
- Compactor runs, but `PackResult.packed` is **never used**
- Actual prompt remains the original, uncompacted version
- Shadow logs are written (if `ENABLE_COMPACTOR_SHADOW=true`)
- **This is Phase 2 behavior**

When TRUE:
- Compactor output **replaces the original sections** in the actual prompt
- Prompts are now subject to compaction truncation
- **This is Phase 3 behavior**

**When to activate:**
- Only after 1,000+ shadow turns confirm:
  - Compaction rate < 15% (most turns don't get truncated)
  - CCEE composite score ≥ -3 (no regression)
  - Median response latency +0-50ms (no slowdown from distillation calls)

---

## 7. Phase 3 GO Criteria

Before activating `USE_COMPACTION=true`, validate all conditions:

### Data-Driven Criteria
```sql
SELECT
  COUNT(*) as total_turns,
  SUM(CASE WHEN compaction_applied THEN 1 ELSE 0 END) as compacted_turns,
  100.0 * SUM(CASE WHEN compaction_applied THEN 1 ELSE 0 END) / COUNT(*) as compaction_rate,
  AVG(divergence_chars) as avg_divergence,
  MAX(divergence_chars) as max_divergence
FROM context_compactor_shadow_log
WHERE timestamp > NOW() - INTERVAL '7 days'
GROUP BY creator_id
HAVING COUNT(*) >= 200;
```

**Accept Phase 3 if:**
- `compaction_rate < 15%` across all active creators (1,000+ turns minimum)
- `avg_divergence < 50 chars` per turn (shadow rarely differs significantly from actual)
- `max_divergence < 500 chars` (no catastrophic deviations)

### Quality Criteria (CCEE)
- Run 100-turn CCEE validation on 3+ creators with `USE_COMPACTION=true` in shadow
- Composite score change CCEE_with_compaction - CCEE_baseline >= -3
- No regression in factual correctness (K1 score)

### Performance Criteria
- P95 latency: +0-100ms acceptable (distillation service adds latency)
- Error rate: <= 0.1% (same as baseline)
- Distill cache hit rate: >= 50% (StyleDistillCache working)

---

## 8. Runbook: Analyze Shadow Data

### 8.1 Query Compaction Rate by Creator

```sql
SELECT
  c.name as creator_slug,
  COUNT(*) as shadow_turns,
  SUM(CASE WHEN csl.compaction_applied THEN 1 ELSE 0 END) as compacted,
  ROUND(100.0 * SUM(CASE WHEN csl.compaction_applied THEN 1 ELSE 0 END) / COUNT(*), 2) as pct_compacted,
  ROUND(AVG(csl.divergence_chars), 1) as avg_divergence,
  MAX(csl.divergence_chars) as max_divergence
FROM context_compactor_shadow_log csl
JOIN creators c ON csl.creator_id = c.id
WHERE csl.timestamp > NOW() - INTERVAL '7 days'
GROUP BY c.id, c.name
ORDER BY pct_compacted DESC;
```

**Expected output (good state):**
```
creator_slug | shadow_turns | compacted | pct_compacted | avg_divergence | max_divergence
iris_bertran | 342          | 28        | 8.19%         | 12.3           | 287
stefano_xxx  | 215          | 19        | 8.84%         | 14.7           | 425
...
```

### 8.2 Analyze Truncation Reasons

```sql
SELECT
  reason,
  COUNT(*) as freq,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as pct,
  ROUND(AVG(divergence_chars), 1) as avg_diff,
  MAX(divergence_chars) as max_diff
FROM context_compactor_shadow_log
WHERE compaction_applied = true
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY reason
ORDER BY freq DESC;
```

**Expected reasons:**
- `RATIO_CAPS` — truncation by ratio caps (most common, good)
- `AGGRESSIVE_TRUNC` — lowest-priority truncation (means ratios weren't enough)
- `DISTILL_APPLIED` — style_prompt was compressed (Phase 3 only)

### 8.3 Inspect Sections Truncated

```sql
SELECT
  reason,
  sections_truncated,
  COUNT(*) as freq
FROM context_compactor_shadow_log
WHERE compaction_applied = true
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY reason, sections_truncated
ORDER BY freq DESC
LIMIT 20;
```

**Interpretation:**
- If `few_shots` is frequently truncated → ratio too low, increase from 0.05 to 0.08
- If `lead_memories` never truncated → ratio not hitting cap, may be over-provisioned
- If `style_prompt` repeatedly truncated but distill_applied=false → Phase 3 will fix via distillation

### 8.4 Check for Divergence Spikes

```sql
SELECT
  DATE_TRUNC('hour', timestamp) as hour,
  COUNT(*) as calls,
  ROUND(AVG(divergence_chars), 1) as avg_div,
  MAX(divergence_chars) as max_div,
  ROUND(100.0 * SUM(CASE WHEN divergence_chars > 200 THEN 1 ELSE 0 END) / COUNT(*), 2) as pct_spike
FROM context_compactor_shadow_log
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY hour
ORDER BY hour DESC;
```

If spikes > 300 chars appear, investigate the specific creator and turn.

---

## 9. Phase 3 Rollout Plan

Once Phase 2 shadow data validates, Phase 3 rolls out live compaction progressively:

### Day 1: Stefano (10% traffic)
```bash
USE_COMPACTION=true
# Targets: 10% of Stefano's messages
# Monitor: error_rate, latency P95, CCEE_composite
```

### Day 2: Stefano (25% traffic)
```bash
# Targets: 25% of Stefano's messages
# Metrics: confirm no regression from Day 1
```

### Day 3: Stefano (50%) + Iris (10%)
```bash
# Splits: 50% of Stefano, 10% of Iris
# Rationale: if both show consistent ≥-3 CCEE delta, expand
```

### Day 4-5: Staged Expansion
- Add each creator at 10%, then 25%, then 50%
- Each step waits 4-6 hours for metrics
- Stop if CCEE_composite drops > -5 or error_rate spikes

### Full Production
- When all creators at 50%, monitor for 24h
- Then move to 100% if metrics stable

**Kill Switch:**
```bash
USE_COMPACTION=false
# Immediately reverts to Phase 2 shadow (no output change)
# Database logging continues if ENABLE_COMPACTOR_SHADOW=true
```

**No-Go Criteria (Automatic Rollback):**
- CCEE composite score < baseline - 5 points
- Error rate > 2x baseline (usually < 0.1%, so > 0.2%)
- P95 latency > baseline + 200ms
- Any distill_service failures (rate > 2% of calls)

---

## 10. Known Limitations

### Shadow Doesn't See Whitelist Individually
The shadow logger receives `combined_context` (length N) and estimates whitelist cost ~530 chars, but the actual breakdown per whitelist section is not logged individually. This is acceptable because:
- Whitelist is never truncated in Phase 3
- Divergence is measured at the combined level
- If combined divergence is acceptable, whitelist subset is acceptable

### Distill Service is Null in Phase 2
Phase 2 uses `distill_service=None` in the compactor. The `distill_applied` flag will be FALSE during Phase 2 even if style_prompt would trigger distillation. Phase 3 wires `StyleDistillService` and distillation becomes live.

### No Turn-Level Metadata
The shadow table does not capture which specific sections made up the combined context (e.g., "style_prompt was 1200 chars, lead_facts was 800 chars"). Only the final truncated list and aggregate divergence are logged. Full per-section breakdown would require more schema columns; Phase 4 may add this.

### Boundary Truncation Approximation
`truncate_preserving_structure()` has three fallback levels (paragraph → sentence → word → hard cut). In rare cases where text has no paragraph or sentence boundaries for 100 chars, it falls back to hard cut at word boundary. This may result in small differences between the simulated truncation and live truncation of the exact same content.

---

## 11. File References

| Path | Role |
|------|------|
| `core/generation/compactor.py` | PromptSliceCompactor class, pack() algorithm |
| `core/dm/phases/context.py` | _assemble_context(), _run_compactor_shadow(), _log_shadow_compactor_sync() |
| `core/feature_flags.py` | `flags.compactor_shadow`, `flags.use_compaction` |
| `alembic/versions/049_arc3_compactor_shadow_log.py` | Migration: context_compactor_shadow_log table |
| `tests/compactor/test_compactor.py` | 10 unit tests covering pack() steps |

---

## 12. FAQ

**Q: Will shadow mode slow down my API?**  
A: No. Shadow runs in `asyncio.create_task()` (fire-and-forget) and DB logging is in a thread pool. Impact is < 5ms per request.

**Q: Why is style_prompt 35% of the budget?**  
A: Doc D (style definition) is the most informative section for style, tone, and voice quality. If truncated, CCEE scores drop significantly. 35% ensures Doc D is preserved unless everything is over budget.

**Q: What if distill_service fails in Phase 3?**  
A: If `distill_service.get_or_generate()` throws, it's caught and logged at DEBUG. Compaction continues without distillation — the compactor falls back to ratio caps. This is safe; the LLM call is never blocked.

**Q: Can I adjust DEFAULT_RATIOS during Phase 2?**  
A: Yes, but only if you re-run the shadow analysis to validate the new ratios. Changing ratios mid-phase 2 makes historical data incomparable. Best practice: lock ratios for 7+ days of shadow data, then adjust once (if needed) and run a new batch.

**Q: Phase 3: will users notice truncated prompts?**  
A: Unlikely if compaction_rate < 15%. Most users' contexts will not be compacted. For those that are, truncation happens at paragraph/sentence boundaries and lowest-priority sections (message_history, few_shots), not at the core identity/DNA level.

**Q: How do I know when Phase 2 is complete?**  
A: When you have >= 1,000 turns of shadow data and all GO criteria are met:
  - compaction_rate < 15%
  - avg_divergence < 50 chars
  - CCEE_composite >= -3
  - No spikes in error rate or latency

---

**Last Updated:** 2026-04-19  
**Next Review:** After Phase 3 Day 1 (1,000+ compacted turns analyzed)
