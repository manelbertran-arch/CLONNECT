"""
Response Engine v2 - Integración de Magic Slice.
Fase 1 - Magic Slice

Este módulo integra todos los componentes de Magic Slice:
- ToneProfile para clonar la voz del creador
- CitationContext para referenciar contenido
- Generación de respuestas mejoradas

Habilita los 3 WOWs:
- WOW #2: "Es igualito a como habla"
- WOW #3: "Responde como si fuera yo"
- WOW #4: "Sabe tanto como el creador"
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .tone_analyzer import ToneProfile
from .content_citation import CitationContext, should_cite_content

logger = logging.getLogger(__name__)


@dataclass
class FollowerContext:
    """
    Contexto del seguidor que envía el mensaje.
    """
    follower_id: str
    username: Optional[str] = None
    display_name: Optional[str] = None

    # Historial de interacciones
    previous_messages: List[str] = field(default_factory=list)
    interaction_count: int = 0
    first_interaction: Optional[datetime] = None
    last_interaction: Optional[datetime] = None

    # Metadata adicional
    is_subscriber: bool = False
    subscriber_tier: Optional[str] = None

    def is_returning_follower(self) -> bool:
        """Verifica si es un seguidor que ya ha interactuado antes."""
        return self.interaction_count > 1

    def get_greeting_context(self) -> str:
        """Genera contexto para saludos personalizados."""
        if self.display_name:
            name = self.display_name
        elif self.username:
            name = self.username
        else:
            name = None

        if self.is_returning_follower():
            if name:
                return f"(Seguidor recurrente: {name}, {self.interaction_count} interacciones previas)"
            return f"(Seguidor recurrente, {self.interaction_count} interacciones previas)"
        else:
            if name:
                return f"(Primera interacción con: {name})"
            return "(Primera interacción)"


@dataclass
class ConversationContext:
    """
    Contexto completo para generar una respuesta.
    Combina información del seguidor, creador y citas.
    """
    # Mensaje actual
    message: str

    # Contexto del seguidor
    follower: FollowerContext

    # Perfil del creador (voz clonada)
    creator_tone: Optional[ToneProfile] = None

    # Citas de contenido relevante
    citation_context: Optional[CitationContext] = None

    # Configuración
    max_response_length: int = 500
    include_citations: bool = True
    response_style: str = "casual"  # casual, formal, minimal

    # Metadata
    platform: str = "instagram"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_system_prompt(self) -> str:
        """
        Genera el system prompt completo para el LLM.
        Combina voz del creador + citas + contexto del seguidor.
        """
        sections = []

        # Base del prompt
        sections.append("Eres el asistente de un creador de contenido.")
        sections.append("Tu trabajo es responder mensajes de seguidores como si fueras el creador.")
        sections.append("")

        # Contexto del seguidor
        sections.append("CONTEXTO DEL SEGUIDOR:")
        sections.append(self.follower.get_greeting_context())
        sections.append("")

        # Voz del creador (WOW #2 y #3)
        if self.creator_tone:
            sections.append(self.creator_tone.to_system_prompt_section())
            sections.append("")

        # Citas de contenido (WOW #4)
        if self.citation_context and self.include_citations:
            citation_prompt = self.citation_context.to_prompt_context()
            if citation_prompt:
                sections.append(citation_prompt)
                sections.append("")

        # Instrucciones finales
        sections.append("INSTRUCCIONES FINALES:")
        sections.append(f"- Mantén las respuestas concisas (máximo {self.max_response_length} caracteres)")
        sections.append(f"- Usa un estilo {self.response_style}")
        sections.append("- Responde SOLO lo que se pregunta, no añadas información no solicitada")
        sections.append("- Sé auténtico y natural, como si estuvieras chateando")

        return "\n".join(sections)

    def should_include_citation(self, min_relevance: float = 0.6) -> bool:
        """Determina si se debería incluir una cita en la respuesta."""
        if not self.citation_context or not self.include_citations:
            return False
        return should_cite_content(self.message, self.citation_context, min_relevance)


class ResponseEngineV2:
    """
    Motor de generación de respuestas mejorado.
    Integra todos los componentes de Magic Slice.
    """

    def __init__(
        self,
        llm_client: Any = None,
        default_model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.7
    ):
        """
        Args:
            llm_client: Cliente de LLM (OpenAI, etc.)
            default_model: Modelo por defecto
            temperature: Temperatura para generación
        """
        self.llm_client = llm_client
        self.default_model = default_model
        self.temperature = temperature

    async def generate_response(
        self,
        context: ConversationContext,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Genera una respuesta usando Magic Slice.

        Args:
            context: ConversationContext completo
            model: Modelo a usar (override del default)

        Returns:
            Dict con respuesta y metadata
        """
        try:
            # Construir prompts
            system_prompt = context.to_system_prompt()
            user_message = self._build_user_message(context)

            # Generar respuesta
            if self.llm_client:
                response_text = await self._call_llm(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    model=model or self.default_model
                )
            else:
                # Modo demo sin LLM
                response_text = self._generate_demo_response(context)

            # Procesar respuesta
            processed_response = self._post_process_response(
                response_text,
                context
            )

            # Construir resultado
            result = {
                "response": processed_response,
                "original_message": context.message,
                "citations_used": self._extract_used_citations(context),
                "tone_applied": context.creator_tone is not None,
                "follower_context": {
                    "is_returning": context.follower.is_returning_follower(),
                    "interaction_count": context.follower.interaction_count
                },
                "metadata": {
                    "model": model or self.default_model,
                    "temperature": self.temperature,
                    "response_length": len(processed_response),
                    "generated_at": datetime.now(timezone.utc).isoformat()
                }
            }

            logger.info(
                f"Generated response for follower {context.follower.follower_id}: "
                f"{len(processed_response)} chars"
            )

            return result

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {
                "response": self._get_fallback_response(context),
                "error": str(e),
                "original_message": context.message
            }

    def _build_user_message(self, context: ConversationContext) -> str:
        """Construye el mensaje del usuario para el LLM."""
        parts = [f"Mensaje del seguidor: {context.message}"]

        # Añadir historial si existe
        if context.follower.previous_messages:
            recent = context.follower.previous_messages[-3:]  # Últimos 3 mensajes
            if recent:
                parts.append("\nMensajes previos recientes:")
                for msg in recent:
                    parts.append(f"- {msg}")

        return "\n".join(parts)

    async def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
        model: str
    ) -> str:
        """Llama al LLM para generar respuesta."""
        if not self.llm_client:
            raise ValueError("LLM client not configured")

        # Interfaz genérica - adaptable a diferentes clientes
        try:
            # OpenAI-style interface
            response = await self.llm_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=self.temperature,
                max_tokens=600
            )
            return response.choices[0].message.content
        except AttributeError:
            # Fallback para otros clientes
            if hasattr(self.llm_client, 'generate'):
                return await self.llm_client.generate(
                    system_prompt=system_prompt,
                    user_message=user_message
                )
            raise

    def _generate_demo_response(self, context: ConversationContext) -> str:
        """Genera respuesta demo cuando no hay LLM configurado."""
        greeting = ""

        if context.follower.display_name:
            greeting = f"Hola {context.follower.display_name}! "
        elif context.follower.username:
            greeting = f"Hey @{context.follower.username}! "
        else:
            greeting = "Hola! "

        base_response = f"{greeting}Gracias por tu mensaje."

        # Añadir referencia a cita si aplica
        if context.should_include_citation():
            top_citations = context.citation_context.get_top_citations(1)
            if top_citations:
                citation = top_citations[0]
                ref = citation.to_natural_reference(style=context.response_style)
                base_response += f" Justo {ref} hablé de algo similar."

        return base_response

    def _post_process_response(
        self,
        response: str,
        context: ConversationContext
    ) -> str:
        """Post-procesa la respuesta generada."""
        # Truncar si es muy larga
        if len(response) > context.max_response_length:
            # Buscar punto de corte natural
            truncated = response[:context.max_response_length]
            last_period = truncated.rfind('.')
            last_exclaim = truncated.rfind('!')
            last_question = truncated.rfind('?')

            cut_point = max(last_period, last_exclaim, last_question)
            if cut_point > context.max_response_length * 0.7:
                response = truncated[:cut_point + 1]
            else:
                response = truncated.rstrip() + "..."

        # Limpiar espacios extra
        response = " ".join(response.split())

        return response

    def _extract_used_citations(
        self,
        context: ConversationContext
    ) -> List[Dict[str, Any]]:
        """Extrae información de las citas que podrían usarse."""
        if not context.citation_context:
            return []

        citations = []
        for citation in context.citation_context.get_top_citations():
            citations.append({
                "content_type": citation.content_type.value,
                "source_id": citation.source_id,
                "relevance_score": citation.relevance_score,
                "title": citation.title
            })

        return citations

    def _get_fallback_response(self, context: ConversationContext) -> str:
        """Respuesta de fallback cuando hay error."""
        if context.follower.display_name:
            return f"Hola {context.follower.display_name}! Gracias por escribirme. Te respondo pronto!"
        return "Hola! Gracias por tu mensaje. Te respondo en breve!"


