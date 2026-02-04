"""
DM Orchestrated Router - Test endpoint for the orchestrated DM agent.

This provides endpoints to test the full bot autopilot integration:
- Edge case detection
- Response pools
- Conversation memory
- Message splitting
- Natural timing
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.dm_agent_orchestrated import get_orchestrated_agent

router = APIRouter(prefix="/dm/orchestrated", tags=["DM Orchestrated"])


class DMRequest(BaseModel):
    """Request model for processing a DM."""

    creator_id: str
    lead_id: str
    message: str
    context: Optional[dict] = None


class DMResponse(BaseModel):
    """Response model with orchestration metadata."""

    messages: List[str]
    delays: List[float]
    should_escalate: bool
    used_pool: bool
    edge_case: Optional[str]
    total_delay: float
    is_multi_message: bool


@router.post("/process", response_model=DMResponse)
async def process_dm_orchestrated(request: DMRequest):
    """
    Process a DM using the complete orchestrated system.

    Flow:
    1. Check active hours (8am-11pm Madrid)
    2. Detect edge cases (sarcasm, complaints, aggression)
    3. Try response pools (greetings, thanks, emojis)
    4. Load conversation memory
    5. Generate with LLM if needed
    6. Update memory with facts
    7. Split if >80 chars
    8. Calculate natural delays (2-30s)

    Returns:
        DMResponse with message(s), delays, and metadata
    """
    try:
        agent = await get_orchestrated_agent(request.creator_id)

        response = await agent.process_message(
            message=request.message,
            lead_id=request.lead_id,
            context=request.context or {},
        )

        return DMResponse(
            messages=response.messages,
            delays=response.delays,
            should_escalate=response.should_escalate,
            used_pool=response.used_pool,
            edge_case=response.edge_case,
            total_delay=response.total_delay,
            is_multi_message=response.is_multi_message,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-pool")
async def test_pool_responses(request: DMRequest):
    """
    Test which messages trigger pool responses (no LLM).

    Pool types:
    - greeting: "Hola!", "Hey!", etc.
    - thanks: "Gracias!", "Muchas gracias"
    - emoji_reaction: "💪", "❤️"
    - confirmation: "Ok", "Vale", "Perfecto"
    - laugh: "Jajaja"
    - farewell: "Un abrazo!", "Hablamos!"
    """
    try:
        agent = await get_orchestrated_agent(request.creator_id)

        response = await agent.process_message(
            message=request.message,
            lead_id=request.lead_id,
            context=request.context or {},
        )

        return {
            "message": request.message,
            "used_pool": response.used_pool,
            "response": response.primary_response,
            "pool_response_means": "No LLM was used - fast response from pre-defined pool",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-edge-case")
async def test_edge_case_detection(request: DMRequest):
    """
    Test edge case detection for a message.

    Edge case types:
    - sarcasm: "Claro que sí, como no"
    - irony: "😂😂😂"
    - personal_question: "Tienes novia?"
    - off_topic: "Qué opinas de política?"
    - complaint: "Quiero mi devolución"
    - aggressive: "Eres un idiota"
    """
    try:
        from services.edge_case_handler import get_edge_case_handler

        handler = get_edge_case_handler()
        result = handler.detect(request.message)

        return {
            "message": request.message,
            "edge_type": result.edge_type.value,
            "confidence": result.confidence,
            "should_escalate": result.should_escalate,
            "suggested_response": result.suggested_response,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "dm_orchestrated",
        "features": [
            "edge_case_detection",
            "response_pools",
            "conversation_memory",
            "message_splitting",
            "natural_timing",
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# V2 ENDPOINT - Con prompt universal mejorado
# ═══════════════════════════════════════════════════════════════════════════════

from core.dm_agent_orchestrated_v2 import get_orchestrated_agent_v2


@router.post("/process-v2", response_model=DMResponse)
async def process_dm_orchestrated_v2(request: DMRequest):
    """
    Process DM with V2 system (improved universal prompt).

    Improvements over V1:
    - No unnecessary questions (fixes 35% of issues)
    - Controlled length (fixes 30% of issues)
    - No generic phrases
    - Better punctuation matching
    """
    try:
        agent = await get_orchestrated_agent_v2(request.creator_id)

        response = await agent.process_message(
            message=request.message,
            lead_id=request.lead_id,
            context=request.context or {},
        )

        return DMResponse(
            messages=response.messages,
            delays=response.delays,
            should_escalate=response.should_escalate,
            used_pool=response.used_pool,
            edge_case=response.edge_case,
            total_delay=response.total_delay,
            is_multi_message=response.is_multi_message,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
