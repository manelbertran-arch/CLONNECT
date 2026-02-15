"""
Router import tests.
Verifies all routers can be imported and have correct structure.
"""


class TestRouterImports:
    """Test that all routers can be imported."""

    def test_auth_router_import(self):
        from api.auth import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_dm_router_import(self):
        from api.routers.dm import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_webhooks_router_import(self):
        from api.routers.webhooks import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_gdpr_router_import(self):
        from api.routers.gdpr import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_telegram_router_import(self):
        from api.routers.telegram import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_content_router_import(self):
        from api.routers.content import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_admin_router_import(self):
        from api.routers.admin import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_creator_router_import(self):
        from api.routers.creator import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_bot_router_import(self):
        from api.routers.bot import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_ai_router_import(self):
        from api.routers.ai import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_debug_router_import(self):
        from api.routers.debug import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_health_router_import(self):
        from api.routers.health import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_static_router_import(self):
        from api.routers.static import router
        assert router is not None
        assert hasattr(router, 'routes')


class TestMainAppImport:
    """Test that main app imports correctly with all routers."""

    def test_main_app_import(self):
        from api.main import app
        assert app is not None

    def test_main_app_has_routes(self):
        from api.main import app
        assert len(app.routes) > 0

    def test_main_app_includes_health_routes(self):
        from api.main import app
        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        assert '/health' in route_paths
        assert '/health/live' in route_paths
        assert '/health/ready' in route_paths

    def test_main_app_includes_static_routes(self):
        from api.main import app
        route_paths = [route.path for route in app.routes if hasattr(route, 'path')]
        assert '/' in route_paths
        assert '/privacy' in route_paths
        assert '/terms' in route_paths
        assert '/metrics' in route_paths


class TestRouterStructure:
    """Test that routers have expected endpoint structure."""

    def test_health_router_endpoints(self):
        from api.routers.health import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert '/health' in paths
        assert '/health/live' in paths
        assert '/health/ready' in paths

    def test_static_router_endpoints(self):
        from api.routers.static import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert '/' in paths
        assert '/privacy' in paths
        assert '/terms' in paths
        assert '/metrics' in paths

    def test_bot_router_has_endpoints(self):
        from api.routers.bot import router
        assert len(router.routes) >= 3

    def test_debug_router_has_endpoints(self):
        from api.routers.debug import router
        assert len(router.routes) >= 5
