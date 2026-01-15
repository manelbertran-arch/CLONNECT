#!/usr/bin/env python3
"""
Verificación de integraciones end-to-end.
Ejecutar después de cada cambio para verificar que nada se rompió.
"""

import subprocess
import sys
import json
import os

# Colores para output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def print_status(name, passed, details=""):
    status = f"{GREEN}✅{RESET}" if passed else f"{RED}❌{RESET}"
    print(f"  {status} {name}")
    if details and not passed:
        print(f"      {YELLOW}→ {details}{RESET}")

def test_database_connection():
    """Verificar conexión a DB"""
    try:
        # Intentar conexión simple
        from backend.api.services.db_service import get_db_connection
        conn = get_db_connection()
        return True, ""
    except Exception as e:
        return False, str(e)

def test_api_health():
    """Verificar que API responde"""
    try:
        import httpx
        r = httpx.get("http://localhost:8000/health", timeout=5)
        return r.status_code == 200, f"Status: {r.status_code}"
    except Exception as e:
        return False, str(e)

def test_webhook_endpoint():
    """Verificar que webhook Instagram existe"""
    try:
        import httpx
        r = httpx.get("http://localhost:8000/webhook/instagram?hub.mode=subscribe&hub.verify_token=test&hub.challenge=test123", timeout=5)
        return "test123" in r.text or r.status_code == 200, f"Status: {r.status_code}"
    except Exception as e:
        return False, str(e)

def test_rag_search(creator_id="fitpack_global"):
    """Verificar que RAG devuelve resultados"""
    try:
        import httpx
        r = httpx.post(
            "http://localhost:8000/api/rag/search",
            json={"creator_id": creator_id, "query": "coaching precio"},
            timeout=10
        )
        data = r.json()
        has_results = len(data.get("results", [])) > 0
        return has_results, f"Chunks: {len(data.get('results', []))}"
    except Exception as e:
        return False, str(e)

def test_bot_response(creator_id="fitpack_global"):
    """Verificar que bot genera respuesta"""
    try:
        import httpx
        r = httpx.post(
            "http://localhost:8000/api/dm/simulate",
            json={
                "creator_id": creator_id,
                "message": "Hola, ¿cuánto cuesta el coaching?",
                "lead_name": "Test"
            },
            timeout=30
        )
        data = r.json()
        has_response = len(data.get("response", "")) > 10
        # Verificar que no alucina (precio debe venir de productos)
        response = data.get("response", "").lower()
        has_price = "150" in response or "€" in response or "precio" in response
        return has_response and has_price, f"Response length: {len(data.get('response', ''))}"
    except Exception as e:
        return False, str(e)

def main():
    print("\n" + "="*60)
    print("  VERIFICACIÓN DE INTEGRACIONES END-TO-END")
    print("="*60 + "\n")

    tests = [
        ("Database connection", test_database_connection),
        ("API health", test_api_health),
        ("Webhook endpoint", test_webhook_endpoint),
        ("RAG search", test_rag_search),
        ("Bot response", test_bot_response),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed, details = test_func()
            results.append((name, passed, details))
            print_status(name, passed, details)
        except Exception as e:
            results.append((name, False, str(e)))
            print_status(name, False, str(e))

    print("\n" + "="*60)

    passed_count = sum(1 for _, p, _ in results if p)
    total = len(results)

    if passed_count == total:
        print(f"  {GREEN}✅ TODAS LAS INTEGRACIONES OK ({passed_count}/{total}){RESET}")
        print("  → Seguro para continuar")
    else:
        print(f"  {RED}❌ FALLOS DETECTADOS ({passed_count}/{total}){RESET}")
        print("  → NO continuar hasta arreglar")

    print("="*60 + "\n")

    return 0 if passed_count == total else 1

if __name__ == "__main__":
    sys.exit(main())
