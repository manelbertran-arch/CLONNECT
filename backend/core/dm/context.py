"""
DM Agent Phase 2-3: Memory & Context Loading.

Handles intent classification, parallel DB/IO operations,
RAG retrieval, relationship detection, and prompt assembly.
"""

import asyncio
import logging
import os
import time
from typing import TYPE_CHECKING, Dict

from core.agent_config import AGENT_THRESHOLDS
from core.dm.models import (
    ContextBundle,
    DetectionResult,
    ENABLE_ADVANCED_PROMPTS,
    ENABLE_CITATIONS,
    ENABLE_CONVERSATION_STATE,
    ENABLE_DNA_AUTO_CREATE,
    ENABLE_LEAD_CATEGORIZER,
    ENABLE_QUERY_EXPANSION,
    ENABLE_QUESTION_CONTEXT,
    ENABLE_RELATIONSHIP_DETECTION,
)
from core.rag.reranker import ENABLE_RERANKING
from services import LeadStage

if TYPE_CHECKING:
    from core.dm.agent import DMResponderAgentV2

logger = logging.getLogger(__name__)


async def phase_memory_and_context(
    agent: "DMResponderAgentV2",
    message: str,
    sender_id: str,
    metadata: Dict,
    cognitive_metadata: Dict,
    detection: DetectionResult,
) -> ContextBundle:
    """Phase 2-3: Intent classification, parallel DB/IO, context assembly."""
    ctx = ContextBundle()
    _t1 = time.monotonic()

    # Step 2: Classify intent
    intent = agent.intent_classifier.classify(message)
    intent_value = intent.value if hasattr(intent, "value") else str(intent)
    logger.debug(f"Intent classified: {intent_value}")
    _t1a = time.monotonic()

    # Step 2b: Analyze bot's last question for short affirmation context
    if ENABLE_QUESTION_CONTEXT:
        try:
            from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer, is_short_affirmation

            if is_short_affirmation(message):
                hist = metadata.get("history", [])
                last_bot = next(
                    (m.get("content", "") for m in reversed(hist) if m.get("role") == "assistant"),
                    None,
                )
                if last_bot:
                    q_type, q_conf = get_bot_question_analyzer().analyze_with_confidence(last_bot)
                    if q_type != QuestionType.UNKNOWN:
                        cognitive_metadata["question_context"] = q_type.value
        except Exception as e:
            logger.debug(f"Question context failed: {e}")

    # =================================================================
    # PARALLEL DB/IO + CONTEXT LOADING
    # =================================================================
    from services.dm_agent_context_integration import build_context_prompt as _build_ctx
    from services.relationship_dna_repository import get_relationship_dna as _get_raw_dna

    async def _load_conv_state():
        if not ENABLE_CONVERSATION_STATE:
            return "", {}
        try:
            from core.conversation_state import get_state_manager

            state_mgr = get_state_manager()
            conv_state = await asyncio.to_thread(state_mgr.get_state, sender_id, agent.creator_id)
            state_ctx = state_mgr.build_enhanced_prompt(conv_state)
            return state_ctx, {"conversation_phase": conv_state.phase.value}
        except Exception as e:
            logger.debug(f"Conversation state failed: {e}")
            return "", {}

    follower, dna_context, (state_context, state_meta), raw_dna = await asyncio.gather(
        agent.memory_store.get_or_create(
            creator_id=agent.creator_id,
            follower_id=sender_id,
            username=metadata.get("username", sender_id),
        ),
        _build_ctx(agent.creator_id, sender_id),
        _load_conv_state(),
        asyncio.to_thread(_get_raw_dna, agent.creator_id, sender_id),
    )
    cognitive_metadata.update(state_meta)

    # Memory recall (per-lead context from past conversations)
    memory_context = ""
    if os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true":
        try:
            from services.memory_engine import get_memory_engine

            mem_engine = get_memory_engine()
            memory_context = await mem_engine.recall(agent.creator_id, sender_id, message)
            if memory_context:
                cognitive_metadata["memory_recalled"] = True
                cognitive_metadata["memory_chars"] = len(memory_context)
        except Exception as e:
            logger.debug(f"[MEMORY] recall failed: {e}")

    # ECHO Engine: Load pending commitments
    commitment_text = ""
    if os.getenv("ENABLE_COMMITMENT_TRACKING", "true").lower() == "true":
        try:
            from services.commitment_tracker import get_commitment_tracker

            tracker = get_commitment_tracker()
            commitment_text = await asyncio.to_thread(tracker.get_pending_text, sender_id)
            if commitment_text:
                cognitive_metadata["commitments_pending"] = True
        except Exception as e:
            logger.debug(f"[COMMITMENT] load failed: {e}")

    _bot_instructions = ""
    if dna_context:
        logger.debug(f"DNA context loaded for {sender_id}")
    if raw_dna:
        _bot_instructions = raw_dna.get("bot_instructions", "") or ""
        metadata["dna_data"] = raw_dna

    # Auto-create seed DNA if none exists and lead has some history
    if ENABLE_DNA_AUTO_CREATE and not dna_context and follower.total_messages >= 2:
        try:
            from services.relationship_type_detector import RelationshipTypeDetector

            hist = metadata.get("history", [])
            if len(hist) >= 2:
                det_result = RelationshipTypeDetector().detect(hist)
                detected_type = det_result.get("type", "DESCONOCIDO")
                det_confidence = det_result.get("confidence", 0)

                async def _create_seed_dna():
                    try:
                        from services.relationship_dna_repository import (
                            create_relationship_dna,
                            get_relationship_dna as _get_dna,
                        )

                        existing = await asyncio.to_thread(_get_dna, agent.creator_id, sender_id)
                        if existing:
                            return
                        await asyncio.to_thread(
                            create_relationship_dna,
                            creator_id=agent.creator_id,
                            follower_id=sender_id,
                            relationship_type=detected_type,
                            trust_score=round(det_confidence * 0.3, 2),
                            depth_level=0,
                        )
                        logger.info(
                            f"[DNA-SEED] Created seed DNA for {sender_id}: "
                            f"type={detected_type} confidence={det_confidence}"
                        )
                    except Exception as e:
                        logger.debug(f"Seed DNA creation failed: {e}")

                asyncio.create_task(_create_seed_dna())
                cognitive_metadata["relationship_type"] = detected_type
                cognitive_metadata["dna_seed_created"] = True
        except Exception as e:
            logger.debug(f"DNA auto-create check failed: {e}")

    _t1b = time.monotonic()
    logger.info(f"[TIMING] Phase 2 sub: intent={int((_t1a - _t1) * 1000)}ms parallel_io={int((_t1b - _t1a) * 1000)}ms")

    # RAG retrieval — skip for simple intents
    _SKIP_RAG_INTENTS = {"greeting", "farewell", "thanks", "saludo", "despedida"}
    rag_query = message
    if intent_value in _SKIP_RAG_INTENTS:
        rag_results = []
        cognitive_metadata["rag_skipped"] = intent_value
        logger.info(f"[RAG] Skipped for intent={intent_value} (no knowledge needed)")
    else:
        if ENABLE_QUERY_EXPANSION:
            try:
                from core.query_expansion import get_query_expander

                expanded = get_query_expander().expand(message, max_expansions=2)
                if len(expanded) > 1:
                    rag_query = " ".join(expanded)
                    cognitive_metadata["query_expanded"] = True
            except Exception as e:
                logger.debug(f"Query expansion failed: {e}")
        rag_results = agent.semantic_rag.search(
            rag_query, top_k=agent.config.rag_top_k, creator_id=agent.creator_id
        )
    if rag_results:
        logger.info(f"[RAG] query='{rag_query[:50]}' results={len(rag_results)}")
    else:
        logger.debug(f"[RAG] query='{rag_query[:50]}' results=0")

    if ENABLE_RERANKING and rag_results:
        cognitive_metadata["rag_reranked"] = True

    rag_context = _format_rag_context(rag_results)

    # Relationship type detection (in-memory)
    if ENABLE_RELATIONSHIP_DETECTION:
        try:
            from services.relationship_type_detector import RelationshipTypeDetector

            hist = metadata.get("history", [])
            if len(hist) >= 2:
                rel_result = RelationshipTypeDetector().detect(hist)
                if rel_result.get("confidence", 0) > 0.5:
                    cognitive_metadata["relationship_type"] = rel_result["type"]
        except Exception as e:
            logger.debug(f"Relationship detection failed: {e}")

    _rel_type = cognitive_metadata.get("relationship_type", "")
    is_friend = _rel_type in ("amigo", "FAMILIA", "AMISTAD_CERCANA", "INTIMA")

    # Lead stage
    current_stage = _get_lead_stage(agent, follower, metadata)

    # Knowledge base lookup
    kb_context = ""
    try:
        from services.knowledge_base import get_knowledge_base

        kb = get_knowledge_base(agent.creator_id)
        kb_result = kb.lookup(message)
        if kb_result:
            kb_context = f"Info factual relevante: {kb_result}"
            logger.debug(f"KB hit for message: {message[:50]}")
    except Exception as e:
        logger.debug(f"KB lookup failed: {e}")

    # Build prompts
    prompt_override = metadata.get("system_prompt_override", "")
    advanced_section = ""
    if ENABLE_ADVANCED_PROMPTS:
        try:
            from core.prompt_builder import build_rules_section

            creator_name = agent.personality.get("name", "el creador")
            advanced_section = build_rules_section(creator_name)
        except Exception as e:
            logger.debug(f"Advanced prompts failed: {e}")

    citation_context = ""
    if ENABLE_CITATIONS:
        try:
            from core.citation_service import get_citation_prompt_section

            citation_context = get_citation_prompt_section(agent.creator_id, message)
        except Exception as e:
            logger.debug(f"Citation loading failed: {e}")

    # Friend/family context suppression
    friend_context = ""
    if is_friend:
        if _rel_type == "FAMILIA":
            friend_context = (
                "IMPORTANTE: Esta persona es FAMILIAR del creador (padre, madre, hijo, etc.). "
                "NO intentes vender, ofrecer productos, ni hacer preguntas de cualificación. "
                "Habla con cariño y naturalidad. Si pide ayuda, ayúdale directamente. "
                "NO uses frases como 'contame qué te trae por acá' ni similares."
            )
            logger.info("[A1] Family member detected — suppressing acquisition behavior")
        else:
            friend_context = (
                "IMPORTANTE: Esta persona es un AMIGO/A del creador, NO un lead. "
                "NO intentes vender, ofrecer productos, ni hacer preguntas de cualificación. "
                "Habla de forma natural, personal y relajada como con un amigo cercano. "
                "NO uses frases como 'contame qué te trae por acá' ni similares."
            )
            logger.info("[A1] Friend detected — suppressing acquisition behavior")

    # Few-shot examples from calibration
    few_shot_section = ""
    if agent.calibration:
        try:
            from services.calibration_loader import get_few_shot_section

            few_shot_section = get_few_shot_section(agent.calibration, max_examples=2)
        except Exception as e:
            logger.debug(f"Few-shot loading failed: {e}")

    # Audio context
    from core.dm.helpers import build_audio_context
    audio_context = build_audio_context(metadata, cognitive_metadata)

    # ECHO Engine: Relational context
    relational_block = ""
    _echo_rel_ctx = None
    if os.getenv("ENABLE_RELATIONSHIP_ADAPTER", "true").lower() == "true":
        try:
            from services.relationship_adapter import RelationshipAdapter, style_profile_from_analyzer
            from core.style_analyzer import load_profile_from_db
            from api.database import SessionLocal
            from api.models import Creator

            _sp = None
            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=agent.creator_id).first()
                if creator:
                    _raw_profile = load_profile_from_db(str(creator.id))
                    _sp = style_profile_from_analyzer(_raw_profile)
            finally:
                session.close()

            adapter = RelationshipAdapter()
            _dna_rel_type = "DESCONOCIDO"
            if isinstance(raw_dna, dict):
                _dna_rel_type = raw_dna.get("relationship_type", "DESCONOCIDO")

            _echo_rel_ctx = adapter.get_relational_context(
                lead_status=current_stage,
                style_profile=_sp,
                commitment_text=commitment_text,
                lead_memory_summary=memory_context,
                relationship_type=_dna_rel_type,
                lead_name=follower.username if hasattr(follower, 'username') else None,
                message_count=follower.total_messages if hasattr(follower, 'total_messages') else 0,
            )
            relational_block = _echo_rel_ctx.prompt_instructions
            if relational_block:
                cognitive_metadata["relational_adapted"] = True
                cognitive_metadata["lead_warmth"] = _echo_rel_ctx.warmth_score
        except Exception as e:
            logger.debug(f"[ECHO] Relationship Adapter failed: {e}")

    # Priority ordering: style first, then knowledge, then context
    combined_context = "\n\n".join(
        filter(
            None,
            [
                agent.style_prompt,
                friend_context,
                relational_block,
                rag_context,
                memory_context,
                few_shot_section,
                dna_context,
                state_context,
                audio_context,
                kb_context,
                citation_context,
                advanced_section,
                prompt_override,
            ],
        )
    )
    prompt_products = [] if is_friend else agent.products
    system_prompt = agent.prompt_builder.build_system_prompt(
        products=prompt_products, custom_instructions=combined_context
    )

    from core.dm.helpers import get_history_from_follower
    history = get_history_from_follower(follower)
    _t1c = time.monotonic()
    logger.info(f"[TIMING] Phase 3 sub: fast_ops={int((_t1c - _t1b) * 1000)}ms")

    # Build lead_info for richer context
    _lead_info = {}
    if follower.interests:
        _lead_info["interests"] = follower.interests[:5]
    if follower.objections_raised:
        _lead_info["objections"] = follower.objections_raised[:5]
    if follower.products_discussed:
        _lead_info["products_discussed"] = follower.products_discussed[:5]
    if follower.purchase_intent_score > 0:
        _lead_info["purchase_score"] = round(follower.purchase_intent_score, 2)
    if follower.is_customer:
        _lead_info["is_customer"] = True
    if follower.conversation_summary:
        _lead_info["summary"] = follower.conversation_summary[:200]

    user_context = agent.prompt_builder.build_user_context(
        username=follower.username or sender_id,
        stage=current_stage,
        history=history,
        lead_info=_lead_info if _lead_info else None,
    )

    _t2 = time.monotonic()
    logger.info(f"[TIMING] Phase 2-3 (context+RAG+prompt): {int((_t2 - _t1) * 1000)}ms")

    # Populate context bundle
    ctx.intent = intent
    ctx.intent_value = intent_value
    ctx.follower = follower
    ctx.dna_context = dna_context
    ctx.state_context = state_context
    ctx.raw_dna = raw_dna
    ctx.memory_context = memory_context
    ctx.commitment_text = commitment_text
    ctx.bot_instructions = _bot_instructions
    ctx.rag_results = rag_results
    ctx.rag_context = rag_context
    ctx.is_friend = is_friend
    ctx.rel_type = _rel_type
    ctx.current_stage = current_stage
    ctx.kb_context = kb_context
    ctx.system_prompt = system_prompt
    ctx.history = history
    ctx.user_context = user_context
    ctx.few_shot_section = few_shot_section
    ctx.audio_context = audio_context
    ctx.relational_block = relational_block
    ctx.echo_rel_ctx = _echo_rel_ctx
    ctx.friend_context = friend_context
    ctx.citation_context = citation_context
    ctx.advanced_section = advanced_section
    ctx.prompt_override = prompt_override
    ctx.cognitive_metadata = cognitive_metadata
    return ctx


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _format_rag_context(rag_results: list) -> str:
    """Format RAG results as context for the prompt."""
    if not rag_results:
        return ""
    context_parts = ["Informacion relevante:"]
    for result in rag_results[:3]:
        content = result.get("content", "")[:200]
        score = result.get("score", 0)
        context_parts.append(f"- [{score:.2f}] {content}")
    return "\n".join(context_parts)


def _get_lead_stage(agent: "DMResponderAgentV2", follower, metadata: Dict) -> str:
    """Get current lead stage for user."""
    if metadata.get("lead_stage"):
        return metadata["lead_stage"]
    if ENABLE_LEAD_CATEGORIZER:
        try:
            from core.lead_categorizer import get_lead_categorizer

            messages = follower.last_messages[-20:] if follower.last_messages else []
            category, score, reason = get_lead_categorizer().categorize(
                messages=messages, is_customer=follower.is_customer,
            )
            logger.debug(f"Lead categorizer: {category.value} ({reason})")
            return category.value
        except Exception as e:
            logger.debug(f"Lead categorizer failed: {e}")
    if follower.is_customer:
        return LeadStage.CLIENTE.value
    if follower.purchase_intent_score >= 0.7:
        return LeadStage.CALIENTE.value
    if follower.purchase_intent_score >= 0.4:
        return LeadStage.INTERESADO.value
    return LeadStage.NUEVO.value


