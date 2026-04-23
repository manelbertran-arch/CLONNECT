"""Forensic unit tests for core.dm.strategy — vocab_meta + fallback + gates.

Covers:
  - Happy path each active branch (P3, P3+AYUDA, P4, P5, P6, P7, default).
  - Dormant branches (P1, P2) still return their hint when directly invoked
    with the relevant flags — the callsite hardcodes them away, but the
    function must remain correct for unit/audit callers.
  - vocab_meta lookup: mined vs fallback wiring for each of the 4 linguistic
    vocab types (apelativos, openers_to_avoid, anti_bugs_verbales, help_signals).
  - creator_id=None must not crash and must not emit creator-specific vocab.
  - Bootstrap script: merge idempotency (pure logic, no DB).

Tests are intentionally self-contained (monkeypatch-only) and avoid hitting
the DB so they run in <5s on CI.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.dm.strategy import _determine_response_strategy  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _call(**overrides) -> str:
    """Thin wrapper with safe defaults so each test only specifies what it changes."""
    defaults = dict(
        message="",
        intent_value="",
        relationship_type="",
        is_first_message=False,
        is_friend=False,
        lead_stage="",
        history_len=0,
        creator_id=None,
        creator_display_name="",
    )
    defaults.update(overrides)
    return _determine_response_strategy(**defaults)


def _patch_vocab(mapping: Dict[str, List[str]]):
    """Patch services.calibration_loader._load_creator_vocab to return mapping."""
    return patch("services.calibration_loader._load_creator_vocab", return_value=mapping)


# ─────────────────────────────────────────────────────────────────────────────
# Branch precedence — happy paths
# ─────────────────────────────────────────────────────────────────────────────

class TestBranchPrecedence:
    def test_p1_personal_familia_fires_when_relationship_is_familia(self):
        hint = _call(relationship_type="FAMILIA", message="hola")
        assert "PERSONAL-FAMILIA" in hint
        assert "NUNCA vendas" in hint

    def test_p2_personal_amigo_fires_when_is_friend_true(self):
        hint = _call(is_friend=True, message="hola")
        assert "PERSONAL-AMIGO" in hint

    def test_p3_bienvenida_fires_on_first_message_without_question(self):
        hint = _call(is_first_message=True, message="hola qué tal")
        assert "BIENVENIDA" in hint and "AYUDA" not in hint

    def test_p3_bienvenida_ayuda_fires_on_first_message_with_question(self):
        hint = _call(is_first_message=True, message="Hola ¿cuánto cuesta?")
        assert "BIENVENIDA + AYUDA" in hint

    def test_p4_recurrente_fires_when_history_long_and_not_first(self, monkeypatch):
        # vocab_meta empty → neutral fallback phrasing but still RECURRENTE token.
        with _patch_vocab({}):
            hint = _call(
                message="hola",
                history_len=10,
                is_first_message=False,
                creator_id="iris_bertran",
            )
        assert "RECURRENTE" in hint

    def test_p5_ayuda_fires_for_returning_user_with_help_signal(self):
        with _patch_vocab({"help_signals": ["ayuda"]}):
            hint = _call(
                message="necesito ayuda",
                history_len=1,  # not recurrent, not first
                creator_id="iris_bertran",
            )
        assert "AYUDA" in hint
        assert "RECURRENTE" not in hint

    def test_p6_venta_fires_for_purchase_intent(self):
        hint = _call(intent_value="pricing", message="cuánto vale")
        assert "VENTA" in hint

    def test_p7_reactivacion_fires_for_ghost_stage(self):
        hint = _call(lead_stage="fantasma", message="holis")
        assert "REACTIVACIÓN" in hint

    def test_default_empty_when_no_branch_matches(self):
        with _patch_vocab({}):
            hint = _call(
                message="ok",
                history_len=1,
                creator_id="iris_bertran",
            )
        assert hint == ""


# ─────────────────────────────────────────────────────────────────────────────
# Precedence across overlapping conditions
# ─────────────────────────────────────────────────────────────────────────────

class TestPrecedence:
    def test_first_message_beats_help_signal(self):
        with _patch_vocab({"help_signals": ["ayuda"]}):
            hint = _call(
                message="Hola, necesito ayuda",
                is_first_message=True,
                history_len=0,
                creator_id="iris_bertran",
            )
        assert "BIENVENIDA + AYUDA" in hint
        assert not hint.startswith("ESTRATEGIA: AYUDA")

    def test_recurrente_beats_help_signal_when_history_long(self):
        with _patch_vocab({"help_signals": ["ayuda"]}):
            hint = _call(
                message="necesito ayuda",
                history_len=10,
                is_first_message=False,
                creator_id="iris_bertran",
            )
        assert "RECURRENTE" in hint
        assert not hint.startswith("ESTRATEGIA: AYUDA")

    def test_recurrente_beats_venta_when_both_match(self):
        """history_len >= 4 + intent=pricing → RECURRENTE wins (P4 before P6)."""
        with _patch_vocab({}):
            hint = _call(
                intent_value="pricing",
                message="ok, ¿y el plan?",
                history_len=6,
                is_first_message=False,
                creator_id="iris_bertran",
            )
        assert "RECURRENTE" in hint


# ─────────────────────────────────────────────────────────────────────────────
# vocab_meta: mined vs fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestVocabMetaMined:
    def test_p4_uses_mined_apelativos_and_display_name(self):
        with _patch_vocab({"apelativos": ["tesoro", "bella"]}):
            hint = _call(
                message="ciao",
                history_len=8,
                is_first_message=False,
                creator_id="stefano_bonanno",
                creator_display_name="Stefano",
            )
        assert "tesoro" in hint and "bella" in hint
        assert "Stefano" in hint
        # Must not leak Iris vocabulary or name anywhere.
        for forbidden in ("nena", "cuca", "flor", "Iris"):
            assert forbidden not in hint

    def test_p4_uses_mined_anti_bugs_verbales(self):
        with _patch_vocab({
            "apelativos": ["tesoro"],
            "anti_bugs_verbales": ["sweetheart"],
        }):
            hint = _call(
                message="ciao",
                history_len=8,
                is_first_message=False,
                creator_id="stefano_bonanno",
                creator_display_name="Stefano",
            )
        assert "sweetheart" in hint
        assert "NUNCA" in hint  # anti-bug clause must be instructive

    def test_p4_uses_mined_openers_to_avoid(self):
        with _patch_vocab({
            "openers_to_avoid": ["Che ti ha colpito?", "What caught your attention?"],
        }):
            hint = _call(
                message="ciao",
                history_len=8,
                is_first_message=False,
                creator_id="stefano_bonanno",
                creator_display_name="Stefano",
            )
        assert "Che ti ha colpito?" in hint
        assert "What caught your attention?" in hint
        assert "¿Que te llamó la atención?" not in hint  # no ES leak for Stefano

    def test_p5_uses_mined_help_signals_in_italian(self):
        with _patch_vocab({"help_signals": ["aiuto", "non riesco"]}):
            hint = _call(
                message="non riesco ad accedere",
                history_len=1,
                creator_id="stefano_bonanno",
            )
        assert "AYUDA" in hint


class TestVocabMetaFallback:
    def test_p4_neutral_fallback_when_vocab_empty(self):
        with _patch_vocab({}):
            hint = _call(
                message="hola",
                history_len=8,
                is_first_message=False,
                creator_id="unknown_creator",
                creator_display_name="",
            )
        assert "RECURRENTE" in hint
        # No creator-specific tokens should be present.
        for forbidden in ("nena", "tia", "flor", "cuca", "reina", "Iris", "flower"):
            assert forbidden not in hint
        # Must still give the returning-user guardrails (rules 2 & 3).
        assert "NO saludes" in hint or "NO abras" in hint

    def test_help_signals_fallback_returns_false_when_no_vocab(self):
        """When vocab empty and message has no "?" the fallback detects no help."""
        with _patch_vocab({}):
            hint = _call(
                message="necesito ayuda",  # help-looking but no vocab match
                history_len=1,
                creator_id="stefano_bonanno",
            )
        # Should NOT match AYUDA via legacy hardcoded ES list anymore.
        assert "ESTRATEGIA: AYUDA" not in hint

    def test_creator_id_none_does_not_crash_and_skips_vocab(self):
        hint = _call(
            message="hola",
            history_len=8,
            is_first_message=False,
            creator_id=None,
            creator_display_name="",
        )
        assert "RECURRENTE" in hint
        for forbidden in ("nena", "cuca", "Iris", "flower"):
            assert forbidden not in hint


# ─────────────────────────────────────────────────────────────────────────────
# follower_interests removal — regression test for BUG-011
# ─────────────────────────────────────────────────────────────────────────────

class TestSignatureHygiene:
    def test_signature_does_not_accept_follower_interests(self):
        with pytest.raises(TypeError):
            _determine_response_strategy(
                message="x",
                intent_value="",
                relationship_type="",
                is_first_message=False,
                is_friend=False,
                follower_interests=[],  # legacy — must fail now
                lead_stage="",
                history_len=0,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap script merge logic
# ─────────────────────────────────────────────────────────────────────────────

class TestBootstrapMerge:
    def test_merge_is_idempotent_when_fully_seeded(self):
        import scripts.bootstrap_vocab_meta_iris_strategy as boot
        existing = dict(boot.IRIS_SEED)
        merged, actions = boot._merge(existing, boot.IRIS_SEED)
        assert merged == existing
        for k, v in actions.items():
            assert "already covered" in v or "no-op" in v

    def test_merge_appends_missing_keys(self):
        import scripts.bootstrap_vocab_meta_iris_strategy as boot
        existing = {"apelativos": ["reina"], "blacklist_emojis": ["😊"]}
        merged, actions = boot._merge(existing, boot.IRIS_SEED)
        # Existing emoji list is preserved untouched
        assert merged["blacklist_emojis"] == ["😊"]
        # Apelativos get new entries appended (not overwritten)
        assert "reina" in merged["apelativos"]
        assert "nena" in merged["apelativos"]
        # Other seed keys are inserted
        assert merged["anti_bugs_verbales"] == ["flower"]
        assert set(actions.keys()) == set(boot.IRIS_SEED.keys())
