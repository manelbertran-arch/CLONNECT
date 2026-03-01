"""
Master population script: Phases 2-8
Populates user_profiles, lead_intelligence, lead_activities, product_analytics,
nurturing_sequences, nurturing_followups, conversation_states, post_contexts.

Uses 100% of available data — ALL 259 leads, ALL 6,240 messages.
"""
import os
import time
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
CREATOR_UUID = "5e5c2364-c99a-4484-b986-741bb84a11cf"
CREATOR_STR = "stefano_bonanno"

# Product patterns for matching
PRODUCT_PATTERNS = {
    "fitpack": {
        "id": None,  # Will be loaded from DB
        "patterns": [
            r"fitpack", r"challenge", r"11\s*d[ií]as?", r"11\s*days?",
            r"transformar?\s+(tu|mi)\s+relaci[oó]n", r"movimiento\s+y\s+bienestar",
        ],
    },
    "sintoma_plenitud": {
        "id": None,
        "patterns": [
            r"s[ií]ntoma", r"plenitud", r"del\s+s[ií]ntoma",
        ],
    },
    "respira_siente": {
        "id": None,
        "patterns": [
            r"respira", r"siente\s+y?\s*conecta", r"respiraci[oó]n",
        ],
    },
    "circulo_hombres": {
        "id": None,
        "patterns": [
            r"c[ií]rculo", r"hombres", r"circulo\s+de\s+hombres",
        ],
    },
    "sesion_descubrimiento": {
        "id": None,
        "patterns": [
            r"sesi[oó]n", r"descubrimiento", r"discovery",
            r"llamada", r"consulta\s+gratis",
        ],
    },
}

# Intent/interest patterns
INTEREST_PATTERNS = {
    "fitness": [r"fitness", r"ejercicio", r"entrena", r"gym", r"deporte", r"musculo"],
    "coaching": [r"coaching", r"coach", r"mentor", r"sesi[oó]n", r"acompa[ñn]"],
    "bienestar": [r"bienestar", r"salud", r"energ[ií]a", r"equilibrio", r"medit"],
    "nutricion": [r"nutrici[oó]n", r"dieta", r"comida", r"aliment", r"comer"],
    "respiracion": [r"respira", r"respiraci[oó]n", r"breathwork"],
    "sanacion": [r"sana", r"sanaci[oó]n", r"heal", r"terapia", r"terapeut"],
    "movimiento": [r"movimiento", r"cuerpo", r"yoga", r"flexib"],
    "masculinidad": [r"hombre", r"masculin", r"viril", r"c[ií]rculo"],
}

OBJECTION_PATTERNS = [
    (r"(es\s+)?caro|precio|cost[oa]|no\s+puedo\s+pagar|dinero|plata", "price"),
    (r"no\s+tengo\s+tiempo|ocupado|trabajo\s+mucho|ahora\s+no", "time"),
    (r"no\s+s[eé]\s+si|duda|no\s+estoy\s+segur|pienso|pensar", "doubt"),
    (r"ya\s+prob[eé]|intent[eé]|no\s+funcion|no\s+me\s+sirv", "past_experience"),
    (r"despu[eé]s|m[aá]s\s+adelante|otro\s+momento|cuando\s+pueda", "timing"),
]

