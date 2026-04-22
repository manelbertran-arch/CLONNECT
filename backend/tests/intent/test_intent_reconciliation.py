"""
Tests for fix/intent-dual-reconciliation.

Verifies that:
1. services.IntentClassifier (canonical) returns expected values for key messages.
2. classify_intent_simple() remains callable (backward compat) and emits deprecation log.
3. svc_to_core_intent() maps canonical → core intent correctly (Tabla B).
4. detect_all() wires canonical intent into DetectedContext coherently.
5. sensitive_action_required originates from ContextBundle, not from IntentClassifier.
6. CASUAL short-message bug is present (unresolved, tracked in docs/bugs/).
"""

import logging

import pytest

from core.context_detector import detect_all
from core.context_detector.intent_mapping import SVC_TO_CORE_INTENT, svc_to_core_intent
from core.intent_classifier import Intent as CoreIntent
from core.intent_classifier import classify_intent_simple
from services.intent_service import Intent as SvcIntent
from services.intent_service import IntentClassifier as CanonicalClassifier


# ---------------------------------------------------------------------------
# 1. Canonical classifier — direct output for key message types
# ---------------------------------------------------------------------------

class TestCanonicalClassifierDirect:
    """services.IntentClassifier.classify() returns expected Intent for known messages."""

    def setup_method(self):
        self.clf = CanonicalClassifier()

    def test_greeting(self):
        assert self.clf.classify("Hola, qué tal") == SvcIntent.GREETING

    def test_product_question(self):
        intent = self.clf.classify("¿Qué incluye el FitPack Challenge?")
        assert intent in (SvcIntent.QUESTION_PRODUCT, SvcIntent.PRODUCT_QUESTION)

    def test_purchase_intent(self):
        intent = self.clf.classify("Quiero comprar el curso, ¿cómo pago?")
        assert intent == SvcIntent.PURCHASE_INTENT

    def test_objection_price(self):
        intent = self.clf.classify("Es muy caro para mí, no puedo pagarlo")
        assert intent == SvcIntent.OBJECTION_PRICE

    def test_objection_time(self):
        intent = self.clf.classify("No tengo tiempo ahora mismo")
        assert intent == SvcIntent.OBJECTION_TIME

    def test_pricing_question(self):
        intent = self.clf.classify("¿Cuánto cuesta el FitPack?")
        assert intent == SvcIntent.PRICING

    def test_interest_strong(self):
        intent = self.clf.classify("Me interesa mucho, cuéntame más")
        assert intent == SvcIntent.INTEREST_STRONG

    def test_escalation(self):
        intent = self.clf.classify("Quiero hablar con una persona real")
        assert intent == SvcIntent.ESCALATION


# ---------------------------------------------------------------------------
# 2. classify_intent_simple — backward compat + deprecation warning
# ---------------------------------------------------------------------------

class TestClassifyIntentSimpleBackwardCompat:
    """classify_intent_simple() is callable, returns valid string, logs deprecation."""

    def test_still_callable_greeting(self):
        result = classify_intent_simple("Hola, qué tal")
        assert result == "greeting"

    def test_still_callable_purchase(self):
        result = classify_intent_simple("Quiero comprar el curso")
        assert result == "interest_strong"

    def test_still_callable_objection(self):
        result = classify_intent_simple("Es muy caro para mí")
        assert result == "objection"

    def test_still_callable_support(self):
        result = classify_intent_simple("Tengo un problema con el acceso")
        assert result == "support"

    def test_returns_valid_legacy_string(self):
        valid = {"interest_strong", "purchase", "interest_soft",
                 "question_product", "objection", "greeting", "support", "other"}
        for msg in [
            "Hola", "Quiero comprar", "Me interesa", "Es muy caro",
            "¿Qué incluye?", "No puedo acceder", "Gracias"
        ]:
            result = classify_intent_simple(msg)
            assert result in valid, f"Unexpected result {result!r} for {msg!r}"

    def test_emits_deprecation_log(self, caplog):
        import core.intent_classifier as _mod
        # Reset the warned flag so the warning fires in this isolated test.
        original = _mod._classify_intent_simple_warned
        _mod._classify_intent_simple_warned = False
        try:
            with caplog.at_level(logging.WARNING, logger="core.intent_classifier"):
                classify_intent_simple("test message")
            assert any(
                "DEPRECATED" in r.message and "classify_intent_simple" in r.message
                for r in caplog.records
            ), "Expected DEPRECATED warning was not emitted"
        finally:
            _mod._classify_intent_simple_warned = original

    def test_emits_once_per_process(self, caplog):
        """After the first call, no duplicate warnings are emitted."""
        import core.intent_classifier as _mod
        _mod._classify_intent_simple_warned = False
        try:
            with caplog.at_level(logging.WARNING, logger="core.intent_classifier"):
                classify_intent_simple("first call")
                classify_intent_simple("second call")
                classify_intent_simple("third call")
            deprecated_records = [
                r for r in caplog.records
                if "DEPRECATED" in r.message and "classify_intent_simple" in r.message
            ]
            assert len(deprecated_records) == 1, (
                f"Expected exactly 1 DEPRECATED warning, got {len(deprecated_records)}"
            )
        finally:
            _mod._classify_intent_simple_warned = True


