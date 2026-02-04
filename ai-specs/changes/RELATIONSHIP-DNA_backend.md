# Backend Implementation Plan: RELATIONSHIP-DNA

## Overview

**Ticket**: RELATIONSHIP-DNA
**Feature**: Relationship Context Layer - Personalized style per lead
**Architecture**: DDD Layered - Domain Layer (Services) + Data Layer (Models)

This plan follows ai-specs methodology:
- TDD (tests before implementation)
- Baby steps (one change at a time)
- Documentation before commit
- 90% test coverage minimum

## Problem Statement

**Current State:**
```
ToneProfile (per CREATOR) → Applied EQUALLY to ALL leads
Stefan talks the same to his girlfriend as to a new client
```

**Target State:**
```
ToneProfile (per CREATOR) + RelationshipDNA (per LEAD) → Personalized per relationship
Stefan talks differently to Nadia (💙, intimate) vs Johnny (bro, hermano) vs new client (formal)
```

## Solution Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    INCOMING MESSAGE                             │
│                    Lead: @username                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              RELATIONSHIP DNA SERVICE                           │
│                                                                 │
│  1. get_or_create_dna(creator_id, lead_id)                     │
│  2. If not exists OR stale → analyze_relationship()            │
│  3. Return RelationshipDNA with:                               │
│     - relationship_type (INTIMA/AMISTAD_CERCANA/CLIENTE/etc)   │
│     - vocabulary (uses/avoids per this relationship)           │
│     - patterns (avg_length, questions_freq, emojis)            │
│     - bot_instructions (personalized prompt addition)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  CONTEXT ASSEMBLY                               │
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │   LAYER 1       │    │   LAYER 3       │                    │
│  │   Creator DNA   │ +  │   Relationship  │                    │
│  │   (ToneProfile) │    │   DNA           │                    │
│  └─────────────────┘    └─────────────────┘                    │
│                                                                 │
│  Combined prompt = base_prompt + relationship_instructions      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BOT RESPONSE                                 │
│                    Personalized for THIS relationship           │
└─────────────────────────────────────────────────────────────────┘
```

## Data Model

### Table: relationship_dna

```sql
CREATE TABLE relationship_dna (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id VARCHAR(100) NOT NULL REFERENCES creators(id),
    follower_id VARCHAR(255) NOT NULL,

    -- Relationship classification
    relationship_type VARCHAR(50) NOT NULL DEFAULT 'DESCONOCIDO',
    trust_score FLOAT DEFAULT 0.0,
    depth_level INTEGER DEFAULT 0,

    -- Vocabulary specific to this relationship
    vocabulary_uses JSONB DEFAULT '[]',
    vocabulary_avoids JSONB DEFAULT '[]',
    emojis JSONB DEFAULT '[]',

    -- Interaction patterns
    avg_message_length INTEGER,
    questions_frequency FLOAT,
    multi_message_frequency FLOAT,
    tone_description TEXT,

    -- Shared context
    recurring_topics JSONB DEFAULT '[]',
    private_references JSONB DEFAULT '[]',

    -- Generated instructions for bot
    bot_instructions TEXT,

    -- Golden examples
    golden_examples JSONB DEFAULT '[]',

    -- Metadata
    total_messages_analyzed INTEGER DEFAULT 0,
    last_analyzed_at TIMESTAMP WITH TIME ZONE,
    version INTEGER DEFAULT 1,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(creator_id, follower_id)
);

CREATE INDEX idx_relationship_dna_creator_follower ON relationship_dna(creator_id, follower_id);
CREATE INDEX idx_relationship_dna_type ON relationship_dna(relationship_type);
```

### Enum: RelationshipType

```python
class RelationshipType(str, Enum):
    INTIMA = "INTIMA"                    # Romantic/very close
    AMISTAD_CERCANA = "AMISTAD_CERCANA"  # Close friend, uses "hermano/bro"
    AMISTAD_CASUAL = "AMISTAD_CASUAL"    # Casual friend, uses "crack"
    CLIENTE = "CLIENTE"                  # Client/prospect
    COLABORADOR = "COLABORADOR"          # Business collaborator
    DESCONOCIDO = "DESCONOCIDO"          # New lead, no history
