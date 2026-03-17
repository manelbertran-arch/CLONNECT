"""
Knowledge Base - Simple key-value lookup for creator-specific factual info.

Used for the ~1-3% of messages that need factual data (prices, sessions, etc.).
Filled during onboarding. Simple keyword matching, no embedding needed.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Simple knowledge base with keyword-based lookup."""

    def __init__(self, creator_id: str, base_dir: str = "knowledge_bases"):
        self.creator_id = creator_id
        self.base_dir = base_dir
        self.data: dict = {}
        self._load()

    def _load(self) -> None:
        """Load knowledge base from JSON file."""
        path = Path(self.base_dir) / f"{self.creator_id}.json"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
            logger.debug(f"Loaded KB for {self.creator_id}: {len(self.data)} categories")

    def lookup(self, query: str) -> Optional[str]:
        """
        Simple keyword-based lookup.

        Returns the content of the best matching category, or None.
        """
        if not self.data:
            return None

        query_lower = query.lower()
        best_match: Optional[str] = None
        best_score = 0

        for _category, info in self.data.items():
            if not isinstance(info, dict):
                continue
            keywords = info.get("keywords", [])
            content = info.get("content", "")
            if not content:
                continue

            score = sum(1 for kw in keywords if kw in query_lower)
            if score > best_score:
                best_score = score
                best_match = content

        return best_match if best_score > 0 else None

    @staticmethod
    def create_template(creator_id: str, base_dir: str = "knowledge_bases") -> dict:
        """Create a default knowledge base template for onboarding."""
        template = {
            "precios": {
                "keywords": ["precio", "cuesta", "cuanto", "cuánto", "valor", "tarifa", "inversión"],
                "content": "",
            },
            "sesiones": {
                "keywords": ["sesión", "sesiones", "consulta", "frecuencia", "duración", "cuánto dura"],
                "content": "",
            },
            "servicios": {
                "keywords": ["servicio", "ofrecés", "hacés", "programa", "método", "qué incluye"],
                "content": "",
            },
            "horarios": {
                "keywords": ["horario", "disponible", "cuándo", "agenda", "turno", "cita"],
                "content": "",
            },
            "ubicacion": {
                "keywords": ["dónde", "ubicación", "dirección", "presencial", "online", "virtual"],
                "content": "",
            },
            "contacto": {
                "keywords": ["contacto", "teléfono", "email", "whatsapp", "llamar"],
                "content": "",
            },
        }

        path = Path(base_dir) / f"{creator_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)

        logger.info(f"Created KB template for {creator_id}")
        return template


# Cache — bounded to prevent memory leaks
from core.cache import BoundedTTLCache
_kb_cache = BoundedTTLCache(max_size=50, ttl_seconds=600)


def get_knowledge_base(creator_id: str) -> KnowledgeBase:
    """Get or create a KnowledgeBase instance (cached)."""
    cached = _kb_cache.get(creator_id)
    if cached is not None:
        return cached
    kb = KnowledgeBase(creator_id)
    _kb_cache.set(creator_id, kb)
    return kb
