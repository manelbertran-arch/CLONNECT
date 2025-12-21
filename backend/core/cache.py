#!/usr/bin/env python3
"""
LRU cache para respuestas de LLM y búsquedas.
Migrado de clonnect-memory-engine y adaptado para Clonnect Creators.

Beneficios:
- 10-100x más rápido para queries repetidas
- Reduce costes de LLM significativamente
- Ideal para preguntas frecuentes (FAQ)
"""
from typing import Any, Dict, Optional
import hashlib
import json
import time
import logging

logger = logging.getLogger(__name__)


class QueryCache:
    """
    LRU cache con TTL para respuestas de LLM.

    Casos de uso:
    - Cachear respuestas a preguntas frecuentes
    - Cachear resultados de búsqueda RAG
    - Cachear clasificaciones de intención

    Configuración por defecto:
    - 500 entradas máximo (suficiente para MVP)
    - TTL de 30 minutos (respuestas pueden cambiar)
    """

    def __init__(self, max_size: int = 500, ttl_seconds: int = 1800):
        """
        Initialize query cache.

        Args:
            max_size: Máximo de entradas en cache (default: 500)
            ttl_seconds: Tiempo de vida en segundos (default: 30 min)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.access_times: Dict[str, float] = {}
        self.hits = 0
        self.misses = 0

    def _make_key(self, query: str, **params) -> str:
        """
        Create cache key from query and parameters.

        Args:
            query: Texto de búsqueda o mensaje
            **params: Parámetros adicionales (creator_id, intent, etc.)

        Returns:
            Hash MD5 como clave
        """
        key_data = {
            "query": query.strip().lower(),
            **{k: v for k, v in sorted(params.items()) if v is not None}
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, query: str, **params) -> Optional[Any]:
        """
        Get cached result.

        Args:
            query: Texto de búsqueda
            **params: Parámetros adicionales

        Returns:
            Resultado cacheado o None
        """
        key = self._make_key(query, **params)

        if key in self.cache:
            entry = self.cache[key]
            age = time.time() - entry['timestamp']

            if age > self.ttl_seconds:
                # Expirado
                del self.cache[key]
                del self.access_times[key]
                self.misses += 1
                return None

            # Cache hit
            self.access_times[key] = time.time()
            self.hits += 1
            logger.debug(f"Cache HIT (age: {age:.0f}s)")
            return entry['result']

        self.misses += 1
        return None

    def set(self, query: str, result: Any, **params):
        """
        Store result in cache.

        Args:
            query: Texto de búsqueda
            result: Resultado a cachear
            **params: Parámetros adicionales
        """
        key = self._make_key(query, **params)

        # Evict oldest if at max size
        if len(self.cache) >= self.max_size:
            self._evict_lru()

        self.cache[key] = {
            'result': result,
            'timestamp': time.time()
        }
        self.access_times[key] = time.time()

    def _evict_lru(self):
        """Evict least recently used entry"""
        if not self.access_times:
            return

        lru_key = min(self.access_times.items(), key=lambda x: x[1])[0]

        if lru_key in self.cache:
            del self.cache[lru_key]
        if lru_key in self.access_times:
            del self.access_times[lru_key]

    def clear(self):
        """Clear all cache"""
        self.cache.clear()
        self.access_times.clear()
        self.hits = 0
        self.misses = 0
        logger.info("Cache cleared")

    def cleanup_expired(self):
        """Remove all expired entries"""
        now = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if now - entry['timestamp'] > self.ttl_seconds
        ]

        for key in expired_keys:
            del self.cache[key]
            if key in self.access_times:
                del self.access_times[key]

        if expired_keys:
            logger.info(f"Cache cleanup: {len(expired_keys)} expired entries removed")

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0

        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1%}",
            "ttl_seconds": self.ttl_seconds
        }


# Instancias globales
_response_cache = None
_search_cache = None


def get_response_cache() -> QueryCache:
    """Get global response cache (for LLM responses)"""
    global _response_cache
    if _response_cache is None:
        _response_cache = QueryCache(max_size=500, ttl_seconds=1800)  # 30 min
    return _response_cache


def get_search_cache() -> QueryCache:
    """Get global search cache (for RAG results)"""
    global _search_cache
    if _search_cache is None:
        _search_cache = QueryCache(max_size=200, ttl_seconds=3600)  # 1 hour
    return _search_cache
