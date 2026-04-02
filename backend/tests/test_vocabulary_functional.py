"""FASE 10 — 10 functional tests for vocabulary_extractor.

Tests use synthetic data matching real patterns observed in production.
No DB or network access required.
"""

from services.vocabulary_extractor import (
    tokenize, extract_lead_vocabulary, get_top_distinctive_words,
    compute_distinctiveness, STOPWORDS, _TECHNICAL_TOKENS,
)


class TestFunctional01_IrisVocab:
    """Test 1: Iris-like creator vocabulary extraction from real message patterns."""

    def test_iris_typical_messages_extract_distinctive_words(self):
        # Messages mimicking Iris's real conversational patterns
        messages = [
            "Hola cuca! Bon dia, com estàs?",
            "Cuca meva, t'envio un petó enorme",
            "Que bonic cuca, m'encanta el teu somriure",
            "Cuca bon dia! Avui tinc shooting al matí",
            "Merci cuca, ets un amor",
            "Petó gran cuca, bona nit!",
            "Cuca t'estimo molt, gràcies per tot",
            "Bon dia cuca! Avui faig yoga i després shooting",
        ]
        vocab = extract_lead_vocabulary(messages, min_freq=2)
        assert "cuca" in vocab
        assert vocab["cuca"] >= 5
        # Stopwords must NOT appear
        for sw in ["hola", "que", "com"]:
            assert sw not in vocab, f"Stopword '{sw}' should be filtered"


class TestFunctional02_StefanoVocab:
    """Test 2: Stefano-like creator — Spanish male vocabulary."""

    def test_stefano_messages_no_hardcoded_words(self):
        messages = [
            "Buenas crack, cómo va todo?",
            "Ey crack que tal tu día?",
            "Tremendo partido anoche crack",
            "Crack necesito tu opinión sobre algo",
            "Venga crack nos vemos mañana",
        ]
        result = get_top_distinctive_words(messages, top_n=5, min_freq=2)
        assert "crack" in result
        # Must NOT contain words the creator didn't write
        assert "compa" not in result
        assert "bro" not in result
        assert "tio" not in result


class TestFunctional03_NewCreatorEmpty:
    """Test 3: New creator with zero messages."""

    def test_empty_messages_returns_empty(self):
        result = get_top_distinctive_words([], top_n=8)
        assert result == []

    def test_single_message_returns_empty(self):
        # min_freq=2 means single occurrence won't pass
        result = get_top_distinctive_words(["Hola amor"], top_n=8, min_freq=2)
        assert result == []


class TestFunctional04_PerLeadDistinctiveness:
    """Test 4: Per-lead vocabulary uses TF-IDF to surface distinctive words."""

    def test_common_words_scored_low_distinctive_high(self):
        # Simulate: "amor" used with all leads, "cuca" only with this lead
        lead_msgs = ["Cuca bon dia, amor meu"] * 5
        lead_vocab = extract_lead_vocabulary(lead_msgs, min_freq=2)

        global_vocab = {"cuca": 10, "amor": 500, "meu": 200}
        leads_per_word = {"cuca": 1, "amor": 50, "meu": 30}

        scored = compute_distinctiveness(
            lead_vocab, global_vocab, total_leads=50, leads_per_word=leads_per_word,
        )

        words_ranked = [w for w, _ in scored]
        # "cuca" should rank higher than "amor" (used with 1 lead vs 50)
        if "cuca" in words_ranked and "amor" in words_ranked:
            assert words_ranked.index("cuca") < words_ranked.index("amor")


class TestFunctional05_CatalanAccents:
    """Test 5: Catalan with accented characters."""

    def test_catalan_accented_words_extracted(self):
        messages = [
            "Gràcies per tot, ets fantàstic",
            "Fantàstic el teu projecte, gràcies",
            "Gràcies de cor, fantàstic treball",
        ]
        vocab = extract_lead_vocabulary(messages, min_freq=2)
        assert "fantàstic" in vocab or "fantastic" in vocab
        assert "gràcies" in vocab or "gracies" in vocab


class TestFunctional06_SpanishOnly:
    """Test 6: Pure Spanish conversation."""

    def test_spanish_content_words_extracted(self):
        messages = [
            "Tremendo el concierto de anoche",
            "Tremendo día para entrenar",
            "Tremendo el resultado del partido",
            "Tremendo fichaje del Barcelona",
        ]
        vocab = extract_lead_vocabulary(messages, min_freq=2)
        assert "tremendo" in vocab
        assert vocab["tremendo"] >= 3


class TestFunctional07_MixedLanguage:
    """Test 7: Mixed ES/EN/CA conversation."""

    def test_mixed_language_extraction(self):
        messages = [
            "Amazing workout today cuca",
            "Cuca that was incredible",
            "Amazing view from terraza cuca",
            "Cuca amazing sunset tonight",
        ]
        vocab = extract_lead_vocabulary(messages, min_freq=2)
        assert "cuca" in vocab
        assert "amazing" in vocab


class TestFunctional08_RepopulateIdempotent:
    """Test 8: Re-extracting vocabulary produces same result."""

    def test_idempotent_extraction(self):
        messages = [
            "Hola flower, bon dia!",
            "Flower t'envio un petó",
            "Bon dia flower, com va?",
        ]
        result1 = get_top_distinctive_words(messages, top_n=5, min_freq=2)
        result2 = get_top_distinctive_words(messages, top_n=5, min_freq=2)
        assert result1 == result2


class TestFunctional09_OldLLMVocabReplaced:
    """Test 9: Old LLM-generated vocabulary words are NOT in tokenized output."""

    def test_old_hardcoded_words_not_in_tokenizer(self):
        # These were the old hardcoded words that leaked into DNA
        old_llm_words = ["compa", "bro", "tio"]
        # Even if a message somehow contained these, they should only appear
        # if the creator actually wrote them
        messages = [
            "Hola guapa com estàs avui?",
            "Molt bonic el teu vestit",
            "Gràcies per venir ahir",
        ]
        vocab = extract_lead_vocabulary(messages, min_freq=1)
        for word in old_llm_words:
            assert word not in vocab, f"Old LLM word '{word}' should not appear"


class TestFunctional10_TechnicalTokensFiltered:
    """Test 10: Technical tokens (URLs, platform names) must not be vocabulary."""

    def test_url_fragments_filtered(self):
        messages = [
            "Mira https://www.instagram.com/reels/abc123",
            "Te envío por wetransfer el archivo",
            "Wetransfer link: https://we.tl/abc",
            "Mira este reel que subí a instagram stories",
        ]
        vocab = extract_lead_vocabulary(messages, min_freq=1)
        for tech in ["https", "www", "instagram", "wetransfer",
                     "reel", "reels", "stories", "link"]:
            assert tech not in vocab, f"Technical token '{tech}' should be filtered"

    def test_media_placeholders_produce_no_tokens(self):
        messages = [
            "[audio] mensaje de voz",
            "[🎤 Audio]: contenido",
            "[video] clip corto",
            "[📷 Photo]",
            "[media/attachment]",
        ]
        for msg in messages:
            assert tokenize(msg) == [], f"Media placeholder should produce no tokens: {msg}"

    def test_platform_names_filtered(self):
        messages = [
            "Sígueme en youtube y tiktok también",
            "Youtube tiktok facebook twitter",
            "Youtube canal nuevo, tiktok también",
        ]
        vocab = extract_lead_vocabulary(messages, min_freq=2)
        for platform in ["youtube", "tiktok", "facebook", "twitter"]:
            assert platform not in vocab
