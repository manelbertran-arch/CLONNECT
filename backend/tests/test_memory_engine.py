"""
Tests for Memory Engine — Sprint 3.

Tests fact extraction, semantic search, conflict resolution,
conversation summaries, memory injection, Ebbinghaus decay,
GDPR forget, and token budget enforcement.
"""

import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import os
os.environ["ENABLE_MEMORY_ENGINE"] = "true"
os.environ["ENABLE_MEMORY_DECAY"] = "true"

from services.memory_engine import (
    DECAY_HALF_LIFE_BASE_DAYS,
    DECAY_THRESHOLD,
    MAX_FACTS_IN_PROMPT,
    MAX_FACTS_PER_EXTRACTION,
    ConversationSummaryData,
    ExtractionResult,
    LeadMemory,
    MemoryEngine,
    get_memory_engine,
)


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def engine():
    """Fresh MemoryEngine instance."""
    return MemoryEngine()


@pytest.fixture
def creator_id():
    return str(uuid.uuid4())


@pytest.fixture
def lead_id():
    return str(uuid.uuid4())


@pytest.fixture
def sample_conversation():
    return [
        {"role": "user", "content": "Hola! Vi tu post sobre el programa de nutricion y me interesa mucho"},
        {"role": "assistant", "content": "Hola! Que bien que te interese! El programa tiene 8 modulos. Que te gustaria saber?"},
        {"role": "user", "content": "Cuanto cuesta? Estoy un poco justa de presupuesto"},
        {"role": "assistant", "content": "El precio es 197EUR pero tenemos facilidades de pago. Te mando el enlace manana?"},
        {"role": "user", "content": "Si porfa! Manana lo miro"},
    ]


@pytest.fixture
def sample_facts():
    now = datetime.now(timezone.utc)
    return [
        LeadMemory(
            id=str(uuid.uuid4()),
            creator_id="c1",
            lead_id="l1",
            fact_type="preference",
            fact_text="Le interesa el curso de nutricion",
            confidence=0.9,
            created_at=now - timedelta(days=3),
        ),
        LeadMemory(
            id=str(uuid.uuid4()),
            creator_id="c1",
            lead_id="l1",
            fact_type="commitment",
            fact_text="Se le prometio enviar el enlace manana",
            confidence=0.85,
            created_at=now - timedelta(days=1),
        ),
        LeadMemory(
            id=str(uuid.uuid4()),
            creator_id="c1",
            lead_id="l1",
            fact_type="objection",
            fact_text="Tiene presupuesto limitado",
            confidence=0.8,
            created_at=now - timedelta(days=5),
        ),
    ]


