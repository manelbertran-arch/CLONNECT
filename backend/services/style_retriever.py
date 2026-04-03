"""
StyleRetriever — curate and retrieve creator response examples for few-shot injection.

Upgraded from gold_examples_service.py with embedding-based retrieval (DITTO paper).
Primary retrieval: cosine similarity on gold_examples.embedding (pgvector).
Fallback: keyword scoring when < 3 embeddings exist (original get_matching_examples).

Feature flag: ENABLE_GOLD_EXAMPLES (default false)
"""

import logging
import os
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GOLD_MAX_EXAMPLES_IN_PROMPT = int(os.getenv("GOLD_MAX_EXAMPLES_IN_PROMPT", "3"))
GOLD_MAX_CHARS_PER_EXAMPLE = int(os.getenv("GOLD_MAX_CHARS_PER_EXAMPLE", "500"))
GOLD_MAX_EXAMPLES_PER_CREATOR = 100
GOLD_EXPIRY_DAYS = 90

# Minimum quality for embedding-based retrieval
GOLD_MIN_QUALITY = 0.6

# LRU-bounded TTL cache for get_matching_examples (max 200 entries)
_examples_cache: OrderedDict = OrderedDict()
_examples_cache_ts: Dict[str, float] = {}
_EXAMPLES_CACHE_TTL = 120  # seconds
_EXAMPLES_CACHE_MAX = 200
_cache_lock = threading.Lock()

# Non-text prefixes (audio, sticker, media) — same as autolearning_analyzer
_NON_TEXT_PREFIXES = ("[🎤 Audio]", "[🏷️ Sticker]", "[📷", "[🎥", "[📎", "[Media", "[🎬")

# Language detection (lightweight heuristic — CA/ES/EN)
_CA_WORDS = re.compile(
    r'\b(vaig|però|molt|avui|demà|tinc|estic|puc|podem|que fas|que et|que em|'
    r'gràcies|fins|dilluns|dimarts|dimecres|dijous|divendres|dissabte|diumenge|'
    r'doncs|ara|anem|hem|heu|han|venir|vine|vindràs|bon dia|bona)\b',
    re.IGNORECASE,
)
_ES_WORDS = re.compile(
    r'\b(tengo|tienes|tiene|tenemos|pero|muy|mucho|estoy|estás|estamos|'
    r'soy|eres|fue|fui|hoy|mañana|gracias|señor|señora|buenas|buenos|'
    r'qué tal|cómo estás|hasta luego|me llamo|me ha|lo que|lo sé)\b',
    re.IGNORECASE,
)
_ES_TILDE_N = re.compile(r'[ñÑ]')

# Quality scores by source
_SOURCE_QUALITY = {
    "manual_override": 0.9,
    "approved": 0.8,
    "minor_edit": 0.7,
    "resolved_externally": 0.75,
    "historical": 0.6,
}


def detect_language(text: str) -> str:
    """Detect language of text. Returns 'ca', 'es', 'mixto', or 'unknown'."""
    ca = len(_CA_WORDS.findall(text))
    es = len(_ES_WORDS.findall(text)) + len(_ES_TILDE_N.findall(text))
    if ca > 0 and es > 0:
        return "mixto"
    if ca > 0:
        return "ca"
    if es > 0:
        return "es"
    return "unknown"


def _is_non_text(text: str) -> bool:
    """Check if text is a non-text response (audio, sticker, media)."""
    if not text:
        return True
    return any(text.startswith(prefix) for prefix in _NON_TEXT_PREFIXES)


# ---------------------------------------------------------------------------
# Embedding helpers (NEW — DITTO paper §3.2)
# ---------------------------------------------------------------------------

def _embed_text(text: str) -> Optional[List[float]]:
    """Embed text using OpenAI text-embedding-3-small (1536 dims).

    Returns list of floats or None if embedding API unavailable.
    """
    try:
        from core.embeddings import generate_embedding
        return generate_embedding(text)
    except Exception as e:
        logger.warning("[STYLE_RETRIEVER] _embed_text failed: %s", e)
        return None


