"""
Pydantic schemas for Audience/Follower endpoints.

SPRINT1-T1.1: Extended follower detail response unifying:
- follower_memories (basic data)
- leads (CRM fields)
- conversation_states (sales funnel)
- user_profiles (weighted interests)
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageSummary(BaseModel):
    """Summary of a message in conversation history."""

    role: str = Field(description="Message role: 'user' or 'assistant'")
    content: str = Field(description="Message content")
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp")


class FollowerDetailResponse(BaseModel):
    """
    Unified follower profile combining data from multiple sources.

    Sources:
    - follower_memories: Basic interaction data
    - leads: CRM fields (email, phone, notes, deal_value)
    - conversation_states: Sales funnel position
    - user_profiles: Weighted interests and preferences
    """

    # === Core Identity (from follower_memories) ===
    follower_id: str = Field(description="Unique follower identifier (platform prefixed)")
    username: Optional[str] = Field(default=None, description="Platform username")
    name: Optional[str] = Field(default=None, description="Display name")
    platform: Optional[str] = Field(default=None, description="Platform: instagram, telegram, whatsapp")
    profile_pic_url: Optional[str] = Field(default=None, description="Profile picture URL")

    # === Timestamps ===
    first_contact: Optional[str] = Field(default=None, description="First interaction timestamp")
    last_contact: Optional[str] = Field(default=None, description="Last interaction timestamp")

    # === Interaction Stats (from follower_memories) ===
    total_messages: int = Field(default=0, description="Total message count")
    interests: List[str] = Field(default_factory=list, description="Detected interests (unweighted)")
    products_discussed: List[str] = Field(default_factory=list, description="Products mentioned")
    objections_raised: List[str] = Field(default_factory=list, description="Objections raised")

    # === Lead Scoring (from follower_memories) ===
    purchase_intent_score: float = Field(default=0.0, description="Purchase intent 0.0-1.0")
    is_lead: bool = Field(default=False, description="Marked as lead")
    is_customer: bool = Field(default=False, description="Has made purchase")
    status: Optional[str] = Field(default=None, description="Lead status: nuevo, interesado, caliente, cliente, fantasma")

    # === Preferences (from follower_memories) ===
    preferred_language: Optional[str] = Field(default="es", description="Preferred language code")

    # === Conversation History (from follower_memories) ===
    last_messages: List[Dict[str, Any]] = Field(
        default_factory=list, description="Last 10 messages in conversation"
    )

    # === CRM Fields (from leads table) ===
    email: Optional[str] = Field(default=None, description="Captured email address")
    phone: Optional[str] = Field(default=None, description="Captured phone number")
    notes: Optional[str] = Field(default=None, description="Free-form CRM notes")
    deal_value: Optional[float] = Field(default=None, description="Potential deal value in EUR")
    tags: List[str] = Field(default_factory=list, description="CRM tags: vip, price_sensitive, etc.")
    source: Optional[str] = Field(default=None, description="Lead source: instagram_dm, story_reply, ad_click")
    assigned_to: Optional[str] = Field(default=None, description="Team member assignment")

    # === Sales Funnel (from conversation_states) ===
    funnel_phase: Optional[str] = Field(
        default=None,
        description="Sales funnel phase: inicio, cualificacion, descubrimiento, propuesta, objeciones, cierre, escalar",
    )
    funnel_context: Dict[str, Any] = Field(
        default_factory=dict, description="Accumulated conversation context (UserContext)"
    )

    # === Behavior Profile (from user_profiles) ===
    weighted_interests: Dict[str, float] = Field(
        default_factory=dict, description="Interests with weights: {topic: weight}"
    )
    preferences: Dict[str, Any] = Field(
        default_factory=dict, description="User preferences: {language, tone, response_style}"
    )
    interested_products: List[Dict[str, Any]] = Field(
        default_factory=list, description="Products of interest with engagement data"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "follower_id": "ig_123456789",
                "username": "fitness_fan",
                "name": "Maria Garcia",
                "platform": "instagram",
                "profile_pic_url": "https://cdn.instagram.com/...",
                "first_contact": "2024-01-15T10:30:00Z",
                "last_contact": "2024-01-28T14:20:00Z",
                "total_messages": 15,
                "interests": ["fitness", "nutrition"],
                "products_discussed": ["curso_fitpack"],
                "objections_raised": ["price"],
                "purchase_intent_score": 0.75,
                "is_lead": True,
                "is_customer": False,
                "status": "caliente",
                "preferred_language": "es",
                "last_messages": [
                    {"role": "user", "content": "Hola!", "timestamp": "2024-01-28T14:20:00Z"}
                ],
                "email": "maria@example.com",
                "phone": "+34600123456",
                "notes": "Very interested in the premium plan",
                "deal_value": 297.0,
                "tags": ["vip", "engaged"],
                "source": "story_reply",
                "assigned_to": None,
                "funnel_phase": "propuesta",
                "funnel_context": {"pain_points": ["time"], "budget": "medium"},
                "weighted_interests": {"fitness": 0.9, "nutrition": 0.6},
                "preferences": {"language": "es", "tone": "friendly"},
                "interested_products": [{"id": "prod_1", "name": "FitPack", "interest_count": 3}],
            }
        }
