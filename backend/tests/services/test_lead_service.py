"""
Lead Service tests - Written BEFORE implementation (TDD).
Run these tests FIRST - they should FAIL until service is created.
"""


class TestLeadServiceImport:
    """Test lead service can be imported."""

    def test_lead_service_module_exists(self):
        """Lead service module should exist."""
        import services.lead_service
        assert services.lead_service is not None

    def test_lead_service_class_exists(self):
        """LeadService class should exist."""
        from services.lead_service import LeadService
        assert LeadService is not None

    def test_lead_stage_enum_exists(self):
        """LeadStage enum should exist."""
        from services.lead_service import LeadStage
        assert LeadStage is not None

    def test_lead_service_has_calculate_score(self):
        """LeadService should have calculate_score method."""
        from services.lead_service import LeadService
        assert hasattr(LeadService, 'calculate_score')

    def test_lead_service_has_determine_stage(self):
        """LeadService should have determine_stage method."""
        from services.lead_service import LeadService
        assert hasattr(LeadService, 'determine_stage')


class TestLeadStage:
    """Test LeadStage enum."""

    def test_nuevo_stage(self):
        """Should have NUEVO stage."""
        from services.lead_service import LeadStage
        assert LeadStage.NUEVO.value == "NUEVO"

    def test_interesado_stage(self):
        """Should have INTERESADO stage."""
        from services.lead_service import LeadStage
        assert LeadStage.INTERESADO.value == "INTERESADO"

    def test_caliente_stage(self):
        """Should have CALIENTE stage."""
        from services.lead_service import LeadStage
        assert LeadStage.CALIENTE.value == "CALIENTE"

    def test_cliente_stage(self):
        """Should have CLIENTE stage."""
        from services.lead_service import LeadStage
        assert LeadStage.CLIENTE.value == "CLIENTE"

    def test_fantasma_stage(self):
        """Should have FANTASMA stage."""
        from services.lead_service import LeadStage
        assert LeadStage.FANTASMA.value == "FANTASMA"


class TestLeadServiceInstantiation:
    """Test LeadService instantiation."""

    def test_lead_service_instantiation(self):
        """LeadService should be instantiable."""
        from services.lead_service import LeadService
        service = LeadService()
        assert service is not None


class TestLeadScoring:
    """Test lead scoring functionality."""

    def test_calculate_score_returns_int(self):
        """calculate_score should return an integer."""
        from services.lead_service import LeadService
        service = LeadService()
        score = service.calculate_score(
            messages_count=5,
            response_rate=0.8,
            purchase_intent=True
        )
        assert isinstance(score, int)

    def test_score_within_range(self):
        """Score should be between 0 and 100."""
        from services.lead_service import LeadService
        service = LeadService()
        score = service.calculate_score(
            messages_count=100,
            response_rate=1.0,
            purchase_intent=True
        )
        assert 0 <= score <= 100

    def test_higher_engagement_higher_score(self):
        """More engagement should result in higher score."""
        from services.lead_service import LeadService
        service = LeadService()
        low_score = service.calculate_score(messages_count=1, response_rate=0.2)
        high_score = service.calculate_score(messages_count=10, response_rate=0.9)
        assert high_score > low_score

    def test_purchase_intent_increases_score(self):
        """Purchase intent should increase score."""
        from services.lead_service import LeadService
        service = LeadService()
        without_intent = service.calculate_score(messages_count=5, purchase_intent=False)
        with_intent = service.calculate_score(messages_count=5, purchase_intent=True)
        assert with_intent > without_intent


class TestStageTransition:
    """Test stage transition logic."""

    def test_new_lead_is_nuevo(self):
        """New lead with low score should be NUEVO."""
        from services.lead_service import LeadService, LeadStage
        service = LeadService()
        stage = service.determine_stage(score=10, days_since_contact=0)
        assert stage == LeadStage.NUEVO

    def test_medium_score_is_interesado(self):
        """Medium score should be INTERESADO."""
        from services.lead_service import LeadService, LeadStage
        service = LeadService()
        stage = service.determine_stage(score=50, days_since_contact=1)
        assert stage == LeadStage.INTERESADO

    def test_high_score_is_caliente(self):
        """High score should be CALIENTE."""
        from services.lead_service import LeadService, LeadStage
        service = LeadService()
        stage = service.determine_stage(score=80, days_since_contact=1)
        assert stage == LeadStage.CALIENTE

    def test_customer_is_cliente(self):
        """Customer should always be CLIENTE."""
        from services.lead_service import LeadService, LeadStage
        service = LeadService()
        stage = service.determine_stage(score=20, is_customer=True)
        assert stage == LeadStage.CLIENTE

    def test_inactive_becomes_fantasma(self):
        """Long inactive lead should become FANTASMA."""
        from services.lead_service import LeadService, LeadStage
        service = LeadService()
        stage = service.determine_stage(score=20, days_since_contact=30)
        assert stage == LeadStage.FANTASMA


class TestIntentScoring:
    """Test intent-based scoring functionality (Phase 3A integration)."""

    def test_calculate_intent_score_exists(self):
        """LeadService should have calculate_intent_score method."""
        from services.lead_service import LeadService
        assert hasattr(LeadService, 'calculate_intent_score')

    def test_direct_purchase_keywords_sets_hot(self):
        """Direct purchase keywords should set score to 75% (hot)."""
        from services.lead_service import LeadService
        service = LeadService()
        score = service.calculate_intent_score(
            current_score=0.0,
            intent="GREETING",
            has_direct_purchase_keywords=True
        )
        assert score == 0.75

    def test_interest_strong_sets_hot(self):
        """INTEREST_STRONG should set score to 75% (hot)."""
        from services.lead_service import LeadService
        service = LeadService()
        score = service.calculate_intent_score(current_score=0.0, intent="INTEREST_STRONG")
        assert score == 0.75

    def test_interest_soft_sets_warm(self):
        """INTEREST_SOFT should set score to 50% (warm)."""
        from services.lead_service import LeadService
        service = LeadService()
        score = service.calculate_intent_score(current_score=0.0, intent="INTEREST_SOFT")
        assert score == 0.50

    def test_question_product_sets_new_threshold(self):
        """QUESTION_PRODUCT should set score to 25%."""
        from services.lead_service import LeadService
        service = LeadService()
        score = service.calculate_intent_score(current_score=0.0, intent="QUESTION_PRODUCT")
        assert score == 0.25

    def test_objection_price_decrements(self):
        """OBJECTION_PRICE should decrement score by 5%."""
        from services.lead_service import LeadService
        service = LeadService()
        score = service.calculate_intent_score(current_score=0.50, intent="OBJECTION_PRICE")
        assert score == 0.45

    def test_never_decrease_on_positive_intent(self):
        """Positive intents should never decrease existing score."""
        from services.lead_service import LeadService
        service = LeadService()
        # If score is already 80%, INTEREST_SOFT (50%) should not decrease it
        score = service.calculate_intent_score(current_score=0.80, intent="INTEREST_SOFT")
        assert score == 0.80

    def test_score_bounds_enforced(self):
        """Score should stay within 0.0-1.0 range."""
        from services.lead_service import LeadService
        service = LeadService()
        # Decrement from 0 should not go negative
        score = service.calculate_intent_score(current_score=0.02, intent="OBJECTION_PRICE")
        assert score >= 0.0
        # High score should not exceed 1.0
        score = service.calculate_intent_score(current_score=0.95, intent="INTEREST_STRONG")
        assert score <= 1.0
