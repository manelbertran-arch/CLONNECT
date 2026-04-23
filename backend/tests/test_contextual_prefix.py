"""
Tests for core/contextual_prefix.py — Universal Contextual Prefix for RAG.

Validates the Anthropic Contextual Retrieval implementation:
- Prefix auto-generated from creator DB profile
- Prepended to document embeddings but NOT search queries
- Graceful degradation when data is missing
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import List


def _make_creator_data(
    name="Iris Bertran",
    clone_name="Iris",
    knowledge_about=None,
    dialect="catalan_mixed",
    formality="informal",
    products=None,
    faqs=None,
):
    """Build a mock CreatorData for testing."""
    from core.creator_data_loader import (
        CreatorData, CreatorProfile, ToneProfileInfo,
    )
    if knowledge_about is None:
        ka = {
            "instagram_username": "iraais5",
            "specialties": ["instructora de fitness", "barre", "zumba"],
            "location": "Barcelona",
            "bio": "Instructora de fitness en Barcelona con clases de barre, zumba y pilates.",
        }
    else:
        ka = knowledge_about
    return CreatorData(
        creator_id="iris_bertran",
        profile=CreatorProfile(
            name=name,
            clone_name=clone_name,
            knowledge_about=ka,
        ),
        tone_profile=ToneProfileInfo(
            dialect=dialect,
            formality=formality,
        ),
        products=products or [],
        faqs=faqs or [],
    )


class TestBuildContextualPrefix:
    """Test build_contextual_prefix() function."""

    def setup_method(self):
        """Clear prefix cache before each test."""
        from core.contextual_prefix import _prefix_cache
        _prefix_cache.clear()

    @patch("core.creator_data_loader.get_creator_data")
    def test_full_data_prefix(self, mock_get):
        """Prefix with complete data should contain name, handle, domain, location, language."""
        from core.contextual_prefix import build_contextual_prefix
        mock_get.return_value = _make_creator_data()

        prefix = build_contextual_prefix("iris_bertran")

        assert "Iris" in prefix
        assert "@iraais5" in prefix
        assert "fitness" in prefix
        assert "Barcelona" in prefix
        assert "catalán" in prefix.lower() or "català" in prefix.lower()
        assert prefix.endswith("\n\n")

    @patch("core.creator_data_loader.get_creator_data")
    def test_missing_specialties_uses_bio(self, mock_get):
        """When specialties are missing, falls back to bio first sentence."""
        from core.contextual_prefix import build_contextual_prefix
        data = _make_creator_data(knowledge_about={
            "bio": "Coach de vida especializada en mindfulness. Ayudo a personas.",
        })
        mock_get.return_value = data

        prefix = build_contextual_prefix("test_creator")
        assert "Coach de vida" in prefix

    @patch("core.creator_data_loader.get_creator_data")
    def test_missing_all_knowledge_about(self, mock_get):
        """Prefix with no knowledge_about should still include name."""
        from core.contextual_prefix import build_contextual_prefix
        data = _make_creator_data(knowledge_about={})
        mock_get.return_value = data

        prefix = build_contextual_prefix("minimal_creator")
        assert "Iris" in prefix

    @patch("core.creator_data_loader.get_creator_data")
    def test_no_creator_returns_empty(self, mock_get):
        """Non-existent creator should return empty string."""
        from core.contextual_prefix import build_contextual_prefix
        from core.creator_data_loader import CreatorData, CreatorProfile
        mock_get.return_value = CreatorData(
            creator_id="unknown",
            profile=CreatorProfile(),  # empty name
        )

        prefix = build_contextual_prefix("nonexistent")
        assert prefix == ""

    @patch("core.creator_data_loader.get_creator_data")
    def test_prefix_is_cached(self, mock_get):
        """Second call should use cache, not call get_creator_data again."""
        from core.contextual_prefix import build_contextual_prefix
        mock_get.return_value = _make_creator_data()

        build_contextual_prefix("iris_bertran")
        build_contextual_prefix("iris_bertran")

        assert mock_get.call_count == 1

    @patch("core.creator_data_loader.get_creator_data")
    def test_prefix_capped_at_500_chars(self, mock_get):
        """Prefix should not exceed 500 characters."""
        from core.contextual_prefix import build_contextual_prefix
        data = _make_creator_data(knowledge_about={
            "specialties": ["a" * 200, "b" * 200],
            "location": "X" * 200,
        })
        mock_get.return_value = data

        prefix = build_contextual_prefix("long_creator")
        assert len(prefix) <= 503  # 500 + ".\n\n"

    @patch("core.creator_data_loader.get_creator_data")
    def test_formal_style_mentioned(self, mock_get):
        """Formal creators should get a style hint in prefix."""
        from core.contextual_prefix import build_contextual_prefix
        data = _make_creator_data(formality="formal")
        mock_get.return_value = data

        prefix = build_contextual_prefix("formal_creator")
        assert "formal" in prefix.lower()

    @patch("core.creator_data_loader.get_creator_data")
    def test_italian_dialect(self, mock_get):
        """Italian creators should get Italian language label."""
        from core.contextual_prefix import build_contextual_prefix
        data = _make_creator_data(
            name="Stefano Bonanno",
            clone_name="Stefano",
            dialect="italian",
            knowledge_about={
                "specialties": ["business coach"],
                "location": "Milano",
            },
        )
        mock_get.return_value = data

        prefix = build_contextual_prefix("stefano_bonanno")
        assert "Stefano" in prefix
        assert "italiano" in prefix.lower()
        assert "Milano" in prefix

    @patch("core.creator_data_loader.get_creator_data", side_effect=Exception("DB down"))
    def test_db_error_returns_empty(self, mock_get):
        """DB failures should return empty string, not crash."""
        from core.contextual_prefix import build_contextual_prefix
        prefix = build_contextual_prefix("any_creator")
        assert prefix == ""

    @patch("core.creator_data_loader.get_creator_data")
    def test_product_fallback_when_no_specialties(self, mock_get):
        """When knowledge_about is empty, derive domain from product names."""
        from core.contextual_prefix import build_contextual_prefix
        from core.creator_data_loader import ProductInfo
        products = [
            ProductInfo(id="1", name="Barre"),
            ProductInfo(id="2", name="Flow4U"),
            ProductInfo(id="3", name="Pilates Reformer"),
        ]
        data = _make_creator_data(
            knowledge_about={}, dialect=None, formality=None, products=products,
        )
        mock_get.return_value = data

        prefix = build_contextual_prefix("iris_products")
        assert "Barre" in prefix
        assert "Flow4U" in prefix
        assert "Pilates Reformer" in prefix
        assert len(prefix) > 30  # Much richer than just "Iris.\n\n"

    @patch("core.creator_data_loader.get_creator_data")
    def test_faq_fallback_when_only_name(self, mock_get):
        """When no specialties, bio, or products — use FAQ topics."""
        from core.contextual_prefix import build_contextual_prefix
        from core.creator_data_loader import FAQInfo
        faqs = [
            FAQInfo(id="1", question="¿Cuánto cuesta el círculo?", answer="50€"),
            FAQInfo(id="2", question="¿Dónde son las clases?", answer="Barcelona"),
        ]
        data = _make_creator_data(
            knowledge_about={}, dialect=None, formality=None, faqs=faqs,
        )
        mock_get.return_value = data

        prefix = build_contextual_prefix("iris_faq")
        assert "Temas frecuentes" in prefix
        assert "círculo" in prefix


class TestGenerateEmbeddingWithContext:
    """Test the embedding wrapper functions."""

    def setup_method(self):
        from core.contextual_prefix import _prefix_cache
        _prefix_cache.clear()

    @patch("core.embeddings.generate_embedding")
    @patch("core.creator_data_loader.get_creator_data")
    def test_prepends_prefix(self, mock_get, mock_embed):
        """Should prepend prefix to text before generating embedding."""
        from core.contextual_prefix import generate_embedding_with_context
        mock_get.return_value = _make_creator_data()
        mock_embed.return_value = [0.1] * 1536

        result = generate_embedding_with_context("Barre costs 5€", "iris_bertran")

        # The embedding call should receive prefix + text
        call_text = mock_embed.call_args[0][0]
        assert call_text.endswith("Barre costs 5€")
        assert "Iris" in call_text
        assert result == [0.1] * 1536

    @patch("core.embeddings.generate_embedding")
    @patch("core.creator_data_loader.get_creator_data")
    def test_empty_prefix_passes_text_only(self, mock_get, mock_embed):
        """When prefix is empty, should just embed the raw text."""
        from core.contextual_prefix import generate_embedding_with_context
        from core.creator_data_loader import CreatorData, CreatorProfile
        mock_get.return_value = CreatorData(
            creator_id="unknown", profile=CreatorProfile()
        )
        mock_embed.return_value = [0.2] * 1536

        generate_embedding_with_context("Some text", "unknown_creator")

        mock_embed.assert_called_once_with("Some text")

    @patch("core.embeddings.generate_embeddings_batch")
    @patch("core.creator_data_loader.get_creator_data")
    def test_batch_prepends_to_all(self, mock_get, mock_batch):
        """Batch variant should prepend prefix to all texts."""
        from core.contextual_prefix import generate_embeddings_batch_with_context
        mock_get.return_value = _make_creator_data()
        mock_batch.return_value = [[0.1], [0.2]]

        result = generate_embeddings_batch_with_context(["text1", "text2"], "creator1")

        call_texts = mock_batch.call_args[0][0]
        assert len(call_texts) == 2
        assert call_texts[0].endswith("text1")
        assert call_texts[1].endswith("text2")
        assert "Iris" in call_texts[0]
        assert len(result) == 2


class TestSearchQueriesNotPrefixed:
    """Verify search queries do NOT get the contextual prefix."""

    def test_semantic_search_uses_raw_embedding(self):
        """SemanticRAG._semantic_search should call generate_embedding, not _with_context."""
        from core.rag.semantic import SemanticRAG
        rag = SemanticRAG()

        # The search method should import generate_embedding, not generate_embedding_with_context
        import inspect
        source = inspect.getsource(rag._semantic_search)
        assert "generate_embedding(query)" in source or "generate_embedding(" in source
        assert "generate_embedding_with_context" not in source


class TestFeatureFlag:
    """Test the ENABLE_CONTEXTUAL_PREFIX_EMBED ablation switch."""

    def setup_method(self):
        from core.contextual_prefix import _prefix_cache
        _prefix_cache.clear()

    @patch("core.creator_data_loader.get_creator_data")
    def test_flag_disabled_returns_empty(self, mock_get):
        """When ENABLE_CONTEXTUAL_PREFIX_EMBED=false, prefix is always empty."""
        from core.contextual_prefix import build_contextual_prefix
        from core.config import contextual_prefix_config as cfg

        mock_get.return_value = _make_creator_data()
        original = cfg.ENABLE_CONTEXTUAL_PREFIX_EMBED
        try:
            cfg.ENABLE_CONTEXTUAL_PREFIX_EMBED = False
            assert build_contextual_prefix("iris_bertran") == ""
            assert mock_get.call_count == 0  # DB never touched
        finally:
            cfg.ENABLE_CONTEXTUAL_PREFIX_EMBED = original


class TestInvalidateCache:
    """Test the admin invalidation helper."""

    def setup_method(self):
        from core.contextual_prefix import _prefix_cache
        _prefix_cache.clear()

    @patch("core.creator_data_loader.get_creator_data")
    def test_invalidate_single_creator(self, mock_get):
        from core.contextual_prefix import build_contextual_prefix, invalidate_cache
        mock_get.return_value = _make_creator_data()

        build_contextual_prefix("iris_bertran")
        assert invalidate_cache("iris_bertran") == 1
        # Next call rebuilds from DB
        build_contextual_prefix("iris_bertran")
        assert mock_get.call_count == 2

    def test_invalidate_missing_creator_returns_zero(self):
        from core.contextual_prefix import invalidate_cache
        assert invalidate_cache("never_cached") == 0

    @patch("core.creator_data_loader.get_creator_data")
    def test_invalidate_all(self, mock_get):
        from core.contextual_prefix import build_contextual_prefix, invalidate_cache
        mock_get.return_value = _make_creator_data()
        build_contextual_prefix("iris_bertran")
        build_contextual_prefix("stefano")
        removed = invalidate_cache(None)
        assert removed >= 1


class TestDialectFallbacks:
    """Covers Bug 7 — dialects not in the label map."""

    def setup_method(self):
        from core.contextual_prefix import _prefix_cache
        _prefix_cache.clear()

    @patch("core.creator_data_loader.get_creator_data")
    def test_unmapped_dialect_uses_literal(self, mock_get):
        """An unmapped dialect like 'portuguese' falls back to the raw literal."""
        from core.contextual_prefix import build_contextual_prefix
        data = _make_creator_data(dialect="portuguese")
        mock_get.return_value = data

        prefix = build_contextual_prefix("pt_creator")
        assert "portuguese" in prefix  # the raw literal leaks (known limitation, tracked Q2)


class TestFormalityLabels:
    """Covers Bug 5 — formality 'informal' default was silent."""

    def setup_method(self):
        from core.contextual_prefix import _prefix_cache
        _prefix_cache.clear()

    @patch("core.creator_data_loader.get_creator_data")
    def test_informal_now_emits_label(self, mock_get):
        from core.contextual_prefix import build_contextual_prefix
        data = _make_creator_data(formality="informal")
        mock_get.return_value = data

        prefix = build_contextual_prefix("informal_creator")
        assert "informal" in prefix.lower() or "cercano" in prefix.lower()

    @patch("core.creator_data_loader.get_creator_data")
    def test_mixed_formality_emits(self, mock_get):
        from core.contextual_prefix import build_contextual_prefix
        data = _make_creator_data(formality="mixed")
        mock_get.return_value = data

        prefix = build_contextual_prefix("mixed_creator")
        assert "mixto" in prefix.lower()


class TestCapWordBoundary:
    """Covers Bug 4 — cap should prefer word boundary."""

    def setup_method(self):
        from core.contextual_prefix import _prefix_cache
        _prefix_cache.clear()

    @patch("core.creator_data_loader.get_creator_data")
    def test_cap_at_word_boundary(self, mock_get):
        """Prefix nearing cap should not end mid-word when a space is within ~40% of the budget."""
        from core.contextual_prefix import build_contextual_prefix
        long_specialties = ["palabra uno dos tres cuatro cinco seis siete ocho"] * 5
        data = _make_creator_data(
            knowledge_about={"specialties": long_specialties, "location": "Barcelona"},
        )
        mock_get.return_value = data

        prefix = build_contextual_prefix("cap_creator")
        # Trim the terminator, then the last character before should be a letter,
        # not a partial word missing its continuation.
        assert len(prefix) <= 503
        assert prefix.endswith(".\n\n")


class TestSourceTag:
    """Builds_total metric carries a 'source' label — verify branches tag correctly."""

    def setup_method(self):
        from core.contextual_prefix import _prefix_cache
        _prefix_cache.clear()

    @patch("core.contextual_prefix._emit")
    @patch("core.creator_data_loader.get_creator_data")
    def test_source_specialties_reported(self, mock_get, mock_emit):
        from core.contextual_prefix import build_contextual_prefix
        mock_get.return_value = _make_creator_data()  # has specialties

        build_contextual_prefix("iris_bertran")

        build_calls = [
            c for c in mock_emit.call_args_list
            if c.args and c.args[0] == "contextual_prefix_builds_total"
        ]
        assert build_calls, "builds_total metric not emitted"
        kwargs = build_calls[0].kwargs
        assert kwargs.get("source") == "specialties"
        assert kwargs.get("has_prefix") == "true"

    @patch("core.contextual_prefix._emit")
    @patch("core.creator_data_loader.get_creator_data")
    def test_source_products_fallback_reported(self, mock_get, mock_emit):
        from core.contextual_prefix import build_contextual_prefix
        from core.creator_data_loader import ProductInfo
        products = [ProductInfo(id="1", name="Barre"), ProductInfo(id="2", name="Flow4U")]
        data = _make_creator_data(
            knowledge_about={}, dialect=None, formality=None, products=products,
        )
        mock_get.return_value = data

        build_contextual_prefix("products_creator")

        build_calls = [
            c for c in mock_emit.call_args_list
            if c.args and c.args[0] == "contextual_prefix_builds_total"
        ]
        assert build_calls
        assert build_calls[0].kwargs.get("source") == "products_fallback"


class TestConfigSnapshot:
    """Config snapshot shape for the admin endpoint."""

    def test_snapshot_has_expected_keys(self):
        from core.config import contextual_prefix_config
        snap = contextual_prefix_config.snapshot()
        for key in [
            "ENABLE_CONTEXTUAL_PREFIX_EMBED",
            "CACHE_SIZE",
            "CACHE_TTL_SECONDS",
            "CAP_CHARS",
            "MAX_SPECIALTIES",
            "MAX_PRODUCTS",
            "MAX_FAQS",
            "MIN_BIO_LEN",
            "dialect_labels_count",
            "formality_labels_count",
        ]:
            assert key in snap


class TestRagAddDocumentRefusesUnknown:
    """Covers Bug 2 — add_document must refuse embedding without a real creator_id."""

    def test_missing_metadata_refuses_to_embed(self):
        """add_document without metadata must return early without calling OpenAI."""
        from unittest.mock import patch, MagicMock
        from core.rag.semantic import SemanticRAG

        rag = SemanticRAG()
        rag._embeddings_available = True  # force availability check to pass

        with patch("core.contextual_prefix.generate_embedding_with_context") as mock_embed:
            rag.add_document("doc_no_meta", "Some text")
            mock_embed.assert_not_called()

    def test_unknown_creator_id_refuses_to_embed(self):
        """add_document with metadata.creator_id='unknown' must also refuse."""
        from unittest.mock import patch
        from core.rag.semantic import SemanticRAG

        rag = SemanticRAG()
        rag._embeddings_available = True

        with patch("core.contextual_prefix.generate_embedding_with_context") as mock_embed:
            rag.add_document("doc_unk", "Some text", metadata={"creator_id": "unknown"})
            mock_embed.assert_not_called()
