"""Auto-provisioner — generates creator profiles on first message.

When a creator receives their first message and has no profiles in DB,
this service generates them in background (baseline_metrics, length_by_intent,
compressed_doc_d). Next message will use real profiles.

BFI is NOT auto-generated (needs OpenAI API, expensive). Run manually if needed.
"""

import asyncio
import logging
import os
import re
import statistics
from collections import Counter
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MIN_MESSAGES_FOR_PROFILE = 50
PROFILE_TTL_DAYS = 30
REQUIRED_PROFILES = ["baseline_metrics", "length_by_intent", "calibration"]

# Track in-flight provisioning to avoid duplicates
_provisioning_in_progress: set[str] = set()


# =============================================================================
# PUBLIC API
# =============================================================================

def ensure_profiles(creator_id: str) -> bool:
    """Check if creator has all required profiles. If missing, generate in background.

    Returns True if all profiles are ready NOW, False if generating in background.
    Called synchronously from agent __init__ — background work is fire-and-forget.
    """
    from services.creator_profile_service import get_existing_types

    existing = get_existing_types(creator_id)

    # Check calibration file separately (stored on disk, not in DB)
    import json
    from pathlib import Path
    cal_path = Path("calibrations") / f"{creator_id}.json"
    has_calibration = cal_path.exists()
    if has_calibration:
        try:
            cal_mtime = datetime.fromtimestamp(cal_path.stat().st_mtime, tz=timezone.utc)
            has_calibration = not _is_stale(cal_mtime.isoformat())
        except Exception:
            has_calibration = False

    # Check which profiles are missing or stale
    needs_generation = []
    for ptype in REQUIRED_PROFILES:
        if ptype == "calibration":
            if not has_calibration:
                needs_generation.append(ptype)
        elif ptype not in existing:
            needs_generation.append(ptype)
        elif _is_stale(existing[ptype]):
            needs_generation.append(ptype)

    if not needs_generation:
        return True  # All ready

    # Already generating?
    if creator_id in _provisioning_in_progress:
        logger.debug("Auto-provisioning already in progress for %s", creator_id)
        return False

    # Check message count
    msg_count = _count_creator_messages(creator_id)
    if msg_count < MIN_MESSAGES_FOR_PROFILE:
        logger.info(
            "Creator %s has %d msgs (need %d) — skipping auto-provisioning",
            creator_id, msg_count, MIN_MESSAGES_FOR_PROFILE,
        )
        return False

    # Fire background generation
    logger.info(
        "Auto-provisioning %s for %s (%d msgs available)",
        needs_generation, creator_id, msg_count,
    )
    _provisioning_in_progress.add(creator_id)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_generate_profiles_async(creator_id, needs_generation))
    except RuntimeError:
        # No event loop — run synchronously (e.g., in script context)
        import threading
        t = threading.Thread(
            target=_generate_profiles_sync, args=(creator_id, needs_generation),
            daemon=True,
        )
        t.start()

    return False


# =============================================================================
# BACKGROUND GENERATION
# =============================================================================

async def _generate_profiles_async(creator_id: str, profile_types: list[str]):
    """Async wrapper — runs sync generation in a thread."""
    try:
        await asyncio.to_thread(_generate_profiles_sync, creator_id, profile_types)
    except Exception as e:
        logger.error("Auto-provisioning failed for %s: %s", creator_id, e)
    finally:
        _provisioning_in_progress.discard(creator_id)


