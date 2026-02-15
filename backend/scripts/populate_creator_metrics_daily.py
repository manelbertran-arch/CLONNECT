"""
Populate creator_metrics_daily from messages + leads history.
IDEMPOTENT: Uses INSERT ON CONFLICT DO UPDATE.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

engine = create_engine(os.getenv("DATABASE_URL"))


def populate():
    with engine.begin() as conn:
        # Get all creator_ids that have messages
        creators = conn.execute(
            text("""
                SELECT DISTINCT l.creator_id::text
                FROM leads l
                JOIN messages m ON m.lead_id = l.id
            """)
        ).fetchall()

        total_inserted = 0

        for (creator_id,) in creators:
            print(f"Processing creator: {creator_id}")

            # Aggregate messages by day
            rows = conn.execute(
                text("""
                    SELECT
                        m.created_at::date AS day,
                        COUNT(*) AS total_messages,
                        COUNT(DISTINCT m.lead_id) AS unique_users,
                        SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END) AS msgs_received,
                        SUM(CASE WHEN m.role = 'assistant' THEN 1 ELSE 0 END) AS msgs_sent
                    FROM messages m
                    JOIN leads l ON m.lead_id = l.id
                    WHERE l.creator_id = :cid
                    GROUP BY m.created_at::date
                    ORDER BY day
                """),
                {"cid": creator_id},
            ).fetchall()

            # Get new leads per day
            new_leads_by_day = {}
            lead_rows = conn.execute(
                text("""
                    SELECT first_contact_at::date AS day, COUNT(*) AS cnt
                    FROM leads
                    WHERE creator_id = :cid AND first_contact_at IS NOT NULL
                    GROUP BY first_contact_at::date
                """),
                {"cid": creator_id},
            ).fetchall()
            for row in lead_rows:
                new_leads_by_day[row[0]] = row[1]

            # Get lead status counts by day (hot leads)
            hot_by_day = {}
            hot_rows = conn.execute(
                text("""
                    SELECT m.created_at::date AS day,
                           COUNT(DISTINCT l.id) FILTER (WHERE l.status = 'caliente') AS hot
                    FROM messages m
                    JOIN leads l ON m.lead_id = l.id
                    WHERE l.creator_id = :cid
                    GROUP BY m.created_at::date
                """),
                {"cid": creator_id},
            ).fetchall()
            for row in hot_rows:
                hot_by_day[row[0]] = row[1]

            for row in rows:
                day = row[0]
                total_messages = row[1]
                unique_users = row[2]
                total_conversations = unique_users  # each lead = 1 conversation/day
                new_leads = new_leads_by_day.get(day, 0)
                leads_hot = hot_by_day.get(day, 0)
                avg_msgs = total_messages / unique_users if unique_users > 0 else 0

                # Get creator name for the creator_id field
                creator_name = conn.execute(
                    text("SELECT name FROM creators WHERE id = :cid"),
                    {"cid": creator_id},
                ).scalar()

                if not creator_name:
                    creator_name = creator_id

                conn.execute(
                    text("""
                        INSERT INTO creator_metrics_daily
                            (creator_id, date, total_conversations, total_messages,
                             unique_users, avg_messages_per_conversation,
                             new_leads, leads_hot)
                        VALUES
                            (:creator_id, :day, :convs, :msgs, :users, :avg_msgs,
                             :new_leads, :hot)
                        ON CONFLICT ON CONSTRAINT uq_metrics_daily_creator_date
                        DO UPDATE SET
                            total_conversations = EXCLUDED.total_conversations,
                            total_messages = EXCLUDED.total_messages,
                            unique_users = EXCLUDED.unique_users,
                            avg_messages_per_conversation = EXCLUDED.avg_messages_per_conversation,
                            new_leads = EXCLUDED.new_leads,
                            leads_hot = EXCLUDED.leads_hot,
                            updated_at = NOW()
                    """),
                    {
                        "creator_id": creator_name,
                        "day": day,
                        "convs": total_conversations,
                        "msgs": total_messages,
                        "users": unique_users,
                        "avg_msgs": round(avg_msgs, 2),
                        "new_leads": new_leads,
                        "hot": leads_hot,
                    },
                )
                total_inserted += 1

        print(f"Done! Inserted/updated {total_inserted} daily metrics rows.")


if __name__ == "__main__":
    populate()
