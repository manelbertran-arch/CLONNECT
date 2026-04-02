"""
Build stratified test set v2 for CPE evaluation.

FIX 1: Sample 50 cases proportionally to real conversation distribution.
FIX 4: Include 10 multi-turn test cases (conversations with 3+ turns of context).

Usage:
    railway run python3 scripts/build_stratified_test_set.py --creator iris_bertran

Output:
    tests/cpe_data/{creator}/test_set_v2_stratified.json
"""

import argparse
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _get_conn():
    """Get psycopg2 connection directly (bypass SQLAlchemy for Python 3.14 compat)."""
    return psycopg2.connect(DATABASE_URL)


# ── Intent mapping: map DB intents → test categories ──────────────────────────
INTENT_TO_CATEGORY = {
    "casual":             "casual",
    "otro":               "casual",
    "humor":              "humor",
    "continuacion":       "casual",
    "pregunta_general":   "question",
    "pregunta_precio":    "product_inquiry",
    "pregunta_producto":  "product_inquiry",
    "pregunta_servicio":  "product_inquiry",
    "reserva":            "booking",
    "saludo":             "greeting",
    "queja":              "objection",
    "agradecimiento":     "thanks",
    "audio":              "audio",
    "sticker":            "emoji_reaction",
    "emoji":              "emoji_reaction",
    "despedida":          "short_response",
    "confirmacion":       "short_response",
    "personal":           "long_personal",
    None:                 "casual",
}


def _resolve_creator_uuid(creator_name: str) -> str:
    """Resolve creator slug to UUID."""
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM creators WHERE name = %s", (creator_name,))
            row = cur.fetchone()
            if not row:
                print(f"ERROR: Creator '{creator_name}' not found")
                sys.exit(1)
            print(f"Creator: {row[1]} (id={row[0]})")
            return str(row[0])
    finally:
        conn.close()


def get_real_distribution(creator_name: str) -> dict:
    """Query DB and classify USER messages by content to get real distribution."""
    creator_uuid = _resolve_creator_uuid(creator_name)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Sample 2000 user messages for classification
            cur.execute("""
                SELECT m.content, m.intent
                FROM messages m
                JOIN leads l ON l.id = m.lead_id
                WHERE l.creator_id = %s
                  AND m.role = 'user'
                  AND m.deleted_at IS NULL
                  AND m.content IS NOT NULL
                  AND m.content != ''
                  AND m.content != '[sticker]'
                  AND m.content != '[Media/Attachment]'
                ORDER BY m.created_at DESC
                LIMIT 2000
            """, (creator_uuid,))
            rows = cur.fetchall()

        dist = Counter()
        for content, intent in rows:
            cat = _classify_message(content, intent)
            dist[cat] += 1

        total = sum(dist.values())
        print(f"\nReal conversation distribution ({total} classified messages):")
        for cat, cnt in sorted(dist.items(), key=lambda x: -x[1]):
            print(f"  {cat:<20} {cnt:>5}  ({cnt/total*100:>5.1f}%)")

        return dict(dist)
    finally:
        conn.close()


def get_language_distribution(creator_name: str) -> dict:
    """Query DB for real language distribution."""
    creator_uuid = _resolve_creator_uuid(creator_name)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(m.msg_metadata->>'language', 'unknown') AS lang,
                       COUNT(m.id)
                FROM messages m
                JOIN leads l ON l.id = m.lead_id
                WHERE l.creator_id = %s
                  AND m.role = 'user'
                  AND m.deleted_at IS NULL
                GROUP BY lang
            """, (creator_uuid,))
            rows = cur.fetchall()
        return {lang: cnt for lang, cnt in rows}
    finally:
        conn.close()


def extract_conversations(creator_name: str, min_turns: int = 1) -> list:
    """Extract conversations with full turn history."""
    creator_uuid = _resolve_creator_uuid(creator_name)
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            # Get leads with enough messages
            cur.execute("""
                SELECT l.id, l.username, l.platform, COUNT(m.id) AS msg_count
                FROM leads l
                JOIN messages m ON m.lead_id = l.id
                WHERE l.creator_id = %s
                  AND m.deleted_at IS NULL
                  AND m.content IS NOT NULL
                  AND m.content != ''
                GROUP BY l.id, l.username, l.platform
                HAVING COUNT(m.id) >= %s
            """, (creator_uuid, min_turns + 1))
            lead_rows = cur.fetchall()

        # Session-aware conversation extraction: split each lead's message stream
        # into separate conversation sessions so we never pair messages from
        # different conversations (e.g., Monday's "quiero barre" with Thursday's
        # "com esta la teva mare").
        from core.conversation_boundary import segment_sessions

        conversations = []
        for lead_id, username, platform, _ in lead_rows:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, role, content, intent, created_at
                    FROM messages
                    WHERE lead_id = %s
                      AND deleted_at IS NULL
                      AND content IS NOT NULL
                      AND content != ''
                    ORDER BY created_at
                """, (lead_id,))
                msg_rows = cur.fetchall()

            if len(msg_rows) < min_turns + 1:
                continue

            all_turns = []
            for msg_id, role, content, intent, created_at in msg_rows:
                all_turns.append({
                    "role": "assistant" if role == "assistant" else "user",
                    "content": content,
                    "intent": intent,
                    "created_at": created_at,
                    "msg_id": str(msg_id),
                })

            # Segment into sessions — each session becomes a separate "conversation"
            sessions = segment_sessions(all_turns)
            for session_turns in sessions:
                if len(session_turns) < min_turns + 1:
                    continue

                # Convert created_at to ISO string for JSON serialization
                for t in session_turns:
                    if t.get("created_at") and not isinstance(t["created_at"], str):
                        t["created_at"] = t["created_at"].isoformat()

                conversations.append({
                    "lead_id": str(lead_id),
                    "lead_username": username or f"lead_{str(lead_id)[:8]}",
                    "platform": platform or "unknown",
                    "turns": session_turns,
                    "msg_count": len(session_turns),
                })

        return conversations
    finally:
        conn.close()