def _generate_profiles_sync(creator_id: str, profile_types: list[str]):
    """Generate missing profiles synchronously (runs in background thread)."""
    from services.creator_profile_service import save_profile

    try:
        if "baseline_metrics" in profile_types:
            logger.info("[AUTO-PROVISION] Generating baseline_metrics for %s", creator_id)
            baseline = _generate_baseline(creator_id)
            if baseline:
                save_profile(creator_id, "baseline_metrics", baseline)
                logger.info("[AUTO-PROVISION] baseline_metrics saved for %s", creator_id)

        if "length_by_intent" in profile_types:
            logger.info("[AUTO-PROVISION] Generating length_by_intent for %s", creator_id)
            length_profile = _generate_length_profile(creator_id)
            if length_profile:
                save_profile(creator_id, "length_by_intent", length_profile)
                logger.info("[AUTO-PROVISION] length_by_intent saved for %s", creator_id)

        if "calibration" in profile_types:
            logger.info("[AUTO-PROVISION] Generating calibration for %s", creator_id)
            _generate_calibration(creator_id)

        # Regenerate compressed_doc_d (depends on baseline)
        logger.info("[AUTO-PROVISION] Generating compressed_doc_d for %s", creator_id)
        _regenerate_compressed_doc_d(creator_id)

        logger.info("[AUTO-PROVISION] Completed for %s: %s", creator_id, profile_types)
    except Exception as e:
        logger.error("[AUTO-PROVISION] Failed for %s: %s", creator_id, e, exc_info=True)
    finally:
        _provisioning_in_progress.discard(creator_id)


# =============================================================================
# HELPERS
# =============================================================================

def _is_stale(updated_at_iso: str) -> bool:
    """Check if a profile is older than PROFILE_TTL_DAYS."""
    if not updated_at_iso:
        return True
    try:
        updated = datetime.fromisoformat(updated_at_iso)
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - updated).days
        return age_days > PROFILE_TTL_DAYS
    except (ValueError, TypeError):
        return True


def _count_creator_messages(creator_id: str) -> int:
    """Count assistant messages for a creator."""
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            row = session.execute(
                text("""
                    SELECT COUNT(*) FROM messages m
                    JOIN leads l ON l.id = m.lead_id
                    JOIN creators c ON c.id = l.creator_id
                    WHERE c.name = :cid AND m.role = 'assistant'
                      AND m.content IS NOT NULL AND LENGTH(m.content) > 2
                """),
                {"cid": creator_id},
            ).fetchone()
            return row[0] if row else 0
        finally:
            session.close()
    except Exception as e:
        logger.debug("_count_creator_messages(%s) failed: %s", creator_id, e)
        return 0


def _get_creator_messages(creator_id: str, limit: int = 500) -> list[dict]:
    """Fetch real creator assistant messages from DB."""
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            from services.creator_profile_service import _resolve_creator_uuid
            cid = _resolve_creator_uuid(session, creator_id)
            if not cid:
                return []

            rows = session.execute(
                text("""
                    SELECT m.content, m.created_at
                    FROM messages m
                    JOIN leads l ON l.id = m.lead_id
                    WHERE l.creator_id = :cid
                      AND m.role = 'assistant'
                      AND m.status IN ('sent', 'resolved_externally')
                      AND m.content IS NOT NULL
                      AND length(m.content) > 2
                      AND m.content NOT LIKE '[%%Audio]%%'
                      AND m.content NOT LIKE '[%%Photo]%%'
                      AND m.content NOT LIKE '[%%Sticker]%%'
                      AND m.content NOT LIKE '[%%Document]%%'
                      AND m.content NOT LIKE 'Sent%%'
                      AND m.content NOT LIKE 'Mentioned%%'
                      AND m.content NOT LIKE 'Shared%%'
                      AND m.content NOT LIKE 'http%%'
                    ORDER BY m.created_at DESC
                    LIMIT :lim
                """),
                {"cid": str(cid), "lim": limit},
            ).fetchall()
            return [{"content": r[0], "created_at": r[1]} for r in rows]
        finally:
            session.close()
    except Exception as e:
        logger.error("_get_creator_messages(%s) failed: %s", creator_id, e)
        return []


# =============================================================================
# BASELINE METRICS GENERATOR (extracted from scripts/cpe_generate_baseline.py)
# =============================================================================

_EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U00002600-\U000027BF]+",
    flags=re.UNICODE,
)

_STOPWORDS = {
    "de", "la", "el", "en", "y", "a", "que", "es", "un", "una", "los",
    "las", "del", "al", "por", "con", "para", "se", "no", "lo", "le",
    "me", "te", "su", "mi", "tu", "si", "ya", "ha", "he", "i", "o",
}

_USTED_MARKERS = re.compile(r"\b(usted|ustedes|le\s+(?:informo|comunico))\b", re.I)
_TUTEO_MARKERS = re.compile(r"\b(tú|tu\s|tienes|puedes|quieres|te\s+(?:mando|paso))\b", re.I)
_VOSEO_MARKERS = re.compile(r"\b(vos|tenés|podés|querés|venís|sabés)\b", re.I)


def _generate_baseline(creator_id: str) -> dict | None:
    """Generate baseline_metrics from DB messages."""
    messages = _get_creator_messages(creator_id, limit=500)
    if len(messages) < MIN_MESSAGES_FOR_PROFILE:
        return None

    texts = [m["content"] for m in messages]
    n = len(texts)

    def pct(data, p):
        s = sorted(data)
        k = int(len(s) * p / 100)
        return s[min(k, len(s) - 1)]

    # Length
    lengths = [len(t) for t in texts]
    word_counts = [len(t.split()) for t in texts]
    length_stats = {
        "char_mean": round(statistics.mean(lengths), 1),
        "char_median": round(statistics.median(lengths), 1),
        "char_p25": pct(lengths, 25),
        "char_p50": pct(lengths, 50),
        "char_p75": pct(lengths, 75),
        "char_p90": pct(lengths, 90),
        "char_min": min(lengths),
        "char_max": max(lengths),
        "word_mean": round(statistics.mean(word_counts), 1),
        "word_median": round(statistics.median(word_counts), 1),
    }

    # Emoji
    emoji_msgs = 0
    emoji_counter = Counter()
    total_emojis = 0
    for t in texts:
        matches = _EMOJI_RE.findall(t)
        chars = []
        for m in matches:
            chars.extend(list(m))
        chars = [c for c in chars if ord(c) > 255 and c not in "\ufe0f\u200d"]
        if chars:
            emoji_msgs += 1
            total_emojis += len(chars)
            emoji_counter.update(chars)

    emoji_stats = {
        "emoji_rate_pct": round(emoji_msgs / n * 100, 1),
        "avg_emoji_count": round(total_emojis / n, 2),
        "top_20_emojis": emoji_counter.most_common(20),
    }

    # Punctuation
    question_rate = round(sum(1 for t in texts if "?" in t) / n * 100, 1)
    exclamation_rate = round(sum(1 for t in texts if "!" in t) / n * 100, 1)
    laugh_re = re.compile(r"(?:ja|je|ji|jo){2,}|(?:ha|he){2,}", re.I)
    laugh_rate = round(sum(1 for t in texts if laugh_re.search(t)) / n * 100, 1)
    ellipsis_rate = round(sum(1 for t in texts if "..." in t) / n * 100, 1)
    caps_rate = round(sum(1 for t in texts if t == t.upper() and len(t) > 3) / n * 100, 1)

    punctuation = {
        "question_rate_pct": question_rate,
        "exclamation_rate_pct": exclamation_rate,
        "laugh_rate_pct": laugh_rate,
        "ellipsis_rate_pct": ellipsis_rate,
        "all_caps_rate_pct": caps_rate,
    }

    # Language detection (lightweight — skip langdetect, just use heuristics)
    languages = {"detected": [{"lang": "es", "count": n, "pct": 100.0}], "total_detected": n}

    # Vocabulary
    word_counter = Counter()
    for t in texts:
        words = re.findall(r"[a-záéíóúàèòüïçñ]+", t.lower())
        for w in words:
            if w not in _STOPWORDS and len(w) >= 2:
                word_counter[w] += 1

    vocabulary = {
        "top_50": word_counter.most_common(50),
        "unique_words": len(word_counter),
        "total_words": sum(word_counter.values()),
    }

    # Diversity
    all_words = []
    for t in texts:
        all_words.extend(re.findall(r"[a-záéíóúàèòüïçñ]+", t.lower()))
    ttr = len(set(all_words)) / max(len(all_words), 1)

    # Formality
    usted_count = sum(1 for t in texts if _USTED_MARKERS.search(t))
    tuteo_count = sum(1 for t in texts if _TUTEO_MARKERS.search(t))
    voseo_count = sum(1 for t in texts if _VOSEO_MARKERS.search(t))

    formality = {
        "usted_pct": round(usted_count / n * 100, 1),
        "tuteo_pct": round(tuteo_count / n * 100, 1),
        "voseo_pct": round(voseo_count / n * 100, 1),
        "dominant": (
            "usted" if usted_count > tuteo_count and usted_count > voseo_count
            else "voseo" if voseo_count > tuteo_count
            else "tuteo"
        ),
    }

    metrics = {
        "total_messages": n,
        "length": length_stats,
        "emoji": emoji_stats,
        "punctuation": punctuation,
        "languages": languages,
        "vocabulary": vocabulary,
        "greeting_patterns": {"top_15_openers": Counter(
            t.split()[0].lower().rstrip("!.,?") for t in texts if t.split()
        ).most_common(15)},
        "diversity": {
            "type_token_ratio": round(ttr, 3),
            "unique_types": len(set(all_words)),
            "total_tokens": len(all_words),
        },
        "formality": formality,
    }

    return {
        "creator": creator_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "messages_analyzed": n,
        "metrics": metrics,
    }


