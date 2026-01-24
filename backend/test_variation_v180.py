#!/usr/bin/env python3
"""
Test script for v1.8.0 Response Variation - Verifies no repetition.
"""

import sys
sys.path.insert(0, '.')

from core.response_variation import (
    VariationEngine,
    get_variation_engine
)


def test_all():
    print("=" * 60)
    print("TEST v1.8.0 RESPONSE VARIATION - 5 Conversaciones")
    print("=" * 60)

    all_passed = True

    # =========================================================================
    # TEST 1: Mismo saludo NO se repite 3 veces
    # =========================================================================
    print("\n[TEST 1] Saludos no se repiten 3 veces consecutivas")
    print("-" * 40)

    engine1 = VariationEngine()
    conv_id = "test_conv_1"

    responses = [
        "¡Hola! ¿Cómo estás?",
        "¡Hola! Gracias por escribir.",
        "¡Hola! Me alegra que preguntes.",
    ]

    greetings_used = []
    for i, resp in enumerate(responses):
        varied = engine1.vary_response(resp, conv_id)
        # Extract greeting
        greeting = varied.split()[0] if varied else ""
        greetings_used.append(greeting)
        print(f"  Msg {i+1}: '{resp[:30]}...' -> '{varied[:30]}...'")
        print(f"          Greeting: {greeting}")

    unique_greetings = len(set(greetings_used))
    print(f"  Unique greetings: {unique_greetings}/3")

    if unique_greetings >= 2:  # At least 2 different greetings out of 3
        print("  RESULT: PASS - Saludos varían")
    else:
        print("  RESULT: FAIL - Saludos no varían suficiente")
        all_passed = False

    # =========================================================================
    # TEST 2: Conectores varían en respuestas consecutivas
    # =========================================================================
    print("\n[TEST 2] Conectores varían")
    print("-" * 40)

    engine2 = VariationEngine()
    conv_id2 = "test_conv_2"

    responses2 = [
        "El programa es genial. Además incluye soporte.",
        "Tenemos garantía. Además tienes acceso de por vida.",
        "Es muy completo. Además hay comunidad privada.",
    ]

    connectors_used = []
    for i, resp in enumerate(responses2):
        varied = engine2.vary_response(resp, conv_id2)
        # Find connector used
        for conn in ["además", "también", "por otro lado", "y además", "aparte"]:
            if conn in varied.lower():
                connectors_used.append(conn)
                break
        print(f"  Msg {i+1}: '...{resp[-30:]}' -> '...{varied[-35:]}'")

    print(f"  Connectors used: {connectors_used}")
    unique_connectors = len(set(connectors_used))

    if unique_connectors >= 2:
        print("  RESULT: PASS - Conectores varían")
    else:
        print("  RESULT: FAIL - Conectores no varían")
        all_passed = False

    # =========================================================================
    # TEST 3: Formato de precio varía
    # =========================================================================
    print("\n[TEST 3] Formato de precio varía")
    print("-" * 40)

    engine3 = VariationEngine()
    conv_id3 = "test_conv_3"

    responses3 = [
        "El curso cuesta 297€ e incluye todo.",
        "Son 297€ con acceso ilimitado.",
        "Por 297 euros tienes todo el contenido.",
    ]

    price_formats = []
    for i, resp in enumerate(responses3):
        varied = engine3.vary_response(resp, conv_id3)
        # Extract price format
        import re
        match = re.search(r'(?:cuesta\s+|son\s+|solo\s+|por\s+)?(\d+)\s*(?:€|euros?|euritos)', varied, re.I)
        if match:
            price_formats.append(match.group(0).lower())
        print(f"  Msg {i+1}: '{resp}' -> '{varied}'")

    print(f"  Price formats: {price_formats}")
    unique_formats = len(set(price_formats))

    if unique_formats >= 2:
        print("  RESULT: PASS - Precios varían formato")
    else:
        print("  RESULT: FAIL - Precios no varían")
        all_passed = False

    # =========================================================================
    # TEST 4: CTAs no se repiten
    # =========================================================================
    print("\n[TEST 4] CTAs no se repiten")
    print("-" * 40)

    engine4 = VariationEngine()
    conv_id4 = "test_conv_4"

    responses4 = [
        "Perfecto, te paso el link: example.com",
        "Genial, te paso el link aquí: example.com",
        "Ok, te paso el link para que veas: example.com",
    ]

    ctas_used = []
    for i, resp in enumerate(responses4):
        varied = engine4.vary_response(resp, conv_id4)
        # Extract CTA
        for cta in ["te paso el link", "aquí lo tienes", "te lo dejo aquí", "mira esto", "este es el enlace"]:
            if cta in varied.lower():
                ctas_used.append(cta)
                break
        print(f"  Msg {i+1}: '{resp[:40]}...' -> '{varied[:40]}...'")

    print(f"  CTAs used: {ctas_used}")
    unique_ctas = len(set(ctas_used))

    if unique_ctas >= 2:
        print("  RESULT: PASS - CTAs varían")
    else:
        print("  RESULT: FAIL - CTAs no varían")
        all_passed = False

    # =========================================================================
    # TEST 5: Tracking es independiente por usuario
    # =========================================================================
    print("\n[TEST 5] Tracking independiente por usuario")
    print("-" * 40)

    engine5 = VariationEngine()

    # User 1 gets Hola
    resp_user1 = engine5.vary_response("¡Hola! Bienvenido.", "creator:user1")
    greeting_user1 = resp_user1.split()[0]

    # User 2 should also be able to get Hola (fresh tracking)
    resp_user2 = engine5.vary_response("¡Hola! Bienvenido.", "creator:user2")
    greeting_user2 = resp_user2.split()[0]

    print(f"  User1 first greeting: {greeting_user1}")
    print(f"  User2 first greeting: {greeting_user2}")

    # Both can get same greeting since they're different users
    # The key test is that user2's tracking is independent
    stats_user1 = engine5.get_usage_stats("creator:user1")
    stats_user2 = engine5.get_usage_stats("creator:user2")

    print(f"  User1 stats: {stats_user1.get('greeting', {})}")
    print(f"  User2 stats: {stats_user2.get('greeting', {})}")

    # Each user should have exactly 1 greeting tracked
    user1_greeting_count = sum(stats_user1.get('greeting', {}).values())
    user2_greeting_count = sum(stats_user2.get('greeting', {}).values())

    if user1_greeting_count == 1 and user2_greeting_count == 1:
        print("  RESULT: PASS - Tracking independiente")
    else:
        print(f"  RESULT: FAIL - Expected 1 greeting each, got {user1_greeting_count}, {user2_greeting_count}")
        all_passed = False

    # =========================================================================
    # TEST 6 (BONUS): Singleton funciona
    # =========================================================================
    print("\n[TEST 6] Singleton pattern")
    print("-" * 40)

    engine_a = get_variation_engine()
    engine_b = get_variation_engine()

    if engine_a is engine_b:
        print("  RESULT: PASS - Singleton funciona")
    else:
        print("  RESULT: FAIL - No es singleton")
        all_passed = False

    # =========================================================================
    # TEST 7 (BONUS): No varía cuando no hay patrones
    # =========================================================================
    print("\n[TEST 7] No varía texto sin patrones conocidos")
    print("-" * 40)

    engine7 = VariationEngine()
    plain_text = "Este es un texto simple sin patrones especiales."
    varied_text = engine7.vary_response(plain_text, "test_conv_7")

    if plain_text == varied_text:
        print(f"  Input:  '{plain_text}'")
        print(f"  Output: '{varied_text}'")
        print("  RESULT: PASS - No modifica texto sin patrones")
    else:
        print("  RESULT: FAIL - Modificó texto sin patrones")
        all_passed = False

    # =========================================================================
    # RESULTADO FINAL
    # =========================================================================
    print("\n" + "=" * 60)
    if all_passed:
        print("TODOS LOS TESTS PASARON")
    else:
        print("ALGUNOS TESTS FALLARON")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = test_all()
    sys.exit(0 if success else 1)