# =============================================================================
# FUNCIONES DE UTILIDAD
# =============================================================================

def create_conversation_context(
    message: str,
    follower_id: str,
    creator_tone: Optional[ToneProfile] = None,
    citation_context: Optional[CitationContext] = None,
    **kwargs
) -> ConversationContext:
    """
    Helper para crear ConversationContext fácilmente.

    Args:
        message: Mensaje del seguidor
        follower_id: ID del seguidor
        creator_tone: Perfil de voz del creador
        citation_context: Contexto de citas
        **kwargs: Parámetros adicionales para FollowerContext y ConversationContext

    Returns:
        ConversationContext configurado
    """
    # Extraer parámetros de follower
    follower_params = {
        'follower_id': follower_id,
        'username': kwargs.pop('username', None),
        'display_name': kwargs.pop('display_name', None),
        'previous_messages': kwargs.pop('previous_messages', []),
        'interaction_count': kwargs.pop('interaction_count', 0),
        'is_subscriber': kwargs.pop('is_subscriber', False),
        'subscriber_tier': kwargs.pop('subscriber_tier', None)
    }

    follower = FollowerContext(**follower_params)

    return ConversationContext(
        message=message,
        follower=follower,
        creator_tone=creator_tone,
        citation_context=citation_context,
        **kwargs
    )


