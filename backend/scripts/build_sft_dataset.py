"""
Build SFT Dataset for Iris Bertran fine-tuning.

Extracts (lead_message, iris_response) pairs from production DB.
Formats as JSON Lines (TRL SFTTrainer / Together AI compatible).

Usage:
    railway run .venv/bin/python3 scripts/build_sft_dataset.py

Output (data/dpo/trl/):
    sft_full.jsonl      — all pairs
    sft_2000.jsonl      — 2,000 diverse pairs
    sft_500.jsonl       — 500 maximally diverse pairs
    sft_eval.jsonl      — 10% random eval set
    sft_together_2000.jsonl — Together AI format (same as TRL)
"""

import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

random.seed(42)

# ── Constants ──────────────────────────────────────────────────────────────
CREATOR_ID = "8e9d1705-4772-40bd-83b1-c6821c5593bf"   # iris_bertran
OUTPUT_DIR = REPO_ROOT / "data" / "dpo" / "trl"
DOC_D_PATH = REPO_ROOT / "data" / "personality_extractions" / "iris_bertran_v2_distilled.md"

# Filters
MIN_RESPONSE_CHARS = 3
MAX_RESPONSE_CHARS = 500
BAD_RESPONSE_PATTERNS = [
    "[error", "sorry, i", "```",
    "lo siento", "hubo un error", "procesando tu mensaje",
    "intenta de nuevo", "por favor intenta",
    "i can't", "i cannot", "as an ai",
    "el audio no se ha podido",   # audio fallback
    "no puc escoltar",            # audio fallback ca
    "escríbemelo",                # audio ask-to-write
    "m'ho pots escriure",         # audio ask-to-write ca
]
# Also filter responses containing bare URLs (model shouldn't memorize dynamic links)
_URL_RE = re.compile(r'https?://')


def has_url(text: str) -> bool:
    return bool(_URL_RE.search(text))

# ── Load Doc D system prompt ───────────────────────────────────────────────
def load_system_prompt() -> str:
    """Extract the system prompt block from Doc D v2 distilled (max 600 chars)."""
    if not DOC_D_PATH.exists():
        return (
            "Eres Iris Bertran. Instructora de fitness/danza en Barcelona. "
            "Respondes DMs como lo harías tú: corto, directo, con emojis, "
            "code-switching catalán/castellano natural. NUNCA preguntes '¿en qué puedo ayudarte?'."
        )

    text = DOC_D_PATH.read_text(encoding="utf-8")

    # Extract the ```...``` block which contains the system prompt
    m = re.search(r"```\n(.*?)```", text, re.DOTALL)
    if m:
        prompt = m.group(1).strip()
        # Trim to max 600 chars at sentence boundary
        if len(prompt) > 600:
            prompt = prompt[:600].rsplit("\n", 1)[0].strip()
        return prompt

    # Fallback: first 600 chars of file
    return text[:600].strip()


SYSTEM_PROMPT = load_system_prompt()
print(f"System prompt: {len(SYSTEM_PROMPT)} chars")
print(f"Preview: {SYSTEM_PROMPT[:120]}...")
print()


# ── Language detection ─────────────────────────────────────────────────────
_CA = re.compile(r'\b(però|molt|avui|demà|tinc|estic|vaig|quan|que fas|que et|gràcies|fins|dilluns|dimarts|dimecres|dijous|divendres|dissabte|diumenge|doncs|ara |anem|heu |han |l\'|d\'[aeiouàèéíòóú])\b', re.IGNORECASE)
_ES = re.compile(r'\b(tengo|tienes|tiene|pero |mucho|estoy|estás|soy|eres|fue|fui|hoy |mañana|gracias|señor|señora|buenas|buenos|cómo estás|me llamo|me ha|lo que)\b|[ñÑ]', re.IGNORECASE)


def detect_lang(text: str) -> str:
    ca = len(_CA.findall(text))
    es = len(_ES.findall(text))
    if ca > 0 and es == 0:
        return "ca"
    if es > 0 and ca == 0:
        return "es"
    if ca > 0 and es > 0:
        return "mixto"
    return "unknown"


