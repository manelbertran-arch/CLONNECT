#!/usr/bin/env python3
"""
Test de mensaje real - Simula mensajes de @bamos_barcelona_mobility a @fitpack_global
SIN enviar nada a Instagram, solo muestra la respuesta generada.
"""
import asyncio
import sys
import os

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()

print(f"DATABASE_URL loaded: {'Yes' if os.getenv('DATABASE_URL') else 'No'}")

from core.dm_agent import DMResponderAgent

async def test_real_messages():
    """Test con mensajes reales de @bamos_barcelona_mobility"""

    print("=" * 70)
    print("🧪 TEST BOT - Mensajes reales de @bamos_barcelona_mobility")
    print("   Creador: stefano_bonanno (el que tiene productos/FAQs/RAG)")
    print("=" * 70)

    # Inicializar el agente para stefano_bonanno (el que tiene los datos)
    agent = DMResponderAgent(creator_id="stefano_bonanno")

    # Mensajes reales del usuario
    messages = [
        "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes con grupos de estudiantes Erasmus",
        "Les escribo en esta ocasión porque tenemos un grupo de estudiantes del área Sports and fitness que llegan de Irlanda en febrero, que quizás podrían interesarles"
    ]

    # Usar un sender_id FRESCO para simular primera interacción real
    import time
    sender_id = f"ig_bamos_test_{int(time.time())}"
    username = "bamos_barcelona_mobility"

    for i, message in enumerate(messages, 1):
        print(f"\n{'─' * 70}")
        print(f"📩 MENSAJE {i}:")
        print(f"   De: @{username}")
        print(f"   Texto: {message}")
        print(f"{'─' * 70}")

        try:
            # Procesar el mensaje
            response = await agent.process_dm(
                sender_id=sender_id,
                message_text=message,
                message_id=f"test_msg_{i}",
                username=username
            )

            print(f"\n🤖 RESPUESTA DEL BOT:")
            print(f"   {response.response_text}")
            print(f"\n📊 METADATA:")
            print(f"   Intent: {response.intent.value if hasattr(response.intent, 'value') else response.intent}")
            print(f"   Confianza: {response.confidence:.0%}")
            print(f"   Acción: {response.action_taken}")
            print(f"   Producto mencionado: {response.product_mentioned or 'Ninguno'}")
            print(f"   Escalar a humano: {'Sí' if response.escalate_to_human else 'No'}")

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'=' * 70}")
    print("✅ TEST COMPLETADO - No se envió nada a Instagram")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_real_messages())
