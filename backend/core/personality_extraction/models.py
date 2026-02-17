"""Data classes for personality extraction pipeline outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── Phase 0: Cleaning ──────────────────────────────────────────────

class MessageOrigin(str, Enum):
    CREATOR_REAL = "creator_real"
    COPILOT_AI = "copilot_ai"
    ORIGIN_UNCERTAIN = "origin_uncertain"
    LEAD = "lead"


@dataclass
class CleanedMessage:
    timestamp: datetime
    role: str  # "creator" or "lead"
    content: str
    origin: MessageOrigin
    msg_type: str = "text"  # text, story_reply, story_mention, audio, image, video, reel_share, link
    metadata: dict = field(default_factory=dict)


@dataclass
class CleanedConversation:
    lead_id: str
    username: str
    full_name: str
    platform: str
    messages: list[CleanedMessage] = field(default_factory=list)
    total_messages: int = 0
    creator_real_count: int = 0
    copilot_ai_count: int = 0
    uncertain_count: int = 0
    lead_count: int = 0
    first_message_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    content_types: set[str] = field(default_factory=set)


@dataclass
class CleaningStats:
    total_messages: int = 0
    creator_real: int = 0
    copilot_ai: int = 0
    uncertain: int = 0
    lead_messages: int = 0
    total_leads: int = 0
    leads_with_enough_data: int = 0  # >=3 creator real messages
    clean_ratio: float = 0.0  # creator_real / (creator_real + copilot_ai + uncertain)


# ── Phase 1: Doc A — Raw Conversations ─────────────────────────────

@dataclass
class FormattedConversation:
    lead_id: str
    username: str
    full_name: str
    header: str  # Formatted header block
    body: str  # Formatted conversation body
    total_messages: int = 0
    creator_real_count: int = 0
    copilot_excluded_count: int = 0
    lead_count: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    content_types: list[str] = field(default_factory=list)


# ── Phase 2: Doc B — Lead Analysis ─────────────────────────────────

class RelationType(str, Enum):
    COLD = "fría"
    WARM = "warm"
    TRUST = "confianza"
    FRIENDSHIP = "amistad"
    TRANSACTIONAL = "transaccional"
    B2B = "B2B"
    VENDOR = "vendor"
    CONFLICT = "conflicto"


class ResponseMode(str, Enum):
    AUTO = "AUTO"
    DRAFT = "DRAFT"
    MANUAL = "MANUAL"


@dataclass
class LeadAnalysis:
    lead_id: str
    username: str
    full_name: str
    total_messages: int = 0
    creator_real_count: int = 0
    lead_count: int = 0
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    # LLM-generated analysis (raw text per section)
    relationship_profile: str = ""
    conversation_nature: str = ""
    creator_patterns: str = ""
    lead_behavior: str = ""
    bot_classification: str = ""
    # Structured fields extracted from LLM
    relation_type: str = ""
    emotional_closeness: str = ""
    recommended_status: str = ""
    estimated_score: int = 0
    recommended_mode: str = "DRAFT"
    risk_level: str = "medium"


@dataclass
class SuperficialLead:
    username: str
    full_name: str
    message_count: int = 0
    probable_type: str = ""
    action: str = "monitorear"


# ── Phase 3: Doc C — Personality Profile ────────────────────────────

@dataclass
class WritingStyle:
    fragmentation_single_pct: float = 0.0
    fragmentation_multi_pct: float = 0.0
    avg_bubbles_per_turn: float = 1.0
    avg_message_length: float = 0.0
    median_message_length: float = 0.0
    p90_message_length: float = 0.0
    short_msgs_pct: float = 0.0  # < 30 chars
    medium_msgs_pct: float = 0.0  # < 60 chars
    long_msgs_pct: float = 0.0  # > 100 chars
    emoji_pct: float = 0.0
    avg_emojis_per_msg: float = 0.0
    max_emojis_observed: int = 0
    top_emojis: list[dict] = field(default_factory=list)  # [{emoji, count, context}]
    punctuation_patterns: dict = field(default_factory=dict)
    laugh_variants: list[dict] = field(default_factory=list)  # [{variant, count}]
    primary_language: str = "es"
    dialect: str = ""
    language_mix: dict = field(default_factory=dict)
    vowel_repetitions: list[dict] = field(default_factory=list)  # [{word, count}]
    dialect_details: dict = field(default_factory=dict)  # {voseo_matches, lunfardo_matches, tuteo_matches}


@dataclass
class CreatorDictionary:
    greetings: list[dict] = field(default_factory=list)  # [{phrase, count, context}]
    farewells: list[dict] = field(default_factory=list)
    gratitude: list[dict] = field(default_factory=list)
    validation: list[dict] = field(default_factory=list)
    confirmation: list[dict] = field(default_factory=list)
    laughter: list[dict] = field(default_factory=list)
    encouragement: list[dict] = field(default_factory=list)
    frequent_questions: list[dict] = field(default_factory=list)
    unique_catchphrases: list[dict] = field(default_factory=list)
    prohibited_vocabulary: list[dict] = field(default_factory=list)


@dataclass
class ToneAdaptation:
    context: str = ""  # e.g. "close_friends", "leads", "b2b"
    tone: str = ""
    length_vs_avg: str = ""
    emoji_vs_avg: str = ""
    example: str = ""


@dataclass
class SalesMethod:
    sells_via_dm: bool = False
    evidence: str = ""
    funnel_steps: list[str] = field(default_factory=list)
    sales_phrases: list[dict] = field(default_factory=list)  # [{phrase, context}]
    cross_sell_observed: str = ""
    uses_pressure: bool = False
    channel_migration_conditions: str = ""
    buy_signals: list[str] = field(default_factory=list)


@dataclass
class PersonalityProfile:
    creator_name: str = ""
    messages_analyzed: int = 0
    leads_analyzed: int = 0
    months_covered: int = 0
    confidence: str = "media"  # alta, media, baja
    # Identity
    identity_facts: dict = field(default_factory=dict)  # profession, location, etc.
    self_image: list[str] = field(default_factory=list)  # How creator describes themselves
    external_image: list[str] = field(default_factory=list)  # How leads describe creator
    # Writing style
    writing_style: WritingStyle = field(default_factory=WritingStyle)
    # Dictionary
    dictionary: CreatorDictionary = field(default_factory=CreatorDictionary)
    # Tone adaptation
    tone_adaptations: list[ToneAdaptation] = field(default_factory=list)
    # Sales method
    sales_method: SalesMethod = field(default_factory=SalesMethod)
    # Limitations
    limitations: list[str] = field(default_factory=list)
    # Raw LLM output (for debugging)
    raw_profile_text: str = ""


# ── Phase 4: Doc D — Bot Configuration ─────────────────────────────

@dataclass
class TemplateEntry:
    text: str
    context: str = ""
    observed_count: int = 0
    variables: list[str] = field(default_factory=list)


@dataclass
class TemplateCategory:
    category: str
    frequency_pct: float = 0.0
    risk_level: str = "low"
    mode: str = "AUTO"
    templates: list[TemplateEntry] = field(default_factory=list)


@dataclass
class MultiBubbleTemplate:
    template_id: str
    intent: str
    messages: list[str] = field(default_factory=list)
    risk: str = "low"
    mode: str = "AUTO"
    requires_context: bool = False
    source_leads: list[str] = field(default_factory=list)


@dataclass
class BotConfiguration:
    system_prompt: str = ""
    blacklist_phrases: list[str] = field(default_factory=list)
    max_message_length_chars: int = 200
    max_emojis_per_message: int = 3
    max_emojis_per_block: int = 5
    enforce_fragmentation: bool = False
    min_bubbles: int = 1
    max_bubbles: int = 3
    template_categories: list[TemplateCategory] = field(default_factory=list)
    multi_bubble_templates: list[MultiBubbleTemplate] = field(default_factory=list)


# ── Phase 5: Doc E — Copilot Rules ─────────────────────────────────

@dataclass
class CopilotRules:
    global_mode: str = "HYBRID"  # AUTOPILOT, COPILOT, HYBRID
    justification: str = ""
    predictability_score: float = 0.0
    systematizability_score: float = 0.0
    replicability_pct: float = 0.0
    # Distribution
    auto_pct: float = 0.0
    draft_pct: float = 0.0
    manual_pct: float = 0.0
    # Decision tree (text format)
    decision_tree: str = ""
    # Intent keywords
    intent_keywords: dict[str, list[str]] = field(default_factory=dict)
    # Quality rules
    quality_rules: list[str] = field(default_factory=list)
    # Raw LLM output
    raw_rules_text: str = ""


# ── Master Result ───────────────────────────────────────────────────

@dataclass
class ExtractionResult:
    creator_id: str
    creator_name: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    # Phase outputs
    cleaning_stats: CleaningStats = field(default_factory=CleaningStats)
    conversations: list[FormattedConversation] = field(default_factory=list)  # Doc A
    lead_analyses: list[LeadAnalysis] = field(default_factory=list)  # Doc B
    superficial_leads: list[SuperficialLead] = field(default_factory=list)  # Doc B supplement
    personality_profile: PersonalityProfile = field(default_factory=PersonalityProfile)  # Doc C
    bot_configuration: BotConfiguration = field(default_factory=BotConfiguration)  # Doc D
    copilot_rules: CopilotRules = field(default_factory=CopilotRules)  # Doc E
    # Errors
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
