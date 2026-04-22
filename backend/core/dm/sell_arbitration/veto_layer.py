"""Layer 1 — hard-veto evaluation (SafeCRS-pattern).

Evaluates P1 (sensitive soft action) and P2 (frustration >= 2) as binary
hard gates. If either fires, the resolver short-circuits to NO_SELL without
entering the ordinal Layer 2.

See docs/research/multi_signal_arbitration_review.md — C3 (SafeCRS) reports
96.5% reduction in violation rate when hard vetos precede learned reasoning.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.dm.sell_arbitration.directives import SellDirective
from core.dm.sell_arbitration.inputs import SellArbiterInputs
from core.observability.metrics import emit_metric

logger = logging.getLogger(__name__)


def evaluate_vetos(inputs: SellArbiterInputs) -> Optional[SellDirective]:
    """Return NO_SELL if a hard veto fires, else None.

    Precedence inside the layer: P1 (sensitive) evaluated before P2
    (frustration). If both would fire, P1 wins and its reason is emitted.
    Order matters only for telemetry — the directive is identical either way.
    """

    # P1 — sensitive soft action (MINOR, EATING_DISORDER, ECONOMIC_DISTRESS).
    # Hard-sensitive cases (SELF_HARM, THREAT, PHISHING, SPAM) exit the
    # pipeline earlier and never reach the arbiter.
    if inputs.sensitive_action_required is not None:
        reason = f"sensitive:{inputs.sensitive_action_required}"
        logger.info("[SELL_VETO] veto triggered: P1 %s", reason)
        emit_metric(
            "sell_veto_triggered",
            priority="P1",
            reason=reason,
            creator_id=inputs.creator_id,
        )
        return SellDirective.NO_SELL

    # P2 — frustration hard gate. Levels 2 and 3 both veto the sale.
    if inputs.frustration_level >= 2:
        reason = f"frustration_level:{inputs.frustration_level}"
        logger.info("[SELL_VETO] veto triggered: P2 %s", reason)
        emit_metric(
            "sell_veto_triggered",
            priority="P2",
            reason=reason,
            creator_id=inputs.creator_id,
        )
        return SellDirective.NO_SELL

    return None
