"""
Tests for System C: StyleRetriever (services/style_retriever.py)
8 tests covering embedding retrieval, fallback, quality gate, language filter, and backward compat.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest


class TestRetrieveWithEmbeddings:
    """retrieve() uses embedding similarity when >= 3 embeddings exist."""

    @pytest.mark.asyncio
    @patch("api.database.engine")
    @patch("api.database.SessionLocal")
    async def test_retrieve_with_embeddings(self, mock_session_cls, mock_engine):
        from services.style_retriever import retrieve

        # Mock: 5 embeddings exist
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.return_value.filter.return_value.count.return_value = 5
        mock_session.close = MagicMock()

        # Mock embedding generation
        with patch("services.style_retriever._embed_text") as mock_embed:
            mock_embed.return_value = [0.1] * 1536

            # Mock SQL similarity query
            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_conn.execute.return_value.fetchall.return_value = [
                (uuid.uuid4(), "Gràcies per escriure!", "greeting", 0.85, 0.92),
                (uuid.uuid4(), "T'envio el link!", "sales", 0.80, 0.88),
            ]

            result = await retrieve(
                creator_db_id=uuid.uuid4(),
                user_message="Hola que tal?",
                language="ca",
            )

        assert isinstance(result, list)
        assert len(result) == 2
        assert "creator_response" in result[0]
        assert "similarity" in result[0]
        assert result[0]["similarity"] >= result[1]["similarity"]


class TestRetrieveFallbackNoEmbeddings:
    """retrieve() falls back to keyword scoring when < 3 embeddings exist."""

    @pytest.mark.asyncio
    @patch("api.database.SessionLocal")
    async def test_retrieve_fallback_no_embeddings(self, mock_session_cls):
        from services.style_retriever import retrieve

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.return_value.filter.return_value.count.return_value = 1  # < 3
        mock_session.close = MagicMock()

        with patch("services.style_retriever.get_matching_examples") as mock_keyword:
            mock_keyword.return_value = [{"creator_response": "Hola!", "intent": "greeting", "quality_score": 0.8}]

            result = await retrieve(
                creator_db_id=uuid.uuid4(),
                user_message="Hola?",
            )

        mock_keyword.assert_called_once()
        assert len(result) == 1


class TestRetrieveQualityGate:
    """retrieve() excludes examples with quality_score < 0.6."""

    @pytest.mark.asyncio
    @patch("api.database.engine")
    @patch("api.database.SessionLocal")
    async def test_retrieve_quality_gate(self, mock_session_cls, mock_engine):
        from services.style_retriever import retrieve

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.return_value.filter.return_value.count.return_value = 5
        mock_session.close = MagicMock()

        with patch("services.style_retriever._embed_text") as mock_embed:
            mock_embed.return_value = [0.1] * 1536

            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            # Only high-quality result (quality=0.85 >= 0.6)
            mock_conn.execute.return_value.fetchall.return_value = [
                (uuid.uuid4(), "Alta qualitat!", "greeting", 0.85, 0.91),
            ]

            result = await retrieve(
                creator_db_id=uuid.uuid4(),
                user_message="Hola!",
            )

        # Verify the SQL query included quality filter (check call args)
        call_args = mock_conn.execute.call_args
        sql_str = str(call_args[0][0])
        assert "quality_score" in sql_str
        assert len(result) == 1


class TestRetrieveLanguageFilter:
    """retrieve() filters by language when specified."""

    @pytest.mark.asyncio
    @patch("api.database.engine")
    @patch("api.database.SessionLocal")
    async def test_retrieve_language_filter(self, mock_session_cls, mock_engine):
        from services.style_retriever import retrieve

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.return_value.filter.return_value.count.return_value = 5
        mock_session.close = MagicMock()

        with patch("services.style_retriever._embed_text") as mock_embed:
            mock_embed.return_value = [0.1] * 1536

            mock_conn = MagicMock()
            mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            # CA response passes; ES response filtered out
            mock_conn.execute.return_value.fetchall.return_value = [
                (uuid.uuid4(), "Gràcies per escriure!", "greeting", 0.85, 0.92),  # CA — passes
                (uuid.uuid4(), "Muchas gracias por escribir!", "greeting", 0.80, 0.88),  # ES — filtered
            ]

            result = await retrieve(
                creator_db_id=uuid.uuid4(),
                user_message="Hola!",
                language="ca",
                max_examples=3,
            )

        # Only the CA example should pass
        assert len(result) == 1
        assert "Gràcies" in result[0]["creator_response"]


class TestCreateGoldExampleWithEmbedding:
    """create_gold_example generates embedding on creation."""

    @patch("api.database.SessionLocal")
    def test_create_gold_example_with_embedding(self, mock_session_cls):
        from services.style_retriever import create_gold_example

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = None  # no existing

        captured_example = {}
        def capture_add(obj):
            captured_example["obj"] = obj
            obj.id = uuid.uuid4()
        mock_session.add.side_effect = capture_add

        with patch("services.style_retriever._embed_text") as mock_embed:
            mock_embed.return_value = [0.1] * 1536

            result = create_gold_example(
                creator_db_id=uuid.uuid4(),
                user_message="Com et trobes?",
                creator_response="Molt bé! Gràcies per preguntar.",
                intent="greeting",
                source="approved",
            )

        assert result is not None
        assert result.get("created") is True
        mock_embed.assert_called_once()
        assert captured_example["obj"].embedding == [0.1] * 1536


class TestEnsureEmbeddingsBackfill:
    """ensure_embeddings() backfills embedding for examples without one."""

    @patch("api.database.SessionLocal")
    def test_ensure_embeddings_backfill(self, mock_session_cls):
        from services.style_retriever import ensure_embeddings

        ex1 = MagicMock()
        ex1.creator_response = "Hola! Com puc ajudar-te?"
        ex1.embedding = None

        ex2 = MagicMock()
        ex2.creator_response = "Gràcies per escriure!"
        ex2.embedding = None

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [ex1, ex2]

        with patch("services.style_retriever._embed_text") as mock_embed:
            mock_embed.return_value = [0.2] * 1536

            count = ensure_embeddings(uuid.uuid4(), batch_size=50)

        assert count == 2
        assert ex1.embedding == [0.2] * 1536
        assert ex2.embedding == [0.2] * 1536
        mock_session.commit.assert_called_once()


class TestCurateExamplesUnchanged:
    """curate_examples() still works (logic unchanged from gold_examples_service)."""

    @pytest.mark.asyncio
    @patch("api.database.SessionLocal")
    async def test_curate_examples_unchanged(self, mock_session_cls):
        from services.style_retriever import curate_examples

        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        # No rows to process
        mock_session.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        # Count > 10 → skip historical mining
        mock_session.query.return_value.filter.return_value.count.return_value = 15

        result = await curate_examples("iris_bertran", uuid.uuid4())

        assert result["status"] == "done"
        assert "created" in result
        assert "expired" in result


class TestBackwardCompatImportsStyleRetriever:
    """from services.gold_examples_service import ... still works via re-export shim."""

    def test_backward_compat_gold_examples_service(self):
        from services.gold_examples_service import (
            _SOURCE_QUALITY,
            create_gold_example,
            curate_examples,
            detect_language,
            ensure_embeddings,
            get_matching_examples,
            mine_historical_examples,
            retrieve,
        )

        assert callable(create_gold_example)
        assert callable(get_matching_examples)
        assert callable(detect_language)
        assert callable(mine_historical_examples)
        assert callable(curate_examples)
        assert callable(retrieve)
        assert callable(ensure_embeddings)
        assert isinstance(_SOURCE_QUALITY, dict)

    def test_detect_language_still_works(self):
        from services.gold_examples_service import detect_language

        assert detect_language("Gràcies però no puc") == "ca"
        assert detect_language("Muchas gracias pero no puedo") == "es"
        assert detect_language("Gràcies però muchas gracias") == "mixto"
        assert detect_language("Hello there") == "unknown"
