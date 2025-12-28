"""
Tests for reasoning modules: SelfConsistency, ChainOfThought, Reflexion
"""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestSelfConsistency:
    """Tests for SelfConsistencyValidator"""

    def test_import(self):
        """Test that module can be imported"""
        from core.reasoning import SelfConsistencyValidator, get_self_consistency_validator
        assert SelfConsistencyValidator is not None
        assert get_self_consistency_validator is not None

    def test_calculate_similarity(self):
        """Test text similarity calculation"""
        from core.reasoning.self_consistency import SelfConsistencyValidator

        mock_llm = MagicMock()
        validator = SelfConsistencyValidator(mock_llm)

        # Identical texts
        sim = validator._calculate_similarity("hola mundo", "hola mundo")
        assert sim == 1.0

        # Similar texts
        sim = validator._calculate_similarity("hola mundo", "hola mundo!")
        assert sim > 0.8

        # Different texts
        sim = validator._calculate_similarity("hola", "adios")
        assert sim < 0.5

        # Empty texts
        sim = validator._calculate_similarity("", "")
        assert sim == 0.0

    def test_extract_key_elements(self):
        """Test key element extraction"""
        from core.reasoning.self_consistency import SelfConsistencyValidator

        mock_llm = MagicMock()
        validator = SelfConsistencyValidator(mock_llm)

        elements = validator._extract_key_elements("El curso de automatización es genial")
        assert "curso" in elements
        assert "automatización" in elements
        # Stopwords should be filtered
        assert "el" not in elements
        assert "de" not in elements
        assert "es" not in elements

    def test_select_best_response(self):
        """Test best response selection from samples"""
        from core.reasoning.self_consistency import SelfConsistencyValidator

        mock_llm = MagicMock()
        validator = SelfConsistencyValidator(mock_llm)

        samples = [
            "El curso cuesta 100 euros",
            "El precio del curso es 100 euros",
            "Cuesta cien euros el curso",
        ]
        best = validator._select_best_response(samples)
        assert best in samples

        # Single sample returns itself
        single = validator._select_best_response(["única respuesta"])
        assert single == "única respuesta"

        # Empty returns empty
        empty = validator._select_best_response([])
        assert empty == ""


class TestChainOfThought:
    """Tests for ChainOfThoughtReasoner"""

    def test_import(self):
        """Test that module can be imported"""
        from core.reasoning import ChainOfThoughtReasoner, get_chain_of_thought_reasoner
        assert ChainOfThoughtReasoner is not None
        assert get_chain_of_thought_reasoner is not None

    def test_is_complex_query_health(self):
        """Test detection of health-related queries"""
        from core.reasoning.chain_of_thought import ChainOfThoughtReasoner

        mock_llm = MagicMock()
        cot = ChainOfThoughtReasoner(mock_llm)

        # Health keywords - use exact keywords from COMPLEX_QUERY_KEYWORDS
        assert cot.is_complex_query("Tengo una lesión en la rodilla")
        assert cot.is_complex_query("Tengo un problema de salud")
        assert cot.is_complex_query("Tengo diabetes, es seguro?")
        assert cot.is_complex_query("I have an injury, can I use this?")

    def test_is_complex_query_length(self):
        """Test detection of long queries"""
        from core.reasoning.chain_of_thought import ChainOfThoughtReasoner

        mock_llm = MagicMock()
        cot = ChainOfThoughtReasoner(mock_llm)

        # Short query - not complex
        assert not cot.is_complex_query("Hola")
        assert not cot.is_complex_query("Cuánto cuesta?")

        # Long query (>50 words) - complex
        long_query = " ".join(["palabra"] * 60)
        assert cot.is_complex_query(long_query)

    def test_is_complex_query_comparison(self):
        """Test detection of comparison queries"""
        from core.reasoning.chain_of_thought import ChainOfThoughtReasoner

        mock_llm = MagicMock()
        cot = ChainOfThoughtReasoner(mock_llm)

        assert cot.is_complex_query("Quiero comparar los productos")
        assert cot.is_complex_query("Cuál es la diferencia entre A y B?")
        assert cot.is_complex_query("What are the requirements?")

    def test_parse_cot_response(self):
        """Test parsing of CoT formatted response"""
        from core.reasoning.chain_of_thought import ChainOfThoughtReasoner

        mock_llm = MagicMock()
        cot = ChainOfThoughtReasoner(mock_llm)

        raw = """
        [RAZONAMIENTO]
        - Paso 1: Analizar la pregunta
        - Paso 2: Evaluar opciones
        - Paso 3: Formular respuesta
        [/RAZONAMIENTO]

        [RESPUESTA]
        Esta es la respuesta final.
        [/RESPUESTA]
        """
        reasoning, answer = cot._parse_cot_response(raw)

        assert len(reasoning) == 3
        assert "Esta es la respuesta final." in answer


class TestReflexion:
    """Tests for ReflexionImprover"""

    def test_import(self):
        """Test that module can be imported"""
        from core.reasoning import ReflexionImprover, get_reflexion_improver
        assert ReflexionImprover is not None
        assert get_reflexion_improver is not None

    def test_parse_critique(self):
        """Test parsing of critique response"""
        from core.reasoning.reflexion import ReflexionImprover

        mock_llm = MagicMock()
        reflexion = ReflexionImprover(mock_llm)

        raw = """
        [CRITICA]
        - El mensaje es muy genérico
        - Falta personalización
        [/CRITICA]

        [PUNTUACION]
        6/10
        [/PUNTUACION]

        [MEJORAS_SUGERIDAS]
        - Usar el nombre del usuario
        - Mencionar sus intereses
        [/MEJORAS_SUGERIDAS]
        """
        critique, score, improvements = reflexion._parse_critique(raw)

        assert "genérico" in critique or len(critique) > 0
        assert score == 0.6  # 6/10
        assert len(improvements) >= 1
