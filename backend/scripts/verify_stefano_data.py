"""
Verify Stefano's data counts pre/post re-ingestion.

Usage:
  # Via production API:
  curl https://www.clonnectapp.com/admin/ingestion/status/5e5c2364-c99a-4484-b986-741bb84a11cf

  # Or run locally with DATABASE_URL:
  DATABASE_URL=... python scripts/verify_stefano_data.py
"""

CREATOR_ID = "5e5c2364-c99a-4484-b986-741bb84a11cf"

TABLES = [
    "leads",
    "messages",
    "content_chunks",
    "instagram_posts",
    "products",
    "follower_memories",
    "nurturing_followups",
]

if __name__ == "__main__":
    import os
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("No DATABASE_URL set. Use the API endpoint instead:")
        print(f"  curl https://www.clonnectapp.com/admin/ingestion/status/{CREATOR_ID}")
        print()
        print("Tables to check:", ", ".join(TABLES))
    else:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_url)
        with engine.connect() as conn:
            print(f"Data counts for creator {CREATOR_ID}:")
            for table in TABLES:
                try:
                    result = conn.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE creator_id = :cid"),
                        {"cid": CREATOR_ID}
                    ).scalar()
                    print(f"  {table}: {result}")
                except Exception as e:
                    print(f"  {table}: ERROR - {e}")
