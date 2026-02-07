"""
Category 5: EXPERIENCIA USUARIO - Test Latencia
Tests that verify pipeline overhead stays within acceptable bounds.

Since actual LLM latency cannot be measured without a real LLM call,
these tests verify that the NON-LLM pipeline stages (context detection,
intent classification, length controller) execute within tight time budgets.

Validates that:
- Context detection + intent classification < 100ms
- Simple intent classification < 50ms
- Length controller computation is fast
- Multiple calls produce consistent timing (no outliers)
- No blocking operations in non-LLM pipeline stages
"""

import time

from core.context_detector import detect_all, detect_frustration, detect_sarcasm
from core.intent_classifier import classify_intent_simple
from services.length_controller import (
    classify_lead_context,
    enforce_length,
    get_context_rule,
    get_length_guidance_prompt,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _time_ms(func, *args, **kwargs):
    """Execute func and return (result, elapsed_ms)."""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = (time.perf_counter() - start) * 1000
    return result, elapsed


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLatencia:
    """Pipeline overhead must remain sub-100ms for non-LLM stages."""

    def test_respuesta_bajo_5_segundos(self):
        """Context detection + intent classification combined < 100ms.

        In production the full pipeline (detect_all + classify_intent_simple)
        runs before the LLM call.  This must stay well under 100ms so the
        overall response can be delivered in under 5 seconds.
        """
        message = "Hola, me interesa saber el precio del curso de coaching"

        start = time.perf_counter()
        ctx = detect_all(message, history=None, is_first_message=True)
        intent = classify_intent_simple(message)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Both should have produced a result
        assert ctx is not None
        assert intent is not None
        # Combined pipeline overhead must be < 100ms
        assert elapsed_ms < 100, (
            f"Context detection + intent classification took {elapsed_ms:.1f}ms "
            f"(expected < 100ms)"
        )

    def test_respuesta_bajo_3_segundos(self):
        """Simple intent classification alone < 50ms.

        classify_intent_simple is a pure keyword-based function; it should
        be nearly instantaneous.
        """
        messages = [
            "Hola!",
            "Quiero comprar el curso",
            "Es muy caro para mi",
            "Cuanto cuesta el programa?",
            "No funciona el link de pago",
        ]

        for msg in messages:
            _, elapsed = _time_ms(classify_intent_simple, msg)
            assert elapsed < 50, (
                f"classify_intent_simple('{msg}') took {elapsed:.1f}ms " f"(expected < 50ms)"
            )

    def test_no_timeout(self):
        """Length controller computation is fast (< 10ms per call).

        get_length_guidance_prompt and enforce_length are pure computation
        with no I/O and must never introduce noticeable latency.
        """
        lead_message = "Quiero saber mas sobre el programa de coaching premium"
        response = (
            "El programa de Coaching Premium incluye 8 semanas de sesiones "
            "personalizadas con ejercicios y seguimiento continuo."
        )

        _, elapsed_guidance = _time_ms(get_length_guidance_prompt, lead_message)
        assert (
            elapsed_guidance < 10
        ), f"get_length_guidance_prompt took {elapsed_guidance:.1f}ms (expected < 10ms)"

        _, elapsed_enforce = _time_ms(enforce_length, response, lead_message)
        assert (
            elapsed_enforce < 10
        ), f"enforce_length took {elapsed_enforce:.1f}ms (expected < 10ms)"

    def test_respuesta_consistente(self):
        """Multiple calls to the same function produce similar timing.

        Runs classify_intent_simple 20 times and verifies the standard
        deviation is small relative to the mean, confirming no sporadic
        blocking or warm-up penalties.
        """
        message = "Me interesa el taller de Instagram, cuanto cuesta?"
        timings = []

        for _ in range(20):
            _, elapsed = _time_ms(classify_intent_simple, message)
            timings.append(elapsed)

        mean_ms = sum(timings) / len(timings)
        max_ms = max(timings)

        # No single call should be more than 10x the mean (relaxed for sub-ms)
        assert max_ms < max(
            mean_ms * 10, 1.0
        ), f"Inconsistent timing: max={max_ms:.2f}ms vs mean={mean_ms:.2f}ms"
        # Mean should be well under 5ms for keyword matching
        assert mean_ms < 5, f"Mean timing {mean_ms:.2f}ms exceeds 5ms budget"

    def test_sin_retrasos_largos(self):
        """No blocking operations in non-LLM pipeline stages.

        Runs the full non-LLM pipeline (detect_all + classify_lead_context +
        get_context_rule + frustration detection + sarcasm detection) for
        several messages and verifies none exceed 50ms individually.
        """
        messages = [
            "Hola, buenos dias!",
            "Ya te lo dije tres veces, no entiendes",
            "Ajá, seguro que si, que gracioso",
            "Les escribe Silvia de Bamos, ya habiamos trabajado antes",
            "Quiero comprar el curso ya, como pago?",
            "",  # edge case: empty message
        ]

        for msg in messages:
            start = time.perf_counter()

            detect_all(msg, history=None, is_first_message=True)
            classify_lead_context(msg)
            ctx_name = classify_lead_context(msg)
            get_context_rule(ctx_name)
            detect_frustration(msg)
            detect_sarcasm(msg)

            elapsed_ms = (time.perf_counter() - start) * 1000
            assert elapsed_ms < 50, (
                f"Full non-LLM pipeline for '{msg[:40]}...' took "
                f"{elapsed_ms:.1f}ms (expected < 50ms)"
            )
