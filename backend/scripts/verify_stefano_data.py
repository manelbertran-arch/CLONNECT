"""
Verify Stefano's data counts pre/post re-ingestion.

Usage:
  # Via production API:
  curl https://www.clonnectapp.com/admin/ingestion/status/5e5c2364-c99a-4484-b986-741bb84a11cf

  # Or run locally with DATABASE_URL:
  DATABASE_URL=... python scripts/verify_stefano_data.py
"""

CREATOR_ID = "5e5c2364-c99a-4484-b986-741bb84a11cf"

QUERIES = [
    ("leads", f"SELECT COUNT(*) FROM leads WHERE creator_id = '{CREATOR_ID}'"),
    ("messages", f"SELECT COUNT(*) FROM messages WHERE creator_id = '{CREATOR_ID}'"),
    ("content_chunks", f"SELECT COUNT(*) FROM content_chunks WHERE creator_id = '{CREATOR_ID}'"),
    ("instagram_posts", f"SELECT COUNT(*) FROM instagram_posts WHERE creator_id = '{CREATOR_ID}'"),
    ("products", f"SELECT COUNT(*) FROM products WHERE creator_id = '{CREATOR_ID}'"),
    ("follower_memories", f"SELECT COUNT(*) FROM follower_memories WHERE creator_id = '{CREATOR_ID}'"),
    ("nurturing_followups", f"SELECT COUNT(*) FROM nurturing_followups WHERE creator_id = '{CREATOR_ID}'"),
]

if __name__ == "__main__":
    import os
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("No DATABASE_URL set. Use the API endpoint instead:")
        print(f"  curl https://www.clonnectapp.com/admin/ingestion/status/{CREATOR_ID}")
        print()
        print("Queries for manual execution:")
        for name, query in QUERIES:
            print(f"  {name}: {query}")
    else:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_url)
        with engine.connect() as conn:
            print(f"Data counts for creator {CREATOR_ID}:")
            for name, query in QUERIES:
                try:
                    result = conn.execute(text(query)).scalar()
                    print(f"  {name}: {result}")
                except Exception as e:
                    print(f"  {name}: ERROR - {e}")
