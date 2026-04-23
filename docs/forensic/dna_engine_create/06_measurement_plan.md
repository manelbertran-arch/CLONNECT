# DNA Engine Auto-Create — Measurement Plan

**Date:** 2026-04-23
**Target creator:** `iris_bertran` (primary).

## 1. Pre-conditions

- [x] PR `sprint/top-6-activations-20260423` merged to main
- [ ] Flag `ENABLE_DNA_AUTO_CREATE` set to `true` in Railway (arm B)
- [ ] Railway `relationship_dna` table reachable (pool pressure baseline measured first)

## 2. Arm design

| Arm | `ENABLE_DNA_AUTO_CREATE` | Description |
|---|---|---|
| A (baseline) | `false` | Pipeline generates without DNA context for leads that have none |
| B (activated) | `true` | On turn ≥ 2 with no DNA → auto-create with 4-layer limiter |

## 3. CCEE commands

Baseline already exists: `baseline_post_6_optimizations_20260423.json`.

Arm B:

```bash
cd ~/Clonnect/backend
source config/env_ccee_gemma4_31b_full.sh
export ENABLE_DNA_AUTO_CREATE=true
CCEE_NO_FALLBACK=1 python3 scripts/run_ccee.py \
  --creator iris_bertran \
  --runs 3 \
  --output tests/ccee_results/iris_bertran/sprint_top6_dna_create_on_20260423.json \
  --compare tests/ccee_results/iris_bertran/baseline_post_6_optimizations_20260423.json
```

## 4. KEEP gate (all must hold)

| Dimension | Δ | Rationale |
|---|---|---|
| B2 (baseline adherence) | ≥ +2 | DNA drives relationship-aware tone. |
| L1 (length calibration) | ≥ +1.5 | Different relationship types → different lengths. |
| K1 (context coherence) | ≥ +1 | DNA carries cross-turn persona state. |

## 5. REVERT gate (any triggers rollback)

| Condition | Threshold |
|---|---|
| Any CCEE composite | ≤ −2 |
| `dna_auto_create_cap_hit_total` % of attempts | > 40% → limiter is too aggressive; tune before revert |
| `dna_auto_create_circuit_tripped_total` in first hour | ≥ 3 → downstream unstable; revert |
| DB pool exhaustion events (from existing `pool_exhaustion` logs) | ≥ 1 | Revert and investigate |

## 6. Secondary metrics

- `dna_auto_create_triggered_total{relationship_type}` — distribution of detected types (expect `CLIENTE`, `DESCONOCIDO`, `AMISTAD_CASUAL` dominant for Iris)
- `dna_auto_create_skipped_total{reason="already_exists"}` — should be ~0 after debounce kicks in
- `generation_duration_ms{status="ok"}` p95 — must not regress >300ms (limiter adds negligible overhead)

## 7. Operational safety windows

- First 15 min after flag-flip: monitor live Prometheus every minute
- Hour 1: summary table; decide continue/revert
- Day 1: 24h aggregates; if KEEP → stable rollout

## 8. Rollback decision tree

```
circuit_tripped ≥ 3 in 1h?      → REVERT
cap_hit > 40% of attempts?       → TUNE (raise TOKEN_BUCKET_CAPACITY) before revert
CCEE Δ composite ≤ −2?          → REVERT + post-mortem
DB pool exhaustion event?       → REVERT + investigate pool separately
None of the above + KEEP gate?  → KEEP (default ON for Iris)
```

## 9. Artefact

`docs/measurements/sprint_top6_dna_create_result_<date>.md` with the KEEP/REVERT decision + all metrics.
