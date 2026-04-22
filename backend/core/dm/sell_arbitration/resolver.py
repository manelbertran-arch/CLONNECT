"""SalesIntentResolver — two-layer composition (veto + arbitration).

Public entry point of the sell_arbitration package. Stateless; safe to
instantiate at module scope and share across requests / threads.

Flow:
  inputs → Layer 1 (veto)  ── NO_SELL ──▶ return
                 │
                 └── None ──▶ Layer 2 (arbitration) → SellDirective → return

Scope v1 — resolve() returns SellDirective only. The design doc §13 originally
proposed a richer SellArbiterResult with aux_text / blocking_signal fields;
v1 defers aux_text synthesis to the P4 adapter layer (outside this package),
which must:

  1. Call resolver.resolve(inputs) to obtain the directive
  2. If directive == NO_SELL AND inputs.has_pending_sales_commitment: synthesize
     aux_text at the adapter layer (not inside the resolver)
  3. Inject aux_text into the prompt separately from the directive

This keeps the resolver a pure decision function with a minimal return surface.

Reference: docs/research/multi_signal_arbitration_review.md (two-layer pattern).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict
from typing import Any, Dict

from core.dm.sell_arbitration.arbitration_layer import evaluate_arbitration
from core.dm.sell_arbitration.directives import SellDirective
from core.dm.sell_arbitration.inputs import SellArbiterInputs
from core.dm.sell_arbitration.veto_layer import evaluate_vetos
from core.observability.metrics import emit_metric

logger = logging.getLogger(__name__)


def _redact_for_log(inputs: SellArbiterInputs) -> Dict[str, Any]:
    """Return a loggable dict with creator_id replaced by a short blake2b hash.

    Keeps log volume bounded and avoids echoing the full creator slug into
    every [SELL_RESOLVER] line. Metrics preserve the full ``creator_id`` in
    Prometheus labels — only logs use the hash.
    """
    d = asdict(inputs)
    cid = d.pop("creator_id", "") or ""
    d["creator_hash"] = hashlib.blake2b(cid.encode("utf-8"), digest_size=4).hexdigest()
    return d


class SalesIntentResolver:
    """Two-layer sell-intent arbitrator. Stateless and thread-safe.

    Usage:
        resolver = SalesIntentResolver()
        directive = resolver.resolve(SellArbiterInputs(...))
    """

    def resolve(self, inputs: SellArbiterInputs) -> SellDirective:
        veto_directive = evaluate_vetos(inputs)
        if veto_directive is not None:
            self._log_outcome(inputs, veto_directive, layer="veto")
            emit_metric(
                "sell_resolver_total",
                layer="veto",
                directive=veto_directive.value,
                creator_id=inputs.creator_id,
            )
            return veto_directive

        arb_directive = evaluate_arbitration(inputs)
        self._log_outcome(inputs, arb_directive, layer="arbitration")
        emit_metric(
            "sell_resolver_total",
            layer="arbitration",
            directive=arb_directive.value,
            creator_id=inputs.creator_id,
        )
        return arb_directive

    @staticmethod
    def _log_outcome(
        inputs: SellArbiterInputs,
        directive: SellDirective,
        layer: str,
    ) -> None:
        logger.info(
            "[SELL_RESOLVER] inputs=%s directive=%s layer=%s",
            _redact_for_log(inputs),
            directive.value,
            layer,
        )
