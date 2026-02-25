"""
WhatsApp Business API Connector and Handler for Clonnect Creators.

Provides WhatsApp Cloud API integration for DM processing.
Follows the same pattern as instagram.py and instagram_handler.py.

Required environment variables:
- WHATSAPP_PHONE_NUMBER_ID: WhatsApp Business phone number ID
- WHATSAPP_ACCESS_TOKEN: Meta Graph API access token
- WHATSAPP_VERIFY_TOKEN: Token for webhook verification
"""

from core.whatsapp.connector import (
    WhatsAppConnector,
    register_phone_number,
    subscribe_waba_webhooks,
)
from core.whatsapp.handler import WhatsAppHandler, get_whatsapp_handler
from core.whatsapp.models import (
    WhatsAppContact,
    WhatsAppHandlerStatus,
    WhatsAppMessage,
)

__all__ = [
    "WhatsAppMessage",
    "WhatsAppContact",
    "WhatsAppHandlerStatus",
    "WhatsAppConnector",
    "WhatsAppHandler",
    "register_phone_number",
    "subscribe_waba_webhooks",
    "get_whatsapp_handler",
]
