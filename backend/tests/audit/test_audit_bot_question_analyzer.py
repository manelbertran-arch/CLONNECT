"""Audit tests for core/bot_question_analyzer.py"""

from core.bot_question_analyzer import (
    BotQuestionAnalyzer,
    QuestionType,
    get_bot_question_analyzer,
    is_short_affirmation,
)


class TestAuditBotQuestionAnalyzer:
    def test_import(self):
        from core.bot_question_analyzer import BotQuestionAnalyzer, QuestionType  # noqa: F811

        assert QuestionType is not None

    def test_init(self):
        analyzer = BotQuestionAnalyzer()
        assert analyzer is not None

    def test_happy_path_analyze(self):
        analyzer = get_bot_question_analyzer()
        result = analyzer.analyze("Te gustaria saber mas sobre el curso?")
        assert result is not None

    def test_edge_case_short_affirmation(self):
        result = is_short_affirmation("si")
        assert isinstance(result, bool)

    def test_error_handling_empty(self):
        analyzer = BotQuestionAnalyzer()
        result = analyzer.analyze("")
        assert result is not None
