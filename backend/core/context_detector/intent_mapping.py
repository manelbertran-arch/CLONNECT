"""
Intent mapping tables — fix/intent-dual-reconciliation.

services.IntentClassifier is the canonical intent source for all production paths.
These tables translate its rich output to legacy representations used by other modules.

Tabla B (SVC_TO_CORE_INTENT): services.Intent → core.intent_classifier.Intent
  Used by: core/context_detector/orchestration.py (DetectedContext.intent)

Tabla A (SVC_TO_LEGACY_STR): services.Intent → legacy 7-string
  Ready for: core/dm_history_service.py — migration BLOCKED pending CASUAL bug fix.
  See: docs/bugs/intent_classifier_casual_short_msg.md

dm_history_service.py still uses classify_intent_simple() (deprecated) until that fix lands.
"""

from core.intent_classifier import Intent as CoreIntent
from services.intent_service import Intent as SvcIntent

# ---------------------------------------------------------------------------
# Tabla B — services.Intent → core.intent_classifier.Intent
# ---------------------------------------------------------------------------
# Notes on non-obvious mappings:
#   PRICING → INTEREST_STRONG  : price questions signal buyer intent (matches legacy "purchase" → INTEREST_STRONG)
#   BOOKING → INTEREST_STRONG  : "reservar"/"agendar" already mapped to interest_strong in classify_intent_simple
#   LEAD_MAGNET → INTEREST_SOFT: requesting a free resource is a soft interest signal
#   ESCALATION → ESCALATION    : BEHAVIOR CHANGE vs legacy (legacy returned OTHER for most escalation patterns)
#                                 Only affects DetectedContext.context_notes (informational, not routing).
#   FEEDBACK_POSITIVE/SPAM      : not reachable from svc — core values stay unreachable (no regression vs legacy)
SVC_TO_CORE_INTENT: dict = {
    SvcIntent.GREETING:               CoreIntent.GREETING,
    SvcIntent.GENERAL_CHAT:           CoreIntent.OTHER,
    SvcIntent.THANKS:                 CoreIntent.OTHER,
    SvcIntent.GOODBYE:                CoreIntent.OTHER,
    SvcIntent.INTEREST_SOFT:          CoreIntent.INTEREST_SOFT,
    SvcIntent.INTEREST_STRONG:        CoreIntent.INTEREST_STRONG,
    SvcIntent.PURCHASE_INTENT:        CoreIntent.INTEREST_STRONG,
    SvcIntent.ACKNOWLEDGMENT:         CoreIntent.OTHER,
    SvcIntent.CORRECTION:             CoreIntent.OTHER,
    SvcIntent.OBJECTION_PRICE:        CoreIntent.OBJECTION,
    SvcIntent.OBJECTION_TIME:         CoreIntent.OBJECTION,
    SvcIntent.OBJECTION_DOUBT:        CoreIntent.OBJECTION,
    SvcIntent.OBJECTION_LATER:        CoreIntent.OBJECTION,
    SvcIntent.OBJECTION_WORKS:        CoreIntent.OBJECTION,
    SvcIntent.OBJECTION_NOT_FOR_ME:   CoreIntent.OBJECTION,
    SvcIntent.OBJECTION_COMPLICATED:  CoreIntent.OBJECTION,
    SvcIntent.OBJECTION_ALREADY_HAVE: CoreIntent.OBJECTION,
    SvcIntent.QUESTION_PRODUCT:       CoreIntent.QUESTION_PRODUCT,
    SvcIntent.QUESTION_GENERAL:       CoreIntent.QUESTION_GENERAL,
    SvcIntent.PRODUCT_QUESTION:       CoreIntent.QUESTION_PRODUCT,   # alias
    SvcIntent.LEAD_MAGNET:            CoreIntent.INTEREST_SOFT,
    SvcIntent.BOOKING:                CoreIntent.INTEREST_STRONG,
    SvcIntent.SUPPORT:                CoreIntent.SUPPORT,
    SvcIntent.ESCALATION:             CoreIntent.ESCALATION,
    SvcIntent.PRICING:                CoreIntent.INTEREST_STRONG,
    SvcIntent.FEEDBACK_NEGATIVE:      CoreIntent.FEEDBACK_NEGATIVE,
    SvcIntent.HUMOR:                  CoreIntent.OTHER,
    SvcIntent.REACTION:               CoreIntent.OTHER,
    SvcIntent.ENCOURAGEMENT:          CoreIntent.OTHER,
    SvcIntent.CONTINUATION:           CoreIntent.OTHER,
    SvcIntent.CASUAL:                 CoreIntent.OTHER,
    SvcIntent.OTHER:                  CoreIntent.OTHER,
}

# ---------------------------------------------------------------------------
# Tabla A — services.Intent → legacy 7-string
# ---------------------------------------------------------------------------
# Ready for dm_history_service.py once CASUAL bug is fixed.
# ESCALATION maps to "other" because the legacy scoring has no escalation bucket.
SVC_TO_LEGACY_STR: dict = {
    SvcIntent.GREETING:               "greeting",
    SvcIntent.GENERAL_CHAT:           "other",
    SvcIntent.THANKS:                 "other",
    SvcIntent.GOODBYE:                "other",
    SvcIntent.INTEREST_SOFT:          "interest_soft",
    SvcIntent.INTEREST_STRONG:        "interest_strong",
    SvcIntent.PURCHASE_INTENT:        "interest_strong",
    SvcIntent.ACKNOWLEDGMENT:         "other",
    SvcIntent.CORRECTION:             "other",
    SvcIntent.OBJECTION_PRICE:        "objection",
    SvcIntent.OBJECTION_TIME:         "objection",
    SvcIntent.OBJECTION_DOUBT:        "objection",
    SvcIntent.OBJECTION_LATER:        "objection",
    SvcIntent.OBJECTION_WORKS:        "objection",
    SvcIntent.OBJECTION_NOT_FOR_ME:   "objection",
    SvcIntent.OBJECTION_COMPLICATED:  "objection",
    SvcIntent.OBJECTION_ALREADY_HAVE: "objection",
    SvcIntent.QUESTION_PRODUCT:       "question_product",
    SvcIntent.QUESTION_GENERAL:       "other",
    SvcIntent.PRODUCT_QUESTION:       "question_product",
    SvcIntent.LEAD_MAGNET:            "interest_soft",
    SvcIntent.BOOKING:                "interest_strong",
    SvcIntent.SUPPORT:                "support",
    SvcIntent.ESCALATION:             "other",
    SvcIntent.PRICING:                "purchase",
    SvcIntent.FEEDBACK_NEGATIVE:      "other",
    SvcIntent.HUMOR:                  "other",
    SvcIntent.REACTION:               "other",
    SvcIntent.ENCOURAGEMENT:          "other",
    SvcIntent.CONTINUATION:           "other",
    SvcIntent.CASUAL:                 "other",
    SvcIntent.OTHER:                  "other",
}


def svc_to_core_intent(svc_intent: SvcIntent) -> CoreIntent:
    """Map canonical services.Intent to core.intent_classifier.Intent (Tabla B)."""
    return SVC_TO_CORE_INTENT.get(svc_intent, CoreIntent.OTHER)
