# Quick-decide: Question Hints

**Date:** 2026-04-23
**Flag:** `ENABLE_QUESTION_HINTS` (now registered as `flags.question_hints`, default `True`)
**Scope:** activate + instrument; no algorithmic change.

## What it does

Injects a contextual hint `"NO incluyas pregunta en este mensaje."` into the LLM prompt when the bot's measured natural question rate exceeds the creator's baseline question rate.

**Data-driven, zero hardcoding**:
- creator_q_rate: `baseline_metrics.punctuation.has_question_msg_pct` (per-creator, loaded by `_load_baseline`)
- bot_q_rate: `creator_profiles.bot_natural_rates.question_rate` (measured, loaded by `_load_bot_natural_rates`)
- suppress_prob: `1 - (creator_rate / bot_rate)` — no absolute thresholds
- Stochastic injection: `random.random() < suppress_prob` per turn

## When it fires

Callsite: `backend/core/dm/phases/context.py:1473` (context-notes assembly, once per turn).

Pre-conditions:
- `ENABLE_QUESTION_HINTS` is `True` (default in Railway prod: `false` pre-sprint)
- `_maybe_question_hint` returns non-empty (i.e., both rates available AND bot > creator AND random sample fired)

Metadata side-effect: `cognitive_metadata["question_hint_injected"] = "<hint text>"`.

## Metric

`question_hint_injection_total{creator_id, decision}` where decision ∈ {injected, skipped, error, disabled}.

Expected distribution for Iris (creator_rate ≈ 10%, bot measured ≈ 18%): `injected ≈ 45%`, `skipped ≈ 55%`, `error ≈ 0%`, `disabled = 0` once flag on.

## Gate

Per `sprint_top6_measurement_plan.md`: Δ L3 ≥ +2 AND Δ J3 ≥ +2 → **KEEP**. Regression > 3 on S1 or K1 → **REVERT** (flag back to false).

## Rollback

`railway variables set ENABLE_QUESTION_HINTS=false --service web` (1 command, no redeploy needed — env var read at startup; effective after next process restart).

## Known non-issues

- Duplicate `ENABLE_QUESTION_HINTS` definition historically existed in `generation.py:57` and `context.py:43`. Both now resolve to `flags.question_hints` (same source). The `generation.py:362` callsite uses `_maybe_question_hint` but the resulting `_q_hint` is never read downstream (legacy code); preserved for now to avoid tangential diff.
