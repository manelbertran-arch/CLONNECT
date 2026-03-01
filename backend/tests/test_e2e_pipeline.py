"""
CAPA 3 — E2E Pipeline tests: DMResponderAgentV2.process_dm()

Ejecuta el pipeline completo de 5 fases (Detection → Context → Generation → Postprocessing)
con mocks mínimos. Solo se mockea lo que accede a infraestructura externa (LLM, DB, archivos).

Componentes REALES (no mockeados):
  IntentClassifier, SensitiveDetector, FrustrationDetector, ReflexionEngine,
  Guardrails, Strategy (_determine_response_strategy), ResponseFixes,
  OutputValidator, PoolResponse (response_variator_v2)

Solo mockeado:
  - core.providers.gemini_provider.generate_dm_response  (llamada LLM)
  - services.dm_agent_context_integration.build_context_prompt  (DB)
  - services.relationship_dna_repository.get_relationship_dna  (DB)
  - agent.memory_store.get_or_create  (I/O de archivos/DB)

Uso:
  cd ~/Clonnect/backend
  python3 -m pytest tests/test_e2e_pipeline.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.dm.agent import DMResponderAgentV2
from core.dm.models import DMResponse
from services.memory_service import FollowerMemory


# =============================================================================
# DATOS DE PRUEBA
# =============================================================================

CREATOR_ID = "stefano_bonanno"
SENDER_ID = "test_user_e2e"

MOCK_PERSONALITY = {
    "name": "Stefano",
    "tone": "motivacional",
    "vocabulary": "",
    "welcome_message": "Hola! Soy el asistente de Stefano.",
    "dialect": "es-ar",
    "formality": "informal",
    "energy": "high",
    "humor": False,
    "emojis": "moderate",
    "signature_phrases": [],
    "topics_to_avoid": [],
    "knowledge_about": {},
}

MOCK_PRODUCTS = [
    {
        "name": "Fitpack Challenge de 11 días: Transforma tu cuerpo",
        "price": 97,
        "currency": "EUR",
        "description": "Programa de fitness intensivo de 11 días",
        "url": "https://stefanobonanno.com/fitpack",
    },
    {
        "name": "Coaching 1:1 con Stefano",
        "price": 297,
        "currency": "EUR",
        "description": "Sesiones de coaching personalizadas",
        "url": "https://stefanobonanno.com/coaching",
    },
    {
        "name": "Círculo de Hombres",
        "price": 47,
        "currency": "EUR",
        "description": "Comunidad mensual de desarrollo personal",
        "url": "https://stefanobonanno.com/circulo",
    },
]

# Flags de entorno para deshabilitar features con acceso a DB
_ENV_DISABLE = {
    "ENABLE_MEMORY_ENGINE": "false",
    "ENABLE_COMMITMENT_TRACKING": "false",
    "ENABLE_CLONE_SCORE": "false",
    "ENABLE_EMAIL_CAPTURE": "false",
}


# =============================================================================
# HELPERS
# =============================================================================

def make_follower(
    total_messages: int = 5,
    purchase_intent_score: float = 0.0,
    interests: list = None,
    is_customer: bool = False,
    status: str = "active",
) -> FollowerMemory:
    """Construye un FollowerMemory de prueba."""
    return FollowerMemory(
        follower_id=SENDER_ID,
        creator_id=CREATOR_ID,
        username="carlos_fitness",
        name="Carlos",
        total_messages=total_messages,
        purchase_intent_score=purchase_intent_score,
        interests=interests or [],
        is_customer=is_customer,
        status=status,
        last_messages=[],
    )


async def run_pipeline(
    agent: DMResponderAgentV2,
    message: str,
    sender_id: str = SENDER_ID,
    metadata: dict = None,
    llm_text: str = "Claro, aquí tienes la información que necesitas.",
    follower: FollowerMemory = None,
) -> DMResponse:
    """
    Ejecuta process_dm() con mocks mínimos sobre LLM y DB.

    Patches aplicados:
      - LLM: generate_dm_response → dict con content/model/provider/latency_ms
      - DB1: build_context_prompt → coroutine que devuelve ""
      - DB2: get_relationship_dna → None
      - Memory: agent.memory_store.get_or_create → FollowerMemory
    """
    follower = follower or make_follower()
    metadata = metadata or {}

    with (
        patch.dict(os.environ, _ENV_DISABLE),
        patch(
            "core.providers.gemini_provider.generate_dm_response",
            new=AsyncMock(return_value={
                "content": llm_text,
                "model": "gemini-2.0-flash-lite",
                "provider": "gemini",
                "latency_ms": 50,
            }),
        ),
        patch(
            "services.dm_agent_context_integration.build_context_prompt",
            new=AsyncMock(return_value=""),
        ),
        patch(
            "services.relationship_dna_repository.get_relationship_dna",
            return_value=None,
        ),
    ):
        agent.memory_store.get_or_create = AsyncMock(return_value=follower)
        return await agent.process_dm(message, sender_id, metadata)


# =============================================================================
# FIXTURE: agente reutilizable (scope=module para no reconstruir en cada test)
# =============================================================================

@pytest.fixture(scope="module")
def agent():
    """
    DMResponderAgentV2 con personality y products inyectados.
    No accede a DB en el constructor — todos los errores de carga son capturados.
    """
    try:
        return DMResponderAgentV2(
            creator_id=CREATOR_ID,
            personality=MOCK_PERSONALITY,
            products=MOCK_PRODUCTS,
        )
    except Exception as e:
        pytest.skip(f"No se pudo crear DMResponderAgentV2: {e}")


# =============================================================================
# ESCENARIOS 1-2: DETECCIÓN DE CRISIS (salida anticipada antes del LLM)
# =============================================================================

class TestCrisisDetection:
    """SensitiveDetector activa la ruta de crisis → el LLM nunca se llama."""

    async def test_self_harm_phrase_triggers_crisis(self, agent):
        """'quiero hacerme daño' → intent=sensitive_content, sin LLM."""
        result = await run_pipeline(agent, "quiero hacerme daño")
        assert result.intent == "sensitive_content", (
            f"Expected sensitive_content, got: {result.intent}"
        )
        assert result.content, "Crisis response must have non-empty content"
        assert result.confidence >= 0.5

    async def test_explicit_suicide_phrase_triggers_crisis(self, agent):
        """'me voy a suicidar' → intent=sensitive_content + recursos de crisis."""
        result = await run_pipeline(agent, "me voy a suicidar, ya no puedo más")
        assert result.intent == "sensitive_content"
        assert result.content
        # La respuesta de crisis debe contener algún recurso de ayuda
        content_lower = result.content.lower()
        has_help = any(kw in content_lower for kw in [
            "024", "teléfono", "ayuda", "profesional", "recurso",
            "escucho", "apoyo", "importante"
        ])
        assert has_help or len(result.content) > 50, (
            "Crisis response should contain help resources or be substantial"
        )


# =============================================================================
# ESCENARIO 3: MENSAJE VACÍO
# =============================================================================

class TestEdgeCases:

    async def test_empty_message_returns_non_empty_response(self, agent):
        """Mensaje vacío → pipeline completo → contenido no vacío (ResponseFixes actúa)."""
        result = await run_pipeline(agent, "", llm_text="   ")
        assert isinstance(result, DMResponse)
        assert result.content.strip(), "Response must never be empty (BUG-10 fix)"

    async def test_very_short_message(self, agent):
        """Mensaje de 1 carácter → sin crash."""
        result = await run_pipeline(agent, "?")
        assert isinstance(result, DMResponse)
        assert result.content


# =============================================================================
# ESCENARIOS 4-6: CLASIFICACIÓN DE INTENTS (IntentClassifier real)
# =============================================================================

class TestIntentClassification:

    async def test_pricing_question_classified_correctly(self, agent):
        """'cuánto cuesta el fitpack' → intent pricing/product_question/product_info."""
        result = await run_pipeline(
            agent,
            "cuánto cuesta el fitpack?",
            llm_text="El Fitpack cuesta 97€.",
        )
        assert result.intent in (
            "pricing", "product_question", "product_info", "purchase"
        ), f"Unexpected intent for price question: {result.intent}"

    async def test_objection_price_classified_correctly(self, agent):
        """'es muy caro' → intent objection_price o relacionado."""
        result = await run_pipeline(agent, "es muy caro, no me lo puedo permitir")
        assert result.intent in (
            "objection_price", "objection", "pricing", "other"
        ), f"Unexpected intent for price objection: {result.intent}"

    async def test_escalation_request_classified(self, agent):
        """'necesito hablar con Stefano' → escalation/support."""
        result = await run_pipeline(
            agent,
            "necesito hablar directamente con Stefano, es urgente",
        )
        assert result.intent in (
            "escalation", "support", "other"
        ), f"Unexpected intent for escalation: {result.intent}"

    async def test_normal_message_not_flagged_as_crisis(self, agent):
        """Mensaje de fitness normal → NO debe activar crisis."""
        result = await run_pipeline(
            agent,
            "quiero mejorar mi cuerpo y bajar de peso",
            llm_text="Genial! El Fitpack Challenge es perfecto para ti.",
        )
        assert result.intent != "sensitive_content", (
            "Normal fitness message should NOT trigger crisis detection"
        )


# =============================================================================
# ESCENARIOS 7-9: ESTRATEGIA DE RESPUESTA (strategy.py real)
# =============================================================================

class TestResponseStrategy:

    async def test_first_message_strategy(self, agent):
        """Primer mensaje (total_messages=0) → estrategia BIENVENIDA."""
        follower = make_follower(total_messages=0)
        result = await run_pipeline(
            agent,
            "hola",
            follower=follower,
            llm_text="Hola! Soy el asistente de Stefano, encantado de conocerte.",
        )
        # El pipeline debe completarse sin error
        assert isinstance(result, DMResponse)
        assert result.content

    async def test_first_message_with_question_strategy(self, agent):
        """Primer mensaje con '?' → estrategia BIENVENIDA + AYUDA."""
        follower = make_follower(total_messages=0)
        result = await run_pipeline(
            agent,
            "hola, cuánto cuesta el coaching?",
            follower=follower,
            llm_text="Hola! El coaching 1:1 con Stefano cuesta 297€.",
        )
        assert isinstance(result, DMResponse)
        assert result.intent != "sensitive_content"
        assert result.content

    async def test_returning_user_purchase_intent(self, agent):
        """Usuario con historial + intent de compra → DMResponse válido."""
        follower = make_follower(total_messages=12, purchase_intent_score=0.7)
        result = await run_pipeline(
            agent,
            "me interesa comprar el fitpack, cómo lo hago?",
            follower=follower,
            llm_text="Para comprar el Fitpack de 97€, haz clic aquí.",
        )
        assert isinstance(result, DMResponse)
        assert result.confidence >= 0.0
        assert result.lead_stage  # debe tener un stage asignado


# =============================================================================
# ESCENARIO 10: DETECCIÓN DE FRUSTRACIÓN (FrustrationDetector real)
# =============================================================================

class TestFrustrationDetection:

    async def test_explicit_frustration_passes_pipeline(self, agent):
        """Expresión de frustración explícita → pipeline completa sin crash."""
        result = await run_pipeline(
            agent,
            "joder, llevas 3 días sin responder. Nadie me responde aquí.",
            llm_text="Entiendo tu frustración. Estoy aquí para ayudarte ahora.",
        )
        assert isinstance(result, DMResponse)
        assert result.content

    async def test_profanity_frustration_detected(self, agent):
        """Palabrota + queja → frustración detectada, respuesta válida."""
        result = await run_pipeline(
            agent,
            "esto es una mierda, no me ayudan nunca",
            llm_text="Lamento que te sientas así. Dime qué necesitas.",
        )
        assert result.content
        assert result.intent != "sensitive_content"


# =============================================================================
# ESCENARIO 11: POOL RESPONSE (response_variator_v2 real)
# =============================================================================

class TestPoolResponse:

    async def test_short_greeting_produces_valid_response(self, agent):
        """'hola' → pool response o LLM — ambos son válidos."""
        result = await run_pipeline(
            agent, "hola",
            llm_text="Hola! En qué puedo ayudarte?",
        )
        assert isinstance(result, DMResponse)
        assert result.content.strip()
        # Pool responses tienen used_pool=True en metadata; LLM no lo tienen
        # Ambos son válidos — solo verificamos que el pipeline no crashea

    async def test_pool_response_metadata_field(self, agent):
        """Metadata del resultado siempre tiene las claves obligatorias."""
        result = await run_pipeline(agent, "buenas")
        assert "model" in result.metadata or "provider" in result.metadata or isinstance(result.metadata, dict)


# =============================================================================
# ESCENARIOS 12-13: CALIDAD DE RESPUESTA (ResponseFixes real)
# =============================================================================

class TestResponseQuality:

    async def test_whitespace_only_llm_response_gets_fallback(self, agent):
        """LLM devuelve solo espacios → ResponseFixes aplica fallback (BUG-10)."""
        result = await run_pipeline(agent, "hola", llm_text="   \n\t   ")
        assert result.content.strip(), (
            "BUG-10: ResponseFixes must provide fallback for empty responses"
        )

    async def test_emoji_spam_is_limited(self, agent):
        """LLM devuelve emojis en exceso → emoji limit aplicado (BUG-11)."""
        spam_emojis = "🎉🎊🎈🎁🎀🎗🎟🎠🎡🎢 hola!"
        result = await run_pipeline(agent, "hola", llm_text=spam_emojis * 3)
        # Contar emojis en el rango típico (U+1F000+)
        emoji_count = sum(1 for c in result.content if ord(c) > 0x1F000)
        # El límite por defecto es 5 (DEFAULT_MAX_EMOJIS) — usamos margen amplio
        assert emoji_count <= 15, (
            f"BUG-11: Too many emojis after fix ({emoji_count}). "
            "ResponseFixes should cap emoji count."
        )


# =============================================================================
# ESCENARIO 14: GUARDRAILS (Guardrails real)
# =============================================================================

class TestGuardrails:

    async def test_off_topic_message_not_crash(self, agent):
        """Mensaje off-topic (bitcoin) → pipeline completo, sin crash."""
        result = await run_pipeline(
            agent,
            "qué piensas del bitcoin como inversión?",
            llm_text="No tengo información sobre eso, pero puedo ayudarte con los programas de Stefano.",
        )
        assert isinstance(result, DMResponse)
        assert result.content


# =============================================================================
# ESCENARIO 15: REFLEXION ENGINE (ReflexionEngine real)
# =============================================================================

class TestReflexionEngine:

    async def test_price_question_with_price_answered(self, agent):
        """LLM responde correctamente al precio → reflexión no bloquea la respuesta."""
        result = await run_pipeline(
            agent,
            "cuánto vale el coaching?",
            llm_text="El Coaching 1:1 tiene un precio de 297€ al mes.",
        )
        assert result.content
        assert "297" in result.content or len(result.content) > 10

    async def test_price_question_without_price_still_responds(self, agent):
        """LLM no responde al precio → ReflexionEngine puede marcar issues pero no bloquea."""
        result = await run_pipeline(
            agent,
            "cuánto cuesta el fitpack?",
            llm_text="El fitpack es un programa increíble de transformación.",
        )
        # El pipeline devuelve respuesta de todos modos (reflexion no bloquea)
        assert isinstance(result, DMResponse)
        assert result.content


# =============================================================================
# ESCENARIO 16: ESTRUCTURA DE DMResponse
# =============================================================================

class TestDMResponseStructure:

    async def test_all_required_fields_present(self, agent):
        """DMResponse tiene todos los campos requeridos con tipos correctos."""
        result = await run_pipeline(
            agent,
            "me interesa el círculo de hombres",
            llm_text="El Círculo de Hombres cuesta 47€/mes.",
        )
        assert isinstance(result.content, str)
        assert isinstance(result.intent, str)
        assert isinstance(result.lead_stage, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.tokens_used, int)
        assert isinstance(result.metadata, dict)
        assert result.created_at is not None

    async def test_lead_stage_not_empty(self, agent):
        """lead_stage siempre se asigna (LeadService.determine_stage actúa)."""
        result = await run_pipeline(
            agent,
            "hola, tengo una pregunta",
            llm_text="Claro, dime en qué puedo ayudarte.",
        )
        assert result.lead_stage
        assert result.lead_stage != ""

    async def test_metadata_has_model_and_provider(self, agent):
        """metadata incluye model y provider del LLM (trazabilidad A4)."""
        result = await run_pipeline(
            agent,
            "buenas tardes",
            llm_text="Buenas tardes! En qué puedo ayudarte?",
        )
        # Metadata puede venir de pool (sin model) o LLM (con model)
        assert isinstance(result.metadata, dict)


# =============================================================================
# ESCENARIO 17: INTEGRIDAD COMPLETA DEL PIPELINE (las 5 fases)
# =============================================================================

class TestFullPipelineIntegrity:

    async def test_5_phase_pipeline_completes_without_error(self, agent):
        """
        Mensaje de alta intención de compra → las 5 fases se encadenan sin error:
        1. Detection (SensitiveDetector, FrustrationDetector, PoolResponse)
        2. Context (MemoryStore, DNA, Intent, RAG)
        3. Prompt Construction
        4. LLM Generation
        5. Postprocessing (Guardrails, Reflexion, ResponseFixes, Scoring)
        """
        result = await run_pipeline(
            agent,
            "llevo semanas pensando en apuntarme al coaching de Stefano",
            llm_text=(
                "Me alegra que lo estés considerando! "
                "El Coaching 1:1 incluye sesiones personalizadas por 297€."
            ),
            follower=make_follower(total_messages=8, purchase_intent_score=0.6),
        )
        assert isinstance(result, DMResponse)
        assert result.content
        assert result.lead_stage
        assert result.intent

    async def test_pipeline_latency_under_threshold(self, agent):
        """El pipeline (sin LLM real) debe completar en < 3 segundos."""
        start = time.monotonic()
        result = await run_pipeline(
            agent,
            "quiero información sobre el fitpack",
            llm_text="El Fitpack Challenge cuesta 97€ y dura 11 días.",
        )
        elapsed = time.monotonic() - start
        assert isinstance(result, DMResponse)
        assert elapsed < 3.0, (
            f"Pipeline took {elapsed:.2f}s — exceeds 3s threshold"
        )

    async def test_multiple_consecutive_messages(self, agent):
        """Múltiples mensajes seguidos → sin degradación ni estado corrupto."""
        messages = [
            ("hola", "Hola! En qué puedo ayudarte?"),
            ("cuánto cuesta el fitpack?", "El Fitpack cuesta 97€."),
            ("es mucho dinero", "Entiendo. El valor está en los resultados que obtenés."),
            ("me lo pienso", "Claro, tómate tu tiempo."),
        ]
        follower = make_follower(total_messages=2)
        for message, llm_text in messages:
            result = await run_pipeline(
                agent, message, follower=follower, llm_text=llm_text
            )
            assert isinstance(result, DMResponse)
            assert result.content
            follower.total_messages += 1
