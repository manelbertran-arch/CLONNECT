# ARC1 A1.5-bis — Final Measurement Report
**Date:** 2026-04-19  
**Run file:** `arc1_a1_5_bis_final_iris_20260419_0025.json`  
**Protocol:** CCEE v5.3 — 3×50 ST + 5×10 MT, Gemma-4-31B (OpenRouter), Qwen3-30B-A3B judge (DeepInfra)  
**Branch:** `feature/arc1-budget-orchestrator`

---

## 1. v5 Composite Progression

| Checkpoint | v5 Composite | Δ vs Baseline | Δ vs A1.3 |
|------------|-------------|---------------|-----------|
| Baseline (main, pre-ARC1) | **69.5** | — | -1.1 |
| A1.3 flag-ON | **70.6** | +1.1 | — |
| **A1.5-bis** | **66.9** | **-2.6** ❌ | **-3.7** ❌ |

**ARC1 target**: ≥71.5 — **NOT MET**. A1.5-bis is a regression vs both A1.3 and baseline.

---

## 2. Full Dimension Comparison Table

| Dim | Weight | Baseline | A1.3 flag-ON | A1.5-bis | Δ (A1.3→A1.5) |
|-----|--------|----------|--------------|----------|----------------|
| S1 | 0.16 | 69.4 | 72.4 | 69.0 | -3.4 |
| S2 | 0.12 | 47.5 | 66.9 | 47.3 | **-19.6** |
| S3 | 0.16 | 66.5 | 65.7 | 56.6 | **-9.1** |
| S4 | 0.09 | 60.6 | 58.1 | 57.3 | -0.8 |
| J_old (J1) | 0.03 | 56.3 | 54.8 | 30.6 | -24.2 |
| J_new | 0.09 | 71.8 | 72.5 | 73.3 | +0.8 |
| J6 | 0.03 | 100.0 | 100.0 | 100.0 | 0.0 |
| K | 0.06 | 86.9 | 76.4 | 85.6 | **+9.2** |
| G5 | 0.05 | 80.0 | 100.0 | 100.0 | 0.0 |
| L | 0.09 | 74.5 | 65.6 | 66.1 | +0.5 |
| H | 0.07 | 92.0 | 78.0 | 90.0 | **+12.0** |
| B | 0.05 | 61.3 | 63.0 | 62.0 | -1.0 |
| **v5 COMPOSITE** | — | **69.5** | **70.6** | **66.9** | **-3.7** |

---

## 3. MT Metrics Comparison

| Metric | Baseline | A1.3 flag-ON | A1.5-bis | Δ (A1.3→A1.5) |
|--------|----------|--------------|----------|----------------|
| K1 context retention | 83.48 | 64.86 | **78.66** | **+13.8** ✅ |
| K2 style retention | 91.98 | 93.69 | **96.02** | +2.3 |
| J3 prompt-to-line | 86.5 | 86.0 | 86.0 | 0.0 |
| J4 line-to-line | 59.16 | 61.88 | 62.08 | +0.2 |
| J5 belief drift | 65.0 | 65.0 | 67.5 | +2.5 |
| L1 language | 88.5 | 81.5 | 85.5 | +4.0 |
| L2 register | 68.78 | 59.88 | 63.8 | +3.9 |
| L3 intimacy | 61.66 | 50.0 | 42.5 | -7.5 |
| H1 Turing (pass%) | 92.0 | 78.0 | **90.0** | **+12.0** ✅ |
| MT composite | 76.18 | 75.98 | **78.82** | **+2.8** ✅ |
| B2 persona depth | — | 43.0 | 38.5 | -4.5 |
| B5 persona consistency | — | 46.0 | 47.5 | +1.5 |

---

## 4. Per-Run ST Composites (v4, for variance reference)

| | Baseline | A1.3 flag-ON | A1.5-bis |
|-|----------|--------------|----------|
| Run 1 | 62.4 | 70.14 | 62.21 |
| Run 2 | 62.64 | 69.39 | 61.93 |
| Run 3 | 62.16 | 69.43 | 60.88 |
| **Mean ± σ** | **62.4 ± 0.2** | **69.65 ± 0.4** | **61.67 ± 0.7** |

> Note: per-run v4 composites use the v4 formula (no L/H/B). The v5 composite is computed post-MT and is the canonical metric.

