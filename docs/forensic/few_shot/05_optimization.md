# Few-Shot Injection — Optimization (Sprint top-6)

**Date:** 2026-04-23
**Verdict:** ADAPT-NOW to instrument + migrate flag to registry. Algorithmic core is KEEP-AS-IS per state-of-the-art (see `04_state_of_art.md`).

## Changes applied this sprint

### A. Flag registry migration (mini-cleanup)

- Added `few_shot: bool` to `core/feature_flags.py` registry. Env: `ENABLE_FEW_SHOT`, default True.
- `context.py:41` changed from inline `os.getenv(...)` to `ENABLE_FEW_SHOT = flags.few_shot` (module-level proxy retained for backward-compat with tests that patch this name).

### B. Prometheus instrumentation (added to central registry)

- `few_shot_injection_total{creator_id, intent, outcome}` — outcome ∈ {injected, empty, error, disabled}
- `few_shot_examples_count{creator_id}` — histogram with buckets [0,1,2,3,4,5,6,7,8]

Emission points in `context.py:1350-1380`:
- `outcome="injected"` when a section is returned
- `outcome="empty"` when no examples or the section is empty
- `outcome="error"` when `get_few_shot_section` raises
- `outcome="disabled"` when the flag is OFF **and** the creator has calibration (the relevant counter-factual)

### C. Tests added (6 new, combined with 3 existing = 9 total)

Location: `backend/tests/test_sprint_top6_forensic_ligero.py` (shared file with Commitment Tracker).

1. `test_few_shot_flag_on_with_section_emits_injected` — happy path
2. `test_few_shot_flag_off_but_calibration_present_emits_disabled` — counter-factual metric
3. `test_few_shot_flag_on_but_no_calibration_emits_nothing` — early return (no creator pack)
4. `test_few_shot_get_few_shot_section_empty_pool` — empty `few_shot_examples` returns ""
5. `test_few_shot_language_filter_same_language` — lang=ES filters ES+mixto
6. `test_few_shot_language_filter_code_switching_full_pool` — lang=ca-es uses full pool
7. `test_few_shot_stratified_respects_k_cap` — render never exceeds max_examples
8. `test_few_shot_intent_stratified_prioritises_matches` — detected_intent drives selection
9. `test_few_shot_detects_ca_es_code_switching` — message language detector tags mixed

## Changes deferred (DEFER-Q2)

| Item | Source | Reason |
|---|---|---|
| DSPy MIPROv2 offline calibration-pack optimisation | `04_state_of_art.md` §3 | Requires offline eval harness; not sprint scope |
| Dynamic-k (k=3 short, k=7 complex) | `04_state_of_art.md` §3 | Requires CPE v2 multi-creator evidence first |
| Parametrise `"=== EJEMPLOS REALES DE COMO RESPONDES ==="` framing per creator/language | `03_bugs.md` FS-01 | LOW severity; non-hispanohablantes are out of current roster |
| Learned selectors (EPR / vote-k) | `04_state_of_art.md` §3 | Post-fine-tuning; the rerank cost is not justified pre-FT |
| Distilled ca/es lang classifier | `03_bugs.md` FS-02 | Post-FT; current hardcoded markers work for Iris/Stefano |

## Activation criteria

- [x] Flag registered in `core/feature_flags.py`
- [x] Prometheus counters in `core/observability/metrics.py`
- [x] 9 tests passing (`pytest tests/test_sprint_top6_forensic_ligero.py tests/test_sprint_top6_quick_decide.py`)
- [x] State-of-the-art doc with explicit verdict: **KEEP-AS-IS** for this sprint
- [x] Bug catalog reviewed: 0 CRITICAL / 0 HIGH / 0 MEDIUM
- [ ] CCEE measurement plan executed (see `06_measurement_plan.md`)
- [ ] Gate decision KEEP/REVERT per `06_measurement_plan.md`

## Railway activation command (reference — CEO executes)

```bash
railway variables set ENABLE_FEW_SHOT=true --service web
```

## Rollback

```bash
railway variables set ENABLE_FEW_SHOT=false --service web
```

Observability to watch post-activation:
- `few_shot_injection_total{outcome="injected"}` should dominate (>90%)
- `few_shot_injection_total{outcome="error"}` should be <1% of total
- `few_shot_examples_count` p50 should land near 5