# ---------------------------------------------------------------------------
# 3. Tabla B mapping — svc_to_core_intent
# ---------------------------------------------------------------------------

class TestTablaB:
    """svc_to_core_intent() maps canonical SvcIntent to CoreIntent correctly."""

    def test_purchase_intent_maps_to_interest_strong(self):
        assert svc_to_core_intent(SvcIntent.PURCHASE_INTENT) == CoreIntent.INTEREST_STRONG

    def test_pricing_maps_to_interest_strong(self):
        assert svc_to_core_intent(SvcIntent.PRICING) == CoreIntent.INTEREST_STRONG

    def test_booking_maps_to_interest_strong(self):
        assert svc_to_core_intent(SvcIntent.BOOKING) == CoreIntent.INTEREST_STRONG

    def test_interest_soft_maps_to_interest_soft(self):
        assert svc_to_core_intent(SvcIntent.INTEREST_SOFT) == CoreIntent.INTEREST_SOFT

    def test_lead_magnet_maps_to_interest_soft(self):
        assert svc_to_core_intent(SvcIntent.LEAD_MAGNET) == CoreIntent.INTEREST_SOFT

    def test_all_objection_subtypes_map_to_objection(self):
        objection_intents = [
            SvcIntent.OBJECTION_PRICE,
            SvcIntent.OBJECTION_TIME,
            SvcIntent.OBJECTION_DOUBT,
            SvcIntent.OBJECTION_LATER,
            SvcIntent.OBJECTION_WORKS,
            SvcIntent.OBJECTION_NOT_FOR_ME,
            SvcIntent.OBJECTION_COMPLICATED,
            SvcIntent.OBJECTION_ALREADY_HAVE,
        ]
        for svc_intent in objection_intents:
            assert svc_to_core_intent(svc_intent) == CoreIntent.OBJECTION, (
                f"{svc_intent} should map to CoreIntent.OBJECTION"
            )

    def test_escalation_maps_to_escalation(self):
        assert svc_to_core_intent(SvcIntent.ESCALATION) == CoreIntent.ESCALATION

    def test_greeting_maps_to_greeting(self):
        assert svc_to_core_intent(SvcIntent.GREETING) == CoreIntent.GREETING

    def test_casual_maps_to_other(self):
        assert svc_to_core_intent(SvcIntent.CASUAL) == CoreIntent.OTHER

    def test_all_svc_intents_covered(self):
        """Every SvcIntent value has an entry in Tabla B (no KeyError via .get fallback)."""
        for svc_intent in SvcIntent:
            result = svc_to_core_intent(svc_intent)
            assert isinstance(result, CoreIntent), (
                f"svc_to_core_intent({svc_intent}) returned non-CoreIntent: {result!r}"
            )


# ---------------------------------------------------------------------------
# 4. detect_all — canonical intent wired end-to-end
# ---------------------------------------------------------------------------

