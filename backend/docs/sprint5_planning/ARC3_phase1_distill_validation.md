# ARC3 Phase 1 — StyleDistillCache Validation

## 1. Setup summary

| Field | Value |
|-------|-------|
| Branch | `feature/arc3-phase1-distill-cache` |
| Base commit | `d82d27f3` |
| Date | 2026-04-19 |
| Phase | SHADOW — distillation generated/cached, NOT read in prod |

### Files created
- `alembic/versions/048_add_creator_style_distill_table.py` — DB migration
- `services/style_distill_service.py` — `StyleDistillService` class
- `scripts/distill_style_prompts.py` — batch distillation CLI
- `tests/distill/__init__.py`
- `tests/distill/test_style_distill_service.py` — 7 unit tests

### Files modified
- `core/feature_flags.py` — added `use_distilled_doc_d` flag (default OFF)
- `core/dm/agent.py` — added ARC3 shadow hook at style_prompt load site

---

## 2. Schema

**Migration:** `048_add_creator_style_distill_table` (revises `047`)

```sql
CREATE TABLE creator_style_distill (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
    doc_d_hash TEXT NOT NULL,           -- SHA256[:16] of style_prompt
    doc_d_chars INT NOT NULL,
    doc_d_version INT NOT NULL,
    distilled_short TEXT NOT NULL,      -- ~1500 chars target
    distilled_med TEXT,                 -- ~3000 chars (optional)
    distilled_chars INT NOT NULL,
    distill_model TEXT NOT NULL,
    distill_prompt_version INT NOT NULL,
    quality_score FLOAT,
    human_validated BOOL DEFAULT false,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(creator_id, doc_d_hash, distill_prompt_version)
);
CREATE INDEX idx_style_distill_creator_hash
    ON creator_style_distill(creator_id, doc_d_hash);
```

**Downgrade:** cleanly drops index then table.

---

## 3. CCEE validation

**Status: DEFERRED — requires staging DB with creator data.**

No `DATABASE_URL` or `OPENROUTER_API_KEY` available in local environment.

CCEE validation must run on staging before Phase 3 activation:

```bash
export USE_DISTILLED_DOC_D=false
python3.11 scripts/run_ccee.py \
  --creator iris_bertran --runs 3 --cases 20 \
  --v4-composite \
  --save-as arc3_distill_baseline_full_$(date +%Y%m%d_%H%M)
```

Then run with `USE_DISTILLED_DOC_D=true` (once batch distillation is complete) and compare.

---

## 4. Distillation prompt v1 (ARC3 §2.2.3)

**`DISTILL_PROMPT_VERSION = 1`** (bump to force re-distillation across all creators).

The prompt instructs the model to:

**Preserve:**
1. Unique voice (verbal tics, characteristic expressions, tone)
2. Concrete representative examples (at least 3–5)
3. Tone rules per lead temperature (cold/warm/hot if present)
4. Form constraints (length, emojis, punctuation)

**Eliminate:**
- Generic phrases about "being authentic" or "connecting with the lead"
- Redundancies (same idea stated 2+ times)
- Meta-commentary about style (saying "my style is X" instead of demonstrating it)
- Less informative examples if multiple similar ones exist

---

## 5. Compression target

| Metric | Value |
|--------|-------|
| Typical iris_bertran Doc D | ~5 500 chars |
| Target distilled_short | ~1 500 chars |
| Target ratio | ~27% of original (73% reduction) |
| Min valid output | 1 200 chars |
| Max valid output | 1 800 chars |
| Retry on out-of-range | Yes — 1 retry with exponential backoff |

This 73% reduction is aggressive. The quality gate (§6) validates that clone quality
loss is acceptable before Phase 3 activation.

---

## 6. Quality gate

**Activation criterion:** ΔCCEE_composite ≥ −3 points vs. full Doc D baseline.

| Delta | Decision |
|-------|----------|
| ≥ 0 | APPROVE immediately |
| −1 to −3 | APPROVE (acceptable quality/cost tradeoff) |
| −4 to −7 | ITERATE — adjust prompt or increase target_chars |
| < −7 | BLOCK — do not activate (reference: QW2 compressed Doc D regressed −10.69) |

Per-metric gates:
- K1 (style fidelity): ΔCCEE_K1 ≥ −5
- S1 (style match): ΔCCEE_S1 ≥ −5
- G5 (persona): ΔCCEE_G5 ≥ −5

---

## 7. Verdict

**PENDING_VALIDATION**

No CCEE run possible without staging DB. Phase 3 activation is blocked until
validation confirms ΔCCEE_composite ≥ −3.

---

## 8. Next steps

1. **Now (Phase 2, parallel):** PromptSliceCompactor shadow — can run independently.
2. **Before Phase 3:** Run batch distillation on staging:
   ```bash
   python3.11 scripts/distill_style_prompts.py --creator-id <iris_uuid>
   ```
3. **Phase 3 gate:** Run CCEE baseline (flag OFF) vs. distilled (flag ON).
   If ΔCCEE_composite ≥ −3 → set `USE_DISTILLED_DOC_D=true` on Railway.
4. **Phase 3 wiring:** Inject DB session into `_load_creator_data` to enable
   actual distilled content substitution (the shadow hook in `agent.py` marks the site).
