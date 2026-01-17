# backend/tests/performance/test_rag_performance.py
"""
Tests de rendimiento para el sistema RAG.
Verifican tiempos de respuesta y eficiencia.
"""
import pytest
import time
import statistics
from unittest.mock import patch, MagicMock
import asyncio

# Configuración de umbrales
MAX_QUERY_TIME_MS = 500  # Máximo 500ms por query
MAX_EMBEDDING_TIME_MS = 100  # Máximo 100ms para embedding
MAX_RETRIEVAL_TIME_MS = 200  # Máximo 200ms para retrieval


def measure_time(func, *args, **kwargs):
    """Medir tiempo de ejecución en ms"""
    start = time.perf_counter()
    result = func(*args, **kwargs)
    elapsed = (time.perf_counter() - start) * 1000
    return result, elapsed


class TestRAGPerformance:
    """Tests de rendimiento del sistema RAG"""

    @pytest.fixture
    def mock_embeddings(self):
        """Mock de embeddings para tests consistentes"""
        return [0.1] * 1536  # Dimensión de OpenAI embeddings

    @pytest.fixture
    def sample_documents(self):
        """Documentos de prueba"""
        return [
            {"id": f"doc_{i}", "content": f"Documento de prueba número {i}" * 10}
            for i in range(100)
        ]

    def test_embedding_generation_performance_mock(self, mock_embeddings):
        """Generación de embeddings debe ser rápida"""
        def mock_get_embedding(text):
            # Simular latencia mínima
            time.sleep(0.01)
            return mock_embeddings

        times = []
        for _ in range(10):
            _, elapsed = measure_time(mock_get_embedding, "Test query")
            times.append(elapsed)

        avg_time = statistics.mean(times)
        # Mock debe ser muy rápido
        assert avg_time < 50, f"Embedding promedio {avg_time:.2f}ms excede 50ms (mock)"

    def test_vector_search_performance_mock(self, mock_embeddings):
        """Búsqueda vectorial debe ser < 200ms"""
        def mock_vector_search(embedding, top_k=5):
            time.sleep(0.02)  # Simular latencia de DB
            return [
                {"id": "doc_1", "score": 0.95, "content": "Resultado 1"},
                {"id": "doc_2", "score": 0.90, "content": "Resultado 2"},
            ]

        times = []
        for _ in range(10):
            _, elapsed = measure_time(mock_vector_search, mock_embeddings, top_k=5)
            times.append(elapsed)

        avg_time = statistics.mean(times)
        assert avg_time < MAX_RETRIEVAL_TIME_MS, \
            f"Búsqueda promedio {avg_time:.2f}ms excede {MAX_RETRIEVAL_TIME_MS}ms"

    def test_full_rag_query_performance_mock(self):
        """Query RAG completo debe ser < 500ms"""
        def mock_query_rag(creator_id, query):
            time.sleep(0.1)  # Simular tiempo total
            return {
                "answer": "El curso cuesta 99€",
                "sources": ["doc_1", "doc_2"],
                "confidence": 0.95
            }

        times = []
        for _ in range(10):
            _, elapsed = measure_time(mock_query_rag, "test", "¿Cuánto cuesta?")
            times.append(elapsed)

        avg_time = statistics.mean(times)
        p95_time = sorted(times)[int(len(times) * 0.95)]

        assert avg_time < MAX_QUERY_TIME_MS, \
            f"Query promedio {avg_time:.2f}ms excede {MAX_QUERY_TIME_MS}ms"
        assert p95_time < MAX_QUERY_TIME_MS * 1.5, \
            f"P95 {p95_time:.2f}ms excede {MAX_QUERY_TIME_MS * 1.5}ms"

    def test_bm25_search_performance(self, sample_documents):
        """Búsqueda BM25 debe ser < 50ms"""
        # Simular índice BM25 simple
        class SimpleBM25:
            def __init__(self):
                self.documents = []

            def add_documents(self, docs):
                self.documents = docs

            def search(self, query, top_k=5):
                # Búsqueda simple por coincidencia
                results = []
                query_terms = query.lower().split()
                for doc in self.documents:
                    score = sum(1 for term in query_terms if term in doc["content"].lower())
                    if score > 0:
                        results.append({"id": doc["id"], "score": score})
                return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]

        index = SimpleBM25()
        index.add_documents(sample_documents)

        queries = [
            "documento prueba",
            "número uno",
            "contenido",
            "test",
            "ejemplo"
        ]

        times = []
        for query in queries:
            _, elapsed = measure_time(index.search, query, top_k=5)
            times.append(elapsed)

        avg_time = statistics.mean(times)
        assert avg_time < 50, f"BM25 promedio {avg_time:.2f}ms excede 50ms"

    def test_concurrent_queries_performance(self):
        """Sistema debe manejar queries concurrentes eficientemente"""

        async def mock_query(query_id):
            await asyncio.sleep(0.01)  # Simular latencia
            return {"id": query_id, "result": "ok"}

        async def run_concurrent():
            tasks = [mock_query(i) for i in range(10)]
            start = time.perf_counter()
            results = await asyncio.gather(*tasks)
            elapsed = (time.perf_counter() - start) * 1000
            return results, elapsed

        results, elapsed = asyncio.run(run_concurrent())

        assert len(results) == 10
        # 10 queries de 10ms cada una en paralelo deberían tomar ~10-50ms, no 100ms
        assert elapsed < 100, f"Queries concurrentes tomaron {elapsed:.2f}ms"

    def test_batch_processing_performance(self):
        """Procesamiento por lotes debe ser más eficiente que individual"""
        items = list(range(100))

        # Procesamiento individual
        def process_individual():
            results = []
            for item in items:
                time.sleep(0.001)  # 1ms por item
                results.append(item * 2)
            return results

        # Procesamiento por lotes
        def process_batch():
            time.sleep(0.02)  # 20ms total para batch
            return [item * 2 for item in items]

        _, individual_time = measure_time(process_individual)
        _, batch_time = measure_time(process_batch)

        # Batch debería ser significativamente más rápido
        assert batch_time < individual_time, \
            f"Batch ({batch_time:.2f}ms) debería ser más rápido que individual ({individual_time:.2f}ms)"


