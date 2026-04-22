"""Unit tests for SellArbiterInputs validation.

Complements the arbitration_layer / resolver tests by focusing on the
dataclass contract: accepted DNA types, invalid types raising ValueError,
and the COLABORADOR case added in P4.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from core.dm.sell_arbitration.inputs import (
    SellArbiterInputs,
    VALID_CONV_PHASES,
    VALID_DNA_TYPES,
    VALID_SENSITIVE_ACTIONS,
)


def _base(**overrides: Any) -> Dict[str, Any]:
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
    return defaults


def test_valid_dna_types_includes_colaborador() -> None:
    assert "COLABORADOR" in VALID_DNA_TYPES


@pytest.mark.parametrize("dna_type", sorted(VALID_DNA_TYPES))
def test_every_valid_dna_type_is_accepted(dna_type: str) -> None:
    SellArbiterInputs(**_base(dna_relationship_type=dna_type))


def test_colaborador_accepted_specifically() -> None:
    inp = SellArbiterInputs(**_base(dna_relationship_type="COLABORADOR"))
    assert inp.dna_relationship_type == "COLABORADOR"


@pytest.mark.parametrize("bad_dna", ["unknown", "family", "colaborador"])
def test_invalid_dna_still_raises(bad_dna: str) -> None:
    with pytest.raises(ValueError, match="invalid dna_relationship_type"):
        SellArbiterInputs(**_base(dna_relationship_type=bad_dna))


@pytest.mark.parametrize("phase", sorted(VALID_CONV_PHASES))
def test_every_valid_phase_is_accepted(phase: str) -> None:
    SellArbiterInputs(**_base(conv_phase=phase))


@pytest.mark.parametrize("bad_phase", ["propuesta", "UNKNOWN", ""])
def test_invalid_phase_raises(bad_phase: str) -> None:
    with pytest.raises(ValueError, match="invalid conv_phase"):
        SellArbiterInputs(**_base(conv_phase=bad_phase))


def test_none_sensitive_action_is_accepted() -> None:
    SellArbiterInputs(**_base(sensitive_action_required=None))


@pytest.mark.parametrize("action", sorted(VALID_SENSITIVE_ACTIONS))
def test_valid_sensitive_actions_accepted(action: str) -> None:
    SellArbiterInputs(**_base(sensitive_action_required=action))


def test_invalid_sensitive_action_raises() -> None:
    with pytest.raises(ValueError, match="invalid sensitive_action_required"):
        SellArbiterInputs(**_base(sensitive_action_required="unknown_action"))


def test_frustration_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="frustration_level out of range"):
        SellArbiterInputs(**_base(frustration_level=4))
    with pytest.raises(ValueError, match="frustration_level out of range"):
        SellArbiterInputs(**_base(frustration_level=-1))


def test_relationship_score_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="relationship_score out of range"):
        SellArbiterInputs(**_base(relationship_score=1.01))
    with pytest.raises(ValueError, match="relationship_score out of range"):
        SellArbiterInputs(**_base(relationship_score=-0.01))


def test_empty_creator_id_raises() -> None:
    with pytest.raises(ValueError, match="creator_id must be a non-empty slug"):
        SellArbiterInputs(**_base(creator_id=""))
    with pytest.raises(ValueError, match="creator_id must be a non-empty slug"):
        SellArbiterInputs(**_base(creator_id="   "))
