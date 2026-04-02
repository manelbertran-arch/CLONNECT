"""Check best-of-N candidates in recent copilot suggestions."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
from api.database import SessionLocal
from api.models import Message, Creator, Lead

s = SessionLocal()
c = s.query(Creator).filter_by(name="iris_bertran").first()
if not c:
    print("Creator not found")
    sys.exit(1)

msgs = (
    s.query(Message.id, Message.status, Message.content, Message.msg_metadata, Message.created_at)
    .filter(
        Message.lead_id.in_(s.query(Lead.id).filter_by(creator_id=c.id)),
        Message.role == "assistant",
    )
    .order_by(Message.created_at.desc())
    .limit(10)
    .all()
)

print(f"Last 10 bot messages for iris_bertran:\n")
for m in msgs:
    meta = m.msg_metadata or {}
    bon = meta.get("best_of_n", {})
    n_cands = len(bon.get("candidates", []))
    print(f"{m.created_at} | status={m.status} | candidates={n_cands}")
    print(f"  content: {str(m.content)[:80]}")
    if n_cands:
        for cd in bon["candidates"]:
            print(f"  T={cd['temperature']} rank={cd.get('rank','?')} conf={cd.get('confidence',0):.3f} | {cd['content'][:60]}")
    print()

# Also check if deleted_at column exists and any messages are deleted
try:
    deleted = s.query(Message.id, Message.content, Message.deleted_at).filter(
        Message.lead_id.in_(s.query(Lead.id).filter_by(creator_id=c.id)),
        Message.deleted_at.isnot(None),
    ).all()
    print(f"\nDeleted messages: {len(deleted)}")
    for d in deleted[:5]:
        print(f"  {d.deleted_at} | {str(d.content)[:60]}")
except Exception as e:
    print(f"\ndeleted_at check error: {e}")

s.close()