@pytest.fixture
def sample_summary():
    return ConversationSummaryData(
        id=str(uuid.uuid4()),
        creator_id="c1",
        lead_id="l1",
        summary_text="El lead pregunto por precios del curso de nutricion. Mostro interes pero pidio pensarlo.",
        key_topics=["nutricion", "precios"],
        commitments_made=["Enviar enlace manana"],
        sentiment="positive",
        message_count=5,
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestFactExtraction:
    """Test fact extraction from conversations."""

    @pytest.mark.asyncio
    async def test_fact_extraction_from_conversation(self, engine, creator_id, lead_id, sample_conversation):
        """Verify LLM-based fact extraction produces valid structured output."""
        mock_llm_response = json.dumps({
            "facts": [
                {"type": "preference", "text": "Le interesa el programa de nutricion", "confidence": 0.95},
                {"type": "objection", "text": "Tiene presupuesto limitado", "confidence": 0.85},
                {"type": "commitment", "text": "Se prometio enviar enlace manana", "confidence": 0.9},
            ],
            "summary": "Lead interesado en nutricion, presupuesto limitado, enlace pendiente.",
            "sentiment": "positive",
            "key_topics": ["nutricion", "precios"],
        })

        with patch.object(engine, "_call_llm", new_callable=AsyncMock, return_value=mock_llm_response), \
             patch.object(engine, "_generate_embeddings_batch", new_callable=AsyncMock, return_value=[[0.1] * 1536] * 3), \
             patch.object(engine, "_get_existing_active_facts", new_callable=AsyncMock, return_value=[]), \
             patch.object(engine, "_store_fact", new_callable=AsyncMock) as mock_store, \
             patch.object(engine, "summarize_conversation", new_callable=AsyncMock, return_value=None):

            mock_store.side_effect = lambda **kwargs: LeadMemory(
                id=str(uuid.uuid4()),
                creator_id=kwargs["creator_id"],
                lead_id=kwargs["lead_id"],
                fact_type=kwargs["fact_type"],
                fact_text=kwargs["fact_text"],
                confidence=kwargs["confidence"],
            )

            result = await engine.add(creator_id, lead_id, sample_conversation)

            assert len(result) == 3
            assert mock_store.call_count == 3

            fact_types = [r.fact_type for r in result]
            assert "preference" in fact_types
            assert "objection" in fact_types
            assert "commitment" in fact_types

    @pytest.mark.asyncio
    async def test_empty_conversation_no_facts(self, engine, creator_id, lead_id):
        """Verify empty/short conversations don't trigger extraction."""
        short_conversation = [
            {"role": "user", "content": "Hola"},
        ]

        result = await engine.add(creator_id, lead_id, short_conversation)
        assert result == []

    @pytest.mark.asyncio
    async def test_extraction_validates_fact_types(self, engine):
        """Verify invalid fact types are filtered out."""
        mock_response = json.dumps({
            "facts": [
                {"type": "preference", "text": "Valid fact", "confidence": 0.8},
                {"type": "invalid_type", "text": "Should be filtered", "confidence": 0.7},
                {"type": "commitment", "text": "Another valid fact", "confidence": 0.9},
            ],
            "summary": "Test",
            "sentiment": "neutral",
            "key_topics": [],
        })

        with patch.object(engine, "_call_llm", new_callable=AsyncMock, return_value=mock_response):
            extraction = await engine._extract_facts_via_llm("Test messages")
            assert len(extraction.facts) == 2
            assert all(f["type"] in {"preference", "commitment"} for f in extraction.facts)

    @pytest.mark.asyncio
    async def test_extraction_caps_confidence(self, engine):
        """Verify confidence values are capped between 0.5 and 1.0."""
        mock_response = json.dumps({
            "facts": [
                {"type": "preference", "text": "High confidence", "confidence": 1.5},
                {"type": "topic", "text": "Low confidence", "confidence": 0.1},
            ],
            "summary": "Test",
            "sentiment": "neutral",
            "key_topics": [],
        })

        with patch.object(engine, "_call_llm", new_callable=AsyncMock, return_value=mock_response):
            extraction = await engine._extract_facts_via_llm("Test messages")
            assert extraction.facts[0]["confidence"] == 1.0
            assert extraction.facts[1]["confidence"] == 0.5


class TestSemanticSearch:
    """Test pgvector-based semantic search."""

    @pytest.mark.asyncio
    async def test_semantic_search_recall(self, engine, creator_id, lead_id, sample_facts):
        """Verify semantic search returns relevant facts."""
        with patch.object(engine, "_generate_embedding", new_callable=AsyncMock, return_value=[0.1] * 1536), \
             patch.object(engine, "_pgvector_search", new_callable=AsyncMock, return_value=sample_facts), \
             patch.object(engine, "_update_access_counters", new_callable=AsyncMock):

            results = await engine.search(creator_id, lead_id, "nutricion precios")

            assert len(results) == 3
            assert results[0].fact_type == "preference"

    @pytest.mark.asyncio
    async def test_search_fallback_to_recent(self, engine, creator_id, lead_id, sample_facts):
        """When embedding generation fails, fall back to recent facts."""
        with patch.object(engine, "_generate_embedding", new_callable=AsyncMock, return_value=None), \
             patch.object(engine, "_get_recent_facts", new_callable=AsyncMock, return_value=sample_facts[:2]):

            results = await engine.search(creator_id, lead_id, "test query")
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_disabled_returns_empty(self, engine, creator_id, lead_id):
        """When ENABLE_MEMORY_ENGINE is false, search returns empty list."""
        with patch("services.memory_engine.ENABLE_MEMORY_ENGINE", False):
            results = await engine.search(creator_id, lead_id, "test")
            assert results == []


class TestConflictResolution:
    """Test fact conflict resolution."""

    @pytest.mark.asyncio
    async def test_conflict_resolution_supersedes_old(self, engine):
        """New fact contradicting existing -> supersede old."""
        existing = [
            LeadMemory(
                id="old-id",
                creator_id="c1",
                lead_id="l1",
                fact_type="personal_info",
                fact_text="Vive en Madrid centro",
                confidence=0.8,
            ),
        ]

        new_fact = {
            "type": "personal_info",
            "text": "Vive en Barcelona Gracia",
            "confidence": 0.9,
        }

        with patch.object(engine, "_supersede_fact", new_callable=AsyncMock):
            result = await engine.resolve_conflict(new_fact, existing)
            assert result == "store"

    @pytest.mark.asyncio
    async def test_conflict_resolution_skips_duplicates(self, engine):
        """Exact duplicates should be skipped."""
        existing = [
            LeadMemory(
                id="old-id",
                creator_id="c1",
                lead_id="l1",
                fact_type="preference",
                fact_text="Le interesa el curso de nutricion",
                confidence=0.9,
            ),
        ]

        new_fact = {
            "type": "preference",
            "text": "Le interesa el curso de nutricion",
            "confidence": 0.85,
        }

        result = await engine.resolve_conflict(new_fact, existing)
        assert result == "skip"

    @pytest.mark.asyncio
    async def test_conflict_resolution_stores_new_different_type(self, engine):
        """Different fact types are never considered conflicts."""
        existing = [
            LeadMemory(
                id="old-id",
                creator_id="c1",
                lead_id="l1",
                fact_type="preference",
                fact_text="Le gusta el yoga",
                confidence=0.9,
            ),
        ]

        new_fact = {
            "type": "objection",
            "text": "El precio le parece alto",
            "confidence": 0.8,
        }

        result = await engine.resolve_conflict(new_fact, existing)
        assert result == "store"


class TestConversationSummary:
    """Test conversation summary generation."""

    @pytest.mark.asyncio
    async def test_conversation_summary_generation(self, engine, creator_id, lead_id, sample_conversation):
        """Verify conversation summary is generated and stored."""
        with patch.object(engine, "_store_summary", new_callable=AsyncMock) as mock_store:
            mock_store.return_value = ConversationSummaryData(
                id=str(uuid.uuid4()),
                creator_id=creator_id,
                lead_id=lead_id,
                summary_text="Lead interesado en nutricion.",
                key_topics=["nutricion"],
                sentiment="positive",
                message_count=5,
            )

            result = await engine.summarize_conversation(
                creator_id=creator_id,
                lead_id=lead_id,
                messages=sample_conversation,
                precomputed_summary="Lead interesado en nutricion.",
                precomputed_topics=["nutricion"],
                precomputed_sentiment="positive",
            )

            assert result is not None
            assert result.summary_text == "Lead interesado en nutricion."
            mock_store.assert_called_once()


class TestMemoryInjection:
    """Test memory formatting for prompt injection."""

    def test_memory_injection_in_prompt(self, engine, sample_facts, sample_summary):
        """Verify memory section is correctly formatted for prompt."""
        result = engine._format_memory_section(sample_facts, sample_summary)

        assert "=== MEMORIA DEL LEAD ===" in result
        assert "=== FIN MEMORIA ===" in result
        assert "Hechos conocidos sobre este lead:" in result
        assert "Le interesa el curso de nutricion" in result
        assert "Se le prometio enviar el enlace manana" in result
        assert "[PENDIENTE]" in result
        assert "Resumen ultima conversacion" in result

    def test_token_budget_enforcement(self, engine):
        """Verify the memory section respects the character/token budget."""
        many_facts = [
            LeadMemory(
                id=str(uuid.uuid4()),
                creator_id="c1",
                lead_id="l1",
                fact_type="topic",
                fact_text=f"Tema de conversacion numero {i} con informacion detallada sobre el producto y sus caracteristicas principales que incluyen multiples beneficios y ventajas competitivas frente a la competencia del mercado" * 2,
                confidence=0.7,
                created_at=datetime.now(timezone.utc) - timedelta(days=i),
            )
            for i in range(20)
        ]

        result = engine._format_memory_section(many_facts, None)

        fact_lines = [line for line in result.split("\n") if line.startswith("- ")]
        assert len(fact_lines) < 20
        assert len(fact_lines) <= MAX_FACTS_IN_PROMPT

    def test_empty_memories_returns_empty_string(self, engine):
        """No memories -> empty string (no section injected)."""
        result = engine._format_memory_section([], None)
        assert result == ""

    def test_commitment_priority_ordering(self, engine):
        """Commitments should appear before other fact types."""
        now = datetime.now(timezone.utc)
        facts = [
            LeadMemory(id="1", creator_id="c", lead_id="l", fact_type="topic",
                       fact_text="Hablaron de yoga", created_at=now),
            LeadMemory(id="2", creator_id="c", lead_id="l", fact_type="commitment",
                       fact_text="Se prometio enviar info", created_at=now - timedelta(days=2)),
            LeadMemory(id="3", creator_id="c", lead_id="l", fact_type="preference",
                       fact_text="Le gusta el pilates", created_at=now),
        ]

        result = engine._format_memory_section(facts, None)
        lines = [l for l in result.split("\n") if l.startswith("- ")]

        assert "Se prometio enviar info" in lines[0]


class TestEbbinghausDecay:
    """Test Ebbinghaus forgetting curve calculations."""

    def test_ebbinghaus_decay_calculation(self):
        """Verify decay formula produces expected results."""
        days_since = 60
        times_accessed = 0
        half_life = DECAY_HALF_LIFE_BASE_DAYS * (1 + times_accessed)
        decay_factor = math.exp(-0.693 * days_since / half_life)

        assert decay_factor < 0.3
        assert decay_factor > 0.2
        assert 0.7 * decay_factor > DECAY_THRESHOLD

    def test_frequently_accessed_memories_persist(self):
        """Memories accessed many times have longer half-life."""
        days_since = 90
        times_accessed = 10
        half_life = DECAY_HALF_LIFE_BASE_DAYS * (1 + times_accessed)
        decay_factor = math.exp(-0.693 * days_since / half_life)

        assert decay_factor > 0.8
        assert 0.7 * decay_factor > DECAY_THRESHOLD

    def test_stale_unaccessed_memory_decays(self):
        """Old, never-accessed memories eventually deactivate."""
        days_since = 200
        times_accessed = 0
        half_life = DECAY_HALF_LIFE_BASE_DAYS * (1 + times_accessed)
        decay_factor = math.exp(-0.693 * days_since / half_life)

        assert decay_factor < 0.02
        assert 0.7 * decay_factor < DECAY_THRESHOLD


class TestGDPRForget:
    """Test GDPR right to erasure."""

    @pytest.mark.asyncio
    async def test_gdpr_forget_deletes_all(self, engine, creator_id, lead_id):
        """Verify forget_lead deletes all memories and summaries."""
        mock_session = MagicMock()
        mock_result1 = MagicMock()
        mock_result1.rowcount = 5
        mock_result2 = MagicMock()
        mock_result2.rowcount = 2

        mock_session.execute.side_effect = [mock_result1, mock_result2]

        with patch("api.database.SessionLocal", return_value=mock_session):
            deleted = await engine.forget_lead(creator_id, lead_id)

        assert deleted == 7
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()


class TestJSONParsing:
    """Test JSON response parsing from LLM."""

    def test_parse_clean_json(self, engine):
        """Parse well-formed JSON."""
        response = '{"facts": [], "summary": "Test", "sentiment": "neutral", "key_topics": []}'
        result = engine._parse_json_response(response)
        assert result is not None
        assert result["summary"] == "Test"

    def test_parse_json_with_markdown_fences(self, engine):
        """Parse JSON wrapped in markdown code fences."""
        response = '```json\n{"facts": [], "summary": "Test"}\n```'
        result = engine._parse_json_response(response)
        assert result is not None
        assert result["summary"] == "Test"

    def test_parse_json_with_surrounding_text(self, engine):
        """Parse JSON embedded in natural language."""
        response = 'Here is the result: {"facts": [], "summary": "Test"} That is all.'
        result = engine._parse_json_response(response)
        assert result is not None
        assert result["summary"] == "Test"

    def test_parse_invalid_json_returns_none(self, engine):
        """Invalid JSON returns None."""
        result = engine._parse_json_response("This is not JSON at all")
        assert result is None

    def test_parse_empty_response_returns_none(self, engine):
        """Empty response returns None."""
        assert engine._parse_json_response("") is None
        assert engine._parse_json_response(None) is None


class TestRelativeTime:
    """Test Spanish relative time formatting."""

    def test_relative_time_minutes(self, engine):
        result = engine._relative_time(datetime.now(timezone.utc) - timedelta(minutes=5))
        assert "minutos" in result

    def test_relative_time_hours(self, engine):
        result = engine._relative_time(datetime.now(timezone.utc) - timedelta(hours=3))
        assert "3 horas" in result

    def test_relative_time_yesterday(self, engine):
        result = engine._relative_time(datetime.now(timezone.utc) - timedelta(days=1))
        assert result == "ayer"

    def test_relative_time_days(self, engine):
        result = engine._relative_time(datetime.now(timezone.utc) - timedelta(days=4))
        assert "4 dias" in result

    def test_relative_time_weeks(self, engine):
        result = engine._relative_time(datetime.now(timezone.utc) - timedelta(days=14))
        assert "2 semanas" in result

    def test_relative_time_months(self, engine):
        result = engine._relative_time(datetime.now(timezone.utc) - timedelta(days=60))
        assert "2 meses" in result

    def test_relative_time_none(self, engine):
        result = engine._relative_time(None)
        assert result == "fecha desconocida"


class TestTextSimilarity:
    """Test Jaccard text similarity."""

    def test_identical_texts(self):
        assert MemoryEngine._text_similarity("le gusta el yoga", "le gusta el yoga") == 1.0

    def test_completely_different(self):
        assert MemoryEngine._text_similarity("abc def", "xyz qrs") == 0.0

    def test_partial_overlap(self):
        sim = MemoryEngine._text_similarity(
            "le interesa el curso de nutricion",
            "le interesa el programa de yoga",
        )
        assert 0.2 < sim < 0.7

    def test_empty_string(self):
        assert MemoryEngine._text_similarity("", "test") == 0.0


class TestSingleton:
    """Test singleton factory."""

    def test_get_memory_engine_returns_same_instance(self):
        """Factory should return the same instance."""
        e1 = get_memory_engine()
        e2 = get_memory_engine()
        assert e1 is e2
