"""
CCEE Business Metrics (I1-I4)

Queries production DB for business impact metrics:
  I1 — Lead response rate: % leads that reply after bot message
  I2 — Conversation continuation: avg turns after bot intervention
  I3 — Escalation rate: % convos where creator took over (lower = better)
  I4 — Funnel progression: % leads whose status advanced
"""

import os
from typing import Any, Dict, Optional

import psycopg2


def _get_conn():
    """Get DB connection (same pattern as style_profile_builder)."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(url)


def _resolve_creator_uuid(conn, creator_slug: str) -> Optional[str]:
    """Resolve creator slug (e.g. 'iris_bertran') to UUID."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM creators WHERE name = %s", (creator_slug,))
    row = cur.fetchone()
    cur.close()
    return str(row[0]) if row else None


def score_i1_lead_response_rate(conn, creator_uuid: str) -> Dict[str, Any]:
    """I1: % of leads that sent at least one message after receiving a bot message.

    Higher = bot engages leads effectively.
    """
    cur = conn.cursor()
    cur.execute("""
        WITH bot_leads AS (
            SELECT DISTINCT m.lead_id
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            WHERE l.creator_id = %s
              AND m.role = 'assistant'
              AND m.deleted_at IS NULL
              AND m.created_at > NOW() - INTERVAL '90 days'
        ),
        responded_leads AS (
            SELECT DISTINCT m.lead_id
            FROM messages m
            JOIN bot_leads bl ON bl.lead_id = m.lead_id
            WHERE m.role = 'user'
              AND m.deleted_at IS NULL
              AND m.created_at > (
                  SELECT MIN(m2.created_at)
                  FROM messages m2
                  WHERE m2.lead_id = m.lead_id AND m2.role = 'assistant'
              )
        )
        SELECT
            (SELECT COUNT(*) FROM bot_leads) AS total_bot_leads,
            (SELECT COUNT(*) FROM responded_leads) AS responded
    """, (creator_uuid,))
    row = cur.fetchone()
    cur.close()

    total = row[0] if row else 0
    responded = row[1] if row else 0
    rate = responded / max(total, 1)

    return {
        "score": round(rate * 100, 2),
        "detail": {"total_bot_leads": total, "responded": responded, "rate": round(rate, 4)},
    }


def score_i2_conversation_continuation(conn, creator_uuid: str) -> Dict[str, Any]:
    """I2: Average number of user messages after first bot message per lead.

    Higher = bot keeps conversations going.
    """
    cur = conn.cursor()
    cur.execute("""
        WITH first_bot AS (
            SELECT m.lead_id, MIN(m.created_at) AS first_bot_at
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            WHERE l.creator_id = %s
              AND m.role = 'assistant'
              AND m.deleted_at IS NULL
              AND m.created_at > NOW() - INTERVAL '90 days'
            GROUP BY m.lead_id
        ),
        post_bot_msgs AS (
            SELECT fb.lead_id, COUNT(*) AS msg_count
            FROM messages m
            JOIN first_bot fb ON fb.lead_id = m.lead_id
            WHERE m.role = 'user'
              AND m.deleted_at IS NULL
              AND m.created_at > fb.first_bot_at
            GROUP BY fb.lead_id
        )
        SELECT
            COUNT(*) AS leads_with_continuation,
            COALESCE(AVG(msg_count), 0) AS avg_turns,
            COALESCE(MAX(msg_count), 0) AS max_turns
        FROM post_bot_msgs
    """, (creator_uuid,))
    row = cur.fetchone()
    cur.close()

    leads = row[0] if row else 0
    avg_turns = float(row[1]) if row else 0.0
    # Score: 0 turns = 0, 5+ turns = 100
    score = min(100.0, avg_turns * 20.0)

    return {
        "score": round(score, 2),
        "detail": {
            "leads_with_continuation": leads,
            "avg_turns_after_bot": round(avg_turns, 2),
            "max_turns": row[2] if row else 0,
        },
    }


