"""Audit tests for services/context_memory_service.py."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from services.context_memory_service import (
    ContextMemoryService,
    ConversationContext,
    get_context_memory_service,
)


class TestContextMemoryInit:
    """Test 1: init/import - Service and dataclass initialize correctly."""

    def test_conversation_context_defaults(self):
        ctx = ConversationContext(lead_id="l1")
        assert ctx.lead_id == "l1"
        assert ctx.lead_name is None
        assert ctx.recent_messages == []
        assert ctx.extracted_facts == {}
        assert ctx.relationship_type is None
        assert ctx.last_interaction is None
        assert ctx.topics_discussed == []

    def test_service_initializes_with_db_url(self):
        svc = ContextMemoryService(db_url="postgresql://test")
        assert svc.db_url == "postgresql://test"
        assert svc._engine is None

    @patch.dict("os.environ", {"DATABASE_URL": "postgresql://env_url"})
    def test_service_uses_env_var_fallback(self):
        svc = ContextMemoryService()
        assert svc.db_url == "postgresql://env_url"

    def test_singleton_returns_same_instance(self):
        import services.context_memory_service as mod

        mod._context_service = None
        s1 = get_context_memory_service()
        s2 = get_context_memory_service()
        assert s1 is s2
        mod._context_service = None  # cleanup

    def test_conversation_context_fields_are_mutable(self):
        ctx = ConversationContext(lead_id="l1")
        ctx.lead_name = "John"
        ctx.relationship_type = "CLIENTE"
        ctx.topics_discussed.append("yoga")
        assert ctx.lead_name == "John"
        assert ctx.relationship_type == "CLIENTE"
        assert "yoga" in ctx.topics_discussed


class TestContextStore:
    """Test 2: happy path - Context is stored and retrieved via to_prompt_context."""

    def test_to_prompt_context_with_lead_name(self):
        ctx = ConversationContext(lead_id="l1", lead_name="Maria")
        text = ctx.to_prompt_context()
        assert "Maria" in text

    def test_to_prompt_context_with_relationship(self):
        ctx = ConversationContext(lead_id="l1", relationship_type="AMISTAD_CERCANA")
        text = ctx.to_prompt_context()
        assert "AMISTAD_CERCANA" in text

    def test_to_prompt_context_with_facts(self):
        ctx = ConversationContext(
            lead_id="l1",
            extracted_facts={"location_mentioned": ["barcelona"]},
        )
        text = ctx.to_prompt_context()
        assert "barcelona" in text

    def test_to_prompt_context_with_messages(self):
        ctx = ConversationContext(
            lead_id="l1",
            recent_messages=[
                {"role": "user", "content": "Hola que tal"},
                {"role": "assistant", "content": "Muy bien!"},
            ],
        )
        text = ctx.to_prompt_context()
        assert "Hola que tal" in text
        assert "Muy bien!" in text
        assert "Lead" in text

    def test_to_prompt_context_with_topics(self):
        ctx = ConversationContext(lead_id="l1", topics_discussed=["fitness", "nutricion"])
        text = ctx.to_prompt_context()
        assert "fitness" in text
        assert "nutricion" in text


class TestContextRetrieval:
    """Test 3: edge case - load_conversation_context with mocked DB."""

    def _make_service(self):
        return ContextMemoryService(db_url="postgresql://test")

    @patch("sqlalchemy.create_engine")
    def test_load_context_returns_lead_name(self, mock_create_engine):
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_create_engine.return_value = mock_engine

        # Mock lead info query
        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("testuser", "Test User")),
            MagicMock(fetchall=lambda: []),
        ]

        svc = self._make_service()
        ctx = svc.load_conversation_context("l1", "c1")
        assert ctx.lead_name == "Test User"

    @patch("sqlalchemy.create_engine")
    def test_load_context_with_messages(self, mock_create_engine):
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_create_engine.return_value = mock_engine

        now = datetime.utcnow()
        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: ("user1", "User One")),
            MagicMock(
                fetchall=lambda: [
                    ("Hola!", "user", now),
                    ("Hey!", "assistant", now),
                ]
            ),
        ]

        svc = self._make_service()
        ctx = svc.load_conversation_context("l1", "c1")
        assert len(ctx.recent_messages) == 2

    def test_load_context_handles_db_error(self):
        svc = self._make_service()
        with patch.object(svc, "_get_engine", side_effect=Exception("DB down")):
            ctx = svc.load_conversation_context("l1", "c1")
        assert ctx.lead_id == "l1"
        assert ctx.recent_messages == []

    @patch("sqlalchemy.create_engine")
    def test_load_context_no_lead_found(self, mock_create_engine):
        mock_conn = MagicMock()
        mock_engine = MagicMock()
        mock_engine.connect.return_value.__enter__ = lambda s: mock_conn
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_create_engine.return_value = mock_engine

        mock_conn.execute.side_effect = [
            MagicMock(fetchone=lambda: None),
            MagicMock(fetchall=lambda: []),
        ]

        svc = self._make_service()
        ctx = svc.load_conversation_context("l1", "c1")
        assert ctx.lead_name is None

    def test_extract_facts_from_messages(self):
        svc = self._make_service()
        messages = [
            {"role": "user", "content": "Vivo en Barcelona y hago yoga"},
            {"role": "user", "content": "Tenemos clase mañana"},
        ]
        facts = svc._extract_facts_from_messages(messages)
        assert "location_mentioned" in facts
        assert "barcelona" in facts["location_mentioned"]
        assert "activity_mentioned" in facts
        assert "yoga" in facts["activity_mentioned"]


class TestExpiredContext:
    """Test 4: error handling - Empty messages and edge cases."""

    def test_to_prompt_context_empty_returns_empty_string(self):
        ctx = ConversationContext(lead_id="l1")
        text = ctx.to_prompt_context()
        assert text == ""

    def test_extract_facts_no_user_messages(self):
        svc = ContextMemoryService(db_url="postgresql://test")
        messages = [
            {"role": "assistant", "content": "Barcelona yoga gym mañana"},
        ]
        facts = svc._extract_facts_from_messages(messages)
        # Only user messages are analyzed, assistant is ignored
        assert facts == {}

    def test_extract_facts_empty_list(self):
        svc = ContextMemoryService(db_url="postgresql://test")
        facts = svc._extract_facts_from_messages([])
        assert facts == {}

    def test_to_prompt_context_limits_messages_to_ten(self):
        messages = [{"role": "user", "content": f"msg{i}"} for i in range(15)]
        ctx = ConversationContext(lead_id="l1", recent_messages=messages)
        text = ctx.to_prompt_context()
        # Only last 10 should appear (the method slices [-10:])
        assert "msg5" in text
        assert "msg14" in text

    def test_recent_summary_no_messages(self):
        svc = ContextMemoryService(db_url="postgresql://test")
        with patch.object(
            svc,
            "load_conversation_context",
            return_value=ConversationContext(lead_id="l1"),
        ):
            summary = svc.get_recent_summary("l1", "c1")
        assert summary == "Primera conversación con este lead."


class TestMemoryClear:
    """Test 5: integration check - get_recent_summary works end-to-end with mocks."""

    def test_recent_summary_with_name_and_message(self):
        svc = ContextMemoryService(db_url="postgresql://test")
        ctx = ConversationContext(
            lead_id="l1",
            lead_name="Ana",
            recent_messages=[
                {"role": "user", "content": "Me interesa el retiro de yoga en Barcelona"},
            ],
        )
        with patch.object(svc, "load_conversation_context", return_value=ctx):
            summary = svc.get_recent_summary("l1", "c1")
        assert "Ana" in summary
        assert "Me interesa el retiro" in summary

    def test_recent_summary_with_relationship(self):
        svc = ContextMemoryService(db_url="postgresql://test")
        ctx = ConversationContext(
            lead_id="l1",
            lead_name="Luis",
            relationship_type="CLIENTE",
            recent_messages=[
                {"role": "user", "content": "Hola"},
            ],
        )
        with patch.object(svc, "load_conversation_context", return_value=ctx):
            summary = svc.get_recent_summary("l1", "c1")
        assert "CLIENTE" in summary

    def test_recent_summary_no_user_messages(self):
        svc = ContextMemoryService(db_url="postgresql://test")
        ctx = ConversationContext(
            lead_id="l1",
            lead_name="Pedro",
            recent_messages=[
                {"role": "assistant", "content": "Hola Pedro!"},
            ],
        )
        with patch.object(svc, "load_conversation_context", return_value=ctx):
            summary = svc.get_recent_summary("l1", "c1")
        # Has a name but no user message found, just name part
        assert "Pedro" in summary

    def test_engine_lazy_init(self):
        """Engine is not created until _get_engine is called."""
        svc = ContextMemoryService(db_url="postgresql://test")
        assert svc._engine is None
        with patch("sqlalchemy.create_engine") as mock_ce:
            mock_ce.return_value = MagicMock()
            engine = svc._get_engine()
            assert engine is not None
            mock_ce.assert_called_once_with("postgresql://test")

    def test_engine_cached_after_first_call(self):
        svc = ContextMemoryService(db_url="postgresql://test")
        with patch("sqlalchemy.create_engine") as mock_ce:
            mock_engine = MagicMock()
            mock_ce.return_value = mock_engine
            e1 = svc._get_engine()
            e2 = svc._get_engine()
            assert e1 is e2
            mock_ce.assert_called_once()
