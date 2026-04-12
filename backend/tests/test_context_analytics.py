"""Tests for G3+G4: context_analytics and G6: truncation detection.

Run with:
    python3 -m pytest tests/test_context_analytics.py -x -q
"""

import pytest
import os

# ── G3: analyze_token_distribution ────────────────────────────────────────────

def test_basic_distribution():
    """Three sections produce correct token estimates and ratios."""
    from core.dm.context_analytics import analyze_token_distribution

    section_sizes = {
        "style": 800,    # 200 tokens
        "rag": 1600,     # 400 tokens
        "memory": 400,   # 100 tokens
    }
    system_prompt = "x" * 2800   # 700 tokens
    history = [{"role": "user", "content": "y" * 400}]  # 100 tokens

    result = analyze_token_distribution(
        section_sizes=section_sizes,
        system_prompt=system_prompt,
        history_messages=history,
        model_context_window=32768,
    )

    assert result["sections"]["style"]["tokens"] == 200
    assert result["sections"]["rag"]["tokens"] == 400
    assert result["sections"]["memory"]["tokens"] == 100
    assert result["history_tokens"] == 100
    assert result["system_prompt_tokens"] == 700
    assert result["total_tokens"] == 800   # system_prompt(700) + history(100)
    assert result["context_window"] == 32768
    assert 0 < result["usage_ratio"] < 1
    assert result["largest_section"] in ("style", "rag", "memory", "history", "none")


def test_empty_sections():
    """Empty or None sections do not cause errors."""
    from core.dm.context_analytics import analyze_token_distribution

    result = analyze_token_distribution(
        section_sizes={},
        system_prompt="",
        history_messages=[],
    )
    assert isinstance(result, dict)
    assert result.get("total_tokens", 0) == 0


def test_zero_char_sections_excluded():
    """Sections with zero chars are excluded from distribution."""
    from core.dm.context_analytics import analyze_token_distribution

    result = analyze_token_distribution(
        section_sizes={"style": 0, "rag": 400},
        system_prompt="x" * 400,
        history_messages=[],
    )
    assert "style" not in result.get("sections", {})
    assert "rag" in result.get("sections", {})


def test_history_with_none_content():
    """History messages with missing content don't crash."""
    from core.dm.context_analytics import analyze_token_distribution

    result = analyze_token_distribution(
        section_sizes={"style": 400},
        system_prompt="x" * 400,
        history_messages=[{"role": "user"}, {"role": "assistant", "content": "hi"}],
    )
    assert result.get("history_tokens", 0) >= 0


# ── G4: check_context_health ──────────────────────────────────────────────────

def test_no_warnings_at_low_usage():
    """No warnings when context is well under limits."""
    from core.dm.context_analytics import check_context_health

    analytics = {
        "total_tokens": 1000,
        "context_window": 32768,
        "usage_ratio": 0.03,
        "largest_section": "style",
        "largest_section_pct": 20.0,
        "over_section_threshold": False,
        "sections": {"style": {"tokens": 200, "pct_of_total": 20.0}},
        "history_tokens": 100,
        "history_pct_of_total": 10.0,
    }
    warnings = check_context_health(analytics)
    assert warnings == []


def test_warning_at_80_percent(monkeypatch):
    """Usage at 83% generates a WARNING (not critical)."""
    monkeypatch.setenv("CONTEXT_WARNING_THRESHOLD", "0.80")
    monkeypatch.setenv("CONTEXT_CRITICAL_THRESHOLD", "0.90")

    from importlib import reload
    import core.dm.context_analytics as mod
    reload(mod)

    analytics = {
        "total_tokens": 27200,
        "context_window": 32768,
        "usage_ratio": 0.83,
        "largest_section": "history",
        "largest_section_pct": 41.0,
        "over_section_threshold": False,
        "sections": {},
        "history_tokens": 11152,
        "history_pct_of_total": 41.0,
    }
    warnings = mod.check_context_health(analytics)
    levels = [w["level"] for w in warnings]
    assert "warning" in levels
    assert "critical" not in levels


