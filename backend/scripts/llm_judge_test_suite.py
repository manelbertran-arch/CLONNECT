#!/usr/bin/env python3
"""
LLM-as-a-Judge Test Suite para Clonnect

Evalúa respuestas GENERADAS del bot usando un LLM como juez.
Mide las categorías que dependen del comportamiento del LLM:
- NO_REPETIR: No hacer preguntas redundantes
- COHERENCIA: Mantener el tema de conversación
- CONVERSION: Proponer CTAs y cerrar ventas
"""

import asyncio
import json
import os
import sys
import uuid
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dm_agent import DMResponderAgent
from core.llm import get_llm_client


class JudgeCategory(Enum):
    NO_REPETIR = "no_repetir"
    COHERENCIA = "coherencia"
    CONVERSION = "conversion"


@dataclass
class JudgeTestCase:
    """Test case para evaluación con LLM judge"""
    id: str
    name: str
    category: JudgeCategory
    messages: List[str]  # Secuencia de mensajes del usuario
    criteria: str  # Criterio de evaluación para el LLM judge
    weight: float = 1.0


@dataclass
class ConversationTurn:
    """Un turno de conversación"""
    user: str
    bot: str
    intent: str = ""
    confidence: float = 0.0


@dataclass
class JudgeResult:
    """Resultado de evaluación del LLM judge"""
    score: int
    passed: bool
    issues: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    feedback: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# TEST CASES
# ═══════════════════════════════════════════════════════════════════════════════

NO_REPETIR_TESTS = [
    JudgeTestCase(
        id="NR1",
        name="No preguntar nombre dos veces",
        category=JudgeCategory.NO_REPETIR,
        messages=[
            "Hola, soy María",
            "Me interesa el curso de meditación",
            "¿Cuánto cuesta?",
            "Ok, cuéntame más"
        ],
        criteria="""
CRITERIO: El bot NO debe preguntar el nombre si el usuario ya lo dio.

✅ PASS si: El bot usa "María" en alguna respuesta Y nunca pregunta
            "¿cómo te llamas?" o similar
❌ FAIL si: El bot pregunta el nombre en cualquier momento después
            de que el usuario dijo "soy María"

También verificar que no pregunte cosas ya respondidas (interés en meditación).
Score 90+ si usa el nombre, 70-89 si no pregunta pero tampoco usa, <70 si pregunta."""
    ),
    JudgeTestCase(
        id="NR2",
        name="Recordar objeción de precio",
        category=JudgeCategory.NO_REPETIR,
        messages=[
            "Me interesa el coaching",
            "¿Cuánto cuesta?",
            "Es un poco caro para mí",
            "Déjame pensarlo",
            "Ok, cuéntame más sobre qué incluye"
        ],
        criteria="""
CRITERIO: El bot debe recordar la objeción de precio.

✅ PASS si: En las últimas respuestas, el bot menciona facilidades de pago,
            descuentos, valor, o ROI - consciente de que el precio es tema
❌ FAIL si: El bot ignora la objeción previa y solo lista características
            sin abordar el tema del precio/valor

Score 90+ si aborda precio proactivamente, 70-89 si lo menciona, <70 si ignora."""
    ),
    JudgeTestCase(
        id="NR3",
        name="No repetir pregunta de interés",
        category=JudgeCategory.NO_REPETIR,
        messages=[
            "Quiero reducir mi ansiedad",
            "Sí, es por el trabajo",
            "Tengo ataques de pánico a veces",
            "¿Qué me recomiendas?"
        ],
        criteria="""
CRITERIO: El bot NO debe preguntar "¿en qué área te puedo ayudar?"
          o "¿qué te gustaría mejorar?" si ya lo sabe.

✅ PASS si: Todas las respuestas asumen que el tema es ansiedad/pánico
            y nunca hacen preguntas genéricas sobre qué necesita
❌ FAIL si: Cualquier respuesta pregunta de nuevo qué problema tiene
            o en qué área quiere ayuda

Score 90+ si recomienda algo específico, 70-89 si mantiene tema, <70 si pregunta."""
    )
]

