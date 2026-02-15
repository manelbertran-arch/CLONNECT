"""
Messaging webhooks router tests - Written BEFORE implementation (TDD).
Run these tests FIRST - they should FAIL until router is created.
"""


class TestMessagingWebhooksRouterImport:
    """Test messaging_webhooks router can be imported."""

    def test_router_import(self):
        """Router should be importable."""
        from api.routers.messaging_webhooks import router
        assert router is not None
        assert hasattr(router, 'routes')

    def test_router_has_instagram_endpoints(self):
        """Router should have Instagram webhook endpoints."""
        from api.routers.messaging_webhooks import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert '/webhook/instagram' in paths

    def test_router_has_whatsapp_endpoints(self):
        """Router should have WhatsApp webhook endpoints."""
        from api.routers.messaging_webhooks import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert '/webhook/whatsapp' in paths

    def test_router_has_telegram_endpoints(self):
        """Router should have Telegram webhook endpoints."""
        from api.routers.messaging_webhooks import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert '/webhook/telegram' in paths


class TestInstagramWebhookEndpoints:
    """Test Instagram webhook endpoint structure."""

    def test_instagram_verify_endpoint_exists(self):
        """Instagram verify (GET) endpoint should exist."""
        from api.routers.messaging_webhooks import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('/webhook/instagram' in path and 'GET' in methods for path, methods in routes)

    def test_instagram_receive_endpoint_exists(self):
        """Instagram receive (POST) endpoint should exist."""
        from api.routers.messaging_webhooks import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('/webhook/instagram' in path and 'POST' in methods for path, methods in routes)

    def test_instagram_legacy_endpoints_exist(self):
        """Instagram legacy endpoints should exist."""
        from api.routers.messaging_webhooks import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert '/instagram/webhook' in paths

    def test_instagram_comments_endpoint_exists(self):
        """Instagram comments webhook endpoint should exist."""
        from api.routers.messaging_webhooks import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert '/webhook/instagram/comments' in paths

    def test_instagram_status_endpoint_exists(self):
        """Instagram status endpoint should exist."""
        from api.routers.messaging_webhooks import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert '/instagram/status' in paths


class TestWhatsAppWebhookEndpoints:
    """Test WhatsApp webhook endpoint structure."""

    def test_whatsapp_verify_endpoint_exists(self):
        """WhatsApp verify (GET) endpoint should exist."""
        from api.routers.messaging_webhooks import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('/webhook/whatsapp' in path and 'GET' in methods for path, methods in routes)

    def test_whatsapp_receive_endpoint_exists(self):
        """WhatsApp receive (POST) endpoint should exist."""
        from api.routers.messaging_webhooks import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('/webhook/whatsapp' in path and 'POST' in methods for path, methods in routes)


class TestTelegramWebhookEndpoints:
    """Test Telegram webhook endpoint structure."""

    def test_telegram_webhook_endpoint_exists(self):
        """Telegram webhook (POST) endpoint should exist."""
        from api.routers.messaging_webhooks import router
        routes = [(r.path, r.methods) for r in router.routes if hasattr(r, 'path')]
        assert any('/webhook/telegram' in path and 'POST' in methods for path, methods in routes)

    def test_telegram_legacy_endpoint_exists(self):
        """Telegram legacy endpoint should exist."""
        from api.routers.messaging_webhooks import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert '/telegram/webhook' in paths


class TestMainAppIncludesMessagingWebhooks:
    """Test main app includes messaging webhooks router."""

    def test_main_app_has_instagram_webhook(self):
        """Main app should have Instagram webhook endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert '/webhook/instagram' in paths

    def test_main_app_has_whatsapp_webhook(self):
        """Main app should have WhatsApp webhook endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert '/webhook/whatsapp' in paths

    def test_main_app_has_telegram_webhook(self):
        """Main app should have Telegram webhook endpoint."""
        from api.main import app
        paths = [r.path for r in app.routes if hasattr(r, 'path')]
        assert '/webhook/telegram' in paths
