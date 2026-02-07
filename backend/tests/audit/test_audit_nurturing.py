"""Audit tests for core/nurturing.py"""

import tempfile

from core.nurturing import (
    FollowUp,
    NurturingManager,
    SequenceType,
    get_nurturing_manager,
    render_template,
)


class TestAuditNurturing:
    def test_import(self):
        from core.nurturing import FollowUp, NurturingManager, SequenceType  # noqa: F811

        assert SequenceType is not None

    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NurturingManager(storage_path=tmpdir)
            assert manager is not None

    def test_happy_path_render_template(self):
        result = render_template("Hola {name}", {"name": "Juan"})
        assert "Juan" in result

    def test_edge_case_sequence_types(self):
        types = list(SequenceType)
        assert len(types) >= 1

    def test_error_handling_get_pending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = NurturingManager(storage_path=tmpdir)
            pending = manager.get_pending_followups("test_creator")
            assert isinstance(pending, list)
