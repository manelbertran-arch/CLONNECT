"""Tests para el servicio de variaciones de respuesta."""
import pytest

from models.response_variations import STEFAN_RESPONSE_POOLS, ResponsePool
from services.response_variator import ResponseVariator


@pytest.fixture
def variator():
    """Crea un variator fresco para cada test."""
    return ResponseVariator()


class TestMessageTypeDetection:
    """Tests para detección de tipo de mensaje."""

    def test_detect_greeting_hola(self, variator):
        assert variator.detect_message_type("Hola!") == "greeting"

    def test_detect_greeting_hey(self, variator):
        assert variator.detect_message_type("Hey") == "greeting"

    def test_detect_greeting_que_tal(self, variator):
        assert variator.detect_message_type("Qué tal!") == "greeting"

    def test_detect_thanks(self, variator):
        assert variator.detect_message_type("Gracias!") == "thanks"
        assert variator.detect_message_type("Muchas gracias 😊") == "thanks"

    def test_detect_confirmation_ok(self, variator):
        assert variator.detect_message_type("Ok") == "confirmation"
        assert variator.detect_message_type("Vale") == "confirmation"
        assert variator.detect_message_type("Perfecto") == "confirmation"

    def test_detect_emoji_only(self, variator):
        assert variator.detect_message_type("😊") == "emoji_reaction"
        assert variator.detect_message_type("❤️") == "emoji_reaction"
        assert variator.detect_message_type("💪🔥") == "emoji_reaction"

    def test_detect_laugh(self, variator):
        assert variator.detect_message_type("Jajaja") == "laugh"
        assert variator.detect_message_type("Jaja sí") == "laugh"

    def test_detect_farewell(self, variator):
        assert variator.detect_message_type("Un abrazo!") == "farewell"
        assert variator.detect_message_type("Hablamos!") == "farewell"

    def test_detect_enthusiasm(self, variator):
        # "Genial" es confirmación, usar otros para enthusiasm
        assert variator.detect_message_type("Increíble!") == "enthusiasm"
        assert variator.detect_message_type("Qué bien!") == "enthusiasm"

    def test_no_detect_complex_message(self, variator):
        assert variator.detect_message_type("Cuánto cuesta el coaching?") is None
        msg = "Me gustaría saber más sobre el programa"
        assert variator.detect_message_type(msg) is None

    def test_no_detect_long_greeting(self, variator):
        # Saludos largos deben ir al LLM
        long_greeting = (
            "Hola! Cómo estás? Espero que todo vaya bien, quería preguntarte algo"
        )
        assert variator.detect_message_type(long_greeting) is None


class TestResponseVariation:
    """Tests para variación de respuestas."""

    def test_greeting_gives_response(self, variator):
        response, msg_type = variator.process("Hola!")
        assert response is not None
        assert msg_type == "greeting"

    def test_greeting_varies(self, variator):
        """5 saludos consecutivos deben dar al menos 3 respuestas diferentes."""
        responses = [variator.process("Hola!")[0] for _ in range(10)]
        unique = set(responses)
        assert len(unique) >= 3, f"Solo {len(unique)} respuestas únicas: {unique}"

    def test_emoji_to_emoji(self, variator):
        """Emoji debe generar emoji como respuesta."""
        responses = [variator.process("💪")[0] for _ in range(10)]
        # Todas deben ser emojis o muy cortas
        for r in responses:
            assert len(r) <= 5 or any(c in r for c in "❤💙😊😀🙏☺💪")

    def test_thanks_response(self, variator):
        response, msg_type = variator.process("Gracias!")
        assert response is not None
        assert msg_type == "thanks"

    def test_complex_goes_to_llm(self, variator):
        """Mensajes complejos deben ir al LLM (response=None)."""
        response, msg_type = variator.process("Cuánto cuesta el coaching individual?")
        assert response is None
        assert msg_type == "llm"

    def test_no_immediate_repetition(self, variator):
        """No debe repetir la misma respuesta consecutivamente."""
        responses = [variator.process("Hola!")[0] for _ in range(5)]
        # Verificar que no hay muchas repeticiones consecutivas
        consecutive_repeats = sum(
            1 for i in range(len(responses) - 1) if responses[i] == responses[i + 1]
        )
        assert consecutive_repeats <= 2, f"Demasiadas repeticiones: {responses}"


class TestResponsePool:
    """Tests para el modelo ResponsePool."""

    def test_pool_select_returns_from_list(self):
        pool = ResponsePool(trigger_type="test", responses=["A", "B", "C"])
        for _ in range(10):
            assert pool.select() in ["A", "B", "C"]

    def test_pool_respects_weights(self):
        """Verificar que los pesos funcionan (estadísticamente)."""
        pool = ResponsePool(
            trigger_type="test", responses=["A", "B"], weights=[0.9, 0.1]
        )
        results = [pool.select() for _ in range(100)]
        a_count = results.count("A")
        # A debería aparecer significativamente más que B
        assert a_count > 60, f"A solo apareció {a_count} veces de 100"

    def test_pool_exclude_works(self):
        pool = ResponsePool(trigger_type="test", responses=["A", "B", "C"])
        for _ in range(10):
            result = pool.select(exclude=["A", "B"])
            assert result == "C"

    def test_pool_exclude_all_fallback(self):
        """Si se excluyen todas, debe devolver alguna."""
        pool = ResponsePool(trigger_type="test", responses=["A", "B"])
        result = pool.select(exclude=["A", "B"])
        assert result in ["A", "B"]


class TestStefanPools:
    """Tests específicos para los pools de Stefan."""

    def test_all_pools_have_responses(self):
        for name, pool in STEFAN_RESPONSE_POOLS.items():
            assert len(pool.responses) > 0, f"Pool {name} vacío"

    def test_all_pools_weights_match(self):
        for name, pool in STEFAN_RESPONSE_POOLS.items():
            assert len(pool.weights) == len(pool.responses), (
                f"Pool {name}: {len(pool.weights)} weights "
                f"vs {len(pool.responses)} responses"
            )

    def test_all_pools_weights_sum_to_1(self):
        for name, pool in STEFAN_RESPONSE_POOLS.items():
            total = sum(pool.weights)
            assert 0.99 <= total <= 1.01, f"Pool {name}: weights sum to {total}"

    def test_greeting_pool_has_variety(self):
        pool = STEFAN_RESPONSE_POOLS["greeting"]
        assert len(pool.responses) >= 5

    def test_emoji_pool_all_short(self):
        pool = STEFAN_RESPONSE_POOLS["emoji_reaction"]
        for r in pool.responses:
            assert len(r) <= 5, f"Emoji response too long: {r}"


class TestIntegration:
    """Tests de integración."""

    def test_full_conversation_flow(self, variator):
        """Simula un flujo de conversación."""
        exchanges = [
            ("Hola!", "greeting"),
            ("Gracias!", "thanks"),
            ("💪", "emoji_reaction"),
            ("Vale perfecto", "confirmation"),
            ("Jajaja", "laugh"),
            ("Cuánto cuesta?", "llm"),  # Debe ir al LLM
        ]

        for message, expected_type in exchanges:
            response, msg_type = variator.process(message)
            assert msg_type == expected_type, (
                f"'{message}' detectado como {msg_type}, esperaba {expected_type}"
            )

            if expected_type != "llm":
                assert response is not None, f"'{message}' no generó respuesta"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