CONVERSION_SIGNALS = [
    r"c[oó]mo\s+pago", r"quiero\s+compr", r"me\s+apunto", r"lo\s+quiero",
    r"d[oó]nde\s+pago", r"link\s+de\s+pago", r"comprar", r"adquirir",
    r"ya\s+pagu[eé]", r"transferencia", r"tarjeta", r"paypal",
]


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def load_all_data(conn):
    """Load all messages and leads into memory."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Load all leads
    cur.execute("""
        SELECT id, creator_id, platform_user_id, username, full_name, status,
               score, purchase_intent, first_contact_at, last_contact_at,
               profile_pic_url, email, phone
        FROM leads
        WHERE creator_id = %s
    """, (CREATOR_UUID,))
    leads = {str(r["id"]): dict(r) for r in cur.fetchall()}
    print(f"Loaded {len(leads)} leads")

    # Load all messages
    cur.execute("""
        SELECT m.id, m.lead_id, m.role, m.content, m.created_at, m.intent,
               m.msg_metadata, m.status
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = %s
        ORDER BY m.created_at
    """, (CREATOR_UUID,))
    messages = [dict(r) for r in cur.fetchall()]
    print(f"Loaded {len(messages)} messages")

    # Group messages by lead
    msgs_by_lead = defaultdict(list)
    for m in messages:
        msgs_by_lead[str(m["lead_id"])].append(m)

    # Load products
    cur.execute("""
        SELECT id, name, price FROM products
        WHERE creator_id = %s
    """, (CREATOR_UUID,))
    products = {str(r["id"]): dict(r) for r in cur.fetchall()}
    print(f"Loaded {len(products)} products")

    # Map product names to IDs
    for pid, p in products.items():
        name_lower = p["name"].lower()
        if "fitpack" in name_lower:
            PRODUCT_PATTERNS["fitpack"]["id"] = pid
        elif "sintoma" in name_lower or "síntoma" in name_lower:
            PRODUCT_PATTERNS["sintoma_plenitud"]["id"] = pid
        elif "respira" in name_lower:
            PRODUCT_PATTERNS["respira_siente"]["id"] = pid
        elif "circulo" in name_lower or "círculo" in name_lower:
            PRODUCT_PATTERNS["circulo_hombres"]["id"] = pid
        elif "sesion" in name_lower or "sesión" in name_lower or "descubrimiento" in name_lower:
            PRODUCT_PATTERNS["sesion_descubrimiento"]["id"] = pid

    # Load instagram posts
    cur.execute("""
        SELECT id, caption, post_timestamp, media_type, permalink, likes_count, comments_count
        FROM instagram_posts
        WHERE creator_id = %s
        ORDER BY post_timestamp DESC
    """, (CREATOR_STR,))
    posts = [dict(r) for r in cur.fetchall()]
    print(f"Loaded {len(posts)} Instagram posts")

    return leads, messages, msgs_by_lead, products, posts


def detect_interests(messages_list):
    """Detect interests from user messages."""
    interests = Counter()
    for m in messages_list:
        if m["role"] != "user" or not m["content"]:
            continue
        text = m["content"].lower()
        for interest, patterns in INTEREST_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, text):
                    interests[interest] += 1
                    break
    return dict(interests.most_common(10))


def detect_objections(messages_list):
    """Detect objection types from user messages."""
    objections = []
    for m in messages_list:
        if m["role"] != "user" or not m["content"]:
            continue
        text = m["content"].lower()
        for pat, obj_type in OBJECTION_PATTERNS:
            if re.search(pat, text):
                objections.append({
                    "type": obj_type,
                    "message": m["content"][:100],
                    "date": str(m["created_at"]),
                })
    return objections


def detect_product_interest(messages_list):
    """Detect which products a lead is interested in."""
    interested = {}
    for m in messages_list:
        if not m["content"]:
            continue
        text = m["content"].lower()
        for pkey, pdata in PRODUCT_PATTERNS.items():
            if not pdata["id"]:
                continue
            for pat in pdata["patterns"]:
                if re.search(pat, text):
                    if pdata["id"] not in interested:
                        interested[pdata["id"]] = {
                            "product_key": pkey,
                            "mention_count": 0,
                            "first_mention": str(m["created_at"]),
                        }
                    interested[pdata["id"]]["mention_count"] += 1
                    break
    return interested


def detect_language(messages_list):
    """Detect primary language from user messages."""
    spanish_words = {"hola", "que", "como", "quiero", "tengo", "pero", "para", "por", "con", "una"}
    english_words = {"hello", "what", "how", "want", "have", "but", "for", "with", "the", "and"}
    es_count = 0
    en_count = 0
    for m in messages_list:
        if m["role"] != "user" or not m["content"]:
            continue
        words = set(m["content"].lower().split())
        es_count += len(words & spanish_words)
        en_count += len(words & english_words)
    return "es" if es_count >= en_count else "en"


# ============================================================
# PHASE 2: USER PROFILES
# ============================================================
def phase2_user_profiles(conn, leads, msgs_by_lead):
    print("\n" + "=" * 60)
    print("PHASE 2: USER PROFILES (259 leads)")
    print("=" * 60)
    start = time.time()
    cur = conn.cursor()

    # Check existing
    cur.execute("SELECT user_id FROM user_profiles WHERE creator_id = %s", (CREATOR_STR,))
    existing = {r[0] for r in cur.fetchall()}
    print(f"  Existing profiles: {len(existing)}")

    inserted = 0
    updated = 0
    errors = 0

    for lead_id, lead in leads.items():
        msgs = msgs_by_lead.get(lead_id, [])
        user_msgs = [m for m in msgs if m["role"] == "user"]
        follower_id = lead.get("platform_user_id") or lead_id

        # Extract data
        interests = detect_interests(msgs)
        objections = detect_objections(msgs)
        products = detect_product_interest(msgs)
        language = detect_language(msgs)

        # Avg message length for response style
        avg_len = 0
        if user_msgs:
            avg_len = sum(len(m["content"] or "") for m in user_msgs) / len(user_msgs)
        response_style = "concise" if avg_len < 50 else "moderate" if avg_len < 150 else "detailed"

        preferences = {
            "language": language,
            "response_style": response_style,
            "avg_message_length": round(avg_len, 1),
        }

        last_interaction = max((m["created_at"] for m in msgs), default=None) if msgs else None

        try:
            if follower_id in existing:
                cur.execute("""
                    UPDATE user_profiles SET
                        preferences = %s, interests = %s, objections = %s,
                        interested_products = %s, interaction_count = %s,
                        last_interaction = %s, updated_at = NOW()
                    WHERE creator_id = %s AND user_id = %s
                """, (
                    json.dumps(preferences), json.dumps(interests),
                    json.dumps(objections), json.dumps(products),
                    len(msgs), last_interaction,
                    CREATOR_STR, follower_id,
                ))
                updated += 1
            else:
                cur.execute("""
                    INSERT INTO user_profiles
                    (id, creator_id, user_id, preferences, interests, objections,
                     interested_products, interaction_count, last_interaction,
                     created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """, (
                    str(uuid.uuid4()), CREATOR_STR, follower_id,
                    json.dumps(preferences), json.dumps(interests),
                    json.dumps(objections), json.dumps(products),
                    len(msgs), last_interaction,
                ))
                inserted += 1
        except Exception as e:
            conn.rollback()
            errors += 1
            if errors <= 3:
                print(f"  ERROR lead {lead_id}: {e}")

    conn.commit()
    elapsed = time.time() - start
    print(f"  Inserted: {inserted}, Updated: {updated}, Errors: {errors}")
    print(f"  Time: {elapsed:.1f}s")

    cur.execute("SELECT count(*) FROM user_profiles WHERE creator_id = %s", (CREATOR_STR,))
    print(f"  TOTAL user_profiles: {cur.fetchone()[0]}")
    return inserted + updated


# ============================================================
# PHASE 3: LEAD INTELLIGENCE
# ============================================================
def phase3_lead_intelligence(conn, leads, msgs_by_lead):
    print("\n" + "=" * 60)
    print("PHASE 3: LEAD INTELLIGENCE (259 leads)")
    print("=" * 60)
    start = time.time()
    cur = conn.cursor()

    # Check existing
    cur.execute("SELECT lead_id FROM lead_intelligence WHERE creator_id = %s", (CREATOR_STR,))
    existing = {r[0] for r in cur.fetchall()}
    print(f"  Existing intelligence: {len(existing)}")

    inserted = 0
    updated = 0
    errors = 0
    now = datetime.now(timezone.utc)

    for lead_id, lead in leads.items():
        msgs = msgs_by_lead.get(lead_id, [])
        user_msgs = [m for m in msgs if m["role"] == "user"]
        follower_id = lead.get("platform_user_id") or lead_id

        # Engagement score (0-100)
        msg_count = len(msgs)
        if msg_count == 0:
            engagement = 5.0
        else:
            # Factor: message count (max 40 pts at 50+ msgs)
            msg_score = min(msg_count / 50 * 40, 40)
            # Factor: recency (max 30 pts if last msg < 3 days)
            last_msg_time = max((m["created_at"] for m in msgs), default=now)
            if last_msg_time.tzinfo is None:
                last_msg_time = last_msg_time.replace(tzinfo=timezone.utc)
            days_since = (now - last_msg_time).days
            recency_score = max(0, 30 - days_since * 2)
            # Factor: frequency (max 30 pts)
            if len(msgs) >= 2:
                first_msg = min(m["created_at"] for m in msgs)
                if first_msg.tzinfo is None:
                    first_msg = first_msg.replace(tzinfo=timezone.utc)
                span_days = max((last_msg_time - first_msg).days, 1)
                freq = msg_count / span_days
                freq_score = min(freq * 15, 30)
            else:
                freq_score = 5
            engagement = min(msg_score + recency_score + freq_score, 100)

        # Intent score from lead data
        intent = float(lead.get("purchase_intent") or lead.get("score") or 0)

        # Conversion probability
        has_price_q = any(re.search(r"preci|cost|cuar?nto|pago", (m["content"] or "").lower()) for m in user_msgs)
        has_conversion_signal = any(
            re.search(pat, (m["content"] or "").lower())
            for m in user_msgs for pat in CONVERSION_SIGNALS
        )
        conversion_prob = intent * 0.4 + (0.2 if has_price_q else 0) + (0.3 if has_conversion_signal else 0) + min(engagement / 100 * 0.1, 0.1)
        conversion_prob = min(conversion_prob, 1.0)

        # Best contact time (hour with most messages)
        hour_counts = Counter()
        for m in user_msgs:
            if m["created_at"]:
                hour_counts[m["created_at"].hour] += 1
        best_hour = hour_counts.most_common(1)[0][0] if hour_counts else 10
        best_contact_time = f"{best_hour:02d}:00:00"

        # Best contact day
        day_counts = Counter()
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for m in user_msgs:
            if m["created_at"]:
                day_counts[day_names[m["created_at"].weekday()]] += 1
        best_day = day_counts.most_common(1)[0][0] if day_counts else "Monday"

        # Interests and objections
        interests = detect_interests(msgs)
        objections = detect_objections(msgs)
        products_interested = detect_product_interest(msgs)

        # Recommended action
        status = lead.get("status", "nuevo")
        if status == "fantasma":
            action = "re_engagement"
        elif conversion_prob > 0.6:
            action = "close_sale"
        elif has_price_q:
            action = "handle_objection"
        elif engagement > 50:
            action = "nurture_warm"
        elif engagement > 20:
            action = "qualify"
        else:
            action = "initial_contact"

        # Churn risk
        if days_since > 30:
            churn = 0.9
        elif days_since > 14:
            churn = 0.7
        elif days_since > 7:
            churn = 0.5
        elif days_since > 3:
            churn = 0.3
        else:
            churn = 0.1

        # Fit score (based on interests matching Stefano's offerings)
        relevant_interests = {"fitness", "coaching", "bienestar", "respiracion", "sanacion", "movimiento", "masculinidad"}
        matching = set(interests.keys()) & relevant_interests
        fit_score = min(len(matching) / 3 * 100, 100) if matching else 30.0

        # Urgency
        urgency = conversion_prob * 50 + (50 - min(days_since, 50))

        try:
            if follower_id in existing:
                cur.execute("""
                    UPDATE lead_intelligence SET
                        engagement_score = %s, intent_score = %s, fit_score = %s,
                        urgency_score = %s, overall_score = %s, conversion_probability = %s,
                        churn_risk = %s, best_contact_time = %s, best_contact_day = %s,
                        interests = %s, objections = %s, products_interested = %s,
                        recommended_action = %s, last_calculated = NOW()
                    WHERE creator_id = %s AND lead_id = %s
                """, (
                    round(engagement, 1), round(intent, 3), round(fit_score, 1),
                    round(urgency, 1), round((engagement + fit_score + intent * 100) / 3, 1),
                    round(conversion_prob, 3),
                    round(churn, 2), best_contact_time, best_day,
                    json.dumps(interests), json.dumps(objections[:5]),
                    json.dumps(products_interested),
                    action, CREATOR_STR, follower_id,
                ))
                updated += 1
            else:
                cur.execute("""
                    INSERT INTO lead_intelligence
                    (creator_id, lead_id, engagement_score, intent_score, fit_score,
                     urgency_score, overall_score, conversion_probability,
                     churn_risk, best_contact_time, best_contact_day,
                     interests, objections, products_interested,
                     recommended_action, last_calculated, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                """, (
                    CREATOR_STR, follower_id,
                    round(engagement, 1), round(intent, 3), round(fit_score, 1),
                    round(urgency, 1), round((engagement + fit_score + intent * 100) / 3, 1),
                    round(conversion_prob, 3),
                    round(churn, 2), best_contact_time, best_day,
                    json.dumps(interests), json.dumps(objections[:5]),
                    json.dumps(products_interested),
                    action,
                ))
                inserted += 1
        except Exception as e:
            conn.rollback()
            errors += 1
            if errors <= 3:
                print(f"  ERROR lead {lead_id}: {e}")

    conn.commit()
    elapsed = time.time() - start
    print(f"  Inserted: {inserted}, Updated: {updated}, Errors: {errors}")
    print(f"  Time: {elapsed:.1f}s")

    cur.execute("SELECT count(*) FROM lead_intelligence WHERE creator_id = %s", (CREATOR_STR,))
    print(f"  TOTAL lead_intelligence: {cur.fetchone()[0]}")

    # Distribution of recommended actions
    cur.execute("""
        SELECT recommended_action, count(*) FROM lead_intelligence
        WHERE creator_id = %s GROUP BY recommended_action ORDER BY count(*) DESC
    """, (CREATOR_STR,))
    print("  Action distribution:")
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]}")

    return inserted + updated


# ============================================================
# PHASE 4: LEAD ACTIVITIES
# ============================================================
def phase4_lead_activities(conn, leads, messages, msgs_by_lead):
    print("\n" + "=" * 60)
    print("PHASE 4: LEAD ACTIVITIES (6,240+ messages)")
    print("=" * 60)
    start = time.time()
    cur = conn.cursor()

    # Check existing count
    cur.execute("SELECT count(*) FROM lead_activities")
    existing_count = cur.fetchone()[0]
    print(f"  Existing activities: {existing_count}")

    # If already substantially populated, skip
    if existing_count > 6000:
        print("  Already populated, skipping.")
        return existing_count

    inserted = 0
    errors = 0
    batch = []
    BATCH_SIZE = 500

    for msg in messages:
        lead_id = str(msg["lead_id"])
        lead = leads.get(lead_id)
        if not lead:
            continue

        activity_type = "message_sent" if msg["role"] == "user" else "message_received"
        content = msg["content"] or ""
        description = content[:200] if content else ""

        # Detect additional activity types from content
        extra_activities = []
        if msg["role"] == "user" and content:
            text_lower = content.lower()
            # Product mention
            for pkey, pdata in PRODUCT_PATTERNS.items():
                if pdata["id"]:
                    for pat in pdata["patterns"]:
                        if re.search(pat, text_lower):
                            extra_activities.append(("product_mentioned", pkey, pdata["id"]))
                            break
            # Conversion signal
            for pat in CONVERSION_SIGNALS:
                if re.search(pat, text_lower):
                    extra_activities.append(("conversion_signal", content[:100], None))
                    break
            # Objection
            for pat, obj_type in OBJECTION_PATTERNS:
                if re.search(pat, text_lower):
                    extra_activities.append(("objection_raised", obj_type, None))
                    break

        # Main activity
        batch.append((
            str(uuid.uuid4()), msg["lead_id"], CREATOR_UUID,
            activity_type, description, None, None,
            json.dumps({"message_id": str(msg["id"]), "role": msg["role"]}),
            "system", msg["created_at"],
        ))

        # Extra activities
        for act_type, act_desc, extra in extra_activities:
            batch.append((
                str(uuid.uuid4()), msg["lead_id"], CREATOR_UUID,
                act_type, act_desc, None, extra,
                json.dumps({"source_message_id": str(msg["id"])}),
                "system", msg["created_at"],
            ))

        if len(batch) >= BATCH_SIZE:
            try:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO lead_activities
                    (id, lead_id, creator_id, activity_type, description,
                     old_value, new_value, extra_data, created_by, created_at)
                    VALUES %s""",
                    batch,
                    template="(%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::json, %s, %s)",
                )
                inserted += len(batch)
            except Exception as e:
                conn.rollback()
                errors += len(batch)
                if errors <= 500:
                    print(f"  BATCH ERROR: {e}")
            batch = []
            conn.commit()

            if inserted % 2000 == 0:
                print(f"  Progress: {inserted} inserted, {errors} errors")

    # Final batch
    if batch:
        try:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO lead_activities
                (id, lead_id, creator_id, activity_type, description,
                 old_value, new_value, extra_data, created_by, created_at)
                VALUES %s""",
                batch,
                template="(%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::json, %s, %s)",
            )
            inserted += len(batch)
        except Exception as e:
            conn.rollback()
            errors += len(batch)
            print(f"  FINAL BATCH ERROR: {e}")
    conn.commit()

    elapsed = time.time() - start
    print(f"  Inserted: {inserted}, Errors: {errors}")
    print(f"  Time: {elapsed:.1f}s")

    cur.execute("SELECT count(*) FROM lead_activities")
    print(f"  TOTAL lead_activities: {cur.fetchone()[0]}")

    cur.execute("""
        SELECT activity_type, count(*) FROM lead_activities
        GROUP BY activity_type ORDER BY count(*) DESC
    """)
    print("  Activity type distribution:")
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]}")

    return inserted


# ============================================================
# PHASE 5: PRODUCT ANALYTICS
# ============================================================
def phase5_product_analytics(conn, leads, messages, msgs_by_lead):
    print("\n" + "=" * 60)
    print("PHASE 5: PRODUCT ANALYTICS (all messages)")
    print("=" * 60)
    start = time.time()
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM product_analytics WHERE creator_id = %s", (CREATOR_STR,))
    existing = cur.fetchone()[0]
    print(f"  Existing product_analytics: {existing}")

    # Analyze all messages by product × week
    # Structure: {(product_id, week_start): {mentions, questions, objections, conversions}}
    analytics = defaultdict(lambda: {"mentions": 0, "questions": 0, "objections": 0, "conversions": 0})

    for msg in messages:
        if not msg["content"]:
            continue
        text_lower = msg["content"].lower()
        msg_date = msg["created_at"]
        if msg_date:
            # Get week start (Monday)
            if hasattr(msg_date, 'date'):
                d = msg_date.date()
            else:
                d = msg_date
            week_start = d - timedelta(days=d.weekday())
        else:
            continue

        for pkey, pdata in PRODUCT_PATTERNS.items():
            if not pdata["id"]:
                continue
            matched = False
            for pat in pdata["patterns"]:
                if re.search(pat, text_lower):
                    matched = True
                    break
            if not matched:
                continue

            key = (pdata["id"], week_start)
            analytics[key]["mentions"] += 1

            # Classify the mention
            if msg["role"] == "user":
                # Question about product
                if re.search(r"\?|qu[eé]|c[oó]mo|cu[aá]nto|info|incluye|dura", text_lower):
                    analytics[key]["questions"] += 1
                # Objection
                for pat, _ in OBJECTION_PATTERNS:
                    if re.search(pat, text_lower):
                        analytics[key]["objections"] += 1
                        break
                # Conversion signal
                for pat in CONVERSION_SIGNALS:
                    if re.search(pat, text_lower):
                        analytics[key]["conversions"] += 1
                        break

    # Insert analytics
    inserted = 0
    errors = 0

    # Clear existing for this creator to avoid duplicates
    if existing > 0:
        cur.execute("DELETE FROM product_analytics WHERE creator_id = %s", (CREATOR_STR,))
        print(f"  Cleared {cur.rowcount} existing records")

    for (product_id, week_start), data in analytics.items():
        try:
            cur.execute("""
                INSERT INTO product_analytics
                (product_id, creator_id, date, mentions, questions, objections, conversions, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                product_id, CREATOR_STR, week_start,
                data["mentions"], data["questions"], data["objections"], data["conversions"],
            ))
            inserted += 1
        except Exception as e:
            conn.rollback()
            errors += 1
            if errors <= 3:
                print(f"  ERROR: {e}")

    conn.commit()
    elapsed = time.time() - start
    print(f"  Inserted: {inserted} week-product records, Errors: {errors}")
    print(f"  Time: {elapsed:.1f}s")

    # Summary by product
    cur.execute("""
        SELECT p.name, SUM(pa.mentions), SUM(pa.questions), SUM(pa.objections), SUM(pa.conversions)
        FROM product_analytics pa
        JOIN products p ON pa.product_id::text = p.id::text
        WHERE pa.creator_id = %s
        GROUP BY p.name
        ORDER BY SUM(pa.mentions) DESC
    """, (CREATOR_STR,))
    print("  Product summary:")
    for r in cur.fetchall():
        print(f"    {r[0]}: mentions={r[1]} questions={r[2]} objections={r[3]} conversions={r[4]}")

    cur.execute("SELECT count(*) FROM product_analytics WHERE creator_id = %s", (CREATOR_STR,))
    print(f"  TOTAL product_analytics: {cur.fetchone()[0]}")

    return inserted


