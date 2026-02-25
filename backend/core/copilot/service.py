"""
Copilot service — slim orchestrator class with utility methods.

The CopilotService class delegates heavy operations to submodules:
- lifecycle: create_pending_response, get_pending_responses
- actions: approve_response, discard_response, auto_discard_pending_for_lead
- messaging: _send_message, debounce regeneration
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CopilotService:
    """Servicio para manejar el modo Copilot"""

    _MAX_CACHE_ENTRIES = 500  # Prevent unbounded growth
    _CACHE_EVICTION_TTL = 3600  # Evict entries older than 1 hour

    def __init__(self):
        from core.copilot.models import PendingResponse

        self._pending_responses: Dict[str, PendingResponse] = {}  # In-memory cache
        self._copilot_mode_cache: Dict[str, bool] = (
            {}
        )  # FIX P1: Cache copilot mode to avoid duplicate DB queries
        self._copilot_mode_cache_ttl: Dict[str, float] = {}  # Cache timestamps
        self._CACHE_TTL = 60  # 60 second cache
        # Debounce: tracks pending regeneration tasks per lead
        self._debounce_tasks: Dict[str, asyncio.Task] = {}
        self._debounce_metadata: Dict[str, dict] = {}

    # ── Calculation helpers ─────────────────────────────────────────────

    def _calculate_purchase_intent(self, current_intent: float, message_intent: str) -> float:
        """
        Calculate updated purchase intent based on message intent.
        Score thresholds: New (0-25%), Warm (25-50%), Hot (50-75%), Customer (75%+)
        """
        intent_scores = {
            "interest_strong": 0.75,  # Hot
            "purchase": 0.85,  # Very Hot
            "interest_soft": 0.50,  # Warm
            "question_product": 0.35,  # Active
            "greeting": 0.10,  # New
            "objection": -0.10,  # Decrease
            "other": 0.05,  # Slight increase
        }

        # DEFENSIVE: Ensure message_intent is a string
        if not isinstance(message_intent, str):
            message_intent = str(message_intent) if message_intent else "other"

        intent_key = message_intent.lower().replace("Intent.", "")
        score_change = intent_scores.get(intent_key, 0.05)

        if score_change < 0:
            # Decrease
            new_intent = max(0.0, current_intent + score_change)
        else:
            # Increase - take the max between current and new
            new_intent = max(current_intent, score_change)

        return min(1.0, new_intent)

    def _calculate_lead_status(self, purchase_intent: float) -> str:
        """Calculate lead status based on purchase intent score."""
        if purchase_intent >= 0.75:
            return "hot"
        elif purchase_intent >= 0.35:
            return "active"
        elif purchase_intent >= 0.15:
            return "warm"
        return "new"

    def _calculate_edit_diff(self, original: str, edited: str) -> dict:
        """Calculate diff between original suggestion and creator's edit."""
        if not original or not edited:
            return {"length_delta": 0, "categories": []}

        categories = []
        length_delta = len(edited) - len(original)

        if length_delta < -10:
            categories.append("shortened")
        elif length_delta > 10:
            categories.append("lengthened")

        # Check if questions were removed
        orig_questions = original.count("?")
        edit_questions = edited.count("?")
        if orig_questions > edit_questions:
            categories.append("removed_question")

        # Check if emojis were removed
        emoji_pattern = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
            "\U00002600-\U000027BF\U0001FA00-\U0001FA6F]+",
            flags=re.UNICODE,
        )
        orig_emojis = len(emoji_pattern.findall(original))
        edit_emojis = len(emoji_pattern.findall(edited))
        if orig_emojis > edit_emojis:
            categories.append("removed_emoji")
        elif edit_emojis > orig_emojis:
            categories.append("added_emoji")

        # Check for complete rewrite (low similarity)
        orig_words = set(original.lower().split())
        edit_words = set(edited.lower().split())
        if orig_words and edit_words:
            overlap = len(orig_words & edit_words) / max(len(orig_words), len(edit_words))
            if overlap < 0.3:
                categories.append("complete_rewrite")
            elif overlap < 0.6:
                categories.append("major_edit")

        return {
            "length_delta": length_delta,
            "original_length": len(original),
            "edited_length": len(edited),
            "categories": categories,
        }

    def _compute_similarity(self, bot_text: str, creator_text: str) -> float:
        """Compute text similarity between bot suggestion and creator response."""
        if not bot_text or not creator_text:
            return 0.0
        return round(SequenceMatcher(None, bot_text.lower(), creator_text.lower()).ratio(), 2)

    # ── Conversation context ────────────────────────────────────────────

    def _get_conversation_context(
        self, session, lead_id, max_messages: int = 15, before_timestamp=None
    ) -> list:
        """
        Get conversation context for a lead using session-based detection.

        A "session" is a group of messages separated by >24h gaps.
        Returns the last 2 sessions, up to max_messages total.
        Messages are returned in chronological order (oldest first).
        Adds session_break markers when gaps >24h are detected.

        Args:
            before_timestamp: If set, only include messages before this datetime.
        """
        from api.models import Message

        # Fetch recent messages (up to 50 to find session boundaries)
        query = session.query(Message.role, Message.content, Message.created_at).filter(
            Message.lead_id == lead_id,
            Message.status.in_(["sent", "edited", "pending_approval"]),
        )
        if before_timestamp:
            query = query.filter(Message.created_at < before_timestamp)

        recent = query.order_by(Message.created_at.desc()).limit(50).all()

        if not recent:
            return []

        # Detect session boundaries (gap >24h between consecutive messages)
        # Messages are in desc order, so we walk backwards in time
        sessions: list[list] = [[]]
        for i, msg in enumerate(recent):
            sessions[-1].append(msg)
            if i + 1 < len(recent):
                gap = (msg.created_at - recent[i + 1].created_at).total_seconds()
                if gap > 86400:  # >24h gap = new session boundary
                    if len(sessions) >= 2:
                        break  # We have 2 sessions, stop
                    sessions.append([])

        # Flatten last 2 sessions and reverse to chronological order
        context_msgs = []
        for s in reversed(sessions):
            context_msgs.extend(reversed(s))

        # Trim to max_messages (keep most recent)
        if len(context_msgs) > max_messages:
            context_msgs = context_msgs[-max_messages:]

        # Build output with session break markers
        result = []
        for i, msg in enumerate(context_msgs):
            item = {
                "role": msg.role,
                "content": msg.content or "",
                "timestamp": msg.created_at.isoformat() if msg.created_at else "",
            }
            # Detect session breaks: gap >24h from previous message
            if i > 0 and msg.created_at and context_msgs[i - 1].created_at:
                gap = (msg.created_at - context_msgs[i - 1].created_at).total_seconds()
                if gap > 86400:
                    item["session_break"] = True
                    item["session_label"] = msg.created_at.isoformat()
            result.append(item)

        return result

    # ── DB helpers ──────────────────────────────────────────────────────

    def _get_creator_db_id(self, creator_name: str, session=None):
        """Get creator DB id from creator name."""
        if not creator_name:
            return None
        from api.models import Creator

        close_session = False
        if session is None:
            from api.database import SessionLocal

            session = SessionLocal()
            close_session = True
        try:
            creator = session.query(Creator.id).filter_by(name=creator_name).first()
            return creator[0] if creator else None
        except Exception:
            return None
        finally:
            if close_session:
                session.close()

    def has_creator_reply_after(self, lead_id, since_time, session=None) -> bool:
        """
        Check if the creator manually replied to a lead after a given time.

        Used to prevent generating copilot suggestions for messages the creator
        already answered.
        """
        from api.models import Message

        close_session = False
        if session is None:
            from api.database import SessionLocal

            session = SessionLocal()
            close_session = True

        try:
            reply = (
                session.query(Message.id)
                .filter(
                    Message.lead_id == lead_id,
                    Message.role == "assistant",
                    Message.approved_by == "creator_manual",
                    Message.created_at > since_time,
                )
                .first()
            )
            return reply is not None
        except Exception as e:
            logger.error(f"[Copilot] has_creator_reply check error: {e}")
            return False
        finally:
            if close_session:
                session.close()

    # ── Copilot mode cache ──────────────────────────────────────────────

    def is_copilot_enabled(self, creator_id: str) -> bool:
        """
        Verificar si el creador tiene modo Copilot activado.
        FIX P1: Uses cache to avoid duplicate DB queries (saves 0.3-0.5s per request).
        """
        # Check cache first
        now = time.time()
        if creator_id in self._copilot_mode_cache:
            cache_time = self._copilot_mode_cache_ttl.get(creator_id, 0)
            if now - cache_time < self._CACHE_TTL:
                return self._copilot_mode_cache[creator_id]

        # Cache miss - query DB
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                result = getattr(creator, "copilot_mode", True)
                if result is None:
                    result = True  # Default to True if NULL
            else:
                result = True

            # Evict stale entries before adding new one
            self._evict_stale_cache_entries(now)

            # Update cache
            self._copilot_mode_cache[creator_id] = result
            self._copilot_mode_cache_ttl[creator_id] = now

            return result
        except Exception as e:
            logger.error(f"Error checking copilot mode: {e}")
            return True
        finally:
            session.close()

    def invalidate_copilot_cache(self, creator_id: str):
        """Invalidate cache when copilot mode is changed"""
        self._copilot_mode_cache.pop(creator_id, None)
        self._copilot_mode_cache_ttl.pop(creator_id, None)

    def _evict_stale_cache_entries(self, now: float):
        """Remove cache entries older than _CACHE_EVICTION_TTL and enforce max size."""
        if len(self._copilot_mode_cache) <= self._MAX_CACHE_ENTRIES:
            return
        # Evict entries older than eviction TTL
        stale_keys = [
            k for k, t in self._copilot_mode_cache_ttl.items()
            if now - t > self._CACHE_EVICTION_TTL
        ]
        for k in stale_keys:
            self._copilot_mode_cache.pop(k, None)
            self._copilot_mode_cache_ttl.pop(k, None)
        # If still over limit, evict oldest entries
        if len(self._copilot_mode_cache) > self._MAX_CACHE_ENTRIES:
            sorted_keys = sorted(self._copilot_mode_cache_ttl, key=self._copilot_mode_cache_ttl.get)
            excess = len(self._copilot_mode_cache) - self._MAX_CACHE_ENTRIES
            for k in sorted_keys[:excess]:
                self._copilot_mode_cache.pop(k, None)
                self._copilot_mode_cache_ttl.pop(k, None)

    # ── Delegating methods ──────────────────────────────────────────────

    async def create_pending_response(self, **kwargs):
        from core.copilot.lifecycle import create_pending_response_impl
        return await create_pending_response_impl(self, **kwargs)

    async def get_pending_responses(self, creator_id, **kwargs):
        from core.copilot.lifecycle import get_pending_responses_impl
        return await get_pending_responses_impl(self, creator_id, **kwargs)

    async def approve_response(self, creator_id, message_id, **kwargs):
        from core.copilot.actions import approve_response_impl
        return await approve_response_impl(self, creator_id, message_id, **kwargs)

    async def discard_response(self, creator_id, message_id, **kwargs):
        from core.copilot.actions import discard_response_impl
        return await discard_response_impl(self, creator_id, message_id, **kwargs)

    def auto_discard_pending_for_lead(self, lead_id, **kwargs):
        from core.copilot.actions import auto_discard_pending_for_lead_impl
        return auto_discard_pending_for_lead_impl(self, lead_id, **kwargs)

    async def _send_message(self, creator, lead, text, **kwargs):
        from core.copilot.messaging import send_message_impl
        return await send_message_impl(self, creator, lead, text, **kwargs)

    def _schedule_debounced_regen(self, **kwargs):
        from core.copilot.messaging import schedule_debounced_regen_impl
        schedule_debounced_regen_impl(self, **kwargs)

    async def _debounced_regeneration(self, lead_key):
        from core.copilot.messaging import _debounced_regeneration_impl
        return await _debounced_regeneration_impl(self, lead_key)


# Singleton instance
_copilot_service: Optional[CopilotService] = None


def get_copilot_service() -> CopilotService:
    """Obtener instancia singleton del servicio Copilot"""
    global _copilot_service
    if _copilot_service is None:
        _copilot_service = CopilotService()
    return _copilot_service
