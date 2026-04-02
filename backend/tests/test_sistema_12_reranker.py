"""
Functional tests for System #12 — Reranker (forensic audit).

Tests:
1. Empty docs → no crash (BUG-RR-01/02 fix)
2. Multilingual quality: CA query ranks CA/ES/IT docs above EN noise
3. Single doc → returns with rerank_score
4. top_k enforcement
5. Disabled flag → passthrough
6. Missing text_key → graceful (empty string)
7. Retry cooldown after init failure
8. rerank_with_threshold filters low scores
9. No doc mutation (uses .copy())
10. Feature flag consistency across modules
"""

import time
from unittest.mock import patch

import pytest


class TestBugRR01EmptyDocs:
    """BUG-RR-01/02: _rerank_local/_rerank_cohere crashed on empty docs."""

    def test_rerank_local_empty(self):
        from core.rag.reranker import _rerank_local
        result = _rerank_local("query", [])
        assert result == []

    def test_rerank_cohere_empty(self):
        from core.rag.reranker import _rerank_cohere
        result = _rerank_cohere("query", [])
        assert result == []

    def test_rerank_main_empty(self):
        from core.rag.reranker import rerank
        result = rerank("query", [])
        assert result == []


class TestMultilingualQuality:
    """Reranker must rank relevant multilingual docs above noise."""

    def test_catalan_query_ranks_catalan_first(self):
        from core.rag.reranker import rerank

        docs = [
            {"content": "The weather in London is rainy today"},
            {"content": "Les classes de barre son dilluns i dimecres a les 10h"},
            {"content": "Me encanta el chocolate con churros"},
        ]
        result = rerank("horari de classes de barre", docs)
        # Catalan barre doc should be ranked first
        assert "barre" in result[0]["content"]
        assert "rerank_score" in result[0]

    def test_spanish_query_ranks_spanish_above_noise(self):
        from core.rag.reranker import rerank

        docs = [
            {"content": "Random English text about nothing"},
            {"content": "Los precios de las clases de yoga son 15 euros la sesión"},
        ]
        result = rerank("cuánto cuestan las clases de yoga", docs)
        assert "yoga" in result[0]["content"]

    def test_italian_cross_lingual(self):
        from core.rag.reranker import rerank

        docs = [
            {"content": "Orari delle lezioni: lunedì e mercoledì alle 10"},
            {"content": "La pizza napoletana è la migliore del mondo"},
        ]
        result = rerank("horario de clases", docs)  # ES query for IT doc
        assert "lezioni" in result[0]["content"]


class TestEdgeCases:
    """Edge cases: single doc, missing key, top_k."""

    def test_single_doc_returns_with_score(self):
        from core.rag.reranker import rerank
        docs = [{"content": "Single document about yoga"}]
        result = rerank("yoga", docs)
        assert len(result) == 1
        assert "rerank_score" in result[0]

    def test_top_k_respected(self):
        from core.rag.reranker import rerank
        docs = [{"content": f"Document {i}"} for i in range(10)]
        result = rerank("document", docs, top_k=3)
        assert len(result) <= 3

    def test_missing_text_key_no_crash(self):
        from core.rag.reranker import rerank
        docs = [{"title": "no content key here"}]
        result = rerank("test", docs, text_key="content")
        assert len(result) == 1  # falls back to empty string

    def test_no_doc_mutation(self):
        from core.rag.reranker import rerank
        original = {"content": "test doc", "score": 0.9}
        rerank("query", [original])
        assert "rerank_score" not in original  # original untouched


class TestDisabledFlag:
    """ENABLE_RERANKING=false → passthrough."""

    def test_disabled_returns_original_order(self):
        import core.rag.reranker as mod
        from core.rag.reranker import rerank

        docs = [
            {"content": "First"},
            {"content": "Second"},
        ]
        with patch.object(mod, "ENABLE_RERANKING", False):
            result = rerank("query", docs)
        assert result[0]["content"] == "First"
        assert "rerank_score" not in result[0]

    def test_disabled_respects_top_k(self):
        import core.rag.reranker as mod
        from core.rag.reranker import rerank

        docs = [{"content": f"Doc {i}"} for i in range(5)]
        with patch.object(mod, "ENABLE_RERANKING", False):
            result = rerank("query", docs, top_k=2)
        assert len(result) == 2


class TestRetryCooldown:
    """30s retry cooldown after model init failure."""

    def test_cooldown_skips_retry(self):
        import core.rag.reranker as mod

        # Simulate a recent failure
        old_reranker = mod._reranker
        old_failure = mod._reranker_last_failure
        try:
            mod._reranker = None
            mod._reranker_last_failure = time.time()  # just failed

            result = mod.get_reranker()
            assert result is None  # should not retry within cooldown
        finally:
            mod._reranker = old_reranker
            mod._reranker_last_failure = old_failure


class TestThreshold:
    """rerank_with_threshold filters low-scoring docs."""

    def test_threshold_filters(self):
        from core.rag.reranker import rerank_with_threshold

        docs = [
            {"content": "Highly relevant document about yoga classes and schedules"},
            {"content": "Completely unrelated random text about weather"},
        ]
        # High threshold should filter the irrelevant doc
        result = rerank_with_threshold(
            "yoga class schedule", docs, threshold=0.5
        )
        assert all(d.get("rerank_score", 0) >= 0.5 for d in result)


class TestFlagConsistency:
    """ENABLE_RERANKING must be consistent across modules."""

    def test_flags_match(self):
        from core.rag.reranker import ENABLE_RERANKING as r1
        from core.rag.semantic import ENABLE_RERANKING as r2
        from core.feature_flags import FeatureFlags
        ff = FeatureFlags()
        assert r1 == r2 == ff.reranking
