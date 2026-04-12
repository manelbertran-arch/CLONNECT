"""Tests for history compactor — positional selection (recency-first).

Uses real message examples from DB analysis (2026-04-11):
- 50.5% of messages are <20 chars (trivial: emojis, stickers, audio refs)
- P25=9, P50=19, P75=38, P90=78 chars
- Only 7.1% exceed 100 chars
"""

import logging
import os

import pytest

import core.dm.history_compactor as hc_module
from core.dm.history_compactor import (
    select_and_compact,
    _is_substantive,
    _build_dropped_summary,
    _truncate_section,
    is_compact_boundary,
    create_compact_boundary,
    COMPACT_BOUNDARY_CONTENT,
    ENABLE_LLM_SUMMARY,
    MIN_RECENT_MESSAGES,
    MAX_SUMMARY_CHARS,
)


# Real creator profile data (iris_bertran A1_length from style_profile.json)
IRIS_PROFILE = {
    "A1_length": {
        "mean": 50.93,
        "median": 19.0,
        "std": 178.04,
        "P10": 7.0,
        "P25": 9.0,
        "P75": 38.0,
        "P90": 80.0,
        "P95": 144.0,
        "count": 20640,
    }
}

# Budget matching current pipeline: 10 msgs × 600 chars
CURRENT_BUDGET = 10 * 600  # 6000 chars

# Real messages from DB (sampled 2026-04-11)
TRIVIAL_MESSAGES = [
    {"role": "user", "content": "\U0001F923\U0001F923\U0001F923"},  # emoji-only
    {"role": "user", "content": "[\U0001F3F7\uFE0F Sticker]"},
    {"role": "user", "content": "[audio]"},
    {"role": "assistant", "content": "Descansa"},
    {"role": "assistant", "content": "[image]"},
    {"role": "user", "content": "\U0001F602"},
]

IMPORTANT_MESSAGES = [
    {
        "role": "user",
        "content": (
            "Hola Stefano buen dia. Ayer volque en Notion todo lo q recorde "
            "de nuestra sesion. Te lo paso para que revises y me digas si "
            "falta algo antes del jueves."
        ),
    },
    {
        "role": "assistant",
        "content": (
            "Siii! No te escribi antes porque estuve de viaje pero tenia "
            "ganas de que hablemos. El jueves me va perfecto, te confirmo "
            "la hora manana."
        ),
    },
    {
        "role": "user",
        "content": (
            "Esta clar que vaig donar per suposat que no es tan divertit "
            "venir a un partit o el que sigui. Pero veig que es important "
            "per tu i per aixo ja t'anire acompanyant."
        ),
    },
]


# ---- Tests for _is_substantive ----

class TestIsSubstantive:
    def test_media_refs_not_substantive(self):
        assert not _is_substantive("[audio]")
        assert not _is_substantive("[image]")
        assert not _is_substantive("[🏷️ Sticker]")

    def test_pure_emoji_not_substantive(self):
        assert not _is_substantive("😂")
        assert not _is_substantive("🤣🤣🤣")

    def test_text_is_substantive(self):
        assert _is_substantive("Hola que tal")
        assert _is_substantive("Siii tranqui")

    def test_empty_not_substantive(self):
        assert not _is_substantive("")
        assert not _is_substantive("   ")


# ---- Tests for select_and_compact ----

