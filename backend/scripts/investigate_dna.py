"""Investigate DNA state for test leads. Run via: railway run python3.11 scripts/investigate_dna.py"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import SessionLocal
from sqlalchemy import text

s = SessionLocal()
try:
    # 1. Total DNA records
    r = s.execute(text('SELECT COUNT(*) FROM relationship_dna')).fetchone()
    print(f'Total DNA records: {r[0]}')

    # 2. Get iris_bertran creator UUID
    cr = s.execute(text("SELECT id FROM creators WHERE name = 'iris_bertran' LIMIT 1")).fetchone()
    if not cr:
        print('ERROR: iris_bertran not found')
        sys.exit(1)
    creator_uuid = str(cr[0])
    print(f'Creator UUID: {creator_uuid}')

    # 3. DNA for iris_bertran (creator_id is varchar, may store UUID or slug)
    for cid_val in [creator_uuid, 'iris_bertran']:
        r2 = s.execute(text("SELECT COUNT(*) FROM relationship_dna WHERE creator_id = :cid"), {'cid': cid_val}).fetchone()
        print(f'DNA where creator_id="{cid_val[:20]}...": {r2[0]}')

    # 4. Sample DNA records (try both creator_id formats)
    rows = s.execute(text("""
        SELECT creator_id, follower_id, relationship_type, trust_score, depth_level,
               total_messages_analyzed, vocabulary_uses, recurring_topics
        FROM relationship_dna
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 10
    """)).fetchall()
    print(f'\nSample DNA records (any creator):')
    for row in rows:
        vocab = row[6][:3] if row[6] else []
        topics = row[7][:3] if row[7] else []
        print(f'  cid={str(row[0])[:12]}... fid={str(row[1])[:12]}... type={row[2]} trust={row[3]} depth={row[4]} msgs={row[5]} vocab={vocab} topics={topics}')

    # 5. Check test leads — find them in leads table, check msg count, check DNA
    with open('tests/cpe_data/iris_bertran/test_set_v2_stratified.json') as f:
        ts = json.load(f)
    convs = ts['conversations']

    print('\n--- Test lead analysis ---')
    leads_info = []
    for c in convs:
        u = c.get('lead_username', '')
        if not u:
            continue

        row = s.execute(text("""
            SELECT l.id, l.platform_user_id, l.username,
                   (SELECT COUNT(*) FROM messages m WHERE m.lead_id = l.id) as msg_count
            FROM leads l
            WHERE l.creator_id = CAST(:cid AS uuid)
              AND (l.platform_user_id = :pid OR l.username = :pid)
            LIMIT 1
        """), {'cid': creator_uuid, 'pid': u}).fetchone()

        if row:
            lead_uuid = str(row[0])
            pid = row[1]
            msgs = row[3]
            # Check DNA with all possible ID formats
            dna = None
            for fid_val in [lead_uuid, pid, u]:
                for cid_val in [creator_uuid, 'iris_bertran']:
                    dna = s.execute(text("""
                        SELECT relationship_type, trust_score, depth_level
                        FROM relationship_dna
                        WHERE creator_id = :cid AND follower_id = :fid
                        LIMIT 1
                    """), {'cid': cid_val, 'fid': fid_val}).fetchone()
                    if dna:
                        break
                if dna:
                    break

            dna_str = f'DNA={dna[0]} trust={dna[1]}' if dna else 'NO DNA'
            print(f'  {c["id"]:20} {u[:25]:25} msgs={msgs:3d}  {dna_str}')
            leads_info.append({
                'case_id': c['id'],
                'lead_uuid': lead_uuid,
                'platform_user_id': pid,
                'username': u,
                'msg_count': msgs,
                'has_dna': dna is not None,
                'dna_type': dna[0] if dna else None,
            })
        else:
            print(f'  {c["id"]:20} {u[:25]:25} NOT FOUND')
            leads_info.append({
                'case_id': c['id'],
                'lead_uuid': None,
                'username': u,
                'msg_count': 0,
                'has_dna': False,
            })

    # Summary
    total = len(leads_info)
    found = sum(1 for l in leads_info if l.get('lead_uuid'))
    with_msgs = sum(1 for l in leads_info if l['msg_count'] >= 2)
    with_5 = sum(1 for l in leads_info if l['msg_count'] >= 5)
    with_dna = sum(1 for l in leads_info if l['has_dna'])
    print(f'\nSummary: {total} test cases, {found} found in DB, {with_msgs} have 2+ msgs, {with_5} have 5+ msgs, {with_dna} have DNA')

    # Env vars
    print(f'\nENABLE_DNA_AUTO_CREATE: {os.getenv("ENABLE_DNA_AUTO_CREATE", "NOT SET")}')
    print(f'ENABLE_DNA_AUTO_ANALYZE: {os.getenv("ENABLE_DNA_AUTO_ANALYZE", "NOT SET")}')

    # Eligible for DNA creation
    eligible = [l for l in leads_info if l['msg_count'] >= 5 and not l['has_dna'] and l.get('lead_uuid')]
    print(f'\nEligible for DNA creation (5+ msgs, no DNA): {len(eligible)}')
    for l in eligible[:15]:
        print(f'  {l["case_id"]}: {l["lead_uuid"]} ({l["username"][:20]}) msgs={l["msg_count"]}')

    # Save for step 2
    with open('/tmp/dna_eligible_leads.json', 'w') as f:
        json.dump(leads_info, f, indent=2)
    print(f'\nSaved lead info to /tmp/dna_eligible_leads.json')

finally:
    s.close()
