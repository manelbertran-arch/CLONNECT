"""Audit tests for core/token_refresh_service.py."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test 1: Init / Import
# ---------------------------------------------------------------------------


class TestTokenRefreshImport:
    """Verify module imports and key constants."""

    def test_import_module(self):
        from core.token_refresh_service import (
            check_and_refresh_if_needed,
            check_and_refresh_sync,
            exchange_for_long_lived_token,
            refresh_all_creator_tokens,
            refresh_long_lived_token,
        )

        # Functions should be callable
        assert callable(exchange_for_long_lived_token)
        assert callable(refresh_long_lived_token)
        assert callable(check_and_refresh_if_needed)
        assert callable(refresh_all_creator_tokens)
        assert callable(check_and_refresh_sync)


# ---------------------------------------------------------------------------
# Test 2: Happy Path -- refresh_long_lived_token with IGAAT token
# ---------------------------------------------------------------------------


class TestRefreshLongLivedToken:
    """Happy path: refreshing an Instagram IGAAT token."""

    @pytest.mark.asyncio
    async def test_refresh_igaat_token_success(self):
        from core.token_refresh_service import refresh_long_lived_token

        mock_response_data = {
            "access_token": "IGAAT_new_refreshed_token",
            "expires_in": 5184000,
        }

        # Build async context manager for the response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=mock_response_data)

        # Build async context manager for the session.get()
        mock_get_cm = AsyncMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_cm.__aexit__ = AsyncMock(return_value=False)

        # Build async context manager for ClientSession()
        mock_session = MagicMock()
        mock_session.get.return_value = mock_get_cm

        mock_client_session_cm = AsyncMock()
        mock_client_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_client_session_cm):
            result = await refresh_long_lived_token("IGAAT_old_token")

        assert result is not None
        assert result["token"] == "IGAAT_new_refreshed_token"
        assert result["expires_in"] == 5184000
        assert "expires_at" in result


# ---------------------------------------------------------------------------
# Test 3: Edge Case -- EAA (Page Access Token) uses Facebook endpoint
# ---------------------------------------------------------------------------


class TestPageAccessTokenEdge:
    """EAA tokens should use the Facebook refresh endpoint."""

    @pytest.mark.asyncio
    async def test_eaa_token_without_credentials_returns_current(self):
        """When META_APP_ID/SECRET not set, return current token as still valid."""
        from core.token_refresh_service import refresh_long_lived_token

        with patch("core.token_refresh_service.META_APP_ID", ""), patch(
            "core.token_refresh_service.META_APP_SECRET", ""
        ):
            result = await refresh_long_lived_token("EAA_page_access_token_xyz")

        # Should return the current token as a fallback
        assert result is not None
        assert result["token"] == "EAA_page_access_token_xyz"
        assert result["expires_in"] == 5184000


# ---------------------------------------------------------------------------
# Test 4: Error Handling -- exchange_for_long_lived_token fails gracefully
# ---------------------------------------------------------------------------


class TestExchangeTokenErrors:
    """Error handling when token exchange fails."""

    @pytest.mark.asyncio
    async def test_exchange_returns_none_when_no_secret(self):
        from core.token_refresh_service import exchange_for_long_lived_token

        with patch("core.token_refresh_service.META_APP_SECRET", ""):
            result = await exchange_for_long_lived_token("short_lived_tok")

        assert result is None

    @pytest.mark.asyncio
    async def test_exchange_returns_none_on_api_error(self):
        from core.token_refresh_service import exchange_for_long_lived_token

        mock_response_data = {"error": {"message": "Invalid token", "code": 190}}

        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_get_cm = AsyncMock()
        mock_get_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_cm.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_get_cm

        mock_client_session_cm = AsyncMock()
        mock_client_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_session_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("core.token_refresh_service.META_APP_SECRET", "real_secret"), patch(
            "aiohttp.ClientSession", return_value=mock_client_session_cm
        ):
            result = await exchange_for_long_lived_token("bad_token")

        assert result is None


# ---------------------------------------------------------------------------
# Test 5: Integration Check -- check_and_refresh_if_needed with mock DB
# ---------------------------------------------------------------------------


class TestCheckAndRefreshIntegration:
    """Integration: check_and_refresh_if_needed with a mocked database."""

    @pytest.mark.asyncio
    async def test_skip_if_token_still_valid(self):
        from core.token_refresh_service import check_and_refresh_if_needed

        mock_session = MagicMock()

        # Simulate a creator whose token expires in 30 days (well above threshold)
        future_expiry = datetime.utcnow() + timedelta(days=30)
        mock_row = (
            "uuid-123",  # id
            "test_creator",  # name
            "IGAAT_valid",  # token
            future_expiry,  # expires_at
        )
        mock_session.execute.return_value.fetchone.return_value = mock_row

        result = await check_and_refresh_if_needed("test_creator", mock_session)

        assert result["action"] == "skip"
        assert result["success"] is True
        assert result["days_until_expiry"] >= 29

    @pytest.mark.asyncio
    async def test_creator_not_found(self):
        from core.token_refresh_service import check_and_refresh_if_needed

        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.return_value = None

        result = await check_and_refresh_if_needed("ghost_creator", mock_session)

        assert result["success"] is False
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_no_token(self):
        from core.token_refresh_service import check_and_refresh_if_needed

        mock_session = MagicMock()
        mock_row = ("uuid-456", "no_token_creator", None, None)
        mock_session.execute.return_value.fetchone.return_value = mock_row

        result = await check_and_refresh_if_needed("no_token_creator", mock_session)

        assert result["success"] is False
        assert "No Instagram token" in result["message"]