```

## Progress Tracking

| Step | Task | Tests Written | Tests Passing | Status | Est. Hours |
|------|------|---------------|---------------|--------|------------|
| 0 | Create feature branch | - | - | ✅ | 0.1 |
| 1 | Create plan document | - | - | ✅ | 0.5 |
| 2 | RelationshipType enum | 0/3 | 0/3 | ⬜ | 0.5 |
| 3 | RelationshipDNA model | 0/8 | 0/8 | ⬜ | 2.0 |
| 4 | SQL migration | 0/2 | 0/2 | ⬜ | 1.0 |
| 5 | RelationshipDNARepository | 0/6 | 0/6 | ⬜ | 2.0 |
| 6 | RelationshipAnalyzer service | 0/12 | 0/12 | ⬜ | 4.0 |
| 7 | VocabularyExtractor | 0/8 | 0/8 | ⬜ | 3.0 |
| 8 | RelationshipTypeDetector | 0/6 | 0/6 | ⬜ | 2.0 |
| 9 | BotInstructionsGenerator | 0/5 | 0/5 | ⬜ | 2.0 |
| 10 | Integration with dm_agent | 0/8 | 0/8 | ⬜ | 3.0 |
| 11 | Auto-update triggers | 0/4 | 0/4 | ⬜ | 2.0 |
| 12 | Migration for existing leads | 0/3 | 0/3 | ⬜ | 2.0 |
| 13 | Integration tests | 0/10 | 0/10 | ⬜ | 3.0 |
| 14 | Documentation | - | - | ⬜ | 1.0 |

**Total Estimated**: 28 hours
**Total Tests**: 75

## Implementation Steps

### Step 2: Create RelationshipType Enum

**2.1 Write tests FIRST (TDD)**
```python
# backend/tests/models/test_relationship_type.py

import pytest
from models.relationship_dna import RelationshipType

class TestRelationshipType:
    def test_all_types_exist(self):
        """Verify all relationship types are defined"""
        assert RelationshipType.INTIMA.value == "INTIMA"
        assert RelationshipType.AMISTAD_CERCANA.value == "AMISTAD_CERCANA"
        assert RelationshipType.AMISTAD_CASUAL.value == "AMISTAD_CASUAL"
        assert RelationshipType.CLIENTE.value == "CLIENTE"
        assert RelationshipType.COLABORADOR.value == "COLABORADOR"
        assert RelationshipType.DESCONOCIDO.value == "DESCONOCIDO"

    def test_type_is_string_enum(self):
        """Verify enum values are strings"""
        assert isinstance(RelationshipType.INTIMA.value, str)

    def test_default_is_desconocido(self):
        """Verify DESCONOCIDO is used for new leads"""
        default = RelationshipType.DESCONOCIDO
        assert default.value == "DESCONOCIDO"
```

**2.2 Run tests (should FAIL)**
```bash
cd backend
pytest tests/models/test_relationship_type.py -v
# Expected: FAIL (module not found)
```

**2.3 Implement**
```python
# backend/models/relationship_dna.py

from enum import Enum

class RelationshipType(str, Enum):
    """Types of relationships between creator and lead.

    Used to determine communication style and vocabulary.
    """
    INTIMA = "INTIMA"                    # Romantic/very close - uses 💙, no "hermano"
    AMISTAD_CERCANA = "AMISTAD_CERCANA"  # Close friend - uses "hermano", "bro"
    AMISTAD_CASUAL = "AMISTAD_CASUAL"    # Casual friend - uses "crack", light tone
    CLIENTE = "CLIENTE"                  # Client/prospect - informative, helpful
    COLABORADOR = "COLABORADOR"          # Business partner - professional but warm
    DESCONOCIDO = "DESCONOCIDO"          # New lead - neutral, no assumptions
```

**2.4 Run tests (should PASS)**
```bash
pytest tests/models/test_relationship_type.py -v
# Expected: 3 passed
```

**2.5 Commit**
```bash
git add backend/models/relationship_dna.py
git add backend/tests/models/test_relationship_type.py
git commit -m "feat(models): add RelationshipType enum

- Add 6 relationship types for lead classification
- INTIMA, AMISTAD_CERCANA, AMISTAD_CASUAL, CLIENTE, COLABORADOR, DESCONOCIDO
- TDD: 3/3 tests passing

Part of RELATIONSHIP-DNA feature"
```

### Step 3: Create RelationshipDNA Model

**3.1 Write tests FIRST (TDD)**
```python
# backend/tests/models/test_relationship_dna.py

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from models.relationship_dna import RelationshipDNA, RelationshipType

