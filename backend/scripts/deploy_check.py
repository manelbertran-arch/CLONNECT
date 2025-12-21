#!/usr/bin/env python3
"""
Clonnect Creators - Deploy Check Script
Verifica que todo esta listo para deploy
"""

import os
import sys
import subprocess
from pathlib import Path

# Colores para output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def ok(msg):
    print(f"{GREEN}[OK]{RESET} {msg}")

def fail(msg):
    print(f"{RED}[FAIL]{RESET} {msg}")

def warn(msg):
    print(f"{YELLOW}[WARN]{RESET} {msg}")

def check_env_vars():
    """Verificar variables de entorno requeridas"""
    print("\n=== Verificando Variables de Entorno ===")

    required = [
        ("LLM_PROVIDER", "Proveedor de LLM (groq/openai)"),
        ("CLONNECT_ADMIN_KEY", "Clave de administrador"),
    ]

    optional = [
        ("GROQ_API_KEY", "API key de Groq"),
        ("OPENAI_API_KEY", "API key de OpenAI"),
        ("INSTAGRAM_ACCESS_TOKEN", "Token de Instagram"),
        ("TELEGRAM_BOT_TOKEN", "Token del bot de Telegram"),
        ("STRIPE_SECRET_KEY", "Clave secreta de Stripe"),
    ]

    errors = []

    for var, desc in required:
        if os.getenv(var):
            ok(f"{var}: {desc}")
        else:
            fail(f"{var}: {desc} - NO CONFIGURADA")
            errors.append(var)

    print("\n--- Variables Opcionales ---")
    for var, desc in optional:
        if os.getenv(var):
            ok(f"{var}: {desc}")
        else:
            warn(f"{var}: {desc} - no configurada")

    return errors

def check_required_files():
    """Verificar que archivos necesarios existen"""
    print("\n=== Verificando Archivos Necesarios ===")

    base_path = Path(__file__).parent.parent

    required_files = [
        "api/main.py",
        "core/dm_agent.py",
        "core/llm.py",
        "core/creator_config.py",
        "core/products.py",
        "core/memory.py",
        "dashboard/app.py",
        "dashboard/admin.py",
        "requirements.txt",
        "railway.json",
        "render.yaml",
    ]

    errors = []

    for file in required_files:
        path = base_path / file
        if path.exists():
            ok(f"{file}")
        else:
            fail(f"{file} - NO ENCONTRADO")
            errors.append(file)

    return errors

def check_data_directory():
    """Verificar directorio de datos"""
    print("\n=== Verificando Directorio de Datos ===")

    data_path = os.getenv("DATA_PATH", "./data")
    base_path = Path(__file__).parent.parent
    full_path = base_path / data_path

    if full_path.exists():
        ok(f"Directorio {data_path} existe")
    else:
        warn(f"Directorio {data_path} no existe - se creara automaticamente")

    subdirs = ["followers", "products", "creators", "analytics"]
    for subdir in subdirs:
        subdir_path = full_path / subdir
        if subdir_path.exists():
            ok(f"  {subdir}/")
        else:
            warn(f"  {subdir}/ no existe - se creara automaticamente")

    return []

def check_syntax():
    """Verificar sintaxis de archivos Python principales"""
    print("\n=== Verificando Sintaxis Python ===")

    base_path = Path(__file__).parent.parent

    files_to_check = [
        "api/main.py",
        "core/dm_agent.py",
        "core/llm.py",
        "dashboard/app.py",
        "dashboard/admin.py",
    ]

    errors = []

    for file in files_to_check:
        path = base_path / file
        if not path.exists():
            continue

        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            ok(f"{file}")
        else:
            fail(f"{file} - Error de sintaxis")
            print(f"    {result.stderr}")
            errors.append(file)

    return errors

def check_imports():
    """Verificar que los imports principales funcionan"""
    print("\n=== Verificando Imports ===")

    errors = []

    imports_to_check = [
        ("fastapi", "FastAPI framework"),
        ("uvicorn", "ASGI server"),
        ("streamlit", "Dashboard framework"),
        ("requests", "HTTP client"),
        ("pydantic", "Data validation"),
    ]

    for module, desc in imports_to_check:
        try:
            __import__(module)
            ok(f"{module}: {desc}")
        except ImportError:
            fail(f"{module}: {desc} - NO INSTALADO")
            errors.append(module)

    # Verificar imports opcionales
    print("\n--- Imports Opcionales ---")
    optional_imports = [
        ("prometheus_client", "Prometheus metrics"),
        ("psutil", "System monitoring"),
        ("aiohttp", "Async HTTP"),
    ]

    for module, desc in optional_imports:
        try:
            __import__(module)
            ok(f"{module}: {desc}")
        except ImportError:
            warn(f"{module}: {desc} - no instalado (opcional)")

    return errors

def check_api_health():
    """Verificar que la API responde (si esta corriendo)"""
    print("\n=== Verificando API (si esta corriendo) ===")

    try:
        import requests
        api_url = os.getenv("API_BASE_URL", "http://localhost:8000")

        response = requests.get(f"{api_url}/health/live", timeout=5)
        if response.status_code == 200:
            ok(f"API respondiendo en {api_url}")
        else:
            warn(f"API respondio con status {response.status_code}")
    except requests.exceptions.ConnectionError:
        warn("API no esta corriendo (normal si es pre-deploy)")
    except Exception as e:
        warn(f"No se pudo verificar API: {e}")

    return []

def main():
    """Ejecutar todas las verificaciones"""
    print("=" * 60)
    print("  CLONNECT CREATORS - DEPLOY CHECK")
    print("=" * 60)

    all_errors = []

    all_errors.extend(check_required_files())
    all_errors.extend(check_syntax())
    all_errors.extend(check_imports())
    all_errors.extend(check_env_vars())
    all_errors.extend(check_data_directory())
    check_api_health()

    print("\n" + "=" * 60)

    if all_errors:
        print(f"{RED}RESULTADO: {len(all_errors)} errores encontrados{RESET}")
        print("\nErrores criticos:")
        for error in all_errors:
            print(f"  - {error}")
        print(f"\n{RED}NO LISTO PARA DEPLOY{RESET}")
        return 1
    else:
        print(f"{GREEN}RESULTADO: Todas las verificaciones pasadas{RESET}")
        print(f"\n{GREEN}READY FOR DEPLOY{RESET}")
        return 0

if __name__ == "__main__":
    sys.exit(main())
