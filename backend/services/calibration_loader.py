"""
Calibration Loader — loads per-creator calibration data for production DM pipeline.

Calibration JSON contains:
- baseline: median_length, emoji_pct, exclamation_pct, question_frequency_pct
- few_shot_examples: [{context, user_message, response, length}, ...]
- response_pools: {greeting: [...], conversational: [...], ...}
- context_soft_max: {saludo: 22, casual: 25, ...}

Used by:
- core/dm_agent_v2.py (few-shot injection, tone enforcement targets)
- services/tone_enforcer.py (emoji/excl/question rate targets)

Universal: works for any creator_id with a calibration file.
"""

import json
import logging
import os
import random
import re as _re
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# In-memory cache: creator_id -> (calibration_dict, timestamp)
_cache: Dict[str, Tuple[Optional[Dict], float]] = {}
_CACHE_TTL = float(os.getenv("CALIBRATION_CACHE_TTL", "300"))

# Cache for pre-computed example embeddings: content_hash -> List[Optional[List[float]]]
_example_embeddings_cache: Dict[int, List] = {}

# Cache for per-creator Doc D vocabulary (blacklist + approved terms)
_vocab_cache: Dict[str, Optional[Dict]] = {}

CALIBRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "calibrations",
)


def _load_creator_vocab(creator_id: str) -> Dict:
    """Load creator vocabulary from Doc D: blacklist + approved substitutes.

    Parses per-creator Doc D file and extracts four lists:
    - blacklist_words:  prohibited address terms ('NO usa: compa, bro, mi vida...')
    - blacklist_emojis: forbidden emojis ('NUNCA uses: 😊 😉 🥰...')
    - approved_terms:   approved address terms ('SÍ usa: nena, tia, cuca...')
    - approved_emojis:  top approved emojis ('Top emojis: 😂 🫠 🩷...')
    - blacklist_phrases: service-bot phrases from §4.2 BLACKLIST section

    Returns empty dict if no Doc D found — safe default, no filtering/replacement.
    Cached per creator_id (module-level, never expires — Doc D changes rarely).
    Universal: works for any creator with a doc_d_bot_configuration.md.
    """
    if creator_id in _vocab_cache:
        return _vocab_cache[creator_id] or {}

    # ── 1. Try DB: vocab_metadata JSON (structured, survives Railway deploys) ──
    try:
        import json as _json
        from api.database import SessionLocal as _SL
        from sqlalchemy import text as _text

        _s = _SL()
        try:
            _row = _s.execute(
                _text(
                    """
                    SELECT pd.content
                    FROM personality_docs pd
                    JOIN creators c ON c.id::text = pd.creator_id
                    WHERE (c.name = :cid OR pd.creator_id = :cid)
                      AND pd.doc_type = 'vocab_meta'
                    LIMIT 1
                    """
                ),
                {"cid": creator_id},
            ).fetchone()
            if _row:
                vocab = _json.loads(_row.content)
                _vocab_cache[creator_id] = vocab
                logger.debug("[Vocab] %s: loaded from DB vocab_metadata", creator_id)
                return vocab
        finally:
            _s.close()
    except Exception as _e:
        logger.debug("[Vocab] DB vocab_metadata lookup failed for %s: %s", creator_id, _e)

    # ── 2. Fall back to disk (manually-curated on-disk files) ────────────────
    base_dir = os.path.dirname(os.path.dirname(__file__))
    doc_paths = [
        os.path.join(base_dir, "data", "personality_extractions", creator_id, "doc_d_bot_configuration.md"),
        os.path.join(base_dir, "data", "personality_extractions", f"{creator_id}_v2_distilled.md"),
        os.path.join(base_dir, "data", "personality_extractions", f"{creator_id}_distilled.md"),
    ]

    content = None
    for path in doc_paths:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            break

    if not content:
        _vocab_cache[creator_id] = None
        return {}

    def _dedup(lst: List[str]) -> List[str]:
        seen: set = set()
        return [x for x in lst if x and not (x in seen or seen.add(x))]  # type: ignore[func-returns-value]

    # ── 1. "NO usa: X, Y, Z" → prohibited address terms ─────────────────────
    blacklist_words: List[str] = []
    for m in _re.finditer(r"NO\s+usa:\s*([^\n.]+)", content, _re.IGNORECASE):
        raw = _re.sub(r"\([^)]*\)", "", m.group(1))
        for part in _re.split(r"[,;/]", raw):
            term = part.strip().strip('"').strip("'").strip()
            if 2 <= len(term) <= 30:
                blacklist_words.append(term.lower())

    # ── 2. "SÍ usa: X, Y, Z" → approved address terms ───────────────────────
    approved_terms: List[str] = []
    for m in _re.finditer(r"SÍ\s+usa:\s*([^\n]+)", content, _re.IGNORECASE):
        raw = _re.sub(r"\([^)]*\)", "", m.group(1))
        for part in _re.split(r"[,;]", raw):
            term = part.strip().strip('"').strip("'").strip()
            if 2 <= len(term) <= 20:
                approved_terms.append(term.lower())

    # ── 3. "NUNCA uses: 😊 😉 ..." → forbidden emojis ───────────────────────
    # Match base emoji + optional skin-tone modifier (U+1F3FB–U+1F3FF) or variation selector.
    # This prevents splitting "✌🏽" into "✌" + "🏽" (a dangling modifier).
    _EMOJI_RE = _re.compile(
        r"[\U0001F300-\U0001FAFF\u2600-\u27BF][\U0001F3FB-\U0001F3FF\uFE0F]?"
    )
    # Pure skin-tone modifier chars (U+1F3FB–U+1F3FF) are never standalone emojis.
    _SKIN_TONE_RE = _re.compile(r"^[\U0001F3FB-\U0001F3FF]$")

    blacklist_emojis: List[str] = []
    for m in _re.finditer(r"NUNCA\s+uses?:\s*([^\n\(]+)", content, _re.IGNORECASE):
        blacklist_emojis.extend(
            e for e in _EMOJI_RE.findall(m.group(1)) if not _SKIN_TONE_RE.match(e)
        )

    # ── 4. "Top emojis: 😂 🫠 ..." → approved emojis ────────────────────────
    approved_emojis: List[str] = []
    for m in _re.finditer(r"Top emojis[^:]*:\s*([^\n]+)", content, _re.IGNORECASE):
        approved_emojis.extend(
            e for e in _EMOJI_RE.findall(m.group(1)) if not _SKIN_TONE_RE.match(e)
        )

    # ── 5. §4.2 BLACKLIST section → service-bot phrases ─────────────────────
    blacklist_phrases: List[str] = []
    in_blacklist = False
    for line in content.splitlines():
        if "4.2" in line or "BLACKLIST" in line.upper():
            in_blacklist = True
        elif line.startswith("## ") and in_blacklist:
            in_blacklist = False
        if in_blacklist:
            for m in _re.finditer(r'"([^"]{4,60})"', line):
                phrase = m.group(1).strip().lower()
                if phrase:
                    blacklist_phrases.append(phrase)

    vocab = {
        "blacklist_words": _dedup(blacklist_words),
        "blacklist_emojis": _dedup(blacklist_emojis),
        "approved_terms": _dedup(approved_terms),
        "approved_emojis": _dedup(approved_emojis),
        "blacklist_phrases": _dedup(blacklist_phrases),
    }
    _vocab_cache[creator_id] = vocab

    logger.debug(
        "[Vocab] %s: %d blacklist_words, %d blacklist_emojis, %d approved_terms, %d approved_emojis",
        creator_id,
        len(vocab["blacklist_words"]),
        len(vocab["blacklist_emojis"]),
        len(vocab["approved_terms"]),
        len(vocab["approved_emojis"]),
    )
    return vocab


