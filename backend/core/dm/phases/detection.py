"""Phase 1: Detection — five input guards run before LLM generation.

Guards (in order):
  1. Empty message gate — return early, no downstream calls
  2. Media placeholder detection — Instagram/WA sends placeholder text
  3. Sensitive content detection — crisis, phishing, harm (fail-closed)
  4. Frustration & context signals — enriches cognitive_metadata
  5. Pool matching — fast-path response for short conversational messages

Note: "edge cases" is NOT a separate system here. This file is the input
guard layer; adversarial inputs (prompt injection, jailbreak) are flagged
via cognitive_metadata and handled by the LLM + postprocessing guardrails.
"""

import logging
import re
from typing import Dict

from core.agent_config import AGENT_THRESHOLDS
from core.context_detector import detect_all as detect_context
from core.dm.models import DMResponse, DetectionResult
from core.dm.text_utils import _message_mentions_product
from core.feature_flags import flags
from core.security.alerting import (
    EVENT_PROMPT_INJECTION,
    EVENT_SENSITIVE_CONTENT,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    dispatch_fire_and_forget as _dispatch_security_alert,
)
from core.sensitive_detector import detect_sensitive_content, get_crisis_resources

logger = logging.getLogger(__name__)

# Dialect → language code for crisis resources
_DIALECT_TO_LANG = {
    "catalan": "ca", "catala": "ca", "català": "ca",
    "english": "en", "anglès": "en", "ingles": "en",
    "castellano": "es", "español": "es", "spanish": "es",
    "neutral": "es",
}

# Prompt injection patterns — Perez & Ribeiro (2022), "Ignore Previous Prompt".
# These flag the message for observability/DPO signal collection.
# They do NOT block: the LLM + postprocessing guardrails handle the actual response.
# Patterns are bounded (no unbounded .* backtracking — ReDoS-safe).
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignor[ae].{0,20}(previous|prior|your|all|mis|tus?|sus?).{0,20}(instructions?|prompt|rules?|instrucciones?)", re.IGNORECASE),
    re.compile(r"olvida.{0,20}(tus?|sus?|las?|mis?).{0,20}(instrucciones?|reglas?|prompt)", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(DAN|GPT|an?\s+AI\s+without|a\s+model\s+without)", re.IGNORECASE),
    re.compile(r"\b(you are now|ahora eres|now you are|eres ahora)\b.{0,40}(DAN|GPT|unrestricted|sin restricciones)", re.IGNORECASE),
    re.compile(r"\b(jailbreak|bypass your|forget everything( you)?|from now on you are|pretend you have no)\b", re.IGNORECASE),
    re.compile(r"\b(mu[eé]strame|show me|reveal|display|tell me).{0,20}(system prompt|tu prompt|tus instrucciones|your instructions)", re.IGNORECASE),
]

# Platform placeholders sent instead of actual media content
MEDIA_PLACEHOLDERS = {
    "sent an attachment",
    "sent a photo",
    "sent a video",
    "shared a reel",
    "shared a story",
    "sent a voice message",
    "[image]", "[video]", "[sticker]",
    "[🏷️ sticker]",
    "[audio]",
    "[🎤 audio]",
    "[🎤 audio message]",
    "[📷 photo]",
    "[📷 foto]",
    "[📸 photo]",
    "[📸 foto]",
    "audio message",
    "mensaje de voz",
    "envió un archivo adjunto",
    "envió una foto",
    "envió un video",
    "compartió un reel",
    "compartió una historia",
}


