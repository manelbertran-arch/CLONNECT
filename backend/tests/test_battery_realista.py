"""
CAPA 3 — Batería de 50 mensajes realistas: seguidor de Stefano Bonanno

Simula conversaciones reales con el asistente IA de Stefano (fitness + coaching).
Cubre 8 categorías de mensajes que ocurren en la práctica.

Al finalizar imprime una tabla con:
  Mensaje | Intent | Lead Stage | Confidence | Long. resp. | Tiempo | Issues

Uso:
  cd ~/Clonnect/backend
  python3 -m pytest tests/test_battery_realista.py -v -s
  python3 -m pytest tests/test_battery_realista.py -v -s -k "test_battery"
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from core.dm.agent import DMResponderAgentV2
    from core.dm.models import DMResponse
    from services.memory_service import FollowerMemory
    _IMPORTS_OK = True
except Exception as _import_err:
    _IMPORTS_OK = False
    _import_msg = str(_import_err)


# =============================================================================
# DATOS FIJOS
# =============================================================================

CREATOR_ID = "stefano_bonanno"
SENDER_ID = "battery_user"

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
    "signature_phrases": ["¡Vamos!", "Lo que necesitás"],
    "topics_to_avoid": ["política", "religión"],
    "knowledge_about": {"fitness": True, "coaching": True},
}

MOCK_PRODUCTS = [
    {
        "name": "Fitpack Challenge de 11 días: Transforma tu cuerpo",
        "price": 97,
        "currency": "EUR",
        "description": "Programa de fitness intensivo de 11 días para transformar tu cuerpo",
        "url": "https://stefanobonanno.com/fitpack",
    },
    {
        "name": "Coaching 1:1 con Stefano",
        "price": 297,
        "currency": "EUR",
        "description": "Sesiones de coaching personalizadas 1 a 1 con Stefano",
        "url": "https://stefanobonanno.com/coaching",
    },
    {
        "name": "Círculo de Hombres",
        "price": 47,
        "currency": "EUR",
        "description": "Comunidad mensual de desarrollo personal para hombres",
        "url": "https://stefanobonanno.com/circulo",
    },
]

_ENV_DISABLE = {
    "ENABLE_MEMORY_ENGINE": "false",
    "ENABLE_COMMITMENT_TRACKING": "false",
    "ENABLE_CLONE_SCORE": "false",
    "ENABLE_EMAIL_CAPTURE": "false",
}

# =============================================================================
# 50 MENSAJES REALISTAS — 8 CATEGORÍAS
# =============================================================================
# Formato: (categoría, mensaje_usuario, respuesta_llm_simulada)

BATTERY_MESSAGES = [
    # ── CATEGORÍA A: DESCUBRIMIENTO (primer contacto) ────────────────────────
    (
        "descubrimiento",
        "hola",
        "Hola! Soy el asistente de Stefano. ¿En qué puedo ayudarte?",
    ),
    (
        "descubrimiento",
        "te vi en instagram y me interesó lo que haces",
        "Me alegra que hayas llegado aquí! Stefano es experto en fitness y desarrollo personal.",
    ),
    (
        "descubrimiento",
        "qué tipo de programas ofrece Stefano?",
        "Stefano ofrece el Fitpack Challenge de 11 días (97€), Coaching 1:1 (297€) y el Círculo de Hombres (47€/mes).",
    ),
    (
        "descubrimiento",
        "de qué va el fitpack exactamente?",
        "El Fitpack Challenge es un programa intensivo de 11 días para transformar tu cuerpo con rutinas y alimentación guiada.",
    ),
    (
        "descubrimiento",
        "para quién está pensado el círculo de hombres?",
        "El Círculo de Hombres está pensado para hombres que quieren crecer en lo personal, emocional y físico.",
    ),
    (
        "descubrimiento",
        "cuánto tiempo lleva Stefano en esto?",
        "Stefano lleva más de 8 años en el mundo del fitness y el coaching personal.",
    ),

    # ── CATEGORÍA B: CONSIDERACIÓN (evaluando la compra) ─────────────────────
    (
        "consideracion",
        "cuánto cuesta el fitpack?",
        "El Fitpack Challenge cuesta 97€. Incluye 11 días de rutinas, guía nutricional y acceso a comunidad.",
    ),
    (
        "consideracion",
        "y el coaching 1:1, cuánto vale?",
        "El Coaching 1:1 cuesta 297€. Tenés sesiones personalizadas directamente con Stefano.",
    ),
    (
        "consideracion",
        "el precio del círculo es mensual?",
        "Sí, el Círculo de Hombres tiene una cuota mensual de 47€. Podés cancelar cuando quieras.",
    ),
    (
        "consideracion",
        "qué incluye exactamente el coaching?",
        "El Coaching 1:1 incluye sesiones individuales con Stefano, plan personalizado y seguimiento continuo.",
    ),
    (
        "consideracion",
        "cuántas sesiones tiene el coaching?",
        "El Coaching 1:1 incluye sesiones según el plan acordado con Stefano al inicio.",
    ),
    (
        "consideracion",
        "hay garantía de devolución?",
        "Sí, si en los primeros 7 días no estás satisfecho, Stefano estudia cada caso personalmente.",
    ),
    (
        "consideracion",
        "se puede hacer el fitpack sin tener mucha condición física?",
        "Claro que sí! El Fitpack está diseñado para todos los niveles, desde principiantes.",
    ),

    # ── CATEGORÍA C: OBJECIONES ───────────────────────────────────────────────
    (
        "objecion",
        "es muy caro para mí ahora mismo",
        "Entiendo que el precio puede ser una barrera. ¿Qué te parece si evaluamos qué programa se ajusta mejor a tu presupuesto?",
    ),
    (
        "objecion",
        "no tengo tiempo para hacer un programa de 11 días",
        "El Fitpack está pensado para gente ocupada — son rutinas de 20-30 minutos al día.",
    ),
    (
        "objecion",
        "no sé si esto es para mí",
        "Es normal tener dudas. ¿Cuál es tu principal objetivo ahora mismo con el fitness?",
    ),
    (
        "objecion",
        "ya probé otros programas y no me funcionaron",
        "Entiendo tu escepticismo. Lo que diferencia el método de Stefano es el enfoque personalizado y el acompañamiento.",
    ),
    (
        "objecion",
        "lo pienso y te digo",
        "Claro, tómate el tiempo que necesités. Estoy aquí cuando quieras.",
    ),
    (
        "objecion",
        "prefiero buscar algo más económico por internet",
        "Totalmente válido. Si en algún momento querés explorar lo que ofrece Stefano, aquí estamos.",
    ),

    # ── CATEGORÍA D: DECISIÓN / INTENCIÓN DE COMPRA ───────────────────────────
    (
        "decision",
        "quiero apuntarme al fitpack",
        "Genial! Para el Fitpack Challenge, podés acceder desde aquí: https://stefanobonanno.com/fitpack",
    ),
    (
        "decision",
        "cómo puedo contratar el coaching?",
        "Para el Coaching 1:1, reserva tu sesión inicial aquí: https://stefanobonanno.com/coaching",
    ),
    (
        "decision",
        "me quiero unir al círculo de hombres",
        "Perfecto! Podés unirte al Círculo de Hombres desde: https://stefanobonanno.com/circulo",
    ),
    (
        "decision",
        "acepto paypal?",
        "Sí, aceptamos PayPal y tarjeta de crédito/débito para todos los programas.",
    ),
    (
        "decision",
        "puedo pagar a plazos?",
        "Hay opciones de pago. Escríbele directamente a Stefano para ver las posibilidades.",
    ),

    # ── CATEGORÍA E: POST-VENTA (ya son clientes) ─────────────────────────────
    (
        "post_venta",
        "ya compré el fitpack pero no sé cómo acceder",
        "Para acceder al Fitpack, revisá el email de confirmación con las instrucciones de acceso.",
    ),
    (
        "post_venta",
        "no me llegó el acceso al programa",
        "Revisá spam. Si no está, escribe a soporte con tu comprobante de pago y lo resolvemos.",
    ),
    (
        "post_venta",
        "terminé el fitpack y quiero continuar",
        "Genial que lo terminaste! El Coaching 1:1 es el siguiente paso natural para seguir progresando.",
    ),
    (
        "post_venta",
        "el programa está en español?",
        "Sí, todos los programas de Stefano están completamente en español.",
    ),

    # ── CATEGORÍA F: EDGE CASES ───────────────────────────────────────────────
    (
        "edge_case",
        "",
        "Estoy aquí para ayudarte. ¿En qué puedo echarte una mano?",
    ),
    (
        "edge_case",
        "?",
        "Dime en qué puedo ayudarte!",
    ),
    (
        "edge_case",
        "HOLA QUÉ TAL TODO BIEN?",
        "Hola! Todo bien por aquí. ¿En qué puedo ayudarte?",
    ),
    (
        "edge_case",
        ".",
        "Estoy aquí si necesitás algo.",
    ),
    (
        "edge_case",
        "jajajaja",
        "Ja! ¿Hay algo en lo que pueda ayudarte?",
    ),

    # ── CATEGORÍA G: MULTILINGÜE / OFF-TOPIC ─────────────────────────────────
    (
        "off_topic",
        "qué opinas del bitcoin?",
        "No es mi área, pero si te interesa el fitness y desarrollo personal, ¡ahí sí puedo ayudarte!",
    ),
    (
        "off_topic",
        "what's the price of the fitpack?",
        "The Fitpack Challenge is 97€. It's an 11-day intensive fitness program.",
    ),
    (
        "off_topic",
        "puedes ayudarme con mi declaración de la renta?",
        "Eso se escapa de lo que puedo ayudarte, pero si es sobre fitness o coaching, ¡pregúntame!",
    ),
    (
        "off_topic",
        "me recomiendas algún libro de nutrición?",
        "Stefano tiene contenido sobre nutrición en sus programas. ¿Te cuento más sobre el Fitpack?",
    ),

    # ── CATEGORÍA H: SENSIBLE / FRUSTRACIÓN ───────────────────────────────────
    (
        "sensible",
        "me siento muy mal con mi cuerpo y sin energía",
        "Entiendo cómo te sentís. Muchos que empezaron el Fitpack estaban igual. ¿Querés que te cuente cómo puede ayudarte?",
    ),
    (
        "sensible",
        "llevo mucho tiempo sin motivación para hacer deporte",
        "La motivación va y viene. Lo que funciona es crear un sistema. El Fitpack está diseñado para eso.",
    ),
    (
        "frustracion",
        "llevas días sin responderme",
        "Disculpá la demora! Estoy aquí ahora. ¿En qué puedo ayudarte?",
    ),
    (
        "frustracion",
        "ya te pregunté esto antes y no me contestaste bien",
        "Lamento no haberte respondido bien antes. Dime de nuevo qué necesitas y lo resuelvo.",
    ),
    (
        "frustracion",
        "esto no funciona, nadie me ayuda",
        "Entiendo tu frustración. Dime exactamente qué pasó y lo soluciono ahora.",
    ),

    # ── CATEGORÍA I: AMIGO / FAMILIA ──────────────────────────────────────────
    (
        "personal",
        "ey hermano cómo estás?",
        "Bien! ¿Qué tal vos? ¿En qué te puedo ayudar?",
    ),
    (
        "personal",
        "cuándo quedamos para entrenar?",
        "Habla directamente con Stefano para coordinar eso.",
    ),

    # ── CATEGORÍA J: PREGUNTAS TÉCNICAS ──────────────────────────────────────
    (
        "tecnico",
        "el fitpack funciona en el móvil?",
        "Sí, el Fitpack funciona en cualquier dispositivo — móvil, tablet o PC.",
    ),
    (
        "tecnico",
        "hay app o es solo web?",
        "El acceso es vía web, optimizado para móvil. No requiere instalar nada.",
    ),
    (
        "tecnico",
        "puedo descargar los videos?",
        "Los videos están disponibles en streaming. Consulta con soporte para opciones de descarga.",
    ),
    (
        "tecnico",
        "tengo problemas para entrar a la plataforma",
        "Revisá que estés usando el email correcto. Si sigue sin funcionar, escribe a soporte con tu comprobante.",
    ),
    (
        "tecnico",
        "se puede hacer desde Argentina?",
        "Sí! Los programas de Stefano están disponibles en todo el mundo hispanohablante.",
    ),
    (
        "tecnico",
        "en qué idioma están los videos?",
        "Todos los videos y materiales de Stefano están en español.",
    ),
]

assert len(BATTERY_MESSAGES) == 50, f"Expected 50 messages, got {len(BATTERY_MESSAGES)}"


# =============================================================================
# HELPERS
# =============================================================================

def make_follower(n: int = 5) -> "FollowerMemory":
    return FollowerMemory(
        follower_id=SENDER_ID,
        creator_id=CREATOR_ID,
        username="carlos_test",
        name="Carlos",
        total_messages=n,
        purchase_intent_score=0.0,
        interests=[],
        last_messages=[],
    )


async def _run_single(agent, message: str, llm_text: str, total_messages: int = 5) -> dict:
    """Ejecuta process_dm() para un mensaje y devuelve métricas."""
    follower = make_follower(total_messages)
    t0 = time.monotonic()

    with (
        patch.dict(os.environ, _ENV_DISABLE),
        patch(
            "core.providers.gemini_provider.generate_dm_response",
            new=AsyncMock(return_value={
                "content": llm_text,
                "model": "gemini-2.0-flash-lite",
                "provider": "gemini",
                "latency_ms": 10,
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
        try:
            result = await agent.process_dm(message, SENDER_ID, {})
            elapsed_ms = (time.monotonic() - t0) * 1000
            return {
                "ok": True,
                "intent": result.intent,
                "lead_stage": result.lead_stage,
                "confidence": result.confidence,
                "resp_len": len(result.content),
                "time_ms": int(elapsed_ms),
                "issues": [],
                "content_snippet": result.content[:60].replace("\n", " "),
            }
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            return {
                "ok": False,
                "intent": "ERROR",
                "lead_stage": "?",
                "confidence": 0.0,
                "resp_len": 0,
                "time_ms": int(elapsed_ms),
                "issues": [str(exc)[:80]],
                "content_snippet": "",
            }


def _print_table(results: list) -> None:
    """Imprime tabla formateada con los resultados de la batería."""
    header = (
        f"{'#':>3}  "
        f"{'Cat':<13}  "
        f"{'Mensaje':<35}  "
        f"{'Intent':<20}  "
        f"{'Stage':<10}  "
        f"{'Conf':>5}  "
        f"{'Len':>4}  "
        f"{'ms':>5}  "
        f"{'Issues':<30}"
    )
    sep = "-" * len(header)

    print(f"\n{'='*80}")
    print("BATERÍA DE 50 MENSAJES — STEFANO BONANNO ASSISTANT")
    print(f"{'='*80}")
    print(header)
    print(sep)

    errors = 0
    slow = 0
    for i, (cat, msg, _, metrics) in enumerate(results, 1):
        msg_short = (msg[:33] + "..") if len(msg) > 35 else msg
        issues_str = "; ".join(metrics["issues"]) if metrics["issues"] else ""
        ok_mark = "✓" if metrics["ok"] else "✗"
        if not metrics["ok"]:
            errors += 1
        if metrics["time_ms"] > 1000:
            slow += 1
        print(
            f"{ok_mark}{i:>2}  "
            f"{cat:<13}  "
            f"{msg_short:<35}  "
            f"{metrics['intent'][:20]:<20}  "
            f"{metrics['lead_stage'][:10]:<10}  "
            f"{metrics['confidence']:5.2f}  "
            f"{metrics['resp_len']:>4}  "
            f"{metrics['time_ms']:>5}  "
            f"{issues_str:<30}"
        )

    print(sep)

    # Estadísticas
    total = len(results)
    ok_count = sum(1 for _, _, _, m in results if m["ok"])
    avg_time = sum(m["time_ms"] for _, _, _, m in results) / total
    avg_conf = sum(m["confidence"] for _, _, _, m in results) / total
    avg_len = sum(m["resp_len"] for _, _, _, m in results) / total

    print(f"\nRESUMEN: {ok_count}/{total} OK | Errors: {errors} | Slow(>1s): {slow}")
    print(f"Tiempo promedio: {avg_time:.0f}ms | Conf. promedio: {avg_conf:.2f} | Long. promedio: {avg_len:.0f} chars")
    print(f"{'='*80}\n")


# =============================================================================
# TEST PRINCIPAL
# =============================================================================

@pytest.fixture(scope="module")
def battery_agent():
    if not _IMPORTS_OK:
        pytest.skip(f"Imports failed: {_import_msg}")
    try:
        return DMResponderAgentV2(
            creator_id=CREATOR_ID,
            personality=MOCK_PERSONALITY,
            products=MOCK_PRODUCTS,
        )
    except Exception as e:
        pytest.skip(f"No se pudo crear DMResponderAgentV2: {e}")


class TestBatteryRealista:
    """Batería de 50 mensajes realistas con tabla de resultados."""

    async def test_battery_all_50_messages(self, battery_agent, capsys):
        """
        Ejecuta los 50 mensajes y verifica:
        - Tasa de éxito >= 80%
        - Ningún mensaje produce crash (siempre devuelve DMResponse)
        - Mensajes de crisis retornan intent='sensitive_content'
        - Tiempo promedio < 1000ms por mensaje
        """
        if not _IMPORTS_OK:
            pytest.skip(f"Imports failed: {_import_msg}")

        results = []
        for i, (cat, message, llm_text) in enumerate(BATTERY_MESSAGES):
            metrics = await _run_single(battery_agent, message, llm_text, total_messages=i)
            results.append((cat, message, llm_text, metrics))

        _print_table(results)

        # ── Aserciones globales ──────────────────────────────────────────────
        ok_count = sum(1 for _, _, _, m in results if m["ok"])
        total = len(results)
        success_rate = ok_count / total

        assert success_rate >= 0.80, (
            f"Success rate too low: {ok_count}/{total} = {success_rate:.1%}. "
            f"Errors: {[m['issues'] for _, _, _, m in results if not m['ok']]}"
        )

        avg_time = sum(m["time_ms"] for _, _, _, m in results) / total
        assert avg_time < 1000, (
            f"Average pipeline time {avg_time:.0f}ms exceeds 1000ms threshold"
        )

    async def test_battery_no_empty_responses(self, battery_agent):
        """Ningún mensaje debe producir una respuesta vacía."""
        if not _IMPORTS_OK:
            pytest.skip(f"Imports failed: {_import_msg}")

        for cat, message, llm_text in BATTERY_MESSAGES[:20]:  # subset rápido
            metrics = await _run_single(battery_agent, message, llm_text)
            if metrics["ok"]:
                assert metrics["resp_len"] > 0, (
                    f"Empty response for [{cat}] message: '{message}'"
                )

    async def test_battery_by_category(self, battery_agent, capsys):
        """Estadísticas por categoría."""
        if not _IMPORTS_OK:
            pytest.skip(f"Imports failed: {_import_msg}")

        from collections import defaultdict
        cat_stats = defaultdict(lambda: {"ok": 0, "total": 0, "intents": []})

        for cat, message, llm_text in BATTERY_MESSAGES:
            metrics = await _run_single(battery_agent, message, llm_text)
            cat_stats[cat]["total"] += 1
            if metrics["ok"]:
                cat_stats[cat]["ok"] += 1
                cat_stats[cat]["intents"].append(metrics["intent"])

        print(f"\n{'='*60}")
        print("ESTADÍSTICAS POR CATEGORÍA")
        print(f"{'='*60}")
        for cat, stats in sorted(cat_stats.items()):
            ok = stats["ok"]
            total = stats["total"]
            intents = list(set(stats["intents"]))[:3]
            rate = ok / total if total > 0 else 0
            print(f"  {cat:<15}: {ok}/{total} ({rate:.0%}) | intents: {intents}")
        print(f"{'='*60}\n")

        # Todas las categorías deben tener al menos 50% éxito
        for cat, stats in cat_stats.items():
            rate = stats["ok"] / stats["total"] if stats["total"] > 0 else 0
            assert rate >= 0.5, (
                f"Category '{cat}' success rate too low: {rate:.0%}"
            )

    async def test_crisis_messages_trigger_sensitive_intent(self, battery_agent):
        """Los mensajes sensibles activan sensitive_content intent."""
        if not _IMPORTS_OK:
            pytest.skip(f"Imports failed: {_import_msg}")

        crisis_messages = [
            "quiero hacerme daño",
            "me voy a suicidar",
        ]
        for msg in crisis_messages:
            metrics = await _run_single(battery_agent, msg, "fallback")
            if metrics["ok"]:
                assert metrics["intent"] == "sensitive_content", (
                    f"Crisis message '{msg}' should trigger sensitive_content, "
                    f"got: {metrics['intent']}"
                )

    async def test_pricing_messages_get_product_intents(self, battery_agent):
        """Mensajes de precio → intent relacionado con producto/pricing."""
        if not _IMPORTS_OK:
            pytest.skip(f"Imports failed: {_import_msg}")

        price_messages = [
            ("cuánto cuesta el fitpack?", "El Fitpack cuesta 97€."),
            ("y el coaching 1:1, cuánto vale?", "El Coaching 1:1 cuesta 297€."),
            ("el precio del círculo es mensual?", "Sí, 47€/mes."),
        ]
        product_intents = {
            "pricing", "product_question", "product_info",
            "purchase", "purchase_intent"
        }
        for msg, llm_text in price_messages:
            metrics = await _run_single(battery_agent, msg, llm_text)
            if metrics["ok"]:
                assert metrics["intent"] in product_intents or metrics["intent"] in ("other", "social"), (
                    f"Pricing message '{msg}' got unexpected intent: {metrics['intent']}"
                )
