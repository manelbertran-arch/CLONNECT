"""
Preference Profile Service — compute and format creator communication style profile.

Analyzes last 100 approved/edited messages to extract quantitative style preferences
(response length, emoji usage, question ending, formality) for injection into DM prompts.

Feature flag: ENABLE_PREFERENCE_PROFILE (default false)
"""

import logging
import re
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Simple TTL cache
_profile_cache: Dict[str, Any] = {}
_profile_cache_ts: Dict[str, float] = {}
_PROFILE_CACHE_TTL = 300  # seconds

# Emoji regex pattern
_EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF]+",
    re.UNICODE,
)


def compute_preference_profile(creator_db_id) -> Optional[Dict]:
    """Compute preference profile from last 100 approved/edited messages.

    Returns dict with response_length, emoji_usage, question_ending,
    cta_inclusion, formality metrics, or None if insufficient data.
    """
    cache_key = str(creator_db_id)
    now = time.time()
    if cache_key in _profile_cache:
        if now - _profile_cache_ts.get(cache_key, 0) < _PROFILE_CACHE_TTL:
            return _profile_cache[cache_key]

    from api.database import SessionLocal
    from api.models import Lead, Message

    session = SessionLocal()
    try:
        messages = (
            session.query(Message.content)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action.in_(["approved", "edited", "manual_override"]),
                Message.content.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .limit(100)
            .all()
        )

        contents = [m[0] for m in messages if m[0] and len(m[0].strip()) > 5]
        if len(contents) < 10:
            return None

        # Response length analysis
        lengths = [len(c) for c in contents]
        avg_len = sum(lengths) / len(lengths)
        min_len = min(lengths)
        max_len = max(lengths)

        if avg_len < 80:
            length_label = "muy_corta"
        elif avg_len < 150:
            length_label = "corta"
        elif avg_len < 300:
            length_label = "media"
        else:
            length_label = "larga"

        # Emoji usage
        emoji_count = sum(1 for c in contents if _EMOJI_RE.search(c))
        emoji_rate = emoji_count / len(contents)

        if emoji_rate > 0.6:
            emoji_style = "frecuente"
        elif emoji_rate > 0.2:
            emoji_style = "moderado"
        else:
            emoji_style = "sin_emojis"

        # Question ending
        question_count = sum(1 for c in contents if c.strip().endswith("?"))
        question_rate = question_count / len(contents)

        # CTA (call-to-action) inclusion — links, "escríbeme", "reserva", etc.
        cta_patterns = re.compile(
            r"(escr[ií]beme|reserva|agenda|link|http|www\.|compra|date de alta|suscr[ií]b)",
            re.IGNORECASE,
        )
        cta_count = sum(1 for c in contents if cta_patterns.search(c))
        cta_rate = cta_count / len(contents)

        # Formality — check for informal markers
        informal_markers = re.compile(
            r"\b(jaja|jeje|haha|xd|tío|bro|mola|crack|genial|brutal|curro)\b",
            re.IGNORECASE,
        )
        formal_markers = re.compile(
            r"\b(estimad[oa]|atentamente|cordial|le informo|quedo a su disposición)\b",
            re.IGNORECASE,
        )
        informal_count = sum(1 for c in contents if informal_markers.search(c))
        formal_count = sum(1 for c in contents if formal_markers.search(c))

        informal_rate = informal_count / len(contents)
        formal_rate = formal_count / len(contents)

        if formal_rate > 0.3:
            formality = "formal"
        elif informal_rate > 0.4:
            formality = "muy_informal"
        elif informal_rate > 0.15:
            formality = "informal"
        else:
            formality = "semi_formal"

        profile = {
            "response_length": {
                "min": min_len,
                "max": max_len,
                "avg": round(avg_len),
                "label": length_label,
            },
            "emoji_usage": {
                "rate": round(emoji_rate, 2),
                "style": emoji_style,
            },
            "question_ending": {
                "rate": round(question_rate, 2),
            },
            "cta_inclusion": {
                "rate": round(cta_rate, 2),
            },
            "formality": {
                "level": formality,
            },
            "sample_size": len(contents),
        }

        _profile_cache[cache_key] = profile
        _profile_cache_ts[cache_key] = now
        return profile

    except Exception as e:
        logger.error("[PREF_PROFILE] compute error: %s", e)
        return None
    finally:
        session.close()


def format_preference_profile_for_prompt(profile: Dict, creator_name: str = "") -> str:
    """Format profile dict into a prompt injection block."""
    if not profile:
        return ""

    length = profile.get("response_length", {})
    emoji = profile.get("emoji_usage", {})
    question = profile.get("question_ending", {})
    formality = profile.get("formality", {})

    length_desc = f"{length.get('avg', '?')} chars ({length.get('label', '?')})"
    emoji_desc = f"{emoji.get('style', '?')} ({int(emoji.get('rate', 0) * 100)}%)"
    question_desc = "frecuente" if question.get("rate", 0) > 0.4 else (
        "ocasional" if question.get("rate", 0) > 0.15 else "raro"
    )
    question_pct = int(question.get("rate", 0) * 100)

    lines = [
        f"=== PERFIL DE PREFERENCIAS{' DE ' + creator_name.upper() if creator_name else ''} ===",
        f"- Largo de respuesta: {length_desc}",
        f"- Emojis: {emoji_desc}",
        f"- Preguntas al final: {question_desc} ({question_pct}%)",
        f"- Tono: {formality.get('level', '?')}",
        "=== FIN PERFIL ===",
    ]
    return "\n".join(lines)
