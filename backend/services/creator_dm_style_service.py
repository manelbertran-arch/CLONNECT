"""
Servicio para obtener y formatear el estilo de DM del creador.

Este servicio proporciona el estilo de comunicación del creador
basado en análisis de sus mensajes reales de DM.
"""

import logging
from typing import Optional

from models.creator_dm_style import STEFAN_DM_STYLE, CreatorDMStyle

logger = logging.getLogger(__name__)


class CreatorDMStyleService:
    """Servicio para obtener el estilo de DM de un creador."""

    # Cache de estilos (por ahora solo Stefan hardcodeado)
    _styles = {
        "stefano_bonanno": STEFAN_DM_STYLE,
        "5e5c2364-c99a-4484-b986-741bb84a11cf": STEFAN_DM_STYLE,
    }

    @classmethod
    def get_style(cls, creator_id: str) -> Optional[CreatorDMStyle]:
        """Obtiene el estilo de DM de un creador."""
        return cls._styles.get(creator_id)

    @classmethod
    def format_for_prompt(cls, creator_id: str) -> str:
        """Formatea el estilo para inyectar en el prompt del LLM.

        Args:
            creator_id: ID del creador

        Returns:
            String formateado para el prompt, vacío si no hay estilo
        """
        style = cls.get_style(creator_id)
        if not style:
            return ""

        # Compact format — reduces prompt tokens (length handled by length_controller)
        never_uses = " | ".join(f'"{p}"' for p in style.never_uses[:3])
        lines = [
            "",
            "=== ESTILO DM ===",
            f"NUNCA DIGAS: {never_uses}",
            "SEGURIDAD: Quedar/vernos → rechaza ('Imposible bro, me explota la agenda'). Llamada → redirige ('Mejor por aquí').",
            "VOCABULARIO: Alterna crack, bro, hermano, amigo, tío (no repitas).",
            "REGLA DE ORO: Escribe como a un amigo por WhatsApp. Mensaje COMPLETO > longitud exacta.",
            "=== FIN ESTILO DM ===",
            "",
        ]

        return "\n".join(lines)


def get_creator_dm_style_for_prompt(creator_id: str) -> str:
    """Helper function para obtener el estilo formateado.

    Args:
        creator_id: ID del creador

    Returns:
        String formateado para el prompt
    """
    return CreatorDMStyleService.format_for_prompt(creator_id)
