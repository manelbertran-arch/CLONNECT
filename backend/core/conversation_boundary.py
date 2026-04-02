"""
Conversation Boundary Detection for continuous message streams.

Instagram/WhatsApp DMs are ONE continuous thread per lead with no session concept.
This module detects where one conversation ends and another begins using a
hybrid multi-signal approach (industry consensus for async messaging).

Signals (weighted):
1. TIME GAP (primary): Tiered thresholds based on literature review
2. GREETING DETECTION (secondary): Multilingual patterns (11 languages)
3. FAREWELL DETECTION (secondary): Detects conversation-ending signals
4. DISCOURSE MARKERS (tertiary): Topic-shift signals ("por cierto", "by the way")
   Source: Topic Shift Detection papers (2023-24), Alibaba CS hybrid approach.

Research basis: 15+ papers reviewed (TextTiling, MSC, LoCoMo, SuperDialSeg),
12 GitHub repos, industry practices (Zendesk, Intercom, WhatsApp Business).
See DECISIONS.md 2026-04-02 for full analysis.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)

# ─── Time gap thresholds (from literature review) ────────────────────────────
GAP_ALWAYS_SAME_MINUTES = 5       # < 5 min: always same session
GAP_CHECK_GREETING_MINUTES = 30   # 5-30 min: same unless greeting detected
GAP_CHECK_SIGNALS_MINUTES = 240   # 30 min - 4h: check greeting + farewell
# > 4h: always new session

# ─── Greeting patterns (multilingual) ────────────────────────────────────────
# Matches at START of message only (greetings mid-sentence are not boundaries)
# BUG-CB-03 fix: Added French, German, Arabic, Japanese, Korean, Chinese greetings
# for universality. Primary time-based detection works for ALL languages; these
# patterns improve accuracy in the 5min-4h ambiguous zone.
_GREETING_PATTERN = re.compile(
    r"^("
    # Spanish
    r"hola|buenos?\s*d[ií]as?|buenas?\s*tardes?|buenas?\s*noches?|buenas!?"
    r"|hey|que\s*tal|oye"
    # Catalan
    r"|bon\s*dia|bona\s*tarda|bona\s*nit|ei\b|eyyy*"
    # English
    r"|hi\b|hello|good\s*morning|good\s*afternoon|good\s*evening"
    # Portuguese
    r"|ol[aá]\b|oi\b|bom\s*dia|boa\s*tarde|boa\s*noite"
    # Italian
    r"|ciao|buongiorno|buonasera|salve"
    # French
    r"|bonjour|bonsoir|salut\b|coucou"
    # German
    r"|hallo|guten\s*(?:morgen|tag|abend)|moin\b|servus"
    # Arabic (common transliterated + native)
    r"|marhaba|salam|salaam|assalamu|مرحبا|السلام"
    # Japanese (native)
    r"|こんにちは|こんばんは|おはよう"
    # Korean (native)
    r"|안녕하세요|안녕"
    # Chinese (native)
    r"|你好|您好"
    # Informal
    r"|wena|ey\b|eyy+\b"
    r")"
    r"[\s!?.,;:🙋‍♀️👋]*",
    re.IGNORECASE,
)

# ─── Farewell patterns ───────────────────────────────────────────────────────
_FAREWELL_PATTERN = re.compile(
    r"("
    # Spanish
    r"\badi[oó]s\b|\bhasta\s+(luego|mañana|pronto|la\s*vista)\b"
    r"|\bnos\s+vemos\b|\bchao\b|\bhasta\s+otro\b"
    # Catalan
    r"|\bad[eé]u\b|\bfins\s+aviat\b|\bfins\s+dem[aà]\b|\bens\s+veiem\b"
    # English
    r"|\bbye\b|\bgoodbye\b|\bsee\s+you\b|\btake\s+care\b"
    # Portuguese
    r"|\btchau\b|\bat[eé]\s+(logo|amanhã|mais)\b"
    # Italian
    r"|\barrivederci\b|\ba\s+dopo\b|\bci\s+vediamo\b"
    # French
    r"|\bau\s+revoir\b|\bà\s+bientôt\b|\bà\s+plus\b|\bsalut\b"
    # German
    r"|\btschüss\b|\bauf\s+wiedersehen\b|\bbis\s+(?:bald|dann|morgen|später)\b"
    # Arabic (transliterated)
    r"|\bma'?a\s*salama\b|\bmaa?\s*salama\b"
    r")",
    re.IGNORECASE,
)

# ─── Discourse marker patterns (topic shift signals) ────────────────────────
# Source: Topic Shift Detection papers (2023-24), Alibaba CS hybrid approach.
# These signal explicit topic changes: "by the way", "another thing", etc.
# Only used in 30min-4h zone as a THIRD signal alongside greeting/farewell.
# Must match at START of message (like greetings) to avoid mid-sentence false positives.
_DISCOURSE_MARKER_PATTERN = re.compile(
    r"^("
    # Spanish
    r"por\s+cierto|otra\s+cosa|cambiando\s+de\s+tema"
    r"|te\s+quer[ií]a\s+(?:preguntar|decir|comentar)"
    r"|oye\s+(?:una\s+cosa|que)"
    # Catalan
    r"|per\s+cert|una\s+altra\s+cosa|canviant\s+de\s+tema"
    r"|et\s+volia\s+(?:preguntar|dir|comentar)"
    r"|ei\s+(?:una\s+cosa|que)"
    # English
    r"|by\s+the\s+way|another\s+thing|changing\s+(?:topic|subject)"
    r"|i\s+wanted\s+to\s+(?:ask|tell|mention)"
    r"|on\s+another\s+note|speaking\s+of\s+which"
    # Portuguese
    r"|a\s+prop[oó]sito|outra\s+coisa|mudando\s+de\s+assunto"
    # Italian
    r"|a\s+proposito|un'?\s*altra\s+cosa|cambiando\s+argomento"
    # French
    r"|au\s+fait|autre\s+chose|en\s+passant"
    # German
    r"|[üu]brigens|noch\s+(?:etwas|was)|was\s+anderes"
    r")"
    r"[\s,.:!?]*",
    re.IGNORECASE,
)


class ConversationBoundaryDetector:
    """Detects conversation session boundaries in continuous message streams.

    Usage:
        detector = ConversationBoundaryDetector()
        sessions = detector.segment(messages)  # List[List[dict]]
        tagged = detector.tag_sessions(messages)  # adds session_id to each msg
        current = detector.get_current_session(messages)  # last session only
    """

    def _is_greeting(self, text: str) -> bool:
        """Check if message starts with a greeting pattern."""
        if not text:
            return False
        return bool(_GREETING_PATTERN.match(text.strip()))

    def _is_farewell(self, text: str) -> bool:
        """Check if message contains a farewell pattern."""
        if not text:
            return False
        return bool(_FAREWELL_PATTERN.search(text.strip()))

    def _is_discourse_marker(self, text: str) -> bool:
        """Check if message starts with a discourse marker signaling topic shift.

        Source: Topic Shift Detection papers (2023-24). Discourse markers like
        "por cierto", "otra cosa", "by the way" explicitly signal the user is
        changing topic. Only used in 30min-4h zone as a third signal.
        """
        if not text:
            return False
        return bool(_DISCOURSE_MARKER_PATTERN.match(text.strip()))

    def _parse_timestamp(self, msg: dict) -> Optional[datetime]:
        """Extract and parse timestamp from message dict."""
        ts = msg.get("created_at")
        if ts is None:
            return None
        if isinstance(ts, datetime):
            # Ensure timezone-aware
            if ts.tzinfo is None:
                return ts.replace(tzinfo=timezone.utc)
            return ts
        if isinstance(ts, (int, float)):
            # BUG-CB-01 fix: Unix timestamp (seconds since epoch)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                return None
        return None

    def _is_boundary(self, prev_msg: dict, curr_msg: dict, prev_prev_msg: Optional[dict] = None) -> bool:
        """Determine if curr_msg starts a new conversation session.

        IMPORTANT: Boundaries only trigger when a USER sends a message after
        a gap. If the bot/creator takes hours to respond, that's a slow reply,
        not a new session. This prevents false splits when the creator is busy.

        Decision logic (tiered):
        1. curr_msg is from assistant → never a boundary (slow reply ≠ new session)
        2. No timestamps → no boundary (can't determine)
        3. Gap < 5 min → SAME session (always)
        4. Gap 5-30 min → NEW only if current message is a greeting
        5. Gap 30 min - 4h → NEW if greeting OR farewell OR discourse marker
        6. Gap > 4h → NEW session (always)
        """
        # Only USER messages can start new sessions. A bot response after 6h
        # is a slow reply to the same conversation, not a new session.
        if curr_msg.get("role") == "assistant":
            return False

        prev_ts = self._parse_timestamp(prev_msg)
        curr_ts = self._parse_timestamp(curr_msg)

        if prev_ts is None or curr_ts is None:
            return False

        gap = curr_ts - prev_ts
        gap_minutes = max(0, gap.total_seconds() / 60)  # Handle clock skew

        # Tier 1: < 5 min → always same
        if gap_minutes < GAP_ALWAYS_SAME_MINUTES:
            return False

        # Tier 5: > 4h → always new
        if gap_minutes >= GAP_CHECK_SIGNALS_MINUTES:
            return True

        curr_content = curr_msg.get("content", "")
        is_greeting = self._is_greeting(curr_content)

        # Check farewell in the most recent message before the gap
        # (could be prev_msg or prev_prev_msg)
        has_farewell = self._is_farewell(prev_msg.get("content", ""))
        if prev_prev_msg and not has_farewell:
            # Check the message before prev if prev is very close to prev_prev
            pp_ts = self._parse_timestamp(prev_prev_msg)
            if pp_ts and prev_ts and (prev_ts - pp_ts).total_seconds() < 120:
                has_farewell = self._is_farewell(prev_prev_msg.get("content", ""))

        # Tier 2: 5-30 min → new only if greeting
        if gap_minutes < GAP_CHECK_GREETING_MINUTES:
            return is_greeting

        # Tier 3: 30 min - 4h → new if greeting OR farewell OR discourse marker
        # Discourse markers (Topic Shift Detection papers, 2023-24): explicit topic
        # change signals like "por cierto", "otra cosa", "by the way".
        has_discourse_marker = self._is_discourse_marker(curr_content)
        return is_greeting or has_farewell or has_discourse_marker

    def segment(self, messages: List[dict]) -> List[List[dict]]:
        """Split a message stream into conversation sessions.

        Args:
            messages: List of message dicts with 'role', 'content', 'created_at'.
                     Must be in chronological order (oldest first).

        Returns:
            List of sessions, each session is a list of message dicts.
        """
        if not messages:
            return []

        sessions = [[messages[0]]]

        # BUG-CB-02 fix: track last known timestamp so a None-timestamp message
        # in the middle of the stream doesn't break gap detection for subsequent
        # messages. Without this, a message with created_at=None acts as a "wall"
        # that absorbs all subsequent messages into the same session.
        last_known_ts = self._parse_timestamp(messages[0])

        for i in range(1, len(messages)):
            prev_msg = messages[i - 1]
            curr_msg = messages[i]
            prev_prev = messages[i - 2] if i >= 2 else None

            # If prev has no timestamp but we have a last-known ts, synthesize
            # a temp reference to keep gap detection alive across missing timestamps.
            if self._parse_timestamp(prev_msg) is None and last_known_ts is not None:
                prev_ref = {**prev_msg, "created_at": last_known_ts}
            else:
                prev_ref = prev_msg

            if self._is_boundary(prev_ref, curr_msg, prev_prev):
                sessions.append([curr_msg])
            else:
                sessions[-1].append(curr_msg)

            curr_ts = self._parse_timestamp(curr_msg)
            if curr_ts is not None:
                last_known_ts = curr_ts

        return sessions

    def tag_sessions(self, messages: List[dict]) -> List[dict]:
        """Return new message dicts with session_id added.

        Session IDs are sequential integers starting from 0.
        Messages in the same session share the same session_id.
        Does NOT mutate the original message dicts.
        """
        if not messages:
            return []

        sessions = self.segment(messages)
        result = []
        for session_idx, session in enumerate(sessions):
            for msg in session:
                result.append({**msg, "session_id": session_idx})
        return result

    def get_current_session(self, messages: List[dict]) -> List[dict]:
        """Return only the messages from the most recent session.

        Useful for context loading: only load context from the current conversation,
        not from a conversation that happened days ago.
        """
        if not messages:
            return []
        sessions = self.segment(messages)
        return sessions[-1]


# ─── Module-level convenience function ────────────────────────────────────────

def segment_sessions(messages: List[dict]) -> List[List[dict]]:
    """Convenience function: split messages into sessions.

    Args:
        messages: List of message dicts in chronological order.

    Returns:
        List of sessions (list of lists).
    """
    return ConversationBoundaryDetector().segment(messages)
