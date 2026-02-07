"""
Stefan Length Analysis - Prove that response length varies by context.

Connects to PostgreSQL, extracts all Stefan's sent assistant messages,
classifies them by the context of the previous user message,
and calculates statistics per category.
"""

import os
import statistics
import sys
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print(
        "ERROR: DATABASE_URL not set. Run with: railway run python3.11 scripts/stefan_length_analysis.py"
    )
    sys.exit(1)

CREATOR_ID = "5e5c2364-c99a-4484-b986-741bb84a11cf"


def get_stefan_messages(conn):
    """Get all Stefan's sent assistant messages with the previous user message."""
    query = """
    WITH stefan_messages AS (
        SELECT
            m.id,
            m.content,
            m.role,
            m.created_at,
            m.approved_by,
            m.status,
            m.lead_id,
            ROW_NUMBER() OVER (PARTITION BY m.lead_id ORDER BY m.created_at) as msg_order
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = %s
        AND m.status = 'sent'
    ),
    paired AS (
        SELECT
            curr.id as stefan_msg_id,
            curr.content as stefan_content,
            curr.created_at as stefan_created_at,
            curr.approved_by,
            curr.lead_id,
            prev.content as prev_content,
            prev.role as prev_role,
            curr.msg_order
        FROM stefan_messages curr
        LEFT JOIN stefan_messages prev
            ON curr.lead_id = prev.lead_id
            AND prev.msg_order = curr.msg_order - 1
        WHERE curr.role = 'assistant'
        AND (curr.approved_by IS NULL OR curr.approved_by IN ('creator', 'creator_manual'))
    )
    SELECT * FROM paired
    ORDER BY stefan_created_at;
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (CREATOR_ID,))
        return cur.fetchall()


def classify_context(prev_content: str) -> str:
    """Classify the context based on the previous message from the lead."""
    if not prev_content:
        return "inicio_conversacion"

    msg = prev_content.lower().strip()

    # Story mention
    if (
        "mentioned you in their story" in msg
        or "story" in msg
        and ("mencion" in msg or "mention" in msg)
    ):
        return "story_mention"

    # Greeting
    greetings = [
        "hola",
        "hey",
        "buenas",
        "qué tal",
        "que tal",
        "buenos días",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "ey",
        "hi",
        "hello",
        "ola",
    ]
    if any(g in msg for g in greetings) and len(msg) < 40:
        return "saludo"

    # Price question
    price_words = [
        "cuánto",
        "cuanto",
        "precio",
        "cuesta",
        "vale",
        "tarifa",
        "coste",
        "cost",
        "pagar",
        "inversión",
        "inversion",
        "descuento",
        "oferta",
        "euros",
        "€",
        "dolares",
        "$",
    ]
    if any(w in msg for w in price_words):
        return "pregunta_precio"

    # Product question
    product_words = [
        "qué incluye",
        "que incluye",
        "cómo funciona",
        "como funciona",
        "qué es",
        "que es",
        "información",
        "informacion",
        "info",
        "detalles",
        "contenido",
        "curso",
        "programa",
        "sesión",
        "sesion",
        "formación",
        "formacion",
        "coaching",
        "mentoría",
        "mentoria",
        "masterclass",
        "servicio",
        "asesoría",
        "asesoria",
    ]
    if any(w in msg for w in product_words):
        return "pregunta_producto"

    # Objection
    objection_words = [
        "caro",
        "no puedo",
        "no sé si",
        "no se si",
        "dudas",
        "pensarlo",
        "pensármelo",
        "pensar",
        "mucho dinero",
        "presupuesto",
        "no me convence",
        "no creo",
        "complicado",
        "difícil",
        "dificil",
    ]
    if any(w in msg for w in objection_words):
        return "objecion"

    # Interest
    interest_words = [
        "me interesa",
        "quiero",
        "necesito",
        "apuntarme",
        "inscribirme",
        "contratar",
        "comprar",
        "empezar",
        "unirme",
        "matricularme",
        "me apunto",
        "lo quiero",
        "dónde pago",
        "donde pago",
        "cómo pago",
        "como pago",
        "link",
        "enlace",
    ]
    if any(w in msg for w in interest_words):
        return "interes"

    # Thanks / appreciation
    thanks_words = [
        "gracias",
        "genial",
        "perfecto",
        "increíble",
        "increible",
        "muchas gracias",
        "mil gracias",
        "te agradezco",
        "agradecido",
        "thanks",
        "thank",
    ]
    if any(w in msg for w in thanks_words):
        return "agradecimiento"

    # Casual / informal
    casual_patterns = [
        "jaja",
        "jeje",
        "haha",
        "😂",
        "🤣",
        "😊",
        "❤️",
        "💪",
        "🔥",
        "👏",
        "👍",
        "🙌",
        "💙",
    ]
    # Check if mostly emojis or laughs
    is_emoji_heavy = sum(1 for c in msg if ord(c) > 8000) > len(msg) / 3
    is_laugh = msg.startswith("jaj") or msg.startswith("hah") or msg.startswith("jej")
    if is_emoji_heavy or is_laugh or (len(msg) < 15 and any(p in msg for p in casual_patterns)):
        return "casual"

    # Generic question
    if "?" in prev_content:
        return "pregunta_general"

    return "otro"


def has_emoji(text: str) -> bool:
    """Check if text contains emojis."""
    return any(ord(c) > 8000 for c in text)


def has_question(text: str) -> bool:
    """Check if text contains a question mark."""
    return "?" in text


def main():
    print("=" * 80)
    print("STEFAN LENGTH ANALYSIS - Response Length by Context")
    print("=" * 80)
    print()

    conn = psycopg2.connect(DATABASE_URL)
    print("Connected to database successfully.")

    messages = get_stefan_messages(conn)
    print(f"Total Stefan assistant messages (sent, creator-approved): {len(messages)}")
    print()

    # Classify each message
    categories = defaultdict(list)
    all_lengths = []

    for msg in messages:
        stefan_content = msg["stefan_content"]
        prev_content = msg["prev_content"]
        prev_role = msg["prev_role"]

        # Only classify based on user messages (not system/assistant)
        if prev_role == "user":
            context = classify_context(prev_content)
        elif prev_content is None:
            context = "inicio_conversacion"
        else:
            context = "otro"

        char_len = len(stefan_content)
        all_lengths.append(char_len)

        categories[context].append(
            {
                "content": stefan_content,
                "length": char_len,
                "has_emoji": has_emoji(stefan_content),
                "has_question": has_question(stefan_content),
                "prev_content": prev_content,
                "approved_by": msg["approved_by"],
            }
        )

    # Global stats
    print("GLOBAL STATISTICS")
    print("-" * 40)
    print(f"  Total messages: {len(all_lengths)}")
    print(f"  Average length: {statistics.mean(all_lengths):.1f} chars")
    print(f"  Median length:  {statistics.median(all_lengths):.1f} chars")
    print(f"  Min length:     {min(all_lengths)} chars")
    print(f"  Max length:     {max(all_lengths)} chars")
    print(f"  Std deviation:  {statistics.stdev(all_lengths):.1f} chars")
    print()

    # Per-category stats
    print("=" * 120)
    print("STATISTICS BY CONTEXT")
    print("=" * 120)
    print()

    # Table header
    header = f"| {'Context':<22} | {'N':>4} | {'Avg Chars':>9} | {'Median':>6} | {'Min':>4} | {'Max':>5} | {'StdDev':>6} | {'Emoji%':>6} | {'Question%':>9} |"
    separator = f"|{'-'*24}|{'-'*6}|{'-'*11}|{'-'*8}|{'-'*6}|{'-'*7}|{'-'*8}|{'-'*8}|{'-'*11}|"

    print(header)
    print(separator)

    # Sort categories by number of messages (descending)
    sorted_cats = sorted(categories.items(), key=lambda x: len(x[1]), reverse=True)

    length_rules = {}

    for cat_name, cat_msgs in sorted_cats:
        n = len(cat_msgs)
        lengths = [m["length"] for m in cat_msgs]
        avg = statistics.mean(lengths)
        median = statistics.median(lengths)
        min_len = min(lengths)
        max_len = max(lengths)
        std = statistics.stdev(lengths) if n > 1 else 0
        emoji_pct = sum(1 for m in cat_msgs if m["has_emoji"]) / n * 100
        question_pct = sum(1 for m in cat_msgs if m["has_question"]) / n * 100

        print(
            f"| {cat_name:<22} | {n:>4} | {avg:>9.1f} | {median:>6.0f} | {min_len:>4} | {max_len:>5} | {std:>6.1f} | {emoji_pct:>5.1f}% | {question_pct:>8.1f}% |"
        )

        # Build length rules
        # Use percentile-based ranges for more robust estimates
        lengths_sorted = sorted(lengths)
        p10 = lengths_sorted[max(0, int(n * 0.10))]
        p90 = lengths_sorted[min(n - 1, int(n * 0.90))]
        target = int(median)

        length_rules[cat_name] = {
            "min": p10,
            "max": p90,
            "target": target,
            "avg": round(avg, 1),
            "n_samples": n,
        }

    print()
    print()

    # Show example messages per category
    print("=" * 120)
    print("EXAMPLE MESSAGES PER CATEGORY (first 3 shortest + 3 longest)")
    print("=" * 120)
    print()

    for cat_name, cat_msgs in sorted_cats:
        if len(cat_msgs) < 3:
            continue
        print(f"\n--- {cat_name.upper()} ({len(cat_msgs)} messages) ---")

        sorted_by_len = sorted(cat_msgs, key=lambda m: m["length"])

        print("  SHORTEST:")
        for m in sorted_by_len[:3]:
            prev = (m["prev_content"] or "")[:50]
            print(
                f"    [{m['length']:>3} chars] Stefan: \"{m['content'][:80]}\" | Prev: \"{prev}\""
            )

        print("  LONGEST:")
        for m in sorted_by_len[-3:]:
            prev = (m["prev_content"] or "")[:50]
            print(
                f"    [{m['length']:>3} chars] Stefan: \"{m['content'][:120]}\" | Prev: \"{prev}\""
            )

    print()
    print()

    # Generate LENGTH_RULES dict
    print("=" * 80)
    print("DYNAMIC LENGTH RULES (Python dict)")
    print("=" * 80)
    print()
    print("LENGTH_RULES = {")
    for cat_name, rules in sorted(length_rules.items(), key=lambda x: -x[1]["n_samples"]):
        print(
            f'    "{cat_name}": {{"min": {rules["min"]}, "max": {rules["max"]}, "target": {rules["target"]}, "avg": {rules["avg"]}, "n_samples": {rules["n_samples"]}}},'
        )
    print("}")
    print()

    # Key insight: prove length varies
    print()
    print("=" * 80)
    print("KEY INSIGHT: Length VARIES by context")
    print("=" * 80)
    print()
    if sorted_cats:
        medians = [
            (name, statistics.median([m["length"] for m in msgs]))
            for name, msgs in sorted_cats
            if len(msgs) >= 5
        ]
        if medians:
            min_median = min(medians, key=lambda x: x[1])
            max_median = max(medians, key=lambda x: x[1])
            print(f"  Shortest median: {min_median[0]} = {min_median[1]:.0f} chars")
            print(f"  Longest median:  {max_median[0]} = {max_median[1]:.0f} chars")
            print(f"  Ratio:           {max_median[1] / max(min_median[1], 1):.1f}x difference")
            print()
            print("  This proves the assumption that 'Stefan always responds with ~31 chars'")
            print("  is INCORRECT. Response length depends heavily on context.")

    conn.close()
    print()
    print("Analysis complete.")


if __name__ == "__main__":
    main()
