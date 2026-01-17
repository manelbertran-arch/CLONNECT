# backend/tests/contracts/test_instagram_contract.py
"""
Contract tests para Instagram Graph API.
Verifican que los payloads enviados/recibidos cumplen el contrato esperado.
"""
import pytest
from pydantic import BaseModel, ValidationError
from typing import Optional, List


# === CONTRATOS (Schemas) ===

class IGMessagePayload(BaseModel):
    """Contrato: Mensaje enviado a Instagram"""
    recipient: dict  # {"id": "user_id"}
    message: dict    # {"text": "..."} o {"attachment": {...}}

    class Config:
        extra = "forbid"  # No permitir campos extra


class IGWebhookEntry(BaseModel):
    """Contrato: Entry de webhook de Instagram"""
    id: str
    time: int
    messaging: List[dict]


class IGWebhookPayload(BaseModel):
    """Contrato: Payload completo de webhook"""
    object: str  # "instagram"
    entry: List[IGWebhookEntry]


class IGSendResponse(BaseModel):
    """Contrato: Respuesta de envío de mensaje"""
    recipient_id: str
    message_id: str


class IGUserProfile(BaseModel):
    """Contrato: Perfil de usuario de Instagram"""
    id: str
    username: Optional[str] = None
    name: Optional[str] = None
    profile_pic: Optional[str] = None


# === TESTS DE CONTRATO ===

class TestInstagramMessageContract:
    """Tests de contrato para mensajes de Instagram"""

    def test_valid_text_message_payload(self):
        """Payload de mensaje de texto válido"""
        payload = {
            "recipient": {"id": "123456789"},
            "message": {"text": "Hola, ¿cómo estás?"}
        }
        validated = IGMessagePayload(**payload)
        assert validated.recipient["id"] == "123456789"

    def test_valid_attachment_payload(self):
        """Payload con attachment válido"""
        payload = {
            "recipient": {"id": "123456789"},
            "message": {
                "attachment": {
                    "type": "image",
                    "payload": {"url": "https://example.com/image.jpg"}
                }
            }
        }
        validated = IGMessagePayload(**payload)
        assert "attachment" in validated.message

    def test_invalid_extra_fields_rejected(self):
        """Campos extra son rechazados"""
        payload = {
            "recipient": {"id": "123"},
            "message": {"text": "test"},
            "extra_field": "not_allowed"
        }
        with pytest.raises(ValidationError):
            IGMessagePayload(**payload)

    def test_missing_recipient_rejected(self):
        """Falta recipient es rechazado"""
        payload = {"message": {"text": "test"}}
        with pytest.raises(ValidationError):
            IGMessagePayload(**payload)

    def test_missing_message_rejected(self):
        """Falta message es rechazado"""
        payload = {"recipient": {"id": "123"}}
        with pytest.raises(ValidationError):
            IGMessagePayload(**payload)


class TestInstagramWebhookContract:
    """Tests de contrato para webhooks de Instagram"""

    def test_valid_webhook_payload(self):
        """Webhook payload válido de Meta"""
        payload = {
            "object": "instagram",
            "entry": [{
                "id": "123456789",
                "time": 1704067200,
                "messaging": [{
                    "sender": {"id": "sender_123"},
                    "recipient": {"id": "recipient_456"},
                    "timestamp": 1704067200000,
                    "message": {
                        "mid": "msg_123",
                        "text": "Hola!"
                    }
                }]
            }]
        }
        validated = IGWebhookPayload(**payload)
        assert validated.object == "instagram"
        assert len(validated.entry) == 1

    def test_webhook_with_multiple_entries(self):
        """Webhook con múltiples entries"""
        payload = {
            "object": "instagram",
            "entry": [
                {"id": "1", "time": 1704067200, "messaging": []},
                {"id": "2", "time": 1704067201, "messaging": []}
            ]
        }
        validated = IGWebhookPayload(**payload)
        assert len(validated.entry) == 2

    def test_webhook_empty_entry_valid(self):
        """Webhook con entry vacío es válido"""
        payload = {
            "object": "instagram",
            "entry": []
        }
        validated = IGWebhookPayload(**payload)
        assert len(validated.entry) == 0

    def test_webhook_object_type_check(self):
        """Object type debe ser verificado en código"""
        payload = {
            "object": "facebook",
            "entry": []
        }
        validated = IGWebhookPayload(**payload)
        # Pasa validación pero código debe verificar object == "instagram"
        assert validated.object != "instagram"


class TestInstagramResponseContract:
    """Tests de contrato para respuestas de Instagram API"""

    def test_valid_send_response(self):
        """Respuesta válida de envío"""
        response = {
            "recipient_id": "123456789",
            "message_id": "mid.123456"
        }
        validated = IGSendResponse(**response)
        assert validated.message_id.startswith("mid.")

    def test_user_profile_minimal(self):
        """Perfil de usuario con campos mínimos"""
        profile = {"id": "123456789"}
        validated = IGUserProfile(**profile)
        assert validated.username is None
        assert validated.name is None

    def test_user_profile_complete(self):
        """Perfil de usuario completo"""
        profile = {
            "id": "123456789",
            "username": "creator_test",
            "name": "Test Creator",
            "profile_pic": "https://instagram.com/pic.jpg"
        }
        validated = IGUserProfile(**profile)
        assert validated.username == "creator_test"
        assert validated.name == "Test Creator"

    def test_user_profile_partial(self):
        """Perfil de usuario parcial (solo algunos campos)"""
        profile = {
            "id": "123456789",
            "username": "partial_user"
            # name y profile_pic omitidos
        }
        validated = IGUserProfile(**profile)
        assert validated.username == "partial_user"
        assert validated.name is None