# ============================================================
# PHASE 6: NURTURING SEQUENCES + FOLLOWUPS
# ============================================================
def phase6_nurturing(conn, leads, msgs_by_lead):
    print("\n" + "=" * 60)
    print("PHASE 6: NURTURING SEQUENCES + FOLLOWUPS")
    print("=" * 60)
    start = time.time()
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM nurturing_sequences WHERE creator_id = %s", (CREATOR_UUID,))
    existing_seq = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM nurturing_followups WHERE creator_id = %s", (CREATOR_STR,))
    existing_fu = cur.fetchone()[0]
    print(f"  Existing sequences: {existing_seq}, followups: {existing_fu}")

    # Insert 4 sequences if not exists
    sequences = [
        ("abandoned_cart", "Carrito Abandonado", [
            {"step": 1, "delay_hours": 24, "template": "Hey {name}! Vi que te interesó {product}. ¿Tenés alguna duda que pueda resolver? 💪"},
            {"step": 2, "delay_hours": 72, "template": "Solo quería saber si necesitás más info sobre {product}. Estoy acá para lo que necesites 🙌"},
            {"step": 3, "delay_hours": 168, "template": "{name}, última oportunidad de sumarte. ¿Qué decís? 🔥"},
        ]),
        ("interest_cold", "Interés Frío", [
            {"step": 1, "delay_hours": 48, "template": "¡{name}! ¿Cómo andás? Hace unos días hablamos, ¿seguís interesado?"},
            {"step": 2, "delay_hours": 120, "template": "Bro, te cuento que tengo novedades que te pueden interesar. ¿Hablamos?"},
        ]),
        ("re_engagement", "Reactivación Ghost", [
            {"step": 1, "delay_hours": 0, "template": "¡Hola {name}! Hace rato no hablamos. ¿Cómo venís con tus objetivos? 💪"},
        ]),
        ("booking_reminder", "Recordatorio Sesión", [
            {"step": 1, "delay_hours": 2, "template": "¡{name}! Recordá que tenés tu sesión pendiente. ¿Confirmamos? 🙏"},
        ]),
    ]

    seq_inserted = 0
    if existing_seq == 0:
        for seq_type, seq_name, steps in sequences:
            try:
                cur.execute("""
                    INSERT INTO nurturing_sequences (id, creator_id, type, name, is_active, steps, created_at)
                    VALUES (%s, %s, %s, %s, true, %s, NOW())
                """, (str(uuid.uuid4()), CREATOR_UUID, seq_type, seq_name, json.dumps(steps)))
                seq_inserted += 1
            except Exception as e:
                conn.rollback()
                print(f"  ERROR seq {seq_type}: {e}")
        conn.commit()
        print(f"  Inserted {seq_inserted} nurturing sequences")
    else:
        print(f"  Sequences already exist ({existing_seq}), skipping insert")

    # Create followups for eligible leads
    now = datetime.now(timezone.utc)
    fu_inserted = 0

    for lead_id, lead in leads.items():
        msgs = msgs_by_lead.get(lead_id, [])
        if not msgs:
            continue

        follower_id = lead.get("platform_user_id") or lead_id
        status = lead.get("status", "nuevo")
        last_msg_time = max((m["created_at"] for m in msgs), default=now)
        if last_msg_time.tzinfo is None:
            last_msg_time = last_msg_time.replace(tzinfo=timezone.utc)
        days_since = (now - last_msg_time).days

        # Determine which sequence applies
        seq_type = None
        if status == "caliente" and days_since >= 1:
            seq_type = "abandoned_cart"
        elif status == "interesado" and days_since >= 3:
            seq_type = "interest_cold"
        elif status == "nuevo" and days_since >= 7:
            seq_type = "re_engagement"
        elif status == "fantasma":
            seq_type = "re_engagement"

        if not seq_type:
            continue

        # Create followup
        try:
            scheduled_at = now + timedelta(hours=1)  # Schedule 1 hour from now
            fu_id = f"fu_{CREATOR_STR}_{follower_id}_{seq_type}"[:100]
            cur.execute("""
                INSERT INTO nurturing_followups
                (id, creator_id, follower_id, sequence_type, step, scheduled_at,
                 message_template, status, created_at)
                VALUES (%s, %s, %s, %s, 1, %s, %s, 'pending', NOW())
                ON CONFLICT (id) DO NOTHING
            """, (
                fu_id, CREATOR_STR, follower_id, seq_type,
                scheduled_at, f"Auto-generated followup for {seq_type}",
            ))
            if cur.rowcount > 0:
                fu_inserted += 1
        except Exception as e:
            conn.rollback()
            if fu_inserted < 3:
                print(f"  ERROR followup: {e}")

    conn.commit()
    elapsed = time.time() - start
    print(f"  Followups inserted: {fu_inserted}")
    print(f"  Time: {elapsed:.1f}s")

    cur.execute("SELECT count(*) FROM nurturing_sequences WHERE creator_id = %s", (CREATOR_UUID,))
    print(f"  TOTAL nurturing_sequences: {cur.fetchone()[0]}")
    cur.execute("SELECT count(*) FROM nurturing_followups WHERE creator_id = %s", (CREATOR_STR,))
    print(f"  TOTAL nurturing_followups: {cur.fetchone()[0]}")

    # Distribution
    cur.execute("""
        SELECT sequence_type, count(*) FROM nurturing_followups
        WHERE creator_id = %s GROUP BY sequence_type ORDER BY count(*) DESC
    """, (CREATOR_STR,))
    print("  Followup distribution:")
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]}")

    return seq_inserted + fu_inserted


