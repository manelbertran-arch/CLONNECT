# Audience Intelligence Architecture Design

**Version:** 1.0
**Created:** 2026-01-28
**Status:** Verified against codebase

---

## Section 1: Inventory of Existing Data

### 1.1 FollowerMemory (JSON Files)

**Location:** `data/followers/{creator_id}/{follower_id}.json`
**Source:** `core/dm_agent.py` (lines 154-190) and `core/memory.py`

```python
@dataclass
class FollowerMemory:
    # Identity
    follower_id: str
    creator_id: str
    username: str = ""
    name: str = ""

    # Timeline
    first_contact: str = ""
    last_contact: str = ""
    total_messages: int = 0

    # Profile (Inferred)
    interests: List[str] = []
    products_discussed: List[str] = []
    objections_raised: List[str] = []

    # Scoring
    purchase_intent_score: float = 0.0  # 0.0-1.0

    # State
    is_lead: bool = False
    is_customer: bool = False
    status: str = "new"  # new, active, hot, customer
    preferred_language: str = "es"

    # Conversation History
    last_messages: List[Dict] = []  # {role, content, timestamp}

    # Link Tracking
    links_sent_count: int = 0
    last_link_message_num: int = 0

    # Objection Handling
    objections_handled: List[str] = []
    arguments_used: List[str] = []

    # Variation Control
    greeting_variant_index: int = 0
    last_greeting_style: str = ""
    last_emojis_used: List[str] = []
    messages_since_name_used: int = 0

    # Alternative Contact
    alternative_contact: str = ""
    alternative_contact_type: str = ""  # whatsapp, telegram
    contact_requested: bool = False
```

**Total Fields:** 27

### 1.2 LeadStage Enum

**Location:** `services/lead_service.py` (lines 16-24)

```python
class LeadStage(str, Enum):
    NUEVO = "NUEVO"
    INTERESADO = "INTERESADO"
    CALIENTE = "CALIENTE"
    CLIENTE = "CLIENTE"
    FANTASMA = "FANTASMA"
```

### 1.3 LeadCategory Enum

**Location:** `core/lead_categorizer.py`

```python
class LeadCategory(Enum):
    NUEVO = "nuevo"
    INTERESADO = "interesado"
    CALIENTE = "caliente"
    CLIENTE = "cliente"
    FANTASMA = "fantasma"
```

### 1.4 Intent Classification

**Location:** `services/intent_service.py` (lines 11-53)

```python
class Intent(Enum):
    # Greetings and social
    GREETING = "greeting"
    GENERAL_CHAT = "general_chat"
    THANKS = "thanks"
    GOODBYE = "goodbye"

    # Interest levels
    INTEREST_SOFT = "interest_soft"
    INTEREST_STRONG = "interest_strong"
    PURCHASE_INTENT = "purchase_intent"

    # Acknowledgments
    ACKNOWLEDGMENT = "acknowledgment"
    CORRECTION = "correction"

    # Objections (8 types)
    OBJECTION_PRICE = "objection_price"
    OBJECTION_TIME = "objection_time"
    OBJECTION_DOUBT = "objection_doubt"
    OBJECTION_LATER = "objection_later"
    OBJECTION_WORKS = "objection_works"
    OBJECTION_NOT_FOR_ME = "objection_not_for_me"
    OBJECTION_COMPLICATED = "objection_complicated"
    OBJECTION_ALREADY_HAVE = "objection_already_have"

    # Questions
    QUESTION_PRODUCT = "question_product"
    QUESTION_GENERAL = "question_general"

    # Actions
    LEAD_MAGNET = "lead_magnet"
    BOOKING = "booking"

    # Support
    SUPPORT = "support"
    ESCALATION = "escalation"
    OTHER = "other"
```

### 1.5 Database Tables (PostgreSQL via Neon)

**Location:** `api/database.py` - SQLAlchemy with connection pooling

Tables identified in codebase:
- `leads` - Lead records
- `messages` - Message history (FK: lead_id)
- `lead_activities` - Activity log
- `lead_tasks` - Tasks per lead
- `nurturing_followups` - Scheduled follow-ups
- `weekly_reports` - Intelligence reports

### 1.6 Existing Services

**Location:** `services/` (2,015 lines total)

