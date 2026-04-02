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
