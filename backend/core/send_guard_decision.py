"""
SendDecision — structured authorization outcome for send_guard.

Companion to `core.send_guard`. Where `check_send_permission` raises `SendBlocked`
on denial (legacy contract for the 6 callsites), `check_send_decision` returns
a typed `SendDecision` (Allowed | Blocked) with machine-readable fields for
auditing, metrics and adapter-layer branching.

Design references (docs/forensic/send_guard/04_state_of_art.md):
- Luke Plant — exceptions vs error objects (sum types with dataclasses).
- Advisor360° Decision Gateway Pattern — structured "tool unavailable" response.
- Cerbos Python SDK — `is_allowed` decision object with async + sync modes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional, Union


DecisionRule = Literal["R1", "R2", "R3", "R4", "R5"]
# R1: approved=True short-circuit  (PASS)
# R2: creator not found            (BLOCK)
# R3: autopilot premium active     (PASS)
# R4: insufficient flags           (BLOCK)
# R5: guard-internal error         (BLOCK, fail-closed)


@dataclass(frozen=True)
class Allowed:
    """Decision: the send is authorized. Always represents a PASS."""

    creator_id: str
    caller: str
    rule: DecisionRule  # R1 or R3
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    sent: Literal[True] = True
    blocked: Literal[False] = False


@dataclass(frozen=True)
class Blocked:
    """Decision: the send is denied. Always represents a BLOCK."""

    creator_id: str
    caller: str
    rule: DecisionRule  # R2, R4 or R5
    reason: str
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    copilot_mode: Optional[bool] = None
    autopilot_premium_enabled: Optional[bool] = None

    sent: Literal[False] = False
    blocked: Literal[True] = True


SendDecision = Union[Allowed, Blocked]


def check_send_decision(
    creator_id: str,
    *,
    approved: bool = False,
    caller: str,
) -> SendDecision:
    """
    Evaluate the send_guard rules and return a typed SendDecision.

    Never raises (except for programming errors like missing `caller`).
    Wraps the legacy sync `check_send_permission` — if SEND_GUARD_AUDIT_ONLY is
    enabled and the rules would BLOCK, this returns a Blocked decision with the
    shadow rule recorded but the caller is free to decide how to handle it
    (typical pattern: shadow logs but still sends).

    Args:
        creator_id: Creator slug (maps to Creator.name).
        approved: True if explicitly approved by the creator or creator-initiated.
        caller: Adapter identifier (e.g. "tg_adapter.send_message"). REQUIRED.

    Returns:
        SendDecision (Allowed | Blocked).
    """
    from core.send_guard import _evaluate  # type: ignore

    return _evaluate(creator_id=creator_id, approved=approved, caller=caller)


async def check_send_decision_async(
    creator_id: str,
    *,
    approved: bool = False,
    caller: str,
) -> SendDecision:
    """
    Async equivalent of `check_send_decision` — offloads the sync DB query to a
    thread so the event loop is not blocked under pool pressure (BUG-04).

    Args:
        creator_id: Creator slug.
        approved: True if explicitly approved.
        caller: Adapter identifier. REQUIRED.

    Returns:
        SendDecision (Allowed | Blocked).
    """
    import asyncio

    return await asyncio.to_thread(
        check_send_decision,
        creator_id,
        approved=approved,
        caller=caller,
    )
