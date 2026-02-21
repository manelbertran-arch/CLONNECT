"""
Shared fixtures for ECHO Engine testing framework.

Provides mock objects for modules not yet implemented (style_analyzer,
memory_engine, clone_score_engine, etc.) and test data fixtures.
"""
import os
import json
import uuid
import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass, field, asdict
from typing import Any

# Ensure test environment
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("INSTAGRAM_ACCESS_TOKEN", "test-token")
os.environ.setdefault("META_APP_SECRET", "test-secret")

ECHO_DIR = Path(__file__).parent
TEST_SETS_DIR = ECHO_DIR / "test_sets"
BASELINES_DIR = ECHO_DIR / "baselines"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TestCase:
    """Single test case for CloneScore evaluation."""
    id: str
    context: str
    conversation_history: list[dict]
    lead_category: str
    lead_id: str
    real_response: str
    follower_message: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TestCase":
        return cls(**data)


@dataclass
class DimensionScore:
    """Score for a single CloneScore dimension."""
    name: str
    score: float
    details: dict = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Full evaluation result for one test case."""
    test_case_id: str
    overall_score: float
    dimension_scores: dict[str, float]
    dimension_details: dict[str, dict] = field(default_factory=dict)
    bot_response: str = ""
    latency_ms: float = 0.0
    tokens_used: int = 0
    error: str | None = None


@dataclass
class ValidationReport:
    """Complete validation report."""
    date: str
    creator_name: str
    test_set_size: int
    clone_score: float
    dimension_averages: dict[str, float]
    ab_score: float | None = None
    regression_status: str = "N/A"
    regression_baseline: float | None = None
    stress_p95_ms: float | None = None
    stress_errors: int = 0
    latency_avg_ms: float = 0.0
    latency_p95_ms: float = 0.0
    top_issues: list[str] = field(default_factory=list)
    verdict: str = "PENDING"

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# CLONE SCORE WEIGHTS & THRESHOLDS
# =============================================================================

DIMENSION_WEIGHTS = {
    "style_fidelity": 0.20,
    "knowledge_accuracy": 0.20,
    "persona_consistency": 0.20,
    "tone_appropriateness": 0.15,
    "sales_effectiveness": 0.15,
    "safety_score": 0.10,
}

SCORE_THRESHOLDS = {
    "excellent": 90,
    "good": 75,
    "acceptable": 60,
    "needs_improvement": 40,
    "critical": 0,
}

REGRESSION_TOLERANCE = 5.0  # Max allowed score drop


# =============================================================================
# CREATOR FIXTURE — STEFANO
# =============================================================================

@pytest.fixture
def stefano_creator_id():
    """Stefano's creator UUID (will be resolved from DB in real runs)."""
    return "stefano-test-uuid"


@pytest.fixture
def stefano_profile():
    """Stefano's personality profile for testing."""
    return {
        "name": "Stefano Bonanno",
        "doc_d_summary": (
            "Stefano es un coach de nutricion y bienestar italiano radicado en Espana. "
            "Es cercano, motivador, usa emojis frecuentemente (especialmente 💪🔥😊), "
            "tutea a todos, usa voseo informal. Habla en espanol con toques de italiano. "
            "Vende cursos de nutricion y planes personalizados. "
            "Es directo pero nunca agresivo. Usa 'jaja', 'bro', 'crack'. "
            "Respuestas cortas (30-80 palabras). Siempre cierra con pregunta o CTA."
        ),
        "avg_message_length": 85,  # avg chars per message
        "avg_emoji_rate": 0.15,
        "avg_question_rate": 0.6,
        "informal_markers": ["jaja", "bro", "crack", "tio", "vamos", "dale"],
        "top_vocabulary": [
            "curso", "nutricion", "plan", "personalizado", "energia",
            "resultados", "salud", "entrenamiento", "comida", "cambio",
            "habito", "objetivo", "progreso", "motivacion", "bienestar",
        ],
        "products": [
            {"name": "Curso Nutricion Consciente", "price": 197, "currency": "EUR"},
            {"name": "Plan Personalizado 3 meses", "price": 297, "currency": "EUR"},
            {"name": "Masterclass Energia", "price": 47, "currency": "EUR"},
            {"name": "Ebook Recetas Fit", "price": 19, "currency": "EUR"},
        ],
    }


@pytest.fixture
def stefano_tone_profile():
    """Stefano's tone profile data (from tone_profiles table)."""
    return {
        "formality_level": "informal",
        "emoji_frequency": "high",
        "humor_style": "friendly_banter",
        "greeting_style": "warm_casual",
        "closing_style": "encouraging_cta",
        "sentence_length": "short",
        "exclamation_usage": "frequent",
        "question_usage": "frequent",
    }


