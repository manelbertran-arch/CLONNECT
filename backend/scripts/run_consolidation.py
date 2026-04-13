#!/usr/bin/env python3.11
"""Standalone consolidation runner — bypasses time/activity gates.

Usage:
    source .env && python3.11 -u scripts/run_consolidation.py [--creator iris_bertran] [--dry-run]

--dry-run: execute all logic (Jaccard, LLM, cross-lead) but skip all DB writes.
           Produces a report of what WOULD happen. No side effects.

Env vars needed:
    DATABASE_URL                  — Postgres connection string
    ENABLE_MEMORY_CONSOLIDATION=true
    ENABLE_LLM_CONSOLIDATION=true — to test LLM path
    CONSOLIDATION_DRY_RUN=true    — alternative to --dry-run flag
"""

import asyncio
import collections
import logging
import os
import sys

# Ensure backend root is on path (scripts/ is a subdirectory)
_backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

# Parse --dry-run flag before imports (sets env var so modules pick it up)
DRY_RUN = "--dry-run" in sys.argv or os.getenv("CONSOLIDATION_DRY_RUN", "").lower() == "true"
if DRY_RUN:
    os.environ["CONSOLIDATION_DRY_RUN"] = "true"

# Configure logging before any imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("run_consolidation")

if DRY_RUN:
    logger.info("*** DRY-RUN MODE — no DB writes will occur ***")

# Verify DATABASE_URL
if not os.getenv("DATABASE_URL"):
    logger.error("DATABASE_URL not set — run: source .env && python3.11 -u scripts/run_consolidation.py")
    sys.exit(1)

# Verify flags
if os.getenv("ENABLE_MEMORY_CONSOLIDATION", "").lower() != "true":
    logger.error("ENABLE_MEMORY_CONSOLIDATION not set to true")
    sys.exit(1)

if os.getenv("CCEE_NO_FALLBACK"):
    logger.warning("CCEE_NO_FALLBACK=%s is set — unsetting to allow LLM fallback", os.getenv("CCEE_NO_FALLBACK"))
    del os.environ["CCEE_NO_FALLBACK"]

llm_enabled = os.getenv("ENABLE_LLM_CONSOLIDATION", "").lower() == "true"
provider = os.getenv("CONSOLIDATION_LLM_PROVIDER", "deepinfra")
logger.info("ENABLE_LLM_CONSOLIDATION=%s provider=%s", llm_enabled, provider)


def _print_dry_run_report(all_actions: list) -> None:
    """Print structured dry-run report to stdout."""
    if not all_actions:
        print("\n[DRY-RUN REPORT] No actions would be taken.")
        return

    # Group by lead
    by_lead: dict = collections.defaultdict(list)
    for a in all_actions:
        by_lead[a["lead_id"]].append(a)

    # Group by fact_type
    by_type: dict = collections.Counter(a["fact_type"] for a in all_actions)

    # Group by reason
    by_reason: dict = collections.Counter(a["reason"] for a in all_actions)

    print("\n" + "=" * 70)
    print("DRY-RUN REPORT — Memory Consolidation")
    print("=" * 70)
    print(f"\n## Resumen")
    print(f"  Leads procesados:              {len(by_lead)}")
    print(f"  Leads con acciones:            {sum(1 for v in by_lead.values() if v)}")
    print(f"  Total facts que se desactivarían: {len(all_actions)}")

    print(f"\n## Por razón")
    for reason, count in sorted(by_reason.items(), key=lambda x: -x[1]):
        print(f"  {reason:<30} {count:>4}")

    print(f"\n## Por tipo de fact")
    print(f"  {'Tipo':<35} {'Count':>5}  {'%':>5}")
    total = len(all_actions)
    for ftype, count in sorted(by_type.items(), key=lambda x: -x[1]):
        pct = 100 * count / total if total else 0
        print(f"  {ftype:<35} {count:>5}  {pct:>4.1f}%")

    print(f"\n## Por lead (top 15 por impacto)")
    print(f"  {'Lead ID':<12} {'Facts total':>11} {'A desactivar':>12} {'%reduc':>7}")
    lead_impact = sorted(by_lead.items(), key=lambda x: -len(x[1]))
    for lead_id, actions in lead_impact[:15]:
        n = len(actions)
        print(f"  {lead_id[:8]:<12} {'?':>11} {n:>12}")

    # Leads with many actions (>60 — candidates for cap adjustment)
    large_leads = [(lid, acts) for lid, acts in by_lead.items() if len(acts) >= 10]
    if large_leads:
        print(f"\n## Leads con ≥10 acciones (candidatos a ajuste de cap)")
        for lid, acts in sorted(large_leads, key=lambda x: -len(x[1])):
            types = collections.Counter(a["reason"] for a in acts)
            print(f"  {lid[:8]}: {len(acts)} acciones — {dict(types)}")

    print(f"\n## Acciones detalladas (primeras 50)")
    for a in all_actions[:50]:
        score_str = f" score={a['score']:.3f}" if a.get("score") else ""
        content = (a.get("content") or "")[:60].replace("\n", " ")
        print(f"  lead={a['lead_id'][:8]} action={a['action']} type={a['fact_type']}"
              f" reason={a['reason']}{score_str}")
        print(f"    content: {content!r}")

    print("=" * 70)
    print("FIN DRY-RUN REPORT")
    print("=" * 70)


