#!/usr/bin/env python3
"""Analyze PromptSliceCompactor shadow log data.

Usage:
  python3 scripts/analyze_compactor_shadow.py [--hours N] [--creator-id UUID] [--output {md,json,csv}]
"""

import argparse
import csv
import json
import os
import sys

import sqlalchemy as sa

# ── CLI ──────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Analyze PromptSliceCompactor shadow log data."
)
parser.add_argument(
    "--hours",
    type=int,
    default=24,
    metavar="N",
    help="Analysis window in hours (default: 24)",
)
parser.add_argument(
    "--creator-id",
    default=None,
    metavar="UUID",
    help="Optional: filter to one creator UUID",
)
parser.add_argument(
    "--output",
    choices=["md", "json", "csv"],
    default="md",
    help="Output format: md (default), json, or csv",
)
args = parser.parse_args()

# ── DB connection ─────────────────────────────────────────────────────────────

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
    sys.exit(1)

try:
    engine = sa.create_engine(DATABASE_URL)
    # Test connectivity eagerly
    with engine.connect() as _conn:
        pass
except Exception as exc:
    print(f"ERROR: Could not connect to database: {exc}", file=sys.stderr)
    sys.exit(1)

# ── Helper: optional creator_id clause ───────────────────────────────────────

CREATOR_CLAUSE = "AND l.creator_id = :creator_id" if args.creator_id else ""
CREATOR_CLAUSE_NOALIAS = "AND creator_id = :creator_id" if args.creator_id else ""

params: dict = {"hours": args.hours}
if args.creator_id:
    params["creator_id"] = args.creator_id

# ── Query 1: Total turns and compaction rate ──────────────────────────────────

q_summary = sa.text(f"""
    SELECT
        COUNT(*) AS total_turns,
        SUM(CASE WHEN compaction_applied THEN 1 ELSE 0 END) AS compacted_turns,
        ROUND(
            100.0 * SUM(CASE WHEN compaction_applied THEN 1 ELSE 0 END)
            / NULLIF(COUNT(*), 0),
            1
        ) AS compaction_pct
    FROM context_compactor_shadow_log
    WHERE timestamp > NOW() - INTERVAL ':hours hours'
    {CREATOR_CLAUSE_NOALIAS}
""".replace("':hours hours'", f"'{args.hours} hours'"))

# ── Query 2: Per-creator reason breakdown ─────────────────────────────────────

q_reasons = sa.text(f"""
    SELECT
        c.name AS creator_slug,
        l.reason,
        COUNT(*) AS count
    FROM context_compactor_shadow_log l
    JOIN creators c ON c.id = l.creator_id
    WHERE l.timestamp > NOW() - INTERVAL '{args.hours} hours'
    {CREATOR_CLAUSE}
    GROUP BY c.name, l.reason
    ORDER BY c.name, count DESC
""")

# ── Query 3: Top 5 sections most truncated ────────────────────────────────────

q_sections = sa.text(f"""
    SELECT
        section_name,
        COUNT(*) AS truncation_count
    FROM context_compactor_shadow_log,
         jsonb_array_elements_text(sections_truncated) AS section_name
    WHERE timestamp > NOW() - INTERVAL '{args.hours} hours'
    {CREATOR_CLAUSE_NOALIAS}
    GROUP BY section_name
    ORDER BY truncation_count DESC
    LIMIT 5
""")

# ── Query 4: Average divergence ───────────────────────────────────────────────

q_divergence = sa.text(f"""
    SELECT
        ROUND(AVG(divergence_chars), 0) AS avg_divergence_chars,
        MAX(divergence_chars) AS max_divergence_chars,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY divergence_chars) AS p95_divergence
    FROM context_compactor_shadow_log
    WHERE timestamp > NOW() - INTERVAL '{args.hours} hours'
    {CREATOR_CLAUSE_NOALIAS}
""")

# ── Query 5: Extreme cases (divergence > 2000) ────────────────────────────────

q_extreme = sa.text(f"""
    SELECT
        l.timestamp,
        c.name AS creator_slug,
        l.actual_chars_before,
        l.shadow_chars_after,
        l.divergence_chars,
        l.reason
    FROM context_compactor_shadow_log l
    JOIN creators c ON c.id = l.creator_id
    WHERE l.timestamp > NOW() - INTERVAL '{args.hours} hours'
      AND l.divergence_chars > 2000
      {CREATOR_CLAUSE}
    ORDER BY l.divergence_chars DESC
    LIMIT 10
""")

# ── Execute queries ───────────────────────────────────────────────────────────

with engine.connect() as conn:
    summary_row = conn.execute(q_summary, params if args.creator_id else {"hours": args.hours}).fetchone()
    reasons_rows = conn.execute(q_reasons, params if args.creator_id else {"hours": args.hours}).fetchall()
    sections_rows = conn.execute(q_sections, params if args.creator_id else {"hours": args.hours}).fetchall()
    divergence_row = conn.execute(q_divergence, params if args.creator_id else {"hours": args.hours}).fetchone()
    extreme_rows = conn.execute(q_extreme, params if args.creator_id else {"hours": args.hours}).fetchall()

# ── Empty-table guard ─────────────────────────────────────────────────────────

