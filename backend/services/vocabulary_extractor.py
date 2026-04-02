"""Vocabulary extractor — data-mined, per-lead, TF-IDF distinctive.

Extracts vocabulary from creator's REAL messages only.
Uses word-boundary matching (not substring), stopword filtering,
and TF-IDF distinctiveness scoring for per-lead vocabulary.

Universal: works for any creator in any language.
Zero hardcoding: no vocabulary lists, no forbidden words.
"""

import logging
import math
import re
import time
from collections import Counter
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─── Canonical stopwords (ES + CA + EN + PT + IT) ───
# Pure function words only — content words are kept as potentially characteristic.
# Shared across RelationshipAnalyzer, compressed_doc_d, and this module.
STOPWORDS = frozenset({
    # Spanish
    "de", "la", "el", "en", "que", "un", "una", "es", "se", "no", "lo",
    "con", "por", "su", "para", "al", "del", "las", "los", "me", "te",
    "ya", "si", "mi", "le", "a", "y", "o", "pero", "como", "más", "muy",
    "bien", "hay", "todo", "esta", "esto", "eso", "hola", "gracias",
    "bueno", "buena", "vale", "pues", "ser", "hoy", "fue", "has", "han",
    "era", "son", "tan", "vez", "aquí", "ahí", "qué", "cómo", "sí",
    "sus", "nos", "les", "unos", "unas", "estos", "esas", "ese",
    "ella", "él", "ellos", "ellas", "nosotros", "vosotros",
    "estar", "tener", "hacer", "poder", "decir",
    "donde", "cuando", "quien", "cual", "cuanto",
    "ese", "esos", "esa", "esas", "aquel",
    "va", "voy", "ti", "yo", "tu",
    "soy", "estoy", "tengo",
    "sin", "sobre", "entre", "también",
    "cada", "otro", "otra", "otros", "otras",
    "ahora", "así", "después", "antes",
    "ayer", "mañana", "mensaje",
    # Catalan
    "és", "amb", "els", "les", "pel", "dels", "als", "seva", "són",
    "què", "com", "molt", "bé", "però", "ara", "hem", "fer",
    "uns", "unes", "qui", "quan", "on", "jo", "tu", "ell",
    "nosaltres", "vosaltres",
    "perquè", "tot", "res",
    "estic", "fas", "fes", "tinc", "puc",
    "doncs", "encara", "sempre", "mai", "també",
    # English
    "the", "is", "it", "to", "and", "of", "in", "for", "on", "my",
    "you", "do", "so", "ok", "hi", "yes", "not", "can", "was",
    "are", "be", "have", "has", "had", "will", "just", "that", "this",
    "with", "from", "what", "how", "but", "all", "your", "they",
    "would", "could", "should", "about", "been", "were", "its",
    "also", "than", "then", "some", "these", "those", "them",
    # Portuguese
    "e", "da", "do", "das", "dos", "em", "uma",
    "seu", "sua", "não", "mais", "mas", "foi", "são",
    # Italian
    "che", "di", "il", "per", "non", "sono",
    "della", "dei", "delle", "gli", "anche", "più",
    # Universal high-frequency non-distinctive
    "jaja", "jajaja", "jajajaja", "haha", "hahaha", "lol",
    "buenas", "buenos",
})

# Media placeholders to skip
_MEDIA_PREFIXES = (
    "[audio]", "[video]", "[image]", "[sticker]",
    "[📷", "[🎤", "[📹", "[📍", "[📄", "[📎",
    "[👤", "[🔗", "[gif]", "[media",
)

# Technical / URL / platform tokens that should never be vocabulary
_TECHNICAL_TOKENS = frozenset({
    # URLs and web
    "https", "http", "www", "com", "org", "net",
    # Platforms
    "instagram", "whatsapp", "telegram", "facebook", "tiktok",
    "youtube", "twitter", "snapchat", "spotify", "google",
    # Technical sharing
    "wetransfer", "drive", "dropbox", "link", "download",
    # WhatsApp/IG media types that leak through
    "sticker", "reaction", "gif", "audio", "video", "image",
    "attachment", "shared", "content", "sent", "voice", "message",
    # URL fragments
    "igsh", "utm", "reel", "reels", "stories", "story",
    # Email
    "gmail", "hotmail", "yahoo", "outlook", "email",
})