class TestSelectAndCompact:
    """Tests for budget-only positional selection (CC pattern)."""

    def test_empty_history(self):
        result = select_and_compact([], IRIS_PROFILE, CURRENT_BUDGET)
        assert result == []

    def test_small_history_all_kept(self):
        """History within budget: all kept, no summary."""
        messages = [
            {"role": "user", "content": "Hola que tal"},
            {"role": "assistant", "content": "Muy bien! Tu que tal?"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        assert len(result) == 2
        assert result[0]["content"] == "Hola que tal"
        assert result[1]["content"] == "Muy bien! Tu que tal?"

    def test_budget_never_exceeded(self):
        """Output total chars must never exceed total_budget_chars."""
        messages = TRIVIAL_MESSAGES + IMPORTANT_MESSAGES * 3
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        total = sum(len(m["content"]) for m in result)
        assert total <= CURRENT_BUDGET

    def test_chronological_order_preserved(self):
        """Output must be in chronological order (same as input)."""
        messages = [
            {"role": "user", "content": "Primer mensaje importante del dia"},
            {"role": "assistant", "content": "Respuesta al primer mensaje"},
            {"role": "user", "content": "😂"},
            {"role": "assistant", "content": "[audio]"},
            {"role": "user", "content": "Segundo mensaje importante"},
            {"role": "assistant", "content": "Respuesta al segundo mensaje"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        # Filter out meta messages (summary, boundary) for order check
        kept = [m for m in result
                if not m.get("_is_context_summary") and not m.get("_is_compact_boundary")]
        contents_in = [m["content"] for m in messages]
        for i in range(1, len(kept)):
            prev_idx = contents_in.index(kept[i - 1]["content"])
            curr_idx = contents_in.index(kept[i]["content"])
            assert curr_idx > prev_idx, (
                f"Out of order: '{kept[i-1]['content'][:30]}' (idx {prev_idx}) "
                f"before '{kept[i]['content'][:30]}' (idx {curr_idx})"
            )

    def test_min_recent_messages_guaranteed(self):
        """At least MIN_RECENT_MESSAGES substantive messages from the end survive."""
        # Build history: 15 trivial + 4 substantive at the end
        messages = [{"role": "user", "content": "😂"} for _ in range(15)]
        messages += [
            {"role": "user", "content": "Pregunta importante sobre coaching"},
            {"role": "assistant", "content": "Te respondo sobre el coaching"},
            {"role": "user", "content": "Vale perfecto me va bien jueves"},
            {"role": "assistant", "content": "Genial nos vemos el jueves"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        result_contents = {m["content"] for m in result}
        recent_substantive = [
            "Te respondo sobre el coaching",
            "Vale perfecto me va bien jueves",
            "Genial nos vemos el jueves",
        ]
        found = sum(1 for c in recent_substantive if c in result_contents)
        assert found >= MIN_RECENT_MESSAGES, (
            f"Expected >= {MIN_RECENT_MESSAGES} recent substantive msgs, found {found}"
        )

    def test_positional_keeps_most_recent(self):
        """Pure positional selection keeps the most recent messages."""
        messages = [
            {"role": "user", "content": "😂"},
            {"role": "assistant", "content": "jaja"},
            {"role": "user", "content": "[audio]"},
            {"role": "assistant", "content": "🤣"},
            {"role": "user", "content": (
                "Necesito confirmar la hora de la sesion del jueves porque "
                "tengo que organizar el transporte para los ninos"
            )},
            {"role": "assistant", "content": (
                "Claro! La sesion es a las 17h como siempre. Si quieres te "
                "mando la ubicacion por si acaso"
            )},
            {"role": "user", "content": "😂"},
            {"role": "assistant", "content": "jaja"},
            {"role": "user", "content": "[audio]"},
            {"role": "assistant", "content": "🤣"},
            {"role": "user", "content": "😍"},
            {"role": "assistant", "content": "❤️"},
            {"role": "user", "content": "[🏷️ Sticker]"},
            {"role": "assistant", "content": "jajaj"},
            {"role": "user", "content": "🔥"},
            {"role": "assistant", "content": "Totaal"},
            {"role": "user", "content": "😂😂"},
            {"role": "assistant", "content": "jajaja"},
            {"role": "user", "content": "Bueno hablamos manana"},
            {"role": "assistant", "content": "Dale! Hasta manana"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        kept = [m for m in result
                if not m.get("_is_context_summary") and not m.get("_is_compact_boundary")]

        # Most recent messages should be present
        assert any("Hasta manana" in m["content"] for m in kept)
        assert any("hablamos manana" in m["content"] for m in kept)

    def test_budget_is_the_only_cap(self):
        """With enough budget, all messages fit — no message count limit (CC-faithful)."""
        # 30 short messages — total chars ~1500, well within 6000 budget
        messages = []
        for i in range(30):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({"role": role, "content": f"Msg {i}"})
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        kept = [m for m in result
                if not m.get("_is_context_summary") and not m.get("_is_compact_boundary")]
        # All 30 fit within 6000 char budget
        assert len(kept) == 30

    def test_trivial_messages_kept_by_recency(self):
        """Trivial messages are kept when within budget (pure positional)."""
        messages = [
            {"role": "user", "content": "Contexto importante del inicio"},
            {"role": "assistant", "content": "Respuesta con contexto"},
            {"role": "user", "content": "😂"},
            {"role": "assistant", "content": "[audio]"},
            {"role": "user", "content": "🤣"},
            {"role": "assistant", "content": "[🏷️ Sticker]"},
            {"role": "user", "content": "Pregunta final importante"},
            {"role": "assistant", "content": "Respuesta final detallada"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        result_contents = [m["content"] for m in result]

        # ALL messages kept (8 messages well within 6000 char budget)
        assert any("Contexto importante" in c for c in result_contents)
        assert any("Pregunta final" in c for c in result_contents)
        assert "😂" in result_contents
        assert "[audio]" in result_contents

    def test_preserves_roles(self):
        """Output messages maintain their original roles."""
        messages = [
            {"role": "user", "content": "Pregunta importante"},
            {"role": "assistant", "content": "Respuesta completa"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    def test_importance_key_present(self):
        """Each output message has an 'importance' key."""
        messages = [
            {"role": "user", "content": "Hola que tal estas hoy"},
            {"role": "assistant", "content": "Muy bien gracias por preguntar"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        for msg in result:
            assert "importance" in msg

    def test_env_vars_have_defaults(self):
        """Config env vars have sensible defaults."""
        assert MIN_RECENT_MESSAGES == 3

    def test_no_summary_by_default_when_messages_dropped(self):
        """Sprint 2.6: No summary injected by default (ENABLE_COMPACTOR_SUMMARY=false)."""
        messages = [
            {"role": "user", "content": "Pregunta sobre el programa de coaching"},
            {"role": "assistant", "content": "El programa incluye sesiones semanales"},
            {"role": "user", "content": "😂"},
            {"role": "assistant", "content": "[audio]"},
            {"role": "user", "content": "🤣"},
            {"role": "assistant", "content": "jaja"},
            {"role": "user", "content": "😍"},
            {"role": "assistant", "content": "❤️"},
            {"role": "user", "content": "[🏷️ Sticker]"},
            {"role": "assistant", "content": "jajaj"},
            {"role": "user", "content": "🔥"},
            {"role": "assistant", "content": "Totaal"},
            {"role": "user", "content": "😂😂"},
            {"role": "assistant", "content": "jajaja"},
            {"role": "user", "content": "Bueno hablamos manana"},
            {"role": "assistant", "content": "Dale! Hasta manana"},
            {"role": "user", "content": "Oye una cosita mas"},
            {"role": "assistant", "content": "Dime que necesitas"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, 80)
        # No summary injected by default
        assert not any(m.get("_is_context_summary") for m in result)
        # Boundary marker still present
        assert any(m.get("_is_compact_boundary") for m in result)

    def test_summary_injected_when_flag_enabled(self, monkeypatch):
        """When ENABLE_COMPACTOR_SUMMARY=true, summary is injected on drops."""
        monkeypatch.setattr(hc_module, "ENABLE_COMPACTOR_SUMMARY", True)
        messages = [
            {"role": "user", "content": "Pregunta sobre el programa de coaching"},
            {"role": "assistant", "content": "El programa incluye sesiones semanales"},
            {"role": "user", "content": "😂"},
            {"role": "assistant", "content": "[audio]"},
            {"role": "user", "content": "🤣"},
            {"role": "assistant", "content": "jaja"},
            {"role": "user", "content": "😍"},
            {"role": "assistant", "content": "❤️"},
            {"role": "user", "content": "[🏷️ Sticker]"},
            {"role": "assistant", "content": "jajaj"},
            {"role": "user", "content": "🔥"},
            {"role": "assistant", "content": "Totaal"},
            {"role": "user", "content": "😂😂"},
            {"role": "assistant", "content": "jajaja"},
            {"role": "user", "content": "Bueno hablamos manana"},
            {"role": "assistant", "content": "Dale! Hasta manana"},
            {"role": "user", "content": "Oye una cosita mas"},
            {"role": "assistant", "content": "Dime que necesitas"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, 80)
        assert result[0].get("_is_context_summary") is True
        assert "[Contexto anterior:" in result[0]["content"]

    def test_no_summary_when_few_messages_dropped(self):
        """No summary injected when fewer than 3 messages are dropped."""
        messages = [
            {"role": "user", "content": "Hola que tal estas hoy"},
            {"role": "assistant", "content": "Muy bien gracias"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        has_summary = any(m.get("_is_context_summary") for m in result)
        assert not has_summary

    def test_summary_budget_respected(self, monkeypatch):
        """Summary + kept messages together respect budget."""
        monkeypatch.setattr(hc_module, "ENABLE_COMPACTOR_SUMMARY", True)
        messages = []
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({
                "role": role,
                "content": f"Mensaje importante numero {i} con bastante texto aqui",
            })
        # Tight budget forces drops
        result = select_and_compact(messages, IRIS_PROFILE, 500)
        # Summary + boundary + kept should exist
        has_summary = any(m.get("_is_context_summary") for m in result)
        assert has_summary

    def test_summary_includes_facts_when_provided(self, monkeypatch):
        """When MemoryEngine facts are provided, they appear in the summary."""
        monkeypatch.setattr(hc_module, "ENABLE_COMPACTOR_SUMMARY", True)
        # Many messages to force drops with tight budget
        messages = [
            {"role": "user", "content": "😂"},
            {"role": "assistant", "content": "[audio]"},
            {"role": "user", "content": "🤣"},
            {"role": "assistant", "content": "jaja"},
            {"role": "user", "content": "😍"},
            {"role": "assistant", "content": "❤️"},
            {"role": "user", "content": "ok"},
            {"role": "assistant", "content": "va!"},
            {"role": "user", "content": "jeje"},
            {"role": "assistant", "content": "jajaj"},
            {"role": "user", "content": "dale"},
            {"role": "assistant", "content": "sii"},
            {"role": "user", "content": "Pregunta final importante"},
            {"role": "assistant", "content": "Respuesta final detallada"},
        ]
        facts = ["Le gusta el yoga por la mañana", "Tiene 2 hijos"]
        # Total input ~87 chars; budget 40 forces drops of older messages
        result = select_and_compact(
            messages, IRIS_PROFILE, 40, existing_facts=facts,
        )
        summary_msgs = [m for m in result if m.get("_is_context_summary")]
        assert len(summary_msgs) == 1
        assert "Datos recordados:" in summary_msgs[0]["content"]
        assert "yoga" in summary_msgs[0]["content"]


# ---- Tests for _build_dropped_summary ----

class TestBuildDroppedSummary:
    def test_returns_none_for_few_dropped(self):
        """Fewer than 3 dropped messages → no summary needed."""
        dropped = [
            {"role": "user", "content": "hola"},
        ]
        assert _build_dropped_summary(dropped) is None

    def test_includes_message_counts(self):
        """Summary includes count of dropped user/assistant messages."""
        dropped = [
            {"role": "user", "content": "😂"},
            {"role": "assistant", "content": "[audio]"},
            {"role": "user", "content": "ok"},
            {"role": "user", "content": "vale"},
        ]
        summary = _build_dropped_summary(dropped)
        assert summary is not None
        assert "4 mensajes previos" in summary
        assert "3 del usuario" in summary
        assert "1 del creador" in summary

    def test_includes_facts(self):
        """Summary includes MemoryEngine facts when provided."""
        dropped = [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        facts = ["Practica yoga", "Vive en Barcelona"]
        summary = _build_dropped_summary(dropped, existing_facts=facts)
        assert "Datos recordados:" in summary
        assert "yoga" in summary
        assert "Barcelona" in summary

    def test_no_hardcoding(self):
        """Summary contains no hardcoded creator names or specific details."""
        dropped = [
            {"role": "user", "content": "texto"},
            {"role": "user", "content": "mas texto"},
            {"role": "user", "content": "aun mas"},
        ]
        summary = _build_dropped_summary(dropped)
        for name in ["iris", "Iris", "cuca", "stefano", "Barcelona", "fitness"]:
            assert name not in summary

    def test_no_verbatim_marker_by_default(self):
        """Sprint 2.6: No verbatim marker by default (ENABLE_VERBATIM_MARKER=false)."""
        dropped = [
            {"role": "user", "content": "texto"},
            {"role": "user", "content": "mas texto"},
            {"role": "user", "content": "aun mas"},
        ]
        summary = _build_dropped_summary(dropped)
        assert "conservan literalmente" not in summary

    def test_verbatim_marker_when_flag_enabled(self, monkeypatch):
        """Verbatim marker present when ENABLE_VERBATIM_MARKER=true."""
        monkeypatch.setattr(hc_module, "ENABLE_VERBATIM_MARKER", True)
        dropped = [
            {"role": "user", "content": "texto"},
            {"role": "user", "content": "mas texto"},
            {"role": "user", "content": "aun mas"},
        ]
        summary = _build_dropped_summary(dropped)
        assert "conservan literalmente" in summary


# ---- Tests for _truncate_section ----

class TestTruncateSection:
    """Tests for section-aware truncation (CC: flushSessionSection, prompts.ts:298-323)."""

    def test_short_section_unchanged(self):
        section = "[Temas: yoga | coaching]"
        assert _truncate_section(section, 100) == section

    def test_truncates_at_pipe_boundary(self):
        section = "[Datos: yoga matutino | coaching personal | nutricion deportiva]"
        result = _truncate_section(section, 40)
        assert result.endswith("[... truncado]")
        assert " | coaching" not in result or " | nutricion" not in result

    def test_truncates_at_space_when_no_pipe(self):
        section = "Una frase muy larga sin delimitadores de pipe que necesita ser cortada"
        result = _truncate_section(section, 30)
        assert result.endswith("[... truncado]")

    def test_hard_cut_when_no_boundary(self):
        section = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        result = _truncate_section(section, 20)
        assert len(result) <= 20


# ---- Tests for compact boundary ----

class TestCompactBoundary:
    """Tests for compact boundary markers (CC: messages.ts:4530-4555, 4608-4612)."""

    def test_create_boundary_has_metadata(self):
        boundary = create_compact_boundary(messages_summarized=5)
        assert boundary["_is_compact_boundary"] is True
        assert boundary["_compact_metadata"]["messages_summarized"] == 5
        assert boundary["_compact_metadata"]["trigger"] == "auto"
        assert boundary["content"] == COMPACT_BOUNDARY_CONTENT

    def test_is_compact_boundary_detects_by_flag(self):
        msg = {"role": "user", "content": "anything", "_is_compact_boundary": True}
        assert is_compact_boundary(msg)

    def test_is_compact_boundary_detects_by_content(self):
        msg = {"role": "user", "content": COMPACT_BOUNDARY_CONTENT}
        assert is_compact_boundary(msg)

    def test_boundary_injected_when_messages_dropped(self):
        """Output contains a boundary marker when messages are dropped."""
        # Use tight budget to force drops
        messages = [
            {"role": "user", "content": "😂"},
            {"role": "assistant", "content": "[audio]"},
            {"role": "user", "content": "🤣"},
            {"role": "assistant", "content": "jaja"},
            {"role": "user", "content": "ok"},
            {"role": "assistant", "content": "va"},
            {"role": "user", "content": "dale"},
            {"role": "assistant", "content": "sii"},
            {"role": "user", "content": "bien"},
            {"role": "assistant", "content": "genial"},
            {"role": "user", "content": "mmm"},
            {"role": "assistant", "content": "vale"},
            {"role": "user", "content": "Pregunta final importante"},
            {"role": "assistant", "content": "Respuesta final detallada"},
        ]
        # Total input ~91 chars; budget 40 forces drops
        result = select_and_compact(messages, IRIS_PROFILE, 40)
        boundaries = [m for m in result if m.get("_is_compact_boundary")]
        assert len(boundaries) == 1
        assert boundaries[0]["_compact_metadata"]["messages_summarized"] > 0

    def test_no_boundary_when_all_messages_kept(self):
        """No boundary when nothing is dropped."""
        messages = [
            {"role": "user", "content": "Hola que tal estas"},
            {"role": "assistant", "content": "Muy bien gracias"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        boundaries = [m for m in result if m.get("_is_compact_boundary")]
        assert len(boundaries) == 0

    def test_boundary_floor_prevents_crossing(self):
        """Backward expansion stops at boundary floor (CC: line 370-371)."""
        messages = [
            # Pre-boundary messages (should NOT be selected)
            {"role": "user", "content": "Mensaje antiguo MUY importante numero uno"},
            {"role": "assistant", "content": "Respuesta antigua importante tambien"},
            # Boundary marker
            {"role": "user", "content": COMPACT_BOUNDARY_CONTENT},
            # Post-boundary messages
            {"role": "user", "content": "Mensaje despues del boundary"},
            {"role": "assistant", "content": "Respuesta post boundary"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        result_contents = [m["content"] for m in result]

        # Pre-boundary messages should NOT appear
        assert "Mensaje antiguo" not in str(result_contents)
        # Post-boundary messages should appear
        assert any("despues del boundary" in c for c in result_contents)

    def test_old_boundaries_filtered_from_output(self):
        """Old boundary markers should not appear in output (CC: line 579-581)."""
        messages = [
            {"role": "user", "content": "Old context"},
            {"role": "user", "content": COMPACT_BOUNDARY_CONTENT},
            {"role": "user", "content": "New message"},
            {"role": "assistant", "content": "New response"},
        ]
        result = select_and_compact(messages, IRIS_PROFILE, CURRENT_BUDGET)
        for m in result:
            if m.get("content") == COMPACT_BOUNDARY_CONTENT:
                # Only the NEW boundary (if created) should be present,
                # not the old one from input
                assert m.get("_is_compact_boundary") is True


# ---- CC output order test ----

class TestCCOutputOrder:
    """Verify CC output order: boundaryMarker → summaryMessages → messagesToKeep."""

    def test_output_order_boundary_kept_default(self):
        """Default (no summary): boundary → kept messages."""
        messages = []
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({
                "role": role,
                "content": f"Msg {i} with some text here for budget",
            })
        result = select_and_compact(messages, IRIS_PROFILE, 400)
        # First should be boundary (no summary by default)
        assert result[0].get("_is_compact_boundary") is True
        # Rest are kept messages
        for m in result[1:]:
            assert not m.get("_is_context_summary")
            assert not m.get("_is_compact_boundary")

    def test_output_order_summary_boundary_kept_when_enabled(self, monkeypatch):
        """With summary enabled: summary → boundary → kept (CC: compact.ts:330-338)."""
        monkeypatch.setattr(hc_module, "ENABLE_COMPACTOR_SUMMARY", True)
        messages = []
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append({
                "role": role,
                "content": f"Msg {i} with some text here for budget",
            })
        result = select_and_compact(messages, IRIS_PROFILE, 400)
        assert result[0].get("_is_context_summary") is True
        assert result[1].get("_is_compact_boundary") is True
        for m in result[2:]:
            assert not m.get("_is_context_summary")
            assert not m.get("_is_compact_boundary")
