"""
CAPA 2 — Unit tests: Lead Scoring
Tests classify_lead() and calculate_score() as pure functions.
No DB required.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from services.lead_scoring import (
    classify_lead,
    calculate_score,
    SCORE_RANGES,
    FOLLOWER_PURCHASE_KEYWORDS,
    FOLLOWER_INTEREST_KEYWORDS,
    SOCIAL_KEYWORDS,
    NEGATIVE_KEYWORDS,
    COLLABORATION_KEYWORDS,
)


# ─── Helper ────────────────────────────────────────────────────────────────────

def base_signals(**overrides):
    """Return a minimal signals dict with sensible defaults."""
    signals = {
        "total_messages": 4,
        "follower_messages": 2,
        "creator_messages": 2,
        "follower_purchase_hits": 0,
        "follower_interest_hits": 0,
        "follower_scheduling_hits": 0,
        "follower_negative_hits": 0,
        "follower_social_hits": 0,
        "creator_social_hits": 0,
        "social_hits": 0,
        "collaboration_hits": 0,
        "follower_avg_length": 20.0,
        "short_reactions": 0,
        "story_replies": 0,
        "bidirectional_ratio": 0.5,
        "strong_intents": 0,
        "soft_intents": 0,
        "days_since_last": 1,
        "days_since_first": 5,
        "is_existing_customer": False,
    }
    signals.update(overrides)
    return signals


# ─── classify_lead ─────────────────────────────────────────────────────────────

class TestClassifyLead:

    def test_existing_customer_returns_cliente(self):
        s = base_signals(is_existing_customer=True)
        assert classify_lead(s) == "cliente"

    def test_two_purchase_hits_returns_caliente(self):
        s = base_signals(follower_purchase_hits=2)
        assert classify_lead(s) == "caliente"

    def test_one_purchase_plus_scheduling_returns_caliente(self):
        s = base_signals(follower_purchase_hits=1, follower_scheduling_hits=1)
        assert classify_lead(s) == "caliente"

    def test_strong_intents_plus_purchase_returns_caliente(self):
        s = base_signals(strong_intents=2, follower_purchase_hits=1)
        assert classify_lead(s) == "caliente"

    def test_collaboration_hits_gte2_returns_colaborador(self):
        s = base_signals(collaboration_hits=2)
        assert classify_lead(s) == "colaborador"

    def test_bidirectional_social_high_volume_returns_amigo(self):
        s = base_signals(
            follower_social_hits=2,
            creator_social_hits=2,
            social_hits=4,
            total_messages=8,
            bidirectional_ratio=0.5,
        )
        assert classify_lead(s) == "amigo"

    def test_inactive_14days_returns_frio(self):
        s = base_signals(days_since_last=20, total_messages=5)
        assert classify_lead(s) == "frío"

    def test_two_interest_hits_returns_caliente(self):
        s = base_signals(follower_interest_hits=2, days_since_last=2)
        assert classify_lead(s) == "caliente"

    def test_no_signals_returns_nuevo(self):
        s = base_signals()
        assert classify_lead(s) == "nuevo"

    def test_cliente_beats_purchase_signals(self):
        """Existing customer status preserved even with new purchase signals."""
        s = base_signals(is_existing_customer=True, follower_purchase_hits=3)
        assert classify_lead(s) == "cliente"

    def test_frio_requires_prior_activity(self):
        """Inactive but zero messages → stays nuevo."""
        s = base_signals(days_since_last=30, total_messages=1)
        # total_messages < 2, so frio condition fails → nuevo
        assert classify_lead(s) == "nuevo"

    def test_collab_one_hit_not_colaborador(self):
        s = base_signals(collaboration_hits=1)
        assert classify_lead(s) != "colaborador"


# ─── calculate_score ───────────────────────────────────────────────────────────

class TestCalculateScore:

    def test_score_within_range_cliente(self):
        s = base_signals(is_existing_customer=True, days_since_last=3, follower_messages=12)
        score = calculate_score("cliente", s)
        lo, hi = SCORE_RANGES["cliente"]
        assert lo <= score <= hi, f"score {score} outside [{lo},{hi}]"

    def test_score_within_range_caliente(self):
        s = base_signals(follower_purchase_hits=2, days_since_last=1)
        score = calculate_score("caliente", s)
        lo, hi = SCORE_RANGES["caliente"]
        assert lo <= score <= hi

    def test_score_within_range_colaborador(self):
        s = base_signals(collaboration_hits=3)
        score = calculate_score("colaborador", s)
        lo, hi = SCORE_RANGES["colaborador"]
        assert lo <= score <= hi

    def test_score_within_range_amigo(self):
        s = base_signals(social_hits=5, total_messages=10)
        score = calculate_score("amigo", s)
        lo, hi = SCORE_RANGES["amigo"]
        assert lo <= score <= hi

    def test_score_within_range_frio(self):
        s = base_signals(days_since_last=20)
        score = calculate_score("frío", s)
        lo, hi = SCORE_RANGES["frío"]
        assert lo <= score <= hi

    def test_score_within_range_nuevo(self):
        s = base_signals(follower_messages=1, days_since_last=2)
        score = calculate_score("nuevo", s)
        lo, hi = SCORE_RANGES["nuevo"]
        assert lo <= score <= hi

    def test_negative_keywords_lower_caliente_score(self):
        s_no_neg = base_signals(follower_purchase_hits=2, follower_negative_hits=0, days_since_last=5)
        s_neg    = base_signals(follower_purchase_hits=2, follower_negative_hits=2, days_since_last=5)
        score_clean = calculate_score("caliente", s_no_neg)
        score_neg   = calculate_score("caliente", s_neg)
        assert score_neg <= score_clean, "Negative keywords should lower or equal score"

    def test_recent_activity_boosts_caliente(self):
        s_recent = base_signals(follower_purchase_hits=2, days_since_last=1)
        s_old    = base_signals(follower_purchase_hits=2, days_since_last=30)
        assert calculate_score("caliente", s_recent) >= calculate_score("caliente", s_old)

    def test_score_never_exceeds_100(self):
        s = base_signals(is_existing_customer=True, days_since_last=1, follower_messages=50)
        assert calculate_score("cliente", s) <= 100

    def test_score_never_below_0(self):
        s = base_signals(follower_negative_hits=10)
        assert calculate_score("caliente", s) >= 0

    def test_unknown_status_falls_to_nuevo_range(self):
        s = base_signals()
        score = calculate_score("desconocido", s)
        # Unknown status uses (0,25) range from .get(..., (0,25))
        assert 0 <= score <= 25


# ─── Keyword Lists ─────────────────────────────────────────────────────────────

class TestKeywordLists:

    def test_purchase_keywords_nonempty(self):
        assert len(FOLLOWER_PURCHASE_KEYWORDS) > 5

    def test_interest_keywords_nonempty(self):
        assert len(FOLLOWER_INTEREST_KEYWORDS) > 5

    def test_social_keywords_nonempty(self):
        assert len(SOCIAL_KEYWORDS) > 5

    def test_negative_keywords_nonempty(self):
        assert len(NEGATIVE_KEYWORDS) > 3

    def test_collaboration_keywords_nonempty(self):
        assert len(COLLABORATION_KEYWORDS) > 2

    def test_precio_in_purchase_keywords(self):
        assert "precio" in FOLLOWER_PURCHASE_KEYWORDS

    def test_comprar_in_purchase_keywords(self):
        assert "comprar" in FOLLOWER_PURCHASE_KEYWORDS

    def test_caro_in_negative_keywords(self):
        assert "caro" in NEGATIVE_KEYWORDS

    def test_collab_in_collaboration_keywords(self):
        assert "collab" in COLLABORATION_KEYWORDS

    def test_score_ranges_all_six_statuses(self):
        for status in ["cliente", "caliente", "colaborador", "amigo", "nuevo", "frío"]:
            assert status in SCORE_RANGES, f"Missing SCORE_RANGES['{status}']"
            lo, hi = SCORE_RANGES[status]
            assert lo < hi, f"SCORE_RANGES['{status}'] invalid: {lo} >= {hi}"