# ── Filtering ──────────────────────────────────────────────────────────────
def is_bad_response(text: str) -> bool:
    if not text or len(text.strip()) < MIN_RESPONSE_CHARS:
        return True
    if len(text.strip()) > MAX_RESPONSE_CHARS:
        return True
    t = text.lower()
    return any(pat in t for pat in BAD_RESPONSE_PATTERNS)


def is_bad_user_msg(text: str) -> bool:
    if not text or len(text.strip()) < 1:
        return True
    # Skip pure system placeholders
    skip = ["sent a payment", "started a video call", "missed video call",
            "sent an attachment", "liked your message"]
    t = text.lower().strip()
    return any(s in t for s in skip)


# ── Main extraction ────────────────────────────────────────────────────────
def extract_pairs():
    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        print(f"Connecting to DB... extracting messages for creator {CREATOR_ID}")

        # Pull all messages for Iris's leads, ordered by lead + time
        # We fetch in one query to minimize round trips
        rows = session.execute(text("""
            SELECT
                m.lead_id,
                m.role,
                m.content,
                m.created_at,
                m.copilot_action
            FROM messages m
            JOIN leads l ON m.lead_id = l.id
            WHERE l.creator_id = :creator_id
              AND m.deleted_at IS NULL
              AND m.content IS NOT NULL
              AND m.content != ''
            ORDER BY m.lead_id, m.created_at
        """), {"creator_id": CREATOR_ID}).fetchall()

        print(f"Raw rows from DB: {len(rows)}")

        # Group by lead
        by_lead = defaultdict(list)
        for row in rows:
            by_lead[row.lead_id].append({
                "role": row.role,
                "content": row.content.strip(),
                "created_at": row.created_at,
                "copilot_action": row.copilot_action,
            })

        print(f"Unique leads: {len(by_lead)}")

        pairs = []

        for lead_id, msgs in by_lead.items():
            # Build (user_msg, iris_response) pairs
            # Strategy: for each run of consecutive assistant messages where
            # copilot_action IS NULL, find the preceding user message.
            i = 0
            while i < len(msgs):
                msg = msgs[i]

                # Find a manual Iris response (assistant, no copilot_action)
                if msg["role"] == "assistant" and not msg["copilot_action"]:
                    # Collect consecutive manual Iris messages (concatenate)
                    iris_parts = [msg["content"]]
                    j = i + 1
                    while j < len(msgs):
                        nxt = msgs[j]
                        if nxt["role"] == "assistant" and not nxt["copilot_action"]:
                            iris_parts.append(nxt["content"])
                            j += 1
                        else:
                            break

                    iris_response = "\n".join(iris_parts)

                    # Find the last user message BEFORE position i
                    user_msg = None
                    for k in range(i - 1, -1, -1):
                        if msgs[k]["role"] == "user":
                            user_msg = msgs[k]["content"]
                            break

                    if user_msg and not is_bad_user_msg(user_msg) and not is_bad_response(iris_response) and not has_url(iris_response):
                        pairs.append({
                            "user": user_msg,
                            "assistant": iris_response,
                            "created_at": msg["created_at"],
                            "lead_id": str(lead_id),
                        })

                    i = j  # Skip the consumed Iris messages
                else:
                    i += 1

        return pairs

    finally:
        session.close()


# ── Build JSONL line ───────────────────────────────────────────────────────
def make_line(pair: dict) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": pair["user"]},
            {"role": "assistant", "content": pair["assistant"]},
        ]
    }


