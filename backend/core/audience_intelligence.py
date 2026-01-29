"""
Audience Intelligence Module (SPRINT1-T1.2)

Provides intelligent audience profiling with:
- Narrative context generation
- Automatic segment detection
- Action recommendations
- Objection handling suggestions

This module builds on the raw data from T1.1 to provide
actionable insights for creators.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class AudienceProfile:
    """
    Complete audience profile with intelligence layer.

    Combines raw data with:
    - Human-readable narrative
    - Auto-detected segments
    - Recommended actions
    - Objection suggestions
    """

    # Core identity
    follower_id: str
    username: Optional[str] = None
    name: Optional[str] = None
    platform: Optional[str] = None
    profile_pic_url: Optional[str] = None

    # Timestamps
    first_contact: Optional[str] = None
    last_contact: Optional[str] = None

    # Interaction stats
    total_messages: int = 0
    interests: List[str] = field(default_factory=list)
    products_discussed: List[str] = field(default_factory=list)

    # Lead scoring
    purchase_intent_score: float = 0.0
    is_lead: bool = False
    is_customer: bool = False

    # Funnel position
    funnel_phase: Optional[str] = None
    funnel_context: Dict[str, Any] = field(default_factory=dict)

    # Intelligence layer (computed)
    narrative: Optional[str] = None
    segments: List[str] = field(default_factory=list)
    recommended_action: Optional[str] = None
    action_priority: Optional[str] = None  # low, medium, high, urgent
    objections: List[Dict[str, Any]] = field(default_factory=list)

    # Computed metrics
    days_inactive: int = 0
    last_message_role: Optional[str] = None

    # CRM data (from Lead table)
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "follower_id": self.follower_id,
            "username": self.username,
            "name": self.name,
            "platform": self.platform,
            "profile_pic_url": self.profile_pic_url,
            "first_contact": self.first_contact,
            "last_contact": self.last_contact,
            "total_messages": self.total_messages,
            "interests": self.interests,
            "products_discussed": self.products_discussed,
            "purchase_intent_score": self.purchase_intent_score,
            "is_lead": self.is_lead,
            "is_customer": self.is_customer,
            "funnel_phase": self.funnel_phase,
            "funnel_context": self.funnel_context,
            "narrative": self.narrative,
            "segments": self.segments,
            "recommended_action": self.recommended_action,
            "action_priority": self.action_priority,
            "objections": self.objections,
            "days_inactive": self.days_inactive,
            "last_message_role": self.last_message_role,
            "email": self.email,
            "phone": self.phone,
            "notes": self.notes,
        }


# =============================================================================
# PROFILE DATA (intermediate structure for segment detection)
# =============================================================================


@dataclass
class ProfileData:
    """Intermediate data structure for segment detection rules."""

    purchase_intent_score: float = 0.0
    funnel_phase: Optional[str] = None
    is_customer: bool = False
    total_messages: int = 0
    days_inactive: int = 0
    last_message_role: Optional[str] = None
    objections_raised: List[str] = field(default_factory=list)
    objections_handled: List[str] = field(default_factory=list)
    segments: List[str] = field(default_factory=list)
    name: Optional[str] = None
    funnel_context: Dict[str, Any] = field(default_factory=dict)
    interests: List[str] = field(default_factory=list)


# =============================================================================
# AUDIENCE PROFILE BUILDER
# =============================================================================


class AudienceProfileBuilder:
    """
    Builds intelligent audience profiles with context and recommendations.

    Features:
    - Narrative generation from context
    - Automatic segment detection
    - Action recommendations with priority
    - Objection handling suggestions
    """

    # Suggestions for each objection type
    OBJECTION_SUGGESTIONS: Dict[str, str] = {
        "precio": "Ofrece pago en cuotas o destaca el ROI del programa",
        "tiempo": "Enfatiza que solo son 15 minutos al día y resultados rápidos",
        "duda": "Comparte testimonios de clientes en situación similar",
        "despues": "Crea urgencia con oferta limitada o bonus exclusivo",
        "funciona": "Muestra casos de éxito con datos concretos y garantía",
        "no_para_mi": "Pregunta qué situación específica tiene para personalizar",
        "complicado": "Explica que es paso a paso, ideal para principiantes",
        "ya_tengo": "Diferencia tu producto: qué tiene que otros no ofrecen",
    }

    # Default suggestion for unknown objections
    DEFAULT_OBJECTION_SUGGESTION = "Escucha activamente y pregunta más detalles sobre su preocupación"

    # Segment detection rules
    SEGMENT_RULES: Dict[str, Callable[[ProfileData], bool]] = {
        "hot_lead": lambda p: p.purchase_intent_score > 0.7 and p.funnel_phase in ["propuesta", "cierre"],
        "warm_lead": lambda p: 0.4 <= p.purchase_intent_score <= 0.7 and not p.is_customer,
        "ghost": lambda p: p.days_inactive > 7 and p.last_message_role == "assistant",
        "price_objector": lambda p: "precio" in (p.objections_raised or []),
        "time_objector": lambda p: "tiempo" in (p.objections_raised or []),
        "customer": lambda p: p.is_customer,
        "new": lambda p: p.total_messages < 3,
    }

    def __init__(self, creator_id: str, db: Any = None):
        """
        Initialize the profile builder.

        Args:
            creator_id: Creator identifier
            db: Database session (optional, for direct DB queries)
        """
        self.creator_id = creator_id
        self.db = db
        logger.debug(f"AudienceProfileBuilder initialized for {creator_id}")

    async def build_profile(self, follower_id: str) -> Optional[AudienceProfile]:
        """
        Build a complete audience profile with intelligence.

        Args:
            follower_id: Platform-prefixed follower ID

        Returns:
            AudienceProfile with narrative, segments, and recommendations
            or None if follower not found
        """
        # Fetch raw data
        raw_data = await self._fetch_follower_data(follower_id)

        if not raw_data:
            return None

        # Calculate computed fields
        days_inactive = self._calculate_days_inactive(raw_data.get("last_contact"))
        last_message_role = self._get_last_message_role(raw_data.get("last_messages", []))

        # Create intermediate ProfileData for segment detection
        profile_data = ProfileData(
            purchase_intent_score=raw_data.get("purchase_intent_score", 0.0),
            funnel_phase=raw_data.get("funnel_phase"),
            is_customer=raw_data.get("is_customer", False),
            total_messages=raw_data.get("total_messages", 0),
            days_inactive=days_inactive,
            last_message_role=last_message_role,
            objections_raised=raw_data.get("objections_raised", []),
            objections_handled=raw_data.get("objections_handled", []),
            name=raw_data.get("name"),
            funnel_context=raw_data.get("funnel_context", {}),
            interests=raw_data.get("interests", []),
        )

        # Detect segments
        segments = self._detect_segments(profile_data)
        profile_data.segments = segments

        # Get action recommendation
        action, priority = self._recommend_action(profile_data)

        # Generate narrative
        narrative = self._generate_narrative(profile_data)

        # Build objections with suggestions
        objections = self._build_objections_with_suggestions(
            raw_data.get("objections_raised", []),
            raw_data.get("objections_handled", []),
        )

        # Build final profile
        return AudienceProfile(
            follower_id=follower_id,
            username=raw_data.get("username"),
            name=raw_data.get("name"),
            platform=raw_data.get("platform"),
            profile_pic_url=raw_data.get("profile_pic_url"),
            first_contact=raw_data.get("first_contact"),
            last_contact=raw_data.get("last_contact"),
            total_messages=raw_data.get("total_messages", 0),
            interests=raw_data.get("interests", []),
            products_discussed=raw_data.get("products_discussed", []),
            purchase_intent_score=raw_data.get("purchase_intent_score", 0.0),
            is_lead=raw_data.get("is_lead", False),
            is_customer=raw_data.get("is_customer", False),
            funnel_phase=raw_data.get("funnel_phase") or "inicio",
            funnel_context=raw_data.get("funnel_context", {}),
            narrative=narrative,
            segments=segments,
            recommended_action=action,
            action_priority=priority,
            objections=objections,
            days_inactive=days_inactive,
            last_message_role=last_message_role,
            email=raw_data.get("email"),
            phone=raw_data.get("phone"),
            notes=raw_data.get("notes"),
        )

    def _detect_segments(self, profile_data: ProfileData) -> List[str]:
        """
        Detect segments based on profile data.

        Applies all segment rules and returns matching segments.

        Args:
            profile_data: ProfileData with current state

        Returns:
            List of matching segment names
        """
        segments = []

        for segment_name, rule in self.SEGMENT_RULES.items():
            try:
                if rule(profile_data):
                    segments.append(segment_name)
            except Exception as e:
                logger.warning(f"Error evaluating segment {segment_name}: {e}")

        return segments

    def _recommend_action(self, profile_data: ProfileData) -> Tuple[str, str]:
        """
        Recommend next action based on profile state.

        Args:
            profile_data: ProfileData with segments

        Returns:
            Tuple of (action_text, priority)
        """
        segments = profile_data.segments

        # Priority 1: Hot lead ready to close
        if "hot_lead" in segments and profile_data.funnel_phase in ["propuesta", "cierre"]:
            return ("Envía el link de pago y cierra la venta", "urgent")

        # Priority 2: Customer - nurture
        if "customer" in segments:
            return ("Solicita testimonio o ofrece upsell", "low")

        # Priority 3: Has pending objections
        pending_objections = [
            obj for obj in profile_data.objections_raised
            if obj not in profile_data.objections_handled
        ]
        if pending_objections:
            first_objection = pending_objections[0]
            suggestion = self.OBJECTION_SUGGESTIONS.get(
                first_objection, self.DEFAULT_OBJECTION_SUGGESTION
            )
            return (f"Maneja objeción de '{first_objection}': {suggestion}", "high")

        # Priority 4: Ghost - reactivate
        if "ghost" in segments:
            return (
                f"Reactivar: llevan {profile_data.days_inactive} días sin responder. "
                "Envía mensaje de seguimiento personalizado",
                "medium"
            )

        # Priority 5: Warm lead - nurture
        if "warm_lead" in segments:
            return ("Continúa nurturing: comparte contenido de valor o caso de éxito", "medium")

        # Priority 6: New lead - qualify
        if "new" in segments:
            return ("Cualifica: pregunta sobre su situación y objetivos", "medium")

        # Default
        return ("Mantener conversación y detectar necesidades", "low")

    def _generate_narrative(self, profile_data: ProfileData) -> str:
        """
        Generate human-readable narrative from profile context.

        Args:
            profile_data: ProfileData with context

        Returns:
            Narrative string like "Madre de 3. Quiere bajar peso. Le preocupa el tiempo."
        """
        parts = []

        # Name
        if profile_data.name:
            parts.append(profile_data.name)

        # Context from funnel_context
        context = profile_data.funnel_context or {}

        # Family/personal info
        if context.get("family"):
            parts.append(str(context["family"]).capitalize())

        # Goals
        goals = context.get("goals", [])
        if goals:
            if isinstance(goals, list) and goals:
                parts.append(f"Quiere {goals[0]}")
            elif isinstance(goals, str):
                parts.append(f"Quiere {goals}")

        # Pain points
        pain_points = context.get("pain_points", [])
        if pain_points:
            if isinstance(pain_points, list) and pain_points:
                parts.append(f"Le preocupa {pain_points[0]}")
            elif isinstance(pain_points, str):
                parts.append(f"Le preocupa {pain_points}")

        # Interests
        if profile_data.interests and not parts:
            interests_str = ", ".join(profile_data.interests[:2])
            parts.append(f"Interesado en {interests_str}")

        # Objections
        if profile_data.objections_raised:
            obj = profile_data.objections_raised[0]
            parts.append(f"Objeción: {obj}")

        # Build narrative
        if not parts:
            return "Nuevo contacto. Sin información de contexto todavía."

        return ". ".join(parts) + "."

    def _build_objections_with_suggestions(
        self,
        raised: List[str],
        handled: List[str],
    ) -> List[Dict[str, Any]]:
        """
        Build objection list with handling suggestions.

        Args:
            raised: List of objection types raised
            handled: List of objection types already handled

        Returns:
            List of dicts with type, handled, suggestion
        """
        objections = []

        for objection_type in raised:
            suggestion = self.OBJECTION_SUGGESTIONS.get(
                objection_type,
                self.DEFAULT_OBJECTION_SUGGESTION,
            )

            objections.append({
                "type": objection_type,
                "handled": objection_type in handled,
                "suggestion": suggestion,
            })

        return objections

    async def _fetch_follower_data(self, follower_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch follower data from PostgreSQL database.

        Queries FollowerMemoryDB, Lead, ConversationStateDB, and UserProfileDB
        to build a unified profile.

        Args:
            follower_id: Platform-prefixed follower ID

        Returns:
            Dict with follower data or None
        """
        try:
            from api.database import SessionLocal
            from api.models import FollowerMemoryDB, Lead, ConversationStateDB, UserProfileDB

            db = SessionLocal()
            if not db:
                logger.warning("Database not available")
                return None

            try:
                # Query FollowerMemoryDB (primary source)
                follower = db.query(FollowerMemoryDB).filter(
                    FollowerMemoryDB.creator_id == self.creator_id,
                    FollowerMemoryDB.follower_id == follower_id,
                ).first()

                if not follower:
                    logger.debug(f"Follower {follower_id} not found in follower_memories")
                    return None

                # Build base result
                result = {
                    "follower_id": follower.follower_id,
                    "username": follower.username,
                    "name": follower.name,
                    "platform": "instagram" if follower_id.startswith("ig_") else "unknown",
                    "profile_pic_url": None,
                    "first_contact": follower.first_contact,
                    "last_contact": follower.last_contact,
                    "total_messages": follower.total_messages or 0,
                    "interests": follower.interests or [],
                    "products_discussed": follower.products_discussed or [],
                    "objections_raised": follower.objections_raised or [],
                    "objections_handled": follower.objections_handled or [],
                    "purchase_intent_score": follower.purchase_intent_score or 0.0,
                    "is_lead": follower.is_lead,
                    "is_customer": follower.is_customer,
                    "status": follower.status,
                    "last_messages": follower.last_messages or [],
                    # Defaults for enrichment
                    "email": None,
                    "phone": None,
                    "notes": None,
                    "deal_value": None,
                    "funnel_phase": None,
                    "funnel_context": {},
                }

                # Enrich from Lead table (CRM data)
                lead = db.query(Lead).filter(
                    Lead.platform_user_id == follower_id,
                ).first()
                if lead:
                    result["profile_pic_url"] = lead.profile_pic_url
                    result["email"] = lead.email
                    result["phone"] = lead.phone
                    result["notes"] = lead.notes
                    result["deal_value"] = lead.deal_value

                # Enrich from ConversationStateDB (funnel data)
                conv_state = db.query(ConversationStateDB).filter(
                    ConversationStateDB.creator_id == self.creator_id,
                    ConversationStateDB.follower_id == follower_id,
                ).first()
                if conv_state:
                    result["funnel_phase"] = conv_state.phase
                    result["funnel_context"] = conv_state.context or {}

                return result

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error fetching follower data: {e}")
            return None

    def _calculate_days_inactive(self, last_contact: Optional[str]) -> int:
        """Calculate days since last contact."""
        if not last_contact:
            return 0

        try:
            # Handle ISO format with or without timezone
            if "T" in last_contact:
                last_dt = datetime.fromisoformat(last_contact.replace("Z", "+00:00"))
            else:
                last_dt = datetime.fromisoformat(last_contact)

            # Make naive if needed for comparison
            if last_dt.tzinfo:
                last_dt = last_dt.replace(tzinfo=None)

            delta = datetime.now() - last_dt
            return max(0, delta.days)

        except Exception as e:
            logger.warning(f"Could not parse last_contact '{last_contact}': {e}")
            return 0

    def _get_last_message_role(self, messages: List[Dict]) -> Optional[str]:
        """Get the role of the last message in conversation."""
        if not messages:
            return None

        last_msg = messages[-1] if messages else None
        if isinstance(last_msg, dict):
            return last_msg.get("role")

        return None


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def get_audience_profile_builder(creator_id: str, db: Any = None) -> AudienceProfileBuilder:
    """
    Factory function to create an AudienceProfileBuilder.

    Args:
        creator_id: Creator identifier
        db: Optional database session

    Returns:
        AudienceProfileBuilder instance
    """
    return AudienceProfileBuilder(creator_id=creator_id, db=db)
