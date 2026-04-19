# ARC3 Phase 1 Worker D — Distill Flag Wiring

## Status: MERGED (feature/arc3-distill-flag-wiring → main pending)

## What changed

Connected the `USE_DISTILLED_DOC_D` feature flag (previously a `pass` no-op) to the actual
Doc D cache lookup. When enabled, the DMAgent swaps the full Doc D style prompt (~38K chars)
for its cached distilled version (~3–5K chars) before building the context.

### Files modified

| File | Change |
|------|--------|
| `core/dm/agent.py` | Replaced `pass` block (lines 189–195) with live wiring to `get_distilled_style_prompt_sync` |
| `services/creator_style_loader.py` | Added `get_distilled_style_prompt_sync(creator_id, full_doc_d)` |
| `tests/distill/test_distill_loader_wiring.py` | 10 unit tests for flag logic + DB helper |

## Architecture

### Sync/async boundary

`_load_creator_data()` in `agent.py` is **sync**. `StyleDistillService.get_or_generate()`
is **async** (makes LLM calls). Solution: `get_distilled_style_prompt_sync()` is a
**cache-only, sync DB read** — it never triggers LLM generation. Populate the cache
first with `scripts/distill_style_prompts.py`.

### Slug → UUID resolution

`creator_style_distill` stores UUID `creator_id`, but `agent.py` uses slug (`iris_bertran`).
The helper resolves via `SELECT id FROM creators WHERE name = :name LIMIT 1`.

### Hash format

`doc_d_hash = hashlib.sha256(full_doc_d.encode()).hexdigest()[:16]` — matches
`StyleDistillService.compute_hash()`. Lookup also filters by `distill_prompt_version = 1`.

### Fail-silent guarantee

All three outcomes (flag off, cache miss, any exception) fall back to the full Doc D.
The live prompt is never corrupted by a distill failure.

## Flag behavior

| `USE_DISTILLED_DOC_D` | Cache state | Outcome |
|------------------------|-------------|---------|
| `false` (default)      | any         | Full Doc D used (no DB call) |
| `true`                 | hit         | Distilled text replaces full Doc D; INFO logged |
| `true`                 | miss        | Full Doc D kept; DEBUG logged |
| `true`                 | DB error    | Full Doc D kept; WARNING logged |

## Activation prerequisite

**Worker E** must run first:

```bash
# Populate cache for active creators before enabling flag
.venv/bin/python3.11 scripts/distill_style_prompts.py --creator iris_bertran
```

Then enable:
```bash
railway variables set USE_DISTILLED_DOC_D=true
```

## Validation (Worker E)

Run CCEE with flag OFF vs ON, compare composite scores:
- Hypothesis: distilled Doc D scores within ±3 points of full Doc D
- If composite regression > 3 points → keep flag OFF pending Doc D improvements
