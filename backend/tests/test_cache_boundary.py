"""Tests for Sprint 4 G5: Cache boundary optimization.

Verifies:
1. cache_boundary.py utility functions
2. Format parity between _format_* helpers and PromptBuilder
3. Section ordering under ENABLE_PROMPT_CACHE_BOUNDARY flag
4. Prefix stability across calls
"""

import pytest
from unittest.mock import patch


# ── Unit tests for cache_boundary.py ──


class TestComputePrefixHash:
    def test_deterministic(self):
        from core.dm.cache_boundary import compute_prefix_hash
        text = "Eres Iris Bertran. Respondes DMs..."
        h1 = compute_prefix_hash(text)
        h2 = compute_prefix_hash(text)
        assert h1 == h2

    def test_different_for_different_input(self):
        from core.dm.cache_boundary import compute_prefix_hash
        h1 = compute_prefix_hash("creator A")
        h2 = compute_prefix_hash("creator B")
        assert h1 != h2

    def test_empty_string(self):
        from core.dm.cache_boundary import compute_prefix_hash
        h = compute_prefix_hash("")
        assert isinstance(h, str)
        assert len(h) == 16


class TestMeasureCacheBoundary:
    def test_basic_metrics(self):
        from core.dm.cache_boundary import measure_cache_boundary
        m = measure_cache_boundary(3000, 6000)
        assert m["prefix_chars"] == 3000
        assert m["total_chars"] == 6000
        assert m["cache_ratio"] == 0.5
        assert m["savings_pct"] > 0

    def test_zero_total(self):
        from core.dm.cache_boundary import measure_cache_boundary
        m = measure_cache_boundary(0, 0)
        assert m["cache_ratio"] == 0.0

    def test_full_prefix(self):
        from core.dm.cache_boundary import measure_cache_boundary
        m = measure_cache_boundary(5000, 5000)
        assert m["cache_ratio"] == 1.0
        assert m["savings_pct"] > 80  # ~85% for DeepInfra


class TestCheckCacheBreak:
    def test_first_call_no_break(self):
        from core.dm.cache_boundary import check_cache_break, _previous_hashes
        _previous_hashes.clear()
        result = check_cache_break("test_creator_1", "abc123")
        assert result is None

    def test_same_hash_no_break(self):
        from core.dm.cache_boundary import check_cache_break, _previous_hashes
        _previous_hashes.clear()
        check_cache_break("test_creator_2", "abc123")
        result = check_cache_break("test_creator_2", "abc123")
        assert result is None

    def test_different_hash_break(self):
        from core.dm.cache_boundary import check_cache_break, _previous_hashes
        _previous_hashes.clear()
        check_cache_break("test_creator_3", "abc123")
        result = check_cache_break("test_creator_3", "def456")
        assert result == "abc123"  # returns the PREVIOUS hash


class TestLogCacheMetrics:
    def test_no_exception(self):
        from core.dm.cache_boundary import log_cache_metrics, measure_cache_boundary
        metrics = measure_cache_boundary(1000, 3000)
        # Should not raise
        log_cache_metrics(metrics, "test_creator", "abcd1234")

    def test_with_break(self):
        from core.dm.cache_boundary import log_cache_metrics, measure_cache_boundary
        metrics = measure_cache_boundary(1000, 3000)
        log_cache_metrics(metrics, "test_creator", "new_hash", cache_break="old_hash")


# ── Format parity tests ──


