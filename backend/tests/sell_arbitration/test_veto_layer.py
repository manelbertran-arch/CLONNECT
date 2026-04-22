"""Unit tests for the sell_arbitration Layer 1 veto function.

Covers the 9 cases from the Fase 3 spec:
  1. P1 fires with "no_pressure_sale"            -> NO_SELL
  2. P1 fires with "empathetic_response"         -> NO_SELL
  3. P1 silent with action_required=None         -> None (falls through)
  4. P2 fires with frustration_level=2           -> NO_SELL
  5. P2 fires with frustration_level=3           -> NO_SELL
  6. P2 silent with frustration_level in {0, 1}  -> None
  7. P1 beats P2 when both would fire            -> NO_SELL with P1 reason
  8. emit_metric called with correct labels      -> verified via monkeypatch
  9. Logger emits reason on trigger              -> verified via caplog
Plus an extra input-contract check:
 10. creator_id empty                            -> ValueError at __post_init__
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pytest

from core.dm.sell_arbitration.directives import SellDirective
from core.dm.sell_arbitration.inputs import SellArbiterInputs
from core.dm.sell_arbitration.veto_layer import evaluate_vetos


def _valid_inputs(**overrides: Any) -> SellArbiterInputs:
    """Build a SellArbiterInputs that triggers no veto and no arbitration.

    Fields can be selectively overridden for each test scenario.
    """

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
# P1 — sensitive soft action
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("action", ["no_pressure_sale", "empathetic_response"])
def test_p1_fires_for_each_soft_sensitive_action(action: str) -> None:
    inputs = _valid_inputs(sensitive_action_required=action)
    assert evaluate_vetos(inputs) is SellDirective.NO_SELL


def test_p1_silent_when_action_required_is_none() -> None:
    inputs = _valid_inputs(sensitive_action_required=None)
    assert evaluate_vetos(inputs) is None


# ─────────────────────────────────────────────────────────────────────────────
# P2 — frustration hard gate
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("level", [2, 3])
def test_p2_fires_for_frustration_level_ge_2(level: int) -> None:
    inputs = _valid_inputs(frustration_level=level)
    assert evaluate_vetos(inputs) is SellDirective.NO_SELL


@pytest.mark.parametrize("level", [0, 1])
def test_p2_silent_for_frustration_level_lt_2(level: int) -> None:
    inputs = _valid_inputs(frustration_level=level)
    assert evaluate_vetos(inputs) is None


# ─────────────────────────────────────────────────────────────────────────────
# Precedence — P1 beats P2 when both would fire
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_precedes_p2_when_both_would_fire(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        calls.append({"name": name, "value": value, "labels": labels})

    monkeypatch.setattr("core.dm.sell_arbitration.veto_layer.emit_metric", _capture)

    inputs = _valid_inputs(
        sensitive_action_required="empathetic_response",
        frustration_level=3,
    )

    result = evaluate_vetos(inputs)
    assert result is SellDirective.NO_SELL
    # Exactly one metric emitted, from P1 (short-circuit before P2 check).
    assert len(calls) == 1
    assert calls[0]["name"] == "sell_veto_triggered"
    assert calls[0]["labels"]["priority"] == "P1"
    assert calls[0]["labels"]["reason"] == "sensitive:empathetic_response"


# ─────────────────────────────────────────────────────────────────────────────
# Metric labels shape
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_metric_labels_for_p1(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        calls.append({"name": name, "labels": labels})

    monkeypatch.setattr("core.dm.sell_arbitration.veto_layer.emit_metric", _capture)

    inputs = _valid_inputs(
        creator_id="iris_bertran",
        sensitive_action_required="no_pressure_sale",
    )
    assert evaluate_vetos(inputs) is SellDirective.NO_SELL
    assert calls == [{
        "name": "sell_veto_triggered",
        "labels": {
            "priority": "P1",
            "reason": "sensitive:no_pressure_sale",
            "creator_id": "iris_bertran",
        },
    }]


def test_emit_metric_labels_for_p2(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        calls.append({"name": name, "labels": labels})

    monkeypatch.setattr("core.dm.sell_arbitration.veto_layer.emit_metric", _capture)

    inputs = _valid_inputs(creator_id="stefano_bonanno", frustration_level=2)
    assert evaluate_vetos(inputs) is SellDirective.NO_SELL
    assert calls == [{
        "name": "sell_veto_triggered",
        "labels": {
            "priority": "P2",
            "reason": "frustration_level:2",
            "creator_id": "stefano_bonanno",
        },
    }]


def test_no_metric_emitted_when_no_veto_fires(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        calls.append(name)

    monkeypatch.setattr("core.dm.sell_arbitration.veto_layer.emit_metric", _capture)

    assert evaluate_vetos(_valid_inputs()) is None
    assert calls == []


# ─────────────────────────────────────────────────────────────────────────────
# Logging — reason content
# ─────────────────────────────────────────────────────────────────────────────

def test_logger_contains_reason_on_p1(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="core.dm.sell_arbitration.veto_layer")
    evaluate_vetos(_valid_inputs(sensitive_action_required="empathetic_response"))
    messages = [rec.getMessage() for rec in caplog.records]
    assert any(
        "[SELL_VETO]" in m and "P1" in m and "sensitive:empathetic_response" in m
        for m in messages
    ), messages


def test_logger_contains_reason_on_p2(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="core.dm.sell_arbitration.veto_layer")
    evaluate_vetos(_valid_inputs(frustration_level=3))
    messages = [rec.getMessage() for rec in caplog.records]
    assert any(
        "[SELL_VETO]" in m and "P2" in m and "frustration_level:3" in m
        for m in messages
    ), messages


# ─────────────────────────────────────────────────────────────────────────────
# Input contract — creator_id required
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cid", ["", "   "])
def test_empty_creator_id_raises_value_error(cid: str) -> None:
    with pytest.raises(ValueError, match="creator_id"):
        _valid_inputs(creator_id=cid)
