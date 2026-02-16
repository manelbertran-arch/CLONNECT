"""
User Context Loader - Unified user data loading for LLM context injection.

This module loads ALL user/follower data for personalizing responses:
- From FollowerMemory (JSON): conversation history, scores, interests
- From UserProfile (JSON): preferences, communication style
- From Lead table (PostgreSQL): CRM status, tags, deal value

Used for context injection into LLM prompts for personalized responses.
"""

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Check if PostgreSQL is available
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)


@dataclass
class ConversationMessage:
    """A single message in conversation history."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMessage":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class LeadInfo:
    """CRM lead information from PostgreSQL."""

    id: str = ""
    status: str = "nuevo"  # nuevo, interesado, caliente, cliente, fantasma
    score: int = 0
    purchase_intent: float = 0.0
    deal_value: float = 0.0
    tags: List[str] = field(default_factory=list)
    source: str = ""
    notes: str = ""
    email: str = ""
    phone: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_db_row(cls, row) -> "LeadInfo":
        """Create from SQLAlchemy Lead model."""
        return cls(
            id=str(row.id) if row.id else "",
            status=row.status or "nuevo",
            score=row.score or 0,
            purchase_intent=float(row.purchase_intent or 0),
            deal_value=float(row.deal_value or 0) if row.deal_value else 0.0,
            tags=row.tags or [],
            source=row.source or "",
            notes=row.notes or "",
            email=row.email or "",
            phone=row.phone or "",
        )


@dataclass
class UserPreferences:
    """User communication preferences."""

    language: str = "es"
    response_style: str = "balanced"  # concise, balanced, detailed
    communication_tone: str = "friendly"  # formal, friendly, casual

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class UserContext:
    """
    Complete user context for LLM personalization.

    Aggregates data from:
    - FollowerMemory (JSON storage)
    - UserProfile (JSON storage)
    - Lead table (PostgreSQL)
    """

    # Identity
    follower_id: str
    creator_id: str
    username: str = ""
    name: str = ""

    # Preferences (from UserProfile)
    preferences: UserPreferences = field(default_factory=UserPreferences)

    # Interests and history (from FollowerMemory + UserProfile)
    interests: List[str] = field(default_factory=list)
    top_interests: List[str] = field(default_factory=list)  # Weighted top 5
    products_discussed: List[str] = field(default_factory=list)
    objections_raised: List[str] = field(default_factory=list)

    # Scores (from FollowerMemory)
    purchase_intent_score: float = 0.0
    engagement_score: float = 0.0

    # Status flags (from FollowerMemory)
    is_lead: bool = False
    is_customer: bool = False

    # Conversation (from FollowerMemory)
    conversation_summary: str = ""
    last_messages: List[ConversationMessage] = field(default_factory=list)
    total_messages: int = 0

    # CRM data (from Lead table)
    lead_info: LeadInfo = field(default_factory=LeadInfo)

    # Computed flags
    is_first_message: bool = True
    is_returning_user: bool = False
    days_since_last_contact: int = 0

    # Timestamps
    first_contact: str = ""
    last_contact: str = ""
    loaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # --- Computed properties ---

    def get_display_name(self) -> str:
        """Get best available name for addressing user."""
        if self.name:
            return self.name
        if self.username:
            return self.username
        return "amigo"

    def get_conversation_length(self) -> str:
        """Classify conversation length for prompt context."""
        if self.total_messages == 0:
            return "new"
        elif self.total_messages <= 3:
            return "short"
        elif self.total_messages <= 10:
            return "medium"
        else:
            return "long"

    def get_engagement_level(self) -> str:
        """Classify engagement level for prompt context."""
        if self.engagement_score >= 0.7:
            return "high"
        elif self.engagement_score >= 0.3:
            return "medium"
        else:
            return "low"

    def get_purchase_intent_level(self) -> str:
        """Classify purchase intent for prompt context."""
        if self.purchase_intent_score >= 0.7:
            return "high"
        elif self.purchase_intent_score >= 0.4:
            return "medium"
        else:
            return "low"

    def has_tag(self, tag: str) -> bool:
        """Check if user has a specific CRM tag."""
        return tag.lower() in [t.lower() for t in self.lead_info.tags]

    def is_vip(self) -> bool:
        """Check if user is marked as VIP."""
        return self.has_tag("vip") or self.is_customer

    def is_price_sensitive(self) -> bool:
        """Check if user has shown price sensitivity."""
        return self.has_tag("price_sensitive") or "precio" in self.objections_raised

    def get_recent_messages(self, limit: int = 5) -> List[ConversationMessage]:
        """Get most recent messages."""
        return self.last_messages[-limit:] if self.last_messages else []

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "follower_id": self.follower_id,
            "creator_id": self.creator_id,
            "username": self.username,
            "name": self.name,
            "preferences": self.preferences.to_dict(),
            "interests": self.interests,
            "top_interests": self.top_interests,
            "products_discussed": self.products_discussed,
            "objections_raised": self.objections_raised,
            "purchase_intent_score": self.purchase_intent_score,
            "engagement_score": self.engagement_score,
            "is_lead": self.is_lead,
            "is_customer": self.is_customer,
            "conversation_summary": self.conversation_summary,
            "last_messages": [m.to_dict() for m in self.last_messages],
            "total_messages": self.total_messages,
            "lead_info": self.lead_info.to_dict(),
            "is_first_message": self.is_first_message,
            "is_returning_user": self.is_returning_user,
            "days_since_last_contact": self.days_since_last_contact,
            "first_contact": self.first_contact,
            "last_contact": self.last_contact,
            "loaded_at": self.loaded_at,
        }


# =============================================================================
# MAIN LOADER FUNCTION
# =============================================================================


def _parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse ISO datetime string to datetime object."""
    if not dt_str:
        return None
    try:
        # Handle various ISO formats
        dt_str = dt_str.replace("Z", "+00:00")
        if "+" not in dt_str and "-" not in dt_str[10:]:
            dt_str += "+00:00"
        return datetime.fromisoformat(dt_str)
    except (ValueError, TypeError):
        return None