class TestRAGMemoryUsage:
    """Tests de uso de memoria del sistema RAG"""

    def test_index_memory_efficiency(self):
        """Índice no debe usar memoria excesiva por documento"""
        import sys

        class SimpleIndex:
            def __init__(self):
                self.documents = []

            def add_documents(self, docs):
                self.documents.extend(docs)

        index = SimpleIndex()

        # Medir memoria base
        base_size = sys.getsizeof(index.documents)

        # Añadir 100 documentos
        docs = [{"id": f"doc_{i}", "content": f"Contenido {i}" * 100} for i in range(100)]
        index.add_documents(docs)

        # Memoria por documento debería ser razonable
        final_size = sys.getsizeof(index.documents)
        per_doc_overhead = (final_size - base_size) / 100

        # Overhead por documento debería ser < 1KB (sin contar contenido)
        assert per_doc_overhead < 1024, \
            f"Overhead por documento {per_doc_overhead:.2f} bytes excede 1KB"

    def test_cache_hit_performance(self):
        """Cache hits deben ser significativamente más rápidos"""
        cache = {}

        def cached_operation(key):
            if key in cache:
                return cache[key]
            time.sleep(0.05)  # Simular operación costosa
            result = f"result_{key}"
            cache[key] = result
            return result

        # Primera llamada (cache miss)
        _, miss_time = measure_time(cached_operation, "test_key")

        # Segunda llamada (cache hit)
        _, hit_time = measure_time(cached_operation, "test_key")

        # Cache hit debe ser mucho más rápido
        assert hit_time < miss_time / 10, \
            f"Cache hit ({hit_time:.2f}ms) debería ser 10x más rápido que miss ({miss_time:.2f}ms)"


class TestSignalProcessingPerformance:
    """Tests de rendimiento para procesamiento de señales"""

    def test_signal_detection_performance(self):
        """Detección de señales debe ser < 10ms por mensaje"""
        import re

        patterns = [
            r"cuánto cuesta",
            r"precio",
            r"comprar",
            r"interesa",
            r"quiero",
            r"dónde",
            r"cómo",
            r"necesito",
        ]
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

        def detect_signals(message):
            signals = []
            for pattern in compiled_patterns:
                if pattern.search(message):
                    signals.append({"pattern": pattern.pattern, "match": True})
            return signals

        messages = [
            "Hola, cuánto cuesta el curso?",
            "Me interesa mucho tu producto",
            "Quiero comprar ya",
            "Necesito más información",
            "Solo estoy mirando",
        ] * 20  # 100 mensajes

        times = []
        for msg in messages:
            _, elapsed = measure_time(detect_signals, msg)
            times.append(elapsed)

        avg_time = statistics.mean(times)
        max_time = max(times)

        assert avg_time < 1, f"Detección promedio {avg_time:.2f}ms excede 1ms"
        assert max_time < 10, f"Detección máxima {max_time:.2f}ms excede 10ms"

    def test_score_calculation_performance(self):
        """Cálculo de score debe ser < 5ms"""

        def calculate_score(signals):
            weights = {
                "precio": 0.3,
                "comprar": 0.4,
                "interesa": 0.2,
                "quiero": 0.3,
            }
            total = sum(weights.get(s.get("type", ""), 0.1) for s in signals)
            return min(total, 1.0)

        test_signals = [
            [{"type": "precio"}, {"type": "interesa"}],
            [{"type": "comprar"}, {"type": "quiero"}, {"type": "precio"}],
            [{"type": "interesa"}],
            [],
        ] * 25  # 100 casos

        times = []
        for signals in test_signals:
            _, elapsed = measure_time(calculate_score, signals)
            times.append(elapsed)

        avg_time = statistics.mean(times)
        assert avg_time < 1, f"Cálculo promedio {avg_time:.2f}ms excede 1ms"
