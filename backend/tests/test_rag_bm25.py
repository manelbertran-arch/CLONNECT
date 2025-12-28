"""
Tests for RAG modules: BM25Retriever and HybridRAG
"""

import pytest


class TestBM25Retriever:
    """Tests for BM25Retriever"""

    def test_import(self):
        """Test that module can be imported"""
        from core.rag import BM25Retriever, get_bm25_retriever
        assert BM25Retriever is not None
        assert get_bm25_retriever is not None

    def test_tokenize(self):
        """Test tokenization"""
        from core.rag.bm25 import BM25Retriever

        bm25 = BM25Retriever()
        tokens = bm25._tokenize("El curso de automatización es muy bueno")

        assert "curso" in tokens
        assert "automatización" in tokens
        assert "bueno" in tokens
        # Stopwords removed
        assert "el" not in tokens
        assert "de" not in tokens
        assert "es" not in tokens
        assert "muy" not in tokens

    def test_add_document(self):
        """Test adding documents"""
        from core.rag.bm25 import BM25Retriever

        bm25 = BM25Retriever()
        bm25.add_document("doc1", "Este es un documento de prueba")
        bm25.add_document("doc2", "Este es otro documento diferente")

        assert bm25.corpus_size == 2
        assert "doc1" in bm25.documents
        assert "doc2" in bm25.documents

    def test_search(self):
        """Test search functionality"""
        from core.rag.bm25 import BM25Retriever

        bm25 = BM25Retriever()
        bm25.add_document("doc1", "Curso de automatización con Python")
        bm25.add_document("doc2", "Mentoría personalizada de marketing")
        bm25.add_document("doc3", "Ebook gratuito sobre productividad")

        results = bm25.search("automatización Python", top_k=2)

        assert len(results) > 0
        assert results[0].doc_id == "doc1"  # Most relevant
        assert results[0].score > 0

    def test_search_empty_corpus(self):
        """Test search on empty corpus"""
        from core.rag.bm25 import BM25Retriever

        bm25 = BM25Retriever()
        results = bm25.search("algo")

        assert len(results) == 0

    def test_search_no_matches(self):
        """Test search with no matching terms"""
        from core.rag.bm25 import BM25Retriever

        bm25 = BM25Retriever()
        bm25.add_document("doc1", "perro gato ratón")

        results = bm25.search("elefante jirafa")

        assert len(results) == 0

    def test_remove_document(self):
        """Test document removal"""
        from core.rag.bm25 import BM25Retriever

        bm25 = BM25Retriever()
        bm25.add_document("doc1", "Documento uno")
        bm25.add_document("doc2", "Documento dos")

        assert bm25.corpus_size == 2

        removed = bm25.remove_document("doc1")
        assert removed
        assert bm25.corpus_size == 1
        assert "doc1" not in bm25.documents

        # Remove non-existent
        removed = bm25.remove_document("doc99")
        assert not removed

    def test_metadata_filter(self):
        """Test search with metadata filter"""
        from core.rag.bm25 import BM25Retriever

        bm25 = BM25Retriever()
        bm25.add_document("doc1", "Curso premium", {"creator_id": "manel"})
        bm25.add_document("doc2", "Curso básico", {"creator_id": "otro"})

        results = bm25.search("curso", filter_metadata={"creator_id": "manel"})

        assert len(results) == 1
        assert results[0].doc_id == "doc1"

    def test_get_stats(self):
        """Test stats retrieval"""
        from core.rag.bm25 import BM25Retriever

        bm25 = BM25Retriever()
        bm25.add_document("doc1", "Primero")
        bm25.add_document("doc2", "Segundo")

        stats = bm25.get_stats()

        assert stats["corpus_size"] == 2
        assert stats["vocabulary_size"] > 0
        assert stats["k1"] == 1.5
        assert stats["b"] == 0.75


class TestHybridRAG:
    """Tests for HybridRAG"""

    def test_import(self):
        """Test that module can be imported"""
        from core.rag import HybridRAG, get_hybrid_rag
        assert HybridRAG is not None
        assert get_hybrid_rag is not None

    def test_add_document(self):
        """Test adding documents to hybrid index"""
        from core.rag import HybridRAG

        hybrid = HybridRAG()
        hybrid.add_document("doc1", "Curso de automatización", {"type": "course"})

        assert hybrid.count() == 1
        doc = hybrid.get_document("doc1")
        assert doc is not None
        assert doc.text == "Curso de automatización"

    def test_search_semantic_only(self):
        """Test search with semantic only (hybrid disabled)"""
        from core.rag import HybridRAG

        hybrid = HybridRAG()
        hybrid.add_document("doc1", "Automatización de marketing")

        results = hybrid.search("marketing automation", use_hybrid=False)

        # Should work even with mock embedder
        assert isinstance(results, list)

    def test_delete_document(self):
        """Test document deletion from hybrid index"""
        from core.rag import HybridRAG

        hybrid = HybridRAG()
        hybrid.add_document("doc1", "Documento uno")
        hybrid.add_document("doc2", "Documento dos")

        assert hybrid.count() == 2

        hybrid.delete_document("doc1")

        assert hybrid.count() == 1
        assert hybrid.get_document("doc1") is None
        assert hybrid.get_document("doc2") is not None


class TestRAGIntegration:
    """Integration tests for RAG system"""

    def test_simple_rag_singleton(self):
        """Test SimpleRAG singleton"""
        from core.rag import get_simple_rag

        rag1 = get_simple_rag()
        rag2 = get_simple_rag()

        assert rag1 is rag2

    def test_bm25_singleton(self):
        """Test BM25 singleton per creator"""
        from core.rag import get_bm25_retriever

        bm25_a = get_bm25_retriever("creator_a")
        bm25_b = get_bm25_retriever("creator_b")
        bm25_a2 = get_bm25_retriever("creator_a")

        assert bm25_a is bm25_a2  # Same creator = same instance
        assert bm25_a is not bm25_b  # Different creators = different instances
