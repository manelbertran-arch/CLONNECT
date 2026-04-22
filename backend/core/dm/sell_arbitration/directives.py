"""Sales Intent directives emitted by the SalesIntentResolver.

Single enum with the four canonical outcomes of the arbitration pipeline.
See sibling resolver.py and docs/research/multi_signal_arbitration_review.md.
"""

from __future__ import annotations

from enum import Enum


class SellDirective(Enum):
    SELL_ACTIVELY = "SELL_ACTIVELY"
    SOFT_MENTION = "SOFT_MENTION"
    NO_SELL = "NO_SELL"
    REDIRECT = "REDIRECT"
