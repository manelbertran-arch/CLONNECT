# Few-Shot Injection — Forensic Audit Index

**Date:** 2026-04-23
**Sprint:** `sprint/top-6-activations-20260423`
**Flag:** `flags.few_shot` (env `ENABLE_FEW_SHOT`, Railway default `false` pre-sprint)

## Phase docs

| # | File | Summary |
|---|---|---|
| 1 | [`01_description.md`](01_description.md) | What/value/CCEE dimensions + callsite + selection pipeline. |
| 2 | [`02_forensic.md`](02_forensic.md) | Module function map, callsite code, git history, dependencies. |
| 3 | [`03_bugs.md`](03_bugs.md) | 0 CRITICAL / 0 HIGH / 0 MEDIUM / 3 LOW / 2 INFO. Creator-specific hardcoding audit: **clean**. |
| 4 | [`04_state_of_art.md`](04_state_of_art.md) | 5 papers + 3 repos. Verdict **KEEP-AS-IS**. DSPy MIPROv2, dynamic-k, learned selectors deferred Q2. |
| 5 | [`05_optimization.md`](05_optimization.md) | Registry migration + Prometheus + 9 tests. Deferred items enumerated. |
| 6 | [`06_measurement_plan.md`](06_measurement_plan.md) | CCEE 50×3 arm B plan, gate criteria, rollout. |

## Activation summary

| Aspect | Status |
|---|---|
| Algorithmic change | NO (KEEP-AS-IS — state-of-the-art already implemented) |
| Flag migrated to registry | YES |
| Duplicated `ENABLE_QUESTION_HINTS`-style cleanup needed | NO (Few-Shot had a single inline definition) |
| Prometheus metrics added | YES (`few_shot_injection_total`, `few_shot_examples_count`) |
| Tests added | 9 (6 new + 3 from quick-decide sibling) |
| Creator-specific hardcoding | None — confirmed by audit |
| Production-grade caveats | 3 LOW items deferred to Q2 |
| Blocker for flag-flip | NONE |

## Key references

- Callsite: `backend/core/dm/phases/context.py:1350-1380`
- Module: `backend/services/calibration_loader.py` (699 LOC, read-only)
- Test file: `backend/tests/test_sprint_top6_forensic_ligero.py`
- Metric registry: `backend/core/observability/metrics.py` (search `few_shot_`)
