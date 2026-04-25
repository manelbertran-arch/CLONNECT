#!/usr/bin/env python3
"""
CCEE-Mini Correlation Validation (Sprint 7)

Calcula correlación Pearson entre CCEE-Mini (20 cases) y CCEE Full (50 cases)
usando per-case data de los resultados existentes (BL_pipeline + FT_sprint6).

Método: retrospective bootstrap — subsamples 20 de los 50 per-case scores reales.
Esto es equivalente a correr CCEE-Mini vs CCEE Full en el mismo pipeline porque:
  - S1-S4 y B son promedio de per-case scores
  - J6, K, L, H, G5 son idénticos entre Mini y Full (provienen de 5 MT conversations)

Resultado: si Pearson r ≥ 0.8 → CCEE-Mini válido como gate entre fases Sprint 7.
"""

import json
import statistics
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr

BASE = Path(__file__).parent.parent.parent
RESULTS_DIR = BASE / "tests/ccee_results/iris_bertran"
MEASUREMENTS_DIR = BASE / "measurements/validation/ccee_mini_correlation"

# ─── Source files ─────────────────────────────────────────────────────────────
BL_FILE = RESULTS_DIR / "bl_pipeline_doc_d_c0bcbd73_20260425_1729.json"
FT_FILE = RESULTS_DIR / "ft_sft_20260425_0130.json"

MINI_N_CASES = 20
MINI_SEED = 3407
N_BOOTSTRAP = 1000  # for CI estimation


def load_condition(path: Path) -> dict:
    """Load a CCEE result file and extract all needed data."""
    data = json.loads(path.read_text())
    per_case = data["per_case_records"]  # list of 50 dicts
    prom = data["prometheus_scores"]
    v5 = data["v5_composite"]

    return {
        "path": str(path.name),
        "n_cases": len(per_case),
        # per-case S dims
        "S1": [c["s1_score"] for c in per_case],
        "S2": [c["s2_score"] for c in per_case],
        "S3": [c["s3_score"] for c in per_case],
        "S4": [c["s4_score"] for c in per_case],
        # per-case B sub-dims
        "B2": prom["B2_persona_consistency"]["per_case"],
        "B5": prom["B5_emotional_signature"]["per_case"],
        # fixed MT dims (same between Mini and Full)
        "J_old": v5["dimension_scores"]["J_old"],
        "J_new": v5["dimension_scores"]["J_new"],
        "J6": v5["dimension_scores"]["J6"],
        "K": v5["dimension_scores"]["K"],
        "G5": v5["dimension_scores"]["G5"],
        "L": v5["dimension_scores"]["L"],
        "H": v5["dimension_scores"]["H"],
        # weights and full composite
        "weights": v5["dimension_weights"],
        "full_composite": v5["score"],
        "full_dims": v5["dimension_scores"],
    }


def compute_b_dimension(b2_scores: list, b5_scores: list, b4: float = 100.0) -> float:
    """B = mean(B4=100, B2_mean, B5_mean). B1=None is excluded."""
    return float(np.mean([b4, np.mean(b2_scores), np.mean(b5_scores)]))


def compute_mini_dims(cond: dict, idx: np.ndarray) -> dict:
    """
    Compute dimension scores for a Mini subset (20-case indices).
    Fixed MT dims (J6, H, K, L, G5) are unchanged.
    """
    s1 = float(np.mean([cond["S1"][i] for i in idx]))
    s2 = float(np.mean([cond["S2"][i] for i in idx]))
    s3 = float(np.mean([cond["S3"][i] for i in idx]))
    s4 = float(np.mean([cond["S4"][i] for i in idx]))
    b2_sub = [cond["B2"][i] for i in idx]
    b5_sub = [cond["B5"][i] for i in idx]
    b = compute_b_dimension(b2_sub, b5_sub)

    return {
        "S1": s1, "S2": s2, "S3": s3, "S4": s4, "B": b,
        "J_old": cond["J_old"],
        "J_new": cond["J_new"],
        "J6": cond["J6"],
        "K": cond["K"],
        "G5": cond["G5"],
        "L": cond["L"],
        "H": cond["H"],
    }


def compute_composite(dim_scores: dict, weights: dict) -> float:
    return float(sum(weights[k] * dim_scores[k] for k in weights if k in dim_scores))


