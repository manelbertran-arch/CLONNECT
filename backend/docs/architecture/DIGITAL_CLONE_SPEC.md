# 🤖 CLONNECT DIGITAL CLONE - Complete Architecture Specification

## Executive Summary

The Digital Clone is Clonnect's core AI system that replicates a creator's communication style, knowledge, and relationship patterns to automate Instagram DM conversations while maintaining authenticity.

**Vision**: "Not just automation - replication of the creator's unique voice adapted to each relationship."

**Key Differentiator**: Unlike generic chatbots, the Digital Clone adapts its communication style per relationship, understanding that creators speak differently to their girlfriend vs a client vs a close friend.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│                    🧠 DIGITAL CLONE ARCHITECTURE                            │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    LAYER 5: AUTONOMY                                  │  │
│  │                    Capacity to ACT, not just respond                  │  │
│  │                    [Copilot → Autopilot → Full Agent]                │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    LAYER 4: TEMPORAL STATE                            │  │
│  │                    Current moment context                             │  │
│  │                    [Mood, Agenda, Campaigns, Availability]            │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    LAYER 3: RELATIONSHIP CONTEXT                      │  │
│  │                    How creator relates to EACH person                 │  │
│  │                    [RelationshipDNA per lead]                         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    LAYER 2: EPISODIC MEMORY                           │  │
│  │                    Everything creator has said/done                   │  │
│  │                    [Conversations, Content, Events]                   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    LAYER 1: IDENTITY BASE                             │  │
│  │                    Who the creator IS                                 │  │
│  │                    [Personality, Knowledge, Style, Voice]             │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Identity Base (Creator DNA)

### Purpose
The immutable essence of who the creator is - their personality, expertise, communication style, and voice. This layer answers: "Who am I?"

### Components

| Component | Description | Data Sources |
|-----------|-------------|--------------|
| **Personality** | Values, humor style, worldview | Bio, posts, interviews |
| **Knowledge** | Expertise, services, pricing, FAQs | Products, content, conversations |
| **Style** | Vocabulary, sentence structure, emojis | Historical messages |
| **Voice** | Dialect, formality, regional expressions | Audio/video content |

### Data Model

```python
class CreatorDNA:
    # Identity
    creator_id: UUID
    display_name: str
    bio: str
    niche: str  # fitness, coaching, education, etc.

    # Personality
    tone_profile: ToneProfile
    values: List[str]  # ["authenticity", "growth", "community"]
    humor_style: str  # "sarcastic", "wholesome", "dry"

    # Knowledge
    products: List[Product]
    services: List[Service]
    faqs: List[FAQ]
    pricing: Dict[str, float]

    # Style
    vocabulary: VocabularyProfile
    emoji_usage: EmojiProfile
    message_patterns: MessagePatterns

    # Voice
    dialect: str  # "es-ES", "es-LATAM", "es-AR"
    formality_default: float  # 0.0 (casual) to 1.0 (formal)
    regional_expressions: List[str]
```

### ToneProfile Schema (Existing)

```python
class ToneProfile:
    style: str  # "casual", "professional", "friendly"
    emoji_frequency: float  # 0.0-1.0
    avg_message_length: int
    questions_frequency: float
    exclamation_usage: float
    vocabulary_level: str  # "simple", "technical", "mixed"
    common_expressions: List[str]
    forbidden_words: List[str]
    response_patterns: Dict[str, str]
```

### Implementation Status

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| ToneProfile | ✅ Implemented | `core/tone_profile.py` | Loaded per creator |
| VocabularyProfile | ✅ Implemented | `data/creator_vocabulary.json` | Per creator |
| Products/Services | ✅ Implemented | `products` table | Full CRUD |
| FAQs | ✅ Implemented | `content_chunks` table | RAG-indexed |
| Brand Guardrails | ⚠️ Partial | `core/guardrails.py` | Exists but needs creator-specific rules |

### Gaps & TODOs

- [ ] **Creator-specific guardrails**: Currently guardrails are global, need per-creator "never say" rules
- [ ] **Voice profile from audio**: No audio analysis for voice characteristics
- [ ] **Automatic DNA extraction**: Manual setup, should auto-extract from content

---

## Layer 2: Episodic Memory

### Purpose
Everything the creator has said, done, or experienced. This layer enables the clone to "remember" past interactions and reference relevant content. Answers: "What have I done/said?"

### Components

