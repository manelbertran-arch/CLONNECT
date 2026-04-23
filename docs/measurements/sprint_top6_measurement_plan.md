# Sprint Top-6 — Measurement Plan

**Date:** 2026-04-23
**Baseline:** `tests/ccee_results/iris_bertran/baseline_post_6_optimizations_20260423.json` (composite v5 = 69.1)
**Target creator:** `iris_bertran` (Stefano optional secondary)
**PR:** `sprint/top-6-activations-20260423` (to be referenced post-merge)

## 0. Pre-conditions

- [ ] PR merged to main (PR URL to be filled post-merge)
- [ ] Railway deployed main with PR changes
- [ ] `railway run alembic current` returns clean chain (no pending migration)
- [ ] `curl https://www.clonnectapp.com/health` → status=healthy

## 1. Bootstrap (single command)

```bash
# Dry-run first (prints stats without writing):
railway run python3 backend/scripts/bootstrap_sprint_top6_activations.py \
  --creator iris_bertran --dry-run

# If dry-run OK (n_examples > 0, DB reachable), commit:
railway run python3 backend/scripts/bootstrap_sprint_top6_activations.py \
  --creator iris_bertran
```

Expected exit code: `0`. Failure codes:
- `2` import error (Python path)
- `3` creator not found
- `4` few-shot calibration missing (deploy calibration pack first)
- `5` DB write failed

## 2. Flag activation sequence

Activate one at a time on Railway; observe Prometheus for 5 min between activations.

```bash
# Independent flags (can be activated in any order):
railway variables set ENABLE_QUESTION_HINTS=true  --service web
railway variables set ENABLE_RESPONSE_FIXES=true   --service web
railway variables set ENABLE_QUERY_EXPANSION=true  --service web
railway variables set ENABLE_FEW_SHOT=true         --service web
railway variables set ENABLE_COMMITMENT_TRACKING=true --service web
railway variables set ENABLE_DNA_AUTO_CREATE=true  --service web
```

Observability sanity between each:
```bash
curl -s https://www.clonnectapp.com/metrics | grep -E \
  "question_hint_injection_total|response_fixes_applied_total|query_expansion_applied_total|few_shot_injection_total|commitment_detected_total|dna_auto_create"
```

## 3. CCEE measurement command (combined arm B)

```bash
cd ~/Clonnect/backend
source config/env_ccee_gemma4_31b_full.sh
# All 6 flags ON simultaneously for combined measurement.
export ENABLE_QUESTION_HINTS=true
export ENABLE_RESPONSE_FIXES=true
export ENABLE_QUERY_EXPANSION=true
export ENABLE_FEW_SHOT=true
export ENABLE_COMMITMENT_TRACKING=true
export ENABLE_DNA_AUTO_CREATE=true

CCEE_NO_FALLBACK=1 python3 scripts/run_ccee.py \
  --creator iris_bertran \
  --runs 3 \
  --output tests/ccee_results/iris_bertran/baseline_post_sprint_top6_20260424.json \
  --compare tests/ccee_results/iris_bertran/baseline_post_6_optimizations_20260423.json
```

Expected runtime: ~30 min (50 examples × 3 runs × ~10-12s each including retries).

## 4. Gates per system (individual KEEP/REVERT)

Each system evaluated independently. A system's gate REVERT → flip only that flag off, keep the others.

### 4.1 Question Hints
- **KEEP:** Δ L3 ≥ +2 AND Δ J3 ≥ +2
- **REVERT:** Δ S1 ≤ −3 OR Δ K1 ≤ −3

### 4.2 Response Fixes
- **KEEP:** Δ S1 ≥ +1.5 AND Δ S2 ≥ +1
- **REVERT:** Δ B2 ≤ −3 OR `response_fixes_applied_total{outcome="error"}` > 5%

### 4.3 Query Expansion
- **KEEP:** Δ J6 ≥ +1 AND Δ C3 ≥ +2
- **REVERT:** `generation_duration_ms` p95 regression > 500ms OR Δ global composite ≤ −2

### 4.4 Few-Shot Injection (primary — highest expected lift)
- **KEEP:** Δ B2 ≥ +3 AND Δ S1 ≥ +2 AND Δ L1 ≥ +1.5
- **REVERT:** Δ K1 ≤ −3 OR Δ global composite ≤ −2 OR `few_shot_injection_total{outcome="error"}` ≥ 5%

### 4.5 Commitment Tracker
- **KEEP:** Δ J2 ≥ +2 AND Δ S2 ≥ +1
- **REVERT:** Δ J-family regression > 3 OR `commitment_tracker_patterns_source{source="hardcoded_fallback"}` = 100% (means vocab_meta bootstrap didn't land)

### 4.6 DNA Engine auto-create
- **KEEP:** Δ B2 ≥ +2 AND Δ L1 ≥ +1.5 AND Δ K1 ≥ +1
- **REVERT:** Δ global ≤ −2 OR `dna_auto_create_cap_hit_total` > 40% of attempts OR `dna_auto_create_circuit_tripped_total` ≥ 3 in first hour

### 4.7 INCONCLUSIVE (INCONC) — any system

Δ in critical dimensions within [−1, +1] → re-run with n=5 runs or extend window. Don't flip flag off, don't default ON either.

## 5. Composite-level objective

Baseline composite v5 = **69.1** (from `baseline_post_6_optimizations_20260423.json`).
Target: **≥ 72** combined (best-case for all 6 systems admitted).
Stretch: **≥ 74**.

## 6. Statistical robustness

- **Wilcoxon signed-rank** per dimension on paired (baseline, sprint) composites, n=150 (50×3).
- **Cliff's delta** effect size; report when |d| ≥ 0.147 (small) to flag directional signal.
- **σ_intra** from the 3 independent runs per arm; use as the error bar.

## 7. Rollout plan if KEEP

1. Iris keeps all 6 flags ON in Railway.
2. Monitor 48h for latency, error rate, pool pressure (from existing dashboards).
3. Stefano mini-CCEE 30×3 → repeat gates.
4. If Stefano also KEEP: defaults ON for all creators.

## 8. Rollback plan if REVERT (per-system)

```bash
# Flip only the offending flag; others stay ON.
railway variables set ENABLE_<SYSTEM>=false --service web
```

- Zero code rollback required.
- Prometheus counters will show `outcome="disabled"` dominant for that system.
- Post-mortem doc: `docs/measurements/sprint_top6_<system>_revert_<date>.md` with Δ dimensions, root cause, next step.

## 9. Reporting artefact (post-measurement)

`docs/measurements/sprint_top6_result_<date>.md` with:
- Δ composite (combined arm B − baseline)
- Per-system per-dimension table
- Wilcoxon + Cliff's delta
- Per-system gate decision (KEEP / REVERT / INCONC)
- Resulting new state: which flags remain ON, which revert
- New baseline JSON path (if KEEP → replaces `baseline_post_6_optimizations_20260423.json`)

## 10. Timeline

- Bootstrap: 5 min
- Flag activation + Prometheus smoke: 30 min
- CCEE 50×3 run: 30 min
- Analysis + per-system gates: 60 min
- **Total gate decision: same day.**