# =============================================================================
# LENGTH PROFILE GENERATOR (extracted from scripts/cpe_generate_length_profile.py)
# =============================================================================

def _generate_length_profile(creator_id: str) -> dict | None:
    """Generate length_by_intent from DB message pairs."""
    try:
        import numpy as np
        from api.database import SessionLocal
        from sqlalchemy import text
        from services.length_controller import classify_lead_context
        from services.creator_profile_service import _resolve_creator_uuid

        session = SessionLocal()
        try:
            cid = _resolve_creator_uuid(session, creator_id)
            if not cid:
                return None

            rows = session.execute(
                text("""
                    SELECT m_user.content AS user_msg, LENGTH(m_bot.content) AS bot_len
                    FROM messages m_bot
                    JOIN LATERAL (
                        SELECT content FROM messages
                        WHERE lead_id = m_bot.lead_id AND role = 'user'
                          AND created_at < m_bot.created_at
                        ORDER BY created_at DESC LIMIT 1
                    ) m_user ON TRUE
                    JOIN leads l ON l.id = m_bot.lead_id
                    WHERE l.creator_id = :cid
                      AND m_bot.role = 'assistant'
                      AND m_bot.content IS NOT NULL
                      AND LENGTH(m_bot.content) > 0
                    ORDER BY m_bot.created_at DESC LIMIT 500
                """),
                {"cid": str(cid)},
            ).fetchall()

            if len(rows) < MIN_MESSAGES_FOR_PROFILE:
                return None

            # Group by context
            groups: dict[str, list[int]] = {}
            all_lengths: list[int] = []
            for row in rows:
                user_msg = row[0] or ""
                bot_len = row[1] or 0
                context = classify_lead_context(user_msg)
                groups.setdefault(context, []).append(bot_len)
                all_lengths.append(bot_len)

            def compute_stats(lengths: list[int]) -> dict:
                arr = np.array(lengths)
                return {
                    "p25": int(np.percentile(arr, 25)),
                    "median": int(np.median(arr)),
                    "p75": int(np.percentile(arr, 75)),
                    "p90": int(np.percentile(arr, 90)),
                    "count": len(lengths),
                }

            profile = {ctx: compute_stats(lens) for ctx, lens in groups.items()}
            profile["default"] = compute_stats(all_lengths)
            return profile

        finally:
            session.close()
    except Exception as e:
        logger.error("_generate_length_profile(%s) failed: %s", creator_id, e, exc_info=True)
        return None


