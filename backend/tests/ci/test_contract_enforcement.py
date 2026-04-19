"""
Tests for scripts/ci/contract_enforcement.py — ARC5 Phase 5.

Each test uses a temporary directory with synthetic Python files so the suite
is fast and hermetic (no dependency on current codebase state).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.ci.contract_enforcement import (
    CheckResult,
    Violation,
    check1_direct_metadata_assignment,
    check2_counter_without_emit_metric,
    check3_define_but_never_read,
    check4_magic_numbers,
    run_all_checks,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def write_py(tmp_path: Path, rel: str, source: str) -> Path:
    """Write a Python file under tmp_path, creating parent dirs."""
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(source), encoding="utf-8")
    return p


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1 — Direct metadata assignment
# ─────────────────────────────────────────────────────────────────────────────

def test_detects_direct_metadata_assignment(tmp_path):
    write_py(tmp_path, "core/dm/phases/detection.py", """
        def run(msg):
            msg.metadata["detection_ts"] = "2026-01-01"
    """)
    result = check1_direct_metadata_assignment(tmp_path)
    assert result.has_errors, "Expected error for direct metadata assignment"
    assert any("detection_ts" in v.message for v in result.violations)


def test_detects_metadata_update(tmp_path):
    write_py(tmp_path, "core/dm/agent.py", """
        def update(msg, ts):
            msg.metadata.update({"foo": ts, "bar": 1})
    """)
    result = check1_direct_metadata_assignment(tmp_path)
    assert result.has_errors


def test_allows_typed_metadata_setter(tmp_path):
    write_py(tmp_path, "core/dm/phases/detection.py", """
        from core.metadata.serdes import write_metadata
        from core.metadata.models import DetectionMetadata

        def run(msg):
            write_metadata(msg, DetectionMetadata(...))
    """)
    result = check1_direct_metadata_assignment(tmp_path)
    assert not result.has_errors, "Typed setter should not trigger CHECK 1"


def test_allows_metadata_assignment_in_tests(tmp_path):
    write_py(tmp_path, "tests/unit/test_something.py", """
        def test_thing():
            msg.metadata["key"] = "value"
    """)
    result = check1_direct_metadata_assignment(tmp_path)
    # tests/ is excluded
    assert not result.violations


def test_allows_metadata_assignment_in_scripts(tmp_path):
    write_py(tmp_path, "scripts/backfill_something.py", """
        def backfill():
            msg.metadata["key"] = "value"
    """)
    result = check1_direct_metadata_assignment(tmp_path)
    assert not result.violations


def test_noqa_annotation_suppresses_check1(tmp_path):
    write_py(tmp_path, "core/dm/agent.py", """
        def run(msg):
            msg.metadata["foo"] = "bar"  # noqa: contract
    """)
    result = check1_direct_metadata_assignment(tmp_path)
    assert not result.violations


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2 — Counter/Gauge/Histogram without emit_metric
# ─────────────────────────────────────────────────────────────────────────────

def test_detects_counter_without_emit_metric(tmp_path):
    write_py(tmp_path, "services/some_service.py", """
        from prometheus_client import Counter

        MY_COUNTER = Counter("my_counter", "some counter", ["creator_id"])

        def do_thing():
            MY_COUNTER.labels(creator_id="iris").inc()
    """)
    result = check2_counter_without_emit_metric(tmp_path)
    assert result.violations, "Expected warning for Counter without emit_metric"
    assert not any(v.is_error for v in result.violations), "Should be warning, not error"


def test_allows_emit_metric_usage(tmp_path):
    write_py(tmp_path, "services/some_service.py", """
        from prometheus_client import Counter
        from core.observability.metrics import emit_metric

        def do_thing():
            emit_metric("my_counter", creator_id="iris")
    """)
    result = check2_counter_without_emit_metric(tmp_path)
    assert not result.violations, "emit_metric usage should satisfy CHECK 2"


def test_allows_metrics_registry_file(tmp_path):
    """core/observability/metrics.py is exempt — it IS the registry."""
    write_py(tmp_path, "core/observability/metrics.py", """
        from prometheus_client import Counter, Gauge, Histogram

        MY_COUNTER = Counter("x", "y", [])
    """)
    result = check2_counter_without_emit_metric(tmp_path)
    assert not result.violations


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3 — Define-but-never-read metadata fields
# ─────────────────────────────────────────────────────────────────────────────

def _write_minimal_models(tmp_path: Path) -> None:
    write_py(tmp_path, "core/metadata/models.py", """
        from pydantic import BaseModel
        from typing import Optional

        class DetectionMetadata(BaseModel):
            detection_ts: str
            confidence: float

        class ScoringMetadata(BaseModel):
            score_after: float
            orphan_field: Optional[str] = None

        class GenerationMetadata(BaseModel):
            generation_model: str

        class PostGenMetadata(BaseModel):
            safety_status: str
    """)


def test_detects_define_but_never_read(tmp_path):
    _write_minimal_models(tmp_path)
    # orphan_field is declared in ScoringMetadata but never used elsewhere
    write_py(tmp_path, "services/lead_scoring.py", """
        def score(msg):
            x = msg.metadata.get("score_after")
    """)
    result = check3_define_but_never_read(tmp_path)
    orphan_violations = [v for v in result.violations if "orphan_field" in v.message]
    assert orphan_violations, "orphan_field should be detected as define-but-never-read"


def test_no_violation_when_field_is_read(tmp_path):
    _write_minimal_models(tmp_path)
    # Provide readers for all fields
    write_py(tmp_path, "services/pipeline.py", """
        def process(meta):
            ts = meta.detection_ts
            conf = meta.confidence
            score = meta.score_after
            model = meta.generation_model
            status = meta.safety_status
    """)
    result = check3_define_but_never_read(tmp_path)
    # orphan_field from ScoringMetadata won't have a reader, so may still fire
    # — only asserting the non-orphan fields do NOT fire
    non_orphan_violations = [v for v in result.violations if "orphan_field" not in v.message]
    assert not non_orphan_violations, f"Unexpected violations: {non_orphan_violations}"


def test_no_violation_when_emit_metric_used(tmp_path):
    _write_minimal_models(tmp_path)
    write_py(tmp_path, "services/pipeline.py", """
        from core.observability.metrics import emit_metric

        def track(meta):
            emit_metric("orphan_field")
            ts = meta.detection_ts
            conf = meta.confidence
            score = meta.score_after
            model = meta.generation_model
            status = meta.safety_status
    """)
    result = check3_define_but_never_read(tmp_path)
    assert not result.violations


def test_gracefully_handles_missing_models_file(tmp_path):
    """If core/metadata/models.py doesn't exist, CHECK 3 should be a no-op."""
    result = check3_define_but_never_read(tmp_path)
    assert not result.violations


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 4 — Magic numbers in pipeline code
# ─────────────────────────────────────────────────────────────────────────────

