#!/usr/bin/env python3
"""Debug test - Ver exactamente qué detecta el bot"""
import asyncio
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()

from core.dm_agent_v2 import DMResponderAgent

# Test sarcasm patterns manually
sarcasm_patterns = [
    r'como si', r'seguro que s[íi]', r'ya ver[áa]s',
    r'aj[áa]', r'ya ya', r'qu[ée] gracioso',
    r's[íi].*(?:claro|seguro).*no', r'claro.*como si',
    r'obvio.*que no', r'seguro.*(?:vas|puedes|sabes)',
    r'otra vez.*(?:igual|lo mismo)',
]

msg1 = "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes con grupos de estudiantes Erasmus"

print("=== TEST PATRONES SARCASMO ===")
print(f"Mensaje: {msg1}")
print()

for pattern in sarcasm_patterns:
    match = re.search(pattern, msg1.lower())
    if match:
        print(f"❌ MATCH: '{pattern}' -> '{match.group()}'")
    else:
        print(f"✓ No match: '{pattern}'")

print()
print("=== TEST COMPLETO DEL BOT ===")

async def test():
    agent = DMResponderAgent(creator_id="stefano_bonanno")

    # Check what _detect_conversation_continuation returns
    print("\n--- Checking conversation continuation detection ---")

    # Simulate a follower with no history
    from core.memory import FollowerMemory
    follower = FollowerMemory(
        follower_id="test_debug",
        creator_id="stefano_bonanno",
        platform="instagram"
    )

    # Check the method
    result = agent._detect_conversation_continuation(msg1, follower)
    print(f"_detect_conversation_continuation result: {result}")

    # Check intent classification
    print("\n--- Checking intent classification ---")
    intent, confidence = agent._classify_intent(msg1, [])
    print(f"Intent: {intent.value}, Confidence: {confidence}")

    # Full process
    print("\n--- Full process_dm ---")
    response = await agent.process_dm(
        sender_id="test_debug",
        message_text=msg1,
        message_id="test_1",
        username="bamos_barcelona_mobility"
    )

    print(f"Response: {response.response_text}")
    print(f"Intent: {response.intent}")
    print(f"Action: {response.action_taken}")
    print(f"Metadata: {response.metadata}")

asyncio.run(test())
