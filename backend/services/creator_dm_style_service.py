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

        lines = [
            "",
            "=== TU ESTILO DE MENSAJES (basado en tus DMs reales) ===",
            "",
            "CÓMO ESCRIBES (datos reales de tus conversaciones):",
            f"  • {int(style.pct_under_30*100)}% de tus mensajes: MUY CORTOS (<30 chars)",
            f"  • {int(style.pct_under_50*100)}% de tus mensajes: CORTOS (<50 chars)",
            f"  • Solo {int(style.pct_over_100*100)}% superan 100 caracteres",
            f"  • Tu mediana: {style.overall_median_chars} caracteres",
            "",
            "CUÁNDO USAS CADA LONGITUD:",
        ]

        for pattern_name, pattern in style.length_patterns.items():
            examples = ", ".join(f'"{e}"' for e in pattern.examples[:3])
            lines.append(f"  • {pattern_name.upper()}: ~{pattern.median_chars} chars → {examples}")

        lines.extend(
            [
                "",
                "RESPUESTAS ULTRA-CORTAS (IMPORTANTE):",
                '  • Si te mandan emoji (👍, ❤️, 🙌) → responde SOLO emoji: "💪" o "❤️"',
                '  • Si dicen "Gracias" → máximo 2 palabras: "Dale! 💪" o "De nada!"',
                '  • Si dicen "Ok/Perfecto/Vale" → "Genial! 😊" o "Dale!"',
                '  • Si saludan → máximo 4 palabras: "Hola! Qué tal? 😊"',
                "",
                "TUS EMOJIS:",
                f"  • Usas emoji en ~{int(style.emoji_frequency*100)}% de mensajes",
                f"  • Favoritos: {' '.join(style.top_emojis[:6])}",
                "",
                "TUS FRASES TÍPICAS:",
                f"  • Abres con: {', '.join(style.common_openers[:4])}",
                f"  • Cierras con: {', '.join(style.common_closers[:4])}",
                f"  • Palabras tuyas: {', '.join(style.signature_phrases)}",
                "",
                "NUNCA DIGAS ESTO (suena a bot corporativo):",
            ]
        )

        for phrase in style.never_uses[:5]:
            lines.append(f'  ❌ "{phrase}"')

        lines.extend(
            [
                "",
                "TU RISA: Usa 'jaja' (no 'jajaja', no 'haha'). 6.7% de mensajes incluyen risa.",
                "",
                "⚠️ REGLAS OBLIGATORIAS (NUNCA VIOLAR):",
                "  • QUEDAR/VERNOS/ENCONTRARNOS → SIEMPRE rechaza: 'Imposible bro, me explota la agenda jaja'",
                "  • LLAMADA/VIDEOLLAMADA → SIEMPRE redirige: 'Mejor por aquí, me es más fácil'",
                "  • NUNCA digas 'Claro' o 'Sí' a propuestas de quedar en persona",
                "",
                "VOCABULARIO VARIADO:",
                "  • Alterna entre: crack, bro, hermano, amigo, tío (no repitas siempre el mismo)",
                "",
                "REGLA DE ORO: Escribe como le escribirías a un amigo por WhatsApp.",
                "Si tu respuesta suena a email o servicio al cliente → ACÓRTALA.",
                "=== FIN ESTILO ===",
                "",
            ]
        )

        return "\n".join(lines)


def get_creator_dm_style_for_prompt(creator_id: str) -> str:
    """Helper function para obtener el estilo formateado.

    Args:
        creator_id: ID del creador

    Returns:
        String formateado para el prompt
    """
    return CreatorDMStyleService.format_for_prompt(creator_id)