def _load_creator_blacklist(creator_id: str) -> List[str]:
    """Return flat list of all prohibited terms for few-shot filtering.

    Combines blacklist_words + blacklist_emojis + blacklist_phrases from Doc D.
    Returns empty list if no Doc D found — safe default, no filtering applied.
    """
    vocab = _load_creator_vocab(creator_id)
    if not vocab:
        return []
    terms = (
        vocab.get("blacklist_words", [])
        + vocab.get("blacklist_emojis", [])
        + vocab.get("blacklist_phrases", [])
    )
    seen: set = set()
    result = [t for t in terms if t and not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]
    if result:
        logger.debug("[Blacklist] %s: %d prohibited terms", creator_id, len(result))
    return result


def apply_blacklist_replacement(response: str, creator_id: str) -> "tuple[str, bool]":
    """Replace prohibited words/emojis in a generated response with approved equivalents.

    Reads the creator's Doc D to determine:
    - Words to replace (from 'NO usa:') → substituted with a random approved address term
    - Emojis to replace (from 'NUNCA uses:') → substituted with a random approved emoji

    Only applies to SHORT address-term words (≤3 words) to avoid mangling sentences.
    Full service-bot phrases (§4.2) are NOT replaced here — they indicate a deeper
    style failure that would require regeneration.

    Returns (modified_response, was_changed).
    Safe no-op if no Doc D found or no violations detected.
    """
    vocab = _load_creator_vocab(creator_id)
    if not vocab:
        return response, False

    import random as _rng

    modified = response
    changed = False
    approved_terms = vocab.get("approved_terms", [])
    approved_emojis = vocab.get("approved_emojis", [])

    # ── Replace prohibited address words ─────────────────────────────────────
    for word in vocab.get("blacklist_words", []):
        # Only replace single or two-word address terms, never fragments of long phrases
        if len(word.split()) > 2:
            continue
        # Allow elongated last char (e.g. "compaa", "brooo") + optional plural 's'
        stem = _re.escape(word[:-1])
        tail = _re.escape(word[-1])
        pattern = r"\b" + stem + tail + r"+s?\b"
        if not _re.search(pattern, modified, _re.IGNORECASE):
            continue

        if approved_terms:
            replacement = _rng.choice(approved_terms)
            new_modified = _re.sub(pattern, replacement, modified, flags=_re.IGNORECASE)
        else:
            # No replacement defined — strip the word with its surrounding comma/space
            new_modified = _re.sub(
                r"(\s*,\s*)?\b" + stem + tail + r"+s?\b(\s*,\s*)?",
                lambda m: " " if (m.group(1) and m.group(2)) else "",
                modified,
                flags=_re.IGNORECASE,
            ).strip()

        if new_modified != modified:
            logger.info(
                "[Blacklist] %s: '%s' → '%s' in response",
                creator_id, word, approved_terms[0] if approved_terms else "(removed)",
            )
            modified = new_modified
            changed = True

    # ── Replace forbidden emojis ──────────────────────────────────────────────
    for emoji in vocab.get("blacklist_emojis", []):
        if emoji not in modified:
            continue
        replacement_emoji = _rng.choice(approved_emojis) if approved_emojis else ""
        new_modified = modified.replace(emoji, replacement_emoji)
        if new_modified != modified:
            logger.info(
                "[Blacklist] %s: emoji %s → %s",
                creator_id, emoji, replacement_emoji or "(removed)",
            )
            modified = new_modified
            changed = True

    return modified, changed


