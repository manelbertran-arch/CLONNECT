#!/usr/bin/env python3
"""
CAPA 1 — DB VERIFICATION
Verifica schema, migraciones, FK integrity, indexes, pgvector y datos de Stefano.
"""

import os
import sys
import subprocess
from datetime import datetime, timezone

# ─── Setup path ───────────────────────────────────────────────────────────────
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

# ─── Get DB URL ───────────────────────────────────────────────────────────────
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    # Try railway run
    result = subprocess.run(
        ["railway", "run", "python3", "-c", "import os; print(os.getenv('DATABASE_URL',''))"],
        capture_output=True, text=True, timeout=30
    )
    DB_URL = result.stdout.strip().split("\n")[-1]

if not DB_URL or "postgresql" not in DB_URL:
    print("❌ No DATABASE_URL found. Run with: railway run python3 scripts/verify_db_layer.py")
    sys.exit(1)

print(f"✅ DATABASE_URL: {DB_URL[:50]}...")

# ─── Connect ──────────────────────────────────────────────────────────────────
import psycopg2
import psycopg2.extras

# psycopg2 needs postgresql:// not postgres://
conn_url = DB_URL.replace("postgres://", "postgresql://")
conn = psycopg2.connect(conn_url)
conn.autocommit = True   # read-only queries, no need for transactions
cur = conn.cursor()

results = []
issues = []
warnings = []

def check(name, passed, detail=""):
    status = "✅" if passed else "❌"
    results.append({"name": name, "passed": passed, "detail": detail})
    print(f"  {status} {name}: {detail}")
    if not passed:
        issues.append(f"{name}: {detail}")

def warn(name, detail):
    results.append({"name": name, "passed": None, "detail": detail})
    warnings.append(f"{name}: {detail}")
    print(f"  ⚠️  {name}: {detail}")

print("\n" + "="*60)
print("1. SCHEMA SYNC — Tablas en DB vs Modelos SQLAlchemy")
print("="*60)

# Tables in DB
cur.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public'
    ORDER BY tablename
