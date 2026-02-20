"""Audio Transcription Post-Processor.

Takes raw Whisper transcription output and restructures it into clean,
readable text using LLM post-processing. Preserves all factual content
while removing repetitions, fillers, and circularities.

Feature flag: ENABLE_AUDIO_INTELLIGENCE (default OFF).
When OFF, transcription still happens (Whisper) but post-processing is skipped.

Output fields stored in msg_metadata:
  - transcript_raw: Original Whisper output (always preserved)
  - transcript_full: Complete restructured text (for AI context, RAG, DNA)
  - transcript_summary: Short readable version (for chat UI)
"""

import asyncio
import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration
MIN_WORDS_FOR_PROCESSING = 30
LLM_TIMEOUT_SECONDS = 25
ENABLE_AUDIO_INTELLIGENCE = os.getenv("ENABLE_AUDIO_INTELLIGENCE", "false").lower() == "true"

AUDIO_INTELLIGENCE_PROMPT = """You are an audio transcription post-processor. You receive raw speech-to-text output from Whisper and must restructure it into clean, readable text.

RULES:
1. PRESERVE all factual content: names, numbers, dates, prices, locations, decisions
2. REMOVE: filler words (um, uh, eh, este, o sea, bueno, pues), false starts, repetitions, circular rambling
3. RESTRUCTURE: reorder ideas logically, merge fragmented sentences, add paragraph breaks for topic changes
4. NEVER add information not present in the original
5. NEVER change the speaker's meaning or intent
6. Keep the speaker's natural tone and vocabulary (formal/informal)
7. Output in the SAME LANGUAGE as the input
8. CRITICAL: The transcript_summary MUST be written in FIRST PERSON — as if the speaker wrote it. NEVER use third person ("La persona dice...", "El usuario menciona..."). Example: "Me voy a una maratón de biodanza" NOT "La persona va a una maratón de biodanza"

{style_context}

Respond with ONLY a JSON object (no markdown fences, no explanation):
{{
  "transcript_full": "Complete restructured text with all facts preserved. Use paragraph breaks for topic changes. First person.",
  "transcript_summary": "2-3 sentence summary capturing the key points. Max 120 words. MUST be first person."
}}

RAW TRANSCRIPTION:
{raw_text}"""


def _make_fallback(raw_text: str) -> dict:
    """Return fallback result where all 3 fields equal the raw text."""
    return {
        "transcript_raw": raw_text,
        "transcript_full": raw_text,
        "transcript_summary": raw_text,
    }


def _extract_entities(text: str) -> set:
    """Extract significant entities from text: capitalized words and numbers."""
    # Capitalized words (2+ chars, not at sentence start)
    words = re.findall(r'(?<=[.!?\s])\s*([A-Z\u00C0-\u00DC][a-z\u00E0-\u00FC]+)', text)
    # Also get standalone capitalized words
    words += re.findall(r'\b([A-Z\u00C0-\u00DC][a-z\u00E0-\u00FC]{2,})\b', text)
    # Numbers (integers and decimals)
    numbers = re.findall(r'\b\d+(?:[.,]\d+)?\b', text)
    return {w.lower() for w in words} | set(numbers)


def _validate_transcription(raw: str, full: str, summary: str) -> bool:
    """Validate that the full transcription preserves entities from raw text.

    Tolerance: allows up to 2 missing entities.
    """
    raw_entities = _extract_entities(raw)
    if not raw_entities:
        return True  # No entities to check

    full_entities = _extract_entities(full)
    missing = raw_entities - full_entities
    if len(missing) > 2:
        logger.warning(
            "Entity check failed: %d entities missing from transcript_full: %s",
            len(missing), list(missing)[:5],
        )
        return False
    return True


