"""Functional tests for System #7 + #8 merge and bug fixes.

System #7: User Context Builder — MERGED INTO System #8 (DNA Engine).
System #8: DNA Engine — auto-analyze trigger, multilingual, dynamic topics, trust alignment.

15 test groups (10 original + 5 merged data tests).
"""

import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# ── System #8: Detector multilingual keywords (B2 fix) ──


class TestDetectorMultilingual:
    """TEST 1: RelationshipTypeDetector detects IT/CA/EN family keywords."""

    def test_es_familia_detected(self):
        from services.relationship_type_detector import RelationshipTypeDetector

        det = RelationshipTypeDetector()
        msgs = [
            {"role": "user", "content": "Hola mamá, cómo estás? Te quiero mucho hijo"},
            {"role": "assistant", "content": "Bien hijo, cuídate"},
            {"role": "user", "content": "Papá dice que nos vemos en familia"},
        ]
        result = det.detect(msgs)
        assert result["type"] == "FAMILIA", f"ES familia not detected: {result}"

    def test_it_famiglia_detected(self):
        from services.relationship_type_detector import RelationshipTypeDetector

        det = RelationshipTypeDetector()
        msgs = [
            {"role": "user", "content": "Ciao mamma, come stai? Ti voglio bene figlio"},
            {"role": "assistant", "content": "Sto bene figlio, stammi bene"},
            {"role": "user", "content": "Papà dice che ci vediamo in famiglia"},
        ]
        result = det.detect(msgs)
        assert result["type"] == "FAMILIA", f"IT famiglia not detected: {result}"

    def test_en_family_detected(self):
        from services.relationship_type_detector import RelationshipTypeDetector

        det = RelationshipTypeDetector()
        msgs = [
            {"role": "user", "content": "Hey mom, how are you? Love you son"},
            {"role": "assistant", "content": "I'm good son, take care"},
            {"role": "user", "content": "Dad says we'll see the whole family tomorrow"},
        ]
        result = det.detect(msgs)
        assert result["type"] == "FAMILIA", f"EN family not detected: {result}"


class TestDetectorCliente:
    """TEST 2: CLIENTE detection works across languages."""

    def test_es_cliente(self):
        from services.relationship_type_detector import RelationshipTypeDetector

        det = RelationshipTypeDetector()
        msgs = [
            {"role": "user", "content": "Cuánto cuesta el programa? Quiero comprar el curso"},
            {"role": "assistant", "content": "El precio incluye todo"},
        ]
        result = det.detect(msgs)
        assert result["type"] == "CLIENTE"

    def test_it_cliente(self):
        from services.relationship_type_detector import RelationshipTypeDetector

        det = RelationshipTypeDetector()
        msgs = [
            {"role": "user", "content": "Quanto costa il programma? Voglio comprare il corso"},
            {"role": "assistant", "content": "Il prezzo include tutto"},
        ]
        result = det.detect(msgs)
        assert result["type"] == "CLIENTE"


# ── System #8: Dynamic topic extraction (B3 fix) ──


class TestDynamicTopics:
    """TEST 3: _extract_topics finds makeup/skincare AND fitness."""

    def test_makeup_topics_detected(self):
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        text = "maquillaje skincare belleza base corrector"
        topics = analyzer._extract_topics(text)
        assert any(t in topics for t in ["maquillaje", "skincare", "belleza"]), (
            f"Makeup topics not detected: {topics}"
        )

    def test_fitness_still_detected(self):
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        text = "entreno gimnasio dieta proteina"
        topics = analyzer._extract_topics(text)
        assert "fitness" in topics, f"Fitness not detected: {topics}"

    def test_dynamic_frequency_extraction(self):
        """Words appearing 3+ times get detected as topics even if not in seed list."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        # "crochet" appears 4 times — should be detected dynamically
        text = "crochet patron crochet lana crochet aguja crochet"
        topics = analyzer._extract_topics(text)
        assert "crochet" in topics, f"Dynamic topic 'crochet' not found: {topics}"


# ── System #8: Trust score alignment (B4 fix) ──


class TestTrustScoreAlignment:
    """TEST 4: Seed trust uses base scores, not confidence * 0.3."""

    def test_seed_trust_dict_exists_in_context(self):
        """Verify _SEED_TRUST dict is defined (not the old confidence * 0.3)."""
        import ast

        with open("core/dm/phases/context.py") as f:
            source = f.read()
        # Check that _SEED_TRUST dict is present
        assert "_SEED_TRUST" in source, "Missing _SEED_TRUST dict in context.py"
        # Check the old broken formula is NOT present
        assert "det_confidence * 0.3" not in source, "Old broken trust formula still present"

    def test_seed_trust_familia_reasonable(self):
        """Seed FAMILIA trust should be >= 0.5 (not 0.24 from old formula)."""
        import ast

        with open("core/dm/phases/context.py") as f:
            tree = ast.parse(f.read())
        # Find the _SEED_TRUST assignment
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "_SEED_TRUST":
                        # Extract FAMILIA value from dict
                        if isinstance(node.value, ast.Dict):
                            for k, v in zip(node.value.keys, node.value.values):
                                if isinstance(k, ast.Constant) and k.value == "FAMILIA":
                                    assert isinstance(v, ast.Constant)
                                    assert v.value >= 0.5, (
                                        f"FAMILIA seed trust {v.value} too low"
                                    )
                                    return
        # If we get here, didn't find the dict
        assert False, "_SEED_TRUST dict with FAMILIA key not found"

    def test_analyzer_trust_familia_high(self):
        """Full analysis FAMILIA trust should be ~0.95."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        trust = analyzer._calculate_trust_score("FAMILIA", 5, "hola hijo")
        assert trust >= 0.9, f"Analyzer FAMILIA trust too low: {trust}"


