#!/usr/bin/env python3
"""
CPE Baseline Metrics Generator — universal quantitative style profile.

Extracts last N messages from a creator's DB history and computes
quantitative style metrics for Clone Personality Evaluation.

Usage:
    python scripts/cpe_generate_baseline.py --creator iris_bertran
    python scripts/cpe_generate_baseline.py --creator stefano_bonanno --limit 1000

Output:
    tests/cpe_data/{creator}/baseline_metrics.json
"""

import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

# Emoji regex (broad unicode coverage)
_EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U00002600-\U000027BF]+",
    flags=re.UNICODE,
)

# Stopwords (ES + CA minimal set — keeping distinctive words)
_STOPWORDS = {
    "de", "la", "el", "en", "y", "a", "que", "es", "un", "una", "los",
    "las", "del", "al", "por", "con", "para", "se", "no", "lo", "le",
    "me", "te", "su", "mi", "tu", "si", "ya", "ha", "he", "i", "o",
    "les", "us", "em", "et", "ho", "li", "hi",
}

# Formality markers
_USTED_MARKERS = re.compile(r"\b(usted|ustedes|le\s+(?:informo|comunico)|su\s+(?:pedido|solicitud))\b", re.I)
_TUTEO_MARKERS = re.compile(r"\b(tú|tu\s|tienes|puedes|quieres|vienes|te\s+(?:mando|paso|apunto))\b", re.I)
_VOSEO_MARKERS = re.compile(r"\b(vos|tenés|podés|querés|venís|sabés)\b", re.I)


