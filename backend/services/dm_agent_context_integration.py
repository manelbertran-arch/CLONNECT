"""DM Agent Context Integration - Combines all context sources.

Integrates:
- CreatorDNA (Layer 1)
- RelationshipDNA (Layer 3)
- PostContext (Layer 4)

Part of POST-CONTEXT-DETECTION feature (Layer 4).
"""

import logging
from typing import Any, Dict, Optional

from models.post_context import PostContext
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

    Combines all context into a single prompt section.

    Args:
        creator_id: Creator identifier
        lead_id: Lead identifier

    Returns:
        Context string for prompt
    """
    sections = []

    # Get RelationshipDNA
    try:
        dna = get_relationship_dna(creator_id, lead_id)
        if dna:
            dna_section = _format_dna_for_prompt(dna)
            if dna_section:
                sections.append(dna_section)
    except Exception as e:
        logger.error(f"Error formatting DNA: {e}")

    # Get PostContext
    try:
        post_ctx = get_post_context(creator_id)
        if post_ctx:
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
            user_msg = ex.get("user", "")
            assistant_msg = ex.get("assistant", "")
            if user_msg and assistant_msg:
                parts.append(f"  Usuario: {user_msg[:80]}")
                parts.append(f"  Tú: {assistant_msg[:80]}")

    parts.append("=== FIN CONTEXTO RELACIÓN ===")

    return "\n".join(parts)


def _format_post_context_for_prompt(ctx: Dict[str, Any]) -> Optional[str]:
    """Format PostContext for prompt.

    Args:
        ctx: PostContext dict

    Returns:
        Formatted string or None
    """
    if not ctx:
        return None

    # Use the PostContext model for formatting
    try:
        post_context = PostContext(
            creator_id=ctx.get("creator_id", ""),
            active_promotion=ctx.get("active_promotion"),
            promotion_urgency=ctx.get("promotion_urgency"),
            recent_topics=ctx.get("recent_topics", []),
            recent_products=ctx.get("recent_products", []),
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

        topics = ctx.get("recent_topics", [])
        if topics:
            parts.append(f"- Temas recientes: {', '.join(topics[:5])}")

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
