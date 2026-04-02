"""
Functional tests for System #10: Episodic Memory.

Tests the _episodic_search function and SemanticMemoryPgvector integration.
Target: 9/10 pass.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_result(content, role="user", similarity=0.75):
    return {
        "content": content,
        "role": role,
        "similarity": similarity,
        "created_at": "2026-03-30T10:00:00",
        "metadata": {},
    }


def _run_search(search_results=None, message="me interesa el curso de nutrición",
                recent_history=None, db_fails=False):
    """Run _episodic_search with mocked DB and SemanticMemoryPgvector."""
    from core.dm.phases.context import _episodic_search

    mock_sm = MagicMock()
    mock_sm.search.return_value = search_results or []

    mock_session = MagicMock()
    creator_row = MagicMock()
    creator_row.__getitem__ = lambda self, i: "aaaa-bbbb-cccc"
    lead_row = MagicMock()
    lead_row.__getitem__ = lambda self, i: "dddd-eeee-ffff"
    mock_session.execute.return_value.fetchone.side_effect = [creator_row, lead_row]

    mock_session_cls = MagicMock(return_value=mock_session)
    if db_fails:
        mock_session_cls.side_effect = Exception("DB down")

    with patch("core.semantic_memory_pgvector.SemanticMemoryPgvector") as cls_mock:
        cls_mock.return_value = mock_sm
        with patch("api.database.SessionLocal", mock_session_cls):
            result = _episodic_search(
                "iris_bertran", "12345", message,
                recent_history=recent_history,
            )
    return result, mock_sm, cls_mock


class TestEpisodicSearch(unittest.TestCase):
    """Test _episodic_search function from core/dm/phases/context.py."""

    def test_01_returns_empty_when_no_results(self):
        """T01: No embeddings found → empty string."""
        result, _, _ = _run_search(search_results=[])
        self.assertEqual(result, "")

    def test_02_formats_results_correctly(self):
        """T02: Results formatted as 'lead:' and 'tú:' with quotes."""
        results = [
            _make_result("Me interesa el curso de nutrición", role="user", similarity=0.80),
            _make_result("Claro, el curso cuesta 297€", role="assistant", similarity=0.75),
        ]
        result, _, _ = _run_search(search_results=results)
        self.assertIn("Conversaciones pasadas relevantes:", result)
        self.assertIn('- lead: "Me interesa el curso de nutrición"', result)
        self.assertIn('- tú: "Claro, el curso cuesta 297€"', result)

    def test_03_min_similarity_060(self):
        """T03: Verify search is called with min_similarity >= 0.60."""
        results = [_make_result("test", similarity=0.65)]
        _, mock_sm, _ = _run_search(search_results=results)
        self.assertTrue(mock_sm.search.called)
        for call in mock_sm.search.call_args_list:
            kwargs = call.kwargs if call.kwargs else {}
            if "min_similarity" in kwargs:
                self.assertGreaterEqual(kwargs["min_similarity"], 0.60)

    def test_04_deduplicates_against_recent_history(self):
        """T04: Messages already in history are filtered out."""
        dup_content = "Me interesa el curso de nutrición pero el precio es alto"
        results = [
            _make_result(dup_content, similarity=0.80),
            _make_result("Quiero saber sobre los horarios del gym", similarity=0.70),
        ]
        recent = [{"role": "user", "content": dup_content}]
        result, _, _ = _run_search(search_results=results, recent_history=recent)
        self.assertNotIn("precio es alto", result)
        self.assertIn("horarios", result)

    def test_05_caps_at_3_results(self):
        """T05: Even with 5 results, only 3 are included."""
        results = [
            _make_result(f"Message number {i} about different topics", similarity=0.90 - i * 0.05)
            for i in range(5)
        ]
        result, _, _ = _run_search(search_results=results)
        lines = [l for l in result.split("\n") if l.startswith("- ")]
        self.assertLessEqual(len(lines), 3)

    def test_06_content_truncation_at_250_chars(self):
        """T06: Long content is truncated at 250 chars, not 150."""
        long_content = "A" * 300
        results = [_make_result(long_content, similarity=0.80)]
        result, _, _ = _run_search(search_results=results)
        self.assertIn("A" * 250 + "...", result)

    def test_07_uuid_resolution_tried_first(self):
        """T07: UUID pair is tried before slug pair."""
        results = [_make_result("Found via UUID", similarity=0.80)]
        result, mock_sm, cls_mock = _run_search(search_results=results)
        self.assertIn("Found via UUID", result)
        first_call = cls_mock.call_args_list[0][0]
        self.assertEqual(first_call[0], "aaaa-bbbb-cccc")

    def test_08_db_failure_falls_back_to_slug(self):
        """T08: If DB resolution fails, falls back to slug pair."""
        results = [_make_result("Found via slug", similarity=0.75)]
        result, _, _ = _run_search(search_results=results, db_fails=True)
        self.assertIn("Found via slug", result)

    def test_09_empty_recent_history_no_crash(self):
        """T09: Empty or None recent_history doesn't crash."""
        results = [_make_result("Some memory", similarity=0.80)]
        result1, _, _ = _run_search(search_results=results, recent_history=None)
        result2, _, _ = _run_search(search_results=results, recent_history=[])
        self.assertIn("Some memory", result1)
        self.assertIn("Some memory", result2)

    def test_10_role_mapping(self):
        """T10: user → 'lead', assistant → 'tú'."""
        results = [
            _make_result("User said this", role="user", similarity=0.80),
            _make_result("Bot replied this", role="assistant", similarity=0.75),
        ]
        result, _, _ = _run_search(search_results=results)
        self.assertIn("- lead:", result)
        self.assertIn("- tú:", result)


class TestEmbeddingIndexing(unittest.TestCase):
    """Test BUG-EP-01 fix: post_response writes to conversation_embeddings."""

    def test_post_response_calls_add_message(self):
        """Verify sync_post_response calls add_message for user and assistant."""
        from core.dm.post_response import sync_post_response

        mock_agent = MagicMock()
        mock_agent.creator_id = "iris_bertran"
        mock_agent.products = []

        mock_follower = MagicMock()
        mock_follower.last_messages = []
        mock_follower.total_messages = 5
        mock_follower.name = "Tania"
        mock_follower.is_customer = False
        mock_follower.purchase_intent_score = 0.3

        mock_sm = MagicMock()

        with patch.dict(os.environ, {
            "ENABLE_SEMANTIC_MEMORY_PGVECTOR": "true",
            "ENABLE_DNA_TRIGGERS": "false",
        }):
            with patch("core.semantic_memory_pgvector.get_semantic_memory", return_value=mock_sm):
                with patch("core.copilot_service.get_copilot_service") as mock_copilot:
                    mock_copilot.return_value.is_copilot_enabled.return_value = False
                    sync_post_response(
                        agent=mock_agent,
                        follower=mock_follower,
                        message="Me interesa el curso",
                        formatted_content="Claro, te cuento!",
                        intent_value="product_inquiry",
                        sender_id="12345",
                        metadata={},
                        cognitive_metadata={},
                    )

        calls = mock_sm.add_message.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], ("user", "Me interesa el curso"))
        self.assertEqual(calls[1][0], ("assistant", "Claro, te cuento!"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
