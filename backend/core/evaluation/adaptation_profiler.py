"""
CCEE Script 3: Adaptation Profiler

Analyzes how the creator adapts their style depending on trust level.
Segments leads by trust_score from relationship_dna, computes A1-A5
per segment, and measures adaptation direction and magnitude.
"""

import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psycopg2
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.evaluation.style_profile_builder import (
    EMOJI_RE,
    _get_conn,
    _percentiles,
    _resolve_creator_uuid,
)
from services.vocabulary_extractor import tokenize

# ---------------------------------------------------------------------------
# Trust segments
# ---------------------------------------------------------------------------

TRUST_SEGMENTS = {
    "UNKNOWN": (0.0, 0.3),
    "KNOWN": (0.3, 0.7),
    "CLOSE": (0.7, 0.9),
    "INTIMATE": (0.9, 1.01),  # inclusive upper
}

MIN_MESSAGES_PER_SEGMENT = 10


def _trust_segment(score: float) -> str:
    for name, (lo, hi) in TRUST_SEGMENTS.items():
        if lo <= score < hi:
            return name
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Adaptation Profiler
# ---------------------------------------------------------------------------

class AdaptationProfiler:
    """Profiles how a creator adapts style based on relationship trust level."""

    def build(self, creator_id: str) -> Dict[str, Any]:
        """Build adaptation profile for a creator.

        Args:
            creator_id: Creator slug

        Returns:
            Adaptation profile with per-segment metrics and direction analysis.
        """
        conn = _get_conn()
        try:
            creator_uuid = _resolve_creator_uuid(conn, creator_id)
            if not creator_uuid:
                raise ValueError(f"Creator '{creator_id}' not found")

            segmented = self._fetch_messages_with_trust(conn, creator_id, creator_uuid)

            per_segment = {}
            for segment, messages in segmented.items():
                if len(messages) < MIN_MESSAGES_PER_SEGMENT:
                    per_segment[segment] = {
                        "status": "insufficient_data",
                        "message_count": len(messages),
                        "min_required": MIN_MESSAGES_PER_SEGMENT,
                    }
                    continue
                per_segment[segment] = self._compute_segment_metrics(messages)

            adaptation = self._compute_adaptation_direction(per_segment)

            return {
                "creator_id": creator_id,
                "segments": per_segment,
                "adaptation": adaptation,
                "segment_counts": {
                    seg: len(msgs) for seg, msgs in segmented.items()
                },
            }
        finally:
            conn.close()

    def _fetch_messages_with_trust(
        self, conn, creator_id: str, creator_uuid: str,
        page_size: int = 5000,
    ) -> Dict[str, List[str]]:
        """Fetch creator messages grouped by trust segment of the lead."""
        segmented: Dict[str, List[str]] = defaultdict(list)
        offset = 0

        with conn.cursor() as cur:
            while True:
                cur.execute("""
                    SELECT m.content, COALESCE(rd.trust_score, 0.0) AS trust
                    FROM messages m
                    JOIN leads l ON l.id = m.lead_id
                    LEFT JOIN relationship_dna rd
                        ON rd.creator_id = %s
                        AND rd.follower_id = l.platform_user_id
                    WHERE l.creator_id = CAST(%s AS uuid)
                      AND m.role = 'assistant'
                      AND m.content IS NOT NULL
                      AND LENGTH(m.content) > 2
                      AND m.deleted_at IS NULL
                      AND COALESCE(m.approved_by, 'human')
                          NOT IN ('auto', 'autopilot')
                    ORDER BY m.created_at
                    LIMIT %s OFFSET %s
                """, (creator_id, creator_uuid, page_size, offset))

                rows = cur.fetchall()
                if not rows:
                    break
                for content, trust in rows:
                    segment = _trust_segment(float(trust))
                    segmented[segment].append(content)
                offset += page_size

        return dict(segmented)

    def _compute_segment_metrics(self, messages: List[str]) -> Dict[str, Any]:
        """Compute A1-A5 metrics for a segment of messages."""
        # A1: Length
        lengths = [len(m) for m in messages]

        # A2: Emoji rate
        emoji_flags = [1.0 if EMOJI_RE.search(m) else 0.0 for m in messages]
        emoji_rate = sum(emoji_flags) / len(emoji_flags)

        # A3: Exclamation rate
        excl_flags = [1.0 if "!" in m else 0.0 for m in messages]
        excl_rate = sum(excl_flags) / len(excl_flags)

        # A4: Question rate
        q_flags = [1.0 if "?" in m else 0.0 for m in messages]
        q_rate = sum(q_flags) / len(q_flags)

        # A5: Vocabulary diversity (unique words / total words)
        all_tokens = []
        for m in messages:
            all_tokens.extend(tokenize(m))
        vocab_diversity = (
            len(set(all_tokens)) / len(all_tokens) if all_tokens else 0.0
        )

        return {
            "message_count": len(messages),
            "A1_length": _percentiles(lengths),
            "A2_emoji_rate": emoji_rate,
            "A3_exclamation_rate": excl_rate,
            "A4_question_rate": q_rate,
            "A5_vocab_diversity": vocab_diversity,
        }

    def _compute_adaptation_direction(
        self, per_segment: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze if creator adapts style with trust level.

        Checks if metrics trend in a direction as trust increases:
        - Length: typically increases with trust (more expressive)
        - Emoji: typically increases with trust
        - Exclamations: typically increases with trust
        - Questions: may decrease (less interrogative with close people)
        - Vocab diversity: may decrease (more relaxed, repetitive)

        Returns direction vectors and adaptation_score (0-100).
        """
        ordered = ["UNKNOWN", "KNOWN", "CLOSE", "INTIMATE"]
        valid_segments = [
            s for s in ordered
            if s in per_segment and isinstance(per_segment[s], dict)
            and "A1_length" in per_segment[s]
        ]

        if len(valid_segments) < 2:
            return {
                "adaptation_score": 50.0,
                "status": "insufficient_segments",
                "valid_segments": len(valid_segments),
                "directions": {},
            }

        # Extract metric values in trust order
        metrics = {
            "length_mean": [],
            "emoji_rate": [],
            "exclamation_rate": [],
            "question_rate": [],
            "vocab_diversity": [],
        }
        for seg in valid_segments:
            d = per_segment[seg]
            metrics["length_mean"].append(d["A1_length"]["mean"])
            metrics["emoji_rate"].append(d["A2_emoji_rate"])
            metrics["exclamation_rate"].append(d["A3_exclamation_rate"])
            metrics["question_rate"].append(d["A4_question_rate"])
            metrics["vocab_diversity"].append(d["A5_vocab_diversity"])

        # Compute direction for each metric (slope of linear fit)
        directions = {}
        for metric_name, values in metrics.items():
            if len(values) < 2:
                directions[metric_name] = {"direction": "neutral", "magnitude": 0.0}
                continue
            x = np.arange(len(values), dtype=float)
            y = np.array(values, dtype=float)
            # Normalize y to [0, 1] for comparison
            y_range = y.max() - y.min()
            if y_range > 0:
                slope = np.polyfit(x, y, 1)[0]
                norm_slope = slope / y_range
            else:
                norm_slope = 0.0

            if norm_slope > 0.1:
                direction = "increases_with_trust"
            elif norm_slope < -0.1:
                direction = "decreases_with_trust"
            else:
                direction = "neutral"

            directions[metric_name] = {
                "direction": direction,
                "magnitude": round(abs(norm_slope), 4),
                "values_by_segment": {
                    seg: round(val, 4)
                    for seg, val in zip(valid_segments, values)
                },
            }

        # Adaptation score: how many metrics show clear direction?
        adapting = sum(
            1 for d in directions.values()
            if d["direction"] != "neutral"
        )
        adaptation_score = min(100.0, (adapting / len(directions)) * 100)

        return {
            "adaptation_score": round(adaptation_score, 1),
            "valid_segments": len(valid_segments),
            "directions": directions,
        }


# ---------------------------------------------------------------------------
# Save + CLI
# ---------------------------------------------------------------------------

def save_adaptation_profile(
    profile: Dict, creator_id: str, output_dir: str = "evaluation_profiles"
):
    os.makedirs(os.path.join(output_dir, creator_id), exist_ok=True)
    path = os.path.join(output_dir, creator_id, "adaptation_profile.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False, default=str)
    return path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build adaptation profile")
    parser.add_argument("--creator", required=True)
    args = parser.parse_args()

    profiler = AdaptationProfiler()
    profile = profiler.build(args.creator)
    path = save_adaptation_profile(profile, args.creator)
    print(f"Adaptation profile saved to {path}")
    print(f"  Segments: {profile['segment_counts']}")
    print(f"  Adaptation score: {profile['adaptation']['adaptation_score']}")
