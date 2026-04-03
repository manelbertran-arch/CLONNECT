"""
Tests for PersonaCompiler (System B) — learning consolidation 7→3 phase 2.

10 tests covering:
1. compile_persona basic flow
2. compile_persona skips insufficient evidence
3. _categorize_evidence
4. _extract_current_sections
5. _apply_sections
6. filter_contradictions
7. Doc D versioning (_snapshot_doc_d)
8. Multi-language compilation (detect_language)
9. Daily evaluation unchanged (regression)
10. Weekly triggers compilation
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. compile_persona basic flow
# ---------------------------------------------------------------------------

class TestCompilePersonaBasic:
    @pytest.mark.asyncio
    @patch("services.persona_compiler._compile_section")
    @patch("api.database.SessionLocal")
    async def test_compile_persona_basic(self, mock_session_cls, mock_compile):
        """With 5+ preference pairs, produces Doc D update."""
        from services.persona_compiler import compile_persona

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # Mock: no previous run
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        # Mock: 5 preference pairs with edit_diff
        mock_pairs = []
        for i in range(5):
            p = MagicMock()
            p.id = uuid.uuid4()
            p.chosen = f"Short reply {i}"
            p.rejected = f"This is a much longer response that goes on and on {i}"
            p.action_type = "edited"
            p.edit_diff = {"categories": ["shortened"], "length_delta": -30}
            mock_pairs.append(p)

        # Mock _collect_signals by patching the query chain
        # Instead, patch _collect_signals directly
        with patch("services.persona_compiler._collect_signals") as mock_collect:
            mock_collect.return_value = {
                "pairs": mock_pairs,
                "feedback": [],
                "evaluations": [],
            }

            # Mock creator
            mock_creator = MagicMock()
            mock_creator.doc_d = "Existing Doc D content"
            mock_creator.id = uuid.uuid4()
            mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creator

            # Mock _compile_section to return a section
            mock_compile.return_value = "Responde de forma breve, máximo 2 frases."

            # Mock _snapshot_doc_d
            with patch("services.persona_compiler._snapshot_doc_d") as mock_snap:
                mock_snap.return_value = str(uuid.uuid4())

                # Mock _persist_run
                with patch("services.persona_compiler._persist_run"):
                    # Mock the update query for batch_analyzed_at
                    mock_session.query.return_value.filter.return_value.update.return_value = 5

                    result = await compile_persona("test_creator", uuid.uuid4())

        assert result["status"] == "done"
        assert "categories_updated" in result
        assert len(result["categories_updated"]) > 0


# ---------------------------------------------------------------------------
# 2. compile_persona skips insufficient evidence
# ---------------------------------------------------------------------------

class TestCompileSkipsInsufficientEvidence:
    @pytest.mark.asyncio
    @patch("api.database.SessionLocal")
    async def test_compile_skips_insufficient_evidence(self, mock_session_cls):
        """< 3 items → skipped."""
        from services.persona_compiler import compile_persona

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # No previous run
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        with patch("services.persona_compiler._collect_signals") as mock_collect:
            mock_collect.return_value = {
                "pairs": [MagicMock()],  # Only 1 pair
                "feedback": [],
                "evaluations": [],
            }
            with patch("services.persona_compiler._persist_run"):
                result = await compile_persona("test_creator", uuid.uuid4())

        assert result["status"] == "skipped"
        assert result["reason"] == "insufficient_evidence"


# ---------------------------------------------------------------------------
# 3. _categorize_evidence
# ---------------------------------------------------------------------------

class TestCategorizeEvidence:
    def test_categorize_evidence(self):
        """Pairs with edit_diff categorize correctly."""
        from services.persona_compiler import _categorize_evidence

        mock_pair = MagicMock()
        mock_pair.chosen = "Hola!"
        mock_pair.rejected = "Hola! Com estàs? Necessites alguna cosa?"
        mock_pair.action_type = "edited"
        mock_pair.edit_diff = {"categories": ["shortened", "removed_question"], "length_delta": -25}

        signals = {"pairs": [mock_pair, mock_pair, mock_pair], "feedback": [], "evaluations": []}
        result = _categorize_evidence(signals)

        assert "length" in result
        assert "questions" in result
        assert len(result["length"]) >= 3
        assert all(e["direction"] == "less" for e in result["length"])


# ---------------------------------------------------------------------------
# 4. _extract_current_sections
# ---------------------------------------------------------------------------

class TestSectionExtraction:
    def test_section_extraction(self):
        """Parse [PERSONA_COMPILER:*] tags from Doc D text."""
        from services.persona_compiler import _extract_current_sections

        doc_d = """Soy Iris Bertran, creadora de contenido.

[PERSONA_COMPILER:tone]
Responde siempre de forma cercana y directa.
[/PERSONA_COMPILER:tone]

Algunas instrucciones manuales aquí.

[PERSONA_COMPILER:length]
Mantén las respuestas entre 1-3 frases máximo.
[/PERSONA_COMPILER:length]
"""
        sections = _extract_current_sections(doc_d)

        assert "tone" in sections
        assert "length" in sections
        assert "cercana" in sections["tone"]
        assert "1-3 frases" in sections["length"]


# ---------------------------------------------------------------------------
# 5. _apply_sections
# ---------------------------------------------------------------------------

class TestSectionApplication:
    def test_section_application_replace(self):
        """Correctly replace existing sections without touching human content."""
        from services.persona_compiler import _apply_sections

        doc_d = """Manual content.

[PERSONA_COMPILER:tone]
Old tone section.
[/PERSONA_COMPILER:tone]

