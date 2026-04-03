"""
CCEE Script 2: Strategy Map Builder

Analyzes what STRATEGY the creator uses for each type of lead input.
Produces a distribution of strategies per input type from real message pairs.
Universal — strategies are classified via content heuristics, not LLM.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.conversation_boundary import ConversationBoundaryDetector
from core.evaluation.style_profile_builder import (
    EMOJI_RE,
    _MEDIA_PREFIXES,
    classify_context,
    _get_conn,
    _resolve_creator_uuid,
)

# ---------------------------------------------------------------------------
# Strategy classification
# ---------------------------------------------------------------------------

# Validation markers (multilingual)
_VALIDATION_MARKERS = frozenset({
    # CA
    "entenc", "ostres", "uf", "vaja", "cert", "clar", "ja",
    "comprenc", "ho sento", "normal",
    # ES
    "entiendo", "claro", "uf", "vaya", "ostras", "qué fuerte",
    "lo siento", "normal", "te entiendo",
    # EN
    "i understand", "of course", "oh no", "i see", "totally",
    "that makes sense", "i hear you",
    # PT
    "entendo", "claro", "puxa",
    # IT
    "capisco", "certo", "oddio",
})

_REDIRECT_MARKERS = frozenset({
    # CA
    "mira", "millor", "et recomano", "escriu-me", "fes un cop d'ull",
    # ES
    "mira", "mejor", "te recomiendo", "escríbeme", "echa un vistazo",
    # EN
    "check out", "i suggest", "you should try", "take a look",
    "better to", "reach out",
    # PT
    "olha", "melhor", "recomendo",
    # IT
    "guarda", "meglio", "ti consiglio",
})

_INFORM_INDICATORS = re.compile(
    r"(\d+\s*€|€\s*\d+|\d+[.,]\d+\s*€|https?://|www\.|"
    r"\d{1,2}:\d{2}|\d{1,2}h|\blunes\b|\bmartes\b|\blunes\b|"
    r"\bdilluns\b|\bdimarts\b|\bmonday\b|\btuesday\b)",
    re.IGNORECASE,
)


def _word_overlap(text_a: str, text_b: str) -> float:
    """Jaccard similarity between word sets."""
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def classify_strategy(user_msg: str, creator_response: str) -> str:
    """Classify the creator's response strategy.

    Strategies (priority order):
    - MIRROR: short response reflecting user tone (< 15 chars, has emoji or high overlap)
    - ASK: response contains a question
    - INFORM: response contains factual data (prices, schedules, URLs)
    - REDIRECT: response redirects to another channel/action
    - VALIDATE: response acknowledges emotion
    - IGNORE: very short or no content overlap
    """
    resp = creator_response.strip()
    resp_lower = resp.lower()
    resp_len = len(resp)

    # MIRROR: short + emoji or high overlap
    if resp_len < 15:
        if EMOJI_RE.search(resp) or _word_overlap(user_msg, resp) > 0.3:
            return "MIRROR"

    # ASK: contains question mark
    if "?" in resp:
        return "ASK"

    # INFORM: contains prices, times, URLs, schedule words
    if _INFORM_INDICATORS.search(resp):
        return "INFORM"

    # REDIRECT: redirect markers
    if any(m in resp_lower for m in _REDIRECT_MARKERS):
        return "REDIRECT"

    # VALIDATE: empathetic markers
    if any(m in resp_lower for m in _VALIDATION_MARKERS):
        return "VALIDATE"

    # IGNORE: very low overlap + short
    if resp_len < 30 and _word_overlap(user_msg, resp) < 0.05:
        return "IGNORE"

    # Default: check overlap
    if _word_overlap(user_msg, resp) < 0.05:
        return "REDIRECT"

    return "VALIDATE"


# ---------------------------------------------------------------------------
# Strategy Map Builder
# ---------------------------------------------------------------------------

STRATEGY_TYPES = ("MIRROR", "VALIDATE", "INFORM", "REDIRECT", "ASK", "IGNORE")
INPUT_TYPES = (
    "EMOJI_ONLY", "GREETING", "QUESTION_SERVICE", "EMOTIONAL",
    "HEALTH", "LAUGH", "MEDIA", "OTHER",
)


class StrategyMapBuilder:
    """Builds strategy distribution map from real creator conversations."""

    def __init__(self):
        self._boundary_detector = ConversationBoundaryDetector()

    def build(self, creator_id: str) -> Dict[str, Any]:
        """Build strategy map for a creator.

        Args:
            creator_id: Creator slug (e.g. 'iris_bertran')

        Returns:
            Strategy map with distributions per input type.
        """
        conn = _get_conn()
        try:
            creator_uuid = _resolve_creator_uuid(conn, creator_id)
            if not creator_uuid:
                raise ValueError(f"Creator '{creator_id}' not found")

            sessions = self._fetch_sessions(conn, creator_uuid)
            pairs = self._extract_pairs(sessions)

            if not pairs:
                raise ValueError(f"No message pairs found for '{creator_id}'")

            strategy_map = self._build_distributions(pairs)

            return {
                "creator_id": creator_id,
                "total_sessions": len(sessions),
                "total_pairs": len(pairs),
                "strategy_map": strategy_map,
                "global_strategy_distribution": self._global_distribution(pairs),
            }
        finally:
            conn.close()

    def _fetch_sessions(
        self, conn, creator_uuid: str
    ) -> List[List[Dict]]:
        """Fetch messages grouped by lead, then segment into sessions."""
        all_sessions = []

        # Single query: all messages ordered by lead + time
        with conn.cursor() as cur:
            cur.execute("""
                SELECT m.lead_id, m.role, m.content, m.created_at
                FROM messages m
                JOIN leads l ON l.id = m.lead_id
                WHERE l.creator_id = CAST(%s AS uuid)
                  AND m.deleted_at IS NULL
                  AND m.content IS NOT NULL
                  AND LENGTH(m.content) > 0
                ORDER BY m.lead_id, m.created_at
            """, (creator_uuid,))

            # Group by lead_id in Python
            current_lead = None
            current_msgs = []
            for lead_id, role, content, created_at in cur:
                if lead_id != current_lead:
                    if len(current_msgs) >= 2:
                        sessions = self._boundary_detector.segment(current_msgs)
                        all_sessions.extend(sessions)
                    current_lead = lead_id
                    current_msgs = []
                current_msgs.append({
                    "role": role, "content": content, "created_at": created_at,
                })

            # Flush last lead
            if len(current_msgs) >= 2:
                sessions = self._boundary_detector.segment(current_msgs)
                all_sessions.extend(sessions)

        return all_sessions

    def _extract_pairs(
        self, sessions: List[List[Dict]]
    ) -> List[Tuple[str, str, str]]:
        """Extract (input_type, user_msg, creator_response) from sessions."""
        pairs = []
        for session in sessions:
            for i in range(len(session) - 1):
                if (session[i]["role"] == "user"
                        and session[i + 1]["role"] == "assistant"):
                    user_msg = session[i]["content"]
                    creator_msg = session[i + 1]["content"]
                    input_type = classify_context(user_msg)
                    pairs.append((input_type, user_msg, creator_msg))
        return pairs

    def _build_distributions(
        self, pairs: List[Tuple[str, str, str]]
    ) -> Dict[str, Dict[str, float]]:
        """Build strategy distribution per input type."""
        by_input: Dict[str, List[str]] = defaultdict(list)

        for input_type, user_msg, creator_msg in pairs:
            strategy = classify_strategy(user_msg, creator_msg)
            by_input[input_type].append(strategy)

        result = {}
        for input_type in INPUT_TYPES:
            strategies = by_input.get(input_type, [])
            if not strategies:
                result[input_type] = {
                    "distribution": {},
                    "count": 0,
                    "dominant": None,
                }
                continue

            counts = Counter(strategies)
            total = len(strategies)
            dist = {s: round(counts.get(s, 0) / total, 4) for s in STRATEGY_TYPES}
            # Remove zero entries
            dist = {k: v for k, v in dist.items() if v > 0}
            dominant = counts.most_common(1)[0][0]
            result[input_type] = {
                "distribution": dist,
                "count": total,
                "dominant": dominant,
            }

        return result

    def _global_distribution(
        self, pairs: List[Tuple[str, str, str]]
    ) -> Dict[str, float]:
        """Compute overall strategy distribution across all input types."""
        all_strategies = [
            classify_strategy(user_msg, creator_msg)
            for _, user_msg, creator_msg in pairs
        ]
        counts = Counter(all_strategies)
        total = len(all_strategies)
        return {s: round(counts.get(s, 0) / total, 4) for s in STRATEGY_TYPES if counts.get(s, 0) > 0}


# ---------------------------------------------------------------------------
# Save + CLI
# ---------------------------------------------------------------------------

def save_strategy_map(
    strategy_map: Dict, creator_id: str, output_dir: str = "evaluation_profiles"
):
    os.makedirs(os.path.join(output_dir, creator_id), exist_ok=True)
    path = os.path.join(output_dir, creator_id, "strategy_map.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(strategy_map, f, indent=2, ensure_ascii=False, default=str)
    return path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build strategy map for a creator")
    parser.add_argument("--creator", required=True)
    args = parser.parse_args()

    builder = StrategyMapBuilder()
    result = builder.build(args.creator)
    path = save_strategy_map(result, args.creator)
    print(f"Strategy map saved to {path}")
    print(f"  Sessions: {result['total_sessions']}")
    print(f"  Pairs: {result['total_pairs']}")
    print(f"  Global: {result['global_strategy_distribution']}")
