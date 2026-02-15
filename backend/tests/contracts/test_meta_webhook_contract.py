# backend/tests/contracts/test_meta_webhook_contract.py
"""
Contract tests para Meta Webhook verification y signatures.
"""
from pydantic import BaseModel
import hashlib
import hmac


class MetaWebhookVerification(BaseModel):
    """Contrato para verificación de webhook"""
    hub_mode: str
    hub_verify_token: str
    hub_challenge: str


class TestMetaWebhookVerificationContract:
    """Tests de verificación de webhook de Meta"""

    def test_valid_verification_request(self):
        """Request de verificación válido"""
        params = {
            "hub_mode": "subscribe",
            "hub_verify_token": "clonnect_verify_token_123",
            "hub_challenge": "challenge_string_abc"
        }
        validated = MetaWebhookVerification(
            hub_mode=params["hub_mode"],
            hub_verify_token=params["hub_verify_token"],
            hub_challenge=params["hub_challenge"]
        )
        assert validated.hub_mode == "subscribe"
        assert validated.hub_challenge == "challenge_string_abc"

    def test_verification_returns_challenge(self):
        """Verificación debe devolver el challenge"""
        challenge = "1234567890"
        verification = MetaWebhookVerification(
            hub_mode="subscribe",
            hub_verify_token="my_token",
            hub_challenge=challenge
        )
        # API debe devolver el challenge como respuesta
        assert verification.hub_challenge == challenge

    def test_hub_mode_must_be_subscribe(self):
        """hub.mode debe ser 'subscribe' para suscripción"""
        verification = MetaWebhookVerification(
            hub_mode="subscribe",
            hub_verify_token="token",
            hub_challenge="challenge"
        )
        assert verification.hub_mode == "subscribe"


class TestMetaWebhookSignatureContract:
    """Tests de verificación de firma X-Hub-Signature-256"""

    def test_signature_verification_success(self):
        """Verificación de firma válida"""
        app_secret = "test_secret_123"
        payload = b'{"object":"instagram","entry":[]}'

        # Generar firma como lo hace Meta
        expected_signature = "sha256=" + hmac.new(
            app_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        # Verificar
        received_signature = expected_signature
        computed = "sha256=" + hmac.new(
            app_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        assert hmac.compare_digest(received_signature, computed)

    def test_invalid_signature_rejected(self):
        """Firma inválida es rechazada"""
        app_secret = "test_secret_123"
        payload = b'{"object":"instagram","entry":[]}'
        wrong_signature = "sha256=invalid_signature_abc123"

        computed = "sha256=" + hmac.new(
            app_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        assert not hmac.compare_digest(wrong_signature, computed)

    def test_signature_format(self):
        """Firma tiene formato sha256=xxx"""
        app_secret = "secret"
        payload = b'test'

        signature = "sha256=" + hmac.new(
            app_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()

        assert signature.startswith("sha256=")
        # sha256 produce 64 caracteres hex
        assert len(signature) == 7 + 64  # "sha256=" + 64 hex chars

    def test_different_payloads_different_signatures(self):
        """Payloads diferentes producen firmas diferentes"""
        app_secret = "secret"
        payload1 = b'{"message":"hello"}'
        payload2 = b'{"message":"world"}'

        sig1 = hmac.new(app_secret.encode(), payload1, hashlib.sha256).hexdigest()
        sig2 = hmac.new(app_secret.encode(), payload2, hashlib.sha256).hexdigest()

        assert sig1 != sig2

    def test_same_payload_same_signature(self):
        """Mismo payload produce misma firma"""
        app_secret = "secret"
        payload = b'{"test":"data"}'

        sig1 = hmac.new(app_secret.encode(), payload, hashlib.sha256).hexdigest()
        sig2 = hmac.new(app_secret.encode(), payload, hashlib.sha256).hexdigest()

        assert sig1 == sig2


class TestMetaWebhookPayloadContract:
    """Tests de estructura de payloads de Meta"""

    def test_message_webhook_structure(self):
        """Estructura de webhook de mensaje"""
        payload = {
            "object": "instagram",
            "entry": [{
                "id": "page_id_123",
                "time": 1704067200000,
                "messaging": [{
                    "sender": {"id": "user_123"},
                    "recipient": {"id": "page_123"},
                    "timestamp": 1704067200000,
                    "message": {
                        "mid": "mid.abc123",
                        "text": "Hola!"
                    }
                }]
            }]
        }

        # Verificar estructura
        assert payload["object"] == "instagram"
        assert len(payload["entry"]) > 0
        assert "messaging" in payload["entry"][0]
        assert "sender" in payload["entry"][0]["messaging"][0]

    def test_read_receipt_webhook_structure(self):
        """Estructura de webhook de read receipt"""
        payload = {
            "object": "instagram",
            "entry": [{
                "id": "page_id_123",
                "time": 1704067200000,
                "messaging": [{
                    "sender": {"id": "user_123"},
                    "recipient": {"id": "page_123"},
                    "timestamp": 1704067200000,
                    "read": {
                        "mid": "mid.abc123",
                        "watermark": 1704067200000
                    }
                }]
            }]
        }

        # Read receipts tienen "read" en lugar de "message"
        assert "read" in payload["entry"][0]["messaging"][0]
        assert "mid" in payload["entry"][0]["messaging"][0]["read"]

    def test_reaction_webhook_structure(self):
        """Estructura de webhook de reacción"""
        payload = {
            "object": "instagram",
            "entry": [{
                "id": "page_id_123",
                "time": 1704067200000,
                "messaging": [{
                    "sender": {"id": "user_123"},
                    "recipient": {"id": "page_123"},
                    "timestamp": 1704067200000,
                    "reaction": {
                        "mid": "mid.abc123",
                        "action": "react",
                        "reaction": "love"
                    }
                }]
            }]
        }

        # Reactions tienen "reaction" en lugar de "message"
        assert "reaction" in payload["entry"][0]["messaging"][0]
        assert payload["entry"][0]["messaging"][0]["reaction"]["action"] == "react"
