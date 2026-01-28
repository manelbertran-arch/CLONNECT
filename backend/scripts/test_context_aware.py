#!/usr/bin/env python3
"""
Test del Context-Aware Intent Classification.

Verifica que "Si" se clasifique correctamente según el contexto:
- Bot: "¿Quieres saber más?" + User: "Si" → INTEREST_SOFT
- Bot: "¿Te paso el link?" + User: "Si" → INTEREST_STRONG
- Bot: "¿Agendamos una llamada?" + User: "Si" → BOOKING

Ejecutar: python scripts/test_context_aware.py
"""

import sys
import os

# Añadir backend al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.bot_question_analyzer import (
    BotQuestionAnalyzer,
    QuestionType,
    is_short_affirmation
)


def test_bot_question_analyzer():
    """Test del BotQuestionAnalyzer."""
    print("\n" + "=" * 80)
    print("TEST: BotQuestionAnalyzer - Detección de tipo de pregunta del bot")
    print("=" * 80 + "\n")

    analyzer = BotQuestionAnalyzer()

    test_cases = [
        # (mensaje del bot, tipo esperado)
        ("¿Te gustaría saber más sobre el programa?", QuestionType.INTEREST),
        ("¿Quieres que te cuente cómo funciona?", QuestionType.INTEREST),
        ("¿Te interesa conocer más detalles?", QuestionType.INTEREST),

        ("¿Te paso el link de pago?", QuestionType.PURCHASE),
        ("¿Lo compramos entonces?", QuestionType.PURCHASE),
        ("¿Procedemos con la compra?", QuestionType.PURCHASE),

        ("¿Qué aspecto te gustaría mejorar?", QuestionType.INFORMATION),
        ("¿En qué puedo ayudarte?", QuestionType.INFORMATION),
        ("Cuéntame más sobre tu situación", QuestionType.INFORMATION),

        ("¿Te quedó claro?", QuestionType.CONFIRMATION),
        ("¿Alguna duda?", QuestionType.CONFIRMATION),

        ("¿Quieres agendar una llamada?", QuestionType.BOOKING),
        ("¿Agendamos una videollamada?", QuestionType.BOOKING),
        ("¿Cuándo puedes para una llamada?", QuestionType.BOOKING),

        ("¿Cómo prefieres pagar?", QuestionType.PAYMENT_METHOD),
        ("¿Tarjeta o transferencia?", QuestionType.PAYMENT_METHOD),

        ("Gracias por tu mensaje.", QuestionType.UNKNOWN),  # Sin pregunta
    ]

    passed = 0
    failed = 0

    for bot_msg, expected_type in test_cases:
        result = analyzer.analyze(bot_msg)
        status = "✅" if result == expected_type else "❌"
        if result == expected_type:
            passed += 1
        else:
            failed += 1
        print(f"{status} '{bot_msg[:50]}...' → {result.value} (esperado: {expected_type.value})")

    print(f"\n{'─' * 40}")
    print(f"Passed: {passed} | Failed: {failed}")
    return failed == 0


def test_short_affirmation():
    """Test de is_short_affirmation."""
    print("\n" + "=" * 80)
    print("TEST: is_short_affirmation - Detección de afirmaciones cortas")
    print("=" * 80 + "\n")

    test_cases = [
        # (mensaje, es afirmación corta)
        ("Si", True),
        ("Sí", True),
        ("Ok", True),
        ("Vale", True),
        ("Dale", True),
        ("Claro", True),
        ("Bueno", True),
        ("Perfecto", True),
        ("Si!", True),
        ("Vale.", True),
        ("Si claro", True),
        ("Ok perfecto", True),

        # No son afirmaciones cortas
        ("Si, me interesa mucho el programa de coaching", False),
        ("Quiero comprar el curso", False),
        ("Hola", False),
        ("No", False),
        ("", False),
    ]

    passed = 0
    failed = 0

    for msg, expected in test_cases:
        result = is_short_affirmation(msg)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status} '{msg}' → {result} (esperado: {expected})")

    print(f"\n{'─' * 40}")
    print(f"Passed: {passed} | Failed: {failed}")
    return failed == 0


