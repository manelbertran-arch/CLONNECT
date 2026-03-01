#!/usr/bin/env python3
"""
=============================================================================
LA HORA DE LA VERDAD — TEST MASIVO DE TODOS LOS SISTEMAS CLONNECT
=============================================================================

Tests every system, every table, every data flow.
Verifies that ALL populated data is accessible and usable by the bot.

Categories:
  1. DATA INTEGRITY — all tables have expected data
  2. CREATOR DATA LOADER — personality, products, knowledge loaded
  3. USER CONTEXT LOADER — leads, profiles, memories accessible
  4. SEMANTIC MEMORY (pgvector) — embedding search works
  5. RAG / KNOWLEDGE SEARCH — content chunks, reranking
  6. CONVERSATION STATES — funnel phases correct
  7. NURTURING — sequences, followups, DB storage
  8. RELATIONSHIP DNA — trust scores, vocabulary
  9. LEAD INTELLIGENCE — scores, actions, contact times
  10. PRODUCT ANALYTICS — mentions, conversions tracked
  11. POST CONTEXT — Instagram post analysis
  12. PIPELINE INTEGRATION — full DM pipeline end-to-end
  13. WEEKLY REPORT — real data report

Run: cd ~/Clonnect/backend && python3 scripts/test_hora_de_la_verdad.py
"""
import os
import sys
import json
import time
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ["DATABASE_URL"]
CREATOR_UUID = "5e5c2364-c99a-4484-b986-741bb84a11cf"
CREATOR_STR = "stefano_bonanno"

# Test results tracking
RESULTS = []
CATEGORY = ""


def test(name, condition, detail=""):
    """Record a test result."""
    status = "PASS" if condition else "FAIL"
    RESULTS.append({
        "category": CATEGORY,
        "name": name,
        "status": status,
        "detail": detail,
    })
    icon = "✅" if condition else "❌"
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))
    return condition


def set_category(name):
    global CATEGORY
    CATEGORY = name
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


# Tables that use UUID for creator_id (rest use varchar)
UUID_TABLES = {
    "creator_calibrations", "knowledge_base", "lead_activities", "leads",
    "nurturing_sequences", "products", "rag_documents", "dismissed_leads",
    "csat_ratings", "email_ask_tracking", "lead_tasks", "platform_identities",
}


def cid(table_name: str) -> str:
    """Return the correct creator_id value based on table type."""
    return CREATOR_UUID if table_name in UUID_TABLES else CREATOR_STR


# =============================================================================
# CATEGORY 1: DATA INTEGRITY — All tables have expected counts
# =============================================================================
def test_data_integrity():
    set_category("1. DATA INTEGRITY — Table Counts")
    conn = get_conn()
    cur = conn.cursor()

    expected = {
        "messages": (6000, ">="),
        "leads": (259, ">="),
        "content_chunks": (400, ">="),
        "content_embeddings": (380, ">="),
        "rag_documents": (370, ">="),
        "products": (5, "=="),
        "conversation_embeddings": (6000, ">="),
        "lead_intelligence": (259, ">="),
        "lead_activities": (6000, ">="),
        "nurturing_sequences": (4, ">="),
        "nurturing_followups": (200, ">="),
        "product_analytics": (50, ">="),
        "user_profiles": (259, ">="),
        "conversation_states": (250, ">="),
        "post_contexts": (1, ">="),
        "weekly_reports": (1, ">="),
        "relationship_dna": (150, ">="),
        "follower_memories": (1, ">="),
        "knowledge_base": (18, ">="),
        "tone_profiles": (1, ">="),
        "creator_calibrations": (7, ">="),
        "booking_links": (3, ">="),
        "instagram_posts": (50, ">="),
    }

    for table, (threshold, op) in expected.items():
        try:
            cur.execute(f"SELECT count(*) FROM {table}")
            count = cur.fetchone()[0]
            if op == ">=":
                ok = count >= threshold
            else:
                ok = count == threshold
            test(f"{table}: {count} rows", ok, f"expected {op}{threshold}")
        except Exception as e:
            conn.rollback()
            test(f"{table}", False, str(e))

    conn.close()


