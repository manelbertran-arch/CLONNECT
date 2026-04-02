"""Tests for vocabulary_extractor — data-mined, per-lead, TF-IDF.

Validates:
- Word-boundary matching (not substring)
- Stopword filtering
- Frequency thresholds
- TF-IDF distinctiveness scoring
- Unicode handling
- Media placeholder filtering
"""

import pytest
from services.vocabulary_extractor import (
    STOPWORDS,
    tokenize,
    extract_lead_vocabulary,
    compute_distinctiveness,
    get_top_distinctive_words,
)


class TestTokenize:
    """Word-boundary tokenization tests."""

    def test_basic_tokenization(self):
        tokens = tokenize("Hola cuca, com estàs avui?")
        assert "cuca" in tokens
        assert "avui" in tokens

    def test_word_boundary_compa_not_in_acompanyar(self):
        """CRITICAL: 'compa' must NOT be extracted from 'acompanyar'."""
        tokens = tokenize("Voy a acompanyarte al retiro")
        assert "compa" not in tokens
        assert "acompanyarte" in tokens

    def test_word_boundary_compa_not_in_compartir(self):
        tokens = tokenize("Quiero compartir esto contigo")
        assert "compa" not in tokens
        assert "compartir" in tokens

    def test_word_boundary_bro_not_in_problemas(self):
        tokens = tokenize("Tengo problemas con el browser")
        assert "bro" not in tokens
        assert "problemas" in tokens
        assert "browser" in tokens

    def test_standalone_compa_is_captured(self):
        tokens = tokenize("Ya te digo algo, compa")
        assert "compa" in tokens

    def test_stopwords_filtered(self):
        tokens = tokenize("que de la el en y a los las")
        assert len(tokens) == 0

    def test_catalan_stopwords(self):
        tokens = tokenize("perquè amb els però ara hem fer")
        assert len(tokens) == 0

    def test_unicode_accented_words(self):
        tokens = tokenize("Tío, carinyo, café tranquilo")
        assert "tío" in tokens
        assert "carinyo" in tokens
        assert "café" in tokens
        assert "tranquilo" in tokens

    def test_short_words_excluded(self):
        """Words < 3 chars should be excluded."""
        tokens = tokenize("yo tu no si ok de la")
        assert len(tokens) == 0

    def test_digits_excluded(self):
        tokens = tokenize("tengo 300 euros y 42 años")
        assert "300" not in tokens
        assert "42" not in tokens  # "42" is only 2 chars anyway
        assert "euros" in tokens
        assert "años" in tokens

    def test_media_placeholder_skipped(self):
        assert tokenize("[🎤 Audio]: algo") == []
        assert tokenize("[media/attachment]") == []
        assert tokenize("[📷 Photo]") == []

    def test_real_message_not_skipped(self):
        tokens = tokenize("Bon dia reina!")
        assert "bon" in tokens or "dia" in tokens or "reina" in tokens


class TestExtractLeadVocabulary:
    """Frequency-based vocabulary extraction tests."""

    def test_basic_extraction(self):
        messages = [
            "Hola cuca, bon dia!",
            "Cuca, que tal avui?",
            "Adeu cuca!",
        ]
        vocab = extract_lead_vocabulary(messages, min_freq=2)
        assert "cuca" in vocab
        assert vocab["cuca"] >= 2

    def test_min_freq_filter(self):
        messages = ["Hola reina", "Bon dia"]
        vocab = extract_lead_vocabulary(messages, min_freq=2)
        assert "reina" not in vocab  # appears only once

    def test_adaptive_threshold_large_conversations(self):
        """For 50+ messages, threshold should be raised to 3."""
        messages = ["palabra rara"] * 2 + ["otro mensaje normal"] * 50
        vocab = extract_lead_vocabulary(messages, min_freq=2)
        # "rara" appears only 2x, but with 52 messages the adaptive threshold is 3
        assert "rara" not in vocab

    def test_empty_messages(self):
        assert extract_lead_vocabulary([]) == {}
        assert extract_lead_vocabulary(["", ""]) == {}

    def test_stopwords_not_in_result(self):
        messages = ["que bueno que estás bien"] * 5
        vocab = extract_lead_vocabulary(messages, min_freq=2)
        for sw in ["que", "bueno", "bien"]:
            assert sw not in vocab


class TestComputeDistinctiveness:
    """TF-IDF distinctiveness scoring tests."""

    def test_unique_word_scores_higher(self):
        """A word used only with lead A should score higher than a common word."""
        lead_vocab = {"cuca": 5, "genial": 5}
        global_vocab = {"cuca": 5, "genial": 100}
        leads_per_word = {"cuca": 1, "genial": 20}

        scored = compute_distinctiveness(
            lead_vocab, global_vocab, total_leads=20,
            leads_per_word=leads_per_word,
        )
        scores = dict(scored)
        assert scores["cuca"] > scores["genial"]

    def test_empty_lead_vocab(self):
        assert compute_distinctiveness({}, {"word": 10}, 5) == []

    def test_single_lead(self):
        """With 1 lead, all words should score > 0."""
        lead_vocab = {"hello": 3, "world": 2}
        scored = compute_distinctiveness(lead_vocab, {}, total_leads=1)
        assert len(scored) == 2
        assert all(s >= 0 for _, s in scored)


class TestGetTopDistinctiveWords:
    """Integration test for the main entry point."""

    def test_with_global_corpus(self):
        messages = [
            "Hola flower, bon dia!",
            "Flower, que tal?",
            "Adeu flower, un petó!",
        ]
        global_vocab = {"flower": 3, "bon": 100, "dia": 100, "tal": 100, "adeu": 50, "petó": 20}
        leads_per_word = {"flower": 1, "bon": 20, "dia": 20, "tal": 20, "adeu": 10, "petó": 5}

        words = get_top_distinctive_words(
            messages,
            global_vocab=global_vocab,
            total_leads=20,
            leads_per_word=leads_per_word,
        )
        # "flower" should be #1 since it only appears with this lead
        assert "flower" in words[:3]

    def test_without_global_corpus(self):
        """Fallback: frequency-only when no global corpus."""
        messages = ["Hola reina"] * 5 + ["Bon dia guapa"] * 3
        words = get_top_distinctive_words(messages, top_n=3)
        assert len(words) <= 3

    def test_returns_max_top_n(self):
        messages = ["alpha beta gamma delta epsilon"] * 10
        words = get_top_distinctive_words(messages, top_n=3)
        assert len(words) <= 3

    def test_empty_input(self):
        assert get_top_distinctive_words([]) == []
        assert get_top_distinctive_words(["", ""]) == []


class TestStopwordsCompleteness:
    """Verify stopwords cover the most common function words."""

    def test_spanish_stopwords(self):
        for w in ["de", "la", "el", "que", "pero", "como", "más", "hola", "gracias"]:
            assert w in STOPWORDS, f"Missing Spanish stopword: {w}"

    def test_catalan_stopwords(self):
        for w in ["és", "amb", "però", "perquè", "molt"]:
            assert w in STOPWORDS, f"Missing Catalan stopword: {w}"

    def test_english_stopwords(self):
        for w in ["the", "is", "and", "but", "with", "from"]:
            assert w in STOPWORDS, f"Missing English stopword: {w}"

    def test_universal_non_distinctive(self):
        for w in ["jaja", "jajaja", "haha", "lol"]:
            assert w in STOPWORDS, f"Missing universal stopword: {w}"
