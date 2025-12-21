"""
Tests para el conector de Instagram
"""

import pytest
from datetime import datetime
from core.instagram import (
    InstagramMessage,
    InstagramUser,
    InstagramConnector
)


class TestInstagramMessage:
    """Tests para InstagramMessage"""

    def test_message_creation(self):
        """Test crear mensaje"""
        msg = InstagramMessage(
            message_id="msg-123",
            sender_id="sender-456",
            recipient_id="recipient-789",
            text="Hola!",
            timestamp=datetime.now()
        )

        assert msg.message_id == "msg-123"
        assert msg.sender_id == "sender-456"
        assert msg.text == "Hola!"
        assert msg.attachments == []

    def test_message_with_attachments(self):
        """Test mensaje con adjuntos"""
        msg = InstagramMessage(
            message_id="msg-123",
            sender_id="sender-456",
            recipient_id="recipient-789",
            text="Mira esto",
            timestamp=datetime.now(),
            attachments=[{"type": "image", "url": "https://example.com/img.jpg"}]
        )

        assert len(msg.attachments) == 1
        assert msg.attachments[0]["type"] == "image"


class TestInstagramUser:
    """Tests para InstagramUser"""

    def test_user_creation(self):
        """Test crear usuario"""
        user = InstagramUser(
            user_id="user-123",
            username="test_user",
            name="Test User"
        )

        assert user.user_id == "user-123"
        assert user.username == "test_user"
        assert user.name == "Test User"
        assert user.profile_pic_url == ""

    def test_user_with_profile_pic(self):
        """Test usuario con foto de perfil"""
        user = InstagramUser(
            user_id="user-123",
            username="test_user",
            name="Test User",
            profile_pic_url="https://example.com/pic.jpg"
        )

        assert user.profile_pic_url == "https://example.com/pic.jpg"


class TestInstagramConnector:
    """Tests para InstagramConnector"""

    def setup_method(self):
        """Setup connector para tests"""
        self.connector = InstagramConnector(
            access_token="test-token",
            page_id="test-page-id",
            ig_user_id="test-user-id",
            app_secret="test-secret",
            verify_token="test-verify"
        )

    def test_connector_creation(self):
        """Test crear connector"""
        assert self.connector.access_token == "test-token"
        assert self.connector.page_id == "test-page-id"
        assert self.connector.verify_token == "test-verify"

    def test_verify_webhook_challenge_success(self):
        """Test verificacion webhook exitosa"""
        result = self.connector.verify_webhook_challenge(
            mode="subscribe",
            token="test-verify",
            challenge="challenge-123"
        )
        assert result == "challenge-123"

    def test_verify_webhook_challenge_wrong_token(self):
        """Test verificacion webhook con token incorrecto"""
        result = self.connector.verify_webhook_challenge(
            mode="subscribe",
            token="wrong-token",
            challenge="challenge-123"
        )
        assert result is None

    def test_verify_webhook_challenge_wrong_mode(self):
        """Test verificacion webhook con modo incorrecto"""
        result = self.connector.verify_webhook_challenge(
            mode="unsubscribe",
            token="test-verify",
            challenge="challenge-123"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_webhook_event_with_message(self):
        """Test procesar evento webhook con mensaje"""
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "sender-123"},
                    "recipient": {"id": "recipient-456"},
                    "timestamp": 1700000000000,
                    "message": {
                        "mid": "msg-789",
                        "text": "Hola!"
                    }
                }]
            }]
        }

        messages = await self.connector.handle_webhook_event(payload)
        assert len(messages) == 1
        assert messages[0].message_id == "msg-789"
        assert messages[0].text == "Hola!"
        assert messages[0].sender_id == "sender-123"

    @pytest.mark.asyncio
    async def test_handle_webhook_event_empty(self):
        """Test procesar evento webhook vacio"""
        payload = {"entry": []}
        messages = await self.connector.handle_webhook_event(payload)
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_handle_webhook_event_no_message(self):
        """Test procesar evento webhook sin mensaje"""
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "sender-123"},
                    "recipient": {"id": "recipient-456"},
                    "timestamp": 1700000000000
                    # No "message" key
                }]
            }]
        }

        messages = await self.connector.handle_webhook_event(payload)
        assert len(messages) == 0

    def test_verify_webhook_signature_no_secret(self):
        """Test verificacion de firma sin secret"""
        connector = InstagramConnector(
            access_token="test",
            page_id="test",
            ig_user_id="test",
            app_secret=""  # Sin secret
        )

        # Deberia devolver True (skip verificacion)
        result = connector.verify_webhook_signature(b"payload", "sha256=xxx")
        assert result is True
