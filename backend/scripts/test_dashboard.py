#!/usr/bin/env python3
"""
Test script para verificar que la API y Dashboard funcionan correctamente.
Ejecutar con: python scripts/test_dashboard.py
"""

import asyncio
import sys
import os

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dm_agent import DMResponderAgent, Intent


async def test_dm_agent():
    """Test del DM Agent"""
    print("\n" + "="*50)
    print("🧪 TEST: DM Agent")
    print("="*50)

    try:
        agent = DMResponderAgent(creator_id="manel")
        print(f"✅ Agent creado para: {agent.creator_id}")
        print(f"✅ Productos cargados: {len(agent.products)}")

        # Test clasificación de intents
        test_messages = [
            ("Hola!", Intent.GREETING),
            ("Quiero comprar el curso", Intent.INTEREST_STRONG),
            ("Es muy caro", Intent.OBJECTION_PRICE),
            ("No tengo tiempo", Intent.OBJECTION_TIME),
            ("Luego te escribo", Intent.OBJECTION_LATER),
            ("¿Funciona de verdad?", Intent.OBJECTION_WORKS),
            ("No es para mí, soy principiante", Intent.OBJECTION_NOT_FOR_ME),
            ("Es muy complicado", Intent.OBJECTION_COMPLICATED),
            ("Ya tengo algo similar", Intent.OBJECTION_ALREADY_HAVE),
        ]

        print("\n📋 Test de clasificación de intents:")
        for msg, expected in test_messages:
            intent, confidence = agent._classify_intent(msg)
            status = "✅" if intent == expected else "❌"
            print(f"  {status} '{msg}' → {intent.value} ({confidence:.0%})")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


async def test_process_dm():
    """Test de procesamiento de DM"""
    print("\n" + "="*50)
    print("🧪 TEST: Procesar DM")
    print("="*50)

    try:
        agent = DMResponderAgent(creator_id="manel")

        # Simular conversación
        test_conversation = [
            "Hola! Me encanta tu contenido",
            "Tienes algún curso de automatización?",
            "Cuánto cuesta?",
            "Es un poco caro para mí",
            "Quiero comprarlo!"
        ]

        print("\n💬 Simulando conversación:")
        for msg in test_conversation:
            print(f"\n👤 Usuario: {msg}")
            response = await agent.process_dm(
                sender_id="test_user_123",
                message_text=msg,
                username="test_user"
            )
            print(f"🤖 Bot: {response.response_text}")
            print(f"   Intent: {response.intent.value} | Producto: {response.product_mentioned}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_metrics():
    """Test de métricas y conversaciones"""
    print("\n" + "="*50)
    print("🧪 TEST: Métricas y Conversaciones")
    print("="*50)

    try:
        agent = DMResponderAgent(creator_id="manel")

        # Test get_metrics
        metrics = await agent.get_metrics()
        print(f"\n📊 Métricas:")
        print(f"  - Total mensajes: {metrics['total_messages']}")
        print(f"  - Total seguidores: {metrics['total_followers']}")
        print(f"  - Leads: {metrics['leads']}")
        print(f"  - Clientes: {metrics['customers']}")
        print(f"  - Alta intención: {metrics['high_intent_followers']}")

        # Test get_all_conversations
        conversations = await agent.get_all_conversations(limit=5)
        print(f"\n💬 Conversaciones recientes: {len(conversations)}")
        for conv in conversations[:3]:
            print(f"  - {conv.get('username', 'N/A')}: {conv.get('total_messages', 0)} msgs")

        # Test get_leads
        leads = await agent.get_leads()
        print(f"\n🎯 Leads: {len(leads)}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_endpoints():
    """Test de endpoints de la API (requiere API corriendo)"""
    print("\n" + "="*50)
    print("🧪 TEST: API Endpoints (requiere API corriendo)")
    print("="*50)

    try:
        import requests
        API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

        endpoints = [
            ("GET", "/health"),
            ("GET", "/creator/manel/products"),
            ("GET", "/dm/metrics/manel"),
            ("GET", "/dashboard/manel/overview"),
        ]

        print(f"\n🌐 Testing API en {API_URL}")

        for method, endpoint in endpoints:
            try:
                if method == "GET":
                    resp = requests.get(f"{API_URL}{endpoint}", timeout=5)
                status = "✅" if resp.ok else "❌"
                print(f"  {status} {method} {endpoint} → {resp.status_code}")
            except requests.exceptions.ConnectionError:
                print(f"  ⚠️ {method} {endpoint} → API no disponible")
                return False

        return True

    except ImportError:
        print("  ⚠️ requests no instalado, saltando test de API")
        return True


async def main():
    """Ejecutar todos los tests"""
    print("\n" + "🚀 CLONNECT DASHBOARD TEST SUITE ".center(50, "="))

    results = []

    # Test DM Agent
    results.append(("DM Agent", await test_dm_agent()))

    # Test Process DM
    results.append(("Process DM", await test_process_dm()))

    # Test Metrics
    results.append(("Metrics", await test_metrics()))

    # Test API (opcional)
    results.append(("API Endpoints", await test_api_endpoints()))

    # Resumen
    print("\n" + "="*50)
    print("📋 RESUMEN")
    print("="*50)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")

    print(f"\n{'='*50}")
    print(f"Total: {passed}/{total} tests pasados")

    if passed == total:
        print("🎉 ¡Todos los tests pasaron!")
        return 0
    else:
        print("⚠️ Algunos tests fallaron")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
