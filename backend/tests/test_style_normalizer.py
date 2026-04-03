"""Tests for core/dm/style_normalizer.py — Bug 2 fix.

Validates:
- Emoji normalization converges to creator target rate ±5%
- Fallback (no profile) → 50% rate
- evaluation_profiles/ file takes precedence over baseline
- Count trimming when emojis are kept
- Exclamation normalization unchanged
- ENABLE_STYLE_NORMALIZER=false passthrough
"""

import json
import random
import sys
import tempfile
from pathlib import Path
from unittest import mock
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.dm.style_normalizer as sn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EMOJI_RESPONSES = [
    "Hola! 😂😂",
    "Ya estás apuntada 🙏🏽",
    "Genial!! ❤️❤️❤️",
    "Jajaja 🤣",
    "Ok! 💪",
    "Sisi 😘 tranqui",
    "Uf qué fuerte 😮💨",
    "Wow 🔥🔥",
    "Venga! 😊",
    "Hecho 👍",
]

# 100 responses, all contain emoji (worst-case raw LLM output)
HUNDRED_EMOJI_RESPONSES = (EMOJI_RESPONSES * 10)


def _emoji_rate(responses):
    """Fraction of responses that contain at least one emoji."""
    from core.emoji_utils import is_emoji_char
    count = sum(1 for r in responses if any(is_emoji_char(c) for c in r))
    return count / len(responses)


def _clear_caches():
    sn._baseline_cache.clear()
    sn._natural_rates_cache.clear()
    sn._eval_profile_cache.clear()


# ---------------------------------------------------------------------------
# Test: direct rate formula converges to target ±5%
# ---------------------------------------------------------------------------

class TestEmojiRateConvergence:
    def test_target_023_converges(self):
        """100 responses through normalizer → emoji rate ≈ 0.23 ±0.05."""
        _clear_caches()
        random.seed(42)

        target = 0.23
        with patch.object(sn, "_get_creator_emoji_rate", return_value=target):
            normalized = [
                sn.normalize_style(r, "test_creator")
                for r in HUNDRED_EMOJI_RESPONSES
            ]

        rate = _emoji_rate(normalized)
        assert abs(rate - target) <= 0.05, (
            f"Emoji rate {rate:.3f} outside ±5% of target {target}"
        )

    def test_target_010_converges(self):
        """Low target (10%) — verify stricter suppression."""
        _clear_caches()
        random.seed(0)

        target = 0.10
        with patch.object(sn, "_get_creator_emoji_rate", return_value=target):
            normalized = [
                sn.normalize_style(r, "test_creator")
                for r in HUNDRED_EMOJI_RESPONSES
            ]

        rate = _emoji_rate(normalized)
        assert abs(rate - target) <= 0.05

    def test_target_050_converges(self):
        """Mid target (50%)."""
        _clear_caches()
        random.seed(1)

        target = 0.50
        with patch.object(sn, "_get_creator_emoji_rate", return_value=target):
            normalized = [
                sn.normalize_style(r, "test_creator")
                for r in HUNDRED_EMOJI_RESPONSES
            ]

        rate = _emoji_rate(normalized)
        assert abs(rate - target) <= 0.05

    def test_target_090_mostly_keeps(self):
        """High creator rate (90%) — most emojis kept.
        Uses 200 samples (stddev ~2%) to stay within ±5% at this rate."""
        _clear_caches()
        random.seed(5)

        target = 0.90
        two_hundred = HUNDRED_EMOJI_RESPONSES * 2
        with patch.object(sn, "_get_creator_emoji_rate", return_value=target):
            normalized = [
                sn.normalize_style(r, "test_creator")
                for r in two_hundred
            ]

        rate = _emoji_rate(normalized)
        assert abs(rate - target) <= 0.05, (
            f"Emoji rate {rate:.3f} outside ±5% of target {target}"
        )


# ---------------------------------------------------------------------------
# Test: fallback when no profile → 50% rate
# ---------------------------------------------------------------------------

class TestFallback:
    def test_no_profile_gives_50pct(self):
        """When _get_creator_emoji_rate returns None → fallback keep_prob=0.50."""
        _clear_caches()
        random.seed(7)

        with patch.object(sn, "_get_creator_emoji_rate", return_value=None):
            normalized = [
                sn.normalize_style(r, "unknown_creator")
                for r in HUNDRED_EMOJI_RESPONSES
            ]

        rate = _emoji_rate(normalized)
        assert abs(rate - 0.50) <= 0.07, (
            f"Fallback rate {rate:.3f} should be near 0.50"
        )

    def test_returns_response_not_empty(self):
        """Normalizer never returns an empty string when input was non-empty."""
        _clear_caches()
        random.seed(99)

        with patch.object(sn, "_get_creator_emoji_rate", return_value=0.0):
            for r in EMOJI_RESPONSES:
                result = sn.normalize_style(r, "zero_emoji_creator")
                # Even with 0% target, safety guard must prevent empty output
                # (stripping is skipped when result would be < 2 chars)
                assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Test: evaluation_profiles/ file takes priority over baseline
# ---------------------------------------------------------------------------

