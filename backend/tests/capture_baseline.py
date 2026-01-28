"""
Captura respuestas del bot ACTUAL para comparar después del refactor.
FASE 0: Preparación del refactor de arquitectura
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Añadir backend al path
sys.path.insert(0, "/Users/manelbertranluque/Desktop/CLONNECT/backend")

# Cargar variables de entorno
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/Users/manelbertranluque/Desktop/CLONNECT/backend/.env.local")

# Casos de prueba
TEST_CASES = [
    {
        "id": "silvia_b2b",
        "name": "Silvia (B2B)",
        "message": "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes con grupos de estudiantes Erasmus. Queríamos ver si podemos organizar algo para febrero.",
        "expected_issue": "No debería decir 'frustrado'",
    },
    {
        "id": "frustrado",
        "name": "Usuario frustrado",
        "message": "Ya te dije 3 veces que quiero el precio del FitPack, ¿me lo puedes dar o no?",
        "expected_issue": "Debería dar el precio, no solo disculparse",
    },
    {
        "id": "booking",
        "name": "Booking",
        "message": "Quiero reservar una sesión de coaching contigo",
        "expected_issue": "Debería incluir link de reserva",
    },
    {
        "id": "precio",
        "name": "Precio",
        "message": "¿Cuánto cuesta el FitPack Challenge?",
        "expected_issue": "Debería dar precio correcto",
    },
    {
        "id": "anti_alucinacion",
        "name": "Anti-alucinación",
        "message": "¿Cuánto cuesta el retiro de yoga en Bali?",
        "expected_issue": "NO debería inventar precio",
    },
    {
        "id": "escalacion",
        "name": "Escalación",
        "message": "Quiero hablar con Stefano directamente, no con un bot",
        "expected_issue": "Debería escalar",
    },
    {
        "id": "lead_magnet",
        "name": "Lead magnet",
        "message": "¿Tienes algo gratis para empezar? No quiero comprar todavía",
        "expected_issue": "Debería dar link gratis si existe",
    },
]


async def capture_baseline():
    """Captura respuestas del bot actual."""

    print("=" * 60)
    print("CAPTURA DE BASELINE - Respuestas ANTES del refactor")
    print("=" * 60)

    results = {
        "captured_at": datetime.now().isoformat(),
        "branch": "main (antes del refactor)",
        "cases": [],
    }

    # Intentar importar el agente
    try:
        from core.dm_agent_v2 import DMResponderAgent  # noqa: F401

        print("✅ DMResponderAgent importado correctamente")
    except Exception as e:
        print(f"❌ Error importando DMResponderAgent: {e}")
        print("\nCreando baseline manual con respuestas placeholder...")

        # Si no podemos importar, crear baseline manual
        for case in TEST_CASES:
            results["cases"].append(
                {
                    "id": case["id"],
                    "name": case["name"],
                    "input": case["message"],
                    "output": "[PENDIENTE - Ejecutar manualmente con el bot]",
                    "escalated": False,
                    "expected_issue": case["expected_issue"],
                }
            )

        save_results(results)
        return results

    # Intentar crear el agente
    try:
        # Usar un creator_id de prueba
        creator_id = os.getenv("TEST_CREATOR_ID", "stefano")
        agent = DMResponderAgent(creator_id=creator_id)
        print(f"✅ Agente creado para creator: {creator_id}")
    except Exception as e:
        print(f"❌ Error creando agente: {e}")

        # Crear baseline con placeholders
        for case in TEST_CASES:
            results["cases"].append(
                {
                    "id": case["id"],
                    "name": case["name"],
                    "input": case["message"],
                    "output": f"[ERROR: {str(e)[:100]}]",
                    "escalated": False,
                    "expected_issue": case["expected_issue"],
                }
            )

        save_results(results)
        return results

    # Procesar cada caso de prueba
    for i, case in enumerate(TEST_CASES, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/7] {case['name']}")
        print(f"{'='*60}")
        print(f"INPUT: {case['message']}")

        try:
            # Crear un sender_id único para cada caso
            sender_id = f"baseline_test_{case['id']}"

            # Procesar mensaje
            response = await agent.process_dm(
                sender_id=sender_id,
                message_text=case["message"],
                message_id=f"test_{i}",
                username=f"test_{case['id']}",
            )

            if response:
                response_text = response.response_text
                escalated = getattr(response, "escalate_to_human", False)
            else:
                response_text = "ERROR: No response"
                escalated = False

        except Exception as e:
            response_text = f"ERROR: {str(e)}"
            escalated = False

        print(
            f"OUTPUT: {response_text[:200]}..."
            if len(str(response_text)) > 200
            else f"OUTPUT: {response_text}"
        )
        print(f"ESCALATED: {escalated}")

        results["cases"].append(
            {
                "id": case["id"],
                "name": case["name"],
                "input": case["message"],
                "output": response_text,
                "escalated": escalated,
                "expected_issue": case["expected_issue"],
            }
        )

    save_results(results)
    return results


def save_results(results):
    """Guardar resultados en JSON y Markdown."""

    # Guardar JSON
    output_path = Path("/Users/manelbertranluque/Desktop/CLONNECT/docs/baseline_responses.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"✅ Baseline JSON guardado en: {output_path}")

    # Crear versión markdown
    md_path = Path("/Users/manelbertranluque/Desktop/CLONNECT/docs/baseline_responses.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# BASELINE - Respuestas ANTES del refactor\n\n")
        f.write(f"**Fecha:** {results['captured_at']}\n")
        f.write(f"**Branch:** {results['branch']}\n\n")
        f.write("---\n\n")

        for case in results["cases"]:
            f.write(f"## {case['name']}\n\n")
            f.write(f"**Input:**\n```\n{case['input']}\n```\n\n")
            f.write(f"**Output:**\n```\n{case['output']}\n```\n\n")
            f.write(f"**Escalated:** {case['escalated']}\n\n")
            f.write(f"**Problema esperado:** {case['expected_issue']}\n\n")
            f.write("---\n\n")

    print(f"✅ Baseline Markdown guardado en: {md_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(capture_baseline())
