#!/usr/bin/env python3
"""
Test script for v1.6.0 State Machine - Verifies conversation phases and transitions.
"""

import sys
sys.path.insert(0, '.')

from core.conversation_state import (
    ConversationPhase,
    ConversationState,
    UserContext,
    StateManager,
    get_state_manager
)


def test_all():
    print("=" * 60)
    print("TEST v1.6.0 STATE MACHINE - 5 Conversaciones de prueba")
    print("=" * 60)

    all_passed = True
    state_manager = StateManager()

    # =========================================================================
    # TEST 1: Flujo INICIO -> CUALIFICACION
    # =========================================================================
    print("\n[TEST 1] Flujo INICIO -> CUALIFICACION")
    print("-" * 40)

    state = state_manager.get_state("user1", "creator1")
    print(f"  Estado inicial: {state.phase.value}")

    # Simular primer mensaje
    state = state_manager.update_state(state, "Hola, vi tu post", "greeting", "Hola! Que te llamo la atencion?")

    print(f"  Despues de 'Hola, vi tu post': {state.phase.value}")

    if state.phase == ConversationPhase.CUALIFICACION:
        print("  RESULT: PASS - Transiciono a CUALIFICACION")
    else:
        print(f"  RESULT: FAIL - Esperaba CUALIFICACION, obtuvo {state.phase.value}")
        all_passed = False

    # Verificar que NO menciona productos en INICIO
    phase_instructions = state_manager.get_phase_instructions(ConversationPhase.INICIO)
    if "NO menciones productos" in phase_instructions:
        print("  BONUS: Instrucciones de INICIO correctas (no productos)")
    else:
        print("  WARNING: Instrucciones de INICIO no mencionan restriccion de productos")

    # =========================================================================
    # TEST 2: Contexto recordado (hijos + tiempo)
    # =========================================================================
    print("\n[TEST 2] Contexto recordado")
    print("-" * 40)

    state2 = state_manager.get_state("user2", "creator1")
    state2.phase = ConversationPhase.CUALIFICACION

    # Mensaje con contexto personal
    state2 = state_manager.update_state(
        state2,
        "Tengo 3 hijos y poco tiempo para entrenar",
        "question_general",
        "Entiendo, con 3 hijos es complicado encontrar tiempo!"
    )

    print(f"  Situacion extraida: {state2.context.situation}")
    print(f"  Restricciones: {state2.context.constraints}")

    has_hijos = state2.context.situation and "hijos" in state2.context.situation
    has_tiempo = "poco tiempo" in state2.context.constraints

    if has_hijos and has_tiempo:
        print("  RESULT: PASS - Contexto extraido correctamente")
    else:
        print(f"  RESULT: FAIL - Falta contexto (hijos={has_hijos}, tiempo={has_tiempo})")
        all_passed = False

    # Verificar que el contexto aparece en el prompt
    context_prompt = state2.context.to_prompt_context()
    print(f"  Prompt context: {context_prompt[:100]}...")

    if "hijos" in context_prompt.lower() or "tiempo" in context_prompt.lower():
        print("  BONUS: Contexto incluido en prompt")
    else:
        print("  WARNING: Contexto no aparece en prompt")

    # =========================================================================
    # TEST 3: Flujo hasta PROPUESTA
    # =========================================================================
    print("\n[TEST 3] Flujo hasta PROPUESTA")
    print("-" * 40)

    state3 = state_manager.get_state("user3", "creator1")

    # Simular conversacion completa
    messages = [
        ("Hola!", "greeting", "Hola! Que te trajo por aqui?"),
        ("Quiero bajar de peso", "interest_soft", "Genial! Cuanto tiempo tienes disponible?"),
        ("Tengo poco tiempo, trabajo mucho", "question_general", "Entiendo, te recomiendo mi programa express de 297 euros"),
    ]

    for msg, intent, response in messages:
        state3 = state_manager.update_state(state3, msg, intent, response)
        print(f"  '{msg[:30]}...' -> {state3.phase.value}")

    if state3.phase == ConversationPhase.PROPUESTA:
        print("  RESULT: PASS - Llego a PROPUESTA")
    else:
        print(f"  RESULT: FAIL - Esperaba PROPUESTA, obtuvo {state3.phase.value}")
        all_passed = False

    # Verificar que extrajo el objetivo
    if state3.context.goal == "bajar de peso":
        print("  BONUS: Objetivo extraido correctamente")
    else:
        print(f"  WARNING: Objetivo esperado 'bajar de peso', obtuvo '{state3.context.goal}'")

    # =========================================================================
    # TEST 4: Manejo de objecion (no repetir precio)
    # =========================================================================
    print("\n[TEST 4] Manejo de objecion - No repetir precio")
    print("-" * 40)

    state4 = state_manager.get_state("user4", "creator1")
    state4.phase = ConversationPhase.PROPUESTA
    state4.context.price_discussed = True  # Ya se menciono precio

    # Obtener reminder
    reminder = state_manager.get_context_reminder(state4)
    print(f"  Reminder generado: '{reminder}'")

    if "precio" in reminder.lower():
        print("  RESULT: PASS - Reminder advierte sobre precio")
    else:
        print("  RESULT: FAIL - Reminder no menciona precio")
        all_passed = False

    # Simular objecion
    state4 = state_manager.update_state(
        state4,
        "Es muy caro para mi",
        "objection_price",
        "Entiendo tu preocupacion. Hay opciones de pago fraccionado."
    )

    if state4.phase == ConversationPhase.OBJECIONES:
        print("  BONUS: Transiciono a OBJECIONES correctamente")
    else:
        print(f"  INFO: Fase actual: {state4.phase.value}")

    # =========================================================================
    # TEST 5: Escalacion
    # =========================================================================
    print("\n[TEST 5] Escalacion")
    print("-" * 40)

    state5 = state_manager.get_state("user5", "creator1")
    state5.phase = ConversationPhase.PROPUESTA

    state5 = state_manager.update_state(
        state5,
        "Quiero hablar con Stefano directamente",
        "escalation",
        "Entendido, le notifico a Stefano para que te contacte."
    )

    print(f"  Despues de pedir humano: {state5.phase.value}")

    if state5.phase == ConversationPhase.ESCALAR:
        print("  RESULT: PASS - Transiciono a ESCALAR")
    else:
        print(f"  RESULT: FAIL - Esperaba ESCALAR, obtuvo {state5.phase.value}")
        all_passed = False

    # =========================================================================
    # TEST 6 (BONUS): build_enhanced_prompt
    # =========================================================================
    print("\n[TEST 6] build_enhanced_prompt")
    print("-" * 40)

    state6 = state_manager.get_state("user6", "creator1")
    state6.phase = ConversationPhase.DESCUBRIMIENTO
    state6.context.goal = "mas energia"
    state6.context.situation = "trabaja mucho"

    enhanced = state_manager.build_enhanced_prompt(state6)

    print(f"  Prompt generado ({len(enhanced)} chars)")
    print(f"  Preview: {enhanced[:200]}...")

    has_phase = "DESCUBRIMIENTO" in enhanced.upper()
    has_context = "energia" in enhanced.lower() or "trabaja" in enhanced.lower()

    if has_phase and has_context:
        print("  RESULT: PASS - Prompt incluye fase y contexto")
    else:
        print(f"  RESULT: FAIL - Falta fase={has_phase} o contexto={has_context}")
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