def ensure_embeddings(creator_db_id, batch_size: int = 50) -> int:
    """Backfill embeddings for gold examples that don't have one yet.

    Processes up to batch_size examples per call to avoid long-running DB locks.
    Returns count of embeddings generated.
    """
    from api.database import SessionLocal
    from api.models import GoldExample

    session = SessionLocal()
    generated = 0
    try:
        examples = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
                GoldExample.embedding.is_(None),
            )
            .limit(batch_size)
            .all()
        )

        for ex in examples:
            if not ex.creator_response:
                continue
            embedding = _embed_text(ex.creator_response)
            if embedding is not None:
                ex.embedding = embedding
                generated += 1

        if generated > 0:
            session.commit()
            logger.info(
                "[STYLE_RETRIEVER] ensure_embeddings: generated %d for creator %s",
                generated, creator_db_id,
            )
    except Exception as e:
        logger.error("[STYLE_RETRIEVER] ensure_embeddings error: %s", e)
        session.rollback()
    finally:
        session.close()

    return generated


# ---------------------------------------------------------------------------
# Primary retrieval — embedding similarity (DITTO paper)
# ---------------------------------------------------------------------------

async def retrieve(
    creator_db_id,
    user_message: str,
    intent: Optional[str] = None,
    lead_stage: Optional[str] = None,
    language: Optional[str] = None,
    max_examples: int = 3,
) -> List[Dict[str, str]]:
    """Retrieve gold examples by embedding similarity (primary path).

    Algorithm:
    1. Embed user_message → query vector
    2. Cosine similarity search on gold_examples WHERE quality_score >= 0.6
    3. Language filter: exclude mismatches (unknown/mixto always pass)
    4. Return top max_examples by similarity

    Falls back to get_matching_examples() if < 3 embeddings exist.
    """
    import asyncio
    return await asyncio.to_thread(
        _retrieve_sync, creator_db_id, user_message, intent, lead_stage, language, max_examples
    )


def _retrieve_sync(
    creator_db_id,
    user_message: str,
    intent: Optional[str],
    lead_stage: Optional[str],
    language: Optional[str],
    max_examples: int,
) -> List[Dict[str, str]]:
    """Synchronous implementation of retrieve() for asyncio.to_thread."""
    from api.database import SessionLocal
    from api.models import GoldExample

    session = SessionLocal()
    try:
        # Count how many embeddings exist for this creator
        embedded_count = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
                GoldExample.embedding.isnot(None),
                GoldExample.quality_score >= GOLD_MIN_QUALITY,
            )
            .count()
        )

        # Fallback to keyword scoring if < 3 embeddings (transitional)
        if embedded_count < 3:
            logger.debug(
                "[STYLE_RETRIEVER] Only %d embeddings, falling back to keyword scoring",
                embedded_count,
            )
            return get_matching_examples(
                creator_db_id=creator_db_id,
                intent=intent,
                lead_stage=lead_stage,
                language=language,
            )

        # Embed the query message
        query_vec = _embed_text(user_message)
        if query_vec is None:
            logger.warning("[STYLE_RETRIEVER] Failed to embed query, falling back to keyword scoring")
            return get_matching_examples(
                creator_db_id=creator_db_id,
                intent=intent,
                lead_stage=lead_stage,
                language=language,
            )

        # Cosine similarity search via pgvector <=> operator
        from sqlalchemy import text as sql_text
        from api.database import engine

        with engine.connect() as conn:
            rows = conn.execute(
                sql_text("""
                    SELECT id, creator_response, intent, quality_score,
                           1 - (embedding <=> CAST(:query_vec AS vector)) AS similarity
                    FROM gold_examples
                    WHERE creator_id = :creator_id
                      AND is_active = true
                      AND quality_score >= :min_quality
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(:query_vec AS vector)
                    LIMIT :limit
                """),
                {
                    "query_vec": str(query_vec),
                    "creator_id": str(creator_db_id),
                    "min_quality": GOLD_MIN_QUALITY,
                    "limit": max_examples * 3,  # over-fetch for language filter
                },
            ).fetchall()

        results = []
        for row in rows:
            ex_id, creator_response, ex_intent, quality, similarity = row
            if not creator_response:
                continue

            # Language filter
            if language:
                ex_lang = detect_language(creator_response)
                if ex_lang not in (language, "mixto", "unknown"):
                    continue

            results.append({
                "creator_response": creator_response[:GOLD_MAX_CHARS_PER_EXAMPLE],
                "intent": ex_intent,
                "quality_score": float(quality),
                "similarity": float(similarity),
            })

            if len(results) >= max_examples:
                break

        logger.info(
            "[STYLE_RETRIEVER] retrieve: %d results for creator %s (embedding_count=%d)",
            len(results), creator_db_id, embedded_count,
        )
        return results

    except Exception as e:
        logger.error("[STYLE_RETRIEVER] _retrieve_sync error: %s", e)
        # Final fallback
        return get_matching_examples(
            creator_db_id=creator_db_id,
            intent=intent,
            lead_stage=lead_stage,
            language=language,
        )
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Fallback retrieval — keyword scoring (transitional, from gold_examples_service)
# ---------------------------------------------------------------------------

