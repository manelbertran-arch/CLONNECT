"""Unit tests for the sell_arbitration Layer 2 arbitration function.

Covers:
  - Each _check_pN in isolation (P3, P4, P5, P6) with tuple returns
  - evaluate_arbitration end-to-end for every priority + P7 default
  - Precedence chains (P3 > P4, P3 > P6, P4 > P5, P5 > P6)
  - Metric emission per priority with expected labels
  - Log output contains [SELL_ARB] with priority/directive/reason
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pytest

from core.dm.sell_arbitration.arbitration_layer import (
    _check_p3,
    _check_p4,
    _check_p5,
    _check_p6,
    evaluate_arbitration,
)
from core.dm.sell_arbitration.directives import SellDirective
from core.dm.sell_arbitration.inputs import SellArbiterInputs


def _valid_inputs(**overrides: Any) -> SellArbiterInputs:
    """Build neutral inputs that trigger no priority (falls through to P7)."""
    defaults: Dict[str, Any] = {
        "creator_id": "test_creator",
        "dna_relationship_type": "DESCONOCIDO",
        "conv_phase": "INICIO",
        "frustration_level": 0,
        "relationship_score": 0.3,
        "suppress_products": False,
        "soft_suppress": False,
        "sensitive_action_required": None,
        "has_pending_sales_commitment": False,
    }
    defaults.update(overrides)
    return SellArbiterInputs(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# _check_p3 in isolation — DNA no-sell set
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dna_type", ["FAMILIA", "INTIMA"])
def test_check_p3_fires_for_no_sell_dna(dna_type: str) -> None:
    fires, directive, reason = _check_p3(_valid_inputs(dna_relationship_type=dna_type))
    assert fires is True
    assert directive is SellDirective.NO_SELL
    assert reason == f"dna:{dna_type}"


@pytest.mark.parametrize("dna_type", ["AMISTAD_CERCANA", "AMISTAD_CASUAL", "CLIENTE", "DESCONOCIDO"])
def test_check_p3_silent_for_other_dna(dna_type: str) -> None:
    fires, directive, reason = _check_p3(_valid_inputs(dna_relationship_type=dna_type))
    assert fires is False
    assert directive is None
    assert reason == ""


# ─────────────────────────────────────────────────────────────────────────────
# _check_p4 in isolation — scorer suppress_products
# ─────────────────────────────────────────────────────────────────────────────

def test_check_p4_fires_on_suppress_products() -> None:
    fires, directive, reason = _check_p4(_valid_inputs(suppress_products=True))
    assert fires is True
    assert directive is SellDirective.REDIRECT
    assert reason == "scorer_suppress_products"


def test_check_p4_silent_when_suppress_false() -> None:
    fires, directive, reason = _check_p4(_valid_inputs(suppress_products=False))
    assert fires is False
    assert directive is None
    assert reason == ""


# ─────────────────────────────────────────────────────────────────────────────
# _check_p5 in isolation — scorer soft_suppress OR DNA=AMISTAD_CERCANA
# ─────────────────────────────────────────────────────────────────────────────

def test_check_p5_fires_on_soft_suppress() -> None:
    fires, directive, reason = _check_p5(_valid_inputs(soft_suppress=True))
    assert fires is True
    assert directive is SellDirective.SOFT_MENTION
    assert reason == "scorer_soft_suppress"


def test_check_p5_fires_on_amistad_cercana() -> None:
    fires, directive, reason = _check_p5(
        _valid_inputs(dna_relationship_type="AMISTAD_CERCANA")
    )
    assert fires is True
    assert directive is SellDirective.SOFT_MENTION
    assert reason == "dna:AMISTAD_CERCANA"


def test_check_p5_soft_suppress_wins_over_dna_soft() -> None:
    # Both conditions true — soft_suppress branch evaluated first.
    fires, directive, reason = _check_p5(
        _valid_inputs(soft_suppress=True, dna_relationship_type="AMISTAD_CERCANA")
    )
    assert fires is True
    assert directive is SellDirective.SOFT_MENTION
    assert reason == "scorer_soft_suppress"


def test_check_p5_silent_when_neutral() -> None:
    fires, directive, reason = _check_p5(_valid_inputs())
    assert fires is False
    assert directive is None
    assert reason == ""


# ─────────────────────────────────────────────────────────────────────────────
# _check_p6 in isolation — sell phases
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phase", ["PROPUESTA", "CIERRE"])
def test_check_p6_fires_on_sell_phases(phase: str) -> None:
    fires, directive, reason = _check_p6(_valid_inputs(conv_phase=phase))
    assert fires is True
    assert directive is SellDirective.SELL_ACTIVELY
    assert reason == f"phase:{phase}"


@pytest.mark.parametrize(
    "phase", ["INICIO", "CUALIFICACION", "DESCUBRIMIENTO", "OBJECIONES", "ESCALAR"]
)
def test_check_p6_silent_on_non_sell_phases(phase: str) -> None:
    fires, directive, reason = _check_p6(_valid_inputs(conv_phase=phase))
    assert fires is False
    assert directive is None
    assert reason == ""


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_arbitration end-to-end — per priority happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_arb_p3_no_sell_for_familia() -> None:
    assert evaluate_arbitration(
        _valid_inputs(dna_relationship_type="FAMILIA")
    ) is SellDirective.NO_SELL


def test_arb_p3_no_sell_for_intima() -> None:
    assert evaluate_arbitration(
        _valid_inputs(dna_relationship_type="INTIMA")
    ) is SellDirective.NO_SELL


def test_arb_p4_redirect_when_suppress() -> None:
    assert evaluate_arbitration(
        _valid_inputs(suppress_products=True, conv_phase="PROPUESTA")
    ) is SellDirective.REDIRECT


def test_arb_p5_soft_mention_on_soft_suppress() -> None:
    assert evaluate_arbitration(
        _valid_inputs(soft_suppress=True)
    ) is SellDirective.SOFT_MENTION


def test_arb_p5_soft_mention_on_amistad_cercana() -> None:
    assert evaluate_arbitration(
        _valid_inputs(dna_relationship_type="AMISTAD_CERCANA")
    ) is SellDirective.SOFT_MENTION


@pytest.mark.parametrize("phase", ["PROPUESTA", "CIERRE"])
def test_arb_p6_sell_actively_for_clean_sell_phase(phase: str) -> None:
    assert evaluate_arbitration(
        _valid_inputs(conv_phase=phase, dna_relationship_type="DESCONOCIDO")
    ) is SellDirective.SELL_ACTIVELY


def test_arb_p7_default_for_neutral_inputs() -> None:
    assert evaluate_arbitration(_valid_inputs()) is SellDirective.SOFT_MENTION


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_arbitration precedence chains
# ─────────────────────────────────────────────────────────────────────────────

def test_p3_precedes_p4_dna_familia_beats_suppress() -> None:
    """DNA=FAMILIA + suppress_products=True → P3 wins, result NO_SELL."""
    assert evaluate_arbitration(
        _valid_inputs(dna_relationship_type="FAMILIA", suppress_products=True)
    ) is SellDirective.NO_SELL


def test_p3_precedes_p6_dna_familia_beats_propuesta() -> None:
    """R.4 case: DNA=FAMILIA + phase=PROPUESTA → P3 wins, result NO_SELL."""
    assert evaluate_arbitration(
        _valid_inputs(dna_relationship_type="FAMILIA", conv_phase="PROPUESTA")
    ) is SellDirective.NO_SELL


def test_p4_precedes_p5_suppress_beats_amistad_cercana() -> None:
    """suppress_products=True + DNA=AMISTAD_CERCANA → P4 wins, result REDIRECT."""
    assert evaluate_arbitration(
        _valid_inputs(suppress_products=True, dna_relationship_type="AMISTAD_CERCANA")
    ) is SellDirective.REDIRECT


def test_p5_precedes_p6_amistad_cercana_beats_cierre() -> None:
    """DNA=AMISTAD_CERCANA + phase=CIERRE → P5 wins, result SOFT_MENTION."""
    assert evaluate_arbitration(
        _valid_inputs(dna_relationship_type="AMISTAD_CERCANA", conv_phase="CIERRE")
    ) is SellDirective.SOFT_MENTION


def test_p5_soft_suppress_precedes_p6_propuesta() -> None:
    """soft_suppress=True + phase=PROPUESTA → P5 wins, result SOFT_MENTION."""
    assert evaluate_arbitration(
        _valid_inputs(soft_suppress=True, conv_phase="PROPUESTA")
    ) is SellDirective.SOFT_MENTION


# ─────────────────────────────────────────────────────────────────────────────
# Metric emission
# ─────────────────────────────────────────────────────────────────────────────

def test_metric_emitted_for_p3(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        calls.append({"name": name, "labels": labels})

    monkeypatch.setattr(
        "core.dm.sell_arbitration.arbitration_layer.emit_metric", _capture
    )
    evaluate_arbitration(
        _valid_inputs(creator_id="iris_bertran", dna_relationship_type="FAMILIA")
    )
    assert calls == [{
        "name": "sell_arbitration_resolved",
        "labels": {
            "priority": "P3",
            "directive": "NO_SELL",
            "reason": "dna:FAMILIA",
            "creator_id": "iris_bertran",
        },
    }]


def test_metric_emitted_for_p7_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        calls.append({"name": name, "labels": labels})

    monkeypatch.setattr(
        "core.dm.sell_arbitration.arbitration_layer.emit_metric", _capture
    )
    evaluate_arbitration(_valid_inputs(creator_id="stefano_bonanno"))
    assert calls == [{
        "name": "sell_arbitration_resolved",
        "labels": {
            "priority": "P7",
            "directive": "SOFT_MENTION",
            "reason": "default",
            "creator_id": "stefano_bonanno",
        },
    }]


def test_metric_emitted_for_p6(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        calls.append({"name": name, "labels": labels})

    monkeypatch.setattr(
        "core.dm.sell_arbitration.arbitration_layer.emit_metric", _capture
    )
    evaluate_arbitration(
        _valid_inputs(creator_id="iris_bertran", conv_phase="PROPUESTA")
    )
    assert calls == [{
        "name": "sell_arbitration_resolved",
        "labels": {
            "priority": "P6",
            "directive": "SELL_ACTIVELY",
            "reason": "phase:PROPUESTA",
            "creator_id": "iris_bertran",
        },
    }]


def test_only_one_metric_emitted_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with multiple priorities active, exactly one metric is emitted (first match)."""
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        calls.append(name)

    monkeypatch.setattr(
        "core.dm.sell_arbitration.arbitration_layer.emit_metric", _capture
    )
    # FAMILIA (P3) + suppress (P4) + soft_suppress (P5) + PROPUESTA (P6) all active.
    evaluate_arbitration(_valid_inputs(
        dna_relationship_type="FAMILIA",
        suppress_products=True,
        soft_suppress=True,
        conv_phase="PROPUESTA",
    ))
    assert len(calls) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def test_logger_emits_p3_line(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="core.dm.sell_arbitration.arbitration_layer")
    evaluate_arbitration(_valid_inputs(dna_relationship_type="FAMILIA"))
    msgs = [rec.getMessage() for rec in caplog.records]
    assert any(
        "[SELL_ARB]" in m and "priority=P3" in m and "directive=NO_SELL" in m
        and "reason=dna:FAMILIA" in m
        for m in msgs
    ), msgs


def test_logger_emits_p7_default_line(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="core.dm.sell_arbitration.arbitration_layer")
    evaluate_arbitration(_valid_inputs())
    msgs = [rec.getMessage() for rec in caplog.records]
    assert any(
        "[SELL_ARB]" in m and "priority=P7" in m and "directive=SOFT_MENTION" in m
        and "reason=default" in m
        for m in msgs
    ), msgs
