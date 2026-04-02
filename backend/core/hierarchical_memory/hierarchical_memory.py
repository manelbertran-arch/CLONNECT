"""
Hierarchical Memory Manager — 3-level memory system inspired by IMPersona (Princeton, 2025).

IMPersona shows that hierarchical memory adds +19 pts to human pass rate.
This module implements:

  Level 1 (Episodic):  Per-conversation summaries with topics.
                       Source: build_memories.py → memories_level1.jsonl
  Level 2 (Semantic):  Patterns grouped by topic across conversations.
                       Aggregated from Level 1 over time periods.
  Level 3 (Abstract):  Generalizations about the creator's behavior.
                       Distilled from Level 2 patterns into stable rules.

Retrieval strategy for prompt injection:
  - Always: top-K Level 3 (abstract generalizations — stable behavioral rules)
  - Keyword search: top-K Level 2 (patterns relevant to this message)
  - Per-lead name: top-K Level 1 (episodic memories for this lead)

Storage: JSONL files in data/persona/{creator_id}/memories_level{N}.jsonl
Compatible with existing MemoryEngine (COMEDY). Runs alongside it.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Storage directory (matches build_memories.py output)
BASE_DIR = Path(os.getenv(
    "HIERARCHICAL_MEMORY_DIR",
    str(Path(__file__).parent.parent.parent / "data" / "persona"),
))


def _load_jsonl(path: Path) -> List[Dict]:
    """Load a JSONL file into a list of dicts."""
    if not path.exists():
        return []
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


class HierarchicalMemoryManager:
    """
    3-level hierarchical memory manager for a single creator.

    Reads JSONL files produced by scripts/build_memories.py.
    Provides get_context_for_message() for prompt injection.

    Usage:
        hmm = HierarchicalMemoryManager("iris_bertran")
        context = hmm.get_context_for_message(lead_name="Tania", message="hola")
        # → string ready for system prompt injection
    """

    def __init__(self, creator_id: str):
        self.creator_id = creator_id
        persona_dir = BASE_DIR / creator_id

        self._l1: List[Dict] = _load_jsonl(persona_dir / "memories_level1.jsonl")
        self._l2: List[Dict] = _load_jsonl(persona_dir / "memories_level2.jsonl")
        self._l3: List[Dict] = _load_jsonl(persona_dir / "memories_level3.jsonl")

        logger.info(
            "[HierMem] Loaded %s: L1=%d, L2=%d, L3=%d",
            creator_id, len(self._l1), len(self._l2), len(self._l3),
        )

    def get_context_for_message(
        self,
        message: str,
        lead_name: Optional[str] = None,
        lead_id: Optional[str] = None,
        max_tokens: int = 500,
    ) -> str:
        """Build memory context string for prompt injection.

        Strategy (IMPersona):
          1. Always include top-K Level 3 (abstract generalizations, sorted by confidence)
          2. Keyword search Level 2 (patterns relevant to this message topic)
          3. If lead_name/id: recent Level 1 episodic memories for this lead

        Returns a formatted string for the system prompt.
        Respects max_tokens (approximated as chars/3.5).
        """
        max_chars = int(max_tokens * 3.5)
        sections = []
        used_chars = 0

        # --- Level 3: Abstract (always included, top 3 by confidence) ---
        l3_sorted = sorted(self._l3, key=lambda m: m.get("confidence", 0), reverse=True)
        l3_top = l3_sorted[:3]
        if l3_top:
            l3_lines = ["[Comportamiento habitual]"]
            for m in l3_top:
                l3_lines.append(f"- {m['memory']}")
            l3_text = "\n".join(l3_lines)
            if used_chars + len(l3_text) <= max_chars:
                sections.append(l3_text)
                used_chars += len(l3_text)

        # --- Level 2: Semantic (top 3 by keyword overlap with message) ---
        l2_scored = self._score_l2_relevance(message)
        l2_top = l2_scored[:3]
        if l2_top:
            l2_lines = ["[Patrones recientes]"]
            for m, _score in l2_top:
                period = m.get("period", "")
                count = m.get("count", 0)
                l2_lines.append(f"- {m['memory']}")
            l2_text = "\n".join(l2_lines)
            if used_chars + len(l2_text) <= max_chars:
                sections.append(l2_text)
                used_chars += len(l2_text)

        # --- Level 1: Episodic (per-lead, top 3 most recent) ---
        if lead_name or lead_id:
            search_term = (lead_name or "").lower()
            l1_lead = [
                m for m in self._l1
                if search_term and search_term in (m.get("lead_name", "")).lower()
            ]
            # Sort by date descending
            l1_lead.sort(key=lambda m: m.get("date", ""), reverse=True)
            l1_top = l1_lead[:3]
            if l1_top:
                l1_lines = [f"[Historial con {lead_name or lead_id}]"]
                for m in l1_top:
                    l1_lines.append(f"- {m.get('date', '')}: {m['memory']}")
                l1_text = "\n".join(l1_lines)
                if used_chars + len(l1_text) <= max_chars:
                    sections.append(l1_text)
                    used_chars += len(l1_text)

        if not sections:
            return ""

        return "\n\n".join(sections)

    # BUG-EP-10 fix: Stopwords to filter from keyword overlap (ES/CA/EN/IT)
    _L2_STOPWORDS = frozenset({
        "de", "la", "el", "en", "que", "un", "una", "los", "las", "del", "al",
        "es", "por", "con", "para", "se", "su", "no", "lo", "le", "ya", "pero",
        "como", "más", "muy", "o", "me", "mi", "te", "tu", "si", "yo",
        "the", "a", "an", "is", "in", "on", "to", "and", "or", "of", "it",
        "di", "il", "che", "per", "non", "sono", "come", "anche",
        "i", "he", "she", "we", "you", "they", "this", "that",
    })

    def _score_l2_relevance(self, message: str):
        """Score Level 2 memories by keyword overlap with the message (stopwords filtered)."""
        if not self._l2 or not message:
            return []

        msg_words = set(message.lower().split()) - self._L2_STOPWORDS
        scored = []
        for mem in self._l2:
            mem_text = mem.get("memory", "") + " " + mem.get("topic", "") + " " + mem.get("pattern", "")
            mem_words = set(mem_text.lower().split()) - self._L2_STOPWORDS
            overlap = len(msg_words & mem_words)
            scored.append((mem, overlap))

        scored.sort(key=lambda x: (-x[1], -x[0].get("count", 0)))
        return scored

    def stats(self) -> Dict[str, Any]:
        """Return memory statistics."""
        return {
            "creator_id": self.creator_id,
            "level1_count": len(self._l1),
            "level2_count": len(self._l2),
            "level3_count": len(self._l3),
            "level1_leads": len({m.get("lead_name", "") for m in self._l1}),
            "level2_topics": len({m.get("topic", "") for m in self._l2}),
            "level3_types": len({m.get("type", "") for m in self._l3}),
        }


# BUG-EP-08 fix: Cached factory — avoid re-reading JSONL from disk on every message.
from core.cache import BoundedTTLCache

_hmm_cache: BoundedTTLCache = BoundedTTLCache(max_size=50, ttl_seconds=300)


def get_hierarchical_memory(creator_id: str) -> HierarchicalMemoryManager:
    """Get or create a cached HierarchicalMemoryManager for a creator."""
    cached = _hmm_cache.get(creator_id)
    if cached is not None:
        return cached
    hmm = HierarchicalMemoryManager(creator_id)
    _hmm_cache.set(creator_id, hmm)
    return hmm
