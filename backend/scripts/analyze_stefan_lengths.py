"""
Analyze Stefan's real message lengths by conversation context.
Connects to PostgreSQL, classifies each message by the lead's prior message,
and produces statistics per context category.
"""

import json
import os
import re
import statistics
import sys

import sqlalchemy as sa

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

engine = sa.create_engine(DATABASE_URL)

# ──────────────────────────────────────────────
# STEP 1: Extract all conversations with Stefan's messages
# ──────────────────────────────────────────────

print("=" * 70)
print("STEP 1: Extracting messages from PostgreSQL")
print("=" * 70)

query = sa.text("""
    SELECT
        m.id,
        m.lead_id,
        m.role,
        m.content,
        m.status,
        m.approved_by,
        m.created_at,
        l.platform_user_id,
        l.full_name as lead_name
    FROM messages m
    JOIN leads l ON m.lead_id = l.id
    WHERE l.creator_id = '5e5c2364-c99a-4484-b986-741bb84a11cf'
    AND m.content IS NOT NULL
    AND m.content != ''
    ORDER BY m.lead_id, m.created_at ASC
""")

with engine.connect() as conn:
    rows = conn.execute(query).fetchall()

print(f"Total rows fetched: {len(rows)}")

# ──────────────────────────────────────────────
# STEP 2: Build conversation pairs (lead_msg → stefan_reply)
# ──────────────────────────────────────────────

print("\n" + "=" * 70)
print("STEP 2: Building conversation pairs")
print("=" * 70)

# Group messages by lead_id
from collections import defaultdict

conversations = defaultdict(list)
for row in rows:
    conversations[row.lead_id].append({
        "role": row.role,
        "content": row.content,
        "status": row.status or "",
        "approved_by": row.approved_by or "",
    })

# Build pairs: (lead_message, stefan_reply)
pairs = []
for lead_id, msgs in conversations.items():
    for i in range(1, len(msgs)):
        current = msgs[i]
        previous = msgs[i - 1]

        # Current must be Stefan's human message
        if current["role"] != "assistant":
            continue
        if current["status"] != "sent":
            continue
        # approved_by=NULL or creator/creator_manual = human Stefan
        if current["approved_by"] not in ("", "creator", "creator_manual"):
            continue

        # Previous must be from the lead
        if previous["role"] != "user":
            continue

        pairs.append({
            "lead_msg": previous["content"],
            "stefan_msg": current["content"],
            "stefan_len": len(current["content"]),
        })

print(f"Conversation pairs (lead→stefan): {len(pairs)}")

# ──────────────────────────────────────────────
# STEP 3: Classify each pair by context
# ──────────────────────────────────────────────

print("\n" + "=" * 70)
print("STEP 3: Classifying by context")
print("=" * 70)


