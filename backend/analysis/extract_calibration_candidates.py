"""
Read-only script: Extract Iris's best manual responses for calibration file.
Two-pass approach: 1) get manual assistant msgs, 2) batch-fetch preceding user msgs.

Usage: export DATABASE_URL=... && python3 analysis/extract_calibration_candidates.py
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

# ── DB connection ──────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
if DATABASE_URL and "sslmode" not in DATABASE_URL:
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL = f"{DATABASE_URL}{sep}sslmode=require"

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 30})

print("Connecting to DB...")
with engine.connect() as conn:
    row = conn.execute(text("SELECT id FROM creators WHERE name = 'iris_bertran'")).fetchone()
    if not row:
        print("ERROR: Creator 'iris_bertran' not found")
        sys.exit(1)
    creator_uuid = str(row[0])
    print(f"Creator UUID: {creator_uuid}")

three_months_ago = datetime.now(timezone.utc) - timedelta(days=90)

# ── Step 1: copilot_action stats ───────────────────────────────────
print("\nChecking copilot_action distribution...")
with engine.connect() as conn:
    stats = conn.execute(text("""
        SELECT m.copilot_action, m.status, count(*)
        FROM messages m JOIN leads l ON l.id = m.lead_id
        WHERE l.creator_id = :cid AND m.role = 'assistant' AND m.created_at >= :since
        GROUP BY m.copilot_action, m.status ORDER BY count(*) DESC
    """), {"cid": creator_uuid, "since": three_months_ago}).fetchall()
    for s in stats:
        print(f"  copilot_action={s[0]}, status={s[1]}: {s[2]}")

# ── Step 2: Get manual assistant messages (LIMIT 300) ──────────────
print("\nFetching manual assistant messages...")
with engine.connect() as conn:
    assistant_rows = conn.execute(text("""
        SELECT m.id, m.lead_id, m.content, m.copilot_action, m.created_at,
               m.msg_metadata, m.intent,
               l.username, l.full_name, l.platform
        FROM messages m
        JOIN leads l ON l.id = m.lead_id
        WHERE l.creator_id = :cid
          AND m.role = 'assistant'
          AND m.created_at >= :since
          AND m.deleted_at IS NULL
          AND m.content IS NOT NULL
          AND length(m.content) > 10
          AND (m.copilot_action IS NULL OR m.copilot_action = 'manual_override')
        ORDER BY m.created_at DESC
        LIMIT 300
    """), {"cid": creator_uuid, "since": three_months_ago}).fetchall()

print(f"Manual assistant messages: {len(assistant_rows)}")
if not assistant_rows:
    print("No manual responses found!")
    sys.exit(0)

# ── Step 3: For each, get the preceding user message ───────────────
# Batch by lead_id to reduce queries
from collections import defaultdict

by_lead = defaultdict(list)
for r in assistant_rows:
    by_lead[str(r.lead_id)].append(r)

print(f"Unique leads: {len(by_lead)}")
print("Fetching preceding user messages per lead...")

pairs = []
batch_num = 0
lead_ids_list = list(by_lead.keys())

# Process in batches of 50 leads
for batch_start in range(0, len(lead_ids_list), 50):
    batch_leads = lead_ids_list[batch_start:batch_start + 50]
    batch_num += 1

    with engine.connect() as conn:
        # Get ALL user messages for these leads in one query
        # Build IN clause with cast to avoid SQLAlchemy :param vs ::cast conflict
        placeholders = ", ".join(f"'{lid}'::uuid" for lid in batch_leads)
        user_msgs_rows = conn.execute(text(f"""
            SELECT m.lead_id, m.content, m.created_at, m.msg_metadata
            FROM messages m
            WHERE m.lead_id IN ({placeholders})
              AND m.role = 'user'
              AND m.created_at >= :since
              AND m.deleted_at IS NULL
              AND m.content IS NOT NULL
              AND length(m.content) > 2
            ORDER BY m.lead_id, m.created_at
        """), {"since": three_months_ago}).fetchall()

    # Index user messages by lead_id
    user_msgs_by_lead = defaultdict(list)
    for um in user_msgs_rows:
        user_msgs_by_lead[str(um.lead_id)].append(um)

    # Pair each assistant message with its preceding user message
    for lid in batch_leads:
        user_msgs = user_msgs_by_lead.get(lid, [])
        for ar in by_lead[lid]:
            # Find the last user message before this assistant message
            prev_user = None
            for um in reversed(user_msgs):
                if um.created_at < ar.created_at:
                    prev_user = um
                    break
            if not prev_user:
                continue

            pairs.append({
                "msg_id": str(ar.id),
                "iris_response": ar.content.strip(),
                "iris_metadata": ar.msg_metadata or {},
                "copilot_action": ar.copilot_action,
                "response_at": ar.created_at,
                "lead_message": prev_user.content.strip(),
                "lead_metadata": prev_user.msg_metadata or {},
                "lead_username": ar.username or "unknown",
                "lead_name": ar.full_name or "",
                "platform": ar.platform,
            })

    if batch_num % 5 == 0:
        print(f"  Processed {batch_start + len(batch_leads)}/{len(lead_ids_list)} leads, {len(pairs)} pairs so far")

print(f"Total paired responses: {len(pairs)}")

# ── Step 4: Classification ──────────────────────────────────────────

def detect_language(text_content: str) -> str:
    catalan_markers = [
        r'\bmolt\b', r'\bbon\s+dia\b', r'\bbona\s+tarda\b',
        r'\bgràcies\b', r'\bperò\b', r'\bamb\b', r'\bdoncs\b',
        r'\baixò\b', r'\baixí\b', r'\bnosaltres\b', r'\bvosaltres\b',
        r'\btambé\b', r'\bperquè\b', r'\bteniu\b', r'\bpodeu\b',
        r'\besteu\b', r'\bfem\b', r'\bvoleu\b',
        r'\bescolta\b', r'\bquè\b', r'\bés\b', r'\bsón\b',
        r'\bnostres\b', r'\bveure\b', r'\bpuc\b', r'\bpots\b',
        r'\bmerci\b', r'\bbé\b',
    ]
    spanish_markers = [
        r'\bgracias\b', r'\bpero\b', r'\bpuedes\b', r'\bnosotros\b',
        r'\btienes\b', r'\bestás\b', r'\bhacemos\b', r'\bquieres\b',
        r'\bmira\b', r'\bdime\b', r'\bbueno\b', r'\bvale\b',
        r'\bclaro\b', r'\bcuánto\b', r'\bprecio\b',
    ]
    text_lower = text_content.lower()
    ca_score = sum(1 for p in catalan_markers if re.search(p, text_lower))
    es_score = sum(1 for p in spanish_markers if re.search(p, text_lower))
    if ca_score > es_score:
        return "ca"
    elif es_score > ca_score:
        return "es"
    return "ca"


def classify_type(lead_msg: str, iris_msg: str, lead_meta, iris_meta) -> str:
    lead_lower = (lead_msg or "").lower()
    iris_lower = iris_msg.lower()
    combined = f"{lead_lower} {iris_lower}"

    lead_type = ""
    if lead_meta and isinstance(lead_meta, dict):
        lead_type = lead_meta.get("type", "") or lead_meta.get("media_type", "") or ""
    if lead_type in ("audio", "voice"):
        return "audio"

    if any(re.search(p, combined) for p in [
        r'preci[os]', r'cuánt[oa]', r'cost[ae]', r'preu', r'quant\s+val',
        r'tarif[as]', r'cobr[ae]s', r'valor', r'pressupost', r'pagar',
        r'descuento', r'descompte', r'€', r'euro', r'inversión', r'inversi[oó]',
        r'rata', r'packs?', r'sesion[es]', r'sesió', r'mensualidad',
    ]):
        return "precio"

    if any(re.search(p, lead_lower) for p in [
        r'no\s+(s[eé]|estoy|creo|puc|tinc)', r'no\s+me\s+(interesa|convence)',
        r'es\s+car[oa]', r'és\s+car', r'no\s+tengo\s+tiempo', r'no\s+tinc\s+temps',
        r'ya\s+(tengo|tinc)', r'no\s+necesit[oa]', r'no\s+necessit',
        r'lo\s+pensaré', r'ho\s+pensaré', r'más\s+adelante', r'més\s+endavant',
        r'dud[ao]', r'dubte', r'no\s+lo\s+veo\s+claro', r'segur[oa]\?',
    ]):
        return "objecion"

    if any(re.search(p, combined) for p in [
        r'quiero\s+(reservar|comprar|empezar|apuntar)',
        r'vull\s+(reservar|comprar|començar|apuntar)',
        r'me\s+apunto', r"m'apunto", r'reserv[ao]', r'cuando\s+empezamos',
        r'quan\s+comencem', r'siguiente\s+paso', r'proper\s+pas',
        r'link\s+de\s+pago', r'formulari', r'formulario',
    ]):
        return "lead_caliente"

    if any(re.search(p, combined) for p in [
        r'com\s+estàs', r'cómo\s+estás', r'què\s+tal', r'qué\s+tal',
        r'bon\s+dia', r'buenos\s+días', r'felicitats', r'felicidades',
        r'aniversari', r'cumpleaños', r'vacaciones', r'vacances',
        r'quedamos', r'quedem', r'abraç', r'abraz',
        r'familia', r'família', r'amig[oa]', r'amic',
        r'et\s+trobo\s+a\s+faltar', r'te\s+echo\s+de\s+menos',
        r'jajaj', r'hahah', r'jejej', r'😂|🤣|❤️|😘|🥰',
    ]):
        return "personal"

    if any(re.search(p, lead_lower) for p in [
        r'^hola\b', r'^hey\b', r'^ei\b', r'^bon\s+dia', r'^buenos',
        r'^buenas', r'^bona\s+tarda', r'primera\s+vez', r'primer\s+cop',
        r'acabo\s+de\s+(seguir|descubri)', r'acab[oa]\s+de\s+seguir',
        r'te\s+sigo\s+desde', r'et\s+segueixo',
    ]):
        return "saludo"

    if any(w in combined for w in ["audio", "nota de voz", "nota de veu", "àudio"]):
        return "audio"

    return "otro"


candidates = []
for p in pairs:
    lead_msg = p["lead_message"]
    iris_msg = p["iris_response"]

    if iris_msg.startswith("http") and len(iris_msg.split()) <= 2:
        continue

    msg_type = classify_type(lead_msg, iris_msg, p["lead_metadata"], p["iris_metadata"])
    lang = detect_language(iris_msg)

    candidates.append({
        "msg_id": p["msg_id"],
        "lead_username": p["lead_username"],
        "lead_name": p["lead_name"],
        "platform": p["platform"],
        "lead_message": lead_msg,
        "iris_response": iris_msg,
        "type": msg_type,
        "language": lang,
        "response_at": p["response_at"].isoformat() if p["response_at"] else None,
        "copilot_action": p["copilot_action"],
        "response_length": len(iris_msg),
        "has_emoji": bool(re.search(r'[\U0001F300-\U0001F9FF]', iris_msg)),
        "has_question": "?" in iris_msg,
        "has_exclamation": "!" in iris_msg,
    })

print(f"Candidates after filtering: {len(candidates)}")

# ── Distribution stats ──────────────────────────────────────────────

type_counts = {}
for c in candidates:
    type_counts[c["type"]] = type_counts.get(c["type"], 0) + 1

print("\n=== TYPE DISTRIBUTION ===")
total = len(candidates)
for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
    pct = count / total * 100 if total else 0
    print(f"  {t:20s}: {count:4d} ({pct:.1f}%)")

lang_counts = {}
for c in candidates:
    lang_counts[c["language"]] = lang_counts.get(c["language"], 0) + 1
print(f"\n=== LANGUAGE ===")
for l, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
    print(f"  {l}: {count}")

# ── Quality scoring ─────────────────────────────────────────────────

def quality_score(c: dict) -> float:
    score = 0.0
    resp = c["iris_response"]
    resp_len = c["response_length"]

    if 20 <= resp_len <= 200:
        score += 3.0
    elif 200 < resp_len <= 400:
        score += 2.0
    elif resp_len > 400:
        score += 0.5

    if c["has_emoji"]:
        score += 1.0
    if c["has_exclamation"]:
        score += 0.5
    if c["has_question"]:
        score += 0.5
    if resp[0].islower():
        score += 0.5

    for pat in [r"jaja", r"haha", r"jeje", r"😊", r"💪", r"🙏", r"❤", r"!!", r"\.\.\."]:
        if re.search(pat, resp):
            score += 0.3

    for pat in [r"Estimad[oa]", r"Atentamente", r"Cordialmente", r"Le informamos"]:
        if re.search(pat, resp):
            score -= 2.0

    for pat in [r"como asistente", r"com a assistent", r"no puedo", r"soy una IA", r"sóc una IA"]:
        if re.search(pat, resp, re.IGNORECASE):
            score -= 5.0

    return score

for c in candidates:
    c["quality_score"] = quality_score(c)

# ── Select top 30 ──────────────────────────────────────────────────

top30 = []
for msg_type in type_counts:
    typed = sorted([c for c in candidates if c["type"] == msg_type], key=lambda x: -x["quality_score"])
    proportion = type_counts[msg_type] / total
    n_take = max(2, round(30 * proportion))
    top30.extend(typed[:n_take])

top30.sort(key=lambda x: -x["quality_score"])
top30 = top30[:30]

print(f"\n=== TOP 30 CANDIDATES ===")
top30_types = {}
for c in top30:
    top30_types[c["type"]] = top30_types.get(c["type"], 0) + 1
for t, count in sorted(top30_types.items(), key=lambda x: -x[1]):
    print(f"  {t:20s}: {count}")

# ── Select final 20 proportionally ──────────────────────────────────

type_slots = {}
for t in top30_types:
    proportion = type_counts[t] / total
    type_slots[t] = max(1, round(20 * proportion))

while sum(type_slots.values()) > 20:
    max_t = max(type_slots, key=lambda t: type_slots[t] - (20 * type_counts[t] / total))
    if type_slots[max_t] > 1:
        type_slots[max_t] -= 1
    else:
        # All types at 1 slot, remove the least represented
        min_t = min(type_slots, key=lambda t: type_counts.get(t, 0))
        del type_slots[min_t]

while sum(type_slots.values()) < 20:
    min_t = min(type_slots, key=lambda t: type_slots[t] - (20 * type_counts[t] / total))
    type_slots[min_t] += 1

print(f"\n=== TARGET SLOTS (20 total) ===")
for t, slots in sorted(type_slots.items(), key=lambda x: -x[1]):
    avail = len([c for c in top30 if c["type"] == t])
    print(f"  {t:20s}: {slots} slots (available: {avail})")

final20 = []
for msg_type, n_slots in type_slots.items():
    typed = sorted([c for c in top30 if c["type"] == msg_type], key=lambda x: -x["quality_score"])
    final20.extend(typed[:n_slots])

if len(final20) < 20:
    used = {c["msg_id"] for c in final20}
    rest = sorted([c for c in top30 if c["msg_id"] not in used], key=lambda x: -x["quality_score"])
    final20.extend(rest[:20 - len(final20)])

final20 = final20[:20]

print(f"\n=== FINAL 20 SELECTION ===")
ft, fl = {}, {}
for c in final20:
    ft[c["type"]] = ft.get(c["type"], 0) + 1
    fl[c["language"]] = fl.get(c["language"], 0) + 1
print("By type:")
for t, n in sorted(ft.items(), key=lambda x: -x[1]):
    print(f"  {t:20s}: {n}")
print("By language:")
for l, n in sorted(fl.items(), key=lambda x: -x[1]):
    print(f"  {l}: {n}")

# ── Save ────────────────────────────────────────────────────────────

output = {
    "metadata": {
        "creator": "iris_bertran",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": f"{three_months_ago.strftime('%Y-%m-%d')} to {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "total_manual_responses": len(candidates),
        "type_distribution_real": type_counts,
        "selection_criteria": "Top 20 most natural manual responses, proportional to real type volume",
    },
    "examples": []
}

for i, c in enumerate(final20, 1):
    output["examples"].append({
        "id": i,
        "type": c["type"],
        "language": c["language"],
        "lead_message": c["lead_message"],
        "iris_response": c["iris_response"],
        "lead_username": c["lead_username"],
        "platform": c["platform"],
        "response_at": c["response_at"],
        "quality_score": round(c["quality_score"], 2),
    })

output_path = os.path.join(os.path.dirname(__file__), "candidate_fewshot_examples.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\nSaved to: {output_path}")
print(f"Total examples: {len(output['examples'])}")

print("\n" + "="*70)
print("FULL PREVIEW OF ALL 20 EXAMPLES")
print("="*70)
for ex in output["examples"]:
    print(f"\n--- #{ex['id']} [{ex['type']}] [{ex['language']}] score={ex['quality_score']} @{ex['lead_username']} ---")
    print(f"  LEAD: {ex['lead_message'][:200]}")
    print(f"  IRIS: {ex['iris_response'][:250]}")
