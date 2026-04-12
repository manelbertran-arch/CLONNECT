"""
Exemplar Calibration for CCEE Judge (PersonaGym EMNLP 2025)

Generates concrete example responses at each quality level (1-5) from a
creator's Doc D, so the judge has calibration anchors instead of abstract
rubric descriptions alone.

Exemplars are GENERATED from Doc D via LLM (zero hardcoding) and cached
per creator_id for the duration of the process.
"""

import json
import logging
import os
import re
from typing import Dict, Optional

import openai

logger = logging.getLogger(__name__)

# In-process cache: {creator_id: {5: "...", 4: "...", ...}}
_exemplar_cache: Dict[str, Dict[int, str]] = {}

# Use same DeepInfra/Qwen3 config as lead simulator
_EXEMPLAR_MODEL = os.environ.get("LEAD_SIM_MODEL", "Qwen/Qwen3-30B-A3B")


def _get_deepinfra_client() -> openai.OpenAI:
    api_key = os.environ.get("DEEPINFRA_API_KEY") or os.environ.get("DEEPINFRA_TOKEN")
    if not api_key:
        raise RuntimeError("DEEPINFRA_API_KEY not set for exemplar generation")
    return openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepinfra.com/v1/openai",
        timeout=60,
    )


def generate_exemplar_responses(
    doc_d_text: str,
    creator_id: str = "",
    user_input: str = "",
) -> Dict[int, str]:
    """Generate 5 exemplar responses for score levels 1-5.

    Uses LLM to create responses that demonstrate each quality level
    based on the creator's personality profile (Doc D).

    Args:
        doc_d_text: The creator's compressed Doc D text
        creator_id: Creator slug (used for caching)
        user_input: Optional sample user message for context

    Returns:
        Dict mapping score level (1-5) to example response string.
        Returns empty dict on failure.
    """
    # Check cache
    if creator_id and creator_id in _exemplar_cache:
        return _exemplar_cache[creator_id]

    if not doc_d_text:
        logger.warning("Exemplar generation: no Doc D text provided")
        return {}

    sample_input = user_input or "Hola! Me interesa info sobre tus servicios"

    prompt = f"""Given this creator's personality profile:

{doc_d_text}

A follower sent: "{sample_input}"

Generate exactly 5 example responses that demonstrate different quality levels of persona match. Each response should be realistic DM-style text (short, casual).

LEVEL 5 (PERFECT CLONE): Indistinguishable from the real creator. Uses their exact language patterns, slang, emoji style, tone, language mixing, and communication style as documented in the profile.

LEVEL 4 (GOOD): Mostly matches the creator's style. Right language and general tone but missing some creator-specific markers (catchphrases, specific emoji patterns, language mixing nuances).

LEVEL 3 (GENERIC): Doesn't violate the persona but doesn't demonstrate it. A generic friendly response that any helpful person could write. No creator-specific markers.

LEVEL 2 (WRONG REGISTER): Wrong formality level for this creator. Too formal, too structured, or too cold compared to the documented personality. Right language but wrong feel.

LEVEL 1 (WRONG PERSONA): Completely wrong style. Opposite language, wrong tone, sounds like a corporate chatbot or a completely different person.

Output ONLY valid JSON with string keys "5","4","3","2","1" mapping to the example response text. No explanation, no markdown, just the JSON object. /no_think"""

    client = _get_deepinfra_client()
    try:
        resp = client.chat.completions.create(
            model=_EXEMPLAR_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800,
        )
        text = resp.choices[0].message.content or ""

        # Strip thinking artifacts
        from core.providers.deepinfra_provider import strip_thinking_artifacts
        text = strip_thinking_artifacts(text)

        # Extract JSON from response (may be wrapped in ```json blocks)
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        data = json.loads(text)
        exemplars = {}
        for level in [5, 4, 3, 2, 1]:
            val = data.get(str(level), data.get(level, ""))
            if val:
                exemplars[level] = str(val).strip()

        if len(exemplars) < 3:
            logger.warning(f"Exemplar generation: only got {len(exemplars)} levels, expected 5")
            return {}

        # Cache
        if creator_id:
            _exemplar_cache[creator_id] = exemplars

        logger.info(f"Generated {len(exemplars)} exemplar responses for {creator_id or 'unknown'}")
        return exemplars

    except json.JSONDecodeError as e:
        logger.warning(f"Exemplar generation: JSON parse error: {e}, raw: {text[:200]}")
        return {}
    except Exception as e:
        logger.warning(f"Exemplar generation failed: {e}")
        return {}


def get_exemplar_rubric_block(
    doc_d_text: str,
    creator_id: str = "",
    base_rubric: str = "",
) -> str:
    """Build a rubric block enhanced with concrete exemplar examples.

    If exemplar generation fails, falls back to the base_rubric unchanged.

    Args:
        doc_d_text: Creator's Doc D text for generating exemplars
        creator_id: Creator slug for caching
        base_rubric: The original rubric text (used as fallback)

    Returns:
        Enhanced rubric string with examples, or base_rubric on failure.
    """
    exemplars = generate_exemplar_responses(doc_d_text, creator_id=creator_id)
    if not exemplars:
        return base_rubric

    lines = []
    rubric_defs = {
        5: "ACTIVE persona match — indistinguishable from the real creator",
        4: "Good match — mostly aligned, some creator-specific elements",
        3: "Passive/generic — doesn't violate persona but doesn't demonstrate it",
        2: "Wrong register — formality, tone, or emotional register off",
        1: "Wrong persona — clearly not this creator's style",
    }

    for level in [5, 4, 3, 2, 1]:
        definition = rubric_defs[level]
        example = exemplars.get(level, "")
        if example:
            lines.append(f"[{level}] {definition}\n     Example: \"{example}\"")
        else:
            lines.append(f"[{level}] {definition}")

    return "\n".join(lines)


def clear_cache(creator_id: Optional[str] = None) -> None:
    """Clear exemplar cache. If creator_id given, clear only that entry."""
    if creator_id:
        _exemplar_cache.pop(creator_id, None)
    else:
        _exemplar_cache.clear()