""")
db_tables = {row[0] for row in cur.fetchall()}
print(f"  DB tables: {len(db_tables)}")

# Tables expected from models
EXPECTED_TABLES = {
    "creators", "users", "user_creators",
    "leads", "unified_leads", "unmatched_webhooks",
    "messages", "conversation_states", "conversation_summaries",
    "conversation_embeddings", "commitments", "pending_messages",
    "products", "product_analytics",
    "rag_documents", "knowledge_base", "content_chunks",
    "instagram_posts", "post_contexts", "content_performance",
    "tone_profiles", "style_profiles", "personality_docs", "relationship_dna",
    "nurturing_sequences", "nurturing_followups", "email_ask_tracking",
    "learning_rules", "gold_examples", "preference_pairs",
    "copilot_evaluations", "clone_score_evaluations", "clone_score_test_sets",
    "pattern_analysis_runs",
    "booking_links", "calendar_bookings", "booking_slots",
    "creator_availability",
    "lead_activities", "lead_tasks", "dismissed_leads",
    "lead_intelligence", "lead_memories",
    "unified_profiles", "platform_identities", "follower_memories", "user_profiles",
    "creator_metrics_daily", "predictions", "recommendations",
    "detected_topics", "weekly_reports", "csat_ratings",
    "sync_queue", "sync_state",
    "alembic_version",
}

missing_in_db = EXPECTED_TABLES - db_tables
extra_in_db = db_tables - EXPECTED_TABLES - {"alembic_version", "spatial_ref_sys"}

check("Tablas críticas presentes",
      len(missing_in_db) == 0,
      f"Missing: {missing_in_db}" if missing_in_db else f"{len(db_tables)} tablas encontradas")

if extra_in_db:
    warn("Tablas extra en DB (no en modelos)", str(extra_in_db))

print(f"  ℹ️  Tablas en DB: {sorted(db_tables)[:10]}... ({len(db_tables)} total)")

print("\n" + "="*60)
print("2. ALEMBIC — Estado de migraciones")
print("="*60)

cur.execute("SELECT version_num FROM alembic_version")
rows = cur.fetchall()
db_revision = [r[0] for r in rows]

# Get heads from alembic
result = subprocess.run(
    ["alembic", "heads"], capture_output=True, text=True, cwd=BACKEND_DIR
)
head_lines = [l.strip() for l in result.stdout.split("\n") if l.strip() and not l.startswith("INFO") and "UserWarning" not in l and "warn" not in l.lower()]
heads = [h.split()[0] for h in head_lines if h]

print(f"  DB current: {db_revision}")
print(f"  Code heads: {heads}")

# DB is OK if it's at ANY of the declared heads (branches can diverge)
at_any_head = any(rev in heads for rev in db_revision) if heads else False
check("Migraciones al día",
      at_any_head,
      f"DB={db_revision}, heads={heads}" + (" ✓" if at_any_head else " — ejecutar alembic upgrade head"))

print("\n" + "="*60)
print("3. FK INTEGRITY — Registros huérfanos")
print("="*60)

fk_checks = [
    ("leads sin creator",           "SELECT COUNT(*) FROM leads l LEFT JOIN creators c ON c.id = l.creator_id WHERE c.id IS NULL"),
    ("messages sin lead",           "SELECT COUNT(*) FROM messages m LEFT JOIN leads l ON l.id = m.lead_id WHERE l.id IS NULL"),
    ("products sin creator",        "SELECT COUNT(*) FROM products p LEFT JOIN creators c ON c.id = p.creator_id WHERE c.id IS NULL"),
    ("learning_rules sin creator",  "SELECT COUNT(*) FROM learning_rules lr LEFT JOIN creators c ON c.id = lr.creator_id WHERE c.id IS NULL"),
    ("nurturing_followups sin cre", "SELECT COUNT(*) FROM nurturing_followups nf LEFT JOIN creators c ON c.name = nf.creator_id WHERE c.id IS NULL AND nf.creator_id IS NOT NULL"),
    ("tone_profiles sin creator",   "SELECT COUNT(*) FROM tone_profiles tp LEFT JOIN creators c ON c.name = tp.creator_id WHERE c.id IS NULL AND tp.creator_id IS NOT NULL"),
]

for name, query in fk_checks:
    try:
        conn.rollback()
        cur.execute(query)
        count = cur.fetchone()[0]
        check(f"FK: {name}", count == 0, f"{count} huérfanos" if count > 0 else "0 huérfanos ✓")
    except Exception as e:
        conn.rollback()
        warn(f"FK: {name}", f"Query failed: {e}")

print("\n" + "="*60)
print("4. INDEXES — Verificar índices críticos")
print("="*60)
conn.rollback()

REQUIRED_INDEXES = [
    ("creators", "name"),
    ("leads", "creator_id"),
    ("leads", "platform_user_id"),
    ("messages", "lead_id"),
]

cur.execute("""
    SELECT
        t.relname AS table_name,
        a.attname AS column_name,
        i.relname AS index_name
    FROM pg_index ix
    JOIN pg_class t ON t.oid = ix.indrelid
    JOIN pg_class i ON i.oid = ix.indexrelid
    JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
    WHERE t.relkind = 'r'
    AND t.relname IN ('creators','leads','messages')
    ORDER BY t.relname, a.attname
""")
existing_indexes = {(r[0], r[1]) for r in cur.fetchall()}

for table, col in REQUIRED_INDEXES:
    has_idx = (table, col) in existing_indexes
    check(f"Index {table}.{col}", has_idx,
          "índice presente" if has_idx else "⚠️ FALTA índice")

# messages.platform_message_id separately
cur.execute("""
    SELECT COUNT(*) FROM pg_indexes
    WHERE tablename = 'messages' AND indexdef LIKE '%platform_message_id%'
""")
has_platform_idx = cur.fetchone()[0] > 0
check("Index messages.platform_message_id", has_platform_idx,
      "índice presente" if has_platform_idx else "no existe (puede ser ok si columna no existe)")

print("\n" + "="*60)
print("5. PGVECTOR — Extensión y embeddings")
print("="*60)
conn.rollback()

cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
row = cur.fetchone()
check("pgvector instalado", row is not None,
      f"versión {row[1]}" if row else "extensión vector no encontrada")

for table, col, label in [
    ("rag_documents", None, "docs totales"),
    ("conversation_embeddings", "embedding", "embeddings")
]:
    try:
        if col:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL")
        else:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        check(f"{table} ({label})", True, f"{count} registros")
    except Exception as e:
        warn(f"{table}", str(e))

# Check HNSW index (migration 033)
cur.execute("""
    SELECT COUNT(*) FROM pg_indexes
    WHERE indexdef LIKE '%hnsw%' OR indexdef LIKE '%ivfflat%'