COHERENCIA_TESTS = [
    JudgeTestCase(
        id="CO1",
        name="Mantener tema ansiedad",
        category=JudgeCategory.COHERENCIA,
        messages=[
            "Tengo mucha ansiedad últimamente",
            "¿Tienes algo que me pueda ayudar?",
            "¿Cuánto tiempo toma ver resultados?",
            "Ok",
            "¿Y funciona para todos?"
        ],
        criteria="""
CRITERIO: TODAS las respuestas deben estar relacionadas con ansiedad.

✅ PASS si: Cada respuesta del bot menciona ansiedad, estrés, calma,
            o el programa específico para este problema
❌ FAIL si: Alguna respuesta cambia a otro tema (yoga genérico, otros
            cursos no relacionados) o pierde el hilo completamente

Score 90+ si 5/5 respuestas son coherentes, 70-89 si 4/5, <70 si menos."""
    ),
    JudgeTestCase(
        id="CO2",
        name="No mezclar productos",
        category=JudgeCategory.COHERENCIA,
        messages=[
            "Quiero info del curso de meditación",
            "¿Cuántos módulos tiene?",
            "¿Y cuánto cuesta?",
            "¿Tiene garantía?"
        ],
        criteria="""
CRITERIO: Todas las respuestas deben ser sobre el curso de MEDITACIÓN.

✅ PASS si: Precio, módulos y garantía se refieren al curso de meditación
❌ FAIL si: El bot mezcla info de otros productos, da precios de otro
            curso, o pregunta "¿de qué curso?" cuando ya está claro

Score 90+ si todo es coherente, 70-89 si mayormente, <70 si mezcla."""
    ),
    JudgeTestCase(
        id="CO3",
        name="Seguir hilo de objeción tiempo",
        category=JudgeCategory.COHERENCIA,
        messages=[
            "Me interesa pero no tengo mucho tiempo",
            "Trabajo 10 horas al día",
            "Hmm",
            "No sé si puedo comprometerme"
        ],
        criteria="""
CRITERIO: El bot debe mantener el tema de TIEMPO/FLEXIBILIDAD.

✅ PASS si: Todas las respuestas abordan la falta de tiempo, mencionan
            flexibilidad, duración corta, o adaptan el pitch a su situación
❌ FAIL si: Alguna respuesta ignora el tema del tiempo y habla de otra
            cosa, o peor, añade más compromisos de tiempo

Score 90+ si aborda tiempo en todas, 70-89 si en la mayoría, <70 si ignora."""
    )
]

