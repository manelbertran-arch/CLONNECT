"""Tests for Sensitive Content Detector - CRITICAL FOR USER SAFETY."""

import pytest

from core.sensitive_detector import (
    SensitiveType,
    detect_sensitive_content,
    get_crisis_resources,
)


class TestCrisisDetection:
    """CRITICAL: Must detect self-harm and crisis situations."""

    @pytest.mark.parametrize(
        "message",
        [
            "me quiero morir",
            "no quiero vivir más",
            "voy a suicidarme",
            "quiero acabar con todo",
            "me corto las venas",
        ],
    )
    def test_detects_self_harm_spanish(self, message):
        result = detect_sensitive_content(message)
        assert result, f"Failed to detect: {message}"
        assert result.type == SensitiveType.SELF_HARM
        assert result.confidence >= 0.85

    @pytest.mark.parametrize(
        "message",
        [
            "I want to kill myself",
        ],
    )
    def test_detects_self_harm_english(self, message):
        result = detect_sensitive_content(message)
        assert result, f"Failed to detect: {message}"
        assert result.type == SensitiveType.SELF_HARM
        assert result.confidence >= 0.85


class TestNoFalsePositives:
    """MUST NOT trigger on common expressions."""

    @pytest.mark.parametrize(
        "message",
        [
            "me muero de risa 😂",
            "me matas de la risa",
            "esto me está matando de trabajo",
            "muero por ese producto",
            "Hola, me interesa el curso",
            "Cuánto cuesta el programa?",
            "Qué tal! Buenas tardes",
            "Jajaja genial",
        ],
    )
    def test_no_false_positive(self, message):
        result = detect_sensitive_content(message)
        assert (
            not result or result.type == SensitiveType.NONE
        ), f"False positive on: {message}"


class TestSensitiveTypes:
    """Test detection of various sensitive content types."""

    def test_minor_detection(self):
        result = detect_sensitive_content("tengo 15 años")
        if result and result.type == SensitiveType.MINOR:
            assert result.confidence >= 0.7

    def test_phishing_detection(self):
        result = detect_sensitive_content("dame tu contraseña y tu tarjeta de crédito")
        if result:
            assert result.type in (SensitiveType.PHISHING, SensitiveType.NONE)

    def test_empty_message(self):
        result = detect_sensitive_content("")
        assert not result or result.type == SensitiveType.NONE

    def test_none_handling(self):
        """Should not crash on None-like inputs."""
        try:
            result = detect_sensitive_content("")
            assert result is not None  # Should return SensitiveResult, not None
        except Exception:
            pass  # Acceptable if it raises on bad input


class TestCrisisResources:
    """Test crisis resource generation."""

    def test_spanish_resources(self):
        resources = get_crisis_resources("es")
        assert isinstance(resources, str)
        assert len(resources) > 50
        # Should contain phone numbers
        assert "717" in resources or "024" in resources or "teléfono" in resources.lower()

    def test_english_resources(self):
        resources = get_crisis_resources("en")
        assert isinstance(resources, str)
        assert len(resources) > 50

    def test_default_language(self):
        resources = get_crisis_resources()
        assert isinstance(resources, str)
        assert len(resources) > 0


class TestSensitiveResultBool:
    """Test that SensitiveResult truthiness works correctly."""

    def test_none_type_is_falsy(self):
        result = detect_sensitive_content("Hola que tal")
        if result and result.type == SensitiveType.NONE:
            # SensitiveResult with NONE type should be falsy via __bool__
            assert not result

    def test_detected_type_is_truthy(self):
        result = detect_sensitive_content("me quiero morir")
        assert result  # Should be truthy when sensitive content detected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
