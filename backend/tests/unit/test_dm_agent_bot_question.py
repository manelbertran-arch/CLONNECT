"""Tests for bot_question_analyzer — vocab_meta DB integration + universal fallback.

Principio: zero hardcoding lingüístico. Las afirmaciones vienen de vocab_meta
mined per-creator; el fallback universal solo detecta emojis Unicode
convencionalmente afirmativos. Los tests usan mocks para simular creators con
vocab poblado vs vacío.
"""

import pytest


@pytest.fixture(autouse=True)
def _reset_vocab_cache_and_metrics():
    """Isolate each test — clear calibration_loader cache + BQA metrics."""
    from services.calibration_loader import _vocab_cache
    from core.bot_question_analyzer import reset_metrics
    _vocab_cache.clear()
    reset_metrics()
    yield
    _vocab_cache.clear()
    reset_metrics()


class TestBotQuestionAnalyzer:

    def test_01_flag_exists_in_correct_module(self):
        """BUG-8 fix — flag lives in core.dm.phases.context after refactor ae7adf52."""
        from core.dm.phases.context import ENABLE_QUESTION_CONTEXT
        assert isinstance(ENABLE_QUESTION_CONTEXT, bool)

    def test_02_module_importable_and_singleton(self):
        from core.bot_question_analyzer import get_bot_question_analyzer
        a1 = get_bot_question_analyzer()
        a2 = get_bot_question_analyzer()
        assert a1 is a2

    def test_03_analyze_seven_types(self):
        """Bot-side regex patterns son semánticos universales (no identity-dependent)."""
        from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer
        a = get_bot_question_analyzer()
        assert a.analyze("¿Te gustaría saber más?") == QuestionType.INTEREST
        assert a.analyze("¿Te paso el link de compra?") == QuestionType.PURCHASE
        assert a.analyze("¿Cómo prefieres pagar?") == QuestionType.PAYMENT_METHOD
        assert a.analyze("¿Quieres agendar una llamada?") == QuestionType.BOOKING
        assert a.analyze("¿Te quedó claro?") == QuestionType.CONFIRMATION
        assert a.analyze("¿Qué problema tienes?") == QuestionType.INFORMATION
        assert a.analyze("random text with zero patterns") == QuestionType.UNKNOWN

    # ─── vocab_meta mined path ─────────────────────────────────────────────

    def test_04_mined_vocab_from_vocab_meta(self, monkeypatch):
        """Creator con vocab_meta.affirmations poblado → usa vocab mined."""
        from core.bot_question_analyzer import is_short_affirmation
        import services.calibration_loader as cl
        fake_vocab = {
            "affirmations": ["si", "vale", "ok", "clar", "dale"],
            "blacklist_words": [],
        }
        monkeypatch.setattr(cl, "_load_creator_vocab", lambda cid: fake_vocab)

        assert is_short_affirmation("si", creator_id="iris_bertran") is True
        assert is_short_affirmation("vale", creator_id="iris_bertran") is True
        assert is_short_affirmation("clar", creator_id="iris_bertran") is True
        assert is_short_affirmation("dale", creator_id="iris_bertran") is True
        # Palabra NO en vocab mined → False (sin listas preasignadas)
        assert is_short_affirmation("yes", creator_id="iris_bertran") is False

    def test_05_mined_vocab_elongation_normalization(self, monkeypatch):
        """Vocab mined con 'si', 'ok' debe tolerar alargamientos 'siii', 'okkk'."""
        from core.bot_question_analyzer import is_short_affirmation
        import services.calibration_loader as cl
        monkeypatch.setattr(cl, "_load_creator_vocab",
                            lambda cid: {"affirmations": ["si", "ok", "vale"]})
        assert is_short_affirmation("siiii", creator_id="x") is True
        assert is_short_affirmation("okkk", creator_id="x") is True
        assert is_short_affirmation("sii", creator_id="x") is True
        # "vale" no tiene repetición → queda como está
        assert is_short_affirmation("vale", creator_id="x") is True

    def test_06_mined_vocab_multi_token(self, monkeypatch):
        """≤3 palabras todas en vocab mined → True."""
        from core.bot_question_analyzer import is_short_affirmation
        import services.calibration_loader as cl
        monkeypatch.setattr(cl, "_load_creator_vocab",
                            lambda cid: {"affirmations": ["ok", "si"]})
        assert is_short_affirmation("ok ok", creator_id="x") is True
        assert is_short_affirmation("si ok", creator_id="x") is True
        # Una palabra no está → False
        assert is_short_affirmation("ok nope", creator_id="x") is False

    # ─── Fallback universal (emoji-only) ────────────────────────────────────

    def test_07_fallback_none_creator_id(self):
        """creator_id=None → fallback universal (emojis únicamente)."""
        from core.bot_question_analyzer import is_short_affirmation, get_metrics
        assert is_short_affirmation("👍") is True
        assert is_short_affirmation("👌") is True
        assert is_short_affirmation("✅") is True
        # Palabras NO caen en fallback — vocab_meta es la única fuente.
        assert is_short_affirmation("si") is False
        assert is_short_affirmation("ok") is False
        assert is_short_affirmation("vale") is False
        m = get_metrics()
        assert m.get("vocab_source.fallback", 0) >= 3

    def test_08_fallback_empty_vocab(self, monkeypatch):
        """creator_id dado pero vocab_meta sin 'affirmations' → fallback + métrica empty."""
        from core.bot_question_analyzer import is_short_affirmation, get_metrics
        import services.calibration_loader as cl
        monkeypatch.setattr(cl, "_load_creator_vocab",
                            lambda cid: {"blacklist_words": ["x"]})  # sin affirmations
        assert is_short_affirmation("👍", creator_id="bootstrap_pending") is True
        assert is_short_affirmation("si", creator_id="bootstrap_pending") is False
        m = get_metrics()
        assert m.get("vocab_source.empty", 0) >= 1, "empty source metric must fire"
        assert m.get("vocab_source.fallback", 0) == 0

    def test_09_fallback_db_failure(self, monkeypatch):
        """Si _load_creator_vocab lanza excepción → degrada a fallback, no crash."""
        from core.bot_question_analyzer import is_short_affirmation
        import services.calibration_loader as cl
        def boom(cid):
            raise RuntimeError("db down")
        monkeypatch.setattr(cl, "_load_creator_vocab", boom)
        # No crash — cae a fallback
        assert is_short_affirmation("👍", creator_id="any") is True
        assert is_short_affirmation("si", creator_id="any") is False

    # ─── Guards estructurales universales (independientes de idioma) ───────

    def test_10_edge_cases_universal(self):
        """Guards que nunca dependen de listas."""
        from core.bot_question_analyzer import is_short_affirmation
        # None / empty
        assert is_short_affirmation(None) is False
        assert is_short_affirmation("") is False
        # whitespace-only (BUG-1)
        assert is_short_affirmation("   ") is False
        assert is_short_affirmation("\t\n ") is False
        # punct-only (BUG-2)
        for p in ["?", "??", "...", "!!!", "¿?", "¡!", ".,?"]:
            assert is_short_affirmation(p) is False
        # too long
        assert is_short_affirmation("si " * 20) is False

    def test_11_prometheus_source_metric_shape(self, monkeypatch):
        """Métrica vocab_source tiene las 3 labels esperadas."""
        from core.bot_question_analyzer import is_short_affirmation, get_metrics
        import services.calibration_loader as cl

        # Caso mined
        monkeypatch.setattr(cl, "_load_creator_vocab",
                            lambda cid: {"affirmations": ["si"]})
        is_short_affirmation("si", creator_id="iris")

        # Caso empty
        monkeypatch.setattr(cl, "_load_creator_vocab",
                            lambda cid: {"blacklist_words": []})
        is_short_affirmation("hola mundo", creator_id="stefano")

        # Caso fallback (None)
        is_short_affirmation("👍")

        m = get_metrics()
        assert m.get("vocab_source.mined", 0) >= 1
        assert m.get("vocab_source.empty", 0) >= 1
        assert m.get("vocab_source.fallback", 0) >= 1

    # ─── Backward compat callsite (prod L803) ───────────────────────────────

    def test_12_callsite_backward_compat(self, monkeypatch):
        """Llamada sin creator_id (legacy) sigue funcionando — no crash."""
        from core.bot_question_analyzer import is_short_affirmation
        # Legacy 1-arg invocation (no existing importers depend on it post-refactor,
        # but signature must remain tolerant)
        result = is_short_affirmation("test")
        assert isinstance(result, bool)
        # Legacy 1-arg with emoji in universal fallback
        assert is_short_affirmation("👍") is True

    def test_13_no_static_vocab_exports(self):
        """AFFIRMATION_WORDS ya NO existe. vocab_meta es la única fuente."""
        import core.bot_question_analyzer as mod
        assert not hasattr(mod, "AFFIRMATION_WORDS"), \
            "AFFIRMATION_WORDS hardcoded set debe estar eliminado — usar vocab_meta"
        # _UNIVERSAL_AFFIRMATION_EMOJI es fallback Unicode, no lista por idioma
        assert hasattr(mod, "_UNIVERSAL_AFFIRMATION_EMOJI")
        assert len(mod._UNIVERSAL_AFFIRMATION_EMOJI) <= 15, \
            "fallback universal debe mantenerse mínimo"

    def test_14_confidence_and_threshold(self):
        from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer
        a = get_bot_question_analyzer()
        assert a.analyze_with_confidence("¿Te paso el link?") == (QuestionType.PURCHASE, 0.92)
        _, conf = a.analyze_with_confidence("¿Te quedó claro?")
        assert conf >= 0.7

    def test_15_statement_to_interest(self):
        from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer
        a = get_bot_question_analyzer()
        assert a.analyze("son solo 50€") == QuestionType.INTEREST
        assert a.analyze("te va a encantar") == QuestionType.INTEREST
