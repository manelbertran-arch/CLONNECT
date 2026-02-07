"""Audit tests for core/whatsapp.py."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.whatsapp import (
    WhatsAppConnector,
    WhatsAppContact,
    WhatsAppHandler,
    WhatsAppHandlerStatus,
    WhatsAppMessage,
)


class TestWhatsAppConnectorInit:
    """Test 1: Initialization and imports."""

    def test_connector_init_with_explicit_params(self):
        """Connector stores params when provided explicitly."""
        connector = WhatsAppConnector(
            phone_number_id="12345",
            access_token="tok_abc",
            verify_token="ver_xyz",
            app_secret="secret_123",
        )
        assert connector.phone_number_id == "12345"
        assert connector.access_token == "tok_abc"
        assert connector.verify_token == "ver_xyz"
        assert connector.app_secret == "secret_123"
        assert connector._session is None

    def test_connector_init_falls_back_to_env(self):
        """Connector reads env vars when no params given."""
        with patch.dict(
            "os.environ",
            {
                "WHATSAPP_PHONE_NUMBER_ID": "env_phone",
                "WHATSAPP_ACCESS_TOKEN": "env_token",
                "WHATSAPP_VERIFY_TOKEN": "env_verify",
                "WHATSAPP_APP_SECRET": "env_secret",
            },
        ):
            connector = WhatsAppConnector()
            assert connector.phone_number_id == "env_phone"
            assert connector.access_token == "env_token"

    def test_whatsapp_message_dataclass_defaults(self):
        """WhatsAppMessage sets default empty list/dict for attachments and context."""
        msg = WhatsAppMessage(
            message_id="m1",
            sender_id="s1",
            recipient_id="r1",
            text="Hello",
            timestamp=datetime.now(timezone.utc),
        )
        assert msg.attachments == []
        assert msg.context == {}
        assert msg.message_type == "text"

    def test_handler_status_to_dict(self):
        """WhatsAppHandlerStatus.to_dict returns a plain dict."""
        status = WhatsAppHandlerStatus(connected=True, phone_number_id="123")
        d = status.to_dict()
        assert isinstance(d, dict)
        assert d["connected"] is True
        assert d["phone_number_id"] == "123"

    def test_whatsapp_contact_defaults(self):
        """WhatsAppContact default fields are empty strings."""
        contact = WhatsAppContact(wa_id="123456")
        assert contact.profile_name == ""
        assert contact.phone_number == ""


class TestWhatsAppSendMessage:
    """Test 2: Happy path - message sending mock."""

    @pytest.mark.asyncio
    async def test_send_message_builds_correct_payload(self):
        """send_message posts correct JSON to the API."""
        connector = WhatsAppConnector(
            phone_number_id="99999",
            access_token="test_token",
        )
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"messages": [{"id": "wamid.abc"}]})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False
        connector._session = mock_session

        result = await connector.send_message("1234567890", "Hello World")

        assert result == {"messages": [{"id": "wamid.abc"}]}
        mock_session.post.assert_called_once()
        call_kwargs = mock_session.post.call_args
        assert call_kwargs[1]["json"]["to"] == "1234567890"
        assert call_kwargs[1]["json"]["text"]["body"] == "Hello World"


class TestWhatsAppWebhookVerification:
    """Test 3: Edge case - webhook verification logic."""

    def test_verify_webhook_success(self):
        """verify_webhook returns challenge on valid subscribe + token match."""
        connector = WhatsAppConnector(verify_token="my_token")
        result = connector.verify_webhook("subscribe", "my_token", "challenge_abc")
        assert result == "challenge_abc"

    def test_verify_webhook_wrong_mode(self):
        """verify_webhook returns None when mode is not 'subscribe'."""
        connector = WhatsAppConnector(verify_token="my_token")
        result = connector.verify_webhook("unsubscribe", "my_token", "challenge_abc")
        assert result is None

    def test_verify_webhook_wrong_token(self):
        """verify_webhook returns None when token does not match."""
        connector = WhatsAppConnector(verify_token="my_token")
        result = connector.verify_webhook("subscribe", "wrong_token", "challenge_abc")
        assert result is None

    def test_verify_signature_skips_when_no_secret(self):
        """verify_webhook_signature returns True when no app_secret configured."""
        connector = WhatsAppConnector(app_secret="")
        assert connector.verify_webhook_signature(b"anything", "sig") is True


class TestWhatsAppEmptyPayload:
    """Test 4: Error handling - empty and malformed payloads."""

    @pytest.mark.asyncio
    async def test_handle_webhook_event_empty_payload(self):
        """handle_webhook_event returns empty list for empty payload."""
        connector = WhatsAppConnector(phone_number_id="123")
        messages = await connector.handle_webhook_event({})
        assert messages == []

    @pytest.mark.asyncio
    async def test_handle_webhook_event_no_messages(self):
        """handle_webhook_event returns empty list when entry has no messages."""
        connector = WhatsAppConnector(phone_number_id="123")
        payload = {"entry": [{"changes": [{"value": {}}]}]}
        messages = await connector.handle_webhook_event(payload)
        assert messages == []

    @pytest.mark.asyncio
    async def test_handle_webhook_event_malformed_data(self):
        """handle_webhook_event handles malformed data gracefully."""
        connector = WhatsAppConnector(phone_number_id="123")
        payload = {"entry": [{"changes": [{"value": {"messages": [{}]}}]}]}
        # Should not raise, empty message gets filtered (no text)
        messages = await connector.handle_webhook_event(payload)
        assert isinstance(messages, list)

    @pytest.mark.asyncio
    async def test_handler_webhook_empty_returns_zero_processed(self):
        """Handler.handle_webhook returns 0 messages_processed for empty payload."""
        with patch("core.whatsapp.WhatsAppHandler._init_agent"):
            handler = WhatsAppHandler(
                phone_number_id="123",
                access_token="tok",
                verify_token="ver",
            )
            result = await handler.handle_webhook({})
            assert result["messages_processed"] == 0
            assert result["status"] == "ok"


class TestWhatsAppRateLimitAndStatus:
    """Test 5: Integration check - status tracking and message limits."""

    def test_recent_messages_capped_at_10(self):
        """Handler._record_received caps recent_messages list at 10."""
        with patch("core.whatsapp.WhatsAppHandler._init_agent"):
            handler = WhatsAppHandler(
                phone_number_id="123",
                access_token="tok",
                verify_token="ver",
            )
            for i in range(15):
                msg = WhatsAppMessage(
                    message_id=f"m_{i}",
                    sender_id=f"sender_{i}",
                    recipient_id="123",
                    text=f"Message {i}",
                    timestamp=datetime.now(timezone.utc),
                )
                handler._record_received(msg)

            assert len(handler.recent_messages) == 10
            assert handler.status.messages_received == 15

    def test_recent_responses_capped_at_10(self):
        """Handler._record_response caps recent_responses list at 10."""
        with patch("core.whatsapp.WhatsAppHandler._init_agent"):
            handler = WhatsAppHandler(
                phone_number_id="123",
                access_token="tok",
                verify_token="ver",
            )
            for i in range(15):
                msg = WhatsAppMessage(
                    message_id=f"m_{i}",
                    sender_id=f"sender_{i}",
                    recipient_id="123",
                    text=f"Message {i}",
                    timestamp=datetime.now(timezone.utc),
                )
                mock_response = MagicMock()
                mock_response.response_text = "reply"
                mock_response.intent = MagicMock(value="greeting")
                mock_response.confidence = 0.9
                mock_response.product_mentioned = None
                mock_response.escalate_to_human = False
                handler._record_response(msg, mock_response)

            assert len(handler.recent_responses) == 10

    def test_get_status_returns_dict(self):
        """Handler.get_status returns serializable dict."""
        with patch("core.whatsapp.WhatsAppHandler._init_agent"):
            handler = WhatsAppHandler(
                phone_number_id="123",
                access_token="tok",
                verify_token="ver",
            )
            status = handler.get_status()
            assert isinstance(status, dict)
            assert "connected" in status
            assert "messages_received" in status

    def test_handler_init_without_credentials_not_connected(self):
        """Handler without credentials sets connected=False."""
        with patch("core.whatsapp.WhatsAppHandler._init_agent"):
            with patch.dict("os.environ", {}, clear=True):
                handler = WhatsAppHandler(
                    phone_number_id="",
                    access_token="",
                )
                assert handler.status.connected is False
                assert handler.connector is None

    def test_get_recent_messages_respects_limit(self):
        """get_recent_messages returns up to limit items."""
        with patch("core.whatsapp.WhatsAppHandler._init_agent"):
            handler = WhatsAppHandler(
                phone_number_id="123",
                access_token="tok",
                verify_token="ver",
            )
            for i in range(5):
                msg = WhatsAppMessage(
                    message_id=f"m_{i}",
                    sender_id="s",
                    recipient_id="123",
                    text=f"Msg {i}",
                    timestamp=datetime.now(timezone.utc),
                )
                handler._record_received(msg)

            assert len(handler.get_recent_messages(limit=3)) == 3
            assert len(handler.get_recent_messages(limit=10)) == 5
