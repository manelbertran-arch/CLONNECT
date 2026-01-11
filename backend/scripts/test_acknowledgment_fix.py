#!/usr/bin/env python3
"""
Test del fix de ACKNOWLEDGMENT - Verificar que "Si" pasa por el LLM con contexto.

Este script simula la conversación:
1. User: "Hola, me interesa saber sobre tus servicios de coaching"
2. Bot: [respuesta]
3. User: "Para bajar la ansiedad"
4. Bot: [respuesta - debería preguntar si quiere saber más]
5. User: "Si"
6. Bot: [VERIFICAR - NO debe decir "¿En qué más puedo ayudarte?"]

Ejecutar: python scripts/test_acknowledgment_fix.py
"""

import asyncio
import logging
import sys
import os

# Añadir backend al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configurar logging para ver el flujo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(message)s',
    datefmt='%H:%M:%S'
)

# Silenciar logs muy verbosos
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)

logger = logging.getLogger('test_acknowledgment')


async def test_acknowledgment_flow():
    """Test del flujo de ACKNOWLEDGMENT con contexto."""

    print("\n" + "="*80)
    print("TEST: ACKNOWLEDGMENT FIX - Verificar que 'Si' usa contexto")
    print("="*80 + "\n")

    # Importar después de configurar el path
    from core.dm_agent import DMResponderAgent

    # Usar creator "manel" que tiene configuración
    creator_id = "manel"
    agent = DMResponderAgent(creator_id=creator_id)

    # Forzar bot activo para el test (mockear is_bot_active)
    agent.config_manager.is_bot_active = lambda x: True

    # ID único para este test
    test_follower_id = f"test_ack_{int(asyncio.get_event_loop().time())}"

    # Conversación de test
    conversation = [
        {
            "message": "Hola, me interesa saber sobre tus servicios de coaching",
            "expected_not_contains": ["¿En qué más puedo ayudarte?"],
            "description": "Saludo inicial con interés"
        },
        {
            "message": "Para bajar la ansiedad",
            "expected_not_contains": ["¿En qué más puedo ayudarte?"],
            "description": "Usuario especifica su necesidad"
        },
        {
            "message": "Si",
            "expected_not_contains": ["¿En qué más puedo ayudarte?", "¿En qué puedo ayudarte?"],
            "expected_context": ["ansiedad", "coaching", "programa", "ayud"],  # Debería mencionar algo del contexto
            "description": "CRÍTICO: Usuario confirma - NO debe ignorar contexto"
        }
    ]

    results = []

    for i, turn in enumerate(conversation, 1):
        print(f"\n{'─'*80}")
        print(f"TURNO {i}: {turn['description']}")
        print(f"{'─'*80}")
        print(f"👤 Usuario: {turn['message']}")

        try:
            # Procesar mensaje (el método es process_dm)
            response = await agent.process_dm(
                sender_id=test_follower_id,
                message_text=turn['message'],
                username="test_user"
            )

            response_text = response.response_text if hasattr(response, 'response_text') else str(response)
            intent = response.intent.value if hasattr(response, 'intent') else "unknown"

            print(f"🤖 Bot: {response_text}")
            print(f"   Intent: {intent}")

            # Verificar que NO contiene frases prohibidas
            failed_checks = []
            for forbidden in turn.get('expected_not_contains', []):
                if forbidden.lower() in response_text.lower():
                    failed_checks.append(f"❌ CONTIENE FRASE PROHIBIDA: '{forbidden}'")

            # Verificar contexto (solo para el mensaje "Si")
            if turn.get('expected_context'):
                has_context = any(ctx.lower() in response_text.lower() for ctx in turn['expected_context'])
                if not has_context:
                    failed_checks.append(f"⚠️ NO MENCIONA CONTEXTO (esperado alguno de: {turn['expected_context']})")

            # Resultado del turno
            if failed_checks:
                print(f"\n   🔴 FALLOS:")
                for fail in failed_checks:
                    print(f"      {fail}")
                results.append({"turn": i, "status": "FAIL", "issues": failed_checks})
            else:
                print(f"\n   ✅ OK")
                results.append({"turn": i, "status": "PASS"})

        except Exception as e:
            print(f"🔴 ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append({"turn": i, "status": "ERROR", "error": str(e)})

    # Resumen final
    print("\n" + "="*80)
    print("RESUMEN DEL TEST")
    print("="*80)

    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    errors = sum(1 for r in results if r['status'] == 'ERROR')

    print(f"\n✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"🔴 Errors: {errors}")

    # El test crítico es el turno 3 (el "Si")
    turno_si = next((r for r in results if r['turn'] == 3), None)
    if turno_si:
        print(f"\n{'='*80}")
        if turno_si['status'] == 'PASS':
            print("🎉 TEST CRÍTICO PASADO: 'Si' recibe respuesta contextual")
        else:
            print("💥 TEST CRÍTICO FALLIDO: 'Si' aún recibe respuesta genérica")
            if 'issues' in turno_si:
                for issue in turno_si['issues']:
                    print(f"   {issue}")
        print("="*80)

    return all(r['status'] == 'PASS' for r in results)


async def test_acknowledgment_classification():
    """Test adicional: verificar que la clasificación de intent funciona."""

    print("\n" + "="*80)
    print("TEST: Clasificación de ACKNOWLEDGMENT")
    print("="*80 + "\n")

    from core.dm_agent import DMResponderAgent, Intent

    agent = DMResponderAgent(creator_id="test")

    test_cases = [
        ("Si", Intent.ACKNOWLEDGMENT),
        ("Vale", Intent.ACKNOWLEDGMENT),
        ("Ok", Intent.ACKNOWLEDGMENT),
        ("Sí, me interesa", Intent.INTEREST_SOFT),  # Esto debería ser INTEREST_SOFT
        ("Quiero comprar", Intent.INTEREST_STRONG),
    ]

    for message, expected_intent in test_cases:
        intent, confidence = agent._classify_intent(message)
        status = "✅" if intent == expected_intent else "❌"
        print(f"{status} '{message}' → {intent.value} (esperado: {expected_intent.value})")


if __name__ == "__main__":
    print("\n" + "🧪"*40)
    print("INICIANDO TEST DE ACKNOWLEDGMENT FIX")
    print("🧪"*40)

    # Test principal
    success = asyncio.run(test_acknowledgment_flow())

    # Test de clasificación
    asyncio.run(test_acknowledgment_classification())

    # Exit code
    sys.exit(0 if success else 1)
