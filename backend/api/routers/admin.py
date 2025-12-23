"""
Admin endpoints for demo/testing purposes
"""
import os
import logging
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Only enable if ENABLE_DEMO_RESET is set
DEMO_RESET_ENABLED = os.getenv("ENABLE_DEMO_RESET", "false").lower() == "true"


@router.post("/reset-demo-data/{creator_id}")
async def reset_demo_data(creator_id: str):
    """
    Reset all demo data for a creator (leads, messages, metrics).
    Only available when ENABLE_DEMO_RESET=true environment variable is set.
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {
        "creator_id": creator_id,
        "deleted": {
            "leads": 0,
            "messages": 0,
            "conversations": 0,
            "metrics_reset": False
        }
    }

    # Try database reset first
    try:
        from api.database import get_db_connection, DATABASE_URL
        if DATABASE_URL:
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()

                # Delete messages for this creator's leads
                cursor.execute("""
                    DELETE FROM messages
                    WHERE lead_id IN (
                        SELECT id FROM leads WHERE creator_id = %s
                    )
                """, (creator_id,))
                results["deleted"]["messages"] = cursor.rowcount

                # Delete leads
                cursor.execute("DELETE FROM leads WHERE creator_id = %s", (creator_id,))
                results["deleted"]["leads"] = cursor.rowcount

                # Reset metrics if table exists
                try:
                    cursor.execute("""
                        UPDATE creator_metrics
                        SET messages_today = 0,
                            leads_today = 0,
                            hot_leads_count = 0,
                            conversion_rate = 0
                        WHERE creator_id = %s
                    """, (creator_id,))
                    results["deleted"]["metrics_reset"] = cursor.rowcount > 0
                except Exception:
                    pass  # Metrics table might not exist

                conn.commit()
                cursor.close()
                conn.close()

                logger.info(f"Demo data reset for {creator_id}: {results}")
                return {"status": "success", **results}
    except Exception as e:
        logger.warning(f"Database reset failed, trying JSON fallback: {e}")

    # JSON fallback
    import json
    from pathlib import Path

    data_dir = Path("data")

    # Reset leads JSON
    leads_file = data_dir / f"leads_{creator_id}.json"
    if leads_file.exists():
        try:
            with open(leads_file) as f:
                leads_data = json.load(f)
            results["deleted"]["leads"] = len(leads_data.get("leads", []))
            leads_file.write_text(json.dumps({"leads": []}, indent=2))
        except Exception as e:
            logger.error(f"Failed to reset leads JSON: {e}")

    # Reset conversations JSON
    conversations_file = data_dir / f"conversations_{creator_id}.json"
    if conversations_file.exists():
        try:
            with open(conversations_file) as f:
                conv_data = json.load(f)
            results["deleted"]["conversations"] = len(conv_data.get("conversations", []))
            conversations_file.write_text(json.dumps({"conversations": []}, indent=2))
        except Exception as e:
            logger.error(f"Failed to reset conversations JSON: {e}")

    # Reset messages JSON
    messages_file = data_dir / f"messages_{creator_id}.json"
    if messages_file.exists():
        try:
            with open(messages_file) as f:
                msg_data = json.load(f)
            results["deleted"]["messages"] = len(msg_data.get("messages", []))
            messages_file.write_text(json.dumps({"messages": []}, indent=2))
        except Exception as e:
            logger.error(f"Failed to reset messages JSON: {e}")

    # Reset metrics JSON
    metrics_file = data_dir / f"metrics_{creator_id}.json"
    if metrics_file.exists():
        try:
            metrics_file.write_text(json.dumps({
                "messages_today": 0,
                "leads_today": 0,
                "hot_leads_count": 0,
                "conversion_rate": 0,
                "total_messages": 0,
                "total_leads": 0
            }, indent=2))
            results["deleted"]["metrics_reset"] = True
        except Exception as e:
            logger.error(f"Failed to reset metrics JSON: {e}")

    # Reset sales tracking data
    sales_file = data_dir / f"sales_{creator_id}.json"
    if sales_file.exists():
        try:
            sales_file.write_text(json.dumps({"clicks": [], "sales": []}, indent=2))
        except Exception as e:
            logger.error(f"Failed to reset sales JSON: {e}")

    logger.info(f"Demo data reset (JSON fallback) for {creator_id}: {results}")
    return {"status": "success", **results}


@router.get("/demo-status")
async def get_demo_status():
    """Check if demo reset is enabled"""
    return {
        "demo_reset_enabled": DEMO_RESET_ENABLED,
        "message": "Set ENABLE_DEMO_RESET=true environment variable to enable demo data reset"
    }