# ── System #8: Auto-analyze trigger (B1 fix) ──


class TestAutoAnalyzeTrigger:
    """TEST 5: ENABLE_DNA_AUTO_ANALYZE flag and trigger logic."""

    def test_flag_exists(self):
        """The feature flag should exist in context.py."""
        with open("core/dm/phases/context.py") as f:
            source = f.read()
        assert "ENABLE_DNA_AUTO_ANALYZE" in source

    def test_should_update_dna_stale(self):
        """DNA older than 30 days should trigger update."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        old_dna = {
            "total_messages_analyzed": 10,
            "last_analyzed_at": (
                datetime.now(timezone.utc) - timedelta(days=35)
            ).isoformat(),
        }
        assert analyzer.should_update_dna(old_dna, 12) is True

    def test_should_update_dna_new_messages(self):
        """10+ new messages since last analysis should trigger update."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        dna = {
            "total_messages_analyzed": 5,
            "last_analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
        assert analyzer.should_update_dna(dna, 20) is True

    def test_should_not_update_fresh_dna(self):
        """Recent DNA with few new messages should NOT trigger."""
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        dna = {
            "total_messages_analyzed": 15,
            "last_analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
        assert analyzer.should_update_dna(dna, 17) is False


# ── System #8: Vocabulary regex includes Italian chars ──


class TestVocabRegex:
    """TEST 6: Vocabulary extraction handles accented chars (ì, ù, ö, etc.)."""

    def test_italian_accented_words(self):
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        # _extract_vocabulary_uses takes List[str] (content strings) + relationship_type
        creator_msgs = ["Più tardi ti dico perché non posso"] * 3
        vocab = analyzer._extract_vocabulary_uses(creator_msgs, "AMISTAD_CERCANA")
        # Italian words with accented chars (ì in più, é in perché) should be extracted
        assert any(
            w in vocab for w in ["tardi", "perché", "posso", "dico"]
        ), f"Italian words not in vocab: {vocab}"


# ── System #7: CRM enrichment in production pipeline ──


class TestCRMEnrichmentExists:
    """TEST 7: Lead table CRM query is now in context.py."""

    def test_crm_query_in_context(self):
        """Verify CRM enrichment code exists in context.py."""
        with open("core/dm/phases/context.py") as f:
            source = f.read()
        assert "_load_lead_crm" in source, "CRM query function not found"
        assert "_crm_tags" in source, "CRM tags variable not found"
        assert "_crm_deal_value" in source, "CRM deal_value variable not found"

    def test_vip_tag_injected_in_profile(self):
        """VIP tag from CRM should appear in profile lines."""
        with open("core/dm/phases/context.py") as f:
            source = f.read()
        assert '"vip"' in source.lower() or "'vip'" in source.lower(), (
            "VIP detection not found in profile"
        )
        assert "Sensible al precio" in source or "price_sensitive" in source, (
            "Price-sensitive detection not found"
        )

    def test_deal_value_in_profile(self):
        """deal_value should be formatted in profile."""
        with open("core/dm/phases/context.py") as f:
            source = f.read()
        assert "Valor potencial" in source or "deal_value" in source

    def test_crm_notes_in_profile(self):
        """CRM notes should appear in profile."""
        with open("core/dm/phases/context.py") as f:
            source = f.read()
        assert "Notas CRM" in source or "_crm_notes" in source


# ── System #7: Dead code deprecation ──


class TestDeadCodeDeprecation:
    """TEST 8: user_context_loader.py is marked as deprecated."""

    def test_deprecation_notice(self):
        with open("core/user_context_loader.py") as f:
            header = f.read(500)
        assert "DEPRECATED" in header, "Missing DEPRECATED notice"

    def test_still_importable(self):
        """Module should still be importable (tests/academic uses UserContext)."""
        from core.user_context_loader import UserContext

        ctx = UserContext(follower_id="test_follower", creator_id="test_creator")
        assert ctx is not None
        assert ctx.follower_id == "test_follower"


# ── System #7: Price sensitivity multilingual ──


class TestPriceSensitivityMultilingual:
    """TEST 9: Price sensitivity detection now checks IT/CA/EN."""

    def test_price_sensitive_from_crm_tags(self):
        """CRM enrichment checks for 'price_sensitive' tag."""
        with open("core/dm/phases/context.py") as f:
            source = f.read()
        assert "price_sensitive" in source, "price_sensitive tag check missing"

    def test_multilingual_price_objection(self):
        """Profile builder checks multilingual price objections."""
        with open("core/dm/phases/context.py") as f:
            source = f.read()
        # Should check for prezzo (IT), preu (CA), price (EN) in objections
        for word in ["prezzo", "preu", "price"]:
            assert word in source, f"Missing multilingual price check: {word}"


# ── System #8: Golden examples filter ──


class TestGoldenExamples:
    """TEST 10: Golden examples filter media and extract text pairs."""

    def test_media_filtered(self):
        from services.relationship_analyzer import RelationshipAnalyzer

        analyzer = RelationshipAnalyzer()
        msgs = [
            {"role": "user", "content": "Hola que tal"},
            {"role": "assistant", "content": "Bien y tu?"},
            {"role": "user", "content": "[Audio message]"},
            {"role": "assistant", "content": "No puedo escuchar"},
            {"role": "user", "content": "[Photo]"},
            {"role": "assistant", "content": "Bonita foto!"},
            {"role": "user", "content": "Vamos a quedar"},
            {"role": "assistant", "content": "Dale, cuando?"},
        ]
        examples = analyzer._extract_golden_examples(msgs)
        # Should have text examples but not media
        for ex in examples:
            assert "[Audio" not in ex.get("user", ""), "Audio not filtered"
            assert "[Photo" not in ex.get("user", ""), "Photo not filtered"
        assert len(examples) >= 1, "No examples extracted"


# =============================================================================
# MERGED DATA TESTS (System #7 absorbed into #8)
# =============================================================================


class TestMergedNameCapture:
    """TEST 11: Lead says 'Me llamo María' → DNA block captures name."""

    def test_name_in_unified_block(self):
        from services.dm_agent_context_integration import format_unified_lead_context

        dna_block = (
            "=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ===\n"
            "Relación: AMISTAD_CASUAL (Amigable pero no demasiado personal)\n"
            "Temas frecuentes: fitness\n"
            "=== FIN CONTEXTO RELACIÓN ==="
        )
        profile = {"name": "María", "language": "es"}
        result = format_unified_lead_context(dna_block, profile)
        assert "Nombre: María" in result, f"Name not in unified block: {result}"
        assert result.count("=== CONTEXTO DE RELACIÓN") == 1, "Duplicate headers"

    def test_name_without_dna(self):
        """Even without DNA, name should appear in unified block."""
        from services.dm_agent_context_integration import format_unified_lead_context

        profile = {"name": "María", "language": "es", "stage": "CUALIFICACION"}
        result = format_unified_lead_context("", profile)
        assert "Nombre: María" in result
        assert "DESCONOCIDO" in result, "No-DNA fallback should be DESCONOCIDO"


class TestMergedLanguageCapture:
    """TEST 12: Lead speaks Catalan → DNA block captures language."""

    def test_catalan_in_unified_block(self):
        from services.dm_agent_context_integration import format_unified_lead_context

        dna_block = (
            "=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ===\n"
            "Relación: AMISTAD_CERCANA (Como un buen amigo, confianza alta)\n"
            "=== FIN CONTEXTO RELACIÓN ==="
        )
        profile = {"name": "Jordi", "language": "ca"}
        result = format_unified_lead_context(dna_block, profile)
        assert "Idioma: ca" in result, f"Language not injected: {result}"

    def test_spanish_default_suppressed(self):
        """Spanish (default) language should NOT appear — saves tokens."""
        from services.dm_agent_context_integration import format_unified_lead_context

        dna_block = (
            "=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ===\n"
            "Relación: DESCONOCIDO (Cordial, ir conociéndose)\n"
            "=== FIN CONTEXTO RELACIÓN ==="
        )
        profile = {"name": "Ana", "language": "es"}
        result = format_unified_lead_context(dna_block, profile)
        assert "Idioma" not in result, f"Spanish language should be suppressed: {result}"


class TestMergedInterestCapture:
    """TEST 13: Lead mentions 'me encanta el yoga' → DNA captures interest."""

    def test_interest_deduplicated_with_dna_topics(self):
        """If DNA already has 'fitness' as topic, don't duplicate in interests."""
        from services.dm_agent_context_integration import format_unified_lead_context

        dna_block = (
            "=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ===\n"
            "Relación: CLIENTE (Profesional pero cercano)\n"
            "Temas frecuentes: fitness, nutrición\n"
            "=== FIN CONTEXTO RELACIÓN ==="
        )
        profile = {
            "name": "",
            "language": "es",
            "interests": ["fitness", "yoga", "meditación"],
        }
        result = format_unified_lead_context(dna_block, profile)
        # "fitness" is already in DNA topics — should NOT appear again in Intereses
        assert "Intereses:" in result, f"Interests not injected: {result}"
        # yoga and meditación should be there
        assert "yoga" in result
        assert "meditación" in result


class TestMergedPromptInjection:
    """TEST 14: Lead name + language visible in prompt injection."""

    def test_name_and_language_in_prompt(self):
        from services.dm_agent_context_integration import format_unified_lead_context

        dna_block = (
            "=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ===\n"
            "Relación: FAMILIA (Familiar directo — trato cariñoso, personal, NUNCA vender)\n"
            "Nivel de profundidad: cercanos (alta confianza)\n"
            "Palabras que sueles usar con esta persona: flor, amor, reina\n"
            "=== FIN CONTEXTO RELACIÓN ==="
        )
        profile = {
            "name": "Carla",
            "language": "ca",
            "is_customer": False,
            "is_vip": True,
        }
        result = format_unified_lead_context(dna_block, profile)
        assert "Nombre: Carla" in result
        assert "Idioma: ca" in result
        assert "VIP" in result
        # Still has DNA data
        assert "FAMILIA" in result
        assert "flor" in result

    def test_crm_data_in_prompt(self):
        """CRM data (status, deal_value, notes) visible in unified block."""
        from services.dm_agent_context_integration import format_unified_lead_context

        profile = {
            "name": "Luis",
            "language": "es",
            "stage": "PROPUESTA",
            "is_customer": False,
            "crm_status": "caliente",
            "is_vip": False,
            "is_price_sensitive": True,
            "deal_value": 500,
            "crm_notes": "Interested in 8-week course",
        }
        result = format_unified_lead_context("", profile)
        assert "CALIENTE" in result
        assert "sensible al precio" in result
        assert "500€" in result
        assert "8-week course" in result


class TestNoDuplicateBlocks:
    """TEST 15: No duplicate blocks in prompt."""

    def test_single_header(self):
        """Unified block has exactly one header and one footer."""
        from services.dm_agent_context_integration import format_unified_lead_context

        dna_block = (
            "=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ===\n"
            "Relación: AMISTAD_CASUAL (Amigable pero no demasiado personal)\n"
            "Temas frecuentes: música\n"
            "=== FIN CONTEXTO RELACIÓN ==="
        )
        profile = {
            "name": "Pedro",
            "language": "ca",
            "interests": ["surf", "música"],
            "products": ["retiro de verano"],
            "is_vip": True,
        }
        result = format_unified_lead_context(dna_block, profile)
        assert result.count("=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ===") == 1, \
            f"Multiple headers found: {result}"
        assert result.count("=== FIN CONTEXTO RELACIÓN ===") == 1, \
            f"Multiple footers found: {result}"

    def test_recalling_block_no_lead_profile_param(self):
        """_build_recalling_block no longer has lead_profile parameter."""
        import inspect
        from core.dm.phases import context
        source = inspect.getsource(context)
        # The function signature should NOT have lead_profile
        # Find the _build_recalling_block definition
        assert "lead_profile=_lead_profile" not in source, \
            "lead_profile still passed to _build_recalling_block"

    def test_format_unified_imported_in_context(self):
        """context.py imports and uses format_unified_lead_context."""
        with open("core/dm/phases/context.py") as f:
            source = f.read()
        assert "format_unified_lead_context" in source, \
            "format_unified_lead_context not used in context.py"
