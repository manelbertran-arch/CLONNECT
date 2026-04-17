"""
Category 4 - DIALOGO MULTI-TURNO: Escalation Handling Tests

Tests that the system correctly detects and handles escalation scenarios:
crisis/self-harm, high frustration, explicit human-agent requests, and
that normal conversations do NOT trigger false escalations.

All tests are FAST: no LLM calls, no DB.

Note: detect_frustration from core.context_detector is now a STUB that
always returns FrustrationResult(is_frustrated=False). Production frustration
detection uses FrustrationDetector from core.frustration_detector.
"""

from core.frustration_detector import FrustrationDetector
from core.intent_classifier import Intent, IntentClassifier
from core.sensitive_detector import SensitiveType, detect_sensitive_content, get_crisis_resources

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEscalacion:
    """Escalation handling for crisis, frustration, and human requests."""

    def test_escala_crisis(self):
        """Self-harm message triggers SELF_HARM detection with high confidence.

        The sensitive content detector must identify suicidal ideation
        and return a result with type SELF_HARM, high confidence, and
        immediate escalation action.
        """
        crisis_messages = [
            "No quiero vivir mas",
            "Pienso en suicidarme",
            "Quiero desaparecer de este mundo",
            "Me hago dano a mi misma",
        ]

        for msg in crisis_messages:
            result = detect_sensitive_content(msg)
            assert (
                result.type == SensitiveType.SELF_HARM
            ), f"Expected SELF_HARM for '{msg}', got {result.type}"
            assert (
                result.confidence >= 0.9
            ), f"Expected confidence >= 0.9 for '{msg}', got {result.confidence}"
            assert result.action_required == "escalate_immediate"

    def test_escala_queja_grave(self):
        """High frustration triggers escalation-level signals.

        When the user expresses severe frustration (explicit insults,
        demanding to talk to a human), the FrustrationDetector should
        return a high score and explicit_frustration=True, which the
        system uses to flag for escalation.
        """
        detector = FrustrationDetector()

        # Messages with language-agnostic frustration signals:
        # - explicit count ("5 veces") → COUNT_RE
        # - escalation pattern ("quiero hablar con alguien real")
        # - frustration emoji 😡
        # Note: pure keyword insults ("Eres inutil") without para-linguistic signals
        # are no longer detected — v3 is language-agnostic, not keyword-based.
        # v3 is language-agnostic: CAPS + punctuation burst + COUNT_RE each add weight.
        # Three or more language-agnostic signals → level >= 2.
        severe_messages = [
            # all-CAPS + punctuation burst + COUNT_RE → 0.15+0.15+0.30 = 0.60 → level 2
            "NO FUNCIONA!!! YA TE LO DIJE 5 VECES",
            # escalation pattern → level = 3 (forced)
            "No me ayudas nada, quiero hablar con alguien real",
            # all-CAPS + COUNT_RE + punctuation burst → level >= 2
            "NO ME AYUDAS, 3 VECES TE LO DIJE!!!",
        ]

        for msg in severe_messages:
            signals, score = detector.analyze_message(msg, conversation_id="test_conv")
            # Severe frustration should produce high level (>=2) and score (>=0.3)
            # Note: explicit_frustration only fires for "explicit" signal type patterns,
            # not for repetition+failure combos which still produce high levels.
            assert signals.level >= 2, (
                f"Expected frustration level >= 2 for '{msg}', got level={signals.level}"
            )
            assert score >= 0.3, f"Expected score >= 0.3 for '{msg}', got {score}"

    def test_escala_solicitud_humano(self):
        """'Quiero hablar con una persona' is detected as human request.

        The intent classifier (via quick patterns) should identify
        escalation-type messages requesting a human agent.
        """
        human_request_messages = [
            "Quiero hablar con una persona real",
            "Pasame con un humano",
            "Eres un bot? Quiero hablar con alguien",
            "Quiero hablar con un humano de verdad",
            "Prefiero hablar con un operador",
        ]

        classifier = IntentClassifier(llm_client=None)

        for msg in human_request_messages:
            result = classifier._quick_classify(msg)
            assert result is not None, f"Expected quick classification for '{msg}'"
            assert (
                result.intent == Intent.ESCALATION
            ), f"Expected ESCALATION for '{msg}', got {result.intent}"
            assert result.confidence >= 0.8

    def test_no_escala_innecesariamente(self):
        """Normal conversation does not trigger escalation flags.

        Polite greetings, product questions, and positive feedback should
        NOT be flagged as frustration, self-harm, or escalation requests.
        """
        normal_messages = [
            "Hola, me interesa tu curso",
            "Cuanto cuesta el programa?",
            "Gracias por la informacion!",
            "Suena genial, cuentame mas",
            "Me lo voy a pensar",
        ]

        detector = FrustrationDetector()

        for msg in normal_messages:
            # Sensitive detector should return NONE
            sensitive = detect_sensitive_content(msg)
            assert (
                sensitive.type == SensitiveType.NONE
            ), f"Unexpected sensitive detection for '{msg}': {sensitive.type}"

            # Frustration should be low via FrustrationDetector
            signals, score = detector.analyze_message(msg, conversation_id=f"normal_{msg[:10]}")
            assert signals.explicit_frustration is False, f"Unexpected frustration for '{msg}'"
            assert signals.level == 0, (
                f"Unexpected frustration level for '{msg}': level={signals.level}"
            )

    def test_mensaje_escalacion_correcto(self):
        """Crisis resources include verified phone numbers for immediate help.

        Contract reflects the 2026-04-17 hotline update (BUG-S3):
          * ES primary line is 024 (Ministerio de Sanidad).
          * CA resources lead with 900 925 555 (Telèfon de Prevenció del
            Suïcidi, Barcelona) and include 024 as national backup.
          * EN uses Samaritans 116 123 (UK/ROI) — US-only 988/741741 dropped
            because the backend serves creators in Spain by default.
        See `docs/safety/self_harm_guardrail.md` for verified source list.
        """
        # Spanish resources
        resources_es = get_crisis_resources("es")
        assert "717 003 717" in resources_es, "Missing Telefono de la Esperanza"
        assert "024" in resources_es, "Missing linea 024"
        assert "900 107 917" in resources_es, "Missing Cruz Roja Escucha"

        # English resources — Samaritans replaces US-only lines.
        resources_en = get_crisis_resources("en")
        assert "116 123" in resources_en, "Missing Samaritans"
        assert "Samaritans" in resources_en, "Missing Samaritans label"

        # Catalan resources — regional (900 925 555) + national (024).
        resources_ca = get_crisis_resources("ca")
        assert "900 925 555" in resources_ca, "Missing Barcelona regional hotline"
        assert "024" in resources_ca, "Missing national Catalan suicide line"

        # Unknown language should fall back to Spanish.
        resources_unknown = get_crisis_resources("xx")
        assert "024" in resources_unknown, "Fallback should use Spanish (024)"
