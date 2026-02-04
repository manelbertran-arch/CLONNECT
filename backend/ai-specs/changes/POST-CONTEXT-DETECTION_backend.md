# Backend Implementation Plan: POST-CONTEXT-DETECTION

## Overview

**Ticket**: POST-CONTEXT-DETECTION
**Feature**: Auto-detect creator context from recent Instagram posts
**Architecture**: DDD Layered - Service + Integration
**Layer**: Layer 4 - Temporal State

## Problem Statement

```
ACTUAL:
Stefan publica "🚀 Lanzamos el curso de meditación!"
Lead pregunta: "¿Qué cursos tienes?"
Bot: Respuesta genérica sin mencionar el lanzamiento

OBJETIVO:
Bot detecta el lanzamiento y responde:
"¡Justo hoy lancé mi curso de meditación! ¿Te cuento más?"
```

## Solution Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    INSTAGRAM POSTS                              │
│                                                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐           │
│  │ Post 1  │  │ Post 2  │  │ Story   │  │ Reel    │           │
│  │ (2h ago)│  │ (1d ago)│  │ (5h ago)│  │ (3d ago)│           │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 POST ANALYZER SERVICE                           │
│                                                                 │
│  1. Fetch recent posts (last 7 days)                           │
│  2. Analyze with LLM:                                          │
│     - Is this a launch/promotion?                              │
│     - Is this about travel/availability?                       │
│     - Key topics/products mentioned?                           │
│  3. Generate context summary                                   │
│  4. Cache for 6 hours                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CREATOR CONTEXT                              │
│                                                                 │
│  {                                                             │
│    "active_promotion": "Curso meditación 20% dto",            │
│    "promotion_urgency": "48h restantes",                       │
│    "recent_topics": ["meditación", "retiro Bali"],            │
│    "availability_hint": null,                                  │
│    "context_instructions": "Menciona el lanzamiento del       │
│                            curso si el lead pregunta por       │
│                            cursos o meditación"                │
│  }                                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BOT RESPONSE                                 │
│                                                                 │
│  Context = CreatorDNA + RelationshipDNA + PostContext          │
│                                                                 │
│  "¡Hola! Justo ayer lancé mi curso de meditación, y está      │
│   con 20% de descuento las primeras 48h. ¿Te interesa?"       │
└─────────────────────────────────────────────────────────────────┘
```

## Data Model

### PostContext Schema

```python
@dataclass
class PostContext:
    creator_id: str

    # Promotions
    active_promotion: Optional[str]       # "Curso meditación 20% dto"
    promotion_deadline: Optional[datetime] # When offer expires
    promotion_urgency: Optional[str]       # "48h restantes"

    # Topics
    recent_topics: List[str]              # ["meditación", "retiro"]
    recent_products: List[str]            # ["curso meditación"]

    # Availability hints
    availability_hint: Optional[str]      # "De viaje por Bali"

    # Generated instructions
    context_instructions: str             # Instructions for bot

    # Metadata
    posts_analyzed: int
    analyzed_at: datetime
    expires_at: datetime                  # Cache expiry (6h)
    source_posts: List[str]               # Post IDs analyzed
```

### Database Table

```sql
CREATE TABLE post_contexts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id VARCHAR(100) NOT NULL,

    -- Promotions
    active_promotion TEXT,
    promotion_deadline TIMESTAMP WITH TIME ZONE,
    promotion_urgency TEXT,

    -- Topics (JSONB arrays)
    recent_topics JSONB DEFAULT '[]',
    recent_products JSONB DEFAULT '[]',

    -- Availability
    availability_hint TEXT,

    -- Generated
    context_instructions TEXT NOT NULL,

    -- Metadata
    posts_analyzed INTEGER NOT NULL DEFAULT 0,
    analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    source_posts JSONB DEFAULT '[]',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_creator_context UNIQUE (creator_id)
);

