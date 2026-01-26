#!/usr/bin/env python3
"""
Script de verificación de integración - CLONNECT

Verifica que todos los bloques congelados siguen funcionando.
Ejecutar después de cada cambio antes de hacer commit.

Uso:
    python scripts/verify_integration.py
    python scripts/verify_integration.py --creator fitpack_global
"""

import sys
import json
import argparse
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

# Configuración
BASE_URL = "https://api.clonnectapp.com"
DEFAULT_CREATOR = "fitpack_global"

# Colores para output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def check(name: str, condition: bool, details: str = ""):
    """Imprime resultado de verificación"""
    if condition:
        print(f"  {GREEN}✅{RESET} {name}")
    else:
        print(f"  {RED}❌{RESET} {name}: {details}")
    return condition


def api_get(endpoint: str) -> dict:
    """GET request a la API"""
    try:
        url = f"{BASE_URL}{endpoint}"
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": str(e.reason)}
    except URLError as e:
        return {"error": "Connection failed", "detail": str(e.reason)}
    except Exception as e:
        return {"error": "Unknown", "detail": str(e)}


def api_post(endpoint: str, data: dict) -> dict:
    """POST request a la API"""
    try:
        url = f"{BASE_URL}{endpoint}"
        json_data = json.dumps(data).encode("utf-8")
        req = Request(url, data=json_data, headers={
            "Accept": "application/json",
            "Content-Type": "application/json"
        })
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except HTTPError as e:
        return {"error": f"HTTP {e.code}", "detail": str(e.reason)}
    except URLError as e:
        return {"error": "Connection failed", "detail": str(e.reason)}
    except Exception as e:
        return {"error": "Unknown", "detail": str(e)}


def verify_health():
    """Verifica health del backend"""
    print("\n📡 BACKEND HEALTH")
    result = api_get("/health")

    ok = check("Backend responde", "status" in result, result.get("error", ""))
    if not ok:
        return False

    check("Status healthy", result.get("status") == "healthy")

    checks = result.get("checks", {})
    check("LLM disponible", checks.get("llm", {}).get("status") == "ok")
    check("Disco OK", checks.get("disk", {}).get("status") == "ok")

    return True


def verify_products(creator_id: str):
    """Verifica productos"""
    print(f"\n📦 PRODUCTOS ({creator_id})")
    result = api_get(f"/creator/{creator_id}/products")

    if "error" in result:
        check("API productos", False, result.get("error"))
        return False

    products = result.get("products", [])
    check("Tiene productos", len(products) > 0, f"Encontrados: {len(products)}")

    # Verificar precios específicos
    coaching = next((p for p in products if "coaching" in p.get("name", "").lower()), None)
    if coaching:
        price = coaching.get("price", 0)
        check("Coaching 1:1 = 77€", price == 77, f"Actual: {price}€")

    return True


def verify_rag(creator_id: str):
    """Verifica RAG/contenido"""
    print(f"\n🔍 RAG SEARCH ({creator_id})")
    result = api_get(f"/content/search?creator_id={creator_id}&query=coaching&limit=3")

    if "error" in result:
        check("API RAG", False, result.get("error"))
        return False

    results = result.get("results", [])
    check("RAG tiene contenido", len(results) > 0, f"Resultados: {len(results)}")

    if results:
        first = results[0]
        has_text = len(first.get("text", "")) > 50
        check("Contenido real (no vacío)", has_text)

    return True


def verify_copilot(creator_id: str):
    """Verifica copilot endpoints"""
    print(f"\n🤖 COPILOT ({creator_id})")
    result = api_get(f"/copilot/{creator_id}/status")

    if "error" in result:
        check("API copilot", False, result.get("error"))
        return False

    check("Endpoint status OK", "copilot_enabled" in result or "status" in result)

    # Verificar pending
    pending = api_get(f"/copilot/{creator_id}/pending")
    check("Endpoint pending OK", "pending_responses" in pending or "error" not in pending)

    return True


def verify_leads(creator_id: str):
    """Verifica leads"""
    print(f"\n👥 LEADS ({creator_id})")
    result = api_get(f"/dm/leads/{creator_id}")

    if "error" in result:
        check("API leads", False, result.get("error"))
        return False

    leads = result.get("leads", [])
    check("Tiene leads", len(leads) > 0, f"Encontrados: {len(leads)}")

    return True


def verify_connections(creator_id: str):
    """Verifica conexiones"""
    print(f"\n🔌 CONEXIONES ({creator_id})")
    result = api_get(f"/connections/{creator_id}")

    if "error" in result:
        check("API conexiones", False, result.get("error"))
        return False

    ig = result.get("instagram", {})
    check("Instagram conectado", ig.get("connected") == True)

    return True


def main():
    parser = argparse.ArgumentParser(description="Verificar integración CLONNECT")
    parser.add_argument("--creator", default=DEFAULT_CREATOR, help="Creator ID a verificar")
    parser.add_argument("--url", default=BASE_URL, help="URL base del backend")
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.url
    creator_id = args.creator

    print("=" * 50)
    print("🔬 VERIFICACIÓN DE INTEGRACIÓN - CLONNECT")
    print(f"   Backend: {BASE_URL}")
    print(f"   Creator: {creator_id}")
    print("=" * 50)

    all_passed = True

    # Ejecutar verificaciones
    all_passed &= verify_health()
    all_passed &= verify_products(creator_id)
    all_passed &= verify_rag(creator_id)
    all_passed &= verify_copilot(creator_id)
    all_passed &= verify_leads(creator_id)
    all_passed &= verify_connections(creator_id)

    # Resumen
    print("\n" + "=" * 50)
    if all_passed:
        print(f"{GREEN}✅ TODAS LAS VERIFICACIONES PASARON{RESET}")
        print("   Es seguro hacer commit/deploy")
    else:
        print(f"{RED}❌ ALGUNAS VERIFICACIONES FALLARON{RESET}")
        print("   NO hacer commit hasta resolver")
    print("=" * 50)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
