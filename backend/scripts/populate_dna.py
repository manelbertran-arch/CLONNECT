"""Populate DNA for test leads that don't have it yet.
Run: railway run python3.11 scripts/populate_dna.py
"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import SessionLocal
from sqlalchemy import text
from services.relationship_dna_service import get_dna_service
from services.relationship_dna_repository import get_relationship_dna


def main():
    s = SessionLocal()
    cr = s.execute(text("SELECT id FROM creators WHERE name = 'iris_bertran' LIMIT 1")).fetchone()
    creator_uuid = str(cr[0])

    with open('tests/cpe_data/iris_bertran/test_set_v2_stratified.json') as f:
        ts = json.load(f)
    convs = ts['conversations']

    dna_svc = get_dna_service()
    created = 0
    failed = 0
    skipped = 0

    for c in convs:
        u = c.get('lead_username', '')
        if not u:
            continue

        row = s.execute(text("""
            SELECT l.id, l.platform_user_id
            FROM leads l
            WHERE l.creator_id = CAST(:cid AS uuid)
              AND (l.platform_user_id = :pid OR l.username = :pid)
            LIMIT 1
        """), {'cid': creator_uuid, 'pid': u}).fetchone()

        if not row:
            continue

        lead_uuid = str(row[0])
        pid = row[1]

        # Check DNA already exists
        dna = get_relationship_dna('iris_bertran', pid)
        if dna:
            skipped += 1
            continue

        # Get conversation messages for this lead
        msgs = s.execute(text("""
            SELECT role, content FROM messages
            WHERE lead_id = CAST(:lid AS uuid)
            ORDER BY created_at ASC
            LIMIT 50
        """), {'lid': lead_uuid}).fetchall()

        if len(msgs) < 5:
            print(f"  {c['id']}: {u[:20]} — only {len(msgs)} msgs, skipping")
            failed += 1
            continue

        msg_list = [{'role': r[0], 'content': r[1]} for r in msgs if r[1]]
        print(f"  {c['id']}: {u[:20]} — {len(msg_list)} msgs, analyzing...")

        try:
            result = dna_svc.analyze_and_update_dna(
                creator_id='iris_bertran',
                follower_id=pid,
                messages=msg_list,
            )
            if result:
                created += 1
                print(f"    OK: type={result.get('relationship_type', '?')} trust={result.get('trust_score', '?')}")
            else:
                failed += 1
                print(f"    FAILED: no result returned")
        except Exception as e:
            failed += 1
            print(f"    ERROR: {e}")

    s.close()
    print(f"\nDone: {skipped} already had DNA, {created} created, {failed} failed")


if __name__ == "__main__":
    main()