def _calculate_days_since(dt_str: str) -> int:
    """Calculate days since a datetime string."""
    dt = _parse_datetime(dt_str)
    if not dt:
        return 0
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    return max(0, delta.days)


def load_user_context(
    creator_id: str,
    follower_id: str,
    username: str = "",
    name: str = "",
) -> UserContext:
    """
    Load complete user context from all sources.

    This is the main entry point. It loads data from:
    1. FollowerMemory (JSON) - conversation history, scores
    2. UserProfile (JSON) - preferences, weighted interests
    3. Lead table (PostgreSQL) - CRM data

    Args:
        creator_id: Creator name (e.g., 'stefano')
        follower_id: Platform user ID (e.g., 'ig_123', 'tg_456')
        username: Optional username hint
        name: Optional name hint

    Returns:
        UserContext with all available data
    """
    context = UserContext(
        follower_id=follower_id,
        creator_id=creator_id,
        username=username,
        name=name,
    )

    # 1. Load from FollowerMemory (JSON)
    _load_from_follower_memory(context)

    # 2. Load from UserProfile (JSON)
    _load_from_user_profile(context)

    # 3. Load from Lead table (PostgreSQL)
    _load_from_lead_table(context)

    # 4. Calculate computed flags
    _calculate_flags(context)

    logger.debug(
        f"UserContext loaded for {follower_id}: "
        f"messages={context.total_messages}, "
        f"is_first={context.is_first_message}, "
        f"days_since={context.days_since_last_contact}"
    )

    return context


def _load_from_follower_memory(context: UserContext):
    """Load data from FollowerMemory (JSON storage)."""
    try:
        from core.memory import MemoryStore

        store = MemoryStore()
        # Use sync approach - MemoryStore.get is async but we need sync here
        # Read directly from file
        import json
        from pathlib import Path

        file_path = Path(store.storage_path) / context.creator_id / f"{context.follower_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Fill context from memory data
            context.username = data.get("username", context.username) or context.username
            context.name = data.get("name", context.name) or context.name
            context.interests = data.get("interests", []) or []
            context.products_discussed = data.get("products_discussed", []) or []
            context.objections_raised = data.get("objections_raised", []) or []
            context.purchase_intent_score = float(data.get("purchase_intent_score", 0) or 0)
            context.engagement_score = float(data.get("engagement_score", 0) or 0)
            context.is_lead = bool(data.get("is_lead", False))
            context.is_customer = bool(data.get("is_customer", False))
            context.conversation_summary = data.get("conversation_summary", "") or ""
            context.total_messages = int(data.get("total_messages", 0) or 0)
            context.first_contact = data.get("first_contact", "") or ""
            context.last_contact = data.get("last_contact", "") or ""

            # Load last messages
            raw_messages = data.get("last_messages", []) or []
            context.last_messages = [ConversationMessage.from_dict(m) for m in raw_messages[-20:]]

            # Set preferred language if available
            if data.get("preferred_language"):
                context.preferences.language = data["preferred_language"]

            logger.debug(f"Loaded FollowerMemory for {context.follower_id}")

    except Exception as e:
        logger.debug(f"Could not load FollowerMemory: {e}")


