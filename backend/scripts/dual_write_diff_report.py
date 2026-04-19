"""
ARC2 A2.4 — Dual-Write Drift Report.

Compares write counts between legacy memory systems and arc2_lead_memories
to detect dual-write coverage gaps.

Usage:
    .venv/bin/python3.11 -m scripts.dual_write_diff_report
    .venv/bin/python3.11 -m scripts.dual_write_diff_report --json
"""

import argparse
import json
import sys


def _get_counts() -> dict:
    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    try:
        legacy = {}
        arc2 = {}

        # Legacy source A: follower_memories (MemoryStore JSON files proxied via FollowerMemory)
        # Approximate via DB lead_memories table using source_type heuristics
        row = session.execute(
            text("SELECT COUNT(*) FROM lead_memories WHERE is_active = true")
        ).fetchone()
        legacy["lead_memories_active"] = int(row[0]) if row else 0

        # Legacy source B: follower_memories table (ConversationMemoryService)
        try:
            row = session.execute(
                text(
                    "SELECT COUNT(*) FROM lead_memories "
                    "WHERE fact_type = '_conv_memory_state' AND is_active = true"
                )
            ).fetchone()
            legacy["conv_memory_states"] = int(row[0]) if row else 0
        except Exception:
            legacy["conv_memory_states"] = -1

        # arc2_lead_memories breakdown by last_writer
        rows = session.execute(
            text(
                "SELECT last_writer, COUNT(*) AS cnt "
                "FROM arc2_lead_memories "
                "WHERE deleted_at IS NULL "
                "GROUP BY last_writer ORDER BY cnt DESC"
            )
        ).fetchall()
        for r in rows:
            arc2[r.last_writer] = int(r.cnt)

        # arc2 by memory_type
        type_rows = session.execute(
            text(
                "SELECT memory_type, COUNT(*) AS cnt "
                "FROM arc2_lead_memories "
                "WHERE deleted_at IS NULL "
                "GROUP BY memory_type ORDER BY memory_type"
            )
        ).fetchall()
        arc2_by_type = {r.memory_type: int(r.cnt) for r in type_rows}

        # Dual-write totals (live writes only, excludes migration_*)
        dual_write_total = sum(
            v for k, v in arc2.items()
            if k.startswith("dual_write_")
        )
        migration_total = sum(
            v for k, v in arc2.items()
            if k.startswith("migration_") or k == "reextraction"
        )
        arc2_total = sum(arc2.values())

        return {
            "legacy": legacy,
            "arc2_by_writer": arc2,
            "arc2_by_type": arc2_by_type,
            "totals": {
                "arc2_total": arc2_total,
                "dual_write_live": dual_write_total,
                "migration": migration_total,
            },
        }
    finally:
        session.close()


def _print_report(counts: dict) -> None:
    legacy = counts["legacy"]
    arc2_by_writer = counts["arc2_by_writer"]
    arc2_by_type = counts["arc2_by_type"]
    totals = counts["totals"]

    print("=" * 60)
    print("ARC2 Dual-Write Drift Report")
    print("=" * 60)

    print("\n── Legacy systems ──────────────────────────────────────")
    print(f"  lead_memories (active):      {legacy['lead_memories_active']:>8}")
    print(f"  conv_memory_states (active): {legacy['conv_memory_states']:>8}")

    print("\n── arc2_lead_memories by writer ────────────────────────")
    for writer, cnt in sorted(arc2_by_writer.items(), key=lambda x: -x[1]):
        tag = " ← LIVE" if writer.startswith("dual_write_") else ""
        print(f"  {writer:<40} {cnt:>6}{tag}")

    print("\n── arc2_lead_memories by type ──────────────────────────")
    for mtype, cnt in sorted(arc2_by_type.items()):
        print(f"  {mtype:<30} {cnt:>6}")

    print("\n── Totals ──────────────────────────────────────────────")
    print(f"  arc2_total:          {totals['arc2_total']:>8}")
    print(f"  dual_write_live:     {totals['dual_write_live']:>8}  (ongoing writes)")
    print(f"  migration:           {totals['migration']:>8}  (historical backfill)")

    # Coverage ratio
    legacy_total = sum(v for v in legacy.values() if v > 0)
    if legacy_total > 0 and totals["dual_write_live"] > 0:
        ratio = totals["dual_write_live"] / legacy_total * 100
        print(f"\n  Dual-write coverage: {ratio:.1f}%  ({totals['dual_write_live']}/{legacy_total})")

    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="ARC2 dual-write drift report")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of text")
    args = parser.parse_args()

    try:
        counts = _get_counts()
    except Exception as exc:
        print(f"ERROR: Could not connect to DB — {exc}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(counts, indent=2))
    else:
        _print_report(counts)


if __name__ == "__main__":
    main()
