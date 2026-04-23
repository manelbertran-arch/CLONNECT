# DNA Engine Auto-Create — Forensic Audit Index

**Date:** 2026-04-23
**Sprint:** `sprint/top-6-activations-20260423`
**Flag:** `flags.dna_auto_create` (env `ENABLE_DNA_AUTO_CREATE`, Railway default `false` pre-sprint)

## Phase docs

| # | File | Summary |
|---|---|---|
| 1 | [`01_description.md`](01_description.md) | What/value/CCEE dimensions + callsite + why 4-layer cap. |
| 2 | [`02_forensic.md`](02_forensic.md) | Module map, callsite flow, git history, failure modes pre-sprint. |
| 3 | [`03_bugs.md`](03_bugs.md) | 0 CRITICAL / 2 HIGH (fixed) / 2 MEDIUM (fixed) / 2 LOW (1 fixed, 1 deferred) / 2 INFO. |
| 4 | [`04_state_of_art.md`](04_state_of_art.md) | 5 papers + 3 repos (mem0 53.9k, letta 22.2k, langgraph 30.2k). Verdict **ADAPT-NOW 4-layer cap**. |
| 5 | [`05_optimization.md`](05_optimization.md) | New module `dna_auto_create_limiter.py` (135 LOC) + callsite rewrite + 4 counters + 9 tests. |
| 6 | [`06_measurement_plan.md`](06_measurement_plan.md) | CCEE arm B plan, KEEP/REVERT gates with explicit cap-hit and circuit thresholds. |

## Activation summary

| Aspect | Status |
|---|---|
| Structural fix (cap/semaphore/circuit) | **YES — 4-layer limiter** implemented |
| Flag registered | YES (`flags.dna_auto_create`) |
| Prometheus metrics | 4 new counters |
| Tests | 9 (all async, all passing) |
| Creator-specific hardcoding | `_SEED_TRUST` map still hardcoded → DEFER-Q2 (not blocker) |
| HIGH severity pre-sprint bugs | 2 — **both fixed** |
| Blocker for flag-flip | NONE post-sprint |

## Key references

- New limiter: `backend/services/dna_auto_create_limiter.py`
- Callsite: `backend/core/dm/phases/context.py:1034-1099`
- DB layer: `backend/services/relationship_dna_repository.py`
- Detector: `backend/core/relationship_type_detector.py`
- Tests: `backend/tests/test_sprint_top6_dna_create.py`
- Metrics: `backend/core/observability/metrics.py` (search `dna_auto_create_`)
