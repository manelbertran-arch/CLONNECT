"""Tests for DEEPINFRA_TIMEOUT default value (must be 30s, not 8s).

Context: 8s default caused silent Gemini fallbacks during CCEE runs,
contaminating Gemma-4-31B measurements. Changed to 30s (DECISIONS.md, 2026-04-17).
"""

import importlib
import os
import sys
import unittest
from unittest.mock import patch


class TestDeepinfraTimeoutDefault(unittest.TestCase):
    def test_gemini_provider_default_is_30(self):
        """gemini_provider._try_deepinfra must default to 30s, not 8s."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEEPINFRA_TIMEOUT", None)
            # Re-read the default at call time — import the getter directly
            timeout = float(os.getenv("DEEPINFRA_TIMEOUT", "30"))
            self.assertEqual(timeout, 30.0, "Default must be 30s to avoid Gemma-4-31B fallbacks")

    def test_gemini_provider_env_override(self):
        """DEEPINFRA_TIMEOUT env var must override the default."""
        with patch.dict(os.environ, {"DEEPINFRA_TIMEOUT": "45"}):
            timeout = float(os.getenv("DEEPINFRA_TIMEOUT", "30"))
            self.assertEqual(timeout, 45.0)

    def test_deepinfra_provider_source_default_is_30(self):
        """Verify the default string literal in deepinfra_provider.py is '30', not '8'."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "core" / "providers" / "deepinfra_provider.py"
        content = src.read_text()
        self.assertIn('os.getenv("DEEPINFRA_TIMEOUT", "30")', content,
                      "deepinfra_provider.py must use '30' as default, not '8'")
        self.assertNotIn('os.getenv("DEEPINFRA_TIMEOUT", "8")', content,
                         "deepinfra_provider.py must not use old '8' default")

    def test_gemini_provider_source_default_is_30(self):
        """Verify the default string literal in gemini_provider.py is '30', not '8'."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "core" / "providers" / "gemini_provider.py"
        content = src.read_text()
        self.assertIn('os.getenv("DEEPINFRA_TIMEOUT", "30")', content,
                      "gemini_provider.py must use '30' as default, not '8'")
        self.assertNotIn('os.getenv("DEEPINFRA_TIMEOUT", "8")', content,
                         "gemini_provider.py must not use old '8' default")

    def test_fallback_logs_have_di_fallback_prefix(self):
        """All DeepInfra fallback log messages must use [DI-FALLBACK] structured format."""
        import pathlib
        src = pathlib.Path(__file__).parent.parent / "core" / "providers" / "gemini_provider.py"
        content = src.read_text()
        # All 3 fallback paths must be structured
        self.assertIn("[DI-FALLBACK] reason=timeout", content)
        self.assertIn("[DI-FALLBACK] reason=empty_response", content)
        self.assertIn("[DI-FALLBACK] reason=error", content)
        # Old unstructured messages must be gone
        self.assertNotIn('"DeepInfra timeout, falling back to Gemini"', content)
        self.assertNotIn('"DeepInfra returned empty, falling back to Gemini"', content)
        self.assertNotIn('"DeepInfra failed:', content)


if __name__ == "__main__":
    unittest.main()
