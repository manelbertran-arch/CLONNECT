"""
CCEE Script 1: Style Profile Builder

Builds a statistical style profile from ALL real creator messages.
Produces metrics A1-A9 with [P10, P90] thresholds from actual distribution.
Universal — no hardcoding for any specific creator or language.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Reuse existing components
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from services.vocabulary_extractor import (
    _MEDIA_PREFIXES,
    _WORD_RE,
    STOPWORDS,
    build_global_corpus,
    tokenize,
)
from services.calibration_loader import detect_message_language

# ---------------------------------------------------------------------------
# Emoji regex (from cpe_v3_evaluator.py)
# ---------------------------------------------------------------------------
EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F900-\U0001F9FF]"
    r"[\U0001F3FB-\U0001F3FF\uFE0F]?"
)

# ---------------------------------------------------------------------------
# Multilingual context classification keywords
# ---------------------------------------------------------------------------
_GREETING_KW = frozenset({
    # ES
    "hola", "buenos dias", "buenas tardes", "buenas noches", "buenas", "qué tal",
    # CA
    "bon dia", "bona tarda", "bona nit", "ei", "ey",
    # EN
    "hello", "hi", "hey", "good morning", "good evening",
    # PT
    "olá", "oi", "bom dia", "boa tarde",
    # IT
    "ciao", "buongiorno", "buonasera",
    # FR
    "bonjour", "bonsoir", "salut",
})

_QUESTION_SERVICE_KW = frozenset({
    # ES
    "precio", "cuánto", "horario", "reserva", "inscripción", "clase", "sesión",
    "cita", "disponibilidad", "comprar", "pagar", "oferta", "descuento",
    # CA
    "preu", "quant", "horari", "reserva", "inscripció", "classe", "sessió",
    "disponibilitat", "comprar", "pagar", "oferta", "descompte",
    # EN
    "price", "how much", "schedule", "booking", "reservation", "class",
    "session", "appointment", "availability", "buy", "pay", "offer", "discount",
    # PT
    "preço", "quanto", "horário", "reserva", "aula",
    # IT
    "prezzo", "quanto", "orario", "prenotazione", "lezione",
})

_EMOTIONAL_KW = frozenset({
    # ES
    "triste", "enfadado", "frustrado", "contento", "feliz", "ansiedad",
    "deprimido", "emocionado", "agradecido", "agobiad",
    # CA
    "trist", "enfadat", "frustrat", "content", "feliç", "ansiós",
    "deprimit", "emocionat", "agraït", "agobiat",
    # EN
    "sad", "angry", "frustrated", "happy", "anxious", "depressed",
    "excited", "grateful", "stressed", "overwhelmed",
    # PT
    "triste", "feliz", "ansioso", "animado", "grato",
    # IT
    "triste", "arrabbiato", "felice", "ansioso", "grato",
})

_HEALTH_KW = frozenset({
    # ES
    "hospital", "médico", "enfermo", "operación", "dolor", "salud",
    "lesión", "recuperación", "tratamiento", "diagnóstico",
    "duele", "enfermedad", "cirugía", "operar",
    # CA
    "hospital", "metge", "malalt", "operació", "dolor", "salut",
    "lesió", "recuperació", "tractament", "diagnòstic", "fa mal",
    # EN
    "hospital", "doctor", "sick", "surgery", "pain", "health",
    "injury", "recovery", "treatment", "diagnosis", "hurts",
    # PT
    "hospital", "médico", "doente", "cirurgia", "dor", "saúde",
    # IT
    "ospedale", "medico", "malato", "intervento", "dolore", "salute",
})

_LAUGH_KW = frozenset({
    "jaja", "jajaja", "jajajaja", "haha", "hahaha", "lol", "lool",
    "jejeje", "jeje", "rsrs", "kkk", "xd", "xdd",
})

LAUGH_EMOJI = frozenset({"😂", "🤣", "😆", "😹"})

# ---------------------------------------------------------------------------
# Context classifier
# ---------------------------------------------------------------------------

def _is_emoji_only(text: str) -> bool:
    """Return True if text is composed entirely of emojis and whitespace."""
    stripped = EMOJI_RE.sub("", text).strip()
    return len(stripped) == 0 and len(text.strip()) > 0


def _is_media(text: str) -> bool:
    low = text.strip().lower()
    return any(low.startswith(p) for p in _MEDIA_PREFIXES)


def _text_contains_any(text: str, keywords: frozenset) -> bool:
    low = text.lower()
    for kw in keywords:
        if kw in low:
            return True
    return False


def classify_context(user_msg: str) -> str:
    """Classify a user message into one of 8 context types.

    Priority order: EMOJI_ONLY > MEDIA > LAUGH > GREETING > HEALTH >
    EMOTIONAL > QUESTION_SERVICE > OTHER
    """
    if not user_msg or not user_msg.strip():
        return "OTHER"
    if _is_emoji_only(user_msg):
        return "EMOJI_ONLY"
    if _is_media(user_msg):
        return "MEDIA"
    low = user_msg.lower()
    # LAUGH: keywords or laugh emojis
    if any(kw in low for kw in _LAUGH_KW) or any(e in user_msg for e in LAUGH_EMOJI):
        return "LAUGH"
    if _text_contains_any(user_msg, _GREETING_KW):
        return "GREETING"
    if _text_contains_any(user_msg, _HEALTH_KW):
        return "HEALTH"
    if _text_contains_any(user_msg, _EMOTIONAL_KW):
        return "EMOTIONAL"
    if _text_contains_any(user_msg, _QUESTION_SERVICE_KW):
        return "QUESTION_SERVICE"
    return "OTHER"


# ---------------------------------------------------------------------------
# Percentile helpers
# ---------------------------------------------------------------------------

def _percentiles(values: List[float]) -> Dict[str, float]:
    if not values:
        return {}
    arr = np.array(values, dtype=float)
    return {
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "P10": float(np.percentile(arr, 10)),
        "P25": float(np.percentile(arr, 25)),
        "P75": float(np.percentile(arr, 75)),
        "P90": float(np.percentile(arr, 90)),
        "P95": float(np.percentile(arr, 95)),
        "count": len(values),
    }


def _threshold(values: List[float]) -> Tuple[float, float]:
    """Return [P10, P90] thresholds from distribution."""
    if len(values) < 5:
        return (0.0, float("inf"))
    arr = np.array(values, dtype=float)
    return (float(np.percentile(arr, 10)), float(np.percentile(arr, 90)))


# ---------------------------------------------------------------------------
# DB access
# ---------------------------------------------------------------------------
def _get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return psycopg2.connect(url)


def _resolve_creator_uuid(conn, creator_slug: str) -> Optional[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM creators WHERE name = %s", (creator_slug,))
        row = cur.fetchone()
        return str(row[0]) if row else None


# ---------------------------------------------------------------------------
# Style Profile Builder
# ---------------------------------------------------------------------------

class StyleProfileBuilder:
    """Builds a complete statistical style profile from real creator messages."""

    def build(self, creator_id: str) -> Dict[str, Any]:
        """Build style profile for a creator.

        Args:
            creator_id: Creator slug (e.g. 'iris_bertran')

        Returns:
            Complete style profile dict with A1-A9 metrics and thresholds.
        """
        conn = _get_conn()
        try:
            creator_uuid = _resolve_creator_uuid(conn, creator_id)
            if not creator_uuid:
                raise ValueError(f"Creator '{creator_id}' not found")

            creator_msgs = self._fetch_creator_messages(conn, creator_uuid)
            if len(creator_msgs) < 5:
                raise ValueError(
                    f"Creator '{creator_id}' has only {len(creator_msgs)} "
                    f"messages — need at least 5"
                )

            pairs = self._fetch_message_pairs(conn, creator_uuid)

            profile = {
                "creator_id": creator_id,
                "total_messages": len(creator_msgs),
                "total_pairs": len(pairs),
                "A1_length": self._compute_a1(creator_msgs),
                "A2_emoji": self._compute_a2(creator_msgs, pairs),
                "A3_exclamations": self._compute_a3(creator_msgs),
                "A4_questions": self._compute_a4(creator_msgs),
                "A5_vocabulary": self._compute_a5(creator_id, creator_msgs),
                "A6_language_ratio": self._compute_a6(creator_msgs),
                "A7_fragmentation": self._compute_a7(conn, creator_uuid),
                "A8_formality": self._compute_a8(creator_msgs),
                "A9_catchphrases": self._compute_a9(creator_msgs),
            }
            return profile
        finally:
            conn.close()

    # -- DB fetch ----------------------------------------------------------

    def _fetch_creator_messages(
        self, conn, creator_uuid: str, page_size: int = 5000
    ) -> List[str]:
        """Fetch all real creator messages (approved, not deleted)."""
        messages = []
        offset = 0
        with conn.cursor() as cur:
            while True:
                cur.execute("""
                    SELECT m.content
                    FROM messages m
                    JOIN leads l ON l.id = m.lead_id
                    WHERE l.creator_id = CAST(%s AS uuid)
                      AND m.role = 'assistant'
                      AND m.content IS NOT NULL
                      AND LENGTH(m.content) > 2
                      AND m.deleted_at IS NULL
                      AND COALESCE(m.approved_by, 'human')
                          NOT IN ('auto', 'autopilot')
                    ORDER BY m.created_at
                    LIMIT %s OFFSET %s
                """, (creator_uuid, page_size, offset))
                rows = cur.fetchall()
                if not rows:
                    break
                messages.extend(row[0] for row in rows)
                offset += page_size
        return messages

    def _fetch_message_pairs(
        self, conn, creator_uuid: str, page_size: int = 5000
    ) -> List[Tuple[str, str]]:
        """Fetch (user_msg, creator_response) pairs ordered by time."""
        all_msgs: List[Tuple[str, str, str]] = []  # (role, content, created_at)
        offset = 0
        with conn.cursor() as cur:
            while True:
                cur.execute("""
                    SELECT m.role, m.content, m.created_at
                    FROM messages m
                    JOIN leads l ON l.id = m.lead_id
                    WHERE l.creator_id = CAST(%s AS uuid)
                      AND m.content IS NOT NULL
                      AND LENGTH(m.content) > 2
                      AND m.deleted_at IS NULL
                      AND (m.role = 'user'
                           OR COALESCE(m.approved_by, 'human')
                              NOT IN ('auto', 'autopilot'))
                    ORDER BY m.lead_id, m.created_at
                    LIMIT %s OFFSET %s
                """, (creator_uuid, page_size, offset))
                rows = cur.fetchall()
                if not rows:
                    break
                all_msgs.extend(rows)
                offset += page_size

        # Pair: user msg followed by assistant msg
        pairs = []
        for i in range(len(all_msgs) - 1):
            if all_msgs[i][0] == "user" and all_msgs[i + 1][0] == "assistant":
                pairs.append((all_msgs[i][1], all_msgs[i + 1][1]))
        return pairs

    # -- A1: Length --------------------------------------------------------

    def _compute_a1(self, messages: List[str]) -> Dict[str, Any]:
        lengths = [len(m) for m in messages]
        stats = _percentiles(lengths)
        stats["threshold"] = list(_threshold(lengths))
        return stats

    # -- A2: Emoji (global + per context type) -----------------------------

    def _compute_a2(
        self, messages: List[str], pairs: List[Tuple[str, str]]
    ) -> Dict[str, Any]:
        # Global emoji rate
        has_emoji = sum(1 for m in messages if EMOJI_RE.search(m))
        global_rate = has_emoji / len(messages) if messages else 0.0

        # Emoji count per message
        emoji_counts = [len(EMOJI_RE.findall(m)) for m in messages]

        # Per context type
        context_rates: Dict[str, List[int]] = defaultdict(list)
        for user_msg, creator_msg in pairs:
            ctx = classify_context(user_msg)
            has = 1 if EMOJI_RE.search(creator_msg) else 0
            context_rates[ctx].append(has)

        per_context = {}
        for ctx, vals in context_rates.items():
            rate = sum(vals) / len(vals) if vals else 0.0
            per_context[ctx] = {"rate": rate, "count": len(vals)}

        return {
            "global_rate": global_rate,
            "emoji_count_stats": _percentiles(emoji_counts),
            "per_context": per_context,
            "threshold_global": list(_threshold(
                [1.0 if EMOJI_RE.search(m) else 0.0 for m in messages]
            )),
        }

    # -- A3: Exclamations --------------------------------------------------

    def _compute_a3(self, messages: List[str]) -> Dict[str, Any]:
        has_excl = [1.0 if "!" in m else 0.0 for m in messages]
        rate = sum(has_excl) / len(has_excl) if has_excl else 0.0
        return {"rate": rate, "threshold": list(_threshold(has_excl))}

    # -- A4: Questions -----------------------------------------------------

    def _compute_a4(self, messages: List[str]) -> Dict[str, Any]:
        has_q = [1.0 if "?" in m else 0.0 for m in messages]
        rate = sum(has_q) / len(has_q) if has_q else 0.0
        return {"rate": rate, "threshold": list(_threshold(has_q))}

    # -- A5: Distinctive vocabulary ----------------------------------------

    def _compute_a5(
        self, creator_id: str, messages: List[str]
    ) -> Dict[str, Any]:
        # Build TF for creator
        word_freq: Counter = Counter()
        for m in messages:
            word_freq.update(tokenize(m))

        # Use existing vocabulary extractor for global corpus
        try:
            global_vocab, total_leads, leads_per_word = build_global_corpus(
                creator_id, use_cache=False
            )
        except Exception:
            # Fallback: use raw frequency
            top = word_freq.most_common(50)
            return {"top_50": [{"word": w, "freq": f} for w, f in top],
                    "method": "frequency_fallback"}

        from services.vocabulary_extractor import compute_distinctiveness
        scored = compute_distinctiveness(
            dict(word_freq), global_vocab, total_leads, leads_per_word
        )
        top_50 = scored[:50]
        return {
            "top_50": [{"word": w, "score": round(s, 4)} for w, s in top_50],
            "method": "tfidf",
        }

    # -- A6: Language ratio ------------------------------------------------

    def _compute_a6(self, messages: List[str]) -> Dict[str, Any]:
        lang_counts: Counter = Counter()
        for m in messages:
            lang = detect_message_language(m)
            if lang:
                lang_counts[lang] += 1
            else:
                lang_counts["unknown"] += 1
        total = sum(lang_counts.values())
        ratios = {k: round(v / total, 4) for k, v in lang_counts.most_common()}
        return {"ratios": ratios, "total_detected": total}

    # -- A7: Fragmentation ------------------------------------------------

    def _compute_a7(self, conn, creator_uuid: str) -> Dict[str, Any]:
        """Measure consecutive assistant messages without user reply."""
        frag_counts = []
        with conn.cursor() as cur:
            # Single query: all roles ordered by lead + time
            cur.execute("""
                SELECT m.lead_id, m.role
                FROM messages m
                JOIN leads l ON l.id = m.lead_id
                WHERE l.creator_id = CAST(%s AS uuid)
                  AND m.deleted_at IS NULL
                  AND m.content IS NOT NULL
                ORDER BY m.lead_id, m.created_at
            """, (creator_uuid,))

            current_lead = None
            consecutive = 0
            for lead_id, role in cur:
                if lead_id != current_lead:
                    # New lead — flush previous
                    if consecutive > 0:
                        frag_counts.append(consecutive)
                    current_lead = lead_id
                    consecutive = 0

                if role == "assistant":
                    consecutive += 1
                else:
                    if consecutive > 0:
                        frag_counts.append(consecutive)
                    consecutive = 0

            if consecutive > 0:
                frag_counts.append(consecutive)

        stats = _percentiles(frag_counts) if frag_counts else {"mean": 1.0}
        stats["threshold"] = list(_threshold(frag_counts)) if frag_counts else [1.0, 1.0]
        return stats

    # -- A8: Formality ----------------------------------------------------

    _FORMAL_MARKERS = frozenset({
        # ES formal
        "usted", "ustedes", "le ruego", "atentamente",
        # CA formal
        "vostè", "vostès", "li prego",
        # EN formal
        "sir", "madam", "regards", "sincerely",
    })
    _INFORMAL_MARKERS = frozenset({
        # ES informal
        "tío", "tía", "mola", "guay", "curro", "flipar",
        # CA informal
        "tio", "tia", "mola", "guai", "xulo", "flipar",
        # EN informal
        "dude", "bro", "gonna", "wanna", "lol", "omg",
    })
    _ABBREVIATIONS = frozenset({
        "tb", "tmb", "pq", "xq", "dnd", "q", "k", "pa", "x",
        "tbh", "idk", "imo", "btw", "ngl", "fr",
    })

    def _compute_a8(self, messages: List[str]) -> Dict[str, Any]:
        formal_count = 0
        informal_count = 0
        abbrev_count = 0
        for m in messages:
            words = set(m.lower().split())
            if words & self._FORMAL_MARKERS:
                formal_count += 1
            if words & self._INFORMAL_MARKERS:
                informal_count += 1
            if words & self._ABBREVIATIONS:
                abbrev_count += 1
        n = len(messages)
        return {
            "formal_rate": formal_count / n if n else 0.0,
            "informal_rate": informal_count / n if n else 0.0,
            "abbreviation_rate": abbrev_count / n if n else 0.0,
            "formality_score": (
                formal_count / (formal_count + informal_count)
                if (formal_count + informal_count) > 0
                else 0.5
            ),
        }

    # -- A9: Catchphrases -------------------------------------------------

    def _compute_a9(self, messages: List[str]) -> Dict[str, Any]:
        ngram_counts: Counter = Counter()
        for m in messages:
            words = _WORD_RE.findall(m.lower())
            words = [w for w in words if w not in STOPWORDS]
            for n in range(2, 5):  # 2-grams to 4-grams
                for i in range(len(words) - n + 1):
                    gram = " ".join(words[i:i + n])
                    ngram_counts[gram] += 1

        # Filter: 5+ occurrences, take top 20
        top = [
            (gram, count)
            for gram, count in ngram_counts.most_common(100)
            if count >= 5
        ][:20]
        return {"catchphrases": [{"phrase": g, "count": c} for g, c in top]}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def save_profile(profile: Dict, creator_id: str, output_dir: str = "evaluation_profiles"):
    """Save profile JSON to disk."""
    os.makedirs(os.path.join(output_dir, creator_id), exist_ok=True)
    path = os.path.join(output_dir, creator_id, "style_profile.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False, default=str)
    return path


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build style profile for a creator")
    parser.add_argument("--creator", required=True, help="Creator slug")
    args = parser.parse_args()

    builder = StyleProfileBuilder()
    profile = builder.build(args.creator)
    path = save_profile(profile, args.creator)
    print(f"Style profile saved to {path}")
    print(f"  Messages: {profile['total_messages']}")
    print(f"  Pairs: {profile['total_pairs']}")
    print(f"  Languages: {profile['A6_language_ratio']['ratios']}")
    print(f"  Catchphrases: {len(profile['A9_catchphrases']['catchphrases'])}")
