"""RelationshipDNA models for personalized communication per lead.

This module contains the data models for storing relationship-specific
context between creators and their leads, enabling personalized
communication style based on relationship type.

Part of RELATIONSHIP-DNA feature.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Optional
from uuid import uuid4


class RelationshipType(str, Enum):
    """Types of relationships between creator and lead.

    Used to determine communication style and vocabulary.
    Each type has specific vocabulary rules:

    - FAMILIA: Family member - warm, personal, never sell
    - INTIMA: Romantic/very close - uses 💙, vulnerable tone, no "hermano"
    - AMISTAD_CERCANA: Close friend - uses "hermano", "bro", spiritual tone
    - AMISTAD_CASUAL: Casual friend - uses "crack", light and fun tone
    - CLIENTE: Client/prospect - informative, helpful, professional but warm
    - COLABORADOR: Business partner - professional, respectful
    - DESCONOCIDO: New lead - neutral, no assumptions
    """

    FAMILIA = "FAMILIA"
    INTIMA = "INTIMA"
    AMISTAD_CERCANA = "AMISTAD_CERCANA"
    AMISTAD_CASUAL = "AMISTAD_CASUAL"
    CLIENTE = "CLIENTE"
    COLABORADOR = "COLABORADOR"
    DESCONOCIDO = "DESCONOCIDO"


@dataclass
class RelationshipDNA:
    """Stores relationship-specific context between creator and lead.

    This enables personalized communication style per relationship,
    not just per creator. Each lead can have unique vocabulary,
    tone, and interaction patterns.

    Attributes:
        creator_id: The creator's unique identifier
        follower_id: The lead/follower's unique identifier
        relationship_type: Classification of the relationship
        trust_score: 0.0-1.0 indicating relationship trust level
        depth_level: 0-4 based on conversation history depth
        vocabulary_uses: Words/phrases to use with this lead
        vocabulary_avoids: Words/phrases to avoid with this lead
        emojis: Emojis appropriate for this relationship
        avg_message_length: Average message length in characters
        questions_frequency: 0.0-1.0 how often to ask questions
        multi_message_frequency: 0.0-1.0 how often to send multiple messages
        tone_description: Text description of tone to use
        recurring_topics: Topics that come up frequently
        private_references: Inside jokes, shared memories
        bot_instructions: Generated instructions for the bot
        golden_examples: Representative conversation examples
        total_messages_analyzed: Number of messages used for analysis
        last_analyzed_at: When the DNA was last updated
        version: Version number for tracking updates
        created_at: When the record was created
        updated_at: When the record was last modified
    """

    # Required fields
    creator_id: str
    follower_id: str

    # Relationship classification
    relationship_type: str = field(default_factory=lambda: RelationshipType.DESCONOCIDO.value)
    trust_score: float = 0.0
    depth_level: int = 0

    # Vocabulary specific to this relationship
    vocabulary_uses: List[str] = field(default_factory=list)
    vocabulary_avoids: List[str] = field(default_factory=list)
    emojis: List[str] = field(default_factory=list)

    # Interaction patterns
    avg_message_length: Optional[int] = None
    questions_frequency: Optional[float] = None
    multi_message_frequency: Optional[float] = None
    tone_description: Optional[str] = None

    # Shared context
    recurring_topics: List[str] = field(default_factory=list)
    private_references: List[str] = field(default_factory=list)

    # Generated instructions for bot
    bot_instructions: Optional[str] = None

    # Golden examples
    golden_examples: List[Dict[str, str]] = field(default_factory=list)

    # Metadata
    id: str = field(default_factory=lambda: str(uuid4()))
    total_messages_analyzed: int = 0
    last_analyzed_at: Optional[datetime] = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
