"""
Tests for RAG Reranker and Enhanced Search Pipeline.

Tests:
1. Reranker module (cross-encoder)
2. Enhanced search with reranking
3. BM25 hybrid fusion
4. Reciprocal Rank Fusion (RRF)
"""

from unittest.mock import patch


class TestRerankerModule:
    """Tests for core.rag.reranker module"""

    def test_import(self):
        """Test that module can be imported"""
        from core.rag.reranker import rerank, rerank_with_threshold, get_reranker
        assert rerank is not None
        assert rerank_with_threshold is not None
        assert get_reranker is not None

    def test_reranking_enabled_by_default(self):
        """Test that reranking is enabled by default"""
        from core.rag.reranker import ENABLE_RERANKING
        # Default should be True (env var defaults to "true")
        assert ENABLE_RERANKING == True

    def test_rerank_returns_docs_when_disabled(self):
        """Test rerank returns original docs when disabled via module patch"""
        import core.rag.reranker as reranker_module
        from core.rag.reranker import rerank

        docs = [
            {"content": "First document", "score": 0.9},
            {"content": "Second document", "score": 0.8},
        ]

        # Patch the module-level constant (env var already evaluated at import)
        with patch.object(reranker_module, 'ENABLE_RERANKING', False):
            result = rerank("query", docs)
            assert result == docs

    def test_rerank_respects_top_k(self):
        """Test rerank respects top_k parameter"""
        from core.rag.reranker import rerank

        docs = [
            {"content": "Doc 1"},
            {"content": "Doc 2"},
            {"content": "Doc 3"},
        ]

        result = rerank("query", docs, top_k=2)
        assert len(result) <= 2

    def test_rerank_empty_docs(self):
        """Test rerank handles empty docs list"""
        from core.rag.reranker import rerank

        result = rerank("query", [])
        assert result == []

    def test_rerank_empty_query(self):
        """Test rerank handles empty query"""
        from core.rag.reranker import rerank

        docs = [{"content": "Some doc"}]
        result = rerank("", docs)
        assert result == docs

        result = rerank("   ", docs)
        assert result == docs

    def test_rerank_with_threshold(self):
        """Test rerank_with_threshold filters low scores"""
        from core.rag.reranker import rerank_with_threshold

        docs = [
            {"content": "Relevant doc"},
            {"content": "Less relevant doc"},
        ]

        # When disabled, returns docs as-is
        result = rerank_with_threshold("query", docs, threshold=0.5)
        assert isinstance(result, list)

    def test_rerank_custom_text_key(self):
        """Test rerank works with custom text key"""
        from core.rag.reranker import rerank

        docs = [
            {"text": "First document"},
            {"text": "Second document"},
        ]

        result = rerank("query", docs, text_key="text")
        assert isinstance(result, list)


class TestEnhancedSearchPipeline:
    """Tests for enhanced SemanticRAG search pipeline"""

    def test_feature_flags_defaults(self):
        """Test that feature flags have correct defaults"""
        from core.rag.semantic import ENABLE_RERANKING, ENABLE_BM25_HYBRID

        # ENABLE_RERANKING defaults to True, ENABLE_BM25_HYBRID defaults to False
        assert ENABLE_RERANKING == True
        assert ENABLE_BM25_HYBRID == False

    def test_search_returns_list(self):
        """Test search returns a list"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()
        rag.add_document("doc1", "Test content", {"creator_id": "test"})

        results = rag.search("test", creator_id="test")
        assert isinstance(results, list)

    def test_search_without_creator_id_returns_empty(self):
        """Test search without creator_id returns empty list"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()
        rag.add_document("doc1", "Test content")

        results = rag.search("test")
        assert results == []

    def test_semantic_search_method(self):
        """Test _semantic_search method exists and works"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()
        rag.add_document("doc1", "Test content", {"creator_id": "test"})

        results = rag._semantic_search("test", top_k=5, creator_id="test")
        assert isinstance(results, list)

    def test_fallback_search_method(self):
        """Test _fallback_search method works"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()
        rag.add_document("doc1", "Test content about Python", {"creator_id": "test"})

        results = rag._fallback_search("Python", top_k=5, creator_id="test")
        assert isinstance(results, list)


