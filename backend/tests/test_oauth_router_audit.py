"""Audit tests for api/routers/oauth.py."""

import os
from unittest.mock import patch


# ---------------------------------------------------------------------------
# 1. Init / Import
# ---------------------------------------------------------------------------
class TestOauthRouterImport:
    """Verify that the oauth router and its key symbols can be imported."""

    def test_router_imports_successfully(self):
        """The router object and key helpers should be importable."""
        from api.routers.oauth import router

        assert router is not None
        assert router.prefix == "/oauth"
        assert "oauth" in router.tags

    def test_internal_helpers_importable(self):
        """Internal async helpers should be importable."""
        from api.routers.oauth import _auto_onboard_after_instagram_oauth, refresh_google_token

        assert callable(_auto_onboard_after_instagram_oauth)
        assert callable(refresh_google_token)


# ---------------------------------------------------------------------------
# 2. Happy Path -- OAuth callback (mocked)
# ---------------------------------------------------------------------------
class TestOauthCallbackMock:
    """Test OAuth Instagram start endpoint returns correct URL structure."""

    def test_instagram_start_returns_auth_url(self, client):
        """GET /oauth/instagram/start should return auth_url when app_id is set."""
        with patch.dict(os.environ, {"INSTAGRAM_APP_ID": "123456789"}):
            # Need to reload the module-level constant
            import api.routers.oauth as oauth_mod

            original_app_id = oauth_mod.INSTAGRAM_APP_ID
            oauth_mod.INSTAGRAM_APP_ID = "123456789"

            try:
                response = client.get("/oauth/instagram/start?creator_id=test_creator")
                assert response.status_code == 200
                data = response.json()
                assert "auth_url" in data
                assert "instagram.com/oauth/authorize" in data["auth_url"]
                assert "state" in data
                assert "scopes_requested" in data
            finally:
                oauth_mod.INSTAGRAM_APP_ID = original_app_id


# ---------------------------------------------------------------------------
# 3. Edge Case -- Invalid token handling
# ---------------------------------------------------------------------------
class TestInvalidTokenHandling:
    """Test behavior when OAuth tokens are missing or invalid."""

    def test_instagram_start_fails_without_app_id(self, client):
        """GET /oauth/instagram/start should return 500 if no app_id configured."""
        import api.routers.oauth as oauth_mod

        original_app = oauth_mod.INSTAGRAM_APP_ID
        original_meta = oauth_mod.META_APP_ID
        oauth_mod.INSTAGRAM_APP_ID = ""
        oauth_mod.META_APP_ID = ""

        try:
            response = client.get("/oauth/instagram/start?creator_id=test")
            assert response.status_code == 500
            assert "not configured" in response.json()["detail"]
        finally:
            oauth_mod.INSTAGRAM_APP_ID = original_app
            oauth_mod.META_APP_ID = original_meta


# ---------------------------------------------------------------------------
# 4. Error Handling -- Token refresh mock
# ---------------------------------------------------------------------------
class TestTokenRefreshMock:
    """Test Google token refresh endpoint error paths."""

    def test_google_refresh_fails_when_db_unavailable(self, client):
        """POST /oauth/refresh/google/{creator_id} fails gracefully without DB."""
        # The refresh function calls SessionLocal which will fail in test env
        response = client.post("/oauth/refresh/google/nonexistent_creator")
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# 5. Integration Check -- Multi-platform support
# ---------------------------------------------------------------------------
class TestMultiPlatformSupport:
    """Verify that the router supports multiple OAuth platforms."""

    def test_router_has_all_platform_routes(self):
        """The router should have endpoints for Instagram, Google, Stripe, PayPal."""
        from api.routers.oauth import router

        route_paths = [route.path for route in router.routes]

        # Instagram endpoints (paths include router prefix)
        assert "/oauth/instagram/start" in route_paths
        assert "/oauth/instagram/callback" in route_paths

        # Google endpoints
        assert "/oauth/google/start" in route_paths
        assert "/oauth/google/callback" in route_paths

        # Stripe endpoints
        assert "/oauth/stripe/start" in route_paths
        assert "/oauth/stripe/callback" in route_paths

        # Status endpoint
        assert "/oauth/status/{creator_id}" in route_paths

    def test_debug_endpoint_returns_platform_config(self, client):
        """GET /oauth/debug should list config for all platforms."""
        response = client.get("/oauth/debug")
        assert response.status_code == 200
        data = response.json()
        assert "meta" in data
        assert "stripe" in data
        assert "paypal" in data
        assert "google" in data
