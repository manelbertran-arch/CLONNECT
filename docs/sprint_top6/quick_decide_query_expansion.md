# Quick-decide: Query Expansion

**Date:** 2026-04-23
**Flag:** `ENABLE_QUERY_EXPANSION` (registered as `flags.query_expansion`, default `True`)
**Scope:** activate + instrument; no algorithmic change.

## What it does

Expands the user's incoming message into synonymous/complementary queries via `core.query_expansion.get_query_expander().expand(message, max_expansions=2)` before issuing the RAG semantic search. The expanded query is concatenated with the original and used as the RAG input.

Expansion strategy lives in `core/query_expansion.py` (not modified here). Zero linguistic hardcoding at this callsite.

## When it fires

Callsite: `backend/core/dm/phases/context.py:1166` (inside the RAG retrieval branch, only when `_needs_retrieval == True`).

Pre-conditions:
- `ENABLE_RAG` is `True`
- `_needs_retrieval` is `True` (intent requires knowledge retrieval)
- `ENABLE_QUERY_EXPANSION` is `True` (Railway prod pre-sprint: `false`)

Outcome `expanded` is recorded only when the expander returns >1 variant. If it returns 1 (no expansion available), outcome is `single` — flag was on, expander ran, just no alternatives.

Metadata side-effect: `cognitive_metadata["query_expanded"] = True` when `expanded` path fires.

## Metric

`query_expansion_applied_total{creator_id, outcome}` where outcome ∈ {expanded, single, error, disabled}.

Expected for Iris: ~60% `expanded`, ~35% `single`, <5% `error`, 0% `disabled` once flag on.

## Gate

Per `sprint_top6_measurement_plan.md`: Δ J6 ≥ +1 AND Δ C3 ≥ +2 → **KEEP**. Regression > 3 on latency (RAG query doubles request time) → review expander caching before REVERT.

## Rollback

`railway variables set ENABLE_QUERY_EXPANSION=false --service web`.

## Known caveat

`get_query_expander()` may hit an external embedding API or local model depending on the expander implementation. Latency impact per turn is additive to the existing RAG latency. Monitor `llm_api_duration_ms{provider=<expander_provider>}` alongside the gate.
