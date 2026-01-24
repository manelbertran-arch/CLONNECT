#!/usr/bin/env python3
"""
Test script for v1.7.0 Reflexion + Frustration - Verifies detection and analysis.
"""

import sys
sys.path.insert(0, '.')

from core.frustration_detector import (
    FrustrationDetector,
    FrustrationSignals,
    get_frustration_detector
)
from core.reflexion_engine import (
    ReflexionEngine,
    ReflexionResult,
    get_reflexion_engine
)


def test_all():
    print("=" * 60)
    print("TEST v1.7.0 REFLEXION + FRUSTRATION - 5 Conversaciones")
    print("=" * 60)

    all_passed = True
    frustration_detector = FrustrationDetector()
    reflexion_engine = ReflexionEngine()

    # =========================================================================
    # TEST 1: Deteccion de frustracion explicita
    # =========================================================================
    print("\n[TEST 1] Deteccion de frustracion explicita")
    print("-" * 40)

    msg1 = "Ya te dije que quiero el programa de 297 euros!!"
    signals1, score1 = frustration_detector.analyze_message(msg1, "conv1")

    print(f"  Mensaje: '{msg1}'")
    print(f"  Score: {score1:.2f}")
    print(f"  Explicit frustration: {signals1.explicit_frustration}")

    if signals1.explicit_frustration and score1 >= 0.3:
        print("  RESULT: PASS - Detecta frustracion explicita")
    else:
        print(f"  RESULT: FAIL - Expected explicit=True, score>=0.3")
        all_passed = False

    # =========================================================================
    # TEST 2: Deteccion de preguntas repetidas
    # =========================================================================
    print("\n[TEST 2] Deteccion de preguntas repetidas")
    print("-" * 40)

    detector2 = FrustrationDetector()

    # Simular historial
    msgs = [
        "Cuanto cuesta el curso?",
        "Me interesa saber el precio",
        "Cual es el precio del curso?"  # Repeticion
    ]

    signals2 = None
    score2 = 0
    for i, msg in enumerate(msgs):
        signals2, score2 = detector2.analyze_message(msg, "conv2")
        print(f"  Msg {i+1}: '{msg}' -> score={score2:.2f}")

    print(f"  Repeated questions: {signals2.repeated_questions}")

    if signals2.repeated_questions >= 1:
        print("  RESULT: PASS - Detecta pregunta repetida")
    else:
        print(f"  RESULT: FAIL - Expected repeated_questions >= 1")
        all_passed = False

    # =========================================================================
    # TEST 3: CAPS detection
    # =========================================================================
    print("\n[TEST 3] Deteccion de MAYUSCULAS (frustracion)")
    print("-" * 40)

    msg3 = "QUIERO COMPRAR EL CURSO AHORA MISMO"
    signals3, score3 = frustration_detector.analyze_message(msg3, "conv3")

    print(f"  Mensaje: '{msg3}'")
    print(f"  CAPS ratio: {signals3.caps_ratio:.2f}")
    print(f"  Score: {score3:.2f}")

    if signals3.caps_ratio > 0.5:
        print("  RESULT: PASS - Detecta uso excesivo de mayusculas")
    else:
        print(f"  RESULT: FAIL - Expected caps_ratio > 0.5")
        all_passed = False

    # =========================================================================
    # TEST 4: Reflexion - Respuesta muy larga
    # =========================================================================
    print("\n[TEST 4] Reflexion - Respuesta muy larga")
    print("-" * 40)

    user_msg4 = "Hola"
    response4 = """Hola! Bienvenido a mi programa de entrenamiento personal.
    Tengo varios cursos disponibles que pueden ayudarte a alcanzar tus objetivos.
    El programa premium incluye 12 modulos de entrenamiento, acceso a comunidad,
    sesiones en vivo semanales, y mucho mas. Tambien tengo un ebook gratuito
    que puedes descargar. Por donde te gustaria empezar? Que objetivos tienes?
    Cuanto tiempo llevas entrenando? Tienes alguna lesion o limitacion?"""

    result4 = reflexion_engine.analyze_response(response4, user_msg4)

    print(f"  User msg: '{user_msg4}'")
    print(f"  Response length: {len(response4)} chars")
    print(f"  Needs revision: {result4.needs_revision}")
    print(f"  Issues: {result4.issues}")

    if result4.needs_revision and "Respuesta muy larga" in str(result4.issues):
        print("  RESULT: PASS - Detecta respuesta muy larga")
    else:
        print(f"  RESULT: FAIL - Expected to flag long response")
        all_passed = False

    # =========================================================================
    # TEST 5: Reflexion - Falta precio en PROPUESTA
    # =========================================================================
    print("\n[TEST 5] Reflexion - Falta precio en fase PROPUESTA")
    print("-" * 40)

    user_msg5 = "Cuentame del programa"
    response5 = "El programa incluye 12 modulos de entrenamiento, acceso de por vida y soporte."

    result5 = reflexion_engine.analyze_response(
        response5,
        user_msg5,
        conversation_phase="propuesta"
    )

    print(f"  User msg: '{user_msg5}'")
    print(f"  Response: '{response5}'")
    print(f"  Phase: propuesta")
    print(f"  Needs revision: {result5.needs_revision}")
    print(f"  Issues: {result5.issues}")

    if result5.needs_revision and any("precio" in str(i).lower() for i in result5.issues):
        print("  RESULT: PASS - Detecta falta de precio en PROPUESTA")
    else:
        print(f"  RESULT: FAIL - Expected to flag missing price")
        all_passed = False

    # =========================================================================
    # TEST 6 (BONUS): Frustration context generation
    # =========================================================================
    print("\n[TEST 6] Generacion de contexto de frustracion")
    print("-" * 40)

    signals6 = FrustrationSignals(
        repeated_questions=2,
        explicit_frustration=True,
        negative_markers=3
    )
    score6 = signals6.get_score()

    context6 = frustration_detector.get_frustration_context(score6, signals6)

    print(f"  Score calculado: {score6:.2f}")
    print(f"  Context preview: {context6[:100]}...")

    if "ALTO" in context6 and "DISCULPA" in context6.upper():
        print("  RESULT: PASS - Genera contexto apropiado")
    else:
        print(f"  RESULT: FAIL - Expected ALTO level context")
        all_passed = False

    # =========================================================================
    # TEST 7 (BONUS): Reflexion - Pregunta de precio sin respuesta
    # =========================================================================
    print("\n[TEST 7] Reflexion - Pregunta precio sin respuesta")
    print("-" * 40)

    user_msg7 = "Cuanto cuesta el curso?"
    response7 = "El curso es muy completo e incluye muchos beneficios para tu entrenamiento."

    result7 = reflexion_engine.analyze_response(response7, user_msg7)

    print(f"  User msg: '{user_msg7}'")
    print(f"  Response: '{response7}'")
    print(f"  Issues: {result7.issues}")

    if result7.needs_revision and any("precio" in str(i).lower() for i in result7.issues):
        print("  RESULT: PASS - Detecta que no responde precio")
    else:
        print(f"  RESULT: FAIL - Expected to flag unanswered price")
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
