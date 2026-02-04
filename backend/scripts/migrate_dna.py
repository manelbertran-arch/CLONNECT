"""DNA Migration Script for existing leads.

Analyzes existing conversations and creates RelationshipDNA records
for leads that have sufficient message history.

Usage:
    python scripts/migrate_dna.py --creator stefan --limit 100 --min-messages 10

Part of RELATIONSHIP-DNA feature.
"""

import argparse
import logging
import sys
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, ".")

logger = logging.getLogger(__name__)


class DNAMigrator:
    """Migrates existing leads to have RelationshipDNA records."""

    def __init__(self):
        """Initialize the migrator."""
        self._stats = {
            "processed": 0,
            "success": 0,
            "skipped": 0,
            "errors": 0,
        }

    def migrate(
        self,
        creator_id: str,
        limit: Optional[int] = None,
        min_messages: int = 5,
        dry_run: bool = False,
    ) -> Dict:
        """Migrate existing leads for a creator.

        Args:
            creator_id: Creator identifier
            limit: Maximum number of leads to process (None = all)
            min_messages: Minimum messages required for analysis
            dry_run: If True, don't actually create DNA records

        Returns:
            Dict with migration stats
        """
        logger.info(f"Starting DNA migration for {creator_id}")
        logger.info(f"  limit={limit}, min_messages={min_messages}, dry_run={dry_run}")

        # Reset stats
        self._stats = {"processed": 0, "success": 0, "skipped": 0, "errors": 0}

        # Get leads with message counts
        leads = self._get_leads_with_messages(creator_id)

        # Sort by message count (highest first)
        leads = sorted(leads, key=lambda x: x["message_count"], reverse=True)

        # Apply limit
        if limit:
            leads = leads[:limit]

        logger.info(f"Found {len(leads)} leads to process")

        for lead in leads:
            # Skip if below minimum messages
            if lead["message_count"] < min_messages:
                self._stats["skipped"] += 1
                logger.debug(
                    f"Skipping {lead['follower_id']}: {lead['message_count']} < {min_messages} messages"
                )
                continue

            self._stats["processed"] += 1

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would analyze {lead['follower_id']} ({lead['message_count']} messages)"
                )
                self._stats["success"] += 1
                continue

            # Analyze and create DNA
            try:
                success = self._analyze_and_create_dna(lead)
                if success:
                    self._stats["success"] += 1
                else:
                    self._stats["errors"] += 1
            except Exception as e:
                logger.error(f"Error processing {lead['follower_id']}: {e}")
                self._stats["errors"] += 1

        logger.info(f"Migration complete: {self._stats}")
        return self._stats

    def _get_leads_with_messages(self, creator_id: str) -> List[Dict]:
        """Get all leads with their message counts.

        Args:
            creator_id: Creator identifier

        Returns:
            List of lead dicts with message_count
        """
        try:
            from api.services.db_service import get_session

            session = get_session()
            if not session:
                logger.warning("No database session available")
                return []

            try:
                from sqlalchemy import func

                from api.models import Creator, Lead, Message

                # Get creator
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    logger.warning(f"Creator {creator_id} not found")
                    return []

                # Get leads with message counts
                results = (
                    session.query(
                        Lead.platform_user_id,
                        func.count(Message.id).label("message_count"),
                    )
                    .outerjoin(Message, Lead.id == Message.lead_id)
                    .filter(Lead.creator_id == creator.id)
                    .group_by(Lead.platform_user_id)
                    .all()
                )

                return [
                    {
                        "creator_id": creator_id,
                        "follower_id": r.platform_user_id,
                        "message_count": r.message_count or 0,
                    }
                    for r in results
                ]

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Error getting leads: {e}")
            return []

    def _analyze_and_create_dna(self, lead: Dict) -> bool:
        """Analyze a lead's conversation and create DNA.

        Args:
            lead: Lead dict with creator_id, follower_id, message_count

        Returns:
            True if successful
        """
        try:
            from services.relationship_dna_service import get_dna_service

            creator_id = lead["creator_id"]
            follower_id = lead["follower_id"]

            # Get messages for analysis
            messages = self._get_messages(creator_id, follower_id)

            if not messages:
                logger.warning(f"No messages found for {follower_id}")
                return False

            # Use DNA service to analyze and create
            service = get_dna_service()
            result = service.analyze_and_update_dna(creator_id, follower_id, messages)

            if result:
                logger.info(
                    f"Created DNA for {follower_id}: "
                    f"type={result.get('relationship_type')}, "
                    f"trust={result.get('trust_score', 0):.2f}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error analyzing {lead['follower_id']}: {e}")
            return False

    def _get_messages(self, creator_id: str, follower_id: str) -> List[Dict]:
        """Get messages for a specific lead.

        Args:
            creator_id: Creator identifier
            follower_id: Lead/follower identifier

        Returns:
            List of message dicts with role and content
        """
        try:
            from api.services.db_service import get_session

            session = get_session()
            if not session:
                return []

            try:
                from api.models import Creator, Lead, Message

                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    return []

                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                    .first()
                )
                if not lead:
                    return []

                messages = (
                    session.query(Message)
                    .filter_by(lead_id=lead.id)
                    .order_by(Message.created_at)
                    .all()
                )

                return [{"role": m.role, "content": m.content} for m in messages]

            finally:
                session.close()

        except Exception as e:
            logger.error(f"Error getting messages: {e}")
            return []


def main():
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(description="Migrate existing leads to DNA")
    parser.add_argument("--creator", required=True, help="Creator ID to migrate")
    parser.add_argument("--limit", type=int, help="Maximum leads to process")
    parser.add_argument(
        "--min-messages", type=int, default=5, help="Minimum messages required"
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't create records")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run migration
    migrator = DNAMigrator()
    result = migrator.migrate(
        creator_id=args.creator,
        limit=args.limit,
        min_messages=args.min_messages,
        dry_run=args.dry_run,
    )

    print(f"\nMigration complete:")
    print(f"  Processed: {result['processed']}")
    print(f"  Success: {result['success']}")
    print(f"  Skipped: {result['skipped']}")
    print(f"  Errors: {result['errors']}")


if __name__ == "__main__":
    main()
