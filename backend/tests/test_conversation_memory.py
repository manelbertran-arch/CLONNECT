"""Tests para el servicio de memoria de conversaciones."""
import pytest
from datetime import datetime, timedelta

from services.memory_service import ConversationMemoryService
from models.conversation_memory import ConversationMemory, FactType


@pytest.fixture
def memory_service(tmp_path):
    """Crea un servicio de memoria con storage temporal."""
    return ConversationMemoryService(storage_path=str(tmp_path))


@pytest.fixture
def sample_memory():
    """Crea una memoria de ejemplo."""
    memory = ConversationMemory(
        lead_id="test_lead",
        creator_id="test_creator"
    )
    memory.info_given = {"precio": "150€"}
    memory.last_interaction = datetime.now() - timedelta(days=2)
    return memory


class TestPastReferenceDetection:
    """Tests para detección de referencias al pasado."""

    def test_detect_ya_te_dije(self, memory_service):
        assert memory_service.detect_past_reference("ya te dije que me interesa")

    def test_detect_como_te_comente(self, memory_service):
        assert memory_service.detect_past_reference("como te comenté antes")

    def test_detect_la_otra_vez(self, memory_service):
        assert memory_service.detect_past_reference("la otra vez hablamos de esto")

    def test_detect_el_otro_dia(self, memory_service):
        assert memory_service.detect_past_reference("el otro día me dijiste algo")

    def test_no_detect_normal_message(self, memory_service):
        assert not memory_service.detect_past_reference("Hola, qué tal?")

    def test_no_detect_new_question(self, memory_service):
        assert not memory_service.detect_past_reference("Cuánto cuesta el coaching?")


class TestFactExtraction:
    """Tests para extracción de facts."""

    def test_extract_price_euros(self, memory_service):
        facts = memory_service.extract_facts("", "El precio es 150€")
        assert any(f.fact_type == FactType.PRICE_GIVEN for f in facts)
        assert any("150" in f.content for f in facts)

    def test_extract_price_word(self, memory_service):
        facts = memory_service.extract_facts("", "Cuesta 200 euros la sesión")
        assert any(f.fact_type == FactType.PRICE_GIVEN for f in facts)

    def test_extract_link(self, memory_service):
        facts = memory_service.extract_facts("", "Aquí tienes el link: https://pay.me/123")
        assert any(f.fact_type == FactType.LINK_SHARED for f in facts)

    def test_extract_product_explanation(self, memory_service):
        response = (
            "El Círculo de Hombres es una comunidad donde trabajamos "
            "el desarrollo personal masculino a través de encuentros semanales."
        )
        facts = memory_service.extract_facts("", response)
        assert any(f.fact_type == FactType.PRODUCT_EXPLAINED for f in facts)

    def test_detect_lead_question(self, memory_service):
        facts = memory_service.extract_facts(
            "Cuánto cuesta el coaching?", "", is_bot_response=False
        )
        assert any(f.fact_type == FactType.QUESTION_ASKED for f in facts)


class TestShouldRepeatInfo:
    """Tests para determinar si repetir información."""

    def test_should_give_new_info(self, memory_service, sample_memory):
        sample_memory.info_given = {}
        should_repeat, _ = memory_service.should_repeat_info(sample_memory, "precio")
        assert should_repeat

    def test_should_not_repeat_recent(self, memory_service, sample_memory):
        sample_memory.last_interaction = datetime.now() - timedelta(days=1)
        should_repeat, prev = memory_service.should_repeat_info(sample_memory, "precio")
        assert not should_repeat
        assert prev == "150€"

    def test_should_repeat_after_week(self, memory_service, sample_memory):
        sample_memory.last_interaction = datetime.now() - timedelta(days=10)
        should_repeat, prev = memory_service.should_repeat_info(sample_memory, "precio")
        assert should_repeat
        assert prev == "150€"


class TestMemoryPersistence:
    """Tests para persistencia de memoria."""

    @pytest.mark.asyncio
    async def test_save_and_load(self, memory_service):
        memory = ConversationMemory(lead_id="test1", creator_id="creator1")
        memory.info_given = {"test": "value"}
        memory.last_topic = "coaching"

        await memory_service.save(memory)
        loaded = await memory_service.load("test1", "creator1")

        assert loaded.info_given == {"test": "value"}
        assert loaded.last_topic == "coaching"

    @pytest.mark.asyncio
    async def test_load_nonexistent(self, memory_service):
        memory = await memory_service.load("nonexistent", "creator")
        assert memory.lead_id == "nonexistent"
        assert memory.info_given == {}


class TestQuestionDetection:
    """Tests para detección de tipos de pregunta."""

    def test_detect_price_question(self, memory_service):
        assert memory_service.detect_question_type("Cuánto cuesta?") == "precio"
        assert memory_service.detect_question_type("Qué precio tiene?") == "precio"

    def test_detect_product_question(self, memory_service):
        assert memory_service.detect_question_type("Qué es el Círculo?") == "producto"
        assert memory_service.detect_question_type("Cómo funciona?") == "producto"

    def test_detect_availability_question(self, memory_service):
        assert memory_service.detect_question_type("Cuándo es el próximo?") == "disponibilidad"

    def test_no_detect_statement(self, memory_service):
        assert memory_service.detect_question_type("Me interesa mucho") is None


class TestMemoryContextGeneration:
    """Tests para generación de contexto."""

    def test_context_includes_info_given(self, memory_service, sample_memory):
        context = memory_service.get_memory_context_for_prompt(sample_memory)
        assert "150€" in context
        assert "NO REPETIR" in context

    def test_context_includes_days_since(self, memory_service, sample_memory):
        sample_memory.last_interaction = datetime.now() - timedelta(days=5)
        context = memory_service.get_memory_context_for_prompt(sample_memory)
        assert "5 días" in context

    def test_empty_context_for_new_conversation(self, memory_service):
        memory = ConversationMemory(lead_id="new", creator_id="creator")
        context = memory_service.get_memory_context_for_prompt(memory)
        assert context == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