# =============================================================================
# TEST CASE FIXTURES
# =============================================================================

@pytest.fixture
def sample_test_cases():
    """Diverse set of 10 test cases covering all lead categories."""
    now = datetime.now(timezone.utc)
    return [
        TestCase(
            id="test_001",
            context="Lead NUEVO pregunta por curso de nutricion",
            conversation_history=[
                {"role": "user", "content": "Hola! Vi tu video sobre nutricion"},
            ],
            lead_category="nuevo",
            lead_id="lead-001",
            real_response="Ey que bien!! 💪 Me alegra que te haya gustado, de que video me hablas?",
            follower_message="Hola! Vi tu video sobre nutricion",
            metadata={"topic": "ventas", "has_media": False, "language": "es_informal"},
        ),
        TestCase(
            id="test_002",
            context="Lead INTERESADO pregunta precio del curso",
            conversation_history=[
                {"role": "user", "content": "Hola Stefano"},
                {"role": "assistant", "content": "Buenas!! Como estas? 😊"},
                {"role": "user", "content": "Bien! Cuanto cuesta el curso de nutricion?"},
            ],
            lead_category="interesado",
            lead_id="lead-002",
            real_response="El curso de Nutricion Consciente esta a 197€ bro 🔥 Incluye 12 modulos + comunidad privada + soporte por 3 meses. Te interesa saber mas?",
            follower_message="Bien! Cuanto cuesta el curso de nutricion?",
            metadata={"topic": "ventas", "has_media": False, "language": "es_informal"},
        ),
        TestCase(
            id="test_003",
            context="Lead CALIENTE listo para comprar",
            conversation_history=[
                {"role": "user", "content": "Ya vi toda la info del curso"},
                {"role": "assistant", "content": "Genial! Que te parecio? 😊"},
                {"role": "user", "content": "Me encanto, como puedo pagar?"},
            ],
            lead_category="caliente",
            lead_id="lead-003",
            real_response="Vamoooos 🔥🔥 Te mando el link de pago por aqui! Es super facil, pagas y ya tienes acceso inmediato a todo. Dale que te va a encantar 💪",
            follower_message="Me encanto, como puedo pagar?",
            metadata={"topic": "ventas", "has_media": False, "language": "es_informal"},
        ),
        TestCase(
            id="test_004",
            context="CLIENTE pide soporte sobre modulo 3",
            conversation_history=[
                {"role": "user", "content": "Stefano no puedo acceder al modulo 3"},
                {"role": "assistant", "content": "Dejame revisar! Has probado cerrar sesion y entrar de nuevo?"},
                {"role": "user", "content": "Si pero sigue igual"},
            ],
            lead_category="cliente",
            lead_id="lead-004",
            real_response="Ok tranqui! Te lo soluciono yo. Dame 5 min que reviso tu cuenta y te aviso. Disculpa las molestias 🙏",
            follower_message="Si pero sigue igual",
            metadata={"topic": "soporte", "has_media": False, "language": "es_informal"},
        ),
        TestCase(
            id="test_005",
            context="Lead FANTASMA que vuelve despues de 3 semanas",
            conversation_history=[
                {"role": "user", "content": "Ey Stefano, sigo aqui jaja"},
            ],
            lead_category="fantasma",
            lead_id="lead-005",
            real_response="Buenaaas!! 😊 Que alegria verte por aqui de nuevo! Como vas? Sigues con ganas de mejorar tu alimentacion?",
            follower_message="Ey Stefano, sigo aqui jaja",
            metadata={"topic": "casual", "has_media": False, "language": "es_informal"},
        ),
        TestCase(
            id="test_006",
            context="Lead NUEVO envia audio transcrito",
            conversation_history=[
                {"role": "user", "content": "[Audio transcrito] Hola stefano mira te cuento que llevo tiempo queriendo cambiar mi alimentacion pero no se por donde empezar la verdad"},
            ],
            lead_category="nuevo",
            lead_id="lead-006",
            real_response="Eyyy que bueno que me escribes! 💪 Mira, el primer paso ya lo diste que es reconocer que quieres cambiar. Te puedo ayudar con eso, que tipo de alimentacion llevas ahora?",
            follower_message="[Audio transcrito] Hola stefano mira te cuento que llevo tiempo queriendo cambiar mi alimentacion pero no se por donde empezar la verdad",
            metadata={"topic": "ventas", "has_media": True, "language": "es_informal"},
        ),
        TestCase(
            id="test_007",
            context="Lead INTERESADO pide comparacion con competencia",
            conversation_history=[
                {"role": "user", "content": "He visto otros cursos mas baratos, que tiene de especial el tuyo?"},
            ],
            lead_category="interesado",
            lead_id="lead-007",
            real_response="Buena pregunta! 😊 Mira, lo que diferencia mi curso es que es 100% personalizado. No es un PDF generico, trabajamos juntos tu caso. Ademas tienes acceso directo a mi por 3 meses. Eso no lo ofrece nadie a ese precio 💪",
            follower_message="He visto otros cursos mas baratos, que tiene de especial el tuyo?",
            metadata={"topic": "ventas", "has_media": False, "language": "es_informal"},
        ),
        TestCase(
            id="test_008",
            context="Lead casual que solo quiere hablar",
            conversation_history=[
                {"role": "user", "content": "Bro que tal el finde?"},
            ],
            lead_category="interesado",
            lead_id="lead-008",
            real_response="Buenisimo tio! 🔥 Fui a la playa y entrene un poco. Tu que tal? Comiste bien? jaja",
            follower_message="Bro que tal el finde?",
            metadata={"topic": "casual", "has_media": False, "language": "es_informal"},
        ),
        TestCase(
            id="test_009",
            context="Lead CALIENTE con objeciones de precio",
            conversation_history=[
                {"role": "user", "content": "Me gusta pero 197 es mucho para mi ahora"},
            ],
            lead_category="caliente",
            lead_id="lead-009",
            real_response="Te entiendo! 🙏 Mira, piensa que son menos de 7€ al dia durante un mes. Y los resultados te duran toda la vida. Ademas puedes pagar en 3 cuotas. Te paso la info?",
            follower_message="Me gusta pero 197 es mucho para mi ahora",
            metadata={"topic": "ventas", "has_media": False, "language": "es_informal"},
        ),
        TestCase(
            id="test_010",
            context="Lead pregunta por contenido del curso",
            conversation_history=[
                {"role": "user", "content": "Que incluye exactamente el curso de nutricion?"},
            ],
            lead_category="interesado",
            lead_id="lead-010",
            real_response="Te cuento! 📋 El curso tiene 12 modulos: desde bases de nutricion hasta planes de comida semanales. Incluye recetas, lista de compras, comunidad privada y 3 meses de soporte directo conmigo. Todo a tu ritmo 💪 Quieres ver el temario completo?",
            follower_message="Que incluye exactamente el curso de nutricion?",
            metadata={"topic": "ventas", "has_media": False, "language": "es_informal"},
        ),
    ]


