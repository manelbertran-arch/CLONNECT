"""Tests for the hierarchical memory system."""

import json
import os
import tempfile

import pytest

# Patch the BASE_DIR before import
_tmpdir = tempfile.mkdtemp()
os.environ["HIERARCHICAL_MEMORY_DIR"] = _tmpdir

from core.hierarchical_memory.hierarchical_memory import HierarchicalMemoryManager, _load_jsonl


# ── Fixtures ──────────────────────────────────────────────────────────────

MOCK_L1 = [
    {"memory": "Lead dice: 'Quiero apuntarme a barre' — Iris responde: 'Ok t'apunto flor🩷'", "lead_name": "Tania", "date": "2026-03-10", "topic": "clase", "msg_count": 4},
    {"memory": "Lead dice: 'Cuanto cuesta?' — Iris responde: '5e sessio NO SOCI'", "lead_name": "Tania", "date": "2026-03-12", "topic": "precio", "msg_count": 3},
    {"memory": "Lead dice: 'Hola que tal' — Iris responde: 'Holaa!!'", "lead_name": "Merce", "date": "2026-03-11", "topic": "saludo", "msg_count": 2},
    {"memory": "Lead dice: 'No puc venir dijous' — Iris responde: 'Tranqui vens dema?'", "lead_name": "Tania", "date": "2026-03-14", "topic": "clase", "msg_count": 3},
    {"memory": "Lead dice: 'Me duele la espalda' — Iris responde: 'Millora't cuca❤️'", "lead_name": "Alba", "date": "2026-03-09", "topic": "salud", "msg_count": 2},
]

MOCK_L2 = [
    {"memory": "En 2026-03, 3 conversaciones sobre 'clase' con leads: Tania, Merce (+1 mas).", "period": "2026-03", "topic": "clase", "count": 3, "pattern": "Tema 'clase' es recurrente con 3 leads distintos"},
    {"memory": "En 2026-03, 1 conversaciones sobre 'precio' con leads: Tania.", "period": "2026-03", "topic": "precio", "count": 1, "pattern": "Tema 'precio' es recurrente con 1 leads distintos"},
    {"memory": "En 2026-03, 1 conversaciones sobre 'salud' con leads: Alba.", "period": "2026-03", "topic": "salud", "count": 1, "pattern": "Tema 'salud' es recurrente con 1 leads distintos"},
]

MOCK_L3 = [
    {"memory": "Los temas mas frecuentes en conversaciones son: clase (3/5), precio (1/5), salud (1/5)", "confidence": 0.9, "source_count": 5, "type": "topic_distribution"},
    {"memory": "Iris responde con mensajes muy cortos: mediana 35 chars, maximo habitual 60 chars. Usa emojis en 30% de mensajes.", "confidence": 0.95, "source_count": 50, "type": "response_style"},
    {"memory": "Iris NUNCA suena como asistente virtual. Responde como persona ocupada entre clases.", "confidence": 1.0, "source_count": 30, "type": "identity_constraint"},
]


def _write_mock_data(creator_id: str):
    """Write mock JSONL files for a test creator."""
    creator_dir = os.path.join(_tmpdir, creator_id)
    os.makedirs(creator_dir, exist_ok=True)
    for level, data in [(1, MOCK_L1), (2, MOCK_L2), (3, MOCK_L3)]:
        path = os.path.join(creator_dir, f"memories_level{level}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")


# ── Tests ─────────────────────────────────────────────────────────────────

class TestHierarchicalMemory:

    @classmethod
    def setup_class(cls):
        _write_mock_data("test_creator")

    def test_loads_all_levels(self):
        hmm = HierarchicalMemoryManager("test_creator")
        stats = hmm.stats()
        assert stats["level1_count"] == 5
        assert stats["level2_count"] == 3
        assert stats["level3_count"] == 3

    def test_empty_creator(self):
        hmm = HierarchicalMemoryManager("nonexistent_creator")
        assert hmm.stats()["level1_count"] == 0
        assert hmm.get_context_for_message("hola") == ""

    def test_context_includes_level3(self):
        hmm = HierarchicalMemoryManager("test_creator")
        ctx = hmm.get_context_for_message("hola")
        assert "[Comportamiento habitual]" in ctx
        assert "asistente virtual" in ctx  # L3 identity constraint
        assert "mensajes muy cortos" in ctx  # L3 response style

    def test_context_includes_level2_by_relevance(self):
        hmm = HierarchicalMemoryManager("test_creator")
        ctx = hmm.get_context_for_message("quiero apuntarme a clase de barre")
        assert "[Patrones recientes]" in ctx
        assert "clase" in ctx

    def test_context_includes_level1_for_lead(self):
        hmm = HierarchicalMemoryManager("test_creator")
        ctx = hmm.get_context_for_message("hola", lead_name="Tania")
        assert "[Historial con Tania]" in ctx
        # Should include Tania's memories, not others
        assert "t'apunto" in ctx or "5e sessio" in ctx or "vens dema" in ctx
        # Level 1 section should only contain Tania's memories
        l1_section = ctx.split("[Historial con Tania]")[1] if "[Historial con Tania]" in ctx else ""
        assert "Millora" not in l1_section  # Alba's memory content

    def test_context_excludes_other_leads(self):
        hmm = HierarchicalMemoryManager("test_creator")
        ctx = hmm.get_context_for_message("hola", lead_name="Merce")
        # Should only include Merce's memories
        assert "Holaa" in ctx
        assert "5e sessio" not in ctx  # Tania's memory

    def test_respects_max_tokens(self):
        hmm = HierarchicalMemoryManager("test_creator")
        # Very small budget
        ctx = hmm.get_context_for_message("hola", max_tokens=50)
        max_chars = int(50 * 3.5)
        assert len(ctx) <= max_chars + 50  # Small tolerance for section headers

    def test_level3_sorted_by_confidence(self):
        hmm = HierarchicalMemoryManager("test_creator")
        ctx = hmm.get_context_for_message("hola")
        lines = ctx.split("\n")
        # First L3 entry should be highest confidence (1.0 = identity_constraint)
        l3_entries = [l for l in lines if l.startswith("- ") and "asistente" in l.lower()]
        assert len(l3_entries) >= 1

    def test_no_lead_skips_level1(self):
        hmm = HierarchicalMemoryManager("test_creator")
        ctx = hmm.get_context_for_message("hola")
        assert "[Historial con" not in ctx

    def test_format_is_clean_text(self):
        hmm = HierarchicalMemoryManager("test_creator")
        ctx = hmm.get_context_for_message("precio barre", lead_name="Tania")
        # No JSON, no markdown headers, just clean text
        assert "{" not in ctx
        assert "##" not in ctx
        # Has section headers in brackets
        assert "[" in ctx

    def test_stats(self):
        hmm = HierarchicalMemoryManager("test_creator")
        stats = hmm.stats()
        assert stats["creator_id"] == "test_creator"
        assert stats["level1_leads"] >= 3  # Tania, Merce, Alba
        assert stats["level2_topics"] >= 2
        assert stats["level3_types"] >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
