"""
Category 1: INTELIGENCIA COGNITIVA
Test Suite: Consistencia Intra-Conversacion

Tests that the DM bot maintains consistency within a single conversation:
- Product price stays the same throughout
- Product availability doesn't contradict
- Product benefits don't change
- Tone profile stays consistent across turns
- Creator personality data doesn't mutate mid-conversation

Uses REAL modules (prompt_service, conversation_state, context_detector)
and mocks only the LLM/DB services.
"""

import copy

import pytest
from services.prompt_service import PromptBuilder


class TestConsistenciaIntra:
    """Test suite for intra-conversation consistency."""

    # ─── Fixtures ───────────────────────────────────────────────────────

    @pytest.fixture
    def products(self):
        """Standard product list for tests."""
        return [
            {
                "name": "Curso Premium",
                "price": 297,
                "description": "12 modulos de coaching",
                "url": "https://pay.example.com/premium",
            },
            {
                "name": "Sesion Individual",
                "price": 97,
                "description": "Sesion 1-on-1 de 60 minutos",
                "url": "https://pay.example.com/session",
            },
        ]

    @pytest.fixture
    def personality(self):
        """Standard personality for tests."""
        return {
            "name": "Coach Elena",
            "tone": "friendly",
            "vocabulary": "cercano, motivador",
            "dialect": "espanol_neutro",
            "formality": "informal",
            "energy": "high",
            "humor": True,
            "emojis": "moderate",
            "signature_phrases": ["vamos a por ello", "tu puedes"],
            "topics_to_avoid": ["politica", "religion"],
            "knowledge_about": {
                "bio": "Coach de vida con 10 anos de experiencia",
                "website_url": "https://coachelena.com",
            },
        }

    # ─── test_no_contradice_precio ──────────────────────────────────────

    def test_no_contradice_precio(self, products, personality):
        """
        If product price is 297 EUR, the system prompt should consistently
        show that price across multiple prompt builds (simulating multiple turns).
        """
        builder = PromptBuilder(personality=personality)

        # Build system prompt at turn 1
        prompt_turn1 = builder.build_system_prompt(products=products)
        assert "297" in prompt_turn1, "Price should appear in turn 1 prompt"

        # Build system prompt at turn 3 (same builder, same products)
        prompt_turn3 = builder.build_system_prompt(products=products)
        assert "297" in prompt_turn3, "Price should still appear in turn 3 prompt"

        # Verify the product section is identical between turns
        # Extract the product section from both prompts
        def extract_product_section(prompt):
            start = prompt.find("=== PRODUCTOS Y SERVICIOS ===")
            end = prompt.find("=== FIN PRODUCTOS ===")
            if start == -1 or end == -1:
                return ""
            return prompt[start:end]

        section1 = extract_product_section(prompt_turn1)
        section3 = extract_product_section(prompt_turn3)
        assert section1 == section3, "Product section should be identical across turns"

        # Verify both products have correct prices
        assert "297" in section1
        assert "97" in section1

    # ─── test_no_contradice_disponibilidad ──────────────────────────────

    def test_no_contradice_disponibilidad(self, products, personality):
        """
        Product availability (present in the products list) stays consistent.
        If a product is in the list, it appears in every prompt build.
        If removed, it should disappear.
        """
        builder = PromptBuilder(personality=personality)

        # Turn 1: Both products available
        prompt_with_both = builder.build_system_prompt(products=products)
        assert "Curso Premium" in prompt_with_both
        assert "Sesion Individual" in prompt_with_both

        # Turn 2: Same products, same availability
        prompt_turn2 = builder.build_system_prompt(products=products)
        assert "Curso Premium" in prompt_turn2
        assert "Sesion Individual" in prompt_turn2

        # Consistency: products list is not mutated between calls
        assert len(products) == 2
        assert products[0]["name"] == "Curso Premium"
        assert products[0]["price"] == 297

        # If we build with only one product (simulating stock change),
        # the other should correctly not appear
        single_product = [products[0]]
        prompt_single = builder.build_system_prompt(products=single_product)
        assert "Curso Premium" in prompt_single
        assert "Sesion Individual" not in prompt_single

    # ─── test_no_contradice_beneficios ──────────────────────────────────

    def test_no_contradice_beneficios(self, products, personality):
        """
        Product benefits (description) don't change between prompt builds.
        The description in the products list is the single source of truth.
        """
        builder = PromptBuilder(personality=personality)

        # Build prompt multiple times
        prompt1 = builder.build_system_prompt(products=products)
        prompt2 = builder.build_system_prompt(products=products)
        prompt3 = builder.build_system_prompt(products=products)

        # Descriptions should appear consistently
        assert "12 modulos de coaching" in prompt1
        assert "12 modulos de coaching" in prompt2
        assert "12 modulos de coaching" in prompt3

        assert "Sesion 1-on-1 de 60 minutos" in prompt1
        assert "Sesion 1-on-1 de 60 minutos" in prompt2
        assert "Sesion 1-on-1 de 60 minutos" in prompt3

        # Products list is immutable between calls
        original_desc = products[0]["description"]
        builder.build_system_prompt(products=products)
        assert (
            products[0]["description"] == original_desc
        ), "Product description should not be mutated by prompt builder"

    # ─── test_mismo_tono_toda_conversacion ──────────────────────────────

    def test_mismo_tono_toda_conversacion(self, personality):
        """
        Tone profile stays consistent across multiple prompt builds
        within the same conversation (same PromptBuilder instance).
        """
        builder = PromptBuilder(personality=personality)

        # Build system prompt at different "turns"
        prompt_turn1 = builder.build_system_prompt(products=[])
        prompt_turn5 = builder.build_system_prompt(products=[])
        prompt_turn10 = builder.build_system_prompt(products=[])

        # The builder's personality should not change
        assert builder.personality["tone"] == "friendly"
        assert builder.personality["name"] == "Coach Elena"

        # Identity section should be consistent
        assert "Coach Elena" in prompt_turn1
        assert "Coach Elena" in prompt_turn5
        assert "Coach Elena" in prompt_turn10

        # Tone description should be consistent (friendly = "amigable")
        # The PromptBuilder uses TONES dict for description
        tone_config = PromptBuilder.TONES.get("friendly", {})
        assert "amigable" in tone_config.get("description", "")

        # Personality dict is not mutated
        assert personality["tone"] == "friendly"
        assert personality["energy"] == "high"

    # ─── test_no_cambia_personalidad ────────────────────────────────────

    def test_no_cambia_personalidad(self, personality, products):
        """
        Creator personality data (name, tone, knowledge) doesn't change
        mid-conversation. Deep copy the personality before building prompts
        and verify it's unchanged after multiple builds.
        """
        personality_snapshot = copy.deepcopy(personality)

        builder = PromptBuilder(personality=personality)

        # Build prompts 5 times (simulating 5 turns)
        for i in range(5):
            builder.build_system_prompt(
                products=products,
                custom_instructions=f"Turn {i+1} custom instruction",
            )
            builder.build_user_context(
                username=f"user_{i}",
                stage="interesado",
                history=[{"role": "user", "content": f"Message {i}"}],
            )

        # Personality should be identical to the snapshot
        assert builder.personality["name"] == personality_snapshot["name"]
        assert builder.personality["tone"] == personality_snapshot["tone"]
        assert builder.personality["vocabulary"] == personality_snapshot["vocabulary"]
        assert builder.personality["knowledge_about"] == personality_snapshot["knowledge_about"]
        assert builder.personality["signature_phrases"] == personality_snapshot["signature_phrases"]
        assert builder.personality["topics_to_avoid"] == personality_snapshot["topics_to_avoid"]

        # Also verify the original dict was not mutated
        assert (
            personality == personality_snapshot
        ), "Personality dict should not be mutated by PromptBuilder"