def _detect_language(text: str) -> str:
    """Simple language detection."""
    import re
    ca_re = re.compile(
        r"\b(tinc|estic|però|molt|doncs|també|perquè|això|vull|puc|"
        r"gràcies|gracies|bon dia|puguis|vulguis|avui|aqui|clar)\b", re.I
    )
    es_re = re.compile(
        r"\b(tengo|estoy|pero|mucho|entonces|también|porque|quiero|"
        r"puedo|necesito|bueno|gracias|vale|claro|genial)\b", re.I
    )
    pt_re = re.compile(r"\b(obrigad|olá|voce|tenho|estou|também|porque)\b", re.I)
    en_re = re.compile(r"\b(the|is|are|have|what|how|when|want|need|please)\b", re.I)

    ca = len(ca_re.findall(text))
    es = len(es_re.findall(text))
    pt = len(pt_re.findall(text))
    en = len(en_re.findall(text))

    scores = {"ca": ca, "es": es, "pt": pt, "en": en}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "unknown"
    return best


def _classify_message(text: str, intent: str = None) -> str:
    """Content-based classification (DB intent is poorly populated)."""
    text_l = text.lower().strip()

    # Short responses
    if len(text_l) < 8 and not "?" in text_l:
        return "short_response"

    # Emoji-only reactions
    emoji_re = re.compile(
        r"[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F900-\U0001F9FF]"
    )
    text_no_emoji = emoji_re.sub("", text_l).strip()
    if not text_no_emoji or len(text_no_emoji) < 3:
        return "emoji_reaction"

    # Greetings
    if re.match(r"^(hola|hey|bon dia|bona tarda|buenos?|hi|hello|ola)\b", text_l):
        return "greeting"

    # Thanks
    if re.match(r"^(gr[aà]cies|gracias|thanks|merci|obrigad)", text_l):
        return "thanks"

    # Audio/media
    if text_l in ("[audio]", "[media/attachment]", "[media]", "[voice message]"):
        return "audio"

    # Questions with price/product keywords
    if "?" in text:
        price_kw = ["precio", "preu", "cost", "quanto", "cuanto", "cuánto",
                     "pack", "tarifa", "descuento", "oferta", "pagar"]
        if any(w in text_l for w in price_kw):
            return "product_inquiry"
        product_kw = ["clase", "classe", "sesión", "sessió", "curso",
                      "programa", "plan", "servicio"]
        if any(w in text_l for w in product_kw):
            return "product_inquiry"
        return "question"

    # Booking/scheduling
    booking_kw = ["reserv", "apunt", "horari", "schedule", "cita",
                  "disponib", "libre", "lliure", "booking"]
    if any(w in text_l for w in booking_kw):
        return "booking"

    # Objections/complaints
    obj_kw = ["no puedo", "no puc", "caro", "car ", "difícil", "problema",
              "queja", "cancel", "devol", "reembols"]
    if any(w in text_l for w in obj_kw):
        return "objection"

    # Humor
    humor_kw = ["jaja", "haha", "😂", "🤣", "jeje", "lol"]
    humor_count = sum(1 for kw in humor_kw if kw in text_l)
    if humor_count >= 2 or text_l.count("jaja") >= 2:
        return "humor"

    # Long personal messages
    if len(text) > 100:
        personal_kw = ["siento", "me sento", "vida", "familia", "trabajo",
                       "feina", "relación", "salud", "ansiedad", "estrés"]
        if any(w in text_l for w in personal_kw):
            return "long_personal"

    # Fallback: use DB intent if available
    if intent and intent in INTENT_TO_CATEGORY:
        return INTENT_TO_CATEGORY[intent]

    return "casual"


