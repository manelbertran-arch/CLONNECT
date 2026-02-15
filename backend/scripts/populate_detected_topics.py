"""
Populate detected_topics from follower_memories interests + products_discussed.
IDEMPOTENT: Deletes existing rows for the period before inserting.
"""
import json
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

engine = create_engine(os.getenv("DATABASE_URL"))


def populate():
    with engine.begin() as conn:
        # Get all follower_memories with non-empty interests
        memories = conn.execute(
            text("""
                SELECT creator_id, follower_id, interests::text, products_discussed::text
                FROM follower_memories
                WHERE interests::text != '[]' OR products_discussed::text != '[]'
            """)
        ).fetchall()

        # Aggregate topics by creator
        # Structure: {creator_id: {topic_label: {type, count, users set}}}
        topics_by_creator = defaultdict(lambda: defaultdict(lambda: {"type": "interest", "count": 0, "users": set()}))

        for mem in memories:
            creator_id = mem[0]
            follower_id = mem[1]

            try:
                interests = json.loads(mem[2]) if mem[2] else []
            except Exception:
                interests = []

            try:
                products = json.loads(mem[3]) if mem[3] else []
            except Exception:
                products = []

            for interest in interests:
                if interest and isinstance(interest, str) and len(interest) > 1:
                    key = interest.lower().strip()
                    topics_by_creator[creator_id][key]["type"] = "interest"
                    topics_by_creator[creator_id][key]["count"] += 1
                    topics_by_creator[creator_id][key]["users"].add(follower_id)

            for product in products:
                if product and isinstance(product, str) and len(product) > 1:
                    key = product.strip()
                    topics_by_creator[creator_id][key]["type"] = "product_interest"
                    topics_by_creator[creator_id][key]["count"] += 1
                    topics_by_creator[creator_id][key]["users"].add(follower_id)

        # Use a 30-day period ending today
        period_end = date.today()
        period_start = period_end - timedelta(days=30)

        # Delete existing for this period to be idempotent
        conn.execute(
            text("DELETE FROM detected_topics WHERE period_start = :ps AND period_end = :pe"),
            {"ps": period_start, "pe": period_end},
        )

        total = 0
        for creator_id, topics in topics_by_creator.items():
            for topic_label, data in topics.items():
                conn.execute(
                    text("""
                        INSERT INTO detected_topics
                            (creator_id, period_start, period_end, topic_label, topic_type,
                             message_count, unique_users, keywords)
                        VALUES
                            (:creator_id, :period_start, :period_end, :topic_label, :topic_type,
                             :message_count, :unique_users, CAST(:keywords AS json))
                    """),
                    {
                        "creator_id": creator_id,
                        "period_start": period_start,
                        "period_end": period_end,
                        "topic_label": topic_label,
                        "topic_type": data["type"],
                        "message_count": data["count"],
                        "unique_users": len(data["users"]),
                        "keywords": json.dumps([topic_label]),
                    },
                )
                total += 1

        print(f"Done! Inserted {total} detected_topics across {len(topics_by_creator)} creators.")


if __name__ == "__main__":
    populate()
