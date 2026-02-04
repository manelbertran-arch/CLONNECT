"""
DM Orchestrated Router - Production Bot Autopilot endpoints.

V4 is the production default (100% clean rate + context).

Endpoints:
- /process → V4 (PRODUCTION DEFAULT)
- /process-v4 → V4 (versioned)
- /process-v3 → V3 (legacy)
- /process-v2 → V2 (legacy)
- /process-v1 → V1 (original)
"""

from typing import List, Optional

from core.dm_agent_orchestrated import get_orchestrated_agent
from core.dm_agent_orchestrated_v2 import get_orchestrated_agent_v2
from core.dm_agent_orchestrated_v3 import get_orchestrated_agent_v3
from core.dm_agent_orchestrated_v4 import get_orchestrated_agent_v4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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


# ═══════════════════════════════════════════════════════════════════════════════
# PRODUCTION DEFAULT - V4 (100% clean rate + context + knowledge)
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/process", response_model=DMResponse)
async def process_dm_production(request: DMRequest):
    """
    PRODUCTION DEFAULT - Uses V4 (best performing version).

    V4 achieves 100% clean rate with:
    - Conversation memory (last 15 messages)
    - Creator knowledge (profile, services, FAQs)
    - No unnecessary questions (0%)
    - Stefan-like brevity (avg 7 chars)
    - Natural response pools (9 categories)

    Improvement: V1 31.3% → V4 100%
    """
    try:
        agent = await get_orchestrated_agent_v4(request.creator_id)

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


# ═══════════════════════════════════════════════════════════════════════════════
# V1 ENDPOINT - Original (legacy, 31.3% clean rate)
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/process-v1", response_model=DMResponse)
async def process_dm_orchestrated_v1(request: DMRequest):
    """
    V1 endpoint (original, legacy).

    Clean rate: 31.3%
    Use /process or /process-v3 for production.
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
# V2 ENDPOINT - Improved universal prompt (53.8% clean rate)
# ═══════════════════════════════════════════════════════════════════════════════


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


# ═══════════════════════════════════════════════════════════════════════════════
# V3 ENDPOINT - All improvements integrated (100% clean rate)
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/process-v3")
async def process_dm_orchestrated_v3(request: DMRequest):
    """
    Process DM with V3 system (all improvements).

    V3 improvements over V2:
    - Stricter length control (target 20 chars, max 28)
    - Question removal post-processor
    - Expanded response pools (9 categories)
    - Post-processing pipeline: questions -> length -> punctuation
    """
    try:
        agent = await get_orchestrated_agent_v3(request.creator_id)

        response = await agent.process_message(
            message=request.message,
            lead_id=request.lead_id,
            context=request.context or {},
        )

        return {
            "messages": response.messages,
            "delays": response.delays,
            "should_escalate": response.should_escalate,
            "used_pool": response.used_pool,
            "edge_case": response.edge_case,
            "total_delay": response.total_delay,
            "is_multi_message": response.is_multi_message,
            "processing_steps": response.processing_steps,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# V4 ENDPOINT - Context memory + Creator knowledge
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/process-v4")
async def process_dm_orchestrated_v4(request: DMRequest):
    """
    Process DM with V4 system (context + knowledge).

    V4 adds over V3:
    - Conversation memory (last 15-20 messages)
    - Creator knowledge (profile, services, FAQs)
    - Context-aware responses
    """
    try:
        agent = await get_orchestrated_agent_v4(request.creator_id)

        response = await agent.process_message(
            message=request.message,
            lead_id=request.lead_id,
            context=request.context or {},
        )

        return {
            "messages": response.messages,
            "delays": response.delays,
            "should_escalate": response.should_escalate,
            "used_pool": response.used_pool,
            "edge_case": response.edge_case,
            "total_delay": response.total_delay,
            "is_multi_message": response.is_multi_message,
            "context_used": response.context_used,
            "knowledge_used": response.knowledge_used,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
