"""
Onboarding Verification Router — Post-onboarding health checks.

Endpoints:
- GET /onboarding/verification/{creator_id} — Check onboarding completeness
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter(tags=["onboarding"])


@router.get("/verification/{creator_id}")
async def verify_onboarding(creator_id: str, _auth: str = Depends(require_creator_access)):
    """
    Verify that all onboarding components are properly configured.

    Returns a dict with status per component: "ok" or "pending".
    """
    from api.database import SessionLocal
    from api.models import Creator, KnowledgeBase, Product, RAGDocument, ToneProfile

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        results = {}

        # 1. Products
        product_count = session.query(Product).filter_by(creator_id=creator_id).count()
        results["products"] = {
            "status": "ok" if product_count > 0 else "pending",
            "count": product_count,
        }

        # 2. FAQs (knowledge_base)
        faq_count = session.query(KnowledgeBase).filter_by(creator_id=creator_id).count()
        results["faqs"] = {
            "status": "ok" if faq_count > 0 else "pending",
            "count": faq_count,
        }

        # 3. Tone profile
        tone = session.query(ToneProfile).filter_by(creator_id=creator_id).first()
        results["tone_profile"] = {
            "status": "ok" if tone else "pending",
            "confidence": tone.confidence_score if tone else None,
        }

        # 4. RAG documents (content chunks)
        rag_count = session.query(RAGDocument).filter_by(creator_id=creator_id).count()
        results["rag_documents"] = {
            "status": "ok" if rag_count > 0 else "pending",
            "count": rag_count,
        }

        # 5. Personality extraction (filesystem)
        extraction_path = f"data/personality_extractions/{creator_id}/extraction_summary.json"
        # Also check by creator UUID
        extraction_exists = os.path.exists(extraction_path)
        if not extraction_exists and creator.id:
            alt_path = f"data/personality_extractions/{creator.id}/extraction_summary.json"
            extraction_exists = os.path.exists(alt_path)
        results["personality_extraction"] = {
            "status": "ok" if extraction_exists else "pending",
        }

        # 6. Leads (informational)
        from api.models import Lead

        lead_count = session.query(Lead).filter_by(creator_id=creator.id).count()
        results["leads"] = {
            "status": "ok" if lead_count > 0 else "pending",
            "count": lead_count,
        }

        # 7. DM history (messages)
        from api.models import Message

        msg_count = (
            session.query(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(Lead.creator_id == creator.id)
            .count()
        )
        results["dm_history"] = {
            "status": "ok" if msg_count > 0 else "pending",
            "count": msg_count,
        }

        # Summary
        pending_items = [k for k, v in results.items() if v["status"] == "pending"]
        all_ok = len(pending_items) == 0

        if pending_items:
            logger.warning(
                f"[B8] Onboarding verification for {creator_id}: pending items: {pending_items}"
            )

        return {
            "creator_id": creator_id,
            "overall_status": "complete" if all_ok else "incomplete",
            "pending_items": pending_items,
            "components": results,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[B8] Verification error for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


async def _verify_onboarding_internal(creator_id: str, session) -> dict:
    """Internal verification used by clone.py during onboarding (reuses existing session)."""
    from api.models import Creator, KnowledgeBase, Lead, Product, RAGDocument, ToneProfile

    creator = session.query(Creator).filter_by(name=creator_id).first()
    if not creator:
        return {"overall_status": "error", "pending_items": ["creator_not_found"], "components": {}}

    results = {}

    product_count = session.query(Product).filter_by(creator_id=creator_id).count()
    results["products"] = {"status": "ok" if product_count > 0 else "pending", "count": product_count}

    faq_count = session.query(KnowledgeBase).filter_by(creator_id=creator_id).count()
    results["faqs"] = {"status": "ok" if faq_count > 0 else "pending", "count": faq_count}

    tone = session.query(ToneProfile).filter_by(creator_id=creator_id).first()
    results["tone_profile"] = {"status": "ok" if tone else "pending"}

    rag_count = session.query(RAGDocument).filter_by(creator_id=creator_id).count()
    results["rag_documents"] = {"status": "ok" if rag_count > 0 else "pending", "count": rag_count}

    extraction_path = f"data/personality_extractions/{creator_id}/extraction_summary.json"
    extraction_exists = os.path.exists(extraction_path)
    if not extraction_exists and creator.id:
        extraction_exists = os.path.exists(
            f"data/personality_extractions/{creator.id}/extraction_summary.json"
        )
    results["personality_extraction"] = {"status": "ok" if extraction_exists else "pending"}

    pending_items = [k for k, v in results.items() if v["status"] == "pending"]
    return {
        "overall_status": "complete" if not pending_items else "incomplete",
        "pending_items": pending_items,
        "components": results,
    }