def _load_from_user_profile(context: UserContext):
    """Load data from UserProfile (JSON storage)."""
    try:
        from core.user_profiles import get_user_profile

        profile = get_user_profile(context.follower_id, context.creator_id)
        profile_data = profile.to_dict()

        # Preferences
        prefs = profile_data.get("preferences", {})
        context.preferences.language = prefs.get("language", context.preferences.language)
        context.preferences.response_style = prefs.get("response_style", "balanced")
        context.preferences.communication_tone = prefs.get("communication_tone", "friendly")

        # Top interests (weighted)
        interests_dict = profile_data.get("interests", {})
        if interests_dict:
            sorted_interests = sorted(interests_dict.items(), key=lambda x: x[1], reverse=True)
            context.top_interests = [topic for topic, _ in sorted_interests[:5]]
            # Merge with existing interests
            for topic in context.top_interests:
                if topic not in context.interests:
                    context.interests.append(topic)

        # Objections from profile
        profile_objections = profile_data.get("objections", [])
        for obj in profile_objections:
            obj_type = obj.get("type", "") if isinstance(obj, dict) else str(obj)
            if obj_type and obj_type not in context.objections_raised:
                context.objections_raised.append(obj_type)

        logger.debug(f"Loaded UserProfile for {context.follower_id}")

    except Exception as e:
        logger.debug(f"Could not load UserProfile: {e}")


def _load_from_lead_table(context: UserContext):
    """Load data from Lead table (PostgreSQL)."""
    if not USE_POSTGRES:
        return

    try:
        from api.database import SessionLocal

        if SessionLocal is None:
            return
    except ImportError:
        return

    session = SessionLocal()
    try:
        from api.models import Creator, Lead

        # Get creator
        creator = session.query(Creator).filter_by(name=context.creator_id).first()
        if not creator:
            return

        # Get lead by platform_user_id
        lead = (
            session.query(Lead)
            .filter_by(creator_id=creator.id, platform_user_id=context.follower_id)
            .first()
        )

        if lead:
            context.lead_info = LeadInfo.from_db_row(lead)

            # Override some fields from lead if available
            if lead.full_name and not context.name:
                context.name = lead.full_name
            if lead.username and not context.username:
                context.username = lead.username

            # Update customer status from lead status
            if lead.status == "cliente":
                context.is_customer = True
            if lead.status in ["caliente", "cliente", "colaborador"]:
                context.is_lead = True

            logger.debug(f"Loaded Lead info for {context.follower_id}: status={lead.status}")

    except Exception as e:
        logger.error(f"Error loading Lead data: {e}")
    finally:
        session.close()


def _calculate_flags(context: UserContext):
    """Calculate computed flags based on loaded data."""
    # is_first_message: no messages in history
    context.is_first_message = len(context.last_messages) == 0 and context.total_messages == 0

    # days_since_last_contact
    context.days_since_last_contact = _calculate_days_since(context.last_contact)

    # is_returning_user: has history and >7 days since last contact
    context.is_returning_user = (
        context.total_messages > 0 and context.days_since_last_contact >= 7
    )


# =============================================================================
# CACHE LAYER
# =============================================================================

_user_context_cache: Dict[str, UserContext] = {}
_cache_timestamps: Dict[str, float] = {}
_CACHE_TTL_SECONDS = 60  # 1 minute (shorter than creator data)


def get_user_context(
    creator_id: str,
    follower_id: str,
    username: str = "",
    name: str = "",
    use_cache: bool = True,
) -> UserContext:
    """
    Get user context with optional caching.

    Args:
        creator_id: Creator name
        follower_id: Platform user ID
        username: Optional username
        name: Optional name
        use_cache: Whether to use cached data (default True)

    Returns:
        UserContext instance
    """
    import time

    cache_key = f"{creator_id}:{follower_id}"

    if use_cache and cache_key in _user_context_cache:
        cache_age = time.time() - _cache_timestamps.get(cache_key, 0)
        if cache_age < _CACHE_TTL_SECONDS:
            logger.debug(f"Using cached UserContext for {cache_key}")
            return _user_context_cache[cache_key]

    # Load fresh data
    context = load_user_context(creator_id, follower_id, username, name)

    # Cache it
    _user_context_cache[cache_key] = context
    _cache_timestamps[cache_key] = time.time()

    return context


