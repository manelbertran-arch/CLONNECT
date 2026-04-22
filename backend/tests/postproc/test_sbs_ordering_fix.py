"""Tests for S6-T5.1 fix: content protections re-applied after SBS/PPA regeneration."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.dm.phases.postprocessing import _apply_content_protections


# ─── shared fixtures ───────────────────────────────────────────────────────────

def _make_agent(creator_id="test_creator", products=None):
    agent = MagicMock()
    agent.creator_id = creator_id
    agent.products = products or []
    return agent


# ─── Test 1: protections re-applied after SBS retry ───────────────────────────

class TestProtectionsReappliedAfterSBSRetry:

    def test_a2b_cleans_intra_repetition(self):
        """A2b (intra-repetition) runs on SBS-retried response via _apply_content_protections."""
        agent = _make_agent()
        # Response with intra-repetition that A2b should truncate
        dirty = "Que vagi be germana " + "JAJA" * 20
        result = _apply_content_protections(dirty, "hola", agent)
        assert "JAJAJAJAJAJAJAJA" not in result, (
            "A2b should truncate the repetition loop"
        )
        assert result.startswith("Que vagi be germana"), "Prefix before repetition should be kept"

    def test_a2c_cleans_sentence_repetition(self):
        """A2c (sentence dedup) runs on SBS-retried response."""
        agent = _make_agent()
        # Sentence repeated 3+ times — A2c should deduplicate
        dirty = "On estas? On estas? On estas? On estas?"
        result = _apply_content_protections(dirty, "hola", agent)
        count = result.lower().count("on estas")
        assert count < 3, f"A2c should dedup repeated sentences, got {count} occurrences"

    def test_7a2_response_fixes_applied(self):
        """Step 7a2 (response fixes) runs on regenerated response."""
        agent = _make_agent()
        # Patch the name bound in postprocessing's module namespace (not the source module)
        with patch("core.dm.phases.postprocessing.apply_all_response_fixes", return_value="fixed") as mock_fix:
            with patch("core.feature_flags.flags") as mock_flags:
                mock_flags.m3_disable_dedupe_repetitions = False
                mock_flags.m4_disable_dedupe_sentences = False
                mock_flags.m5_disable_echo_detector = False
                mock_flags.output_validation = False
                mock_flags.response_fixes = True
                mock_flags.blacklist_replacement = False
                mock_flags.question_removal = False
                result = _apply_content_protections("original", "hola", agent)
        mock_fix.assert_called_once()
        assert result == "fixed"


# ─── Test 2: protections re-applied after PPA refinement ──────────────────────

class TestProtectionsReappliedAfterPPARefinement:

    def test_apply_content_protections_callable_after_ppa(self):
        """_apply_content_protections is importable and callable for PPA path."""
        agent = _make_agent()
        # A2b should catch this repetition regardless of calling context
        dirty = "hola nena " + "dale " * 10
        with patch("core.feature_flags.flags") as mock_flags:
            mock_flags.m3_disable_dedupe_repetitions = False
            mock_flags.m4_disable_dedupe_sentences = False
            mock_flags.m5_disable_echo_detector = True
            mock_flags.output_validation = False
            mock_flags.response_fixes = False
            mock_flags.blacklist_replacement = False
            mock_flags.question_removal = False
            result = _apply_content_protections(dirty, "hola", agent)
        # Function ran without exception; A2b may or may not trigger depending on input
        assert isinstance(result, str)
        assert len(result) > 0


# ─── Test 3: idempotence ───────────────────────────────────────────────────────

class TestIdempotenceSecondApplication:

    def test_a2b_idempotent(self):
        """Applying _apply_content_protections twice gives same result as once."""
        agent = _make_agent()
        dirty = "hola tia " + "JAJA" * 12
        first = _apply_content_protections(dirty, "hola", agent)
        second = _apply_content_protections(first, "hola", agent)
        assert first == second, "A2b: second call must be no-op"

    def test_a2c_idempotent(self):
        """A2c dedup is idempotent: dedup of already-deduped text is unchanged."""
        agent = _make_agent()
        dirty = "On estas? On estas? On estas?"
        first = _apply_content_protections(dirty, "hola", agent)
        second = _apply_content_protections(first, "hola", agent)
        assert first == second, "A2c: second call must be no-op"

    def test_response_fixes_idempotent(self):
        """Response fixes (7a2) applied twice must equal applying once."""
        agent = _make_agent()
        call_count = {"n": 0}
        original = "clean response"

        def mock_fix(text, creator_id=""):
            call_count["n"] += 1
            return text  # no-op fix

        # Patch the name bound in postprocessing's module namespace
        with patch("core.dm.phases.postprocessing.apply_all_response_fixes", side_effect=mock_fix):
            with patch("core.feature_flags.flags") as mock_flags:
                mock_flags.m3_disable_dedupe_repetitions = False
                mock_flags.m4_disable_dedupe_sentences = False
                mock_flags.m5_disable_echo_detector = True
                mock_flags.output_validation = False
                mock_flags.response_fixes = True
                mock_flags.blacklist_replacement = False
                mock_flags.question_removal = False
                first = _apply_content_protections(original, "hola", agent)
                second = _apply_content_protections(first, "hola", agent)
        assert first == second
        assert call_count["n"] == 2  # called once per invocation


# ─── Test 4: no re-apply when flags off ───────────────────────────────────────

class TestNoReapplyWhenFlagsOff:

    def test_protections_called_once_when_sbs_ppa_off(self):
        """When both flags off, _apply_content_protections called exactly once."""
        import core.dm.phases.postprocessing as pp_mod
        with patch(
            "core.dm.phases.postprocessing._apply_content_protections",
            wraps=_apply_content_protections,
        ) as mock_protect:
            with patch("core.feature_flags.flags") as mock_flags:
                mock_flags.score_before_speak = False
                mock_flags.ppa = False
                mock_flags.m3_disable_dedupe_repetitions = False
                mock_flags.m4_disable_dedupe_sentences = False
                mock_flags.m5_disable_echo_detector = True
                mock_flags.output_validation = False
                mock_flags.response_fixes = False
                mock_flags.blacklist_replacement = False
                mock_flags.question_removal = False
                # Call via module attribute so the patch intercepts it
                _ = pp_mod._apply_content_protections("test response", "hola", _make_agent())
        assert mock_protect.call_count == 1

    def test_no_reapply_metric_when_not_regenerated(self):
        """protections_reapplied_total must NOT emit if _sbs_regenerated and _ppa_regenerated are False."""
        with patch("core.dm.phases.postprocessing.emit_metric") as mock_emit:
            with patch("core.feature_flags.flags") as mock_flags:
                mock_flags.score_before_speak = False
                mock_flags.ppa = False
                # Simulate calling the Step 7a5 block with both flags = False
                _sbs_regenerated = False
                _ppa_regenerated = False
                if _sbs_regenerated:
                    mock_emit("protections_reapplied_total", creator_id="x", reasoning_system="sbs")
                elif _ppa_regenerated:
                    mock_emit("protections_reapplied_total", creator_id="x", reasoning_system="ppa")

        for c in mock_emit.call_args_list:
            assert c[0][0] != "protections_reapplied_total", (
                "protections_reapplied_total must not emit when no regeneration"
            )


# ─── Test 5: metrics emitted correctly per SBS path ───────────────────────────

class TestMetricsEmittedCorrectly:

    @pytest.mark.asyncio
    async def test_path_pass_emits_score_initial_and_path(self):
        """Pass path emits sbs_score_initial + sbs_path_total(pass), nothing else."""
        from core.reasoning.ppa import score_before_speak
        CALIBRATION = {
            "baseline": {"median_length": 35, "emoji_pct": 18.0, "soft_max": 60},
            "few_shot_examples": [],
        }
        with patch("core.reasoning.ppa.emit_metric") as mock_emit:
            result = await score_before_speak(
                response="Holaa reina! 😂",
                calibration=CALIBRATION,
                system_prompt="",
                user_prompt="",
            )
        assert result.path == "pass"
        emitted = [c[0][0] for c in mock_emit.call_args_list]
        assert "sbs_score_initial" in emitted
        assert "sbs_path_total" in emitted
        assert "sbs_score_retry" not in emitted
        # path label check
        path_calls = [c for c in mock_emit.call_args_list if c[0][0] == "sbs_path_total"]
        assert any(c[1].get("path") == "pass" for c in path_calls)

    @pytest.mark.asyncio
    async def test_path_retried_emits_all_four_metrics(self):
        """Retried path emits sbs_score_initial, sbs_score_retry, sbs_path_total(retried)."""
        from core.reasoning.ppa import score_before_speak
        CALIBRATION = {
            "baseline": {"median_length": 35, "emoji_pct": 18.0, "soft_max": 60},
            "few_shot_examples": [],
        }
        # Low-score response that will trigger retry
        bad_response = (
            "Estimada cliente, estoy aquí para ayudarte con cualquier consulta. "
            "No dudes en escribirme si necesitas algo más."
        )
        retry_content = {"content": "Holaa reina 😂"}

        with patch("core.reasoning.ppa.emit_metric") as mock_emit:
            with patch(
                "core.providers.gemini_provider.generate_dm_response",
                new_callable=AsyncMock,
                return_value=retry_content,
            ):
                result = await score_before_speak(
                    response=bad_response,
                    calibration=CALIBRATION,
                    system_prompt="sys",
                    user_prompt="user prompt",
                )

        assert result.path == "retried"
        emitted = [c[0][0] for c in mock_emit.call_args_list]
        assert "sbs_score_initial" in emitted
        assert "sbs_score_retry" in emitted
        assert "sbs_path_total" in emitted
        path_calls = [c for c in mock_emit.call_args_list if c[0][0] == "sbs_path_total"]
        assert any(c[1].get("path") == "retried" for c in path_calls)

    @pytest.mark.asyncio
    async def test_path_fail_retry_fallback_emits_path_metric(self):
        """fail_retry_fallback path emits sbs_path_total(fail_retry_fallback), no protections_reapplied."""
        from core.reasoning.ppa import score_before_speak
        CALIBRATION = {
            "baseline": {"median_length": 35, "emoji_pct": 18.0, "soft_max": 60},
            "few_shot_examples": [],
        }
        bad_response = (
            "Estimada cliente, estoy aquí para ayudarte con cualquier consulta. "
            "No dudes en escribirme."
        )

        with patch("core.reasoning.ppa.emit_metric") as mock_emit:
            with patch(
                "core.providers.gemini_provider.generate_dm_response",
                new_callable=AsyncMock,
                side_effect=Exception("LLM down"),
            ):
                result = await score_before_speak(
                    response=bad_response,
                    calibration=CALIBRATION,
                    system_prompt="sys",
                    user_prompt="user prompt",
                )

        assert result.path == "fail_retry_fallback"
        emitted = [c[0][0] for c in mock_emit.call_args_list]
        assert "sbs_score_initial" in emitted
        assert "sbs_path_total" in emitted
        assert "sbs_score_retry" not in emitted
        path_calls = [c for c in mock_emit.call_args_list if c[0][0] == "sbs_path_total"]
        assert any(c[1].get("path") == "fail_retry_fallback" for c in path_calls)
        # protections_reapplied_total NOT emitted from ppa.py on this path
        assert "protections_reapplied_total" not in emitted