---

## 5. S4 Status (A1.4 Proximity Fix)

S4 (contextual adaptation):
- Baseline: 60.6
- A1.3: 58.1 (-2.5 vs baseline)
- A1.5-bis: 57.3 (-3.3 vs baseline)

**Status: Not recovered.** The A1.4 S4-proximity fix (appending last 200 chars of lead message as `<RECENT_LEAD_MESSAGE>` anchor) has not closed the gap vs baseline. S4 remains below baseline in both A1.3 and A1.5-bis. This is a pre-existing deficit inherited from the orchestrator integration — the proximity anchor alone is insufficient.

---

## 6. K1 Status

K1 (context retention across MT turns):
- Baseline: 83.48
- A1.3: 64.86 (**-18.62** vs baseline — the known regression from ARC1 integration)
- A1.5-bis: 78.66 (**-4.82** vs baseline, **+13.80** vs A1.3)

**Status: Significantly recovered but not fully closed.** The recalling cap increase (400→700) did succeed in improving context retention from 64.86 to 78.66. The K1 deficit vs baseline shrunk from -18.62 to -4.82 (74% recovery). However, the S3 regression (-9.1 points) indicates the extra context is hurting single-turn strategic alignment.

---

## 7. Regression Diagnosis

### Primary cause: S3 strategic alignment drop (-9.1 pts, -1.46 weighted pts)
The recalling cap increase (400→700) injects significantly more recalling context. While this improves K1, the additional context causes strategic drift in single-turn responses — the model receives more historical signal but produces responses less aligned with the strategic intent of each message. This is the most impactful real regression.

### Secondary cause: S2 lexical similarity drop (-19.6 pts raw, -2.35 weighted pts)
S2 baseline = 47.5; A1.5-bis = 47.3; A1.3 = 66.9. A1.3's S2 was anomalously high vs baseline. A1.5-bis returns to baseline-level S2. Likely case-set variance — A1.3 happened to generate lexically closer responses for the test set. This explains ~2.35 weighted points of the gap.

### Tertiary cause: J_old (J1) drop (-24.2 pts raw, -0.73 weighted pts)
J1 dropped from 54.8 to 30.6. With weight 0.03, accounts for only 0.73 pts. Could be MT conversation variance (different 5 conversations in each run).

### Summary of weighted impact
| Source | Weighted Δ |
|--------|-----------|
| S3 regression | -1.46 |
| S2 case-variance | -2.35 |
| J_old drop | -0.73 |
| S1 drop | -0.54 |
| H gain | +0.84 |
| K gain | +0.55 |
| Other | +0.00 |
| **Total** | **-3.69 ≈ -3.7** |

---

## 8. ARC1 Verdict

**CLOSE ARC1 AT A1.3.** A1.5-bis optimizations are net-negative.

| Question | Answer |
|----------|--------|
| Did A1.5-bis exceed A1.3? | ❌ No (66.9 vs 70.6, -3.7) |
| Did A1.5-bis exceed baseline? | ❌ No (66.9 vs 69.5, -2.6) |
| Did cap increases help K1? | ✅ Yes (+13.8, deficit -18.62→-4.82) |
| Did cap increases hurt ST quality? | ✅ Yes (S3 -9.1, S2 case-variance) |
| ARC1 goal met (≥71.5)? | ❌ Not at any checkpoint |

**Best ARC1 result: A1.3 flag-ON, v5=70.6 (+1.1 vs baseline, +1.57%).**

### Action items post-ARC1:
1. **Revert recalling cap 700→400** (A1.5-bis cap hurt S3; K1 gain not worth ST cost at this level).  
   Optionally keep 500 (A1.5 interim) as a middle ground — untested.
2. **Keep history cap at original** (500 or prior).
3. **Keep rag purchase_intent multiplier 1.4** (no evidence it harmed anything; S3 boost in E1 confirmed in A1.3).
4. **S4 gap (-3.3 vs baseline)** requires a dedicated sprint — proximity anchor alone insufficient.
5. **K1 gap (-4.82 vs baseline)** — partially recovered; further gains require targeted memory retrieval improvements, not context padding.
6. **ARC2 target**: S3 recovery + S4 recovery + K1 full recovery → feasible composite target ≥72.0.