total_turns = int(summary_row.total_turns) if summary_row and summary_row.total_turns else 0
if total_turns == 0:
    print("No data in window.")
    sys.exit(0)

compacted_turns = int(summary_row.compacted_turns) if summary_row.compacted_turns else 0
compaction_pct = float(summary_row.compaction_pct) if summary_row.compaction_pct else 0.0

gate_pass = compaction_pct < 15.0

creator_label = args.creator_id if args.creator_id else "all"

# ── Structured data ───────────────────────────────────────────────────────────

reason_breakdown = [
    {"creator": r.creator_slug, "reason": r.reason, "count": int(r.count)}
    for r in reasons_rows
]

top_sections = [
    {"section": r.section_name, "count": int(r.truncation_count)}
    for r in sections_rows
]

avg_div = int(divergence_row.avg_divergence_chars) if divergence_row and divergence_row.avg_divergence_chars is not None else 0
p95_div = int(divergence_row.p95_divergence) if divergence_row and divergence_row.p95_divergence is not None else 0
max_div = int(divergence_row.max_divergence_chars) if divergence_row and divergence_row.max_divergence_chars is not None else 0

divergence_stats = {
    "avg_chars": avg_div,
    "p95_chars": p95_div,
    "max_chars": max_div,
}

extreme_cases = [
    {
        "timestamp": str(r.timestamp),
        "creator": r.creator_slug,
        "actual_chars_before": int(r.actual_chars_before),
        "shadow_chars_after": int(r.shadow_chars_after),
        "divergence_chars": int(r.divergence_chars),
        "reason": r.reason,
    }
    for r in extreme_rows
]

# ── Output: JSON ──────────────────────────────────────────────────────────────

if args.output == "json":
    result = {
        "total_turns": total_turns,
        "compaction_pct": compaction_pct,
        "gate_pass": gate_pass,
        "reason_breakdown": reason_breakdown,
        "top_sections": top_sections,
        "divergence": divergence_stats,
        "extreme_cases": extreme_cases,
    }
    print(json.dumps(result, indent=2))
    sys.exit(0)

# ── Output: CSV ───────────────────────────────────────────────────────────────

if args.output == "csv":
    writer = csv.writer(sys.stdout)
    # Summary header rows
    writer.writerow(["# ARC3 Phase 2 Compactor Shadow Analysis"])
    writer.writerow(["window_hours", "total_turns", "compacted_turns", "compaction_pct", "gate_pass"])
    writer.writerow([args.hours, total_turns, compacted_turns, compaction_pct, gate_pass])
    writer.writerow([])
    # Extreme cases
    writer.writerow(["timestamp", "creator", "actual_chars_before", "shadow_chars_after", "divergence_chars", "reason"])
    for ec in extreme_cases:
        writer.writerow([
            ec["timestamp"],
            ec["creator"],
            ec["actual_chars_before"],
            ec["shadow_chars_after"],
            ec["divergence_chars"],
            ec["reason"],
        ])
    sys.exit(0)

# ── Output: Markdown (default) ────────────────────────────────────────────────

gate_status = (
    f"**STATUS: ✅ PASS** — {compaction_pct}% < 15% threshold. Ready for Phase 3 live activation."
    if gate_pass
    else f"**STATUS: ❌ FAIL** — {compaction_pct}% > 15% threshold. Recalibrate ratios before Phase 3."
)

lines = []
lines.append("# ARC3 Phase 2 — Compactor Shadow Analysis")
lines.append(f"Window: last {args.hours}h | Creator: {creator_label}")
lines.append("")
lines.append("## Summary")
lines.append(f"- Total turns analyzed: {total_turns:,}")
lines.append(f"- Compaction triggered: {compacted_turns:,} turns ({compaction_pct}%)")
lines.append("")
lines.append("## Phase 3 Gate: < 15% compaction rate")
lines.append(gate_status)
lines.append("")
lines.append("## Reason Breakdown by Creator")
lines.append("| Creator | Reason | Count |")
lines.append("|---------|--------|-------|")
for rb in reason_breakdown:
    lines.append(f"| {rb['creator']} | {rb['reason']} | {rb['count']:,} |")
lines.append("")
lines.append("## Top 5 Truncated Sections")
lines.append("| Section | Count |")
lines.append("|---------|-------|")
for ts in top_sections:
    lines.append(f"| {ts['section']} | {ts['count']:,} |")
lines.append("")
lines.append("## Divergence Stats")
lines.append(f"- Avg: {avg_div:,} chars")
lines.append(f"- P95: {p95_div:,} chars")
lines.append(f"- Max: {max_div:,} chars")
lines.append("")
lines.append("## Extreme Cases (divergence > 2000)")
if extreme_cases:
    lines.append("| Timestamp | Creator | Actual | Shadow | Divergence | Reason |")
    lines.append("|-----------|---------|--------|--------|------------|--------|")
    for ec in extreme_cases:
        lines.append(
            f"| {ec['timestamp']} | {ec['creator']} | {ec['actual_chars_before']:,} "
            f"| {ec['shadow_chars_after']:,} | {ec['divergence_chars']:,} | {ec['reason']} |"
        )
else:
    lines.append("_No extreme cases found in this window._")

print("\n".join(lines))
