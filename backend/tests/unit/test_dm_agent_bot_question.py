"""Test bot_question_analyzer integration in dm_agent_v2 (Step 5)."""


class TestBotQuestionAnalyzerIntegration:
    def test_module_importable(self):
        from core.bot_question_analyzer import get_bot_question_analyzer

        analyzer = get_bot_question_analyzer()
        assert analyzer is not None

    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_QUESTION_CONTEXT

        assert isinstance(ENABLE_QUESTION_CONTEXT, bool)

    def test_analyze_interest_question(self):
        from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer

        analyzer = get_bot_question_analyzer()
        result = analyzer.analyze("¿Te gustaría saber más?")
        assert result == QuestionType.INTEREST

    def test_analyze_purchase_question(self):
        from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer

        analyzer = get_bot_question_analyzer()
        result = analyzer.analyze("¿Te paso el link de compra?")
        assert result == QuestionType.PURCHASE

    def test_short_affirmation_detection(self):
        from core.bot_question_analyzer import is_short_affirmation

        assert is_short_affirmation("Si")
        assert is_short_affirmation("Vale")
        assert is_short_affirmation("Ok")
        assert not is_short_affirmation("Quiero saber más sobre el curso de python")
