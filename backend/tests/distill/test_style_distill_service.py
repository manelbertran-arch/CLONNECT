"""Tests for StyleDistillService (ARC3 Phase 1).

All LLM calls are mocked — no real DB or API required.
Uses MagicMock session following the pattern from tests/memory/.
"""

import asyncio
import hashlib
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from services.style_distill_service import (
    DISTILL_MIN_CHARS,
    DISTILL_MAX_CHARS,
    DISTILL_PROMPT_VERSION,
    StyleDistillService,
    _distill_model,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

CREATOR_ID = str(uuid.UUID("00000000-0000-0000-0000-000000000001"))

_SHORT_DOC = "x" * 500
_VALID_DOC = "y" * 5000

# A valid distilled output (inside [DISTILL_MIN_CHARS, DISTILL_MAX_CHARS]).
_VALID_DISTILLED = "z" * 1400  # 1400 chars — within [1200, 1800]


def _make_service(fetchone=None, fetchall=None):
    """Return (service, mock_session)."""
    session = MagicMock()
    exec_result = MagicMock()
    exec_result.fetchone.return_value = fetchone
    exec_result.fetchall.return_value = fetchall or []
    session.execute.return_value = exec_result
    return StyleDistillService(session), session


def _make_llm_response(content: str) -> dict:
    """Minimal OpenRouter response dict."""
    return {"content": content, "model": "google/gemma-4-31b-it", "provider": "openrouter"}


# ─────────────────────────────────────────────────────────────────────────────
# test_compute_hash_deterministic
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_hash_deterministic():
    """Same input always produces the same 16-char hex hash."""
    svc, _ = _make_service()
    text = "Soy Iris Bertran y mi estilo es muy personal."

    h1 = svc.compute_hash(text)
    h2 = svc.compute_hash(text)

    assert h1 == h2, "Hash must be deterministic"
    assert len(h1) == 16, "Hash must be 16 chars"
    assert h1 == hashlib.sha256(text.encode()).hexdigest()[:16], "Hash algorithm mismatch"


def test_compute_hash_different_inputs():
    """Different inputs produce different hashes."""
    svc, _ = _make_service()
    h1 = svc.compute_hash("foo")
    h2 = svc.compute_hash("bar")
    assert h1 != h2


# ─────────────────────────────────────────────────────────────────────────────
# test_get_or_generate_new_content_calls_llm
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_or_generate_new_content_calls_llm():
    """When no cached row exists, LLM is called and result is stored."""
    # fetchone returns None → cache miss
    svc, session = _make_service(fetchone=None)

    with patch(
        "core.providers.openrouter_provider.call_openrouter",
        new_callable=AsyncMock,
        return_value=_make_llm_response(_VALID_DISTILLED),
    ) as mock_llm:
        result = await svc.get_or_generate(
            creator_id=CREATOR_ID,
            source_doc_d=_VALID_DOC,
            prompt_version=1,
        )

    assert result == _VALID_DISTILLED
    mock_llm.assert_called_once()
    # DB commit must have been called (to store the row)
    session.commit.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# test_get_or_generate_cached_content_skips_llm
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_or_generate_cached_content_skips_llm():
    """When a cached row exists, LLM is NOT called and cached value is returned."""
    # Make fetchone() return something that indexes as row[0]
    fetchone_value = (_VALID_DISTILLED,)  # tuple, so row[0] = _VALID_DISTILLED

    svc, session = _make_service(fetchone=fetchone_value)

    with patch(
        "core.providers.openrouter_provider.call_openrouter",
        new_callable=AsyncMock,
    ) as mock_llm:
        result = await svc.get_or_generate(
            creator_id=CREATOR_ID,
            source_doc_d=_VALID_DOC,
            prompt_version=1,
        )

    assert result == _VALID_DISTILLED
    mock_llm.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# test_force_regenerates_even_if_cached
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_force_regenerates_even_if_cached():
    """force=True causes LLM to be called even if a cached row exists."""
    # Even though fetchone would return something, force skips the cache check
    fetchone_value = (_VALID_DISTILLED,)
    svc, session = _make_service(fetchone=fetchone_value)

    new_distilled = "a" * 1350  # different content, valid length

    with patch(
        "core.providers.openrouter_provider.call_openrouter",
        new_callable=AsyncMock,
        return_value=_make_llm_response(new_distilled),
    ) as mock_llm:
        result = await svc.get_or_generate(
            creator_id=CREATOR_ID,
            source_doc_d=_VALID_DOC,
            prompt_version=1,
            force=True,
        )

    assert result == new_distilled
    mock_llm.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# test_distill_length_validation_retries
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_distill_length_validation_retries():
    """If LLM returns <1200 chars on first attempt, it retries and succeeds."""
    too_short = "x" * 500  # fails length check
    svc, session = _make_service(fetchone=None)

    call_count = 0

    async def fake_llm(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_llm_response(too_short)
        return _make_llm_response(_VALID_DISTILLED)

    with patch(
        "core.providers.openrouter_provider.call_openrouter",
        side_effect=fake_llm,
    ):
        result = await svc.get_or_generate(
            creator_id=CREATOR_ID,
            source_doc_d=_VALID_DOC,
            prompt_version=1,
        )

    assert result == _VALID_DISTILLED
    assert call_count == 2, f"Expected 2 LLM calls (1 fail + 1 retry), got {call_count}"


# ─────────────────────────────────────────────────────────────────────────────
# test_llm_failure_raises_and_logs
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_failure_raises_and_logs():
    """If LLM raises on every attempt, RuntimeError is propagated."""
    svc, session = _make_service(fetchone=None)

    with patch(
        "core.providers.openrouter_provider.call_openrouter",
        new_callable=AsyncMock,
        side_effect=Exception("LLM unavailable"),
    ):
        with pytest.raises(RuntimeError, match="distillation attempts failed"):
            await svc.get_or_generate(
                creator_id=CREATOR_ID,
                source_doc_d=_VALID_DOC,
                prompt_version=1,
            )