def get_matching_examples(
    creator_db_id,
    intent: Optional[str] = None,
    lead_stage: Optional[str] = None,
    relationship_type: Optional[str] = None,
    language: Optional[str] = None,
) -> List[Dict]:
    """Get context-scored examples for prompt injection (keyword scoring fallback).

    Scoring: +3 intent, +2 stage, +1 relationship × quality_score.
    Returns top N examples, max GOLD_MAX_CHARS_PER_EXAMPLE chars each.
    Language filter: if provided, excludes examples whose detected language
    doesn't match (unknown/mixto always pass).
    """
    cache_key = f"{creator_db_id}:{intent}:{lead_stage}:{relationship_type}:{language}"
    now = time.time()
    with _cache_lock:
        if cache_key in _examples_cache:
            if now - _examples_cache_ts.get(cache_key, 0) < _EXAMPLES_CACHE_TTL:
                _examples_cache.move_to_end(cache_key)
                return _examples_cache[cache_key]

    from api.database import SessionLocal
    from api.models import GoldExample

    session = SessionLocal()
    try:
        examples = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
            )
            .limit(20)
            .all()
        )

        if not examples:
            _set_cache(cache_key, [], now)
            return []

        scored = []
        for ex in examples:
            # Language filter: skip examples in wrong language
            if language:
                ex_lang = detect_language(ex.creator_response)
                if ex_lang not in (language, "mixto", "unknown"):
                    continue

            score = 0.1

            # Intent match
            if intent and ex.intent and ex.intent.lower() == intent.lower():
                score += 3

            # Lead stage match
            if lead_stage and ex.lead_stage and ex.lead_stage.lower() == lead_stage.lower():
                score += 2

            # Relationship type match
            if relationship_type and ex.relationship_type:
                if ex.relationship_type.lower() == relationship_type.lower():
                    score += 1

            # Universal examples (no context) get base score
            if not (ex.intent or ex.lead_stage or ex.relationship_type):
                score += 0.5

            # Multiply by quality
            score *= ex.quality_score

            scored.append((score, ex))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:GOLD_MAX_EXAMPLES_IN_PROMPT]

        # Build result dicts BEFORE any commit to avoid expired ORM objects
        result = [
            {
                "creator_response": ex.creator_response[:GOLD_MAX_CHARS_PER_EXAMPLE],
                "intent": ex.intent,
                "quality_score": ex.quality_score,
            }
            for _, ex in top
            if _ > 0
        ]

        # Increment times_used for selected examples (best-effort)
        selected_ids = [ex.id for _, ex in top if _ > 0]
        if selected_ids:
            try:
                session.query(GoldExample).filter(
                    GoldExample.id.in_(selected_ids)
                ).update(
                    {GoldExample.times_used: GoldExample.times_used + 1},
                    synchronize_session=False,
                )
                session.commit()
            except Exception as inc_err:
                logger.debug("[STYLE_RETRIEVER] times_used increment failed: %s", inc_err)
                session.rollback()

        _set_cache(cache_key, result, now)
        return result

    except Exception as e:
        logger.error("[STYLE_RETRIEVER] get_matching_examples error: %s", e)
        return []
    finally:
        session.close()


def _set_cache(key: str, value: Any, ts: float):
    """Set cache entry with LRU eviction at _EXAMPLES_CACHE_MAX. Thread-safe."""
    with _cache_lock:
        _examples_cache[key] = value
        _examples_cache_ts[key] = ts
        _examples_cache.move_to_end(key)
        while len(_examples_cache) > _EXAMPLES_CACHE_MAX:
            oldest_key, _ = _examples_cache.popitem(last=False)
            _examples_cache_ts.pop(oldest_key, None)