More manual content."""

        updates = {"tone": "New tone: be direct and casual."}
        result = _apply_sections(doc_d, updates)

        assert "New tone: be direct and casual." in result
        assert "Old tone section." not in result
        assert "Manual content." in result
        assert "More manual content." in result

    def test_section_application_add_new(self):
        """Add new section at end without touching existing content."""
        from services.persona_compiler import _apply_sections

        doc_d = "Manual content only."
        updates = {"emoji": "No uses emojis en las respuestas."}
        result = _apply_sections(doc_d, updates)

        assert "Manual content only." in result
        assert "[PERSONA_COMPILER:emoji]" in result
        assert "No uses emojis" in result


# ---------------------------------------------------------------------------
# 6. filter_contradictions
# ---------------------------------------------------------------------------

class TestContradictionResolution:
    def test_contradiction_resolution(self):
        """Newer evidence overrides conflicting old section."""
        from services.persona_compiler import filter_contradictions

        rules = [
            {"rule_text": "Usa emojis en cada mensaje", "confidence": 0.5},
            {"rule_text": "Evita emojis, no uses emoticono", "confidence": 0.8},
        ]
        result = filter_contradictions(rules)

        assert len(result) == 1
        assert result[0]["confidence"] == 0.8
        assert "Evita" in result[0]["rule_text"]


# ---------------------------------------------------------------------------
# 7. Doc D versioning
# ---------------------------------------------------------------------------

class TestDocDVersioning:
    def test_doc_d_versioning(self):
        """_snapshot_doc_d inserts into doc_d_versions."""
        from services.persona_compiler import _snapshot_doc_d

        mock_session = MagicMock()
        creator_id = uuid.uuid4()

        version_id = _snapshot_doc_d(
            mock_session, creator_id, "Old Doc D text", "weekly_compilation", ["tone"]
        )

        assert version_id is not None
        mock_session.execute.assert_called_once()
        # Verify the SQL contains INSERT INTO doc_d_versions
        call_args = mock_session.execute.call_args
        sql_text = str(call_args[0][0])
        assert "doc_d_versions" in sql_text


# ---------------------------------------------------------------------------
# 8. Multi-language compilation
# ---------------------------------------------------------------------------

class TestMultiLanguageCompilation:
    def test_multi_language_compilation(self):
        """Mixed CA/ES evidence detected correctly."""
        from services.persona_compiler import detect_language

        assert detect_language("Tinc una pregunta, estoy muy bien") == "mixto"
        assert detect_language("Tinc una pregunta molt important") == "ca"
        assert detect_language("Tengo una pregunta muy importante") == "es"
        assert detect_language("Hello, how are you?") == "unknown"


# ---------------------------------------------------------------------------
# 9. Daily evaluation unchanged (regression)
# ---------------------------------------------------------------------------

class TestDailyEvaluationUnchanged:
    @pytest.mark.asyncio
    @patch("api.database.SessionLocal")
    async def test_daily_evaluation_unchanged(self, mock_session_cls):
        """Daily eval still works as before (regression test)."""
        from services.persona_compiler import run_daily_evaluation

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # Already evaluated
        mock_session.query.return_value.filter_by.return_value.first.return_value = MagicMock()

        result = await run_daily_evaluation("test_creator", uuid.uuid4())
        assert result == {"skipped": True}

    @pytest.mark.asyncio
    @patch("api.database.SessionLocal")
    async def test_daily_evaluation_direct(self, mock_session_cls):
        """Direct import from persona_compiler works."""
        from services.persona_compiler import run_daily_evaluation

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = MagicMock()

        result = await run_daily_evaluation("test_creator", uuid.uuid4())
        assert result == {"skipped": True}


# ---------------------------------------------------------------------------
# 10. Weekly triggers compilation
# ---------------------------------------------------------------------------

class TestWeeklyTriggersCompilation:
    @pytest.mark.asyncio
    @patch("api.database.SessionLocal")
    async def test_weekly_triggers_compilation(self, mock_session_cls):
        """Weekly recalibration triggers compile_persona when recommendations exist."""
        from services.persona_compiler import run_weekly_recalibration

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # No existing weekly eval
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        # 4 daily evals with data
        daily_evals = []
        for i in range(4):
            ev = MagicMock()
            ev.metrics = {
                "total_actions": 10,
                "approval_rate": 0.3,
                "edit_rate": 0.6,
                "discard_rate": 0.1,
                "clone_accuracy": 0.5,
            }
            ev.patterns = [{"type": "consistent_shortening", "suggestion": "shorten"}]
            daily_evals.append(ev)

        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = daily_evals

        result = await run_weekly_recalibration("test_creator", uuid.uuid4())

        assert result.get("stored") is True
        assert "recommendations" in result
        # high_edit_rate should be detected (0.6 > 0.5 threshold)
        rec_types = [r["type"] for r in result["recommendations"]]
        assert "high_edit_rate" in rec_types


# ---------------------------------------------------------------------------
# Backward compatibility: old imports still work
# ---------------------------------------------------------------------------

class TestBackwardCompat:
    def test_direct_persona_compiler_exports(self):
        """All consolidated functions are importable directly from persona_compiler."""
        from services.persona_compiler import (
            run_daily_evaluation,
            run_weekly_recalibration,
            compile_persona,
            compile_persona_all,
            analyze_creator_action,
            _is_non_text_response,
        )
        assert callable(run_daily_evaluation)
        assert callable(run_weekly_recalibration)
        assert callable(compile_persona)
        assert callable(compile_persona_all)
        assert callable(analyze_creator_action)
        assert callable(_is_non_text_response)