| Service | Lines | Purpose |
|---------|-------|---------|
| `lead_service.py` | 332 | Lead scoring, stage management |
| `intent_service.py` | 184 | Intent classification |
| `memory_service.py` | 309 | Follower memory management |
| `rag_service.py` | 337 | Knowledge retrieval |
| `llm_service.py` | 414 | LLM response generation |
| `prompt_service.py` | 214 | Prompt building |
| `instagram_service.py` | 196 | Instagram API |

### 1.7 Existing Routers

**Location:** `api/routers/` (23,189 lines total)

Key routers for Audience Intelligence:
- `dm.py` (745 lines) - `/dm/follower/{creator_id}/{follower_id}`
- `leads.py` (1,025 lines) - Lead CRUD operations
- `intelligence.py` (315 lines) - Predictions, recommendations
- `messages.py` (619 lines) - Message history

---

## Section 2: Architecture Proposed

```
+-----------------------------------------------------------------------+
|                       AUDIENCE INTELLIGENCE                            |
+-----------------------------------------------------------------------+
|                                                                        |
|  +------------------+    +------------------+    +------------------+  |
|  |   DATA SOURCES   |    |    SERVICES      |    |    ROUTERS       |  |
|  |   (Existing)     |--->|    (New/Extend)  |--->|    (New)         |  |
|  +------------------+    +------------------+    +------------------+  |
|                                                                        |
|  JSON Files:             services/               api/routers/          |
|  - data/followers/       - audience_service.py   - audience.py         |
|  - data/products/                                                      |
|                          Extends:                                      |
|  PostgreSQL:             - lead_service.py                             |
|  - leads                 - memory_service.py                           |
|  - messages                                                            |
|  - lead_activities                                                     |
|                                                                        |
+-----------------------------------------------------------------------+
```

---

## Section 3: New Service - audience_service.py