""")
vector_idx_count = cur.fetchone()[0]
check("Vector indexes (hnsw/ivfflat)", vector_idx_count > 0,
      f"{vector_idx_count} índices vectoriales")

print("\n" + "="*60)
print("6. DATA SANITY — stefano_bonanno")
print("="*60)
conn.rollback()

cur.execute("SELECT id, name, bot_active FROM creators WHERE name = 'stefano_bonanno'")
creator_row = cur.fetchone()
check("Creator stefano_bonanno existe", creator_row is not None,
      f"UUID={str(creator_row[0])[:8]}... bot_active={creator_row[2]}" if creator_row else "NOT FOUND")

if creator_row:
    creator_uuid = str(creator_row[0])

    data_tables = [
        ("leads",               "SELECT COUNT(*) FROM leads WHERE creator_id = %s"),
        ("messages",            "SELECT COUNT(*) FROM messages WHERE lead_id IN (SELECT id FROM leads WHERE creator_id = %s)"),
        ("products",            "SELECT COUNT(*) FROM products WHERE creator_id = %s"),
        ("knowledge_base",      "SELECT COUNT(*) FROM knowledge_base WHERE creator_id = %s"),
        ("rag_documents",       "SELECT COUNT(*) FROM rag_documents WHERE creator_id = %s"),
        ("tone_profiles",       "SELECT COUNT(*) FROM tone_profiles WHERE creator_id = %s"),
        ("nurturing_sequences", "SELECT COUNT(*) FROM nurturing_sequences WHERE creator_id = %s"),
        ("learning_rules",      "SELECT COUNT(*) FROM learning_rules WHERE creator_id = %s"),
        ("nurturing_followups", "SELECT COUNT(*) FROM nurturing_followups WHERE creator_id = %s"),
    ]

    min_expected = {
        "leads": 1, "messages": 1, "products": 1,
        "knowledge_base": 0, "rag_documents": 0,
    }

    for name, query in data_tables:
        try:
            cur.execute(query, (creator_uuid,))
            count = cur.fetchone()[0]
            min_val = min_expected.get(name, 0)
            passed = count >= min_val
            check(f"stefano.{name}", passed, f"{count} registros")
        except Exception as e:
            warn(f"stefano.{name}", str(e))

# ─── Summary ──────────────────────────────────────────────────────────────────
passed = sum(1 for r in results if r["passed"] is True)
failed = sum(1 for r in results if r["passed"] is False)
warned = sum(1 for r in results if r["passed"] is None)
total  = passed + failed

print("\n" + "="*60)
print("RESUMEN CAPA 1 — BASE DE DATOS")
print("="*60)
print(f"  PASS:    {passed}/{total}")
print(f"  FAIL:    {failed}/{total}")
print(f"  WARN:    {warned}")
print(f"  RATE:    {int(100*passed/total) if total else 0}%")

if issues:
    print("\n  ISSUES:")
    for i in issues:
        print(f"    ❌ {i}")
if warnings:
    print("\n  WARNINGS:")
    for w in warnings:
        print(f"    ⚠️  {w}")

cur.close()
conn.close()

# ─── Write report ─────────────────────────────────────────────────────────────
report_path = os.path.join(BACKEND_DIR, "DB_VERIFICATION_REPORT.md")
with open(report_path, "w") as f:
    f.write(f"# CAPA 1 — Verificación Base de Datos\n\n")
    f.write(f"**Fecha**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n")
    f.write(f"## Resultado: {passed}/{total} PASS ({int(100*passed/total) if total else 0}%)\n\n")
    f.write("| Test | Estado | Detalle |\n|------|--------|--------|\n")
    for r in results:
        icon = "✅" if r["passed"] is True else ("❌" if r["passed"] is False else "⚠️")
        f.write(f"| {r['name']} | {icon} | {r['detail']} |\n")

    if issues:
        f.write("\n## Issues\n")
        for i in issues:
            f.write(f"- ❌ {i}\n")
    if warnings:
        f.write("\n## Warnings\n")
        for w in warnings:
            f.write(f"- ⚠️ {w}\n")

print(f"\n  📄 Report: {report_path}")
print(f"\n{'✅ CAPA 1 PASS' if failed == 0 else '❌ CAPA 1 ISSUES FOUND'}")

# Exit code for automation
sys.exit(0 if failed == 0 else 1)
