"""Tests for bot_question_analyzer — 10 canonical + edge cases.

Cobertura:
    1. Flag exists (import from correct module after 2026-02 refactor).
    2. Module importable + singleton.
    3. Analyzer classifies each of 7 QuestionType values.
    4. Multilingual affirmation (ES/CA/IT/EN).
    5. Edge: whitespace/punct/None.
    6. Edge: emojis 👍👌✅.
    7. Edge: elongations sii/okkkk/perfeeecto.
    8. Regression: BUG-1 "   ", BUG-2 "??", BUG-3 👍, BUG-4 sii.
    9. Data-derived vocab loads correctly.
   10. Confidence mapping respects 0.7 threshold.
"""


class TestBotQuestionAnalyzer:
    def test_01_flag_exists_in_correct_module(self):
        """BUG-8 fix — flag lives in core.dm.phases.context after refactor ae7adf52."""
        from core.dm.phases.context import ENABLE_QUESTION_CONTEXT
        assert isinstance(ENABLE_QUESTION_CONTEXT, bool)

    def test_02_module_importable_and_singleton(self):
        from core.bot_question_analyzer import get_bot_question_analyzer
        a1 = get_bot_question_analyzer()
        a2 = get_bot_question_analyzer()
        assert a1 is a2, "singleton must return same instance"

    def test_03_analyze_seven_types(self):
        from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer
        a = get_bot_question_analyzer()
        assert a.analyze("¿Te gustaría saber más?") == QuestionType.INTEREST
        assert a.analyze("¿Te paso el link de compra?") == QuestionType.PURCHASE
        assert a.analyze("¿Cómo prefieres pagar?") == QuestionType.PAYMENT_METHOD
        assert a.analyze("¿Quieres agendar una llamada?") == QuestionType.BOOKING
        assert a.analyze("¿Te quedó claro?") == QuestionType.CONFIRMATION
        assert a.analyze("¿Qué problema tienes?") == QuestionType.INFORMATION
        assert a.analyze("random text with zero patterns") == QuestionType.UNKNOWN

    def test_04_multilingual_affirmations(self):
        from core.bot_question_analyzer import is_short_affirmation
        for es in ["si", "sí", "ok", "vale", "dale", "claro", "perfecto"]:
            assert is_short_affirmation(es), f"ES: {es!r}"
        for ca in ["clar", "perfecte", "top", "va bé", "d'acord", "endavant"]:
            assert is_short_affirmation(ca), f"CA: {ca!r}"
        for it in ["sì", "certo", "perfetto", "va bene", "d'accordo", "capito"]:
            assert is_short_affirmation(it), f"IT: {it!r}"
        for en in ["yes", "sure", "alright", "yep", "cool", "got it", "done"]:
            assert is_short_affirmation(en), f"EN: {en!r}"

    def test_05_edge_null_and_long(self):
        from core.bot_question_analyzer import is_short_affirmation
        assert is_short_affirmation(None) is False
        assert is_short_affirmation("") is False
        assert is_short_affirmation("   ") is False  # BUG-1
        assert is_short_affirmation("\t\n  ") is False
        assert is_short_affirmation("si " * 20) is False  # >30 chars
        assert is_short_affirmation("Quiero saber más del curso de python") is False

    def test_06_edge_punct_only(self):
        """BUG-2 regression — punct-only must be False."""
        from core.bot_question_analyzer import is_short_affirmation
        for punct in ["?", "??", "...", "!!!", "¿?", "¡!", ".,?", "---"]:
            assert is_short_affirmation(punct) is False, f"punct: {punct!r}"

    def test_07_emoji_affirmations(self):
        """BUG-3 regression — thumbs/check/muscle emojis count as affirmation."""
        from core.bot_question_analyzer import is_short_affirmation
        for emoji in ["👍", "👌", "🙌", "✅", "💪", "🙏", "🤙", "💯", "👏"]:
            assert is_short_affirmation(emoji) is True, f"emoji: {emoji!r}"

    def test_08_elongation_normalization(self):
        """BUG-4 regression — sii, siiiii, okkkk, perfeeecto all accepted."""
        from core.bot_question_analyzer import is_short_affirmation
        assert is_short_affirmation("sii") is True
        assert is_short_affirmation("siiiiii") is True
        assert is_short_affirmation("okkkk") is True
        assert is_short_affirmation("perfeeecto") is True
        # palabras legítimas con letras dobles (cool, sounds good) siguen funcionando
        assert is_short_affirmation("cool") is True
        assert is_short_affirmation("sounds good") is True
        # palabras con dobles que NO están en vocab siguen siendo False
        assert is_short_affirmation("coffee") is False

    def test_09_data_derived_vocab_loads(self):
        """Vocab JSON loader funciona y expone términos base."""
        from core.bot_question_analyzer import _load_vocab, AFFIRMATION_WORDS
        vocab = _load_vocab()
        for w in ["si", "ok", "vale", "clar", "certo", "yes", "👍"]:
            assert w in vocab, f"{w!r} missing from loaded vocab"
        # backward compat: AFFIRMATION_WORDS export still importable
        assert "si" in AFFIRMATION_WORDS

    def test_10_confidence_and_threshold(self):
        from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer
        a = get_bot_question_analyzer()
        assert a.analyze_with_confidence("¿Te paso el link?") == (QuestionType.PURCHASE, 0.92)
        assert a.analyze_with_confidence("¿Cómo prefieres pagar?") == (QuestionType.PAYMENT_METHOD, 0.90)
        assert a.analyze_with_confidence("¿Quieres agendar?") == (QuestionType.BOOKING, 0.88)
        assert a.analyze_with_confidence("¿Te gustaría saber más?") == (QuestionType.INTEREST, 0.85)
        # CONFIRMATION 0.70 pasa el umbral 0.7 del callsite injection
        _, conf = a.analyze_with_confidence("¿Te quedó claro?")
        assert conf >= 0.7, "CONFIRMATION conf must meet injection threshold"
        # UNKNOWN 0.50 NO pasa
        _, u_conf = a.analyze_with_confidence("random no-pattern text")
        assert u_conf < 0.7

    def test_11_statement_expecting_response_to_interest(self):
        """Statements sin `?` (ofertas, precios) → INTEREST para inyección útil."""
        from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer
        a = get_bot_question_analyzer()
        assert a.analyze("son solo 50€") == QuestionType.INTEREST
        assert a.analyze("te va a encantar") == QuestionType.INTEREST
        assert a.analyze("podemos hacerlo juntos") == QuestionType.INTEREST

    def test_12_priority_purchase_over_interest(self):
        """Mensaje con 'link' gana INTEREST porque compra tiene prioridad."""
        from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer
        a = get_bot_question_analyzer()
        assert a.analyze("¿Te paso el link? te interesa") == QuestionType.PURCHASE
