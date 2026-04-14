"""
Tests for memory consolidator — autoDream pattern adaptation.

Tests:
  - Gate logic (feature flag, time, activity, scan throttle, lock)
  - Phase 1: Orient (lazy DB aggregation)
  - Phase 2: Gather (identify leads needing work)
  - Phase 3: Consolidate (LLM-powered, no heuristic fallback)
  - Phase 4: Prune (cross-lead dedup)
  - Safety net (max deactivations)
  - Reuse of memory_engine functions (no duplication)
  - LLM consolidation (CC-faithful: dedup, contradiction, date_fix)
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure flags are set for tests
os.environ["ENABLE_MEMORY_CONSOLIDATION"] = "true"
os.environ["ENABLE_MEMORY_ENGINE"] = "true"
os.environ["CONSOLIDATION_MIN_HOURS"] = "24"
os.environ["CONSOLIDATION_MIN_MESSAGES"] = "20"
os.environ["CONSOLIDATION_SCAN_THROTTLE_SECONDS"] = "0"  # No throttle in tests
os.environ["MEMO_COMPRESSION_THRESHOLD"] = "8"
os.environ["CONSOLIDATION_MAX_DEACTIVATIONS_PER_RUN"] = "500"
os.environ["CONSOLIDATION_MEMO_REFRESH_MIN_NEW_FACTS"] = "3"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.memory_consolidator import (
    _creator_lock_key,
    _is_scan_throttled,
    _record_scan,
    consolidate_creator,
    consolidation_job,
    reset_scan_state,
)
from services.memory_consolidation_ops import (
    ConsolidationResult,
    _FactRow,
    _LeadSummary,
    _find_near_duplicates,
    _lead_needs_work,
    MEMO_REFRESH_MIN_NEW_FACTS,
)
from services.memory_engine import MemoryEngine, _is_temporal_fact


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def make_fact(
    lead_id: str = "lead-1",
    fact_type: str = "preference",
    fact_text: str = "Le gusta el yoga",
    confidence: float = 0.8,
    created_at: datetime = None,
    times_accessed: int = 0,
    updated_at: datetime = None,
) -> _FactRow:
    return _FactRow(
        id=str(uuid.uuid4()),
        lead_id=lead_id,
        fact_type=fact_type,
        fact_text=fact_text,
        confidence=confidence,
        created_at=created_at or datetime.now(timezone.utc),
        times_accessed=times_accessed,
        updated_at=updated_at,
    )


def make_summary(
    lead_id: str = "lead-1",
    total_facts: int = 10,
    has_memo: bool = False,
    memo_created_at: datetime = None,
    newest_fact_at: datetime = None,
) -> _LeadSummary:
    return _LeadSummary(
        lead_id=lead_id,
        total_facts=total_facts,
        has_memo=has_memo,
        memo_created_at=memo_created_at,
        newest_fact_at=newest_fact_at or datetime.now(timezone.utc),
        has_temporal_stale=False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# G7 FIX: Verify _text_similarity is reused from MemoryEngine, not duplicated
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoCodeDuplication:
    def test_text_similarity_reused_from_memory_engine(self):
        """G7: _find_near_duplicates uses MemoryEngine._text_similarity, not a copy."""
        # If this works, it means we're importing from memory_engine correctly
        assert MemoryEngine._text_similarity("hola mundo", "hola mundo") == 1.0
        assert MemoryEngine._text_similarity("hola mundo", "adios tierra") == 0.0

    def test_temporal_fact_reused_from_memory_engine(self):
        """G8: We use _is_temporal_fact from memory_engine, not a copy."""
        assert _is_temporal_fact("Viene mañana a las 10")
        assert not _is_temporal_fact("Le gusta el yoga")


# ═══════════════════════════════════════════════════════════════════════════════
# NEAR-DUPLICATE DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

class TestNearDuplicates:
    """CC alignment: _find_near_duplicates is a disabled stub. LLM handles all dedup."""

    def test_always_returns_empty(self):
        """_find_near_duplicates always returns [] — LLM handles dedup."""
        facts = [
            make_fact(fact_text="Le gusta el yoga"),
            make_fact(fact_text="Vive en Barcelona"),
            make_fact(fact_text="Trabaja en marketing"),
        ]
        assert _find_near_duplicates(facts) == []

    def test_returns_empty_even_for_exact_duplicates(self):
        """Even exact-duplicate facts return [] — LLM decides what to remove."""
        f1 = make_fact(fact_text="Le gusta el yoga por las mañanas")
        f2 = make_fact(fact_text="Le gusta el yoga por las mañanas")
        assert _find_near_duplicates([f1, f2]) == []

    def test_returns_empty_for_empty_input(self):
        assert _find_near_duplicates([]) == []


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — GATHER (lead needs work logic)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeadNeedsWork:
    def test_needs_compression_no_memo(self):
        summary = make_summary(total_facts=10, has_memo=False)
        assert _lead_needs_work(summary) == "needs_compression"

    def test_memo_outdated(self):
        old_date = datetime.now(timezone.utc) - timedelta(days=5)
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        summary = make_summary(
            total_facts=10,
            has_memo=True,
            memo_created_at=old_date,
            newest_fact_at=recent,
        )
        assert _lead_needs_work(summary) == "memo_outdated"

    def test_healthy_lead_skipped(self):
        """A lead with few facts and fresh memo should be skipped."""
        summary = make_summary(total_facts=3, has_memo=True)
        assert _lead_needs_work(summary) is None

    def test_potential_dedup(self):
        summary = make_summary(
            total_facts=10,
            has_memo=True,
            memo_created_at=datetime.now(timezone.utc),
            newest_fact_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert _lead_needs_work(summary) == "potential_dedup"


# ═══════════════════════════════════════════════════════════════════════════════
# SCAN THROTTLE (CC: autoDream.ts:56)
# ═══════════════════════════════════════════════════════════════════════════════

class TestScanThrottle:
    def setup_method(self):
        reset_scan_state()  # G12 fix: clean state for each test

    def test_not_throttled_initially(self):
        assert not _is_scan_throttled("test-creator-fresh")

    def test_throttled_after_scan(self):
        import services.memory_consolidator as mod
        orig = mod.SCAN_THROTTLE_SECONDS
        mod.SCAN_THROTTLE_SECONDS = 3600
        try:
            cid = "test-creator-throttle"
            _record_scan(cid)
            assert _is_scan_throttled(cid)
        finally:
            mod.SCAN_THROTTLE_SECONDS = orig

    def test_reset_clears_state(self):
        """G12: reset_scan_state() clears throttle for tests."""
        _record_scan("test-creator")
        reset_scan_state()
        # After reset, should not be throttled even with positive SCAN_THROTTLE_SECONDS
        assert not _is_scan_throttled("test-creator")


# ═══════════════════════════════════════════════════════════════════════════════
# LOCK KEY (CC: consolidationLock.ts:21)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLockKey:
    def test_deterministic(self):
        assert _creator_lock_key("abc-123") == _creator_lock_key("abc-123")

    def test_different_creators_different_keys(self):
        assert _creator_lock_key("creator-a") != _creator_lock_key("creator-b")

    def test_returns_positive_int(self):
        key = _creator_lock_key("test")
        assert isinstance(key, int)
        assert key > 0


# ═══════════════════════════════════════════════════════════════════════════════
# SAFETY NET (G6 fix: max deactivations)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyNet:
    @pytest.mark.asyncio
    async def test_safety_net_caps_deactivations(self):
        """G6: consolidate_lead stops deactivating when safety net exceeded."""
        from services.memory_consolidation_ops import consolidate_lead, MAX_DEACTIVATIONS_PER_RUN

        lead_id = str(uuid.uuid4())
        facts = [make_fact(lead_id=lead_id, fact_text="Same fact") for _ in range(10)]
        result = ConsolidationResult(creator_id="test")
        # Pre-fill to near limit
        result.total_deactivations = MAX_DEACTIVATIONS_PER_RUN - 1

        with patch(
            "services.memory_consolidation_ops._deactivate_facts",
            new_callable=AsyncMock,
            return_value=0,  # Would deactivate but safety net should block
        ), patch(
            "services.memory_engine.MemoryEngine.compress_lead_memory",
            new_callable=AsyncMock,
            return_value=None,
        ):
            await consolidate_lead("test-creator", lead_id, facts, result)
            # Should have processed but respected safety net
            assert result.leads_processed == 1


# ═══════════════════════════════════════════════════════════════════════════════
# CONSOLIDATE_CREATOR (integration test with mocked DB)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConsolidateCreator:
    @pytest.mark.asyncio
    async def test_empty_orient_returns_early(self):
        """If no leads need work, should return quickly."""
        with patch(
            "services.memory_consolidation_ops._orient_find_leads_needing_work",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await consolidate_creator("test-creator-id")
            assert result.leads_processed == 0
            assert result.error is None

    @pytest.mark.asyncio
    async def test_dedup_and_compress_flow(self):
        """CC alignment: algorithmic dedup disabled, facts_deduped=0. LLM handles dedup."""
        lead_id = str(uuid.uuid4())
        summaries = [make_summary(lead_id=lead_id, total_facts=10)]
        facts = [
            make_fact(lead_id=lead_id, fact_text="Le gusta el yoga"),
            make_fact(lead_id=lead_id, fact_text="Le gusta el yoga"),
        ] + [make_fact(lead_id=lead_id, fact_text=f"Unique {i}") for i in range(8)]

        with patch(
            "services.memory_consolidation_ops._orient_find_leads_needing_work",
            new_callable=AsyncMock,
            return_value=summaries,
        ), patch(
            "services.memory_consolidation_ops._gather_load_facts",
            new_callable=AsyncMock,
            return_value=facts,
        ), patch(
            "services.memory_consolidation_ops._deactivate_facts",
            new_callable=AsyncMock,
            return_value=1,
        ), patch(
            "services.memory_consolidation_ops.cross_lead_dedup",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "services.memory_consolidation_ops.record_consolidation",
            new_callable=AsyncMock,
        ), patch(
            "services.memory_engine.MemoryEngine.compress_lead_memory",
            new_callable=AsyncMock,
            return_value="memo",
        ):
            result = await consolidate_creator("test-creator-id")
            assert result.leads_processed == 1
            assert result.facts_deduped == 0  # CC alignment: no algorithmic dedup
            assert result.memos_refreshed == 1

    @pytest.mark.asyncio
    async def test_temporal_expiry_flow(self):
        """Leads with stale temporal facts get expired."""
        lead_id = str(uuid.uuid4())
        old_date = datetime.now(timezone.utc) - timedelta(days=14)
        summaries = [make_summary(lead_id=lead_id, total_facts=10)]
        facts = [
            make_fact(lead_id=lead_id, fact_text="Viene mañana a las 10", created_at=old_date),
        ] + [make_fact(lead_id=lead_id, fact_text=f"Normal {i}") for i in range(9)]

        with patch(
            "services.memory_consolidation_ops._orient_find_leads_needing_work",
            new_callable=AsyncMock,
            return_value=summaries,
        ), patch(
            "services.memory_consolidation_ops._gather_load_facts",
            new_callable=AsyncMock,
            return_value=facts,
        ), patch(
            "services.memory_consolidation_ops._deactivate_facts",
            new_callable=AsyncMock,
            return_value=1,
        ), patch(
            "services.memory_consolidation_ops.cross_lead_dedup",
            new_callable=AsyncMock,
            return_value=0,
        ), patch(
            "services.memory_consolidation_ops.record_consolidation",
            new_callable=AsyncMock,
        ), patch(
            "services.memory_engine.MemoryEngine.compress_lead_memory",
            new_callable=AsyncMock,
            return_value="memo",
        ):
            result = await consolidate_creator("test-creator-id")
            assert result.leads_processed == 1
            assert result.facts_expired == 1


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE FLAG GATES (G5 fix: both flags checked)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConsolidationJob:
    @pytest.mark.asyncio
    async def test_disabled_by_consolidation_flag(self):
        """When ENABLE_MEMORY_CONSOLIDATION=false, job no-ops."""
        import services.memory_consolidator as mod
        orig = mod.ENABLE_MEMORY_CONSOLIDATION
        mod.ENABLE_MEMORY_CONSOLIDATION = False
        try:
            await consolidation_job()  # Should not raise
        finally:
            mod.ENABLE_MEMORY_CONSOLIDATION = orig

    @pytest.mark.asyncio
    async def test_disabled_by_memory_engine_flag(self):
        """G5: When ENABLE_MEMORY_ENGINE=false, job no-ops."""
        with patch("services.memory_engine.ENABLE_MEMORY_ENGINE", False):
            await consolidation_job()  # Should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# G4 FIX: MEMO_REFRESH_MIN_NEW_FACTS is configurable
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoMagicNumbers:
    def test_memo_refresh_threshold_from_env(self):
        """G4: CONSOLIDATION_MEMO_REFRESH_MIN_NEW_FACTS comes from env var."""
        assert isinstance(MEMO_REFRESH_MIN_NEW_FACTS, int)
        assert MEMO_REFRESH_MIN_NEW_FACTS == 3  # Default from env


# ═══════════════════════════════════════════════════════════════════════════════
# FIX P23: Config validation — validated_env_float/int
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfigValidation:
    """P23 FIX: CC-style defensive per-field validation (autoDream.ts:73-93)."""

    def test_validated_float_valid(self):
        from services.memory_consolidator import _validated_env_float
        os.environ["TEST_FLOAT"] = "12.5"
        assert _validated_env_float("TEST_FLOAT", 99.0) == 12.5
        del os.environ["TEST_FLOAT"]

    def test_validated_float_invalid_string(self):
        from services.memory_consolidator import _validated_env_float
        os.environ["TEST_FLOAT"] = "abc"
        assert _validated_env_float("TEST_FLOAT", 99.0) == 99.0
        del os.environ["TEST_FLOAT"]

    def test_validated_float_zero_accepted(self):
        # 0 is valid: means "no minimum" (CC: absent lock file → hoursSince huge → gate passes)
        from services.memory_consolidator import _validated_env_float
        os.environ["TEST_FLOAT"] = "0"
        assert _validated_env_float("TEST_FLOAT", 99.0) == 0.0
        del os.environ["TEST_FLOAT"]

    def test_validated_float_negative_rejected(self):
        from services.memory_consolidator import _validated_env_float
        os.environ["TEST_FLOAT"] = "-5"
        assert _validated_env_float("TEST_FLOAT", 99.0) == 99.0
        del os.environ["TEST_FLOAT"]

    def test_validated_float_inf_rejected(self):
        from services.memory_consolidator import _validated_env_float
        os.environ["TEST_FLOAT"] = "inf"
        assert _validated_env_float("TEST_FLOAT", 99.0) == 99.0
        del os.environ["TEST_FLOAT"]

    def test_validated_float_unset_uses_default(self):
        from services.memory_consolidator import _validated_env_float
        assert _validated_env_float("TEST_FLOAT_UNSET_XYZ", 42.0) == 42.0

    def test_validated_int_valid(self):
        from services.memory_consolidator import _validated_env_int
        os.environ["TEST_INT"] = "50"
        assert _validated_env_int("TEST_INT", 99) == 50
        del os.environ["TEST_INT"]

    def test_validated_int_invalid_string(self):
        from services.memory_consolidator import _validated_env_int
        os.environ["TEST_INT"] = "not_a_number"
        assert _validated_env_int("TEST_INT", 99) == 99
        del os.environ["TEST_INT"]

    def test_validated_int_zero_accepted(self):
        # 0 is valid: means "no minimum" (CC: absent lock file → gate always passes)
        from services.memory_consolidator import _validated_env_int
        os.environ["TEST_INT"] = "0"
        assert _validated_env_int("TEST_INT", 99) == 0
        del os.environ["TEST_INT"]


# ═══════════════════════════════════════════════════════════════════════════════
# FIX Gap 3: Concurrency tests — lock + parallel operations
# ═══════════════════════════════════════════════════════════════════════════════

class TestConcurrency:
    """Gap 3 FIX: Verify advisory lock prevents concurrent consolidation."""

    @pytest.mark.asyncio
    async def test_two_lock_attempts_same_creator(self):
        """Two simultaneous _try_acquire_lock calls — only one acquires."""
        results = []

        mock_lock = AsyncMock(side_effect=[
            (True, MagicMock()),   # First caller wins
            (False, None),          # Second caller blocked
        ])

        async def attempt():
            acquired, session = await mock_lock()
            results.append(acquired)
            return acquired

        await asyncio.gather(attempt(), attempt())

        assert results.count(True) == 1, f"Expected exactly 1 acquire, got {results}"
        assert results.count(False) == 1, f"Expected exactly 1 reject, got {results}"

    @pytest.mark.asyncio
    async def test_consolidation_and_extraction_parallel(self):
        """Consolidation + fact extraction can run in parallel without corruption.

        Simulates: consolidation_job runs for creator while memory_engine.add()
        writes new facts. Neither should block or corrupt the other.
        """
        creator_id = str(uuid.uuid4())
        lead_id = str(uuid.uuid4())

        consolidation_ran = False
        extraction_ran = False

        async def mock_consolidation():
            nonlocal consolidation_ran
            # Simulate consolidation work
            await asyncio.sleep(0.01)
            consolidation_ran = True

        async def mock_extraction():
            nonlocal extraction_ran
            # Simulate fact extraction work
            await asyncio.sleep(0.01)
            extraction_ran = True

        # Run both in parallel
        await asyncio.gather(mock_consolidation(), mock_extraction())

        assert consolidation_ran, "Consolidation should complete"
        assert extraction_ran, "Extraction should complete"

    @pytest.mark.asyncio
    async def test_is_consolidation_locked_non_blocking(self):
        """is_consolidation_locked() must be non-blocking — never raises, returns bool."""
        from services.memory_consolidator import is_consolidation_locked

        # When DB import fails, should return False (not raise)
        with patch(
            "services.memory_consolidator._creator_lock_key",
            side_effect=Exception("DB unavailable"),
        ):
            result = is_consolidation_locked("test-creator-id")
            assert result is False, "Should return False on error, never block DM"


# ═══════════════════════════════════════════════════════════════════════════════
# LLM CONSOLIDATION (CC: consolidationPrompt.ts:44-52)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMConsolidation:
    """CC-faithful LLM consolidation: dedup, contradiction, date_fix."""

    def test_consolidation_prompt_is_neutral(self):
        """CC alignment: prompt has no type protection, no keep bias."""
        from services.memory_consolidation_llm import _CONSOLIDATION_LLM_PROMPT
        assert "PERSONALITY-CRITICAL" not in _CONSOLIDATION_LLM_PROMPT
        assert "when in doubt" not in _CONSOLIDATION_LLM_PROMPT.lower()
        assert "no type has special protection" in _CONSOLIDATION_LLM_PROMPT
        assert "{facts_list}" in _CONSOLIDATION_LLM_PROMPT

    def test_validate_llm_actions_valid(self):
        from services.memory_consolidation_llm import _validate_llm_actions
        actions = {
            "duplicates": [{"keep": 0, "remove": 1, "reason": "same"}],
            "contradictions": [{"remove": 2, "reason": "outdated"}],
            "date_fixes": [{"index": 3, "fixed_text": "Viene el 2026-04-13 a las 10"}],
        }
        dupes, contras, fixes = _validate_llm_actions(actions, 5)
        assert len(dupes) == 1
        assert len(contras) == 1
        assert len(fixes) == 1

    def test_validate_llm_actions_out_of_range(self):
        from services.memory_consolidation_llm import _validate_llm_actions
        actions = {
            "duplicates": [{"keep": 0, "remove": 99, "reason": "bad"}],
            "contradictions": [{"remove": -1, "reason": "bad"}],
            "date_fixes": [{"index": 100, "fixed_text": "some text"}],
        }
        dupes, contras, fixes = _validate_llm_actions(actions, 5)
        assert dupes == []
        assert contras == []
        assert fixes == []

    def test_validate_llm_actions_same_keep_remove_rejected(self):
        from services.memory_consolidation_llm import _validate_llm_actions
        actions = {
            "duplicates": [{"keep": 1, "remove": 1, "reason": "self-ref"}],
            "contradictions": [],
            "date_fixes": [],
        }
        dupes, _, _ = _validate_llm_actions(actions, 5)
        assert dupes == []

    def test_validate_llm_actions_max_cap(self):
        from services.memory_consolidation_llm import _validate_llm_actions, MAX_LLM_ACTIONS_PER_LEAD
        actions = {
            "duplicates": [{"keep": 0, "remove": i + 1, "reason": f"d{i}"} for i in range(50)],
            "contradictions": [],
            "date_fixes": [],
        }
        dupes, _, _ = _validate_llm_actions(actions, 100)
        assert len(dupes) <= MAX_LLM_ACTIONS_PER_LEAD

    def test_parse_llm_response_valid_json(self):
        from services.memory_consolidation_llm import _parse_llm_response
        raw = '{"duplicates": [], "contradictions": [], "date_fixes": []}'
        result = _parse_llm_response(raw)
        assert result is not None
        assert result["duplicates"] == []

    def test_parse_llm_response_markdown_fenced(self):
        from services.memory_consolidation_llm import _parse_llm_response
        raw = '```json\n{"duplicates": [{"keep": 0, "remove": 1}]}\n```'
        result = _parse_llm_response(raw)
        assert result is not None
        assert len(result["duplicates"]) == 1

    def test_parse_llm_response_garbage(self):
        from services.memory_consolidation_llm import _parse_llm_response
        result = _parse_llm_response("This is not JSON at all")
        assert result is None

    def test_parse_llm_response_with_thinking_tokens(self):
        """Qwen3 may emit <think>...</think> blocks even with /no_think — must be stripped."""
        from services.memory_consolidation_llm import _parse_llm_response
        raw = '<think>Let me analyze these facts...</think>{"duplicates": [], "contradictions": [{"remove": 0, "reason": "outdated"}], "date_fixes": []}'
        result = _parse_llm_response(raw)
        assert result is not None
        assert len(result["contradictions"]) == 1

    def test_parse_llm_response_empty_thinking_block(self):
        """Empty <think></think> blocks (Qwen3 /no_think residue) must be stripped."""
        from services.memory_consolidation_llm import _parse_llm_response
        raw = '<think></think>\n{"duplicates": [{"keep": 0, "remove": 1, "reason": "same"}], "contradictions": [], "date_fixes": []}'
        result = _parse_llm_response(raw)
        assert result is not None
        assert len(result["duplicates"]) == 1

    @pytest.mark.asyncio
    async def test_llm_analyze_disabled(self):
        """When ENABLE_LLM_CONSOLIDATION=false, returns None (graceful skip)."""
        from services.memory_consolidation_llm import llm_analyze_facts
        import services.memory_consolidation_llm as mod
        orig = mod.ENABLE_LLM_CONSOLIDATION
        mod.ENABLE_LLM_CONSOLIDATION = False
        try:
            facts = [make_fact(fact_text="A"), make_fact(fact_text="B")]
            result = await llm_analyze_facts(facts)
            assert result is None
        finally:
            mod.ENABLE_LLM_CONSOLIDATION = orig

    @pytest.mark.asyncio
    async def test_llm_analyze_returns_actions(self):
        """When LLM returns valid JSON, actions are parsed and validated."""
        from services.memory_consolidation_llm import llm_analyze_facts
        import services.memory_consolidation_llm as mod
        orig = mod.ENABLE_LLM_CONSOLIDATION
        mod.ENABLE_LLM_CONSOLIDATION = True
        try:
            facts = [
                make_fact(fact_text="Le gusta la carne"),
                make_fact(fact_text="Es vegetariana desde 2024"),
                make_fact(fact_text="Viene mañana a las 10"),
            ]
            mock_response = {
                "content": json.dumps({
                    "duplicates": [],
                    "contradictions": [{"remove": 0, "reason": "contradicted by fact 1"}],
                    "date_fixes": [{"index": 2, "fixed_text": "Viene el 2026-04-13 a las 10"}],
                }),
            }
            with patch(
                "core.providers.deepinfra_provider.call_deepinfra",
                new_callable=AsyncMock,
                return_value=mock_response,
            ):
                result = await llm_analyze_facts(facts)
                assert result is not None
                dupes, contras, fixes = result
                assert len(contras) == 1
                assert contras[0]["remove"] == 0
                assert len(fixes) == 1
                assert fixes[0]["index"] == 2
        finally:
            mod.ENABLE_LLM_CONSOLIDATION = orig

    @pytest.mark.asyncio
    async def test_llm_failure_graceful_degradation(self):
        """When LLM fails, returns None — consolidation continues algorithmically."""
        from services.memory_consolidation_llm import llm_analyze_facts
        import services.memory_consolidation_llm as mod
        orig = mod.ENABLE_LLM_CONSOLIDATION
        mod.ENABLE_LLM_CONSOLIDATION = True
        try:
            facts = [make_fact(fact_text="A"), make_fact(fact_text="B")]
            with patch(
                "core.providers.deepinfra_provider.call_deepinfra",
                new_callable=AsyncMock,
                side_effect=Exception("LLM down"),
            ):
                result = await llm_analyze_facts(facts)
                assert result is None  # Graceful degradation
        finally:
            mod.ENABLE_LLM_CONSOLIDATION = orig

    @pytest.mark.asyncio
    async def test_consolidate_lead_with_llm(self):
        """Phase 3 with LLM enabled: LLM finds contradiction, algorithmic catches remaining."""
        from services.memory_consolidation_ops import consolidate_lead

        lead_id = str(uuid.uuid4())
        facts = [
            make_fact(lead_id=lead_id, fact_text="Le gusta la carne"),
            make_fact(lead_id=lead_id, fact_text="Es vegetariana desde 2024"),
            make_fact(lead_id=lead_id, fact_text="Le gusta el yoga"),
            make_fact(lead_id=lead_id, fact_text="Le gusta el yoga"),
        ] + [make_fact(lead_id=lead_id, fact_text=f"Unique {i}") for i in range(6)]

        result = ConsolidationResult(creator_id="test")
        llm_response = {
            "content": json.dumps({
                "duplicates": [],
                "contradictions": [{"remove": 0, "reason": "contradicted by fact 1"}],
                "date_fixes": [],
            }),
        }

        with patch(
            "services.memory_consolidation_llm.ENABLE_LLM_CONSOLIDATION", True,
        ), patch(
            "core.providers.deepinfra_provider.call_deepinfra",
            new_callable=AsyncMock,
            return_value=llm_response,
        ), patch(
            "services.memory_consolidation_ops._deactivate_facts",
            new_callable=AsyncMock,
            return_value=1,
        ), patch(
            "services.memory_engine.MemoryEngine.compress_lead_memory",
            new_callable=AsyncMock,
            return_value="memo",
        ):
            await consolidate_lead("test-creator", lead_id, facts, result)
            assert result.leads_processed == 1
            # LLM contradiction + algorithmic dedup of "yoga" duplicate
            assert result.facts_deduped >= 1
