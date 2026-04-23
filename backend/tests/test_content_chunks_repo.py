"""Tests for core/data/content_chunks_repo.py (Domain B — RAG chunks)."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_db(first_return=None):
    """Build a MagicMock session whose first() returns `first_return` and
    whose query().filter().delete() returns an int we can assert later."""
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = first_return
    return session


def _patch_sys_modules(session, model_name="ContentChunk"):
    @contextmanager
    def fake_session():
        yield session

    mock_db = MagicMock()
    mock_db.get_db_session = fake_session
    mock_models = MagicMock()
    setattr(mock_models, model_name, MagicMock())
    return patch.dict("sys.modules", {"api.database": mock_db, "api.models": mock_models})


# ---------------------------------------------------------------------------
# Save — insert + update + metadata
# ---------------------------------------------------------------------------
class TestSaveContentChunks:
    @pytest.mark.asyncio
    async def test_save_new_chunks_inserts_rows(self):
        from core.data.content_chunks_repo import save_content_chunks_db

        session = _make_mock_db(first_return=None)  # no existing
        with _patch_sys_modules(session):
            n = await save_content_chunks_db(
                "ccr_save",
                [
                    {"id": "c1", "content": "hello", "source_type": "instagram_post"},
                    {"id": "c2", "content": "world", "source_type": "youtube"},
                ],
            )
        assert n == 2
        assert session.add.call_count == 2
        session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_existing_chunks_updates_rows(self):
        from core.data.content_chunks_repo import save_content_chunks_db

        existing = MagicMock()
        session = _make_mock_db(first_return=existing)
        with _patch_sys_modules(session):
            n = await save_content_chunks_db(
                "ccr_update",
                [{"id": "c1", "content": "updated"}],
            )
        assert n == 1
        assert existing.content == "updated"
        assert session.add.call_count == 0

    @pytest.mark.asyncio
    async def test_save_preserves_metadata_as_extra_data(self):
        """Regression: DB column was renamed metadata → extra_data (commit 0264a352)."""
        from core.data.content_chunks_repo import save_content_chunks_db

        session = _make_mock_db(first_return=None)
        mock_model = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "api.database": _mk_db_mod(session),
                "api.models": _mk_models_mod(ContentChunk=mock_model),
            },
        ):
            await save_content_chunks_db(
                "ccr_meta",
                [{"id": "c1", "content": "x", "metadata": {"foo": "bar"}}],
            )
        kwargs = mock_model.call_args.kwargs
        assert kwargs["extra_data"] == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_save_returns_zero_on_error(self):
        from core.data.content_chunks_repo import save_content_chunks_db

        n = await save_content_chunks_db("ccr_bad", [{"id": "c1"}])
        assert n == 0


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------
class TestGetContentChunks:
    @pytest.mark.asyncio
    async def test_get_returns_all_chunks_for_creator(self):
        from core.data.content_chunks_repo import get_content_chunks_db

        row = MagicMock()
        row.chunk_id = "c1"
        row.creator_id = "ccr_get"
        row.content = "hello"
        row.source_type = "instagram_post"
        row.source_id = "post1"
        row.source_url = "https://x/1"
        row.title = "t"
        row.chunk_index = 0
        row.total_chunks = 1
        row.extra_data = {"foo": "bar"}
        row.created_at = None

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [row]

        with _patch_sys_modules(session):
            result = await get_content_chunks_db("ccr_get")

        assert len(result) == 1
        assert result[0]["id"] == "c1"
        assert result[0]["metadata"] == {"foo": "bar"}  # API shape stays "metadata"

    @pytest.mark.asyncio
    async def test_get_returns_empty_on_error(self):
        from core.data.content_chunks_repo import get_content_chunks_db

        assert await get_content_chunks_db("ccr_bad") == []


# ---------------------------------------------------------------------------
# Delete — with / without source_type filter
# ---------------------------------------------------------------------------
class TestDeleteContentChunks:
    @pytest.mark.asyncio
    async def test_delete_all_chunks_for_creator(self):
        from core.data.content_chunks_repo import delete_content_chunks_db

        session = MagicMock()
        session.query.return_value.filter.return_value.delete.return_value = 3
        with _patch_sys_modules(session):
            n = await delete_content_chunks_db("ccr_del")
        assert n == 3

    @pytest.mark.asyncio
    async def test_delete_only_source_type_filter(self):
        """Verifies the source_type= filter (regression trap for YouTube vs IG separation)."""
        from core.data.content_chunks_repo import delete_content_chunks_db

        session = MagicMock()
        filter_chain = session.query.return_value.filter.return_value.filter.return_value
        filter_chain.delete.return_value = 2

        with _patch_sys_modules(session):
            n = await delete_content_chunks_db("ccr_del_src", source_type="youtube")
        assert n == 2
        # filter called twice: once for creator_id, once for source_type
        assert session.query.return_value.filter.return_value.filter.called

    @pytest.mark.asyncio
    async def test_delete_returns_zero_on_error(self):
        from core.data.content_chunks_repo import delete_content_chunks_db

        assert await delete_content_chunks_db("ccr_bad") == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mk_db_mod(session):
    @contextmanager
    def fake_session():
        yield session

    m = MagicMock()
    m.get_db_session = fake_session
    return m


def _mk_models_mod(**entities):
    m = MagicMock()
    for name, entity in entities.items():
        setattr(m, name, entity)
    return m
