"""Audit tests for core/embeddings.py — Gemini gemini-embedding-001."""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test 1: Init / Import — Gemini provider constants
# ---------------------------------------------------------------------------


class TestEmbeddingsImport:
    """Verify module imports and constants."""

    def test_import_module_gemini_defaults(self):
        from core.embeddings import DEFAULT_MIN_SIMILARITY, EMBEDDING_DIMENSIONS, EMBEDDING_MODEL

        assert EMBEDDING_DIMENSIONS == 1536
        assert "gemini-embedding-001" in EMBEDDING_MODEL
        assert 0.0 <= DEFAULT_MIN_SIMILARITY <= 1.0

    def test_no_api_key_returns_none(self):
        import core.embeddings as mod

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "", "GEMINI_API_KEY": ""}, clear=False):
            with patch("core.embeddings._get_gemini_api_key", return_value=None):
                result = mod.generate_embedding("test text no key")
                assert result is None


# ---------------------------------------------------------------------------
# Test 2: Gemini embedding generation (mocked httpx)
# ---------------------------------------------------------------------------


class TestGeminiEmbeddings:
    """Gemini API embedding generation — mocked httpx calls."""

    def _mock_single_response(self, values):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"embedding": {"values": values}}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_generate_single_embedding(self):
        import core.embeddings as mod

        mock_resp = self._mock_single_response([0.1] * 1536)

        with patch("core.embeddings._get_gemini_api_key", return_value="fake-key"):
            with patch("httpx.post", return_value=mock_resp):
                result = mod.generate_embedding("Hello world gemini test")

        assert result is not None
        assert len(result) == 1536

    def test_generate_embedding_no_key_returns_none(self):
        import core.embeddings as mod

        with patch("core.embeddings._get_gemini_api_key", return_value=None):
            result = mod.generate_embedding("Some text no key test")

        assert result is None

    def test_generate_embedding_empty_text_returns_none(self):
        import core.embeddings as mod

        result = mod.generate_embedding("")
        assert result is None

        result = mod.generate_embedding("   ")
        assert result is None

    def test_generate_batch(self):
        import core.embeddings as mod

        side_effects = [[0.1] * 1536, [0.2] * 1536]

        with patch("core.embeddings.generate_embedding", side_effect=side_effects):
            result = mod.generate_embeddings_batch(["text_a batch", "text_b batch"])

        assert result[0] is not None
        assert result[1] is not None
        assert result[0][0] == pytest.approx(0.1)
        assert result[1][0] == pytest.approx(0.2)

    def test_api_error_returns_none(self):
        import core.embeddings as mod

        with patch("core.embeddings._get_gemini_api_key", return_value="fake-key"):
            with patch("httpx.post", side_effect=Exception("API rate limit")):
                result = mod.generate_embedding("error text test")

        assert result is None

    def test_batch_error_returns_nones(self):
        import core.embeddings as mod

        with patch("core.embeddings._get_gemini_api_key", return_value="fake-key"):
            with patch("httpx.post", side_effect=Exception("Batch error")):
                result = mod.generate_embeddings_batch(["a test", "b test"])

        assert result == [None, None]

    def test_truncates_long_text(self):
        import core.embeddings as mod

        mock_resp = self._mock_single_response([0.1] * 1536)
        long_text = "a " * 20000  # 40000 chars, over 30000 limit

        with patch("core.embeddings._get_gemini_api_key", return_value="fake-key"):
            with patch("httpx.post", return_value=mock_resp) as mock_post:
                result = mod.generate_embedding(long_text)

        assert result is not None
        call_json = mock_post.call_args.kwargs["json"]
        sent_text = call_json["content"]["parts"][0]["text"]
        assert len(sent_text) <= 30000

    def test_cache_returns_same_result(self):
        import core.embeddings as mod

        mock_resp = self._mock_single_response([0.42] * 1536)

        with patch("core.embeddings._get_gemini_api_key", return_value="fake-key"):
            with patch("httpx.post", return_value=mock_resp) as mock_post:
                emb1 = mod.generate_embedding("cache test unique gemini input xyz")
                emb2 = mod.generate_embedding("cache test unique gemini input xyz")

        assert emb1 == emb2
        # Should only call API once (second call served from cache)
        assert mock_post.call_count == 1

    def test_task_type_retrieval_query(self):
        import core.embeddings as mod

        mock_resp = self._mock_single_response([0.5] * 1536)

        with patch("core.embeddings._get_gemini_api_key", return_value="fake-key"):
            with patch("httpx.post", return_value=mock_resp) as mock_post:
                mod.generate_embedding("search query text", task_type="RETRIEVAL_QUERY")

        call_json = mock_post.call_args.kwargs["json"]
        assert call_json["taskType"] == "RETRIEVAL_QUERY"


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
        """EMBEDDING_DIMENSIONS must be 1536 (matches pgvector schema)."""
        from core.embeddings import EMBEDDING_DIMENSIONS

        assert EMBEDDING_DIMENSIONS == 1536
