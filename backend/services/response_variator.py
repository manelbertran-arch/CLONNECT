"""
ResponseVariator - Añade variación natural a las respuestas del bot.

Evita que el bot responda siempre igual al mismo tipo de mensaje.
"""
import random
import re
from collections import deque
from typing import Optional, Tuple

from models.response_variations import STEFAN_RESPONSE_POOLS, ResponsePool


class ResponseVariator:
    """Servicio que añade variación a las respuestas."""

    def __init__(self, pools: dict = None):
        self.pools = pools or STEFAN_RESPONSE_POOLS
        # Historial reciente para evitar repetición inmediata
        self.recent_responses: deque = deque(maxlen=10)

    def detect_message_type(self, message: str) -> Optional[str]:
        """
        Detecta el tipo de mensaje para usar un pool.

        Returns:
            Tipo de pool o None si debe usar LLM.
        """
        message_lower = message.lower().strip()
        message_clean = re.sub(r"[^\w\s]", "", message_lower)

        # PROPUESTAS DE QUEDAR - PRIORIDAD MÁXIMA (Stefan siempre rechaza)
        meeting_words = [
            "quedar",
            "quedamos",
            "vernos",
            "encontrarnos",
            "veámonos",
            "veamonos",
            "viéndonos",
            "viendonos",
            "tomarnos algo",
            "tomar algo",
            "un café",
            "un cafe",
            "unas birras",
            "unas cervezas",
            "podemos vernos",
            "nos vemos mañana",
            "nos juntamos",
        ]
        if any(m in message_lower for m in meeting_words):
            return "meeting_request"

        # SALUDOS - Alta prioridad
        greetings = [
            "hola",
            "hey",
            "buenas",
            "ey",
            "buenos días",
            "buenas tardes",
            "buenas noches",
            "qué tal",
            "que tal",
            "hi",
            "hello",
        ]
        if any(
            message_clean.startswith(g) or message_clean == g for g in greetings
        ):
            if len(message_clean.split()) <= 4:  # Saludo corto
                return "greeting"

        # DESPEDIDAS - Alta prioridad (antes de risas por "hablamos")
        farewells = [
            "adiós",
            "adios",
            "chao",
            "chau",
            "bye",
            "hasta luego",
            "nos vemos",
            "hablamos",
            "cuídate",
            "cuidate",
            "un abrazo",
        ]
        if any(f in message_lower for f in farewells):
            return "farewell"

        # AGRADECIMIENTOS
        thanks_words = ["gracias", "thank", "thx", "grax", "muchas gracias"]
        if any(t in message_lower for t in thanks_words):
            if len(message.split()) <= 5:  # Agradecimiento corto
                return "thanks"

        # CONFIRMACIONES - Antes de emoji (ok, vale, etc.)
        confirmations = [
            "ok",
            "vale",
            "perfecto",
            "genial",
            "bien",
            "de acuerdo",
            "entendido",
            "claro",
            "sí",
            "si",
            "okey",
            "okay",
            "listo",
        ]
        if message_clean in confirmations or any(
            message_clean.startswith(c + " ") for c in confirmations
        ):
            if len(message.split()) <= 3:
                return "confirmation"

        # ENTUSIASMO SIMPLE - Antes de risas
        enthusiasm = [
            "increíble",
            "increible",
            "wow",
            "guau",
            "qué bien",
            "que bien",
            "me encanta",
            "qué bueno",
        ]
        if any(e in message_lower for e in enthusiasm):
            if len(message.split()) <= 4:
                return "enthusiasm"

        # RISAS - Solo patrones claros de risa
        laugh_patterns = [r"jaja+", r"jeje+", r"^ja+$", r"😂", r"🤣"]
        if any(re.search(p, message_lower, re.IGNORECASE) for p in laugh_patterns):
            if len(message) <= 20:  # Risa corta
                return "laugh"

        # EMOJI SOLO - Después de todo lo demás
        # Patrón amplio para emojis
        emoji_chars = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"  # dingbats
            "\U0001F900-\U0001F9FF"  # supplemental
            "\U00002600-\U000026FF"  # misc symbols
            "\U0001FA00-\U0001FA6F"  # chess, etc.
            "\U0001FA70-\U0001FAFF"  # symbols ext
            "\U00002300-\U000023FF"  # misc technical
            "\U0000FE00-\U0000FE0F"  # variation selectors
            "\U0001F3FB-\U0001F3FF"  # skin tones
            "❤️💙💪🔥"  # common ones explicitly
            "]+"
        )

        # Verificar si es solo emojis (quitando espacios)
        stripped = message.strip()
        without_emoji = emoji_chars.sub("", stripped)
        without_emoji = without_emoji.replace(" ", "").replace("\ufe0f", "")

        if len(without_emoji) == 0 and len(stripped) > 0:
            return "emoji_reaction"

        # No usar pool - dejar al LLM
        return None

    def get_response(self, message_type: str) -> Optional[str]:
        """
        Obtiene una respuesta variada del pool.

        Args:
            message_type: Tipo de mensaje detectado.

        Returns:
            Respuesta o None si no hay pool.
        """
        pool = self.pools.get(message_type)
        if not pool:
            return None

        # Seleccionar evitando las últimas usadas
        response = pool.select(exclude=list(self.recent_responses))
        self.recent_responses.append(response)

        return response

    def should_use_dry_response(self, context: dict = None) -> bool:
        """
        Determina si usar respuesta seca basado en contexto.

        10% de probabilidad para confirmaciones simples.
        """
        return random.random() < 0.10

    def maybe_add_follow_up(self, response: str, message_type: str) -> str:
        """
        Ocasionalmente añade pregunta de seguimiento (como hace Stefan).

        15% de probabilidad después de saludos.
        """
        if message_type == "greeting" and random.random() < 0.15:
            follow_up = self.pools["follow_up_question"].select()
            return f"{response} {follow_up}"

        return response

    def process(self, message: str) -> Tuple[Optional[str], str]:
        """
        Procesa un mensaje y decide si usar pool o LLM.

        Returns:
            (response, message_type) - response es None si debe usar LLM
        """
        message_type = self.detect_message_type(message)

        if not message_type:
            return None, "llm"

        response = self.get_response(message_type)

        if response:
            # Ocasionalmente añadir seguimiento
            response = self.maybe_add_follow_up(response, message_type)

            # Ocasionalmente usar respuesta seca en confirmaciones
            if message_type == "confirmation" and self.should_use_dry_response():
                response = self.get_response("dry_response") or response

        return response, message_type


# Singleton
_variator: Optional[ResponseVariator] = None


def get_response_variator() -> ResponseVariator:
    """Obtiene la instancia global del variator."""
    global _variator
    if _variator is None:
        _variator = ResponseVariator()
    return _variator