def test_critical_at_90_percent(monkeypatch):
    """Usage at 92% generates a CRITICAL warning."""
    monkeypatch.setenv("CONTEXT_WARNING_THRESHOLD", "0.80")
    monkeypatch.setenv("CONTEXT_CRITICAL_THRESHOLD", "0.90")

    from importlib import reload
    import core.dm.context_analytics as mod
    reload(mod)

    analytics = {
        "total_tokens": 30000,
        "context_window": 32768,
        "usage_ratio": 0.92,
        "largest_section": "rag",
        "largest_section_pct": 35.0,
        "over_section_threshold": False,
        "sections": {},
        "history_tokens": 5000,
        "history_pct_of_total": 16.0,
    }
    warnings = mod.check_context_health(analytics)
    levels = [w["level"] for w in warnings]
    assert "critical" in levels


def test_section_warning_when_section_over_40_percent(monkeypatch):
    """A section consuming >40% of total budget generates a section WARNING."""
    monkeypatch.setenv("SECTION_WARNING_THRESHOLD", "0.40")

    from importlib import reload
    import core.dm.context_analytics as mod
    reload(mod)

    # rag takes 45% of a 10k-token context → over threshold
    analytics = {
        "total_tokens": 10000,
        "context_window": 32768,
        "usage_ratio": 0.31,
        "largest_section": "rag",
        "largest_section_pct": 45.0,
        "over_section_threshold": True,
        "sections": {
            "rag": {"tokens": 4500, "pct_of_total": 45.0},
            "style": {"tokens": 2000, "pct_of_total": 20.0},
        },
        "history_tokens": 1500,
        "history_pct_of_total": 15.0,
    }
    warnings = mod.check_context_health(analytics)
    # Should have a warning about the section dominating
    section_warnings = [w for w in warnings if "40%" in w["message"] or "Section" in w["message"]]
    assert section_warnings, f"Expected section warning, got: {warnings}"


def test_empty_analytics_returns_no_warnings():
    """Empty dict input returns empty warning list without crashing."""
    from core.dm.context_analytics import check_context_health
    assert check_context_health({}) == []


# ── G6: _is_truncated_by_api (API signal, not content heuristic) ──────────────

def test_is_truncated_by_api_length():
    """finish_reason='length' (max_tokens hit) → truncated."""
    from core.dm.phases.generation import _is_truncated_by_api
    assert _is_truncated_by_api("length") is True


def test_is_truncated_by_api_stop():
    """finish_reason='stop' (natural end) → NOT truncated."""
    from core.dm.phases.generation import _is_truncated_by_api
    assert _is_truncated_by_api("stop") is False


def test_is_truncated_by_api_safety():
    """finish_reason='safety' (filtered) → NOT truncated."""
    from core.dm.phases.generation import _is_truncated_by_api
    assert _is_truncated_by_api("safety") is False


def test_is_truncated_by_api_none():
    """finish_reason=None (provider didn't return signal) → NOT truncated (safe default)."""
    from core.dm.phases.generation import _is_truncated_by_api
    assert _is_truncated_by_api(None) is False


def test_is_truncated_by_api_empty_string():
    """finish_reason='' → NOT truncated."""
    from core.dm.phases.generation import _is_truncated_by_api
    assert _is_truncated_by_api("") is False


def test_is_truncated_by_api_unknown():
    """Unknown finish_reason → NOT truncated (safe default, no assumptions)."""
    from core.dm.phases.generation import _is_truncated_by_api
    assert _is_truncated_by_api("recitation") is False
    assert _is_truncated_by_api("other") is False
    assert _is_truncated_by_api("MAX_TOKENS") is False  # non-normalized → False


def test_truncation_retry_constant():
    """MAX_TRUNCATION_RETRIES is at most 2 by default."""
    from core.dm.phases.generation import MAX_TRUNCATION_RETRIES
    assert MAX_TRUNCATION_RETRIES <= 2


def test_no_content_heuristic_constants():
    """TRUNCATION_TOKEN_MULTIPLIER and TRUNCATION_TOKEN_CAP no longer exist (removed)."""
    import core.dm.phases.generation as gen_module
    assert not hasattr(gen_module, "TRUNCATION_TOKEN_MULTIPLIER"), \
        "TRUNCATION_TOKEN_MULTIPLIER should have been removed (magic number)"
    assert not hasattr(gen_module, "TRUNCATION_TOKEN_CAP"), \
        "TRUNCATION_TOKEN_CAP should have been removed (magic number)"


def test_no_detect_truncation_heuristic():
    """_detect_truncation() (content heuristic) no longer exists."""
    import core.dm.phases.generation as gen_module
    assert not hasattr(gen_module, "_detect_truncation"), \
        "_detect_truncation should have been removed (content heuristic violates zero hardcoding)"
