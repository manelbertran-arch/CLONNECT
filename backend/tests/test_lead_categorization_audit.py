"""Audit tests for core/lead_categorization.py."""

from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Test 1: Init / Import
# ---------------------------------------------------------------------------


class TestLeadCategorizationImport:
    """Verify module imports and key exports."""

    def test_import_module(self):
        from core.lead_categorization import (
            CATEGORIAS_CONFIG,
            KEYWORDS_CALIENTE,
            KEYWORDS_INTERESADO,
            CategorizationResult,
        )

        # CategorizationResult should be a dataclass
        result = CategorizationResult(
            categoria="nuevo",
            intent_score=0.1,
            razones=["test"],
            keywords_detectados=[],
        )
        assert result.categoria == "nuevo"
        assert result.intent_score == 0.1

        # Keyword lists should be non-empty
        assert len(KEYWORDS_CALIENTE) > 0
        assert len(KEYWORDS_INTERESADO) > 0

        # Config should have all 5 categories
        assert set(CATEGORIAS_CONFIG.keys()) == {
            "nuevo",
            "interesado",
            "caliente",
            "cliente",
            "fantasma",
        }


# ---------------------------------------------------------------------------
# Test 2: Happy Path -- Status transition rules
# ---------------------------------------------------------------------------


class TestStatusTransitionRules:
    """Verify correct categorization for clear-cut scenarios."""

    def test_cliente_has_max_priority(self):
        """A confirmed customer should always be 'cliente' regardless of messages."""
        from core.lead_categorization import calcular_categoria

        mensajes = [
            {"role": "user", "content": "Hola quiero comprar el curso"},
            {"role": "assistant", "content": "Claro!"},
        ]
        result = calcular_categoria(mensajes=mensajes, es_cliente=True)
        assert result.categoria == "cliente"
        assert result.intent_score == 1.0

    def test_caliente_when_price_asked(self):
        """User asking about price should be categorized as 'caliente'."""
        from core.lead_categorization import calcular_categoria

        mensajes = [
            {"role": "user", "content": "Cuanto cuesta el programa?"},
        ]
        result = calcular_categoria(mensajes=mensajes)
        assert result.categoria == "caliente"
        assert result.intent_score >= 0.5

    def test_interesado_with_interest_keywords(self):
        """User showing curiosity should be 'interesado'."""
        from core.lead_categorization import calcular_categoria

        mensajes = [
            {"role": "user", "content": "Me interesa, dame mas detalles de tus servicios"},
        ]
        result = calcular_categoria(mensajes=mensajes)
        assert result.categoria == "interesado"
        assert 0.0 < result.intent_score < 0.5

    def test_nuevo_with_generic_message(self):
        """Generic greeting should be 'nuevo'."""
        from core.lead_categorization import calcular_categoria

        mensajes = [
            {"role": "user", "content": "Hola"},
        ]
        result = calcular_categoria(mensajes=mensajes)
        assert result.categoria == "nuevo"
        assert result.intent_score == 0.1

    def test_legacy_status_mapping(self):
        """Legacy status mapping should be bidirectional."""
        from core.lead_categorization import categoria_a_status_legacy, status_legacy_a_categoria

        pairs = [
            ("nuevo", "new"),
            ("interesado", "active"),
            ("caliente", "hot"),
            ("cliente", "customer"),
            ("fantasma", "ghost"),
        ]
        for cat, legacy in pairs:
            assert categoria_a_status_legacy(cat) == legacy
            assert status_legacy_a_categoria(legacy) == cat


# ---------------------------------------------------------------------------
# Test 3: Edge Case -- Invalid status and empty inputs
# ---------------------------------------------------------------------------


