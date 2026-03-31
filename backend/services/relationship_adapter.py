"""
Relationship Adapter — ECHO Engine HARMONIZE Layer

Adapta el estilo de comunicación del clon según la categoría del lead
y su historial de relación. Personaliza los templates por defecto
usando el StyleProfile del creador (Sprint 1).

Integración:
- Se invoca en Phase 2 de dm_agent_v2.py (parallel IO) para cargar contexto
- Genera instrucciones que se inyectan en Phase 3 (prompt assembly)
- Ajusta parámetros LLM en Phase 4 (LLM call)

Feature flag: ENABLE_RELATIONSHIP_ADAPTER (default: true)
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

ENABLE_RELATIONSHIP_ADAPTER = os.getenv(
    "ENABLE_RELATIONSHIP_ADAPTER", "true"
).lower() == "true"


# ---------------------------------------------------------------------------
# Data classes (contracts with other modules)
# ---------------------------------------------------------------------------

@dataclass
class StyleProfile:
    """Contract with Sprint 1 (Style Analyzer).
    If Style Analyzer is not available, defaults are used."""
    avg_message_length: float = 45.0
    emoji_ratio: float = 0.05
    question_ratio: float = 0.10
    exclamation_ratio: float = 0.08
    informal_markers: float = 0.15
    vocabulary_richness: float = 0.60
    top_50_words: list = field(default_factory=list)
    muletillas: list = field(default_factory=list)
    emoji_favorites: list = field(default_factory=list)
    code_switching_ratio: float = 0.0
    sentence_length_distribution: dict = field(default_factory=dict)
    avg_response_time_seconds: float = 300.0


@dataclass
class RelationalContext:
    """Output of RelationshipAdapter — passed to prompt_builder."""
    lead_status: str                    # nuevo|interesado|caliente|cliente|fantasma
    prompt_instructions: str            # Text block to inject in prompt
    prohibited_actions: list            # List of prohibitions
    llm_temperature: float              # Adjusted temperature
    llm_max_tokens: int                 # Adjusted max_tokens
    commitment_reminders: str           # Pending commitments (from CommitmentTracker)
    warmth_score: float                 # 0-1, tone calibration
    sales_push_score: float             # 0-1, sales calibration
    max_questions: int                  # Max questions per message
    emoji_target_ratio: float           # Target emoji ratio (unused — Style Normalizer owns emoji control)


# ---------------------------------------------------------------------------
# Default relational profiles per lead category
# ---------------------------------------------------------------------------

RELATIONAL_PROFILES = {
    "nuevo": {
        "display_name": "Lead Nuevo",
        "tone": "profesional-cercano",
        "objective": "cualificar interés sin vender directo",
        "warmth": 0.5,
        "formality": 0.6,
        "sales_push": 0.1,
        "humor": 0.2,
        "emoji_multiplier": 0.7,
        "max_questions_per_msg": 1,
        "prompt_instructions": (
            "Este es un lead NUEVO que no te conoce. "
            "Sé profesional pero cercano. Preséntate brevemente si es el primer mensaje. "
            "Pregunta qué necesita. NO intentes vender nada aún. "
            "NO asumas familiaridad. NO uses jerga interna del negocio."
        ),
        "prohibited": [
            "no asumas que ya te conoce",
            "no menciones precios sin que pregunte",
            "no uses jerga interna del negocio",
        ],
        "llm_params": {"temperature": 0.6, "max_tokens": 200},
    },
    "interesado": {
        "display_name": "Lead Interesado",
        "tone": "cercano, demuestra expertise",
        "objective": "resolver dudas y construir confianza",
        "warmth": 0.7,
        "formality": 0.4,
        "sales_push": 0.3,
        "humor": 0.4,
        "emoji_multiplier": 0.9,
        "max_questions_per_msg": 2,
        "prompt_instructions": (
            "Este lead ya mostró INTERÉS. Sé más cercano. "
            "Comparte experiencias y detalles de servicios si pregunta. "
            "Menciona testimonios o casos de éxito cuando sea natural. "
            "Construye confianza, no presiones la venta."
        ),
        "prohibited": [
            "no presiones para comprar",
            "no inventes testimonios",
        ],
        "llm_params": {"temperature": 0.7, "max_tokens": 250},
    },
    "caliente": {
        "display_name": "Lead Caliente",
        "tone": "entusiasta, cómplice",
        "objective": "cerrar venta y eliminar objeciones",
        "warmth": 0.85,
        "formality": 0.3,
        "sales_push": 0.7,
        "humor": 0.5,
        "emoji_multiplier": 1.0,
        "max_questions_per_msg": 2,
        "prompt_instructions": (
            "Este lead está MUY INTERESADO y cerca de comprar. "
            "Habla como si ya fuera parte de la comunidad. "
            "Resuelve objeciones con entusiasmo. "
            "Puedes mencionar precios y links de pago."
        ),
        "prohibited": [
            "no inventes descuentos que no existen",
            "no hagas promesas no autorizadas",
        ],
        "llm_params": {"temperature": 0.7, "max_tokens": 300},
    },
    "cliente": {
        "display_name": "Cliente",
        "tone": "familiar, de confianza",
        "objective": "fidelizar, upsell natural, soporte",
        "warmth": 0.95,
        "formality": 0.2,
        "sales_push": 0.2,
        "humor": 0.6,
        "emoji_multiplier": 1.1,
        "max_questions_per_msg": 2,
        "prompt_instructions": (
            "Este lead YA ES CLIENTE. Trátalo con confianza. "
            "Prioriza soporte y satisfacción. "
            "Puedes recomendar otros productos de forma natural. "
            "NUNCA intentes venderle lo que ya compró."
        ),
        "prohibited": [
            "no intentes venderle lo que ya compró",
            "no ignores problemas con su compra",
        ],
        "llm_params": {"temperature": 0.75, "max_tokens": 300},
    },
    "fantasma": {
        "display_name": "Lead Fantasma",
        "tone": "ligero, sin presión",
        "objective": "re-engagement suave",
        "warmth": 0.6,
        "formality": 0.3,
        "sales_push": 0.0,
        "humor": 0.5,
        "emoji_multiplier": 0.8,
        "max_questions_per_msg": 1,
        "prompt_instructions": (
            "Este lead lleva tiempo SIN RESPONDER. "
            "Sé breve y casual. Usa un gancho interesante. "
            "NO culpabilices por no responder. NO hagas spam. "
            "Menciona algo nuevo o relevante."
        ),
        "prohibited": [
            "no culpabilices por no responder",
            "no hagas spam",
            "no mandes mensajes largos",
        ],
        "llm_params": {"temperature": 0.65, "max_tokens": 150},
    },
    "amigo": {
        "display_name": "Amigo/a",
        "tone": "ultra-informal, familiar",
        "objective": "conversar como amigo, cero ventas",
        "warmth": 0.95,
        "formality": 0.1,
        "sales_push": 0.0,
        "humor": 0.7,
        "emoji_multiplier": 1.2,
        "max_questions_per_msg": 2,
        "prompt_instructions": (
            "Esta persona es AMIGO/A del creador. "
            "Habla con total confianza e informalidad. "
            "CERO ventas, CERO productos, CERO preguntas de cualificación. "
            "Solo calidez y naturalidad."
        ),
        "prohibited": [
            "no intentes vender nada",
            "no menciones productos ni servicios",
            "no hagas preguntas de cualificación",
        ],
        "llm_params": {"temperature": 0.8, "max_tokens": 150},
    },
}

# Fallback for unknown lead_status
_DEFAULT_STATUS = "nuevo"


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

class RelationshipAdapter:
    """Adapts clone style based on lead category.

    Usage from dm_agent_v2.py:
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(
            lead_status="interesado",
            style_profile=style_profile,       # from Style Analyzer (Sprint 1)
            commitment_text=commitment_text,    # from Commitment Tracker
            lead_memory_summary=memory_summary, # from Memory Engine (Sprint 3)
            relationship_type="DESCONOCIDO",    # from relationship_dna
        )
        # ctx.prompt_instructions → inject in Phase 3
        # ctx.llm_temperature → use in Phase 4
    """

    def __init__(
        self,
        custom_profiles: Optional[dict] = None,
    ):
        """
        Args:
            custom_profiles: Per-creator profile overrides (from creator_config).
                             If None, uses default RELATIONAL_PROFILES.
        """
        self.profiles = custom_profiles or RELATIONAL_PROFILES

    def get_relational_context(
        self,
        lead_status: str,
        style_profile: Optional[StyleProfile] = None,
        commitment_text: str = "",
        lead_memory_summary: str = "",
        relationship_type: str = "DESCONOCIDO",
        lead_name: Optional[str] = None,
        message_count: int = 0,
        has_doc_d: bool = False,
    ) -> RelationalContext:
        """Generate relational context for prompt injection.

        Args:
            lead_status: Lead status (nuevo|interesado|caliente|cliente|fantasma)
            style_profile: Creator's style profile (Sprint 1). None = defaults.
            commitment_text: Pending commitment text (Commitment Tracker).
            lead_memory_summary: Lead memory summary (Memory Engine Sprint 3).
            relationship_type: DNA relationship type (FAMILIA|INTIMA|AMISTAD|DESCONOCIDO).
            lead_name: Lead name (for personalization).
            message_count: Total messages with this lead.
            has_doc_d: True if creator has a Doc D style prompt. When True,
                       ECHO skips tone/style instructions (Doc D already covers them)
                       and only injects data: lead name, memory, commitments.

        Returns:
            RelationalContext with instructions, parameters and restrictions.
        """
        if not ENABLE_RELATIONSHIP_ADAPTER:
            return self._default_context(lead_status)

        # 1. Get base profile
        status = lead_status if lead_status in self.profiles else _DEFAULT_STATUS
        profile = self.profiles[status]
        sp = style_profile or StyleProfile()

        # 2. Calculate emoji target ratio (profile × creator style)
        emoji_target = profile["emoji_multiplier"] * sp.emoji_ratio

        # 3. Build instruction block
        instructions_parts = []

        if has_doc_d:
            # Doc D already defines tone, style, prohibitions, sales behavior.
            # ECHO only injects per-lead DATA — no tone/style instructions.
            logger.debug("[ECHO] Doc D present — data-only mode (no tone instructions)")
        else:
            # Legacy: no Doc D — ECHO provides full tone/style guidance.
            # 3a. Base relational instruction
            instructions_parts.append(
                f"[RELACIÓN CON ESTE LEAD: {profile['display_name'].upper()}]\n"
                f"Objetivo: {profile['objective']}.\n"
                f"{profile['prompt_instructions']}"
            )

            # 3b. Override by relationship_type (family/friends don't get sales)
            if relationship_type in ("FAMILIA", "INTIMA", "AMISTAD"):
                instructions_parts.append(
                    f"\nNOTA: Este lead es {relationship_type.lower()}. "
                    "NO hagas NINGÚN intento de venta. Habla como lo harías "
                    "con alguien cercano."
                )

        # 3c. Lead memory context (always injected — this is data, not style)
        if lead_memory_summary:
            instructions_parts.append(
                f"\n[MEMORIA DEL LEAD]\n{lead_memory_summary}"
            )

        # 3d. Pending commitments (always injected — this is data)
        if commitment_text:
            instructions_parts.append(
                f"\n[COMPROMISOS PENDIENTES]\n{commitment_text}\n"
                "IMPORTANTE: Si hay compromisos pendientes, menciónalos "
                "o cúmplelos en esta respuesta."
            )

        # 3e. Name personalization (always injected — this is data)
        if lead_name and message_count > 3:
            instructions_parts.append(
                f"\nEl lead se llama {lead_name}. Puedes usar su nombre "
                "de vez en cuando de forma natural."
            )

        # 3f. Prohibitions (only when no Doc D — Doc D has its own blacklist)
        prohibitions = profile["prohibited"] if not has_doc_d else []
        if prohibitions:
            instructions_parts.append(
                "\n[PROHIBIDO EN ESTA CONVERSACIÓN]\n"
                + "\n".join(f"- {p}" for p in prohibitions)
            )

        # 4. Assemble final prompt
        prompt_instructions = "\n".join(instructions_parts)

        # 5. Adjust LLM parameters
        llm_params = profile["llm_params"]

        return RelationalContext(
            lead_status=status,
            prompt_instructions=prompt_instructions,
            prohibited_actions=prohibitions,
            llm_temperature=llm_params["temperature"],
            llm_max_tokens=llm_params["max_tokens"],
            commitment_reminders=commitment_text,
            warmth_score=profile["warmth"],
            sales_push_score=profile["sales_push"],
            max_questions=profile["max_questions_per_msg"],
            emoji_target_ratio=emoji_target,
        )

    def get_profile_for_status(self, lead_status: str) -> dict:
        """Return raw profile for a given status. Useful for debug."""
        return self.profiles.get(lead_status, self.profiles[_DEFAULT_STATUS])

    def _default_context(self, lead_status: str) -> RelationalContext:
        """Return minimal context when adapter is disabled."""
        return RelationalContext(
            lead_status=lead_status or _DEFAULT_STATUS,
            prompt_instructions="",
            prohibited_actions=[],
            llm_temperature=0.7,
            llm_max_tokens=250,
            commitment_reminders="",
            warmth_score=0.5,
            sales_push_score=0.3,
            max_questions=2,
            emoji_target_ratio=0.05,
        )


# ---------------------------------------------------------------------------
# Helper: build StyleProfile from Style Analyzer output
# ---------------------------------------------------------------------------

def style_profile_from_analyzer(profile_data: Optional[dict]) -> Optional[StyleProfile]:
    """Convert Style Analyzer JSON output to StyleProfile dataclass.

    Args:
        profile_data: Output from load_profile_from_db() or analyze_creator()

    Returns:
        StyleProfile instance or None
    """
    if not profile_data:
        return None

    try:
        quant = profile_data.get("quantitative", {})
        emoji = quant.get("emoji", {})
        punct = quant.get("punctuation", {})
        length = quant.get("length", {})

        return StyleProfile(
            avg_message_length=length.get("char_mean", 45.0),
            emoji_ratio=emoji.get("avg_per_message", 0.05),
            question_ratio=punct.get("question_pct", 10.0) / 100,
            exclamation_ratio=punct.get("exclamation_pct", 8.0) / 100,
            informal_markers=0.15,  # calculated from abbreviations
            top_50_words=[],
            muletillas=[m[0] for m in quant.get("muletillas_top_20", [])[:10]],
            emoji_favorites=[e[0] for e in emoji.get("top_20", [])[:10]],
        )
    except Exception as e:
        logger.warning(f"[RELATIONSHIP] Failed to parse style profile: {e}")
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_adapter_instance: Optional[RelationshipAdapter] = None


def get_relationship_adapter(
    custom_profiles: Optional[dict] = None,
) -> RelationshipAdapter:
    """Get singleton RelationshipAdapter instance."""
    global _adapter_instance
    if _adapter_instance is None or custom_profiles:
        _adapter_instance = RelationshipAdapter(custom_profiles=custom_profiles)
    return _adapter_instance