# =============================================================================
# COMPRESSED DOC D REGENERATION
# =============================================================================

def _generate_calibration(creator_id: str):
    """Generate calibration JSON (few-shot examples, response pools, baseline) and save to file.

    Imports functions from the calibration pipeline script rather than reimplementing.
    Saves to calibrations/{creator_slug}.json for the calibration_loader to find.
    """
    try:
        import json
        from pathlib import Path
        from services.creator_profile_service import _resolve_creator_uuid
        from api.database import SessionLocal

        session = SessionLocal()
        try:
            creator_uuid = _resolve_creator_uuid(session, creator_id)
            if not creator_uuid:
                logger.warning("[AUTO-PROVISION] Cannot resolve UUID for %s", creator_id)
                return
        finally:
            session.close()

        from scripts.creator_calibration_pipeline import (
            load_conversation_pairs, compute_baseline, compute_context_soft_max,
            extract_response_pools, extract_few_shot, extract_creator_vocabulary,
        )
        from scripts.backtest.contamination_filter import filter_turns

        conversations, all_turns = load_conversation_pairs(str(creator_uuid))
        if len(all_turns) < MIN_MESSAGES_FOR_PROFILE:
            logger.info("[AUTO-PROVISION] Not enough turns (%d) for calibration", len(all_turns))
            return

        clean_turns, _, _ = filter_turns(conversations, all_turns)
        baseline = compute_baseline(clean_turns)
        context_soft_max = compute_context_soft_max(clean_turns, baseline["soft_max"])
        pools = extract_response_pools(clean_turns)
        few_shot = extract_few_shot(clean_turns, n_examples=12)
        vocab = extract_creator_vocabulary(
            [t["real_response"] for t in clean_turns]
        )

        # Filter out [Media/Attachment] entries and cap pool size
        few_shot = [e for e in few_shot if "[Media" not in e.get("response", "")]
        MAX_POOL_PER_CONTEXT = 50
        for k in pools:
            pools[k] = [r for r in pools[k] if "[Media" not in r and len(r) > 2]
            if len(pools[k]) > MAX_POOL_PER_CONTEXT:
                pools[k] = pools[k][:MAX_POOL_PER_CONTEXT]

        calibration = {
            "baseline": baseline,
            "context_soft_max": context_soft_max,
            "response_pools": pools,
            "few_shot_examples": few_shot,
            "creator_vocabulary": vocab,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        cal_path = Path("calibrations") / f"{creator_id}.json"
        cal_path.parent.mkdir(exist_ok=True)
        cal_path.write_text(json.dumps(calibration, ensure_ascii=False, indent=2))
        logger.info("[AUTO-PROVISION] Calibration saved to %s (%d examples, %d pool responses)",
                     cal_path, len(few_shot), sum(len(v) for v in pools.values()))
    except Exception as e:
        logger.error("[AUTO-PROVISION] _generate_calibration(%s) failed: %s", creator_id, e, exc_info=True)


def _regenerate_compressed_doc_d(creator_id: str):
    """Regenerate and cache compressed_doc_d in DB."""
    try:
        from core.dm.compressed_doc_d import build_compressed_doc_d
        from services.creator_profile_service import save_profile, clear_cache

        # Clear profile cache so build_compressed_doc_d reads fresh baseline
        clear_cache()

        doc_d = build_compressed_doc_d(creator_id)
        if doc_d:
            save_profile(creator_id, "compressed_doc_d", {"text": doc_d})
    except Exception as e:
        logger.error("_regenerate_compressed_doc_d(%s) failed: %s", creator_id, e)