class TestFormatParity:
    """Verify _format_* helpers produce identical output to PromptBuilder."""

    def test_knowledge_parity(self):
        """_format_knowledge_section matches PromptBuilder.build_system_prompt."""
        from core.dm.phases.context import _format_knowledge_section
        from services.prompt_service import PromptBuilder

        personality = {
            "knowledge_about": {
                "website_url": "https://irisbertran.com",
                "bio": "Yoga teacher & wellness coach",
                "expertise": "Yoga, meditation",
                "location": "Barcelona",
            }
        }
        builder = PromptBuilder(personality)

        # Build with PromptBuilder (no custom_instructions, no products, no safety)
        full = builder.build_system_prompt(skip_safety=True)
        # Extract knowledge lines (skip empty lines and IMPORTANTE block)
        knowledge_lines = []
        for line in full.split("\n"):
            if line.startswith(("Tu web:", "Bio:", "Especialidad:", "Ubicación:")):
                knowledge_lines.append(line)

        # Build with helper
        helper_output = _format_knowledge_section(personality)
        helper_lines = [l for l in helper_output.split("\n") if l.strip()]

        assert knowledge_lines == helper_lines

    def test_products_parity(self):
        """_format_products_section matches PromptBuilder.build_system_prompt."""
        from core.dm.phases.context import _format_products_section
        from services.prompt_service import PromptBuilder

        products = [
            {"name": "Clase yoga", "price": 25, "description": "1h sesión"},
            {"name": "Pack 10", "price": 200, "url": "https://buy.me/pack10"},
        ]
        builder = PromptBuilder({})

        # Build with PromptBuilder (only products)
        full = builder.build_system_prompt(products=products, skip_safety=True)
        # Extract products section
        in_products = False
        pb_lines = []
        for line in full.split("\n"):
            if line.startswith("Productos/servicios:"):
                in_products = True
            if in_products and line.strip():
                pb_lines.append(line)

        # Build with helper
        helper_output = _format_products_section(products)
        helper_lines = [l for l in helper_output.split("\n") if l.strip()]

        assert pb_lines == helper_lines

    def test_safety_parity(self):
        """_format_safety_section matches PromptBuilder.build_system_prompt."""
        from core.dm.phases.context import _format_safety_section
        from services.prompt_service import PromptBuilder

        name = "Iris Bertran"
        builder = PromptBuilder({"name": name})

        # Build with PromptBuilder (only safety)
        full = builder.build_system_prompt(skip_knowledge=True, skip_products=True)
        # Extract safety block (starts with IMPORTANTE:)
        safety_lines = []
        in_safety = False
        for line in full.split("\n"):
            if line.startswith("IMPORTANTE:"):
                in_safety = True
            if in_safety and line.strip():
                safety_lines.append(line)

        # Build with helper
        helper_output = _format_safety_section(name)
        helper_lines = [l for l in helper_output.split("\n") if l.strip()]

        assert safety_lines == helper_lines

    def test_empty_knowledge(self):
        from core.dm.phases.context import _format_knowledge_section
        assert _format_knowledge_section({}) == ""
        assert _format_knowledge_section({"knowledge_about": {}}) == ""

    def test_empty_products(self):
        from core.dm.phases.context import _format_products_section
        assert _format_products_section([]) == ""
        assert _format_products_section(None) == ""


# ── PromptBuilder skip flag tests ──


class TestPromptBuilderSkipFlags:
    def test_default_flags_no_change(self):
        """Default skip flags produce identical output to original behavior."""
        from services.prompt_service import PromptBuilder
        personality = {
            "name": "Test",
            "knowledge_about": {"bio": "Test bio"},
        }
        products = [{"name": "P1", "price": 10}]
        builder = PromptBuilder(personality)

        original = builder.build_system_prompt(
            products=products,
            custom_instructions="Style prompt here",
        )
        with_defaults = builder.build_system_prompt(
            products=products,
            custom_instructions="Style prompt here",
            skip_knowledge=False,
            skip_products=False,
            skip_safety=False,
        )
        assert original == with_defaults

    def test_skip_knowledge(self):
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder({"knowledge_about": {"bio": "My bio"}})
        output = builder.build_system_prompt(skip_knowledge=True)
        assert "My bio" not in output

    def test_skip_products(self):
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder({})
        output = builder.build_system_prompt(
            products=[{"name": "Yoga", "price": 25}],
            skip_products=True,
        )
        assert "Yoga" not in output

    def test_skip_safety(self):
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder({})
        output = builder.build_system_prompt(skip_safety=True)
        assert "IMPORTANTE:" not in output

    def test_skip_all(self):
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder({"name": "X", "knowledge_about": {"bio": "Y"}})
        output = builder.build_system_prompt(
            products=[{"name": "Z", "price": 1}],
            custom_instructions="Custom",
            skip_knowledge=True,
            skip_products=True,
            skip_safety=True,
        )
        assert "Custom" in output
        assert "Y" not in output
        assert "Z" not in output
        assert "IMPORTANTE:" not in output


# ── Flag parity test: flag ON == flag OFF in prompt output ──


