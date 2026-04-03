"""
CCEE Script 5: Calibrator

Calibrates CCEE sub-score weights using Spearman correlation
with human (creator) ratings. Given 50 human ratings (1-5) paired
with CCEE evaluations, finds optimal weights that maximize
correlation between composite score and human judgment.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def _rank(values: List[float]) -> List[float]:
    """Assign ranks to values (1-based, average ties)."""
    n = len(values)
    indexed = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n

    i = 0
    while i < n:
        j = i
        while j < n - 1 and values[indexed[j]] == values[indexed[j + 1]]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-based
        for k in range(i, j + 1):
            ranks[indexed[k]] = avg_rank
        i = j + 1

    return ranks


def spearman_rho(x: List[float], y: List[float]) -> float:
    """Compute Spearman rank correlation coefficient.

    Returns rho in [-1, 1]. 1 = perfect positive, -1 = perfect negative.
    """
    if len(x) != len(y) or len(x) < 3:
        return 0.0

    rx = _rank(x)
    ry = _rank(y)

    n = len(x)
    d_sq = sum((a - b) ** 2 for a, b in zip(rx, ry))
    rho = 1 - (6 * d_sq) / (n * (n ** 2 - 1))
    return max(-1.0, min(1.0, rho))


class CCEECalibrator:
    """Calibrates CCEE weights from human ratings."""

    def calibrate(
        self,
        human_ratings: List[float],
        ccee_evaluations: List[Dict],
    ) -> Dict[str, Any]:
        """Find optimal weights by maximizing Spearman with human ratings.

        Args:
            human_ratings: List of human ratings (1-5 scale)
            ccee_evaluations: List of CCEE result dicts, each with
                S1_style_fidelity, S2_response_quality,
                S3_strategic_alignment, S4_adaptation sub-dicts with 'score'.

        Returns:
            Dict with calibrated weights and correlation stats.
        """
        if len(human_ratings) != len(ccee_evaluations):
            raise ValueError("human_ratings and ccee_evaluations must have same length")
        if len(human_ratings) < 10:
            raise ValueError("Need at least 10 paired ratings for calibration")

        # Extract sub-scores
        s1_scores = [e["S1_style_fidelity"]["score"] for e in ccee_evaluations]
        s2_scores = [e["S2_response_quality"]["score"] for e in ccee_evaluations]
        s3_scores = [e["S3_strategic_alignment"]["score"] for e in ccee_evaluations]
        s4_scores = [e["S4_adaptation"]["score"] for e in ccee_evaluations]

        # Individual correlations
        rho_s1 = spearman_rho(s1_scores, human_ratings)
        rho_s2 = spearman_rho(s2_scores, human_ratings)
        rho_s3 = spearman_rho(s3_scores, human_ratings)
        rho_s4 = spearman_rho(s4_scores, human_ratings)

        # Grid search for best weights
        best_rho = -2.0
        best_weights = {"S1": 0.25, "S2": 0.25, "S3": 0.25, "S4": 0.25}

        # Search in 5% increments
        for w1 in range(0, 105, 5):
            for w2 in range(0, 105 - w1, 5):
                for w3 in range(0, 105 - w1 - w2, 5):
                    w4 = 100 - w1 - w2 - w3
                    ww = {
                        "S1": w1 / 100, "S2": w2 / 100,
                        "S3": w3 / 100, "S4": w4 / 100,
                    }
                    composite = [
                        ww["S1"] * s1 + ww["S2"] * s2 + ww["S3"] * s3 + ww["S4"] * s4
                        for s1, s2, s3, s4 in zip(
                            s1_scores, s2_scores, s3_scores, s4_scores
                        )
                    ]
                    rho = spearman_rho(composite, human_ratings)
                    if rho > best_rho:
                        best_rho = rho
                        best_weights = dict(ww)

        return {
            "calibrated_weights": best_weights,
            "composite_rho": round(best_rho, 4),
            "individual_rhos": {
                "S1": round(rho_s1, 4),
                "S2": round(rho_s2, 4),
                "S3": round(rho_s3, 4),
                "S4": round(rho_s4, 4),
            },
            "n_samples": len(human_ratings),
        }

    def save(
        self, weights: Dict, creator_id: str,
        output_dir: str = "evaluation_profiles",
    ) -> str:
        os.makedirs(os.path.join(output_dir, creator_id), exist_ok=True)
        path = os.path.join(output_dir, creator_id, "weights.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(weights, f, indent=2)
        return path

    @staticmethod
    def load(path: str) -> Optional[Dict]:
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
