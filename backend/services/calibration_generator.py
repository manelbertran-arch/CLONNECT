"""
Calibration Generator — auto-generate calibration files from conversation history.

Analyzes a creator's manual responses to compute baseline stats and select
diverse few-shot examples. Output is compatible with calibration_loader.py.

All stats (language, length, emoji rate) are computed from data — nothing hardcoded.
"""

import json
import logging
import os
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CALIBRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "calibrations",
)

# ─── Language detection (reused from calibration_loader) ─────────────

_CA_WORDS = re.compile(
    r'\b(vaig|però|molt|avui|demà|tinc|estic|puc|podem|podeu|que fas|que et|que em|'
    r'gràcies|fins |dilluns|dimarts|dimecres|dijous|divendres|dissabte|diumenge|'
    r'doncs|ara |anem|hem |heu |han |venir|vine |vindràs|vindre|bon dia|bona)\b',
    re.IGNORECASE,
)
_ES_WORDS = re.compile(
    r'\b(tengo|tienes|tiene|tenemos|pero |muy |mucho|estoy|estás|estamos|'
    r'soy|eres|fue|fui|hoy |mañana|gracias|señor|señora|buenas|buenos|'
    r'qué tal|cómo estás|hasta luego|me llamo|me ha|lo que|lo sé)\b',
    re.IGNORECASE,
)
_ES_TILDE_N = re.compile(r'[ñÑ]')
_EMOJI_RE = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]')

# ─── Type classification ────────────────────────────────────────────

_PRECIO_KW = re.compile(
    r'\b(preu|precio|cost|euros?|\d+€|apuntar|reservar|classe|clase|'
    r'horari|horario|dispo|matrícula|promo|descompte|pack|bono|mensual|abonament)\b',
    re.IGNORECASE,
)
_OBJECION_KW = re.compile(
    r'\b(no puedo|no puc|difícil|complicad|caro|car |lejos|lluny|'
    r'miedo|ocupad|liada|liado|dubte|duda|cancelar|baja|deixar)\b',
    re.IGNORECASE,
)
_SALUDO_KW = re.compile(
    r'^(hola|hey|holaaa*|bon dia|bona tarda|buenas|buenos|ei+|'
    r'que tal|qué tal|hello)',
    re.IGNORECASE,
)
_PERSONAL_KW = re.compile(
    r'\b(familia|mare|pare|fill|filla|gos|gat|perro|gato|novia|novio|'
    r'pareja|cumpleaños|aniversari|vacaciones|vacances|feina|trabajo|casa)\b',
    re.IGNORECASE,
)


def _detect_language(text: str) -> str:
    """Detect language of text. Returns 'ca', 'es', or 'mixto'."""
    ca = len(_CA_WORDS.findall(text))
    es = len(_ES_WORDS.findall(text)) + len(_ES_TILDE_N.findall(text))
    if ca > 0 and es > 0:
        return "mixto"
    if ca > 0:
        return "ca"
    if es > 0:
        return "es"
    return "unknown"


def _classify_type(user_msg: str, creator_msg: str) -> str:
    """Classify conversation type from message pair."""
    combined = f"{user_msg} {creator_msg}"
    if _PERSONAL_KW.search(combined):
        return "personal"
    if _PRECIO_KW.search(combined):
        return "precio"
    if _OBJECION_KW.search(user_msg):
        return "objecion"
    if _SALUDO_KW.match(user_msg.strip()):
        return "saludo"
    if len(user_msg.strip()) <= 15:
        return "saludo"
    return "conversacional"


# ─── Core generation ─────────────────────────────────────────────────

def _compute_baseline(responses: List[str]) -> Dict:
    """Compute baseline stats from all creator responses."""
    if not responses:
        return {}

    lengths = [len(r) for r in responses]
    has_emoji = [bool(_EMOJI_RE.search(r)) for r in responses]
    has_excl = [("!" in r) for r in responses]
    has_question = [("?" in r) for r in responses]

    median_len = int(statistics.median(lengths))
    # soft_max: 90th percentile
    sorted_lens = sorted(lengths)
    p90_idx = min(int(len(sorted_lens) * 0.9), len(sorted_lens) - 1)
    soft_max = sorted_lens[p90_idx]

    # Detect languages across all responses
    lang_counts = Counter(_detect_language(r) for r in responses)
    total = sum(lang_counts.values())
    languages = {
        lang: round(count / total * 100, 1)
        for lang, count in lang_counts.most_common()
        if lang != "unknown"
    }

    return {
        "median_length": median_len,
        "emoji_pct": round(sum(has_emoji) / len(responses) * 100, 1),
        "exclamation_pct": round(sum(has_excl) / len(responses) * 100, 1),
        "question_frequency_pct": round(sum(has_question) / len(responses) * 100, 1),
        "soft_max": soft_max,
        "languages": languages,
        "total_responses_analyzed": len(responses),
    }


def _select_diverse_examples(
    pairs: List[Dict],
    target_n: int = 50,
) -> List[Dict]:
    """Select diverse few-shot examples balancing type and language."""
    if len(pairs) <= target_n:
        return pairs

    # Group by (type, language)
    buckets: Dict[Tuple[str, str], List[Dict]] = {}
    for p in pairs:
        key = (p["context"], p["language"])
        buckets.setdefault(key, []).append(p)

    # Round-robin selection from each bucket
    selected = []
    selected_set = set()

    # First pass: at least 1 from each bucket
    for key, bucket in sorted(buckets.items()):
        if bucket:
            ex = bucket[0]
            uid = (ex["user_message"], ex["response"])
            if uid not in selected_set:
                selected.append(ex)
                selected_set.add(uid)

    # Second pass: round-robin until target
    idx_per_bucket = {k: 1 for k in buckets}
    while len(selected) < target_n:
        added = False
        for key, bucket in sorted(buckets.items()):
            if len(selected) >= target_n:
                break
            idx = idx_per_bucket.get(key, 0)
            if idx < len(bucket):
                ex = bucket[idx]
                uid = (ex["user_message"], ex["response"])
                if uid not in selected_set:
                    selected.append(ex)
                    selected_set.add(uid)
                    added = True
                idx_per_bucket[key] = idx + 1
        if not added:
            break

    return selected