class TestCategorizationEdgeCases:
    """Edge cases: empty messages, unknown statuses, non-string input."""

    def test_no_messages_returns_nuevo(self):
        from core.lead_categorization import calcular_categoria

        result = calcular_categoria(mensajes=[])
        assert result.categoria == "nuevo"
        assert "Sin mensajes del usuario" in result.razones[0]

    def test_unknown_legacy_status_defaults(self):
        from core.lead_categorization import categoria_a_status_legacy, status_legacy_a_categoria

        assert categoria_a_status_legacy("invented_status") == "new"
        assert status_legacy_a_categoria("invented_status") == "nuevo"

    def test_detectar_keywords_with_non_string_input(self):
        """detectar_keywords should handle dict or None gracefully."""
        from core.lead_categorization import detectar_keywords

        # Dict input
        result = detectar_keywords({"text": "precio"}, ["precio"])
        assert "precio" in result

        # None input
        result_none = detectar_keywords(None, ["precio"])
        assert isinstance(result_none, list)


# ---------------------------------------------------------------------------
# Test 4: Error Handling -- Fantasma detection
# ---------------------------------------------------------------------------


class TestFantasmaDetection:
    """Ghost lead detection based on time thresholds."""

    def test_fantasma_after_7_days_no_reply(self):
        """Lead should be 'fantasma' if last user message was 8+ days ago
        and last message is from assistant."""
        from core.lead_categorization import calcular_categoria

        old_date = datetime.now(timezone.utc) - timedelta(days=10)
        mensajes = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola! Como te puedo ayudar?"},
        ]
        result = calcular_categoria(
            mensajes=mensajes,
            ultimo_mensaje_lead=old_date,
        )
        assert result.categoria == "fantasma"
        assert result.intent_score <= 0.2

    def test_not_fantasma_if_recent(self):
        """Lead with recent activity should NOT be fantasma."""
        from core.lead_categorization import calcular_categoria

        recent_date = datetime.now(timezone.utc) - timedelta(days=1)
        mensajes = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola!"},
        ]
        result = calcular_categoria(
            mensajes=mensajes,
            ultimo_mensaje_lead=recent_date,
        )
        assert result.categoria != "fantasma"

    def test_fantasma_no_messages_old_creation(self):
        """Lead with zero user messages created >7 days ago is fantasma."""
        from core.lead_categorization import calcular_categoria

        old_creation = datetime.now(timezone.utc) - timedelta(days=14)
        result = calcular_categoria(
            mensajes=[],
            lead_created_at=old_creation,
        )
        assert result.categoria == "fantasma"


# ---------------------------------------------------------------------------
# Test 5: Integration Check -- Score calculation and config lookup
# ---------------------------------------------------------------------------


class TestScoreCalculation:
    """Verify intent_score ranges and config helper."""

    def test_caliente_score_increases_with_signals(self):
        """More purchase signals should yield a higher intent score."""
        from core.lead_categorization import calcular_categoria

        # Single signal
        msgs_single = [
            {"role": "user", "content": "Cuanto cuesta?"},
        ]
        r1 = calcular_categoria(mensajes=msgs_single)

        # Multiple signals
        msgs_multi = [
            {
                "role": "user",
                "content": "Quiero comprar, cuanto cuesta? dame el link de pago y el calendario",
            },
        ]
        r2 = calcular_categoria(mensajes=msgs_multi)

        assert r2.intent_score >= r1.intent_score
        assert r2.intent_score <= 1.0

    def test_interesado_score_capped_below_half(self):
        """Interesado intent_score must never reach 0.5 (caliente territory)."""
        from core.lead_categorization import calcular_categoria

        msgs = [
            {"role": "user", "content": "Dame mas informacion y detalles"},
            {"role": "user", "content": "Que servicios ofreces"},
            {"role": "user", "content": "Cuentame mas opciones"},
            {"role": "user", "content": "Que productos tienes"},
            {"role": "user", "content": "Explicame como funciona"},
            {"role": "user", "content": "Mas detalles por favor"},
        ]
        result = calcular_categoria(mensajes=msgs)
        assert result.categoria == "interesado"
        assert result.intent_score <= 0.49

    def test_get_categoria_config_returns_dict(self):
        """get_categoria_config should return config for known and unknown categories."""
        from core.lead_categorization import get_categoria_config

        config = get_categoria_config("caliente")
        assert "color" in config
        assert "label" in config
        assert config["priority"] == 1  # highest

        # Unknown category falls back to "nuevo"
        fallback = get_categoria_config("xyz")
        assert fallback["label"] == "Nuevo"
