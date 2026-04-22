"""Unit tests for ``_build_recalling_block`` — the single point where the
four P4-replaced injections converge.

Covers:
  - Byte-identical output under flag OFF (default directive_block="") against
    the pre-P4 invariant captured inline.
  - New directive_block param slots between ``dna`` and ``state`` when present.
  - All-empty inputs still return "".
  - Order of sections is stable across every combination (regression guard).
"""

from __future__ import annotations

import pytest

from core.dm.phases.context import _build_recalling_block


# ─────────────────────────────────────────────────────────────────────────────
# Pre-P4 baseline — every test under flag OFF reproduces this exactly.
# ─────────────────────────────────────────────────────────────────────────────

PRE_P4_PARTS_ORDER = ["relational", "dna", "state", "episodic", "frustration_note", "context_notes", "memory"]
_FOOTER = "IMPORTANTE: Lee las etiquetas <memoria> y responde mencionando algo de ahí. No repitas textual."


def _reference_pre_p4(
    username: str, relational: str, memory: str, dna: str, state: str,
    frustration_note: str = "", context_notes: str = "", episodic: str = "",
) -> str:
    """Inlined copy of the pre-P4 function body. Kept here as the regression
    baseline. If ``_build_recalling_block`` diverges from this when
    ``directive_block=""`` (the default), the test fails."""
    parts = [p for p in [relational, dna, state, episodic, frustration_note, context_notes, memory] if p]
    if not parts:
        return ""
    header = f"Sobre @{username}:"
    return header + "\n" + "\n".join(parts) + "\n" + _FOOTER


# ─────────────────────────────────────────────────────────────────────────────
# Golden / byte-identical invariant — flag OFF must match the pre-P4 baseline.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("case", [
    # (label, kwargs)
    ("all-empty", {}),
    ("only-dna", {"dna": "Relación: CLIENTE (profesional)"}),
    ("dna+state+frustration (R.5 shape)", {
        "dna": "Relación: CLIENTE",
        "state": "FASE: PROPUESTA — Menciona el producto...",
        "frustration_note": "Nota: el lead parece frustrado. No vendas ahora.",
    }),
    ("familia-propuesta (R.4 shape)", {
        "dna": "Relación: FAMILIA — Familiar directo — trato cariñoso, personal, NUNCA vender",
        "state": "FASE: PROPUESTA — Menciona el producto ADAPTADO.",
    }),
    ("full recall (identity + memory + episodic)", {
        "relational": "Echo: cálido, buena relación previa",
        "dna": "Relación: AMISTAD_CERCANA",
        "state": "FASE: DESCUBRIMIENTO — Pregunta sobre situación",
        "episodic": "[Conversación previa] ...",
        "frustration_note": "Nota: el lead puede estar algo molesto.",
        "context_notes": "El lead confirma interés.",
        "memory": "Hechos:\n- Es estudiante\n- Vive en Barcelona",
    }),
    ("only-memory", {"memory": "Hechos:\n- Único dato"}),
])
def test_flag_off_output_matches_pre_p4_baseline(case) -> None:
    label, overrides = case
    kwargs = {
        "username": "iris_test",
        "relational": "",
        "memory": "",
        "dna": "",
        "state": "",
    }
    kwargs.update(overrides)

    got = _build_recalling_block(**kwargs)  # directive_block defaults to ""
    expected = _reference_pre_p4(**kwargs)
    assert got == expected, (
        f"[{label}] recalling block diverged from pre-P4 baseline when "
        f"directive_block is empty — this is a regression.\n"
        f"GOT:\n{got!r}\nEXPECTED:\n{expected!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# directive_block — placement invariant
# ─────────────────────────────────────────────────────────────────────────────

def test_directive_block_slots_between_dna_and_state() -> None:
    out = _build_recalling_block(
        username="u",
        relational="REL",
        memory="MEM",
        dna="DNA",
        state="STATE",
        frustration_note="FRUST",
        context_notes="NOTES",
        episodic="EPISODIC",
        directive_block="DIRECTIVE",
    )
    lines = out.split("\n")
    # Header + 7 sections + footer = 9 lines. Directive must be index 3
    # (after header at 0, REL at 1, DNA at 2 → directive at 3).
    assert lines[0] == "Sobre @u:"
    assert lines[1] == "REL"
    assert lines[2] == "DNA"
    assert lines[3] == "DIRECTIVE"
    assert lines[4] == "STATE"
    assert lines[5] == "EPISODIC"
    assert lines[6] == "FRUST"
    assert lines[7] == "NOTES"
    assert lines[8] == "MEM"
    assert lines[9] == _FOOTER


def test_directive_block_empty_is_filtered_out() -> None:
    """The default empty directive_block must NOT appear as a blank line."""
    out = _build_recalling_block(
        username="u",
        relational="REL",
        memory="MEM",
        dna="DNA",
        state="STATE",
    )
    assert "\n\n" not in out  # no empty sections from the filter comprehension
    assert out.count("\n") == 5  # header + 4 parts + footer → 5 separators


def test_directive_block_only_returns_valid_block() -> None:
    out = _build_recalling_block(
        username="u", relational="", memory="", dna="", state="",
        directive_block="Directiva: NO vendas.",
    )
    assert out.startswith("Sobre @u:\n")
    assert "Directiva: NO vendas." in out
    assert out.endswith(_FOOTER)


def test_all_empty_including_directive_returns_empty_string() -> None:
    assert _build_recalling_block(
        username="u", relational="", memory="", dna="", state="",
    ) == ""
    assert _build_recalling_block(
        username="u", relational="", memory="", dna="", state="",
        directive_block="",
    ) == ""
