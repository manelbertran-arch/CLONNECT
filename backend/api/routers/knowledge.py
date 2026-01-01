"""Knowledge base endpoints - FAQs and About Me/Business"""
from fastapi import APIRouter, Body, HTTPException
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/creator/config", tags=["knowledge"])

USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service

@router.get("/{creator_id}/knowledge")
async def get_knowledge(creator_id: str):
    """Get full knowledge base: FAQs + About Me"""
    if USE_DB:
        try:
            knowledge = db_service.get_full_knowledge(creator_id)
            return {
                "status": "ok",
                "faqs": knowledge.get("faqs", []),
                "about": knowledge.get("about", {}),
                "items": knowledge.get("faqs", []),  # Legacy compatibility
                "count": len(knowledge.get("faqs", []))
            }
        except Exception as e:
            logger.warning(f"DB get knowledge failed for {creator_id}: {e}")
    return {"status": "ok", "faqs": [], "about": {}, "items": [], "count": 0}

@router.get("/{creator_id}/knowledge/faqs")
async def get_faqs(creator_id: str):
    """Get FAQ items only"""
    if USE_DB:
        try:
            items = db_service.get_knowledge_items(creator_id)
            return {"status": "ok", "items": items, "count": len(items)}
        except Exception as e:
            logger.warning(f"DB get FAQs failed for {creator_id}: {e}")
    return {"status": "ok", "items": [], "count": 0}

@router.post("/{creator_id}/knowledge/faqs")
async def add_faq(creator_id: str, data: dict = Body(...)):
    """Add a new FAQ"""
    question = data.get("question", "").strip()
    answer = data.get("answer", "").strip()

    if not question or not answer:
        raise HTTPException(status_code=400, detail="Question and answer are required")

    if USE_DB:
        try:
            item = db_service.add_knowledge_item(creator_id, question, answer)
            if item:
                return {"status": "ok", "item": item}
        except Exception as e:
            logger.warning(f"DB add FAQ failed for {creator_id}: {e}")
    raise HTTPException(status_code=500, detail="Failed to add FAQ")

@router.delete("/{creator_id}/knowledge/faqs/{item_id}")
async def delete_faq(creator_id: str, item_id: str):
    """Delete a FAQ"""
    if USE_DB:
        try:
            success = db_service.delete_knowledge_item(creator_id, item_id)
            if success:
                return {"status": "ok", "message": "FAQ deleted"}
        except Exception as e:
            logger.warning(f"DB delete FAQ failed for {creator_id}: {e}")
    raise HTTPException(status_code=404, detail="FAQ not found")

@router.get("/{creator_id}/knowledge/about")
async def get_about(creator_id: str):
    """Get About Me/Business info"""
    if USE_DB:
        try:
            about = db_service.get_knowledge_about(creator_id)
            return {"status": "ok", "about": about}
        except Exception as e:
            logger.warning(f"DB get about failed for {creator_id}: {e}")
    return {"status": "ok", "about": {}}

@router.put("/{creator_id}/knowledge/about")
async def update_about(creator_id: str, data: dict = Body(...)):
    """Update About Me/Business info"""
    if USE_DB:
        try:
            success = db_service.update_knowledge_about(creator_id, data)
            if success:
                return {"status": "ok", "message": "About info updated"}
        except Exception as e:
            logger.warning(f"DB update about failed for {creator_id}: {e}")
    raise HTTPException(status_code=500, detail="Failed to update about info")

# Legacy endpoint compatibility
@router.post("/{creator_id}/knowledge")
async def add_knowledge_legacy(creator_id: str, data: dict = Body(...)):
    """Legacy: Add knowledge (auto-parse Q&A format)"""
    text = data.get("text", "").strip()
    doc_type = data.get("doc_type", "faq")

    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    # Try to parse Q: A: format
    question = ""
    answer = ""

    if "Q:" in text and "A:" in text:
        parts = text.split("A:", 1)
        question = parts[0].replace("Q:", "").strip()
        answer = parts[1].strip() if len(parts) > 1 else ""
    else:
        # Use text as both question and answer
        question = text[:100] + "..." if len(text) > 100 else text
        answer = text

    if USE_DB:
        try:
            item = db_service.add_knowledge_item(creator_id, question, answer)
            if item:
                return {"status": "ok", "doc_id": item["id"]}
        except Exception as e:
            logger.warning(f"DB add knowledge failed for {creator_id}: {e}")
    raise HTTPException(status_code=500, detail="Failed to add knowledge")

@router.delete("/{creator_id}/knowledge/{item_id}")
async def delete_knowledge_legacy(creator_id: str, item_id: str):
    """Legacy: Delete knowledge item"""
    if USE_DB:
        try:
            success = db_service.delete_knowledge_item(creator_id, item_id)
            if success:
                return {"status": "ok", "message": "Knowledge deleted"}
        except Exception as e:
            logger.warning(f"DB delete knowledge failed for {creator_id}: {e}")
    raise HTTPException(status_code=404, detail="Knowledge item not found")