def _filter_blacklisted_examples(
    examples: List[Dict],
    blacklist: List[str],
    creator_id: str = "",
) -> List[Dict]:
    """Remove few-shot examples whose response contains a blacklisted term.

    Safe: returns all examples unchanged if blacklist is empty.
    """
    if not blacklist or not examples:
        return examples

    clean, removed = [], 0
    for ex in examples:
        response_lower = ex.get("response", "").lower()
        if any(term in response_lower for term in blacklist):
            removed += 1
            logger.debug(
                "[Blacklist] %s: removed example '%s...'",
                creator_id or "?",
                ex.get("response", "")[:50],
            )
        else:
            clean.append(ex)

    if removed:
        logger.info(
            "[Blacklist] %s: removed %d/%d blacklisted few-shot examples, %d remain",
            creator_id or "?", removed, len(examples), len(clean),
        )
    return clean


def load_calibration(creator_id: str) -> Optional[Dict]:
    """Load and cache calibration data for a creator.

    Looks for calibrations/{creator_id}.json.
    Returns None if no calibration exists.
    """
    now = time.time()
    if creator_id in _cache:
        cached_data, cached_ts = _cache[creator_id]
        if (now - cached_ts) < _CACHE_TTL:
            return cached_data

    # Prefer unified pool (larger, higher retrieval quality) over base calibration
    cal_path = os.path.join(CALIBRATIONS_DIR, f"{creator_id}_unified.json")
    if not os.path.isfile(cal_path):
        cal_path = os.path.join(CALIBRATIONS_DIR, f"{creator_id}.json")
    if not os.path.isfile(cal_path):
        _cache[creator_id] = (None, now)
        return None

    try:
        with open(cal_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Filter few-shot examples against the creator's Doc D blacklist.
        # Removes responses containing prohibited words/phrases/emojis defined in §4.2 or
        # "NO usa:" / "NUNCA uses:" sections. No-op if no Doc D found.
        few_shot = data.get("few_shot_examples", [])
        if few_shot:
            blacklist = _load_creator_blacklist(creator_id)
            if blacklist:
                filtered = _filter_blacklisted_examples(few_shot, blacklist, creator_id)
                if len(filtered) != len(few_shot):
                    data = dict(data)
                    data["few_shot_examples"] = filtered

        _cache[creator_id] = (data, now)
        baseline = data.get("baseline", {})
        n_fse = len(data.get("few_shot_examples", []))
        logger.info(
            "Loaded calibration for %s: median=%s, emoji=%.1f%%, fse=%d",
            creator_id,
            baseline.get("median_length"),
            baseline.get("emoji_pct", 0),
            n_fse,
        )
        return data
    except Exception as e:
        logger.error("Failed to load calibration for %s: %s", creator_id, e)
        _cache[creator_id] = (None, now)
        return None


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two vectors using numpy."""
    import numpy as np
    va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def _select_examples_by_similarity(
    examples: List[Dict],
    current_message: str,
    n_semantic: int,
    n_random: int,
) -> List[Dict]:
    """Return n_semantic examples closest to current_message + n_random from the rest.

    Falls back to pure random.sample() if embeddings are unavailable.
    """
    try:
        from core.embeddings import generate_embedding, generate_embeddings_batch

        # Cache example embeddings by content hash (stable across calls)
        cache_key = hash(tuple(ex.get("user_message", "") for ex in examples))
        if cache_key not in _example_embeddings_cache:
            texts = [ex.get("user_message", "") for ex in examples]
            _example_embeddings_cache[cache_key] = generate_embeddings_batch(texts)
            logger.debug(
                "Computed embeddings for %d few-shot examples (cache key %d)",
                len(texts), cache_key,
            )

        example_embeddings = _example_embeddings_cache[cache_key]
        msg_embedding = generate_embedding(current_message)

        if not msg_embedding:
            raise ValueError("Empty message embedding")

        # Rank examples by cosine similarity to current_message
        scored = [
            (_cosine_similarity(msg_embedding, emb), i)
            for i, emb in enumerate(example_embeddings)
            if emb is not None
        ]
        scored.sort(reverse=True)

        top_indices = {i for _, i in scored[:n_semantic]}
        semantic_examples = [examples[i] for _, i in scored[:n_semantic]]
        remaining = [ex for i, ex in enumerate(examples) if i not in top_indices]
        random_examples = random.sample(remaining, min(n_random, len(remaining)))

        logger.debug(
            "Few-shot: %d semantic (top sim=%.2f) + %d random",
            len(semantic_examples),
            scored[0][0] if scored else 0,
            len(random_examples),
        )
        return semantic_examples + random_examples

    except Exception as e:
        logger.debug("Semantic few-shot selection failed, using random: %s", e)
        k = min(n_semantic + n_random, len(examples))
        return random.sample(examples, k)


def detect_message_language(text: str) -> Optional[str]:
    """Detect the language of a message, including code-switching between any pair.

    Returns an ISO 639-1 code ('ca', 'es', 'it', 'en', ...), a hyphenated
    code-switching tag ('ca-es', 'es-it', 'en-fr', ...), or None.

    Strategy:
      1. Fast-path: ca/es marker detection (langdetect can't reliably
         distinguish Catalan from Spanish on short text).
      2. Clause-level langdetect: split by punctuation, detect each clause.
         If 2+ languages → code-switching. Works for ANY language pair.

    When a hyphenated tag is returned, the few-shot pool should NOT be
    filtered by language so the LLM sees examples in both languages.
    """
    import re

    stripped = text.strip()
    if len(stripped) < 10:
        return None

    lower = stripped.lower()

    # ── Fast-path: ca/es markers (langdetect merges them) ──────────────
    _CA_RE = re.compile(
        r"\b(tinc|estic|però|molt|doncs|també|perquè|això|vull|"
        r"puc|setmana|dimarts|dijous|dissabte|diumenge|"
        r"gràcies|gracies|bona nit|bona tarda|bon dia|"
        r"nosaltres|puguis|vulguis|xk|pq|xfi)\b"
    )
    _ES_RE = re.compile(
        r"\b(tengo|estoy|pero|mucho|entonces|también|porque|quiero|"
        r"puedo|necesito|bueno|gracias|vale|claro|genial|"
        r"miércoles|jueves|sábado|domingo|"
        r"nosotros|puedes|quieres|necesitas)\b"
    )
    ca_hits = _CA_RE.findall(lower)
    es_hits = _ES_RE.findall(lower)

    if ca_hits and es_hits:
        logger.debug("Code-switching ca-es: ca=%s es=%s", ca_hits[:3], es_hits[:3])
        return "ca-es"
    if ca_hits and not es_hits:
        return "ca"

    # ── Clause-level langdetect (universal for all other pairs) ────────
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0
    except ImportError:
        return None

    clauses = re.split(r'[,.;!?\n]+', stripped)
    clauses = [c.strip() for c in clauses if len(c.strip()) > 5]

    if len(clauses) < 2:
        try:
            return detect(stripped)
        except Exception:
            return None

    langs = []
    for clause in clauses:
        try:
            langs.append(detect(clause))
        except Exception:
            pass

    if not langs:
        return None

    unique = set(langs)
    if len(unique) >= 2:
        from collections import Counter
        top2 = [lang for lang, _ in Counter(langs).most_common(2)]
        tag = "-".join(sorted(top2))
        logger.debug("Code-switching detected: %s (clause langs: %s)", tag, langs)
        return tag

    return langs[0]


# ── Intent → calibration context mapping ──────────────────────────────────
# Maps Intent enum values to calibration example "context" field values.
# Universal: works for any creator. Add new intents here as needed.
_INTENT_TO_CONTEXTS: Dict[str, List[str]] = {
    # Greetings
    "greeting": ["saludo", "reaccion_breve", "reaccion_emoji"],
    "farewell": ["despedida", "despedida_breve"],
    "thanks": ["confirmacion_breve", "ultra_breve_ca"],
    # Product / pricing
    "question_product": ["precio", "lead_caliente", "clase_entreno", "clase"],
    "question_general": ["conversacional", "contenido_confirmacion"],
    "purchase_intent": ["precio", "lead_caliente", "confirmacion_breve"],
    # Interest
    "interest_soft": ["lead_caliente", "conversacional"],
    "interest_strong": ["lead_caliente", "precio", "confirmacion_breve"],
    # Objections
    "objection_price": ["objecion", "precio"],
    "objection_time": ["objecion", "redirect_clase"],
    "objection_doubt": ["objecion", "conversacional"],
    "objection_later": ["objecion", "empatia"],
    "objection_works": ["objecion"],
    "objection_not_for_me": ["objecion", "empatia"],
    "objection_complicated": ["objecion"],
    "objection_already_have": ["objecion"],
    # Support
    "escalation": ["empatia"],
    "support": ["empatia", "conversacional"],
    "feedback_negative": ["empatia", "objecion"],
    # Casual
    "humor": ["reaccion_breve", "conversacional", "personal_amigos"],
    "pool_response": ["reaccion_breve", "ultra_breve_ca"],
    "continuation": ["conversacional", "confirmacion_breve"],
    # Media
    "media_share": ["reaccion_sticker", "reaccion_emoji", "reaccion_breve",
                     "audio_reply", "audio_sin_transcripcion", "contenido_reaccion_media"],
    # Other
    "other": ["conversacional", "personal_amigos"],
}


def _select_stratified(
    pool: List[Dict],
    intent_value: Optional[str],
    current_message: Optional[str],
    max_examples: int,
) -> List[Dict]:
    """Intent-stratified + semantic hybrid selection. Universal.

    Strategy (for max_examples=10):
      1. Up to 3 examples from intent-matched contexts
      2. Up to 5 examples from diverse OTHER contexts (1 per context group)
      3. Up to 2 semantic matches (only if message > 15 chars)

    Falls back to 5 semantic + 5 random if no intent is provided.
    """
    n_intent = min(3, max_examples // 3)
    n_diverse = min(5, max_examples // 2)
    n_semantic = max_examples - n_intent - n_diverse

    selected: List[Dict] = []
    used_indices: set = set()

    # ── Step 1: Intent-matched examples ───────────────────────────────────
    if intent_value:
        target_contexts = _INTENT_TO_CONTEXTS.get(intent_value, [])
        intent_pool = [
            (i, ex) for i, ex in enumerate(pool)
            if ex.get("context") in target_contexts
        ]
        if intent_pool:
            k = min(n_intent, len(intent_pool))
            picks = random.sample(intent_pool, k)
            for idx, ex in picks:
                selected.append(ex)
                used_indices.add(idx)
            logger.debug(
                "Few-shot: %d intent-matched (%s → %s)",
                len(picks), intent_value, target_contexts[:2],
            )

    # ── Step 2: Diverse examples from OTHER contexts ──────────────────────
    # Group remaining examples by context, pick 1 from each
    from collections import defaultdict
    ctx_groups: Dict[str, List[tuple]] = defaultdict(list)
    for i, ex in enumerate(pool):
        if i not in used_indices:
            ctx_groups[ex.get("context", "other")].append((i, ex))

    diverse_picks = []
    group_keys = list(ctx_groups.keys())
    random.shuffle(group_keys)
    for ctx_key in group_keys:
        if len(diverse_picks) >= n_diverse:
            break
        candidates = ctx_groups[ctx_key]
        idx, ex = random.choice(candidates)
        if idx not in used_indices:
            diverse_picks.append(ex)
            used_indices.add(idx)
    selected.extend(diverse_picks)

    # ── Step 3: Semantic matches (only for non-trivial messages) ──────────
    remaining_needed = max_examples - len(selected)
    if remaining_needed > 0 and current_message and len(current_message) > 15:
        remaining_pool = [ex for i, ex in enumerate(pool) if i not in used_indices]
        if remaining_pool:
            sem_picks = _select_examples_by_similarity(
                remaining_pool, current_message,
                n_semantic=remaining_needed, n_random=0,
            )
            selected.extend(sem_picks[:remaining_needed])
    elif remaining_needed > 0:
        # Short message — fill with random
        remaining_pool = [ex for i, ex in enumerate(pool) if i not in used_indices]
        if remaining_pool:
            k = min(remaining_needed, len(remaining_pool))
            selected.extend(random.sample(remaining_pool, k))

    return selected[:max_examples]


def get_few_shot_section(
    calibration: Dict,
    max_examples: int = 5,
    current_message: Optional[str] = None,
    lead_language: Optional[str] = None,
    detected_intent: Optional[str] = None,
) -> str:
    """Format few-shot examples from calibration into a prompt section.

    Selection strategy (intent-stratified + semantic hybrid):
      - 3 examples matching the detected intent context
      - 5 examples from diverse other contexts (1 per group)
      - 2 semantic matches (for messages > 15 chars)
    Falls back to semantic + random if no intent is provided.

    Language filtering: same-language + 'mixto'. Code-switching tags
    (e.g. 'ca-es') skip filtering to expose the LLM to both languages.

    Universal: works for any creator with a calibration file.
    Returns empty string if no examples exist.
    """
    examples: List[Dict] = calibration.get("few_shot_examples", [])
    if not examples:
        return ""

    # Language-aware pool filtering: prefer same-language + mixto examples.
    # For code-switching (any "X-Y" tag): use FULL pool so LLM sees both languages.
    pool = examples
    is_code_switching = lead_language and "-" in lead_language
    if lead_language and not is_code_switching:
        filtered = [
            ex for ex in examples
            if ex.get("language") in (lead_language, "mixto")
        ]
        if len(filtered) >= max_examples:
            pool = filtered
            logger.debug(
                "Few-shot: language filter=%s reduced pool %d->%d",
                lead_language, len(examples), len(pool),
            )
    elif is_code_switching:
        logger.debug("Few-shot: code-switching %s, full pool (%d)", lead_language, len(pool))

    # Select examples using intent-stratified strategy
    selected = _select_stratified(pool, detected_intent, current_message, max_examples)

    lines = ["=== EJEMPLOS REALES DE COMO RESPONDES ==="]
    for ex in selected:
        user_msg = ex.get("user_message", "")
        response = ex.get("response", "")
        if user_msg and response:
            lines.append(f"Follower: {user_msg}")
            lines.append(f"Tu: {response}")
            lines.append("")
    lines.append("Responde de forma breve y natural, como en los ejemplos.")
    lines.append("=== FIN EJEMPLOS ===")
    return "\n".join(lines)


def invalidate_cache(creator_id: Optional[str] = None) -> None:
    """Clear cached calibration data."""
    if creator_id:
        _cache.pop(creator_id, None)
    else:
        _cache.clear()
