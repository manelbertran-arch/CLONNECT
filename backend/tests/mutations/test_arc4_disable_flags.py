"""
ARC4 Phase 1 — Tests for DISABLE_M* feature flags.

These tests only verify that the kill-switch flags skip the mutation
when set to "true". They do NOT test mutation logic itself.
No prod behavior is modified — all flags default to false.
"""
import importlib
import os
import sys
import unittest


def _reload_flags():
    """Reload feature_flags module to pick up new os.environ values."""
    # Invalidate cached singleton
    if "core.feature_flags" in sys.modules:
        del sys.modules["core.feature_flags"]
    from core.feature_flags import FeatureFlags
    return FeatureFlags()


class TestM3DisableFlag(unittest.TestCase):
    """M3 — DISABLE_M3_DEDUPE_REPETITIONS"""

    def test_flag_default_false(self):
        os.environ.pop("DISABLE_M3_DEDUPE_REPETITIONS", None)
        flags = _reload_flags()
        self.assertFalse(flags.m3_disable_dedupe_repetitions)

    def test_flag_true_when_env_set(self):
        os.environ["DISABLE_M3_DEDUPE_REPETITIONS"] = "true"
        try:
            flags = _reload_flags()
            self.assertTrue(flags.m3_disable_dedupe_repetitions)
        finally:
            del os.environ["DISABLE_M3_DEDUPE_REPETITIONS"]

    def test_flag_false_when_env_false(self):
        os.environ["DISABLE_M3_DEDUPE_REPETITIONS"] = "false"
        try:
            flags = _reload_flags()
            self.assertFalse(flags.m3_disable_dedupe_repetitions)
        finally:
            del os.environ["DISABLE_M3_DEDUPE_REPETITIONS"]


class TestM4DisableFlag(unittest.TestCase):
    """M4 — DISABLE_M4_DEDUPE_SENTENCES"""

    def test_flag_default_false(self):
        os.environ.pop("DISABLE_M4_DEDUPE_SENTENCES", None)
        flags = _reload_flags()
        self.assertFalse(flags.m4_disable_dedupe_sentences)

    def test_flag_true_when_env_set(self):
        os.environ["DISABLE_M4_DEDUPE_SENTENCES"] = "true"
        try:
            flags = _reload_flags()
            self.assertTrue(flags.m4_disable_dedupe_sentences)
        finally:
            del os.environ["DISABLE_M4_DEDUPE_SENTENCES"]


class TestM5DisableFlag(unittest.TestCase):
    """M5-alt — DISABLE_M5_ECHO_DETECTOR"""

    def test_flag_default_false(self):
        os.environ.pop("DISABLE_M5_ECHO_DETECTOR", None)
        flags = _reload_flags()
        self.assertFalse(flags.m5_disable_echo_detector)

    def test_flag_true_when_env_set(self):
        os.environ["DISABLE_M5_ECHO_DETECTOR"] = "true"
        try:
            flags = _reload_flags()
            self.assertTrue(flags.m5_disable_echo_detector)
        finally:
            del os.environ["DISABLE_M5_ECHO_DETECTOR"]


class TestM6DisableFlag(unittest.TestCase):
    """M6 — DISABLE_M6_NORMALIZE_LENGTH skips enforce_length"""

    def test_flag_skips_enforcement(self):
        """When DISABLE_M6=true, enforce_length must return response unchanged."""
        os.environ["DISABLE_M6_NORMALIZE_LENGTH"] = "true"
        try:
            # Reload length_controller to pick up the env var
            if "services.length_controller" in sys.modules:
                del sys.modules["services.length_controller"]
            from services.length_controller import enforce_length
            long_response = "x" * 1000
            result = enforce_length(long_response, "hola", creator_id="iris_bertran")
            self.assertEqual(result, long_response, "M6 disabled: response must not be truncated")
        finally:
            del os.environ["DISABLE_M6_NORMALIZE_LENGTH"]
            if "services.length_controller" in sys.modules:
                del sys.modules["services.length_controller"]

    def test_flag_default_does_not_skip(self):
        """When DISABLE_M6 not set, enforce_length runs normally."""
        os.environ.pop("DISABLE_M6_NORMALIZE_LENGTH", None)
        if "services.length_controller" in sys.modules:
            del sys.modules["services.length_controller"]
        from services.length_controller import enforce_length
        # Short response — should pass through regardless
        short = "Hola!"
        result = enforce_length(short, "hola", creator_id="iris_bertran")
        # Should not raise or break
        self.assertIsInstance(result, str)