| Component | Description | Technology |
|-----------|-------------|------------|
| **Conversations** | All DM history indexed | PostgreSQL + pgvector |
| **Content** | Posts, stories, reels | `content_chunks` table |
| **Events** | Workshops, launches, milestones | `events` table |
| **Opinions** | Stated views on topics | Extracted from conversations |

### Data Model

```python
class EpisodicMemory:
    # Conversation Memory
    conversations: List[Conversation]
    message_embeddings: VectorStore  # pgvector

    # Content Memory
    posts: List[ContentChunk]
    stories: List[ContentChunk]

    # Event Memory
    events: List[Event]
    milestones: List[Milestone]

    # Semantic Index
    topics: Dict[str, List[UUID]]  # topic -> relevant content IDs
    entities: Dict[str, List[UUID]]  # entity -> mentions
```

### RAG Pipeline (Existing)

```
Query → Embedding → Vector Search → Rerank → Context Assembly → LLM
         │              │              │
         │              │              └── Cross-Encoder (optional)
         │              └── pgvector similarity search
         └── OpenAI ada-002
```

### Implementation Status

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| Message Storage | ✅ Implemented | `messages` table | Full history |
| Embeddings | ✅ Implemented | `message_embeddings` table | pgvector |
| Semantic Search | ✅ Implemented | `core/semantic_search.py` | Working |
| Content Chunks | ✅ Implemented | `content_chunks` table | RAG-indexed |
| Cross-Encoder Rerank | ✅ Implemented | `core/reranker.py` | Optional, needs Pro plan |
| Conversation Context | ✅ Implemented | `UserContextLoader` | Loads full context |

### Gaps & TODOs

- [ ] **Topic extraction**: No automatic topic tagging of conversations
- [ ] **Entity recognition**: No NER for people, places, products mentioned
- [ ] **Temporal indexing**: No "what did we discuss in January" queries

---

## Layer 3: Relationship Context

### Purpose
How the creator relates to EACH specific person. This is the critical differentiator - the clone adapts its vocabulary, tone, and intimacy level per relationship. Answers: "How do I relate to THIS person?"

### Key Insight

> "Stefan doesn't have ONE communication style. He has RELATIONSHIPS."
>
> - With Nadia (girlfriend): 💙, vulnerable, NEVER "hermano"
> - With Johnny (close friend): "hermano", "bro", spiritual topics
> - With clients: informative, helpful, professional

### Components

| Component | Description | Storage |
|-----------|-------------|---------|
| **Relationship Type** | Classification of relationship | `relationship_type` enum |
| **Vocabulary DNA** | Words to use/avoid per lead | `vocabulary_uses/avoids` JSON |
| **Interaction Patterns** | Message length, questions, emojis | Numeric fields |
| **Shared Context** | Topics discussed, private references | JSON arrays |
| **Bot Instructions** | Generated prompt additions | Text field |

### RelationshipType Enum

```python
class RelationshipType(str, Enum):
    INTIMA = "INTIMA"                    # Romantic/very close (💙, amor)
    AMISTAD_CERCANA = "AMISTAD_CERCANA"  # Close friend (hermano, bro)
    AMISTAD_CASUAL = "AMISTAD_CASUAL"    # Casual friend (crack, tío)
    CLIENTE = "CLIENTE"                  # Client/prospect (professional)
    COLABORADOR = "COLABORADOR"          # Business partner (warm professional)
    DESCONOCIDO = "DESCONOCIDO"          # New lead (neutral)
```

### RelationshipDNA Schema

```python
class RelationshipDNA:
    id: UUID
    creator_id: UUID
    lead_id: UUID

    # Classification
    relationship_type: RelationshipType
    trust_score: float  # 0.0-1.0
    depth_level: int  # 0-4 based on message count

    # Vocabulary
    vocabulary_uses: List[str]    # ["hermano", "bro", "🙏🏽"]
    vocabulary_avoids: List[str]  # ["amigo", "💙"]
    emojis: List[str]             # Emojis for this relationship

    # Patterns
    avg_message_length: int
    questions_frequency: float
    multi_message_frequency: float
    tone_description: str

    # Shared Context
    recurring_topics: List[str]
    private_references: List[str]  # Inside jokes, shared memories

    # Generated Instructions
    bot_instructions: str  # "Con este lead usar 'hermano'. NUNCA usar..."
    golden_examples: List[Dict]  # Best response examples

    # Metadata
    total_messages_analyzed: int
    last_analyzed_at: datetime
    version: int
```