```python
# backend/services/audience_service.py
"""
Audience Intelligence Service.

Aggregates data from multiple sources to provide:
- Complete follower profiles
- Audience segmentation
- Aggregate metrics
- Predictions and recommendations
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import logging

from services.lead_service import LeadService, LeadStage
from services.memory_service import MemoryStore

logger = logging.getLogger(__name__)


class FunnelPhase(str, Enum):
    """Sales funnel phases."""
    INICIO = "inicio"
    CUALIFICACION = "cualificacion"
    DESCUBRIMIENTO = "descubrimiento"
    PROPUESTA = "propuesta"
    OBJECIONES = "objeciones"
    CIERRE = "cierre"


@dataclass
class AudienceProfile:
    """Complete follower profile aggregating all sources."""

    # Identity
    follower_id: str
    username: str
    name: str
    profile_pic_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

    # Funnel State
    phase: FunnelPhase = FunnelPhase.INICIO
    status: str = "nuevo"  # nuevo, interesado, caliente, cliente, fantasma
    purchase_intent: float = 0.0  # 0.0-1.0

    # Interests & Products
    interests: List[str] = field(default_factory=list)
    weighted_interests: Dict[str, float] = field(default_factory=dict)
    products_discussed: List[str] = field(default_factory=list)

    # Objections
    objections_raised: List[str] = field(default_factory=list)
    objections_handled: List[str] = field(default_factory=list)

    # Activity
    total_messages: int = 0
    first_contact: Optional[datetime] = None
    last_contact: Optional[datetime] = None
    days_since_contact: int = 0

    # Predictions
    purchase_probability: float = 0.0
    churn_risk: float = 0.0

    # Recommendations
    recommended_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "follower_id": self.follower_id,
            "username": self.username,
            "name": self.name,
            "profile_pic_url": self.profile_pic_url,
            "email": self.email,
            "phone": self.phone,
            "phase": self.phase.value,
            "status": self.status,
            "purchase_intent": self.purchase_intent,
            "interests": self.interests,
            "weighted_interests": self.weighted_interests,
            "products_discussed": self.products_discussed,
            "objections_raised": self.objections_raised,
            "objections_handled": self.objections_handled,
            "total_messages": self.total_messages,
            "first_contact": self.first_contact.isoformat() if self.first_contact else None,
            "last_contact": self.last_contact.isoformat() if self.last_contact else None,
            "days_since_contact": self.days_since_contact,
            "purchase_probability": self.purchase_probability,
            "churn_risk": self.churn_risk,
            "recommended_actions": self.recommended_actions,
        }


@dataclass
class AudienceSegment:
    """A segment of audience."""
    name: str
    icon: str
    criteria: str
    count: int
    action: str
    users: List[AudienceProfile] = field(default_factory=list)


@dataclass
class AudienceMetrics:
    """Aggregated audience metrics."""
    total_active: int
    funnel_distribution: Dict[str, int]
    top_interests: List[Tuple[str, int]]
    common_objections: List[Tuple[str, int]]
    products_demand: List[Tuple[str, int]]
    avg_messages_per_user: float
    conversion_rate: float


class AudienceService:
    """Main service for Audience Intelligence."""

    # Segment definitions
    SEGMENTS = {
        "hot_leads": {
            "name": "Hot Leads",
            "icon": "fire",
            "criteria": "purchase_intent > 0.7",
            "action": "Contacto personal urgente"
        },
        "warm_leads": {
            "name": "Warm Leads",
            "icon": "thermometer",
            "criteria": "purchase_intent 0.4-0.7 AND mensajes > 10",
            "action": "Nurturing activo"
        },
        "price_objectors": {
            "name": "Objecion Precio",
            "icon": "dollar",
            "criteria": "'precio' IN objections_raised",
            "action": "Ofrecer cuotas/descuento"
        },
        "time_objectors": {
            "name": "Objecion Tiempo",
            "icon": "clock",
            "criteria": "'tiempo' IN objections_raised",
            "action": "Mostrar que es rapido/facil"
        },
        "ghosts": {
            "name": "Ghosts",
            "icon": "ghost",
            "criteria": "dias_sin_actividad > 7",
            "action": "Re-engagement campaign"
        },
        "customers": {
            "name": "Clientes",
            "icon": "star",
            "criteria": "is_customer = true",
            "action": "Cross-sell, pedir testimonio"
        },
        "new": {
            "name": "Nuevos",
            "icon": "sparkle",
            "criteria": "mensajes < 3",
            "action": "Cualificacion inicial"
        }
    }

    def __init__(self):
        """Initialize service with dependencies."""
        self.lead_service = LeadService()
        self.memory_store = MemoryStore()
        logger.info("[AudienceService] Initialized")

    async def get_profile(
        self,
        creator_id: str,
        follower_id: str
    ) -> AudienceProfile:
        """
        Build complete profile aggregating all sources.

        Args:
            creator_id: Creator identifier
            follower_id: Follower identifier

        Returns:
            AudienceProfile with all data
        """
        # Load follower memory (JSON)
        follower = await self.memory_store.get_or_create(
            creator_id=creator_id,
            follower_id=follower_id,
            username=follower_id
        )

        # Calculate days since contact
        days_since = 0
        if follower.last_contact:
            try:
                last = datetime.fromisoformat(follower.last_contact.replace('Z', '+00:00'))
                days_since = (datetime.now(last.tzinfo) - last).days
            except Exception:
                pass

        # Determine funnel phase
        phase = self._determine_phase(follower)

        # Calculate predictions
        purchase_prob = self._predict_purchase_probability(follower, days_since)
        churn_risk = self._predict_churn_risk(follower, days_since)

        # Generate recommendations
        actions = self._recommend_actions(follower, phase, days_since)

        # Build weighted interests
        weighted = {}
        for i, interest in enumerate(follower.interests):
            # More recent = higher weight
            weight = 1.0 - (i * 0.1)
            weighted[interest] = max(0.1, weight)

        return AudienceProfile(
            follower_id=follower.follower_id,
            username=follower.username,
            name=follower.name,
            phase=phase,
            status=follower.status,
            purchase_intent=follower.purchase_intent_score,
            interests=follower.interests,
            weighted_interests=weighted,
            products_discussed=follower.products_discussed,
            objections_raised=follower.objections_raised,
            objections_handled=follower.objections_handled,
            total_messages=follower.total_messages,
            first_contact=datetime.fromisoformat(follower.first_contact) if follower.first_contact else None,
            last_contact=datetime.fromisoformat(follower.last_contact.replace('Z', '+00:00')) if follower.last_contact else None,
            days_since_contact=days_since,
            purchase_probability=purchase_prob,
            churn_risk=churn_risk,
            recommended_actions=actions,
        )

    def _determine_phase(self, follower) -> FunnelPhase:
        """Determine funnel phase from follower state."""
        if follower.is_customer:
            return FunnelPhase.CIERRE
        if follower.purchase_intent_score > 0.7:
            return FunnelPhase.PROPUESTA
        if follower.objections_raised:
            return FunnelPhase.OBJECIONES
        if follower.products_discussed:
            return FunnelPhase.DESCUBRIMIENTO
        if follower.total_messages > 3:
            return FunnelPhase.CUALIFICACION
        return FunnelPhase.INICIO

    def _predict_purchase_probability(
        self,
        follower,
        days_since: int
    ) -> float:
        """Calculate purchase probability 0.0-1.0."""
        score = 0.0

        # Intent directo (30%)
        score += follower.purchase_intent_score * 0.3

        # Fase del funnel (30%)
        phase_weights = {
            FunnelPhase.INICIO: 0.1,
            FunnelPhase.CUALIFICACION: 0.2,
            FunnelPhase.DESCUBRIMIENTO: 0.4,
            FunnelPhase.PROPUESTA: 0.7,
            FunnelPhase.OBJECIONES: 0.6,
            FunnelPhase.CIERRE: 0.9,
        }
        phase = self._determine_phase(follower)
        score += phase_weights.get(phase, 0.1) * 0.3

        # Engagement (20%)
        engagement = min(1.0, follower.total_messages / 50)
        score += engagement * 0.2

        # Penalty for objections (-5% each)
        score -= len(follower.objections_raised) * 0.05

        # Penalty for days without contact (-2% per day after 3)
        if days_since > 3:
            score -= (days_since - 3) * 0.02

        return max(0.0, min(1.0, score))

    def _predict_churn_risk(self, follower, days_since: int) -> float:
        """Calculate churn risk 0.0-1.0."""
        risk = 0.0

        # Days without contact (40%)
        risk += min(1.0, days_since / 14) * 0.4

        # Unresolved objections (30%)
        unresolved = set(follower.objections_raised) - set(follower.objections_handled)
        risk += min(1.0, len(unresolved) / 3) * 0.3

        # Low engagement (30%)
        if follower.total_messages < 5:
            risk += 0.3

        return max(0.0, min(1.0, risk))

    def _recommend_actions(
        self,
        follower,
        phase: FunnelPhase,
        days_since: int
    ) -> List[str]:
        """Generate personalized action recommendations."""
        actions = []

        # By specific objections
        if 'precio' in [o.lower() for o in follower.objections_raised]:
            actions.append("Ofrecer pago en cuotas o descuento")
        if 'tiempo' in [o.lower() for o in follower.objections_raised]:
            actions.append("Enviar testimonio de alguien ocupado que lo logro")
        if 'dudas' in [o.lower() for o in follower.objections_raised]:
            actions.append("Ofrecer call gratuita de 15 min")

        # By funnel phase
        if phase == FunnelPhase.PROPUESTA and follower.purchase_intent_score > 0.6:
            actions.insert(0, "Contactar HOY - esta listo para comprar")
        elif phase == FunnelPhase.DESCUBRIMIENTO:
            actions.append("Enviar caso de exito relevante")

        # By churn risk
        churn = self._predict_churn_risk(follower, days_since)
        if churn > 0.7:
            actions.insert(0, "Re-engagement urgente - puede perderse")

        # By days without contact
        if days_since > 5:
            actions.append(f"Han pasado {days_since} dias - hacer follow-up")

        return actions[:3]  # Max 3 actions

    async def get_segments(
        self,
        creator_id: str
    ) -> Dict[str, AudienceSegment]:
        """
        Get audience segmented by predefined criteria.

        Returns:
            Dict mapping segment_id to AudienceSegment
        """
        # Load all followers for creator
        followers = await self._load_all_followers(creator_id)

        segments = {}
        for seg_id, seg_def in self.SEGMENTS.items():
            segment_users = self._filter_segment(followers, seg_id)
            segments[seg_id] = AudienceSegment(
                name=seg_def["name"],
                icon=seg_def["icon"],
                criteria=seg_def["criteria"],
                count=len(segment_users),
                action=seg_def["action"],
                users=segment_users[:10]  # Top 10 only
            )

        return segments

    def _filter_segment(
        self,
        profiles: List[AudienceProfile],
        segment_id: str
    ) -> List[AudienceProfile]:
        """Filter profiles by segment criteria."""
        result = []

        for p in profiles:
            match = False

            if segment_id == "hot_leads":
                match = p.purchase_intent > 0.7
            elif segment_id == "warm_leads":
                match = 0.4 <= p.purchase_intent <= 0.7 and p.total_messages > 10
            elif segment_id == "price_objectors":
                match = any('precio' in o.lower() for o in p.objections_raised)
            elif segment_id == "time_objectors":
                match = any('tiempo' in o.lower() for o in p.objections_raised)
            elif segment_id == "ghosts":
                match = p.days_since_contact > 7 and p.status != "cliente"
            elif segment_id == "customers":
                match = p.status == "cliente"
            elif segment_id == "new":
                match = p.total_messages < 3

            if match:
                result.append(p)

        return result

    async def _load_all_followers(
        self,
        creator_id: str
    ) -> List[AudienceProfile]:
        """Load all follower profiles for a creator."""
        import os
        from pathlib import Path

        profiles = []
        folder = Path(f"data/followers/{creator_id}")

        if not folder.exists():
            return profiles

        for file in folder.glob("*.json"):
            follower_id = file.stem
            try:
                profile = await self.get_profile(creator_id, follower_id)
                profiles.append(profile)
            except Exception as e:
                logger.warning(f"Error loading {follower_id}: {e}")

        return profiles

    async def get_metrics(self, creator_id: str) -> AudienceMetrics:
        """
        Get aggregated audience metrics.

        Returns:
            AudienceMetrics with counts and distributions
        """
        profiles = await self._load_all_followers(creator_id)

        if not profiles:
            return AudienceMetrics(
                total_active=0,
                funnel_distribution={},
                top_interests=[],
                common_objections=[],
                products_demand=[],
                avg_messages_per_user=0.0,
                conversion_rate=0.0,
            )

        # Funnel distribution
        funnel = {}
        for phase in FunnelPhase:
            funnel[phase.value] = sum(1 for p in profiles if p.phase == phase)

        # Interest aggregation
        interest_counts: Dict[str, int] = {}
        for p in profiles:
            for interest in p.interests:
                interest_counts[interest] = interest_counts.get(interest, 0) + 1
        top_interests = sorted(interest_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Objection aggregation
        objection_counts: Dict[str, int] = {}
        for p in profiles:
            for obj in p.objections_raised:
                objection_counts[obj] = objection_counts.get(obj, 0) + 1
        common_objections = sorted(objection_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Product demand
        product_counts: Dict[str, int] = {}
        for p in profiles:
            for prod in p.products_discussed:
                product_counts[prod] = product_counts.get(prod, 0) + 1
        products_demand = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        # Averages
        total_messages = sum(p.total_messages for p in profiles)
        avg_messages = total_messages / len(profiles) if profiles else 0

        customers = sum(1 for p in profiles if p.status == "cliente")
        conversion_rate = customers / len(profiles) if profiles else 0

        return AudienceMetrics(
            total_active=len(profiles),
            funnel_distribution=funnel,
            top_interests=top_interests,
            common_objections=common_objections,
            products_demand=products_demand,
            avg_messages_per_user=avg_messages,
            conversion_rate=conversion_rate,
        )

    async def search(
        self,
        creator_id: str,
        interest: Optional[str] = None,
        phase: Optional[str] = None,
        min_intent: Optional[float] = None,
        objection: Optional[str] = None,
        limit: int = 50,
    ) -> List[AudienceProfile]:
        """
        Advanced search for followers.

        Args:
            creator_id: Creator identifier
            interest: Filter by interest
            phase: Filter by funnel phase
            min_intent: Minimum purchase intent score
            objection: Filter by objection type
            limit: Max results

        Returns:
            List of matching AudienceProfile
        """
        profiles = await self._load_all_followers(creator_id)

        # Apply filters
        if interest:
            profiles = [p for p in profiles if interest.lower() in [i.lower() for i in p.interests]]

        if phase:
            profiles = [p for p in profiles if p.phase.value == phase]

        if min_intent is not None:
            profiles = [p for p in profiles if p.purchase_intent >= min_intent]

        if objection:
            profiles = [p for p in profiles if objection.lower() in [o.lower() for o in p.objections_raised]]

        # Sort by purchase probability (most likely to convert first)
        profiles.sort(key=lambda p: p.purchase_probability, reverse=True)

        return profiles[:limit]


# Singleton instance
_audience_service: Optional[AudienceService] = None


def get_audience_service() -> AudienceService:
    """Get singleton instance of AudienceService."""
    global _audience_service
    if _audience_service is None:
        _audience_service = AudienceService()
    return _audience_service
```

