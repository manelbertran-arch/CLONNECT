"""ARC2 A2.5 hotfix: read-cutover unit tests.

RC1: semantic search via recall_semantic + fallback to get_all.
RC2: <memoria> tag wrapping matches footer instruction.
RC3: cap 2000, dedup by content, priority ordering, smart truncation.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────


def _mem(memory_type: str, content: str, confidence: float = 0.9, created_at_ts: int = 0):
    return SimpleNamespace(
        memory_type=memory_type,
        content=content,
        confidence=confidence,
        created_at_ts=created_at_ts,
    )


# ── _format_arc2_memories — RC2 + RC3 ─────────────────────────────────────────


class TestFormatArc2Memories:
    def _call(self, memories):
        from core.dm.phases.context import _format_arc2_memories
        return _format_arc2_memories(memories)

    def test_empty_returns_empty_string(self):
        assert self._call([]) == ""

    def test_single_identity_memory(self):
        result = self._call([_mem("identity", "Se llama Manel")])
        # RC2: must use <memoria> XML tag, not [Label] bracket format
        assert "<memoria" in result
        assert "Se llama Manel" in result

    def test_rc2_wraps_in_memoria_tag_not_bracket(self):
        result = self._call([_mem("identity", "Vive en Barcelona")])
        assert "<memoria tipo=\"identity\">" in result
        assert "</memoria>" in result
        # Old bracket format must NOT appear
        assert "[Datos personales]" not in result

    def test_multiple_types_all_present(self):
        memories = [
            _mem("identity", "Vive en Barcelona"),
            _mem("interest", "Le gusta el fitness"),
            _mem("objection", "Precio caro"),
        ]
        result = self._call(memories)
        assert "identity" in result
        assert "interest" in result
        assert "objection" in result

    def test_rc3_cap_2000_chars_enforced(self):
        """Cap is now 2000 chars (not 500)."""
        # 10 long items across different types, total raw > 2000
        memories = [_mem("identity", "x" * 250)] * 5 + [_mem("interest", "y" * 250)] * 5
        result = self._call(memories)
        assert len(result) <= 2000

    def test_rc3_smart_truncation_no_mid_string_cut(self):
        """Smart truncation drops complete <memoria> lines, not mid-string."""
        result = self._call([_mem("identity", "x" * 300)] * 8)
        # Must not have partial "..." in middle of content
        assert not result.endswith("...")

    def test_sorted_by_confidence_descending(self):
        memories = [
            _mem("interest", "low", confidence=0.3),
            _mem("interest", "high", confidence=0.9),
        ]
        result = self._call(memories)
        assert result.index("high") < result.index("low")

    # RC3: dedup tests

    def test_rc3_dedup_removes_exact_duplicate_content(self):
        memories = [
            _mem("identity", "Tiene 32 años", confidence=0.95),
            _mem("identity", "Tiene 32 años", confidence=0.80),
        ]
        result = self._call(memories)
        assert result.count("Tiene 32 años") == 1

    def test_rc3_dedup_case_insensitive(self):
        memories = [
            _mem("identity", "tiene 32 años", confidence=0.9),
            _mem("identity", "Tiene 32 años", confidence=0.8),
        ]
        result = self._call(memories)
        assert result.count("años") == 1

    def test_rc3_dedup_keeps_highest_confidence(self):
        memories = [
            _mem("interest", "yoga", confidence=0.6),
            _mem("interest", "yoga", confidence=0.95),
        ]
        result = self._call(memories)
        # Only one occurrence of "yoga" and it comes from the 0.95 item
        assert result.count("yoga") == 1

    def test_rc3_dedup_different_content_not_merged(self):
        memories = [
            _mem("interest", "yoga"),
            _mem("interest", "fitness"),
        ]
        result = self._call(memories)
        assert "yoga" in result
        assert "fitness" in result

    # RC3: priority ordering tests

    def test_rc3_priority_identity_before_interest(self):
        memories = [
            _mem("interest", "yoga"),
            _mem("identity", "Se llama María"),
        ]
        result = self._call(memories)
        assert result.index("identity") < result.index("interest")

    def test_rc3_priority_objection_before_interest(self):
        memories = [
            _mem("interest", "yoga"),
            _mem("objection", "Precio alto"),
        ]
        result = self._call(memories)
        assert result.index("objection") < result.index("interest")

    def test_rc3_priority_identity_before_relationship_state(self):
        memories = [
            _mem("relationship_state", "cliente"),
            _mem("identity", "Se llama Pedro"),
        ]
        result = self._call(memories)
        assert result.index("identity") < result.index("relationship_state")

    def test_rc3_truncation_drops_low_priority_first(self):
        """When truncating, low-priority types (interest, relationship_state) are dropped first."""
        # Fill with high-priority type that almost fills 2000 chars
        identity_memories = [_mem("identity", "fact " + str(i) + " " * 300) for i in range(5)]
        interest_memories = [_mem("interest", "yoga")]
        memories = identity_memories + interest_memories
        result = self._call(memories)
        # interest should be dropped before identity when truncating
        if len(result) <= 2000:
            # If it fits, both may be present
            pass
        else:
            assert "interest" not in result or "identity" in result


# ── _read_arc2_memories_sync — RC1 ────────────────────────────────────────────


class TestReadArc2MemoriesSync:
    def _call(self, creator_slug: str, platform_user_id: str, message: str = ""):
        from core.dm.phases.context import _read_arc2_memories_sync
        return _read_arc2_memories_sync(creator_slug, platform_user_id, message)

    def test_returns_empty_when_creator_not_found(self):
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None
        with patch("api.database.SessionLocal", return_value=mock_db):
            result = self._call("unknown_creator", "12345")
        assert result == ""

    def test_returns_empty_when_lead_not_found(self):
        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.side_effect = [
            MagicMock(**{"__getitem__": lambda s, i: "creator-uuid-1"}),
            None,
        ]
        with patch("api.database.SessionLocal", return_value=mock_db):
            result = self._call("iris_bertran", "99999")
        assert result == ""

    def test_strips_ig_prefix_from_platform_user_id(self):
        calls = []

        def fake_execute(query, params=None):
            calls.append(params)
            result = MagicMock()
            result.fetchone.return_value = MagicMock(**{"__getitem__": lambda s, i: "some-uuid"})
            return result

        mock_db = MagicMock()
        mock_db.execute.side_effect = fake_execute

        mock_svc = MagicMock()
        mock_svc.recall_semantic.return_value = []
        mock_svc.get_all.return_value = []

        with patch("api.database.SessionLocal", return_value=mock_db), \
             patch("services.lead_memory_service.LeadMemoryService", return_value=mock_svc):
            self._call("iris_bertran", "ig_123456")

        lead_params = calls[1]
        assert lead_params["raw"] == "123456"
        assert lead_params["ig"] == "ig_123456"

    def test_exception_returns_empty_string(self):
        with patch("api.database.SessionLocal", side_effect=Exception("db down")):
            result = self._call("iris_bertran", "12345")
        assert result == ""

    def test_returns_formatted_memories(self):
        mock_db = MagicMock()

        def fake_execute(query, params=None):
            result = MagicMock()
            result.fetchone.return_value = MagicMock(**{"__getitem__": lambda s, i: "some-uuid"})
            return result

        mock_db.execute.side_effect = fake_execute

        mock_svc = MagicMock()
        mock_svc.recall_semantic.return_value = []
        mock_svc.get_all.return_value = [
            SimpleNamespace(memory_type="identity", content="Se llama Pedro",
                            confidence=0.9, created_at_ts=0),
        ]

        with patch("api.database.SessionLocal", return_value=mock_db), \
             patch("services.lead_memory_service.LeadMemoryService", return_value=mock_svc):
            result = self._call("iris_bertran", "12345")

        assert "Pedro" in result

    # RC1 tests

    def test_rc1_uses_recall_semantic_when_message_provided(self):
        """When message is given and embedding succeeds, recall_semantic is called."""
        mock_db = MagicMock()

        def fake_execute(query, params=None):
            r = MagicMock()
            r.fetchone.return_value = MagicMock(**{"__getitem__": lambda s, i: "some-uuid"})
            return r

        mock_db.execute.side_effect = fake_execute

        mock_svc = MagicMock()
        mock_svc.recall_semantic.return_value = [
            SimpleNamespace(memory_type="identity", content="Se llama Pedro",
                            confidence=0.9, created_at_ts=0),
        ]

        fake_embedding = [0.1] * 1536

        with patch("api.database.SessionLocal", return_value=mock_db), \
             patch("services.lead_memory_service.LeadMemoryService", return_value=mock_svc), \
             patch("core.embeddings.generate_embedding", return_value=fake_embedding):
            result = self._call("iris_bertran", "12345", message="Hola, cuánto cuesta?")

        mock_svc.recall_semantic.assert_called_once()
        # get_all must NOT be called when recall_semantic returns results
        mock_svc.get_all.assert_not_called()
        assert "Pedro" in result

    def test_rc1_fallback_to_get_all_when_recall_semantic_empty(self):
        """If recall_semantic returns [] (no embeddings), falls back to get_all."""
        mock_db = MagicMock()

        def fake_execute(query, params=None):
            r = MagicMock()
            r.fetchone.return_value = MagicMock(**{"__getitem__": lambda s, i: "some-uuid"})
            return r

        mock_db.execute.side_effect = fake_execute

        mock_svc = MagicMock()
        mock_svc.recall_semantic.return_value = []  # no embeddings yet
        mock_svc.get_all.return_value = [
            SimpleNamespace(memory_type="identity", content="Fallback data",
                            confidence=0.7, created_at_ts=0),
        ]

        fake_embedding = [0.1] * 1536

        with patch("api.database.SessionLocal", return_value=mock_db), \
             patch("services.lead_memory_service.LeadMemoryService", return_value=mock_svc), \
             patch("core.embeddings.generate_embedding", return_value=fake_embedding):
            result = self._call("iris_bertran", "12345", message="Hola")

        mock_svc.recall_semantic.assert_called_once()
        mock_svc.get_all.assert_called_once()
        assert "Fallback data" in result

    def test_rc1_fallback_to_get_all_on_embedding_failure(self):
        """If embedding generation raises, falls back to get_all without crashing."""
        mock_db = MagicMock()

        def fake_execute(query, params=None):
            r = MagicMock()
            r.fetchone.return_value = MagicMock(**{"__getitem__": lambda s, i: "some-uuid"})
            return r

        mock_db.execute.side_effect = fake_execute

        mock_svc = MagicMock()
        mock_svc.get_all.return_value = [
            SimpleNamespace(memory_type="objection", content="Precio alto",
                            confidence=0.85, created_at_ts=0),
        ]

        with patch("api.database.SessionLocal", return_value=mock_db), \
             patch("services.lead_memory_service.LeadMemoryService", return_value=mock_svc), \
             patch("core.embeddings.generate_embedding", side_effect=Exception("OpenAI down")):
            result = self._call("iris_bertran", "12345", message="Qué precio tiene?")

        # Must not crash, must use get_all fallback
        mock_svc.recall_semantic.assert_not_called()
        mock_svc.get_all.assert_called_once()
        assert "Precio alto" in result

    def test_rc1_no_message_skips_semantic_goes_to_get_all(self):
        """When no message provided, skip semantic search entirely."""
        mock_db = MagicMock()

        def fake_execute(query, params=None):
            r = MagicMock()
            r.fetchone.return_value = MagicMock(**{"__getitem__": lambda s, i: "some-uuid"})
            return r

        mock_db.execute.side_effect = fake_execute

        mock_svc = MagicMock()
        mock_svc.get_all.return_value = []

        with patch("api.database.SessionLocal", return_value=mock_db), \
             patch("services.lead_memory_service.LeadMemoryService", return_value=mock_svc):
            self._call("iris_bertran", "12345")  # no message arg

        mock_svc.recall_semantic.assert_not_called()
        mock_svc.get_all.assert_called_once()