CREATE INDEX idx_post_contexts_creator ON post_contexts(creator_id);
CREATE INDEX idx_post_contexts_expires ON post_contexts(expires_at);
```

## Progress Tracking

| Step | Task | Tests | Status | Hours |
|------|------|-------|--------|-------|
| 0 | Create branch | - | ✅ | 0.1 |
| 1 | Create plan | - | ✅ | 0.5 |
| 2 | PostContext model | 0/5 | ⬜ | 0.5 |
| 3 | SQL migration | 0/2 | ⬜ | 0.5 |
| 4 | PostContextRepository | 0/6 | ⬜ | 1.0 |
| 5 | InstagramPostFetcher | 0/4 | ⬜ | 1.5 |
| 6 | PostAnalyzer (LLM) | 0/8 | ⬜ | 2.0 |
| 7 | PostContextService | 0/6 | ⬜ | 1.5 |
| 8 | dm_agent integration | 0/4 | ⬜ | 1.0 |
| 9 | Auto-refresh scheduler | 0/3 | ⬜ | 1.0 |
| 10 | Integration tests | 0/4 | ⬜ | 0.5 |

**Total Estimated**: 10 hours
**Total Tests**: 42

## Implementation Steps

### Step 2: PostContext Model (TDD)

**2.1 Tests FIRST**
```python
# tests/models/test_post_context.py
import pytest
from datetime import datetime, timedelta
from models.post_context import PostContext

class TestPostContext:
    def test_create_minimal(self):
        ctx = PostContext(
            creator_id="uuid",
            context_instructions="No special context",
            expires_at=datetime.utcnow() + timedelta(hours=6)
        )
        assert ctx.active_promotion is None
        assert ctx.recent_topics == []

    def test_create_with_promotion(self):
        ctx = PostContext(
            creator_id="uuid",
            active_promotion="Curso 20% dto",
            promotion_urgency="48h",
            context_instructions="Mencionar curso",
            expires_at=datetime.utcnow() + timedelta(hours=6)
        )
        assert ctx.active_promotion == "Curso 20% dto"

    def test_is_expired(self):
        ctx = PostContext(
            creator_id="uuid",
            context_instructions="Test",
            expires_at=datetime.utcnow() - timedelta(hours=1)
        )
        assert ctx.is_expired() == True

    def test_has_promotion(self):
        ctx = PostContext(
            creator_id="uuid",
            active_promotion="Sale!",
            context_instructions="Test",
            expires_at=datetime.utcnow() + timedelta(hours=6)
        )
        assert ctx.has_active_promotion() == True

    def test_to_prompt_addition(self):
        ctx = PostContext(
            creator_id="uuid",
            active_promotion="Curso meditación",
            recent_topics=["meditación", "mindfulness"],
            context_instructions="Menciona el curso",
            expires_at=datetime.utcnow() + timedelta(hours=6)
        )
        prompt = ctx.to_prompt_addition()
        assert "Curso meditación" in prompt
        assert "meditación" in prompt
```

### Step 5: InstagramPostFetcher

```python
# services/instagram_post_fetcher.py
class InstagramPostFetcher:
    """Fetches recent posts from Instagram Graph API"""

    async def fetch_recent_posts(
        self,
        creator_id: str,
        days: int = 7,
        limit: int = 10
    ) -> List[InstagramPost]:
        """
        Fetch posts from last N days
        Returns: List of posts with caption, timestamp, media_type
        """
        pass

    async def fetch_recent_stories(
        self,
        creator_id: str,
        hours: int = 24
    ) -> List[InstagramStory]:
        """
        Fetch stories from last N hours
        Note: Stories expire after 24h
        """
        pass
