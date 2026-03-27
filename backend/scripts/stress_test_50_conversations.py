"""
50-Conversation Stress Test — validates DM pipeline under load.

Runs 50 synthetic conversations through DMResponderAgent.process_dm(),
covering 10 categories x 5 scenarios each. Measures latency, success rate,
and validates response quality.

Usage:
    cd ~/Clonnect/backend
    python3 scripts/stress_test_50_conversations.py [--creator CREATOR_NAME] [--parallel N]

Requirements:
    - Database must be accessible (reads creator config)
    - LLM providers must be configured (Gemini/OpenAI keys)
    - Creator must exist in DB with onboarding completed

Output: JSON report at stress_test_output/report_{timestamp}.json
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("stress_test")


# =============================================================================
# TEST SCENARIOS — 10 categories x 5 conversations = 50 total
# =============================================================================

@dataclass
class ConversationScenario:
    """A single conversation scenario to test."""
    id: str
    category: str
    description: str
    turns: List[Dict[str, str]]  # [{"role": "user", "content": "..."}, ...]


SCENARIOS: List[ConversationScenario] = [
    # --- Category 1: GREETINGS (5) ---
    ConversationScenario("G1", "greeting", "Simple hola", [
        {"role": "user", "content": "Hola!"},
    ]),
    ConversationScenario("G2", "greeting", "Greeting with name", [
        {"role": "user", "content": "Hola, soy María"},
    ]),
    ConversationScenario("G3", "greeting", "Emoji greeting", [
        {"role": "user", "content": "Hey! 👋"},
    ]),
    ConversationScenario("G4", "greeting", "Evening greeting", [
        {"role": "user", "content": "Buenas noches, cómo estás?"},
    ]),
    ConversationScenario("G5", "greeting", "Informal greeting", [
        {"role": "user", "content": "Qué onda!"},
    ]),

    # --- Category 2: PRODUCT QUESTIONS (5) ---
    ConversationScenario("PQ1", "product_question", "Price inquiry", [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola! Cómo estás?"},
        {"role": "user", "content": "Cuánto cuesta tu curso?"},
    ]),
    ConversationScenario("PQ2", "product_question", "What's included", [
        {"role": "user", "content": "Qué incluye tu programa?"},
    ]),
    ConversationScenario("PQ3", "product_question", "Duration question", [
        {"role": "user", "content": "Cuánto dura la mentoría?"},
    ]),
    ConversationScenario("PQ4", "product_question", "Comparison question", [
        {"role": "user", "content": "Qué diferencia hay entre el curso y la mentoría?"},
    ]),
    ConversationScenario("PQ5", "product_question", "Payment methods", [
        {"role": "user", "content": "Se puede pagar en cuotas?"},
    ]),

    # --- Category 3: OBJECTIONS (5) ---
    ConversationScenario("OB1", "objection", "Too expensive", [
        {"role": "user", "content": "Hola, vi tu curso"},
        {"role": "assistant", "content": "Genial! Te cuento, el programa cuesta 297€"},
        {"role": "user", "content": "Uff, es muy caro para mí"},
    ]),
    ConversationScenario("OB2", "objection", "No time", [
        {"role": "user", "content": "Me interesa pero no tengo tiempo ahora"},
    ]),
    ConversationScenario("OB3", "objection", "Need to think", [
        {"role": "user", "content": "Déjame pensarlo y te aviso"},
    ]),
    ConversationScenario("OB4", "objection", "Not sure it works", [
        {"role": "user", "content": "No sé si esto funciona realmente"},
    ]),
    ConversationScenario("OB5", "objection", "Had bad experience", [
        {"role": "user", "content": "Ya compré algo parecido y no me sirvió"},
    ]),

    # --- Category 4: BOOKING / SCHEDULING (5) ---
    ConversationScenario("BK1", "booking", "Want to book", [
        {"role": "user", "content": "Quiero agendar una sesión contigo"},
    ]),
    ConversationScenario("BK2", "booking", "Availability question", [
        {"role": "user", "content": "Tienes disponibilidad esta semana?"},
    ]),
    ConversationScenario("BK3", "booking", "Reschedule", [
        {"role": "user", "content": "Hola, necesito cambiar mi cita del martes"},
    ]),
    ConversationScenario("BK4", "booking", "Cancel booking", [
        {"role": "user", "content": "Tengo que cancelar mi sesión de mañana"},
    ]),
    ConversationScenario("BK5", "booking", "Group session", [
        {"role": "user", "content": "Hacen sesiones grupales? Somos 3 amigas"},
    ]),

    # --- Category 5: CONVERSION / PURCHASE INTENT (5) ---
    ConversationScenario("CV1", "conversion", "Ready to buy", [
        {"role": "user", "content": "Hola"},
        {"role": "assistant", "content": "Hola! En qué te puedo ayudar?"},
        {"role": "user", "content": "Quiero comprar el curso, cómo pago?"},
    ]),
    ConversationScenario("CV2", "conversion", "Send link", [
        {"role": "user", "content": "Mándame el link de pago"},
    ]),
    ConversationScenario("CV3", "conversion", "After objection resolved", [
        {"role": "user", "content": "Hola, pensé en lo del curso"},
        {"role": "assistant", "content": "Qué bueno que vuelves! Cuéntame"},
        {"role": "user", "content": "Sí, me decidí. Quiero inscribirme"},
    ]),
    ConversationScenario("CV4", "conversion", "Referral purchase", [
        {"role": "user", "content": "Mi amiga hizo tu curso y me recomendó, quiero apuntarme"},
    ]),
    ConversationScenario("CV5", "conversion", "Upgrade question", [
        {"role": "user", "content": "Ya tengo el curso básico, cómo puedo pasar al premium?"},
    ]),

    # --- Category 6: CONTENT / EXPERTISE QUESTIONS (5) ---
    ConversationScenario("CQ1", "content_question", "Specific advice", [
        {"role": "user", "content": "Qué ejercicios recomiendas para empezar?"},
    ]),
    ConversationScenario("CQ2", "content_question", "Story response", [
        {"role": "user", "content": "Vi tu historia de hoy, increíble!"},
    ]),
    ConversationScenario("CQ3", "content_question", "Deep question", [
        {"role": "user", "content": "Cómo puedo manejar mejor el estrés en mi vida diaria?"},
    ]),
    ConversationScenario("CQ4", "content_question", "Results question", [
        {"role": "user", "content": "Cuánto tiempo tarda en verse resultados?"},
    ]),
    ConversationScenario("CQ5", "content_question", "Beginner question", [
        {"role": "user", "content": "Soy principiante total, por dónde empiezo?"},
    ]),

    # --- Category 7: MULTI-TURN COMPLEX (5) ---
    ConversationScenario("MT1", "multi_turn", "Full funnel journey", [
        {"role": "user", "content": "Hola, acabo de encontrar tu perfil"},
        {"role": "assistant", "content": "Hola! Bienvenido/a, en qué te puedo ayudar?"},
        {"role": "user", "content": "Qué tipo de programas tienes?"},
        {"role": "assistant", "content": "Tengo mentoría 1:1, curso online y sesiones grupales"},
        {"role": "user", "content": "Cuánto cuesta la mentoría?"},
        {"role": "assistant", "content": "La mentoría tiene un precio de 297€"},
        {"role": "user", "content": "Ok me interesa, cómo es el proceso?"},
    ]),
    ConversationScenario("MT2", "multi_turn", "Objection handling chain", [
        {"role": "user", "content": "Hola, vi tu programa"},
        {"role": "assistant", "content": "Hola! Cuéntame más"},
        {"role": "user", "content": "Es caro"},
        {"role": "assistant", "content": "Entiendo, hay opciones de pago"},
        {"role": "user", "content": "Pero no sé si funciona"},
        {"role": "assistant", "content": "Mira estos testimonios de alumnos"},
        {"role": "user", "content": "Bueno, me convenciste, quiero probar"},
    ]),
    ConversationScenario("MT3", "multi_turn", "Support escalation", [
        {"role": "user", "content": "Compré el curso pero no puedo acceder"},
        {"role": "assistant", "content": "Lo siento, dime tu email para verificar"},
        {"role": "user", "content": "es maria@test.com"},
        {"role": "assistant", "content": "Encontré tu cuenta, te envío instrucciones"},
        {"role": "user", "content": "Sigue sin funcionar"},
    ]),
    ConversationScenario("MT4", "multi_turn", "Returning customer", [
        {"role": "user", "content": "Hola! Soy Ana, ya hice tu curso el año pasado"},
        {"role": "assistant", "content": "Ana! Qué gusto volver a saber de ti"},
        {"role": "user", "content": "Me encantó, tienes algo nuevo?"},
        {"role": "assistant", "content": "Sí! Lancé un programa avanzado"},
        {"role": "user", "content": "Genial, hay descuento para ex alumnos?"},
    ]),
    ConversationScenario("MT5", "multi_turn", "Detailed Q&A session", [
        {"role": "user", "content": "Necesito información detallada del curso"},
        {"role": "assistant", "content": "Claro, pregúntame lo que quieras"},
        {"role": "user", "content": "Cuántas horas de contenido son?"},
        {"role": "assistant", "content": "Son 40 horas en total, divididas en 8 módulos"},
        {"role": "user", "content": "Hay certificación al terminar?"},
    ]),

    # --- Category 8: UNUSUAL INPUTS (5) ---
    ConversationScenario("EC1", "unusual_input", "Empty-ish message", [
        {"role": "user", "content": "..."},
    ]),
    ConversationScenario("EC2", "unusual_input", "Only emoji", [
        {"role": "user", "content": "🔥🔥🔥"},
    ]),
    ConversationScenario("EC3", "unusual_input", "Bot detection attempt", [
        {"role": "user", "content": "Eres un bot?"},
    ]),
    ConversationScenario("EC4", "unusual_input", "Spam message", [
        {"role": "user", "content": "COMPRA AHORA EN MITIENDA.COM DESCUENTO 80% OFERTA LIMITADA!!!"},
    ]),
    ConversationScenario("EC5", "unusual_input", "Very long message", [
        {"role": "user", "content": (
            "Hola, te escribo porque llevo mucho tiempo siguiéndote en Instagram y la verdad es que "
            "tu contenido me ha ayudado muchísimo. Quería preguntarte sobre tu programa de mentoría "
            "porque tengo varias dudas. Primero, no sé si es para principiantes como yo, ya que nunca "
            "he trabajado con un coach antes. Segundo, me preocupa el tema del dinero porque ahora "
            "mismo no estoy en mi mejor momento económico. Y tercero, quería saber si hay algún tipo "
            "de garantía o período de prueba, porque me da un poco de miedo invertir y que no sea lo "
            "que esperaba. También me gustaría saber si das sesiones en persona o solo online, porque "
            "prefiero el contacto presencial. Gracias por tomarte el tiempo de leer esto!"
        )},
    ]),

    # --- Category 9: CASUAL / SOCIAL (5) ---
    ConversationScenario("CS1", "casual", "Compliment", [
        {"role": "user", "content": "Me encanta tu contenido, eres genial!"},
    ]),
    ConversationScenario("CS2", "casual", "Laugh", [
        {"role": "user", "content": "Jajaja tu último reel me mató"},
    ]),
    ConversationScenario("CS3", "casual", "Personal share", [
        {"role": "user", "content": "Hoy tuve un día horrible en el trabajo"},
    ]),
    ConversationScenario("CS4", "casual", "Thank you", [
        {"role": "user", "content": "Gracias por la info del otro día, me sirvió mucho"},
    ]),
    ConversationScenario("CS5", "casual", "Random chat", [
        {"role": "user", "content": "De dónde eres?"},
    ]),

    # --- Category 10: FOREIGN LANGUAGE / MIXED (5) ---
    ConversationScenario("FL1", "foreign", "English message", [
        {"role": "user", "content": "Hi! I saw your profile, do you speak English?"},
    ]),
    ConversationScenario("FL2", "foreign", "Portuguese", [
        {"role": "user", "content": "Olá! Vi o seu perfil e achei muito interessante"},
    ]),
    ConversationScenario("FL3", "foreign", "Italian", [
        {"role": "user", "content": "Ciao! Quanto costa il tuo programma?"},
    ]),
    ConversationScenario("FL4", "foreign", "Mixed Spanish-English", [
        {"role": "user", "content": "Hey, me gusta mucho tu content, very inspirational"},
    ]),
    ConversationScenario("FL5", "foreign", "French", [
        {"role": "user", "content": "Bonjour! Je suis intéressé par votre programme"},
    ]),
]


# =============================================================================
# TEST RUNNER
# =============================================================================

@dataclass
class TurnResult:
    """Result of processing a single turn."""
    scenario_id: str
    turn_index: int
    user_message: str
    bot_response: str
    intent: str
    confidence: float
    latency_ms: int
    success: bool
    error: str = ""


@dataclass
class ScenarioResult:
    """Result of running a complete scenario."""
    scenario_id: str
    category: str
    description: str
    turns: List[TurnResult] = field(default_factory=list)
    total_latency_ms: int = 0
    success: bool = True
    error: str = ""


@dataclass
class StressTestReport:
    """Final report for the stress test."""
    creator_id: str
    timestamp: str
    total_scenarios: int = 0
    passed: int = 0
    failed: int = 0
    total_turns: int = 0
    avg_latency_ms: float = 0
    p50_latency_ms: float = 0
    p95_latency_ms: float = 0
    max_latency_ms: float = 0
    by_category: Dict = field(default_factory=dict)
    failures: List[Dict] = field(default_factory=list)
    scenarios: List[ScenarioResult] = field(default_factory=list)


async def run_scenario(agent, scenario: ConversationScenario) -> ScenarioResult:
    """Run a single conversation scenario through the DM pipeline."""
    result = ScenarioResult(
        scenario_id=scenario.id,
        category=scenario.category,
        description=scenario.description,
    )

    # Build conversation history from prior turns
    history = []

    for i, turn in enumerate(scenario.turns):
        if turn["role"] == "assistant":
            # This is a pre-scripted assistant response (context setup)
            history.append(turn)
            continue

        # This is a user turn — process it through the pipeline
        user_msg = turn["content"]
        metadata = {
            "history": list(history),
            "conversation_id": f"stress_{scenario.id}",
            "turn_index": i,
        }

        start = time.monotonic()
        try:
            response = await agent.process_dm(
                message=user_msg,
                sender_id=f"stress_test_{scenario.id}",
                metadata=metadata,
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            bot_text = response.content if response else ""
            intent = response.intent if response else "error"
            confidence = response.confidence if response else 0.0

            turn_ok = bool(bot_text and len(bot_text.strip()) > 0)

            turn_result = TurnResult(
                scenario_id=scenario.id,
                turn_index=i,
                user_message=user_msg,
                bot_response=bot_text[:200],
                intent=intent,
                confidence=confidence,
                latency_ms=latency_ms,
                success=turn_ok,
                error="" if turn_ok else "empty_response",
            )

            # Add to history for next turn
            history.append({"role": "user", "content": user_msg})
            if bot_text:
                history.append({"role": "assistant", "content": bot_text})

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            turn_result = TurnResult(
                scenario_id=scenario.id,
                turn_index=i,
                user_message=user_msg,
                bot_response="",
                intent="error",
                confidence=0.0,
                latency_ms=latency_ms,
                success=False,
                error=str(e)[:200],
            )

        result.turns.append(turn_result)
        result.total_latency_ms += turn_result.latency_ms

        if not turn_result.success:
            result.success = False
            result.error = turn_result.error

    return result


async def run_stress_test(creator_id: str, parallel: int = 1) -> StressTestReport:
    """Run all 50 scenarios and produce a report."""
    from core.dm_agent_v2 import DMResponderAgent

    print(f"\nInitializing DM agent for '{creator_id}'...")
    agent = DMResponderAgent(creator_id)

    report = StressTestReport(
        creator_id=creator_id,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        total_scenarios=len(SCENARIOS),
    )

    all_latencies = []

    print(f"\nRunning {len(SCENARIOS)} scenarios (parallelism={parallel})...\n")

    # Run scenarios with controlled parallelism
    semaphore = asyncio.Semaphore(parallel)

    async def run_with_semaphore(scenario):
        async with semaphore:
            return await run_scenario(agent, scenario)

    tasks = [run_with_semaphore(s) for s in SCENARIOS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for i, res in enumerate(results):
        scenario = SCENARIOS[i]
        if isinstance(res, Exception):
            sr = ScenarioResult(
                scenario_id=scenario.id,
                category=scenario.category,
                description=scenario.description,
                success=False,
                error=str(res)[:200],
            )
        else:
            sr = res

        report.scenarios.append(sr)

        # Collect latencies from all turns
        for turn in sr.turns:
            all_latencies.append(turn.latency_ms)
            report.total_turns += 1

        if sr.success:
            report.passed += 1
            status = "PASS"
        else:
            report.failed += 1
            status = "FAIL"
            report.failures.append({
                "id": sr.scenario_id,
                "category": sr.category,
                "description": sr.description,
                "error": sr.error,
            })

        # Category aggregation
        cat = sr.category
        if cat not in report.by_category:
            report.by_category[cat] = {"total": 0, "passed": 0, "failed": 0, "avg_latency_ms": 0, "latencies": []}
        report.by_category[cat]["total"] += 1
        if sr.success:
            report.by_category[cat]["passed"] += 1
        else:
            report.by_category[cat]["failed"] += 1
        for turn in sr.turns:
            report.by_category[cat]["latencies"].append(turn.latency_ms)

        # Print progress
        last_turn = sr.turns[-1] if sr.turns else None
        latency_str = f"{sr.total_latency_ms}ms" if sr.total_latency_ms else "N/A"
        response_preview = last_turn.bot_response[:60] if last_turn else "N/A"
        print(f"  [{status}] {scenario.id} ({scenario.category}) — {latency_str} — {response_preview}")

    # Compute aggregate latency stats
    if all_latencies:
        all_latencies.sort()
        report.avg_latency_ms = round(sum(all_latencies) / len(all_latencies))
        report.p50_latency_ms = all_latencies[len(all_latencies) // 2]
        report.p95_latency_ms = all_latencies[int(len(all_latencies) * 0.95)]
        report.max_latency_ms = all_latencies[-1]

    # Clean up category latencies → avg
    for cat in report.by_category:
        lats = report.by_category[cat].pop("latencies", [])
        if lats:
            report.by_category[cat]["avg_latency_ms"] = round(sum(lats) / len(lats))

    return report


def print_summary(report: StressTestReport):
    """Print a human-readable summary."""
    print("\n" + "=" * 60)
    print("STRESS TEST RESULTS")
    print("=" * 60)
    print(f"  Creator:     {report.creator_id}")
    print(f"  Timestamp:   {report.timestamp}")
    print(f"  Scenarios:   {report.total_scenarios}")
    print(f"  Turns:       {report.total_turns}")
    print(f"  Passed:      {report.passed}/{report.total_scenarios}")
    print(f"  Failed:      {report.failed}/{report.total_scenarios}")
    print(f"  Pass Rate:   {report.passed / report.total_scenarios * 100:.1f}%")
    print()
    print(f"  Latency (avg):  {report.avg_latency_ms}ms")
    print(f"  Latency (p50):  {report.p50_latency_ms}ms")
    print(f"  Latency (p95):  {report.p95_latency_ms}ms")
    print(f"  Latency (max):  {report.max_latency_ms}ms")

    print("\n  By Category:")
    for cat, stats in sorted(report.by_category.items()):
        rate = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
        print(f"    {cat:20s}  {stats['passed']}/{stats['total']} ({rate:.0f}%)  avg={stats['avg_latency_ms']}ms")

    if report.failures:
        print(f"\n  Failures ({len(report.failures)}):")
        for f in report.failures:
            print(f"    [{f['id']}] {f['category']}: {f['description']} — {f['error'][:80]}")

    print("=" * 60)


def save_report(report: StressTestReport, output_dir: str = "stress_test_output"):
    """Save report as JSON."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{output_dir}/report_{ts}.json"

    # Convert to serializable dict
    data = {
        "creator_id": report.creator_id,
        "timestamp": report.timestamp,
        "summary": {
            "total_scenarios": report.total_scenarios,
            "passed": report.passed,
            "failed": report.failed,
            "pass_rate": round(report.passed / report.total_scenarios * 100, 1),
            "total_turns": report.total_turns,
            "avg_latency_ms": report.avg_latency_ms,
            "p50_latency_ms": report.p50_latency_ms,
            "p95_latency_ms": report.p95_latency_ms,
            "max_latency_ms": report.max_latency_ms,
        },
        "by_category": report.by_category,
        "failures": report.failures,
        "scenarios": [
            {
                "id": s.scenario_id,
                "category": s.category,
                "description": s.description,
                "success": s.success,
                "total_latency_ms": s.total_latency_ms,
                "error": s.error,
                "turns": [
                    {
                        "turn": t.turn_index,
                        "user": t.user_message[:100],
                        "bot": t.bot_response[:200],
                        "intent": t.intent,
                        "confidence": t.confidence,
                        "latency_ms": t.latency_ms,
                        "success": t.success,
                        "error": t.error,
                    }
                    for t in s.turns
                ],
            }
            for s in report.scenarios
        ],
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n  Report saved to: {filename}")
    return filename


async def main():
    parser = argparse.ArgumentParser(description="50-Conversation Stress Test")
    parser.add_argument("--creator", default="stefano_bonanno", help="Creator ID to test")
    parser.add_argument("--parallel", type=int, default=3, help="Max concurrent scenarios")
    parser.add_argument("--output", default="stress_test_output", help="Output directory")
    args = parser.parse_args()

    report = await run_stress_test(args.creator, parallel=args.parallel)
    print_summary(report)
    save_report(report, args.output)


if __name__ == "__main__":
    asyncio.run(main())