# Word-boundary tokenizer: captures words with Unicode letters, 3+ chars
# Uses letter classes (not \w) to avoid matching underscores in handles/URLs
_WORD_RE = re.compile(r"\b([a-zA-Z\u00C0-\u024F]{3,})\b", re.UNICODE)


def tokenize(text: str) -> List[str]:
    """Tokenize text into words using word-boundary regex.

    Returns lowercase words of 3+ characters, excluding stopwords,
    media placeholders, and technical tokens.
    """
    text_lower = text.lower().strip()

    # Skip media placeholders
    if text_lower.startswith(_MEDIA_PREFIXES):
        return []

    words = _WORD_RE.findall(text_lower)
    return [
        w for w in words
        if w not in STOPWORDS
        and w not in _TECHNICAL_TOKENS
        and not w.isdigit()
    ]


def extract_lead_vocabulary(
    creator_messages: List[str],
    min_freq: int = 2,
) -> Dict[str, int]:
    """Extract word frequencies from creator's messages to a specific lead.

    Args:
        creator_messages: List of message content strings from the creator.
        min_freq: Minimum frequency to include a word.

    Returns:
        Dict of word -> count, filtered by frequency threshold.
    """
    counts: Counter = Counter()
    for msg in creator_messages:
        counts.update(tokenize(msg))

    # Adaptive threshold: raise for large conversations
    effective_min = min_freq
    if len(creator_messages) >= 50:
        effective_min = max(min_freq, 3)

    return {w: c for w, c in counts.items() if c >= effective_min}


def compute_distinctiveness(
    lead_vocab: Dict[str, int],
    global_vocab: Dict[str, int],
    total_leads: int,
    leads_per_word: Optional[Dict[str, int]] = None,
) -> List[Tuple[str, float]]:
    """Score vocabulary by TF-IDF distinctiveness.

    Words used with many leads score low (generic).
    Words concentrated on this lead score high (distinctive).

    Args:
        lead_vocab: Word frequencies for this specific lead.
        global_vocab: Aggregate word frequencies across all leads.
        total_leads: Total number of leads for this creator.
        leads_per_word: Dict of word -> number of leads that use it.

    Returns:
        List of (word, score) sorted by score descending.
    """
    if not lead_vocab or total_leads < 1:
        return []

    scored = []
    for word, count in lead_vocab.items():
        tf = count

        if leads_per_word and word in leads_per_word:
            df = leads_per_word[word]
            idf = math.log(max(1, total_leads) / max(1, df))
        elif global_vocab.get(word, 0) > 0:
            global_count = global_vocab[word]
            concentration = count / max(1, global_count)
            idf = max(0.1, concentration * math.log(max(2, total_leads)))
        else:
            idf = math.log(max(2, total_leads))

        scored.append((word, tf * idf))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def get_top_distinctive_words(
    creator_messages: List[str],
    global_vocab: Optional[Dict[str, int]] = None,
    total_leads: int = 1,
    leads_per_word: Optional[Dict[str, int]] = None,
    top_n: int = 8,
    min_freq: int = 2,
) -> List[str]:
    """Extract the top N distinctive words for a lead.

    Main entry point for DNA vocabulary extraction.

    Args:
        creator_messages: Creator's messages to this specific lead.
        global_vocab: Aggregate vocabulary across all leads (for TF-IDF).
        total_leads: Total leads for this creator.
        leads_per_word: Optional word -> lead_count mapping.
        top_n: Number of words to return.
        min_freq: Minimum frequency threshold.

    Returns:
        List of distinctive words, ordered by score.
    """
    lead_vocab = extract_lead_vocabulary(creator_messages, min_freq=min_freq)

    if not lead_vocab:
        return []

    if global_vocab and total_leads > 1:
        scored = compute_distinctiveness(
            lead_vocab, global_vocab, total_leads, leads_per_word,
        )
        return [w for w, _ in scored[:top_n]]
    else:
        # Fallback: frequency-only (no global corpus available)
        sorted_words = sorted(
            lead_vocab.items(), key=lambda x: x[1], reverse=True,
        )
        return [w for w, _ in sorted_words[:top_n]]


