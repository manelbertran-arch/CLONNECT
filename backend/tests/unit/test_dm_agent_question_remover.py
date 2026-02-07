"""Test question_remover integration in dm_agent_v2 (Step 19)."""


class TestQuestionRemoverIntegration:
    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_QUESTION_REMOVAL

        assert isinstance(ENABLE_QUESTION_REMOVAL, bool)

    def test_import_works(self):
        from services.question_remover import process_questions

        assert callable(process_questions)

    def test_returns_string(self):
        from services.question_remover import process_questions

        result = process_questions("Hola, me alegra que preguntes.", "Cuanto cuesta?")
        assert isinstance(result, str)

    def test_preserves_non_question_content(self):
        from services.question_remover import process_questions

        response = "El curso cuesta 97 euros y tiene garantia de 30 dias."
        result = process_questions(response, "precio?")
        assert "97" in result
