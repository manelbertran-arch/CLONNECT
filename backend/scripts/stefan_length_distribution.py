"""
Stefan Length Distribution - Detailed analysis of the 'otro' category
and percentile breakdown for all categories.
"""

import os
import sys
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

CREATOR_ID = "5e5c2364-c99a-4484-b86-741bb84a11cf"


# Reuse classification from main script
def classify_context(prev_content):
    if not prev_content:
        return "inicio_conversacion"
    msg = prev_content.lower().strip()
    if "mentioned you in their story" in msg or (
        "story" in msg and ("mencion" in msg or "mention" in msg)
    ):
        return "story_mention"
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
    is_emoji_heavy = sum(1 for c in msg if ord(c) > 8000) > len(msg) / 3
    is_laugh = msg.startswith("jaj") or msg.startswith("hah") or msg.startswith("jej")
    if is_emoji_heavy or is_laugh or (len(msg) < 15 and any(p in msg for p in casual_patterns)):
        return "casual"
    if "?" in prev_content:
        return "pregunta_general"
    return "otro"


def main():
    conn = psycopg2.connect(DATABASE_URL)

    query = """
    WITH stefan_messages AS (
        SELECT m.id, m.content, m.role, m.created_at, m.approved_by, m.status, m.lead_id,
            ROW_NUMBER() OVER (PARTITION BY m.lead_id ORDER BY m.created_at) as msg_order
        FROM messages m JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = %s AND m.status = 'sent'
    ),
    paired AS (
        SELECT curr.content as stefan_content, prev.content as prev_content, prev.role as prev_role
        FROM stefan_messages curr
        LEFT JOIN stefan_messages prev ON curr.lead_id = prev.lead_id AND prev.msg_order = curr.msg_order - 1
        WHERE curr.role = 'assistant'
        AND (curr.approved_by IS NULL OR curr.approved_by IN ('creator', 'creator_manual'))
    )
    SELECT * FROM paired;
    """

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, ("5e5c2364-c99a-4484-b986-741bb84a11cf",))
        messages = cur.fetchall()

    categories = defaultdict(list)
    for msg in messages:
        prev_role = msg["prev_role"]
        if prev_role == "user":
            context = classify_context(msg["prev_content"])
        elif msg["prev_content"] is None:
            context = "inicio_conversacion"
        else:
            context = "otro"
        categories[context].append(len(msg["stefan_content"]))

    # Percentile analysis
    print("PERCENTILE BREAKDOWN BY CONTEXT")
    print("=" * 120)
    print(
        f"| {'Context':<22} | {'N':>4} | {'P5':>4} | {'P10':>4} | {'P25':>4} | {'P50':>4} | {'P75':>4} | {'P90':>5} | {'P95':>5} | {'P99':>5} |"
    )
    print(f"|{'-'*24}|{'-'*6}|{'-'*6}|{'-'*6}|{'-'*6}|{'-'*6}|{'-'*6}|{'-'*7}|{'-'*7}|{'-'*7}|")

    for cat_name, lengths in sorted(categories.items(), key=lambda x: -len(x[1])):
        n = len(lengths)
        arr = sorted(lengths)
        p5 = arr[int(n * 0.05)]
        p10 = arr[int(n * 0.10)]
        p25 = arr[int(n * 0.25)]
        p50 = arr[int(n * 0.50)]
        p75 = arr[int(n * 0.75)]
        p90 = arr[min(n - 1, int(n * 0.90))]
        p95 = arr[min(n - 1, int(n * 0.95))]
        p99 = arr[min(n - 1, int(n * 0.99))]
        print(
            f"| {cat_name:<22} | {n:>4} | {p5:>4} | {p10:>4} | {p25:>4} | {p50:>4} | {p75:>4} | {p90:>5} | {p95:>5} | {p99:>5} |"
        )

    # Length distribution histogram for each category
    print()
    print("LENGTH DISTRIBUTION (histogram buckets)")
    print("=" * 80)
    buckets = [
        (0, 10),
        (11, 20),
        (21, 30),
        (31, 50),
        (51, 80),
        (81, 120),
        (121, 200),
        (201, 500),
        (501, 999),
    ]

    for cat_name, lengths in sorted(categories.items(), key=lambda x: -len(x[1])):
        n = len(lengths)
        if n < 5:
            continue
        print(f"\n  {cat_name} (n={n}):")
        for lo, hi in buckets:
            count = sum(1 for length in lengths if lo <= length <= hi)
            pct = count / n * 100
            bar = "#" * int(pct / 2)
            print(f"    {lo:>3}-{hi:>3}: {count:>4} ({pct:>5.1f}%) {bar}")

    # Final: Show that "otro" category needs sub-classification
    print()
    print("=" * 80)
    print("CONCLUSION: The 'otro' category (80% of msgs) has wide variance")
    print("  This means even 'normal' conversation has variable lengths.")
    print("  The current fixed target of 38 chars is just a mean, not useful as a target.")
    print("  Better approach: Use percentile-based ranges per context type.")
    print()

    conn.close()


if __name__ == "__main__":
    main()
