"""
Relationship Scorer v2 — multi-signal, gradated, universal, USER-only.

Replaces RelationshipTypeDetector's keyword matching on ALL messages
(which false-positive'd on Iris's apelativos in assistant messages)
with a multi-signal scoring approach using only USER messages and
structural data.

Returns a continuous score (0.0-1.0) instead of a binary is_friend.
The score drives gradated product suppression:
  < 0.3 → TRANSACTIONAL: products visible, sales active
  0.3-0.6 → CASUAL: products visible, no aggressive push
  0.6-0.8 → CLOSE: products only if user asks
  > 0.8 → PERSONAL: zero products in prompt

Universal: markers are multilingual, signals are structural.
Zero LLM calls. Works for any creator.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Multilingual markers (extend per language as needed) ───────────
PERSONAL_MARKERS = {
    "friend", "amiga", "amigo", "amic", "madre", "mother", "mare",
    "padre", "father", "pare", "hermano", "hermana", "brother", "sister",
    "germà", "germana", "familia", "family", "família", "mamma", "papa",
    "novia", "novio", "pareja", "partner", "marido", "mujer",
    "husband", "wife", "hijo", "hija", "figlia", "figlio",
    "abuelo", "abuela", "nonna", "nonno",
}

TRANSACTIONAL_MARKERS = {
    "class", "clase", "cours", "pack", "reserv", "book",
    "pago", "payment", "precio", "price", "prezzo", "prix",
    "compra", "purchase", "acheter", "comprar", "inscri",
    "tarifa", "descuento", "factura", "horario", "schedule",
}


@dataclass
class RelationshipScore:
    """Result of multi-signal relationship scoring."""
    score: float  # 0.0-1.0
    category: str  # TRANSACTIONAL / CASUAL / CLOSE / PERSONAL
    signals: Dict[str, float] = field(default_factory=dict)
    suppress_products: bool = False  # score > 0.8
    soft_suppress: bool = False  # 0.6 < score <= 0.8

    @property
    def is_friend(self) -> bool:
        """Legacy compat: True if score >= 0.6 (CLOSE or PERSONAL)."""
        return self.score >= 0.6


def _categorize(score: float) -> str:
    if score >= 0.8:
        return "PERSONAL"
    if score >= 0.6:
        return "CLOSE"
    if score >= 0.3:
        return "CASUAL"
    return "TRANSACTIONAL"


class RelationshipScorer:
    """Multi-signal relationship scorer.

    Scores a lead's relationship closeness using structural signals
    (frequency, duration, message format) and memory facts — never
    assistant messages.

    Usage:
        scorer = RelationshipScorer()
        result = scorer.score_sync(
            user_messages=user_msgs,
            lead_facts=facts,
            days_span=120,
            lead_status="amigo",
        )
        if result.suppress_products:
            products = []
    """

    def score_sync(
        self,
        user_messages: Optional[List[Dict]] = None,
        lead_facts: Optional[List[Dict]] = None,
        days_span: int = 0,
        lead_status: str = "",
    ) -> RelationshipScore:
        """Score relationship from available data (synchronous, no DB calls).

        Called from context.py which already has follower data loaded.
        All heavy DB queries are done in the parallel IO phase — this
        function only processes already-loaded data.

        Args:
            user_messages: USER-only messages [{content, ...}]
            lead_facts: Memory facts [{fact_type, fact_text}]
            days_span: Days between first and last message
            lead_status: Lead status from DB ("amigo", "caliente", etc.)
        """
        signals = {}
        user_msgs = user_messages or []
        facts = lead_facts or []

        # Signal 1: Memory facts — personal vs transactional (max 0.35)
        signals["memory"] = self._score_memory_facts(facts)

        # Signal 2: Lead status from DB (max 0.25)
        signals["status"] = self._score_db_status(lead_status)

        # Signal 3: Message frequency — user messages only (max 0.15)
        signals["frequency"] = self._score_frequency(len(user_msgs))

        # Signal 4: Relationship duration (max 0.15)
        signals["duration"] = self._score_duration(days_span)

        # Signal 5: Message format — audios, long messages (max 0.10)
        signals["format"] = self._score_format(user_msgs)

        total = sum(signals.values())
        total = max(0.0, min(1.0, total))
        category = _categorize(total)

        return RelationshipScore(
            score=round(total, 3),
            category=category,
            signals=signals,
            suppress_products=(total > 0.8),
            soft_suppress=(0.6 < total <= 0.8),
        )

    def _score_memory_facts(self, facts: List[Dict]) -> float:
        """Score from memory engine facts. Max 0.35."""
        if not facts:
            return 0.0

        personal_count = 0
        transactional_count = 0

        for f in facts:
            text = (f.get("fact_text", "") or "").lower()
            ftype = (f.get("fact_type", "") or "").lower()

            # Check fact text for personal markers
            if any(m in text for m in PERSONAL_MARKERS):
                personal_count += 1
            # Check fact type
            if ftype in ("personal_info", "personal", "datos_personales"):
                personal_count += 1

            # Transactional markers
            if any(m in text for m in TRANSACTIONAL_MARKERS):
                transactional_count += 1
            if ftype in ("producto_mencionado", "commitment", "objection"):
                transactional_count += 1

        if personal_count == 0:
            return 0.0

        # Strong personal signal
        if personal_count >= 3 and transactional_count == 0:
            return 0.35
        if personal_count >= 2:
            return 0.25
        if personal_count >= 1:
            return 0.15
        return 0.0

    def _score_db_status(self, lead_status: str) -> float:
        """Score from DB lead.status field. Max 0.30.

        The lead.status field is manually curated or set by the scoring
        system — it's the most reliable signal we have.
        """
        status = (lead_status or "").lower()
        if status == "amigo":
            return 0.30  # Strongest single signal — curated by creator
        if status == "colaborador":
            return 0.20
        if status in ("caliente", "cliente"):
            return 0.0  # Commercial, not personal
        return 0.0  # nuevo, frío, etc.

    def _score_frequency(self, user_msg_count: int) -> float:
        """Score from user message count. Max 0.15."""
        if user_msg_count > 50:
            return 0.15
        if user_msg_count > 20:
            return 0.10
        if user_msg_count > 5:
            return 0.05
        return 0.0

    def _score_duration(self, days_span: int) -> float:
        """Score from relationship duration. Max 0.15."""
        if days_span > 90:
            return 0.15
        if days_span > 30:
            return 0.05
        return 0.0

    def _score_format(self, user_msgs: List[Dict]) -> float:
        """Score from message format — audios and long messages. Max 0.10."""
        if not user_msgs:
            return 0.0

        total = len(user_msgs)
        audio_count = sum(
            1 for m in user_msgs
            if any(tag in (m.get("content", "") or "")
                   for tag in ["[audio]", "[🎤", "Audio]", "voice"])
        )
        long_count = sum(
            1 for m in user_msgs if len(m.get("content", "") or "") > 100
        )

        score = 0.0
        if total > 0:
            if audio_count / total > 0.10:
                score += 0.05
            if long_count / total > 0.20:
                score += 0.05
        return score


# ── Singleton ──────────────────────────────────────────────────────

_scorer_instance: Optional[RelationshipScorer] = None


def get_relationship_scorer() -> RelationshipScorer:
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = RelationshipScorer()
    return _scorer_instance
