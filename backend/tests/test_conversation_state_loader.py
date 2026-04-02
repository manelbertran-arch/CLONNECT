"""
Functional tests for Sistema #6: Conversation State Loader.

Tests the 4 bug fixes:
- BUG-CS-01: History limit reduced from 20 to 10
- BUG-CS-02: Media placeholders replaced with descriptive text
- BUG-CS-03: Audio transcriptions stored in DB content
- BUG-CS-06: ConversationState universal (no health/fitness hardcoded keywords)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dm.helpers import (
    _clean_media_placeholders,
    get_history_from_follower,
    get_history_from_db,
)
from core.conversation_state import ConversationState, StateManager, ConversationPhase

results = []


def test(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def run_tests():
    print("\n" + "=" * 70)
    print("FUNCTIONAL TESTS: Sistema #6 — Conversation State Loader")
    print("=" * 70)

    # ─── TEST 1: First message — empty history graceful ───
    print("\n--- Test 1: First message (empty history) ---")

    class MockFollower:
        last_messages = []

    class MockAgent:
        creator_id = "test_creator"

    history = get_history_from_follower(MockAgent(), MockFollower())
    test("1. Empty history returns []", history == [], f"got {history}")

    # ─── TEST 2: Lead with 3 previous messages ───
    print("\n--- Test 2: Lead with 3 messages ---")

    class MockFollower3:
        last_messages = [
            {"role": "user", "content": "Hola!"},
            {"role": "assistant", "content": "Hey! Que tal?"},
            {"role": "user", "content": "Bien, quiero saber mas"},
        ]

    history = get_history_from_follower(MockAgent(), MockFollower3())
    test("2. 3 messages all loaded", len(history) == 3, f"got {len(history)}")

    # ─── TEST 3: Lead with 100+ messages — only last 10 loaded ───
    print("\n--- Test 3: Lead with 100+ messages (BUG-CS-01) ---")

    class MockFollower100:
        last_messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg_{i}"}
            for i in range(100)
        ]

    history = get_history_from_follower(MockAgent(), MockFollower100())
    test(
        "3. 100 messages → only last 10 loaded",
        len(history) == 10,
        f"got {len(history)}",
    )
    # Verify we got the LAST 10, not the first 10
    test(
        "3b. Last 10 are the newest ones",
        history[0]["content"] == "msg_90",
        f"first={history[0]['content']}",
    )

    # ─── TEST 4: Media messages in history (BUG-CS-02) ───
    print("\n--- Test 4: Media placeholders cleaned (BUG-CS-02) ---")
    media_history = [
        {"role": "user", "content": "Sent a photo"},
        {"role": "user", "content": "Hola que tal"},
        {"role": "user", "content": "Sent a voice message"},
        {"role": "user", "content": "Shared a reel"},
        {"role": "user", "content": "[sticker]"},
        {"role": "user", "content": "Shared a story"},
        {"role": "assistant", "content": "Sent a photo"},  # assistant — should NOT be cleaned
    ]
    cleaned = _clean_media_placeholders(media_history)
    test(
        "4a. Photo placeholder → descriptive",
        cleaned[0]["content"] == "[Lead envio una foto]",
        f"got '{cleaned[0]['content']}'",
    )
    test(
        "4b. Normal text untouched",
        cleaned[1]["content"] == "Hola que tal",
        f"got '{cleaned[1]['content']}'",
    )
    test(
        "4c. Voice message → audio",
        cleaned[2]["content"] == "[Lead envio un audio]",
        f"got '{cleaned[2]['content']}'",
    )
    test(
        "4d. Reel → video",
        cleaned[3]["content"] == "[Lead envio un video]",
        f"got '{cleaned[3]['content']}'",
    )
    test(
        "4e. Sticker → sticker",
        cleaned[4]["content"] == "[Lead envio un sticker]",
        f"got '{cleaned[4]['content']}'",
    )
    test(
        "4f. Story → story",
        cleaned[5]["content"] == "[Lead compartio una story]",
        f"got '{cleaned[5]['content']}'",
    )
    test(
        "4g. Assistant message NOT cleaned",
        cleaned[6]["content"] == "Sent a photo",
        f"got '{cleaned[6]['content']}'",
    )

    # ─── TEST 5: Conversation in Catalan preserves language ───
    print("\n--- Test 5: Catalan conversation preserved ---")

    class MockFollowerCat:
        last_messages = [
            {"role": "user", "content": "Hola! Vull saber mes sobre les teves classes"},
            {"role": "assistant", "content": "Ei! Que vols saber exactament?"},
        ]

    history = get_history_from_follower(MockAgent(), MockFollowerCat())
    test(
        "5. Catalan text preserved",
        "Vull saber mes" in history[0]["content"],
        f"got '{history[0]['content'][:50]}'",
    )

    # ─── TEST 6: Conversation in Spanish preserves language ───
    print("\n--- Test 6: Spanish conversation preserved ---")

    class MockFollowerES:
        last_messages = [
            {"role": "user", "content": "Me interesa mucho tu programa"},
        ]

    history = get_history_from_follower(MockAgent(), MockFollowerES())
    test(
        "6. Spanish text preserved",
        "Me interesa mucho" in history[0]["content"],
    )

    # ─── TEST 7: Price context available within window ───
    print("\n--- Test 7: Price question 5 messages ago (within window) ---")

    class MockFollowerPrice:
        last_messages = [
            {"role": "user", "content": "Cuanto cuesta el programa?"},
            {"role": "assistant", "content": "El programa cuesta 49 euros"},
            {"role": "user", "content": "Ok interesante"},
            {"role": "assistant", "content": "Te apuntas?"},
            {"role": "user", "content": "Dejame pensarlo"},
            {"role": "assistant", "content": "Claro, sin prisa"},
            {"role": "user", "content": "Ya me he decidido"},
        ]

    history = get_history_from_follower(MockAgent(), MockFollowerPrice())
    all_content = " ".join(m["content"] for m in history)
    test(
        "7. Price context still visible in history",
        "49 euros" in all_content,
        f"history has {len(history)} msgs",
    )

    # ─── TEST 8: Frustration context carries forward ───
    print("\n--- Test 8: Frustration carries forward ---")

    class MockFollowerFrustrated:
        last_messages = [
            {"role": "user", "content": "No me has contestado en 3 dias!!!"},
            {"role": "assistant", "content": "Perdon, he estado liada"},
            {"role": "user", "content": "Ya pero es que siempre igual"},
            {"role": "assistant", "content": "Tienes razon, lo siento mucho"},
            {"role": "user", "content": "Bueno vale"},
        ]

    history = get_history_from_follower(MockAgent(), MockFollowerFrustrated())
    all_content = " ".join(m["content"] for m in history)
    test(
        "8. Frustration context in history",
        "No me has contestado" in all_content,
    )

    # ─── TEST 9: Two leads no cross-contamination ───
    print("\n--- Test 9: Two leads isolated ---")

    class MockFollowerA:
        last_messages = [{"role": "user", "content": "Soy lead A, me llamo Maria"}]

    class MockFollowerB:
        last_messages = [{"role": "user", "content": "Soy lead B, me llamo Juan"}]

    history_a = get_history_from_follower(MockAgent(), MockFollowerA())
    history_b = get_history_from_follower(MockAgent(), MockFollowerB())
    test(
        "9a. Lead A has own content",
        "Maria" in history_a[0]["content"],
    )
    test(
        "9b. Lead B has own content",
        "Juan" in history_b[0]["content"],
    )
    test(
        "9c. No cross-contamination",
        "Juan" not in history_a[0]["content"]
        and "Maria" not in history_b[0]["content"],
    )

    # ─── TEST 10: Audio transcription handling (BUG-CS-03) ───
    print("\n--- Test 10: Audio transcription in history ---")
    # Simulates what happens when audio is transcribed and stored properly
    audio_history = [
        {"role": "user", "content": "[\U0001f3a4 Audio]: Hola quiero saber los precios"},
        {"role": "assistant", "content": "Claro! Te cuento..."},
    ]
    cleaned = _clean_media_placeholders(audio_history)
    test(
        "10a. Transcribed audio preserved (not cleaned)",
        "Hola quiero saber los precios" in cleaned[0]["content"],
        f"got '{cleaned[0]['content'][:60]}'",
    )
    # Raw placeholder should be cleaned
    raw_audio = [{"role": "user", "content": "[audio]"}]
    cleaned_raw = _clean_media_placeholders(raw_audio)
    test(
        "10b. Raw [audio] placeholder cleaned",
        cleaned_raw[0]["content"] == "[Lead envio un audio]",
        f"got '{cleaned_raw[0]['content']}'",
    )

    # ─── TEST 11: ConversationState universal (BUG-CS-06) ───
    print("\n--- Test 11: ConversationState universal extraction (BUG-CS-06) ---")
    sm = StateManager()

    # Test with non-fitness message (yoga teacher, Catalan)
    state = ConversationState(follower_id="test1", creator_id="yoga_teacher")
    sm._extract_context(state, "Tinc 35 anys i vull apuntar-me a les teves classes")
    test(
        "11a. Age extracted from Catalan",
        state.context.situation is not None and "35" in state.context.situation,
        f"situation='{state.context.situation}'",
    )

    # Test with English message
    state2 = ConversationState(follower_id="test2", creator_id="english_coach")
    sm._extract_context(state2, "I'm 28 years old and I want to improve my skills")
    test(
        "11b. Age extracted from English",
        state2.context.situation is not None and "28" in state2.context.situation,
        f"situation='{state2.context.situation}'",
    )

    # Test goal extraction (generic, not health-specific)
    state3 = ConversationState(follower_id="test3", creator_id="art_creator")
    sm._extract_context(state3, "Quiero aprender a pintar acuarelas")
    test(
        "11c. Goal extracted generically",
        state3.context.goal is not None and "pintar" in state3.context.goal,
        f"goal='{state3.context.goal}'",
    )

    # Test name extraction
    state4 = ConversationState(follower_id="test4", creator_id="any_creator")
    sm._extract_context(state4, "Me llamo Laura y estoy interesada")
    test(
        "11d. Name extracted",
        state4.context.name == "Laura",
        f"name='{state4.context.name}'",
    )

    # Test that random tech message doesn't crash or extract garbage
    state5 = ConversationState(follower_id="test5", creator_id="tech_creator")
    sm._extract_context(state5, "Can you help me with my React project?")
    test(
        "11e. Non-matching message doesn't crash",
        True,  # If we get here, no crash
        f"situation='{state5.context.situation}', goal='{state5.context.goal}'",
    )

    # ─── SUMMARY ───
    print("\n" + "=" * 70)
    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"RESULTS: {passed}/{total} passed")
    if passed == total:
        print("ALL TESTS PASSED")
    else:
        failed = [name for name, p in results if not p]
        print(f"FAILED: {', '.join(failed)}")
    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