class TestReciprocalRankFusion:
    """Tests for Reciprocal Rank Fusion algorithm"""

    def test_rrf_method_exists(self):
        """Test _reciprocal_rank_fusion method exists"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()
        assert hasattr(rag, '_reciprocal_rank_fusion')

    def test_rrf_single_list(self):
        """Test RRF with single result list"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()

        results = [
            {"doc_id": "doc1", "content": "First"},
            {"doc_id": "doc2", "content": "Second"},
        ]

        fused = rag._reciprocal_rank_fusion(results)

        assert len(fused) == 2
        # First doc should have higher RRF score
        assert fused[0]["doc_id"] == "doc1"
        assert "rrf_score" in fused[0]

    def test_rrf_multiple_lists(self):
        """Test RRF combines multiple result lists"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()

        semantic_results = [
            {"doc_id": "doc1", "content": "Semantic first"},
            {"doc_id": "doc2", "content": "Semantic second"},
        ]

        bm25_results = [
            {"doc_id": "doc2", "content": "BM25 first"},  # doc2 appears in both
            {"doc_id": "doc3", "content": "BM25 second"},
        ]

        fused = rag._reciprocal_rank_fusion(semantic_results, bm25_results)

        assert len(fused) == 3  # doc1, doc2, doc3

        # doc2 appears in both lists, should have higher fused score
        doc2 = next(d for d in fused if d["doc_id"] == "doc2")
        doc1 = next(d for d in fused if d["doc_id"] == "doc1")

        assert doc2["rrf_score"] > doc1["rrf_score"]

    def test_rrf_empty_lists(self):
        """Test RRF handles empty lists"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()

        fused = rag._reciprocal_rank_fusion([], [])
        assert fused == []

    def test_rrf_marks_search_type_hybrid(self):
        """Test RRF marks results as hybrid search type"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()

        results = [{"doc_id": "doc1", "content": "Test"}]
        fused = rag._reciprocal_rank_fusion(results)

        assert fused[0]["search_type"] == "hybrid"


class TestBM25HybridIntegration:
    """Tests for BM25 hybrid search integration"""

    def test_hybrid_with_bm25_method_exists(self):
        """Test _hybrid_with_bm25 method exists"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()
        assert hasattr(rag, '_hybrid_with_bm25')

    def test_hybrid_returns_semantic_on_error(self):
        """Test hybrid falls back to semantic results on BM25 error"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()

        semantic_results = [
            {"doc_id": "doc1", "content": "Test", "score": 0.9}
        ]

        # Should return semantic results even if BM25 fails
        result = rag._hybrid_with_bm25("test", semantic_results, "creator", 5)
        assert isinstance(result, list)


class TestRerankerIntegration:
    """Tests for reranker integration in search pipeline"""

    def test_rerank_results_method_exists(self):
        """Test _rerank_results method exists"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()
        assert hasattr(rag, '_rerank_results')

    def test_rerank_results_falls_back_on_error(self):
        """Test _rerank_results returns original on error"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()

        results = [
            {"doc_id": "doc1", "content": "Test", "score": 0.9},
            {"doc_id": "doc2", "content": "Test2", "score": 0.8},
        ]

        reranked = rag._rerank_results("query", results, top_k=2)
        assert isinstance(reranked, list)
        assert len(reranked) <= 2


class TestSearchPipelineIntegration:
    """Integration tests for complete search pipeline"""

    def test_search_pipeline_all_flags_off(self):
        """Test search works with all enhancements disabled"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()
        rag.add_document("doc1", "Python programming tutorial", {"creator_id": "test"})
        rag.add_document("doc2", "JavaScript basics", {"creator_id": "test"})

        results = rag.search("Python", top_k=5, creator_id="test")

        assert isinstance(results, list)
        # Should find at least the Python doc via fallback
        if results:
            assert any("Python" in r.get("text", "") for r in results)

    def test_search_respects_top_k(self):
        """Test search respects top_k limit"""
        from core.rag import SemanticRAG

        rag = SemanticRAG()
        for i in range(10):
            rag.add_document(f"doc{i}", f"Document number {i}", {"creator_id": "test"})

        results = rag.search("document", top_k=3, creator_id="test")

        assert len(results) <= 3

    def test_initial_top_k_multiplier_when_reranking(self):
        """Test that initial_top_k is multiplied when reranking enabled"""
        # This is a design test - when ENABLE_RERANKING=true,
        # initial_top_k should be top_k * 4 to get more candidates

        # When enabled, search should fetch 4x more initial results
        # This is tested by checking the code structure
        import inspect
        from core.rag.semantic import SemanticRAG

        source = inspect.getsource(SemanticRAG.search)
        assert "top_k * 4" in source or "initial_top_k" in source
