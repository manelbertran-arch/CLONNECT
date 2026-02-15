"""Simple in-memory cache with TTL for API responses.

Provides fast responses for frequently accessed endpoints like
/conversations and /leads by caching results for a short TTL.

Usage:
    from api.cache import api_cache

    # Get cached value
    cached = api_cache.get("conversations:creator:50")
    if cached:
        return cached

    # Set cached value (10 second TTL)
    api_cache.set("conversations:creator:50", result, ttl_seconds=10)

    # Invalidate on updates
    api_cache.invalidate("conversations:creator")
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class SimpleCache:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self):
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        with self._lock:
            if key in self._cache:
                value, expires_at = self._cache[key]
                if datetime.now(timezone.utc) < expires_at:
                    self._hits += 1
                    return value
                else:
                    # Expired - clean up
                    del self._cache[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any, ttl_seconds: int = 10):
        """Set value in cache with TTL."""
        with self._lock:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            self._cache[key] = (value, expires_at)

    def invalidate(self, key_prefix: str):
        """Invalidate all keys starting with prefix."""
        with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(key_prefix)]
            for key in keys_to_delete:
                del self._cache[key]
            if keys_to_delete:
                logger.debug(f"[CACHE] Invalidated {len(keys_to_delete)} keys with prefix '{key_prefix}'")

    def clear(self):
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()
            logger.info("[CACHE] Cleared all cached values")

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.1f}%",
                "cached_keys": len(self._cache),
            }


# Global cache instance
api_cache = SimpleCache()