CONVERSION_TESTS = [
    JudgeTestCase(
        id="CV1",
        name="Proponer acción después de interés",
        category=JudgeCategory.CONVERSION,
        messages=[
            "Me interesa mucho el programa",
            "Sí, creo que es lo que necesito",
            "¿Cómo funciona?",
            "Suena bien",
            "Ok, me convence"
        ],
        criteria="""
CRITERIO: Después de señales claras de interés, el bot DEBE proponer acción.

✅ PASS si: En las últimas 2 respuestas hay un CTA claro:
            - Link de pago
            - Propuesta de llamada
            - "¿Te lo reservo?"
            - Método de pago concreto
❌ FAIL si: El bot solo hace más preguntas o da más info sin proponer
            el siguiente paso concreto

Score 90+ si hay CTA claro, 70-89 si hay propuesta vaga, <70 si no hay."""
    ),
    JudgeTestCase(
        id="CV2",
        name="Cerrar cuando piden precio",
        category=JudgeCategory.CONVERSION,
        messages=[
            "¿Cuánto cuesta el programa?",
            "Ok, ¿y qué incluye?",
            "¿Hay garantía?",
            "Vale, me interesa"
        ],
        criteria="""
CRITERIO: Cuando el usuario dice "me interesa" después de preguntar precio,
          el bot debe CERRAR, no seguir vendiendo.

✅ PASS si: La última respuesta incluye forma de pago o siguiente paso,
            NO más argumentos de venta
❌ FAIL si: El bot sigue explicando beneficios en lugar de facilitar
            la compra

Score 90+ si cierra con CTA, 70-89 si propone algo, <70 si sigue vendiendo."""
    ),
    JudgeTestCase(
        id="CV3",
        name="No estancarse en preguntas",
        category=JudgeCategory.CONVERSION,
        messages=[
            "Hola, me interesa el coaching",
            "Para mejorar mi productividad",
            "Soy emprendedor",
            "Trabajo desde casa",
            "Sí, tengo problemas de enfoque",
            "Me cuesta concentrarme"
        ],
        criteria="""
CRITERIO: En 6 mensajes, debe haber al menos 1 propuesta concreta.

✅ PASS si: Al menos una respuesta propone algo específico:
            - "Te recomiendo X programa"
            - "Podemos agendar una llamada"
            - "El curso de X es ideal para ti"
❌ FAIL si: TODAS las respuestas son preguntas sin ninguna propuesta.
            El bot no debe ser solo un interrogador.

Score 90+ si propone temprano, 70-89 si propone al final, <70 si nunca."""
    )
]


