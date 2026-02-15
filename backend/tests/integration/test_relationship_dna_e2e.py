"""End-to-end integration tests for RelationshipDNA.

Tests the complete flow from conversation analysis to personalized responses.
Uses realistic conversation data based on Stefan's actual communication style.

Part of RELATIONSHIP-DNA feature.
"""

from unittest.mock import patch

from models.relationship_dna import RelationshipType


class TestFullFlowNewLead:
    """Test complete flow for new leads."""

    def test_full_flow_new_lead(self):
        """Should analyze new lead and create DNA with correct defaults."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        with patch("services.relationship_dna_service.get_relationship_dna") as mock_get:
            with patch("services.relationship_dna_service.get_or_create_relationship_dna") as mock_create:
                mock_get.return_value = None
                mock_create.return_value = {
                    "id": "new-uuid",
                    "creator_id": "stefan",
                    "follower_id": "new_user",
                    "relationship_type": RelationshipType.DESCONOCIDO.value,
                    "trust_score": 0.0,
                    "vocabulary_uses": [],
                }

                # Get or create DNA for new lead
                dna = service.get_or_create_dna("stefan", "new_user", [])

                assert dna is not None
                assert dna["relationship_type"] == RelationshipType.DESCONOCIDO.value
                assert dna["trust_score"] == 0.0


class TestFullFlowExistingLead:
    """Test complete flow for existing leads with history."""

    def test_full_flow_existing_lead(self):
        """Should load existing DNA and generate personalized instructions."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        with patch("services.relationship_dna_service.get_relationship_dna") as mock_get:
            mock_get.return_value = {
                "id": "existing-uuid",
                "creator_id": "stefan",
                "follower_id": "existing_user",
                "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
                "trust_score": 0.75,
                "vocabulary_uses": ["hermano", "bro"],
                "vocabulary_avoids": ["amigo"],
                "emojis": ["🙏🏽"],
                "bot_instructions": "Usa hermano con este lead",
            }

            dna = service.get_dna_for_lead("stefan", "existing_user")
            instructions = service.get_prompt_instructions(dna)

            assert dna is not None
            assert dna["relationship_type"] == RelationshipType.AMISTAD_CERCANA.value
            assert "hermano" in instructions.lower() or "fraternal" in instructions.lower()


class TestFlowIntimaRelationship:
    """Test flow for intimate relationships (like Stefan/Nadia)."""

    def test_flow_intima_relationship(self):
        """Should detect and handle INTIMA relationship correctly."""
        from services.relationship_analyzer import RelationshipAnalyzer

        # Simulated Nadia conversation
        nadia_messages = [
            {"role": "user", "content": "Hola mi amor 💙"},
            {"role": "assistant", "content": "Hola preciosa! Como estas? 💙"},
            {"role": "user", "content": "Te extraño mucho"},
            {"role": "assistant", "content": "Y yo a ti cariño, mucho mucho 💙"},
            {"role": "user", "content": "Cuando nos vemos?"},
            {"role": "assistant", "content": "Este finde? Te preparo algo especial"},
            {"role": "user", "content": "Siii te amo"},
            {"role": "assistant", "content": "Te amo más mi vida 💙"},
        ]

        analyzer = RelationshipAnalyzer()
        result = analyzer.analyze("stefan", "nadia", nadia_messages)

        assert result["relationship_type"] == RelationshipType.INTIMA.value
        assert result["trust_score"] >= 0.8
        assert "💙" in result["emojis"]
        # Should NOT use "hermano" with intimate partner
        assert "hermano" not in result.get("vocabulary_uses", [])


class TestFlowAmistadRelationship:
    """Test flow for close friendship (like Stefan/Johnny)."""

    def test_flow_amistad_relationship(self):
        """Should detect and handle AMISTAD_CERCANA relationship correctly."""
        from services.relationship_analyzer import RelationshipAnalyzer

        # Simulated Johnny conversation
        johnny_messages = [
            {"role": "user", "content": "Hermano que tal el retiro?"},
            {"role": "assistant", "content": "Brutal bro! Muy transformador 🙏🏽"},
            {"role": "user", "content": "Me alegro hermano! Cuando el proximo circulo?"},
            {"role": "assistant", "content": "En dos semanas, vienes? Va a estar genial"},
            {"role": "user", "content": "Claro que si hermano, ahi estare"},
            {"role": "assistant", "content": "Perfecto! Te mando el link 💪🏽"},
            {"role": "user", "content": "Gracias bro!"},
            {"role": "assistant", "content": "Un abrazo grande hermano 🫂"},
        ]

        analyzer = RelationshipAnalyzer()
        result = analyzer.analyze("stefan", "johnny", johnny_messages)

        assert result["relationship_type"] == RelationshipType.AMISTAD_CERCANA.value
        assert "hermano" in result["vocabulary_uses"] or "bro" in result["vocabulary_uses"]
        # Should NOT use "amor" with friends
        assert "amor" not in result.get("vocabulary_uses", [])


class TestFlowClienteRelationship:
    """Test flow for client relationships."""

    def test_flow_cliente_relationship(self):
        """Should detect and handle CLIENTE relationship correctly."""
        from services.relationship_analyzer import RelationshipAnalyzer

        # Client inquiry conversation
        client_messages = [
            {"role": "user", "content": "Hola! Vi tu contenido sobre circulos de hombres"},
            {"role": "assistant", "content": "Hola! Que bueno, en que puedo ayudarte?"},
            {"role": "user", "content": "Cuanto cuesta participar?"},
            {"role": "assistant", "content": "El programa son 497 euros, incluye 8 sesiones grupales"},
            {"role": "user", "content": "Y que incluye exactamente?"},
            {"role": "assistant", "content": "Incluye las sesiones, acceso a la comunidad y material de apoyo"},
            {"role": "user", "content": "Como puedo pagar?"},
            {"role": "assistant", "content": "Te paso el link de pago por aqui"},
        ]

        analyzer = RelationshipAnalyzer()
        result = analyzer.analyze("stefan", "potential_client", client_messages)

        assert result["relationship_type"] == RelationshipType.CLIENTE.value
        # Trust score should be moderate (not yet established)
        assert result["trust_score"] < 0.5


