"""
Tests for Memory Extraction — CC-faithful guards.

Tests: overlap guard, manifest pre-injection, prompt format,
cursor, turn throttle, drain, delegation.
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import os
os.environ["ENABLE_MEMORY_ENGINE"] = "true"
os.environ["MEMORY_OVERLAP_GUARD_ENABLED"] = "true"
os.environ["MEMORY_MANIFEST_ENABLED"] = "true"

from services.memory_engine import LeadMemory, MemoryEngine, ExtractionResult
from services.memory_extraction import (
    FACT_EXTRACTION_PROMPT,
    MemoryExtractor,
    _format_fact_manifest,
)


@pytest.fixture
def engine():
    """Fresh MemoryEngine with common methods mocked."""
    e = MemoryEngine()
    e._resolve_creator_uuid = AsyncMock(side_effect=lambda x: x)
    e._resolve_lead_uuid = AsyncMock(side_effect=lambda c, l: l)
    return e


@pytest.fixture
def extractor(engine):
    """Fresh MemoryExtractor per test (no singleton interference)."""
    return MemoryExtractor(engine)


@pytest.fixture
def creator_id():
    return str(uuid.uuid4())


@pytest.fixture
def lead_id():
    return str(uuid.uuid4())


@pytest.fixture
def sample_conversation():
    return [
        {"role": "user", "content": "Hola! Me interesa el programa de nutricion y quiero saber precios"},
        {"role": "assistant", "content": "El programa cuesta 197EUR. Te mando el enlace?"},
        {"role": "user", "content": "Si, mandamelo manana porfa. Estoy en Barcelona y trabajo de enfermera"},
    ]


@pytest.fixture
def existing_facts():
    now = datetime.now(timezone.utc)
    return [
        LeadMemory(
            id=str(uuid.uuid4()), creator_id="c1", lead_id="l1",
            fact_type="preference", fact_text="Interested in nutrition program",
            confidence=0.9, created_at=now - timedelta(days=5),
        ),
        LeadMemory(
            id=str(uuid.uuid4()), creator_id="c1", lead_id="l1",
            fact_type="personal_info", fact_text="Lives in Barcelona",
            confidence=0.85, created_at=now - timedelta(days=2),
        ),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# TEST: Overlap Guard (CC: extractMemories.ts:550-558)
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverlapGuard:
    """CC: inProgress flag prevents concurrent extractions for same lead."""

    @pytest.mark.asyncio
    async def test_concurrent_calls_second_returns_empty(self, extractor, engine, creator_id, lead_id, sample_conversation):
        """Second call for same (creator,lead) returns [] immediately."""
        barrier = asyncio.Event()

        async def slow_get_facts(*args, **kwargs):
            await barrier.wait()
            return []

        engine._get_existing_active_facts = AsyncMock(side_effect=slow_get_facts)
        engine._call_llm = AsyncMock(return_value='{"facts":[],"summary":"","sentiment":"neutral","key_topics":[]}')

        task1 = asyncio.create_task(
            extractor.extract_and_store(creator_id, lead_id, sample_conversation)
        )
        await asyncio.sleep(0.01)

        result2 = await extractor.extract_and_store(creator_id, lead_id, sample_conversation)
        assert result2 == []

        barrier.set()
        await task1

    @pytest.mark.asyncio
    async def test_overlap_clears_after_completion(self, extractor, engine, creator_id, lead_id, sample_conversation):
        """After extraction completes, in_progress flag is cleared."""
        engine._get_existing_active_facts = AsyncMock(return_value=[])
        engine._call_llm = AsyncMock(return_value='{"facts":[],"summary":"","sentiment":"neutral","key_topics":[]}')

        await extractor.extract_and_store(creator_id, lead_id, sample_conversation)
        key = f"{creator_id}:{lead_id}"
        assert key not in extractor._in_progress

    @pytest.mark.asyncio
    async def test_different_leads_run_parallel(self, extractor, engine, sample_conversation):
        """Different leads can extract simultaneously."""
        cid = str(uuid.uuid4())
        lid1 = str(uuid.uuid4())
        lid2 = str(uuid.uuid4())
        call_count = 0

        async def counting_get_facts(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return []

        engine._get_existing_active_facts = AsyncMock(side_effect=counting_get_facts)
        engine._call_llm = AsyncMock(return_value='{"facts":[],"summary":"test","sentiment":"neutral","key_topics":[]}')

        await asyncio.gather(
            extractor.extract_and_store(cid, lid1, sample_conversation),
            extractor.extract_and_store(cid, lid2, sample_conversation),
        )
        assert call_count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# TEST: Manifest Pre-injection (CC: extractMemories.ts:400-404)
# ═══════════════════════════════════════════════════════════════════════════════

class TestManifestPreInjection:
    """CC: Pre-inject existing facts into prompt to prevent re-extraction."""

    def test_format_fact_manifest(self, existing_facts):
        """Verify manifest formats facts with type and age."""
        now = datetime.now(timezone.utc)
        manifest = _format_fact_manifest(existing_facts, now)
        assert "[preference]" in manifest
        assert "[personal_info]" in manifest
        assert "Interested in nutrition program" in manifest
        assert "Lives in Barcelona" in manifest
        assert "d ago)" in manifest

    def test_empty_facts_empty_manifest(self):
        """Empty facts produce empty manifest."""
        now = datetime.now(timezone.utc)
        assert _format_fact_manifest([], now) == ""

    @pytest.mark.asyncio
    async def test_manifest_injected_into_prompt(self, extractor, engine, creator_id, lead_id, sample_conversation, existing_facts):
        """Verify existing facts appear in the LLM prompt."""
        engine._get_existing_active_facts = AsyncMock(return_value=existing_facts)
        captured_prompt = None

        async def capture_llm(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return '{"facts":[],"summary":"","sentiment":"neutral","key_topics":[]}'

        engine._call_llm = AsyncMock(side_effect=capture_llm)

        await extractor.extract_and_store(creator_id, lead_id, sample_conversation)

        assert captured_prompt is not None
        assert "Existing facts" in captured_prompt
        assert "Interested in nutrition program" in captured_prompt
        assert "Lives in Barcelona" in captured_prompt


# ═══════════════════════════════════════════════════════════════════════════════
# TEST: Prompt Format (CC: prompts.ts + memoryTypes.ts)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPromptFormat:
    """CC: English prompt with exclusion rules, per-type guidance, date conversion."""

    def test_prompt_is_english(self):
        """Verify prompt is in English (CC: better LLM reasoning)."""
        assert "You are extracting" in FACT_EXTRACTION_PROMPT
        assert "Today's date" in FACT_EXTRACTION_PROMPT

    def test_prompt_has_exclusion_rules(self):
        """CC: WHAT_NOT_TO_SAVE_SECTION (memoryTypes.ts:183-195)."""
        assert "What NOT to extract" in FACT_EXTRACTION_PROMPT
        assert "BOT said" in FACT_EXTRACTION_PROMPT
        assert "Generic greetings" in FACT_EXTRACTION_PROMPT
        assert "knowledge base" in FACT_EXTRACTION_PROMPT

    def test_prompt_has_date_conversion(self):
        """CC: 'convert relative dates to absolute' (memoryTypes.ts:79)."""
        assert "Convert relative dates" in FACT_EXTRACTION_PROMPT
        assert "absolute dates" in FACT_EXTRACTION_PROMPT

    def test_prompt_has_per_type_guidance(self):
        """CC: TYPES_SECTION_INDIVIDUAL (memoryTypes.ts:113-178)."""
        for fact_type in ["preference", "commitment", "topic", "objection", "personal_info", "purchase_history"]:
            assert fact_type in FACT_EXTRACTION_PROMPT

    def test_prompt_has_conservative_instruction(self):
        """CC: 'be CONSERVATIVE' (consolidationPrompt.ts:92, same principle)."""
        assert "CONSERVATIVE" in FACT_EXTRACTION_PROMPT

    def test_prompt_has_existing_facts_placeholder(self):
        """Verify manifest injection point exists."""
        assert "{existing_facts_section}" in FACT_EXTRACTION_PROMPT


# ═══════════════════════════════════════════════════════════════════════════════
# TEST: Turn Throttle (CC: extractMemories.ts:389-395)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTurnThrottle:
    """CC: turnsSinceLastExtraction counter, configurable via env var."""

    @pytest.mark.asyncio
    async def test_throttle_skips_intermediate_turns(self, engine, creator_id, lead_id, sample_conversation):
        """With EXTRACT_EVERY_N_TURNS=3, only run on every 3rd call."""
        with patch("services.memory_extraction.EXTRACT_EVERY_N_TURNS", 3):
            extractor = MemoryExtractor(engine)
            engine._get_existing_active_facts = AsyncMock(return_value=[])
            engine._call_llm = AsyncMock(return_value='{"facts":[],"summary":"","sentiment":"neutral","key_topics":[]}')

            r1 = await extractor.extract_and_store(creator_id, lead_id, sample_conversation)
            r2 = await extractor.extract_and_store(creator_id, lead_id, sample_conversation)
            r3 = await extractor.extract_and_store(creator_id, lead_id, sample_conversation)

            # Only 3rd call should reach LLM
            assert engine._call_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_throttle_default_1_runs_every_turn(self, extractor, engine, creator_id, lead_id, sample_conversation):
        """With default N=1, every call triggers extraction."""
        engine._get_existing_active_facts = AsyncMock(return_value=[])
        engine._call_llm = AsyncMock(return_value='{"facts":[],"summary":"","sentiment":"neutral","key_topics":[]}')

        await extractor.extract_and_store(creator_id, lead_id, sample_conversation)
        await extractor.extract_and_store(creator_id, lead_id, sample_conversation)
        assert engine._call_llm.call_count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# TEST: Drain (CC: extractMemories.ts:611-615)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDrain:
    """CC: drainPendingExtraction — await in-flight with timeout."""

    @pytest.mark.asyncio
    async def test_drain_completes_tracked_tasks(self, extractor):
        """Drain waits for tracked tasks to complete."""
        completed = False

        async def slow_work():
            nonlocal completed
            await asyncio.sleep(0.05)
            completed = True

        task = asyncio.create_task(slow_work())
        extractor.track_task(task)

        await extractor.drain(timeout=2.0)
        assert completed

    @pytest.mark.asyncio
    async def test_drain_noop_when_empty(self, extractor):
        """Drain returns immediately when no tasks are tracked."""
        await extractor.drain(timeout=1.0)

    @pytest.mark.asyncio
    async def test_track_task_auto_removes_on_done(self, extractor):
        """Completed tasks are auto-removed from in_flight set."""
        async def quick():
            pass

        task = asyncio.create_task(quick())
        extractor.track_task(task)
        await asyncio.sleep(0.01)
        assert len(extractor._in_flight) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# TEST: Delegation (verify thin wrapper works)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDelegation:
    """Verify MemoryEngine.add() delegates to MemoryExtractor."""

    @pytest.mark.asyncio
    async def test_add_delegates_to_extractor(self, engine, creator_id, lead_id, sample_conversation):
        """engine.add() calls extractor.extract_and_store()."""
        engine._get_existing_active_facts = AsyncMock(return_value=[])
        engine._call_llm = AsyncMock(return_value='{"facts":[],"summary":"test","sentiment":"neutral","key_topics":[]}')

        result = await engine.add(creator_id, lead_id, sample_conversation)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_add_disabled_returns_empty(self):
        """When ENABLE_MEMORY_ENGINE=false, add() returns [] without calling extractor."""
        with patch("services.memory_engine.ENABLE_MEMORY_ENGINE", False):
            engine = MemoryEngine()
            result = await engine.add("cid", "lid", [{"role": "user", "content": "test"}])
            assert result == []
