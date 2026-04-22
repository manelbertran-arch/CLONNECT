"""P4 adapter — bridges the DM pipeline context to SellArbiterInputs.

The resolver itself is a pure decision function (see resolver.py). This
adapter:

  1. Extracts the 9 fields of SellArbiterInputs from the heterogeneous
     context available at ``core/dm/phases/context.py`` (raw_dna dict,
     state_meta dict, cognitive_metadata dict, DetectionResult,
     RelationshipScore, commitment text).
  2. Normalizes enum strings to UPPERCASE (conv_phase, dna_relationship_type)
     and applies defensive fallbacks when upstream sources are missing.
  3. Renders the human-readable directive text that replaces the four
     previous prompt injections (dna hint / state_context / frustration_note
     / product list stripping) in recalling block assembly.
  4. Synthesizes the R.9 aux_text ("pending sales commitment") when
     directive == NO_SELL AND inputs.has_pending_sales_commitment is True.

Every fallback emits ``sell_adapter_fallback`` so prolonged fallback rates
surface upstream bugs instead of silently degrading arbitration quality.

Reference:
  - sell_arbitration/README.md §"Integration notes for P4"
  - docs/audit_sprint5/s6_rematrix/sales_arbitration_design.md §2 / §13
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from core.dm.sell_arbitration.directives import SellDirective
from core.dm.sell_arbitration.inputs import (
    SellArbiterInputs,
    VALID_CONV_PHASES,
    VALID_DNA_TYPES,
    VALID_SENSITIVE_ACTIONS,
)
from core.observability.metrics import emit_metric

logger = logging.getLogger(__name__)


_DIRECTIVE_TEXTS: dict[SellDirective, str] = {
    SellDirective.NO_SELL: (
        "Directiva: NO vendas en este mensaje. Responde con naturalidad sin "
        "mencionar productos, precios ni enlaces de compra."
    ),
    SellDirective.SOFT_MENTION: (
        "Directiva: puedes mencionar tu oferta solo si encaja de forma natural "
        "con el tema, sin presionar ni dar precios/links salvo que los pida."
    ),
    SellDirective.SELL_ACTIVELY: (
        "Directiva: este es momento de presentar el producto. Sé claro con lo "
        "que ofreces, incluye precio si es relevante y facilita el siguiente paso."
    ),
    SellDirective.REDIRECT: (
        "Directiva: la relación no soporta venta ahora. Responde con valor "
        "(consejo, empatía, info útil) sin mencionar productos ni precios."
    ),
}

_AUX_TEXT_R9 = (
    "Tienes un compromiso pendiente con esta persona. Cuando sea buen momento, "
    "cumple lo prometido sin añadir presión de venta."
)

_DEFAULT_DNA = "DESCONOCIDO"
_DEFAULT_PHASE = "INICIO"


def _emit_fallback(creator_id: str, field: str) -> None:
    emit_metric("sell_adapter_fallback", creator_id=creator_id, field=field)


def _extract_dna(
    creator_id: str, raw_dna: Optional[Mapping[str, Any]]
) -> str:
    # raw_dna may be None or dict without the key; DB stores uppercase strings
    # but we .upper() defensively so casing drift in callers can't break us.
    if raw_dna is None:
        _emit_fallback(creator_id, "dna")
        return _DEFAULT_DNA
    value = raw_dna.get("relationship_type")
    if not value:
        _emit_fallback(creator_id, "dna")
        return _DEFAULT_DNA
    normalized = str(value).upper()
    if normalized not in VALID_DNA_TYPES:
        # Unknown value — fall back rather than raise to keep the pipeline alive.
        # The resolver's fail-fast still catches it if someone bypasses the adapter.
        logger.warning(
            "[sell-adapter] unknown dna_relationship_type=%r — using %s",
            value, _DEFAULT_DNA,
        )
        _emit_fallback(creator_id, "dna")
        return _DEFAULT_DNA
    return normalized


def _extract_phase(
    creator_id: str, state_meta: Optional[Mapping[str, Any]]
) -> str:
    if not state_meta:
        _emit_fallback(creator_id, "phase")
        return _DEFAULT_PHASE
    value = state_meta.get("conversation_phase")
    if not value:
        _emit_fallback(creator_id, "phase")
        return _DEFAULT_PHASE
    normalized = str(value).upper()
    if normalized not in VALID_CONV_PHASES:
        logger.warning(
            "[sell-adapter] unknown conv_phase=%r — using %s",
            value, _DEFAULT_PHASE,
        )
        _emit_fallback(creator_id, "phase")
        return _DEFAULT_PHASE
    return normalized


def _extract_frustration(creator_id: str, detection: Any) -> int:
    if detection is None:
        _emit_fallback(creator_id, "frustration")
        return 0
    fsig = getattr(detection, "frustration_signals", None)
    if fsig is None:
        _emit_fallback(creator_id, "frustration")
        return 0
    raw = getattr(fsig, "level", 0)
    try:
        level = int(raw)
    except (TypeError, ValueError):
        _emit_fallback(creator_id, "frustration")
        return 0
    if level < 0:
        return 0
    if level > 3:
        return 3
    return level


def _extract_rel_score_fields(
    creator_id: str, rel_score: Any
) -> tuple[float, bool, bool]:
    if rel_score is None:
        _emit_fallback(creator_id, "rel_score")
        return 0.0, False, False
    try:
        score = float(getattr(rel_score, "score", 0.0))
    except (TypeError, ValueError):
        score = 0.0
    if score < 0.0:
        score = 0.0
    elif score > 1.0:
        score = 1.0
    suppress = bool(getattr(rel_score, "suppress_products", False))
    soft = bool(getattr(rel_score, "soft_suppress", False))
    return score, suppress, soft


def _extract_sensitive_action(
    creator_id: str, cognitive_metadata: Mapping[str, Any]
) -> Optional[str]:
    value = cognitive_metadata.get("sensitive_action_required")
    if value is None or value == "none":
        # Absence is the common case — no fallback metric.
        return None
    if value in VALID_SENSITIVE_ACTIONS:
        return value
    # Unknown action seen upstream — treat as absent but log + count so the
    # divergence is visible without breaking the resolver contract.
    logger.warning(
        "[sell-adapter] unknown sensitive_action_required=%r — treated as None",
        value,
    )
    _emit_fallback(creator_id, "sensitive")
    return None


def _extract_pending_commitment(commitment_text: Optional[str]) -> bool:
    if not commitment_text:
        return False
    return bool(commitment_text.strip())


def extract_sell_arbiter_inputs(
    *,
    creator_id: str,
    raw_dna: Optional[Mapping[str, Any]],
    state_meta: Optional[Mapping[str, Any]],
    cognitive_metadata: Optional[Mapping[str, Any]],
    detection: Any,
    rel_score: Any,
    commitment_text: Optional[str],
) -> SellArbiterInputs:
    """Build a validated ``SellArbiterInputs`` from pipeline-level sources.

    Every upstream source is permitted to be None/missing: the adapter
    applies a documented default and emits ``sell_adapter_fallback`` so the
    fallback rate is observable. The resolver's own fail-fast validation
    still catches genuinely impossible values (unknown DNA type that slips
    past this filter, out-of-range frustration, etc.).
    """
    meta: Mapping[str, Any] = cognitive_metadata or {}

    score, suppress, soft = _extract_rel_score_fields(creator_id, rel_score)

    return SellArbiterInputs(
        creator_id=creator_id,
        dna_relationship_type=_extract_dna(creator_id, raw_dna),
        conv_phase=_extract_phase(creator_id, state_meta),
        frustration_level=_extract_frustration(creator_id, detection),
        relationship_score=score,
        suppress_products=suppress,
        soft_suppress=soft,
        sensitive_action_required=_extract_sensitive_action(creator_id, meta),
        has_pending_sales_commitment=_extract_pending_commitment(commitment_text),
    )


def render_directive_text(directive: SellDirective) -> str:
    """Return the prompt-ready Spanish directive line for a SellDirective.

    The text is concise (1–2 sentences, prefixed with ``Directiva:``) and
    self-contained so it can stand alone in the recalling block without
    leaning on the suppressed state_context or frustration_note.
    """
    text = _DIRECTIVE_TEXTS.get(directive)
    if text is None:
        # Defensive — new SellDirective added without updating this map.
        raise KeyError(f"no directive text registered for {directive!r}")
    return text


def synthesize_aux_text(
    directive: SellDirective,
    inputs: SellArbiterInputs,
) -> str:
    """Return R.9 aux_text when applicable, else empty string.

    R.9 (sales_arbitration_design.md §3 Caso B): when the resolver orders
    NO_SELL but a sales-ish commitment is pending, the LLM still needs to
    acknowledge the commitment — otherwise the lead perceives ghosting.
    The aux_text is injected separately from the directive so the resolver
    stays a pure decision function (§13 design doc).
    """
    if directive is SellDirective.NO_SELL and inputs.has_pending_sales_commitment:
        return _AUX_TEXT_R9
    return ""