### Implementation Status

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| RelationshipType Enum | ✅ Implemented | `models/relationship_dna.py` | 6 types |
| RelationshipDNA Model | ✅ Implemented | `models/relationship_dna.py` | Full schema |
| DNA Repository | ✅ Implemented | `services/relationship_dna_repository.py` | CRUD |
| Relationship Analyzer | ✅ Implemented | `services/relationship_analyzer.py` | Main engine |
| Vocabulary Extractor | ✅ Implemented | `services/vocabulary_extractor.py` | Words, emojis |
| Type Detector | ✅ Implemented | `services/relationship_type_detector.py` | Weighted scoring |
| Instructions Generator | ✅ Implemented | `services/bot_instructions_generator.py` | NL instructions |
| DNA Service | ✅ Implemented | `services/relationship_dna_service.py` | dm_agent integration |
| Auto-Update Triggers | ✅ Implemented | `services/dna_update_triggers.py` | 24h cooldown |
| Migration Script | ✅ Implemented | `scripts/migrate_dna.py` | Backfill existing |
| SQL Migration | ✅ Implemented | `migrations/relationship_dna.sql` | Table + indexes |

### Tests

- Unit tests: 56 passing
- Integration tests: 18 passing
- E2E tests: 7 passing
- **Total: 81 tests**

### Gaps & TODOs

- [x] ~~RelationshipDNA model~~ ✅ PR #48
- [x] ~~Vocabulary extraction~~ ✅ PR #48
- [x] ~~Type detection~~ ✅ PR #48
- [x] ~~dm_agent integration~~ ✅ PR #48
- [x] ~~Auto-update triggers~~ ✅ PR #48
- [ ] **UI for manual override**: No frontend to manually adjust DNA
- [ ] **Confidence scores**: No confidence metric on type detection

---

## Layer 4: Temporal State

### Purpose
The current moment context - what's happening NOW in the creator's life. This layer ensures the clone knows about current availability, mood, and active campaigns. Answers: "What's happening right now?"

### Components

| Component | Description | Update Frequency |
|-----------|-------------|------------------|
| **Emotional State** | Current mood/energy | Manual or detected |
| **Availability** | Schedule, trips, busy periods | Calendar sync |
| **Active Campaigns** | Current promotions, launches | Manual config |
| **Recent Events** | Just happened (surgery, travel) | Manual or detected |

### Data Model

```python
class TemporalState:
    creator_id: UUID

    # Emotional
    current_mood: str  # "energized", "tired", "focused"
    energy_level: float  # 0.0-1.0

    # Availability
    is_available: bool
    busy_until: datetime
    current_location: str
    timezone: str

    # Campaigns
    active_campaigns: List[Campaign]
    current_promotion: Optional[Promotion]

    # Recent Context
    recent_events: List[str]  # ["just finished workshop", "traveling"]
    topics_to_mention: List[str]
    topics_to_avoid: List[str]

    # Auto-detected
    last_post_topic: str
    last_story_time: datetime
    response_delay_avg: timedelta
```

### Implementation Status

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| Availability | ⚠️ Partial | `creators.is_active` | Basic on/off only |
| Campaigns | ✅ Implemented | `campaigns` table | Full CRUD |
| Promotions | ✅ Implemented | `products.discount_*` | Price overrides |
| Recent Context | ❌ Missing | - | No temporal context |
| Mood/Energy | ❌ Missing | - | No mood tracking |
| Calendar Sync | ❌ Missing | - | No external calendar |

### Gaps & TODOs

- [ ] **Temporal context persistence**: State doesn't persist between deploys
- [ ] **Mood input UI**: No way for creator to set current mood
- [ ] **Calendar integration**: No Google/Apple calendar sync
- [ ] **Auto-detection from posts**: Should infer state from recent content
- [ ] **"Out of office" mode**: No vacation/unavailable handling

---

## Layer 5: Autonomy

### Purpose
The clone's capacity to ACT, not just respond. This layer defines what the clone can do independently vs what requires human approval. Answers: "What can I do on my own?"

### Autonomy Levels

```
Level 0: DISABLED
└── Clone is off, all manual

Level 1: COPILOT (Current)
├── Suggests responses
├── Human approves/edits
└── Human sends

Level 2: AUTOPILOT LIMITED
├── Auto-responds to simple messages
├── Escalates complex to human
└── Human handles sales

Level 3: SIMPLE ACTIONS
├── Schedules meetings
├── Sends links/resources
├── Classifies and tags leads
└── Triggers sequences

Level 4: COMPLEX ACTIONS
├── Negotiates pricing
├── Closes sales
├── Handles objections
└── Multi-step workflows

Level 5: FULL AGENT
├── Operates as creator
├── Makes decisions
├── Manages relationships
└── Minimal oversight
```