class LLMJudgeTestSuite:
    """Test suite que usa LLM para evaluar respuestas generadas"""

    def __init__(self, creator_id: str = "manel"):
        self.creator_id = creator_id
        self.dm_agent = None
        self.llm = None
        self.results: Dict[str, List[Dict]] = {
            "no_repetir": [],
            "coherencia": [],
            "conversion": []
        }

    async def initialize(self):
        """Inicializar agentes"""
        print("Inicializando DMResponderAgent...")
        self.dm_agent = DMResponderAgent(creator_id=self.creator_id)
        print(f"✓ Agent initialized for creator: {self.creator_id}")

        print("Inicializando LLM judge...")
        self.llm = get_llm_client()
        print("✓ LLM judge ready")

    async def run_conversation(self, messages: List[str]) -> List[ConversationTurn]:
        """Ejecuta una conversación completa y retorna respuestas"""
        conversation = []
        follower_id = f"test_judge_{uuid.uuid4().hex[:8]}"

        for user_msg in messages:
            try:
                response = await self.dm_agent.process_dm(
                    sender_id=follower_id,
                    message_text=user_msg,
                    message_id=str(uuid.uuid4()),
                    username="test_user",
                    name="Usuario Test"
                )

                conversation.append(ConversationTurn(
                    user=user_msg,
                    bot=response.response_text or "(sin respuesta)",
                    intent=response.intent.value if response.intent else "unknown",
                    confidence=response.confidence or 0.0
                ))
            except Exception as e:
                print(f"  ⚠️ Error en mensaje '{user_msg[:30]}...': {e}")
                conversation.append(ConversationTurn(
                    user=user_msg,
                    bot=f"(error: {str(e)[:50]})",
                    intent="error",
                    confidence=0.0
                ))

        return conversation

    async def evaluate_with_llm(
        self,
        conversation: List[ConversationTurn],
        test: JudgeTestCase
    ) -> JudgeResult:
        """Usa LLM para evaluar la conversación según criterios"""

        conv_text = "\n".join([
            f"Usuario: {turn.user}\nBot: {turn.bot}"
            for turn in conversation
        ])

        eval_prompt = f"""Eres un evaluador experto de chatbots de ventas.
Tu trabajo es ser ESTRICTO pero JUSTO al evaluar.

═══════════════════════════════════════════════════════════════
CONVERSACIÓN A EVALUAR:
═══════════════════════════════════════════════════════════════
{conv_text}

═══════════════════════════════════════════════════════════════
CATEGORÍA: {test.category.value.upper()}
TEST: {test.name}
═══════════════════════════════════════════════════════════════

CRITERIO DE EVALUACIÓN:
{test.criteria}

═══════════════════════════════════════════════════════════════
INSTRUCCIONES:
═══════════════════════════════════════════════════════════════
Evalúa la conversación y responde ÚNICAMENTE con este JSON (sin texto adicional):
{{
    "score": <número 0-100>,
    "passed": <true si score >= 70, false si no>,
    "issues": ["lista de problemas específicos encontrados"],
    "strengths": ["lista de cosas bien hechas"],
    "feedback": "resumen de 1-2 líneas sobre qué mejorar"
}}

Sé específico en issues/strengths citando frases exactas de la conversación."""

        try:
            response = await self.llm.chat([
                {"role": "user", "content": eval_prompt}
            ], max_tokens=600, temperature=0.3)

            # Limpiar respuesta y extraer JSON
            response = response.strip()

            # Buscar JSON en la respuesta
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                response = json_match.group()

            result = json.loads(response)

            return JudgeResult(
                score=result.get("score", 50),
                passed=result.get("passed", False),
                issues=result.get("issues", []),
                strengths=result.get("strengths", []),
                feedback=result.get("feedback", "")
            )
        except json.JSONDecodeError as e:
            print(f"  ⚠️ Error parsing JSON: {e}")
            print(f"  Response was: {response[:200]}...")
            return JudgeResult(
                score=50,
                passed=False,
                issues=["Error parsing LLM response"],
                feedback="No se pudo evaluar"
            )
        except Exception as e:
            print(f"  ⚠️ Error en evaluación: {e}")
            return JudgeResult(
                score=50,
                passed=False,
                issues=[f"Error: {str(e)}"],
                feedback="Error en evaluación"
            )

    async def run_test(self, test: JudgeTestCase) -> Dict:
        """Ejecuta un test individual"""
        print(f"\n{'─'*60}")
        print(f"🔄 Test {test.id}: {test.name}")
        print(f"{'─'*60}")

        # Ejecutar conversación real
        conversation = await self.run_conversation(test.messages)

        # Mostrar conversación
        print("\n📝 Conversación:")
        for i, turn in enumerate(conversation, 1):
            print(f"  [{i}] User: {turn.user}")
            bot_preview = turn.bot[:100] + "..." if len(turn.bot) > 100 else turn.bot
            print(f"      Bot:  {bot_preview}")

        # Evaluar con LLM
        print("\n⚖️ Evaluando con LLM judge...")
        result = await self.evaluate_with_llm(conversation, test)

        # Mostrar resultado
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"\n📊 Score: {result.score}/100 {status}")

        if result.issues:
            print(f"   Issues: {', '.join(result.issues[:2])}")
        if result.strengths:
            print(f"   Strengths: {', '.join(result.strengths[:2])}")
        if result.feedback:
            print(f"   Feedback: {result.feedback}")

        return {
            "test_id": test.id,
            "name": test.name,
            "category": test.category.value,
            "score": result.score,
            "passed": result.passed,
            "issues": result.issues,
            "strengths": result.strengths,
            "feedback": result.feedback,
            "conversation": [
                {"user": t.user, "bot": t.bot}
                for t in conversation
            ]
        }

    async def run_all_tests(self) -> Dict:
        """Ejecuta todos los tests"""
        await self.initialize()

        all_tests = {
            JudgeCategory.NO_REPETIR: NO_REPETIR_TESTS,
            JudgeCategory.COHERENCIA: COHERENCIA_TESTS,
            JudgeCategory.CONVERSION: CONVERSION_TESTS
        }

        print("\n" + "═"*70)
        print("    CLONNECT LLM-AS-A-JUDGE TEST SUITE")
        print("═"*70)
        print(f"Total tests: {sum(len(t) for t in all_tests.values())}")
        print(f"Categories: {len(all_tests)}")
        print("═"*70)

        results_by_category = {}

        for category, tests in all_tests.items():
            print(f"\n{'═'*60}")
            print(f"CATEGORÍA: {category.value.upper()}")
            print(f"Tests: {len(tests)}")
            print(f"{'═'*60}")

            category_results = []
            for test in tests:
                result = await self.run_test(test)
                category_results.append(result)
                self.results[category.value].append(result)

                # Pequeña pausa para rate limiting
                await asyncio.sleep(1)

            avg_score = sum(r["score"] for r in category_results) / len(category_results)
            passed = sum(1 for r in category_results if r["passed"])

            results_by_category[category.value] = {
                "average_score": avg_score,
                "tests_passed": passed,
                "total_tests": len(tests),
                "results": category_results
            }

        return results_by_category

    def print_report(self, results: Dict):
        """Imprime el reporte final"""
        print("\n" + "═"*70)
        print("              CLONNECT LLM JUDGE TEST REPORT")
        print(f"              Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("═"*70)

        # Calcular score total ponderado
        weights = {
            "no_repetir": 0.35,
            "coherencia": 0.35,
            "conversion": 0.30
        }

        total_weighted = sum(
            results[cat]["average_score"] * weights[cat]
            for cat in results
        )

        stars = "⭐" * min(5, int(total_weighted / 20))
        print(f"\n    SCORE TOTAL: {total_weighted:.0f}/100 {stars}")

        print("\n" + "═"*70)
        print("    BREAKDOWN POR CATEGORÍA:")
        print("═"*70)

        targets = {
            "no_repetir": 85,
            "coherencia": 90,
            "conversion": 80
        }

        print("\n    ┌────────────────────────┬────────┬────────┬─────────┐")
        print("    │ Categoría              │ Score  │ Target │ Status  │")
        print("    ├────────────────────────┼────────┼────────┼─────────┤")

        for cat, data in results.items():
            score = data["average_score"]
            target = targets[cat]
            passed = data["tests_passed"]
            total = data["total_tests"]

            if score >= target:
                status = "✅"
            elif score >= target - 10:
                status = "⚠️"
            else:
                status = "❌"

            cat_display = f"{cat.upper():15}"
            print(f"    │ {cat_display} │  {score:4.0f}% │  {target:3}% │ {status} {passed}/{total}   │")

        print("    └────────────────────────┴────────┴────────┴─────────┘")

        # Tests fallidos
        failed_tests = []
        for cat, data in results.items():
            for result in data["results"]:
                if not result["passed"]:
                    failed_tests.append(result)

        if failed_tests:
            print("\n" + "═"*70)
            print("    TESTS FALLIDOS:")
            print("═"*70)
            for test in failed_tests:
                print(f"    ❌ {test['test_id']}: {test['name']}")
                if test.get("feedback"):
                    print(f"       → {test['feedback']}")

        # Recomendaciones
        print("\n" + "═"*70)
        print("    RECOMENDACIONES:")
        print("═"*70)

        recommendations = []
        for cat, data in results.items():
            score = data["average_score"]
            target = targets[cat]
            if score < target:
                gap = target - score
                if cat == "no_repetir":
                    recommendations.append(
                        f"NO_REPETIR ({gap:.0f}% bajo target): Mejorar memoria de contexto"
                    )
                elif cat == "coherencia":
                    recommendations.append(
                        f"COHERENCIA ({gap:.0f}% bajo target): Mantener tema en respuestas"
                    )
                elif cat == "conversion":
                    recommendations.append(
                        f"CONVERSION ({gap:.0f}% bajo target): Añadir más CTAs"
                    )

        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                print(f"    {i}. {rec}")
        else:
            print("    ✅ Todas las categorías cumplen sus targets!")

        print("\n" + "═"*70)


async def main():
    """Entry point"""
    suite = LLMJudgeTestSuite(creator_id="manel")

    try:
        results = await suite.run_all_tests()
        suite.print_report(results)
    except Exception as e:
        print(f"\n❌ Error ejecutando tests: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
