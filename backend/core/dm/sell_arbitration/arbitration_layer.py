"""Layer 2 — ordinal arbitration (P3-P7).

Runs only when Layer 1 (veto_layer.evaluate_vetos) returned None. Evaluates
priorities P3 (DNA no-sell), P4 (scorer suppress), P5 (scorer soft / DNA soft),
P6 (conv_phase sell) in order; falls through to P7 default SOFT_MENTION.

Each _check_pN helper is a pure predicate returning (fires, directive, reason)
for unit-test isolation. evaluate_arbitration iterates them and returns the
first match.

Reference: docs/audit_sprint5/s6_rematrix/sales_arbitration_design.md §3 + §12.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional, Tuple

from core.dm.sell_arbitration.directives import SellDirective
from core.dm.sell_arbitration.inputs import SellArbiterInputs
from core.observability.metrics import emit_metric

logger = logging.getLogger(__name__)

DNA_NO_SELL_SET = frozenset({"FAMILIA", "INTIMA"})
DNA_SOFT_SET = frozenset({"AMISTAD_CERCANA"})
SELL_PHASES = frozenset({"PROPUESTA", "CIERRE"})

CheckResult = Tuple[bool, Optional[SellDirective], str]


def _check_p3(inputs: SellArbiterInputs) -> CheckResult:
    """P3 — DNA relationship types that forbid selling."""
    if inputs.dna_relationship_type in DNA_NO_SELL_SET:
        return True, SellDirective.NO_SELL, f"dna:{inputs.dna_relationship_type}"
    return False, None, ""


def _check_p4(inputs: SellArbiterInputs) -> CheckResult:
    """P4 — scorer hard suppress (products stripped from prompt).

    The design doc's "AND dna NOT in NO_SELL set" qualifier is redundant:
    P3 short-circuits first, so when P4 runs, DNA is already not in the
    no-sell set.
    """
    if inputs.suppress_products:
        return True, SellDirective.REDIRECT, "scorer_suppress_products"
    return False, None, ""


def _check_p5(inputs: SellArbiterInputs) -> CheckResult:
    """P5 — scorer soft suppress OR close-friend DNA."""
    if inputs.soft_suppress:
        return True, SellDirective.SOFT_MENTION, "scorer_soft_suppress"
    if inputs.dna_relationship_type in DNA_SOFT_SET:
        return True, SellDirective.SOFT_MENTION, f"dna:{inputs.dna_relationship_type}"
    return False, None, ""


def _check_p6(inputs: SellArbiterInputs) -> CheckResult:
    """P6 — conversation phase signals active sell stage."""
    if inputs.conv_phase in SELL_PHASES:
        return True, SellDirective.SELL_ACTIVELY, f"phase:{inputs.conv_phase}"
    return False, None, ""


_PRIORITY_CHECKS: List[Tuple[str, Callable[[SellArbiterInputs], CheckResult]]] = [
    ("P3", _check_p3),
    ("P4", _check_p4),
    ("P5", _check_p5),
    ("P6", _check_p6),
]


def evaluate_arbitration(inputs: SellArbiterInputs) -> SellDirective:
    """Layer 2 — ordinal arbitration. Always returns a SellDirective.

    Precondition: caller (resolver.py) invokes this only when Layer 1 veto
    returned None. Layer 2 never returns NO_SELL via P1/P2 — those paths are
    owned by Layer 1.
    """
    for priority, check in _PRIORITY_CHECKS:
        fires, directive, reason = check(inputs)
        if fires and directive is not None:
            logger.info(
                "[SELL_ARB] arbitration: priority=%s directive=%s reason=%s",
                priority, directive.value, reason,
            )
            emit_metric(
                "sell_arbitration_resolved",
                priority=priority,
                directive=directive.value,
                reason=reason,
                creator_id=inputs.creator_id,
            )
            return directive

    # P7 default — no priority fired, emit SOFT_MENTION.
    logger.info(
        "[SELL_ARB] arbitration: priority=P7 directive=%s reason=default",
        SellDirective.SOFT_MENTION.value,
    )
    emit_metric(
        "sell_arbitration_resolved",
        priority="P7",
        directive=SellDirective.SOFT_MENTION.value,
        reason="default",
        creator_id=inputs.creator_id,
    )
    return SellDirective.SOFT_MENTION
