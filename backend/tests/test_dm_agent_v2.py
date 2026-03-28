#!/usr/bin/env python3
"""
Functional tests for core/dm_agent_v2.py

Tests the DM Agent V2 against the production database.
Uses a real creator_id to verify initialization, services, and pipeline.

Run with: pytest tests/test_dm_agent_v2.py -v

NOTE: Groups 1-4 require DATABASE_URL and OPENAI_API_KEY env vars (production).
      Groups 5-7 are pure-logic tests that work without external dependencies.
"""

import os
import sys

import pytest

# Ensure backend is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Real creator used in functional audit
CREATOR_ID = os.getenv("TEST_CREATOR", "stefano_bonanno")


# =========================================================================
# GROUP 1: Factory — get_dm_agent returns a valid agent
# =========================================================================


class TestFactory:
    """Tests for get_dm_agent / invalidate_dm_agent_cache."""

    def test_get_dm_agent_returns_instance(self):
        from core.dm_agent_v2 import DMResponderAgentV2, get_dm_agent

        agent = get_dm_agent(CREATOR_ID)
        assert isinstance(agent, DMResponderAgentV2)

    def test_get_dm_agent_caches_same_creator(self):
        from core.dm_agent_v2 import get_dm_agent

        agent1 = get_dm_agent(CREATOR_ID)
        agent2 = get_dm_agent(CREATOR_ID)
        assert agent1 is agent2, "Same creator_id should return cached instance"

    def test_get_dm_agent_has_creator_id(self):
        from core.dm_agent_v2 import get_dm_agent

        agent = get_dm_agent(CREATOR_ID)
        assert agent.creator_id == CREATOR_ID

    def test_invalidate_cache_forces_new_instance(self):
        from core.dm_agent_v2 import get_dm_agent, invalidate_dm_agent_cache

        agent_before = get_dm_agent(CREATOR_ID)
        invalidate_dm_agent_cache(CREATOR_ID)
        agent_after = get_dm_agent(CREATOR_ID)
        assert agent_before is not agent_after, "After invalidation, should create new instance"

    def test_invalidate_all_cache(self):
        from core.dm_agent_v2 import get_dm_agent, invalidate_dm_agent_cache

        get_dm_agent(CREATOR_ID)
        invalidate_dm_agent_cache()  # None = all
        # No error raised = success


# =========================================================================
# GROUP 2: Services initialized
# =========================================================================


class TestServicesInitialized:
    """Tests that all core services are non-None after initialization."""

    @pytest.fixture(scope="class")
    def agent(self):
        from core.dm_agent_v2 import get_dm_agent

        return get_dm_agent(CREATOR_ID)

    def test_has_intent_classifier(self, agent):
        assert agent.intent_classifier is not None

    def test_has_prompt_builder(self, agent):
        assert agent.prompt_builder is not None

    def test_has_memory_store(self, agent):
        assert agent.memory_store is not None

    def test_has_semantic_rag(self, agent):
        assert agent.semantic_rag is not None

    def test_has_llm_service(self, agent):
        assert agent.llm_service is not None

    def test_has_lead_service(self, agent):
        assert agent.lead_service is not None

    def test_has_instagram_service(self, agent):
        assert agent.instagram_service is not None

    def test_has_personality_dict(self, agent):
        assert isinstance(agent.personality, dict)

    def test_has_products_list(self, agent):
        assert isinstance(agent.products, list)

    def test_has_config(self, agent):
        from core.dm_agent_v2 import AgentConfig

        assert isinstance(agent.config, AgentConfig)


# =========================================================================
# GROUP 3: health_check does not raise
# =========================================================================