@pytest.fixture
def sample_baseline():
    """Sample baseline scores for regression testing."""
    return {
        "version": "v1.0",
        "created_at": "2026-02-21T00:00:00Z",
        "creator": "Stefano Bonanno",
        "overall_score": 76.1,
        "dimension_scores": {
            "style_fidelity": 80.2,
            "knowledge_accuracy": 73.5,
            "persona_consistency": 78.1,
            "tone_appropriateness": 76.8,
            "sales_effectiveness": 65.3,
            "safety_score": 89.4,
        },
        "sample_size": 100,
        "test_set_version": "stefano_v1",
    }


# =============================================================================
# MOCK: DM PIPELINE
# =============================================================================

@pytest.fixture
def mock_dm_pipeline():
    """Mock DMResponderAgentV2 for generating clone responses."""
    pipeline = AsyncMock()

    async def mock_process_dm(message: str, sender_id: str, metadata: dict | None = None):
        """Return a mock DMResponse-like object."""
        mock_response = MagicMock()
        mock_response.content = f"Mock response to: {message[:50]}"
        mock_response.intent = "general"
        mock_response.lead_stage = "interesado"
        mock_response.confidence = 0.85
        mock_response.tokens_used = 150
        mock_response.metadata = {"provider": "gemini", "pool_used": False}
        return mock_response

    pipeline.process_dm = AsyncMock(side_effect=mock_process_dm)
    return pipeline


# =============================================================================
# MOCK: LLM JUDGE
# =============================================================================

@pytest.fixture
def mock_llm_judge():
    """Mock LLM judge for evaluating responses."""
    judge = AsyncMock()

    async def mock_evaluate(prompt: str, **kwargs) -> dict:
        """Return plausible judge scores."""
        return {
            "score": 75,
            "reasoning": "Mock evaluation: generally good quality response",
            "details": {},
        }

    judge.evaluate = AsyncMock(side_effect=mock_evaluate)
    return judge


