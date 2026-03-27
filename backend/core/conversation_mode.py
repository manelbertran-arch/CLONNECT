"""
Conversation Mode Detection — determines conversation type per message.
Universal: conversation types come from creator calibration (auto-discovered).
Zero LLM calls: uses intent mapping + structural signal matching.

Feature flag: ENABLE_CONVERSATION_MODE (default: false)
"""

import logging
import re
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Map from intent classifier outputs to structural conversation types
INTENT_TO_MODE = {
    "greeting": "greeting",
    "farewell": "farewell",
    "thanks": "thanks",
    "question_product": "product_inquiry",
    "question_price": "product_inquiry",
    "interest_strong": "product_inquiry",
    "purchase_intent": "product_inquiry",
    "interest_soft": "question",
    "objection_price": "product_inquiry",
    "objection_time": "question",
    "objection_doubt": "question",
    "media_share": "audio_message",
    "humor": "casual_humor",
    "continuation": "short_response",
    "pool_response": "short_response",
}


class ConversationMode:
    """Detects conversation mode from message + intent + creator's discovered types."""

    def __init__(self, conversation_types: Optional[Dict] = None):
        self.conversation_types = conversation_types or {}

    def detect(
        self,
        message: str,
        detected_intent: Optional[str] = None,
        history: Optional[list] = None,
    ) -> Tuple[str, Dict[str, float], bool]:
        """Detect conversation mode.

        Returns:
            (dominant_mode, probabilities, products_relevant)
        """
        if not self.conversation_types:
            return ("unknown", {}, False)

        probabilities = {}

        for type_name, type_data in self.conversation_types.items():
            score = 0.0

            # Signal 1: Intent mapping (weight 0.5)
            if detected_intent:
                mapped = INTENT_TO_MODE.get(detected_intent, "casual_chat")
                if mapped == type_name:
                    score += 0.5
                elif mapped in type_name or type_name in mapped:
                    score += 0.25

            # Signal 2: Structural matching (weight 0.3)
            structural_type = self._classify_structural(message)
            if structural_type == type_name:
                score += 0.3
            elif structural_type in type_name or type_name in structural_type:
                score += 0.15

            # Signal 3: Frequency prior (weight 0.2)
            score += type_data.get("frequency", 0) * 0.2

            probabilities[type_name] = score

        # Normalize
        total = sum(probabilities.values())
        if total > 0:
            probabilities = {k: round(v / total, 3) for k, v in probabilities.items()}

        dominant = max(probabilities, key=probabilities.get) if probabilities else "unknown"
        products_relevant = False
        dominant_prob = probabilities.get(dominant, 0)
        if dominant_prob > 0.3:
            products_relevant = self.conversation_types.get(dominant, {}).get("products_relevant", False)

        return (dominant, probabilities, products_relevant)

    def _classify_structural(self, message: str) -> str:
        """Structural classification — same logic as discovery for consistency."""
        if not message:
            return "empty"
        c = message.strip()
        cl = c.lower()

        if c.startswith("[audio") or c.startswith("[Audio") or c.startswith("[🎤"):
            return "audio_message"
        if re.match(r'^[\U0001f000-\U0001ffff\u2600-\u27bf\u2764\ufe0f\s]+$', c):
            return "emoji_reaction"
        if re.search(r'[€$£¥]|\d+\s*(eur|usd|gbp)', cl):
            return "product_inquiry"
        if re.match(r'^(hol[ae]|hey|hi|bon\s*dia|buen[ao]s|ey|ei|hello)', cl) and len(c) <= 20:
            return "greeting"
        if re.search(r'graci|merci|thanks|gràci', cl):
            return "thanks"
        if re.search(r'[jh]a[jh]a|😂|🤣', cl) and len(c) < 40:
            return "casual_humor"
        if len(c) <= 12 and "?" not in c:
            return "short_response"
        if "?" in c and len(c) > 15:
            return "question"
        return "casual_chat"

    def build_context_note(
        self,
        dominant: str,
        probability: float,
        products_relevant: bool,
        threshold: float = 0.35,
    ) -> str:
        """Build factual context note for Recalling block.

        Only injects if mode is clear (above threshold).
        NEVER injects behavior instructions — only facts.
        Doc D handles all tone/style.
        """
        if probability < threshold:
            return ""

        if products_relevant:
            return "El lead muestra interés comercial."

        # For casual/personal/greeting/farewell — no injection needed.
        # Doc D + few-shot examples handle all non-commercial modes.
        return ""
