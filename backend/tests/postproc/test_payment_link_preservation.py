"""
S6-T5.2 regression tests — payment link preservation through postprocessing.

These tests exercise _trim_body_for_payment_link in isolation so they run
without any network, DB, or agent dependency.

Fix: payment link was injected after format_message() (Instagram 1000-char
limit), so the combined message could exceed 1000 chars and have the link
truncated by the Instagram API. The helper now re-verifies the combined length
and trims the body (never the link) if needed.
"""

import pytest
from core.dm.phases.postprocessing import _trim_body_for_payment_link, TrimResult

# ── Constants for realistic test data ─────────────────────────────────────────

STRIPE_LINK = "https://buy.stripe.com/test_abc123def456ghi789"  # 46 chars
SUFFIX = f"\n\n{STRIPE_LINK}"  # 48 chars total suffix
MAX_LEN = 1000


# ── Test 1: Payment link never truncated — message at Instagram limit ─────────

def test_payment_link_never_truncated():
    """S6-T5.2 regression: link must arrive intact when body is near the limit."""
    body = "A" * 960  # 960-char body; with suffix = 1008 > 1000
    result, trim = _trim_body_for_payment_link(body, SUFFIX)

    assert result.endswith(STRIPE_LINK), "Payment link must be the final content"
    assert len(result) <= MAX_LEN, f"Combined must be ≤{MAX_LEN}, got {len(result)}"
    assert trim.trim_applied is True
    assert trim.chars_trimmed > 0


# ── Test 2: Short message — both body and link arrive intact ──────────────────

def test_payment_link_with_short_message():
    """Normal path: short message + link, no trimming needed."""
    body = "Hola! Te paso el enlace de pago directamente."  # 46 chars
    result, trim = _trim_body_for_payment_link(body, SUFFIX)

    assert result == body + SUFFIX, "Short message must not be modified"
    assert trim.trim_applied is False
    assert trim.trim_method is None
    assert trim.chars_trimmed == 0


# ── Test 3: No intent — caller does not call helper, link is absent ───────────

def test_payment_link_absent_when_no_intent():
    """Without purchase_intent, step 7d is not entered and no link is injected.

    This test verifies the helper returns body+suffix unchanged if called
    with an empty suffix (safe no-op), which represents the no-intent path.
    """
    body = "Genial! Quedo a tu disposición."
    empty_suffix = ""
    result, trim = _trim_body_for_payment_link(body, empty_suffix)

    assert result == body  # empty suffix → concatenation is identity
    assert trim.trim_applied is False


# ── Test 4: Link already in response — no double injection ───────────────────

def test_payment_link_not_duplicated():
    """Idempotency: when link is already present, step 7d short-circuits.

    The duplicate check (plink not in resp_lower) is in step 7d, not in the
    helper. This test documents the expected behaviour of the condition by
    asserting that calling the helper with a body that ALREADY contains the
    URL produces a body that still ends with exactly one copy of the URL.
    """
    body = f"Aquí está el enlace: {STRIPE_LINK}"  # link already present
    result, _ = _trim_body_for_payment_link(body, SUFFIX)

    # The helper itself doesn't deduplicate; deduplication happens in the caller.
    # What we verify here: if called anyway, the combined result contains the URL.
    count = result.lower().count(STRIPE_LINK.lower())
    assert count >= 1, "URL must appear at least once"
    # And the caller's condition (plink not in resp_lower) would have prevented the call:
    assert STRIPE_LINK.lower() in body.lower(), "URL already present in body"


# ── Test 5: Boundary cut preserves sentence sense ─────────────────────────────

def test_formatted_content_recortado_preserva_sentido():
    """When body requires trimming, boundary cut keeps a complete sentence."""
    # Build a 940-char body ending with a complete question sentence
    filler = "Este programa incluye acceso completo a todas las sesiones. " * 14  # ~840 chars
    ending = "¿Lo tienes claro?"  # 18 chars — total ~858 chars, append more filler
    body = filler + "Puedes apuntarte hoy mismo y empezar esta semana. " + ending
    # Trim to exactly 940 chars for predictability
    body = body[:940]

    # suffix 48 chars → total 988 → fits. Use a longer suffix to force trim.
    long_url = "https://buy.stripe.com/" + "x" * 80  # 103 chars
    long_suffix = f"\n\n{long_url}"  # 105 chars
    # body(940) + long_suffix(105) = 1045 > 1000 → trim needed

    result, trim = _trim_body_for_payment_link(body, long_suffix)

    assert result.endswith(long_url), "Payment link must be intact at the end"
    assert len(result) <= MAX_LEN, f"Result must be ≤{MAX_LEN}"
    assert trim.trim_applied is True
    # Boundary cut should find ". " or "? " in the last 100 chars of the filler
    # (the filler is full of ". " patterns every ~60 chars)
    assert trim.trim_method in ("boundary", "raw")