---

## Section 4: New Router - audience.py

```python
# backend/api/routers/audience.py
"""
Audience Intelligence API endpoints.

Provides:
- Individual follower profiles
- Audience segmentation
- Aggregate metrics
- Advanced search
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional
import logging

from services.audience_service import (
    get_audience_service,
    AudienceProfile,
    AudienceSegment,
    AudienceMetrics,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audience", tags=["audience"])


@router.get("/{creator_id}/profile/{follower_id}")
async def get_follower_profile(
    creator_id: str,
    follower_id: str
) -> Dict:
    """
    Get complete profile for a single follower.

    Aggregates data from:
    - Follower memory (JSON)
    - Conversation history
    - Lead scoring
    - Predictions
    - Recommendations
    """
    service = get_audience_service()

    try:
        profile = await service.get_profile(creator_id, follower_id)
        return {
            "status": "ok",
            "profile": profile.to_dict()
        }
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/segments")
async def get_audience_segments(creator_id: str) -> Dict:
    """
    Get audience segmented by predefined criteria.

    Segments:
    - hot_leads: Purchase intent > 70%
    - warm_leads: Intent 40-70%, engaged
    - price_objectors: Raised price objection
    - time_objectors: Raised time objection
    - ghosts: Inactive > 7 days
    - customers: Converted customers
    - new: Less than 3 messages
    """
    service = get_audience_service()

    try:
        segments = await service.get_segments(creator_id)
        return {
            "status": "ok",
            "creator_id": creator_id,
            "segments": {
                k: {
                    "name": v.name,
                    "icon": v.icon,
                    "criteria": v.criteria,
                    "count": v.count,
                    "action": v.action,
                    "users": [u.to_dict() for u in v.users]
                }
                for k, v in segments.items()
            }
        }
    except Exception as e:
        logger.error(f"Error getting segments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/metrics")
async def get_audience_metrics(creator_id: str) -> Dict:
    """
    Get aggregated audience metrics.

    Returns:
    - Total active followers
    - Funnel distribution
    - Top interests
    - Common objections
    - Product demand
    - Conversion rate
    """
    service = get_audience_service()

    try:
        metrics = await service.get_metrics(creator_id)
        return {
            "status": "ok",
            "creator_id": creator_id,
            "metrics": {
                "total_active": metrics.total_active,
                "funnel_distribution": metrics.funnel_distribution,
                "top_interests": metrics.top_interests,
                "common_objections": metrics.common_objections,
                "products_demand": metrics.products_demand,
                "avg_messages_per_user": round(metrics.avg_messages_per_user, 1),
                "conversion_rate": round(metrics.conversion_rate * 100, 1),
            }
        }
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/search")
async def search_audience(
    creator_id: str,
    interest: Optional[str] = Query(None, description="Filter by interest"),
    phase: Optional[str] = Query(None, description="Filter by funnel phase"),
    min_intent: Optional[float] = Query(None, ge=0, le=1, description="Minimum purchase intent"),
    objection: Optional[str] = Query(None, description="Filter by objection type"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
) -> Dict:
    """
    Advanced search for followers.

    Filter by:
    - interest: Topic of interest
    - phase: Funnel phase (inicio, cualificacion, descubrimiento, propuesta, objeciones, cierre)
    - min_intent: Minimum purchase intent (0.0-1.0)
    - objection: Objection type raised
    """
    service = get_audience_service()

    try:
        profiles = await service.search(
            creator_id=creator_id,
            interest=interest,
            phase=phase,
            min_intent=min_intent,
            objection=objection,
            limit=limit,
        )
        return {
            "status": "ok",
            "creator_id": creator_id,
            "filters": {
                "interest": interest,
                "phase": phase,
                "min_intent": min_intent,
                "objection": objection,
            },
            "count": len(profiles),
            "results": [p.to_dict() for p in profiles]
        }
    except Exception as e:
        logger.error(f"Error searching audience: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Section 5: Files to Create

```
backend/
├── services/
│   └── audience_service.py    # NEW - Main service (est. 400 lines)
├── api/routers/
│   └── audience.py            # NEW - API router (est. 150 lines)
└── tests/
    └── test_audience_service.py  # NEW - TDD tests (est. 200 lines)