def build_single_turn_cases(conversations: list, target_dist: dict, n: int = 40) -> list:
    """Build single-turn test cases with stratified sampling."""
    # Build pool: for each conversation, the LAST user message before a bot reply
    pool_by_category = defaultdict(list)

    for conv in conversations:
        turns = conv["turns"]
        for i, turn in enumerate(turns):
            if turn["role"] == "user" and i + 1 < len(turns):
                next_turn = turns[i + 1]
                if next_turn["role"] == "assistant":
                    content = turn["content"]
                    gt = next_turn["content"]

                    # Skip media/sticker messages
                    if content in ("[sticker]", "[Media/Attachment]", "[media]"):
                        continue
                    if gt in ("[sticker]", "[Media/Attachment]", "[media]"):
                        continue
                    if len(content.strip()) < 2 or len(gt.strip()) < 2:
                        continue

                    cat = _classify_message(content, turn.get("intent"))
                    lang = _detect_language(content)

                    # Collect preceding turns as context
                    context_turns = []
                    for j in range(max(0, i - 5), i):
                        t = turns[j]
                        if t["content"] not in ("[sticker]", "[Media/Attachment]"):
                            context_turns.append({
                                "role": t["role"],
                                "content": t["content"],
                            })

                    pool_by_category[cat].append({
                        "test_input": content,
                        "ground_truth": gt,
                        "category": cat,
                        "language": lang,
                        "platform": conv["platform"],
                        "lead_username": conv["lead_username"],
                        "turns": context_turns,
                        "msg_count": len(context_turns),
                        "source_msg_id": turn.get("msg_id", ""),
                    })

    # Calculate proportional allocation
    total_real = sum(target_dist.values())
    allocation = {}
    for cat, count in target_dist.items():
        proportion = count / total_real
        alloc = max(1, round(proportion * n))
        allocation[cat] = alloc

    # Adjust to exactly n
    while sum(allocation.values()) > n:
        # Remove from largest
        largest = max(allocation, key=allocation.get)
        allocation[largest] -= 1
    while sum(allocation.values()) < n:
        # Add to categories with available pool
        for cat in sorted(allocation, key=lambda c: len(pool_by_category.get(c, [])), reverse=True):
            if len(pool_by_category.get(cat, [])) > allocation.get(cat, 0):
                allocation[cat] = allocation.get(cat, 0) + 1
                break
        else:
            break

    print(f"\nTarget allocation ({n} single-turn):")
    for cat, alloc in sorted(allocation.items(), key=lambda x: -x[1]):
        pool_size = len(pool_by_category.get(cat, []))
        print(f"  {cat:<20} {alloc:>3} (pool: {pool_size})")

    # Sample from each category
    cases = []
    seen_inputs = set()
    for cat, alloc in allocation.items():
        pool = pool_by_category.get(cat, [])
        if not pool:
            print(f"  WARNING: no pool for '{cat}', skipping {alloc} cases")
            continue

        random.shuffle(pool)
        selected = 0
        for item in pool:
            if selected >= alloc:
                break
            # Dedup by test_input
            if item["test_input"] in seen_inputs:
                continue
            seen_inputs.add(item["test_input"])
            cases.append(item)
            selected += 1

        if selected < alloc:
            print(f"  WARNING: only {selected}/{alloc} cases for '{cat}'")

    return cases


def build_multi_turn_cases(conversations: list, n: int = 10) -> list:
    """Build multi-turn test cases with 3-5 messages of context (FIX 4)."""
    # Filter conversations with at least 6 turns (3 context + user + bot reply)
    long_convs = [c for c in conversations if c["msg_count"] >= 6]
    random.shuffle(long_convs)

    cases = []
    seen_leads = set()

    for conv in long_convs:
        if len(cases) >= n:
            break
        if conv["lead_username"] in seen_leads:
            continue

        turns = conv["turns"]

        # Find a good user→bot pair that has at least 3 turns of context before it
        for i in range(len(turns) - 1, 4, -1):
            if turns[i]["role"] == "assistant" and turns[i - 1]["role"] == "user":
                user_msg = turns[i - 1]["content"]
                bot_msg = turns[i]["content"]

                if user_msg in ("[sticker]", "[Media/Attachment]", "[media]"):
                    continue
                if bot_msg in ("[sticker]", "[Media/Attachment]", "[media]"):
                    continue
                if len(user_msg.strip()) < 2 or len(bot_msg.strip()) < 2:
                    continue

                # Take 3-5 context turns before the user message
                context_start = max(0, i - 1 - 5)  # up to 5 context turns
                context_end = i - 1  # before the target user message
                context_turns = []
                for j in range(context_start, context_end):
                    t = turns[j]
                    if t["content"] not in ("[sticker]", "[Media/Attachment]"):
                        context_turns.append({
                            "role": t["role"],
                            "content": t["content"],
                        })

                if len(context_turns) < 3:
                    continue

                cat = _classify_message(user_msg, turns[i - 1].get("intent"))
                lang = _detect_language(user_msg)

                cases.append({
                    "test_input": user_msg,
                    "ground_truth": bot_msg,
                    "category": cat,
                    "language": lang,
                    "platform": conv["platform"],
                    "lead_username": conv["lead_username"],
                    "turns": context_turns[-5:],  # max 5 context turns
                    "msg_count": len(context_turns[-5:]),
                    "is_multi_turn": True,
                    "source_msg_id": turns[i - 1].get("msg_id", ""),
                })
                seen_leads.add(conv["lead_username"])
                break

    print(f"\nMulti-turn cases: {len(cases)} extracted")
    for c in cases:
        print(f"  [{c['category']}/{c['language']}] {c['msg_count']} ctx turns | "
              f"{c['test_input'][:60]!r}")

    return cases