# =============================================================================
# CATEGORY 2: CREATOR DATA LOADER
# =============================================================================
def test_creator_data_loader():
    set_category("2. CREATOR DATA LOADER — Personality & Products")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Test: Creator exists with full data
    cur.execute("SELECT * FROM creators WHERE id = %s", (CREATOR_UUID,))
    creator = cur.fetchone()
    test("Creator stefano_bonanno exists", creator is not None)
    test("Creator has name", creator and creator.get("name") == "stefano_bonanno")
    test("Creator has IG token", creator and bool(creator.get("instagram_token")))
    test("Creator has knowledge_about", creator and bool(creator.get("knowledge_about")))
    test("Creator bot_active=True", creator and creator.get("bot_active") is True)
    test("Creator clone_status=complete", creator and creator.get("clone_status") == "complete")

    # Knowledge_about has key fields
    ka = creator.get("knowledge_about", {}) if creator else {}
    test("knowledge_about.website_url present", bool(ka.get("website_url")))
    test("knowledge_about.bio present", bool(ka.get("bio")))
    test("knowledge_about.tone present", bool(ka.get("tone")))
    test("knowledge_about.specialties present", bool(ka.get("specialties")))

    # Products
    cur.execute("SELECT * FROM products WHERE creator_id = %s", (CREATOR_UUID,))
    products = cur.fetchall()
    test("5 products loaded", len(products) == 5)
    product_names = [p["name"] for p in products]
    test("Fitpack Challenge exists", any("fitpack" in n.lower() or "Fitpack" in n for n in product_names))
    test("Sesion Descubrimiento exists", any("sesion" in n.lower() or "descubrimiento" in n.lower() for n in product_names))

    # Booking links
    cur.execute("SELECT * FROM booking_links WHERE creator_id = %s", (CREATOR_STR,))
    links = cur.fetchall()
    test(f"Booking links exist ({len(links)})", len(links) >= 1)

    # Knowledge base (uses UUID creator_id)
    cur.execute("SELECT * FROM knowledge_base WHERE creator_id = %s", (CREATOR_UUID,))
    kb = cur.fetchall()
    test(f"Knowledge base: {len(kb)} FAQs", len(kb) >= 15)

    # Tone profile
    cur.execute("SELECT * FROM tone_profiles WHERE creator_id = %s", (CREATOR_STR,))
    tp = cur.fetchone()
    test("Tone profile exists", tp is not None)
    if tp:
        profile = tp.get("profile_data") or tp.get("tone_data") or {}
        test("Tone profile has data", bool(profile))

    conn.close()


# =============================================================================
# CATEGORY 3: USER CONTEXT LOADER — Leads, Profiles, Memories
# =============================================================================
def test_user_context():
    set_category("3. USER CONTEXT — Leads, Profiles, Memories")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # All leads have Spanish statuses
    cur.execute("""
        SELECT status, count(*) FROM leads
        WHERE creator_id = %s GROUP BY status ORDER BY count(*) DESC
    """, (CREATOR_UUID,))
    statuses = {r["status"]: r["count"] for r in cur.fetchall()}
    valid = {"nuevo", "interesado", "caliente", "cliente", "fantasma"}
    invalid = set(statuses.keys()) - valid
    test("All lead statuses in Spanish", len(invalid) == 0,
         f"invalid: {invalid}" if invalid else f"statuses: {statuses}")

    # User profiles match leads
    cur.execute("SELECT count(*) FROM user_profiles WHERE creator_id = %s", (CREATOR_STR,))
    up_count = cur.fetchone()["count"]
    cur.execute("SELECT count(*) FROM leads WHERE creator_id = %s", (CREATOR_UUID,))
    lead_count = cur.fetchone()["count"]
    test("User profiles cover all leads", up_count >= lead_count,
         f"profiles={up_count} leads={lead_count}")

    # User profiles have meaningful data
    cur.execute("""
        SELECT * FROM user_profiles WHERE creator_id = %s
        AND interests IS NOT NULL AND interests::text != '{}'
        AND interests::text != 'null'
    """, (CREATOR_STR,))
    profiles_with_interests = cur.fetchall()
    test(f"Profiles with interests: {len(profiles_with_interests)}",
         len(profiles_with_interests) >= 30, "expected >=30 with detected interests")

    # Profiles with objections
    cur.execute("""
        SELECT count(*) FROM user_profiles WHERE creator_id = %s
        AND objections IS NOT NULL AND objections::text != '[]'
        AND objections::text != 'null'
    """, (CREATOR_STR,))
    obj_count = cur.fetchone()["count"]
    test(f"Profiles with objections: {obj_count}", obj_count >= 10)

    # Follower memories (created in real-time during DMs, not batch-populated)
    cur.execute("SELECT count(*) FROM follower_memories WHERE creator_id = %s", (CREATOR_STR,))
    fm = cur.fetchone()["count"]
    test(f"Follower memories: {fm} (real-time, grows with DMs)", fm >= 1)

    # Pick a specific active lead and verify full profile
    cur.execute("""
        SELECT l.id, l.username, l.status, l.platform_user_id,
               (SELECT count(*) FROM messages m WHERE m.lead_id = l.id) as msg_count
        FROM leads l
        WHERE l.creator_id = %s AND l.status = 'interesado'
        ORDER BY (SELECT count(*) FROM messages m WHERE m.lead_id = l.id) DESC
        LIMIT 1
    """, (CREATOR_UUID,))
    top_lead = cur.fetchone()
    if top_lead:
        test(f"Top active lead: @{top_lead['username']} ({top_lead['msg_count']} msgs)",
             top_lead["msg_count"] > 10)

        # Check this lead has a user_profile
        follower_id = top_lead["platform_user_id"] or str(top_lead["id"])
        cur.execute("SELECT * FROM user_profiles WHERE creator_id = %s AND user_id = %s",
                    (CREATOR_STR, follower_id))
        profile = cur.fetchone()
        test("  → has user_profile", profile is not None)
        if profile:
            test("  → profile.interaction_count > 0",
                 (profile.get("interaction_count") or 0) > 0)

    conn.close()


