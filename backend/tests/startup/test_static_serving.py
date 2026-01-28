"""
Static file serving module tests - Written BEFORE implementation (TDD).
"""
import pytest


class TestStaticServingModuleImport:
    """Test static serving module can be imported."""

    def test_static_serving_module_exists(self):
        """Static serving module should exist and be importable."""
        import api.static_serving
        assert api.static_serving is not None

    def test_static_serving_has_register_function(self):
        """Static serving should have register_static_routes function."""
        from api.static_serving import register_static_routes
        assert register_static_routes is not None
        assert callable(register_static_routes)


class TestMainAppStaticEndpoints:
    """Test main app has static endpoints registered."""

    def test_main_app_has_catchall_route(self):
        """Main app should have catch-all route for SPA."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        # The catch-all is /{full_path:path}
        assert '/{full_path:path}' in paths
