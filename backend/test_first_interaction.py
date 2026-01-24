#!/usr/bin/env python3
"""Test específico de primera interacción"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from core.dm_agent import (
    DMResponderAgent,
    extract_name_from_message,
    detect_b2b_context,
    is_first_interaction,
    build_bot_introduction
)
from core.memory import MemoryStore

msg1 = "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes con grupos de estudiantes Erasmus"

print("=" * 70)
print("🔍 TEST PRIMERA INTERACCIÓN")
print("=" * 70)

# 1. Test extracción de nombre
print("\n1. Extracción de nombre:")
name = extract_name_from_message(msg1)
print(f"   Mensaje: {msg1}")
print(f"   Nombre extraído: {name}")

# 2. Test detección B2B
print("\n2. Detección de contexto B2B:")
b2b = detect_b2b_context(msg1)
print(f"   Contexto B2B: {b2b}")

# 3. Test is_first_interaction con follower nuevo
print("\n3. Test is_first_interaction:")
from core.memory import FollowerMemory
new_follower = FollowerMemory(follower_id="test_new_user", creator_id="test")
new_follower.last_messages = []
new_follower.total_messages = 0
print(f"   Follower nuevo (0 msgs): {is_first_interaction(new_follower)}")

follower_with_msgs = FollowerMemory(follower_id="test_existing", creator_id="test")
follower_with_msgs.last_messages = [{"role": "assistant", "content": "Hola!"}]
follower_with_msgs.total_messages = 2
print(f"   Follower con msgs (2 msgs): {is_first_interaction(follower_with_msgs)}")

# 4. Test build_bot_introduction
print("\n4. Test mensaje de presentación:")
intro = build_bot_introduction(
    creator_name="Stefano Bonanno",
    user_name="Silvia",
    b2b_context="previous_work",
    dialect="neutral"
)
print(f"   Mensaje:\n{intro}")

# 5. Test completo con memoria limpia
print("\n" + "=" * 70)
print("5. TEST COMPLETO CON MEMORIA LIMPIA")
print("=" * 70)

async def test_fresh():
    # Limpiar memoria para este test
    memory = MemoryStore()

    # Asegurar que no existe memoria previa
    test_sender = "ig_test_silvia_fresh_123"

    agent = DMResponderAgent(creator_id="stefano_bonanno")

    # Forzar limpieza de memoria para este sender
    try:
        # Intentar borrar memoria existente si hay
        await memory.delete(agent.creator_id, test_sender)
    except:
        pass

    response = await agent.process_dm(
        sender_id=test_sender,
        message_text=msg1,
        message_id="test_fresh_1",
        username="bamos_barcelona_mobility"
    )

    print(f"\n   Respuesta: {response.response_text}")
    print(f"   Intent: {response.intent}")
    print(f"   Acción: {response.action_taken}")
    print(f"   Escalar: {response.escalate_to_human}")
    print(f"   Metadata: {response.metadata}")

asyncio.run(test_fresh())

print("\n" + "=" * 70)