def test_context_aware_classification():
    """Test de clasificación context-aware simulada."""
    print("\n" + "=" * 80)
    print("TEST: Context-Aware Classification - Flujo completo")
    print("=" * 80 + "\n")

    # Simular el flujo de _classify_intent
    from core.dm_agent_v2 import DMResponderAgent, Intent

    # Crear agent de prueba
    agent = DMResponderAgent(creator_id="test_context")

    test_cases = [
        # (historial, mensaje usuario, intent esperado)
        (
            [
                {"role": "user", "content": "Hola, me interesa el coaching"},
                {"role": "assistant", "content": "¡Hola! Genial. ¿Quieres que te cuente más sobre el programa?"}
            ],
            "Si",
            Intent.INTEREST_SOFT
        ),
        (
            [
                {"role": "user", "content": "Me interesa comprarlo"},
                {"role": "assistant", "content": "¡Perfecto! ¿Te paso el link de pago?"}
            ],
            "Si",
            Intent.INTEREST_STRONG
        ),
        (
            [
                {"role": "user", "content": "Quiero una llamada"},
                {"role": "assistant", "content": "¡Genial! ¿Agendamos una videollamada?"}
            ],
            "Vale",
            Intent.BOOKING
        ),
        (
            [
                {"role": "user", "content": "Ya entendí"},
                {"role": "assistant", "content": "¿Te quedó claro todo?"}
            ],
            "Si",
            Intent.ACKNOWLEDGMENT  # Aquí sí es ACKNOWLEDGMENT porque es confirmación
        ),
        (
            [],  # Sin historial
            "Si",
            Intent.ACKNOWLEDGMENT
        ),
    ]

    passed = 0
    failed = 0

    for history, user_msg, expected_intent in test_cases:
        intent, confidence = agent._classify_intent(user_msg, history)

        last_bot = history[-1]["content"][:40] if history else "Sin historial"
        status = "✅" if intent == expected_intent else "❌"
        if intent == expected_intent:
            passed += 1
        else:
            failed += 1

        print(f"{status} Bot: '{last_bot}...' + User: '{user_msg}'")
        print(f"   → {intent.value} (esperado: {expected_intent.value})\n")

    print(f"{'─' * 40}")
    print(f"Passed: {passed} | Failed: {failed}")
    return failed == 0


def test_meta_message_detection():
    """Test de detección de meta-mensajes."""
    print("\n" + "=" * 80)
    print("TEST: Meta-Message Detection - Detección de referencias a la conversación")
    print("=" * 80 + "\n")

    from core.dm_agent_v2 import DMResponderAgent

    agent = DMResponderAgent(creator_id="test_meta")

    test_cases = [
        # (mensaje, historial, acción esperada)
        (
            "Ya te lo dije antes",
            [{"role": "user", "content": "Me interesa el curso de trading"}],
            "REVIEW_HISTORY"
        ),
        (
            "Revisa el chat",
            [{"role": "user", "content": "Quiero información sobre coaching"}],
            "REVIEW_HISTORY"
        ),
        (
            "No me entiendes",
            [{"role": "assistant", "content": "¿Qué te gustaría saber?"}],
            "USER_FRUSTRATED"
        ),
        (
            "Eres un bot inútil",
            [],
            "USER_FRUSTRATED"
        ),
        (
            "Puedes repetir?",
            [{"role": "assistant", "content": "El precio es 297€"}],
            "REPEAT_REQUESTED"
        ),
        (
            "Hola, me interesa",  # No es meta-mensaje
            [],
            None
        ),
    ]

    passed = 0
    failed = 0

    for msg, history, expected_action in test_cases:
        result = agent._detect_meta_message(msg, history)
        actual_action = result.get("action") if result else None

        status = "✅" if actual_action == expected_action else "❌"
        if actual_action == expected_action:
            passed += 1
        else:
            failed += 1

        print(f"{status} '{msg}' → {actual_action} (esperado: {expected_action})")

    print(f"\n{'─' * 40}")
    print(f"Passed: {passed} | Failed: {failed}")
    return failed == 0


if __name__ == "__main__":
    print("\n" + "🧪" * 40)
    print("INICIANDO TESTS DE CONTEXT-AWARE CLASSIFICATION")
    print("🧪" * 40)

    all_passed = True

    # Test 1: BotQuestionAnalyzer
    if not test_bot_question_analyzer():
        all_passed = False

    # Test 2: Short affirmation detection
    if not test_short_affirmation():
        all_passed = False

    # Test 3: Context-aware classification
    if not test_context_aware_classification():
        all_passed = False

    # Test 4: Meta-message detection
    if not test_meta_message_detection():
        all_passed = False

    # Resumen final
    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 TODOS LOS TESTS PASARON")
    else:
        print("💥 ALGUNOS TESTS FALLARON")
    print("=" * 80)

    sys.exit(0 if all_passed else 1)
