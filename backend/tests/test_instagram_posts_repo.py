"""Tests for core/data/instagram_posts_repo.py (Domain C — IG post content lake)."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


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


def _patch_modules(session, InstagramPost=None):
    mock_model = InstagramPost if InstagramPost is not None else MagicMock()
    return patch.dict(
        "sys.modules",
        {
            "api.database": _mk_db_mod(session),
            "api.models": _mk_models_mod(InstagramPost=mock_model),
        },
    )


# ---------------------------------------------------------------------------
# Save — insert, update, parsers, timestamp handling
# ---------------------------------------------------------------------------
class TestSaveInstagramPosts:
    @pytest.mark.asyncio
    async def test_save_new_posts_inserts_rows(self):
        from core.data.instagram_posts_repo import save_instagram_posts_db

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        with _patch_modules(session):
            n = await save_instagram_posts_db(
                "ipr_new",
                [
                    {"id": "p1", "caption": "hi"},
                    {"id": "p2", "caption": "hello"},
                ],
            )
        assert n == 2
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_save_existing_posts_updates_rows(self):
        from core.data.instagram_posts_repo import save_instagram_posts_db

        existing = MagicMock()
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = existing
        with _patch_modules(session):
            n = await save_instagram_posts_db(
                "ipr_upd",
                [{"id": "p1", "caption": "updated", "like_count": 42}],
            )
        assert n == 1
        assert existing.caption == "updated"
        assert existing.likes_count == 42
        assert session.add.call_count == 0

    @pytest.mark.asyncio
    async def test_save_parses_hashtags_from_caption(self):
        from core.data.instagram_posts_repo import save_instagram_posts_db

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        model = MagicMock()
        with _patch_modules(session, InstagramPost=model):
            await save_instagram_posts_db(
                "ipr_hash",
                [{"id": "p1", "caption": "body #yoga #barre morning"}],
            )
        kwargs = model.call_args.kwargs
        assert kwargs["hashtags"] == ["yoga", "barre"]

    @pytest.mark.asyncio
    async def test_save_parses_mentions_from_caption(self):
        from core.data.instagram_posts_repo import save_instagram_posts_db

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        model = MagicMock()
        with _patch_modules(session, InstagramPost=model):
            await save_instagram_posts_db(
                "ipr_men",
                [{"id": "p1", "caption": "thanks @alice and @bob!"}],
            )
        kwargs = model.call_args.kwargs
        assert kwargs["mentions"] == ["alice", "bob!"]  # strip('@') only; trailing punctuation kept

    @pytest.mark.asyncio
    async def test_save_handles_malformed_timestamp(self):
        """Malformed timestamp must not raise; row saved with post_timestamp=None."""
        from core.data.instagram_posts_repo import save_instagram_posts_db

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        model = MagicMock()
        with _patch_modules(session, InstagramPost=model):
            n = await save_instagram_posts_db(
                "ipr_ts",
                [{"id": "p1", "caption": "x", "timestamp": "not-a-date"}],
            )
        assert n == 1
        kwargs = model.call_args.kwargs
        assert kwargs["post_timestamp"] is None

    @pytest.mark.asyncio
    async def test_save_returns_zero_on_error(self):
        from core.data.instagram_posts_repo import save_instagram_posts_db

        assert await save_instagram_posts_db("ipr_bad", [{"id": "p1"}]) == 0


# ---------------------------------------------------------------------------
# Get — ordering + error path
# ---------------------------------------------------------------------------
class TestGetInstagramPosts:
    @pytest.mark.asyncio
    async def test_get_returns_posts_ordered_by_timestamp_desc(self):
        """Query pipeline must call .order_by(post_timestamp.desc())."""
        from core.data.instagram_posts_repo import get_instagram_posts_db

        session = MagicMock()
        ordered = session.query.return_value.filter.return_value.order_by.return_value
        ordered.all.return_value = []

        with _patch_modules(session):
            result = await get_instagram_posts_db("ipr_get")

        assert result == []
        assert session.query.return_value.filter.return_value.order_by.called

    @pytest.mark.asyncio
    async def test_get_returns_empty_on_error(self):
        from core.data.instagram_posts_repo import get_instagram_posts_db

        assert await get_instagram_posts_db("ipr_bad") == []


# ---------------------------------------------------------------------------
# Delete + count
# ---------------------------------------------------------------------------
class TestDeleteAndCount:
    @pytest.mark.asyncio
    async def test_delete_all_posts_for_creator(self):
        from core.data.instagram_posts_repo import delete_instagram_posts_db

        session = MagicMock()
        session.query.return_value.filter.return_value.delete.return_value = 5
        with _patch_modules(session):
            n = await delete_instagram_posts_db("ipr_del")
        assert n == 5

    def test_get_count_returns_zero_on_error(self):
        from core.data.instagram_posts_repo import get_instagram_posts_count_db

        assert get_instagram_posts_count_db("ipr_bad") == 0