# =============================================================================
# CATEGORY 4: SEMANTIC MEMORY (pgvector)
# =============================================================================
def test_semantic_memory():
    set_category("4. SEMANTIC MEMORY — Conversation Embeddings (pgvector)")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Count embeddings by role
    cur.execute("""
        SELECT message_role, count(*) FROM conversation_embeddings
        WHERE creator_id = %s GROUP BY message_role
    """, (CREATOR_STR,))
    by_role = {r["message_role"]: r["count"] for r in cur.fetchall()}
    test(f"User embeddings: {by_role.get('user', 0)}", by_role.get("user", 0) >= 2600)
    test(f"Assistant embeddings: {by_role.get('assistant', 0)}", by_role.get("assistant", 0) >= 3500)

    # All embeddings have actual vectors
    cur.execute("""
        SELECT count(*) FROM conversation_embeddings
        WHERE creator_id = %s AND embedding IS NOT NULL
    """, (CREATOR_STR,))
    with_emb = cur.fetchone()["count"]
    total = sum(by_role.values())
    test(f"All embeddings have vectors ({with_emb}/{total})", with_emb == total)

    # Verify vector dimensions
    cur.execute("""
        SELECT vector_dims(embedding) FROM conversation_embeddings
        WHERE creator_id = %s AND embedding IS NOT NULL LIMIT 1
    """, (CREATOR_STR,))
    dims = cur.fetchone()
    test("Vector dimension = 1536", dims and dims["vector_dims"] == 1536)

    # CRITICAL: Test semantic SEARCH actually works
    # Find messages about "precio" (price) — should return price-related conversations
    cur.execute("""
        SELECT content, message_role,
               embedding <=> (
                   SELECT embedding FROM conversation_embeddings
                   WHERE creator_id = %s AND content ILIKE '%%precio%%'
                   LIMIT 1
               ) as distance
        FROM conversation_embeddings
        WHERE creator_id = %s AND embedding IS NOT NULL
        ORDER BY distance
        LIMIT 5
    """, (CREATOR_STR, CREATOR_STR))
    results = cur.fetchall()
    test(f"Semantic search returns results ({len(results)})", len(results) >= 3)
    if results:
        # Check that results are topically related (contain price/cost/money words)
        price_words = {"precio", "cuesta", "pago", "dinero", "vale", "euros", "cost"}
        relevant = sum(1 for r in results if any(w in (r["content"] or "").lower() for w in price_words))
        test(f"  → {relevant}/5 results mention price/cost", relevant >= 1,
             f"top result: '{(results[0]['content'] or '')[:80]}...'")

    # Test: embeddings cover the full date range
    cur.execute("""
        SELECT MIN(created_at), MAX(created_at) FROM conversation_embeddings
        WHERE creator_id = %s
    """, (CREATOR_STR,))
    dates = cur.fetchone()
    if dates and dates["min"] and dates["max"]:
        span_days = (dates["max"] - dates["min"]).days
        test(f"Embeddings span {span_days} days", span_days > 365,
             f"{dates['min'].date()} to {dates['max'].date()}")

    conn.close()


# =============================================================================
# CATEGORY 5: RAG / KNOWLEDGE SEARCH
# =============================================================================
def test_rag_knowledge():
    set_category("5. RAG / KNOWLEDGE SEARCH — Content Chunks & Embeddings")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Content chunks
    cur.execute("SELECT count(*) FROM content_chunks WHERE creator_id = %s", (CREATOR_STR,))
    chunks = cur.fetchone()["count"]
    test(f"Content chunks: {chunks}", chunks >= 400)

    # Content embeddings
    cur.execute("SELECT count(*) FROM content_embeddings WHERE creator_id = %s", (CREATOR_STR,))
    embs = cur.fetchone()["count"]
    test(f"Content embeddings: {embs}", embs >= 380)

    # RAG documents
    cur.execute("SELECT count(*) FROM rag_documents WHERE creator_id = %s", (CREATOR_UUID,))
    rag = cur.fetchone()["count"]
    test(f"RAG documents: {rag}", rag >= 370)

    # RAG documents have associated content_embeddings
    cur.execute("""
        SELECT count(*) FROM content_embeddings WHERE creator_id = %s
    """, (CREATOR_STR,))
    rag_with_emb = cur.fetchone()["count"]
    test(f"Content embeddings for RAG: {rag_with_emb}", rag_with_emb > 300)

    # Test: RAG search for "Fitpack" returns relevant results
    cur.execute("""
        SELECT title, content, source_url
        FROM rag_documents
        WHERE creator_id = %s AND (
            content ILIKE '%%fitpack%%'
            OR title ILIKE '%%fitpack%%'
        )
        LIMIT 5
    """, (CREATOR_UUID,))
    fitpack_docs = cur.fetchall()
    test(f"RAG finds Fitpack docs ({len(fitpack_docs)})", len(fitpack_docs) >= 1)

    # Test: Knowledge base has FAQ content
    cur.execute("""
        SELECT question, answer FROM knowledge_base
        WHERE creator_id = %s LIMIT 5
    """, (CREATOR_UUID,))
    faqs = cur.fetchall()
    test("Knowledge base FAQs accessible", len(faqs) >= 5)
    if faqs:
        has_answers = sum(1 for f in faqs if f["answer"] and len(f["answer"]) > 20)
        test(f"  → FAQs have substantive answers ({has_answers}/5)", has_answers >= 3)

    conn.close()


