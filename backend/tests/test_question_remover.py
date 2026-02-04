"""Tests for question remover."""

import pytest
from services.question_remover import (
    contains_banned_question,
    convert_question_to_statement,
    process_questions,
    remove_banned_questions,
    should_allow_question,
)


class TestContainsBannedQuestion:
    def test_detects_que_tal(self):
        assert contains_banned_question("Hola! ¿Qué tal?") == True

    def test_detects_como_estas(self):
        assert contains_banned_question("Hey! ¿Cómo estás?") == True

    def test_detects_todo_bien(self):
        assert contains_banned_question("Genial! ¿Todo bien?") == True

    def test_allows_specific_questions(self):
        assert contains_banned_question("¿Cuándo nos vemos?") == False
        assert contains_banned_question("¿Te interesa el programa?") == False


class TestRemoveBannedQuestions:
    def test_removes_que_tal(self):
        result = remove_banned_questions("Hola! ¿Qué tal?")
        assert "¿qué tal?" not in result.lower()

    def test_removes_y_tu(self):
        result = remove_banned_questions("Bien! ¿Y tú?")
        assert "¿y tú?" not in result.lower()

    def test_preserves_rest(self):
        result = remove_banned_questions("Genial! ¿Qué tal? Nos vemos!")
        assert "genial" in result.lower()
        assert "nos vemos" in result.lower()


class TestShouldAllowQuestion:
    def test_allows_when_lead_asked(self):
        assert should_allow_question("¿Cómo va el programa?", "Bien! ¿Te interesa?") == True

    def test_allows_clarification(self):
        assert should_allow_question("Quiero reservar", "¿Qué día te va bien?") == True

    def test_blocks_generic_after_greeting(self):
        assert should_allow_question("Hola!", "Hola! ¿Qué tal?") == False


class TestProcessQuestions:
    def test_removes_unnecessary_question(self):
        result = process_questions("Hola! ¿Qué tal? 😊", "Hola!", question_rate=0.10)
        assert "?" not in result

    def test_keeps_necessary_question(self):
        result = process_questions(
            "Genial! ¿Qué día te va bien?", "Quiero agendar una sesión", question_rate=0.10
        )
        assert "?" in result

    def test_no_change_if_no_question(self):
        result = process_questions("Genial hermano!", "Gracias!", question_rate=0.10)
        assert result == "Genial hermano!"


class TestConvertQuestionToStatement:
    def test_converts_como_te_fue(self):
        result = convert_question_to_statement("Genial! ¿Cómo te fue?")
        assert "?" not in result

    def test_converts_que_te_parecio(self):
        result = convert_question_to_statement("Lo vi! ¿Qué te pareció?")
        assert "?" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
