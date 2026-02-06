"""
Response Variator V2 - Expanded pools based on real Stefan data.

Categories:
- greeting: Hola, Hey, Buenas
- confirmation: Dale, Ok, Perfecto
- thanks: Gracias, A ti
- laugh: Jaja, Jajaja
- emoji: 😊, 💙, 👍
- celebration: Genial, Qué bien
- farewell: Un abrazo, Hablamos
- dry: Ok, Dale, Sí
- empathy: Entiendo, Ánimo
"""

import json
import os
import random
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class PoolMatch:
    """Result of pool matching."""

    matched: bool
    response: Optional[str] = None
    category: Optional[str] = None
    confidence: float = 0.0


class ResponseVariatorV2:
    """Response variator with expanded pools."""

    def __init__(self, pools_path: str = "data/pools/stefan_real_pools.json"):
        self.pools = self._load_pools(pools_path)
        self._setup_fallback_pools()

    def _load_pools(self, path: str) -> dict:
        """Load pools from file."""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            return {}

    def _setup_fallback_pools(self):
        """Setup fallback pools if no data exists."""
        fallback = {
            "greeting": [
                "Hola! 😊",
                "Hey!",
                "Buenas!",
                "Ey!",
                "Qué tal!",
                "Hola hermano!",
                "Buenas buenas!",
                "Hey 😊",
                "Hola! 😀",
            ],
            "confirmation": [
                "Dale!",
                "Ok!",
                "Perfecto!",
                "Genial!",
                "Vale!",
                "Sí!",
                "Claro!",
                "Bien!",
                "👍",
                "Dale dale!",
            ],
            "thanks": [
                "Gracias!",
                "A ti!",
                "Gracias hermano!",
                "Nada!",
                "De nada!",
                "Gracias! 😊",
                "💙",
                "Gracias! 💪",
            ],
            "laugh": ["Jaja", "Jajaja", "Jajajaja", "😂", "🤣", "Jeje"],
            "emoji": ["😊", "💙", "👍", "🙌", "❤️", "💪", "🔥", "✨", "😀"],
            "celebration": [
                "Genial!",
                "Qué bien!",
                "Buenísimo!",
                "Increíble!",
                "Excelente!",
                "Genial! 🙌",
                "Qué bueno!",
                "Me alegro!",
            ],
            "farewell": [
                "Un abrazo!",
                "Abrazo!",
                "Hablamos!",
                "Cuídate!",
                "Hasta pronto!",
                "Un abrazo grande!",
                "💙",
                "Abrazo! 💙",
            ],
            "dry": ["Ok", "Dale", "Sí", "Va", "Bien", "Ya", "Eso"],
            "empathy": [
                "Entiendo",
                "Te entiendo",
                "Es así",
                "Normal",
                "Pasa",
                "A veces es así",
                "Ánimo!",
                "Fuerza!",
            ],
            "affection": [
                "Yo a ti! 💙",
                "Igualmente! ❤️",
                "Y yo a ti!",
                "Gracias! Te quiero! 💙",
                "Yo más! 😊",
                "Lo mismo! ❤️",
                "Un abrazo grande! 💙",
                "Sos un/a crack! 💙",
            ],
            "praise": [
                "Gracias! 😊",
                "Muchas gracias! 💙",
                "Qué lindo! 😊",
                "Me alegro!",
                "Qué bueno!",
                "Gracias hermano!",
                "💙",
            ],
            # PROPUESTAS DE QUEDAR - Stefan siempre rechaza amablemente
            "meeting_request": [
                "Imposible bro, me explota la agenda jaja",
                "Uf imposible, tengo la agenda llena 😅",
                "Me es imposible ahora mismo, hermano",
                "Ahora no puedo, bro. Quizás más adelante! 😊",
                "Difícil ahora, tengo todo el mes pillado jaja",
            ],
        }

        # Merge with loaded pools
        for cat, items in fallback.items():
            if cat not in self.pools or not self.pools[cat]:
                self.pools[cat] = items
            else:
                existing = set(self.pools[cat])
                for item in items:
                    if item not in existing:
                        self.pools[cat].append(item)

    def _detect_category(self, message: str) -> Tuple[Optional[str], float]:
        """
        Detect message category.

        Returns:
            (category, confidence)
        """
        msg = message.lower().strip()
        msg_clean = msg.rstrip("!").rstrip(".").rstrip("?")

        # MEETING REQUESTS - HIGHEST PRIORITY (Stefan always declines)
        meeting_triggers = [
            "quedar",
            "quedamos",
            "vernos",
            "encontrarnos",
            "veámonos",
            "veamonos",
            "tomarnos algo",
            "tomar algo",
            "un café",
            "un cafe",
            "unas birras",
            "unas cervezas",
            "nos vemos mañana",
            "nos juntamos",
        ]
        if any(m in msg for m in meeting_triggers):
            return ("meeting_request", 0.98)

        # Greetings (high confidence)
        greetings = ["hola", "hey", "buenas", "ey", "hi", "hello"]
        if msg_clean in greetings or any(msg.startswith(g) for g in greetings):
            if len(msg) < 15:
                return ("greeting", 0.9)

        # Confirmations (high confidence)
        confirmations = [
            "ok",
            "dale",
            "vale",
            "perfecto",
            "genial",
            "bien",
            "sí",
            "si",
            "claro",
            "bueno",
        ]
        if msg_clean in confirmations:
            return ("confirmation", 0.95)

        # Emoji only
        if all(ord(c) > 127000 or c.isspace() for c in msg):
            return ("emoji", 0.9)

        # Laugh
        if msg.startswith("jaj") or msg.startswith("hah") or msg_clean == "jeje":
            return ("laugh", 0.95)

        # Thanks
        if "gracias" in msg or "thanks" in msg:
            if len(msg) < 30:
                return ("thanks", 0.85)

        # Farewell
        farewells = ["abrazo", "chao", "bye", "cuídate", "hablamos", "hasta"]
        if any(f in msg for f in farewells):
            return ("farewell", 0.8)

        # Celebration (from lead)
        celebrations = ["genial", "increíble", "qué bien", "buenísimo", "lo logré"]
        if any(c in msg for c in celebrations):
            return ("celebration", 0.7)

        # Empathy (lead sharing difficulty)
        empathy_triggers = ["difícil", "cuesta", "triste", "mal", "complicado"]
        if any(e in msg for e in empathy_triggers):
            return ("empathy", 0.6)

        # Affection (te quiero, te amo)
        affection_triggers = ["te quiero", "te amo", "eres el mejor", "eres la mejor", "te adoro"]
        if any(a in msg for a in affection_triggers):
            return ("affection", 0.9)

        # Praise (positive feedback about Stefan)
        praise_triggers = ["muy lindo", "estuvo genial", "increíble", "eres hermoso", "sos hermoso", "que crack"]
        if any(p in msg for p in praise_triggers):
            if len(msg) > 30:  # Long praise messages
                return ("praise", 0.85)

        return (None, 0.0)

    def try_pool_response(self, lead_message: str, min_confidence: float = 0.7) -> PoolMatch:
        """
        Try to generate response from pool.

        Args:
            lead_message: Lead's message
            min_confidence: Minimum confidence to use pool

        Returns:
            PoolMatch with result
        """
        category, confidence = self._detect_category(lead_message)

        if category is None or confidence < min_confidence:
            return PoolMatch(matched=False)

        pool = self.pools.get(category, [])
        if not pool:
            return PoolMatch(matched=False)

        response = random.choice(pool)

        return PoolMatch(matched=True, response=response, category=category, confidence=confidence)

    def get_pool_for_context(self, context: str) -> list:
        """Get pool of responses for a specific context."""
        return self.pools.get(context, [])


# Singleton
_variator_v2: Optional[ResponseVariatorV2] = None


def get_response_variator_v2() -> ResponseVariatorV2:
    """Get variator V2 instance."""
    global _variator_v2
    if _variator_v2 is None:
        _variator_v2 = ResponseVariatorV2()
    return _variator_v2
