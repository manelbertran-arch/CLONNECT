"""SellArbiterInputs — the 9-field contract consumed by the two-layer resolver.

Fields are validated at construction. Adapters (e.g. P4 wiring in context.py)
must pass uppercase string enums (``dna_relationship_type``, ``conv_phase``);
normalization belongs at the adapter boundary, not inside the resolver.

See docs/audit_sprint5/s6_rematrix/sales_arbitration_design.md §2 for the
field-by-field design rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# BY_DESIGN: raise on unknown DNA/phase/sensitive values to detect upstream
# adapter bugs fast. Change to warning+default only if silent-degrade becomes
# a real operational need (tracked via sell_* telemetry).
VALID_DNA_TYPES = frozenset({
    "FAMILIA",
    "INTIMA",
    "AMISTAD_CERCANA",
    "AMISTAD_CASUAL",
    "CLIENTE",
    "DESCONOCIDO",
})

VALID_CONV_PHASES = frozenset({
    "INICIO",
    "CUALIFICACION",
    "DESCUBRIMIENTO",
    "PROPUESTA",
    "OBJECIONES",
    "CIERRE",
    "ESCALAR",
})

VALID_SENSITIVE_ACTIONS = frozenset({
    "no_pressure_sale",
    "empathetic_response",
})


@dataclass(frozen=True)
class SellArbiterInputs:
    """Immutable input record for the SalesIntentResolver.

    All nine fields are required. conv_phase and dna_relationship_type must
    be uppercase — the adapter is responsible for normalization before
    constructing this record.
    """

    creator_id: str
    dna_relationship_type: str
    conv_phase: str
    frustration_level: int
    relationship_score: float
    suppress_products: bool
    soft_suppress: bool
    sensitive_action_required: Optional[str]
    # BY_DESIGN: has_pending_sales_commitment is NOT consumed by the resolver
    # in v1. It is retained so the P4 adapter layer can synthesize aux_text
    # for the NO_SELL directive (design case R.9: pending commitment +
    # frustration). See sales_arbitration_design.md §3 Caso B / §13 aux_text
    # and README "Scope v1".
    has_pending_sales_commitment: bool

    def __post_init__(self) -> None:
        # BY_DESIGN fail-fast: bad inputs = bug in adapter (P4), not silently
        # masked. All raises carry the offending value verbatim for log triage.
        if not self.creator_id or not self.creator_id.strip():
            raise ValueError("creator_id must be a non-empty slug")
        if self.dna_relationship_type not in VALID_DNA_TYPES:
            raise ValueError(
                f"invalid dna_relationship_type: {self.dna_relationship_type!r} "
                f"(expected one of {sorted(VALID_DNA_TYPES)})"
            )
        if self.conv_phase not in VALID_CONV_PHASES:
            raise ValueError(
                f"invalid conv_phase: {self.conv_phase!r} "
                f"(expected one of {sorted(VALID_CONV_PHASES)})"
            )
        if not isinstance(self.frustration_level, int) or not (0 <= self.frustration_level <= 3):
            raise ValueError(
                f"frustration_level out of range 0..3: {self.frustration_level!r}"
            )
        if not (0.0 <= float(self.relationship_score) <= 1.0):
            raise ValueError(
                f"relationship_score out of range 0.0..1.0: {self.relationship_score!r}"
            )
        if (
            self.sensitive_action_required is not None
            and self.sensitive_action_required not in VALID_SENSITIVE_ACTIONS
        ):
            raise ValueError(
                f"invalid sensitive_action_required: {self.sensitive_action_required!r} "
                f"(expected None or one of {sorted(VALID_SENSITIVE_ACTIONS)})"
            )