def run_correlation(bl: dict, ft: dict) -> dict:
    """
    Compute Pearson r between Mini and Full scores across all dimensions
    for both conditions (BL + FT), using seed=3407 for Mini case selection.
    """
    rng = np.random.RandomState(MINI_SEED)
    idx_bl = rng.choice(50, size=MINI_N_CASES, replace=False)
    rng2 = np.random.RandomState(MINI_SEED)
    idx_ft = rng2.choice(50, size=MINI_N_CASES, replace=False)

    bl_mini_dims = compute_mini_dims(bl, idx_bl)
    ft_mini_dims = compute_mini_dims(ft, idx_ft)

    bl_mini_composite = compute_composite(bl_mini_dims, bl["weights"])
    ft_mini_composite = compute_composite(ft_mini_dims, ft["weights"])

    dimensions = ["S1", "S2", "S3", "S4", "J_old", "J_new", "J6", "K", "G5", "L", "H", "B"]

    mini_scores = []
    full_scores = []
    for dim in dimensions:
        mini_scores.append(bl_mini_dims[dim])
        full_scores.append(bl["full_dims"][dim])
        mini_scores.append(ft_mini_dims[dim])
        full_scores.append(ft["full_dims"][dim])

    # Add composite
    mini_scores.append(bl_mini_composite)
    full_scores.append(bl["full_composite"])
    mini_scores.append(ft_mini_composite)
    full_scores.append(ft["full_composite"])

    r, p = pearsonr(mini_scores, full_scores)

    # Per-variable dims only (S1-S4, B) — these actually differ between Mini and Full
    variable_dims = ["S1", "S2", "S3", "S4", "B"]
    v_mini = []
    v_full = []
    for dim in variable_dims:
        v_mini.extend([bl_mini_dims[dim], ft_mini_dims[dim]])
        v_full.extend([bl["full_dims"][dim], ft["full_dims"][dim]])
    r_var, p_var = pearsonr(v_mini, v_full)

    per_dim = {}
    for dim in dimensions:
        bl_mini = bl_mini_dims[dim]
        ft_mini = ft_mini_dims[dim]
        bl_full = bl["full_dims"][dim]
        ft_full = ft["full_dims"][dim]
        per_dim[dim] = {
            "BL_mini": round(bl_mini, 2),
            "BL_full": round(bl_full, 2),
            "FT_mini": round(ft_mini, 2),
            "FT_full": round(ft_full, 2),
            "delta_BL": round(bl_mini - bl_full, 2),
            "delta_FT": round(ft_mini - ft_full, 2),
            "fixed": dim not in variable_dims,
        }
    per_dim["Composite"] = {
        "BL_mini": round(bl_mini_composite, 2),
        "BL_full": round(bl["full_composite"], 2),
        "FT_mini": round(ft_mini_composite, 2),
        "FT_full": round(ft["full_composite"], 2),
        "delta_BL": round(bl_mini_composite - bl["full_composite"], 2),
        "delta_FT": round(ft_mini_composite - ft["full_composite"], 2),
        "fixed": False,
    }

    return {
        "r": round(float(r), 4),
        "p_value": round(float(p), 6),
        "n_points": len(mini_scores),
        "r_variable_dims_only": round(float(r_var), 4),
        "p_variable": round(float(p_var), 6),
        "per_dim": per_dim,
        "bl_mini_composite": round(bl_mini_composite, 2),
        "ft_mini_composite": round(ft_mini_composite, 2),
    }


def bootstrap_ci(bl: dict, ft: dict, n: int = N_BOOTSTRAP) -> dict:
    """
    Bootstrap CI for Pearson r using N random 20-case subsets.
    Only variable dims (S1-S4, B) participate since MT dims are fixed.
    """
    variable_dims = ["S1", "S2", "S3", "S4", "B"]
    rs = []

    for seed in range(n):
        rng = np.random.RandomState(seed)
        idx_bl = rng.choice(50, size=MINI_N_CASES, replace=False)
        rng2 = np.random.RandomState(seed + n)
        idx_ft = rng2.choice(50, size=MINI_N_CASES, replace=False)

        bl_m = compute_mini_dims(bl, idx_bl)
        ft_m = compute_mini_dims(ft, idx_ft)

        v_mini = []
        v_full = []
        for dim in variable_dims:
            v_mini.extend([bl_m[dim], ft_m[dim]])
            v_full.extend([bl["full_dims"][dim], ft["full_dims"][dim]])

        try:
            r, _ = pearsonr(v_mini, v_full)
            if not np.isnan(r):
                rs.append(r)
        except Exception:
            pass

    rs = sorted(rs)
    return {
        "n_bootstrap": len(rs),
        "mean_r": round(float(np.mean(rs)), 4),
        "median_r": round(float(np.median(rs)), 4),
        "ci_95_low": round(float(np.percentile(rs, 2.5)), 4),
        "ci_95_high": round(float(np.percentile(rs, 97.5)), 4),
        "pct_above_08": round(float(np.mean(np.array(rs) >= 0.8) * 100), 1),
        "pct_above_06": round(float(np.mean(np.array(rs) >= 0.6) * 100), 1),
    }