# ============================================================
# PHASE 7: CONVERSATION STATES
# ============================================================
def phase7_conversation_states(conn, leads, msgs_by_lead):
    print("\n" + "=" * 60)
    print("PHASE 7: CONVERSATION STATES (259 leads)")
    print("=" * 60)
    start = time.time()
    cur = conn.cursor()

    cur.execute("SELECT follower_id FROM conversation_states WHERE creator_id = %s", (CREATOR_STR,))
    existing = {r[0] for r in cur.fetchall()}
    print(f"  Existing states: {len(existing)}")

    _now = datetime.now(timezone.utc)
    inserted = 0
    updated = 0
    errors = 0

    phase_distribution = Counter()

    for lead_id, lead in leads.items():
        msgs = msgs_by_lead.get(lead_id, [])
        follower_id = lead.get("platform_user_id") or lead_id
        status = lead.get("status", "nuevo")
        intent = float(lead.get("purchase_intent") or lead.get("score") or 0)
        msg_count = len(msgs)
        user_msgs = [m for m in msgs if m["role"] == "user"]

        # Skip ghosts (as per instructions)
        if status == "fantasma":
            continue

        # Determine funnel phase
        has_price_q = any(re.search(r"preci|cost|cuar?nto|pago", (m["content"] or "").lower()) for m in user_msgs)
        has_conversion = any(
            re.search(pat, (m["content"] or "").lower())
            for m in user_msgs for pat in CONVERSION_SIGNALS
        )
        has_objection = any(
            re.search(pat, (m["content"] or "").lower())
            for m in user_msgs for pat, _ in OBJECTION_PATTERNS
        )

        if has_conversion or (intent >= 0.8 and has_price_q):
            phase = "CIERRE"
        elif has_price_q and intent >= 0.5:
            phase = "PROPUESTA"
        elif has_objection and intent >= 0.3:
            phase = "OBJECIONES"
        elif intent >= 0.3 and msg_count > 4:
            phase = "DESCUBRIMIENTO"
        elif msg_count > 2:
            phase = "CUALIFICACION"
        else:
            phase = "INICIO"

        phase_distribution[phase] += 1

        # Build context from last messages
        last_msgs = msgs[-5:] if msgs else []
        context = {
            "last_messages": [
                {"role": m["role"], "content": (m["content"] or "")[:100], "date": str(m["created_at"])}
                for m in last_msgs
            ],
            "total_messages": msg_count,
            "status": status,
            "intent_score": intent,
        }

        try:
            if follower_id in existing:
                cur.execute("""
                    UPDATE conversation_states SET
                        phase = %s, message_count = %s, context = %s, updated_at = NOW()
                    WHERE creator_id = %s AND follower_id = %s
                """, (phase, msg_count, json.dumps(context), CREATOR_STR, follower_id))
                updated += 1
            else:
                cur.execute("""
                    INSERT INTO conversation_states
                    (id, creator_id, follower_id, phase, message_count, context, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                """, (str(uuid.uuid4()), CREATOR_STR, follower_id, phase, msg_count, json.dumps(context)))
                inserted += 1
        except Exception as e:
            conn.rollback()
            errors += 1
            if errors <= 3:
                print(f"  ERROR: {e}")

    conn.commit()
    elapsed = time.time() - start
    print(f"  Inserted: {inserted}, Updated: {updated}, Errors: {errors}")
    print(f"  Time: {elapsed:.1f}s")

    print("  Phase distribution:")
    for phase, count in phase_distribution.most_common():
        print(f"    {phase}: {count}")

    cur.execute("SELECT count(*) FROM conversation_states WHERE creator_id = %s", (CREATOR_STR,))
    print(f"  TOTAL conversation_states: {cur.fetchone()[0]}")

    return inserted + updated