```

### Step 6: PostAnalyzer (LLM)

```python
# services/post_analyzer.py
class PostAnalyzer:
    """Analyzes posts with LLM to extract context"""

    ANALYSIS_PROMPT = '''
    Analiza estos posts recientes de un creador de contenido.

    Posts:
    {posts}

    Extrae:
    1. ¿Hay alguna promoción o lanzamiento activo? (producto, descuento, deadline)
    2. ¿Temas principales mencionados?
    3. ¿Alguna indicación de disponibilidad? (viaje, ocupado, etc)
    4. ¿Productos o servicios mencionados?

    Responde en JSON:
    {
        "active_promotion": "descripción o null",
        "promotion_deadline": "fecha o null",
        "promotion_urgency": "urgencia o null",
        "recent_topics": ["tema1", "tema2"],
        "recent_products": ["producto1"],
        "availability_hint": "hint o null",
        "context_instructions": "instrucciones para el bot en español"
    }
    '''

    async def analyze_posts(
        self,
        posts: List[InstagramPost]
    ) -> PostAnalysisResult:
        """Analyze posts with LLM and return structured result"""
        pass
```

### Step 8: dm_agent Integration

```python
# In dm_agent.py, add to context assembly:

async def assemble_context(creator_id, lead_id, message):
    # Existing context
    creator_dna = await get_creator_dna(creator_id)
    relationship_dna = await get_relationship_dna(creator_id, lead_id)

    # NEW: Post context
    post_context = await post_context_service.get_or_refresh(creator_id)

    # Combine for prompt
    context = f"""
    {creator_dna.to_prompt()}

    {relationship_dna.to_prompt()}

    CONTEXTO ACTUAL DEL CREADOR:
    {post_context.to_prompt_addition() if post_context else "Sin contexto especial"}
    """

    return context
```

## LLM Prompt for Analysis

```
Eres un asistente que analiza posts de Instagram para entender el contexto actual de un creador.

POSTS RECIENTES:
---
[Post 1 - hace 2 horas]
"🚀 ¡Por fin! Después de meses de trabajo, lanzo mi curso de MEDITACIÓN PARA EMPRENDEDORES.

20% de descuento las primeras 48h con el código LAUNCH20.

Link en bio 🧘‍♂️"
---
[Post 2 - hace 1 día]
"Grabando los últimos módulos del curso. Qué emoción compartir esto con ustedes 🙏"
---

ANALIZA Y RESPONDE EN JSON:
{
    "active_promotion": "Curso de Meditación para Emprendedores - 20% descuento código LAUNCH20",
    "promotion_deadline": "48 horas desde el lanzamiento",
    "promotion_urgency": "alta - solo 48h",
    "recent_topics": ["meditación", "emprendedores", "curso online", "lanzamiento"],
    "recent_products": ["Curso Meditación para Emprendedores"],
    "availability_hint": null,
    "context_instructions": "El creador acaba de lanzar su curso de meditación con 20% de descuento (código LAUNCH20) por 48h. Si el lead pregunta por cursos, meditación, o desarrollo personal, menciona este lanzamiento con entusiasmo. Transmite la urgencia del descuento limitado."
}
```

## Cache Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                    CACHE FLOW                                   │
│                                                                 │
│  Request for PostContext                                        │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────┐                                           │
│  │ Check DB cache  │                                           │
│  └────────┬────────┘                                           │
│           │                                                     │
│     ┌─────┴─────┐                                              │
│     │           │                                              │
│   Fresh      Expired/Missing                                   │
│     │           │                                              │
│     ▼           ▼                                              │
│  Return    Fetch new posts                                     │
│  cached    Analyze with LLM                                    │
│            Save to DB                                          │
│            Return fresh                                        │
│                                                                 │
│  Cache TTL: 6 hours                                            │
│  Background refresh: Every 4 hours                             │
└─────────────────────────────────────────────────────────────────┘
```

## Success Metrics

| Metric | Target |
|--------|--------|
| Unit tests | 42 |
| Cache hit rate | >80% |
| Analysis latency | <3s |
| Bot mentions active promotions | >90% relevance |
| False positive rate | <10% |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Instagram API rate limits | Cache aggressively (6h TTL) |
| LLM misinterprets sarcasm | Conservative analysis, only high-confidence |
| Stale promotions | Include deadline, auto-expire |
| Cost of LLM calls | Batch analysis, cache results |