# ---------------------------------------------------------------------------
# Create gold example (with embedding generation)
# ---------------------------------------------------------------------------

def create_gold_example(
    creator_db_id,
    user_message: str,
    creator_response: str,
    intent: Optional[str] = None,
    lead_stage: Optional[str] = None,
    relationship_type: Optional[str] = None,
    source: str = "approved",
    source_message_id=None,
) -> Optional[Dict]:
    """Create a gold example with deduplication. Generates embedding on creation."""
    from api.database import SessionLocal
    from api.models import GoldExample

    if not user_message or not creator_response:
        return None

    # Reject non-text content (audio, sticker, media)
    if _is_non_text(user_message) or _is_non_text(creator_response):
        return None

    # Reject emoji-only or very short non-text responses
    alpha_chars = re.sub(r'[^a-zA-ZáéíóúàèìòùñçÀ-ÿ]', '', creator_response)
    if len(alpha_chars) < 3:
        return None

    # Truncate long responses
    creator_response = creator_response[:GOLD_MAX_CHARS_PER_EXAMPLE]

    session = SessionLocal()
    try:
        # Dedup: for long messages use first 100-char prefix; for short messages
        # use the full text to avoid false-positive merges ("Hola!" collapsing all greetings)
        if len(user_message) >= 30:
            user_prefix = user_message[:100]
            existing = (
                session.query(GoldExample)
                .filter(
                    GoldExample.creator_id == creator_db_id,
                    GoldExample.is_active.is_(True),
                    GoldExample.user_message.startswith(user_prefix),
                )
                .first()
            )
        else:
            existing = (
                session.query(GoldExample)
                .filter(
                    GoldExample.creator_id == creator_db_id,
                    GoldExample.is_active.is_(True),
                    GoldExample.user_message == user_message,
                )
                .first()
            )
        if existing:
            # Update with newer response if quality is higher
            new_quality = _SOURCE_QUALITY.get(source, 0.5)
            if new_quality > existing.quality_score:
                existing.creator_response = creator_response
                existing.quality_score = new_quality
                existing.source = source
                # Regenerate embedding for updated response
                embedding = _embed_text(creator_response)
                if embedding is not None:
                    existing.embedding = embedding
                session.commit()
                _invalidate_examples_cache(str(creator_db_id))
                return {"id": str(existing.id), "updated": True}
            return {"id": str(existing.id), "skipped": True}

        quality = _SOURCE_QUALITY.get(source, 0.5)

        # Generate embedding for new example (best-effort)
        embedding = _embed_text(creator_response)

        example = GoldExample(
            creator_id=creator_db_id,
            user_message=user_message,
            creator_response=creator_response,
            intent=intent,
            lead_stage=lead_stage,
            relationship_type=relationship_type,
            source=source,
            source_message_id=source_message_id,
            quality_score=quality,
            embedding=embedding,
        )
        session.add(example)
        session.commit()

        _invalidate_examples_cache(str(creator_db_id))
        return {"id": str(example.id), "created": True, "quality": quality}

    except Exception as e:
        logger.error("[STYLE_RETRIEVER] create_gold_example error: %s", e)
        session.rollback()
        return None
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Historical mining and curation (verbatim from gold_examples_service)
# ---------------------------------------------------------------------------

async def mine_historical_examples(
    creator_id: str, creator_db_id, limit: int = 500
) -> int:
    """Mine historical creator messages (copilot_action IS NULL) for gold examples."""
    from sqlalchemy import func as sqlfunc
    from api.database import SessionLocal
    from api.models import Lead, Message

    session = SessionLocal()
    created = 0
    try:
        rows = (
            session.query(Message, Lead)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action.is_(None),
                sqlfunc.length(Message.content) >= 15,
                sqlfunc.length(Message.content) <= 250,
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )

        examples_per_lead: Dict[str, int] = {}

        for msg, lead in rows:
            lead_key = str(msg.lead_id)
            if examples_per_lead.get(lead_key, 0) >= 5:
                continue

            user_msg = (
                session.query(Message)
                .filter(
                    Message.lead_id == msg.lead_id,
                    Message.role == "user",
                    Message.created_at < msg.created_at,
                    sqlfunc.length(Message.content) > 5,
                )
                .order_by(Message.created_at.desc())
                .first()
            )
            if not user_msg or not user_msg.content:
                continue

            result = create_gold_example(
                creator_db_id=creator_db_id,
                user_message=user_msg.content,
                creator_response=msg.content,
                intent=msg.intent,
                lead_stage=lead.status,
                relationship_type=lead.relationship_type,
                source="historical",
                source_message_id=msg.id,
            )
            if result and result.get("created"):
                created += 1
                examples_per_lead[lead_key] = examples_per_lead.get(lead_key, 0) + 1

        logger.info("[STYLE_RETRIEVER] mine_historical_examples %s: created=%d from %d candidates",
                    creator_id, created, len(rows))
        return created

    except Exception as e:
        logger.error("[STYLE_RETRIEVER] mine_historical_examples error for %s: %s", creator_id, e)
        return 0
    finally:
        session.close()