### Components

| Component | Description | Current Level |
|-----------|-------------|---------------|
| **Response Generation** | Draft responses | Level 1 (Copilot) |
| **Lead Nurturing** | Follow-up sequences | Level 3 (Auto) |
| **Ghost Reactivation** | Re-engage dormant leads | Level 3 (Auto) |
| **Lead Scoring** | Classify lead quality | Level 3 (Auto) |
| **Booking** | Schedule appointments | Level 2 (Semi-auto) |
| **Sales** | Close transactions | Level 1 (Human) |

### Implementation Status

| Component | Status | Location | Notes |
|-----------|--------|----------|-------|
| Copilot Mode | ✅ Implemented | `core/dm_agent.py` | Suggests responses |
| Lead Nurturing | ✅ Implemented | `core/nurturing.py` | 12 sequences, 759 lines |
| Ghost Reactivation | ✅ Implemented | `core/ghost_reactivation.py` | 351 lines |
| Lead Scoring | ✅ Implemented | `core/lead_scoring.py` | Multi-factor |
| Intent Classification | ✅ Implemented | `core/intent_classifier.py` | LLM-based |
| Guardrails | ✅ Implemented | `core/guardrails.py` | Safety checks |
| Autopilot Mode | ⚠️ Partial | `core/dm_agent.py` | Exists but disabled |
| Booking Actions | ⚠️ Partial | `api/routers/booking.py` | Links only |
| Sales Actions | ❌ Missing | - | Human only |

### Nurturing Sequences (Existing)

```python
SEQUENCES = [
    "interest_cold",       # Soft follow-up
    "objection_price",     # Price objection handling
    "objection_time",      # Time objection handling
    "objection_doubt",     # Doubt handling
    "objection_later",     # "Later" objection
    "abandoned",           # Cart recovery
    "re_engagement",       # Dormant lead reactivation
    "post_purchase",       # Post-sale follow-up
    "discount_urgency",    # Urgency creation
    "spots_limited",       # Scarcity
    "offer_expiring",      # Deadline reminder
    "flash_sale",          # Flash promotion
]
```

### Gaps & TODOs

- [ ] **Autopilot toggle**: UI to enable/disable autopilot per creator
- [ ] **Confidence threshold**: Auto-send only if confidence > X%
- [ ] **Escalation rules**: Define when to escalate to human
- [ ] **Action execution**: Actually perform actions (not just suggest)
- [ ] **Multi-step workflows**: Complex automated sequences

---

## Integration Flow

### Message Processing Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INCOMING MESSAGE                                    │
│                         From: @username                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: CONTEXT ASSEMBLY                                                    │
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   LAYER 1   │  │   LAYER 2   │  │   LAYER 3   │  │   LAYER 4   │        │
│  │  Creator    │  │  Episodic   │  │ Relationship│  │  Temporal   │        │
│  │    DNA      │  │   Memory    │  │     DNA     │  │   State     │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │                │
│         └────────────────┴────────────────┴────────────────┘                │
│                                    │                                        │
│                          Combined Context                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: INTENT CLASSIFICATION                                               │
│                                                                             │
│  Message → IntentClassifier → Intent + Confidence                          │
│                                                                             │
│  Intents: GREETING, QUESTION, PRICE_INQUIRY, BOOKING, OBJECTION,           │
│           PURCHASE_INTENT, COMPLAINT, SPAM, OTHER                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: RESPONSE GENERATION                                                 │
│                                                                             │
│  Context + Intent → LLM → Draft Response                                   │
│                                                                             │
│  Prompt includes:                                                           │
│  - Creator DNA (personality, style)                                         │
│  - Relationship DNA (vocabulary, tone for THIS lead)                        │
│  - Relevant memories (RAG)                                                  │
│  - Temporal context (if available)                                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: GUARDRAILS CHECK                                                    │
│                                                                             │
│  Response → Guardrails → Approved/Modified/Blocked                         │
│                                                                             │
│  Checks:                                                                    │
│  - No hallucinated prices                                                   │
│  - No promises creator can't keep                                           │
│  - No inappropriate content                                                 │
│  - Vocabulary appropriate for relationship                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: AUTONOMY DECISION (LAYER 5)                                         │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  IF autonomy_level >= AUTOPILOT AND confidence > threshold:         │   │
│  │      → Send automatically                                           │   │
│  │  ELSE:                                                              │   │
│  │      → Present to human for approval (Copilot mode)                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: POST-RESPONSE ACTIONS                                               │
│                                                                             │
│  - Update conversation state                                                │
│  - Trigger DNA update if needed (cooldown check)                           │
│  - Update lead score                                                        │
│  - Trigger nurturing sequence if applicable                                 │
│  - Log analytics                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Current Status Summary

