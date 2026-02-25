"""Ingestion testing endpoints."""
import logging

from api.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/test-ingestion-v2/{creator_id}")
async def test_ingestion_v2(creator_id: str, website_url: str, admin: str = Depends(require_admin)):
    """
    Test endpoint to run IngestionV2Pipeline directly.

    Usage: POST /admin/test-ingestion-v2/stefano?website_url=https://stefanobonanno.com
    """
    try:
        from api.database import SessionLocal
        from ingestion.v2.pipeline import IngestionV2Pipeline

        session = SessionLocal()
        try:
            pipeline = IngestionV2Pipeline(db_session=session)
            result = await pipeline.run(
                creator_id=creator_id, website_url=website_url, clean_before=True, re_verify=True
            )

            # Ensure commit is done
            session.commit()

            return {
                "status": result.status,
                "success": result.success,
                "products_saved": result.products_saved,
                "knowledge_saved": result.knowledge_saved,
                "products_count": len(result.products),
                "products": result.products[:5] if result.products else [],
                "bio": result.bio,
                "faqs_count": len(result.faqs) if result.faqs else 0,
                "faqs": result.faqs[:3] if result.faqs else [],
                "tone": result.tone,
                "errors": result.errors,
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"test_ingestion_v2 error: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "error": str(e)}
