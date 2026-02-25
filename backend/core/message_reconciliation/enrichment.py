"""
Profile enrichment functions for message reconciliation.

Functions for fetching Instagram profiles and enriching leads without profile info.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("clonnect-reconciliation")


async def _fetch_profile_for_lead(user_id: str, access_token: str) -> Dict[str, Any]:
    """
    Fetch Instagram profile for a lead.
    Returns dict with username, name, profile_pic or empty dict on failure.
    """
    try:
        from core.instagram_profile import fetch_instagram_profile_with_retry

        result = await fetch_instagram_profile_with_retry(user_id, access_token, max_retries=1)
        if result.success and result.profile:
            return result.profile
    except Exception as e:
        logger.debug(f"[Reconciliation] Profile fetch failed for {user_id}: {e}")

    return {}


async def _queue_profile_enrichment(creator_id: str, user_id: str) -> None:
    """Queue a lead for profile enrichment retry."""
    try:
        from api.database import SessionLocal
        from api.models import SyncQueue

        session = SessionLocal()
        try:
            # Check if already queued
            existing = (
                session.query(SyncQueue)
                .filter_by(
                    creator_id=creator_id,
                    conversation_id=f"profile_retry:{user_id}",
                )
                .filter(SyncQueue.status.in_(["pending", "processing"]))
                .first()
            )
            if existing:
                return

            queue_item = SyncQueue(
                creator_id=creator_id,
                conversation_id=f"profile_retry:{user_id}",
                status="pending",
                attempts=0,
            )
            session.add(queue_item)
            session.commit()
            logger.debug(f"[Reconciliation] Queued profile retry for {user_id}")

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[Reconciliation] Failed to queue profile retry: {e}")


async def enrich_leads_without_profile(
    creator_id: str, access_token: str, limit: int = 10
) -> Dict[str, int]:
    """
    Find and enrich leads that don't have profile info.
    Called periodically to fix leads created without profiles.

    Returns:
        Dict with counts: processed, enriched, failed
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead

    result = {"processed": 0, "enriched": 0, "failed": 0, "queued": 0}

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            return result

        # Find leads without username
        leads_to_enrich = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id,
                Lead.platform == "instagram",
                (Lead.username.is_(None)) | (Lead.username == ""),
            )
            .limit(limit)
            .all()
        )

        for lead in leads_to_enrich:
            result["processed"] += 1

            # Extract user_id from platform_user_id (ig_XXXXX -> XXXXX)
            user_id = lead.platform_user_id.replace("ig_", "")

            # Try to fetch profile
            profile = await _fetch_profile_for_lead(user_id, access_token)

            if profile.get("username"):
                lead.username = profile["username"]
                lead.full_name = profile.get("name") or lead.full_name
                lead.profile_pic_url = profile.get("profile_pic") or lead.profile_pic_url

                # Clear pending flag
                if lead.context and isinstance(lead.context, dict):
                    lead.context.pop("profile_pending", None)

                session.commit()
                result["enriched"] += 1
                logger.info(f"[Reconciliation] Enriched lead {user_id} -> @{profile['username']}")
            else:
                # Queue for retry
                await _queue_profile_enrichment(creator_id, user_id)
                result["queued"] += 1
                result["failed"] += 1

    except Exception as e:
        logger.error(f"[Reconciliation] Error enriching leads: {e}")

    finally:
        session.close()

    return result
