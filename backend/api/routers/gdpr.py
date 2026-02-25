"""
GDPR Router - GDPR compliance endpoints
Extracted from main.py as part of refactoring
"""
import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

# Core imports
from core.gdpr import ConsentType, get_gdpr_manager

router = APIRouter(prefix="/gdpr", tags=["gdpr"])


# ---------------------------------------------------------
# GDPR COMPLIANCE
# ---------------------------------------------------------
@router.get("/{creator_id}/export/{follower_id}")
async def gdpr_export_data(creator_id: str, follower_id: str):
    """
    Export all user data (GDPR Right to Access).
    Returns JSON with all data we hold for this user.
    """
    try:
        gdpr = get_gdpr_manager()
        export_data = gdpr.export_user_data(creator_id, follower_id)
        return {"status": "ok", **export_data}

    except Exception as e:
        logger.error(f"Error exporting GDPR data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{creator_id}/delete/{follower_id}")
async def gdpr_delete_data(creator_id: str, follower_id: str, reason: str = "user_request"):
    """
    Delete all user data (GDPR Right to be Forgotten).
    Permanently removes all data for this user.
    """
    try:
        gdpr = get_gdpr_manager()
        result = gdpr.delete_user_data(creator_id, follower_id, reason)

        if not result["success"]:
            raise HTTPException(status_code=500, detail="Internal server error")

        return {"status": "ok", **result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting GDPR data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{creator_id}/anonymize/{follower_id}")
async def gdpr_anonymize_data(creator_id: str, follower_id: str):
    """
    Anonymize user data instead of deleting.
    Keeps aggregated data for analytics while removing PII.
    """
    try:
        gdpr = get_gdpr_manager()
        result = gdpr.anonymize_user_data(creator_id, follower_id)

        if not result["success"]:
            raise HTTPException(status_code=500, detail="Internal server error")

        return {"status": "ok", **result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error anonymizing GDPR data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/consent/{follower_id}")
async def gdpr_get_consent(creator_id: str, follower_id: str):
    """Get consent status for a user"""
    try:
        gdpr = get_gdpr_manager()
        status = gdpr.get_consent_status(creator_id, follower_id)
        return {"status": "ok", **status}

    except Exception as e:
        logger.error(f"Error getting consent status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{creator_id}/consent/{follower_id}")
async def gdpr_record_consent(
    creator_id: str, follower_id: str, consent_type: str, granted: bool, source: str = "api"
):
    """
    Record a consent decision.

    consent_type options: data_processing, marketing, analytics, third_party, profiling
    """
    try:
        # Validate consent type
        valid_types = [ct.value for ct in ConsentType]
        if consent_type not in valid_types:
            raise HTTPException(
                status_code=400, detail=f"Invalid consent_type. Must be one of: {valid_types}"
            )

        gdpr = get_gdpr_manager()
        consent = gdpr.record_consent(
            creator_id=creator_id,
            follower_id=follower_id,
            consent_type=consent_type,
            granted=granted,
            source=source,
        )
        return {"status": "ok", "consent": consent.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording consent: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/inventory/{follower_id}")
async def gdpr_data_inventory(creator_id: str, follower_id: str):
    """Get inventory of what data we hold for a user"""
    try:
        gdpr = get_gdpr_manager()
        inventory = gdpr.get_data_inventory(creator_id, follower_id)
        return {"status": "ok", **inventory}

    except Exception as e:
        logger.error(f"Error getting data inventory: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{creator_id}/audit/{follower_id}")
async def gdpr_audit_log(creator_id: str, follower_id: str, limit: int = 50):
    """Get audit log for a user"""
    try:
        gdpr = get_gdpr_manager()
        logs = gdpr.get_audit_log(creator_id, follower_id, limit=limit)
        return {"status": "ok", "logs": logs, "count": len(logs)}

    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
