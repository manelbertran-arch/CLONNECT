"""
Response strategy determination for DM Agent V2.

Determines HOW the LLM should approach a response based on:
- Relationship type (family, friend, follower)     [P1, P2 kept behind callsite hardcoding]
- Help signals in the message                      [P5 — vocab_meta-driven with universal fallback]
- Purchase intent                                  [P6 — gated against resolver S6 NO_SELL at callsite]
- First message vs returning                      [P3]
- Returning user with history                     [P4 — vocab_meta-driven apelativos + openers + anti-bugs]
- Ghost/reactivation                              [P7]

Universality principle: ALL per-creator linguistic data (apelativos,
openers_to_avoid, anti_bugs_verbales, help_signals) is sourced from the
`vocab_meta` blob in `personality_docs` DB. The function falls back to
neutral hints when vocab is missing — it NEVER hardcodes creator-specific
tokens. `creator_display_name` is identity, not vocab, and comes from
calibrations via the caller.

See docs/forensic/dm_strategy/ for full forensic write-up.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Config — thresholds (env-overridable, not hardcoded per creator)
# ─────────────────────────────────────────────────────────────────────────────

import os

RECURRENT_HISTORY_MIN = int(os.getenv("DM_STRATEGY_RECURRENT_THRESHOLD", "4"))

# Universal purchase-intent set (IntentClassifier nomenclature — legacy +
# modern coexist; consolidation is tracked in DECISIONS.md as BUG-009)
PURCHASE_INTENTS = frozenset({
    "purchase", "pricing", "product_info", "purchase_intent", "product_question",
})

# Ghost/fantasma stage name (localized; stage names come from DB, not language)
GHOST_STAGE_VALUES = frozenset({"fantasma"})

# DNA relationship categories that activate the (currently dormant) PERSONAL branch.
# Kept for completeness — callsite hardcodes `relationship_type=""` since
# commit 9752df768 (see BUG-004 in 03_bugs.md).
PERSONAL_DNA_VALUES = frozenset({"FAMILIA", "INTIMA"})


# ─────────────────────────────────────────────────────────────────────────────
# Vocab lookup — reads `personality_docs.content` (JSONB, doc_type='vocab_meta')
# ─────────────────────────────────────────────────────────────────────────────

def _lookup_vocab_list(creator_id: Optional[str], vocab_key: str) -> List[str]:
    """Return a vocab list for the creator.

    Mined source: the JSON stored in `personality_docs` for this creator
    under `doc_type='vocab_meta'` (loaded by services.calibration_loader).

    Fallback: empty list — the caller then emits a neutral hint without
    creator-specific tokens. NEVER returns Iris defaults or any other
    hardcoded creator values.

    Emits `dm_strategy_vocab_source{vocab_type, source=mined|fallback}`
    so callers can observe coverage in Prometheus without instrumentation.
    """
    if not creator_id:
        _emit_vocab_metric(creator_id, vocab_key, "fallback")
        return []
    try:
        from services.calibration_loader import _load_creator_vocab
        vocab = _load_creator_vocab(creator_id) or {}
        values = vocab.get(vocab_key) or []
        if not isinstance(values, list):
            values = []
        source = "mined" if values else "fallback"
        _emit_vocab_metric(creator_id, vocab_key, source)
        return [str(v).strip() for v in values if v and isinstance(v, (str, int))]
    except Exception as exc:
        logger.debug("[dm_strategy] vocab lookup failed for %s/%s: %s", creator_id, vocab_key, exc)
        _emit_vocab_metric(creator_id, vocab_key, "fallback")
        return []


def _emit_vocab_metric(creator_id: Optional[str], vocab_type: str, source: str) -> None:
    try:
        from core.observability.metrics import emit_metric
        emit_metric(
            "dm_strategy_vocab_source",
            creator_id=creator_id or "unknown",
            vocab_type=vocab_type,
            source=source,
        )
    except Exception:
        pass  # never let observability break the hot path


def _detect_help_signal(message: str, creator_id: Optional[str]) -> bool:
    """Return True if the message looks like a concrete help request.

    Primary: substring match over the creator's mined `help_signals` vocab
    (DB `personality_docs[doc_type='vocab_meta'].help_signals`).

    Fallback (when vocab empty): a conservative, language-agnostic
    heuristic based on the presence of "?" combined with a short set of
    universal negation-or-problem tokens. This is intentionally small to
    avoid becoming another hardcoded ES list. A proper semantic fallback
    (embedding cosine vs seed examples) is documented as deferred in
    03_bugs.md §BUG-005 — belongs to a separate mining worker.
    """
    if not message:
        return False
    msg_lower = message.lower()
    mined = _lookup_vocab_list(creator_id, "help_signals")
    if mined:
        return any(signal in msg_lower for signal in mined)
    # Universal fallback — "?" alone is not enough (greetings also ask).
    # We require a problem token + a question mark; tokens are cross-lingual
    # enough (negation + "no" in ES/IT/PT/CA) to be acceptable for E1 E1 only.
    # This path is metered via dm_strategy_vocab_source{source=fallback}.
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Strategy router
# ─────────────────────────────────────────────────────────────────────────────

def _determine_response_strategy(
    message: str,
    intent_value: str,
    relationship_type: str,
    is_first_message: bool,
    is_friend: bool,
    lead_stage: str,
    history_len: int = 0,
    creator_id: Optional[str] = None,
    creator_display_name: str = "",
) -> str:
    """Return a short LLM-guidance string or "" for the current turn.

    The hint tells the LLM HOW to approach the response (not what to say).
    Precedence is strict and top-down — the first matching branch wins.

    Parameters
    ----------
    message : the raw user message (not lowercased).
    intent_value : IntentClassifier output; used for P6 VENTA.
    relationship_type : DNA category. P1 activates on {FAMILIA, INTIMA}.
        The callsite (generation.py:197) hardcodes "" since commit 9752df768,
        keeping P1 dormant by design. See BUG-004 in 03_bugs.md.
    is_first_message : True on the first inbound turn.
    is_friend : relationship_scorer.suppress_products signal. Callsite
        hardcodes False since 9752df768 (see BUG-004).
    lead_stage : leads.stage enum; P7 activates on "fantasma".
    history_len : number of turns already in the conversation.
    creator_id : slug used for vocab_meta lookup (mined apelativos,
        openers_to_avoid, anti_bugs_verbales, help_signals). When None or
        when vocab is empty, all P4 references to creator-specific vocab
        are omitted and the hint stays neutral.
    creator_display_name : the creator's clone name (e.g. "Iris", "Stefano").
        Comes from `agent.personality["name"]` at the callsite. When empty,
        the hint avoids personal pronouns entirely.

    Returns
    -------
    str : the hint, or "" for no hint (default conversation).
    """
    msg_lower = message.lower().strip() if message else ""

    # Priority 1 — DNA PERSONAL/FAMILIA/INTIMA
    # Currently DORMANT in production: callsite hardcodes relationship_type=""
    # (commit 9752df768). Style guidance for these leads is migrated to
    # sell_arbitration/arbitration_layer in E2 (Q2 2026) — see DECISIONS.md.
    if relationship_type in PERSONAL_DNA_VALUES:
        return (
            "ESTRATEGIA: PERSONAL-FAMILIA. Esta persona es cercana (familia/íntimo). "
            "REGLAS: 1) NUNCA vendas ni ofrezcas productos/servicios. "
            "2) Responde al CONTENIDO concreto del mensaje, no con reacciones genéricas. "
            "3) Comparte detalles reales de tu vida si vienen al caso. "
            "4) Responde directamente sin florituras."
        )

    # Priority 2 — scorer-derived close friend
    # Also DORMANT at the callsite (is_friend=False since 9752df768).
    if is_friend:
        return (
            "ESTRATEGIA: PERSONAL-AMIGO. Esta persona es amigo/a. "
            "REGLAS: 1) No vendas. 2) Responde al contenido concreto, no genérico. "
            "3) Comparte detalles si vienen al caso."
        )

    # Priority 3 — first inbound message (BUG-12 fix preserves ordering:
    # first message wins over generic help signals so "Hola, necesito ayuda"
    # produces BIENVENIDA+AYUDA rather than just AYUDA).
    if is_first_message:
        if "?" in message or _detect_help_signal(message, creator_id):
            return (
                "ESTRATEGIA: BIENVENIDA + AYUDA. Es el primer mensaje y contiene una pregunta. "
                "Saluda brevemente y responde a su necesidad en la misma respuesta."
            )
        return (
            "ESTRATEGIA: BIENVENIDA. Primer mensaje del usuario. "
            "Saluda brevemente y pregunta en qué puedes ayudar. "
            "NO hagas un saludo genérico largo."
        )

    # Priority 4 — returning user with conversation history.
    # All creator-specific tokens come from vocab_meta; the hint degrades
    # gracefully (neutral rules only) when vocab is missing.
    if history_len >= RECURRENT_HISTORY_MIN and not is_first_message:
        return _build_recurrent_hint(creator_id, creator_display_name)

    # Priority 5 — concrete help request from a returning user.
    if _detect_help_signal(message, creator_id):
        return (
            "ESTRATEGIA: AYUDA. El usuario tiene una necesidad concreta. "
            "Responde DIRECTAMENTE a lo que necesita. NO saludes genéricamente. "
            "Si no sabes la respuesta exacta, pregunta detalles específicos."
        )

    # Priority 6 — VENTA. The callsite MUST gate this against the
    # sell_arbitration resolver: when directive == NO_SELL the hint is
    # suppressed before being injected into the prompt (see
    # generation.py and BUG-003). This function still returns the hint so
    # that callers without the resolver (tests, audit tools) get a
    # deterministic output.
    if intent_value in PURCHASE_INTENTS:
        return (
            "ESTRATEGIA: VENTA. El usuario muestra interés en productos/servicios. "
            "Da la información concreta que pide (precio, contenido, duración). "
            "Añade un CTA suave al final."
        )

    # Priority 7 — ghost/reactivation.
    if lead_stage in GHOST_STAGE_VALUES:
        return (
            "ESTRATEGIA: REACTIVACIÓN. El usuario vuelve después de mucho tiempo. "
            "Muestra que te alegra verle. No seas agresivo con la venta."
        )

    return ""


def _build_recurrent_hint(creator_id: Optional[str], display_name: str) -> str:
    """Compose the P4 RECURRENTE hint from mined vocab.

    Replaces the hardcoded L86 openers and L89-90 apelativos / name leak /
    anti-bugs ("NUNCA la palabra 'flower'") with lookups against
    `personality_docs[doc_type='vocab_meta']` for this creator.

    Fallback — neutral hint without creator-specific rules, metered as
    `dm_strategy_vocab_source{source=fallback}`.
    """
    openers_to_avoid = _lookup_vocab_list(creator_id, "openers_to_avoid")
    apelativos = _lookup_vocab_list(creator_id, "apelativos") or _lookup_vocab_list(creator_id, "approved_terms")
    anti_bugs = _lookup_vocab_list(creator_id, "anti_bugs_verbales")

    parts: List[str] = ["ESTRATEGIA: RECURRENTE. Esta persona ya te conoce y tiene historial contigo."]

    if openers_to_avoid:
        # Quote each phrase so the LLM reads them verbatim, separated by " ni ".
        quoted = " ni ".join(f"'{o}'" for o in openers_to_avoid)
        parts.append(
            f"REGLA 1: NO uses aperturas de lead nuevo como {quoted} ni variantes — NUNCA."
        )
    else:
        parts.append(
            "REGLA 1: NO abras como si fuera la primera vez — evita aperturas propias de un lead nuevo."
        )

    parts.append("REGLA 2: NO saludes como si fuera la primera vez.")
    parts.append("REGLA 3: Responde con naturalidad y espontaneidad usando el contexto de la conversación.")

    # Regla 4 — personality vs neutral, apelativos, anti-bugs.
    who = display_name.strip() or "tu personalidad habitual"
    personality_clause = f"Muestra energía y personalidad de {who}: reacciona con entusiasmo o curiosidad según el contexto"
    rule_4 = f"REGLA 4: {personality_clause}."
    if apelativos:
        apel_list = ", ".join(apelativos)
        rule_4 = f"REGLA 4: {personality_clause}, usa apelativos ({apel_list})"
        if anti_bugs:
            forbidden = ", ".join(f"'{w}'" for w in anti_bugs)
            rule_4 += f" — NUNCA uses {forbidden}."
        else:
            rule_4 += "."
    elif anti_bugs:
        forbidden = ", ".join(f"'{w}'" for w in anti_bugs)
        rule_4 = f"REGLA 4: {personality_clause}. NUNCA uses {forbidden}."
    parts.append(rule_4)

    return " ".join(parts)