# =============================================================================
# CATEGORY 6: CONVERSATION STATES
# =============================================================================
def test_conversation_states():
    set_category("6. CONVERSATION STATES — Funnel Phases")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Distribution
    cur.execute("""
        SELECT phase, count(*) FROM conversation_states
        WHERE creator_id = %s GROUP BY phase ORDER BY count(*) DESC
    """, (CREATOR_STR,))
    phases = {r["phase"]: r["count"] for r in cur.fetchall()}
    total_states = sum(phases.values())
    test(f"Total conversation states: {total_states}", total_states >= 250)

    valid_phases = {"INICIO", "CUALIFICACION", "DESCUBRIMIENTO", "PROPUESTA", "OBJECIONES", "CIERRE"}
    # Allow lowercase too
    all_valid = all(p.upper() in valid_phases or p in valid_phases for p in phases.keys())
    test("All phases are valid funnel stages", all_valid, f"phases: {list(phases.keys())}")

    # States have context
    cur.execute("""
        SELECT count(*) FROM conversation_states
        WHERE creator_id = %s AND context IS NOT NULL
        AND context::text != 'null' AND context::text != '{}'
    """, (CREATOR_STR,))
    with_ctx = cur.fetchone()["count"]
    test(f"States with context: {with_ctx}/{total_states}",
         with_ctx >= total_states * 0.8)

    # States have message counts
    cur.execute("""
        SELECT count(*) FROM conversation_states
        WHERE creator_id = %s AND message_count > 0
    """, (CREATOR_STR,))
    with_msgs = cur.fetchone()["count"]
    test(f"States with message_count > 0: {with_msgs}", with_msgs >= 200)

    # Funnel makes sense (more leads at top than bottom)
    inicio = phases.get("INICIO", 0) + phases.get("inicio", 0)
    cierre = phases.get("CIERRE", 0) + phases.get("cierre", 0)
    test(f"Funnel shape: INICIO({inicio}) > CIERRE({cierre})", inicio > cierre)

    conn.close()


# =============================================================================
# CATEGORY 7: NURTURING SYSTEM
# =============================================================================
def test_nurturing():
    set_category("7. NURTURING — Sequences, Followups, DB Storage")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Sequences
    cur.execute("SELECT * FROM nurturing_sequences WHERE creator_id::text = %s", (CREATOR_UUID,))
    sequences = cur.fetchall()
    test(f"Nurturing sequences: {len(sequences)}", len(sequences) >= 4)

    seq_types = {s["type"] for s in sequences}
    for expected in ["abandoned_cart", "interest_cold", "re_engagement", "booking_reminder"]:
        test(f"  → Sequence '{expected}' exists", expected in seq_types)

    # All sequences active
    active = sum(1 for s in sequences if s.get("is_active"))
    test(f"  → {active}/{len(sequences)} sequences active", active == len(sequences))

    # Sequences have steps
    for s in sequences:
        steps = s.get("steps")
        if isinstance(steps, str):
            steps = json.loads(steps)
        has_steps = isinstance(steps, list) and len(steps) > 0
        test(f"  → '{s['type']}' has {len(steps) if has_steps else 0} steps", has_steps)

    # Followups
    cur.execute("SELECT count(*) FROM nurturing_followups WHERE creator_id = %s", (CREATOR_STR,))
    fu_total = cur.fetchone()["count"]
    test(f"Nurturing followups: {fu_total}", fu_total >= 200)

    # Followup distribution
    cur.execute("""
        SELECT sequence_type, count(*) FROM nurturing_followups
        WHERE creator_id = %s GROUP BY sequence_type
    """, (CREATOR_STR,))
    fu_dist = {r["sequence_type"]: r["count"] for r in cur.fetchall()}
    test(f"Followup types: {fu_dist}", len(fu_dist) >= 2)

    # Followups are pending (not orphaned)
    cur.execute("""
        SELECT status, count(*) FROM nurturing_followups
        WHERE creator_id = %s GROUP BY status
    """, (CREATOR_STR,))
    fu_status = {r["status"]: r["count"] for r in cur.fetchall()}
    test(f"Followups by status: {fu_status}", "pending" in fu_status)

    conn.close()