async def phase_detection(
    agent, message: str, sender_id: str, metadata: Dict, cognitive_metadata: Dict
) -> DetectionResult:
    """Phase 1: Five input guards — empty gate, media placeholder, sensitive,
    frustration/context signals, pool matching.
    Returns a DetectionResult; if pool_response is set the pipeline short-circuits.
    """
    result = DetectionResult()

    # GUARD 0: Empty / whitespace-only messages — skip all guards, let LLM handle
    if not message or not message.strip():
        metadata["is_empty_message"] = True
        logger.info("Empty message received from sender %s — skipping all guards", sender_id)
        return result

    # GUARD 0b: Input length truncation (OWASP LLM10 — token flooding / context overflow).
    # Instagram native limit is ~2200 chars; real leads never hit 3000.
    # Synthetic / misconfigured webhook payloads can be arbitrarily long.
    if len(message) > 3000:
        logger.warning("Oversized message from sender %s (%d chars) — truncating to 3000", sender_id, len(message))
        message = message[:3000]

    # QW3 helper: resolve creator_id once for all security-alert dispatches.
    # Agents always carry a slug; falling back to "unknown" would poison the
    # security_events table, so log loudly if that path ever fires.
    _alert_creator_id = getattr(agent, "creator_id", None)
    if not _alert_creator_id:
        logger.warning("phase_detection: agent.creator_id missing — security alerts will be tagged 'unknown'")
        _alert_creator_id = "unknown"

    # GUARD 1 (observability): Prompt injection / jailbreak attempt detection.
    # Per Perez & Ribeiro (2022). Flags only — no blocking. LLM + guardrails handle response.
    if flags.prompt_injection_detection:
        for _pat in _PROMPT_INJECTION_PATTERNS:
            if _pat.search(message):
                cognitive_metadata["prompt_injection_attempt"] = True
                logger.warning(
                    "Prompt injection pattern detected from sender %s: pattern=%s",
                    sender_id, _pat.pattern[:60],
                )
                # QW3: fire-and-forget alert. Fail-silent — dispatcher swallows errors.
                try:
                    _dispatch_security_alert(
                        creator_id=_alert_creator_id,
                        sender_id=sender_id,
                        event_type=EVENT_PROMPT_INJECTION,
                        content=message,
                        severity=SEVERITY_WARNING,
                        metadata={"pattern_prefix": _pat.pattern[:60]},
                    )
                except Exception:
                    logger.debug("security alerting dispatch failed", exc_info=True)
                break  # one match is enough to flag

    # GUARD 2: Media placeholder detection
    # Instagram/WhatsApp send placeholder text like "Sent an attachment" instead of
    # actual content. Flag it so the LLM reacts naturally instead of asking "what?".
    msg_stripped = message.strip().lower().rstrip(".")
    if flags.media_placeholder_detection and msg_stripped in MEDIA_PLACEHOLDERS:
        metadata["is_media_placeholder"] = True
        cognitive_metadata["intent_override"] = "media_share"
        logger.info("Media placeholder detected: %s", message.strip())

    # GUARD 3: SENSITIVE CONTENT DETECTION (Security)
    if flags.sensitive_detection:
        try:
            sensitive_result = detect_sensitive_content(message)
            if sensitive_result and sensitive_result.confidence >= AGENT_THRESHOLDS.sensitive_confidence:
                logger.warning(f"Sensitive content detected: {sensitive_result.type.value}")
                cognitive_metadata["sensitive_detected"] = True
                cognitive_metadata["sensitive_category"] = sensitive_result.type.value
                # QW3: fire-and-forget alert. CRITICAL if at/above escalation threshold.
                _severity = (
                    SEVERITY_CRITICAL
                    if sensitive_result.confidence >= AGENT_THRESHOLDS.sensitive_escalation
                    else SEVERITY_WARNING
                )
                try:
                    _dispatch_security_alert(
                        creator_id=_alert_creator_id,
                        sender_id=sender_id,
                        event_type=EVENT_SENSITIVE_CONTENT,
                        content=message,
                        severity=_severity,
                        metadata={
                            "sensitive_category": sensitive_result.type.value,
                            "confidence": float(sensitive_result.confidence),
                        },
                    )
                except Exception:
                    logger.debug("security alerting dispatch failed", exc_info=True)
                if sensitive_result.confidence >= AGENT_THRESHOLDS.sensitive_escalation:
                    # Resolve crisis language from creator's dialect (BUG-S2 fix).
                    # BUG-S3 (2026-04-17): Catalan creators default to the Barcelona
                    # regional hotline first (900 925 555). An explicit location
                    # value from agent metadata wins over this default when present.
                    # `agent.personality` may be explicitly None in some loaders,
                    # so collapse both "missing attribute" and "None attribute" to {}.
                    _personality = getattr(agent, "personality", None) or {}
                    _dialect = _personality.get("dialect", "neutral") or "neutral"
                    _crisis_lang = _DIALECT_TO_LANG.get(_dialect.lower(), "es")
                    _location_hint = (
                        _personality.get("location")
                        or ("Barcelona" if _crisis_lang == "ca" else None)
                    )
                    crisis_response = get_crisis_resources(
                        language=_crisis_lang, location_hint=_location_hint,
                    )
                    result.pool_response = DMResponse(
                        content=crisis_response,
                        intent="sensitive_content",
                        lead_stage="unknown",
                        confidence=sensitive_result.confidence,
                        tokens_used=0,
                        metadata={"sensitive_category": sensitive_result.type.value},
                    )
                    return result
        except Exception as e:
            # FAIL-CLOSED: if we can't verify it's NOT a crisis, escalate to human
            logger.error(f"CRITICAL: Sensitive detection failed, escalating by default: {e}")
            creator_name = getattr(agent, "creator_id", "el creador")
            result.pool_response = DMResponse(
                content=(
                    f"Ahora mismo no puedo responderte bien. "
                    f"Le paso tu mensaje a {creator_name} directamente 🙏"
                ),
                intent="sensitive_detection_failure",
                lead_stage="unknown",
                confidence=1.0,
                tokens_used=0,
                metadata={"sensitive_failsafe": True, "error": str(e)},
            )
            return result

    # GUARD 4a: Detect frustration level
    if flags.frustration_detection and hasattr(agent, "frustration_detector"):
        try:
            history = metadata.get("history", [])
            prev_messages = [
                m.get("content", "") for m in history if m.get("role") == "user"
            ]
            result.frustration_signals, result.frustration_level = (
                agent.frustration_detector.analyze_message(message, sender_id, prev_messages)
            )
            if result.frustration_level > 0.3:
                logger.info(f"Frustration detected: {result.frustration_level:.2f}")
        except Exception as e:
            logger.debug(f"Frustration detection failed: {e}")

    # GUARD 4b: Detect context signals (sarcasm, B2B, etc.)
    # Context signals ARE consumed in core/dm/phases/context.py:712
    if flags.context_detection:
        try:
            history = metadata.get("history", [])
            result.context_signals = detect_context(message, history)
            # BUG-UC-02 fix: Always write context_signals so user_name is
            # available in post_response even when no alerts fired.
            if result.context_signals:
                cognitive_metadata["context_signals"] = result.context_signals.to_dict()
        except Exception as e:
            logger.debug(f"Context detection failed: {e}")

    # GUARD 5: Try pool response for simple messages (fast path)
    # NOTE: product mentions are intentionally NOT used to block pool responses.
    # All pool categories (cancel, confirmation, thanks, etc.) are social/conversational —
    # none are purchase-related. Class names like "Barre" or "Zumba" are also product
    # names in the DB, so the product guard incorrectly blocked class-cancel pool responses.
    if flags.pool_matching and hasattr(agent, "response_variator"):
        if len(message.strip()) <= 80:
            from services.length_controller import classify_lead_context
            pool_context = classify_lead_context(message)
            conv_id = metadata.get("conversation_id", sender_id)

            pool_result = agent.response_variator.try_pool_response(
                message,
                conv_id=conv_id,
                turn_index=metadata.get("turn_index", 0),
                context=pool_context,
                creator_id=agent.creator_id,
            )
            if pool_result.matched and pool_result.confidence >= AGENT_THRESHOLDS.pool_confidence:
                import random as _rng
                if _rng.random() < 0.30:
                    multi_bubbles = agent.response_variator.try_multi_bubble(
                        message, creator_id=agent.creator_id, conv_id=conv_id,
                    )
                    if multi_bubbles:
                        logger.debug(f"Multi-bubble matched: {len(multi_bubbles)} bubbles")
                        result.pool_response = DMResponse(
                            content=multi_bubbles[0],
                            intent="pool_response",
                            lead_stage="unknown",
                            confidence=0.85,
                            tokens_used=0,
                            metadata={
                                "pool_category": "multi_bubble",
                                "used_pool": True,
                                "message_parts": [
                                    {"text": b, "delay": 0.8} for b in multi_bubbles
                                ],
                            },
                        )
                        return result

                logger.debug(f"Pool response matched: {pool_result.category}")
                result.pool_response = DMResponse(
                    content=pool_result.response,
                    intent="pool_response",
                    lead_stage="unknown",
                    confidence=pool_result.confidence,
                    tokens_used=0,
                    metadata={"pool_category": pool_result.category, "used_pool": True},
                )
                return result

    return result
