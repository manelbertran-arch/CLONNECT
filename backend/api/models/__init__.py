"""
Clonnect SQLAlchemy models — split by domain.

All models are re-exported here for backward compatibility.
Import from here: `from api.models import Lead, Creator, Message`
"""

try:
    from api.database import Base
except ImportError:
    from database import Base

# Auth
from api.models.auth import User, UserCreator

# Creator
from api.models.creator import (
    Creator, CreatorAvailability, ToneProfile,
    StyleProfileModel, PersonalityDoc, RelationshipDNAModel,
)

# Lead
from api.models.lead import (
    Lead, UnifiedLead, UnmatchedWebhook, LeadActivity, LeadTask,
    DismissedLead, LeadIntelligence, LeadMemory,
)

# Message
from api.models.message import (
    Message, ConversationStateDB, ConversationSummary,
    ConversationEmbedding, CommitmentModel, PendingMessage,
)

# Product
from api.models.product import Product, ProductAnalytics

# Content
from api.models.content import (
    ContentChunk, InstagramPost, PostContextModel,
    ContentPerformance, RAGDocument, KnowledgeBase,
)

# Booking
from api.models.booking import BookingLink, CalendarBooking, BookingSlot

# Nurturing
from api.models.nurturing import NurturingSequence, EmailAskTracking

# Learning
from api.models.learning import (
    CopilotEvaluation, LearningRule, GoldExample,
    PatternAnalysisRun, PreferencePair,
    CloneScoreEvaluation, CloneScoreTestSet,
    LLMUsageLog,
)

# Analytics
from api.models.analytics import (
    CreatorMetricsDaily, Prediction, Recommendation,
    DetectedTopic, WeeklyReport, CSATRating,
)

# Profile
from api.models.profile import (
    UnifiedProfile, PlatformIdentity,
    FollowerMemoryDB, UserProfileDB,
)

# Sync
from api.models.sync import SyncQueue, SyncState

# Re-export all for star imports
__all__ = [
    "Base",
    "User", "UserCreator",
    "Creator", "CreatorAvailability", "ToneProfile",
    "StyleProfileModel", "PersonalityDoc", "RelationshipDNAModel",
    "Lead", "UnifiedLead", "UnmatchedWebhook", "LeadActivity", "LeadTask",
    "DismissedLead", "LeadIntelligence", "LeadMemory",
    "Message", "ConversationStateDB", "ConversationSummary",
    "ConversationEmbedding", "CommitmentModel", "PendingMessage",
    "Product", "ProductAnalytics",
    "ContentChunk", "InstagramPost", "PostContextModel",
    "ContentPerformance", "RAGDocument", "KnowledgeBase",
    "BookingLink", "CalendarBooking", "BookingSlot",
    "NurturingSequence", "EmailAskTracking",
    "CopilotEvaluation", "LearningRule", "GoldExample",
    "PatternAnalysisRun", "PreferencePair",
    "CloneScoreEvaluation", "CloneScoreTestSet",
    "LLMUsageLog",
    "CreatorMetricsDaily", "Prediction", "Recommendation",
    "DetectedTopic", "WeeklyReport", "CSATRating",
    "UnifiedProfile", "PlatformIdentity",
    "FollowerMemoryDB", "UserProfileDB",
    "SyncQueue", "SyncState",
]
