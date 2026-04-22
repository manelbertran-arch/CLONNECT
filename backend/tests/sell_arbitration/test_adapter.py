"""Unit tests for the P4 adapter (extract_sell_arbiter_inputs + render + synth).

Covers:
  - Happy path: all upstream sources present → valid SellArbiterInputs built.
  - Fallbacks: every optional source (raw_dna, state_meta, detection,
    rel_score, cognitive_metadata, commitment_text) may be None → adapter
    applies a documented default AND emits ``sell_adapter_fallback``.
  - Normalization: lowercase phase values (ConversationPhase enum stores
    lowercase) are uppercased before construction.
  - Sensitive action: persisted values are filtered to the 2 whitelisted
    actions; missing keys and ``"none"`` map to None silently; unknown
    values map to None + warning + fallback metric.
  - Commitment flag: ``bool(commitment_text.strip())``.
  - render_directive_text: one unique string per SellDirective, all 4 covered.
  - synthesize_aux_text: fires iff NO_SELL + has_pending_sales_commitment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pytest

from core.dm.sell_arbitration.adapter import (
    _DIRECTIVE_TEXTS,
    extract_sell_arbiter_inputs,
    render_directive_text,
    synthesize_aux_text,
)
from core.dm.sell_arbitration.directives import SellDirective
from core.dm.sell_arbitration.inputs import SellArbiterInputs


# ─────────────────────────────────────────────────────────────────────────────
# Minimal stand-ins for DetectionResult / RelationshipScore. We avoid the real
# classes to keep tests independent of their fields and to exercise the
# adapter's getattr-based extraction.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _FakeFrustrationSignals:
    level: int = 0


@dataclass
class _FakeDetection:
    frustration_signals: Any = None


@dataclass
class _FakeRelScore:
    score: float = 0.0
    suppress_products: bool = False
    soft_suppress: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Metric capture helper
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def captured_fallbacks(monkeypatch: pytest.MonkeyPatch) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        if name == "sell_adapter_fallback":
            calls.append(labels)

    monkeypatch.setattr("core.dm.sell_arbitration.adapter.emit_metric", _capture)
    return calls


# ─────────────────────────────────────────────────────────────────────────────
# extract_sell_arbiter_inputs — happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_happy_path_all_sources_present(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris_bertran",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "propuesta"},  # lowercase from enum.value
        cognitive_metadata={"sensitive_action_required": "no_pressure_sale"},
        detection=_FakeDetection(frustration_signals=_FakeFrustrationSignals(level=1)),
        rel_score=_FakeRelScore(score=0.55, suppress_products=False, soft_suppress=False),
        commitment_text="- [hace 2 días] Prometiste enviarle el link.",
    )
    assert isinstance(inputs, SellArbiterInputs)
    assert inputs.creator_id == "iris_bertran"
    assert inputs.dna_relationship_type == "CLIENTE"
    assert inputs.conv_phase == "PROPUESTA"  # uppercased by the adapter
    assert inputs.frustration_level == 1
    assert inputs.relationship_score == pytest.approx(0.55)
    assert inputs.suppress_products is False
    assert inputs.soft_suppress is False
    assert inputs.sensitive_action_required == "no_pressure_sale"
    assert inputs.has_pending_sales_commitment is True
    assert captured_fallbacks == []  # no fallback emitted on the happy path


# ─────────────────────────────────────────────────────────────────────────────
# Fallbacks — one per optional source
# ─────────────────────────────────────────────────────────────────────────────

def test_fallback_raw_dna_none(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna=None,
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.dna_relationship_type == "DESCONOCIDO"
    assert {"creator_id": "iris", "field": "dna"} in captured_fallbacks


def test_fallback_raw_dna_missing_key(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.dna_relationship_type == "DESCONOCIDO"
    assert {"creator_id": "iris", "field": "dna"} in captured_fallbacks


def test_fallback_raw_dna_unknown_value(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "NOT_A_REAL_TYPE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    # Adapter swallows unknown upstream value and falls back, rather than
    # letting the resolver raise — pipeline survives.
    assert inputs.dna_relationship_type == "DESCONOCIDO"
    assert {"creator_id": "iris", "field": "dna"} in captured_fallbacks


def test_fallback_state_meta_empty(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.conv_phase == "INICIO"
    assert {"creator_id": "iris", "field": "phase"} in captured_fallbacks


def test_fallback_state_meta_none(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta=None,
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.conv_phase == "INICIO"
    assert {"creator_id": "iris", "field": "phase"} in captured_fallbacks


def test_fallback_detection_none(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.frustration_level == 0
    assert {"creator_id": "iris", "field": "frustration"} in captured_fallbacks


def test_fallback_detection_missing_signals(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=_FakeDetection(frustration_signals=None),
        rel_score=None,
        commitment_text="",
    )
    assert inputs.frustration_level == 0
    assert {"creator_id": "iris", "field": "frustration"} in captured_fallbacks


def test_frustration_clamped_to_range(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=_FakeDetection(frustration_signals=_FakeFrustrationSignals(level=99)),
        rel_score=None,
        commitment_text="",
    )
    assert inputs.frustration_level == 3  # clamped from 99


def test_fallback_rel_score_none(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.relationship_score == 0.0
    assert inputs.suppress_products is False
    assert inputs.soft_suppress is False
    assert {"creator_id": "iris", "field": "rel_score"} in captured_fallbacks


def test_rel_score_clamped_to_range() -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=None,
        rel_score=_FakeRelScore(score=1.5),
        commitment_text="",
    )
    assert inputs.relationship_score == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# sensitive_action_required handling
# ─────────────────────────────────────────────────────────────────────────────

def test_sensitive_action_missing_key_yields_none(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.sensitive_action_required is None
    # Absence is common — no fallback metric for this field.
    assert all(c.get("field") != "sensitive" for c in captured_fallbacks)


def test_sensitive_action_none_string_treated_as_none(captured_fallbacks) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={"sensitive_action_required": "none"},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.sensitive_action_required is None
    assert all(c.get("field") != "sensitive" for c in captured_fallbacks)


@pytest.mark.parametrize("action", ["no_pressure_sale", "empathetic_response"])
def test_sensitive_action_whitelisted_passes_through(action: str) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={"sensitive_action_required": action},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.sensitive_action_required == action


def test_sensitive_action_unknown_value_maps_to_none_and_emits(
    captured_fallbacks,
) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={"sensitive_action_required": "escalate_human"},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.sensitive_action_required is None
    assert {"creator_id": "iris", "field": "sensitive"} in captured_fallbacks


# ─────────────────────────────────────────────────────────────────────────────
# has_pending_sales_commitment — bool(commitment_text.strip())
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("", False),
    (None, False),
    ("   ", False),
    ("\n\n", False),
    ("- [hace 2 días] Prometiste enviar el link", True),
    ("algo", True),
])
def test_has_pending_sales_commitment_from_commitment_text(
    text: Any, expected: bool
) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text=text,
    )
    assert inputs.has_pending_sales_commitment is expected


# ─────────────────────────────────────────────────────────────────────────────
# Phase normalization — ConversationPhase.value is lowercase
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("lowercase_phase,expected_upper", [
    ("inicio", "INICIO"),
    ("cualificacion", "CUALIFICACION"),
    ("descubrimiento", "DESCUBRIMIENTO"),
    ("propuesta", "PROPUESTA"),
    ("objeciones", "OBJECIONES"),
    ("cierre", "CIERRE"),
    ("escalar", "ESCALAR"),
])
def test_phase_is_uppercased_from_conversation_state_enum(
    lowercase_phase: str, expected_upper: str,
) -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "CLIENTE"},
        state_meta={"conversation_phase": lowercase_phase},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.conv_phase == expected_upper


def test_dna_is_uppercased_defensively() -> None:
    inputs = extract_sell_arbiter_inputs(
        creator_id="iris",
        raw_dna={"relationship_type": "familia"},  # upstream drift
        state_meta={"conversation_phase": "INICIO"},
        cognitive_metadata={},
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    assert inputs.dna_relationship_type == "FAMILIA"


# ─────────────────────────────────────────────────────────────────────────────
# render_directive_text — one unique string per directive
# ─────────────────────────────────────────────────────────────────────────────

def test_render_directive_text_all_four_unique() -> None:
    texts = {d: render_directive_text(d) for d in SellDirective}
    assert len(set(texts.values())) == 4
    for text in texts.values():
        assert text.startswith("Directiva:")
        assert 30 <= len(text) <= 250  # concise


def test_render_directive_text_no_sell_contains_no_sell_cue() -> None:
    text = render_directive_text(SellDirective.NO_SELL)
    assert "NO vendas" in text


def test_render_directive_text_sell_actively_mentions_product() -> None:
    text = render_directive_text(SellDirective.SELL_ACTIVELY)
    assert "producto" in text.lower()


def test_render_directive_text_soft_mention_says_without_pressure() -> None:
    text = render_directive_text(SellDirective.SOFT_MENTION)
    assert "sin presionar" in text.lower() or "sin presión" in text.lower()


def test_render_directive_text_redirect_mentions_no_products() -> None:
    text = render_directive_text(SellDirective.REDIRECT)
    assert "sin mencionar productos" in text.lower()


def test_render_directive_text_covers_every_directive_value() -> None:
    # Catches regression where a new SellDirective is added without a mapping.
    for d in SellDirective:
        assert d in _DIRECTIVE_TEXTS


# ─────────────────────────────────────────────────────────────────────────────
# synthesize_aux_text — R.9 trigger
# ─────────────────────────────────────────────────────────────────────────────

def _inputs_with(has_pending: bool) -> SellArbiterInputs:
    return SellArbiterInputs(
        creator_id="iris",
        dna_relationship_type="FAMILIA",
        conv_phase="PROPUESTA",
        frustration_level=0,
        relationship_score=0.5,
        suppress_products=False,
        soft_suppress=False,
        sensitive_action_required=None,
        has_pending_sales_commitment=has_pending,
    )


def test_synthesize_aux_text_r9_fires_on_no_sell_plus_pending() -> None:
    text = synthesize_aux_text(SellDirective.NO_SELL, _inputs_with(True))
    assert "compromiso pendiente" in text
    assert "sin añadir presión" in text


def test_synthesize_aux_text_no_commitment_returns_empty() -> None:
    assert synthesize_aux_text(SellDirective.NO_SELL, _inputs_with(False)) == ""


@pytest.mark.parametrize("directive", [
    SellDirective.SELL_ACTIVELY,
    SellDirective.SOFT_MENTION,
    SellDirective.REDIRECT,
])
def test_synthesize_aux_text_skips_non_no_sell_directives(
    directive: SellDirective,
) -> None:
    # Pending commitment + non-NO_SELL directive → no aux_text (the directive
    # itself is compatible with mentioning the commitment naturally).
    assert synthesize_aux_text(directive, _inputs_with(True)) == ""


# ─────────────────────────────────────────────────────────────────────────────
# fallback metric labels — regression guard on label names
# ─────────────────────────────────────────────────────────────────────────────

def test_fallback_metric_uses_creator_id_and_field_labels(captured_fallbacks) -> None:
    extract_sell_arbiter_inputs(
        creator_id="stefano_bonanno",
        raw_dna=None,
        state_meta=None,
        cognitive_metadata=None,
        detection=None,
        rel_score=None,
        commitment_text="",
    )
    # 4 fallbacks expected: dna, phase, frustration, rel_score.
    fields = {c["field"] for c in captured_fallbacks}
    assert fields == {"dna", "phase", "frustration", "rel_score"}
    for c in captured_fallbacks:
        assert c["creator_id"] == "stefano_bonanno"
        assert set(c.keys()) == {"creator_id", "field"}