class TestDetectAllCanonicalWiring:
    """detect_all() uses canonical classifier and populates DetectedContext correctly."""

    def test_greeting_context(self):
        ctx = detect_all("Hola, qué tal")
        assert ctx.intent == CoreIntent.GREETING
        assert ctx.interest_level == "none"

    def test_purchase_strong_interest(self):
        ctx = detect_all("Quiero comprar el FitPack, ¿cómo pago?")
        assert ctx.intent == CoreIntent.INTEREST_STRONG
        assert ctx.interest_level == "strong"

    def test_pricing_strong_interest(self):
        ctx = detect_all("¿Cuánto cuesta el curso?")
        assert ctx.intent == CoreIntent.INTEREST_STRONG
        assert ctx.interest_level == "strong"

    def test_objection_price_detection(self):
        ctx = detect_all("Es muy caro para mí, no puedo pagarlo")
        assert ctx.intent == CoreIntent.OBJECTION
        assert ctx.objection_type == "price"

    def test_objection_time_detection(self):
        ctx = detect_all("No tengo tiempo ahora mismo para esto")
        assert ctx.intent == CoreIntent.OBJECTION
        assert ctx.objection_type == "time"

    def test_escalation_detected(self):
        ctx = detect_all("Quiero hablar con una persona real, no con un bot")
        assert ctx.intent == CoreIntent.ESCALATION

    def test_intent_sub_is_granular_svc_value(self):
        """intent_sub holds the granular svc value (e.g. 'objection_price'), not the core bucket."""
        ctx = detect_all("Es muy caro para mí")
        assert ctx.intent_sub == SvcIntent.OBJECTION_PRICE.value


# ---------------------------------------------------------------------------
# 5. sensitive_action_required — NOT from IntentClassifier
# ---------------------------------------------------------------------------

class TestSensitiveActionOrigin:
    """
    sensitive_action_required is set by ContextBundle from SensitiveDetector,
    not by IntentClassifier. Verifies the classifier never produces this value.
    """

    def test_canonical_classifier_never_returns_sensitive(self):
        clf = CanonicalClassifier()
        sensitive_messages = [
            "Quiero hacer un pago",
            "Dame mi contraseña",
            "Necesito tu número de cuenta",
            "quiero cancelar mi suscripción",
        ]
        for msg in sensitive_messages:
            intent = clf.classify(msg)
            assert intent != "sensitive_action_required", (
                f"Classifier must not return 'sensitive_action_required': got {intent!r} for {msg!r}"
            )
            # Verify it's always a valid SvcIntent member
            assert isinstance(intent, SvcIntent), (
                f"Expected SvcIntent, got {type(intent).__name__} for {msg!r}"
            )

    def test_detect_all_has_no_sensitive_attribute(self):
        ctx = detect_all("Quiero hacer un pago ahora")
        # DetectedContext has no sensitive_action_required field — it lives in ContextBundle
        assert not hasattr(ctx, "sensitive_action_required"), (
            "sensitive_action_required must NOT be added to DetectedContext "
            "(belongs to ContextBundle from SensitiveDetector)"
        )


# ---------------------------------------------------------------------------
# 6. CASUAL bug — documented regression, must NOT be silently fixed
# ---------------------------------------------------------------------------

class TestCasualBugPresent:
    """
    Documents the known CASUAL short-message bug in services.IntentClassifier.
    These assertions confirm the bug is STILL present.
    If any of these start PASSING (returning the expected intent), the bug has been
    fixed and the test should be updated accordingly.
    See: docs/bugs/intent_classifier_casual_short_msg.md
    """

    def setup_method(self):
        self.clf = CanonicalClassifier()

    @pytest.mark.xfail(
        reason="CASUAL bug: len(msg)<15 stomps support intent — docs/bugs/intent_classifier_casual_short_msg.md",
        strict=True,
    )
    def test_no_funciona_classified_as_support(self):
        assert self.clf.classify("no funciona") == SvcIntent.SUPPORT

    @pytest.mark.xfail(
        reason="CASUAL bug: len(msg)<15 stomps interest_soft intent",
        strict=True,
    )
    def test_me_interesa_classified_as_interest_soft(self):
        assert self.clf.classify("me interesa") == SvcIntent.INTEREST_SOFT

    @pytest.mark.xfail(
        reason="CASUAL bug: len(msg)<15 stomps objection intent",
        strict=True,
    )
    def test_ahora_no_classified_as_objection_time(self):
        assert self.clf.classify("ahora no") == SvcIntent.OBJECTION_TIME
