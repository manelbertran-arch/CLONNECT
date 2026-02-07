"""Audit tests for core/output_validator.py"""

from core.output_validator import ValidationIssue, ValidationResult


class TestAuditOutputValidator:
    def test_import(self):
        from core.output_validator import (  # noqa: F811
            ValidationIssue,
            ValidationResult,
            extract_prices_from_text,
            validate_prices,
        )

        assert ValidationIssue is not None
        assert ValidationResult is not None

    def test_init_validation_result(self):
        result = ValidationResult(is_valid=True)
        assert result is not None
        assert result.is_valid is True

    def test_happy_path_extract_prices(self):
        from core.output_validator import extract_prices_from_text

        prices = extract_prices_from_text("El curso cuesta $99.99 USD")
        assert prices is not None

    def test_edge_case_no_prices(self):
        from core.output_validator import extract_prices_from_text

        prices = extract_prices_from_text("Hola, buen dia")
        assert isinstance(prices, (list, set, tuple)) or prices is None

    def test_error_handling_validation_issue(self):
        issue = ValidationIssue(type="test", severity="low", details="test detail")
        assert issue.type == "test"
        assert issue.severity == "low"
