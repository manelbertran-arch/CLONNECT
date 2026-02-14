"""DM Agent Context Integration - Combines all context sources.

Integrates:
- CreatorDNA (Layer 1)
- RelationshipDNA (Layer 3)
- PostContext (Layer 4)

Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

import logging
from typing import Any, Dict, List, Optional

from models.post_context import PostContext
from models.writing_patterns import format_writing_patterns_for_prompt
from services.creator_dm_style_service import get_creator_dm_style_for_prompt
from services.post_context_repository import get_post_context
from services.relationship_dna_repository import get_relationship_dna

logger = logging.getLogger(__name__)


async def get_full_context(
    creator_id: str,
    lead_id: str,
) -> Dict[str, Any]:
    """Get full context for response generation.

    Combines all context layers:
    - RelationshipDNA (per-lead personalization)
    - PostContext (temporal state from posts)

    Args:
        creator_id: Creator identifier
        lead_id: Lead identifier

    Returns:
        Dict with all context data
    """
    context = {
        "creator_id": creator_id,
        "lead_id": lead_id,
        "relationship_dna": None,
        "post_context": None,
    }

    try:
        # Load RelationshipDNA
        dna = get_relationship_dna(creator_id, lead_id)
        if dna:
            context["relationship_dna"] = dna
            logger.debug(f"Loaded DNA for {creator_id}/{lead_id}")

    except Exception as e:
        logger.error(f"Error loading DNA: {e}")

    try:
        # Load PostContext
        post_ctx = get_post_context(creator_id)
        if post_ctx:
            context["post_context"] = post_ctx
            logger.debug(f"Loaded post context for {creator_id}")

    except Exception as e:
        logger.error(f"Error loading post context: {e}")

    return context


async def build_context_prompt(
    creator_id: str,
    lead_id: str,
) -> str:
    """Build context section for bot prompt.

    Combines all context into a single prompt section:
    1. CreatorDMStyle - How the creator writes (applies to ALL conversations)
    2. RelationshipDNA - Personalization for this specific lead
    3. PostContext - Temporal context from recent posts

    Args:
        creator_id: Creator identifier
        lead_id: Lead identifier

    Returns:
        Context string for prompt
    """
    sections = []

    # 1. Get CreatorDMStyle (applies to ALL conversations)
    try:
        creator_style = get_creator_dm_style_for_prompt(creator_id)
        if creator_style:
            sections.append(creator_style)
            logger.debug(f"Added CreatorDMStyle for {creator_id}")
    except Exception as e:
        logger.error(f"Error getting creator style: {e}")

    # 1.5 Get WritingPatterns (detailed writing style)
    try:
        writing_patterns = format_writing_patterns_for_prompt(creator_id)
        if writing_patterns:
            sections.append(writing_patterns)
            logger.debug(f"Added WritingPatterns for {creator_id}")
    except Exception as e:
        logger.error(f"Error getting writing patterns: {e}")

    # 2+3. Parallel DB calls for RelationshipDNA + PostContext (non-blocking)
    import asyncio

    dna = None
    post_ctx = None
    try:
        dna, post_ctx = await asyncio.gather(
            asyncio.to_thread(get_relationship_dna, creator_id, lead_id),
            asyncio.to_thread(get_post_context, creator_id),
        )
    except Exception as e:
        logger.error(f"Error in parallel DB lookups: {e}")

    if dna:
        try:
            dna_section = _format_dna_for_prompt(dna)
            if dna_section:
                sections.append(dna_section)
        except Exception as e:
            logger.error(f"Error formatting DNA: {e}")

    if post_ctx:
        try:
            post_section = _format_post_context_for_prompt(post_ctx)
            if post_section:
                sections.append(post_section)
        except Exception as e:
            logger.error(f"Error formatting post context: {e}")

    if not sections:
        return "Sin contexto especial disponible."

    return "\n\n".join(sections)


def _format_dna_for_prompt(dna: Dict[str, Any]) -> Optional[str]:
    """Format RelationshipDNA for prompt.

    Includes all relevant personalization data for this specific lead.
    The LLM uses this to adapt tone, vocabulary, and style.

    Args:
        dna: RelationshipDNA dict

    Returns:
        Formatted string or None
    """
    if not dna:
        return None

    parts = ["=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ==="]

    # Relationship type and depth
    rel_type = dna.get("relationship_type", "DESCONOCIDO")
    depth = dna.get("depth_level", 0)
    trust = dna.get("trust_score", 0.0)

    # Map relationship type to communication style hint
    rel_hints = {
        "INTIMA": "Comunicación muy cercana y personal",
        "AMISTAD_CERCANA": "Como un buen amigo, confianza alta",
        "AMISTAD_CASUAL": "Amigable pero no demasiado personal",
        "CLIENTE": "Profesional pero cercano",
        "COLABORADOR": "Colega de trabajo, respeto mutuo",
        "DESCONOCIDO": "Cordial, ir conociéndose",
    }
    hint = rel_hints.get(rel_type, "Adapta el tono según la conversación")
    parts.append(f"Relación: {rel_type} ({hint})")

    if depth > 0 or trust > 0.3:
        depth_desc = ["superficial", "conocidos", "confianza", "cercanos", "íntimos"]
        trust_hint = " (alta confianza)" if trust > 0.7 else ""
        parts.append(f"Nivel de profundidad: {depth_desc[min(depth, 4)]}{trust_hint}")

    # Vocabulary guidance (not rules)
    vocab_uses = dna.get("vocabulary_uses", [])
    if vocab_uses:
        parts.append(f"Palabras que sueles usar con esta persona: {', '.join(vocab_uses[:8])}")

    vocab_avoids = dna.get("vocabulary_avoids", [])
    if vocab_avoids:
        parts.append(f"Palabras que esta persona usa pero TÚ no: {', '.join(vocab_avoids[:5])}")

    # Emojis for this relationship
    emojis = dna.get("emojis", [])
    if emojis:
        parts.append(f"Emojis típicos en esta relación: {' '.join(emojis[:6])}")

    # Tone description
    tone = dna.get("tone_description")
    if tone:
        parts.append(f"Tono: {tone}")

    # Recurring topics (context)
    topics = dna.get("recurring_topics", [])
    if topics:
        parts.append(f"Temas frecuentes: {', '.join(topics[:5])}")

    # Private references (inside jokes, shared context)
    private = dna.get("private_references", [])
    if private:
        parts.append(f"Referencias compartidas: {', '.join(private[:3])}")

    # Bot instructions (generated guidance)
    instructions = dna.get("bot_instructions")
    if instructions:
        parts.append(f"\nGuía de comunicación: {instructions}")

    # Golden examples for few-shot learning
    examples = dna.get("golden_examples", [])
    if examples and len(examples) > 0:
        parts.append("\nEjemplos de cómo respondes a esta persona:")
        for ex in examples[:3]:
            # Handle both formats: user/assistant or lead/creator
            user_msg = ex.get("user") or ex.get("lead", "")
            assistant_msg = ex.get("assistant") or ex.get("creator", "")
            if user_msg and assistant_msg:
                parts.append(f"  Usuario: {user_msg[:80]}")
                parts.append(f"  Tú: {assistant_msg[:80]}")

    parts.append("=== FIN CONTEXTO RELACIÓN ===")

    return "\n".join(parts)


def _normalize_topic_list(items: List) -> List[str]:
    """Normalize a list that may contain strings or dicts to a list of strings.

    Handles both formats stored in post_contexts.recent_topics:
    - List of strings: ["yoga", "breathwork"] -> returned as-is
    - List of dicts: [{"topic": "yoga", "count": 5}] -> extracts "topic" key
    """
    if not items:
        return []
    normalized = []
    for item in items:
        if isinstance(item, str):
            normalized.append(item)
        elif isinstance(item, dict):
            # Try common keys: topic, name, product
            for key in ("topic", "name", "product"):
                if key in item:
                    normalized.append(str(item[key]))
                    break
            else:
                # Last resort: use first string value
                for v in item.values():
                    if isinstance(v, str):
                        normalized.append(v)
                        break
    return normalized


def _format_post_context_for_prompt(ctx: Dict[str, Any]) -> Optional[str]:
    """Format PostContext for prompt.

    Args:
        ctx: PostContext dict

    Returns:
        Formatted string or None
    """
    if not ctx:
        return None

    # Normalize recent_topics: handle both list of strings and list of dicts
    raw_topics = ctx.get("recent_topics", [])
    normalized_topics = _normalize_topic_list(raw_topics)

    raw_products = ctx.get("recent_products", [])
    normalized_products = _normalize_topic_list(raw_products)

    # Use the PostContext model for formatting
    try:
        post_context = PostContext(
            creator_id=ctx.get("creator_id", ""),
            active_promotion=ctx.get("active_promotion"),
            promotion_urgency=ctx.get("promotion_urgency"),
            recent_topics=normalized_topics,
            recent_products=normalized_products,
            availability_hint=ctx.get("availability_hint"),
            context_instructions=ctx.get("context_instructions", "Sin contexto especial."),
            expires_at=ctx.get("expires_at"),
        )

        return "CONTEXTO TEMPORAL (POSTS RECIENTES):\n" + post_context.to_prompt_addition()

    except Exception as e:
        logger.error(f"Error creating PostContext: {e}")

        # Fallback to manual formatting
        parts = ["CONTEXTO TEMPORAL:"]

        promo = ctx.get("active_promotion")
        if promo:
            parts.append(f"- Promoción activa: {promo}")

        if normalized_topics:
            parts.append(f"- Temas recientes: {', '.join(normalized_topics[:5])}")

        instructions = ctx.get("context_instructions")
        if instructions:
            parts.append(f"- {instructions}")

        return "\n".join(parts)


def get_context_for_dm_agent(
    creator_id: str,
    lead_id: str,
) -> str:
    """Sync wrapper for getting context (for existing dm_agent code).

    Args:
        creator_id: Creator identifier
        lead_id: Lead identifier

    Returns:
        Context string
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If already in async context, run directly
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, build_context_prompt(creator_id, lead_id))
                return future.result(timeout=5)
        else:
            return loop.run_until_complete(build_context_prompt(creator_id, lead_id))
    except Exception as e:
        logger.error(f"Error getting context: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATION MEMORY INTEGRATION (Phase 2)
# ═══════════════════════════════════════════════════════════════════════════════

from models.conversation_memory import ConversationMemory
from services.memory_service import ConversationMemoryService, get_conversation_memory_service


async def get_conversation_memory(lead_id: str, creator_id: str) -> ConversationMemory:
    """Obtiene la memoria de conversación para un lead."""
    service = get_conversation_memory_service()
    return await service.load(lead_id, creator_id)


async def save_conversation_memory(memory: ConversationMemory):
    """Guarda la memoria de conversación."""
    service = get_conversation_memory_service()
    await service.save(memory)


async def update_memory_after_response(
    lead_id: str,
    creator_id: str,
    lead_message: str,
    bot_response: str,
):
    """Actualiza la memoria después de una respuesta del bot."""
    service = get_conversation_memory_service()
    memory = await service.load(lead_id, creator_id)
    memory = await service.update_memory_after_exchange(memory, lead_message, bot_response)
    await service.save(memory)


def get_memory_context_for_prompt(memory: ConversationMemory) -> str:
    """Obtiene el contexto de memoria formateado para el prompt."""
    service = get_conversation_memory_service()
    return service.get_memory_context_for_prompt(memory)


# ═══════════════════════════════════════════════════════════════════════════════
# BOT ORCHESTRATOR INTEGRATION (Final Integration)
# ═══════════════════════════════════════════════════════════════════════════════

from services.bot_orchestrator import BotOrchestrator, BotResponse, get_bot_orchestrator


async def process_with_orchestrator(
    message: str,
    lead_id: str,
    creator_id: str,
    llm_generator: callable = None,
    context: dict = None,
) -> BotResponse:
    """
    Process a message using the full bot orchestrator.

    This is the recommended entry point for processing messages.
    Includes:
    - Edge case handling (sarcasm, complaints, aggression)
    - Response variations (pools for greetings, thanks, emojis)
    - Conversation memory (persistent context)
    - Message splitting (multi-message for long responses)
    - Natural timing delays (2-30s)

    Args:
        message: User's message
        lead_id: Lead identifier
        creator_id: Creator identifier
        llm_generator: Async function for LLM generation
        context: Additional context

    Returns:
        BotResponse with message(s), delays, and metadata

    Usage:
        response = await process_with_orchestrator(
            message="Hola! Cuánto cuesta?",
            lead_id="lead_123",
            creator_id="creator_456",
            llm_generator=my_llm_function
        )

        # response.messages: ["El precio es 150€", "Te paso el link 😊"]
        # response.delays: [3.2, 1.8]
        # response.should_escalate: False
        # response.used_pool: False
    """
    orchestrator = get_bot_orchestrator()
    return await orchestrator.process_message(
        message=message,
        lead_id=lead_id,
        creator_id=creator_id,
        generate_with_llm=llm_generator,
        context=context,
    )


async def send_orchestrated_response(
    bot_response: BotResponse,
    send_func: callable,
):
    """
    Send an orchestrated response with natural delays.

    Args:
        bot_response: Response from process_with_orchestrator
        send_func: Async function to send a single message
    """
    orchestrator = get_bot_orchestrator()
    await orchestrator.send_responses(bot_response, send_func)