class TestM7DisableFlag(unittest.TestCase):
    """M7 — DISABLE_M7_NORMALIZE_EMOJIS"""

    def test_flag_skips_emoji_stripping(self):
        """When DISABLE_M7=true, emojis must not be stripped."""
        os.environ["DISABLE_M7_NORMALIZE_EMOJIS"] = "true"
        os.environ["DISABLE_M8_NORMALIZE_PUNCTUATION"] = "true"
        try:
            if "core.dm.style_normalizer" in sys.modules:
                del sys.modules["core.dm.style_normalizer"]
            from core.dm.style_normalizer import normalize_style
            # Response with emoji — must survive when M7 disabled
            response_with_emoji = "Hola! 😊 Qué tal?"
            result = normalize_style(response_with_emoji, "iris_bertran")
            self.assertIn("😊", result, "M7 disabled: emoji must not be stripped")
        finally:
            del os.environ["DISABLE_M7_NORMALIZE_EMOJIS"]
            del os.environ["DISABLE_M8_NORMALIZE_PUNCTUATION"]
            if "core.dm.style_normalizer" in sys.modules:
                del sys.modules["core.dm.style_normalizer"]


class TestM8DisableFlag(unittest.TestCase):
    """M8 — DISABLE_M8_NORMALIZE_PUNCTUATION"""

    def test_flag_skips_exclamation_normalization(self):
        """When DISABLE_M8=true, exclamation marks are not touched."""
        os.environ["DISABLE_M8_NORMALIZE_PUNCTUATION"] = "true"
        os.environ["DISABLE_M7_NORMALIZE_EMOJIS"] = "true"
        try:
            if "core.dm.style_normalizer" in sys.modules:
                del sys.modules["core.dm.style_normalizer"]
            from core.dm.style_normalizer import normalize_style
            response_with_excl = "Hola! Qué bien!"
            result = normalize_style(response_with_excl, "iris_bertran")
            self.assertIn("!", result, "M8 disabled: exclamations must not be removed")
        finally:
            del os.environ["DISABLE_M8_NORMALIZE_PUNCTUATION"]
            del os.environ["DISABLE_M7_NORMALIZE_EMOJIS"]
            if "core.dm.style_normalizer" in sys.modules:
                del sys.modules["core.dm.style_normalizer"]


class TestFlagDefaults(unittest.TestCase):
    """Verify ALL ARC4 flags default to False (mutations active by default)."""

    def test_all_arc4_flags_default_false(self):
        for env_key in [
            "DISABLE_M3_DEDUPE_REPETITIONS",
            "DISABLE_M4_DEDUPE_SENTENCES",
            "DISABLE_M5_ECHO_DETECTOR",
            "DISABLE_M6_NORMALIZE_LENGTH",
            "DISABLE_M7_NORMALIZE_EMOJIS",
            "DISABLE_M8_NORMALIZE_PUNCTUATION",
        ]:
            os.environ.pop(env_key, None)

        flags = _reload_flags()
        self.assertFalse(flags.m3_disable_dedupe_repetitions)
        self.assertFalse(flags.m4_disable_dedupe_sentences)
        self.assertFalse(flags.m5_disable_echo_detector)
        self.assertFalse(flags.m6_disable_length_enforce)
        self.assertFalse(flags.m7_disable_normalize_emojis)
        self.assertFalse(flags.m8_disable_normalize_punctuation)


if __name__ == "__main__":
    unittest.main()