def main():
    print("═" * 70)
    print("CCEE-Mini Correlation Validation")
    print("BL_pipeline c0bcbd73 (S11) + FT_pipeline Sprint 6")
    print("Method: retrospective bootstrap from per-case scores")
    print("═" * 70)
    print()

    bl = load_condition(BL_FILE)
    ft = load_condition(FT_FILE)

    print(f"BL Full composite: {bl['full_composite']:.1f} ({bl['n_cases']} cases)")
    print(f"FT Full composite: {ft['full_composite']:.1f} ({ft['n_cases']} cases)")
    print()

    # Primary correlation (seed=3407)
    print(f"Running primary correlation (seed={MINI_SEED}, N={MINI_N_CASES})...")
    result = run_correlation(bl, ft)

    print(f"\nPearson r (all dims):           {result['r']:.3f}  (p={result['p_value']:.4f})")
    print(f"Pearson r (variable dims only): {result['r_variable_dims_only']:.3f}  (p={result['p_variable']:.4f})")
    print(f"N data points (all dims):       {result['n_points']}")
    print()

    # Bootstrap CI
    print(f"Running bootstrap CI ({N_BOOTSTRAP} samples, variable dims only)...")
    ci = bootstrap_ci(bl, ft)

    print(f"\nBootstrap CI (95%): [{ci['ci_95_low']:.3f}, {ci['ci_95_high']:.3f}]")
    print(f"Mean r:    {ci['mean_r']:.3f}")
    print(f"Median r:  {ci['median_r']:.3f}")
    print(f"% samples r≥0.8: {ci['pct_above_08']:.1f}%")
    print(f"% samples r≥0.6: {ci['pct_above_06']:.1f}%")
    print()

    # Per-dimension table
    print("Per-dimension breakdown:")
    print(f"{'Dim':<12} {'BL_mini':>8} {'BL_full':>8} {'FT_mini':>8} {'FT_full':>8} {'ΔBL':>7} {'ΔFT':>7} {'type'}")
    print("─" * 75)
    for dim, v in result["per_dim"].items():
        tag = "fixed" if v.get("fixed") else "var"
        print(f"{dim:<12} {v['BL_mini']:>8.1f} {v['BL_full']:>8.1f} {v['FT_mini']:>8.1f} {v['FT_full']:>8.1f} {v['delta_BL']:>+7.1f} {v['delta_FT']:>+7.1f} {tag}")

    print()

    # Verdict
    r_primary = result["r_variable_dims_only"]
    print("═" * 70)
    print("VEREDICTO:")
    if r_primary >= 0.8:
        verdict = "VALID_GATE"
        msg = "✅ CCEE-Mini VÁLIDO como gate (r ≥ 0.8)"
    elif r_primary >= 0.6:
        verdict = "INFORMATIVE_ONLY"
        msg = "🟡 CCEE-Mini SOLO INFORMATIVO (0.6 ≤ r < 0.8)"
    else:
        verdict = "NOT_VALID"
        msg = "🔴 CCEE-Mini NO VÁLIDO (r < 0.6)"
    print(f"  r (variable dims) = {r_primary:.3f}")
    print(f"  {msg}")
    print("═" * 70)

    # Save outputs
    MEASUREMENTS_DIR.mkdir(parents=True, exist_ok=True)

    raw = {
        "verdict": verdict,
        "primary": result,
        "bootstrap_ci": ci,
        "meta": {
            "method": "retrospective_bootstrap",
            "bl_file": BL_FILE.name,
            "ft_file": FT_FILE.name,
            "mini_n_cases": MINI_N_CASES,
            "mini_seed": MINI_SEED,
            "fixed_dims_note": (
                "J_old, J_new, J6, K, G5, L, H are identical between Mini and Full "
                "because they derive from 5 MT conversations (independent of --cases N)"
            ),
        },
    }

    raw_path = MEASUREMENTS_DIR / "raw_correlation.json"
    raw_path.write_text(json.dumps(raw, indent=2))
    print(f"\nRaw data → {raw_path}")


if __name__ == "__main__":
    main()