async def curate_examples(creator_id: str, creator_db_id) -> Dict[str, Any]:
    """Background: scan recent copilot messages and create gold examples."""
    from api.database import SessionLocal
    from api.models import GoldExample, Lead, Message

    session = SessionLocal()
    try:
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        rows = (
            session.query(Message, Lead)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action.in_(
                    ["approved", "edited", "manual_override", "resolved_externally"]
                ),
                Message.created_at >= thirty_days_ago,
            )
            .order_by(Message.created_at.desc())
            .limit(200)
            .all()
        )

        created = 0
        for msg, lead in rows:
            user_msg = (
                session.query(Message)
                .filter(
                    Message.lead_id == msg.lead_id,
                    Message.role == "user",
                    Message.created_at < msg.created_at,
                )
                .order_by(Message.created_at.desc())
                .first()
            )
            if not user_msg or not user_msg.content:
                continue

            source = msg.copilot_action or "approved"
            if source == "edited":
                diff = msg.edit_diff or {}
                if diff.get("similarity_ratio", 1.0) >= 0.8:
                    source = "minor_edit"
                else:
                    continue
            elif source == "resolved_externally":
                if not msg.content or len(msg.content.strip()) < 10:
                    continue

            result = create_gold_example(
                creator_db_id=creator_db_id,
                user_message=user_msg.content,
                creator_response=msg.content,
                intent=msg.intent,
                lead_stage=lead.status,
                relationship_type=lead.relationship_type,
                source=source,
                source_message_id=msg.id,
            )
            if result and result.get("created"):
                created += 1

        total_after_copilot = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
            )
            .count()
        )
        historical_created = 0
        if total_after_copilot < 10:
            historical_created = await mine_historical_examples(
                creator_id, creator_db_id, limit=500
            )
            created += historical_created

        expiry_cutoff = datetime.now(timezone.utc) - timedelta(days=GOLD_EXPIRY_DAYS)
        expired = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
                GoldExample.created_at < expiry_cutoff,
                GoldExample.times_used < 3,
            )
            .update({"is_active": False}, synchronize_session=False)
        )

        total_active = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator_db_id,
                GoldExample.is_active.is_(True),
            )
            .count()
        )
        over_cap = 0
        if total_active > GOLD_MAX_EXAMPLES_PER_CREATOR:
            excess = (
                session.query(GoldExample)
                .filter(
                    GoldExample.creator_id == creator_db_id,
                    GoldExample.is_active.is_(True),
                )
                .order_by(GoldExample.quality_score.asc())
                .limit(total_active - GOLD_MAX_EXAMPLES_PER_CREATOR)
                .all()
            )
            for ex in excess:
                ex.is_active = False
                over_cap += 1

        session.commit()
        _invalidate_examples_cache(str(creator_db_id))

        logger.info(
            "[STYLE_RETRIEVER] %s: created=%d (historical=%d) expired=%d capped=%d",
            creator_id, created, historical_created, expired, over_cap,
        )
        return {
            "status": "done",
            "created": created,
            "historical_created": historical_created,
            "expired": expired,
            "capped": over_cap,
        }

    except Exception as e:
        logger.error("[STYLE_RETRIEVER] curate_examples error for %s: %s", creator_id, e)
        session.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        session.close()


def _invalidate_examples_cache(creator_db_id_str: str):
    """Remove all cache entries for a creator. Thread-safe."""
    with _cache_lock:
        keys_to_remove = [k for k in _examples_cache if k.startswith(creator_db_id_str)]
        for k in keys_to_remove:
            _examples_cache.pop(k, None)
            _examples_cache_ts.pop(k, None)