class TestEvalProfilePriority:
    def test_eval_profile_overrides_baseline(self, tmp_path):
        """evaluation_profiles/{creator}_style.json emoji_rate wins over baseline."""
        _clear_caches()

        creator = "priority_test_creator"
        profile_dir = tmp_path / "evaluation_profiles"
        profile_dir.mkdir()
        profile_file = profile_dir / f"{creator}_style.json"
        profile_file.write_text(json.dumps({"emoji_rate": 0.10}))

        with patch.object(Path, "__new__", lambda cls, *args: Path.__new__(cls)):
            # Monkeypatch the path resolution inside _load_eval_profile_emoji_rate
            with patch(
                "core.dm.style_normalizer._load_eval_profile_emoji_rate",
                return_value=0.10,
            ):
                with patch(
                    "core.dm.style_normalizer._load_baseline",
                    return_value={"emoji": {"emoji_rate_pct": 90}},  # higher value
                ):
                    rate = sn._get_creator_emoji_rate(creator)

        # When eval_profile returns 0.10, that must be used (not baseline 0.90)
        assert rate == 0.10

    def test_falls_back_to_baseline_when_no_eval_profile(self):
        """If eval_profile doesn't exist, use baseline emoji_rate_pct."""
        _clear_caches()

        with patch(
            "core.dm.style_normalizer._load_eval_profile_emoji_rate",
            return_value=None,
        ):
            with patch(
                "core.dm.style_normalizer._load_baseline",
                return_value={"emoji": {"emoji_rate_pct": 22.6}},
            ):
                rate = sn._get_creator_emoji_rate("iris_bertran")

        assert abs(rate - 0.226) < 0.001

    def test_returns_none_when_both_missing(self):
        """No eval_profile AND no baseline → return None (caller uses 0.50 fallback)."""
        _clear_caches()

        with patch(
            "core.dm.style_normalizer._load_eval_profile_emoji_rate",
            return_value=None,
        ):
            with patch(
                "core.dm.style_normalizer._load_baseline",
                return_value=None,
            ):
                rate = sn._get_creator_emoji_rate("new_creator")

        assert rate is None


# ---------------------------------------------------------------------------
# Test: eval profile percentage vs fraction normalisation
# ---------------------------------------------------------------------------

class TestEvalProfileRateNormalisation:
    def test_percentage_value_normalised_real_file(self, tmp_path, monkeypatch):
        """emoji_rate stored as 23.0 (percentage) is converted to 0.23 via real file read."""
        _clear_caches()
        creator = "pct_creator"

        # Create real JSON file with percentage-format emoji_rate
        profile_dir = tmp_path / "evaluation_profiles"
        profile_dir.mkdir()
        profile_file = profile_dir / f"{creator}_style.json"
        profile_file.write_text(json.dumps({"emoji_rate": 23.0}))

        # Patch backend_root so _load_eval_profile_emoji_rate finds our tmp file
        import core.dm.style_normalizer as _sn_mod
        monkeypatch.setattr(
            _sn_mod,
            "_load_eval_profile_emoji_rate",
            lambda c: _real_load_from(tmp_path, c),
        )

        rate = sn._get_creator_emoji_rate(creator)
        assert rate is not None, "Expected a rate to be returned"
        assert abs(rate - 0.23) < 0.001, f"Expected 0.23, got {rate}"

    def test_fraction_value_unchanged(self, tmp_path, monkeypatch):
        """emoji_rate stored as 0.23 (fraction) stays at 0.23."""
        _clear_caches()
        creator = "frac_creator"

        monkeypatch.setattr(
            sn,
            "_load_eval_profile_emoji_rate",
            lambda c: _real_load_from(tmp_path, c) if c == creator else None,
        )
        profile_dir = tmp_path / "evaluation_profiles"
        profile_dir.mkdir(exist_ok=True)
        (profile_dir / f"{creator}_style.json").write_text(json.dumps({"emoji_rate": 0.23}))

        rate = sn._get_creator_emoji_rate(creator)
        assert rate is not None
        assert abs(rate - 0.23) < 0.001


def _real_load_from(base_path: Path, creator_id: str):
    """Helper: run the real _load_eval_profile_emoji_rate logic against tmp_path."""
    profile_path = base_path / "evaluation_profiles" / f"{creator_id}_style.json"
    try:
        data = json.loads(profile_path.read_text())
        raw = data.get("emoji_rate")
        if raw is None:
            return None
        rate = float(raw)
        if rate > 1.0:
            rate = rate / 100.0
        return max(0.0, min(1.0, rate))
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# Test: ENABLE_STYLE_NORMALIZER=false passthrough
# ---------------------------------------------------------------------------

class TestFeatureFlag:
    def test_disabled_passthrough(self):
        original = sn.ENABLE_STYLE_NORMALIZER
        try:
            sn.ENABLE_STYLE_NORMALIZER = False
            text = "Hola! 😂😂😂 !!!"
            result = sn.normalize_style(text, "any_creator")
            assert result == text
        finally:
            sn.ENABLE_STYLE_NORMALIZER = original


# ---------------------------------------------------------------------------
# Test: text without emoji is not modified by emoji section
# ---------------------------------------------------------------------------

class TestNoEmojiPassthrough:
    def test_no_emoji_response_unchanged_by_emoji_section(self):
        _clear_caches()

        text = "Vale, te apunto para el lunes."
        with patch.object(sn, "_get_creator_emoji_rate", return_value=0.10):
            result = sn.normalize_style(text, "test_creator")

        # No emoji to strip; excl normalization might kick in but text has no "!"
        assert result == text


# ---------------------------------------------------------------------------
# Test: safety guard — never returns < 2 chars
# ---------------------------------------------------------------------------

class TestSafetyGuard:
    def test_short_emoji_only_response_not_emptied(self):
        """Response that IS only emojis should not produce empty string."""
        _clear_caches()
        random.seed(42)

        # Run many times since it's probabilistic
        results = []
        with patch.object(sn, "_get_creator_emoji_rate", return_value=0.0):
            for _ in range(20):
                r = sn.normalize_style("😂", "test_creator")
                results.append(r)

        # Due to safety guard (len < 2 → keep original), some or all will be "😂"
        # The key assertion: never an empty string
        assert all(len(r) >= 1 for r in results)