class TestStefanNadiaConversation:
    """Real-world test with Stefan/Nadia style conversation."""

    def test_stefan_nadia_conversation(self):
        """Should correctly personalize for intimate relationship."""
        from services.bot_instructions_generator import BotInstructionsGenerator
        from services.relationship_analyzer import RelationshipAnalyzer

        messages = [
            {"role": "user", "content": "Buenas noches amor 💙"},
            {"role": "assistant", "content": "Buenas noches preciosa 💙"},
            {"role": "user", "content": "Como fue tu dia?"},
            {"role": "assistant", "content": "Intenso pero bien, pensando en ti"},
            {"role": "user", "content": "Yo tambien en ti, te quiero mucho"},
            {"role": "assistant", "content": "Y yo a ti mi vida, descansa 💙"},
        ]

        analyzer = RelationshipAnalyzer()
        result = analyzer.analyze("stefan", "nadia", messages)

        generator = BotInstructionsGenerator()
        instructions = generator.generate(result)

        # Instructions should reflect intimate relationship
        assert "íntim" in instructions.lower() or "cariño" in instructions.lower()
        # Should include the blue heart emoji
        assert "💙" in instructions or "emojis" in instructions.lower()


class TestStefanJohnnyConversation:
    """Real-world test with Stefan/Johnny style conversation."""

    def test_stefan_johnny_conversation(self):
        """Should correctly personalize for close friendship."""
        from services.bot_instructions_generator import BotInstructionsGenerator
        from services.relationship_analyzer import RelationshipAnalyzer

        messages = [
            {"role": "user", "content": "Hermano! Como vas?"},
            {"role": "assistant", "content": "Todo bien bro! Y vos?"},
            {"role": "user", "content": "Bien bien, preparando el circulo"},
            {"role": "assistant", "content": "Que bueno hermano! Cuenta conmigo 🙏🏽"},
            {"role": "user", "content": "Gracias crack, eres el mejor"},
            {"role": "assistant", "content": "Un abrazo grande hermano 💪🏽"},
        ]

        analyzer = RelationshipAnalyzer()
        result = analyzer.analyze("stefan", "johnny", messages)

        generator = BotInstructionsGenerator()
        instructions = generator.generate(result)

        # Instructions should reflect fraternal relationship
        assert "fraternal" in instructions.lower() or "hermano" in instructions.lower()


class TestResponseQualityMaintained:
    """Test that response quality is maintained with DNA."""

    def test_response_quality_maintained(self):
        """DNA integration should enhance, not degrade response quality."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        # DNA with full data
        full_dna = {
            "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
            "vocabulary_uses": ["hermano", "bro"],
            "vocabulary_avoids": ["señor"],
            "emojis": ["🙏🏽", "💪🏽"],
            "recurring_topics": ["circulos"],
            "golden_examples": [
                {"lead": "Que tal?", "creator": "Todo bien hermano!"}
            ],
        }

        instructions = service.get_prompt_instructions(full_dna)

        # Instructions should be substantial
        assert len(instructions) > 100
        # Should include key personalization elements
        assert "hermano" in instructions.lower() or "fraternal" in instructions.lower()
        assert "evita" in instructions.lower()  # Should mention what to avoid


class TestNoRegressionInSpeed:
    """Test that DNA operations are fast enough."""

    def test_no_regression_in_speed(self):
        """DNA operations should not significantly impact response time."""
        import time

        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        with patch("services.relationship_dna_service.get_relationship_dna") as mock_get:
            mock_get.return_value = {
                "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
                "vocabulary_uses": ["hermano"],
                "vocabulary_avoids": [],
                "emojis": ["🙏🏽"],
            }

            # Measure time for 100 operations
            start = time.time()
            for _ in range(100):
                dna = service.get_dna_for_lead("stefan", "test_lead")
                service.get_prompt_instructions(dna)
            elapsed = time.time() - start

            # 100 operations should complete in under 0.5 seconds
            assert elapsed < 0.5, f"Too slow: {elapsed:.3f}s for 100 operations"


class TestDatabaseConsistency:
    """Test database operations maintain consistency."""

    def test_database_consistency(self):
        """DNA operations should maintain data consistency."""
        from services.relationship_dna_service import RelationshipDNAService

        service = RelationshipDNAService()

        with patch("services.relationship_dna_service.get_relationship_dna") as mock_get:
            with patch("services.relationship_dna_service.update_relationship_dna") as mock_update:
                # Initial DNA state
                initial_dna = {
                    "creator_id": "stefan",
                    "follower_id": "test_lead",
                    "total_messages_analyzed": 10,
                    "version": 1,
                }
                mock_get.return_value = initial_dna
                mock_update.return_value = True

                # Record interaction
                service.record_interaction("stefan", "test_lead")

                # Verify update was called with incremented count
                mock_update.assert_called_once()
                call_args = mock_update.call_args
                assert call_args[0][0] == "stefan"
                assert call_args[0][1] == "test_lead"
                # Data should include incremented message count
                update_data = call_args[0][2]
                assert update_data["total_messages_analyzed"] == 11
