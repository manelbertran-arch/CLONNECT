"""Tests para Tone Analyzer."""

import pytest
from datetime import datetime
from backend.ingestion.tone_analyzer import (
    ToneProfile,
    ToneAnalyzer,
    quick_analyze_text
)


class TestToneProfile:
    """Tests para ToneProfile dataclass."""

    def test_create_profile(self):
        profile = ToneProfile(
            creator_id="creator_123",
            formality="informal",
            energy="alta",
            warmth="calido"
        )
        assert profile.creator_id == "creator_123"
        assert profile.formality == "informal"
        assert profile.confidence_score == 0.0

    def test_default_values(self):
        profile = ToneProfile(creator_id="test")
        assert profile.formality == "neutral"
        assert profile.energy == "media"
        assert profile.warmth == "calido"
        assert profile.uses_emojis == True
        assert profile.asks_questions == True

    def test_to_system_prompt_section(self):
        profile = ToneProfile(
            creator_id="test",
            formality="informal",
            energy="alta",
            warmth="muy_calido",
            signature_phrases=["vamos crack", "a tope"],
            favorite_emojis=["...", "..."],
            uses_emojis=True,
            emoji_frequency="alta"
        )

        prompt = profile.to_system_prompt_section()

        assert "informal" in prompt
        assert "alta" in prompt
        assert "vamos crack" in prompt

    def test_to_system_prompt_with_greetings(self):
        profile = ToneProfile(
            creator_id="test",
            common_greetings=["Hola!", "Hey que tal"],
            common_closings=["Un abrazo", "Nos vemos"]
        )

        prompt = profile.to_system_prompt_section()

        assert "FORMAS DE SALUDAR" in prompt
        assert "Hola!" in prompt
        assert "FORMAS DE DESPEDIRSE" in prompt
        assert "Un abrazo" in prompt

    def test_to_dict_and_back(self):
        profile = ToneProfile(
            creator_id="test",
            formality="formal",
            energy="media",
            warmth="neutral",
            signature_phrases=["hola", "gracias"],
            analyzed_posts_count=10
        )

        data = profile.to_dict()
        restored = ToneProfile.from_dict(data)

        assert restored.creator_id == profile.creator_id
        assert restored.formality == profile.formality
        assert restored.signature_phrases == profile.signature_phrases
        assert restored.analyzed_posts_count == 10

    def test_from_dict_with_string_datetime(self):
        data = {
            "creator_id": "test",
            "formality": "informal",
            "energy": "alta",
            "warmth": "calido",
            "last_updated": "2024-01-15T10:30:00"
        }

        profile = ToneProfile.from_dict(data)
        assert profile.creator_id == "test"
        assert isinstance(profile.last_updated, datetime)


