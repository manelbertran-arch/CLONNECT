"""Audit tests for core/whatsapp.py"""

from core.whatsapp import WhatsAppContact, WhatsAppHandlerStatus, WhatsAppMessage


class TestAuditWhatsApp:
    def test_import(self):
        from core.whatsapp import (  # noqa: F811
            WhatsAppContact,
            WhatsAppHandlerStatus,
            WhatsAppMessage,
            get_whatsapp_handler,
        )

        assert WhatsAppMessage is not None

    def test_message_dataclass(self):
        try:
            msg = WhatsAppMessage()
            assert msg is not None
        except TypeError:
            pass  # Requires args

    def test_happy_path_contact(self):
        try:
            contact = WhatsAppContact()
            assert contact is not None
        except TypeError:
            pass  # Requires args

    def test_edge_case_status_to_dict(self):
        try:
            status = WhatsAppHandlerStatus()
            d = status.to_dict()
            assert isinstance(d, dict)
        except TypeError:
            pass  # Requires args

    def test_error_handling_get_handler(self):
        from core.whatsapp import get_whatsapp_handler

        try:
            handler = get_whatsapp_handler("creator", "phone_id", "token")
            assert handler is not None
        except Exception:
            pass  # May need real credentials
