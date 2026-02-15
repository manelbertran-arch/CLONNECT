#!/usr/bin/env python3
"""
Tests for AudienceProfileBuilder (SPRINT1-T1.2)

TDD: These tests are written BEFORE implementation.
Goal: Build audience profiles with:
- Narrative context ("Madre de 3, quiere bajar peso...")
- Auto-detected segments (hot_lead, ghost, price_objector...)
- Action recommendations ("Envíale el link de pago")
- Objection suggestions
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock


class TestAudienceProfileBuilderImport:
    """Test that the module can be imported."""

    def test_module_imports(self):
        """AudienceProfileBuilder should be importable."""
        from core.audience_intelligence import AudienceProfileBuilder
        assert AudienceProfileBuilder is not None

    def test_audience_profile_dataclass_imports(self):
        """AudienceProfile dataclass should be importable."""
        from core.audience_intelligence import AudienceProfile
        assert AudienceProfile is not None


class TestBuildProfile:
    """Tests for the build_profile method."""

    @pytest.mark.asyncio
    async def test_build_profile_returns_complete_profile(self):
        """build_profile should return an AudienceProfile with all fields."""
        from core.audience_intelligence import AudienceProfileBuilder, AudienceProfile

        # Create mock session
        mock_session = MagicMock()

        builder = AudienceProfileBuilder(creator_id="test_creator", db=mock_session)

        # Mock the internal data fetching
        builder._fetch_follower_data = AsyncMock(return_value={
            "follower_id": "ig_123",
            "username": "testuser",
            "name": "Maria Garcia",
            "total_messages": 15,
            "purchase_intent_score": 0.75,
            "is_customer": False,
            "is_lead": True,
            "interests": ["fitness", "nutrition"],
            "objections_raised": ["precio"],
            "objections_handled": [],
            "last_contact": datetime.now().isoformat(),
            "funnel_phase": "propuesta",
            "funnel_context": {"pain_points": ["time", "weight"], "goals": ["lose weight"]},
            "last_messages": [{"role": "user", "content": "cuanto cuesta?"}],
        })

        profile = await builder.build_profile("ig_123")

        assert isinstance(profile, AudienceProfile)
        assert profile.follower_id == "ig_123"
        assert profile.username == "testuser"
        assert profile.narrative is not None
        assert len(profile.segments) > 0
        assert profile.recommended_action is not None
        assert profile.action_priority is not None


class TestSegmentDetection:
    """Tests for segment detection logic."""

    def test_detects_hot_lead_segment(self):
        """Should detect hot_lead when high intent + late funnel phase."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        # Create mock profile data
        profile_data = MagicMock()
        profile_data.purchase_intent_score = 0.85
        profile_data.funnel_phase = "propuesta"
        profile_data.is_customer = False
        profile_data.total_messages = 10
        profile_data.days_inactive = 1
        profile_data.last_message_role = "user"
        profile_data.objections_raised = []

        segments = builder._detect_segments(profile_data)

        assert "hot_lead" in segments

    def test_detects_ghost_segment(self):
        """Should detect ghost when inactive >7 days and last msg was bot."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        profile_data = MagicMock()
        profile_data.purchase_intent_score = 0.5
        profile_data.funnel_phase = "cualificacion"
        profile_data.is_customer = False
        profile_data.total_messages = 8
        profile_data.days_inactive = 10
        profile_data.last_message_role = "assistant"
        profile_data.objections_raised = []

        segments = builder._detect_segments(profile_data)

        assert "ghost" in segments

    def test_detects_price_objector_segment(self):
        """Should detect price_objector when 'precio' in objections."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        profile_data = MagicMock()
        profile_data.purchase_intent_score = 0.5
        profile_data.funnel_phase = "objeciones"
        profile_data.is_customer = False
        profile_data.total_messages = 12
        profile_data.days_inactive = 2
        profile_data.last_message_role = "user"
        profile_data.objections_raised = ["precio", "tiempo"]

        segments = builder._detect_segments(profile_data)

        assert "price_objector" in segments

    def test_detects_customer_segment(self):
        """Should detect customer when is_customer=True."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        profile_data = MagicMock()
        profile_data.purchase_intent_score = 0.9
        profile_data.funnel_phase = "cierre"
        profile_data.is_customer = True
        profile_data.total_messages = 20
        profile_data.days_inactive = 0
        profile_data.last_message_role = "user"
        profile_data.objections_raised = []

        segments = builder._detect_segments(profile_data)

        assert "customer" in segments

    def test_detects_new_segment(self):
        """Should detect new when total_messages < 3."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        profile_data = MagicMock()
        profile_data.purchase_intent_score = 0.1
        profile_data.funnel_phase = "inicio"
        profile_data.is_customer = False
        profile_data.total_messages = 2
        profile_data.days_inactive = 0
        profile_data.last_message_role = "user"
        profile_data.objections_raised = []

        segments = builder._detect_segments(profile_data)

        assert "new" in segments


