"""Integration tests for SalesIntentResolver.

Covers:
  - The 3 Type-1 conflicts from the S6 audit (R.4, R.5, C.8)
  - Happy paths (normal sell, FAMILIA veto, frustration veto)
  - Edge cases (all-neutral → P7 default; resolver is stateless)
  - _redact_for_log behavior (4-byte blake2b hash, no full creator_id in log)
  - sell_resolver_total metric emission with layer labels
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List

import pytest

from core.dm.sell_arbitration.directives import SellDirective
from core.dm.sell_arbitration.inputs import SellArbiterInputs
from core.dm.sell_arbitration.resolver import SalesIntentResolver, _redact_for_log


def _valid_inputs(**overrides: Any) -> SellArbiterInputs:
    """Neutral inputs that fall through to P7 (SOFT_MENTION) by default."""
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


@pytest.fixture
def resolver() -> SalesIntentResolver:
    return SalesIntentResolver()


# ─────────────────────────────────────────────────────────────────────────────
# The 3 Type-1 conflicts from audit S6
# ─────────────────────────────────────────────────────────────────────────────

def test_type_1_R4_dna_familia_vs_conv_propuesta(resolver: SalesIntentResolver) -> None:
    """R.4: DNA=FAMILIA + phase=PROPUESTA → NO_SELL (P3 beats P6).

    Pre-resolver: LLM saw "NUNCA vender" (DNA) + "Menciona el producto" (state).
    Post-resolver: single NO_SELL directive, no contradiction.
    """
    result = resolver.resolve(_valid_inputs(
        dna_relationship_type="FAMILIA",
        conv_phase="PROPUESTA",
    ))
    assert result is SellDirective.NO_SELL


def test_type_1_R5_frustration_vs_suppress(resolver: SalesIntentResolver) -> None:
    """R.5: frustration_level=2 + suppress_products=True → NO_SELL (P2 beats P4).

    Pre-resolver: Conv state/Scorer could emit conflicting signals. P2 (veto
    layer) short-circuits before P4 (arbitration layer) ever runs.
    Post-resolver: NO_SELL from veto layer, REDIRECT never considered.
    """
    result = resolver.resolve(_valid_inputs(
        frustration_level=2,
        suppress_products=True,
        conv_phase="PROPUESTA",
    ))
    assert result is SellDirective.NO_SELL


def test_type_1_C8_multi_trigger(resolver: SalesIntentResolver) -> None:
    """C.8: DNA=FAMILIA + phase=CIERRE + frustration=2 + suppress=True → NO_SELL.

    All 4 systems disagree; P2 wins (frustration veto in Layer 1), making the
    other three signals moot. Demonstrates that Layer 1 short-circuits cleanly
    under multi-trigger collision.
    """
    result = resolver.resolve(_valid_inputs(
        dna_relationship_type="FAMILIA",
        conv_phase="CIERRE",
        frustration_level=2,
        suppress_products=True,
    ))
    assert result is SellDirective.NO_SELL


# ─────────────────────────────────────────────────────────────────────────────
# Happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_happy_path_normal_lead_in_propuesta(resolver: SalesIntentResolver) -> None:
    """Clean sell: no veto, no blockers, phase=PROPUESTA → SELL_ACTIVELY (P6)."""
    result = resolver.resolve(_valid_inputs(
        dna_relationship_type="DESCONOCIDO",
        conv_phase="PROPUESTA",
    ))
    assert result is SellDirective.SELL_ACTIVELY


@pytest.mark.parametrize(
    "phase", ["INICIO", "CUALIFICACION", "DESCUBRIMIENTO", "PROPUESTA", "CIERRE", "OBJECIONES"]
)
def test_familia_blocks_sell_regardless_of_phase(
    resolver: SalesIntentResolver, phase: str
) -> None:
    """FAMILIA → NO_SELL (P3) regardless of conversation phase."""
    result = resolver.resolve(_valid_inputs(
        dna_relationship_type="FAMILIA",
        conv_phase=phase,
    ))
    assert result is SellDirective.NO_SELL


def test_frustrated_lead_asking_price(resolver: SalesIntentResolver) -> None:
    """Frustrated lead (L2) in sell phase → NO_SELL via P2."""
    result = resolver.resolve(_valid_inputs(
        frustration_level=2,
        conv_phase="PROPUESTA",
        dna_relationship_type="CLIENTE",
    ))
    assert result is SellDirective.NO_SELL


def test_colaborador_in_propuesta_yields_no_sell(resolver: SalesIntentResolver) -> None:
    """COLABORADOR in phase=PROPUESTA → NO_SELL (P3 beats P6).

    Added in P4: cross-promo partners are not a sales target. Without this,
    a COLABORADOR in PROPUESTA would have triggered SELL_ACTIVELY, damaging
    the professional relationship.
    """
    result = resolver.resolve(_valid_inputs(
        dna_relationship_type="COLABORADOR",
        conv_phase="PROPUESTA",
    ))
    assert result is SellDirective.NO_SELL


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_all_neutral_inputs_defaults_to_soft_mention(
    resolver: SalesIntentResolver,
) -> None:
    """All inputs at minimum neutral values → SOFT_MENTION via P7 default."""
    result = resolver.resolve(SellArbiterInputs(
        creator_id="minimal",
        dna_relationship_type="DESCONOCIDO",
        conv_phase="INICIO",
        frustration_level=0,
        relationship_score=0.0,
        suppress_products=False,
        soft_suppress=False,
        sensitive_action_required=None,
        has_pending_sales_commitment=False,
    ))
    assert result is SellDirective.SOFT_MENTION


def test_resolver_is_stateless_repeatable_calls(
    resolver: SalesIntentResolver,
) -> None:
    """Same inputs across many calls → same directive (determinism)."""
    inp = _valid_inputs(dna_relationship_type="FAMILIA", conv_phase="PROPUESTA")
    directives = {resolver.resolve(inp) for _ in range(20)}
    assert directives == {SellDirective.NO_SELL}


def test_resolver_same_instance_handles_varied_inputs(
    resolver: SalesIntentResolver,
) -> None:
    """Shared instance handles heterogeneous inputs without state leaking."""
    r1 = resolver.resolve(_valid_inputs(dna_relationship_type="FAMILIA"))
    r2 = resolver.resolve(_valid_inputs(conv_phase="PROPUESTA"))
    r3 = resolver.resolve(_valid_inputs(frustration_level=3))
    assert r1 is SellDirective.NO_SELL
    assert r2 is SellDirective.SELL_ACTIVELY
    assert r3 is SellDirective.NO_SELL


# ─────────────────────────────────────────────────────────────────────────────
# _redact_for_log — creator_id never leaks in plain text
# ─────────────────────────────────────────────────────────────────────────────

def test_redact_for_log_replaces_creator_id_with_blake2b_hash() -> None:
    inp = _valid_inputs(creator_id="iris_bertran")
    redacted = _redact_for_log(inp)

    assert "creator_id" not in redacted
    assert "creator_hash" in redacted

    expected = hashlib.blake2b(b"iris_bertran", digest_size=4).hexdigest()
    assert redacted["creator_hash"] == expected
    # 4 bytes → 8 hex chars.
    assert len(redacted["creator_hash"]) == 8


def test_redact_for_log_keeps_other_fields_intact() -> None:
    inp = _valid_inputs(
        creator_id="stefano_bonanno",
        dna_relationship_type="AMISTAD_CERCANA",
        conv_phase="PROPUESTA",
        frustration_level=1,
    )
    redacted = _redact_for_log(inp)
    assert redacted["dna_relationship_type"] == "AMISTAD_CERCANA"
    assert redacted["conv_phase"] == "PROPUESTA"
    assert redacted["frustration_level"] == 1
    assert redacted["suppress_products"] is False


def test_resolver_log_contains_hash_not_full_creator_id_via_veto(
    resolver: SalesIntentResolver,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="core.dm.sell_arbitration.resolver")

    creator = "iris_bertran"
    expected_hash = hashlib.blake2b(creator.encode("utf-8"), digest_size=4).hexdigest()

    # frustration_level=3 → Layer 1 (veto) fires, layer label = "veto".
    resolver.resolve(_valid_inputs(creator_id=creator, frustration_level=3))

    resolver_records = [
        rec for rec in caplog.records
        if rec.name == "core.dm.sell_arbitration.resolver"
    ]
    assert resolver_records, "resolver logger emitted no records"
    combined = " ".join(r.getMessage() for r in resolver_records)

    assert "[SELL_RESOLVER]" in combined
    assert expected_hash in combined
    assert creator not in combined  # Full creator slug must never appear.
    assert "directive=NO_SELL" in combined
    assert "layer=veto" in combined


def test_resolver_log_contains_hash_not_full_creator_id_via_arbitration(
    resolver: SalesIntentResolver,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="core.dm.sell_arbitration.resolver")

    creator = "stefano_bonanno"
    expected_hash = hashlib.blake2b(creator.encode("utf-8"), digest_size=4).hexdigest()

    # DNA=FAMILIA → Layer 1 returns None, Layer 2 P3 fires, layer label = "arbitration".
    resolver.resolve(_valid_inputs(
        creator_id=creator,
        dna_relationship_type="FAMILIA",
    ))

    resolver_records = [
        rec for rec in caplog.records
        if rec.name == "core.dm.sell_arbitration.resolver"
    ]
    assert resolver_records, "resolver logger emitted no records"
    combined = " ".join(r.getMessage() for r in resolver_records)

    assert "[SELL_RESOLVER]" in combined
    assert expected_hash in combined
    assert creator not in combined
    assert "directive=NO_SELL" in combined
    assert "layer=arbitration" in combined


# ─────────────────────────────────────────────────────────────────────────────
# sell_resolver_total metric emission
# ─────────────────────────────────────────────────────────────────────────────

def test_resolver_emits_veto_layer_metric(
    resolver: SalesIntentResolver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        if name == "sell_resolver_total":
            calls.append(labels)

    monkeypatch.setattr("core.dm.sell_arbitration.resolver.emit_metric", _capture)

    resolver.resolve(_valid_inputs(
        creator_id="iris_bertran",
        frustration_level=3,
    ))
    assert calls == [{
        "layer": "veto",
        "directive": "NO_SELL",
        "creator_id": "iris_bertran",
    }]


def test_resolver_emits_arbitration_layer_metric(
    resolver: SalesIntentResolver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Dict[str, Any]] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        if name == "sell_resolver_total":
            calls.append(labels)

    monkeypatch.setattr("core.dm.sell_arbitration.resolver.emit_metric", _capture)

    resolver.resolve(_valid_inputs(
        creator_id="stefano_bonanno",
        conv_phase="PROPUESTA",
        dna_relationship_type="DESCONOCIDO",
    ))
    assert calls == [{
        "layer": "arbitration",
        "directive": "SELL_ACTIVELY",
        "creator_id": "stefano_bonanno",
    }]


def test_resolver_emits_exactly_one_total_metric_per_call(
    resolver: SalesIntentResolver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[str] = []

    def _capture(name: str, value: Any = 1, **labels: Any) -> None:
        if name == "sell_resolver_total":
            calls.append(name)

    monkeypatch.setattr("core.dm.sell_arbitration.resolver.emit_metric", _capture)

    resolver.resolve(_valid_inputs(conv_phase="PROPUESTA"))
    resolver.resolve(_valid_inputs(frustration_level=2))
    resolver.resolve(_valid_inputs(dna_relationship_type="FAMILIA"))
    assert len(calls) == 3  # Exactly one per resolve() call.
