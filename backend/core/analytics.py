"""
Analytics System for Clonnect Creators.

Provides tracking and metrics for:
- Messages (sent/received by platform)
- Leads and conversions
- Intent distribution
- Funnel analysis

Storage: JSON files in data/analytics/
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from enum import Enum

logger = logging.getLogger("clonnect-analytics")


class EventType(Enum):
    """Types of analytics events"""
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    LEAD_CREATED = "lead_created"
    LEAD_UPDATED = "lead_updated"
    CONVERSION = "conversion"
    OBJECTION = "objection"
    ESCALATION = "escalation"
    NURTURING_SCHEDULED = "nurturing_scheduled"
    NURTURING_SENT = "nurturing_sent"


class Platform(Enum):
    """Supported platforms"""
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    WEB = "web"
    API = "api"


@dataclass
class AnalyticsEvent:
    """Single analytics event"""
    event_id: str
    event_type: str
    creator_id: str
    follower_id: str
    timestamp: str
    platform: str = "unknown"
    intent: str = ""
    product_id: str = ""
    amount: float = 0.0
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'AnalyticsEvent':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DailyStats:
    """Daily statistics"""
    date: str
    messages_received: int = 0
    messages_sent: int = 0
    unique_followers: int = 0
    new_leads: int = 0
    conversions: int = 0
    revenue: float = 0.0
    intents: Dict[str, int] = field(default_factory=dict)
    platforms: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FunnelStats:
    """Funnel statistics"""
    total_contacts: int = 0
    engaged: int = 0  # > 1 message
    interested: int = 0  # interest_soft or interest_strong
    leads: int = 0  # marked as lead
    high_intent: int = 0  # score > 0.5
    conversions: int = 0  # became customer

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def engagement_rate(self) -> float:
        return self.engaged / self.total_contacts if self.total_contacts > 0 else 0

    @property
    def lead_rate(self) -> float:
        return self.leads / self.total_contacts if self.total_contacts > 0 else 0

    @property
    def conversion_rate(self) -> float:
        return self.conversions / self.leads if self.leads > 0 else 0


class AnalyticsManager:
    """
    Manager for tracking and analyzing events.

    Stores events in JSON files per creator.
    """

    def __init__(self, storage_path: str = "data/analytics"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, List[AnalyticsEvent]] = {}

    def _get_events_file(self, creator_id: str) -> str:
        """Get path to events file for creator"""
        return os.path.join(self.storage_path, f"{creator_id}_events.json")

    def _get_stats_file(self, creator_id: str) -> str:
        """Get path to aggregated stats file"""
        return os.path.join(self.storage_path, f"{creator_id}_stats.json")

    def _load_events(self, creator_id: str) -> List[AnalyticsEvent]:
        """Load events for a creator"""
        if creator_id in self._cache:
            return self._cache[creator_id]

        file_path = self._get_events_file(creator_id)
        events = []

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    events = [AnalyticsEvent.from_dict(e) for e in data]
            except Exception as e:
                logger.error(f"Error loading events for {creator_id}: {e}")

        self._cache[creator_id] = events
        return events

    def _save_events(self, creator_id: str, events: List[AnalyticsEvent]):
        """Save events for a creator"""
        file_path = self._get_events_file(creator_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([e.to_dict() for e in events], f, indent=2, ensure_ascii=False)
            self._cache[creator_id] = events
        except Exception as e:
            logger.error(f"Error saving events for {creator_id}: {e}")

    def _generate_event_id(self) -> str:
        """Generate unique event ID"""
        import uuid
        return f"evt_{uuid.uuid4().hex[:12]}"

    def _add_event(self, event: AnalyticsEvent):
        """Add event to storage"""
        events = self._load_events(event.creator_id)
        events.append(event)

        # Keep last 10000 events max
        if len(events) > 10000:
            events = events[-10000:]

        self._save_events(event.creator_id, events)
        logger.debug(f"Analytics event: {event.event_type} for {event.creator_id}")

    # ==========================================================================
    # TRACKING METHODS
    # ==========================================================================

    def track_message(
        self,
        creator_id: str,
        follower_id: str,
        direction: str,  # "received" or "sent"
        intent: str = "",
        platform: str = "unknown",
        metadata: Dict[str, Any] = None
    ):
        """
        Track a message event.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            direction: "received" or "sent"
            intent: Detected intent (for received messages)
            platform: Source platform (instagram, whatsapp, telegram, etc.)
            metadata: Additional data
        """
        event_type = EventType.MESSAGE_RECEIVED.value if direction == "received" else EventType.MESSAGE_SENT.value

        event = AnalyticsEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            creator_id=creator_id,
            follower_id=follower_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=platform,
            intent=intent,
            metadata=metadata or {}
        )
        self._add_event(event)

    def track_conversion(
        self,
        creator_id: str,
        follower_id: str,
        product_id: str,
        amount: float,
        platform: str = "unknown",
        metadata: Dict[str, Any] = None
    ):
        """
        Track a conversion (purchase).

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            product_id: Product purchased
            amount: Purchase amount
            platform: Source platform
            metadata: Additional data
        """
        event = AnalyticsEvent(
            event_id=self._generate_event_id(),
            event_type=EventType.CONVERSION.value,
            creator_id=creator_id,
            follower_id=follower_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=platform,
            product_id=product_id,
            amount=amount,
            metadata=metadata or {}
        )
        self._add_event(event)
        logger.info(f"Conversion tracked: {follower_id} purchased {product_id} for {amount}")

    def track_lead(
        self,
        creator_id: str,
        follower_id: str,
        score: float,
        source: str = "dm",
        platform: str = "unknown",
        metadata: Dict[str, Any] = None
    ):
        """
        Track a lead creation or update.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            score: Lead score (0-1)
            source: Lead source (dm, landing, referral, etc.)
            platform: Source platform
            metadata: Additional data
        """
        event = AnalyticsEvent(
            event_id=self._generate_event_id(),
            event_type=EventType.LEAD_CREATED.value,
            creator_id=creator_id,
            follower_id=follower_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=platform,
            score=score,
            metadata={**(metadata or {}), "source": source}
        )
        self._add_event(event)

    def track_objection(
        self,
        creator_id: str,
        follower_id: str,
        objection_type: str,
        platform: str = "unknown",
        metadata: Dict[str, Any] = None
    ):
        """Track an objection raised by follower"""
        event = AnalyticsEvent(
            event_id=self._generate_event_id(),
            event_type=EventType.OBJECTION.value,
            creator_id=creator_id,
            follower_id=follower_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=platform,
            intent=objection_type,
            metadata=metadata or {}
        )
        self._add_event(event)

    def track_escalation(
        self,
        creator_id: str,
        follower_id: str,
        reason: str = "",
        platform: str = "unknown",
        metadata: Dict[str, Any] = None
    ):
        """Track an escalation to human"""
        event = AnalyticsEvent(
            event_id=self._generate_event_id(),
            event_type=EventType.ESCALATION.value,
            creator_id=creator_id,
            follower_id=follower_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=platform,
            metadata={**(metadata or {}), "reason": reason}
        )
        self._add_event(event)

    def track_nurturing(
        self,
        creator_id: str,
        follower_id: str,
        sequence_type: str,
        action: str = "scheduled",  # "scheduled" or "sent"
        platform: str = "unknown",
        metadata: Dict[str, Any] = None
    ):
        """Track nurturing events"""
        event_type = EventType.NURTURING_SCHEDULED.value if action == "scheduled" else EventType.NURTURING_SENT.value

        event = AnalyticsEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            creator_id=creator_id,
            follower_id=follower_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=platform,
            intent=sequence_type,
            metadata=metadata or {}
        )
        self._add_event(event)

    # ==========================================================================
    # METRICS METHODS
    # ==========================================================================

    def get_daily_stats(self, creator_id: str, date: str = None) -> DailyStats:
        """
        Get statistics for a specific day.

        Args:
            creator_id: Creator ID
            date: Date string (YYYY-MM-DD), defaults to today

        Returns:
            DailyStats object
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        events = self._load_events(creator_id)

        # Filter events for the date
        day_events = [
            e for e in events
            if e.timestamp.startswith(date)
        ]

        stats = DailyStats(date=date)
        unique_followers = set()
        leads_created = set()

        for event in day_events:
            unique_followers.add(event.follower_id)

            if event.event_type == EventType.MESSAGE_RECEIVED.value:
                stats.messages_received += 1
                if event.intent:
                    stats.intents[event.intent] = stats.intents.get(event.intent, 0) + 1
                if event.platform:
                    stats.platforms[event.platform] = stats.platforms.get(event.platform, 0) + 1

            elif event.event_type == EventType.MESSAGE_SENT.value:
                stats.messages_sent += 1

            elif event.event_type == EventType.LEAD_CREATED.value:
                leads_created.add(event.follower_id)

            elif event.event_type == EventType.CONVERSION.value:
                stats.conversions += 1
                stats.revenue += event.amount

        stats.unique_followers = len(unique_followers)
        stats.new_leads = len(leads_created)

        return stats

    def get_weekly_stats(self, creator_id: str, end_date: str = None) -> Dict[str, Any]:
        """
        Get statistics for the last 7 days.

        Args:
            creator_id: Creator ID
            end_date: End date (defaults to today)

        Returns:
            Weekly summary with daily breakdown
        """
        if end_date is None:
            end = datetime.now(timezone.utc)
        else:
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

        daily_stats = []
        totals = {
            "messages_received": 0,
            "messages_sent": 0,
            "unique_followers": set(),
            "new_leads": 0,
            "conversions": 0,
            "revenue": 0.0
        }

        for i in range(7):
            day = end - timedelta(days=i)
            date_str = day.strftime("%Y-%m-%d")
            stats = self.get_daily_stats(creator_id, date_str)
            daily_stats.append(stats.to_dict())

            totals["messages_received"] += stats.messages_received
            totals["messages_sent"] += stats.messages_sent
            totals["new_leads"] += stats.new_leads
            totals["conversions"] += stats.conversions
            totals["revenue"] += stats.revenue

        return {
            "period": "week",
            "start_date": (end - timedelta(days=6)).strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "totals": {
                "messages_received": totals["messages_received"],
                "messages_sent": totals["messages_sent"],
                "total_messages": totals["messages_received"] + totals["messages_sent"],
                "new_leads": totals["new_leads"],
                "conversions": totals["conversions"],
                "revenue": totals["revenue"]
            },
            "daily": list(reversed(daily_stats))  # Oldest first
        }

    def get_funnel_stats(self, creator_id: str, days: int = 30) -> FunnelStats:
        """
        Get funnel statistics.

        Args:
            creator_id: Creator ID
            days: Number of days to analyze

        Returns:
            FunnelStats object
        """
        events = self._load_events(creator_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        # Filter recent events
        recent_events = [e for e in events if e.timestamp >= cutoff_str]

        # Track followers through funnel
        followers_data: Dict[str, Dict[str, Any]] = {}

        for event in recent_events:
            fid = event.follower_id
            if fid not in followers_data:
                followers_data[fid] = {
                    "messages": 0,
                    "interested": False,
                    "is_lead": False,
                    "high_intent": False,
                    "converted": False
                }

            data = followers_data[fid]

            if event.event_type in [EventType.MESSAGE_RECEIVED.value, EventType.MESSAGE_SENT.value]:
                data["messages"] += 1

            if event.intent in ["interest_soft", "interest_strong"]:
                data["interested"] = True

            if event.event_type == EventType.LEAD_CREATED.value:
                data["is_lead"] = True
                if event.score > 0.5:
                    data["high_intent"] = True

            if event.event_type == EventType.CONVERSION.value:
                data["converted"] = True

        # Calculate funnel
        funnel = FunnelStats()
        funnel.total_contacts = len(followers_data)

        for data in followers_data.values():
            if data["messages"] > 1:
                funnel.engaged += 1
            if data["interested"]:
                funnel.interested += 1
            if data["is_lead"]:
                funnel.leads += 1
            if data["high_intent"]:
                funnel.high_intent += 1
            if data["converted"]:
                funnel.conversions += 1

        return funnel

    def get_platform_stats(self, creator_id: str, days: int = 30) -> Dict[str, Dict[str, int]]:
        """
        Get statistics broken down by platform.

        Args:
            creator_id: Creator ID
            days: Number of days to analyze

        Returns:
            Dict with platform stats
        """
        events = self._load_events(creator_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        recent_events = [e for e in events if e.timestamp >= cutoff_str]

        stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {
            "messages_received": 0,
            "messages_sent": 0,
            "leads": 0,
            "conversions": 0,
            "unique_followers": set()
        })

        for event in recent_events:
            platform = event.platform or "unknown"
            platform_stats = stats[platform]

            platform_stats["unique_followers"].add(event.follower_id)

            if event.event_type == EventType.MESSAGE_RECEIVED.value:
                platform_stats["messages_received"] += 1
            elif event.event_type == EventType.MESSAGE_SENT.value:
                platform_stats["messages_sent"] += 1
            elif event.event_type == EventType.LEAD_CREATED.value:
                platform_stats["leads"] += 1
            elif event.event_type == EventType.CONVERSION.value:
                platform_stats["conversions"] += 1

        # Convert sets to counts
        result = {}
        for platform, data in stats.items():
            result[platform] = {
                "messages_received": data["messages_received"],
                "messages_sent": data["messages_sent"],
                "total_messages": data["messages_received"] + data["messages_sent"],
                "leads": data["leads"],
                "conversions": data["conversions"],
                "unique_followers": len(data["unique_followers"])
            }

        return result

    def get_intent_distribution(self, creator_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get distribution of intents.

        Args:
            creator_id: Creator ID
            days: Number of days to analyze

        Returns:
            Dict with intent counts and percentages
        """
        events = self._load_events(creator_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        recent_events = [
            e for e in events
            if e.timestamp >= cutoff_str and e.event_type == EventType.MESSAGE_RECEIVED.value and e.intent
        ]

        intent_counts: Dict[str, int] = defaultdict(int)
        for event in recent_events:
            intent_counts[event.intent] += 1

        total = sum(intent_counts.values())

        # Calculate percentages
        distribution = {}
        for intent, count in sorted(intent_counts.items(), key=lambda x: x[1], reverse=True):
            distribution[intent] = {
                "count": count,
                "percentage": round(count / total * 100, 1) if total > 0 else 0
            }

        return {
            "total_messages": total,
            "period_days": days,
            "distribution": distribution
        }

    def get_objection_stats(self, creator_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get statistics about objections.

        Args:
            creator_id: Creator ID
            days: Number of days to analyze

        Returns:
            Dict with objection counts
        """
        events = self._load_events(creator_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        objection_events = [
            e for e in events
            if e.timestamp >= cutoff_str and e.event_type == EventType.OBJECTION.value
        ]

        objection_counts: Dict[str, int] = defaultdict(int)
        for event in objection_events:
            objection_counts[event.intent] += 1

        total = sum(objection_counts.values())

        return {
            "total_objections": total,
            "period_days": days,
            "by_type": dict(sorted(objection_counts.items(), key=lambda x: x[1], reverse=True))
        }

    def get_summary(self, creator_id: str) -> Dict[str, Any]:
        """
        Get complete analytics summary.

        Args:
            creator_id: Creator ID

        Returns:
            Complete summary dict
        """
        return {
            "creator_id": creator_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "today": self.get_daily_stats(creator_id).to_dict(),
            "weekly": self.get_weekly_stats(creator_id),
            "funnel": self.get_funnel_stats(creator_id).to_dict(),
            "platforms": self.get_platform_stats(creator_id),
            "intents": self.get_intent_distribution(creator_id),
            "objections": self.get_objection_stats(creator_id)
        }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_analytics_manager: Optional[AnalyticsManager] = None


def get_analytics_manager() -> AnalyticsManager:
    """Get or create analytics manager singleton"""
    global _analytics_manager
    if _analytics_manager is None:
        _analytics_manager = AnalyticsManager()
    return _analytics_manager


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def detect_platform(follower_id: str) -> str:
    """Detect platform from follower ID prefix"""
    if follower_id.startswith("ig_"):
        return Platform.INSTAGRAM.value
    elif follower_id.startswith("wa_"):
        return Platform.WHATSAPP.value
    elif follower_id.startswith("tg_"):
        return Platform.TELEGRAM.value
    elif follower_id.startswith("web_"):
        return Platform.WEB.value
    return Platform.API.value
