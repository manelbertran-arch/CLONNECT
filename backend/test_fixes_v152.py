#!/usr/bin/env python3
"""
Test script for v1.5.2 fixes - Verifies all 6 fixes work correctly.
"""

import sys
sys.path.insert(0, '.')

from core.response_fixes import (
    fix_price_typo,
    fix_broken_links,
    fix_identity_claim,
    clean_raw_ctas,
    hide_technical_errors,
    deduplicate_products,
    apply_all_response_fixes
)
from ingestion.content_citation import clean_rag_ctas

def test_all():
    print("=" * 60)
    print("TEST v1.5.2 FIXES - 5 Conversaciones de prueba")
    print("=" * 60)

    all_passed = True

    # =========================================================================
    # TEST 1: "¿Cuánto cuesta?" -> Responde con €
    # =========================================================================
    print("\n[TEST 1] ¿Cuánto cuesta? -> Responde con €")
    print("-" * 40)

    # Simular respuesta con typo de precio
    bad_response = "El curso cuesta 297? y el ebook 22?"
    fixed = fix_price_typo(bad_response)

    print(f"  INPUT:  '{bad_response}'")
    print(f"  OUTPUT: '{fixed}'")

    if "297€" in fixed and "22€" in fixed and "?" not in fixed:
        print("  RESULT: PASS")
    else:
        print("  RESULT: FAIL")
        all_passed = False

    # =========================================================================
    # TEST 2: "¿Qué productos tienes?" -> Sin duplicados
    # =========================================================================
    print("\n[TEST 2] ¿Qué productos tienes? -> Sin duplicados")
    print("-" * 40)

    # Simular productos duplicados
    products_with_dupes = [
        {"name": "Curso Premium", "price": 297},
        {"name": "Ebook Gratis", "price": 0},
        {"name": "curso premium", "price": 297},  # Duplicado (case-insensitive)
        {"name": "Mentoría 1:1", "price": 500},
        {"name": "EBOOK GRATIS", "price": 0},  # Duplicado
    ]

    unique = deduplicate_products(products_with_dupes)

    print(f"  INPUT:  {len(products_with_dupes)} productos")
    for p in products_with_dupes:
        print(f"          - {p['name']}")
    print(f"  OUTPUT: {len(unique)} productos")
    for p in unique:
        print(f"          - {p['name']}")

    if len(unique) == 3:  # Solo 3 únicos
        print("  RESULT: PASS")
    else:
        print("  RESULT: FAIL")
        all_passed = False

    # =========================================================================
    # TEST 3: "Pásame el link" -> URL válida
    # =========================================================================
    print("\n[TEST 3] Pásame el link -> URL válida")
    print("-" * 40)

    # Simular link roto
    bad_link = "Aquí tienes el link: ://www.stripe.com/pay/123"
    fixed = fix_broken_links(bad_link)

    print(f"  INPUT:  '{bad_link}'")
    print(f"  OUTPUT: '{fixed}'")

    if "https://www.stripe.com" in fixed and "://www" not in fixed.replace("https://www", ""):
        print("  RESULT: PASS")
    else:
        print("  RESULT: FAIL")
        all_passed = False

    # =========================================================================
    # TEST 4: "¿Quién eres?" -> No dice "soy Stefano"
    # =========================================================================
    print("\n[TEST 4] ¿Quién eres? -> No dice 'soy Stefano'")
    print("-" * 40)

    # Simular respuesta incorrecta de identidad
    bad_identity = "Hola! Soy Stefano y estoy aquí para ayudarte."
    fixed = fix_identity_claim(bad_identity)

    print(f"  INPUT:  '{bad_identity}'")
    print(f"  OUTPUT: '{fixed}'")

    if "Soy el asistente de Stefano" in fixed and "Soy Stefano" not in fixed:
        print("  RESULT: PASS")
    else:
        print("  RESULT: FAIL")
        all_passed = False

    # Test adicional con "Me llamo"
    bad_identity2 = "Me llamo Stefano, encantado!"
    fixed2 = fix_identity_claim(bad_identity2)
    print(f"  INPUT:  '{bad_identity2}'")
    print(f"  OUTPUT: '{fixed2}'")

    if "asistente de Stefano" in fixed2:
        print("  RESULT: PASS")
    else:
        print("  RESULT: FAIL")
        all_passed = False

    # =========================================================================
    # TEST 5: "Cuéntame del programa" -> Sin CTAs crudos
    # =========================================================================
    print("\n[TEST 5] Cuéntame del programa -> Sin CTAs crudos")
    print("-" * 40)

    # Simular respuesta con CTAs crudos del RAG
    bad_rag = "El programa incluye 12 módulos. QUIERO SER PARTE INSCRIBETE YA Además tienes acceso de por vida."
    fixed = clean_raw_ctas(bad_rag)

    print(f"  INPUT:  '{bad_rag}'")
    print(f"  OUTPUT: '{fixed}'")

    if "QUIERO SER PARTE" not in fixed and "INSCRIBETE" not in fixed:
        print("  RESULT: PASS")
    else:
        print("  RESULT: FAIL")
        all_passed = False

    # Test de clean_rag_ctas (usado en content_citation.py)
    rag_excerpt = "Aprende trading en 30 días. LINK EN MI BIO SWIPE UP Método comprobado."
    clean_excerpt = clean_rag_ctas(rag_excerpt)
    print(f"  INPUT:  '{rag_excerpt}'")
    print(f"  OUTPUT: '{clean_excerpt}'")

    if "LINK EN MI BIO" not in clean_excerpt and "SWIPE UP" not in clean_excerpt:
        print("  RESULT: PASS")
    else:
        print("  RESULT: FAIL")
        all_passed = False

    # =========================================================================
    # TEST 6 (BONUS): Errores técnicos ocultos
    # =========================================================================
    print("\n[TEST 6] Errores técnicos -> Ocultos")
    print("-" * 40)

    bad_error = "Hola! ERROR: Connection timeout. Te ayudo con gusto."
    fixed = hide_technical_errors(bad_error)

    print(f"  INPUT:  '{bad_error}'")
    print(f"  OUTPUT: '{fixed}'")

    if "ERROR:" not in fixed and "timeout" not in fixed.lower():
        print("  RESULT: PASS")
    else:
        print("  RESULT: FAIL")
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
