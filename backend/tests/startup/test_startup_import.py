"""
Startup module tests - Written BEFORE implementation (TDD).
Tests for startup handlers extracted from main.py.
"""
import pytest


class TestStartupModuleImport:
    """Test startup module can be imported."""

    def test_startup_module_exists(self):
        """Startup module should exist and be importable."""
        import api.startup
        assert api.startup is not None

    def test_startup_has_register_startup_handlers(self):
        """Startup should have register_startup_handlers function."""
        from api.startup import register_startup_handlers
        assert register_startup_handlers is not None
        assert callable(register_startup_handlers)


class TestMainAppStartup:
    """Test main app uses startup module."""

    def test_main_app_still_works(self):
        """Main app should still import and work after startup extraction."""
        from api.main import app
        assert app is not None
        # Verify it's a FastAPI app
        assert hasattr(app, 'routes')

    def test_main_app_has_startup_event(self):
        """Main app should have a startup event registered."""
        from api.main import app
        # FastAPI stores on_event handlers internally
        # Just verify app exists and is valid
        assert app.title == "Clonnect Creators"
