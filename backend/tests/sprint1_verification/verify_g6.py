#!/usr/bin/env python3
"""Sprint 1 — G6 Truncation Recovery verification.

Method: Option A — mock generate_dm_response to return a truncated response
on the first call, then a complete response on the second call. Verify that:
  1. _detect_truncation() returns True on the first (truncated) response
  2. The retry fires with higher max_tokens
  3. The final result is the longer/complete response
  4. cognitive_metadata["truncation_recovery"] is set

We also exercise Option B: direct _detect_truncation() calls with realistic
truncated and complete responses derived from real Iris DM history.

Run with:
    python3 tests/sprint1_verification/verify_g6.py
"""

import sys
import os
import asyncio
import logging
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..', '..'))

# ── Capture log output ────────────────────────────────────────────────────────
captured_lines: list[str] = []

class CapturingHandler(logging.Handler):
    def emit(self, record):
        captured_lines.append(self.format(record))

_handler = CapturingHandler()
_handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
logging.getLogger().addHandler(_handler)
logging.getLogger().setLevel(logging.DEBUG)

# ─────────────────────────────────────────────────────────────────────────────

from core.dm.phases.generation import (
    _detect_truncation,
    MAX_TRUNCATION_RETRIES,
    TRUNCATION_TOKEN_MULTIPLIER,
    TRUNCATION_TOKEN_CAP,
)

print("=" * 65)
print("G6 VERIFICATION — Truncation Recovery")
print("=" * 65)

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name} — {detail}")
        failed += 1

# ─────────────────────────────────────────────────────────────────────────────
# PART 1: Option B — direct _detect_truncation() on realistic responses
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Part 1: _detect_truncation() with realistic responses ───")

# Real complete responses from Iris DM style
complete_responses = [
    "Hola!! Qué bien que te interese 💪",
    "El programa dura 8 semanas y es totalmente online. ¿Te cuento más?",
    "Genial! Mañana te mando el link de compra ❤",
    "Está disponible para todos los niveles, no te preocupes 😊",
    "Perfecto, cualquier duda me escribes.",
    "¡Buenísimo! Cuenta conmigo para lo que necesites!",
    "Vale, sin problema.",
    "Sí claro, te lo explico todo…",
    "Venga, te mando toda la info)",
    "De nada!! Un placer 🔥",
]

# Responses that are truncated (cut mid-word/sentence)
truncated_responses = [
    "Hola!! Qué bien que te interese, el programa tiene muchísimas cosas chulas como",
    "El precio del programa es de 97€ y lo que incluye es",
    "Mira, lo que más me gusta del programa es que está pensado para",
    "Genial! Pues entonces te",
    "La verdad es que muchas chicas ya han conseguido sus objet",
    "Si quieres puedo mandarte la info del progr",
]

print("\n  Complete responses (should NOT be truncated):")
for resp in complete_responses:
    result = _detect_truncation(resp)
    ok = not result  # we expect False (not truncated)
    check(f"  NOT truncated: '{resp[:40]}...'", ok,
          f"_detect_truncation returned {result}")

print("\n  Truncated responses (SHOULD be detected as truncated):")
for resp in truncated_responses:
    result = _detect_truncation(resp)
    check(f"  IS truncated: '{resp[:40]}...'", result,
          f"_detect_truncation returned {result}")

# ─────────────────────────────────────────────────────────────────────────────
# PART 2: Option A — mock generate_dm_response + retry loop
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Part 2: Retry loop with mocked generate_dm_response ────")

# We simulate the retry logic directly (without full phase_llm_generation)
# by replicating the retry block with a mock provider.
call_log = []  # records (call_n, max_tokens, response)

async def mock_generate(messages, max_tokens=100, temperature=0.7):
    """Mock provider: returns truncated on first call, complete on second."""
    call_n = len(call_log) + 1
    if call_n == 1:
        # Simulate: short max_tokens → response cut off
        content = "Hola!! El programa tiene much"   # truncated
    else:
        # Retry with more tokens → complete response
        content = "Hola!! El programa tiene muchísimas ventajas y lo puedes empezar cuando quieras 💪"
    call_log.append({"call_n": call_n, "max_tokens": max_tokens, "content": content})
    return {"content": content, "model": "gemini-flash-lite", "provider": "gemini", "latency_ms": 120}


async def run_retry_simulation():
    """Simulate the G6 retry block from generation.py."""
    _llm_max_tokens = 20   # artificially low → triggers truncation
    _llm_temperature = 0.7
    llm_messages = [{"role": "user", "content": "Hola, cuéntame del programa"}]
    cognitive_metadata = {}

    # First call
    llm_result = await mock_generate(llm_messages, max_tokens=_llm_max_tokens, temperature=_llm_temperature)

    # G6 retry block (mirror of generation.py)
    if llm_result and _detect_truncation(llm_result.get("content", "")):
        _best_result = llm_result
        _current_max = _llm_max_tokens
        for _retry_n in range(MAX_TRUNCATION_RETRIES):
            _new_max = min(
                int(_current_max * TRUNCATION_TOKEN_MULTIPLIER),
                _current_max + TRUNCATION_TOKEN_CAP,
            )
            logging.warning(
                "[TruncationRecovery] Truncated response detected (attempt %d/%d), "
                "retrying with max_tokens=%d",
                _retry_n + 1, MAX_TRUNCATION_RETRIES, _new_max,
            )
            try:
                _retry_result = await mock_generate(llm_messages, max_tokens=_new_max, temperature=_llm_temperature)
                if _retry_result:
                    _retry_len = len(_retry_result.get("content", ""))
                    _best_len = len(_best_result.get("content", ""))
                    if _retry_len > _best_len:
                        _best_result = _retry_result
                    if not _detect_truncation(_retry_result.get("content", "")):
                        _best_result = _retry_result
                        logging.info(
                            "[TruncationRecovery] Recovered on attempt %d (max_tokens=%d)",
                            _retry_n + 1, _new_max,
                        )
                        break
                _current_max = _new_max
            except Exception as e:
                logging.warning("[TruncationRecovery] Retry %d failed: %s", _retry_n + 1, e)
                break
        if _best_result is not llm_result:
            cognitive_metadata["truncation_recovery"] = True
        llm_result = _best_result

    return llm_result, cognitive_metadata, call_log[:]


