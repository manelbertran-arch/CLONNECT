"""
Forensic Learning Audit — Run against production DB to verify learning activity.

Usage:
    railway run python3 scripts/forensic_learning_audit.py

Or with DATABASE_URL directly:
    DATABASE_URL=postgresql://... python3 scripts/forensic_learning_audit.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()


def main():
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("No DATABASE_URL set. Run with: railway run python3 scripts/forensic_learning_audit.py")
        sys.exit(1)

    if "asyncpg" in db_url:
        db_url = db_url.replace("postgresql+asyncpg", "postgresql")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    engine = create_engine(db_url)

    with engine.connect() as conn:

        print("=" * 70)
        print("FORENSIC LEARNING AUDIT — PRODUCTION DATA")
        print("=" * 70)

        # ── ENV FLAGS ──
        print("\n### FEATURE FLAGS (runtime) ###")
        for flag in [
            "ENABLE_AUTOLEARNING", "ENABLE_LEARNING_RULES", "ENABLE_GOLD_EXAMPLES",
            "ENABLE_PREFERENCE_PAIRS", "ENABLE_PREFERENCE_PROFILE",
            "ENABLE_MEMORY_ENGINE", "ENABLE_MEMORY_DECAY",
            "ENABLE_COPILOT_EVAL", "ENABLE_COPILOT_RECAL",
            "ENABLE_LEARNING_CONSOLIDATION", "ENABLE_PATTERN_ANALYZER",
        ]:
            val = os.environ.get(flag, "(not set)")
            print(f"  {flag} = {val}")

        # ── LEARNING RULES ──
        print("\n### LEARNING RULES ###")
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN source = 'auto' OR source = 'autolearning' OR source = 'system' THEN 1 END) as auto_gen,
                       COUNT(CASE WHEN source = 'manual' OR source = 'human' THEN 1 END) as manual,
                       MIN(created_at) as first_rule,
                       MAX(created_at) as last_rule
                FROM learning_rules
            """))
            row = result.fetchone()
            print(f"  Total: {row[0]} | Auto: {row[1]} | Manual: {row[2]}")
            print(f"  First: {row[3]} | Last: {row[4]}")
        except Exception as e:
            print(f"  Table missing or error: {e}")

        try:
            result = conn.execute(text("""
                SELECT id, rule_type, rule_text, source, confidence, created_at
                FROM learning_rules
                WHERE created_at > NOW() - INTERVAL '14 days'
                ORDER BY created_at DESC LIMIT 20
            """))
            rows = result.fetchall()
            print(f"\n  Rules last 14 days: {len(rows)}")
            for r in rows:
                print(f"    [{r[5]}] type={r[1]} source={r[3]} conf={r[4]}")
                print(f"      -> {str(r[2])[:120]}")
        except Exception as e:
            print(f"  Error recent rules: {e}")

        # ── GOLD EXAMPLES ──
        print("\n### GOLD EXAMPLES ###")
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) as total, MIN(created_at) as first, MAX(created_at) as last
                FROM gold_examples
            """))
            row = result.fetchone()
            print(f"  Total: {row[0]}, First: {row[1]}, Last: {row[2]}")
        except Exception as e:
            print(f"  Table missing or error: {e}")

        try:
            result = conn.execute(text("""
                SELECT id, user_message, creator_response, source, created_at
                FROM gold_examples
                WHERE created_at > NOW() - INTERVAL '14 days'
                ORDER BY created_at DESC LIMIT 10
            """))
            rows = result.fetchall()
            print(f"  Gold examples last 14 days: {len(rows)}")
            for r in rows:
                print(f"    [{r[4]}] source={r[3]}")
                print(f"      User: {str(r[1])[:80]}")
                print(f"      Creator: {str(r[2])[:80]}")
        except Exception as e:
            print(f"  Error: {e}")

        # ── PREFERENCE PAIRS ──
        print("\n### PREFERENCE PAIRS ###")
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) as total,
                       COUNT(CASE WHEN action_type IN ('approved') THEN 1 END) as approved,
                       COUNT(CASE WHEN action_type IN ('edited') THEN 1 END) as edited,
                       COUNT(CASE WHEN action_type IN ('discarded') THEN 1 END) as discarded,
                       COUNT(CASE WHEN action_type IN ('manual_override') THEN 1 END) as manual,
                       COUNT(CASE WHEN action_type IN ('historical') THEN 1 END) as historical,
                       COUNT(CASE WHEN action_type IN ('best_of_n_ranking') THEN 1 END) as best_of_n,
                       MIN(created_at) as first, MAX(created_at) as last
                FROM preference_pairs
            """))
            row = result.fetchone()
            print(f"  Total: {row[0]}")
            print(f"  Approved: {row[1]} | Edited: {row[2]} | Discarded: {row[3]}")
            print(f"  Manual: {row[4]} | Historical: {row[5]} | BestOfN: {row[6]}")
            print(f"  First: {row[7]} | Last: {row[8]}")
        except Exception as e:
            print(f"  Table missing or error: {e}")

        try:
            result = conn.execute(text("""
                SELECT action_type, COUNT(*) as cnt, MAX(created_at) as last_action
                FROM preference_pairs
                WHERE created_at > NOW() - INTERVAL '14 days'
                GROUP BY action_type
            """))
            rows = result.fetchall()
            if rows:
                print(f"  Last 14 days:")
                for r in rows:
                    print(f"    {r[0]}: {r[1]} pairs (last: {r[2]})")
        except Exception as e:
            print(f"  Error: {e}")

        # ── LEAD MEMORIES ──
        print("\n### LEAD MEMORIES ###")
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) as total, MIN(created_at) as first, MAX(created_at) as last,
                       COUNT(CASE WHEN created_at > NOW() - INTERVAL '14 days' THEN 1 END) as recent
                FROM lead_memories
            """))
            row = result.fetchone()
            print(f"  Total: {row[0]}, First: {row[1]}, Last: {row[2]}, Recent(14d): {row[3]}")
        except Exception as e:
            print(f"  Table missing or error: {e}")

        try:
            result = conn.execute(text("""
                SELECT lm.fact_text, lm.fact_type, lm.created_at, l.username
                FROM lead_memories lm
                JOIN leads l ON lm.lead_id = l.id
                WHERE lm.created_at > NOW() - INTERVAL '14 days'
                ORDER BY lm.created_at DESC LIMIT 15
            """))
            rows = result.fetchall()
            if rows:
                print(f"  Recent facts ({len(rows)}):")
                for r in rows:
                    print(f"    [{r[2]}] @{r[3]} ({r[1]}): {str(r[0])[:100]}")
        except Exception as e:
            print(f"  Error: {e}")

        # ── RELATIONSHIP DNA ──
        print("\n### RELATIONSHIP DNA ###")
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) as total,
                       MIN(created_at) as first_created,
                       MAX(updated_at) as last_updated,
                       COUNT(CASE WHEN updated_at > NOW() - INTERVAL '14 days' THEN 1 END) as recently_updated
                FROM relationship_dna
            """))
            row = result.fetchone()
            print(f"  Total: {row[0]}, First: {row[1]}, Last update: {row[2]}, Recent(14d): {row[3]}")
        except Exception as e:
            print(f"  Table missing or error: {e}")

        # ── COPILOT EVALUATIONS ──
        print("\n### COPILOT EVALUATIONS ###")
        try:
            result = conn.execute(text("""
                SELECT eval_type, COUNT(*) as cnt,
                       MIN(eval_date) as first, MAX(eval_date) as last
                FROM copilot_evaluations
                GROUP BY eval_type
            """))
            rows = result.fetchall()
            for r in rows:
                print(f"  {r[0]}: {r[1]} evaluations (first: {r[2]}, last: {r[3]})")
        except Exception as e:
            print(f"  Table missing or error: {e}")

        try:
            result = conn.execute(text("""
                SELECT eval_type, eval_date, metrics, patterns, recommendations
                FROM copilot_evaluations
                WHERE eval_date > NOW() - INTERVAL '14 days'
                ORDER BY eval_date DESC LIMIT 10
            """))
            rows = result.fetchall()
            if rows:
                print(f"  Recent evaluations ({len(rows)}):")
                for r in rows:
                    print(f"    [{r[1]}] {r[0]}: metrics={r[2]}")
                    if r[3]:
                        print(f"      patterns={r[3]}")
                    if r[4]:
                        print(f"      recommendations={r[4]}")
        except Exception as e:
            print(f"  Error: {e}")

        # ── TABLES WITH RECENT ACTIVITY ──
        print("\n### TABLES WITH RECENT ACTIVITY (14 days) ###")
        try:
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' ORDER BY table_name
            """))
            tables = [r[0] for r in result.fetchall()]
            print(f"  Total tables: {len(tables)}")

            for t in tables:
                for col in ['created_at', 'updated_at', 'timestamp']:
                    try:
                        result = conn.execute(text(
                            f"SELECT COUNT(*) FROM {t} WHERE {col} > NOW() - INTERVAL '14 days'"
                        ))
                        count = result.scalar()
                        if count and count > 0:
                            print(f"  * {t}: {count} records ({col} last 14 days)")
                            break
                    except Exception:
                        continue
        except Exception as e:
            print(f"  Error: {e}")

        # ── MESSAGE ACTIVITY ──
        print("\n### MESSAGE ACTIVITY — BOT vs CREATOR (21 days) ###")
        try:
            result = conn.execute(text("""
                SELECT
                    DATE(created_at) as dia,
                    COUNT(*) as total,
                    COUNT(CASE WHEN role = 'assistant' THEN 1 END) as bot,
                    COUNT(CASE WHEN role = 'user' THEN 1 END) as leads,
                    COUNT(CASE WHEN copilot_action IS NOT NULL THEN 1 END) as copilot_actions
                FROM messages
                WHERE created_at > NOW() - INTERVAL '21 days'
                GROUP BY DATE(created_at)
                ORDER BY dia DESC
            """))
            rows = result.fetchall()
            print(f"\n  {'Day':<12} {'Total':<8} {'Bot':<8} {'Leads':<8} {'Copilot':<8}")
            print(f"  {'-'*44}")
            for r in rows:
                print(f"  {str(r[0]):<12} {r[1]:<8} {r[2]:<8} {r[3]:<8} {r[4]:<8}")
        except Exception as e:
            print(f"  Error: {e}")

        # ── RESOLVED EXTERNALLY STATS ──
        print("\n### RESOLVED EXTERNALLY (direct creator replies) ###")
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) as total,
                       AVG((msg_metadata->>'similarity_score')::float) as avg_similarity,
                       MIN(created_at) as first, MAX(created_at) as last
                FROM messages
                WHERE copilot_action = 'resolved_externally'
            """))
            row = result.fetchone()
            print(f"  Total: {row[0]}")
            print(f"  Avg similarity (bot vs creator): {row[1]}")
            print(f"  First: {row[2]} | Last: {row[3]}")
        except Exception as e:
            print(f"  Error: {e}")

        print("\n" + "=" * 70)
        print("Run complete. Review the data above to determine")
        print("if the system has been actively learning.")
        print("=" * 70)


if __name__ == "__main__":
    main()
