# Quick-decide: Response Fixes

**Date:** 2026-04-23
**Flag:** `ENABLE_RESPONSE_FIXES` (registered as `flags.response_fixes`, default `True`)
**Scope:** activate + instrument; no algorithmic change.

## What it does

Applies a chain of post-LLM text fixes (`apply_all_response_fixes`) to the generated response content before it reaches the guardrails/formatting phase. Fixes are creator-aware (receive `creator_id`).

The fix chain is defined in `core/dm/response_fixes.py` (not modified here). Each fix is idempotent and data-driven; no linguistic hardcoding at this callsite.

## When it fires

Callsite: `backend/core/dm/phases/postprocessing.py:269` (Step 7a2, inside `apply_generation_fixes`).

Pre-conditions:
- `flags.response_fixes` is `True` (Railway prod pre-sprint: `false`)
- Runs unconditionally per turn when flag is on; the individual fixes inside the chain decide whether they modify content.

If `fixed_response` is truthy AND differs from original → replace. Otherwise, preserve original (no silent nulling).

## Metric

`response_fixes_applied_total{creator_id, outcome}` where outcome ∈ {changed, unchanged, error, disabled}.

Expected for Iris: most turns `unchanged` (the chain fixes edge cases); `changed` when the LLM outputs malformed links, stray whitespace, or formatting artefacts the chain catches.

## Gate

Per `sprint_top6_measurement_plan.md`: Δ S1 ≥ +1.5 AND Δ S2 ≥ +1 → **KEEP**. Regression > 3 on B2 (baseline adherence) → **REVERT**.

## Rollback

`railway variables set ENABLE_RESPONSE_FIXES=false --service web`.

## Observability note

The existing `logger.debug("Response fixes applied")` is preserved for local triage. The new Prometheus counter is independent (always fires, regardless of log level).