# In-memory cache for global corpus (TTL-based, per creator)
_corpus_cache: Dict[str, Tuple[float, Dict[str, int], int, Dict[str, int]]] = {}
_CORPUS_CACHE_TTL = 3600  # 1 hour


def build_global_corpus(
    creator_id: str,
    use_cache: bool = True,
) -> Tuple[Dict[str, int], int, Dict[str, int]]:
    """Build global corpus for a creator from the database.

    Results are cached in-memory for 1 hour per creator to avoid
    redundant DB queries when processing multiple leads.

    Queries all real creator messages grouped by lead,
    computes aggregate word frequencies and per-word lead counts.

    Args:
        creator_id: Creator slug (e.g. "iris_bertran").

    Returns:
        Tuple of (global_vocab, total_leads, leads_per_word).
    """
    if use_cache and creator_id in _corpus_cache:
        cached_at, gv, tl, lpw = _corpus_cache[creator_id]
        if time.time() - cached_at < _CORPUS_CACHE_TTL:
            logger.debug("[VOCAB-CORPUS] Cache hit for %s", creator_id)
            return gv, tl, lpw

    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            cr = session.execute(
                text("SELECT id FROM creators WHERE name = :name LIMIT 1"),
                {"name": creator_id},
            ).fetchone()
            if not cr:
                logger.warning("Creator %s not found", creator_id)
                return {}, 0, {}

            creator_uuid = str(cr[0])

            # Paginated fetch to avoid OOM on large creators
            lead_messages: Dict[str, List[str]] = {}
            page_size = 5000
            offset = 0

            while True:
                rows = session.execute(
                    text("""
                        SELECT l.id, m.content
                        FROM messages m
                        JOIN leads l ON m.lead_id = l.id
                        WHERE l.creator_id = CAST(:cid AS uuid)
                        AND m.role = 'assistant'
                        AND m.content IS NOT NULL
                        AND LENGTH(m.content) > 2
                        AND m.deleted_at IS NULL
                        AND COALESCE(m.approved_by, 'human') NOT IN ('auto', 'autopilot')
                        ORDER BY m.created_at
                        LIMIT :lim OFFSET :off
                    """),
                    {"cid": creator_uuid, "lim": page_size, "off": offset},
                ).fetchall()

                if not rows:
                    break

                for lead_id, content in rows:
                    lid = str(lead_id)
                    if lid not in lead_messages:
                        lead_messages[lid] = []
                    lead_messages[lid].append(content)

                if len(rows) < page_size:
                    break
                offset += page_size

            total_leads = len(lead_messages)

            global_vocab: Counter = Counter()
            leads_per_word: Counter = Counter()

            for lid, messages in lead_messages.items():
                lead_words = set()
                for msg in messages:
                    tokens = tokenize(msg)
                    global_vocab.update(tokens)
                    lead_words.update(tokens)
                for w in lead_words:
                    leads_per_word[w] += 1

            logger.info(
                "[VOCAB-CORPUS] Built for %s: %d leads, %d unique words",
                creator_id, total_leads, len(global_vocab),
            )
            result_gv = dict(global_vocab)
            result_lpw = dict(leads_per_word)
            _corpus_cache[creator_id] = (
                time.time(), result_gv, total_leads, result_lpw,
            )
            return result_gv, total_leads, result_lpw

        finally:
            session.close()

    except Exception as e:
        logger.error("build_global_corpus failed for %s: %s", creator_id, e)
        return {}, 0, {}