class TestRelationshipDNAModel:
    def test_create_minimal(self):
        """Create DNA with only required fields"""
        dna = RelationshipDNA(
            creator_id="stefan",
            follower_id="12345"
        )
        assert dna.relationship_type == RelationshipType.DESCONOCIDO
        assert dna.trust_score == 0.0
        assert dna.depth_level == 0

    def test_create_full(self):
        """Create DNA with all fields"""
        dna = RelationshipDNA(
            creator_id="stefan",
            follower_id="12345",
            relationship_type=RelationshipType.AMISTAD_CERCANA,
            trust_score=0.85,
            depth_level=3,
            vocabulary_uses=["hermano", "bro"],
            vocabulary_avoids=["amigo"],
            emojis=["🙏🏽", "🫂", "💪🏽"],
            avg_message_length=45,
            questions_frequency=0.35,
            tone_description="Cercano, espiritual, vulnerable",
            recurring_topics=["circulos de hombres", "vipassana"],
            bot_instructions="Con este lead usar 'hermano'. Preguntar por circulos."
        )
        assert dna.creator_id == "stefan"
        assert dna.relationship_type == RelationshipType.AMISTAD_CERCANA
        assert "hermano" in dna.vocabulary_uses
        assert "amigo" in dna.vocabulary_avoids

    def test_vocabulary_lists_default_empty(self):
        """Vocabulary lists default to empty"""
        dna = RelationshipDNA(creator_id="stefan", follower_id="12345")
        assert dna.vocabulary_uses == []
        assert dna.vocabulary_avoids == []
        assert dna.emojis == []

    def test_golden_examples_structure(self):
        """Golden examples have correct structure"""
        dna = RelationshipDNA(
            creator_id="stefan",
            follower_id="12345",
            golden_examples=[
                {"lead": "Que tal?", "creator": "Todo bien hermano! Y vos??"},
                {"lead": "Gracias!", "creator": "Un placer bro"}
            ]
        )
        assert len(dna.golden_examples) == 2
        assert "lead" in dna.golden_examples[0]
        assert "creator" in dna.golden_examples[0]

    def test_unique_constraint_fields(self):
        """creator_id + follower_id should be unique"""
        dna1 = RelationshipDNA(creator_id="stefan", follower_id="12345")
        dna2 = RelationshipDNA(creator_id="stefan", follower_id="12345")
        assert dna1.creator_id == dna2.creator_id
        assert dna1.follower_id == dna2.follower_id

    def test_version_starts_at_1(self):
        """Version starts at 1"""
        dna = RelationshipDNA(creator_id="stefan", follower_id="12345")
        assert dna.version == 1

    def test_timestamps_auto_set(self):
        """Timestamps are set automatically"""
        dna = RelationshipDNA(creator_id="stefan", follower_id="12345")
        assert dna.created_at is not None
        assert dna.updated_at is not None

    def test_total_messages_analyzed_default(self):
        """total_messages_analyzed defaults to 0"""
        dna = RelationshipDNA(creator_id="stefan", follower_id="12345")
        assert dna.total_messages_analyzed == 0
```

**3.2 Run tests (should FAIL)**
```bash
pytest tests/models/test_relationship_dna.py -v
```

**3.3 Implement model** (see full implementation in models/relationship_dna.py)

**3.4 Run tests (should PASS)**
```bash
pytest tests/models/test_relationship_dna.py -v
# Expected: 8 passed
```

**3.5 Commit**
```bash
git add backend/models/relationship_dna.py
git add backend/tests/models/test_relationship_dna.py
git commit -m "feat(models): add RelationshipDNA SQLAlchemy model

- Full model with all fields for relationship context
- JSONB fields for vocabulary, emojis, topics, examples
- Unique constraint on creator_id + follower_id
- TDD: 8/8 tests passing

Part of RELATIONSHIP-DNA feature"
```

### Steps 4-14: Continue with same TDD pattern...

Each step follows:
1. Write tests FIRST
2. Run tests (FAIL)
3. Implement code
4. Run tests (PASS)
5. Update documentation
6. Show diff
7. Commit with descriptive message

## Testing Checklist

- [ ] All unit tests pass (75 tests)
- [ ] All integration tests pass
- [ ] 90% coverage achieved
- [ ] No regressions in existing bot functionality
- [ ] Tested with real Stefan conversations (243 conversations)
- [ ] Compared bot v3.0 vs v4.0 (with DNA) responses

## Rollout Plan

1. **Staging Deploy**
   - Deploy feature branch to staging
   - Run migration
   - Verify no errors

2. **Test with Stefan Data**
   - Analyze 10 longest conversations
   - Generate RelationshipDNA for each
   - Compare bot responses before/after

3. **Gradual Production Rollout**
   - Enable for Stefan only (1 creator)
   - Monitor for 48h
   - Enable for all creators

## Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Vocabulary correct per relationship | >90% | Manual review of 50 responses |
| Relationship type detection | >95% | Compare to manual classification |
| Turing test (indistinguishability) | <55% | Blind test: human vs bot |
| No regression in response quality | 0 complaints | User feedback |
| Test coverage | >90% | pytest --cov |

## Files to Create/Modify

### New Files
- `backend/models/relationship_dna.py`
- `backend/services/relationship_dna_service.py`
- `backend/services/vocabulary_extractor.py`
- `backend/services/relationship_type_detector.py`
- `backend/services/bot_instructions_generator.py`
- `backend/tests/models/test_relationship_type.py`
- `backend/tests/models/test_relationship_dna.py`
- `backend/tests/services/test_relationship_dna_service.py`
- `backend/tests/services/test_vocabulary_extractor.py`
- `backend/tests/services/test_relationship_type_detector.py`
- `backend/tests/integration/test_relationship_dna_flow.py`
- `backend/alembic/versions/xxx_add_relationship_dna.py`

### Modified Files
- `backend/core/dm_agent.py` (integrate RelationshipDNA into response flow)
- `backend/core/prompt_builder.py` (add relationship section)
- `backend/api/models.py` (add RelationshipDNA model)
