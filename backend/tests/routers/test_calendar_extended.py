"""
Extended calendar router tests - Written BEFORE implementation (TDD).
Tests for unique calendar endpoints that need to move from main.py to calendar.py.
"""
import pytest


class TestCalendarRouterEndpoints:
    """Test calendar router has all required endpoints."""

    def test_get_booking_link_by_type_endpoint_exists(self):
        """Calendar router should have GET /link/{meeting_type} endpoint."""
        from api.routers.calendar import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('link' in path and 'meeting_type' in path and 'GET' in methods
                   for path, methods in routes)

    def test_mark_booking_complete_endpoint_exists(self):
        """Calendar router should have POST /bookings/{booking_id}/complete endpoint."""
        from api.routers.calendar import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('complete' in path and 'POST' in methods for path, methods in routes)

    def test_mark_booking_no_show_endpoint_exists(self):
        """Calendar router should have POST /bookings/{booking_id}/no-show endpoint."""
        from api.routers.calendar import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('no-show' in path and 'POST' in methods for path, methods in routes)


class TestMainAppCalendarEndpoints:
    """Test main app includes all calendar endpoints via router."""

    def test_main_app_has_booking_link_by_type(self):
        """Main app should have /calendar/{creator_id}/link/{meeting_type} endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert '/calendar/{creator_id}/link/{meeting_type}' in paths

    def test_main_app_has_mark_complete(self):
        """Main app should have /calendar/{creator_id}/bookings/{booking_id}/complete endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert '/calendar/{creator_id}/bookings/{booking_id}/complete' in paths

    def test_main_app_has_mark_no_show(self):
        """Main app should have /calendar/{creator_id}/bookings/{booking_id}/no-show endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert '/calendar/{creator_id}/bookings/{booking_id}/no-show' in paths


class TestPublicBookingLinksEndpoint:
    """Test public booking-links endpoint."""

    def test_main_app_has_public_booking_links(self):
        """Main app should have /booking-links/{creator_name} endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert '/booking-links/{creator_name}' in paths
