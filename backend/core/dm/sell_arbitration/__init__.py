"""Sales Intent Arbitration — two-layer resolver package.

Layer 1 (veto): hard binary gates for sensitive/frustration.
Layer 2 (arbitration): ordinal precedence over DNA, scorer, conv state.
Resolver: composes both layers and exposes the public entry point.

Reference: docs/research/multi_signal_arbitration_review.md (SafeCRS-inspired).
Design: docs/audit_sprint5/s6_rematrix/sales_arbitration_design.md.

This PR lands the arbitration module in isolation. Wiring into context.py
(replacing the 4 current injections) belongs to the next PR (P4).
"""

from core.dm.sell_arbitration.arbitration_layer import evaluate_arbitration
from core.dm.sell_arbitration.directives import SellDirective
from core.dm.sell_arbitration.inputs import SellArbiterInputs
from core.dm.sell_arbitration.resolver import SalesIntentResolver
from core.dm.sell_arbitration.veto_layer import evaluate_vetos

__all__ = [
    "SellDirective",
    "SellArbiterInputs",
    "SalesIntentResolver",
    "evaluate_vetos",
    "evaluate_arbitration",
]