def generate_calibration(
    creator_id: str,
    creator_uuid: str,
    min_examples: int = 30,
    max_examples: int = 50,
) -> Optional[Dict]:
    """Generate calibration file from DB conversation history.

    Queries messages where the creator responded manually (copilot_action IS NULL),
    computes baseline stats, and selects diverse few-shot examples.

    Returns the calibration dict (also saved to disk), or None if insufficient data.
    """
    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        # Get all user→creator manual response pairs
        q = text("""
            WITH ordered AS (
                SELECT
                    m.lead_id,
                    m.role,
                    m.content,
                    m.copilot_action,
                    m.created_at,
                    LAG(m.role) OVER (PARTITION BY m.lead_id ORDER BY m.created_at) AS prev_role,
                    LAG(m.content) OVER (PARTITION BY m.lead_id ORDER BY m.created_at) AS prev_content
                FROM messages m
                JOIN leads l ON l.id = m.lead_id
                WHERE l.creator_id = :creator_uuid
                  AND m.created_at >= NOW() - INTERVAL '3 months'
                  AND m.content IS NOT NULL
                  AND LENGTH(m.content) > 0
            )
            SELECT
                lead_id,
                prev_content AS user_message,
                content AS creator_response,
                created_at
            FROM ordered
            WHERE role = 'assistant'
              AND copilot_action IS NULL
              AND prev_role = 'user'
              AND prev_content IS NOT NULL
              AND LENGTH(prev_content) >= 2
              AND LENGTH(content) > 5
            ORDER BY created_at DESC
            LIMIT 2000
        """)

        rows = session.execute(q, {"creator_uuid": creator_uuid}).fetchall()
        logger.info(
            "[CalGen] Found %d manual response pairs for %s",
            len(rows), creator_id,
        )

        if len(rows) < min_examples:
            logger.warning(
                "[CalGen] Only %d pairs (need %d), skipping calibration for %s",
                len(rows), min_examples, creator_id,
            )
            return None

        # Extract all creator responses for baseline computation
        all_responses = [r.creator_response for r in rows]
        baseline = _compute_baseline(all_responses)

        # Build candidate pairs with type/language classification
        candidates = []
        seen = set()
        for r in rows:
            user_msg = r.user_message.strip()
            creator_resp = r.creator_response.strip()

            # Deduplicate by response content
            if creator_resp in seen:
                continue
            seen.add(creator_resp)

            # Filter out error-like responses
            resp_lower = creator_resp.lower()
            if any(w in resp_lower for w in ("error", "traceback", "exception", "null")):
                continue
            # Filter stickers/media-only
            if creator_resp in ("[sticker]", "[image]", "[video]", "[audio]"):
                continue

            lang = _detect_language(creator_resp)
            if lang == "unknown":
                lang = _detect_language(user_msg)
            if lang == "unknown":
                lang = "mixto"

            conv_type = _classify_type(user_msg, creator_resp)

            candidates.append({
                "user_message": user_msg,
                "response": creator_resp,
                "context": conv_type,
                "language": lang,
                "length": len(creator_resp),
            })

        logger.info(
            "[CalGen] %d unique candidates after filtering for %s",
            len(candidates), creator_id,
        )

        # Select diverse subset
        examples = _select_diverse_examples(candidates, max_examples)

        # Compute context_soft_max per type from all responses
        type_lengths: Dict[str, List[int]] = {}
        for c in candidates:
            type_lengths.setdefault(c["context"], []).append(c["length"])

        context_soft_max = {}
        for ctx, lens in type_lengths.items():
            sorted_lens = sorted(lens)
            p90_idx = min(int(len(sorted_lens) * 0.9), len(sorted_lens) - 1)
            context_soft_max[ctx] = sorted_lens[p90_idx]

        # Build calibration dict
        calibration = {
            "creator": creator_id,
            "version": "auto_v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "baseline": baseline,
            "context_soft_max": context_soft_max,
            "few_shot_examples": examples,
        }

        # Save to disk (skip if a hand-curated file already exists)
        os.makedirs(CALIBRATIONS_DIR, exist_ok=True)
        cal_path = os.path.join(CALIBRATIONS_DIR, f"{creator_id}.json")
        if os.path.isfile(cal_path):
            existing = {}
            try:
                with open(cal_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
            if existing.get("version", "").startswith("auto_"):
                # Overwrite previous auto-generated version
                pass
            else:
                # Hand-curated file — don't overwrite, save as _auto variant
                cal_path = os.path.join(CALIBRATIONS_DIR, f"{creator_id}_auto.json")
                logger.info(
                    "[CalGen] Existing curated calibration found, saving as %s",
                    cal_path,
                )

        with open(cal_path, "w", encoding="utf-8") as f:
            json.dump(calibration, f, indent=2, ensure_ascii=False)

        logger.info(
            "[CalGen] Saved calibration for %s: %d examples, median_len=%d, "
            "emoji=%.1f%%, langs=%s → %s",
            creator_id, len(examples), baseline.get("median_length", 0),
            baseline.get("emoji_pct", 0), baseline.get("languages", {}),
            cal_path,
        )

        # Invalidate calibration cache so next load picks up new file
        from services.calibration_loader import invalidate_cache
        invalidate_cache(creator_id)

        return calibration

    finally:
        session.close()