def _validate_lengths(raw: str, full: str, summary: str) -> bool:
    """Validate length constraints on processed transcriptions."""
    raw_words = len(raw.split())
    full_words = len(full.split())
    summary_words = len(summary.split())

    # full must not be longer than raw
    if full_words > raw_words * 1.1:  # 10% tolerance
        logger.warning(
            "Length check failed: transcript_full (%d words) > raw (%d words)",
            full_words, raw_words,
        )
        return False

    # summary must be <= 120 words
    if summary_words > 150:  # Some tolerance over the 120 target
        logger.warning("Length check failed: summary too long (%d words)", summary_words)
        return False

    # Both must be at least 20% of raw
    min_words = max(5, int(raw_words * 0.2))
    if full_words < min_words:
        logger.warning(
            "Length check failed: transcript_full too short (%d words, min %d)",
            full_words, min_words,
        )
        return False
    if summary_words < min(min_words, 10):
        logger.warning(
            "Length check failed: summary too short (%d words)", summary_words,
        )
        return False

    return True


def _parse_llm_response(response: str) -> Optional[dict]:
    """Parse LLM JSON response, stripping markdown fences if present."""
    text = response.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        # Remove closing fence
        text = re.sub(r'\n?```\s*$', '', text)

    try:
        data = json.loads(text)
        full = data.get("transcript_full", "").strip()
        summary = data.get("transcript_summary", "").strip()
        if full and summary:
            return {"transcript_full": full, "transcript_summary": summary}
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning("Failed to parse LLM response as JSON: %s", e)

    return None


def _get_style_context(creator_id: str) -> str:
    """Load creator style context, truncated to 500 chars."""
    if not creator_id:
        return ""
    try:
        from services.creator_style_loader import get_creator_style_prompt

        style = get_creator_style_prompt(creator_id)
        if style:
            truncated = style[:500]
            return f"CREATOR STYLE CONTEXT (match this tone):\n{truncated}"
    except Exception as e:
        logger.debug("Could not load creator style for audio processing: %s", e)
    return ""


async def process_audio_transcription(raw_text: str, creator_id: str = "") -> dict:
    """Post-process a Whisper transcription into structured output.

    Returns:
        dict with keys: transcript_raw, transcript_full, transcript_summary
        Fallback: all 3 fields = raw_text if processing fails or is disabled.
    """
    if not raw_text or not raw_text.strip():
        return _make_fallback(raw_text or "")

    raw_text = raw_text.strip()

    # Skip processing if disabled or text is too short
    word_count = len(raw_text.split())
    if not ENABLE_AUDIO_INTELLIGENCE or word_count < MIN_WORDS_FOR_PROCESSING:
        return _make_fallback(raw_text)

    # Build prompt with creator style context
    style_context = _get_style_context(creator_id)
    prompt = AUDIO_INTELLIGENCE_PROMPT.format(
        style_context=style_context,
        raw_text=raw_text,
    )

    # Call LLM with timeout
    try:
        from core.providers.gemini_provider import generate_simple

        max_tokens = min(word_count * 3, 4096)
        response = await asyncio.wait_for(
            generate_simple(prompt, max_tokens=max_tokens, temperature=0.2),
            timeout=LLM_TIMEOUT_SECONDS,
        )

        if not response:
            logger.warning("Audio post-processing: LLM returned empty response")
            return _make_fallback(raw_text)

        # Parse JSON response
        parsed = _parse_llm_response(response)
        if not parsed:
            logger.warning("Audio post-processing: failed to parse LLM response")
            return _make_fallback(raw_text)

        full = parsed["transcript_full"]
        summary = parsed["transcript_summary"]

        # Run guardrails
        if not _validate_transcription(raw_text, full, summary):
            return _make_fallback(raw_text)
        if not _validate_lengths(raw_text, full, summary):
            return _make_fallback(raw_text)

        logger.info(
            "Audio post-processing OK: raw=%d words → full=%d words, summary=%d words",
            word_count, len(full.split()), len(summary.split()),
        )

        return {
            "transcript_raw": raw_text,
            "transcript_full": full,
            "transcript_summary": summary,
        }

    except asyncio.TimeoutError:
        logger.warning("Audio post-processing timed out after %ds", LLM_TIMEOUT_SECONDS)
        return _make_fallback(raw_text)
    except Exception as e:
        logger.error("Audio post-processing failed: %s", e)
        return _make_fallback(raw_text)
