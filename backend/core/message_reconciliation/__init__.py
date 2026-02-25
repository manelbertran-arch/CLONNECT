"""
Message Reconciliation System

Automatic reconciliation of Instagram messages between API and database.
Runs as part of the nurturing scheduler to ensure no messages are lost.

Features:
- Periodic reconciliation every 5 minutes
- Startup reconciliation of last 24 hours
- Gap detection health check
- No duplicates (checks by platform_message_id)
"""

from core.message_reconciliation.core import (
    MAX_CONVERSATIONS_PER_CYCLE,
    RECONCILIATION_INTERVAL_MINUTES,
    RECONCILIATION_LOOKBACK_HOURS,
    _extract_media_from_attachments,
    check_message_gaps,
    get_reconciliation_status,
    reconcile_messages_for_creator,
    run_reconciliation_cycle,
)
from core.message_reconciliation.enrichment import (
    _fetch_profile_for_lead,
    _queue_profile_enrichment,
    enrich_leads_without_profile,
)
from core.message_reconciliation.fetcher import (
    get_db_message_ids,
    get_instagram_conversations,
)
from core.message_reconciliation.scheduler import (
    run_periodic_reconciliation,
    run_startup_reconciliation,
)

__all__ = [
    # Constants
    "RECONCILIATION_LOOKBACK_HOURS",
    "RECONCILIATION_INTERVAL_MINUTES",
    "MAX_CONVERSATIONS_PER_CYCLE",
    # Enrichment
    "_fetch_profile_for_lead",
    "_queue_profile_enrichment",
    "enrich_leads_without_profile",
    # Fetcher
    "get_instagram_conversations",
    "get_db_message_ids",
    # Core reconciliation
    "_extract_media_from_attachments",
    "reconcile_messages_for_creator",
    "run_reconciliation_cycle",
    "check_message_gaps",
    "get_reconciliation_status",
    # Scheduler
    "run_startup_reconciliation",
    "run_periodic_reconciliation",
]