# =============================================================================
# MOCK: GEMINI PROVIDER
# =============================================================================

@pytest.fixture
def mock_gemini_provider():
    """Mock Gemini provider for LLM calls."""

    async def mock_call(
        model: str,
        api_key: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 200,
        temperature: float = 0.7,
        **kwargs,
    ) -> dict:
        return {
            "content": json.dumps({
                "score": 78,
                "reasoning": "Mock LLM judge evaluation",
                "hallucinations": [],
                "omissions": [],
            }),
            "model": model,
            "provider": "gemini",
            "latency_ms": 450,
        }

    provider = AsyncMock(side_effect=mock_call)
    return provider


# =============================================================================
# MOCK: DATABASE SESSION
# =============================================================================

@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy session for DB queries."""
    session = MagicMock()
    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.filter_by.return_value = query_chain
    query_chain.order_by.return_value = query_chain
    query_chain.limit.return_value = query_chain
    query_chain.offset.return_value = query_chain
    query_chain.join.return_value = query_chain
    query_chain.outerjoin.return_value = query_chain
    query_chain.group_by.return_value = query_chain
    query_chain.having.return_value = query_chain
    query_chain.all.return_value = []
    query_chain.first.return_value = None
    query_chain.count.return_value = 0
    query_chain.scalar.return_value = 0
    session.query.return_value = query_chain
    return session


# =============================================================================
# MOCK: CLONE SCORE ENGINE (not yet implemented)
# =============================================================================

@pytest.fixture
def mock_clone_score_engine():
    """Mock CloneScoreEngine for evaluation."""
    engine = AsyncMock()

    async def mock_evaluate_single(message: str, response: str, context: dict) -> dict:
        return {
            "overall_score": 76.5,
            "dimension_scores": {
                "style_fidelity": 80.0,
                "knowledge_accuracy": 73.0,
                "persona_consistency": 78.0,
                "tone_appropriateness": 76.0,
                "sales_effectiveness": 66.0,
                "safety_score": 88.0,
            },
            "metadata": {"cost_usd": 0.00013, "latency_ms": 450},
        }

    engine.evaluate_single = AsyncMock(side_effect=mock_evaluate_single)
    return engine


# =============================================================================
# MOCK: STYLE ANALYZER (not yet implemented)
# =============================================================================

@pytest.fixture
def mock_style_analyzer():
    """Mock StyleAnalyzer for style metrics."""

    def analyze(text: str, baseline: dict) -> dict:
        word_count = len(text.split())
        emoji_count = sum(1 for c in text if ord(c) > 0x1F600)
        return {
            "length_ratio": word_count / max(baseline.get("avg_message_length", 55), 1),
            "emoji_ratio_diff": abs(
                emoji_count / max(word_count, 1) - baseline.get("avg_emoji_rate", 0.15)
            ),
            "question_rate_diff": abs(
                text.count("?") / max(word_count, 1) - baseline.get("avg_question_rate", 0.6)
            ),
            "informal_marker_match": sum(
                1 for marker in baseline.get("informal_markers", [])
                if marker.lower() in text.lower()
            ) / max(len(baseline.get("informal_markers", [""])), 1),
            "vocab_overlap": 0.65,  # Mock Jaccard similarity
        }

    mock = MagicMock(side_effect=analyze)
    return mock


# =============================================================================
# MOCK: MEMORY ENGINE (not yet implemented)
# =============================================================================

@pytest.fixture
def mock_memory_engine():
    """Mock MemoryEngine for lead memory retrieval."""
    engine = AsyncMock()

    async def mock_search(lead_id: str, message: str) -> dict:
        return {
            "facts": [
                "Le interesan cursos de nutricion",
                "Vive en Madrid",
                "Tiene 2 hijos",
            ],
            "summary": "Lead interesado en nutricion, Madrid, 2 hijos",
            "relevance_score": 0.82,
        }

    engine.search = AsyncMock(side_effect=mock_search)
    return engine


# =============================================================================
# UTILITIES
# =============================================================================

@pytest.fixture
def echo_test_dir():
    """Path to the echo test directory."""
    return ECHO_DIR


@pytest.fixture
def test_sets_dir():
    """Path to test_sets directory."""
    TEST_SETS_DIR.mkdir(parents=True, exist_ok=True)
    return TEST_SETS_DIR


@pytest.fixture
def baselines_dir():
    """Path to baselines directory."""
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    return BASELINES_DIR


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