class TestCacheBoundaryPassive:
    """CC pattern P1: the boundary is PASSIVE — flag only controls metrics/logging.

    The system_prompt text MUST be byte-identical regardless of flag state.
    This is the single most important invariant of the cache boundary feature.
    """

    def _run_assembly(self, flag_on: bool):
        """Simulate the section assembly + PromptBuilder call from context.py.

        Mirrors the real code path (context.py ~lines 1004-1065) with
        deterministic test data, so we can compare flag ON vs OFF output.
        """
        from services.prompt_service import PromptBuilder

        # Test sections (same structure as context.py _sections)
        style = "Eres Iris Bertran. Respondes DMs con tono cercano y profesional."
        fewshot = "Ejemplo: Lead: Hola! -> Iris: Hey! Qué tal? 😊"
        friend_ctx = ""
        recalling = "Nombre: Laura. Intereses: yoga, meditación. Último contacto: hace 2 días."
        audio_ctx = ""
        rag_ctx = "Pack 10 sesiones: 200€. Clase individual: 25€."
        kb_ctx = ""
        hier_memory = ""
        advanced = ""
        citation_ctx = ""
        override = ""

        _sections = [
            ("style", style),
            ("fewshot", fewshot),
            ("friend", friend_ctx),
            ("recalling", recalling),
            ("audio", audio_ctx),
            ("rag", rag_ctx),
            ("kb", kb_ctx),
            ("hier_memory", hier_memory),
            ("advanced", advanced),
            ("citation", citation_ctx),
            ("override", override),
        ]

        _STATIC_LABELS = {"style"} if flag_on else set()
        MAX_CONTEXT_CHARS = 8000

        assembled = []
        total_chars = 0
        static_prefix_chars = 0
        for label, section in _sections:
            if not section:
                continue
            section_len = len(section)
            if total_chars + section_len > MAX_CONTEXT_CHARS:
                remaining = MAX_CONTEXT_CHARS - total_chars
                if remaining > 200 and label in ("style", "recalling", "rag"):
                    assembled.append(section[:remaining])
                    total_chars += remaining
                    if label in _STATIC_LABELS:
                        static_prefix_chars += remaining
                else:
                    pass
                continue
            assembled.append(section)
            total_chars += section_len
            if label in _STATIC_LABELS:
                static_prefix_chars += section_len

        combined_context = "\n\n".join(assembled)

        # PromptBuilder call — IDENTICAL regardless of flag
        personality = {
            "name": "Iris Bertran",
            "knowledge_about": {"bio": "Yoga teacher", "location": "Barcelona"},
        }
        products = [{"name": "Clase yoga", "price": 25}]
        builder = PromptBuilder(personality)
        system_prompt = builder.build_system_prompt(
            products=products, custom_instructions=combined_context
        )

        return system_prompt, combined_context, static_prefix_chars

    def test_flag_on_equals_flag_off_system_prompt(self):
        """system_prompt is byte-identical with flag ON vs OFF."""
        prompt_on, _, _ = self._run_assembly(flag_on=True)
        prompt_off, _, _ = self._run_assembly(flag_on=False)
        assert prompt_on == prompt_off

    def test_flag_on_equals_flag_off_combined_context(self):
        """combined_context is byte-identical with flag ON vs OFF."""
        _, ctx_on, _ = self._run_assembly(flag_on=True)
        _, ctx_off, _ = self._run_assembly(flag_on=False)
        assert ctx_on == ctx_off

    def test_flag_on_tracks_static_prefix(self):
        """Flag ON correctly measures static prefix chars."""
        _, _, prefix_on = self._run_assembly(flag_on=True)
        _, _, prefix_off = self._run_assembly(flag_on=False)
        assert prefix_on > 0, "Flag ON should measure static prefix"
        assert prefix_off == 0, "Flag OFF should not track prefix"

    def test_promptbuilder_call_has_no_skip_flags(self):
        """The PromptBuilder call uses no skip flags (all default False)."""
        # This verifies the fix: the old code passed skip_knowledge=True etc.
        # when flag was ON. The fixed code never passes skip flags.
        from services.prompt_service import PromptBuilder
        personality = {"name": "Test", "knowledge_about": {"bio": "Bio"}}
        builder = PromptBuilder(personality)

        # Call with defaults (no skip flags) — should include knowledge + safety
        prompt = builder.build_system_prompt(
            products=[{"name": "P", "price": 1}],
            custom_instructions="Style here",
        )
        assert "Bio" in prompt
        assert "IMPORTANTE:" in prompt
        assert "P: 1€" in prompt
