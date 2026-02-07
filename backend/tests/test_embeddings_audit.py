"""Audit tests for core/embeddings.py."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test 1: Init / Import
# ---------------------------------------------------------------------------


class TestEmbeddingsImport:
    """Verify module imports and constants."""

    def test_import_module(self):
        from core.embeddings import DEFAULT_MIN_SIMILARITY, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL

        assert EMBEDDING_MODEL == "text-embedding-3-small"
        assert EMBEDDING_DIMENSIONS == 1536
        assert 0.0 <= DEFAULT_MIN_SIMILARITY <= 1.0

    def test_get_openai_client_no_key(self):
        from core.embeddings import get_openai_client

        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            with patch("core.embeddings.os.getenv", return_value=None):
                client = get_openai_client()
                # Should return None when no API key
                assert client is None


# ---------------------------------------------------------------------------
# Test 2: Happy Path -- Vector generation with mock OpenAI
# ---------------------------------------------------------------------------


class TestGenerateEmbedding:
    """Happy path: generating embeddings via mocked OpenAI client."""

    def test_generate_single_embedding(self):
        from core.embeddings import generate_embedding

        mock_embedding_data = MagicMock()
        mock_embedding_data.embedding = [0.1] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding_data]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = generate_embedding("Hello world")

        assert result is not None
        assert len(result) == 1536
        mock_client.embeddings.create.assert_called_once()

    def test_generate_embedding_truncates_long_text(self):
        from core.embeddings import generate_embedding

        mock_embedding_data = MagicMock()
        mock_embedding_data.embedding = [0.5] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding_data]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        long_text = "a" * 50000  # exceeds 30000 char limit

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = generate_embedding(long_text)

        assert result is not None
        # Verify the text was truncated in the call
        call_args = mock_client.embeddings.create.call_args
        assert len(call_args.kwargs.get("input", call_args[1].get("input", ""))) <= 30000


# ---------------------------------------------------------------------------
# Test 3: Edge Case -- Empty text and no client
# ---------------------------------------------------------------------------


class TestEmbeddingsEdgeCases:
    """Edge cases for embedding generation."""

    def test_generate_embedding_no_client_returns_none(self):
        from core.embeddings import generate_embedding

        with patch("core.embeddings.get_openai_client", return_value=None):
            result = generate_embedding("Some text")

        assert result is None

    def test_generate_batch_no_client_returns_nones(self):
        from core.embeddings import generate_embeddings_batch

        with patch("core.embeddings.get_openai_client", return_value=None):
            result = generate_embeddings_batch(["text1", "text2", "text3"])

        assert result == [None, None, None]

    def test_cosine_similarity_zero_vectors(self):
        from core.embeddings import cosine_similarity

        zeros = [0.0] * 10
        normal = [1.0] * 10

        # Zero magnitude vector should return 0
        assert cosine_similarity(zeros, normal) == 0.0
        assert cosine_similarity(normal, zeros) == 0.0
        assert cosine_similarity(zeros, zeros) == 0.0


# ---------------------------------------------------------------------------
# Test 4: Error Handling -- API errors and batch failures
# ---------------------------------------------------------------------------


class TestEmbeddingsErrorHandling:
    """Error handling for API failures."""

    def test_generate_embedding_api_error_returns_none(self):
        from core.embeddings import generate_embedding

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API rate limit")

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = generate_embedding("Some text")

        assert result is None

    def test_generate_batch_api_error_returns_nones(self):
        from core.embeddings import generate_embeddings_batch

        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("Batch API error")

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = generate_embeddings_batch(["a", "b"])

        assert result == [None, None]


# ---------------------------------------------------------------------------
# Test 5: Integration Check -- Cosine similarity and batch embedding
# ---------------------------------------------------------------------------


class TestEmbeddingsIntegration:
    """Integration: cosine similarity math and batch processing."""

    def test_cosine_similarity_identical_vectors(self):
        from core.embeddings import cosine_similarity

        vec = [1.0, 2.0, 3.0, 4.0]
        sim = cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal_vectors(self):
        from core.embeddings import cosine_similarity

        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        sim = cosine_similarity(vec1, vec2)
        assert abs(sim) < 1e-6

    def test_cosine_similarity_opposite_vectors(self):
        from core.embeddings import cosine_similarity

        vec1 = [1.0, 1.0, 1.0]
        vec2 = [-1.0, -1.0, -1.0]
        sim = cosine_similarity(vec1, vec2)
        assert abs(sim - (-1.0)) < 1e-6

    def test_batch_embedding_maps_by_index(self):
        """Batch embedding should correctly map results by index."""
        from core.embeddings import generate_embeddings_batch

        # Build mock response with items indexed out of order
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
            result = generate_embeddings_batch(["text_a", "text_b"])

        assert result[0] is not None
        assert result[1] is not None
        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)

    def test_dimension_validation_in_generate(self):
        """The generated embedding must have exactly EMBEDDING_DIMENSIONS elements."""
        from core.embeddings import EMBEDDING_DIMENSIONS, generate_embedding

        mock_embedding_data = MagicMock()
        mock_embedding_data.embedding = [0.42] * EMBEDDING_DIMENSIONS

        mock_response = MagicMock()
        mock_response.data = [mock_embedding_data]

        mock_client = MagicMock()
        mock_client.embeddings.create.return_value = mock_response

        with patch("core.embeddings.get_openai_client", return_value=mock_client):
            result = generate_embedding("Dimension test")

        assert len(result) == EMBEDDING_DIMENSIONS
