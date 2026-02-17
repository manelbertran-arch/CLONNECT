#!/usr/bin/env python3
"""
CLI script to run personality extraction for a creator.

Usage:
    python scripts/run_personality_extraction.py <creator_id> [options]

Examples:
    # Full extraction with LLM analysis
    python scripts/run_personality_extraction.py stefano_bonanno

    # Statistical analysis only (no LLM calls)
    python scripts/run_personality_extraction.py stefano_bonanno --skip-llm

    # Limit to 20 leads
    python scripts/run_personality_extraction.py stefano_bonanno --limit 20

    # Custom output directory
    python scripts/run_personality_extraction.py stefano_bonanno --output /tmp/extraction
"""

import argparse
import asyncio
import logging
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Reduce noise from HTTP libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run personality extraction for a creator",
    )
    parser.add_argument(
        "creator_id",
        help="Creator UUID or name (looked up in DB)",
    )
    parser.add_argument(
        "--name",
        default="",
        help="Creator display name (auto-detected from DB if not provided)",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Skip LLM phases (statistical analysis only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max leads to process",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: data/personality_extractions/<creator_id>/)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    logger = logging.getLogger("personality_extraction")

    # Verify environment
    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL not set. Run with appropriate environment.")
        return 1

    if not args.skip_llm and not os.getenv("GOOGLE_API_KEY"):
        logger.warning("GOOGLE_API_KEY not set — LLM phases will fail. Use --skip-llm for stats only.")

    # Connect to database
    from api.database import get_db_session
    from core.personality_extraction.extractor import PersonalityExtractor

    with get_db_session() as db:
        # Resolve creator_id — check if it's a UUID or name
        from sqlalchemy import text
        row = db.execute(
            text("SELECT id::text, name FROM creators WHERE id::text = :id OR name = :id LIMIT 1"),
            {"id": args.creator_id},
        ).fetchone()

        if not row:
            logger.error("Creator not found: %s", args.creator_id)
            return 1

        creator_id = row[0]
        creator_name = args.name or row[1]
        logger.info("Creator: %s (id=%s)", creator_name, creator_id)

        # Run extraction
        extractor = PersonalityExtractor(db)
        result = await extractor.run(
            creator_id=creator_id,
            creator_name=creator_name,
            output_dir=args.output,
            skip_llm=args.skip_llm,
            limit_leads=args.limit,
        )

    # Print summary
    print("\n" + "=" * 60)
    print(f"PERSONALITY EXTRACTION COMPLETE")
    print(f"=" * 60)
    print(f"Creator: {result.creator_name}")
    print(f"Duration: {result.duration_seconds}s")
    print(f"\nData Cleaning:")
    stats = result.cleaning_stats
    print(f"  Total messages: {stats.total_messages}")
    print(f"  Creator real: {stats.creator_real}")
    print(f"  Copilot AI: {stats.copilot_ai}")
    print(f"  Uncertain: {stats.uncertain}")
    print(f"  Lead messages: {stats.lead_messages}")
    print(f"  Total leads: {stats.total_leads}")
    print(f"  Leads with enough data (>=3 msgs): {stats.leads_with_enough_data}")
    print(f"  Clean ratio: {stats.clean_ratio:.1%}")

    if result.personality_profile:
        ws = result.personality_profile.writing_style
        print(f"\nWriting Style:")
        print(f"  Avg message length: {ws.avg_message_length} chars")
        print(f"  Emoji usage: {ws.emoji_pct}%")
        print(f"  Multi-bubble: {ws.fragmentation_multi_pct}%")
        print(f"  Language: {ws.primary_language} ({ws.dialect})")

    if result.bot_configuration.system_prompt:
        print(f"\nBot Configuration:")
        print(f"  System prompt: {len(result.bot_configuration.system_prompt)} chars")
        print(f"  Blacklist: {len(result.bot_configuration.blacklist_phrases)} phrases")
        print(f"  Templates: {len(result.bot_configuration.template_categories)} categories")

    if result.copilot_rules.raw_rules_text:
        print(f"\nCopilot Rules:")
        print(f"  Mode: {result.copilot_rules.global_mode}")
        print(f"  AUTO: {result.copilot_rules.auto_pct}%")
        print(f"  DRAFT: {result.copilot_rules.draft_pct}%")
        print(f"  MANUAL: {result.copilot_rules.manual_pct}%")

    if result.errors:
        print(f"\nErrors: {len(result.errors)}")
        for err in result.errors:
            print(f"  ⚠️  {err}")

    output_dir = args.output or f"data/personality_extractions/{creator_id}"
    print(f"\nDocuments saved to: {output_dir}/")
    print(f"  doc_a_conversations.md")
    print(f"  doc_b_lead_analysis.md")
    print(f"  doc_c_personality_profile.md")
    print(f"  doc_d_bot_configuration.md")
    print(f"  doc_e_copilot_rules.md")
    print(f"  extraction_summary.json")

    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
