"""Demo data module for seeding realistic data."""

from .config import (
    CREATOR_ID,
    SEGMENT_DISTRIBUTION,
    PRODUCTS,
    METRICS,
    WEEKLY_INSIGHTS,
    TODAY_BOOKINGS,
)
from .names import SPANISH_NAMES, generate_username, generate_email
from .messages import (
    get_conversation_for_segment,
    HOT_LEAD_TEMPLATES,
    GHOST_TEMPLATES,
    OBJECTION_TEMPLATES,
)
from .interests import (
    TOPICS,
    PASSIONS,
    FRUSTRATIONS,
    PURCHASE_OBJECTIONS,
    INTERESTS_WEIGHTS,
)