def score_i3_escalation_rate(conn, creator_uuid: str) -> Dict[str, Any]:
    """I3: % of conversations where creator manually intervened after bot.

    Lower escalation = better clone. Score = (1 - rate) * 100.
    """
    cur = conn.cursor()
    cur.execute("""
        WITH bot_convos AS (
            SELECT DISTINCT m.lead_id
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            WHERE l.creator_id = %s
              AND m.role = 'assistant'
              AND m.deleted_at IS NULL
              AND m.created_at > NOW() - INTERVAL '90 days'
        ),
        escalated AS (
            SELECT DISTINCT m.lead_id
            FROM messages m
            JOIN bot_convos bc ON bc.lead_id = m.lead_id
            WHERE m.deleted_at IS NULL
              AND (
                  m.copilot_action = 'manual_override'
                  OR m.approved_by IS NOT NULL
              )
              AND m.created_at > NOW() - INTERVAL '90 days'
        )
        SELECT
            (SELECT COUNT(*) FROM bot_convos) AS total,
            (SELECT COUNT(*) FROM escalated) AS escalated
    """, (creator_uuid,))
    row = cur.fetchone()
    cur.close()

    total = row[0] if row else 0
    escalated = row[1] if row else 0
    rate = escalated / max(total, 1)

    return {
        "score": round((1 - rate) * 100, 2),
        "detail": {"total_bot_convos": total, "escalated": escalated, "rate": round(rate, 4)},
    }


def score_i4_funnel_progression(conn, creator_uuid: str) -> Dict[str, Any]:
    """I4: % of leads that progressed in status after bot interaction.

    Checks if leads moved from lower to higher status stages.
    """
    cur = conn.cursor()
    # Status progression: nuevo → interesado → caliente → cliente
    cur.execute("""
        WITH bot_leads AS (
            SELECT DISTINCT l.id, l.status, l.score
            FROM leads l
            JOIN messages m ON m.lead_id = l.id
            WHERE l.creator_id = %s
              AND m.role = 'assistant'
              AND m.deleted_at IS NULL
              AND m.created_at > NOW() - INTERVAL '90 days'
        ),
        progressed AS (
            SELECT id FROM bot_leads
            WHERE status IN ('interesado', 'caliente', 'cliente')
               OR score >= 40
        )
        SELECT
            (SELECT COUNT(*) FROM bot_leads) AS total,
            (SELECT COUNT(*) FROM progressed) AS progressed
    """, (creator_uuid,))
    row = cur.fetchone()
    cur.close()

    total = row[0] if row else 0
    progressed = row[1] if row else 0
    rate = progressed / max(total, 1)

    return {
        "score": round(rate * 100, 2),
        "detail": {"total_bot_leads": total, "progressed": progressed, "rate": round(rate, 4)},
    }


def score_business_metrics(creator_slug: str) -> Dict[str, Any]:
    """Compute all business metrics (I1-I4) for a creator.

    Returns aggregate score and per-metric breakdown.
    """
    conn = _get_conn()
    try:
        creator_uuid = _resolve_creator_uuid(conn, creator_slug)
        if not creator_uuid:
            return {
                "score": 50.0,
                "detail": f"creator '{creator_slug}' not found",
                "I1": {"score": 50.0}, "I2": {"score": 50.0},
                "I3": {"score": 50.0}, "I4": {"score": 50.0},
            }

        i1 = score_i1_lead_response_rate(conn, creator_uuid)
        i2 = score_i2_conversation_continuation(conn, creator_uuid)
        i3 = score_i3_escalation_rate(conn, creator_uuid)
        i4 = score_i4_funnel_progression(conn, creator_uuid)

        aggregate = (i1["score"] + i2["score"] + i3["score"] + i4["score"]) / 4

        return {
            "score": round(aggregate, 2),
            "I1_lead_response_rate": i1,
            "I2_conversation_continuation": i2,
            "I3_escalation_rate": i3,
            "I4_funnel_progression": i4,
        }
    finally:
        conn.close()