async def enhance_response_with_magic_slice(
    message: str,
    creator_id: str,
    follower_id: str,
    tone_profile: Optional[ToneProfile] = None,
    citation_engine: Any = None,
    llm_client: Any = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Función bridge para integrar Magic Slice en el flujo existente.

    Args:
        message: Mensaje del seguidor
        creator_id: ID del creador
        follower_id: ID del seguidor
        tone_profile: Perfil de voz del creador (opcional, se puede cargar)
        citation_engine: ContentCitationEngine para buscar citas
        llm_client: Cliente LLM
        **kwargs: Parámetros adicionales

    Returns:
        Dict con respuesta mejorada
    """
    # Buscar contenido relevante si hay citation engine
    citation_context = None
    if citation_engine:
        try:
            citation_context = await citation_engine.find_relevant_content(
                creator_id=creator_id,
                query=message
            )
        except Exception as e:
            logger.warning(f"Could not fetch citations: {e}")

    # Crear contexto
    context = create_conversation_context(
        message=message,
        follower_id=follower_id,
        creator_tone=tone_profile,
        citation_context=citation_context,
        **kwargs
    )

    # Generar respuesta
    engine = ResponseEngineV2(llm_client=llm_client)
    result = await engine.generate_response(context)

    return result


def build_magic_slice_prompt(
    tone_profile: Optional[ToneProfile] = None,
    citation_context: Optional[CitationContext] = None,
    follower_name: Optional[str] = None,
    is_returning: bool = False
) -> str:
    """
    Construye un prompt de Magic Slice para inyectar en sistemas existentes.

    Útil para integrar con response engines que ya existen.

    Args:
        tone_profile: Perfil de voz
        citation_context: Contexto de citas
        follower_name: Nombre del seguidor
        is_returning: Si es seguidor recurrente

    Returns:
        String para añadir al system prompt
    """
    sections = []

    # Voz del creador
    if tone_profile:
        sections.append("=== ESTILO DE COMUNICACIÓN DEL CREADOR ===")
        sections.append(tone_profile.to_system_prompt_section())
        sections.append("")

    # Citas
    if citation_context:
        citation_prompt = citation_context.to_prompt_context()
        if citation_prompt:
            sections.append("=== CONTENIDO PARA REFERENCIAR ===")
            sections.append(citation_prompt)
            sections.append("")

    # Contexto del seguidor
    if follower_name or is_returning:
        sections.append("=== CONTEXTO DEL SEGUIDOR ===")
        if follower_name:
            sections.append(f"- Nombre: {follower_name}")
        if is_returning:
            sections.append("- Es un seguidor que ya ha interactuado antes")
        else:
            sections.append("- Primera interacción")
        sections.append("")

    return "\n".join(sections)
