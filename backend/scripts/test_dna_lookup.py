"""Test DNA lookup for test leads. Run: railway run python3.11 scripts/test_dna_lookup.py"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.database import SessionLocal
from sqlalchemy import text
from services.relationship_dna_repository import get_relationship_dna
from services.dm_agent_context_integration import _format_dna_for_prompt

with open('tests/cpe_data/iris_bertran/test_set_v2_stratified.json') as f:
    ts = json.load(f)
convs = ts['conversations']

s = SessionLocal()
cr = s.execute(text("SELECT id FROM creators WHERE name = 'iris_bertran' LIMIT 1")).fetchone()
creator_uuid = str(cr[0])

print(f"Testing DNA lookup for 10 leads...\n")

dna_found = 0
dna_missing = 0
for c in convs[:20]:
    u = c.get('lead_username', '')
    case_id = c['id']

    # Get lead's platform_user_id
    row = s.execute(text("""
        SELECT l.id, l.platform_user_id, l.username
        FROM leads l
        WHERE l.creator_id = CAST(:cid AS uuid) AND (l.platform_user_id = :pid OR l.username = :pid)
        LIMIT 1
    """), {'cid': creator_uuid, 'pid': u}).fetchone()

    if not row:
        print(f"  {case_id}: {u} — lead NOT FOUND")
        continue

    lead_uuid = str(row[0])
    pid = row[1]
    username = row[2]

    # Try different ID combos for DNA lookup
    dna = None
    tried = []
    for cid in ['iris_bertran', creator_uuid]:
        for fid in [pid, u, lead_uuid]:
            tried.append(f"({cid[:12]}..., {fid[:20]})")
            dna = get_relationship_dna(cid, fid)
            if dna:
                break
        if dna:
            break

    if dna:
        dna_found += 1
        formatted = _format_dna_for_prompt(dna)
        print(f"  {case_id}: {u[:20]} — DNA FOUND via ({cid[:12]}..., {fid[:20]})")
        print(f"    type={dna['relationship_type']} trust={dna['trust_score']} depth={dna['depth_level']}")
        if formatted:
            print(f"    prompt_chars={len(formatted)}")
    else:
        dna_missing += 1
        print(f"  {case_id}: {u[:20]} — NO DNA (tried: {tried[:3]}...)")
        print(f"    pid={pid} uuid={lead_uuid[:12]}")

s.close()
print(f"\nResult: {dna_found} found, {dna_missing} missing out of first 20")
