"""Audit tests for core/embeddings.py — OpenAI text-embedding-3-small."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test 1: Init / Import — OpenAI provider constants
# ---------------------------------------------------------------------------


class TestEmbeddingsImport:
    """Verify module imports and constants."""

    def test_import_module_openai_defaults(self):
        from core.embeddings import DEFAULT_MIN_SIMILARITY, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL

        assert EMBEDDING_DIMENSIONS == 1536
        assert EMBEDDING_MODEL == "text-embedding-3-small"
        assert 0.0 <= DEFAULT_MIN_SIMILARITY <= 1.0

    def test_get_openai_client_no_key(self):
        from core.embeddings import get_openai_client

        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            with patch("core.embeddings.os.getenv", return_value=None):
                client = get_openai_client()
                assert client is None


# ---------------------------------------------------------------------------
# Test 2: OpenAI embedding generation (mocked)
# ---------------------------------------------------------------------------


class TestOpenAIEmbeddings:
    """OpenAI API embedding generation — mocked calls."""

    def test_generate_single_embedding(self):
        import core.embeddings as mod

        mock_embedding_data = MagicMock()
        mock_embedding_data.embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding_data]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = mod.generate_embedding("Hello world openai test")

        assert result is not None
        assert len(result) == 1536

    def test_generate_embedding_no_client_returns_none(self):
        import core.embeddings as mod

        with patch("core.embeddings.get_openai_client", return_value=None):
            result = mod.generate_embedding("Some text no client test")

        assert result is None

    def test_generate_batch(self):
        import core.embeddings as mod

        mock_item_0 = MagicMock()
        mock_item_0.index = 0
        mock_item_0.embedding = [0.1] * 1536

        mock_item_1 = MagicMock()
        mock_item_1.index = 1
        mock_item_1.embedding = [0.2] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_item_1, mock_item_0]  # reversed order

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = mod.generate_embeddings_batch(["text_a batch", "text_b batch"])

        assert result[0] is not None
        assert result[1] is not None
        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)

    def test_api_error_returns_none(self):
        import core.embeddings as mod

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API rate limit")

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = mod.generate_embedding("error text test")

        assert result is None

    def test_batch_error_returns_nones(self):
        import core.embeddings as mod

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("Batch error")

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = mod.generate_embeddings_batch(["a test", "b test"])

        assert result == [None, None]

    def test_truncates_long_text(self):
        import core.embeddings as mod

        mock_embedding_data = MagicMock()
        mock_embedding_data.embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding_data]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        long_text = "a " * 20000  # 40000 chars, over 30000 limit

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = mod.generate_embedding(long_text)

        assert result is not None
        # Verify truncation happened — the input to create() should be <= 30000 chars
        call_args = mock_client.embeddings.create.call_args
        assert len(call_args.kwargs.get("input", call_args[1].get("input", ""))) <= 30000

    def test_cache_returns_same_result(self):
        import core.embeddings as mod

        mock_embedding_data = MagicMock()
        mock_embedding_data.embedding = [0.42] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding_data]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            emb1 = mod.generate_embedding("cache test unique input")
            emb2 = mod.generate_embedding("cache test unique input")

        assert emb1 == emb2
        # Should only call API once (second call served from cache)
        assert mock_client.embeddings.create.call_count == 1


# ---------------------------------------------------------------------------
# Test 3: Cosine Similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    """Cosine similarity edge cases."""

    def test_zero_vectors(self):
        from core.embeddings import cosine_similarity

        zeros = [0.0] * 10
        normal = [1.0] * 10

        assert cosine_similarity(zeros, normal) == 0.0
        assert cosine_similarity(normal, zeros) == 0.0
        assert cosine_similarity(zeros, zeros) == 0.0

    def test_identical_vectors(self):
        from core.embeddings import cosine_similarity

        vec = [1.0, 2.0, 3.0, 4.0]
        sim = cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        from core.embeddings import cosine_similarity

        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        sim = cosine_similarity(vec1, vec2)
        assert abs(sim) < 1e-6

    def test_opposite_vectors(self):
        from core.embeddings import cosine_similarity

        vec1 = [1.0, 1.0, 1.0]
        vec2 = [-1.0, -1.0, -1.0]
        sim = cosine_similarity(vec1, vec2)
        assert abs(sim - (-1.0)) < 1e-6

    def test_dimension_constant_is_1536(self):
        """EMBEDDING_DIMENSIONS must be 1536 (OpenAI text-embedding-3-small)."""
        from core.embeddings import EMBEDDING_DIMENSIONS

        assert EMBEDDING_DIMENSIONS == 1536
