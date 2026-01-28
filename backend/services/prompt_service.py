"""
Prompt Service - Build LLM prompts for conversations.

Extracted from dm_agent.py as part of REFACTOR-PHASE2.
Provides structured prompt building for system and user contexts.
"""
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Service for building LLM prompts.

    Provides methods to construct system prompts with personality
    and user context with conversation history.
    """

    # Tone configurations
    TONES = {
        "professional": {
            "description": "formal y profesional",
            "emoji_rule": "- Uso de emojis: NINGUNO (tono profesional)",
        },
        "casual": {
            "description": "muy informal y cercano",
            "emoji_rule": "- Uso de emojis: frecuente (2-3 por mensaje)",
        },
        "friendly": {
            "description": "amigable y cercano, equilibrando profesionalismo con calidez",
            "emoji_rule": "- Uso de emojis: moderado (1-2 por mensaje)",
        },
    }

    def __init__(self, personality: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the prompt builder.

        Args:
            personality: Optional personality configuration with keys:
                - tone: 'professional', 'casual', or 'friendly'
                - name: Name of the assistant
                - custom_instructions: Additional custom instructions
        """
        self.personality = personality or {}
        self.default_tone = "friendly"
        self.default_name = "Asistente"

    def build_system_prompt(
        self,
        products: Optional[List[Dict[str, Any]]] = None,
        creator_name: Optional[str] = None,
        custom_instructions: Optional[str] = None,
    ) -> str:
        """
        Build the system prompt for the LLM.

        Args:
            products: List of products/services to include
            creator_name: Name of the creator/business
            custom_instructions: Additional instructions to include

        Returns:
            Complete system prompt string
        """
        tone_key = self.personality.get("tone", self.default_tone)
        tone_config = self.TONES.get(tone_key, self.TONES["friendly"])
        name = self.personality.get("name", self.default_name)

        # Build base prompt
        prompt_parts = [
            f"Eres {name}, un asistente virtual {tone_config['description']}.",
            "Tu objetivo es ayudar a los usuarios y guiarlos hacia las soluciones disponibles.",
            "",
            "=== PERSONALIDAD ===",
            tone_config["emoji_rule"],
        ]

        # Add creator info
        if creator_name:
            prompt_parts.append(f"- Representas a: {creator_name}")

        prompt_parts.append("=== FIN PERSONALIDAD ===")

        # Add products section
        if products:
            prompt_parts.append("")
            prompt_parts.append("=== PRODUCTOS Y SERVICIOS ===")
            for p in products:
                product_name = p.get("name", "Producto")
                price = p.get("price", "Consultar")
                description = p.get("description", "")
                url = p.get("url", "")

                line = f"- {product_name}: {price}€"
                if description:
                    line += f" - {description}"
                if url:
                    line += f"\n  Link: {url}"
                prompt_parts.append(line)
            prompt_parts.append("=== FIN PRODUCTOS ===")

        # Add custom instructions
        if custom_instructions:
            prompt_parts.append("")
            prompt_parts.append("=== INSTRUCCIONES ADICIONALES ===")
            prompt_parts.append(custom_instructions)
            prompt_parts.append("=== FIN INSTRUCCIONES ===")

        # Add guidelines
        prompt_parts.extend([
            "",
            "=== DIRECTRICES ===",
            "- Responde siempre en el idioma del usuario",
            "- Se conciso pero informativo",
            "- Guia hacia la compra cuando sea apropiado, sin presionar",
            "- NUNCA inventes informacion sobre precios o productos",
            "- Si no tienes la informacion, indica que consultaras",
            "=== FIN DIRECTRICES ===",
        ])

        return "\n".join(prompt_parts)

    def build_user_context(
        self,
        username: str,
        stage: str,
        history: Optional[List[Dict[str, str]]] = None,
        lead_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build user context for the LLM.

        Args:
            username: User's username or display name
            stage: Lead stage (NUEVO, INTERESADO, CLIENTE, etc.)
            history: Conversation history as list of {role, content} dicts
            lead_info: Additional lead information

        Returns:
            User context string
        """
        context_parts = [
            "=== CONTEXTO DEL USUARIO ===",
            f"Usuario: {username}",
            f"Etapa: {stage}",
        ]

        # Add lead info if available
        if lead_info:
            if lead_info.get("interests"):
                interests = ", ".join(lead_info["interests"])
                context_parts.append(f"Intereses: {interests}")
            if lead_info.get("objections"):
                objections = ", ".join(lead_info["objections"])
                context_parts.append(f"Objeciones previas: {objections}")
            if lead_info.get("purchase_score"):
                context_parts.append(f"Score de compra: {lead_info['purchase_score']}")

        context_parts.append("=== FIN CONTEXTO ===")

        # Add conversation history
        if history:
            context_parts.append("")
            context_parts.append("=== HISTORIAL DE CONVERSACION ===")
            # Include last 10 messages to avoid context overflow
            for msg in history[-10:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                # Truncate very long messages
                if len(content) > 300:
                    content = content[:297] + "..."
                role_label = "Usuario" if role == "user" else "Asistente"
                context_parts.append(f"{role_label}: {content}")
            context_parts.append("=== FIN HISTORIAL ===")

        return "\n".join(context_parts)

    def build_complete_prompt(
        self,
        user_message: str,
        username: str,
        stage: str,
        products: Optional[List[Dict[str, Any]]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> Dict[str, str]:
        """
        Build complete prompt with system and user parts.

        Args:
            user_message: The current user message
            username: User's username
            stage: Lead stage
            products: Products to include in system prompt
            history: Conversation history
            **kwargs: Additional arguments for build_system_prompt

        Returns:
            Dict with 'system' and 'user' prompt strings
        """
        system_prompt = self.build_system_prompt(products=products, **kwargs)
        user_context = self.build_user_context(
            username=username,
            stage=stage,
            history=history,
        )

        return {
            "system": system_prompt,
            "user": f"{user_context}\n\nMensaje actual: {user_message}",
        }