class TestActionRecommendations:
    """Tests for action recommendation logic."""

    def test_recommends_send_payment_for_ready_buyer(self):
        """Should recommend sending payment link for hot leads in cierre phase."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        profile_data = MagicMock()
        profile_data.purchase_intent_score = 0.9
        profile_data.funnel_phase = "cierre"
        profile_data.is_customer = False
        profile_data.segments = ["hot_lead"]
        profile_data.objections_raised = []
        profile_data.objections_handled = []

        action, priority = builder._recommend_action(profile_data)

        assert "pago" in action.lower() or "link" in action.lower() or "cerrar" in action.lower()
        assert priority in ["high", "urgent"]

    def test_recommends_handle_objection_if_pending(self):
        """Should recommend handling objection when objections exist."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        profile_data = MagicMock()
        profile_data.purchase_intent_score = 0.5
        profile_data.funnel_phase = "objeciones"
        profile_data.is_customer = False
        profile_data.segments = ["price_objector"]
        profile_data.objections_raised = ["precio"]
        profile_data.objections_handled = []

        action, priority = builder._recommend_action(profile_data)

        assert "objeci" in action.lower() or "precio" in action.lower()
        assert priority in ["medium", "high"]

    def test_recommends_reactivate_if_ghost(self):
        """Should recommend reactivation for ghost leads."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        profile_data = MagicMock()
        profile_data.purchase_intent_score = 0.4
        profile_data.funnel_phase = "cualificacion"
        profile_data.is_customer = False
        profile_data.segments = ["ghost"]
        profile_data.objections_raised = []
        profile_data.objections_handled = []
        profile_data.days_inactive = 10

        action, priority = builder._recommend_action(profile_data)

        assert "reactiv" in action.lower() or "seguimiento" in action.lower() or "contactar" in action.lower()


class TestNarrativeGeneration:
    """Tests for narrative generation."""

    def test_generates_narrative_from_context(self):
        """Should generate human-readable narrative from profile context."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        profile_data = MagicMock()
        profile_data.name = "Maria Garcia"
        profile_data.funnel_context = {
            "pain_points": ["falta de tiempo", "sobrepeso"],
            "goals": ["bajar de peso", "sentirse mejor"],
            "family": "madre de 3",
        }
        profile_data.interests = ["fitness", "nutrition"]
        profile_data.objections_raised = ["precio"]

        narrative = builder._generate_narrative(profile_data)

        assert isinstance(narrative, str)
        assert len(narrative) > 20  # Should be a meaningful sentence
        # Should mention some context
        assert any(word in narrative.lower() for word in ["maria", "tiempo", "peso", "madre", "fitness"])


class TestObjectionSuggestions:
    """Tests for objection handling suggestions."""

    def test_adds_suggestion_to_each_objection(self):
        """Should add a suggestion for each objection type."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        raised = ["precio", "tiempo"]
        handled = ["precio"]

        objections = builder._build_objections_with_suggestions(raised, handled)

        assert len(objections) == 2

        # Find precio objection
        precio_obj = next((o for o in objections if o["type"] == "precio"), None)
        assert precio_obj is not None
        assert precio_obj["handled"] is True
        assert "suggestion" in precio_obj
        assert len(precio_obj["suggestion"]) > 10

        # Find tiempo objection
        tiempo_obj = next((o for o in objections if o["type"] == "tiempo"), None)
        assert tiempo_obj is not None
        assert tiempo_obj["handled"] is False
        assert "suggestion" in tiempo_obj

    def test_unknown_objection_gets_generic_suggestion(self):
        """Unknown objection types should get a generic suggestion."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        raised = ["unknown_objection_xyz"]
        handled = []

        objections = builder._build_objections_with_suggestions(raised, handled)

        assert len(objections) == 1
        assert objections[0]["type"] == "unknown_objection_xyz"
        assert "suggestion" in objections[0]


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_handles_missing_conversation_state(self):
        """Should handle gracefully when conversation_state is missing."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        # Mock with missing funnel data
        builder._fetch_follower_data = AsyncMock(return_value={
            "follower_id": "ig_123",
            "username": "testuser",
            "total_messages": 5,
            "purchase_intent_score": 0.3,
            "is_customer": False,
            "is_lead": False,
            "interests": [],
            "objections_raised": [],
            "objections_handled": [],
            "last_contact": datetime.now().isoformat(),
            "funnel_phase": None,  # Missing
            "funnel_context": {},  # Empty
            "last_messages": [],
        })

        profile = await builder.build_profile("ig_123")

        assert profile is not None
        assert profile.funnel_phase is None or profile.funnel_phase == "inicio"

    @pytest.mark.asyncio
    async def test_handles_missing_user_profile(self):
        """Should handle gracefully when user_profile is missing."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        # Mock with missing preferences
        builder._fetch_follower_data = AsyncMock(return_value={
            "follower_id": "ig_456",
            "username": "user2",
            "total_messages": 3,
            "purchase_intent_score": 0.2,
            "is_customer": False,
            "is_lead": False,
            "interests": [],
            "objections_raised": [],
            "objections_handled": [],
            "last_contact": datetime.now().isoformat(),
            "funnel_phase": "inicio",
            "funnel_context": {},
            "last_messages": [],
            "weighted_interests": {},  # Empty
            "preferences": {},  # Empty
        })

        profile = await builder.build_profile("ig_456")

        assert profile is not None
        assert profile.follower_id == "ig_456"

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_follower(self):
        """Should return None when follower doesn't exist."""
        from core.audience_intelligence import AudienceProfileBuilder

        mock_session = MagicMock()
        builder = AudienceProfileBuilder(creator_id="test", db=mock_session)

        builder._fetch_follower_data = AsyncMock(return_value=None)

        profile = await builder.build_profile("nonexistent")

        assert profile is None