# ============================================================
# PHASE 8: POST CONTEXTS
# ============================================================
def phase8_post_contexts(conn, posts):
    print("\n" + "=" * 60)
    print("PHASE 8: POST CONTEXTS (50 Instagram posts)")
    print("=" * 60)
    start = time.time()
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM post_contexts WHERE creator_id = %s", (CREATOR_STR,))
    existing = cur.fetchone()[0]
    print(f"  Existing post_contexts: {existing}")

    if not posts:
        print("  No Instagram posts found, skipping.")
        return 0

    # Analyze posts
    recent_posts = posts[:10]  # Last 10 posts
    all_posts = posts

    # Extract topics from captions
    topics = Counter()
    products_mentioned = Counter()
    active_promotion = None
    _promotion_deadline = None

    for p in all_posts:
        caption = (p.get("caption") or "").lower()
        # Topic detection
        for topic, patterns in INTEREST_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, caption):
                    topics[topic] += 1
                    break
        # Product detection
        for pkey, pdata in PRODUCT_PATTERNS.items():
            for pat in pdata["patterns"]:
                if re.search(pat, caption):
                    products_mentioned[pkey] += 1
                    break

    # Check for promotions in recent posts
    promo_patterns = [
        r"descuento", r"oferta", r"promoci[oó]n", r"gratis", r"free",
        r"\d+%\s*(off|descuento)", r"últim[ao]s?\s+plazas?", r"fecha\s+l[ií]mite",
    ]
    for p in recent_posts:
        caption = (p.get("caption") or "").lower()
        for pat in promo_patterns:
            if re.search(pat, caption):
                active_promotion = (p.get("caption") or "")[:200]
                break
        if active_promotion:
            break

    recent_topics = [{"topic": t, "count": c} for t, c in topics.most_common(10)]
    recent_products = [{"product": p, "mentions": c} for p, c in products_mentioned.most_common(5)]

    source_posts = [
        {
            "id": str(p["id"]),
            "caption": (p.get("caption") or "")[:200],
            "timestamp": str(p.get("post_timestamp")),
            "likes": p.get("likes_count", 0),
            "comments": p.get("comments_count", 0),
        }
        for p in recent_posts
    ]

    try:
        if existing > 0:
            cur.execute("""
                UPDATE post_contexts SET
                    active_promotion = %s, recent_topics = %s, recent_products = %s,
                    posts_analyzed = %s, analyzed_at = NOW(), source_posts = %s,
                    context_instructions = %s, updated_at = NOW()
                WHERE creator_id = %s
            """, (
                active_promotion,
                json.dumps(recent_topics), json.dumps(recent_products),
                len(all_posts), json.dumps(source_posts),
                f"Analyzed {len(all_posts)} posts. Top topics: {', '.join(t for t, _ in topics.most_common(5))}",
                CREATOR_STR,
            ))
        else:
            cur.execute("""
                INSERT INTO post_contexts
                (id, creator_id, active_promotion, recent_topics, recent_products,
                 posts_analyzed, analyzed_at, source_posts, context_instructions,
                 created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, NOW(), NOW())
            """, (
                str(uuid.uuid4()), CREATOR_STR,
                active_promotion,
                json.dumps(recent_topics), json.dumps(recent_products),
                len(all_posts), json.dumps(source_posts),
                f"Analyzed {len(all_posts)} posts. Top topics: {', '.join(t for t, _ in topics.most_common(5))}",
            ))
        conn.commit()
        print(f"  Post context {'updated' if existing > 0 else 'created'}")
    except Exception as e:
        conn.rollback()
        print(f"  ERROR: {e}")

    elapsed = time.time() - start
    print(f"  Posts analyzed: {len(all_posts)}")
    print(f"  Topics found: {dict(topics.most_common(10))}")
    print(f"  Products mentioned: {dict(products_mentioned)}")
    print(f"  Active promotion: {'Yes' if active_promotion else 'No'}")
    print(f"  Time: {elapsed:.1f}s")

    cur.execute("SELECT count(*) FROM post_contexts WHERE creator_id = %s", (CREATOR_STR,))
    print(f"  TOTAL post_contexts: {cur.fetchone()[0]}")

    return 1


# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print("MASTER POPULATION SCRIPT — Phases 2-8")
    print(f"Creator: {CREATOR_STR} ({CREATOR_UUID})")
    print(f"Started: {datetime.now()}")
    print("=" * 60)

    conn = get_connection()
    total_start = time.time()

    # Load all data once
    leads, messages, msgs_by_lead, products, posts = load_all_data(conn)

    # Execute phases
    results = {}

    try:
        results["phase2"] = phase2_user_profiles(conn, leads, msgs_by_lead)
    except Exception as e:
        print(f"\n!!! PHASE 2 FAILED: {e}")
        results["phase2"] = f"ERROR: {e}"

    try:
        results["phase3"] = phase3_lead_intelligence(conn, leads, msgs_by_lead)
    except Exception as e:
        print(f"\n!!! PHASE 3 FAILED: {e}")
        results["phase3"] = f"ERROR: {e}"

    try:
        results["phase4"] = phase4_lead_activities(conn, leads, messages, msgs_by_lead)
    except Exception as e:
        print(f"\n!!! PHASE 4 FAILED: {e}")
        results["phase4"] = f"ERROR: {e}"

    try:
        results["phase5"] = phase5_product_analytics(conn, leads, messages, msgs_by_lead)
    except Exception as e:
        print(f"\n!!! PHASE 5 FAILED: {e}")
        results["phase5"] = f"ERROR: {e}"

    try:
        results["phase6"] = phase6_nurturing(conn, leads, msgs_by_lead)
    except Exception as e:
        print(f"\n!!! PHASE 6 FAILED: {e}")
        results["phase6"] = f"ERROR: {e}"

    try:
        results["phase7"] = phase7_conversation_states(conn, leads, msgs_by_lead)
    except Exception as e:
        print(f"\n!!! PHASE 7 FAILED: {e}")
        results["phase7"] = f"ERROR: {e}"

    try:
        results["phase8"] = phase8_post_contexts(conn, posts)
    except Exception as e:
        print(f"\n!!! PHASE 8 FAILED: {e}")
        results["phase8"] = f"ERROR: {e}"

    total_elapsed = time.time() - total_start
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for phase, result in results.items():
        print(f"  {phase}: {result}")
    print(f"  Total time: {total_elapsed:.1f}s ({total_elapsed/60:.1f}m)")

    conn.close()


if __name__ == "__main__":
    main()
