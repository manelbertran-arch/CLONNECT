"""Store Manel's DPO pair and learning rules from ablation DNA review.

Usage: railway run python3 scripts/store_manel_feedback.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use direct Neon connection (not pooler) for write access
db_url = os.environ.get("DATABASE_URL", "")
if "-pooler" in db_url:
    db_url = db_url.replace("-pooler", "")
    os.environ["DATABASE_URL"] = db_url

from api.database import SessionLocal
from sqlalchemy import text

session = SessionLocal()

# 1. Get iris_bertran creator UUID
row = session.execute(
    text("SELECT id FROM creators WHERE name = 'iris_bertran' LIMIT 1")
).fetchone()
if not row:
    print("ERROR: iris_bertran not found")
    sys.exit(1)
creator_uuid = row[0]
print(f"Creator UUID: {creator_uuid}")

# ── DPO PAIR ──────────────────────────────────────────────────────────────
from api.models import PreferencePair

pair = PreferencePair(
    creator_id=creator_uuid,
    user_message="Com esta la teva mare??",
    chosen="Ja està millor",
    rejected="Ja va bé, compa \U0001f602 La teva mare està bé, gràcies.",
    action_type="evaluator_correction",
    intent="health_inquiry",
    lead_stage=None,
)
session.add(pair)
session.flush()
print(f"DPO Pair created: id={pair.id}")

# ── LEARNING RULES ────────────────────────────────────────────────────────
from api.models import LearningRule

rule1 = LearningRule(
    creator_id=creator_uuid,
    rule_text="NEVER use \U0001f602 or humor when the lead asks about medical/health topics (family illness, hospital visits)",
    pattern="health_sensitivity",
    applies_to_relationship_types=[],
    applies_to_message_types=["health_inquiry", "family_concern"],
    applies_to_lead_stages=[],
    example_bad="Ja va bé, compa \U0001f602 La teva mare està bé, gràcies.",
    example_good="Ja està millor",
    confidence=0.8,
    source="manel_eval",
)
session.add(rule1)
session.flush()
print(f"Learning Rule 1 created: id={rule1.id}")

rule2 = LearningRule(
    creator_id=creator_uuid,
    rule_text="Verify DNA vocabulary against creator's REAL messages — 'compa' is NOT in Iris's vocabulary",
    pattern="vocabulary_validation",
    applies_to_relationship_types=[],
    applies_to_message_types=[],
    applies_to_lead_stages=[],
    example_bad="Ja va bé, compa \U0001f602",
    example_good="Ja està millor",
    confidence=0.8,
    source="manel_eval",
)
session.add(rule2)
session.flush()
print(f"Learning Rule 2 created: id={rule2.id}")

session.commit()
print("\nAll 3 records committed to DB")

# Verify
count_pairs = session.execute(
    text("SELECT COUNT(*) FROM preference_pairs WHERE creator_id = :cid AND action_type = 'evaluator_correction'"),
    {"cid": str(creator_uuid)}
).scalar()
count_rules = session.execute(
    text("SELECT COUNT(*) FROM learning_rules WHERE creator_id = :cid AND source = 'manel_eval'"),
    {"cid": str(creator_uuid)}
).scalar()
print(f"Verification: {count_pairs} evaluator_correction pairs, {count_rules} manel_eval rules in DB")

session.close()