def main():
    parser = argparse.ArgumentParser(description="Build stratified test set v2")
    parser.add_argument("--creator", default="iris_bertran")
    parser.add_argument("--n-single", type=int, default=40,
                        help="Number of single-turn test cases")
    parser.add_argument("--n-multi", type=int, default=10,
                        help="Number of multi-turn test cases")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    creator = args.creator

    print(f"{'='*72}")
    print(f"BUILD STRATIFIED TEST SET v2 — {creator}")
    print(f"{'='*72}")

    # Step 1: Get real distribution from DB
    print("\n--- QUERYING REAL DISTRIBUTION ---")
    real_dist = get_real_distribution(creator)

    # Step 2: Get language distribution
    print("\n--- QUERYING LANGUAGE DISTRIBUTION ---")
    lang_dist = get_language_distribution(creator)
    total_lang = sum(lang_dist.values())
    print(f"Language distribution ({total_lang} user messages):")
    for lang, cnt in sorted(lang_dist.items(), key=lambda x: -x[1])[:10]:
        print(f"  {lang:<10} {cnt:>5}  ({cnt/total_lang*100:>5.1f}%)")

    # Step 3: Extract all conversations
    print("\n--- EXTRACTING CONVERSATIONS ---")
    all_convs = extract_conversations(creator, min_turns=2)
    print(f"Total conversations with 3+ messages: {len(all_convs)}")

    # Step 4: Build single-turn cases (stratified)
    print("\n--- BUILDING SINGLE-TURN CASES ---")
    single_turn = build_single_turn_cases(all_convs, real_dist, n=args.n_single)

    # Step 5: Build multi-turn cases
    print("\n--- BUILDING MULTI-TURN CASES ---")
    multi_turn = build_multi_turn_cases(all_convs, n=args.n_multi)

    # Step 6: Combine and assign IDs
    all_cases = []
    for i, case in enumerate(single_turn, 1):
        case["id"] = f"cpe_{creator[:5]}_{i:03d}"
        case["is_multi_turn"] = False
        all_cases.append(case)

    for i, case in enumerate(multi_turn, len(single_turn) + 1):
        case["id"] = f"cpe_{creator[:5]}_{i:03d}_mt"
        all_cases.append(case)

    # Category distribution
    cat_dist = Counter(c["category"] for c in all_cases)
    lang_dist_out = Counter(c["language"] for c in all_cases)
    mt_count = sum(1 for c in all_cases if c.get("is_multi_turn"))

    test_set = {
        "metadata": {
            "creator": creator,
            "version": "v2_stratified",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_cases": len(all_cases),
            "n_single_turn": len(single_turn),
            "n_multi_turn": mt_count,
            "category_distribution": dict(cat_dist),
            "language_distribution": dict(lang_dist_out),
            "real_distribution_source": "DB query — last 3 months",
            "generator": "build_stratified_test_set.py",
            "seed": args.seed,
        },
        "conversations": all_cases,
    }

    out_dir = REPO_ROOT / "tests" / "cpe_data" / creator
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "test_set_v2_stratified.json"
    out_path.write_text(json.dumps(test_set, indent=2, ensure_ascii=False))

    print(f"\n{'='*72}")
    print(f"SAVED: {out_path}")
    print(f"Total: {len(all_cases)} cases ({len(single_turn)} single + {mt_count} multi-turn)")
    print(f"\nCategory distribution:")
    for cat, cnt in sorted(cat_dist.items(), key=lambda x: -x[1]):
        print(f"  {cat:<20} {cnt:>3}")
    print(f"\nLanguage distribution:")
    for lang, cnt in sorted(lang_dist_out.items(), key=lambda x: -x[1]):
        print(f"  {lang:<10} {cnt:>3}")
    print(f"{'='*72}")


if __name__ == "__main__":
    main()
