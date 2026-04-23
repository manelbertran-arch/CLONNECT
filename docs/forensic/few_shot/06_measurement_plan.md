# Few-Shot Injection — Measurement Plan

**Date:** 2026-04-23
**Target creator:** `iris_bertran` (primary). Stefano optional secondary.

## 1. Pre-conditions

- [x] PR `sprint/top-6-activations-20260423` merged to main
- [x] `calibrations/iris_bertran_unified.json` exists on deploy (verify via Railway SSH or healthcheck)
- [ ] Flag `ENABLE_FEW_SHOT` set to `true` in Railway for arm B

## 2. Arm design

| Arm | `ENABLE_FEW_SHOT` | Description |
|---|---|---|
| A (baseline) | `false` | Current production; LLM generates without creator examples |
| B (activated) | `true` | Few-shot injection active; k=5 intent-stratified + semantic hybrid |

Both arms run CCEE 50×3 against `iris_bertran` corpus.

## 3. Commands

```bash
# Baseline (already exists as baseline_post_6_optimizations_20260423.json)
# No need to re-run.

# Arm B (flag ON)
cd ~/Clonnect/backend
source config/env_ccee_gemma4_31b_full.sh
export ENABLE_FEW_SHOT=true
CCEE_NO_FALLBACK=1 python3 scripts/run_ccee.py \
  --creator iris_bertran \
  --runs 3 \
  --output tests/ccee_results/iris_bertran/sprint_top6_few_shot_on_20260423.json \
  --compare tests/ccee_results/iris_bertran/baseline_post_6_optimizations_20260423.json
```

## 4. Primary gate (per-system, individual KEEP/REVERT)

Decision is made independently of the other 5 systems in the same sprint.

### KEEP conditions (all must hold)

| Dimension | Δ required | Rationale |
|---|---|---|
| B2 (baseline adherence) | ≥ +3 | Main expected lift; if this doesn't move, few-shot isn't helping. |
| S1 (style fidelity) | ≥ +2 | Vocabulary/register mirroring from examples. |
| L1 (length calibration) | ≥ +1.5 | Median-length anchoring. |

### REVERT conditions (any triggers rollback)

| Dimension | Δ required | Reason |
|---|---|---|
| K1 (context coherence) | ≤ −3 | Examples overwhelming context. |
| Any CCEE composite | ≤ −2 | Global regression. |
| `few_shot_injection_total{outcome="error"}` | ≥ 5% of turns | Runtime instability. |

### INCONCLUSIVE (INCONC)

- Δ B2 / S1 / L1 within [−1, +1] → insufficient signal; re-run with n=5 or extend window.

## 5. Secondary metrics to report

- `few_shot_examples_count` p50 and p95 — verify k=5 saturation
- `few_shot_injection_total{outcome}` breakdown — % injected vs error vs empty vs disabled
- Latency impact (from `generation_duration_ms`) — ensure example injection doesn't blow p95 > baseline + 500ms

## 6. Statistical robustness

- Wilcoxon signed-rank test on per-example composite delta (n=50 × 3 runs = 150 pairs)
- Cliff's delta effect size per dimension
- σ_intra reported from 3 independent runs

## 7. Rollout plan if KEEP

- Single-creator activation first (`iris_bertran` only via env condition in code, OR per-creator flag split)
- Monitor for 48h: latency, error rate, Prometheus counters
- If stable → activate Stefano (run mini-CCEE 30×3 first)
- If Stefano also stable → default ON for all creators

## 8. Rollout plan if REVERT

- Flag OFF via Railway (zero LoC change)
- Post-mortem: identify which dimension regressed, which examples or intent buckets degraded
- Options:
  - Retune calibration pack (exclude low-quality example clusters)
  - Lower `max_examples` from 5 to 3
  - Gate few-shot by intent (enable only for `VENTA`, disable for `BIENVENIDA`)

## 9. Timeline

- Arm B CCEE run: ~30 min (50 × 3 × ~10s/example including retries)
- Analysis + decision: ~45 min
- Total gate decision: same day as flag flip

## 10. Reporting artefact

`docs/measurements/sprint_top6_few_shot_result_<date>.md` with:
- Δ composite
- Per-dimension table
- Wilcoxon p-values
- Gate decision (KEEP / REVERT / INCONC)
- Rationale
- Follow-up actions