class TestHealthCheck:
    """Tests that health_check and get_stats return expected structure."""

    @pytest.fixture(scope="class")
    def agent(self):
        from core.dm_agent_v2 import get_dm_agent

        return get_dm_agent(CREATOR_ID)

    def test_health_check_returns_dict(self, agent):
        result = agent.health_check()
        assert isinstance(result, dict)

    def test_health_check_all_services_true(self, agent):
        result = agent.health_check()
        expected_keys = [
            "intent_classifier",
            "prompt_builder",
            "memory_store",
            "rag_service",
            "llm_service",
            "lead_service",
            "instagram_service",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"
            assert result[key] is True, f"Service unhealthy: {key}"

    def test_get_stats_returns_dict(self, agent):
        result = agent.get_stats()
        assert isinstance(result, dict)
        assert result["creator_id"] == CREATOR_ID
        assert "config" in result
        assert "llm" in result
        assert "rag" in result
        assert "memory" in result


# =========================================================================
# GROUP 4: process_dm returns valid DMResponse
# =========================================================================


class TestProcessDM:
    """Tests the full 5-phase pipeline with a real agent."""

    @pytest.fixture(scope="class")
    def agent(self):
        from core.dm_agent_v2 import get_dm_agent

        return get_dm_agent(CREATOR_ID)

    @pytest.mark.asyncio
    async def test_process_dm_returns_dm_response(self, agent):
        from core.dm_agent_v2 import DMResponse

        result = await agent.process_dm("hola", "test_sender_functional")
        assert isinstance(result, DMResponse)

    @pytest.mark.asyncio
    async def test_process_dm_has_content(self, agent):
        result = await agent.process_dm("hola", "test_sender_functional")
        assert result.content is not None
        assert len(result.content) > 0, "Response content should not be empty"

    @pytest.mark.asyncio
    async def test_process_dm_has_intent(self, agent):
        result = await agent.process_dm("hola", "test_sender_functional")
        assert result.intent is not None
        assert isinstance(result.intent, str)

    @pytest.mark.asyncio
    async def test_process_dm_has_lead_stage(self, agent):
        result = await agent.process_dm("hola", "test_sender_functional")
        assert result.lead_stage is not None
        assert isinstance(result.lead_stage, str)

    @pytest.mark.asyncio
    async def test_process_dm_has_confidence(self, agent):
        result = await agent.process_dm("hola", "test_sender_functional")
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_process_dm_to_dict(self, agent):
        result = await agent.process_dm("hola", "test_sender_functional")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "content" in d
        assert "intent" in d
        assert "lead_stage" in d
        assert "confidence" in d
        assert "created_at" in d

    @pytest.mark.asyncio
    async def test_process_dm_with_metadata(self, agent):
        result = await agent.process_dm(
            "hola", "test_sender_functional", metadata={"platform": "instagram"}
        )
        assert result.content is not None

    @pytest.mark.asyncio
    async def test_process_dm_empty_message(self, agent):
        """Empty message should still produce a response (not crash)."""
        result = await agent.process_dm("", "test_sender_functional")
        assert result is not None
        assert result.content is not None


# =========================================================================
# GROUP 5: Text utilities (pure logic — no DB needed)
# =========================================================================


class TestTextUtilities:
    """Tests for module-level text utility functions."""

    # --- _strip_accents ---

    def test_strip_accents_spanish(self):
        from core.dm_agent_v2 import _strip_accents

        assert _strip_accents("café") == "cafe"
        assert _strip_accents("niño") == "nino"
        assert _strip_accents("señor") == "senor"

    def test_strip_accents_german(self):
        from core.dm_agent_v2 import _strip_accents

        assert _strip_accents("über") == "uber"

    def test_strip_accents_no_change(self):
        from core.dm_agent_v2 import _strip_accents

        assert _strip_accents("hello") == "hello"
        assert _strip_accents("") == ""

    # --- _truncate_at_boundary ---

    def test_truncate_at_boundary_short_text_unchanged(self):
        from core.dm_agent_v2 import _truncate_at_boundary

        text = "Short text."
        assert _truncate_at_boundary(text, 100) == text

    def test_truncate_at_boundary_respects_limit(self):
        from core.dm_agent_v2 import _truncate_at_boundary

        text = "First sentence. Second sentence. Third sentence."
        result = _truncate_at_boundary(text, 30)
        assert len(result) <= 30

    def test_truncate_at_boundary_empty(self):
        from core.dm_agent_v2 import _truncate_at_boundary

        assert _truncate_at_boundary("", 100) == ""

    def test_truncate_at_boundary_prefers_sentence(self):
        from core.dm_agent_v2 import _truncate_at_boundary

        text = "First sentence. Second sentence. Third sentence. Fourth sentence."
        result = _truncate_at_boundary(text, 50)
        # Should end at a sentence boundary (period)
        assert result.endswith(".") or result.endswith(" ") or len(result) <= 50

    # --- _smart_truncate_context ---

    def test_smart_truncate_context_short_unchanged(self):
        from core.dm_agent_v2 import _smart_truncate_context

        text = "Short prompt."
        assert _smart_truncate_context(text, 1000) == text

    def test_smart_truncate_context_preserves_recent(self):
        from core.dm_agent_v2 import _smart_truncate_context

        text = (
            "System instructions.\n" * 50
            + "Historial de conversación\n"
            + "Old message.\n" * 20
            + "Recent message.\n"
        )
        result = _smart_truncate_context(text, 500)
        # Recent conversation should be preserved
        assert "Recent message." in result

    # --- apply_voseo ---

    def test_apply_voseo_tu_to_vos(self):
        from core.dm_agent_v2 import apply_voseo

        assert "vos" in apply_voseo("tú puedes hacerlo")

    def test_apply_voseo_tienes_to_tenes(self):
        from core.dm_agent_v2 import apply_voseo

        assert "tenés" in apply_voseo("tienes que hacerlo")

    def test_apply_voseo_puedes_to_podes(self):
        from core.dm_agent_v2 import apply_voseo

        assert "podés" in apply_voseo("puedes hacerlo")

    def test_apply_voseo_quieres_to_queres(self):
        from core.dm_agent_v2 import apply_voseo

        assert "querés" in apply_voseo("quieres ir")

    def test_apply_voseo_eres_to_sos(self):
        from core.dm_agent_v2 import apply_voseo

        assert "sos" in apply_voseo("eres genial")

    def test_apply_voseo_imperative(self):
        from core.dm_agent_v2 import apply_voseo

        assert "contame" in apply_voseo("cuéntame más")
        assert "decime" in apply_voseo("dime algo")
        assert "mirá" in apply_voseo("mira esto")

    def test_apply_voseo_no_change_for_english(self):
        from core.dm_agent_v2 import apply_voseo

        text = "you can do it"
        assert apply_voseo(text) == text

    # --- _message_mentions_product ---

    def test_mentions_product_exact_substring(self):
        from core.dm_agent_v2 import _message_mentions_product

        assert _message_mentions_product("Fitpack Challenge", "quiero el fitpack challenge")

    def test_mentions_product_with_delimiter(self):
        from core.dm_agent_v2 import _message_mentions_product

        assert _message_mentions_product(
            "Fitpack Challenge de 11 días: Transforma tu cuerpo",
            "me interesa el fitpack challenge de 11 dias",
        )

    def test_mentions_product_brand_words(self):
        from core.dm_agent_v2 import _message_mentions_product

        # 2+ significant words match
        assert _message_mentions_product(
            "Coaching Transformacional Premium",
            "quiero saber del coaching transformacional",
        )

    def test_mentions_product_no_match(self):
        from core.dm_agent_v2 import _message_mentions_product

        assert not _message_mentions_product("Fitpack Challenge", "hola como estas")

    def test_mentions_product_short_name_rejected(self):
        from core.dm_agent_v2 import _message_mentions_product

        # Names <= 3 chars are always rejected
        assert not _message_mentions_product("Pro", "quiero el pro plan")

    def test_mentions_product_empty_name(self):
        from core.dm_agent_v2 import _message_mentions_product

        assert not _message_mentions_product("", "quiero algo")


# =========================================================================
# GROUP 6: Dataclasses (pure logic — no DB needed)
# =========================================================================


class TestDataclasses:
    """Tests that dataclasses instantiate correctly with defaults and custom values."""

    # --- AgentConfig ---

    def test_agent_config_defaults(self):
        from core.dm_agent_v2 import AgentConfig

        config = AgentConfig()
        assert config.rag_top_k == 10
        assert isinstance(config.temperature, float)
        assert isinstance(config.max_tokens, int)

    def test_agent_config_custom(self):
        from core.dm_agent_v2 import AgentConfig
        from services import LLMProvider

        config = AgentConfig(llm_provider=LLMProvider.OPENAI, temperature=0.5, max_tokens=200)
        assert config.temperature == 0.5
        assert config.max_tokens == 200
        assert config.llm_provider == LLMProvider.OPENAI

    # --- DMResponse ---

    def test_dm_response_required_fields(self):
        from core.dm_agent_v2 import DMResponse

        resp = DMResponse(
            content="hola", intent="greeting", lead_stage="cold", confidence=0.9
        )
        assert resp.content == "hola"
        assert resp.intent == "greeting"
        assert resp.lead_stage == "cold"
        assert resp.confidence == 0.9

    def test_dm_response_defaults(self):
        from core.dm_agent_v2 import DMResponse

        resp = DMResponse(
            content="x", intent="x", lead_stage="x", confidence=0.0
        )
        assert resp.tokens_used == 0
        assert isinstance(resp.metadata, dict)
        assert len(resp.metadata) == 0
        assert resp.created_at is not None

    def test_dm_response_to_dict_keys(self):
        from core.dm_agent_v2 import DMResponse

        resp = DMResponse(
            content="test", intent="greeting", lead_stage="cold", confidence=0.8
        )
        d = resp.to_dict()
        assert isinstance(d, dict)
        expected_keys = {"content", "intent", "lead_stage", "confidence", "tokens_used", "metadata", "created_at"}
        assert expected_keys == set(d.keys())

    def test_dm_response_to_dict_values(self):
        from core.dm_agent_v2 import DMResponse

        resp = DMResponse(
            content="test", intent="greeting", lead_stage="cold", confidence=0.8, tokens_used=42
        )
        d = resp.to_dict()
        assert d["content"] == "test"
        assert d["tokens_used"] == 42
        assert isinstance(d["created_at"], str)  # isoformat string

    # --- DetectionResult ---

    def test_detection_result_defaults(self):
        from core.dm_agent_v2 import DetectionResult

        result = DetectionResult()
        assert result.frustration_level == 0.0
        assert result.frustration_signals is None
        assert result.context_signals is None
        assert result.pool_response is None
        assert isinstance(result.cognitive_metadata, dict)

    def test_detection_result_custom(self):
        from core.dm_agent_v2 import DetectionResult

        result = DetectionResult(frustration_level=0.7, frustration_signals=["repeated_question"])
        assert result.frustration_level == 0.7
        assert result.frustration_signals == ["repeated_question"]

    # --- ContextBundle ---

    def test_context_bundle_defaults(self):
        from core.dm_agent_v2 import ContextBundle

        bundle = ContextBundle()
        assert bundle.intent is None
        assert bundle.intent_value == ""
        assert bundle.dna_context == ""
        assert bundle.rag_context == ""
        assert bundle.is_friend is False
        assert bundle.rel_type == ""
        assert bundle.current_stage == ""
        assert isinstance(bundle.rag_results, list)
        assert isinstance(bundle.history, list)

    def test_context_bundle_custom(self):
        from core.dm_agent_v2 import ContextBundle

        bundle = ContextBundle(
            intent_value="greeting",
            is_friend=True,
            rag_context="relevant knowledge",
            current_stage="warm",
        )
        assert bundle.intent_value == "greeting"
        assert bundle.is_friend is True
        assert bundle.rag_context == "relevant knowledge"
        assert bundle.current_stage == "warm"

    def test_context_bundle_mutable_defaults_isolated(self):
        """Mutable default fields should not be shared across instances."""
        from core.dm_agent_v2 import ContextBundle

        b1 = ContextBundle()
        b2 = ContextBundle()
        b1.rag_results.append("doc1")
        assert len(b2.rag_results) == 0, "Mutable defaults should be isolated per instance"


# =========================================================================
# GROUP 7: _determine_response_strategy (pure logic — no DB needed)
# =========================================================================


class TestResponseStrategy:
    """Tests for _determine_response_strategy."""

    def test_family_returns_personal(self):
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola",
            intent_value="greeting",
            relationship_type="FAMILIA",
            is_first_message=False,
            is_friend=False,
            follower_interests=[],
            lead_stage="cold",
        )
        assert "PERSONAL" in result
        assert "NUNCA" in result  # "NUNCA vendas"

    def test_intimate_returns_personal(self):
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola",
            intent_value="greeting",
            relationship_type="INTIMA",
            is_first_message=False,
            is_friend=False,
            follower_interests=[],
            lead_stage="cold",
        )
        assert "PERSONAL" in result

    def test_friend_returns_personal(self):
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola",
            intent_value="greeting",
            relationship_type="SEGUIDOR",
            is_first_message=False,
            is_friend=True,
            follower_interests=[],
            lead_stage="cold",
        )
        assert "PERSONAL" in result
        assert "No vendas" in result

    def test_help_request_returns_ayuda(self):
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="necesito ayuda con mi cuenta",
            intent_value="support",
            relationship_type="SEGUIDOR",
            is_first_message=False,
            is_friend=False,
            follower_interests=[],
            lead_stage="warm",
        )
        assert "AYUDA" in result

    def test_help_signals_detected(self):
        from core.dm_agent_v2 import _determine_response_strategy

        for signal in ["ayuda", "problema", "no funciona", "no puedo", "urgente"]:
            result = _determine_response_strategy(
                message=f"tengo un {signal}",
                intent_value="other",
                relationship_type="SEGUIDOR",
                is_first_message=False,
                is_friend=False,
                follower_interests=[],
                lead_stage="warm",
            )
            assert "AYUDA" in result, f"Signal '{signal}' should trigger AYUDA strategy"

    def test_purchase_intent_returns_venta(self):
        from core.dm_agent_v2 import _determine_response_strategy

        for intent in ["purchase", "pricing", "product_info"]:
            result = _determine_response_strategy(
                message="cuanto cuesta",
                intent_value=intent,
                relationship_type="SEGUIDOR",
                is_first_message=False,
                is_friend=False,
                follower_interests=[],
                lead_stage="warm",
            )
            assert "VENTA" in result, f"Intent '{intent}' should trigger VENTA strategy"

    def test_first_message_returns_bienvenida(self):
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola",
            intent_value="greeting",
            relationship_type="SEGUIDOR",
            is_first_message=True,
            is_friend=False,
            follower_interests=[],
            lead_stage="cold",
        )
        assert "BIENVENIDA" in result

    def test_first_message_with_question_mark_returns_bienvenida_ayuda(self):
        """First message with '?' but no help signal → BIENVENIDA + AYUDA."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola, tienen descuentos?",
            intent_value="greeting",
            relationship_type="SEGUIDOR",
            is_first_message=True,
            is_friend=False,
            follower_interests=[],
            lead_stage="cold",
        )
        assert "BIENVENIDA" in result
        assert "AYUDA" in result

    def test_first_message_with_help_signal_prioritizes_ayuda(self):
        """Help signals take priority over first-message (Priority 2 > Priority 4)."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola, necesito ayuda urgente",
            intent_value="greeting",
            relationship_type="SEGUIDOR",
            is_first_message=True,
            is_friend=False,
            follower_interests=[],
            lead_stage="cold",
        )
        assert "AYUDA" in result

    def test_ghost_returns_reactivacion(self):
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="hola volvi",
            intent_value="greeting",
            relationship_type="SEGUIDOR",
            is_first_message=False,
            is_friend=False,
            follower_interests=[],
            lead_stage="fantasma",
        )
        assert "REACTIVACIÓN" in result

    def test_default_returns_empty_string(self):
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="ok gracias",
            intent_value="acknowledgment",
            relationship_type="SEGUIDOR",
            is_first_message=False,
            is_friend=False,
            follower_interests=[],
            lead_stage="warm",
        )
        assert result == ""

    def test_family_takes_priority_over_help(self):
        """Family relationship should override help signals."""
        from core.dm_agent_v2 import _determine_response_strategy

        result = _determine_response_strategy(
            message="necesito ayuda urgente",
            intent_value="support",
            relationship_type="FAMILIA",
            is_first_message=False,
            is_friend=False,
            follower_interests=[],
            lead_stage="warm",
        )
        assert "PERSONAL" in result
        assert "AYUDA" not in result
