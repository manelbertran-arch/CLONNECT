"""
E2E Tests for Instagram Multi-Creator Support

BLOQUE 6: Tests for the new Instagram router with multi-creator routing.
Tests webhook routing, Ice Breakers, Stories handling, and creator management.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest


class TestPayloadExtraction:
    """Tests for extracting page_id from webhook payloads"""

    def test_extract_page_id_from_entry(self):
        """Test extracting page_id from entry.id"""
        from api.routers.instagram import extract_page_id_from_payload

        payload = {
            "object": "instagram",
            "entry": [{"id": "page-123", "time": 1700000000000, "messaging": []}],
        }

        result = extract_page_id_from_payload(payload)
        assert result == "page-123"

    def test_extract_page_id_from_messaging(self):
        """Test extracting page_id from messaging recipient"""
        from api.routers.instagram import extract_page_id_from_payload

        payload = {
            "object": "instagram",
            "entry": [
                {"messaging": [{"sender": {"id": "user-123"}, "recipient": {"id": "page-456"}}]}
            ],
        }

        result = extract_page_id_from_payload(payload)
        # Should return entry id first (None here), then fall back to recipient
        assert result == "page-456"

    def test_extract_page_id_empty_payload(self):
        """Test extracting page_id from empty payload"""
        from api.routers.instagram import extract_page_id_from_payload

        result = extract_page_id_from_payload({})
        assert result is None

        result = extract_page_id_from_payload({"entry": []})
        assert result is None


class TestWebhookEndpoints:
    """Tests for webhook endpoints"""

    @pytest.mark.asyncio
    async def test_webhook_verify_success(self):
        """Test successful webhook verification"""
        from api.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        response = client.get(
            "/instagram/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "clonnect_verify_2024",
                "hub.challenge": "test_challenge_123",
            },
        )

        assert response.status_code == 200
        assert response.text == "test_challenge_123"

    @pytest.mark.asyncio
    async def test_webhook_verify_failure(self):
        """Test failed webhook verification"""
        from api.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        response = client.get(
            "/instagram/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "test_challenge",
            },
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_webhook_receive_unknown_creator(self):
        """Test receiving webhook for unknown creator"""
        from api.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "unknown-page-id",
                    "time": 1700000000000,
                    "messaging": [
                        {
                            "sender": {"id": "user-123"},
                            "recipient": {"id": "unknown-page-id"},
                            "timestamp": 1700000000000,
                            "message": {"mid": "msg-123", "text": "Hello"},
                        }
                    ],
                }
            ],
        }

        with patch("api.routers.instagram.get_creator_by_page_id", return_value=None):
            with patch("api.routers.instagram.get_creator_by_ig_user_id", return_value=None):
                response = client.post("/instagram/webhook", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["warning"] == "unknown_creator"


class TestStoriesHandler:
    """Tests for Stories reply/mention handling"""

    @pytest.mark.asyncio
    async def test_handle_story_mention(self):
        """Test handling story mention"""
        from api.routers.instagram import _handle_story_mention

        creator_info = {
            "creator_id": "test_creator",
            "instagram_token": "token-123",
            "instagram_page_id": "page-456",
            "instagram_user_id": "ig-789",
            "copilot_mode": False,
        }

        with patch("api.routers.instagram.get_handler_for_creator") as mock_get_handler:
            mock_handler = Mock()
            mock_handler.send_response = AsyncMock(return_value=True)
            mock_get_handler.return_value = mock_handler

            with patch("api.routers.instagram._register_story_interaction", new_callable=AsyncMock):
                result = await _handle_story_mention(
                    creator_info=creator_info,
                    sender_id="user-123",
                    story_url="https://instagram.com/story/123",
                    message_text="",
                )

        assert result["type"] == "story_mention"
        assert result["response_sent"] is True
        mock_handler.send_response.assert_called_once()


class TestEchoMessageFiltering:
    """Tests for filtering echo messages (bot's own messages)"""

    @pytest.mark.asyncio
    async def test_skip_echo_messages(self):
        """Test that echo messages are skipped"""
        from core.instagram_handler import InstagramHandler

        handler = InstagramHandler(
            access_token="test", page_id="page-123", ig_user_id="ig-456", creator_id="test_creator"
        )

        # Payload with echo message (is_echo=true)
        payload = {
            "entry": [
                {
                    "messaging": [
                        {
                            "sender": {"id": "page-123"},
                            "recipient": {"id": "user-789"},
                            "message": {"mid": "msg-123", "text": "Bot response", "is_echo": True},
                        }
                    ]
                }
            ]
        }

        # Extract messages should skip echo
        messages = await handler._extract_messages(payload)

        assert len(messages) == 0


class TestMultiCreatorIntegration:
    """Integration tests for multi-creator flow"""

    @pytest.mark.asyncio
    async def test_full_webhook_flow(self):
        """Test complete webhook flow with multi-creator routing"""
        from api.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Create payload from "page-creator1"
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "page-creator1",
                    "time": 1700000000000,
                    "messaging": [
                        {
                            "sender": {"id": "user-123"},
                            "recipient": {"id": "page-creator1"},
                            "timestamp": 1700000000000,
                            "message": {"mid": "msg-123", "text": "Hello!"},
                        }
                    ],
                }
            ],
        }

        creator_info = {
            "creator_id": "creator1",
            "creator_uuid": "uuid-123",
            "instagram_token": "token-123",
            "instagram_page_id": "page-creator1",
            "instagram_user_id": "ig-123",
            "bot_active": True,
            "copilot_mode": True,
        }

        with patch("api.routers.instagram.get_creator_by_page_id", return_value=creator_info):
            with patch("api.routers.instagram.get_handler_for_creator") as mock_get_handler:
                mock_handler = Mock()
                mock_handler.handle_webhook = AsyncMock(
                    return_value={"status": "ok", "messages_processed": 1, "results": []}
                )
                mock_get_handler.return_value = mock_handler

                response = client.post("/instagram/webhook", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["creator_id"] == "creator1"
        assert data["page_id"] == "page-creator1"


class TestBotPausedBehavior:
    """Tests for behavior when bot is paused"""

    @pytest.mark.asyncio
    async def test_skip_when_bot_paused(self):
        """Test that messages are skipped when bot_active=False"""
        from api.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "page-paused",
                    "messaging": [
                        {
                            "sender": {"id": "user-123"},
                            "recipient": {"id": "page-paused"},
                            "message": {"mid": "msg-123", "text": "Hello"},
                        }
                    ],
                }
            ],
        }

        creator_info = {
            "creator_id": "paused_creator",
            "instagram_page_id": "page-paused",
            "bot_active": False,  # Bot is paused
            "copilot_mode": False,
        }

        with patch("api.routers.instagram.get_creator_by_page_id", return_value=creator_info):
            response = client.post("/instagram/webhook", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["info"] == "bot_paused"


class TestMultiCreatorRouterImport:
    """Tests that the router imports correctly"""

    def test_router_exists(self):
        """Test that the router is importable"""
        from api.routers.instagram import router

        assert router is not None

    def test_endpoints_registered(self):
        """Test that expected endpoints are registered"""
        from api.routers.instagram import router

        paths = [route.path for route in router.routes]

        # Paths include the prefix
        assert "/instagram/webhook" in paths
        assert "/instagram/icebreakers/{creator_id}" in paths
        assert "/instagram/persistent-menu/{creator_id}" in paths
        assert "/instagram/webhook/stories" in paths
        assert "/instagram/connect" in paths
        assert "/instagram/status/{creator_id}" in paths
        assert "/instagram/creators" in paths

    def test_helper_functions_exist(self):
        """Test that helper functions exist"""
        from api.routers.instagram import (
            extract_page_id_from_payload,
            get_creator_by_ig_user_id,
            get_creator_by_page_id,
            get_handler_for_creator,
        )

        assert callable(get_creator_by_page_id)
        assert callable(get_creator_by_ig_user_id)
        assert callable(get_handler_for_creator)
        assert callable(extract_page_id_from_payload)


class TestCreatorLookupFunctions:
    """Test creator lookup functions behavior"""

    def test_get_creator_by_page_id_returns_none_when_not_found(self):
        """Test that None is returned when creator is not found"""
        from api.routers.instagram import get_creator_by_page_id

        # When database is not configured, function returns None
        result = get_creator_by_page_id("nonexistent-page-123")
        # Should return None (either not found or DB error)
        assert result is None

    def test_get_creator_by_ig_user_id_returns_none_when_not_found(self):
        """Test that None is returned when creator is not found"""
        from api.routers.instagram import get_creator_by_ig_user_id

        # When database is not configured, function returns None
        result = get_creator_by_ig_user_id("nonexistent-ig-123")
        # Should return None (either not found or DB error)
        assert result is None


class TestIceBreakersValidation:
    """Test Ice Breakers validation logic"""

    def test_ice_breakers_format(self):
        """Test that ice breakers are properly formatted"""
        # This is a logical test - just validating the expected format
        ice_breakers = [
            {"question": "What services?", "payload": "SERVICES"},
            {"question": "How much?", "payload": "PRICING"},
        ]

        formatted = [
            {"question": ib["question"], "payload": ib.get("payload", ib["question"][:20])}
            for ib in ice_breakers
        ]

        assert len(formatted) == 2
        assert formatted[0]["question"] == "What services?"
        assert formatted[0]["payload"] == "SERVICES"

    def test_ice_breakers_max_count(self):
        """Test max ice breakers limit"""
        max_allowed = 4

        ice_breakers_valid = [{"question": f"Q{i}", "payload": f"P{i}"} for i in range(4)]
        ice_breakers_invalid = [{"question": f"Q{i}", "payload": f"P{i}"} for i in range(5)]

        assert len(ice_breakers_valid) <= max_allowed
        assert len(ice_breakers_invalid) > max_allowed