def classify_lead_message(msg: str) -> str:
    """Classify lead message into context category."""
    m = msg.lower().strip()

    # Greeting
    greetings = ["hola", "hey", "buenas", "buenos", "ey", "hi", "hello",
                 "que tal", "qué tal", "buen dia", "buen día"]
    if any(g in m for g in greetings) and len(m) < 40:
        return "saludo"

    # Price question
    price = ["cuánto", "cuanto", "precio", "cuesta", "vale", "cost",
             "tarifa", "inversión", "inversion", "pagar", "cobr"]
    if any(p in m for p in price):
        return "pregunta_precio"

    # Product question
    product = ["qué incluye", "que incluye", "cómo funciona", "como funciona",
               "qué es", "que es", "en qué consiste", "en que consiste",
               "qué ofreces", "que ofreces", "de qué trata", "de que trata",
               "qué haces", "que haces", "a qué te dedicas", "programa",
               "servicio", "sesión", "sesion", "coaching", "hipnosis",
               "círculo", "circulo"]
    if any(p in m for p in product):
        return "pregunta_producto"

    # Objection
    objection = ["caro", "no puedo", "no sé si", "no se si", "duda",
                 "no estoy segur", "no me convence", "no creo", "mucho dinero",
                 "no tengo", "difícil", "dificil", "complicado", "pero"]
    if any(o in m for o in objection) and len(m) > 10:
        return "objecion"

    # Interest
    interest = ["me interesa", "quiero", "necesito", "me gustaría",
                "me gustaria", "dónde me apunto", "donde me apunto",
                "cómo puedo", "como puedo", "inscri", "apuntar",
                "reserv", "agenda"]
    if any(i in m for i in interest):
        return "interes"

    # Thanks / confirmation
    thanks = ["gracias", "genial", "perfecto", "ok", "vale", "dale",
              "bueno", "excelente", "increíble", "increible", "guay",
              "super", "súper", "crack", "grande", "máquina", "maquina",
              "top", "fenomenal", "brutal"]
    m_stripped = m.rstrip("!").rstrip(".").rstrip("😊").strip()
    if m_stripped in thanks or any(t in m for t in ["gracias", "muchas gracias"]):
        return "agradecimiento"

    # Casual / informal
    casual_indicators = 0
    if re.search(r"jaj|hah|jej|😂|🤣", m):
        casual_indicators += 1
    if len(m) < 15:
        casual_indicators += 1
    # Emoji-heavy
    emoji_count = len(re.findall(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ufe00-\ufe0f]", m))
    if emoji_count >= 2:
        casual_indicators += 1
    if casual_indicators >= 2 or (len(m) < 8 and emoji_count >= 1):
        return "casual"

    # Question (generic)
    if "?" in m:
        return "pregunta_general"

    # Emotional / personal story (long messages)
    emotional = ["triste", "feliz", "emocion", "llorar", "lloro", "ansiedad",
                 "depres", "sufr", "dolor", "miedo", "preocup", "angustia",
                 "soledad", "solo", "sola", "mal", "crisis"]
    if any(e in m for e in emotional) and len(m) > 20:
        return "emocional"

    # Personal story (long messages from lead)
    if len(m) > 100:
        return "historia_personal"

    return "otro"


# Classify all pairs
for pair in pairs:
    pair["context"] = classify_lead_message(pair["lead_msg"])

# Count
context_counts = defaultdict(int)
for pair in pairs:
    context_counts[pair["context"]] += 1

print("\nContext distribution:")
for ctx, count in sorted(context_counts.items(), key=lambda x: -x[1]):
    print(f"  {ctx:20s}: {count:4d} ({100*count/len(pairs):.1f}%)")

# ──────────────────────────────────────────────
# STEP 4: Statistics per category
# ──────────────────────────────────────────────

print("\n" + "=" * 70)
print("STEP 4: Statistics per context category")
print("=" * 70)

results = {}
for ctx in sorted(context_counts.keys()):
    lengths = [p["stefan_len"] for p in pairs if p["context"] == ctx]
    has_emoji = sum(1 for p in pairs if p["context"] == ctx
                    and re.search(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]", p["stefan_msg"]))
    has_question = sum(1 for p in pairs if p["context"] == ctx
                       and "?" in p["stefan_msg"])

    avg = statistics.mean(lengths)
    med = statistics.median(lengths)
    mn = min(lengths)
    mx = max(lengths)
    std = statistics.stdev(lengths) if len(lengths) > 1 else 0
    p25 = sorted(lengths)[len(lengths) // 4] if len(lengths) > 3 else mn
    p75 = sorted(lengths)[3 * len(lengths) // 4] if len(lengths) > 3 else mx

    results[ctx] = {
        "n": len(lengths),
        "avg": round(avg, 1),
        "median": round(med, 1),
        "min": mn,
        "max": mx,
        "std": round(std, 1),
        "p25": p25,
        "p75": p75,
        "pct_emoji": round(100 * has_emoji / len(lengths), 1),
        "pct_question": round(100 * has_question / len(lengths), 1),
    }

# Print table
print(f"\n{'Context':<20s} {'N':>5s} {'Avg':>6s} {'Med':>6s} {'Min':>5s} {'Max':>5s} "
      f"{'StdDev':>7s} {'P25':>5s} {'P75':>5s} {'%Emoji':>7s} {'%Quest':>7s}")
print("-" * 95)
for ctx in sorted(results.keys(), key=lambda x: -results[x]["n"]):
    r = results[ctx]
    print(f"{ctx:<20s} {r['n']:5d} {r['avg']:6.1f} {r['median']:6.1f} {r['min']:5d} "
          f"{r['max']:5d} {r['std']:7.1f} {r['p25']:5d} {r['p75']:5d} "
          f"{r['pct_emoji']:6.1f}% {r['pct_question']:6.1f}%")

# ──────────────────────────────────────────────
# STEP 5: Show examples per category
# ──────────────────────────────────────────────

print("\n" + "=" * 70)
print("STEP 5: Example messages per category")
print("=" * 70)

for ctx in sorted(results.keys(), key=lambda x: -results[x]["n"]):
    ctx_pairs = [p for p in pairs if p["context"] == ctx]
    print(f"\n--- {ctx.upper()} (n={results[ctx]['n']}, avg={results[ctx]['avg']} chars) ---")

    # Show shortest, median, and longest
    ctx_pairs_sorted = sorted(ctx_pairs, key=lambda x: x["stefan_len"])

    examples = []
    if len(ctx_pairs_sorted) >= 3:
        examples.append(("SHORTEST", ctx_pairs_sorted[0]))
        examples.append(("MEDIAN", ctx_pairs_sorted[len(ctx_pairs_sorted) // 2]))
        examples.append(("LONGEST", ctx_pairs_sorted[-1]))
    else:
        for i, p in enumerate(ctx_pairs_sorted):
            examples.append((f"MSG {i+1}", p))

    for label, p in examples:
        lead_preview = p["lead_msg"][:60].replace("\n", " ")
        stefan_preview = p["stefan_msg"][:80].replace("\n", " ")
        print(f"  [{label}] Lead: \"{lead_preview}...\"")
        print(f"           Stefan ({p['stefan_len']} chars): \"{stefan_preview}...\"")

# ──────────────────────────────────────────────
# STEP 6: Generate dynamic length rules
# ──────────────────────────────────────────────

print("\n" + "=" * 70)
print("STEP 6: Dynamic length rules (based on real data)")
print("=" * 70)

print("\nLENGTH_RULES_BY_CONTEXT = {")
for ctx in sorted(results.keys(), key=lambda x: -results[x]["n"]):
    r = results[ctx]
    # Use P25 as soft_min and P75 as soft_max (middle 50% of real data)
    # Target = median
    print(f'    "{ctx}": {{"target": {int(r["median"])}, "soft_min": {r["p25"]}, '
          f'"soft_max": {r["p75"]}, "hard_max": {r["max"]}, "n": {r["n"]}}},')
print("}")

# ──────────────────────────────────────────────
# STEP 7: Save raw data as JSON
# ──────────────────────────────────────────────

output = {
    "total_pairs": len(pairs),
    "stats_by_context": results,
    "rules": {},
}
for ctx, r in results.items():
    output["rules"][ctx] = {
        "target": int(r["median"]),
        "soft_min": r["p25"],
        "soft_max": r["p75"],
        "hard_max": r["max"],
    }

output_path = os.path.join(os.path.dirname(__file__), "..", "data", "writing_patterns",
                           "stefan_length_by_context.json")
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\nData saved to: {output_path}")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