async def main():
    from services.memory_consolidator import consolidate_creator

    # Get target creators
    target_slug = None
    if "--creator" in sys.argv:
        idx = sys.argv.index("--creator")
        if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("--"):
            target_slug = sys.argv[idx + 1]
            logger.info("Target creator slug: %s", target_slug)

    def _get_creators():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            if target_slug:
                rows = session.execute(
                    text("SELECT id, name FROM creators WHERE name = :slug AND bot_active = true"),
                    {"slug": target_slug},
                ).fetchall()
            else:
                rows = session.execute(
                    text("SELECT id, name FROM creators WHERE bot_active = true")
                ).fetchall()
            return [(str(r[0]), r[1]) for r in rows]
        finally:
            session.close()

    try:
        creators = await asyncio.to_thread(_get_creators)
    except Exception as e:
        logger.error("Failed to get creators: %s", e)
        sys.exit(1)

    if not creators:
        logger.error("No active creators found%s", f" for slug '{target_slug}'" if target_slug else "")
        sys.exit(1)

    logger.info("Found %d creator(s): %s", len(creators), [name for _, name in creators])

    total_deduped = 0
    total_expired = 0
    total_cross = 0
    llm_success = False
    all_dry_run_actions: list = []

    for creator_id, creator_name in creators:
        logger.info("=" * 60)
        logger.info("%sConsolidating creator: %s (%s)",
                    "[DRY-RUN] " if DRY_RUN else "", creator_name, creator_id[:8])
        logger.info("=" * 60)

        result = await consolidate_creator(creator_id)

        if result.error:
            logger.error("  ERROR: %s", result.error)
        else:
            logger.info("  leads_processed: %d", result.leads_processed)
            logger.info("  facts_deduped:   %d", result.facts_deduped)
            logger.info("  facts_expired:   %d", result.facts_expired)
            logger.info("  cross_deduped:   %d", result.facts_cross_deduped)
            if not DRY_RUN:
                logger.info("  memos_refreshed: %d", result.memos_refreshed)
            logger.info("  total_deact:     %d", result.total_deactivations)
            logger.info("  duration:        %.1fs", result.duration_seconds)

            total_deduped += result.facts_deduped
            total_expired += result.facts_expired
            total_cross += result.facts_cross_deduped

            if result.leads_processed > 0:
                llm_success = True

            if DRY_RUN and result.dry_run_actions:
                all_dry_run_actions.extend(result.dry_run_actions)

    logger.info("")
    logger.info("=" * 60)
    if DRY_RUN:
        logger.info("DRY-RUN COMPLETE (no DB changes made)")
    else:
        logger.info("CONSOLIDATION COMPLETE")
    logger.info("  total deduped:  %d", total_deduped)
    logger.info("  total expired:  %d", total_expired)
    logger.info("  total cross:    %d", total_cross)
    if llm_enabled:
        logger.info("  LLM ran:       %s", "YES" if llm_success else "NO (check logs for errors)")
    logger.info("=" * 60)

    if DRY_RUN:
        _print_dry_run_report(all_dry_run_actions)

    if not DRY_RUN and llm_enabled and not llm_success:
        logger.error("LLM consolidation required but did not run successfully")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