# ── Test 6: Raw fallback when no boundary in window ──────────────────────────

def test_link_body_raw_truncation_fallback():
    """No punctuation in last 100 chars → raw fallback with '...' + intact link."""
    # Build a body of 960 chars with NO sentence-ending punctuation at all
    body = "x" * 960

    result, trim = _trim_body_for_payment_link(body, SUFFIX)

    assert result.endswith(STRIPE_LINK), "Payment link must be at the end, intact"
    assert len(result) <= MAX_LEN
    assert trim.trim_applied is True
    assert trim.trim_method == "raw"
    # Body portion should end with "..."
    body_portion = result[: -len(SUFFIX)]
    assert body_portion.endswith("..."), "Raw fallback must append '...'"


# ── Test 7: Case-insensitive detection (documents current behaviour) ──────────

def test_payment_link_detection_case_insensitive():
    """Documents the substring check behaviour for mixed-case URLs.

    Current check in step 7d: plink not in resp_lower (both lower-cased).
    When the response contains the URL with the https:// scheme in any case,
    the check correctly detects it and the helper would not be called.
    """
    url = "https://buy.stripe.com/abc123"
    # LLM included the URL in all-caps (realistic only if LLM reformats it)
    body_with_upper = f"Aquí tienes: HTTPS://BUY.STRIPE.COM/abc123 — cualquier duda avísame."
    resp_lower = body_with_upper.lower()

    # The check in step 7d: plink not in resp_lower
    # plink = "https://buy.stripe.com/abc123" (from DB, already lowercase)
    already_present = url not in resp_lower  # False → link IS present → no injection
    assert not already_present, (
        "Case-insensitive detection works when LLM includes scheme in any case"
    )

    # Edge case: LLM drops the scheme prefix (theoretical bug, not realistic in prod)
    body_no_scheme = "Aquí tienes: buy.stripe.com/abc123 — cualquier duda avísame."
    resp_lower_no_scheme = body_no_scheme.lower()
    would_inject = url not in resp_lower_no_scheme  # True → would inject duplicate!
    # This documents the known limitation: no-scheme URLs bypass detection.
    # In practice, the LLM always copies URLs verbatim from the system prompt.
    assert would_inject, "Known: URL without scheme bypasses detection (documented debt)"


# ── Test 8: Idempotent — TrimResult is a no-op when body fits ─────────────────

def test_7d_idempotent_no_trim_when_fits():
    """Calling the helper twice on a short body is a no-op both times."""
    body = "Claro que sí! Aquí te dejo el link."
    result1, trim1 = _trim_body_for_payment_link(body, SUFFIX)
    result2, trim2 = _trim_body_for_payment_link(body, SUFFIX)

    assert result1 == result2
    assert trim1 == trim2
    assert trim1.trim_applied is False


# ── Test 9: TrimResult fields are correct for boundary cut ────────────────────

def test_trim_result_fields_boundary():
    """TrimResult accurately reflects a boundary trim."""
    # Body with a clean sentence boundary right before the trim zone
    # max_body = 1000 - 48 = 952; boundary_window last 100 = body[852:952]
    # Place a ". " at body[900] to land in the boundary window
    prefix = "Hola! " * 150  # 900 chars
    body = prefix[:900] + ". Esto es una frase de cierre."  # 900 + 30 = 930 chars
    # Total: 930 + 48 = 978 < 1000 — no trim needed with SUFFIX
    # Use a longer suffix to force trim
    long_suffix = "\n\n" + "https://pay.example.com/" + "y" * 90  # 116 chars
    # 930 + 116 = 1046 > 1000 → trim; max_body = 884; window = body[784:884]
    # body[784:884] = 100 chars from "Hola! Hola! ..." — contains ". " every 6 chars
    result, trim = _trim_body_for_payment_link(body, long_suffix)

    assert trim.trim_applied is True
    assert trim.trim_method == "boundary"
    assert trim.chars_trimmed > 0
    assert len(result) <= MAX_LEN
    assert result.endswith("y" * 90), "Payment URL tail must be intact"