```

---

## Section 6: Files to Modify

```
backend/
├── api/main.py
│   # Add: from api.routers import audience
│   # Add: app.include_router(audience.router)
│
├── services/__init__.py
│   # Add: from services.audience_service import (
│   #     AudienceService, AudienceProfile, AudienceSegment, AudienceMetrics
│   # )
```

---

## Section 7: API Endpoints Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/audience/{creator_id}/profile/{follower_id}` | Full profile |
| GET | `/audience/{creator_id}/segments` | Audience segmentation |
| GET | `/audience/{creator_id}/metrics` | Aggregate metrics |
| GET | `/audience/{creator_id}/search` | Advanced search |

---

## Section 8: UI Mockup

```
+-------------------------------------------------------------------------+
|  TU COMUNIDAD                                            [ Buscar]      |
+-------------------------------------------------------------------------+
|                                                                          |
|  +-------------+  +-------------+  +-------------+  +-------------+     |
|  | Total       |  | Hot Leads   |  | Clientes    |  | Ghosts      |     |
|  |   1,234     |  |    45       |  |    89       |  |   234       |     |
|  +-------------+  +-------------+  +-------------+  +-------------+     |
|                                                                          |
+-------------------------------------------------------------------------+
|  SEGMENTOS                                                               |
|  +-------------------------------------------------------------------+  |
|  | Hot Leads (45)     | Warm Leads (156)  | Objecion Precio (234)   |  |
|  | Ghosts (234)       | Clientes (89)     | Nuevos (398)            |  |
|  +-------------------------------------------------------------------+  |
|                                                                          |
+-------------------------------------------------------------------------+
|  TOP INTERESES               |  POR QUE NO COMPRAN                      |
|  nutricion    45%            |  Precio        42%                       |
|  fitness      32%            |  Tiempo        28%                       |
|  recetas      18%            |  Dudas         16%                       |
+-------------------------------------------------------------------------+
|  LISTA DE SEGUIDORES                                   [ Filtrar ]      |
|  +-------------------------------------------------------------------+  |
|  | @maria_fit    | Maria Garcia    | CALIENTE | 78% | Hace 2h       |  |
|  | @carlos_123   | Carlos Lopez    | INTERESADO | 52% | Hace 1d     |  |
|  | @ana_wellness | Ana Martinez    | NUEVO    | 23% | Hace 3d       |  |
|  +-------------------------------------------------------------------+  |
+-------------------------------------------------------------------------+
```

---

## Section 9: Implementation Plan

### Sprint 1: Quick Wins (3-5 days)

- [ ] Create `services/audience_service.py` with TDD
- [ ] Create `api/routers/audience.py`
- [ ] Add router to `api/main.py`
- [ ] Verify with existing follower data

### Sprint 2: Frontend Integration (3-5 days)

- [ ] Create `Comunidad.tsx` page
- [ ] Add to navigation
- [ ] Connect to API endpoints
- [ ] Add basic styling

### Sprint 3: Polish (2-3 days)

- [ ] Add follower profile panel
- [ ] Integrate in Leads/Inbox pages
- [ ] Performance optimization
- [ ] Documentation

---

## Section 10: Compatibility Notes

### With dm_agent_v2.py

The service uses `MemoryStore` from `services/memory_service.py` which is compatible with the new architecture:

```python
from services.memory_service import MemoryStore
```

### With Existing Routers

Does NOT duplicate functionality from:
- `/dm/follower/{creator_id}/{follower_id}` - Basic follower data
- `/intelligence/{creator_id}/dashboard` - Pattern analysis

New endpoints ADD:
- Complete aggregated profiles
- Audience segmentation
- Advanced search filters

---

**Document verified against codebase on 2026-01-28**
