"""Tests for ARC5 Phase 1 typed metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from core.metadata.helpers import (
    update_detection_metadata,
    update_generation_metadata,
    update_post_gen_metadata,
    update_scoring_metadata,
)
from core.metadata.models import (
    DetectionMetadata,
    GenerationMetadata,
    MessageMetadata,
    PostGenMetadata,
    ScoringMetadata,
)
from core.metadata.serdes import (
    get_legacy_read_count,
    read_metadata,
    reset_legacy_read_count,
    write_metadata,
)


# ── Fixtures ──────────────────────────────────────────────────────────────


def _detection_ok() -> DetectionMetadata:
    return DetectionMetadata(
        detection_ts=datetime(2026, 4, 18, 17, 0, tzinfo=timezone.utc),
        detection_duration_ms=42,
        detected_intent="question",
        confidence=0.87,
        lang_detected="es",
        matched_rules=["RULE_Q1", "RULE_Q2"],
        security_flags=["pii_email"],
        security_severity="low",
    )


def _scoring_ok() -> ScoringMetadata:
    return ScoringMetadata(
        scoring_ts=datetime(2026, 4, 18, 17, 0, 5, tzinfo=timezone.utc),
        scoring_duration_ms=120,
        scoring_model="gemini-2.5-flash",
        score_before=42.0,
        score_after=58.0,
        score_delta=16.0,
        interest_score=0.72,
        intent_score=0.55,
        objection_score=0.10,
        batch_id=UUID("12345678-1234-5678-1234-567812345678"),
        batch_position=3,
    )


def _generation_ok() -> GenerationMetadata:
    return GenerationMetadata(
        generation_ts=datetime(2026, 4, 18, 17, 0, 6, tzinfo=timezone.utc),
        generation_duration_ms=2300,
        generation_model="gemma-4-31b",
        temperature=0.7,
        prompt_tokens=1500,
        completion_tokens=120,
        total_tokens=1620,
        compaction_applied=True,
        distill_cache_hit=False,
        sections_truncated=["memories", "recent_history"],
        context_budget_used_pct=0.83,
        retry_count=1,
        circuit_breaker_tripped=False,
    )


def _post_gen_ok() -> PostGenMetadata:
    return PostGenMetadata(
        post_gen_ts=datetime(2026, 4, 18, 17, 0, 7, tzinfo=timezone.utc),
        safety_status="OK",
        safety_reason=None,
        pii_redacted_types=["email"],
        rule_violations=["emoji", "length"],
        length_regen_triggered=True,
    )


def _msg_stub(raw=None):
    # Simula api.models.Message con el column real msg_metadata.
    return SimpleNamespace(msg_metadata=raw)


# ── Default container ─────────────────────────────────────────────────────


class TestContainerDefaults:
    def test_empty_container_is_schema_version_1(self):
        m = MessageMetadata()
        dumped = m.model_dump()
        assert dumped == {
            "detection": None,
            "scoring": None,
            "generation": None,
            "post_gen": None,
            "schema_version": 1,
        }

    def test_schema_version_literal_is_1(self):
        assert MessageMetadata().schema_version == 1


# ── Round-trip ────────────────────────────────────────────────────────────


class TestRoundTrip:
    def test_full_round_trip(self):
        typed = MessageMetadata(
            detection=_detection_ok(),
            scoring=_scoring_ok(),
            generation=_generation_ok(),
            post_gen=_post_gen_ok(),
        )
        msg = _msg_stub()
        write_metadata(msg, typed)
        assert isinstance(msg.msg_metadata, dict)
        round_tripped = read_metadata(msg)
        assert round_tripped == typed

    def test_partial_round_trip_with_only_detection(self):
        typed = MessageMetadata(detection=_detection_ok())
        msg = _msg_stub()
        write_metadata(msg, typed)
        round = read_metadata(msg)
        assert round.detection == typed.detection
        assert round.scoring is None
        assert round.generation is None
        assert round.post_gen is None
        assert round.schema_version == 1

    def test_exclude_none_on_write(self):
        """Empty sub-sections must NOT leak as null keys in JSONB."""
        typed = MessageMetadata(detection=_detection_ok())
        msg = _msg_stub()
        write_metadata(msg, typed)
        assert "scoring" not in msg.msg_metadata
        assert "generation" not in msg.msg_metadata
        assert "post_gen" not in msg.msg_metadata
        assert msg.msg_metadata["schema_version"] == 1


# ── Validation ────────────────────────────────────────────────────────────


class TestValidation:
    def test_invalid_intent_raises(self):
        with pytest.raises(ValidationError):
            DetectionMetadata(
                detection_ts=datetime.now(timezone.utc),
                detection_duration_ms=10,
                detected_intent="shouting",  # not in Literal
                confidence=0.5,
                lang_detected="es",
            )

    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            DetectionMetadata(
                detection_ts=datetime.now(timezone.utc),
                detection_duration_ms=10,
                detected_intent="question",
                confidence=1.5,  # > 1.0
                lang_detected="es",
            )

    def test_confidence_negative_raises(self):
        with pytest.raises(ValidationError):
            DetectionMetadata(
                detection_ts=datetime.now(timezone.utc),
                detection_duration_ms=10,
                detected_intent="question",
                confidence=-0.1,
                lang_detected="es",
            )

    def test_safety_status_rejects_unknown(self):
        with pytest.raises(ValidationError):
            PostGenMetadata(
                post_gen_ts=datetime.now(timezone.utc),
                safety_status="MAYBE",  # not in Literal
            )

    def test_severity_rejects_unknown(self):
        with pytest.raises(ValidationError):
            DetectionMetadata(
                detection_ts=datetime.now(timezone.utc),
                detection_duration_ms=10,
                detected_intent="question",
                confidence=0.5,
                lang_detected="es",
                security_severity="catastrophic",
            )


# ── Missing / optional fields ─────────────────────────────────────────────


class TestOptionalFields:
    def test_optional_fields_default_to_none_or_empty(self):
        d = DetectionMetadata(
            detection_ts=datetime.now(timezone.utc),
            detection_duration_ms=10,
            detected_intent="greeting",
            confidence=0.9,
            lang_detected="ca",
        )
        assert d.matched_rules == []
        assert d.security_flags == []
        assert d.security_severity is None

    def test_scoring_batch_fields_optional(self):
        s = ScoringMetadata(
            scoring_ts=datetime.now(timezone.utc),
            scoring_duration_ms=10,
            scoring_model="m",
            score_before=0.0,
            score_after=0.0,
            score_delta=0.0,
            interest_score=0.0,
            intent_score=0.0,
            objection_score=0.0,
        )
        assert s.batch_id is None
        assert s.batch_position is None

    def test_generation_flags_default_false(self):
        g = GenerationMetadata(
            generation_ts=datetime.now(timezone.utc),
            generation_duration_ms=10,
            generation_model="m",
            temperature=0.5,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            context_budget_used_pct=0.1,
        )
        assert g.compaction_applied is False
        assert g.distill_cache_hit is False
        assert g.sections_truncated == []
        assert g.retry_count == 0
        assert g.circuit_breaker_tripped is False


# ── Legacy compatibility ──────────────────────────────────────────────────


class TestLegacyCompat:
    def setup_method(self):
        reset_legacy_read_count()

    def test_empty_metadata_returns_default_container(self):
        msg = _msg_stub(raw=None)
        result = read_metadata(msg)
        assert result == MessageMetadata()
        assert get_legacy_read_count() == 0

    def test_empty_dict_returns_default_container(self):
        msg = _msg_stub(raw={})
        result = read_metadata(msg)
        assert result == MessageMetadata()
        assert get_legacy_read_count() == 0

    def test_legacy_dict_does_not_crash_and_increments_counter(self):
        """Pre-typed row with arbitrary legacy keys must not raise."""
        legacy_raw = {
            "some_old_key": "value",
            "detection": {
                "detection_ts": "not-a-date",  # Invalid → triggers ValidationError
                "detected_intent": "foo",
            },
        }
        msg = _msg_stub(raw=legacy_raw)
        result = read_metadata(msg)
        assert result == MessageMetadata()
        assert get_legacy_read_count() == 1

    def test_design_doc_attribute_name_supported(self):
        """Serdes also duck-types the doc-literal `.metadata` attribute."""
        msg = SimpleNamespace(metadata=None)  # No msg_metadata
        assert read_metadata(msg) == MessageMetadata()
        write_metadata(msg, MessageMetadata(detection=_detection_ok()))
        # Wrote to .metadata since msg_metadata absent.
        assert msg.metadata["detection"]["detected_intent"] == "question"


# ── Partial updates ───────────────────────────────────────────────────────


class _FakeAsyncSession:
    """Minimal session stub implementing `get` (sync-return) + `commit`."""

    def __init__(self, message):
        self._message = message
        self.commits = 0

    def get(self, model, message_id):
        return self._message

    def commit(self):
        self.commits += 1


class TestPartialUpdates:
    @pytest.mark.asyncio
    async def test_update_detection_does_not_touch_scoring(self):
        typed = MessageMetadata(scoring=_scoring_ok())
        msg = _msg_stub()
        write_metadata(msg, typed)

        session = _FakeAsyncSession(msg)
        new_detection = _detection_ok()
        await update_detection_metadata(session, uuid4(), new_detection)

        result = read_metadata(msg)
        assert result.detection == new_detection
        assert result.scoring == typed.scoring
        assert result.generation is None
        assert result.post_gen is None
        assert session.commits == 1

    @pytest.mark.asyncio
    async def test_update_scoring_preserves_detection(self):
        typed = MessageMetadata(detection=_detection_ok())
        msg = _msg_stub()
        write_metadata(msg, typed)

        session = _FakeAsyncSession(msg)
        await update_scoring_metadata(session, uuid4(), _scoring_ok())

        result = read_metadata(msg)
        assert result.detection == typed.detection
        assert result.scoring == _scoring_ok()

    @pytest.mark.asyncio
    async def test_update_generation_preserves_others(self):
        typed = MessageMetadata(
            detection=_detection_ok(), scoring=_scoring_ok()
        )
        msg = _msg_stub()
        write_metadata(msg, typed)

        session = _FakeAsyncSession(msg)
        await update_generation_metadata(session, uuid4(), _generation_ok())

        result = read_metadata(msg)
        assert result.detection == typed.detection
        assert result.scoring == typed.scoring
        assert result.generation == _generation_ok()
        assert result.post_gen is None

    @pytest.mark.asyncio
    async def test_update_post_gen_preserves_others(self):
        typed = MessageMetadata(generation=_generation_ok())
        msg = _msg_stub()
        write_metadata(msg, typed)

        session = _FakeAsyncSession(msg)
        await update_post_gen_metadata(session, uuid4(), _post_gen_ok())

        result = read_metadata(msg)
        assert result.generation == typed.generation
        assert result.post_gen == _post_gen_ok()

    @pytest.mark.asyncio
    async def test_update_overwrites_existing_sub_section(self):
        old = _detection_ok()
        new = DetectionMetadata(
            detection_ts=datetime(2027, 1, 1, tzinfo=timezone.utc),
            detection_duration_ms=999,
            detected_intent="purchase",
            confidence=0.99,
            lang_detected="en",
        )
        msg = _msg_stub()
        write_metadata(msg, MessageMetadata(detection=old))

        session = _FakeAsyncSession(msg)
        await update_detection_metadata(session, uuid4(), new)

        result = read_metadata(msg)
        assert result.detection == new
        assert result.detection != old
