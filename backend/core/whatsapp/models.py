"""
WhatsApp Business API data models.

Dataclasses and enums for WhatsApp message processing.
"""

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("clonnect-whatsapp")


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class WhatsAppMessage:
    """Represents a WhatsApp message"""

    message_id: str
    sender_id: str  # Phone number (wa_id)
    recipient_id: str
    text: str
    timestamp: datetime
    message_type: str = "text"  # text, image, audio, video, document, etc.
    sender_name: str = ""  # Profile name from contacts[].profile.name
    attachments: List[dict] = None
    context: Dict[str, Any] = None  # Reply context

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []
        if self.context is None:
            self.context = {}


@dataclass
class WhatsAppContact:
    """Represents a WhatsApp contact"""

    wa_id: str  # WhatsApp ID (phone number)
    profile_name: str = ""
    phone_number: str = ""


@dataclass
class WhatsAppHandlerStatus:
    """Status of the WhatsApp handler"""

    connected: bool = False
    phone_number_id: str = ""
    messages_received: int = 0
    messages_sent: int = 0
    last_message_time: Optional[str] = None
    errors: int = 0
    started_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
