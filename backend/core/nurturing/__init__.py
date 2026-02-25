"""
Nurturing Manager - Sistema de follow-ups automaticos para Clonnect Creators.

Gestiona secuencias de mensajes automatizados para:
- Leads que mostraron interes pero no compraron
- Usuarios con objeciones
- Carritos abandonados (preguntaron como comprar pero no lo hicieron)
"""

from core.nurturing.models import (
    FollowUp,
    NURTURING_SEQUENCES,
    SequenceType,
)
from core.nurturing.utils import (
    activate_default_sequences,
    DEFAULT_ACTIVE_SEQUENCES,
    get_sequence_steps,
    INTENT_TO_SEQUENCE,
    is_sequence_active,
    render_template,
    should_schedule_nurturing,
    TESTING_MODE,
)
from core.nurturing.manager import (
    get_nurturing_manager,
    NurturingManager,
)

__all__ = [
    # Models
    "SequenceType",
    "FollowUp",
    "NURTURING_SEQUENCES",
    # Utils
    "render_template",
    "get_sequence_steps",
    "is_sequence_active",
    "should_schedule_nurturing",
    "activate_default_sequences",
    "INTENT_TO_SEQUENCE",
    "DEFAULT_ACTIVE_SEQUENCES",
    "TESTING_MODE",
    # Manager
    "NurturingManager",
    "get_nurturing_manager",
]
