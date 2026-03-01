"""
Tests for core/identity_resolver.py  (Prioridad 1 — riesgo ALTO)

Identity resolver merges leads from different platforms into a UnifiedLead.
Critical invariants tested:
  - TIER 1: exact email / phone matches → auto-merge
  - TIER 2: exact name / username matches → auto-merge (different platform only!)
  - TIER 3: fuzzy name → log only, NEVER auto-merge
  - Same-platform name match → should NOT merge (false-positive protection)
  - extract_contact_signals: email, phone, instagram handle extraction
  - Helper functions: _normalise_name, _normalise_phone, _levenshtein
  - _refresh_unified: status priority (cliente > caliente > interesado > nuevo)
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, patch
from core.identity_resolver import (
    extract_contact_signals,
    _normalise_name,
    _normalise_phone,
    _levenshtein,
    _match_by_email,
    _match_by_phone,
    _match_by_exact_name,
    _match_by_username,
    _check_fuzzy_name,
    _refresh_unified,
    PLATFORM_PRIORITY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_lead(
    id="lead1", email=None, phone=None, full_name=None, username=None,
    platform="instagram", platform_user_id="ig_user1",
    unified_lead_id=None, creator_id="creator_uuid", status="nuevo",
    first_contact_at=None, last_contact_at=None, profile_pic_url=None,
    score=0,
):
    lead = MagicMock()
    lead.id = id
    lead.email = email
    lead.phone = phone
    lead.full_name = full_name
    lead.username = username
    lead.platform = platform
    lead.platform_user_id = platform_user_id
    lead.unified_lead_id = unified_lead_id
    lead.creator_id = creator_id
    lead.status = status
    lead.first_contact_at = first_contact_at
    lead.last_contact_at = last_contact_at
    lead.profile_pic_url = profile_pic_url
    lead.score = score
    return lead


def make_unified(id="unified1"):
    unified = MagicMock()
    unified.id = id
    unified.email = None
    unified.phone = None
    unified.display_name = None
    unified.profile_pic_url = None
    unified.unified_score = 0.0
    unified.status = "nuevo"
    unified.merge_history = []
    unified.first_contact_at = None
    unified.last_contact_at = None
    return unified


# ---------------------------------------------------------------------------
# extract_contact_signals — pure function
# ---------------------------------------------------------------------------

class TestExtractContactSignals:

    def test_returns_empty_dict_for_empty_string(self):
        assert extract_contact_signals("") == {}

    def test_returns_empty_dict_for_none(self):
        assert extract_contact_signals(None) == {}

    def test_extracts_email(self):
        signals = extract_contact_signals("Mi email es usuario@ejemplo.com")
        assert signals.get("email") == "usuario@ejemplo.com"

    def test_email_lowercased(self):
        signals = extract_contact_signals("Escríbeme a USER@DOMAIN.COM")
        assert signals["email"] == "user@domain.com"

    def test_extracts_instagram_handle(self):
        signals = extract_contact_signals("Mi IG es @mi_usuario_123")
        assert signals.get("instagram_handle") == "mi_usuario_123"

    def test_excludes_email_domains_as_ig_handles(self):
        """@gmail, @hotmail etc. should not be extracted as IG handles."""
        signals = extract_contact_signals("me@gmail.com")
        assert "instagram_handle" not in signals or signals.get("instagram_handle") not in {
            "gmail", "hotmail", "yahoo", "outlook", "icloud"
        }

    def test_extracts_phone_number(self):
        signals = extract_contact_signals("Llámame al +34612345678")
        assert "phone" in signals
        assert "34612345678" in signals["phone"]

    def test_phone_strips_separators(self):
        signals = extract_contact_signals("Tel: 612-345-678")
        assert "phone" in signals
        # Should have no dashes
        assert "-" not in signals["phone"]

    def test_no_signals_in_plain_text(self):
        signals = extract_contact_signals("Hola me interesa el programa")
        assert signals == {}

    def test_multiple_signals_in_one_message(self):
        signals = extract_contact_signals("Email: test@test.com y IG: @testuser123")
        assert "email" in signals
        assert "instagram_handle" in signals


# ---------------------------------------------------------------------------
# _normalise_name — pure helper
# ---------------------------------------------------------------------------

class TestNormaliseName:

    def test_lowercases(self):
        assert _normalise_name("JUAN PÉREZ") == "juan pérez"

    def test_strips_whitespace(self):
        assert _normalise_name("  Ana García  ") == "ana garcía"

    def test_collapses_inner_spaces(self):
        assert _normalise_name("Juan  Carlos  López") == "juan carlos lópez"

    def test_returns_empty_for_none(self):
        assert _normalise_name(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert _normalise_name("") == ""


# ---------------------------------------------------------------------------
# _normalise_phone — pure helper
# ---------------------------------------------------------------------------

class TestNormalisePhone:

    def test_strips_spaces_and_dashes(self):
        assert _normalise_phone("+34 612-345-678") == "+34612345678"

    def test_strips_parentheses_and_dots(self):
        assert _normalise_phone("(612) 345.678") == "612345678"

    def test_preserves_plus_prefix(self):
        result = _normalise_phone("+34612345678")
        assert result.startswith("+")

    def test_returns_empty_for_none(self):
        assert _normalise_phone(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert _normalise_phone("") == ""


# ---------------------------------------------------------------------------
# _levenshtein — pure helper
# ---------------------------------------------------------------------------

class TestLevenshtein:

    def test_identical_strings_have_distance_zero(self):
        assert _levenshtein("juan", "juan") == 0

    def test_empty_string_distance_equals_length(self):
        assert _levenshtein("abc", "") == 3
        assert _levenshtein("", "abc") == 3

    def test_single_substitution(self):
        assert _levenshtein("juan", "jaan") == 1

    def test_single_insertion(self):
        assert _levenshtein("juan", "juana") == 1

    def test_single_deletion(self):
        assert _levenshtein("juana", "juan") == 1

    def test_completely_different_strings(self):
        assert _levenshtein("abc", "xyz") == 3

    def test_symmetric(self):
        """Distance(a, b) == Distance(b, a)."""
        assert _levenshtein("carlos", "carlitos") == _levenshtein("carlitos", "carlos")

    def test_close_names_have_low_distance(self):
        """Names like 'María' and 'Mario' should be close."""
        assert _levenshtein("maria", "mario") <= 2

    def test_very_different_names_have_high_distance(self):
        assert _levenshtein("juan", "xxxxxx") > 3


# ---------------------------------------------------------------------------
# _match_by_email — critical: TIER 1
# ---------------------------------------------------------------------------

class TestMatchByEmail:

    def test_no_email_on_lead_returns_none(self):
        session = MagicMock()
        lead = make_lead(email=None)
        assert _match_by_email(session, "creator_uuid", lead) is None

    def test_empty_email_returns_none(self):
        session = MagicMock()
        lead = make_lead(email="")
        assert _match_by_email(session, "creator_uuid", lead) is None

    def test_finds_unified_by_email_in_unified_table(self):
        unified = make_unified("unified_email_1")
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = unified
        lead = make_lead(email="test@test.com")

        result = _match_by_email(session, "creator_uuid", lead)
        assert result == unified

    def test_returns_none_when_no_email_match(self):
        session = MagicMock()
        # Both queries return None
        session.query.return_value.filter.return_value.first.return_value = None
        lead = make_lead(email="nobody@test.com")

        result = _match_by_email(session, "creator_uuid", lead)
        assert result is None


# ---------------------------------------------------------------------------
# _match_by_phone — critical: WhatsApp extraction
# ---------------------------------------------------------------------------

class TestMatchByPhone:

    def test_whatsapp_extracts_phone_from_platform_user_id(self):
        """WhatsApp leads embed phone in platform_user_id: 'wa_34612345678'."""
        unified = make_unified("unified_wa_1")
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = unified

        lead = make_lead(platform="whatsapp", platform_user_id="wa_34612345678", phone=None)
        result = _match_by_phone(session, "creator_uuid", lead, "whatsapp")
        assert result == unified

    def test_non_digit_whatsapp_id_ignored(self):
        """If WhatsApp platform_user_id is not pure digits after stripping 'wa_', skip."""
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        lead = make_lead(platform="whatsapp", platform_user_id="wa_invalid_id", phone=None)
        result = _match_by_phone(session, "creator_uuid", lead, "whatsapp")
        assert result is None

    def test_instagram_lead_without_phone_returns_none(self):
        session = MagicMock()
        lead = make_lead(platform="instagram", phone=None)
        result = _match_by_phone(session, "creator_uuid", lead, "instagram")
        assert result is None


# ---------------------------------------------------------------------------
# _match_by_exact_name — critical: different platform requirement
# ---------------------------------------------------------------------------

class TestMatchByExactName:

    def test_short_name_returns_none(self):
        """Names <= 2 chars are too ambiguous to match."""
        session = MagicMock()
        lead = make_lead(full_name="Jo")
        assert _match_by_exact_name(session, "creator_uuid", lead) is None

    def test_no_name_returns_none(self):
        session = MagicMock()
        lead = make_lead(full_name=None)
        assert _match_by_exact_name(session, "creator_uuid", lead) is None

    def test_returns_none_when_name_does_not_match(self):
        """If other lead has a different name, no merge occurs.

        Platform filtering is handled by SQL (Lead.platform != lead.platform);
        this test verifies the Python-level name comparison.
        """
        session = MagicMock()
        other = make_lead(
            id="lead2", full_name="Different Person",
            platform="whatsapp",
            unified_lead_id="u1",
        )
        session.query.return_value.filter.return_value.all.return_value = [other]

        lead = make_lead(id="lead1", full_name="Carlos García", platform="instagram")
        result = _match_by_exact_name(session, "creator_uuid", lead)
        assert result is None  # Name mismatch → no merge

    def test_cross_platform_name_match_merges(self):
        """Same name on different platform → TIER 2 merge.

        _match_by_exact_name calls:
          1. session.query(Lead).filter(...).all()  → [other]
          2. session.query(UnifiedLead).filter_by(id=...).first()  → unified
        """
        unified = make_unified("unified_name_1")
        other = make_lead(
            id="lead2", full_name="Carlos García",
            platform="whatsapp",  # Different platform
            unified_lead_id="unified_name_1",
        )

        session = MagicMock()
        # Query 1: Lead filter — single .filter().all()
        session.query.return_value.filter.return_value.all.return_value = [other]
        # Query 2: UnifiedLead filter_by — .filter_by().first()
        session.query.return_value.filter_by.return_value.first.return_value = unified

        lead = make_lead(id="lead1", full_name="Carlos García", platform="instagram")
        result = _match_by_exact_name(session, "creator_uuid", lead)
        assert result == unified


# ---------------------------------------------------------------------------
# _match_by_username — critical: different platform requirement
# ---------------------------------------------------------------------------

class TestMatchByUsername:

    def test_short_username_returns_none(self):
        session = MagicMock()
        lead = make_lead(username="ab")  # < 3 chars
        assert _match_by_username(session, "creator_uuid", lead) is None

    def test_no_username_returns_none(self):
        session = MagicMock()
        lead = make_lead(username=None)
        assert _match_by_username(session, "creator_uuid", lead) is None

    def test_returns_none_when_username_does_not_match(self):
        """If other lead has a different username, no merge occurs.

        Platform filtering is handled by SQL (Lead.platform != lead.platform);
        this test verifies the Python-level username comparison.
        """
        session = MagicMock()
        other = make_lead(
            id="lead2", username="otro_usuario",
            platform="telegram",
            unified_lead_id="u1",
        )
        session.query.return_value.filter.return_value.all.return_value = [other]

        lead = make_lead(id="lead1", username="carlos_fit", platform="instagram")
        result = _match_by_username(session, "creator_uuid", lead)
        assert result is None  # Username mismatch → no merge

    def test_at_sign_stripped_from_username(self):
        """@username and username should match across platforms."""
        session = MagicMock()
        other = make_lead(
            id="lead2", username="carlos_fit",
            platform="telegram",      # Different platform
            unified_lead_id="u1",
        )
        unified = make_unified("u1")

        # Query 1: Lead filter → [other]
        session.query.return_value.filter.return_value.all.return_value = [other]
        # Query 2: UnifiedLead filter_by → unified
        session.query.return_value.filter_by.return_value.first.return_value = unified

        lead = make_lead(id="lead1", username="@carlos_fit", platform="instagram")
        result = _match_by_username(session, "creator_uuid", lead)
        assert result == unified


# ---------------------------------------------------------------------------
# _check_fuzzy_name — TIER 3: must NOT auto-merge
# ---------------------------------------------------------------------------

class TestCheckFuzzyName:

    def test_fuzzy_name_does_not_return_unified(self):
        """TIER 3 is log-only — _check_fuzzy_name always returns None.

        _check_fuzzy_name: session.query(Lead).filter(...).limit(100).all()
        """
        close_lead = make_lead(
            id="lead2", full_name="Carlos García",
            platform="whatsapp",
        )
        session = MagicMock()
        # Single .filter().limit().all() chain
        session.query.return_value.filter.return_value.limit.return_value.all.return_value = [close_lead]

        lead = make_lead(id="lead1", full_name="Carlos Garzia", platform="instagram")
        result = _check_fuzzy_name(session, "creator_uuid", lead)
        assert result is None

    def test_short_name_skipped(self):
        """Names < 4 chars skip fuzzy check entirely."""
        session = MagicMock()
        lead = make_lead(full_name="Ana")
        result = _check_fuzzy_name(session, "creator_uuid", lead)
        assert result is None
        session.query.assert_not_called()


# ---------------------------------------------------------------------------
# _refresh_unified — status priority logic
# ---------------------------------------------------------------------------

class TestRefreshUnified:

    def _make_session_with_leads(self, leads):
        """_refresh_unified: session.query(Lead).filter(...).all()"""
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = leads
        session.close = MagicMock()
        return session

    def test_cliente_beats_interesado(self):
        lead1 = make_lead(id="l1", status="interesado", platform="instagram", score=50)
        lead2 = make_lead(id="l2", status="cliente", platform="whatsapp", score=80)
        unified = make_unified()
        unified.merge_history = []

        session = self._make_session_with_leads([lead1, lead2])
        _refresh_unified(unified, session, "creator_uuid")

        assert unified.status == "cliente"

    def test_caliente_beats_nuevo(self):
        lead1 = make_lead(id="l1", status="nuevo", platform="instagram", score=5)
        lead2 = make_lead(id="l2", status="caliente", platform="whatsapp", score=60)
        unified = make_unified()

        session = self._make_session_with_leads([lead1, lead2])
        _refresh_unified(unified, session, "creator_uuid")

        assert unified.status == "caliente"

    def test_score_is_max_across_leads(self):
        lead1 = make_lead(id="l1", status="nuevo", score=30, platform="instagram")
        lead2 = make_lead(id="l2", status="nuevo", score=75, platform="whatsapp")
        unified = make_unified()

        session = self._make_session_with_leads([lead1, lead2])
        _refresh_unified(unified, session, "creator_uuid")

        assert unified.unified_score == 75.0

    def test_instagram_display_name_preferred_over_whatsapp(self):
        """Instagram has lower PLATFORM_PRIORITY (0) → preferred for display name."""
        ig_lead = make_lead(id="l1", full_name="Carlos García", platform="instagram", score=0)
        wa_lead = make_lead(id="l2", full_name="Carlos WA", platform="whatsapp", score=0)
        unified = make_unified()

        session = self._make_session_with_leads([ig_lead, wa_lead])
        _refresh_unified(unified, session, "creator_uuid")

        assert unified.display_name == "Carlos García"

    def test_no_leads_returns_early(self):
        """If no leads are linked, _refresh_unified does nothing."""
        unified = make_unified()
        original_score = unified.unified_score

        session = self._make_session_with_leads([])
        _refresh_unified(unified, session, "creator_uuid")

        assert unified.unified_score == original_score  # Unchanged


# ---------------------------------------------------------------------------
# PLATFORM_PRIORITY constants
# ---------------------------------------------------------------------------

class TestPlatformPriority:

    def test_instagram_has_lowest_priority_number(self):
        """Lower number = higher priority for display name selection."""
        assert PLATFORM_PRIORITY["instagram"] < PLATFORM_PRIORITY["telegram"]
        assert PLATFORM_PRIORITY["telegram"] < PLATFORM_PRIORITY["whatsapp"]
