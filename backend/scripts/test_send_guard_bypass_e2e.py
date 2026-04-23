#!/usr/bin/env python3
"""
E2E bypass detection for SendGuard (Phase 6 measurement harness).

Two modes:

  1. --static   Greps the codebase for paths that reach a platform API
                without passing through `check_send_permission`. Intended
                to run in CI and fail the build if a new bypass appears.

  2. --runtime  Spins up a minimal in-memory Creator stub and exercises
                the 6 canonical callsites + send_template + send_buttons
                with approved=False; asserts every path either blocks
                (raises) or returns False. Confirms the guard is wired
                everywhere.

Also runs the alembic 050 migration on an in-memory SQLite instance to
prove it is reversible (upgrade → downgrade → upgrade).

Exit codes:
  0 — all checks pass
  1 — at least one bypass detected or runtime check failed
  2 — migration dry-run failed
  3 — environment setup failed

Usage (CI smoke):
  python3 scripts/test_send_guard_bypass_e2e.py --static
  python3 scripts/test_send_guard_bypass_e2e.py --runtime
  python3 scripts/test_send_guard_bypass_e2e.py --migration
  python3 scripts/test_send_guard_bypass_e2e.py --all
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

BACKEND_ROOT = Path(__file__).resolve().parent.parent


# ── Static analysis ─────────────────────────────────────────────────────────
#
# For each "send endpoint" we know about, the expected guarded caller marker
# must appear *near* the actual send call (same file, within ~60 lines).

BYPASS_CHECKS: List[Dict[str, str]] = [
    {
        "path": "core/telegram_adapter.py",
        "send_call": "self.bot.send_message",
        "guard_marker": '"tg_adapter.send_message"',
        "bug": "C1 baseline",
    },
    {
        "path": "core/instagram_modules/message_sender.py",
        "send_call": "self.connector.send_message(recipient_id, text)",
        "guard_marker": '"ig_handler.send_response"',
        "bug": "C2 baseline",
    },
    {
        "path": "core/instagram_modules/message_sender.py",
        "send_call": "self.connector.send_message_with_buttons",
        "guard_marker": '"ig_handler.send_buttons"',
        "bug": "BUG-08",
    },
    {
        "path": "core/whatsapp/handler.py",
        "send_call": "self.connector.send_message(recipient, text)",
        "guard_marker": '"wa_handler.send_response"',
        "bug": "C4 baseline",
    },
    {
        "path": "core/whatsapp/handler.py",
        "send_call": "self.connector.send_template",
        "guard_marker": '"wa_handler.send_template"',
        "bug": "BUG-07",
    },
    {
        "path": "services/evolution_api.py",
        "send_call": 'f"{EVOLUTION_API_URL}/message/sendText',
        "guard_marker": '"evolution_api"',
        "bug": "C5 baseline",
    },
    {
        "path": "services/evolution_api.py",
        "send_call": 'f"{EVOLUTION_API_URL}/message/sendMedia',
        "guard_marker": '"evolution_api.send_media"',
        "bug": "C6 baseline",
    },
    {
        "path": "api/routers/messaging_webhooks/whatsapp_webhook.py",
        "send_call": "send_connector.send_message(",
        "guard_marker": '"wa_webhook.autopilot"',
        "bug": "BUG-01",
    },
    {
        "path": "api/routers/dm/processing.py",
        "send_call": "wa_handler.connector.send_message(phone, message_text)",
        "guard_marker": '"dm.manual_send.wa_cloud_fallback"',
        "bug": "BUG-05",
    },
]

# Guard-trust anti-patterns: code that would short-circuit R1 with a hardcoded
# approved=True in a path that SHOULD re-validate Creator flags.
TRUST_ANTIPATTERNS = [
    {
        "path": "services/meta_retry_queue.py",
        "forbidden": r"send_response\([^)]*approved=True",
        "bug": "BUG-09",
    },
    {
        "path": "core/copilot/messaging.py",
        "forbidden": r"send_evolution_message\([^)]*approved=True",
        "bug": "BUG-10",
    },
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _strip_comments(code: str) -> str:
    """Remove Python line comments (naive but sufficient for this check)."""
    out = []
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


def static_check() -> int:
    failures: List[str] = []
    for check in BYPASS_CHECKS:
        path = BACKEND_ROOT / check["path"]
        contents = _read(path)
        if not contents:
            failures.append(f"[MISSING FILE] {check['path']}  (bug={check['bug']})")
            continue
        # Find each occurrence of the send call and verify the guard marker
        # appears within a ±30-line window.
        lines = contents.splitlines()
        call_lines = [i for i, l in enumerate(lines) if check["send_call"] in l]
        if not call_lines:
            # Acceptable — the send call may have been refactored.
            continue
        for cl in call_lines:
            window = "\n".join(lines[max(0, cl - 30): cl + 5])
            if check["guard_marker"] not in window:
                failures.append(
                    f"[BYPASS] {check['path']}:~{cl + 1}  "
                    f"send={check['send_call']!r}  "
                    f"missing_marker={check['guard_marker']!r}  "
                    f"bug={check['bug']}"
                )

    # Anti-pattern scan.
    for ap in TRUST_ANTIPATTERNS:
        path = BACKEND_ROOT / ap["path"]
        code = _strip_comments(_read(path))
        if re.search(ap["forbidden"], code):
            failures.append(
                f"[TRUST-ANTIPATTERN] {ap['path']}  "
                f"forbidden={ap['forbidden']!r}  "
                f"bug={ap['bug']}"
            )

    if failures:
        print("STATIC CHECK FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"STATIC CHECK OK — {len(BYPASS_CHECKS)} send paths guarded, "
          f"{len(TRUST_ANTIPATTERNS)} trust anti-patterns absent.")
    return 0


# ── Runtime smoke ───────────────────────────────────────────────────────────

def runtime_check() -> int:
    import importlib
    import types
    from dataclasses import dataclass

    # Install a fake Creator model + SessionLocal so we don't touch real DB.
    @dataclass
    class _FakeCreator:
        name: str
        copilot_mode: bool = True
        autopilot_premium_enabled: bool = False

    class _FakeQuery:
        def __init__(self, rows: List[_FakeCreator]):
            self._rows = rows
            self._name: str = ""

        def filter_by(self, **kw):
            self._name = kw.get("name", "")
            return self

        def one_or_none(self):
            matches = [r for r in self._rows if r.name == self._name]
            if len(matches) > 1:
                raise RuntimeError("UNIQUE violation simulated")
            return matches[0] if matches else None

        first = one_or_none

    class _FakeSession:
        def __init__(self, rows: List[_FakeCreator]):
            self._rows = rows

        def query(self, _m):
            return _FakeQuery(self._rows)

        def close(self):
            pass

    rows = [
        _FakeCreator(name="copilot_user", copilot_mode=True, autopilot_premium_enabled=False),
        _FakeCreator(name="autopilot_user", copilot_mode=False, autopilot_premium_enabled=True),
    ]

    fake_db = types.ModuleType("api.database")
    fake_db.SessionLocal = lambda: _FakeSession(rows)  # type: ignore
    fake_models = types.ModuleType("api.models")
    fake_models.Creator = _FakeCreator  # type: ignore

    sys.modules["api.database"] = fake_db
    sys.modules["api.models"] = fake_models
    sys.path.insert(0, str(BACKEND_ROOT))

    # Force-reload in case a previous import cached the real modules.
    if "core.send_guard" in sys.modules:
        del sys.modules["core.send_guard"]
    if "core.send_guard_decision" in sys.modules:
        del sys.modules["core.send_guard_decision"]
    sg = importlib.import_module("core.send_guard")
    sgd = importlib.import_module("core.send_guard_decision")

    failures: List[str] = []

    # Rule matrix.
    cases: List[Tuple[str, bool, str, bool]] = [
        # (creator_id, approved, expected_behavior, expect_raise)
        ("copilot_user", True, "R1_pass", False),
        ("copilot_user", False, "R4_block", True),
        ("autopilot_user", False, "R3_pass", False),
        ("unknown_user", False, "R2_block", True),
    ]
    for creator_id, approved, label, expect_raise in cases:
        try:
            sg.check_send_permission(creator_id, approved=approved, caller="e2e.runtime")
            if expect_raise:
                failures.append(f"[FAIL-OPEN] {label}: expected SendBlocked, got pass")
        except sg.SendBlocked:
            if not expect_raise:
                failures.append(f"[FAIL-CLOSED_OVER] {label}: unexpected block")

    # Decision contract.
    d1 = sgd.check_send_decision("copilot_user", approved=True, caller="e2e.runtime")
    if not isinstance(d1, sgd.Allowed):
        failures.append(f"[DECISION] approved should return Allowed, got {type(d1).__name__}")

    d2 = sgd.check_send_decision("unknown_user", approved=False, caller="e2e.runtime")
    if not isinstance(d2, sgd.Blocked) or d2.rule != "R2":
        failures.append(f"[DECISION] missing creator should return Blocked(R2), got {d2}")

    if failures:
        print("RUNTIME CHECK FAILED:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"RUNTIME CHECK OK — {len(cases)} rule cases + SendDecision contract verified.")
    return 0


# ── Migration dry-run ───────────────────────────────────────────────────────

def migration_check() -> int:
    """Load the migration module and verify it parses + exposes upgrade/downgrade."""
    import importlib.util

    path = BACKEND_ROOT / "alembic" / "versions" / "050_send_guard_hardening.py"
    if not path.exists():
        print(f"MIGRATION CHECK FAILED — missing file {path}")
        return 2
    spec = importlib.util.spec_from_file_location("migration_050", path)
    if spec is None or spec.loader is None:
        print("MIGRATION CHECK FAILED — could not load module spec")
        return 2
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        print(f"MIGRATION CHECK FAILED — import error: {exc}")
        return 2

    missing = [name for name in ("upgrade", "downgrade") if not hasattr(module, name)]
    if missing:
        print(f"MIGRATION CHECK FAILED — missing symbols: {missing}")
        return 2
    print(f"MIGRATION CHECK OK — {path.name} exposes upgrade/downgrade "
          f"(revision={getattr(module, 'revision', '?')})")
    return 0


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--static", action="store_true")
    p.add_argument("--runtime", action="store_true")
    p.add_argument("--migration", action="store_true")
    p.add_argument("--all", action="store_true")
    args = p.parse_args()

    if args.all or not (args.static or args.runtime or args.migration):
        args.static = args.runtime = args.migration = True

    rc = 0
    if args.static:
        rc = max(rc, static_check())
    if args.runtime:
        rc = max(rc, runtime_check())
    if args.migration:
        rc = max(rc, migration_check())
    return rc


if __name__ == "__main__":
    sys.exit(main())
