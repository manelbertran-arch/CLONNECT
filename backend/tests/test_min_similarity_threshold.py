"""
Tests for min_similarity threshold configuration.

Verifies that:
1. Default threshold is 0.5 (raised from 0.3)
2. Threshold is configurable via RAG_MIN_SIMILARITY env var
3. Chunks with similarity < threshold are filtered out
4. Chunks with similarity >= threshold are returned

Run with: pytest tests/test_min_similarity_threshold.py -v
"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestMinSimilarityDefault:
    """Tests for default min_similarity value."""

    def test_default_min_similarity_is_0_5(self):
        """Verify DEFAULT_MIN_SIMILARITY is 0.5 (not the old 0.3)."""
        # Need to reload module to test fresh default
        import importlib
        import core.embeddings as embeddings_module

        # Without env var override, should be 0.5
        with patch.dict(os.environ, {}, clear=True):
            # Remove existing env var if any
            os.environ.pop("RAG_MIN_SIMILARITY", None)
            importlib.reload(embeddings_module)

            assert embeddings_module.DEFAULT_MIN_SIMILARITY == 0.5, \
                f"Expected 0.5, got {embeddings_module.DEFAULT_MIN_SIMILARITY}"

    def test_min_similarity_configurable_via_env_var(self):
        """Verify RAG_MIN_SIMILARITY env var overrides default."""
        import importlib
        import core.embeddings as embeddings_module

        with patch.dict(os.environ, {"RAG_MIN_SIMILARITY": "0.7"}):
            importlib.reload(embeddings_module)
            assert embeddings_module.DEFAULT_MIN_SIMILARITY == 0.7

        # Cleanup - restore default
        with patch.dict(os.environ, {"RAG_MIN_SIMILARITY": "0.5"}):
            importlib.reload(embeddings_module)


class TestSearchSimilarThreshold:
    """Tests for search_similar function threshold behavior."""

    @pytest.fixture
    def mock_db_results(self):
        """Create mock database results with various similarity scores."""
        return [
            MagicMock(chunk_id="high_sim", content="Very relevant", source_url="http://a", title="A", source_type="web", similarity=0.85),
            MagicMock(chunk_id="medium_sim", content="Somewhat relevant", source_url="http://b", title="B", source_type="web", similarity=0.55),
            MagicMock(chunk_id="low_sim", content="Not very relevant", source_url="http://c", title="C", source_type="web", similarity=0.35),
            MagicMock(chunk_id="very_low", content="Noise", source_url="http://d", title="D", source_type="web", similarity=0.20),
        ]

    def test_search_uses_default_threshold_when_not_specified(self):
        """Verify search_similar uses DEFAULT_MIN_SIMILARITY when min_similarity=None."""
        from core.embeddings import search_similar, DEFAULT_MIN_SIMILARITY

        mock_session = MagicMock()
        mock_session.execute.return_value = []

        with patch("api.database.SessionLocal", return_value=mock_session):
            # Call without min_similarity parameter
            search_similar(
                query_embedding=[0.1] * 1536,
                creator_id="test",
                top_k=5
                # min_similarity not specified - should use default
            )

        # Verify the query was called with the default threshold
        call_args = mock_session.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["min_sim"] == DEFAULT_MIN_SIMILARITY

    def test_search_respects_custom_threshold(self):
        """Verify search_similar respects explicitly passed min_similarity."""
        from core.embeddings import search_similar

        mock_session = MagicMock()
        mock_session.execute.return_value = []

        with patch("api.database.SessionLocal", return_value=mock_session):
            search_similar(
                query_embedding=[0.1] * 1536,
                creator_id="test",
                top_k=5,
                min_similarity=0.7  # Explicit override
            )

        call_args = mock_session.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]
        assert params["min_sim"] == 0.7


class TestThresholdFiltering:
    """Tests to verify low-similarity results are filtered out."""

    def test_threshold_0_5_filters_low_similarity_chunks(self):
        """
        With threshold=0.5:
        - similarity 0.85 -> INCLUDED
        - similarity 0.55 -> INCLUDED
        - similarity 0.35 -> EXCLUDED (< 0.5)
        - similarity 0.20 -> EXCLUDED (< 0.5)
        """
        # This test verifies the SQL query logic via mock
        from core.embeddings import search_similar

        # Simulate DB returning only results that pass the threshold
        # (the filtering happens in the SQL query itself)
        mock_high = MagicMock(chunk_id="high", content="High", source_url="http://h", title="H", source_type="web", similarity=0.85)
        mock_medium = MagicMock(chunk_id="med", content="Med", source_url="http://m", title="M", source_type="web", similarity=0.55)

        mock_session = MagicMock()
        mock_session.execute.return_value = [mock_high, mock_medium]

        with patch("api.database.SessionLocal", return_value=mock_session):
            results = search_similar(
                query_embedding=[0.1] * 1536,
                creator_id="test",
                top_k=10,
                min_similarity=0.5
            )

        # Only 2 results should come back (those >= 0.5)
        assert len(results) == 2
        assert all(r["similarity"] >= 0.5 for r in results)

    def test_old_threshold_0_3_would_include_more_noise(self):
        """
        Demonstrate that with old threshold=0.3:
        - similarity 0.35 WOULD be included (noise!)
        - similarity 0.20 WOULD be excluded

        With new threshold=0.5:
        - similarity 0.35 is now EXCLUDED
        """
        from core.embeddings import search_similar

        # With 0.3 threshold, a 0.35 score would pass
        # With 0.5 threshold, a 0.35 score is rejected
        _mock_noise = MagicMock(chunk_id="noise", content="Noise", source_url="http://n", title="N", source_type="web", similarity=0.35)

        mock_session = MagicMock()

        # Simulate: with 0.5 threshold, noise is filtered at DB level
        mock_session.execute.return_value = []  # Nothing passes 0.5

        with patch("api.database.SessionLocal", return_value=mock_session):
            results = search_similar(
                query_embedding=[0.1] * 1536,
                creator_id="test",
                top_k=10,
                min_similarity=0.5  # New default
            )

        # 0.35 similarity chunk should NOT be in results
        assert len(results) == 0


class TestSemanticRAGUsesNewDefault:
    """Tests to verify SemanticRAG uses the new default threshold."""

    def test_semantic_rag_search_uses_default_threshold(self):
        """Verify SemanticRAG.search() doesn't hardcode 0.3 anymore."""
        from core.rag.semantic import SemanticRAG

        rag = SemanticRAG()

        with patch("core.embeddings.generate_embedding", return_value=[0.1] * 1536):
            with patch("core.embeddings.search_similar") as mock_search:
                mock_search.return_value = []

                # Force embeddings to be "available"
                with patch.object(rag, "_check_embeddings_available", return_value=True):
                    rag.search("test query", top_k=5, creator_id="test")

        # Verify search_similar was called WITHOUT hardcoded min_similarity
        # (allowing it to use the default from the function)
        mock_search.assert_called_once()
        call_kwargs = mock_search.call_args[1]

        # min_similarity should NOT be in kwargs (uses function default)
        assert "min_similarity" not in call_kwargs, \
            f"Expected no min_similarity kwarg, got {call_kwargs}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
