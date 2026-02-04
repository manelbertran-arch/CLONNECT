"""Tests for RelationshipAnalyzer service.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.
"""

from unittest.mock import MagicMock, patch

from models.relationship_dna import RelationshipType


class TestRelationshipAnalyzer:
    """Test suite for RelationshipAnalyzer service."""

    def test_analyze_new_lead_returns_dna(self):
        """Should analyze conversation and return DNA for new lead."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        messages = [
            {"role": "user", "content": "Hola que tal?"},
            {"role": "assistant", "content": "Todo bien! Y vos?"},
            {"role": "user", "content": "Bien bien, queria preguntarte algo"},
        ]

        result = analyzer.analyze("stefan", "new_follower", messages)

        assert result is not None
        assert "relationship_type" in result
        assert "trust_score" in result
        assert "vocabulary_uses" in result

    def test_analyze_existing_lead_updates_dna(self):
        """Should update existing DNA with new analysis."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()

        # First analysis
        messages1 = [
            {"role": "user", "content": "Hola hermano!"},
            {"role": "assistant", "content": "Que tal bro!"},
        ]
        result1 = analyzer.analyze("stefan", "existing_follower", messages1)

        # Second analysis with more messages
        messages2 = messages1 + [
            {"role": "user", "content": "Todo bien, como vas con los circulos?"},
            {"role": "assistant", "content": "Increible hermano, preparando el proximo"},
        ]
        result2 = analyzer.analyze("stefan", "existing_follower", messages2)

        assert result2["total_messages_analyzed"] >= result1["total_messages_analyzed"]

    def test_analyze_with_few_messages_returns_desconocido(self):
        """Should return DESCONOCIDO for conversations with <5 messages."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        messages = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola!"},
        ]

        result = analyzer.analyze("stefan", "new_follower", messages)

        assert result["relationship_type"] == RelationshipType.DESCONOCIDO.value
        assert result["depth_level"] == 0

    def test_analyze_with_many_messages_increases_depth(self):
        """Should increase depth_level with more messages."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        # Simulate 50+ messages
        messages = []
        for i in range(25):
            messages.append({"role": "user", "content": f"Mensaje {i} del usuario"})
            messages.append({"role": "assistant", "content": f"Respuesta {i}"})

        result = analyzer.analyze("stefan", "active_follower", messages)

        assert result["depth_level"] >= 2
        assert result["total_messages_analyzed"] == 50

    def test_extract_patterns_from_conversation(self):
        """Should extract interaction patterns from messages."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        messages = [
            {"role": "assistant", "content": "Hola! Como estas?"},
            {"role": "user", "content": "Bien!"},
            {"role": "assistant", "content": "Que bueno hermano"},
            {"role": "assistant", "content": "Te cuento algo"},
            {"role": "user", "content": "Dale"},
        ]

        patterns = analyzer.extract_patterns(messages)

        assert "avg_message_length" in patterns
        assert "questions_frequency" in patterns
        assert "multi_message_frequency" in patterns
        assert patterns["multi_message_frequency"] > 0  # Has consecutive assistant messages

    def test_generate_instructions_for_relationship(self):
        """Should generate bot instructions based on relationship type."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()

        dna_data = {
            "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
            "vocabulary_uses": ["hermano", "bro"],
            "vocabulary_avoids": ["amigo"],
            "emojis": ["🙏🏽", "💪🏽"],
            "recurring_topics": ["circulos de hombres", "meditacion"],
        }

        instructions = analyzer.generate_instructions(dna_data)

        assert instructions is not None
        assert len(instructions) > 0
        assert "hermano" in instructions.lower() or "bro" in instructions.lower()

    def test_should_update_dna_returns_true_when_stale(self):
        """Should return True when DNA needs re-analysis."""
        from datetime import datetime, timedelta, timezone

        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()

        # DNA analyzed 31 days ago
        old_dna = {
            "last_analyzed_at": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),
            "total_messages_analyzed": 10,
        }

        assert analyzer.should_update_dna(old_dna, current_message_count=15) is True

    def test_should_update_dna_returns_false_when_fresh(self):
        """Should return False when DNA is fresh and message count similar."""
        from datetime import datetime, timezone

        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()

        # DNA analyzed today
        fresh_dna = {
            "last_analyzed_at": datetime.now(timezone.utc).isoformat(),
            "total_messages_analyzed": 50,
        }

        assert analyzer.should_update_dna(fresh_dna, current_message_count=52) is False

    def test_update_incremental_preserves_golden_examples(self):
        """Should preserve manually curated golden examples during update."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()

        existing_dna = {
            "golden_examples": [
                {"lead": "Que tal?", "creator": "Todo bien hermano!"}
            ],
            "vocabulary_uses": ["hermano"],
        }

        new_messages = [
            {"role": "user", "content": "Como vas bro?"},
            {"role": "assistant", "content": "Bien crack!"},
        ]

        updated = analyzer.update_incremental(existing_dna, new_messages)

        # Should preserve existing golden examples
        assert len(updated["golden_examples"]) >= 1
        assert updated["golden_examples"][0]["lead"] == "Que tal?"

    def test_analyze_detects_intima_relationship(self):
        """Should detect INTIMA relationship from intimate conversation."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        messages = [
            {"role": "user", "content": "Te extraño mucho mi amor 💙"},
            {"role": "assistant", "content": "Yo también preciosa, mucho 💙"},
            {"role": "user", "content": "Cuando nos vemos?"},
            {"role": "assistant", "content": "Este finde? Te preparo algo especial"},
            {"role": "user", "content": "Siii, te amo"},
            {"role": "assistant", "content": "Te amo más 💙"},
        ]

        result = analyzer.analyze("stefan", "nadia", messages)

        assert result["relationship_type"] == RelationshipType.INTIMA.value
        assert result["trust_score"] >= 0.8
        assert "💙" in result["emojis"]

    def test_analyze_detects_amistad_cercana(self):
        """Should detect AMISTAD_CERCANA from close friend conversation."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        messages = [
            {"role": "user", "content": "Hermano que tal el retiro?"},
            {"role": "assistant", "content": "Brutal bro, fue transformador"},
            {"role": "user", "content": "Me alegro mucho! Cuando el proximo circulo?"},
            {"role": "assistant", "content": "En dos semanas, vienes? 🙏🏽"},
            {"role": "user", "content": "Claro hermano, ahi estare"},
            {"role": "assistant", "content": "Genial! Te mando el link"},
        ]

        result = analyzer.analyze("stefan", "johnny", messages)

        assert result["relationship_type"] == RelationshipType.AMISTAD_CERCANA.value
        assert "hermano" in result["vocabulary_uses"] or "bro" in result["vocabulary_uses"]

    def test_analyze_detects_cliente_relationship(self):
        """Should detect CLIENTE relationship from business conversation."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        messages = [
            {"role": "user", "content": "Hola, cuanto cuesta el programa?"},
            {"role": "assistant", "content": "Hola! El programa son 497€"},
            {"role": "user", "content": "Y que incluye exactamente?"},
            {"role": "assistant", "content": "Incluye 8 sesiones grupales y acceso a la comunidad"},
            {"role": "user", "content": "Ok, como puedo pagar?"},
            {"role": "assistant", "content": "Te paso el link de pago por aqui"},
        ]

        result = analyzer.analyze("stefan", "potential_client", messages)

        assert result["relationship_type"] == RelationshipType.CLIENTE.value
        assert result["trust_score"] < 0.5  # Not yet a close relationship