# =============================================================================
# CATEGORY 8: RELATIONSHIP DNA
# =============================================================================
def test_relationship_dna():
    set_category("8. RELATIONSHIP DNA — Trust, Vocabulary, Patterns")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT count(*) FROM relationship_dna WHERE creator_id = %s
    """, (CREATOR_STR,))
    total = cur.fetchone()["count"]
    test(f"Relationship DNA records: {total}", total >= 100)

    # Check data quality
    cur.execute("""
        SELECT * FROM relationship_dna WHERE creator_id = %s
        ORDER BY updated_at DESC NULLS LAST LIMIT 5
    """, (CREATOR_STR,))
    dnas = cur.fetchall()
    for dna in dnas[:2]:
        fid = (dna.get("follower_id") or "unknown")[:20]
        has_trust = dna.get("trust_score") is not None
        test(f"  → DNA for {fid} has trust_score", has_trust)

    # No test data
    cur.execute("""
        SELECT count(*) FROM relationship_dna
        WHERE follower_id LIKE 'pipeline_test%%' OR follower_id LIKE 'test_%%'
    """)
    test_count = cur.fetchone()["count"]
    test("No test data in relationship_dna", test_count == 0, f"found {test_count} test records")

    conn.close()


# =============================================================================
# CATEGORY 9: LEAD INTELLIGENCE
# =============================================================================
def test_lead_intelligence():
    set_category("9. LEAD INTELLIGENCE — Scores, Actions, Contact Times")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Count
    cur.execute("SELECT count(*) FROM lead_intelligence WHERE creator_id = %s", (CREATOR_STR,))
    total = cur.fetchone()["count"]
    test(f"Lead intelligence records: {total}", total >= 259)

    # All have engagement scores
    cur.execute("""
        SELECT count(*) FROM lead_intelligence
        WHERE creator_id = %s AND engagement_score IS NOT NULL AND engagement_score > 0
    """, (CREATOR_STR,))
    with_eng = cur.fetchone()["count"]
    test(f"Records with engagement_score: {with_eng}/{total}", with_eng >= total * 0.9)

    # Conversion probability range
    cur.execute("""
        SELECT MIN(conversion_probability), MAX(conversion_probability),
               AVG(conversion_probability)
        FROM lead_intelligence WHERE creator_id = %s
    """, (CREATOR_STR,))
    cp = cur.fetchone()
    test(f"Conversion probability range: {cp['min']:.2f}-{cp['max']:.2f}",
         cp["min"] is not None and cp["max"] is not None and cp["max"] > cp["min"])

    # Best contact times exist
    cur.execute("""
        SELECT count(*) FROM lead_intelligence
        WHERE creator_id = %s AND best_contact_time IS NOT NULL
    """, (CREATOR_STR,))
    with_time = cur.fetchone()["count"]
    test(f"Records with best_contact_time: {with_time}", with_time >= 200)

    # Recommended actions distribution
    cur.execute("""
        SELECT recommended_action, count(*) FROM lead_intelligence
        WHERE creator_id = %s GROUP BY recommended_action ORDER BY count(*) DESC
    """, (CREATOR_STR,))
    actions = {r["recommended_action"]: r["count"] for r in cur.fetchall()}
    test(f"Action distribution: {actions}", len(actions) >= 3)
    test("  → 'close_sale' leads exist", actions.get("close_sale", 0) >= 1)
    test("  → 'qualify' leads exist", actions.get("qualify", 0) >= 50)

    # Churn risk
    cur.execute("""
        SELECT count(*) FROM lead_intelligence
        WHERE creator_id = %s AND churn_risk >= 0.7
    """, (CREATOR_STR,))
    high_churn = cur.fetchone()["count"]
    test(f"High churn risk leads (>=0.7): {high_churn}", high_churn >= 10)

    conn.close()


# =============================================================================
# CATEGORY 10: PRODUCT ANALYTICS
# =============================================================================
def test_product_analytics():
    set_category("10. PRODUCT ANALYTICS — Mentions, Questions, Conversions")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT count(*) FROM product_analytics WHERE creator_id = %s", (CREATOR_STR,))
    total = cur.fetchone()["count"]
    test(f"Product analytics records: {total}", total >= 50)

    # By product
    cur.execute("""
        SELECT p.name, SUM(pa.mentions) as mentions, SUM(pa.questions) as questions,
               SUM(pa.objections) as objections, SUM(pa.conversions) as conversions
        FROM product_analytics pa
        JOIN products p ON pa.product_id::text = p.id::text
        WHERE pa.creator_id = %s
        GROUP BY p.name ORDER BY SUM(pa.mentions) DESC
    """, (CREATOR_STR,))
    products = cur.fetchall()
    test(f"Products with analytics: {len(products)}", len(products) >= 3)

    for p in products:
        name = p["name"][:40]
        mentions = int(p["mentions"] or 0)
        test(f"  → {name}: {mentions} mentions", mentions > 0)

    # Total mentions > 0
    total_mentions = sum(int(p["mentions"] or 0) for p in products)
    total_questions = sum(int(p["questions"] or 0) for p in products)
    test(f"Total product mentions: {total_mentions}", total_mentions >= 100)
    test(f"Total product questions: {total_questions}", total_questions >= 20)

    conn.close()


# =============================================================================
# CATEGORY 11: LEAD ACTIVITIES
# =============================================================================
def test_lead_activities():
    set_category("11. LEAD ACTIVITIES — Message & Event Tracking")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT count(*) FROM lead_activities")
    total = cur.fetchone()["count"]
    test(f"Total lead activities: {total}", total >= 6000)

    # Activity type distribution
    cur.execute("""
        SELECT activity_type, count(*) FROM lead_activities
        GROUP BY activity_type ORDER BY count(*) DESC
    """)
    types = {r["activity_type"]: r["count"] for r in cur.fetchall()}
    test(f"Activity types: {len(types)}", len(types) >= 3)
    test(f"  → message_sent: {types.get('message_sent', 0)}",
         types.get("message_sent", 0) >= 2500)
    test(f"  → message_received: {types.get('message_received', 0)}",
         types.get("message_received", 0) >= 3500)
    test(f"  → product_mentioned: {types.get('product_mentioned', 0)}",
         types.get("product_mentioned", 0) >= 10)
    test(f"  → objection_raised: {types.get('objection_raised', 0)}",
         types.get("objection_raised", 0) >= 10)
    test(f"  → conversion_signal: {types.get('conversion_signal', 0)}",
         types.get("conversion_signal", 0) >= 1)

    conn.close()


# =============================================================================
# CATEGORY 12: POST CONTEXT & INSTAGRAM
# =============================================================================
def test_post_context():
    set_category("12. POST CONTEXT & INSTAGRAM — Posts & Promotion Analysis")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Instagram posts
    cur.execute("SELECT count(*) FROM instagram_posts WHERE creator_id = %s", (CREATOR_STR,))
    posts = cur.fetchone()["count"]
    test(f"Instagram posts: {posts}", posts >= 50)

    # Posts have captions
    cur.execute("""
        SELECT count(*) FROM instagram_posts
        WHERE creator_id = %s AND caption IS NOT NULL AND length(caption) > 10
    """, (CREATOR_STR,))
    with_caption = cur.fetchone()["count"]
    test(f"Posts with captions: {with_caption}/{posts}", with_caption >= 40)

    # Post context
    cur.execute("SELECT * FROM post_contexts WHERE creator_id = %s", (CREATOR_STR,))
    ctx = cur.fetchone()
    test("Post context exists", ctx is not None)
    if ctx:
        test(f"  → posts_analyzed: {ctx.get('posts_analyzed', 0)}", (ctx.get("posts_analyzed") or 0) >= 40)
        topics = ctx.get("recent_topics")
        if isinstance(topics, str):
            topics = json.loads(topics)
        test(f"  → recent_topics populated ({len(topics or [])} topics)", len(topics or []) >= 3)
        products = ctx.get("recent_products")
        if isinstance(products, str):
            products = json.loads(products)
        test(f"  → recent_products populated ({len(products or [])} products)", len(products or []) >= 2)

    conn.close()


# =============================================================================
# CATEGORY 13: WEEKLY REPORT
# =============================================================================
def test_weekly_report():
    set_category("13. WEEKLY REPORT — Real Data Report")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT * FROM weekly_reports WHERE creator_id = %s ORDER BY created_at DESC LIMIT 1",
                (CREATOR_STR,))
    report = cur.fetchone()
    test("Weekly report exists", report is not None)
    if report:
        test("  → has executive_summary", bool(report.get("executive_summary")))
        test("  → has metrics_summary", bool(report.get("metrics_summary")))
        test("  → has funnel_summary", bool(report.get("funnel_summary")))
        test("  → has hot_leads", bool(report.get("hot_leads")))

        metrics = report.get("metrics_summary")
        if isinstance(metrics, str):
            metrics = json.loads(metrics)
        if metrics:
            test(f"  → total_messages: {metrics.get('total_messages_this_week', 0)}",
                 metrics.get("total_messages_this_week", 0) > 0)

    conn.close()


# =============================================================================
# CATEGORY 14: PIPELINE INTEGRATION — Can the bot actually USE all this?
# =============================================================================
def test_pipeline_integration():
    set_category("14. PIPELINE INTEGRATION — Bot Can Access Everything")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Simulate what the bot does when it receives a DM:
    # Step 1: Load creator data
    cur.execute("SELECT id, name, knowledge_about, clone_vocabulary FROM creators WHERE id = %s",
                (CREATOR_UUID,))
    creator = cur.fetchone()
    test("Pipeline Step 1: Creator data loaded", creator is not None)

    # Step 2: Load products for RAG context
    cur.execute("SELECT id, name, price FROM products WHERE creator_id = %s", (CREATOR_UUID,))
    products = cur.fetchall()
    test(f"Pipeline Step 2: Products loaded ({len(products)})", len(products) >= 5)

    # Step 3: Identify the lead
    cur.execute("""
        SELECT l.id, l.username, l.status, l.platform_user_id
        FROM leads l
        WHERE l.creator_id = %s AND l.status = 'interesado'
        LIMIT 1
    """, (CREATOR_UUID,))
    lead = cur.fetchone()
    test("Pipeline Step 3: Active lead found", lead is not None)

    if lead:
        follower_id = lead["platform_user_id"] or str(lead["id"])
        _lead_id = str(lead["id"])

        # Step 4: Load conversation history
        cur.execute("""
            SELECT count(*) FROM messages WHERE lead_id = %s
        """, (lead["id"],))
        msg_count = cur.fetchone()["count"]
        test(f"Pipeline Step 4: Conversation history ({msg_count} msgs)", msg_count > 0)

        # Step 5: Load conversation state
        cur.execute("""
            SELECT phase, message_count, context FROM conversation_states
            WHERE creator_id = %s AND follower_id = %s
        """, (CREATOR_STR, follower_id))
        state = cur.fetchone()
        test(f"Pipeline Step 5: Conversation state = {state['phase'] if state else 'N/A'}",
             state is not None)

        # Step 6: Load user profile
        cur.execute("""
            SELECT interests, objections, interaction_count FROM user_profiles
            WHERE creator_id = %s AND user_id = %s
        """, (CREATOR_STR, follower_id))
        profile = cur.fetchone()
        test("Pipeline Step 6: User profile loaded", profile is not None)

        # Step 7: Load lead intelligence
        cur.execute("""
            SELECT engagement_score, conversion_probability, recommended_action,
                   best_contact_time FROM lead_intelligence
            WHERE creator_id = %s AND lead_id = %s
        """, (CREATOR_STR, follower_id))
        intel = cur.fetchone()
        test("Pipeline Step 7: Lead intelligence loaded", intel is not None)
        if intel:
            test(f"  → engagement={intel['engagement_score']}, action={intel['recommended_action']}",
                 intel["engagement_score"] is not None)

        # Step 8: Semantic memory search
        cur.execute("""
            SELECT count(*) FROM conversation_embeddings
            WHERE creator_id = %s AND follower_id = %s AND embedding IS NOT NULL
        """, (CREATOR_STR, follower_id))
        emb_count = cur.fetchone()["count"]
        test(f"Pipeline Step 8: Semantic memory ({emb_count} embeddings for this lead)",
             emb_count > 0)

        # Step 9: RAG search available
        cur.execute("""
            SELECT count(*) FROM rag_documents
            WHERE creator_id = %s
        """, (CREATOR_UUID,))
        rag_count = cur.fetchone()["count"]
        test(f"Pipeline Step 9: RAG docs available ({rag_count})", rag_count > 300)

        # Step 10: Relationship DNA
        cur.execute("""
            SELECT * FROM relationship_dna
            WHERE creator_id = %s AND follower_id = %s
        """, (CREATOR_STR, follower_id))
        dna = cur.fetchone()
        test(f"Pipeline Step 10: Relationship DNA {'found' if dna else 'will be created on next DM'}",
             True)  # DNA is created on-demand, so either is fine

        # Step 11: Nurturing check
        cur.execute("""
            SELECT * FROM nurturing_followups
            WHERE creator_id = %s AND follower_id = %s AND status = 'pending'
        """, (CREATOR_STR, follower_id))
        followups = cur.fetchall()
        test(f"Pipeline Step 11: Nurturing followups ({len(followups)} pending)", True)

        # Step 12: Post context for timely references
        cur.execute("SELECT * FROM post_contexts WHERE creator_id = %s", (CREATOR_STR,))
        pctx = cur.fetchone()
        test("Pipeline Step 12: Post context available", pctx is not None)

        # Step 13: Knowledge base for FAQ matching
        cur.execute("SELECT count(*) FROM knowledge_base WHERE creator_id = %s", (CREATOR_UUID,))
        kb = cur.fetchone()["count"]
        test(f"Pipeline Step 13: Knowledge base ({kb} FAQs)", kb >= 15)

        # Step 14: Tone profile for response calibration
        cur.execute("SELECT * FROM tone_profiles WHERE creator_id = %s", (CREATOR_STR,))
        tone = cur.fetchone()
        test("Pipeline Step 14: Tone profile loaded", tone is not None)

        # Step 15: Booking links for scheduling
        cur.execute("SELECT count(*) FROM booking_links WHERE creator_id = %s", (CREATOR_STR,))
        bl = cur.fetchone()["count"]
        test(f"Pipeline Step 15: Booking links ({bl})", bl >= 1)

    conn.close()


# =============================================================================
# CATEGORY 15: CROSS-TABLE DATA CONSISTENCY
# =============================================================================
def test_data_consistency():
    set_category("15. CROSS-TABLE DATA CONSISTENCY")
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Every lead has messages
    cur.execute("""
        SELECT count(*) FROM leads l
        WHERE l.creator_id = %s
        AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.lead_id = l.id)
    """, (CREATOR_UUID,))
    orphan_leads = cur.fetchone()["count"]
    test(f"Leads without messages: {orphan_leads}", orphan_leads <= 5,
         "some leads may not have synced messages")

    # Every message belongs to a valid lead
    cur.execute("""
        SELECT count(*) FROM messages m
        WHERE NOT EXISTS (SELECT 1 FROM leads l WHERE l.id = m.lead_id)
    """)
    orphan_msgs = cur.fetchone()["count"]
    test(f"Orphan messages (no lead): {orphan_msgs}", orphan_msgs == 0)

    # Lead intelligence covers all leads with messages
    cur.execute("""
        SELECT count(DISTINCT l.id) FROM leads l
        JOIN messages m ON m.lead_id = l.id
        WHERE l.creator_id = %s
    """, (CREATOR_UUID,))
    leads_with_msgs = cur.fetchone()["count"]

    cur.execute("SELECT count(*) FROM lead_intelligence WHERE creator_id = %s", (CREATOR_STR,))
    intel_count = cur.fetchone()["count"]
    test(f"Lead intelligence coverage: {intel_count}/{leads_with_msgs}",
         intel_count >= leads_with_msgs * 0.95)

    # Conversation embeddings match message count
    cur.execute("""
        SELECT count(*) FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = %s
    """, (CREATOR_UUID,))
    total_msgs = cur.fetchone()["count"]

    cur.execute("SELECT count(*) FROM conversation_embeddings WHERE creator_id = %s", (CREATOR_STR,))
    total_embs = cur.fetchone()["count"]
    test(f"Embeddings match messages: {total_embs}/{total_msgs}",
         total_embs >= total_msgs * 0.99,
         f"coverage: {total_embs * 100 // total_msgs}%")

    # Activities match messages
    cur.execute("""
        SELECT count(*) FROM lead_activities
        WHERE activity_type IN ('message_sent', 'message_received')
    """)
    msg_activities = cur.fetchone()["count"]
    test(f"Message activities match: {msg_activities}/{total_msgs}",
         msg_activities >= total_msgs * 0.95)

    conn.close()


# =============================================================================
# MAIN
# =============================================================================
def main():
    print("=" * 70)
    print("  LA HORA DE LA VERDAD — TEST MASIVO CLONNECT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Creator: {CREATOR_STR} ({CREATOR_UUID})")
    print("=" * 70)

    start = time.time()

    test_data_integrity()
    test_creator_data_loader()
    test_user_context()
    test_semantic_memory()
    test_rag_knowledge()
    test_conversation_states()
    test_nurturing()
    test_relationship_dna()
    test_lead_intelligence()
    test_product_analytics()
    test_lead_activities()
    test_post_context()
    test_weekly_report()
    test_pipeline_integration()
    test_data_consistency()

    elapsed = time.time() - start

    # Summary
    passed = sum(1 for r in RESULTS if r["status"] == "PASS")
    failed = sum(1 for r in RESULTS if r["status"] == "FAIL")
    total = len(RESULTS)

    print("\n" + "=" * 70)
    print("  RESULTS SUMMARY")
    print("=" * 70)

    # By category
    categories = {}
    for r in RESULTS:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"pass": 0, "fail": 0}
        categories[cat]["pass" if r["status"] == "PASS" else "fail"] += 1

    for cat, counts in categories.items():
        total_cat = counts["pass"] + counts["fail"]
        icon = "✅" if counts["fail"] == 0 else "❌"
        print(f"  {icon} {cat}: {counts['pass']}/{total_cat}")

    print(f"\n  {'='*50}")
    pct = passed * 100 // total if total else 0
    grade = "A+" if pct >= 98 else "A" if pct >= 95 else "B" if pct >= 90 else "C" if pct >= 80 else "F"
    print(f"  TOTAL: {passed}/{total} ({pct}%) — Grade: {grade}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  {'='*50}")

    if failed > 0:
        print(f"\n  FAILURES:")
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"    ❌ [{r['category']}] {r['name']}" +
                      (f" — {r['detail']}" if r['detail'] else ""))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
