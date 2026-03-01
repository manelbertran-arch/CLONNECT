"""
Tests for services/calibration_loader.py

Calibration loader reads per-creator JSON files and caches them in memory.
Tests cover: file loading, cache TTL, invalidation, and few-shot section formatting.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch
from services.calibration_loader import (
    load_calibration,
    get_few_shot_section,
    invalidate_cache,
)

# ---------------------------------------------------------------------------
# Sample calibration data
# ---------------------------------------------------------------------------

SAMPLE_CAL = {
    "baseline": {
        "median_length": 85,
        "emoji_pct": 25.0,
        "exclamation_pct": 40.0,
        "question_frequency_pct": 30.0,
    },
    "few_shot_examples": [
        {"user_message": "Hola!", "response": "Hola, qué tal todo?", "context": "greeting"},
        {"user_message": "Cuánto cuesta?", "response": "Son 97€ el Fitpack.", "context": "pricing"},
        {"user_message": "Me interesa el programa", "response": "Te cuento más.", "context": "interest"},
    ],
}


@pytest.fixture(autouse=True)
def clear_cache():
    """Reset in-memory cache before and after every test."""
    invalidate_cache()
    yield
    invalidate_cache()


# ---------------------------------------------------------------------------
# load_calibration — file I/O
# ---------------------------------------------------------------------------

class TestLoadCalibration:

    def test_returns_none_for_unknown_creator(self, tmp_path):
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            result = load_calibration("nobody")
        assert result is None

    def test_returns_dict_for_existing_calibration_file(self, tmp_path):
        (tmp_path / "creator_a.json").write_text(json.dumps(SAMPLE_CAL))
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            result = load_calibration("creator_a")
        assert isinstance(result, dict)
        assert result["baseline"]["emoji_pct"] == 25.0

    def test_baseline_values_are_accessible(self, tmp_path):
        (tmp_path / "creator_b.json").write_text(json.dumps(SAMPLE_CAL))
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            result = load_calibration("creator_b")
        baseline = result["baseline"]
        assert baseline["median_length"] == 85
        assert baseline["exclamation_pct"] == 40.0

    def test_returns_none_on_malformed_json(self, tmp_path):
        (tmp_path / "bad_creator.json").write_text("{this: is not valid json!}")
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            result = load_calibration("bad_creator")
        assert result is None

    def test_returns_none_on_empty_file(self, tmp_path):
        (tmp_path / "empty_creator.json").write_text("")
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            result = load_calibration("empty_creator")
        assert result is None


# ---------------------------------------------------------------------------
# load_calibration — caching
# ---------------------------------------------------------------------------

class TestLoadCalibrationCache:

    def test_caches_result_on_second_call(self, tmp_path):
        """Second call returns cached result even if file is deleted."""
        f = tmp_path / "cached.json"
        f.write_text(json.dumps(SAMPLE_CAL))
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            first = load_calibration("cached")
            f.unlink()  # Delete file
            second = load_calibration("cached")  # Should still work from cache
        assert first is not None
        assert second == first

    def test_caches_none_for_missing_file(self, tmp_path):
        """None result is also cached, preventing repeated disk hits."""
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            r1 = load_calibration("never_existed")
            # Create file now — but cache should still return None
            (tmp_path / "never_existed.json").write_text(json.dumps(SAMPLE_CAL))
            r2 = load_calibration("never_existed")
        assert r1 is None
        assert r2 is None  # Cache hit, not re-read

    def test_invalidate_specific_creator_clears_cache(self, tmp_path):
        """After invalidation, next call re-reads from disk."""
        f = tmp_path / "creator_x.json"
        f.write_text(json.dumps(SAMPLE_CAL))
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            load_calibration("creator_x")  # Populate cache
            invalidate_cache("creator_x")
            f.unlink()  # Now remove file
            result = load_calibration("creator_x")  # Must re-read → None
        assert result is None

    def test_invalidate_all_clears_all_entries(self, tmp_path):
        """invalidate_cache() with no args clears everything."""
        for name in ["c1", "c2", "c3"]:
            (tmp_path / f"{name}.json").write_text(json.dumps(SAMPLE_CAL))
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            for name in ["c1", "c2", "c3"]:
                load_calibration(name)  # Populate all
            invalidate_cache()           # Clear all
            for name in ["c1", "c2", "c3"]:
                (tmp_path / f"{name}.json").unlink()
            for name in ["c1", "c2", "c3"]:
                assert load_calibration(name) is None

    def test_different_creators_cached_independently(self, tmp_path):
        """Cache key is per creator_id, not global."""
        (tmp_path / "alpha.json").write_text(json.dumps(SAMPLE_CAL))
        custom_cal = {**SAMPLE_CAL, "baseline": {**SAMPLE_CAL["baseline"], "emoji_pct": 99.0}}
        (tmp_path / "beta.json").write_text(json.dumps(custom_cal))
        with patch("services.calibration_loader.CALIBRATIONS_DIR", str(tmp_path)):
            alpha = load_calibration("alpha")
            beta = load_calibration("beta")
        assert alpha["baseline"]["emoji_pct"] == 25.0
        assert beta["baseline"]["emoji_pct"] == 99.0


# ---------------------------------------------------------------------------
# get_few_shot_section — formatting
# ---------------------------------------------------------------------------

class TestGetFewShotSection:

    def test_returns_empty_string_when_no_examples(self):
        assert get_few_shot_section({}) == ""
        assert get_few_shot_section({"few_shot_examples": []}) == ""

    def test_formats_valid_examples(self):
        result = get_few_shot_section(SAMPLE_CAL)
        assert "Follower: Hola!" in result
        assert "Tú: Hola, qué tal todo?" in result
        assert "=== EJEMPLOS REALES DE CÓMO RESPONDES ===" in result
        assert "=== FIN EJEMPLOS ===" in result

    def test_includes_multiple_examples(self):
        result = get_few_shot_section(SAMPLE_CAL)
        follower_lines = [l for l in result.split("\n") if l.startswith("Follower:")]
        assert len(follower_lines) == 3  # All 3 from SAMPLE_CAL

    def test_respects_max_examples_limit(self):
        result = get_few_shot_section(SAMPLE_CAL, max_examples=1)
        follower_lines = [l for l in result.split("\n") if l.startswith("Follower:")]
        assert len(follower_lines) == 1
        assert "Hola!" in result
        assert "Cuánto cuesta?" not in result

    def test_default_max_is_five(self):
        many = {"few_shot_examples": [
            {"user_message": f"msg{i}", "response": f"resp{i}"}
            for i in range(10)
        ]}
        result = get_few_shot_section(many)
        follower_lines = [l for l in result.split("\n") if l.startswith("Follower:")]
        assert len(follower_lines) == 5

    def test_skips_examples_with_empty_user_message(self):
        cal = {"few_shot_examples": [
            {"user_message": "", "response": "Respuesta sin pregunta"},  # Skip
            {"user_message": "Buena pregunta", "response": "Claro"},    # Keep
        ]}
        result = get_few_shot_section(cal)
        follower_lines = [l for l in result.split("\n") if l.startswith("Follower:")]
        assert len(follower_lines) == 1
        assert "Buena pregunta" in result

    def test_skips_examples_with_empty_response(self):
        cal = {"few_shot_examples": [
            {"user_message": "Pregunta válida", "response": ""},  # Skip
            {"user_message": "Otra pregunta", "response": "Respuesta válida"},  # Keep
        ]}
        result = get_few_shot_section(cal)
        follower_lines = [l for l in result.split("\n") if l.startswith("Follower:")]
        assert len(follower_lines) == 1

    def test_includes_closing_instruction(self):
        result = get_few_shot_section(SAMPLE_CAL)
        assert "Responde de forma breve y natural" in result