def test_detects_magic_number_in_pipeline(tmp_path):
    write_py(tmp_path, "core/dm/agent.py", """
        def process(msg):
            if len(msg.content) > 4096:
                truncate(msg)
    """)
    result = check4_magic_numbers(tmp_path)
    assert result.violations, "Expected warning for magic number 4096"
    assert not any(v.is_error for v in result.violations), "Should be warning, not error"


def test_allows_magic_number_in_test_files(tmp_path):
    """test files are NOT in core/dm, so CHECK 4 (which only scans CHECK4_SCAN_DIRS) ignores them."""
    write_py(tmp_path, "tests/unit/test_dm.py", """
        def test_thing():
            assert len(x) == 4096
    """)
    result = check4_magic_numbers(tmp_path)
    assert not result.violations, "test files are outside CHECK4 scan dirs"


def test_whitelist_numbers_not_flagged(tmp_path):
    write_py(tmp_path, "core/dm/agent.py", """
        def process(items):
            for i in range(0, len(items), 1):
                if i == -1:
                    break
                if i == 100:
                    stop()
    """)
    result = check4_magic_numbers(tmp_path)
    # 0, 1, -1, 100 are whitelisted
    assert not result.violations


def test_noqa_suppresses_magic_number(tmp_path):
    write_py(tmp_path, "core/dm/agent.py", """
        MAX_CHARS = 4096  # noqa: contract
        def process(msg):
            if len(msg.content) > MAX_CHARS:
                pass
    """)
    result = check4_magic_numbers(tmp_path)
    assert not result.violations


# ─────────────────────────────────────────────────────────────────────────────
# Strict vs non-strict mode
# ─────────────────────────────────────────────────────────────────────────────

def test_strict_mode_fails_on_check1_violations(tmp_path):
    """--strict should return exit code 1 when CHECK 1 has errors."""
    _write_minimal_models(tmp_path)
    # Add a CHECK 1 violation in core/dm/
    write_py(tmp_path, "core/dm/agent.py", """
        def run(msg):
            msg.metadata["foo"] = "bar"
    """)
    # Provide readers for all model fields so CHECK 3 doesn't also fail
    write_py(tmp_path, "services/readers.py", """
        def read(meta):
            ts = meta.detection_ts
            conf = meta.confidence
            score = meta.score_after
            orphan = meta.orphan_field
            model = meta.generation_model
            status = meta.safety_status
    """)
    exit_code = run_all_checks(root=tmp_path, strict=True)
    assert exit_code == 1, "Strict mode must return 1 on CHECK 1 error"


def test_non_strict_mode_warns_only(tmp_path):
    """Without --strict, even violations produce exit code 0."""
    _write_minimal_models(tmp_path)
    write_py(tmp_path, "core/dm/agent.py", """
        def run(msg):
            msg.metadata["foo"] = "bar"
    """)
    write_py(tmp_path, "services/readers.py", """
        def read(meta):
            ts = meta.detection_ts
            conf = meta.confidence
            score = meta.score_after
            orphan = meta.orphan_field
            model = meta.generation_model
            status = meta.safety_status
    """)
    exit_code = run_all_checks(root=tmp_path, strict=False)
    assert exit_code == 0, "Non-strict mode must always return 0"


def test_strict_mode_passes_clean_codebase(tmp_path):
    """Clean codebase should always exit 0 in strict mode."""
    _write_minimal_models(tmp_path)
    write_py(tmp_path, "core/dm/agent.py", """
        from core.metadata.serdes import write_metadata
        from core.metadata.models import DetectionMetadata
        from core.observability.metrics import emit_metric

        def run(msg):
            write_metadata(msg, DetectionMetadata(...))
    """)
    write_py(tmp_path, "services/readers.py", """
        def read(meta):
            ts = meta.detection_ts
            conf = meta.confidence
            score = meta.score_after
            orphan = meta.orphan_field
            model = meta.generation_model
            status = meta.safety_status
    """)
    exit_code = run_all_checks(root=tmp_path, strict=True)
    assert exit_code == 0