def get_creator_messages(creator_slug: str, limit: int = 500):
    """Fetch real creator messages from DB."""
    from sqlalchemy import create_engine, text

    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "sslmode" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    engine = create_engine(url, pool_size=2)

    with engine.connect() as conn:
        # Resolve creator UUID
        row = conn.execute(
            text("SELECT id FROM creators WHERE name = :name"), {"name": creator_slug}
        ).fetchone()
        if not row:
            print(f"Creator '{creator_slug}' not found")
            sys.exit(1)
        cid = str(row[0])

        # Fetch messages — real ones only (sent/resolved_externally)
        msgs = conn.execute(
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
                  AND m.content NOT LIKE 'Estoy usando%%'
                ORDER BY m.created_at DESC
                LIMIT :lim
            """),
            {"cid": cid, "lim": limit},
        ).fetchall()

    return [{"content": m[0], "created_at": m[1]} for m in msgs]


def detect_language(text: str) -> str:
    """Detect language using langdetect. Returns ISO 639-1 code."""
    try:
        from langdetect import detect

        return detect(text)
    except Exception:
        return "unknown"


def compute_metrics(messages: list) -> dict:
    """Compute all quantitative style metrics."""
    texts = [m["content"] for m in messages]
    n = len(texts)
    if n == 0:
        return {"error": "no messages"}

    # --- a) Message length ---
    lengths = [len(t) for t in texts]
    word_counts = [len(t.split()) for t in texts]

    def pct(data, p):
        s = sorted(data)
        k = int(len(s) * p / 100)
        return s[min(k, len(s) - 1)]

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

    # --- b) Emoji rate ---
    emoji_msgs = 0
    emoji_counter = Counter()
    total_emojis = 0
    for t in texts:
        matches = _EMOJI_RE.findall(t)
        chars = []
        for m in matches:
            chars.extend(list(m))
        # Filter variation selectors and zero-width joiners
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

    # --- c) Question rate ---
    question_rate = round(sum(1 for t in texts if "?" in t) / n * 100, 1)

    # --- d) Exclamation rate ---
    exclamation_rate = round(sum(1 for t in texts if "!" in t) / n * 100, 1)

    # --- e) Languages detected ---
    lang_counter = Counter()
    for t in texts:
        if len(t) >= 10:  # langdetect needs enough text
            lang = detect_language(t)
            lang_counter[lang] += 1
    lang_total = sum(lang_counter.values())
    languages = {
        "detected": [
            {"lang": lang, "count": cnt, "pct": round(cnt / max(lang_total, 1) * 100, 1)}
            for lang, cnt in lang_counter.most_common(5)
        ],
        "total_detected": lang_total,
    }

    # --- f) Vocabulary top 50 ---
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

    # --- g) Greeting patterns ---
    greeting_counter = Counter()
    for t in texts:
        first = t.split()[0].lower().rstrip("!.,?") if t.split() else ""
        if first:
            greeting_counter[first] += 1

    greeting_patterns = {
        "top_15_openers": greeting_counter.most_common(15),
    }

    # --- h) Response diversity (type-token ratio) ---
    all_words = []
    for t in texts:
        all_words.extend(re.findall(r"[a-záéíóúàèòüïçñ]+", t.lower()))
    ttr = len(set(all_words)) / max(len(all_words), 1)

    diversity = {
        "type_token_ratio": round(ttr, 3),
        "unique_types": len(set(all_words)),
        "total_tokens": len(all_words),
    }

    # --- i) Formality score ---
    usted_count = sum(1 for t in texts if _USTED_MARKERS.search(t))
    tuteo_count = sum(1 for t in texts if _TUTEO_MARKERS.search(t))
    voseo_count = sum(1 for t in texts if _VOSEO_MARKERS.search(t))

    formality = {
        "usted_pct": round(usted_count / n * 100, 1),
        "tuteo_pct": round(tuteo_count / n * 100, 1),
        "voseo_pct": round(voseo_count / n * 100, 1),
        "dominant": "usted" if usted_count > tuteo_count and usted_count > voseo_count
                    else "voseo" if voseo_count > tuteo_count
                    else "tuteo",
    }

    # --- j) Laugh patterns ---
    laugh_re = re.compile(r"(?:ja|je|ji|jo){2,}|(?:ha|he){2,}", re.I)
    laugh_rate = round(sum(1 for t in texts if laugh_re.search(t)) / n * 100, 1)

    # --- k) Punctuation patterns ---
    ellipsis_rate = round(sum(1 for t in texts if "..." in t) / n * 100, 1)
    caps_rate = round(sum(1 for t in texts if t == t.upper() and len(t) > 3) / n * 100, 1)

    punctuation = {
        "question_rate_pct": question_rate,
        "exclamation_rate_pct": exclamation_rate,
        "laugh_rate_pct": laugh_rate,
        "ellipsis_rate_pct": ellipsis_rate,
        "all_caps_rate_pct": caps_rate,
    }

    return {
        "total_messages": n,
        "length": length_stats,
        "emoji": emoji_stats,
        "punctuation": punctuation,
        "languages": languages,
        "vocabulary": vocabulary,
        "greeting_patterns": greeting_patterns,
        "diversity": diversity,
        "formality": formality,
    }


def main():
    parser = argparse.ArgumentParser(description="CPE Baseline Metrics Generator")
    parser.add_argument("--creator", required=True, help="Creator slug (e.g. iris_bertran)")
    parser.add_argument("--limit", type=int, default=500, help="Max messages to analyze")
    parser.add_argument("--output", default=None, help="Output path (default: tests/cpe_data/{creator}/)")
    args = parser.parse_args()

    print(f"Fetching messages for {args.creator}...")
    messages = get_creator_messages(args.creator, args.limit)
    print(f"Fetched {len(messages)} messages")

    if not messages:
        print("No messages found")
        sys.exit(1)

    print("Computing metrics...")
    metrics = compute_metrics(messages)

    # Output
    out_dir = Path(args.output) if args.output else Path("tests/cpe_data") / args.creator
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "baseline_metrics.json"

    output = {
        "creator": args.creator,
        "generated_at": str(messages[0]["created_at"]) if messages else "",
        "messages_analyzed": len(messages),
        "metrics": metrics,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\nSaved to {out_path}")

    # Also save to DB for production access
    try:
        from services.creator_profile_service import save_profile
        if save_profile(args.creator, "baseline_metrics", output):
            print(f"✅ Saved to DB: {args.creator}/baseline_metrics")
        else:
            print(f"⚠️ DB save failed (creator not found?)")
    except Exception as e:
        print(f"⚠️ DB save skipped: {e}")

    # Summary
    m = metrics
    print(f"\n{'='*50}")
    print(f"BASELINE METRICS: {args.creator}")
    print(f"{'='*50}")
    print(f"  Messages: {m['total_messages']}")
    print(f"  Length: mean={m['length']['char_mean']} median={m['length']['char_median']} p90={m['length']['char_p90']}")
    print(f"  Emoji: {m['emoji']['emoji_rate_pct']}% ({m['emoji']['avg_emoji_count']}/msg)")
    top_e = [e[0] for e in m["emoji"]["top_20_emojis"][:5]]
    print(f"  Top emojis: {' '.join(top_e)}")
    print(f"  Questions: {m['punctuation']['question_rate_pct']}%")
    print(f"  Exclamations: {m['punctuation']['exclamation_rate_pct']}%")
    print(f"  Laughs: {m['punctuation']['laugh_rate_pct']}%")
    print(f"  Formality: {m['formality']['dominant']} (tuteo={m['formality']['tuteo_pct']}%)")
    print(f"  Diversity (TTR): {m['diversity']['type_token_ratio']}")
    langs = [f"{l['lang']}={l['pct']}%" for l in m["languages"]["detected"][:3]]
    print(f"  Languages: {', '.join(langs)}")


if __name__ == "__main__":
    main()