print("\n  Running retry simulation (max_tokens=20 → truncation → retry)...")
final_result, metadata, calls = asyncio.run(run_retry_simulation())

print(f"\n  Calls made: {len(calls)}")
for c in calls:
    print(f"    call {c['call_n']}: max_tokens={c['max_tokens']} → '{c['content'][:60]}'")

# Assertions for Part 2
check("First call produced truncated response",
      _detect_truncation(calls[0]["content"]),
      f"content='{calls[0]['content']}'")

check("Retry fired (at least 2 calls total)", len(calls) >= 2,
      f"total calls={len(calls)}")

check("Retry used higher max_tokens than initial",
      calls[1]["max_tokens"] > calls[0]["max_tokens"],
      f"call1={calls[0]['max_tokens']} call2={calls[1]['max_tokens']}")

expected_new_max = min(
    int(20 * TRUNCATION_TOKEN_MULTIPLIER),
    20 + TRUNCATION_TOKEN_CAP,
)
check(f"Retry max_tokens = min(20*{TRUNCATION_TOKEN_MULTIPLIER}, 20+{TRUNCATION_TOKEN_CAP}) = {expected_new_max}",
      calls[1]["max_tokens"] == expected_new_max,
      f"got={calls[1]['max_tokens']}")

check("Final response is NOT truncated",
      not _detect_truncation(final_result.get("content", "")),
      f"content='{final_result.get('content', '')}'")

check("Final response is longer than initial truncated",
      len(final_result.get("content", "")) > len(calls[0]["content"]),
      f"initial={len(calls[0]['content'])} final={len(final_result.get('content',''))}")

check("cognitive_metadata['truncation_recovery'] set",
      metadata.get("truncation_recovery") is True,
      f"metadata={metadata}")

# Check log lines
recovery_logs = [l for l in captured_lines if "TruncationRecovery" in l]
check("[TruncationRecovery] log lines emitted", len(recovery_logs) >= 1,
      f"logs={recovery_logs}")

print(f"\n  [TruncationRecovery] log lines captured:")
for l in recovery_logs:
    print(f"    {l}")

# ── Constants sanity check ────────────────────────────────────────────────────
print("\n── Part 3: Constants ────────────────────────────────────────")
check(f"MAX_TRUNCATION_RETRIES={MAX_TRUNCATION_RETRIES} <= 2", MAX_TRUNCATION_RETRIES <= 2)
check(f"TRUNCATION_TOKEN_MULTIPLIER={TRUNCATION_TOKEN_MULTIPLIER} > 1.0", TRUNCATION_TOKEN_MULTIPLIER > 1.0)
check(f"TRUNCATION_TOKEN_CAP={TRUNCATION_TOKEN_CAP} > 0", TRUNCATION_TOKEN_CAP > 0)

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n── Summary ─────────────────────────────────────────────────")
print(f"  {passed} passed, {failed} failed")

# ── Write log file ─────────────────────────────────────────────────────────────
_dir = os.path.dirname(__file__)
with open(os.path.join(_dir, "g6_truncation_test.log"), "w") as f:
    f.write("# G6 — Truncation Recovery Verification\n")
    f.write(f"# Result: {'PASS' if failed == 0 else 'FAIL'}\n\n")
    f.write("## Part 1: _detect_truncation() with realistic Iris DM responses\n\n")
    f.write("### Complete responses (should NOT flag as truncated):\n")
    for r in complete_responses:
        f.write(f"  _detect_truncation('{r[:60]}') = {_detect_truncation(r)}\n")
    f.write("\n### Truncated responses (SHOULD be detected):\n")
    for r in truncated_responses:
        f.write(f"  _detect_truncation('{r[:60]}') = {_detect_truncation(r)}\n")
    f.write("\n## Part 2: Retry loop simulation\n\n")
    f.write(f"Initial max_tokens: {calls[0]['max_tokens']}\n")
    for c in calls:
        f.write(f"Call {c['call_n']}: max_tokens={c['max_tokens']}, content='{c['content']}'\n")
    f.write(f"\nFinal response: '{final_result.get('content', '')}'\n")
    f.write(f"cognitive_metadata: {metadata}\n\n")
    f.write("## Captured [TruncationRecovery] log lines:\n")
    for l in recovery_logs:
        f.write(f"  {l}\n")
    f.write("\n## Constants:\n")
    f.write(f"  MAX_TRUNCATION_RETRIES = {MAX_TRUNCATION_RETRIES}\n")
    f.write(f"  TRUNCATION_TOKEN_MULTIPLIER = {TRUNCATION_TOKEN_MULTIPLIER}\n")
    f.write(f"  TRUNCATION_TOKEN_CAP = {TRUNCATION_TOKEN_CAP}\n")

print(f"\n  Log written to tests/sprint1_verification/g6_truncation_test.log")
sys.exit(0 if failed == 0 else 1)
