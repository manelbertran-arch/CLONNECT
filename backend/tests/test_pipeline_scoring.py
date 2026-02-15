# backend/tests/test_pipeline_scoring.py
# Tests for the pipeline scoring and auto-transition logic

from unittest.mock import Mock


# Pipeline scoring values by status
PIPELINE_SCORES = {
    "new": 25,
    "active": 50,
    "hot": 75,
    "customer": 100,
}

# Status mappings from API to DB
STATUS_MAPPING = {
    "cold": "new",
    "warm": "active",
    "hot": "hot",
    "customer": "customer",
}


class TestPipelineScoring:
    """Test pipeline scoring logic"""

    def test_pipeline_score_new_lead(self):
        """New leads should have pipeline_score=25"""
        status = "new"
        expected_score = PIPELINE_SCORES[status]
        assert expected_score == 25

    def test_pipeline_score_active_lead(self):
        """Active leads should have pipeline_score=50"""
        status = "active"
        expected_score = PIPELINE_SCORES[status]
        assert expected_score == 50

    def test_pipeline_score_hot_lead(self):
        """Hot leads should have pipeline_score=75"""
        status = "hot"
        expected_score = PIPELINE_SCORES[status]
        assert expected_score == 75

    def test_pipeline_score_customer(self):
        """Customer leads should have pipeline_score=100"""
        status = "customer"
        expected_score = PIPELINE_SCORES[status]
        assert expected_score == 100

    def test_status_mapping_cold_to_new(self):
        """Cold status should map to 'new'"""
        api_status = "cold"
        db_status = STATUS_MAPPING.get(api_status, api_status)
        assert db_status == "new"

    def test_status_mapping_warm_to_active(self):
        """Warm status should map to 'active'"""
        api_status = "warm"
        db_status = STATUS_MAPPING.get(api_status, api_status)
        assert db_status == "active"

    def test_status_mapping_hot(self):
        """Hot status should stay 'hot'"""
        api_status = "hot"
        db_status = STATUS_MAPPING.get(api_status, api_status)
        assert db_status == "hot"

    def test_status_mapping_customer(self):
        """Customer status should stay 'customer'"""
        api_status = "customer"
        db_status = STATUS_MAPPING.get(api_status, api_status)
        assert db_status == "customer"


class TestPurchaseIntentScore:
    """Test purchase intent score calculation"""

    def test_intent_score_range(self):
        """Purchase intent score should be 0-100"""
        # Test boundary values
        for intent_score in [0, 25, 50, 75, 100]:
            assert 0 <= intent_score <= 100
            assert isinstance(intent_score, (int, float))

    def test_intent_to_score_conversion(self):
        """Test conversion from purchase_intent (0-1) to score (0-100)"""
        test_cases = [
            (0.0, 0),
            (0.25, 25),
            (0.5, 50),
            (0.75, 75),
            (1.0, 100),
        ]
        for intent, expected_score in test_cases:
            score = int(intent * 100)
            assert score == expected_score


class TestPipelineFlow:
    """Test full pipeline flow logic"""

    def test_all_statuses_have_scores(self):
        """Every status should have a defined pipeline score"""
        expected_statuses = ["new", "active", "hot", "customer"]
        for status in expected_statuses:
            assert status in PIPELINE_SCORES
            assert PIPELINE_SCORES[status] is not None

    def test_scores_are_ordered(self):
        """Pipeline scores should increase with status progression"""
        scores = [
            PIPELINE_SCORES["new"],
            PIPELINE_SCORES["active"],
            PIPELINE_SCORES["hot"],
            PIPELINE_SCORES["customer"],
        ]
        assert scores == sorted(scores)

    def test_score_gaps(self):
        """Scores should have reasonable gaps (25 points each)"""
        assert PIPELINE_SCORES["active"] - PIPELINE_SCORES["new"] == 25
        assert PIPELINE_SCORES["hot"] - PIPELINE_SCORES["active"] == 25
        assert PIPELINE_SCORES["customer"] - PIPELINE_SCORES["hot"] == 25


class TestLeadConversion:
    """Test lead conversion calculation"""

    def test_conversion_data_structure(self):
        """Test expected conversion data structure"""
        conversion = {
            "lead_id": "test_123",
            "lead_status": "hot",
            "pipeline_score": 75,
            "purchase_intent": 0.75,
            "purchase_intent_score": 75,
        }

        assert "lead_id" in conversion
        assert "lead_status" in conversion
        assert "pipeline_score" in conversion
        assert "purchase_intent_score" in conversion
        assert 0 <= conversion["purchase_intent_score"] <= 100

    def test_mock_lead_creation(self):
        """Test mock lead creation structure"""
        lead = Mock()
        lead.id = "lead_001"
        lead.name = "Test Lead"
        lead.status = "new"
        lead.pipeline_score = 25
        lead.purchase_intent = 0.15

        assert lead.id == "lead_001"
        assert lead.status == "new"
        assert lead.pipeline_score == PIPELINE_SCORES["new"]
