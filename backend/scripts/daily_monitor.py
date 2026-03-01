#!/usr/bin/env python3
"""Daily CloneScore & Copilot monitoring script.

Queries production DB for last 24h metrics:
- Copilot approval/edit/reject rates
- CloneScore from clone_score_evaluations table
- DM response count
- Targets checklist output

Usage:
    python scripts/daily_monitor.py
    python scripts/daily_monitor.py --days 7
    python scripts/daily_monitor.py --creator stefano
"""
import os
import sys
import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

# Targets
TARGETS = {
    "clone_score": 75.0,
    "copilot_approval_rate": 60.0,
    "dm_response_count_24h": 10,
    "style_fidelity": 65.0,
    "safety_score": 90.0,
}


def get_db_session():
    """Get a DB session."""
    from api.database import SessionLocal
    return SessionLocal()


def resolve_creator_id(session, creator_name: str):
    """Resolve creator name to UUID."""
    from api.models import Creator
    creator = (
        session.query(Creator)
        .filter(Creator.name.ilike(f"%{creator_name}%"))
        .first()
    )
    if not creator:
        raise ValueError(f"Creator '{creator_name}' not found")
    return creator.id


def fetch_copilot_stats(session, creator_db_id, since: datetime) -> dict:
    """Fetch copilot action stats for the period."""
    from sqlalchemy import func
    from api.models import Lead, Message

    actions = (
        session.query(
            Message.copilot_action,
            func.count(Message.id),
        )
        .join(Lead, Message.lead_id == Lead.id)
        .filter(
            Lead.creator_id == creator_db_id,
            Message.copilot_action.isnot(None),
            Message.created_at >= since,
        )
        .group_by(Message.copilot_action)
        .all()
    )

    stats = {}
    total = 0
    for action, count in actions:
        stats[action] = count
        total += count

    approved = stats.get("approved", 0)
    edited = stats.get("edited", 0)
    discarded = stats.get("discarded", 0)
    resolved_ext = stats.get("resolved_externally", 0)

    approval_rate = ((approved + edited) / total * 100) if total > 0 else 0

    return {
        "total": total,
        "approved": approved,
        "edited": edited,
        "discarded": discarded,
        "resolved_externally": resolved_ext,
        "approval_rate": round(approval_rate, 1),
        "breakdown": stats,
    }


def fetch_clone_scores(session, creator_db_id, since: datetime) -> dict:
    """Fetch CloneScore evaluations for the period."""
    from api.models import CloneScoreEvaluation

    evals = (
        session.query(CloneScoreEvaluation)
        .filter(
            CloneScoreEvaluation.creator_id == creator_db_id,
            CloneScoreEvaluation.created_at >= since,
        )
        .order_by(CloneScoreEvaluation.created_at.desc())
        .all()
    )

    if not evals:
        return {"count": 0, "latest": None, "avg_overall": None, "dimensions": {}}

    scores = [e.overall_score for e in evals if e.overall_score]
    avg_overall = sum(scores) / len(scores) if scores else 0

    # Average per dimension from the latest eval
    latest = evals[0]
    dims = latest.dimension_scores or {}

    return {
        "count": len(evals),
        "latest": {
            "overall": latest.overall_score,
            "dimensions": dims,
            "date": latest.created_at.isoformat() if latest.created_at else None,
            "sample_size": latest.sample_size,
        },
        "avg_overall": round(avg_overall, 1),
        "dimensions": dims,
    }


def fetch_dm_count(session, creator_db_id, since: datetime) -> int:
    """Count bot DM responses in the period."""
    from sqlalchemy import func
    from api.models import Lead, Message

    count = (
        session.query(func.count(Message.id))
        .join(Lead, Message.lead_id == Lead.id)
        .filter(
            Lead.creator_id == creator_db_id,
            Message.role == "assistant",
            Message.status == "sent",
            Message.created_at >= since,
        )
        .scalar()
    ) or 0

    return count


