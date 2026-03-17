"""
Tests for core/creator_data_loader.py

Tests the Creator Data Loader module that provides unified data loading
for LLM context injection.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestProductInfo:
    """Tests for ProductInfo dataclass."""

    def test_product_info_defaults(self):
        from core.creator_data_loader import ProductInfo

        p = ProductInfo(id="1", name="Test Product")
        assert p.id == "1"
        assert p.name == "Test Product"
        assert p.price == 0.0
        assert p.currency == "EUR"
        assert p.is_active is True
        assert p.is_free is False

    def test_product_info_to_dict(self):
        from core.creator_data_loader import ProductInfo

        p = ProductInfo(
            id="1",
            name="FitPack",
            price=97.0,
            payment_link="https://pay.example.com/fitpack",
        )
        d = p.to_dict()
        assert d["id"] == "1"
        assert d["name"] == "FitPack"
        assert d["price"] == 97.0
        assert d["payment_link"] == "https://pay.example.com/fitpack"

    def test_product_info_from_db_row(self):
        from core.creator_data_loader import ProductInfo

        # Mock SQLAlchemy row
        mock_row = MagicMock()
        mock_row.id = "uuid-123"
        mock_row.name = "Test Course"
        mock_row.description = "A great course"
        mock_row.short_description = "Great course"
        mock_row.price = 149.0
        mock_row.currency = "EUR"
        mock_row.payment_link = "https://pay.example.com"
        mock_row.category = "product"
        mock_row.product_type = "curso"
        mock_row.is_active = True
        mock_row.is_free = False
        mock_row.source_url = "https://example.com/course"

        p = ProductInfo.from_db_row(mock_row)
        assert p.id == "uuid-123"
        assert p.name == "Test Course"
        assert p.price == 149.0


class TestPaymentMethods:
    """Tests for PaymentMethods dataclass."""

    def test_payment_methods_defaults(self):
        from core.creator_data_loader import PaymentMethods

        pm = PaymentMethods()
        assert pm.bizum_enabled is False
        assert pm.bank_enabled is False
        assert pm.get_available_methods() == []

    def test_payment_methods_from_json(self):
        from core.creator_data_loader import PaymentMethods

        data = {
            "bizum": {"enabled": True, "phone": "666123456"},
            "bank_transfer": {"enabled": True, "iban": "ES1234567890", "holder_name": "John Doe"},
            "revolut": {"enabled": False},
        }
        pm = PaymentMethods.from_json(data)
        assert pm.bizum_enabled is True
        assert pm.bizum_phone == "666123456"
        assert pm.bank_enabled is True
        assert pm.bank_iban == "ES1234567890"
        assert pm.bank_holder == "John Doe"
        assert pm.revolut_enabled is False

    def test_get_available_methods(self):
        from core.creator_data_loader import PaymentMethods

        pm = PaymentMethods(
            bizum_enabled=True,
            bizum_phone="666123456",
            bank_enabled=True,
            bank_iban="ES123",
            paypal_enabled=True,
            paypal_email="",  # Empty, should not be included
        )
        methods = pm.get_available_methods()
        assert "bizum" in methods
        assert "bank_transfer" in methods
        assert "paypal" not in methods  # No email configured


class TestCreatorData:
    """Tests for CreatorData dataclass."""

    def test_creator_data_defaults(self):
        from core.creator_data_loader import CreatorData

        data = CreatorData(creator_id="test")
        assert data.creator_id == "test"
        assert data.products == []
        assert data.booking_links == []
        assert data.lead_magnets == []
        assert data.faqs == []

    def test_get_known_prices(self):
        from core.creator_data_loader import CreatorData, ProductInfo

        data = CreatorData(creator_id="test")
        data.products = [
            ProductInfo(id="1", name="FitPack Challenge", price=97.0),
            ProductInfo(id="2", name="Mentoria Premium", price=497.0),
        ]
        data.lead_magnets = [
            ProductInfo(id="3", name="Guia Gratuita", price=0.0),
        ]

        prices = data.get_known_prices()
        assert "fitpack challenge" in prices
        assert prices["fitpack challenge"] == 97.0
        assert "mentoria premium" in prices
        assert prices["mentoria premium"] == 497.0
        # Lead magnet with price 0 should not be included
        assert "guia gratuita" not in prices

    def test_get_known_links(self):
        from core.creator_data_loader import BookingInfo, CreatorData, PaymentMethods, ProductInfo

        data = CreatorData(creator_id="test")
        data.products = [
            ProductInfo(id="1", name="Test", payment_link="https://pay.example.com/1"),
            ProductInfo(id="2", name="Test2", payment_link=""),  # Empty
        ]
        data.booking_links = [
            BookingInfo(
                id="1", meeting_type="discovery", title="Call", url="https://cal.example.com/call"
            ),
        ]
        data.payment_methods = PaymentMethods(
            revolut_enabled=True,
            revolut_link="https://revolut.me/user",
        )

        links = data.get_known_links()
        assert "https://pay.example.com/1" in links
        assert "https://cal.example.com/call" in links
        assert "https://revolut.me/user" in links
        assert len(links) == 3

    def test_get_product_by_name(self):
        from core.creator_data_loader import CreatorData, ProductInfo

        data = CreatorData(creator_id="test")
        data.products = [
            ProductInfo(id="1", name="FitPack Challenge", price=97.0),
            ProductInfo(id="2", name="Mentoria Premium", price=497.0),
        ]

        # Exact match (case insensitive)
        p = data.get_product_by_name("FitPack Challenge")
        assert p is not None
        assert p.id == "1"

        # Partial match
        p = data.get_product_by_name("fitpack")
        assert p is not None
        assert p.id == "1"

        # Not found
        p = data.get_product_by_name("nonexistent")
        assert p is None

    def test_get_featured_product(self):
        from core.creator_data_loader import CreatorData, ProductInfo

        data = CreatorData(creator_id="test")
        data.products = [
            ProductInfo(id="1", name="Cheap", price=10.0, payment_link="https://pay.example.com/1"),
            ProductInfo(
                id="2", name="Expensive", price=500.0, payment_link="https://pay.example.com/2"
            ),
            ProductInfo(id="3", name="Medium", price=100.0),  # No payment link
        ]

        featured = data.get_featured_product()
        assert featured is not None
        assert featured.id == "2"  # Highest price WITH payment link

    def test_has_payment_options(self):
        from core.creator_data_loader import CreatorData, PaymentMethods, ProductInfo

        # No payment options
        data = CreatorData(creator_id="test")
        assert data.has_payment_options() is False

        # With product link
        data.products = [ProductInfo(id="1", name="Test", payment_link="https://pay.example.com")]
        assert data.has_payment_options() is True

        # With alt payment methods only
        data2 = CreatorData(creator_id="test2")
        data2.payment_methods = PaymentMethods(bizum_enabled=True, bizum_phone="666123456")
        assert data2.has_payment_options() is True


class TestFormatters:
    """Tests for prompt formatting functions."""

    def test_format_products_for_prompt(self):
        from core.creator_data_loader import CreatorData, ProductInfo, format_products_for_prompt

        data = CreatorData(creator_id="test")
        data.products = [
            ProductInfo(
                id="1",
                name="FitPack",
                price=97.0,
                payment_link="https://pay.example.com/fitpack",
                short_description="Transform your body",
            ),
        ]
        data.lead_magnets = [
            ProductInfo(id="2", name="Free Guide", is_free=True),
        ]

        text = format_products_for_prompt(data)
        assert "=== MIS PRODUCTOS/SERVICIOS ===" in text
        assert "FitPack: 97€" in text
        assert "https://pay.example.com/fitpack" in text
        assert "=== RECURSOS GRATUITOS ===" in text
        assert "Free Guide (GRATIS)" in text

    def test_format_booking_for_prompt(self):
        from core.creator_data_loader import BookingInfo, CreatorData, format_booking_for_prompt

        data = CreatorData(creator_id="test")
        data.booking_links = [
            BookingInfo(
                id="1",
                meeting_type="discovery",
                title="Discovery Call",
                duration_minutes=30,
                price=0,
                url="https://cal.example.com/discovery",
            ),
        ]

        text = format_booking_for_prompt(data)
        assert "=== LINKS DE RESERVA ===" in text
        assert "Discovery Call (Gratis)" in text
        assert "30min" in text

    def test_format_payment_methods_for_prompt(self):
        from core.creator_data_loader import (
            CreatorData,
            PaymentMethods,
            format_payment_methods_for_prompt,
        )

        data = CreatorData(creator_id="test")
        data.payment_methods = PaymentMethods(
            bizum_enabled=True,
            bizum_phone="666123456",
            bank_enabled=True,
            bank_iban="ES1234567890",
            bank_holder="John Doe",
        )

        text = format_payment_methods_for_prompt(data)
        assert "=== METODOS DE PAGO ALTERNATIVOS ===" in text
        assert "Bizum: 666123456" in text
        assert "Transferencia bancaria: ES1234567890 (John Doe)" in text


class TestCaching:
    """Tests for caching functionality."""

    def test_cache_invalidation(self):
        from core.creator_data_loader import (
            CreatorData,
            _creator_data_cache,
            clear_all_cache,
            invalidate_creator_cache,
        )

        # Add to cache manually
        _creator_data_cache.set("test_creator", CreatorData(creator_id="test_creator"))

        # Invalidate
        invalidate_creator_cache("test_creator")
        assert "test_creator" not in _creator_data_cache

        # Clear all
        _creator_data_cache.set("a", CreatorData(creator_id="a"))
        _creator_data_cache.set("b", CreatorData(creator_id="b"))
        clear_all_cache()
        assert len(_creator_data_cache) == 0


class TestLoadCreatorData:
    """Tests for the main load_creator_data function."""

    def test_load_without_postgres(self):
        """Test that loading without PostgreSQL returns empty data."""
        with patch("core.creator_data_loader.USE_POSTGRES", False):
            from core.creator_data_loader import load_creator_data

            data = load_creator_data("test_creator")
            assert data.creator_id == "test_creator"
            assert data.products == []

    def test_load_returns_creator_data_type(self):
        """Test that load_creator_data returns correct type."""
        from core.creator_data_loader import CreatorData, load_creator_data

        # Without DB, should return empty CreatorData
        data = load_creator_data("nonexistent_creator")
        assert isinstance(data, CreatorData)
        assert data.creator_id == "nonexistent_creator"
        # Should have empty lists when no DB
        assert isinstance(data.products, list)
        assert isinstance(data.booking_links, list)


class TestAntiHallucination:
    """Tests for anti-hallucination validation methods."""

    def test_validate_price_exists(self):
        """Test that we can validate if a price exists."""
        from core.creator_data_loader import CreatorData, ProductInfo

        data = CreatorData(creator_id="test")
        data.products = [
            ProductInfo(id="1", name="FitPack Challenge", price=97.0),
        ]

        prices = data.get_known_prices()

        # Valid price
        assert "fitpack challenge" in prices
        assert prices["fitpack challenge"] == 97.0

        # Invalid price would not be in dict
        assert "nonexistent product" not in prices

    def test_validate_link_exists(self):
        """Test that we can validate if a link exists."""
        from core.creator_data_loader import CreatorData, ProductInfo

        data = CreatorData(creator_id="test")
        data.products = [
            ProductInfo(id="1", name="Test", payment_link="https://real-link.example.com"),
        ]

        links = data.get_known_links()

        # Valid link
        assert "https://real-link.example.com" in links

        # Fake link would not be in list
        assert "https://fake-hallucinated-link.example.com" not in links


class TestRemoveAccents:
    """Tests for accent removal helper."""

    def test_remove_accents(self):
        from core.creator_data_loader import _remove_accents

        assert _remove_accents("café") == "cafe"
        assert _remove_accents("niño") == "nino"
        assert _remove_accents("MÉXICO") == "MEXICO"
        assert _remove_accents("mentoría") == "mentoria"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