class TestToneAnalyzer:
    """Tests para ToneAnalyzer."""

    def test_prepare_posts_text(self):
        analyzer = ToneAnalyzer()
        posts = [
            {"caption": "Primer post"},
            {"caption": "Segundo post"}
        ]

        text = analyzer._prepare_posts_text(posts)

        assert "Primer post" in text
        assert "Segundo post" in text
        assert "POST 1" in text
        assert "POST 2" in text

    def test_prepare_posts_text_empty_caption(self):
        analyzer = ToneAnalyzer()
        posts = [
            {"caption": ""},
            {"caption": "Valido"}
        ]

        text = analyzer._prepare_posts_text(posts)

        assert "Valido" in text

    def test_analyze_statistics(self):
        analyzer = ToneAnalyzer()
        posts = [
            {"caption": "Hola! ... Como estas?"},
            {"caption": "INCREIBLE resultado... #fitness @usuario"},
            {"caption": "Otro post con emoji ..."}
        ]

        stats = analyzer._analyze_statistics(posts)

        assert stats['total_posts'] == 3
        assert stats['uses_caps'] == True  # INCREIBLE
        assert stats['uses_ellipsis'] == True
        assert stats['question_marks'] == 1
        assert 'fitness' in stats['hashtags']
        assert 'usuario' in stats['mentions']

    def test_analyze_statistics_line_breaks(self):
        analyzer = ToneAnalyzer()
        posts = [
            {"caption": "Primera linea\nSegunda linea"}
        ]

        stats = analyzer._analyze_statistics(posts)
        assert stats['uses_line_breaks'] == True

    def test_analyze_statistics_empty(self):
        analyzer = ToneAnalyzer()
        stats = analyzer._analyze_statistics([])

        assert stats['total_posts'] == 0
        assert stats['avg_length'] == 0

    def test_create_default_profile(self):
        analyzer = ToneAnalyzer()
        profile = analyzer._create_default_profile("test_creator")

        assert profile.creator_id == "test_creator"
        assert profile.confidence_score == 0.0
        assert profile.formality == "informal"
        assert profile.energy == "alta"

    def test_merge_analyses_emoji_frequency_none(self):
        analyzer = ToneAnalyzer()

        stats = {
            'emojis': [],
            'emoji_counts': [],
            'hashtags': [],
            'uses_caps': False,
            'uses_ellipsis': False,
            'uses_line_breaks': False,
            'avg_length': 200,
            'question_marks': 0
        }

        profile = analyzer._merge_analyses("test", stats, {}, 3)
        assert profile.emoji_frequency == 'ninguna'

    def test_merge_analyses_emoji_frequency_low(self):
        analyzer = ToneAnalyzer()

        stats = {
            'emojis': ['...', '...'],  # 2 emojis en 3 posts = 0.67 per post
            'emoji_counts': [('...', 2)],
            'hashtags': [],
            'uses_caps': False,
            'uses_ellipsis': False,
            'uses_line_breaks': False,
            'avg_length': 200,
            'question_marks': 0
        }

        profile = analyzer._merge_analyses("test", stats, {}, 3)
        assert profile.emoji_frequency == 'baja'

    def test_merge_analyses_emoji_frequency_very_high(self):
        analyzer = ToneAnalyzer()

        stats = {
            'emojis': ['...'] * 20,  # 20 emojis en 3 posts = 6.67 per post
            'emoji_counts': [('...', 20)],
            'hashtags': [],
            'uses_caps': False,
            'uses_ellipsis': False,
            'uses_line_breaks': False,
            'avg_length': 200,
            'question_marks': 0
        }

        profile = analyzer._merge_analyses("test", stats, {}, 3)
        assert profile.emoji_frequency == 'muy_alta'

    def test_merge_analyses_message_length(self):
        analyzer = ToneAnalyzer()

        # Very short
        stats = {'emojis': [], 'emoji_counts': [], 'hashtags': [],
                 'uses_caps': False, 'uses_ellipsis': False,
                 'uses_line_breaks': False, 'avg_length': 30, 'question_marks': 0}
        profile = analyzer._merge_analyses("test", stats, {}, 1)
        assert profile.average_message_length == 'muy_corta'

        # Very long
        stats['avg_length'] = 1000
        profile = analyzer._merge_analyses("test", stats, {}, 1)
        assert profile.average_message_length == 'muy_larga'

    def test_merge_analyses_confidence_score_low(self):
        analyzer = ToneAnalyzer()
        stats = {
            'emojis': [], 'emoji_counts': [], 'hashtags': [],
            'uses_caps': False, 'uses_ellipsis': False,
            'uses_line_breaks': False, 'avg_length': 200, 'question_marks': 0
        }

        # Pocos posts = baja confianza
        profile = analyzer._merge_analyses("test", stats, {}, 3)
        assert profile.confidence_score == 0.30

    def test_merge_analyses_confidence_score_medium(self):
        analyzer = ToneAnalyzer()
        stats = {
            'emojis': [], 'emoji_counts': [], 'hashtags': [],
            'uses_caps': False, 'uses_ellipsis': False,
            'uses_line_breaks': False, 'avg_length': 200, 'question_marks': 0
        }

        profile = analyzer._merge_analyses("test", stats, {}, 10)
        assert profile.confidence_score == 0.70

    def test_merge_analyses_confidence_score_high(self):
        analyzer = ToneAnalyzer()
        stats = {
            'emojis': [], 'emoji_counts': [], 'hashtags': [],
            'uses_caps': False, 'uses_ellipsis': False,
            'uses_line_breaks': False, 'avg_length': 200, 'question_marks': 0
        }

        # Muchos posts = alta confianza
        profile = analyzer._merge_analyses("test", stats, {}, 30)
        assert profile.confidence_score == 0.95

    def test_merge_analyses_with_llm_data(self):
        analyzer = ToneAnalyzer()
        stats = {
            'emojis': [], 'emoji_counts': [], 'hashtags': [],
            'uses_caps': True, 'uses_ellipsis': True,
            'uses_line_breaks': True, 'avg_length': 200, 'question_marks': 5
        }
        llm_analysis = {
            'formality': 'muy_informal',
            'energy': 'muy_alta',
            'signature_phrases': ['vamos', 'crack'],
            'main_topics': ['fitness', 'nutricion']
        }

        profile = analyzer._merge_analyses("test", stats, llm_analysis, 10)

        assert profile.formality == 'muy_informal'
        assert profile.energy == 'muy_alta'
        assert profile.signature_phrases == ['vamos', 'crack']
        assert profile.main_topics == ['fitness', 'nutricion']
        assert profile.uses_caps_emphasis == True
        assert profile.uses_ellipsis == True


class TestQuickAnalyzeText:
    """Tests para quick_analyze_text."""

    def test_basic_analysis(self):
        result = quick_analyze_text("Hola! Como estas? ...")

        assert result['has_questions'] == True
        assert result['has_exclamations'] == True

    def test_length_and_words(self):
        result = quick_analyze_text("Una dos tres cuatro cinco")

        assert result['length'] == 25
        assert result['word_count'] == 5

    def test_caps_emphasis_detected(self):
        result = quick_analyze_text("Esto es INCREIBLE")
        assert result['has_caps_emphasis'] == True

    def test_caps_emphasis_not_detected(self):
        result = quick_analyze_text("Esto es normal")
        assert result['has_caps_emphasis'] == False

    def test_ellipsis_detected(self):
        result = quick_analyze_text("Pensando... que hacer")
        assert result['has_ellipsis'] == True

    def test_ellipsis_not_detected(self):
        result = quick_analyze_text("Sin puntos suspensivos")
        assert result['has_ellipsis'] == False

    def test_hashtags_mentions(self):
        result = quick_analyze_text("Gran dia #fitness #gym @trainer @coach")
        assert result['hashtag_count'] == 2
        assert result['mention_count'] == 2

    def test_no_hashtags_mentions(self):
        result = quick_analyze_text("Sin hashtags ni menciones")
        assert result['hashtag_count'] == 0
        assert result['mention_count'] == 0

    def test_empty_text(self):
        result = quick_analyze_text("")
        assert result['length'] == 0
        assert result['word_count'] == 1  # split on empty returns ['']
        assert result['has_questions'] == False
