"""
Smoke tests for router imports.
Verifies all routers can be imported without errors.
"""
import pytest


def test_auth_router_import():
    from api.auth import router
    assert router is not None


def test_dm_router_import():
    from api.routers.dm import router
    assert router is not None


def test_webhooks_router_import():
    from api.routers.webhooks import router
    assert router is not None


def test_gdpr_router_import():
    from api.routers.gdpr import router
    assert router is not None


def test_telegram_router_import():
    from api.routers.telegram import router
    assert router is not None


def test_content_router_import():
    from api.routers.content import router
    assert router is not None


def test_admin_router_import():
    from api.routers.admin import router
    assert router is not None


def test_creator_router_import():
    from api.routers.creator import router
    assert router is not None


def test_bot_router_import():
    from api.routers.bot import router
    assert router is not None


def test_ai_router_import():
    from api.routers.ai import router
    assert router is not None


def test_debug_router_import():
    from api.routers.debug import router
    assert router is not None


def test_health_router_import():
    from api.routers.health import router
    assert router is not None


def test_static_router_import():
    from api.routers.static import router
    assert router is not None


def test_main_app_import():
    from api.main import app
    assert app is not None


def test_all_routers_included_in_app():
    """Verify all routers are properly included in the main app"""
    from api.main import app

    # Get all route paths
    routes = [route.path for route in app.routes]

    # Check key endpoints from each router exist
    expected_paths = [
        "/health",          # health.py
        "/health/live",     # health.py
        "/",                # static.py
        "/privacy",         # static.py
        "/terms",           # static.py
        "/metrics",         # static.py
    ]

    for path in expected_paths:
        assert path in routes, f"Expected path {path} not found in app routes"