def print_report(
    creator_name: str,
    days: int,
    copilot: dict,
    clone_scores: dict,
    dm_count: int,
):
    """Print the monitoring report."""
    print(f"\n{'='*60}")
    print(f"  Daily Monitor — {creator_name}")
    print(f"  Period: last {days} day(s) ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})")
    print(f"{'='*60}")

    # DM Activity
    print(f"\n  DM Responses Sent: {dm_count}")
    dm_target = TARGETS["dm_response_count_24h"] * days
    dm_status = "PASS" if dm_count >= dm_target else "BELOW TARGET"
    print(f"  Target: >= {dm_target} | Status: {dm_status}")

    # Copilot Stats
    print(f"\n  Copilot Actions: {copilot['total']}")
    if copilot["total"] > 0:
        print(f"    Approved:  {copilot['approved']:>4d} ({copilot['approved']/copilot['total']*100:.0f}%)")
        print(f"    Edited:    {copilot['edited']:>4d} ({copilot['edited']/copilot['total']*100:.0f}%)")
        print(f"    Discarded: {copilot['discarded']:>4d} ({copilot['discarded']/copilot['total']*100:.0f}%)")
        if copilot["resolved_externally"]:
            print(f"    Resolved:  {copilot['resolved_externally']:>4d} ({copilot['resolved_externally']/copilot['total']*100:.0f}%)")
    approval_status = "PASS" if copilot["approval_rate"] >= TARGETS["copilot_approval_rate"] else "BELOW TARGET"
    print(f"  Approval Rate: {copilot['approval_rate']:.1f}% (target: >= {TARGETS['copilot_approval_rate']}%) | {approval_status}")

    # CloneScore
    print(f"\n  CloneScore Evaluations: {clone_scores['count']}")
    if clone_scores["latest"]:
        latest = clone_scores["latest"]
        overall = latest["overall"]
        cs_status = "PASS" if overall and overall >= TARGETS["clone_score"] else "BELOW TARGET"
        print(f"  Latest Overall: {overall:.1f}/100 (target: >= {TARGETS['clone_score']}) | {cs_status}")
        if latest["dimensions"]:
            print(f"  Dimensions:")
            for dim, score in latest["dimensions"].items():
                target = TARGETS.get(dim)
                marker = ""
                if target and score < target:
                    marker = f" (BELOW {target})"
                print(f"    {dim:25s} {score:.1f}{marker}")
        if latest["date"]:
            print(f"  Last eval: {latest['date']}")
    else:
        print(f"  No evaluations found in period")

    # Checklist
    print(f"\n  {'─'*56}")
    print(f"  TARGETS CHECKLIST:")
    checks = []
    checks.append(("DM count", dm_count >= dm_target))
    checks.append(("Copilot approval >= 60%", copilot["approval_rate"] >= TARGETS["copilot_approval_rate"]))
    if clone_scores["latest"] and clone_scores["latest"]["overall"]:
        checks.append(("CloneScore >= 75", clone_scores["latest"]["overall"] >= TARGETS["clone_score"]))
        dims = clone_scores["latest"]["dimensions"] or {}
        if "style_fidelity" in dims:
            checks.append(("Style fidelity >= 65", dims["style_fidelity"] >= TARGETS["style_fidelity"]))
        if "safety_score" in dims:
            checks.append(("Safety >= 90", dims["safety_score"] >= TARGETS["safety_score"]))

    passed = sum(1 for _, ok in checks if ok)
    for label, ok in checks:
        icon = "PASS" if ok else "FAIL"
        print(f"    [{icon}] {label}")

    print(f"\n  Result: {passed}/{len(checks)} targets met")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Daily CloneScore & Copilot Monitor")
    parser.add_argument("--creator", default="stefano", help="Creator name")
    parser.add_argument("--days", type=int, default=1, help="Period in days (default: 1)")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    session = get_db_session()
    try:
        creator_db_id = resolve_creator_id(session, args.creator)
        since = datetime.now(timezone.utc) - timedelta(days=args.days)

        copilot = fetch_copilot_stats(session, creator_db_id, since)
        clone_scores = fetch_clone_scores(session, creator_db_id, since)
        dm_count = fetch_dm_count(session, creator_db_id, since)

        print_report(args.creator.title(), args.days, copilot, clone_scores, dm_count)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