```
┌─────────────────────────────────┬───────┬─────────────────────────────────┐
│             LAYER               │ SCORE │            STATUS               │
├─────────────────────────────────┼───────┼─────────────────────────────────┤
│ Layer 1: Identity Base          │  75%  │ ⚠️ Needs creator guardrails     │
├─────────────────────────────────┼───────┼─────────────────────────────────┤
│ Layer 2: Episodic Memory        │  85%  │ ✅ Fully functional             │
├─────────────────────────────────┼───────┼─────────────────────────────────┤
│ Layer 3: Relationship Context   │ 100%  │ ✅ COMPLETE (PR #48)            │
├─────────────────────────────────┼───────┼─────────────────────────────────┤
│ Layer 4: Temporal State         │  40%  │ ❌ Major gaps                   │
├─────────────────────────────────┼───────┼─────────────────────────────────┤
│ Layer 5: Autonomy               │  60%  │ ⚠️ Copilot only, no autopilot  │
├─────────────────────────────────┼───────┼─────────────────────────────────┤
│ OVERALL                         │  72%  │                                 │
└─────────────────────────────────┴───────┴─────────────────────────────────┘
```

---

## Roadmap

### Phase 1: Foundation ✅ COMPLETE
- [x] ToneProfile system
- [x] RAG pipeline
- [x] Conversation storage
- [x] Basic copilot mode

### Phase 2: Relationship DNA ✅ COMPLETE (PR #48)
- [x] RelationshipDNA model
- [x] Relationship type detection
- [x] Vocabulary extraction
- [x] Per-lead personalization
- [x] Auto-update triggers

### Phase 3: Temporal State (Next)
- [ ] Creator mood/availability input
- [ ] Calendar integration
- [ ] State persistence
- [ ] Auto-detection from posts

### Phase 4: Enhanced Autonomy
- [ ] Autopilot toggle
- [ ] Confidence thresholds
- [ ] Escalation rules
- [ ] Action execution

### Phase 5: Full Agent
- [ ] Multi-step workflows
- [ ] Sales automation
- [ ] Decision making
- [ ] Minimal oversight mode

---

## API Reference

### Relationship DNA Endpoints

```
GET  /api/relationship-dna/{creator_id}/{lead_id}
POST /api/relationship-dna/{creator_id}/{lead_id}/analyze
PUT  /api/relationship-dna/{creator_id}/{lead_id}
DELETE /api/relationship-dna/{creator_id}/{lead_id}
```

### Response Generation

```
POST /api/dm/generate-response
{
  "creator_id": "uuid",
  "lead_id": "uuid",
  "message": "string",
  "include_dna": true
}
```

---

## Configuration

### Environment Variables

```bash
# Layer 2: Memory
ENABLE_SEMANTIC_MEMORY_PGVECTOR=true
ENABLE_RERANKING=false  # Enable for Pro plan

# Layer 3: Relationship DNA
RELATIONSHIP_DNA_ENABLED=true
DNA_UPDATE_COOLDOWN_HOURS=24
DNA_STALENESS_DAYS=30
DNA_MIN_MESSAGES_FOR_ANALYSIS=10

# Layer 5: Autonomy
NURTURING_ENABLED=true
NURTURING_DRY_RUN=false
GHOST_REACTIVATION_ENABLED=true
AUTOPILOT_ENABLED=false  # Coming soon
```

---

## Glossary

| Term | Definition |
|------|------------|
| **Creator DNA** | The immutable personality/style profile of a creator |
| **Relationship DNA** | Per-lead communication preferences and patterns |
| **ToneProfile** | Style configuration (emojis, length, formality) |
| **Copilot Mode** | Bot suggests, human approves |
| **Autopilot Mode** | Bot acts autonomously within rules |
| **Nurturing** | Automated follow-up sequences |
| **Ghost Reactivation** | Re-engaging dormant leads |
| **Guardrails** | Safety checks preventing harmful responses |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-01 | Initial architecture |
| 2.0 | 2026-01 | Added RAG, nurturing |
| 3.0 | 2026-02 | Added Relationship DNA (Layer 3 complete) |

---

*Document maintained by Clonnect Engineering Team*
*Last updated: 2026-02-04*
