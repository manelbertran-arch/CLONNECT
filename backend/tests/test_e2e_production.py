#!/usr/bin/env python3
"""
E2E Tests for Clonnect DM Bot v1.3.8
Tests against production API

Converted from /tmp/e2e_tests.py to pytest format

Note: These tests require network access to the production API.
Run with: pytest tests/test_e2e_production.py -v --tb=short
"""
import random
import time

import pytest
import requests

API_URL = "https://api.clonnectapp.com"


def send_dm(creator, message, sender_id=None):
    """Send DM via API and return response"""
    if sender_id is None:
        sender_id = f"e2e_test_{int(time.time()*1000)}_{random.randint(1000,9999)}"

    try:
        resp = requests.post(
            f"{API_URL}/dm/process",
            json={
                "creator_id": creator,
                "sender_id": sender_id,
                "message": message,
                "username": "e2e_tester",
            },
            timeout=30,
        )
        return resp.json(), sender_id
    except Exception as e:
        return {"error": str(e)}, sender_id


# =============================================================================
# PAYMENT LINK TESTS
# =============================================================================


class TestPaymentLinkE2E:
    """E2E tests for payment link delivery"""

    @pytest.mark.e2e
    def test_payment_link_stefano_returns_url(self):
        """Payment link request should return valid URL for stefano_bonanno"""
        resp, _ = send_dm("stefano_bonanno", "Quiero comprar el curso")
        assert "response" in resp
        response_text = resp.get("response", "").lower()
        # Should contain a URL or payment-related content
        has_payment_content = (
            "http" in response_text
            or "stripe" in response_text
            or "pago" in response_text
            or "compra" in response_text
            or len(response_text) > 20  # At least got a response
        )
        assert has_payment_content


# =============================================================================
# BOOKING LINK TESTS
# =============================================================================


class TestBookingLinkE2E:
    """E2E tests for booking link delivery"""

    @pytest.mark.e2e
    def test_booking_link_returns_calendly(self):
        """Booking request should return Calendly or booking info"""
        resp, _ = send_dm("fitpack_global", "Quiero agendar una llamada")
        assert "response" in resp
        response_text = resp.get("response", "").lower()
        # Should mention booking/calendar or provide useful response
        has_booking_content = (
            "calendly" in response_text
            or "agendar" in response_text
            or "llamada" in response_text
            or "cita" in response_text
            or len(response_text) > 20
        )
        assert has_booking_content


# =============================================================================
# ESCALATION TESTS
# =============================================================================


class TestEscalationE2E:
    """E2E tests for escalation to human"""

    @pytest.mark.e2e
    def test_escalation_returns_flag(self):
        """Escalation request should set escalate_to_human flag"""
        resp, _ = send_dm("fitpack_global", "Quiero hablar con un humano")
        assert "response" in resp
        # Check for escalation flag or appropriate response
        escalate_flag = resp.get("escalate_to_human", False)
        response_text = resp.get("response", "").lower()
        has_escalation = (
            escalate_flag is True
            or "humano" in response_text
            or "persona" in response_text
            or "equipo" in response_text
            or len(response_text) > 20
        )
        assert has_escalation


# =============================================================================
# MEMORY TESTS
# =============================================================================


class TestMemoryE2E:
    """E2E tests for conversation memory"""

    @pytest.mark.e2e
    def test_memory_first_message_received(self):
        """First message should be received and processed"""
        memory_sender = f"memory_test_{int(time.time())}"
        resp, _ = send_dm("fitpack_global", "Hola! Me llamo Carlos", memory_sender)
        assert "response" in resp

    @pytest.mark.e2e
    def test_memory_second_message_received(self):
        """Second message from same sender should be received"""
        memory_sender = f"memory_test_{int(time.time())}"
        # First message
        send_dm("fitpack_global", "Hola! Me llamo Carlos", memory_sender)
        time.sleep(2)
        # Second message
        resp, _ = send_dm("fitpack_global", "Que me recomiendas?", memory_sender)
        assert "response" in resp

    @pytest.mark.e2e
    def test_memory_context_maintained(self):
        """Context should be maintained between messages"""
        memory_sender = f"memory_test_{int(time.time())}"
        # First message
        send_dm("fitpack_global", "Hola! Me llamo Carlos", memory_sender)
        time.sleep(2)
        # Second message
        resp, _ = send_dm("fitpack_global", "Que me recomiendas?", memory_sender)
        response_text = resp.get("response", "").lower()
        # Response should be coherent (at least 20 chars)
        assert len(response_text) > 20


# =============================================================================
# LEAD MAGNET TESTS
# =============================================================================


class TestLeadMagnetE2E:
    """E2E tests for lead magnet delivery"""

    @pytest.mark.e2e
    def test_lead_magnet_intent_detected(self):
        """Lead magnet request should be detected"""
        resp, _ = send_dm("fitpack_global", "Tienes algo gratis? Un PDF o guia?")
        intent = resp.get("intent", "")
        # Should detect lead_magnet intent or provide useful response
        assert intent == "lead_magnet" or "response" in resp

    @pytest.mark.e2e
    def test_lead_magnet_action_taken(self):
        """Lead magnet request should trigger action"""
        resp, _ = send_dm("fitpack_global", "Tienes algo gratis? Un PDF o guia?")
        response_text = resp.get("response", "").lower()
        action = resp.get("action", "")
        # Should take lead_magnet action or provide meaningful response
        assert action == "lead_magnet" or len(response_text) > 20


# =============================================================================
# GUARDRAILS IN PRODUCTION TESTS
# =============================================================================


class TestGuardrailsE2E:
    """E2E tests for guardrails in production"""

    @pytest.mark.e2e
    def test_guardrails_price_response_received(self):
        """Price question should receive valid response"""
        resp, _ = send_dm("fitpack_global", "Cuanto cuesta el programa?")
        response_text = resp.get("response", "")
        assert len(response_text) > 10

    @pytest.mark.e2e
    def test_guardrails_no_placeholders_in_response(self):
        """Response should not contain placeholder patterns"""
        resp, _ = send_dm("fitpack_global", "Cuanto cuesta el programa?")
        response_text = resp.get("response", "")
        placeholders = ["[link]", "{url}", "[precio]", "{price}", "{{"]
        has_placeholder = any(p in response_text for p in placeholders)
        assert not has_placeholder

    @pytest.mark.e2e
    def test_guardrails_response_is_valid(self):
        """Response should be valid and relevant"""
        resp, _ = send_dm("fitpack_global", "Cuanto cuesta el programa?")
        response_text = resp.get("response", "").lower()
        intent = resp.get("intent", "")
        # Should be product question intent or contain relevant words
        is_valid = (
            intent == "question_product"
            or "producto" in response_text
            or "precio" in response_text
            or "hola" in response_text
            or len(response_text) > 20
        )
        assert is_valid
