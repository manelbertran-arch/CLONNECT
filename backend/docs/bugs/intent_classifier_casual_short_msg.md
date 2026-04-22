# BUG: services.IntentClassifier — CASUAL short-message heuristic stomps specific intents

**Status:** Open — TODO, fix in separate PR  
**Discovered:** 2026-04-22, during fix/intent-dual-reconciliation  
**Severity:** Medium — sales and support signals lost for short messages  

---

## Description

`services/intent_service.py::IntentClassifier.classify()` contains a CASUAL catch-all at priority 3:

```python
# Casual: short messages with emojis, no substance
if len(msg) < 40 and "?" not in msg:
    emoji_count = len(re.findall(r"[\U00010000-\U0010ffff]|[☀-➿]", msg))
    if emoji_count >= 1 or len(msg) < 15:
        return Intent.CASUAL
```

The condition `len(msg) < 15` fires for any message under 15 characters that has no `?`. This runs **after** specific pattern checks, but specific patterns for support (`SUPPORT_PATTERNS`) and interest (`INTEREST_SOFT_PATTERNS`) do not include bare short forms. As a result, valid business-intent messages with < 15 chars fall through to CASUAL.

## Affected messages (confirmed)

| Message | len | Expected | Actual |
|---------|-----|----------|--------|
| `"lo necesito"` | 11 | `interest_strong` | `casual` |
| `"me interesa"` | 11 | `interest_soft` | `casual` |
| `"info"` | 4 | `interest_soft` | `casual` |
| `"no funciona"` | 11 | `support` | `casual` |
| `"error"` | 5 | `support` | `casual` |
| `"ayuda"` | 5 | `support` | `casual` |
| `"no me deja"` | 10 | `support` | `casual` |
| `"demasiado"` | 9 | `objection` | `casual` |
| `"ahora no"` | 8 | `objection_time` | `casual` |
| `"qué tiene"` | 9 | `product_question` | `casual` |
| `"cuanto dura"` | 11 | `product_question` | `casual` |

## Root cause

Two issues:
1. `SUPPORT_PATTERNS` only contains multi-word forms (`"no me funciona el acceso"`, `"no funciona el acceso"`) but NOT bare `"no funciona"`, `"error"`, `"ayuda"`.
2. The CASUAL short-message heuristic (`len < 15`) runs as an unconditional catch-all that never had access to whether a more-specific pattern was already checked.

## Fix (for separate PR)

Option 1 — Add bare short forms to `SUPPORT_PATTERNS` and `INTEREST_SOFT_PATTERNS`:
```python
SUPPORT_PATTERNS = [
    "no funciona", "error", "ayuda", "no me deja",  # ADD
    "no me funciona el acceso", ...
]
INTEREST_SOFT_PATTERNS = [
    "me interesa", "info",  # ADD
    "suena interesante", ...
]
```

Option 2 — Guard CASUAL heuristic with a pre-check:
```python
_already_matched_specific = any(
    any(p in msg for p in patterns)
    for patterns in [self.SUPPORT_PATTERNS, self.INTEREST_SOFT_PATTERNS,
                     self.OBJECTION_PRICE_PATTERNS, self.OBJECTION_TIME_PATTERNS, ...]
)
if not _already_matched_specific and len(msg) < 40 and "?" not in msg:
    ...
```

Option 1 is simpler and more explicit. Option 2 is more defensive.

## Impact

- `dm_history_service.py:330` — scoring misses support signals for short messages (currently `classify_intent_simple` catches these correctly because it has bare `"no funciona"` etc.)
- Future `SalesArbiter.intent_type` input will miss support/objection signals for short-form messages

## DO NOT fix in fix/intent-dual-reconciliation

The reconciliation PR (`fix/intent-dual-reconciliation`) makes `classify_intent_simple()` delegate to `services.IntentClassifier`. Fixing the CASUAL bug in the same commit would conflate two distinct issues and make rollback harder. Fix in a follow-up PR tagged `intent-classifier-v2`.
