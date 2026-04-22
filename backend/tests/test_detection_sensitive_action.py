"""Verifies that phase_detection persists SensitiveResult.action_required in
cognitive_metadata so the P4 sell-arbiter adapter can read it.

Before this fix (detection.py:180-186) only ``sensitive_detected`` and
``sensitive_category`` were persisted; ``action_required`` was computed
inside SensitiveResult but immediately discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from core.dm.phases import detection as detection_module
from core.sensitive_detector import SensitiveType


# ─────────────────────────────────────────────────────────────────────────────
# Minimal agent stub — phase_detection only reads .creator_id.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _FakeAgent:
    creator_id: str = "test_creator"


class _FakeSensitive:
    """Matches SensitiveResult's public surface closely enough for phase_detection."""

    def __init__(
        self,
        type_: SensitiveType,
        confidence: float,
        action_required: str,
        reason: Optional[str] = None,
    ) -> None:
        self.type = type_
        self.confidence = confidence
        self.action_required = action_required
        self.reason = reason

    def __bool__(self) -> bool:
        return self.type != SensitiveType.NONE


@pytest.fixture
def agent() -> _FakeAgent:
    return _FakeAgent()


async def _run_phase(
    agent: _FakeAgent, message: str, cognitive_metadata: Dict[str, Any]
) -> Any:
    return await detection_module.phase_detection(
        agent=agent,
        message=message,
        sender_id="sender_x",
        metadata={},
        cognitive_metadata=cognitive_metadata,
    )


@pytest.mark.asyncio
async def test_detection_persists_no_pressure_sale(
    agent: _FakeAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Eating-disorder / minor → action_required='no_pressure_sale'."""
    fake = _FakeSensitive(
        type_=SensitiveType.EATING_DISORDER,
        confidence=0.8,
        action_required="no_pressure_sale",
    )
    monkeypatch.setattr(detection_module, "detect_sensitive_content", lambda _m: fake)
    monkeypatch.setattr(
        detection_module, "_dispatch_security_alert", lambda **_kw: None
    )

    cm: Dict[str, Any] = {}
    await _run_phase(agent, "tengo un trastorno de la alimentación", cm)
    assert cm.get("sensitive_action_required") == "no_pressure_sale"


@pytest.mark.asyncio
async def test_detection_persists_empathetic_response(
    agent: _FakeAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Self-harm / threat → action_required='empathetic_response'."""
    fake = _FakeSensitive(
        type_=SensitiveType.SELF_HARM,
        confidence=0.95,
        action_required="empathetic_response",
    )
    monkeypatch.setattr(detection_module, "detect_sensitive_content", lambda _m: fake)
    monkeypatch.setattr(
        detection_module, "_dispatch_security_alert", lambda **_kw: None
    )

    cm: Dict[str, Any] = {}
    await _run_phase(agent, "quiero desaparecer", cm)
    assert cm.get("sensitive_action_required") == "empathetic_response"


@pytest.mark.asyncio
async def test_detection_below_threshold_does_not_persist(
    agent: _FakeAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When confidence < sensitive_confidence threshold, nothing is persisted.

    Prevents accidental leakage of action_required for marginal matches.
    """
    fake = _FakeSensitive(
        type_=SensitiveType.EATING_DISORDER,
        confidence=0.2,  # below default 0.7
        action_required="no_pressure_sale",
    )
    monkeypatch.setattr(detection_module, "detect_sensitive_content", lambda _m: fake)
    monkeypatch.setattr(
        detection_module, "_dispatch_security_alert", lambda **_kw: None
    )

    cm: Dict[str, Any] = {}
    await _run_phase(agent, "algo vagamente sensible", cm)
    assert "sensitive_action_required" not in cm
    assert "sensitive_detected" not in cm


@pytest.mark.asyncio
async def test_detection_non_sensitive_leaves_metadata_clean(
    agent: _FakeAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Boring message → no sensitive flags at all, including action_required."""
    fake = _FakeSensitive(
        type_=SensitiveType.NONE,
        confidence=0.0,
        action_required="none",
    )
    monkeypatch.setattr(detection_module, "detect_sensitive_content", lambda _m: fake)

    cm: Dict[str, Any] = {}
    await _run_phase(agent, "hola cuánto cuesta el curso", cm)
    assert "sensitive_action_required" not in cm
