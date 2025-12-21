"""
Clasificador de intención para mensajes de DM
Usa LLM para clasificar la intención del mensaje del seguidor
"""

import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Intent(Enum):
    """Tipos de intención detectables en mensajes"""
    GREETING = "greeting"
    QUESTION_GENERAL = "question_general"
    QUESTION_PRODUCT = "question_product"
    INTEREST_SOFT = "interest_soft"
    INTEREST_STRONG = "interest_strong"
    OBJECTION = "objection"
    SUPPORT = "support"
    FEEDBACK_POSITIVE = "feedback_positive"
    FEEDBACK_NEGATIVE = "feedback_negative"
    ESCALATION = "escalation"  # Usuario quiere hablar con humano
    SPAM = "spam"
    OTHER = "other"


@dataclass
class IntentResult:
    """Resultado de la clasificación de intención"""
    intent: Intent
    confidence: float
    sub_intent: str = ""
    entities: List[str] = None
    suggested_action: str = ""
    reasoning: str = ""

    def __post_init__(self):
        if self.entities is None:
            self.entities = []


class IntentClassifier:
    """Clasificador de intención usando LLM"""

    INTENT_ACTIONS = {
        Intent.GREETING: "greet_and_discover",
        Intent.QUESTION_GENERAL: "answer_from_rag",
        Intent.QUESTION_PRODUCT: "answer_product_info",
        Intent.INTEREST_SOFT: "nurture_and_qualify",
        Intent.INTEREST_STRONG: "close_sale",
        Intent.OBJECTION: "handle_objection",
        Intent.SUPPORT: "provide_support",
        Intent.FEEDBACK_POSITIVE: "thank_and_engage",
        Intent.FEEDBACK_NEGATIVE: "apologize_and_resolve",
        Intent.ESCALATION: "escalate_to_human",
        Intent.SPAM: "ignore",
        Intent.OTHER: "clarify"
    }

    CLASSIFICATION_PROMPT = """Eres un clasificador de intención para mensajes de DM de Instagram.

Clasifica el siguiente mensaje en UNA de estas categorías:

1. GREETING - Saludo inicial ("hola", "buenas", "hey", "qué tal")
2. QUESTION_GENERAL - Pregunta sobre contenido general, no sobre productos
3. QUESTION_PRODUCT - Pregunta específica sobre un producto/servicio/curso
4. INTEREST_SOFT - Interés leve ("me interesa", "cuéntame más", "suena bien")
5. INTEREST_STRONG - Interés de compra ("quiero comprar", "cómo pago", "precio", "me apunto", "dónde compro")
6. OBJECTION - Objeción a la compra ("es caro", "no tengo tiempo", "lo pienso", "ahora no", "no puedo")
7. SUPPORT - Problema, queja o soporte técnico ("no funciona", "error", "ayuda", "problema")
8. FEEDBACK_POSITIVE - Comentario positivo ("gracias", "increíble", "me encanta", "genial")
9. FEEDBACK_NEGATIVE - Comentario negativo o queja ("malo", "decepcionado", "no me gustó")
10. ESCALATION - Usuario quiere hablar con persona real/humano ("hablar con persona", "hablar con humano", "agente real", "quiero hablar con alguien", "pásame con")
11. SPAM - Spam, publicidad, promoción de terceros, irrelevante
12. OTHER - No encaja en ninguna categoría

Contexto del creador: {creator_context}
Historial reciente de conversación: {conversation_history}

Mensaje a clasificar: "{message}"

Responde SOLO con un JSON válido:
{{
    "intent": "CATEGORIA_EN_MAYUSCULAS",
    "confidence": 0.0-1.0,
    "sub_intent": "descripción breve específica",
    "entities": ["entidad1", "entidad2"],
    "reasoning": "explicación breve de por qué esta categoría"
}}"""

    QUICK_PATTERNS = {
        Intent.GREETING: [
            "hola", "buenas", "hey", "hi", "hello", "buenos días",
            "buenas tardes", "buenas noches", "qué tal", "que tal",
            "saludos", "holaa", "holaaa", "ey", "wenas"
        ],
        Intent.FEEDBACK_POSITIVE: [
            "gracias", "genial", "increíble", "me encanta", "excelente",
            "perfecto", "brutal", "top", "crack", "eres el mejor",
            "eres la mejor", "lo mejor", "maravilloso", "fenomenal"
        ],
        Intent.INTEREST_STRONG: [
            "quiero comprar", "cómo pago", "como pago", "me apunto",
            "lo quiero", "dónde compro", "donde compro", "cuánto cuesta",
            "cuanto cuesta", "precio", "cómo lo compro", "quiero el curso",
            "quiero inscribirme", "me interesa comprar"
        ],
        Intent.INTEREST_SOFT: [
            "me interesa", "cuéntame más", "cuentame mas", "suena bien",
            "suena interesante", "quiero saber más", "info", "información",
            "más información", "tienes algo", "ofreces"
        ],
        Intent.OBJECTION: [
            "es caro", "muy caro", "no puedo", "no tengo tiempo",
            "lo pienso", "lo voy a pensar", "ahora no", "más adelante",
            "no sé si", "no estoy seguro", "demasiado caro"
        ],
        Intent.SUPPORT: [
            "no funciona", "error", "problema", "ayuda", "no puedo acceder",
            "no me deja", "falla", "bug", "soporte", "no carga"
        ],
        Intent.ESCALATION: [
            "hablar con persona", "hablar con humano", "persona real",
            "agente humano", "agente real", "quiero hablar con alguien",
            "pásame con", "pasame con", "hablar con un humano",
            "contactar persona", "necesito hablar con", "prefiero hablar con",
            "quiero un humano", "eres un bot", "eres robot", "no eres real",
            "hablar con soporte", "hablar con atención", "operador"
        ]
    }

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: Cliente LLM con método generate() o chat()
        """
        self.llm_client = llm_client

    def _quick_classify(self, message: str) -> Optional[IntentResult]:
        """Clasificación rápida basada en patrones"""
        message_lower = message.lower().strip()

        # Detectar spam por longitud o patrones
        if len(message_lower) > 500 or "http" in message_lower:
            if any(spam in message_lower for spam in ["compra", "gana dinero", "bitcoin", "crypto"]):
                return IntentResult(
                    intent=Intent.SPAM,
                    confidence=0.9,
                    sub_intent="promotional_spam",
                    suggested_action="ignore"
                )

        # Buscar patrones conocidos
        for intent, patterns in self.QUICK_PATTERNS.items():
            for pattern in patterns:
                if pattern in message_lower:
                    return IntentResult(
                        intent=intent,
                        confidence=0.85,
                        sub_intent=f"pattern_match:{pattern}",
                        suggested_action=self.INTENT_ACTIONS.get(intent, "clarify")
                    )

        return None

    async def classify(
        self,
        message: str,
        creator_context: str = "",
        conversation_history: List[dict] = None,
        use_llm: bool = True
    ) -> IntentResult:
        """Clasificar la intención de un mensaje"""

        # Intentar clasificación rápida primero
        quick_result = self._quick_classify(message)
        if quick_result and quick_result.confidence >= 0.85:
            return quick_result

        # Si no hay LLM o no queremos usarlo, devolver resultado rápido o OTHER
        if not use_llm or not self.llm_client:
            if quick_result:
                return quick_result
            return IntentResult(
                intent=Intent.OTHER,
                confidence=0.5,
                sub_intent="no_llm_fallback",
                suggested_action="clarify"
            )

        # Clasificación con LLM
        history_str = ""
        if conversation_history:
            history_str = "\n".join([
                f"{'Usuario' if m.get('role') == 'user' else 'Asistente'}: {m.get('content', '')}"
                for m in conversation_history[-5:]
            ])

        prompt = self.CLASSIFICATION_PROMPT.format(
            creator_context=creator_context or "Creador de contenido que vende cursos y servicios",
            conversation_history=history_str or "Sin historial previo",
            message=message
        )

        try:
            # Soportar diferentes interfaces de LLM
            if hasattr(self.llm_client, 'generate'):
                if hasattr(self.llm_client.generate, '__call__'):
                    import asyncio
                    if asyncio.iscoroutinefunction(self.llm_client.generate):
                        response = await self.llm_client.generate(prompt)
                    else:
                        response = self.llm_client.generate(prompt)
            elif hasattr(self.llm_client, 'chat'):
                import asyncio
                if asyncio.iscoroutinefunction(self.llm_client.chat):
                    response = await self.llm_client.chat([{"role": "user", "content": prompt}])
                else:
                    response = self.llm_client.chat([{"role": "user", "content": prompt}])
            else:
                # Fallback
                response = str(self.llm_client.generate(prompt))

            result = self._parse_response(response)
            return result

        except Exception as e:
            logger.error(f"Error classifying intent: {e}")
            # Usar clasificación rápida como fallback
            if quick_result:
                return quick_result
            return IntentResult(
                intent=Intent.OTHER,
                confidence=0.5,
                sub_intent="classification_error",
                entities=[],
                suggested_action="clarify",
                reasoning=f"Error en clasificación: {str(e)}"
            )

    def _parse_response(self, response: str) -> IntentResult:
        """Parsear respuesta JSON del LLM"""
        try:
            # Limpiar respuesta
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            # Encontrar JSON en la respuesta
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                response = response[start_idx:end_idx]

            data = json.loads(response.strip())

            # Mapear intent
            intent_str = data.get("intent", "OTHER").upper()
            try:
                intent = Intent[intent_str]
            except KeyError:
                # Intentar mapeo flexible
                intent_map = {
                    "GREETING": Intent.GREETING,
                    "QUESTION": Intent.QUESTION_GENERAL,
                    "PRODUCT": Intent.QUESTION_PRODUCT,
                    "INTEREST": Intent.INTEREST_SOFT,
                    "BUY": Intent.INTEREST_STRONG,
                    "PURCHASE": Intent.INTEREST_STRONG,
                    "OBJECTION": Intent.OBJECTION,
                    "SUPPORT": Intent.SUPPORT,
                    "POSITIVE": Intent.FEEDBACK_POSITIVE,
                    "NEGATIVE": Intent.FEEDBACK_NEGATIVE,
                    "ESCALATION": Intent.ESCALATION,
                    "HUMAN": Intent.ESCALATION,
                    "SPAM": Intent.SPAM
                }
                intent = intent_map.get(intent_str, Intent.OTHER)

            return IntentResult(
                intent=intent,
                confidence=float(data.get("confidence", 0.5)),
                sub_intent=data.get("sub_intent", ""),
                entities=data.get("entities", []),
                suggested_action=self.INTENT_ACTIONS.get(intent, "clarify"),
                reasoning=data.get("reasoning", "")
            )

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing intent JSON: {e}, response: {response[:200]}")
            return IntentResult(
                intent=Intent.OTHER,
                confidence=0.3,
                suggested_action="clarify",
                reasoning="Error parsing response"
            )

    def get_action(self, intent: Intent) -> str:
        """Obtener acción sugerida para una intención"""
        return self.INTENT_ACTIONS.get(intent, "clarify")

    @staticmethod
    def get_intent_description(intent: Intent) -> str:
        """Obtener descripción humana de la intención"""
        descriptions = {
            Intent.GREETING: "Saludo inicial",
            Intent.QUESTION_GENERAL: "Pregunta general",
            Intent.QUESTION_PRODUCT: "Pregunta sobre producto",
            Intent.INTEREST_SOFT: "Interés leve",
            Intent.INTEREST_STRONG: "Alta intención de compra",
            Intent.OBJECTION: "Objeción o duda",
            Intent.SUPPORT: "Solicitud de soporte",
            Intent.FEEDBACK_POSITIVE: "Feedback positivo",
            Intent.FEEDBACK_NEGATIVE: "Feedback negativo",
            Intent.ESCALATION: "Solicita hablar con humano",
            Intent.SPAM: "Spam",
            Intent.OTHER: "Otro"
        }
        return descriptions.get(intent, "Desconocido")


class ConversationAnalyzer:
    """Analizador de conversaciones completas"""

    def __init__(self, intent_classifier: IntentClassifier):
        self.classifier = intent_classifier

    async def analyze_conversation(
        self,
        messages: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Analizar una conversación completa"""
        intents = []
        intent_counts = {}

        for msg in messages:
            if msg.get("role") == "user":
                result = await self.classifier.classify(
                    msg.get("content", ""),
                    use_llm=False  # Usar clasificación rápida
                )
                intents.append(result.intent.value)
                intent_counts[result.intent.value] = intent_counts.get(result.intent.value, 0) + 1

        # Calcular puntuación de intención de compra
        purchase_signals = intent_counts.get("interest_strong", 0) * 3
        purchase_signals += intent_counts.get("interest_soft", 0) * 1
        purchase_signals += intent_counts.get("question_product", 0) * 2
        purchase_signals -= intent_counts.get("objection", 0) * 1

        total_messages = len([m for m in messages if m.get("role") == "user"])
        purchase_intent_score = min(1.0, max(0.0, purchase_signals / max(total_messages, 1) / 2))

        # Determinar etapa del embudo
        funnel_stage = "awareness"
        if purchase_intent_score > 0.7:
            funnel_stage = "decision"
        elif purchase_intent_score > 0.4:
            funnel_stage = "consideration"
        elif purchase_intent_score > 0.2:
            funnel_stage = "interest"

        return {
            "total_messages": total_messages,
            "intent_distribution": intent_counts,
            "purchase_intent_score": purchase_intent_score,
            "funnel_stage": funnel_stage,
            "has_objections": intent_counts.get("objection", 0) > 0,
            "is_engaged": total_messages >= 3,
            "needs_support": intent_counts.get("support", 0) > 0
        }
