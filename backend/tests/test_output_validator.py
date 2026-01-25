"""
Tests for core/output_validator.py

Tests the Output Validator module that validates LLM responses
before sending to prevent hallucinations.

Part of refactor/context-injection-v2
"""

import pytest

from core.context_detector import DetectedContext
from core.creator_data_loader import (
    BookingInfo,
    CreatorData,
    CreatorProfile,
    ProductInfo,
)
from core.intent_classifier import Intent
from core.output_validator import (
    ValidationIssue,
    ValidationResult,
    extract_prices_from_text,
    extract_urls_from_text,
    get_safe_response,
    quick_validate,
    smart_truncate,
    validate_links,
    validate_prices,
    validate_products,
    validate_response,
    verify_action_completed,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_creator_data():
    """Create sample creator data for testing."""
    data = CreatorData(creator_id="test_creator")
    data.profile = CreatorProfile(
        id="test_creator",
        name="Stefano",
    )
    data.products = [
        ProductInfo(
            id="1",
            name="FitPack Challenge",
            price=297.0,
            payment_link="https://pay.hotmart.com/fitpack123",
        ),
        ProductInfo(
            id="2",
            name="Mentoria Premium",
            price=497.0,
            payment_link="https://pay.hotmart.com/mentoria456",
        ),
    ]
    data.booking_links = [
        BookingInfo(
            id="1",
            meeting_type="discovery",
            title="Discovery Call",
            duration_minutes=30,
            price=0,
            url="https://calendly.com/stefano/discovery",
        ),
    ]
    data.lead_magnets = [
        ProductInfo(
            id="3",
            name="Guia Gratuita",
            price=0.0,
            is_free=True,
            payment_link="https://example.com/guia-gratis",
        ),
    ]
    return data


@pytest.fixture
def sample_detected_context():
    """Create sample detected context."""
    return DetectedContext(
        intent=Intent.INTEREST_STRONG,
        interest_level="strong",
    )


# =============================================================================
# TEST VALIDATION ISSUE AND RESULT
# =============================================================================


class TestValidationIssue:
    """Tests for ValidationIssue dataclass."""

    def test_validation_issue_creation(self):
        issue = ValidationIssue(
            type="hallucinated_price",
            severity="error",
            details="Price 450€ not found",
        )
        assert issue.type == "hallucinated_price"
        assert issue.severity == "error"
        assert issue.auto_fix is None

    def test_validation_issue_to_dict(self):
        issue = ValidationIssue(
            type="missing_link",
            severity="warning",
            details="No booking link",
            auto_fix="Added link",
        )
        d = issue.to_dict()
        assert d["type"] == "missing_link"
        assert d["auto_fix"] == "Added link"


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_validation_result_defaults(self):
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.issues == []
        assert result.should_escalate is False

    def test_add_issue_error(self):
        result = ValidationResult(is_valid=True)
        result.add_issue("test_error", "error", "Test error")
        assert result.is_valid is False
        assert len(result.issues) == 1

    def test_add_issue_warning(self):
        result = ValidationResult(is_valid=True)
        result.add_issue("test_warning", "warning", "Test warning")
        assert result.is_valid is True  # Warnings don't fail validation
        assert len(result.issues) == 1


# =============================================================================
# TEST PRICE EXTRACTION AND VALIDATION
# =============================================================================


class TestExtractPrices:
    """Tests for extract_prices_from_text."""

    def test_extract_price_euro_symbol(self):
        prices = extract_prices_from_text("El curso cuesta 297€")
        assert len(prices) == 1
        assert prices[0][1] == 297.0

    def test_extract_price_euro_word(self):
        prices = extract_prices_from_text("Son 150 euros")
        assert len(prices) == 1
        assert prices[0][1] == 150.0

    def test_extract_price_with_decimals(self):
        prices = extract_prices_from_text("Precio: 99.90€")
        assert len(prices) == 1
        assert prices[0][1] == 99.90

    def test_extract_price_comma_decimal(self):
        prices = extract_prices_from_text("Cuesta 49,99€")
        assert len(prices) == 1
        assert prices[0][1] == 49.99

    def test_extract_multiple_prices(self):
        prices = extract_prices_from_text("El básico 97€ y el premium 297€")
        assert len(prices) == 2

    def test_extract_no_prices(self):
        prices = extract_prices_from_text("Hola, ¿cómo estás?")
        assert len(prices) == 0


class TestValidatePrices:
    """Tests for validate_prices function."""

    def test_valid_price(self):
        known_prices = {"fitpack": 297.0}
        issues = validate_prices("El curso cuesta 297€", known_prices)
        assert len(issues) == 0

    def test_valid_price_with_tolerance(self):
        """Price within ±1€ tolerance should pass."""
        known_prices = {"fitpack": 297.0}
        issues = validate_prices("Son 298€", known_prices, tolerance=1.0)
        assert len(issues) == 0

    def test_hallucinated_price(self):
        """
        CRITICAL TEST #1: Hallucinated price should be detected.

        Response: "El retiro cuesta 450€"
        known_prices: {"fitpack": 297}
        Expected: is_valid=False, issue="hallucinated_price"
        """
        known_prices = {"fitpack": 297.0}
        issues = validate_prices("El retiro cuesta 450€", known_prices)

        assert len(issues) == 1
        assert issues[0].type == "hallucinated_price"
        assert issues[0].severity == "error"
        assert "450" in issues[0].details

    def test_multiple_prices_one_hallucinated(self):
        known_prices = {"basic": 97.0, "premium": 297.0}
        issues = validate_prices("El básico 97€ y el VIP 599€", known_prices)
        assert len(issues) == 1
        assert "599" in issues[0].details

    def test_no_known_prices_skips_validation(self):
        issues = validate_prices("El curso cuesta 999€", {})
        assert len(issues) == 0


# =============================================================================
# TEST URL EXTRACTION AND VALIDATION
# =============================================================================


class TestExtractUrls:
    """Tests for extract_urls_from_text."""

    def test_extract_https_url(self):
        urls = extract_urls_from_text("Link: https://example.com/page")
        assert len(urls) == 1
        assert "example.com" in urls[0]

    def test_extract_http_url(self):
        urls = extract_urls_from_text("Link: http://test.com")
        assert len(urls) == 1

    def test_extract_url_with_path(self):
        urls = extract_urls_from_text("https://pay.hotmart.com/fitpack123")
        assert len(urls) == 1
        assert "fitpack123" in urls[0]

    def test_extract_no_urls(self):
        urls = extract_urls_from_text("No hay enlaces aquí")
        assert len(urls) == 0


class TestValidateLinks:
    """Tests for validate_links function."""

    def test_valid_known_link(self):
        known_links = ["https://pay.hotmart.com/real"]
        issues, corrected = validate_links(
            "Compra aquí: https://pay.hotmart.com/real",
            known_links,
        )
        assert len(issues) == 0
        assert corrected == "Compra aquí: https://pay.hotmart.com/real"

    def test_valid_allowed_domain(self):
        """Links from allowed domains should pass."""
        known_links = []
        issues, _ = validate_links(
            "Reserva: https://calendly.com/test",
            known_links,
        )
        assert len(issues) == 0

    def test_hallucinated_link(self):
        """
        CRITICAL TEST #2: Hallucinated link should be detected.

        Response: "Compra aquí: https://fake-link.com"
        known_links: ["https://pay.hotmart.com/real"]
        Expected: Link removed or error flagged
        """
        known_links = ["https://pay.hotmart.com/real"]
        issues, corrected = validate_links(
            "Compra aquí: https://fake-link.com",
            known_links,
        )

        assert len(issues) == 1
        assert issues[0].type == "hallucinated_link"
        assert "fake-link.com" not in corrected
        assert "[enlace removido]" in corrected

    def test_multiple_links_one_hallucinated(self):
        known_links = ["https://pay.hotmart.com/real"]
        issues, corrected = validate_links(
            "Real: https://pay.hotmart.com/real Fake: https://scam.com/bad",
            known_links,
        )
        assert len(issues) == 1
        assert "pay.hotmart.com" in corrected
        assert "scam.com" not in corrected


# =============================================================================
# TEST PRODUCT VALIDATION
# =============================================================================


class TestValidateProducts:
    """Tests for validate_products function."""

    def test_known_product(self):
        products = ["FitPack Challenge", "Mentoria Premium"]
        issues = validate_products(
            "El curso FitPack Challenge es genial",
            products,
        )
        assert len(issues) == 0

    def test_unknown_product_warning(self):
        products = ["FitPack Challenge"]
        issues = validate_products(
            'El programa "Retiro Bali" cuesta 500€',
            products,
        )
        # Should be a warning (soft check)
        if issues:
            assert issues[0].severity == "warning"


# =============================================================================
# TEST ACTION VERIFICATION
# =============================================================================


class TestVerifyActionCompleted:
    """Tests for verify_action_completed function."""

    def test_missing_booking_link_auto_added(self, sample_creator_data):
        """
        CRITICAL TEST #3: Missing link should be auto-added.

        Intent: BOOKING (strong interest)
        Response: "¡Perfecto! Te espero en la sesión"
        Expected: auto_fix adds booking link
        """
        ctx = DetectedContext(intent=Intent.INTEREST_STRONG, interest_level="strong")
        response = "¡Perfecto! Te espero en la sesión de descubrimiento"

        issues, corrected = verify_action_completed(
            response, ctx, sample_creator_data
        )

        # Should have added booking link
        assert "calendly.com" in corrected
        assert len(issues) >= 1
        assert any(i.type == "missing_link" for i in issues)

    def test_link_already_present(self, sample_creator_data):
        """If link already present, don't add another."""
        ctx = DetectedContext(intent=Intent.INTEREST_STRONG, interest_level="strong")
        response = "Reserva aquí: https://calendly.com/stefano/discovery"

        issues, corrected = verify_action_completed(
            response, ctx, sample_creator_data
        )

        # Should not add another link
        assert corrected.count("https://") == 1


# =============================================================================
# TEST SMART TRUNCATE
# =============================================================================


class TestSmartTruncate:
    """Tests for smart_truncate function."""

    def test_short_response_not_truncated(self):
        response = "Hola, el precio es 297€"
        result, was_truncated = smart_truncate(response, max_chars=400)
        assert result == response
        assert was_truncated is False

    def test_truncate_with_url_protected(self):
        """
        CRITICAL TEST #4: Response with URL should NOT be truncated.

        Response: "El curso cuesta 297€. Incluye 8 semanas. Link: https://pay.hotmart.com/fitpack"
        Expected: NOT truncated (has URL and €)
        """
        response = (
            "El curso cuesta 297€. Incluye 8 semanas de contenido premium. "
            "Tendrás acceso a la comunidad privada. "
            "Link: https://pay.hotmart.com/fitpack y mucho más contenido."
        )
        result, was_truncated = smart_truncate(response, max_chars=100)

        # Should NOT truncate because it contains URL
        assert "https://pay.hotmart.com" in result
        assert was_truncated is False

    def test_truncate_with_price_protected(self):
        """Response with price should NOT be truncated."""
        response = (
            "El FitPack cuesta 297€. Es un programa de 12 semanas. "
            "Incluye videos, PDFs, y acceso a la comunidad privada."
        )
        result, was_truncated = smart_truncate(response, max_chars=50)

        # Should NOT truncate because it contains price
        assert "297€" in result
        assert was_truncated is False

    def test_truncate_without_protected_content(self):
        """
        CRITICAL TEST #5: Response without URLs/prices CAN be truncated.

        Response: "Hola! Gracias por tu mensaje. Espero que estés bien..."
        Expected: Truncated to ~400 chars by sentence
        """
        response = (
            "Hola! Gracias por tu mensaje. Espero que estés bien. "
            "Te cuento que tenemos varios productos interesantes. "
            "Cada uno está diseñado para diferentes necesidades. "
            "Podemos hablar sobre cuál se ajusta mejor a lo que buscas. "
            "Déjame saber si tienes alguna preferencia específica."
        )
        result, was_truncated = smart_truncate(response, max_chars=150)

        assert len(result) <= 200  # Some tolerance for sentence boundary
        assert was_truncated is True
        assert result.endswith(".")

    def test_truncate_preserves_sentence_boundary(self):
        response = "Primera frase completa. Segunda frase. Tercera frase muy larga que no cabe."
        result, was_truncated = smart_truncate(response, max_chars=50)

        # Should end at sentence boundary
        assert result.endswith(".")

    def test_truncate_with_booking_keyword_protected(self):
        """Response mentioning 'reserva' should NOT be truncated."""
        response = (
            "Puedes hacer tu reserva directamente desde mi calendario. "
            "Te recomiendo elegir un horario que te funcione bien. "
            "Así podemos hablar con calma sobre tus objetivos."
        )
        result, was_truncated = smart_truncate(response, max_chars=50)

        assert "reserva" in result
        assert was_truncated is False


# =============================================================================
# TEST MAIN VALIDATION FUNCTION
# =============================================================================


class TestValidateResponse:
    """Tests for validate_response main function."""

    def test_valid_response(self, sample_creator_data):
        """Valid response should pass validation."""
        response = "El FitPack cuesta 297€. ¿Te interesa?"

        result = validate_response(
            response=response,
            creator_data=sample_creator_data,
        )

        assert result.is_valid is True
        assert len(result.issues) == 0

    def test_hallucinated_price_fails(self, sample_creator_data):
        """Response with hallucinated price should fail and escalate."""
        response = "El retiro de yoga cuesta 1500€"

        result = validate_response(
            response=response,
            creator_data=sample_creator_data,
        )

        assert result.is_valid is False
        assert result.should_escalate is True
        assert any(i.type == "hallucinated_price" for i in result.issues)

    def test_hallucinated_link_removed(self, sample_creator_data):
        """Hallucinated link should be removed from response."""
        response = "Compra aquí: https://fake-scam-site.com/steal"

        result = validate_response(
            response=response,
            creator_data=sample_creator_data,
            auto_correct=True,
        )

        assert "fake-scam-site" not in result.corrected_response
        assert "[enlace removido]" in result.corrected_response

    def test_auto_correct_disabled(self, sample_creator_data):
        """With auto_correct=False, should not modify response."""
        response = "Link: https://fake.com"

        result = validate_response(
            response=response,
            creator_data=sample_creator_data,
            auto_correct=False,
        )

        assert result.is_valid is False
        assert result.corrected_response == response

    def test_complete_flow(self, sample_creator_data, sample_detected_context):
        """Test complete validation flow."""
        response = (
            "El FitPack Challenge cuesta 297€. Es un programa increíble. "
            "Te va a encantar. Tiene muchos beneficios."
        )

        result = validate_response(
            response=response,
            creator_data=sample_creator_data,
            detected_context=sample_detected_context,
            auto_correct=True,
        )

        # Should be valid (price is correct)
        assert result.is_valid is True
        # Should NOT be truncated (has price)
        assert "297€" in result.corrected_response


# =============================================================================
# TEST CONVENIENCE FUNCTIONS
# =============================================================================


class TestGetSafeResponse:
    """Tests for get_safe_response function."""

    def test_valid_response_returned(self, sample_creator_data):
        response = "El FitPack cuesta 297€"
        safe = get_safe_response(response, sample_creator_data)
        assert "297€" in safe

    def test_hallucination_returns_fallback(self, sample_creator_data):
        response = "El curso secreto cuesta 9999€"
        safe = get_safe_response(response, sample_creator_data)

        # Should return fallback, not the hallucinated response
        assert "9999€" not in safe
        assert "verificar" in safe.lower() or "Stefano" in safe


class TestQuickValidate:
    """Tests for quick_validate function."""

    def test_valid_response(self, sample_creator_data):
        response = "El FitPack cuesta 297€"
        assert quick_validate(response, sample_creator_data) is True

    def test_invalid_response(self, sample_creator_data):
        response = "Este producto cuesta 999999€"
        assert quick_validate(response, sample_creator_data) is False


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration tests for complete validation scenarios."""

    def test_full_valid_response(self, sample_creator_data, sample_detected_context):
        """Complete valid response with all checks."""
        response = (
            "¡Genial! El FitPack Challenge cuesta 297€. "
            "Aquí puedes comprarlo: https://pay.hotmart.com/fitpack123"
        )

        result = validate_response(
            response=response,
            creator_data=sample_creator_data,
            detected_context=sample_detected_context,
        )

        assert result.is_valid is True
        assert result.should_escalate is False
        assert len([i for i in result.issues if i.severity == "error"]) == 0

    def test_full_invalid_response(self, sample_creator_data):
        """Response with multiple issues."""
        response = (
            "El Super Mega Curso cuesta 5000€. "
            "Compra aquí: https://totally-fake-site.com/scam"
        )

        result = validate_response(
            response=response,
            creator_data=sample_creator_data,
        )

        assert result.is_valid is False
        # Should have price and link issues
        issue_types = {i.type for i in result.issues}
        assert "hallucinated_price" in issue_types
        assert "hallucinated_link" in issue_types

    def test_empty_creator_data(self):
        """Validation with empty creator data should not crash."""
        empty_data = CreatorData(creator_id="empty")
        response = "El curso cuesta 100€"

        result = validate_response(
            response=response,
            creator_data=empty_data,
        )

        # Should pass (no prices to validate against)
        assert result.is_valid is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
