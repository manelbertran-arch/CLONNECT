"""Tests for Sprint top-6 forensic-ligero activations (Few-Shot Injection
and Commitment Tracker).

Few-Shot: verifies the flag-guard + metric emission around the existing
`get_few_shot_section` callsite in context.py.

Commitment Tracker: verifies (a) flag gate, (b) per-creator vocab_meta
override of hardcoded fallback patterns, (c) metric emission of source.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ─────────────────────────────────────────────────────────────────────────────
# Few-Shot Injection (3 tests)
# ─────────────────────────────────────────────────────────────────────────────

def _exec_few_shot_branch(context_mod, *, flag_on: bool, has_calibration: bool,
                          section_returned: str, creator_id: str = "iris_bertran",
                          intent_value: str = "VENTA") -> tuple[str, str, int]:
    """Replay of the few-shot guarded block from context.py. Returns
    (section_text, outcome_label, examples_found).

    Counter mirrors the production logic: one ``Follower: `` line per example
    in the section emitted by ``calibration_loader.get_few_shot_section``.
    """
    few_shot_section = ""
    outcome = "empty"
    examples = 0

    calibration = {"few_shot_examples": [{"user": "x", "assistant": "y"}]} if has_calibration else None

    if flag_on and calibration:
        _fs_examples_found = 0
        _fs_outcome = "empty"
        try:
            few_shot_section = section_returned
            if few_shot_section:
                # Route through the production helper so a regression of the
                # inline counter at context.py:1386 fails this replay too.
                _fs_examples_found = context_mod._count_few_shot_examples(few_shot_section)
                _fs_outcome = "injected"
        except Exception:
            _fs_outcome = "error"
        context_mod.emit_metric("few_shot_injection_total",
                                creator_id=creator_id,
                                intent=intent_value,
                                outcome=_fs_outcome)
        if _fs_examples_found:
            context_mod.emit_metric("few_shot_examples_count",
                                    _fs_examples_found,
                                    creator_id=creator_id)
        outcome = _fs_outcome
        examples = _fs_examples_found
    elif calibration:
        context_mod.emit_metric("few_shot_injection_total",
                                creator_id=creator_id,
                                intent=intent_value,
                                outcome="disabled")
        outcome = "disabled"

    return few_shot_section, outcome, examples


def test_few_shot_flag_on_with_section_emits_injected():
    from core.dm.phases import context as context_mod

    emitted: list[tuple[str, dict, object]] = []

    def _fake_emit(name, value=1, **labels):
        emitted.append((name, labels, value))

    real_section = (
        "=== EJEMPLOS REALES DE COMO RESPONDES ===\n"
        "Follower: hola\nTu: holaaa\n\n"
        "Follower: gracias\nTu: grax\n\n"
        "Responde de forma breve y natural, como en los ejemplos.\n"
        "=== FIN EJEMPLOS ==="
    )
    with patch.object(context_mod, "emit_metric", side_effect=_fake_emit):
        section, outcome, examples = _exec_few_shot_branch(
            context_mod, flag_on=True, has_calibration=True,
            section_returned=real_section,
        )

    assert outcome == "injected"
    assert examples == 2  # one "Follower: " line per example
    names = [n for n, _, _ in emitted]
    assert "few_shot_injection_total" in names
    assert "few_shot_examples_count" in names


def test_few_shot_flag_off_but_calibration_present_emits_disabled():
    from core.dm.phases import context as context_mod

    emitted: list[tuple[str, dict]] = []

    def _fake_emit(name, value=1, **labels):
        emitted.append((name, labels))

    with patch.object(context_mod, "emit_metric", side_effect=_fake_emit):
        section, outcome, examples = _exec_few_shot_branch(
            context_mod, flag_on=False, has_calibration=True,
            section_returned="<ignored>",
        )

    assert section == ""
    assert outcome == "disabled"
    outcomes = [lbl.get("outcome") for n, lbl in emitted if n == "few_shot_injection_total"]
    assert outcomes == ["disabled"]


def test_few_shot_flag_on_but_no_calibration_emits_nothing():
    """If the creator has no calibration pack, the branch must be a no-op —
    no injection AND no disabled metric (we skip creators without data)."""
    from core.dm.phases import context as context_mod

    emitted: list[tuple[str, dict]] = []

    def _fake_emit(name, value=1, **labels):
        emitted.append((name, labels))

    with patch.object(context_mod, "emit_metric", side_effect=_fake_emit):
        section, outcome, examples = _exec_few_shot_branch(
            context_mod, flag_on=True, has_calibration=False,
            section_returned="<ignored>",
        )

    assert section == ""
    assert outcome == "empty"
    assert emitted == []


def test_few_shot_get_few_shot_section_empty_pool():
    """Empty calibration dict → empty string returned, no crash."""
    from services.calibration_loader import get_few_shot_section
    assert get_few_shot_section({}) == ""
    assert get_few_shot_section({"few_shot_examples": []}) == ""


def test_few_shot_language_filter_same_language():
    """Language filter retains only same-lang + 'mixto' examples when enough remain."""
    from services.calibration_loader import get_few_shot_section

    pool = [
        {"user_message": f"m{i}", "response": f"r{i}", "language": "es", "context": "general"}
        for i in range(10)
    ]
    pool += [
        {"user_message": f"fr{i}", "response": f"fr{i}", "language": "fr", "context": "general"}
        for i in range(10)
    ]
    section = get_few_shot_section(
        {"few_shot_examples": pool},
        max_examples=5,
        lead_language="es",
    )
    # All rendered examples must be in ES (no French text leaked into output)
    assert "fr" not in section.lower().replace("for", "").replace("from", "")
    assert section.count("Follower:") <= 5


def test_few_shot_language_filter_code_switching_full_pool():
    """Code-switching tag ('ca-es') disables language filter; pool stays full."""
    from services.calibration_loader import get_few_shot_section

    pool = [
        {"user_message": f"m{i}", "response": f"r{i}", "language": "es", "context": "general"}
        for i in range(3)
    ] + [
        {"user_message": f"c{i}", "response": f"c{i}", "language": "ca", "context": "general"}
        for i in range(3)
    ]
    section = get_few_shot_section(
        {"few_shot_examples": pool},
        max_examples=5,
        lead_language="ca-es",
    )
    # With full pool available, the 5 rendered examples may mix ca + es.
    assert section.count("Follower:") <= 5
    assert section.startswith("=== EJEMPLOS REALES")


def test_few_shot_stratified_respects_k_cap():
    """Render never emits more than max_examples example pairs, even with many intents."""
    from services.calibration_loader import get_few_shot_section

    intents = ["VENTA", "BIENVENIDA", "CONSULTA", "OBJECION", "DESPEDIDA", "AGRADECIMIENTO"]
    pool = []
    for idx, intent in enumerate(intents):
        pool.extend([
            {"user_message": f"{intent}_m{i}", "response": f"{intent}_r{i}",
             "language": "es", "context": intent, "intent": intent}
            for i in range(3)
        ])
    section = get_few_shot_section(
        {"few_shot_examples": pool},
        max_examples=5,
        lead_language="es",
        detected_intent="VENTA",
    )
    assert section.count("Follower:") == 5, \
        f"Expected exactly 5 examples, got {section.count('Follower:')}"


def test_few_shot_intent_stratified_prioritises_matches():
    """When detected_intent is set, at least one VENTA example must appear in the 5 selected."""
    from services.calibration_loader import get_few_shot_section

    venta_pool = [
        {"user_message": f"venta_q{i}", "response": f"venta_a{i}",
         "language": "es", "context": "VENTA", "intent": "VENTA"}
        for i in range(3)
    ]
    other_pool = [
        {"user_message": f"other_q{i}", "response": f"other_a{i}",
         "language": "es", "context": "BIENVENIDA", "intent": "BIENVENIDA"}
        for i in range(8)
    ]
    section = get_few_shot_section(
        {"few_shot_examples": venta_pool + other_pool},
        max_examples=5,
        lead_language="es",
        detected_intent="VENTA",
    )
    # At least one VENTA example must have been selected (intent-stratified spec)
    assert "venta_q" in section, (
        f"Expected at least one VENTA example in output, got:\n{section}"
    )


def test_few_shot_detects_ca_es_code_switching():
    """detect_message_language must return 'ca-es' for mixed ca+es short message."""
    from services.calibration_loader import detect_message_language

    # Pure Spanish markers
    assert detect_message_language("tengo gracias entonces mucho") == "es"
    # Pure Catalan markers
    assert detect_message_language("tinc gràcies però molt doncs") == "ca"
    # Mixed ca + es
    assert detect_message_language("tinc mucho però necesito gràcies") == "ca-es"


# ─────────────────────────────────────────────────────────────────────────────
# Commitment Tracker (3 tests)
# ─────────────────────────────────────────────────────────────────────────────

def test_commitment_tracker_flag_off_returns_empty():
    """When commitment_tracking is OFF, detect_commitments_regex returns []
    regardless of message content (no DB hit, no metric)."""
    from services import commitment_tracker as ct

    fake_flags = MagicMock()
    fake_flags.commitment_tracking = False

    with patch.object(ct, "flags", fake_flags), \
         patch.object(ct, "emit_metric") as mock_emit:
        result = ct.detect_commitments_regex(
            "te envío el link mañana",
            sender="assistant",
            creator_id="iris_bertran",
        )

    assert result == []
    mock_emit.assert_not_called()


def test_commitment_tracker_hardcoded_fallback_source():
    """Without creator_id, the cold-start Spanish fallback is used and
    source='hardcoded_fallback' is emitted."""
    from services import commitment_tracker as ct

    fake_flags = MagicMock()
    fake_flags.commitment_tracking = True

    emitted: list[tuple[str, dict]] = []

    def _fake_emit(name, value=1, **labels):
        emitted.append((name, labels))

    with patch.object(ct, "flags", fake_flags), \
         patch.object(ct, "emit_metric", side_effect=_fake_emit):
        result = ct.detect_commitments_regex(
            "te envío el link mañana",
            sender="assistant",
            creator_id=None,
        )

    assert result, "Expected at least one detection against the Spanish fallback"
    sources = [lbl.get("source") for n, lbl in emitted if n == "commitment_tracker_patterns_source"]
    assert sources == ["hardcoded_fallback"]

    # Check one commitment detected of type=delivery
    types = {r["commitment_type"] for r in result}
    assert "delivery" in types


def test_few_shot_inline_counter_matches_real_get_few_shot_section_format():
    """Regression: the inline counter at context.py:1386 reads
    ``few_shot_section.count("Follower: ")``. This must equal the number of
    examples actually rendered by ``get_few_shot_section``. Earlier code used
    ``count("\\n- ")`` — a bullet format the loader has never produced — so
    the metric always emitted 1 regardless of k.

    Two-layer guard:
      1. Formatter contract: real output has 5 ``Follower: `` lines and 0 bullets.
      2. End-to-end pipeline: feed the real section through the production
         counter logic and assert the metric value equals 5.
    """
    from core.dm.phases import context as context_mod
    from services.calibration_loader import get_few_shot_section

    pool = [
        {"user_message": f"q{i}", "response": f"a{i}",
         "language": "es", "context": "VENTA", "intent": "VENTA"}
        for i in range(10)
    ]
    section = get_few_shot_section(
        {"few_shot_examples": pool},
        max_examples=5,
        lead_language="es",
        detected_intent="VENTA",
    )
    assert section, "Formatter must return a non-empty section when pool >= max_examples"
    assert section.count("Follower: ") == 5, (
        f"Inline counter contract violated: expected 5 'Follower: ' lines, "
        f"got {section.count('Follower: ')}. Section was:\n{section}"
    )
    # Document the legacy bug: bullet pattern must be absent.
    assert section.count("\n- ") == 0, (
        "Legacy '\\n- ' bullet format reappeared — update context.py counter."
    )

    # Pipeline check: feed the real section through the counter replay used in
    # production (mirrors context.py lines 1384-1398). The histogram value
    # observed by Prometheus must be 5, not 1.
    emitted: list[tuple[str, dict, object]] = []

    def _fake_emit(name, value=1, **labels):
        emitted.append((name, labels, value))

    with patch.object(context_mod, "emit_metric", side_effect=_fake_emit):
        _, outcome, examples = _exec_few_shot_branch(
            context_mod, flag_on=True, has_calibration=True,
            section_returned=section,
        )
    assert outcome == "injected"
    assert examples == 5
    counts = [v for n, _, v in emitted if n == "few_shot_examples_count"]
    assert counts == [5], (
        f"Expected histogram observe(5), got {counts}. "
        "Production counter at context.py:1386 may have regressed."
    )


def test_commitment_tracker_service_forwards_creator_id_to_regex():
    """Regression: CommitmentTrackerService.detect_and_store must forward
    ``creator_id`` to ``detect_commitments_regex``. Earlier the call passed
    only ``response_text`` and ``sender``, so ``_load_creator_patterns(None)``
    short-circuited to the hardcoded fallback and the metric labelled every
    detection ``creator_id="unknown", source="hardcoded_fallback"``.
    """
    from services import commitment_tracker as ct

    captured: dict = {}

    def _spy_detect(response_text, sender, creator_id=None):
        captured["response_text"] = response_text
        captured["sender"] = sender
        captured["creator_id"] = creator_id
        return []  # short-circuit DB path

    with patch.object(ct, "ENABLE_COMMITMENT_TRACKING", True), \
         patch.object(ct, "detect_commitments_regex", side_effect=_spy_detect):
        service = ct.CommitmentTrackerService()
        result = service.detect_and_store(
            response_text="te envío el link mañana",
            creator_id="iris_bertran",
            lead_id="lead-123",
            source_message_id="msg-1",
        )

    assert result == []
    assert captured["sender"] == "assistant"
    assert captured["creator_id"] == "iris_bertran", (
        f"creator_id not forwarded — got {captured['creator_id']!r}. "
        f"vocab_meta lookup will fall back to hardcoded patterns."
    )


def test_commitment_tracker_user_message_returns_empty():
    """Only BOT commitments (sender='assistant') are tracked. User messages
    return [] early — no metric emitted."""
    from services import commitment_tracker as ct

    fake_flags = MagicMock()
    fake_flags.commitment_tracking = True

    with patch.object(ct, "flags", fake_flags), \
         patch.object(ct, "emit_metric") as mock_emit:
        result = ct.detect_commitments_regex(
            "te envío un regalo mañana",  # user saying this, not bot
            sender="user",
            creator_id="iris_bertran",
        )

    assert result == []
    mock_emit.assert_not_called()
