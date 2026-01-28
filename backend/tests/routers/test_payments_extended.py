"""
Extended payments router tests - Written BEFORE implementation (TDD).
Tests for customer purchase and attribution endpoints.
"""
import pytest


class TestPaymentsCustomerEndpoints:
    """Test customer-related payment endpoints."""

    def test_customer_purchases_endpoint_exists(self):
        """Payments router should have customer purchases endpoint."""
        from api.routers.payments import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert any('customer' in path and 'follower_id' in path for path in paths)

    def test_attribute_sale_endpoint_exists(self):
        """Payments router should have attribute sale endpoint."""
        from api.routers.payments import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('attribute' in path and 'POST' in methods for path, methods in routes)


class TestMainAppPaymentsEndpoints:
    """Test main app includes extended payment endpoints."""

    def test_main_app_has_customer_purchases(self):
        """Main app should have customer purchases endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert '/payments/{creator_id}/customer/{follower_id}' in paths

    def test_main_app_has_attribute_sale(self):
        """Main app should have attribute sale endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert '/payments/{creator_id}/attribute' in paths
