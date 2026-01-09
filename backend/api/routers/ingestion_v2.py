"""
Ingestion V2 API Router
Zero-Hallucination website ingestion with provenance tracking
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

try:
    from api.database import get_db
except ImportError:
    from database import get_db

# Import V2 ingestion system
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from ingestion.v2.pipeline import IngestionPipeline, ingest_website
from ingestion.v2.product_detector import SuspiciousExtractionError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion/v2", tags=["ingestion-v2"])


class WebsiteIngestionRequest(BaseModel):
    """Request to ingest a website"""
    creator_id: str
    website_url: str
    persist_to_db: bool = True  # Set to False for dry-run testing


class ProductResult(BaseModel):
    """Single product result"""
    name: str
    description: Optional[str]
    price: Optional[float]
    price_text: Optional[str]
    source_url: str
    signals_matched: list
    confidence: float
    verified: bool
    verification_note: str


class SanityCheckResult(BaseModel):
    """Single sanity check result"""
    name: str
    passed: bool
    message: str


class IngestionResponse(BaseModel):
    """Response from ingestion"""
    status: str
    creator_id: str
    website_url: str
    pages_scraped: int
    service_pages_found: int
    products_detected: int
    products_verified: int
    products: list
    sanity_checks: list
    errors: list


@router.post("/website", response_model=IngestionResponse)
async def ingest_website_endpoint(
    request: WebsiteIngestionRequest,
    db: Session = Depends(get_db)
):
    """
    Ingest products from a website using Zero-Hallucination V2 system.

    Features:
    - Conservative signal-based product detection (requires 3+ signals)
    - Automatic sanity checks (aborts if >20 products detected)
    - Source provenance for every field (source_url + source_html)
    - Re-verification by fetching URLs
    - Clears old data before persisting new

    Set persist_to_db=False for dry-run testing.
    """
    logger.info(f"[IngestionV2] Starting for {request.creator_id} from {request.website_url}")

    try:
        # Create pipeline with or without DB
        db_session = db if request.persist_to_db else None
        pipeline = IngestionPipeline(db_session=db_session)

        # Run ingestion
        result = await pipeline.run(request.creator_id, request.website_url)

        return IngestionResponse(
            status=result.status,
            creator_id=result.creator_id,
            website_url=result.website_url,
            pages_scraped=result.pages_scraped,
            service_pages_found=result.service_pages_found,
            products_detected=result.products_detected,
            products_verified=result.products_verified,
            products=[p.to_dict() for p in result.products],
            sanity_checks=[
                {"name": c.name, "passed": c.passed, "message": c.message}
                for c in result.sanity_checks
            ],
            errors=result.errors
        )

    except SuspiciousExtractionError as e:
        logger.error(f"[IngestionV2] Suspicious extraction: {e}")
        return IngestionResponse(
            status="aborted",
            creator_id=request.creator_id,
            website_url=request.website_url,
            pages_scraped=0,
            service_pages_found=0,
            products_detected=0,
            products_verified=0,
            products=[],
            sanity_checks=[{
                "name": "extraction_sanity",
                "passed": False,
                "message": str(e)
            }],
            errors=[str(e)]
        )

    except Exception as e:
        logger.exception(f"[IngestionV2] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test/{creator_id}")
async def test_ingestion(creator_id: str, website_url: str, db: Session = Depends(get_db)):
    """
    Quick test endpoint - runs dry-run ingestion without persistence.
    Useful for debugging and verification.
    """
    logger.info(f"[IngestionV2] Test run for {creator_id} from {website_url}")

    try:
        pipeline = IngestionPipeline(db_session=None)  # No persistence
        result = await pipeline.run(creator_id, website_url)

        return {
            "status": result.status,
            "summary": {
                "pages_scraped": result.pages_scraped,
                "service_pages_found": result.service_pages_found,
                "products_detected": result.products_detected,
                "products_verified": result.products_verified
            },
            "products": [
                {
                    "name": p.name,
                    "price": p.price,
                    "price_text": p.price_text,
                    "source_url": p.source_url,
                    "signals": p.signals_matched,
                    "confidence": p.confidence,
                    "verified": p.verified
                }
                for p in result.products
            ],
            "sanity_checks": [
                {"name": c.name, "passed": c.passed, "message": c.message}
                for c in result.sanity_checks
            ],
            "errors": result.errors
        }

    except Exception as e:
        logger.exception(f"[IngestionV2] Test error: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.delete("/clear/{creator_id}")
async def clear_products(creator_id: str, db: Session = Depends(get_db)):
    """
    Clear all products for a creator.
    Useful before re-running ingestion.
    """
    try:
        from api.models import Product

        count = db.query(Product).filter(Product.creator_id == creator_id).count()
        db.query(Product).filter(Product.creator_id == creator_id).delete()
        db.commit()

        return {
            "status": "success",
            "message": f"Cleared {count} products for {creator_id}"
        }

    except Exception as e:
        db.rollback()
        logger.exception(f"[IngestionV2] Clear error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
