"""
CPE v3 Validate Metrics — Spearman correlation between automatic metrics and human scores.

Validates which automatic metrics (BERTScore, chrF++, etc.) correlate with
human judgement dimensions (fluency, coherence, style, etc.).

python3.11 shebang equivalent — run with:
    python3.11 tests/cpe_v3_validate_metrics.py \
      --human-scores tests/cpe_data/iris_bertran/results/human_eval_v3.json \
      --auto-scores tests/cpe_data/iris_bertran/sweep/cpe_v3_summary_*.json \
      --output docs/CPE_V3_METRIC_VALIDATION.md
"""

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── repo root on sys.path ────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ── Spearman implementation ───────────────────────────────────────────────────

def _rank(values: List[float]) -> List[float]:
    """Convert values to ranks (1-indexed, average ties)."""
    n = len(values)
    indexed = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n - 1 and values[indexed[j + 1]] == values[indexed[j]]:
            j += 1
        avg_rank = (i + j + 2) / 2.0  # 1-indexed
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1
    return ranks


def _pearson(x: List[float], y: List[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx  = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy  = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if sx == 0 or sy == 0:
        return 0.0
    return num / (sx * sy)


def _spearman_r(x: List[float], y: List[float]) -> Tuple[float, float]:
    """Compute Spearman rho and approximate p-value.

    Uses scipy.stats.spearmanr if available; otherwise ranks + Pearson.
    Returns (rho, p_value).
    """
    if len(x) != len(y) or len(x) < 3:
        return 0.0, 1.0

    try:
        from scipy.stats import spearmanr  # noqa: PLC0415
        res = spearmanr(x, y)
        return float(res.statistic), float(res.pvalue)
    except ImportError:
        pass

    rx = _rank(x)
    ry = _rank(y)
    rho = _pearson(rx, ry)

    # p-value from t-distribution approximation
    n = len(x)
    if abs(rho) >= 1.0:
        return rho, 0.0
    t_stat = rho * math.sqrt(n - 2) / math.sqrt(max(1e-15, 1.0 - rho ** 2))
    # Approximate two-tailed p-value using normal approx for large n
    # or simple t-distribution CDF approximation
    df = n - 2
    # Use a simple rational approximation for the t CDF
    def _t_cdf_approx(t: float, df: int) -> float:
        """Abramowitz & Stegun 26.7.8 approximation."""
        x_val = df / (df + t * t)
        # Regularized incomplete beta: I(x; df/2, 1/2)
        # Use the continued fraction / series approximation
        # For simplicity, use the normal approx when df >= 30
        if df >= 30:
            return float(0.5 * math.erfc(-t / math.sqrt(2)))
        # Wallis-like approximation for small df
        # p(t > |t_obs|) ≈ using the beta distribution
        a = df / 2.0
        b = 0.5
        # Simple approximation: shrink toward normal for df>=10
        if df >= 10:
            correction = 1.0 + t * t / (4.0 * df)
            z_approx = t / math.sqrt(correction)
            return float(0.5 * math.erfc(-z_approx / math.sqrt(2)))
        # Very small df: conservative (return 0.5 * something)
        # Approximate via the Student's t series
        # p_upper = integral from |t| to inf
        # For df=1: arctan, df=2: closed form, else recurse
        abs_t = abs(t)
        if df == 1:
            p_upper = 0.5 - math.atan(abs_t) / math.pi
        elif df == 2:
            p_upper = 0.5 * (1.0 - abs_t / math.sqrt(2.0 + abs_t * abs_t))
        else:
            # Use normal approx as fallback
            correction = 1.0 + abs_t * abs_t / (4.0 * df)
            z_approx = abs_t / math.sqrt(correction)
            p_upper = 0.5 * math.erfc(z_approx / math.sqrt(2))
        return 1.0 - p_upper  # CDF at t

    abs_t = abs(t_stat)
    p_upper = 1.0 - _t_cdf_approx(abs_t, df)
    p_value = 2.0 * p_upper  # two-tailed
    p_value = max(0.0, min(1.0, p_value))
    return round(rho, 6), round(p_value, 6)


def _sig_stars(p: Optional[float]) -> str:
    if p is None:
        return ""
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


# ── data loading ─────────────────────────────────────────────────────────────

def _load_json(path: Path, label: str):
    if not path.exists():
        print(f"ERROR: {label} not found at {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_human_scores(path: Path) -> Dict[str, Dict[str, float]]:
    """Load human evaluation JSON.

    Expected format:
      {"cases": [{"case_id": "...", "scores": {"fluency": 4, "coherence": 5, ...}}]}

    Returns:
      {case_id: {dimension: score}}
    """
    data = _load_json(path, "human scores")
    out: Dict[str, Dict[str, float]] = {}
    cases = data.get("cases", data) if isinstance(data, dict) else data
    for item in cases:
        cid = item.get("case_id") or item.get("id")
        scores = item.get("scores", {})
        if cid and scores:
            out[cid] = {k: float(v) for k, v in scores.items()}
    return out


def _load_auto_scores_from_summary(path: Path) -> Dict[str, Dict[str, float]]:
    """Extract per-case automatic metrics from a cpe_v3_summary JSON.

    Returns {case_id: {metric_name: value}}.
    Falls back to index-based IDs if per-case IDs are unavailable.
    """
    data = _load_json(path, f"auto scores {path}")
    per_case: Dict[str, Dict[str, float]] = {}

    # Pull per-case arrays from top-level
    chrf_scores  = data.get("_per_case_chrf", [])
    bs_scores    = data.get("_per_case_bertscore", [])

    # Also try nested under d2
    d2 = data.get("d2", {})
    if not chrf_scores:
        chrf_scores = d2.get("_per_case_chrf", [])
    if not bs_scores:
        bs_scores = d2.get("_per_case_bertscore", [])

    # We need case IDs — try to find them from run files referenced or from
    # a test_set.json in the same data directory
    # Strategy: derive creator from "creator" key, load test_set.json
    creator = data.get("creator", "")
    test_set_path = REPO_ROOT / "tests" / "cpe_data" / creator / "test_set.json"
    case_ids: List[str] = []
    if test_set_path.exists():
        with open(test_set_path, encoding="utf-8") as fh:
            ts_data = json.load(fh)
        case_ids = [c["id"] for c in ts_data.get("conversations", [])]

    n = max(len(chrf_scores), len(bs_scores))
    for i in range(n):
        cid = case_ids[i] if i < len(case_ids) else f"case_{i:03d}"
        entry: Dict[str, float] = {}
        if i < len(chrf_scores):
            entry["chrf"] = float(chrf_scores[i])
        if i < len(bs_scores):
            entry["bertscore_f1"] = float(bs_scores[i])
        per_case[cid] = entry

    # Add scalar metrics (same value for all cases — useful for cross-run validation)
    scalar_keys = [
        ("rouge_l",      "rouge_l"),
        ("bleu4",        "bleu4"),
        ("vocab_overlap","vocab_overlap"),
    ]
    for json_key, out_key in scalar_keys:
        val = d2.get(json_key)
        if val is not None:
            for cid in per_case:
                per_case[cid][out_key] = float(val)

    # D1 metrics (uniform per-run)
    d1 = data.get("d1", {})
    d1_scalars = [
        ("emoji_rate", "emoji_rate"),
        ("excl_rate",  "excl_rate"),
        ("char_mean",  "char_length"),
    ]
    for json_key, out_key in d1_scalars:
        val = d1.get(json_key)
        if val is not None:
            for cid in per_case:
                per_case[cid][out_key] = float(val)

    return per_case


# ── correlation table ─────────────────────────────────────────────────────────

AUTO_METRIC_LABELS = [
    "bertscore_f1",
    "chrf",
    "rouge_l",
    "bleu4",
    "vocab_overlap",
    "char_length",
    "emoji_rate",
    "excl_rate",
]

HUMAN_DIM_LABELS = [
    "fluency",
    "coherence",
    "style_consistency",
    "human_likeness",
    "expression_diversity",
]


def _build_correlation_table(
    human: Dict[str, Dict[str, float]],
    auto: Dict[str, Dict[str, float]],
) -> Dict[Tuple[str, str], Tuple[float, float]]:
    """Compute Spearman rho for each (auto_metric, human_dim) pair.

    Returns {(auto_metric, human_dim): (rho, p_value)}.
    """
    common_ids = sorted(set(human.keys()) & set(auto.keys()))
    if not common_ids:
        print(f"WARNING: No overlapping case IDs between human ({len(human)}) and auto ({len(auto)}) scores.")
    table: Dict[Tuple[str, str], Tuple[float, float]] = {}

    for auto_key in AUTO_METRIC_LABELS:
        for human_dim in HUMAN_DIM_LABELS:
            pairs = [
                (auto[cid][auto_key], human[cid][human_dim])
                for cid in common_ids
                if auto_key in auto.get(cid, {}) and human_dim in human.get(cid, {})
            ]
            if len(pairs) < 5:
                table[(auto_key, human_dim)] = (float("nan"), float("nan"))
                continue
            x = [p[0] for p in pairs]
            y = [p[1] for p in pairs]
            rho, p = _spearman_r(x, y)
            table[(auto_key, human_dim)] = (rho, p)

    return table


def _fmt_cell(rho: float, p: float) -> str:
    if math.isnan(rho):
        return "  N/A  "
    stars = _sig_stars(p)
    return f"{rho:+.2f}{stars:<2}"


def _print_correlation_table(
    table: Dict[Tuple[str, str], Tuple[float, float]],
    human_dims: List[str],
    auto_keys: List[str],
) -> str:
    """Print + return the table as plain text."""
    lines: List[str] = []

    col_width = 11
    label_width = 16

    header_parts = [f"{'Métrica auto':<{label_width}}"]
    for dim in human_dims:
        short = dim.replace("_", " ").title()[:9]
        header_parts.append(f"{short:^{col_width}}")
    header = " | ".join(header_parts)
    lines.append(header)
    lines.append("-" * len(header))

    for auto_key in auto_keys:
        label_map = {
            "bertscore_f1": "BERTScore F1",
            "chrf":         "chrF++",
            "rouge_l":      "ROUGE-L",
            "bleu4":        "BLEU-4",
            "vocab_overlap":"Vocab Overlap",
            "char_length":  "char_length",
            "emoji_rate":   "emoji_count",
            "excl_rate":    "has_exclamation",
        }
        label = label_map.get(auto_key, auto_key)
        row_parts = [f"{label:<{label_width}}"]
        for human_dim in human_dims:
            rho, p = table.get((auto_key, human_dim), (float("nan"), float("nan")))
            cell = _fmt_cell(rho, p)
            row_parts.append(f"{cell:^{col_width}}")
        lines.append(" | ".join(row_parts))

    lines.append("")
    lines.append("* p<0.05, ** p<0.01")
    return "\n".join(lines)


def _verdict(
    table: Dict[Tuple[str, str], Tuple[float, float]],
    auto_keys: List[str],
    human_dims: List[str],
) -> str:
    """Generate VALIDATION / INFORMATIONAL / DISCARD verdict."""
    lines: List[str] = []
    lines.append("\nVALIDATION VERDICT")

    validated: List[str] = []
    informational: List[str] = []
    discard: List[str] = []

    for auto_key in auto_keys:
        best_rho = float("-inf")
        best_pair = ""
        any_above_05 = False
        for human_dim in human_dims:
            rho, p = table.get((auto_key, human_dim), (float("nan"), float("nan")))
            if math.isnan(rho):
                continue
            if abs(rho) > abs(best_rho):
                best_rho = rho
                best_pair = human_dim
            if abs(rho) >= 0.5:
                any_above_05 = True

        label_map = {
            "bertscore_f1": "BERTScore F1",
            "chrf":         "chrF++",
            "rouge_l":      "ROUGE-L",
            "bleu4":        "BLEU-4",
            "vocab_overlap":"Vocab Overlap",
            "char_length":  "char_length",
            "emoji_rate":   "emoji_count",
            "excl_rate":    "has_exclamation",
        }
        label = label_map.get(auto_key, auto_key)

        if math.isnan(best_rho):
            discard.append(f"{label} (no data)")
        elif abs(best_rho) >= 0.5:
            validated.append(f"{label} ({best_pair.replace('_',' ')}, ρ={best_rho:+.2f})")
        elif abs(best_rho) >= 0.3:
            informational.append(f"{label} (best ρ={best_rho:+.2f} with {best_pair.replace('_',' ')})")
        else:
            discard.append(f"{label} (ρ<0.3 all dims)")

    if validated:
        lines.append(f"- VALIDATED (ρ>0.5): {', '.join(validated)}")
    if informational:
        lines.append(f"- INFORMATIONAL (0.3<ρ<0.5): {', '.join(informational)}")
    if discard:
        lines.append(f"- DISCARD (ρ<0.3 all): {', '.join(discard)}")

    return "\n".join(lines)


# ── markdown export ───────────────────────────────────────────────────────────

def _to_markdown(
    table_text: str,
    verdict_text: str,
    human_path: str,
    auto_paths: List[str],
    n_common: int,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# CPE v3 — Metric Validation Report",
        f"\n_Generated: {now}_\n",
        "## Overview",
        f"",
        f"- Human scores: `{human_path}`",
        f"- Auto scores:  {', '.join(f'`{p}`' for p in auto_paths)}",
        f"- Overlapping cases: {n_common}",
        "",
        "## Spearman Correlation Table",
        "",
        "```",
        "SPEARMAN CORRELATION — Auto Metrics vs Human Scores",
        "",
        table_text,
        "```",
        "",
        "## Verdict",
        "",
        "```",
        verdict_text.strip(),
        "```",
    ]
    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CPE v3 Metric Validation — Spearman correlation between auto and human scores"
    )
    parser.add_argument("--human-scores", required=True,
                        help="Path to human evaluation JSON")
    parser.add_argument("--auto-scores",  required=True, nargs="+",
                        help="Path(s) to cpe_v3_summary JSON file(s) (supports glob expansion)")
    parser.add_argument("--output",       default=None,
                        help="Output path for Markdown report (optional)")
    args = parser.parse_args()

    # ── load human scores ───────────────────────────────────────────────────
    human_path = Path(args.human_scores)
    human_scores = _load_human_scores(human_path)
    print(f"Loaded {len(human_scores)} human-scored cases from {human_path}")

    # ── load auto scores ────────────────────────────────────────────────────
    auto_paths: List[Path] = []
    for pattern in args.auto_scores:
        p = Path(pattern)
        if "*" in str(p) or "?" in str(p):
            auto_paths.extend(sorted(p.parent.glob(p.name)))
        else:
            auto_paths.append(p)

    if not auto_paths:
        print("ERROR: no auto-score files matched.")
        sys.exit(1)

    # Merge per-case auto scores from all files
    merged_auto: Dict[str, Dict[str, float]] = {}
    for ap in auto_paths:
        per_case = _load_auto_scores_from_summary(ap)
        for cid, metrics in per_case.items():
            if cid not in merged_auto:
                merged_auto[cid] = {}
            merged_auto[cid].update(metrics)

    print(f"Loaded auto scores for {len(merged_auto)} cases from {len(auto_paths)} file(s)")

    # ── determine which human dims are present ──────────────────────────────
    present_human_dims: List[str] = []
    for dim in HUMAN_DIM_LABELS:
        if any(dim in scores for scores in human_scores.values()):
            present_human_dims.append(dim)
    if not present_human_dims:
        print("WARNING: none of the expected human dimensions found in human scores.")
        present_human_dims = HUMAN_DIM_LABELS  # show empty table anyway

    present_auto_keys: List[str] = []
    for key in AUTO_METRIC_LABELS:
        if any(key in metrics for metrics in merged_auto.values()):
            present_auto_keys.append(key)
    if not present_auto_keys:
        print("WARNING: no known auto metrics found in auto scores.")
        present_auto_keys = AUTO_METRIC_LABELS

    # ── compute correlations ────────────────────────────────────────────────
    table = _build_correlation_table(human_scores, merged_auto)
    n_common = len(set(human_scores.keys()) & set(merged_auto.keys()))

    # ── print table ─────────────────────────────────────────────────────────
    print(f"\nSPEARMAN CORRELATION — Auto Metrics vs Human Scores\n")
    table_text = _print_correlation_table(table, present_human_dims, present_auto_keys)
    print(table_text)

    verdict_text = _verdict(table, present_auto_keys, present_human_dims)
    print(verdict_text)

    # ── save markdown ────────────────────────────────────────────────────────
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        md = _to_markdown(
            table_text,
            verdict_text,
            str(human_path),
            [str(p) for p in auto_paths],
            n_common,
        )
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"\nSaved Markdown report: {out_path}")


if __name__ == "__main__":
    main()
