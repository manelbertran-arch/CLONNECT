"""
Populate content_performance from instagram_posts.
IDEMPOTENT: Uses INSERT ON CONFLICT DO UPDATE.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

engine = create_engine(os.getenv("DATABASE_URL"))


def populate():
    with engine.begin() as conn:
        # Get all instagram posts
        posts = conn.execute(
            text("""
                SELECT
                    p.creator_id,
                    p.post_id,
                    p.caption,
                    p.media_type,
                    p.post_timestamp,
                    p.likes_count,
                    p.comments_count,
                    p.hashtags::text,
                    p.mentions::text
                FROM instagram_posts p
                ORDER BY p.post_timestamp DESC
            """)
        ).fetchall()

        total = 0
        for post in posts:
            creator_id = post[0]
            content_id = post[1]
            caption = post[2]
            media_type = post[3]
            posted_at = post[4]
            likes = post[5] or 0
            comments = post[6] or 0

            # Parse hashtags/mentions from JSON
            import json
            try:
                hashtags = json.loads(post[7]) if post[7] else []
            except Exception:
                hashtags = []
            try:
                mentions = json.loads(post[8]) if post[8] else []
            except Exception:
                mentions = []

            # Calculate engagement rate (likes + comments)
            total_engagement = likes + comments
            engagement_rate = total_engagement / max(likes, 1) if likes > 0 else 0
            save_rate = 0.0  # No save data available

            conn.execute(
                text("""
                    INSERT INTO content_performance
                        (creator_id, content_id, platform, content_type, posted_at,
                         caption, hashtags, mentions,
                         likes, comments, engagement_rate)
                    VALUES
                        (:creator_id, :content_id, 'instagram', :content_type, :posted_at,
                         :caption, CAST(:hashtags AS json), CAST(:mentions AS json),
                         :likes, :comments, :engagement_rate)
                    ON CONFLICT ON CONSTRAINT uq_content_perf_content_id
                    DO UPDATE SET
                        likes = EXCLUDED.likes,
                        comments = EXCLUDED.comments,
                        engagement_rate = EXCLUDED.engagement_rate,
                        last_updated = NOW()
                """),
                {
                    "creator_id": creator_id,
                    "content_id": content_id,
                    "content_type": media_type,
                    "posted_at": posted_at,
                    "caption": caption,
                    "hashtags": json.dumps(hashtags),
                    "mentions": json.dumps(mentions),
                    "likes": likes,
                    "comments": comments,
                    "engagement_rate": round(engagement_rate, 4),
                },
            )
            total += 1

        print(f"Done! Inserted/updated {total} content_performance rows from {total} instagram posts.")


if __name__ == "__main__":
    populate()
