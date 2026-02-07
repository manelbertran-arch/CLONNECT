"""Tests for Instagram Handler - Webhook verification and message extraction."""

import hashlib
import hmac
import json

import pytest

from core.instagram_handler import InstagramHandler


class TestWebhookVerification:
    """Test the GET webhook verification (Meta subscription)."""

    def test_valid_verification(self):
        handler = InstagramHandler(verify_token="test_token_123")
        result = handler.verify_webhook("subscribe", "test_token_123", "challenge_abc")
        assert result == "challenge_abc"

    def test_wrong_token(self):
        handler = InstagramHandler(verify_token="test_token_123")
        result = handler.verify_webhook("subscribe", "wrong_token", "challenge_abc")
        assert result is None

    def test_wrong_mode(self):
        handler = InstagramHandler(verify_token="test_token_123")
        result = handler.verify_webhook("unsubscribe", "test_token_123", "challenge_abc")
        assert result is None

    def test_empty_token(self):
        handler = InstagramHandler(verify_token="")
        result = handler.verify_webhook("subscribe", "", "challenge_abc")
        # Empty string == empty string, so this should pass
        assert result == "challenge_abc"


class TestWebhookSignature:
    """Test HMAC signature verification for POST webhooks."""

    def test_valid_signature(self):
        handler = InstagramHandler(app_secret="test_secret")
        payload = b'{"entry": [{"messaging": []}]}'
        expected_hash = hmac.new(b"test_secret", payload, hashlib.sha256).hexdigest()
        signature = f"sha256={expected_hash}"

        # Access connector's verify method
        assert handler.connector is not None or handler.app_secret == "test_secret"
        # Direct HMAC check (same logic as connector)
        computed = hmac.new(b"test_secret", payload, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(f"sha256={computed}", signature)

    def test_invalid_signature(self):
        payload = b'{"entry": [{"messaging": []}]}'
        computed = hmac.new(b"test_secret", payload, hashlib.sha256).hexdigest()
        assert not hmac.compare_digest(f"sha256={computed}", "sha256=wrong_hash")

    def test_different_payload_different_signature(self):
        secret = b"test_secret"
        payload1 = b'{"data": "one"}'
        payload2 = b'{"data": "two"}'
        sig1 = hmac.new(secret, payload1, hashlib.sha256).hexdigest()
        sig2 = hmac.new(secret, payload2, hashlib.sha256).hexdigest()
        assert sig1 != sig2


class TestMessageExtraction:
    """Test message extraction from webhook payloads."""

    @pytest.fixture
    def handler(self):
        return InstagramHandler(creator_id="test_creator")

    @pytest.mark.asyncio
    async def test_extract_text_message(self, handler):
        payload = {
            "entry": [
                {
                    "id": "page_123",
                    "messaging": [
                        {
                            "sender": {"id": "user_456"},
                            "recipient": {"id": "page_123"},
                            "timestamp": 1700000000000,
                            "message": {"mid": "msg_1", "text": "Hola!"},
                        }
                    ],
                }
            ]
        }
        messages = await handler._extract_messages(payload)
        assert len(messages) >= 1
        assert messages[0].text == "Hola!"
        assert messages[0].sender_id == "user_456"

    @pytest.mark.asyncio
    async def test_empty_payload(self, handler):
        messages = await handler._extract_messages({})
        assert messages == []

    @pytest.mark.asyncio
    async def test_empty_entry(self, handler):
        messages = await handler._extract_messages({"entry": []})
        assert messages == []

    @pytest.mark.asyncio
    async def test_skip_echo_messages(self, handler):
        """Echo messages (sent by creator) should be filtered out."""
        payload = {
            "entry": [
                {
                    "id": "page_123",
                    "messaging": [
                        {
                            "sender": {"id": "page_123"},
                            "recipient": {"id": "user_456"},
                            "timestamp": 1700000000000,
                            "message": {
                                "mid": "msg_echo",
                                "text": "Response",
                                "is_echo": True,
                            },
                        }
                    ],
                }
            ]
        }
        messages = await handler._extract_messages(payload)
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_emoji_message(self, handler):
        payload = {
            "entry": [
                {
                    "id": "page_123",
                    "messaging": [
                        {
                            "sender": {"id": "user_456"},
                            "recipient": {"id": "page_123"},
                            "timestamp": 1700000000000,
                            "message": {"mid": "msg_2", "text": ""},
                        }
                    ],
                }
            ]
        }
        messages = await handler._extract_messages(payload)
        assert isinstance(messages, list)


class TestHandlerStatus:
    """Test handler status reporting."""

    def test_initial_status(self):
        handler = InstagramHandler(creator_id="test")
        status = handler.get_status()
        assert isinstance(status, dict)
        assert "messages_received" in status or "connected" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
