"""
Creator Style Loader - Unified loader for all creator style/pattern data.

Combines:
- WritingPatterns (from models/writing_patterns.py)
- CreatorDMStyle (from services/creator_dm_style_service.py)
- ToneProfile (from core/tone_service.py)

This provides a single entry point for the DMAgent to get all style data
formatted for prompt injection.

Scalable for N creators - each can have their own patterns stored in DB.
"""

import logging
import os

logger = logging.getLogger(__name__)

# When true, use compressed Doc D (~1.3K chars) from CPE baseline metrics
# instead of the 38K personality extraction. Optimized for Qwen3-14B.
USE_COMPRESSED_DOC_D = os.getenv("USE_COMPRESSED_DOC_D", "false").lower() in (
    "true", "1", "yes",
)


def get_creator_style_prompt(creator_id: str) -> str:
    """
    Get the complete style prompt for a creator.

    Priority:
    0. Compressed Doc D (if USE_COMPRESSED_DOC_D=true) — ~1.3K chars,
       built from CPE baseline metrics + BFI profile. For Qwen3-14B.
    1. If a personality extraction (Doc D) exists, its system prompt
       replaces all legacy sources (WritingPatterns, DMStyle, ToneProfile).
    2. Otherwise falls back to the 3 legacy sources.

    Args:
        creator_id: Creator ID (e.g., 'stefano_bonanno')

    Returns:
        Formatted style prompt string, or empty string if no data
    """
    # Priority 0: Compressed Doc D (CPE-optimized, ~1.3K chars)
    if USE_COMPRESSED_DOC_D:
        try:
            from core.dm.compressed_doc_d import build_compressed_doc_d

            compressed = build_compressed_doc_d(creator_id)
            if compressed:
                logger.info(
                    "Using COMPRESSED Doc D for %s: %d chars",
                    creator_id, len(compressed),
                )
                return compressed
        except Exception as e:
            logger.warning("Compressed Doc D failed for %s: %s", creator_id, e)

    # Priority 1: Personality extraction (Doc D §4.1) — replaces all legacy sources
    try:
        from core.personality_loader import load_extraction

        extraction = load_extraction(creator_id)
        if extraction and extraction.system_prompt:
            logger.info(
                "Using personality extraction for %s: %d chars (replaces legacy sources)",
                creator_id, len(extraction.system_prompt),
            )
            return extraction.system_prompt
    except Exception as e:
        logger.warning("Could not load personality extraction for %s: %s", creator_id, e)

    # Priority 2: Legacy sources (WritingPatterns + DMStyle + ToneProfile)
    sections = []

    # 1. Get writing patterns (punctuation, laughs, emojis, etc.)
    try:
        from models.writing_patterns import format_writing_patterns_for_prompt

        writing_prompt = format_writing_patterns_for_prompt(creator_id)
        if writing_prompt:
            sections.append(writing_prompt)
            logger.debug(f"Loaded writing patterns for {creator_id}")
    except Exception as e:
        logger.warning(f"Could not load writing patterns for {creator_id}: {e}")

    # 2. Get DM style (length patterns, never_uses, etc.)
    try:
        from services.creator_dm_style_service import get_creator_dm_style_for_prompt

        dm_style_prompt = get_creator_dm_style_for_prompt(creator_id)
        if dm_style_prompt:
            sections.append(dm_style_prompt)
            logger.debug(f"Loaded DM style for {creator_id}")
    except Exception as e:
        logger.warning(f"Could not load DM style for {creator_id}: {e}")

    # 3. Get tone profile prompt section (if exists in DB/JSON)
    try:
        from core.tone_service import get_tone_prompt_section

        tone_prompt = get_tone_prompt_section(creator_id)
        if tone_prompt:
            sections.append(tone_prompt)
            logger.debug(f"Loaded tone profile for {creator_id}")
    except Exception as e:
        logger.warning(f"Could not load tone profile for {creator_id}: {e}")

    if not sections:
        logger.info(f"No style data found for {creator_id}")
        return ""

    combined = "\n\n".join(sections)
    logger.info(
        f"Loaded style prompt for {creator_id}: " f"{len(combined)} chars, {len(sections)} sections"
    )

    return combined


def has_style_data(creator_id: str) -> bool:
    """
    Check if a creator has any style data configured.

    Args:
        creator_id: Creator ID

    Returns:
        True if any style data exists
    """
    try:
        from core.personality_loader import load_extraction

        if load_extraction(creator_id):
            return True
    except Exception:
        pass

    try:
        from models.writing_patterns import get_writing_patterns

        if get_writing_patterns(creator_id):
            return True
    except Exception as e:
        logger.warning("Suppressed error in from models.writing_patterns import get_writing...: %s", e)

    try:
        from services.creator_dm_style_service import CreatorDMStyleService

        if CreatorDMStyleService.get_style(creator_id):
            return True
    except Exception as e:
        logger.warning("Suppressed error in from services.creator_dm_style_service import C...: %s", e)

    try:
        from core.tone_service import get_tone_prompt_section

        if get_tone_prompt_section(creator_id):
            return True
    except Exception as e:
        logger.warning("Suppressed error in from core.tone_service import get_tone_prompt_s...: %s", e)

    return False


def list_creators_with_style() -> list:
    """
    List all creator IDs that have style data configured.

    Returns:
        List of creator IDs
    """
    creators = set()

    try:
        from models.writing_patterns import get_writing_patterns

        # Check known creators
        for cid in ["stefano_bonanno", "5e5c2364-c99a-4484-b986-741bb84a11cf"]:
            if get_writing_patterns(cid):
                creators.add(cid)
    except Exception as e:
        logger.warning("Suppressed error in from models.writing_patterns import get_writing...: %s", e)

    try:
        from services.creator_dm_style_service import CreatorDMStyleService

        creators.update(CreatorDMStyleService._styles.keys())
    except Exception as e:
        logger.warning("Suppressed error in from services.creator_dm_style_service import C...: %s", e)

    try:
        from core.tone_service import list_profiles

        creators.update(list_profiles())
    except Exception as e:
        logger.warning("Suppressed error in from core.tone_service import list_profiles: %s", e)

    return list(creators)
