"""Audit tests for core/response_fixes.py."""

from core.response_fixes import (
    apply_all_response_fixes,
    apply_product_fixes,
    clean_raw_ctas,
    deduplicate_products,
    fix_broken_links,
    fix_identity_claim,
    fix_price_typo,
    hide_technical_errors,
    remove_catchphrases,
)

# =========================================================================
# TEST 1: Init / Import
# =========================================================================


class TestResponseFixesInit:
    """Verify all fix functions are importable and callable."""

    def test_all_fix_functions_importable(self):
        """All six individual fix functions and two aggregate functions import."""
        assert callable(fix_price_typo)
        assert callable(deduplicate_products)
        assert callable(fix_broken_links)
        assert callable(fix_identity_claim)
        assert callable(clean_raw_ctas)
        assert callable(hide_technical_errors)
        assert callable(apply_all_response_fixes)
        assert callable(apply_product_fixes)

    def test_fix_functions_accept_empty_string(self):
        """All text-fix functions handle empty string without error."""
        assert fix_price_typo("") == ""
        assert fix_broken_links("") == ""
        assert fix_identity_claim("") == ""
        assert clean_raw_ctas("") == ""
        assert hide_technical_errors("") == ""

    def test_fix_functions_accept_none(self):
        """All text-fix functions handle None gracefully (return falsy)."""
        assert not fix_price_typo(None)
        assert not fix_broken_links(None)
        assert not fix_identity_claim(None)
        assert not clean_raw_ctas(None)
        assert not hide_technical_errors(None)

    def test_deduplicate_products_empty_list(self):
        """deduplicate_products returns empty list for empty input."""
        assert deduplicate_products([]) == []

    def test_deduplicate_products_none(self):
        """deduplicate_products returns None for None input."""
        assert deduplicate_products(None) is None


# =========================================================================
# TEST 2: Happy Path - Broken Link Fix
# =========================================================================


class TestBrokenLinkFix:
    """FIX 3: Broken links ://www -> https://www."""

    def test_fixes_missing_protocol(self):
        """://www.example.com becomes https://www.example.com."""
        text = "Visita ://www.example.com para más info"
        result = fix_broken_links(text)
        assert "https://www.example.com" in result
        assert "://www.example.com" not in result or "https://www.example.com" in result

    def test_leaves_valid_urls_intact(self):
        """Already-valid https URLs are not modified."""
        text = "Visita https://www.example.com para más info"
        assert fix_broken_links(text) == text

    def test_price_typo_happy_path(self):
        """297? at end of sentence becomes 297 euros."""
        text = "El precio es 297? y lo puedes pagar"
        result = fix_price_typo(text)
        assert "297\u20ac" in result  # 297 followed by euro sign

    def test_identity_claim_fix(self):
        """'Soy Stefano' is rewritten to 'Soy el asistente de Stefano'."""
        text = "Soy Stefano y te voy a ayudar"
        result = fix_identity_claim(text)
        assert "asistente" in result.lower()

    def test_no_change_when_no_issues(self):
        """Clean text is returned unmodified."""
        text = "Hola, bienvenido al curso."
        assert fix_broken_links(text) == text
        assert fix_identity_claim(text) == text


# =========================================================================
# TEST 3: Edge Case - Duplicate Text Removal
# =========================================================================


class TestDuplicateRemoval:
    """FIX 2: Product deduplication by name."""

    def test_removes_exact_duplicates(self):
        """Products with same name (case-insensitive) are deduplicated."""
        products = [
            {"name": "Curso Marketing", "price": 99},
            {"name": "curso marketing", "price": 99},
            {"name": "Otro Curso", "price": 199},
        ]
        result = deduplicate_products(products)
        assert len(result) == 2
        names = [p["name"] for p in result]
        assert "Curso Marketing" in names
        assert "Otro Curso" in names

    def test_keeps_first_occurrence(self):
        """The first occurrence of a duplicate product is kept."""
        products = [
            {"name": "Curso", "price": 100},
            {"name": "curso", "price": 200},
        ]
        result = deduplicate_products(products)
        assert len(result) == 1
        assert result[0]["price"] == 100

    def test_products_without_names_skipped(self):
        """Products with empty/missing name are not tracked or deduplicated."""
        products = [
            {"name": "", "price": 50},
            {"name": "", "price": 60},
            {"name": "Real Product", "price": 99},
        ]
        result = deduplicate_products(products)
        # Empty names are not added to seen_names, so they are not kept
        # The first empty-name is skipped because `name and name not in seen_names`
        # requires `name` to be truthy
        assert any(p["name"] == "Real Product" for p in result)

    def test_single_product_no_change(self):
        """A single product list is returned unchanged."""
        products = [{"name": "Solo Curso", "price": 49}]
        result = deduplicate_products(products)
        assert len(result) == 1
        assert result[0]["name"] == "Solo Curso"

    def test_apply_product_fixes_delegates(self):
        """apply_product_fixes delegates to deduplicate_products."""
        products = [
            {"name": "A", "price": 1},
            {"name": "a", "price": 2},
        ]
        result = apply_product_fixes(products)
        assert len(result) == 1


