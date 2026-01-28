"""
Extended debug router tests - Written BEFORE implementation (TDD).
Tests for citations debug endpoint.
"""
import pytest


class TestDebugRouterEndpoints:
    """Test debug router has citations debug endpoint."""

    def test_citations_debug_endpoint_exists(self):
        """Debug router should have /citations/debug/{creator_id} endpoint."""
        from api.routers.debug import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('citations' in path and 'debug' in path and 'GET' in methods
                   for path, methods in routes)


class TestMainAppDebugEndpoints:
    """Test main app includes debug endpoints via router."""

    def test_main_app_has_citations_debug(self):
        """Main app should have /debug/citations/debug/{creator_id} endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert any('citations' in path and 'debug' in path for path in paths)
