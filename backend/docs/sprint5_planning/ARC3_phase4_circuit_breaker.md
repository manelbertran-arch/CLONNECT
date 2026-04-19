# ARC3 Phase 4 — CircuitBreaker

## Overview

Per-(creator, lead) circuit breaker that prevents infinite retry loops in the DM generation pipeline. After `MAX_CONSECUTIVE_FAILURES=3` hard failures for the same conversation, generation is blocked for `TRIP_COOLDOWN_SECONDS=60` and a soft fallback response is returned.

**Complementary to** the provider-level Gemini circuit breaker in `gemini_provider.py` (which skips a specific LLM provider). This breaker operates at the conversation level, regardless of provider.

---

## Architecture

```
phase_llm_generation()
        │
        ▼
  [pre-check]
  breaker.check(creator_id, lead_id)
        │
  False ──→ return LLMResponse(fallback_text)   ← BLOCKED
        │
  True  ──→ generate_dm_response()
               │
       Exception ──→ record_failure(LLM_5XX)
                      └──→ if threshold → TRIP + alert
               │
       result=None ──→ record_failure(EMPTY_RESPONSE)
       result<3ch  ──→ record_failure(RESPONSE_TOO_SHORT)
       result OK   ──→ record_success() → state cleared
```

### Key constants

| Constant | Value | Meaning |
|---|---|---|
| `MAX_CONSECUTIVE_FAILURES` | 3 | Failures before trip |
| `RESET_WINDOW_SECONDS` | 300 | TTL for state (auto-reset on idle) |
| `TRIP_COOLDOWN_SECONDS` | 60 | Block duration after trip |

### State backend

No Redis dependency. Uses `cachetools.TTLCache(maxsize=10_000, ttl=300)` in-process with a `threading.Lock` for thread safety. State auto-expires after `RESET_WINDOW_SECONDS` — an idle conversation gets a free reset.

---

## Failure taxonomy

```python
class FailureType(Enum):
    LLM_TIMEOUT         # Hard: asyncio.TimeoutError on generate_dm_response()
    LLM_5XX             # Hard: exception raised from provider
    CONTENT_FILTER      # Hard: provider refused content
    JSON_PARSE_ERROR    # Hard: structured output parse failure
    EMPTY_RESPONSE      # Soft: result is None or empty string
    RESPONSE_TOO_SHORT  # Soft: content < 3 chars
    LOOP_DETECTED       # Soft: response identical to previous turn
```

**HARD failures** always count. **SOFT failures** also count toward the threshold (by design — 3 empty responses is a clear problem).

**NOT failures**: emoji-only responses, responses outside length range (mutations handle those).

---

## Fallback responses (§2.4.3)

```python
FALLBACK_RESPONSES = {
    "default": "Ey, te respondo en un rato que ando liado/a 🙏",
    "es_long": "Mil perdones, se me está liando el día — te escribo ahorita con calma",
    "en":      "hey! i'll get back to you in a bit, bear with me 🙏",
}
```

Language detection is best-effort (defaults to `"default"` / Spanish). To extend, override `_detect_language()` in `CircuitBreaker` and add a DB lookup.

---

## Feature flag

```python
# core/feature_flags.py
enable_circuit_breaker: bool  # env ENABLE_CIRCUIT_BREAKER, default True
```

Default `ON` — this is a safety net, not an opt-in. Disable only in emergency with `ENABLE_CIRCUIT_BREAKER=false`.

**Automatic bypasses** (flag not needed):
- `CCEE_NO_FALLBACK=1` — evaluation mode, breaker skipped
- `DISABLE_FALLBACK=true` — test mode, breaker skipped

---

## Integration points

### Current: `core/dm/phases/generation.py`

`phase_llm_generation()` is the only active integration point. Added:
1. Pre-check before any LLM call (lines ~476-505)
2. Exception handler wrapping `generate_dm_response()` → records `LLM_5XX`
3. Post-call check on result quality → records `EMPTY_RESPONSE` / `RESPONSE_TOO_SHORT` / `record_success()`
4. ARC5 metadata: `circuit_breaker_tripped` field updated from `cognitive_metadata`

### Future: adding new entry points

If a new generation path is added (e.g., copilot async, bulk reply), wire it the same way:

```python
from core.generation.circuit_breaker import get_circuit_breaker, FailureType

breaker = get_circuit_breaker()
if not await breaker.check(creator_id, lead_id):
    return await breaker.get_fallback_response(creator_id, lead_id)
try:
    result = await my_llm_call(...)
    if not result:
        await breaker.record_failure(creator_id, lead_id, FailureType.EMPTY_RESPONSE)
        return await breaker.get_fallback_response(creator_id, lead_id)
    await breaker.record_success(creator_id, lead_id)
    return result
except Exception:
    await breaker.record_failure(creator_id, lead_id, FailureType.LLM_5XX)
    raise
```

---

## Alerting

On trip, `dispatch_fire_and_forget()` from `core/security/alerting.py` fires a background task:

```python
event_type = "generation_circuit_tripped"
severity   = "WARNING"
metadata   = {
    "failure_type": "llm_timeout",
    "max_consecutive_failures": 3,
    "trip_cooldown_seconds": 60,
}
```

Alert is rate-limited by the existing 60s dedup window in `alerting.py`. One alert per trip per (creator, lead) pair per minute.

---

## Staging validation

To simulate 3 consecutive failures in staging:

```python
# python3 -c "..."
import asyncio
from core.generation.circuit_breaker import get_circuit_breaker, FailureType

async def main():
    b = get_circuit_breaker()
    for i in range(3):
        await b.record_failure("iris_bertran", "999000111", FailureType.LLM_TIMEOUT)
        print(f"failure {i+1}: check={await b.check('iris_bertran', '999000111')}")
    fallback = await b.get_fallback_response("iris_bertran", "999000111")
    print(f"fallback: {fallback!r}")

asyncio.run(main())
```

Expected output:
```
failure 1: check=True
failure 2: check=True
failure 3: check=False
fallback: 'Ey, te respondo en un rato que ando liado/a 🙏'
```

To verify reset after success:
```python
await b.record_success("iris_bertran", "999000111")
assert await b.check("iris_bertran", "999000111") is True
```

---

## Files changed

| File | Change |
|---|---|
| `core/generation/circuit_breaker.py` | New: CircuitBreaker implementation |
| `core/feature_flags.py` | Added `enable_circuit_breaker` flag |
| `core/dm/phases/generation.py` | Integration: pre-check + record_failure/success |
| `tests/circuit_breaker/test_circuit_breaker.py` | 22 unit tests |
| `tests/integration/test_circuit_breaker_integration.py` | 7 integration tests |
| `docs/sprint5_planning/ARC3_phase4_circuit_breaker.md` | This file |
