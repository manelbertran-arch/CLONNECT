"""P4 integration tests — adapter + resolver + _build_recalling_block wiring.

Verifies the end-to-end composition at the smallest level that still
exercises the full arbiter chain, without dragging in the DB/HTTP/asyncio
dependencies of ``phase_memory_and_context``. The chain under test is:

    raw_dna / state_meta / cognitive_metadata / detection / rel_score
        → extract_sell_arbiter_inputs (adapter)
            → SalesIntentResolver.resolve (resolver)
                → render_directive_text + synthesize_aux_text
                    → _build_recalling_block (directive_block + aux in
                                              frustration_note slot)

The 3 Type-1 contradictions of S6 audit (R.4, R.5, C.8) plus a happy path
and R.9 aux_text trigger are covered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from core.dm.phases.context import (
    _NO_PRODUCT_DIRECTIVES,
    _build_recalling_block,
    _SELL_RESOLVER,
)
from core.dm.sell_arbitration import (
    SellDirective,
    extract_sell_arbiter_inputs,
    render_directive_text,
    synthesize_aux_text,
)


@dataclass
class _FakeFrustrationSignals:
    level: int = 0


@dataclass
class _FakeDetection:
    frustration_signals: Any = None


@dataclass
class _FakeRelScore:
    score: float = 0.3
    suppress_products: bool = False
    soft_suppress: bool = False


def _run_chain(
    *,
    creator_id: str = "iris_bertran",
    raw_dna: Any = None,
    state_meta: Any = None,
    detection: Any = None,
    rel_score: Any = None,
    cognitive_metadata: Any = None,
    commitment_text: str = "",
) -> tuple[SellDirective, str, str]:
    inputs = extract_sell_arbiter_inputs(
        creator_id=creator_id,
        raw_dna=raw_dna,
        state_meta=state_meta,
        cognitive_metadata=cognitive_metadata or {},
        detection=detection,
        rel_score=rel_score,
        commitment_text=commitment_text,
    )
    directive = _SELL_RESOLVER.resolve(inputs)
    return directive, render_directive_text(directive), synthesize_aux_text(directive, inputs)


def _flag_on_recalling(
    *,
    directive_text: str,
    aux_text: str,
    dna_context: str,
    relational: str = "",
    memory: str = "",
    episodic: str = "",
    context_notes: str = "",
    username: str = "user_under_test",
) -> str:
    """Mirror the flag-ON callsite in context.py:

      state = ""
      frustration_note = aux_text
      directive_block = directive_text
    """
    return _build_recalling_block(
        username=username,
        relational=relational,
        memory=memory,
        dna=dna_context,
        state="",                       # suppressed under flag ON
        frustration_note=aux_text,      # replaced under flag ON
        context_notes=context_notes,
        episodic=episodic,
        directive_block=directive_text,
    )


# ─────────────────────────────────────────────────────────────────────────────
# R.4 — DNA=FAMILIA + phase=PROPUESTA → single NO_SELL directive,
#        no contradictory "Menciona el producto" state_context.
# ─────────────────────────────────────────────────────────────────────────────

def test_flag_on_familia_propuesta_yields_no_sell_and_no_state_context() -> None:
    directive, directive_text, aux = _run_chain(
        raw_dna={"relationship_type": "FAMILIA"},
        state_meta={"conversation_phase": "propuesta"},  # lowercase from enum
        rel_score=_FakeRelScore(),
        detection=_FakeDetection(frustration_signals=_FakeFrustrationSignals(level=0)),
    )
    assert directive is SellDirective.NO_SELL
    assert aux == ""  # no pending commitment in this test
    recalling = _flag_on_recalling(
        directive_text=directive_text,
        aux_text=aux,
        dna_context="Relación: FAMILIA — Familiar directo — trato cariñoso, personal, NUNCA vender",
    )
    assert "Directiva: NO vendas" in recalling
    # Legacy phase verbs must not leak into the prompt under flag ON.
    assert "FASE: PROPUESTA" not in recalling
    assert "Menciona el producto" not in recalling


def test_flag_on_familia_propuesta_strips_products() -> None:
    directive, *_ = _run_chain(
        raw_dna={"relationship_type": "FAMILIA"},
        state_meta={"conversation_phase": "propuesta"},
        rel_score=_FakeRelScore(),
        detection=_FakeDetection(_FakeFrustrationSignals(level=0)),
    )
    assert directive in _NO_PRODUCT_DIRECTIVES  # is_friend=True derived in context.py


# ─────────────────────────────────────────────────────────────────────────────
# R.5 — frustration=2 + suppress_products=True → single NO_SELL (P2 beats P4).
# ─────────────────────────────────────────────────────────────────────────────

def test_flag_on_frustration2_plus_suppress_yields_no_sell_only() -> None:
    directive, directive_text, aux = _run_chain(
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "propuesta"},
        rel_score=_FakeRelScore(score=0.9, suppress_products=True),
        detection=_FakeDetection(_FakeFrustrationSignals(level=2)),
    )
    assert directive is SellDirective.NO_SELL
    recalling = _flag_on_recalling(
        directive_text=directive_text,
        aux_text=aux,
        dna_context="Relación: CLIENTE",
    )
    # Exactly one directive line, no secondary REDIRECT / SOFT_MENTION text.
    assert recalling.count("Directiva:") == 1
    assert "Directiva: NO vendas" in recalling
    # The legacy L2 frustration note ("No vendas ahora") must not appear as a
    # separate line alongside the directive — the whole note is replaced.
    assert "No vendas ahora." not in recalling


# ─────────────────────────────────────────────────────────────────────────────
# C.8 — All 4 signals disagree → veto (P2) wins cleanly.
# ─────────────────────────────────────────────────────────────────────────────

def test_flag_on_c8_multi_trigger_veto_wins() -> None:
    directive, directive_text, aux = _run_chain(
        raw_dna={"relationship_type": "FAMILIA"},
        state_meta={"conversation_phase": "cierre"},
        rel_score=_FakeRelScore(score=0.9, suppress_products=True),
        detection=_FakeDetection(_FakeFrustrationSignals(level=2)),
    )
    assert directive is SellDirective.NO_SELL
    recalling = _flag_on_recalling(
        directive_text=directive_text,
        aux_text=aux,
        dna_context="Relación: FAMILIA",
    )
    assert recalling.count("Directiva:") == 1


# ─────────────────────────────────────────────────────────────────────────────
# Happy path — clean sell phase, no blockers → SELL_ACTIVELY.
# ─────────────────────────────────────────────────────────────────────────────

def test_flag_on_happy_path_propuesta_yields_sell_actively() -> None:
    directive, directive_text, aux = _run_chain(
        raw_dna={"relationship_type": "DESCONOCIDO"},
        state_meta={"conversation_phase": "propuesta"},
        rel_score=_FakeRelScore(score=0.3),
        detection=_FakeDetection(_FakeFrustrationSignals(level=0)),
    )
    assert directive is SellDirective.SELL_ACTIVELY
    assert aux == ""
    recalling = _flag_on_recalling(
        directive_text=directive_text,
        aux_text=aux,
        dna_context="Relación: DESCONOCIDO",
    )
    assert "Directiva: este es momento de presentar el producto" in recalling
    assert directive not in _NO_PRODUCT_DIRECTIVES  # products stay visible


# ─────────────────────────────────────────────────────────────────────────────
# R.9 — NO_SELL + has_pending_sales_commitment → aux_text appears in the
#       frustration_note slot (not inside the directive).
# ─────────────────────────────────────────────────────────────────────────────

def test_flag_on_r9_aux_text_lands_in_frustration_slot() -> None:
    directive, directive_text, aux = _run_chain(
        raw_dna={"relationship_type": "FAMILIA"},
        state_meta={"conversation_phase": "propuesta"},
        rel_score=_FakeRelScore(),
        detection=_FakeDetection(_FakeFrustrationSignals(level=0)),
        commitment_text="- [hace 2 días] Prometiste enviarle el link del curso.",
    )
    assert directive is SellDirective.NO_SELL
    assert "compromiso pendiente" in aux
    recalling = _flag_on_recalling(
        directive_text=directive_text,
        aux_text=aux,
        dna_context="Relación: FAMILIA",
    )
    # Both strings must be present AND in the correct order:
    # directive (between dna and state) precedes aux_text (in frustration slot).
    assert directive_text in recalling
    assert aux in recalling
    assert recalling.index(directive_text) < recalling.index(aux)


def test_flag_on_soft_mention_does_not_carry_aux_even_with_commitment() -> None:
    directive, directive_text, aux = _run_chain(
        raw_dna={"relationship_type": "AMISTAD_CERCANA"},
        state_meta={"conversation_phase": "propuesta"},
        rel_score=_FakeRelScore(),
        detection=_FakeDetection(_FakeFrustrationSignals(level=0)),
        commitment_text="- [hace 2 días] Prometiste enviar el link.",
    )
    assert directive is SellDirective.SOFT_MENTION
    # aux_text is R.9-specific (NO_SELL only); SOFT_MENTION keeps it empty.
    assert aux == ""


# ─────────────────────────────────────────────────────────────────────────────
# is_friend derivation — directive → product visibility mapping.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("directive,strips_products", [
    (SellDirective.NO_SELL, True),
    (SellDirective.REDIRECT, True),
    (SellDirective.SOFT_MENTION, False),
    (SellDirective.SELL_ACTIVELY, False),
])
def test_no_product_directives_set_matches_design(
    directive: SellDirective, strips_products: bool,
) -> None:
    """Mirrors the is_friend branching in context.py:
        is_friend = _arb_directive in _NO_PRODUCT_DIRECTIVES
    """
    assert (directive in _NO_PRODUCT_DIRECTIVES) is strips_products


# ─────────────────────────────────────────────────────────────────────────────
# Singleton resolver is statefree across test invocations.
# ─────────────────────────────────────────────────────────────────────────────

def test_shared_resolver_singleton_handles_back_to_back_cases() -> None:
    r1, _, _ = _run_chain(
        raw_dna={"relationship_type": "FAMILIA"},
        state_meta={"conversation_phase": "inicio"},
        rel_score=_FakeRelScore(),
    )
    r2, _, _ = _run_chain(
        raw_dna={"relationship_type": "DESCONOCIDO"},
        state_meta={"conversation_phase": "propuesta"},
        rel_score=_FakeRelScore(),
    )
    r3, _, _ = _run_chain(
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "propuesta"},
        rel_score=_FakeRelScore(),
        detection=_FakeDetection(_FakeFrustrationSignals(level=3)),
    )
    assert (r1, r2, r3) == (
        SellDirective.NO_SELL,
        SellDirective.SELL_ACTIVELY,
        SellDirective.NO_SELL,
    )