# ── Diversity-aware 500-sample selection ──────────────────────────────────
def select_diverse_500(pairs: list) -> list:
    """Select 500 pairs maximizing diversity by language, type, and recency."""
    def classify(p):
        lang = detect_lang(p["user"] + " " + p["assistant"])
        u = p["user"].lower()
        a = p["assistant"].lower()
        # Rough type classification
        if any(w in u for w in ["hola", "bon dia", "buenas", "hey ", "holaa"]):
            return "saludo", lang
        if any(w in u for w in ["precio", "cuánto", "preu", "quant", "euros", "€", "pagar", "precio"]):
            return "precio", lang
        if any(w in u for w in ["no puedo", "no puc", "no podré", "no vendré", "trabajo", "treball", "cita"]):
            return "objecion", lang
        if any(w in u for w in ["🎤", "[audio", "nota de voz"]):
            return "audio", lang
        if any(w in u for w in ["apunto", "reservar", "reservo", "inscrib", "apunta", "apúntame"]):
            return "lead_caliente", lang
        # personal: short user messages that feel casual
        if len(p["user"]) < 40:
            return "personal", lang
        return "general", lang

    # Build buckets
    buckets = defaultdict(list)
    for p in pairs:
        t, lang = classify(p)
        buckets[(t, lang)].append(p)

    # Sort each bucket by recency (most recent first) then shuffle for variety
    for key in buckets:
        random.shuffle(buckets[key])

    selected = []
    seen_assistants = set()

    # Priority fills
    targets = [
        ("saludo", "ca", 25), ("saludo", "es", 25),
        ("precio", "ca", 25), ("precio", "es", 25),
        ("personal", "ca", 25), ("personal", "es", 25),
        ("objecion", "ca", 15), ("objecion", "es", 15),
        ("audio", "ca", 10), ("audio", "es", 10),
        ("lead_caliente", "ca", 15), ("lead_caliente", "es", 15),
    ]

    for t, lang, quota in targets:
        bucket = buckets.get((t, lang), [])
        added = 0
        for p in bucket:
            if added >= quota:
                break
            key = p["assistant"].strip().lower()
            if key not in seen_assistants:
                selected.append(p)
                seen_assistants.add(key)
                added += 1

    # Fill remaining from all pairs (deduped)
    remaining_pool = [p for p in pairs if p["assistant"].strip().lower() not in seen_assistants]
    random.shuffle(remaining_pool)
    for p in remaining_pool:
        if len(selected) >= 500:
            break
        key = p["assistant"].strip().lower()
        if key not in seen_assistants:
            selected.append(p)
            seen_assistants.add(key)

    random.shuffle(selected)
    return selected[:500]


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Extract
    print("=" * 60)
    print("EXTRACTING PAIRS FROM DB")
    print("=" * 60)
    pairs = extract_pairs()
    print(f"Raw pairs before filter: {len(pairs)}")

    # 2. Deduplicate (exact assistant response)
    seen = set()
    deduped = []
    for p in pairs:
        key = p["assistant"].strip().lower()
        if key not in seen:
            deduped.append(p)
            seen.add(key)
    print(f"After dedup: {len(deduped)}")

    # Sort by created_at descending (most recent first)
    deduped.sort(key=lambda x: x["created_at"], reverse=True)

    # 3. Stats
    lang_counts = defaultdict(int)
    resp_lengths = []
    for p in deduped:
        lang = detect_lang(p["user"] + " " + p["assistant"])
        lang_counts[lang] += 1
        resp_lengths.append(len(p["assistant"]))

    avg_len = sum(resp_lengths) / len(resp_lengths) if resp_lengths else 0

    # 4. Write sft_full.jsonl
    full_path = OUTPUT_DIR / "sft_full.jsonl"
    with open(full_path, "w", encoding="utf-8") as f:
        for p in deduped:
            f.write(json.dumps(make_line(p), ensure_ascii=False) + "\n")
    print(f"sft_full.jsonl: {len(deduped)} lines")

    # 5. Write sft_2000.jsonl (most recent 2000, deduped)
    pairs_2000 = deduped[:2000]
    path_2000 = OUTPUT_DIR / "sft_2000.jsonl"
    with open(path_2000, "w", encoding="utf-8") as f:
        for p in pairs_2000:
            f.write(json.dumps(make_line(p), ensure_ascii=False) + "\n")
    print(f"sft_2000.jsonl: {len(pairs_2000)} lines")

    # 6. Write sft_500.jsonl (diverse 500)
    pairs_500 = select_diverse_500(deduped)
    path_500 = OUTPUT_DIR / "sft_500.jsonl"
    with open(path_500, "w", encoding="utf-8") as f:
        for p in pairs_500:
            f.write(json.dumps(make_line(p), ensure_ascii=False) + "\n")
    print(f"sft_500.jsonl: {len(pairs_500)} lines")

    # 7. Write sft_eval.jsonl (10% random from full, NOT overlapping with train sets)
    eval_pool = deduped[2000:]   # Everything after sft_2000 window
    if len(eval_pool) < 100:
        # Fallback: sample from full, avoiding sft_500
        train_keys = {p["assistant"].strip().lower() for p in pairs_500}
        eval_pool = [p for p in deduped if p["assistant"].strip().lower() not in train_keys]
    eval_size = max(50, min(500, len(eval_pool) // 10))
    pairs_eval = random.sample(eval_pool, min(eval_size, len(eval_pool)))
    path_eval = OUTPUT_DIR / "sft_eval.jsonl"
    with open(path_eval, "w", encoding="utf-8") as f:
        for p in pairs_eval:
            f.write(json.dumps(make_line(p), ensure_ascii=False) + "\n")
    print(f"sft_eval.jsonl: {len(pairs_eval)} lines")

    # 8. Write sft_together_2000.jsonl (same format, Together AI compatible)
    path_together = OUTPUT_DIR / "sft_together_2000.jsonl"
    with open(path_together, "w", encoding="utf-8") as f:
        for p in pairs_2000:
            f.write(json.dumps(make_line(p), ensure_ascii=False) + "\n")
    print(f"sft_together_2000.jsonl: {len(pairs_2000)} lines")

    # 9. Token estimates (chars / 4)
    def token_est(path):
        total = sum(len(json.dumps(json.loads(l))) for l in open(path, encoding="utf-8"))
        return total // 4

    # 10. Print report
    print()
    print("=" * 60)
    print("DATASET BUILD REPORT — SFT iris_bertran")
    print("=" * 60)
    print(f"Total conversaciones extraídas de BD: {len(pairs)}")
    print(f"Después de filtrar + deduplicar:       {len(deduped)}")
    print()
    print("Líneas por archivo:")
    print(f"  sft_full.jsonl              {len(deduped):>6}  (~{token_est(full_path):,} tokens)")
    print(f"  sft_2000.jsonl              {len(pairs_2000):>6}  (~{token_est(path_2000):,} tokens)")
    print(f"  sft_500.jsonl               {len(pairs_500):>6}  (~{token_est(path_500):,} tokens)")
    print(f"  sft_eval.jsonl              {len(pairs_eval):>6}  (~{token_est(path_eval):,} tokens)")
    print(f"  sft_together_2000.jsonl     {len(pairs_2000):>6}  (~{token_est(path_together):,} tokens)")
    print()
    print("Distribución por idioma (full):")
    for lang in ["ca", "es", "mixto", "unknown"]:
        pct = lang_counts[lang] / len(deduped) * 100 if deduped else 0
        print(f"  {lang:<8} {lang_counts[lang]:>5}  ({pct:.1f}%)")
    print()
    print(f"Longitud media respuesta Iris: {avg_len:.1f} chars")
    print(f"System prompt usado:           {len(SYSTEM_PROMPT)} chars")
    print()
    print("Ejemplos del dataset (3 líneas aleatorias):")
    print("-" * 60)
    samples = random.sample(deduped[:500], min(3, len(deduped)))
    for i, s in enumerate(samples, 1):
        line = make_line(s)
        print(f"\n[{i}] user:      {s['user'][:80]}")
        print(f"    assistant: {s['assistant'][:80]}")
    print()
    print("=" * 60)
    print(f"Archivos en: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