def invalidate_user_cache(creator_id: str, follower_id: str):
    """Invalidate cached data for a user."""
    cache_key = f"{creator_id}:{follower_id}"
    if cache_key in _user_context_cache:
        del _user_context_cache[cache_key]
    if cache_key in _cache_timestamps:
        del _cache_timestamps[cache_key]


def clear_all_user_cache():
    """Clear all cached user data."""
    _user_context_cache.clear()
    _cache_timestamps.clear()


# =============================================================================
# PROMPT FORMATTING HELPERS
# =============================================================================


def format_user_context_for_prompt(context: UserContext) -> str:
    """
    Format user context as text for LLM prompt injection.

    Returns a structured text block suitable for system prompts.
    """
    lines = ["=== CONTEXTO DEL USUARIO ==="]

    # Name
    display_name = context.get_display_name()
    if display_name != "amigo":
        lines.append(f"- Nombre: {display_name}")

    # Language
    if context.preferences.language != "es":
        lines.append(f"- Idioma preferido: {context.preferences.language}")

    # Communication preferences
    if context.preferences.response_style != "balanced":
        style_desc = {
            "concise": "Prefiere respuestas cortas y directas",
            "detailed": "Prefiere explicaciones detalladas",
        }.get(context.preferences.response_style, "")
        if style_desc:
            lines.append(f"- {style_desc}")

    if context.preferences.communication_tone != "friendly":
        tone_desc = {
            "formal": "Prefiere trato formal (usted)",
            "casual": "Prefiere trato muy informal",
        }.get(context.preferences.communication_tone, "")
        if tone_desc:
            lines.append(f"- {tone_desc}")

    # Interests
    if context.top_interests:
        lines.append(f"- Intereses: {', '.join(context.top_interests[:3])}")

    # Products discussed
    if context.products_discussed:
        lines.append(f"- Productos que le interesan: {', '.join(context.products_discussed[-3:])}")

    # Objections
    if context.objections_raised:
        lines.append(f"- Objeciones mencionadas: {', '.join(context.objections_raised[-3:])}")

    # Status flags
    status_flags = []
    if context.is_customer:
        status_flags.append("CLIENTE")
    elif context.is_lead:
        if context.purchase_intent_score >= 0.7:
            status_flags.append("LEAD CALIENTE")
        else:
            status_flags.append("LEAD")
    if context.is_vip():
        status_flags.append("VIP")
    if context.is_price_sensitive():
        status_flags.append("sensible al precio")

    if status_flags:
        lines.append(f"- Estado: {', '.join(status_flags)}")

    # Conversation context
    conv_length = context.get_conversation_length()
    if conv_length == "new":
        lines.append("- PRIMER MENSAJE - Dar bienvenida")
    elif context.is_returning_user:
        lines.append(f"- Usuario que vuelve despues de {context.days_since_last_contact} dias")
    elif conv_length == "long":
        lines.append(f"- Conversacion activa ({context.total_messages} mensajes)")

    if len(lines) == 1:
        return ""  # No context to add

    return "\n".join(lines)


def format_conversation_history_for_prompt(
    context: UserContext, max_messages: int = 10
) -> str:
    """
    Format recent conversation history for LLM prompt.

    Args:
        context: User context
        max_messages: Maximum messages to include

    Returns:
        Formatted conversation history
    """
    messages = context.get_recent_messages(max_messages)
    if not messages:
        return ""

    lines = ["=== HISTORIAL RECIENTE ==="]
    for msg in messages:
        role_label = "Usuario" if msg.role == "user" else "Bot"
        content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
        lines.append(f"{role_label}: {content}")

    return "\n".join(lines)


def build_user_context_prompt(
    creator_id: str,
    follower_id: str,
    include_history: bool = True,
    max_history_messages: int = 6,
    username: str = "",
    name: str = "",
) -> str:
    """
    Build complete user context for LLM prompt injection.

    Args:
        creator_id: Creator name
        follower_id: Platform user ID
        include_history: Include conversation history
        max_history_messages: Max messages in history
        username: Optional username
        name: Optional name

    Returns:
        Formatted context string for prompt injection
    """
    context = get_user_context(creator_id, follower_id, username, name)

    sections = []

    # User context section
    user_section = format_user_context_for_prompt(context)
    if user_section:
        sections.append(user_section)

    # Conversation history section
    if include_history:
        history_section = format_conversation_history_for_prompt(context, max_history_messages)
        if history_section:
            sections.append(history_section)

    if not sections:
        return ""

    return "\n\n".join(sections)