# =========================================================================
# TEST 4: Error Handling - Empty Response and Technical Error Hiding
# =========================================================================


class TestErrorHandling:
    """FIX 6: Hide technical errors and handle edge cases."""

    def test_hides_error_prefix(self):
        """Messages starting with ERROR: are stripped."""
        text = "ERROR: Connection refused. Pero sigue intentando con calma."
        result = hide_technical_errors(text)
        assert "ERROR:" not in result

    def test_hides_python_exception(self):
        """Python exception types are removed from response text."""
        text = "TypeError: something broke. Por favor intenta de nuevo."
        result = hide_technical_errors(text)
        assert "TypeError" not in result

    def test_returns_empty_for_all_error_text(self):
        """If response is entirely error text, return empty for caller fallback."""
        text = "ERROR: boom."
        result = hide_technical_errors(text)
        assert result == ""

    def test_clean_raw_ctas_removes_shouting(self):
        """Raw CTAs like COMPRA AHORA are removed."""
        text = "Este curso es genial. COMPRA AHORA antes de que se acabe."
        result = clean_raw_ctas(text)
        assert "COMPRA AHORA" not in result
        assert "genial" in result

    def test_clean_raw_ctas_leaves_normal_text(self):
        """Normal text without CTAs passes through unchanged."""
        text = "Este curso tiene 20 horas de contenido práctico."
        result = clean_raw_ctas(text)
        assert result == text


# =========================================================================
# TEST 5: Integration - Multiple Fixes in One Message
# =========================================================================


class TestMultipleFixesIntegration:
    """apply_all_response_fixes chains all individual fixes."""

    def test_all_fixes_applied_together(self):
        """A message with multiple issues gets all fixes applied."""
        text = (
            "Soy Stefano. El precio es 297? y puedes ver más en "
            "://www.example.com. COMPRA AHORA y empieza ya."
        )
        result = apply_all_response_fixes(text, creator_name="Stefano")
        # FIX 3: broken link fixed
        assert "https://www.example.com" in result
        # FIX 4: identity claim fixed
        assert "asistente" in result.lower()
        # FIX 5: raw CTA removed
        assert "COMPRA AHORA" not in result

    def test_empty_input_returns_empty(self):
        """apply_all_response_fixes returns falsy for empty/None input."""
        assert not apply_all_response_fixes("")
        assert not apply_all_response_fixes(None)

    def test_clean_message_passes_through(self):
        """A clean message with no issues is returned intact."""
        text = "Hola, el curso incluye 20 horas de contenido."
        result = apply_all_response_fixes(text)
        assert result == text

    def test_fix_order_matters(self):
        """Price fix runs before error hiding so '297?' is fixed, not hidden."""
        text = "Cuesta 297? y ya."
        result = apply_all_response_fixes(text)
        assert "\u20ac" in result  # euro sign present

    def test_multiple_broken_links(self):
        """Multiple broken links in a single message are all fixed."""
        text = "Mira ://www.a.com y ://www.b.com para detalles"
        result = fix_broken_links(text)
        assert "https://www.a.com" in result
        assert "https://www.b.com" in result


class TestCatchphraseRemoval:
    """FIX 9: Global catchphrase removal tests."""

    def test_removes_que_te_llamo_la_atencion(self):
        """Core catchphrase is removed."""
        result = remove_catchphrases("Bueno, qué te llamó la atención? Contame más!")
        assert "llamó la atención" not in result
        assert "Contame más" in result

    def test_removes_without_accents(self):
        """Catchphrase without accents is also removed."""
        result = remove_catchphrases("Hola! que te llamo la atencion? Contame")
        assert "llamo la atencion" not in result

    def test_removes_que_te_trajo(self):
        """'Qué te trajo por acá' variant is removed."""
        result = remove_catchphrases("Hola! ¿Qué te trajo por acá? Me alegra verte!")
        assert "trajo por acá" not in result
        assert "Me alegra verte" in result

    def test_preserves_surrounding_content(self):
        """Content before and after catchphrase is preserved."""
        result = remove_catchphrases("Hola! ¿Qué te llamó la atención? Contame de lo que comparto!")
        assert "Hola" in result
        assert "Contame de lo que comparto" in result

    def test_no_match_unchanged(self):
        """Responses without catchphrases are unchanged."""
        text = "Hola! Cómo estás?"
        assert remove_catchphrases(text) == text

    def test_entire_catchphrase_returns_original(self):
        """If removing catchphrase would leave empty, return original."""
        result = remove_catchphrases("¿Qué te llamó la atención?")
        assert len(result) > 0
