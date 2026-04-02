"""DNA Update Triggers for automatic re-analysis.

Determines when to re-analyze RelationshipDNA based on:
- New message count thresholds
- Time since last analysis
- Conversation phase changes

Part of RELATIONSHIP-DNA feature.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Configuration constants
MIN_MESSAGES_FOR_FIRST_ANALYSIS = 5
NEW_MESSAGE_THRESHOLD = 10  # Re-analyze after 10+ new messages
COOLDOWN_HOURS = 24  # Minimum hours between re-analyses
STALE_DAYS = 30  # Force re-analysis after 30 days


def schedule_dna_update(
    creator_id: str, follower_id: str, messages: List[Dict]
) -> bool:
    """Schedule DNA update in background thread.

    Args:
        creator_id: Creator identifier
        follower_id: Lead/follower identifier
        messages: Conversation history

    Returns:
        True if scheduled successfully
    """
    def run_update():
        for attempt in range(2):
            try:
                from services.relationship_dna_service import get_dna_service

                service = get_dna_service()
                service.analyze_and_update_dna(creator_id, follower_id, messages)
                logger.info(f"Background DNA update completed for {creator_id}/{follower_id}")
                return
            except Exception as e:
                logger.error(
                    f"Background DNA update failed (attempt {attempt + 1}/2) "
                    f"for {creator_id}/{follower_id}: {e}"
                )
                if attempt == 0:
                    import time
                    time.sleep(2)

    thread = threading.Thread(target=run_update, daemon=True)
    thread.start()
    logger.debug(f"Scheduled background DNA update for {creator_id}/{follower_id}")
    return True


class DNAUpdateTriggers:
    """Determines when to trigger DNA re-analysis."""

    def __init__(
        self,
        min_messages: int = MIN_MESSAGES_FOR_FIRST_ANALYSIS,
        new_message_threshold: int = NEW_MESSAGE_THRESHOLD,
        cooldown_hours: int = COOLDOWN_HOURS,
        stale_days: int = STALE_DAYS,
    ):
        """Initialize triggers with configuration.

        Args:
            min_messages: Minimum messages for first analysis
            new_message_threshold: New messages needed to trigger re-analysis
            cooldown_hours: Hours to wait between analyses
            stale_days: Days after which DNA is considered stale
        """
        self.min_messages = min_messages
        self.new_message_threshold = new_message_threshold
        self.cooldown_hours = cooldown_hours
        self.stale_days = stale_days

    def should_update(
        self, existing_dna: Optional[Dict], current_count: int
    ) -> bool:
        """Determine if DNA should be updated.

        Args:
            existing_dna: Current DNA data or None
            current_count: Current total message count

        Returns:
            True if update should be triggered
        """
        # First analysis - need minimum messages
        if not existing_dna:
            return current_count >= self.min_messages

        # Get previous analysis info
        prev_count = existing_dna.get("total_messages_analyzed", 0)
        last_analyzed = existing_dna.get("last_analyzed_at")

        # Parse last_analyzed timestamp
        if last_analyzed:
            if isinstance(last_analyzed, str):
                last_analyzed = datetime.fromisoformat(
                    last_analyzed.replace("Z", "+00:00")
                )
        else:
            # No timestamp - consider stale
            return current_count - prev_count >= self.new_message_threshold

        # Check cooldown period
        now = datetime.now(timezone.utc)
        time_since_analysis = now - last_analyzed

        # During cooldown, don't trigger regardless of message count
        if time_since_analysis < timedelta(hours=self.cooldown_hours):
            return False

        # Check if stale (force update after stale_days)
        if time_since_analysis > timedelta(days=self.stale_days):
            return True

        # Check new message threshold
        new_messages = current_count - prev_count
        return new_messages >= self.new_message_threshold

    def get_update_reason(
        self, existing_dna: Optional[Dict], current_count: int
    ) -> Optional[str]:
        """Get the reason why update should be triggered.

        Args:
            existing_dna: Current DNA data or None
            current_count: Current total message count

        Returns:
            Reason string or None if no update needed
        """
        if not self.should_update(existing_dna, current_count):
            return None

        if not existing_dna:
            return "first_analysis"

        prev_count = existing_dna.get("total_messages_analyzed", 0)
        last_analyzed = existing_dna.get("last_analyzed_at")

        if last_analyzed:
            if isinstance(last_analyzed, str):
                last_analyzed = datetime.fromisoformat(
                    last_analyzed.replace("Z", "+00:00")
                )

            now = datetime.now(timezone.utc)
            if now - last_analyzed > timedelta(days=self.stale_days):
                return "stale"

        new_messages = current_count - prev_count
        if new_messages >= self.new_message_threshold:
            return f"new_messages_{new_messages}"

        return "unknown"

    def schedule_async_update(
        self,
        creator_id: str,
        follower_id: str,
        messages: List[Dict],
    ) -> bool:
        """Schedule async DNA update if needed.

        Args:
            creator_id: Creator identifier
            follower_id: Lead/follower identifier
            messages: Conversation history

        Returns:
            True if update was scheduled
        """
        return schedule_dna_update(creator_id, follower_id, messages)


# Module-level singleton
_triggers: Optional[DNAUpdateTriggers] = None


def get_dna_triggers() -> DNAUpdateTriggers:
    """Get the singleton triggers instance."""
    global _triggers
    if _triggers is None:
        _triggers = DNAUpdateTriggers()
    return _triggers
