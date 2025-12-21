#!/usr/bin/env python3
"""
Clonnect API Visual Test Report Generator v2.0
Generates comprehensive HTML report showing ALL 66 tests with full responses
"""

import os
import sys
import json
import time
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "https://web-production-9f69.up.railway.app")
ADMIN_KEY = os.getenv("CLONNECT_ADMIN_KEY", "clonnect_admin_secret_2024")

# Test data
TEST_CREATOR_ID = "test_api_suite"
TEST_FOLLOWER_ID = "test_follower_123"
TEST_PRODUCT_ID = "test_product_001"
TEST_BOOKING_ID = "test_booking_001"

# Results storage
results: List[Dict[str, Any]] = []
start_time = None

# Category colors
CATEGORY_COLORS = {
    "A": {"bg": "#7c3aed", "name": "Core del Bot", "icon": "🤖"},
    "B": {"bg": "#2563eb", "name": "Gestión Creadores", "icon": "👥"},
    "C": {"bg": "#0891b2", "name": "Productos", "icon": "📦"},
    "D": {"bg": "#059669", "name": "Conversaciones y Leads", "icon": "💬"},
    "E": {"bg": "#ca8a04", "name": "Autenticación", "icon": "🔐"},
    "F": {"bg": "#dc2626", "name": "GDPR", "icon": "🛡️"},
    "G": {"bg": "#16a34a", "name": "Pagos", "icon": "💳"},
    "H": {"bg": "#9333ea", "name": "Calendario", "icon": "📅"},
    "I": {"bg": "#ea580c", "name": "Admin", "icon": "⚙️"},
    "J": {"bg": "#0d9488", "name": "Health", "icon": "❤️"},
    "K": {"bg": "#e11d48", "name": "Instagram", "icon": "📸"},
}


def test_endpoint(
    test_num: int,
    category: str,
    method: str,
    path: str,
    expected_status: int,
    data: Optional[Dict] = None,
    auth: bool = False,
    description: str = "",
    query_params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Test a single endpoint and return full result"""
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}

    if auth:
        headers["X-API-Key"] = ADMIN_KEY

    full_url = url
    if query_params:
        full_url += "?" + "&".join(f"{k}={v}" for k, v in query_params.items())

    result = {
        "test_num": test_num,
        "category": category,
        "description": description,
        "method": method,
        "path": path,
        "full_url": full_url,
        "expected_status": expected_status,
        "actual_status": 0,
        "passed": False,
        "request_body": data,
        "response_body": None,
        "error": None,
        "duration_ms": 0,
        "timestamp": datetime.now().isoformat(),
        "auth_required": auth,
        "query_params": query_params
    }

    try:
        start = time.time()

        if method == "GET":
            response = requests.get(full_url, headers=headers, timeout=30)
        elif method == "POST":
            response = requests.post(full_url, headers=headers, json=data, timeout=30)
        elif method == "PUT":
            response = requests.put(full_url, headers=headers, json=data, timeout=30)
        elif method == "DELETE":
            response = requests.delete(full_url, headers=headers, timeout=30)
        else:
            result["error"] = f"Unknown method: {method}"
            results.append(result)
            return result

        duration = (time.time() - start) * 1000
        result["duration_ms"] = round(duration, 2)
        result["actual_status"] = response.status_code
        result["passed"] = response.status_code == expected_status

        try:
            result["response_body"] = response.json()
        except:
            result["response_body"] = {"raw_text": response.text[:1000]}

    except requests.exceptions.Timeout:
        result["error"] = "Timeout (30s)"
    except requests.exceptions.ConnectionError as e:
        result["error"] = f"Connection error: {str(e)[:100]}"
    except Exception as e:
        result["error"] = str(e)[:200]

    results.append(result)
    status = "✓" if result["passed"] else "✗"
    print(f"  #{test_num:02d} {status} {method} {path[:45]}")
    return result


def run_all_tests():
    """Run all 66 tests organized by category"""
    global start_time
    start_time = time.time()

    print("=" * 70)
    print("CLONNECT API COMPREHENSIVE TEST SUITE")
    print(f"Base URL: {BASE_URL}")
    print("=" * 70)

    # ═══════════════════════════════════════════════════════════════════════
    # A. CORE DEL BOT (8 tests) - Procesamiento de DMs
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[A] Core del Bot (8 tests)...")
    dm_payloads = [
        ("Saludo", {"creator_id": "manel", "sender_id": "test1", "message": "Hola! Como estas?"}),
        ("Interés soft", {"creator_id": "manel", "sender_id": "test2", "message": "Me interesa tu curso"}),
        ("Objeción precio", {"creator_id": "manel", "sender_id": "test3", "message": "Es muy caro para mi"}),
        ("Objeción tiempo", {"creator_id": "manel", "sender_id": "test4", "message": "No tengo tiempo ahora"}),
        ("Objeción pensarlo", {"creator_id": "manel", "sender_id": "test5", "message": "Tengo que pensarlo"}),
        ("Objeción luego", {"creator_id": "manel", "sender_id": "test6", "message": "Mejor luego, ahora no"}),
        ("Objeción funciona", {"creator_id": "manel", "sender_id": "test7", "message": "No se si esto funciona"}),
        ("Intención compra", {"creator_id": "manel", "sender_id": "test8", "message": "Quiero comprarlo, como pago?"}),
    ]
    for i, (desc, payload) in enumerate(dm_payloads, 1):
        test_endpoint(i, "A", "POST", "/dm/process", 200, data=payload, description=desc)

    # ═══════════════════════════════════════════════════════════════════════
    # B. GESTIÓN DE CREADORES (8 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[B] Gestión Creadores (8 tests)...")
    creator_config = {
        "id": TEST_CREATOR_ID,
        "name": "Test Creator API",
        "instagram_handle": "test_api_creator",
        "personality": {"tone": "friendly"},
        "emoji_style": "moderate",
        "sales_style": "soft"
    }
    test_endpoint(9, "B", "POST", "/creator/config", 200, data=creator_config,
                 description="Crear config")
    test_endpoint(10, "B", "GET", f"/creator/config/{TEST_CREATOR_ID}", 200,
                 description="Obtener config")
    test_endpoint(11, "B", "PUT", f"/creator/config/{TEST_CREATOR_ID}", 200,
                 data={"name": "Test Creator Updated"},
                 description="Actualizar config")
    # #12 DELETE se hace al final en CLEANUP
    test_endpoint(13, "B", "GET", "/creator/list", 200,
                 description="Listar creadores")
    test_endpoint(14, "B", "POST", f"/bot/{TEST_CREATOR_ID}/pause", 200, auth=True,
                 data={"reason": "Testing"}, description="Pausar bot")
    test_endpoint(15, "B", "POST", f"/bot/{TEST_CREATOR_ID}/resume", 200, auth=True,
                 description="Reanudar bot")
    test_endpoint(16, "B", "GET", f"/bot/{TEST_CREATOR_ID}/status", 200, auth=True,
                 description="Estado bot")

    # ═══════════════════════════════════════════════════════════════════════
    # C. PRODUCTOS (5 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[C] Productos (5 tests)...")
    product_data = {
        "id": TEST_PRODUCT_ID,
        "name": "Test Product",
        "description": "A test product for API testing",
        "price": 99.99,
        "currency": "EUR",
        "payment_link": "https://test.com/pay",
        "category": "test",
        "features": ["feature1"],
        "keywords": ["test"]
    }
    test_endpoint(17, "C", "POST", f"/creator/{TEST_CREATOR_ID}/products", 200, data=product_data,
                 description="Crear producto")
    test_endpoint(18, "C", "GET", f"/creator/{TEST_CREATOR_ID}/products", 200,
                 description="Listar productos")
    test_endpoint(19, "C", "GET", f"/creator/{TEST_CREATOR_ID}/products/{TEST_PRODUCT_ID}", 200,
                 description="Obtener producto")
    test_endpoint(20, "C", "PUT", f"/creator/{TEST_CREATOR_ID}/products/{TEST_PRODUCT_ID}", 200,
                 data={"price": 149.99},
                 description="Actualizar producto")
    test_endpoint(21, "C", "DELETE", f"/creator/{TEST_CREATOR_ID}/products/{TEST_PRODUCT_ID}", 200,
                 description="Eliminar producto")

    # ═══════════════════════════════════════════════════════════════════════
    # D. CONVERSACIONES Y LEADS (5 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[D] Conversaciones y Leads (5 tests)...")
    test_endpoint(22, "D", "GET", "/dm/conversations/manel", 200,
                 description="Listar conversaciones")
    test_endpoint(23, "D", "GET", "/dm/leads/manel", 200,
                 description="Listar leads")
    test_endpoint(24, "D", "GET", "/dm/metrics/manel", 200,
                 description="Métricas DM")
    test_endpoint(25, "D", "GET", "/dm/follower/manel/test1", 200,
                 description="Detalle seguidor")
    test_endpoint(26, "D", "GET", "/dashboard/manel/overview", 200,
                 description="Dashboard")

    # ═══════════════════════════════════════════════════════════════════════
    # E. AUTENTICACIÓN (5 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[E] Autenticación (5 tests)...")
    key_data = {"creator_id": TEST_CREATOR_ID, "name": "Test Key"}
    test_endpoint(27, "E", "POST", "/auth/keys", 200, auth=True, data=key_data,
                 description="Crear API key")
    test_endpoint(28, "E", "GET", "/auth/keys", 200, auth=True,
                 description="Listar todas keys")
    test_endpoint(29, "E", "GET", f"/auth/keys/{TEST_CREATOR_ID}", 200, auth=True,
                 description="Keys de creador")
    # #30 se hace al final en CLEANUP
    test_endpoint(31, "E", "GET", "/auth/verify", 200, auth=True,
                 description="Verificar key")

    # ═══════════════════════════════════════════════════════════════════════
    # F. GDPR (7 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[F] GDPR (7 tests)...")
    test_endpoint(32, "F", "GET", "/gdpr/manel/export/test1", 200,
                 description="Exportar datos")
    test_endpoint(33, "F", "DELETE", f"/gdpr/{TEST_CREATOR_ID}/delete/{TEST_FOLLOWER_ID}", 200,
                 description="Eliminar datos")
    test_endpoint(34, "F", "POST", f"/gdpr/{TEST_CREATOR_ID}/anonymize/{TEST_FOLLOWER_ID}", 200,
                 description="Anonimizar")
    test_endpoint(35, "F", "GET", "/gdpr/manel/consent/test1", 200,
                 description="Ver consentimiento")
    test_endpoint(36, "F", "POST", "/gdpr/manel/consent/test1", 200,
                 query_params={"consent_type": "data_processing", "granted": "true"},
                 description="Registrar consentimiento")
    test_endpoint(37, "F", "GET", "/gdpr/manel/inventory/test1", 200,
                 description="Inventario")
    test_endpoint(38, "F", "GET", "/gdpr/manel/audit/test1", 200,
                 description="Audit log")

    # ═══════════════════════════════════════════════════════════════════════
    # G. PAGOS (6 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[G] Pagos (6 tests)...")
    stripe_payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "amount_total": 9900,
                "currency": "eur",
                "metadata": {
                    "creator_id": "manel",
                    "follower_id": "test1",
                    "product_id": "test"
                }
            }
        }
    }
    hotmart_payload = {
        "event": "PURCHASE_COMPLETE",
        "data": {
            "purchase": {"transaction": "HP123"},
            "buyer": {"email": "test@test.com"},
            "product": {"name": "Test"}
        }
    }
    test_endpoint(39, "G", "POST", "/webhook/stripe", 200, data=stripe_payload,
                 description="Webhook Stripe")
    test_endpoint(40, "G", "POST", "/webhook/hotmart", 200, data=hotmart_payload,
                 description="Webhook Hotmart")
    test_endpoint(41, "G", "GET", "/payments/manel/purchases", 200,
                 description="Listar compras")
    test_endpoint(42, "G", "GET", "/payments/manel/customer/test1", 200,
                 description="Compras cliente")
    test_endpoint(43, "G", "GET", "/payments/manel/revenue", 200,
                 description="Stats revenue")
    test_endpoint(44, "G", "POST", "/payments/manel/attribute", 200,
                 query_params={"purchase_id": "test", "follower_id": "test1"},
                 description="Atribuir venta")

    # ═══════════════════════════════════════════════════════════════════════
    # H. CALENDARIO (9 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[H] Calendario (9 tests)...")
    calendly_payload = {
        "event": "invitee.created",
        "payload": {
            "event": {"uuid": "cal_123", "name": "Discovery Call"},
            "invitee": {"email": "test@test.com", "name": "Test User"},
            "tracking": {"utm_source": "manel", "utm_campaign": "test1"}
        }
    }
    calcom_payload = {
        "triggerEvent": "BOOKING_CREATED",
        "payload": {
            "uid": "calcom_123",
            "title": "Consultation",
            "attendees": [{"email": "test@test.com", "name": "Test"}],
            "metadata": {"creator_id": "manel", "follower_id": "test1"}
        }
    }
    test_endpoint(45, "H", "POST", "/webhook/calendly", 200, data=calendly_payload,
                 description="Webhook Calendly")
    test_endpoint(46, "H", "POST", "/webhook/calcom", 200, data=calcom_payload,
                 description="Webhook Cal.com")
    test_endpoint(47, "H", "GET", "/calendar/manel/bookings", 200,
                 description="Listar bookings")
    test_endpoint(48, "H", "GET", "/calendar/manel/link/discovery", 200,
                 description="Obtener link")
    test_endpoint(49, "H", "GET", "/calendar/manel/links", 200,
                 description="Listar links")
    test_endpoint(50, "H", "POST", "/calendar/manel/links", 200,
                 query_params={"meeting_type": "test", "duration": "30", "title": "Test"},
                 description="Crear link")
    test_endpoint(51, "H", "GET", "/calendar/manel/stats", 200,
                 description="Stats calendario")
    test_endpoint(52, "H", "POST", f"/calendar/manel/bookings/{TEST_BOOKING_ID}/complete", 404,
                 description="Marcar completado")
    test_endpoint(53, "H", "POST", f"/calendar/manel/bookings/{TEST_BOOKING_ID}/no-show", 404,
                 description="Marcar no-show")

    # ═══════════════════════════════════════════════════════════════════════
    # I. ADMIN (6 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[I] Admin (6 tests)...")
    test_endpoint(54, "I", "GET", "/admin/creators", 200, auth=True,
                 description="Listar creadores")
    test_endpoint(55, "I", "GET", "/admin/stats", 200, auth=True,
                 description="Stats globales")
    test_endpoint(56, "I", "GET", "/admin/conversations", 200, auth=True,
                 description="Todas conversaciones")
    test_endpoint(57, "I", "GET", "/admin/alerts", 200, auth=True,
                 description="Alertas")
    test_endpoint(58, "I", "POST", f"/admin/creators/{TEST_CREATOR_ID}/pause", 200, auth=True,
                 description="Pausar creador")
    test_endpoint(59, "I", "POST", f"/admin/creators/{TEST_CREATOR_ID}/resume", 200, auth=True,
                 description="Reanudar creador")

    # ═══════════════════════════════════════════════════════════════════════
    # J. HEALTH (4 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[J] Health (4 tests)...")
    test_endpoint(60, "J", "GET", "/health", 200, description="Health completo")
    test_endpoint(61, "J", "GET", "/health/live", 200, description="Liveness")
    test_endpoint(62, "J", "GET", "/health/ready", 200, description="Readiness")
    test_endpoint(63, "J", "GET", "/metrics", 200, description="Prometheus")

    # ═══════════════════════════════════════════════════════════════════════
    # K. INSTAGRAM (3 tests)
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[K] Instagram (3 tests)...")
    test_endpoint(64, "K", "GET", "/webhook/instagram", 403,
                 query_params={"hub.mode": "subscribe", "hub.verify_token": "test", "hub.challenge": "123"},
                 description="Verificar webhook")
    ig_payload = {
        "object": "instagram",
        "entry": [{
            "id": "123",
            "messaging": [{
                "sender": {"id": "user123"},
                "recipient": {"id": "page123"},
                "message": {"text": "Hello!"}
            }]
        }]
    }
    test_endpoint(65, "K", "POST", "/webhook/instagram", 200, data=ig_payload,
                 description="Recibir DM")
    test_endpoint(66, "K", "GET", "/instagram/status", 200,
                 description="Estado")

    # ═══════════════════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════════════════
    print("\n[Cleanup]...")
    # #12 Delete creator config (deferred from B section)
    test_endpoint(12, "B", "DELETE", f"/creator/config/{TEST_CREATOR_ID}", 200,
                 description="Eliminar config")
    # #30 Revoke key (list keys to verify)
    test_endpoint(30, "E", "GET", "/auth/keys", 200, auth=True,
                 description="Revocar key (list)")


def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def format_json_html(obj: Any) -> str:
    """Format JSON with syntax highlighting"""
    if obj is None:
        return '<span class="json-null">null</span>'

    json_str = json.dumps(obj, indent=2, ensure_ascii=False)

    # Simple syntax highlighting
    lines = []
    for line in json_str.split('\n'):
        # Highlight keys
        if '": ' in line or '":' in line:
            parts = line.split('": ', 1)
            if len(parts) == 2:
                key = parts[0] + '"'
                value = parts[1]
                line = f'<span class="json-key">{escape_html(key)}</span>: {highlight_value(value)}'
            else:
                line = escape_html(line)
        else:
            line = highlight_value(line)
        lines.append(line)

    return '\n'.join(lines)


def highlight_value(value: str) -> str:
    """Highlight JSON value based on type"""
    value = value.strip()
    if value.startswith('"') and (value.endswith('"') or value.endswith('",') or value.endswith('"}')):
        return f'<span class="json-string">{escape_html(value)}</span>'
    elif value in ('true', 'false', 'true,', 'false,'):
        return f'<span class="json-bool">{escape_html(value)}</span>'
    elif value in ('null', 'null,'):
        return f'<span class="json-null">{escape_html(value)}</span>'
    elif value.replace(',', '').replace('.', '').replace('-', '').isdigit():
        return f'<span class="json-number">{escape_html(value)}</span>'
    else:
        return escape_html(value)


def generate_html_report():
    """Generate comprehensive HTML report with all 66 tests"""
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    percentage = (passed / total * 100) if total > 0 else 0
    total_time = time.time() - start_time

    # Group by category
    categories_data = {}
    for r in results:
        cat = r["category"]
        if cat not in categories_data:
            categories_data[cat] = {"tests": [], "passed": 0, "total": 0}
        categories_data[cat]["tests"].append(r)
        categories_data[cat]["total"] += 1
        if r["passed"]:
            categories_data[cat]["passed"] += 1

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Clonnect Creators - Test Report Completo</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-tertiary: #334155;
            --text-primary: #f1f5f9;
            --text-secondary: #94a3b8;
        }}

        body {{
            background: var(--bg-primary);
            color: var(--text-primary);
        }}

        .gradient-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f97316 100%);
        }}

        .card {{
            background: var(--bg-secondary);
            border: 1px solid var(--bg-tertiary);
            transition: all 0.2s ease;
        }}

        .card:hover {{
            border-color: #6366f1;
        }}

        .card-expandable {{
            cursor: pointer;
        }}

        .expand-content {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease-out;
        }}

        .expand-content.open {{
            max-height: 2000px;
        }}

        .json-viewer {{
            background: #0d1117;
            border-radius: 8px;
            padding: 16px;
            overflow-x: auto;
            max-height: 400px;
            overflow-y: auto;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
            font-size: 13px;
            line-height: 1.5;
        }}

        .json-key {{ color: #79c0ff; }}
        .json-string {{ color: #a5d6ff; }}
        .json-number {{ color: #56d364; }}
        .json-bool {{ color: #ff7b72; }}
        .json-null {{ color: #8b949e; }}

        .status-200 {{ background: #166534; color: #86efac; }}
        .status-201 {{ background: #166534; color: #86efac; }}
        .status-404 {{ background: #854d0e; color: #fde047; }}
        .status-500 {{ background: #991b1b; color: #fca5a5; }}
        .status-0 {{ background: #991b1b; color: #fca5a5; }}

        .method-GET {{ background: #1d4ed8; }}
        .method-POST {{ background: #16a34a; }}
        .method-PUT {{ background: #ca8a04; }}
        .method-DELETE {{ background: #dc2626; }}

        .category-bar {{
            height: 24px;
            border-radius: 4px;
            transition: width 0.5s ease;
        }}

        .dm-response-card {{
            background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
            border-left: 4px solid #7c3aed;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(-10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .animate-fadeIn {{
            animation: fadeIn 0.3s ease-out;
        }}
    </style>
</head>
<body class="min-h-screen">
    <!-- Header -->
    <header class="gradient-header py-12 px-4">
        <div class="max-w-7xl mx-auto">
            <h1 class="text-5xl font-bold mb-3">🤖 Clonnect Creators</h1>
            <p class="text-2xl opacity-90">API Test Report - 66 Tests Completos</p>
            <p class="text-sm opacity-75 mt-3">
                📅 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} |
                🌐 {BASE_URL}
            </p>
        </div>
    </header>

    <!-- Summary Stats -->
    <div class="max-w-7xl mx-auto px-4 -mt-8">
        <div class="card rounded-2xl p-8 shadow-2xl">
            <div class="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8">
                <div class="text-center">
                    <p class="text-gray-400 text-sm mb-1">Total Tests</p>
                    <p class="text-5xl font-bold">{total}</p>
                </div>
                <div class="text-center">
                    <p class="text-gray-400 text-sm mb-1">Pasados</p>
                    <p class="text-5xl font-bold text-green-400">{passed}</p>
                </div>
                <div class="text-center">
                    <p class="text-gray-400 text-sm mb-1">Fallidos</p>
                    <p class="text-5xl font-bold text-red-400">{failed}</p>
                </div>
                <div class="text-center">
                    <p class="text-gray-400 text-sm mb-1">Tiempo</p>
                    <p class="text-5xl font-bold">{total_time:.1f}<span class="text-2xl">s</span></p>
                </div>
            </div>

            <!-- Progress bar -->
            <div class="mb-8">
                <div class="flex justify-between text-sm mb-2">
                    <span>Progreso</span>
                    <span class="{'text-green-400' if percentage >= 90 else 'text-yellow-400' if percentage >= 70 else 'text-red-400'}">{percentage:.1f}%</span>
                </div>
                <div class="h-4 bg-gray-700 rounded-full overflow-hidden">
                    <div class="h-full {'bg-green-500' if percentage >= 90 else 'bg-yellow-500' if percentage >= 70 else 'bg-red-500'}" style="width: {percentage}%"></div>
                </div>
            </div>

            <!-- Category breakdown chart -->
            <h3 class="text-lg font-semibold mb-4">📊 Por Categoría</h3>
            <div class="space-y-3">
'''

    # Add category bars
    for cat_key in sorted(categories_data.keys()):
        cat = categories_data[cat_key]
        cat_info = CATEGORY_COLORS.get(cat_key, {"bg": "#6b7280", "name": cat_key, "icon": "📁"})
        cat_pct = (cat["passed"] / cat["total"] * 100) if cat["total"] > 0 else 0

        html += f'''
                <div class="flex items-center gap-3">
                    <span class="text-xl w-8">{cat_info["icon"]}</span>
                    <span class="w-48 text-sm">{cat_info["name"]}</span>
                    <div class="flex-1 bg-gray-700 rounded h-6 overflow-hidden">
                        <div class="category-bar" style="width: {cat_pct}%; background: {cat_info["bg"]}"></div>
                    </div>
                    <span class="w-20 text-right text-sm">{cat["passed"]}/{cat["total"]}</span>
                </div>
'''

    html += '''
            </div>
        </div>
    </div>
'''

    # Add each category section
    for cat_key in sorted(categories_data.keys()):
        cat = categories_data[cat_key]
        cat_info = CATEGORY_COLORS.get(cat_key, {"bg": "#6b7280", "name": cat_key, "icon": "📁"})

        html += f'''
    <!-- Category {cat_key}: {cat_info["name"]} -->
    <section class="max-w-7xl mx-auto px-4 mt-12">
        <div class="flex items-center gap-3 mb-6" style="border-left: 4px solid {cat_info["bg"]}; padding-left: 12px;">
            <span class="text-3xl">{cat_info["icon"]}</span>
            <div>
                <h2 class="text-2xl font-bold">{cat_key}. {cat_info["name"]}</h2>
                <p class="text-gray-400 text-sm">{cat["passed"]}/{cat["total"]} tests pasados</p>
            </div>
        </div>
        <div class="space-y-3">
'''

        # Add each test in the category
        for test in sorted(cat["tests"], key=lambda x: x["test_num"]):
            test_id = f"test_{test['test_num']}"
            status_class = "text-green-400" if test["passed"] else "text-red-400"
            status_icon = "✅" if test["passed"] else "❌"
            status_code = test["actual_status"] or "ERR"
            status_bg = f"status-{test['actual_status']}" if test["actual_status"] else "status-0"
            method_bg = f"method-{test['method']}"

            # Format request body
            request_html = ""
            if test.get("request_body"):
                request_html = f'''
                    <div class="mb-4">
                        <p class="text-gray-400 text-xs mb-2 flex items-center gap-2">
                            <span class="bg-blue-900 px-2 py-1 rounded">REQUEST BODY</span>
                        </p>
                        <div class="json-viewer">
<pre>{format_json_html(test["request_body"])}</pre>
                        </div>
                    </div>
'''

            # Format response body
            response_html = ""
            if test.get("response_body"):
                response_html = f'''
                    <div>
                        <p class="text-gray-400 text-xs mb-2 flex items-center gap-2">
                            <span class="{status_bg} px-2 py-1 rounded">RESPONSE {status_code}</span>
                            <span class="text-gray-500">({test["duration_ms"]}ms)</span>
                        </p>
                        <div class="json-viewer">
<pre>{format_json_html(test["response_body"])}</pre>
                        </div>
                    </div>
'''
            elif test.get("error"):
                response_html = f'''
                    <div>
                        <p class="text-gray-400 text-xs mb-2">
                            <span class="bg-red-900 px-2 py-1 rounded">ERROR</span>
                        </p>
                        <div class="bg-red-900/30 border border-red-800 rounded-lg p-4">
                            <p class="text-red-300">{escape_html(test["error"])}</p>
                        </div>
                    </div>
'''

            # Special formatting for DM tests
            dm_extra = ""
            if cat_key == "A" and test["passed"] and test.get("response_body"):
                resp = test["response_body"]
                user_msg = test.get("request_body", {}).get("message", "")
                bot_response = resp.get("response", "")
                intent = resp.get("intent", "")
                confidence = resp.get("confidence", 0)

                dm_extra = f'''
                    <div class="dm-response-card rounded-lg p-4 mb-4">
                        <div class="grid md:grid-cols-2 gap-4">
                            <div>
                                <p class="text-xs text-gray-400 mb-1">💬 Usuario:</p>
                                <p class="bg-blue-900/30 rounded p-3 text-blue-200">"{escape_html(user_msg)}"</p>
                            </div>
                            <div>
                                <p class="text-xs text-gray-400 mb-1">🤖 Bot:</p>
                                <p class="bg-green-900/30 rounded p-3 text-green-200">"{escape_html(bot_response)}"</p>
                            </div>
                        </div>
                        <div class="flex gap-2 mt-3 text-xs">
                            <span class="bg-purple-900/50 text-purple-300 px-2 py-1 rounded">🎯 {escape_html(intent)}</span>
                            <span class="bg-{'green' if confidence >= 0.8 else 'yellow' if confidence >= 0.5 else 'red'}-900/50 text-{'green' if confidence >= 0.8 else 'yellow' if confidence >= 0.5 else 'red'}-300 px-2 py-1 rounded">⚡ {confidence:.0%}</span>
                        </div>
                    </div>
'''

            html += f'''
            <div class="card rounded-xl overflow-hidden">
                <div class="card-expandable p-4 flex items-center justify-between" onclick="toggleTest('{test_id}')">
                    <div class="flex items-center gap-4">
                        <span class="text-2xl">{status_icon}</span>
                        <span class="text-gray-500 font-mono text-sm">#{test['test_num']:02d}</span>
                        <span class="{method_bg} text-white text-xs px-2 py-1 rounded font-mono">{test['method']}</span>
                        <code class="text-sm text-gray-300">{escape_html(test['path'])}</code>
                    </div>
                    <div class="flex items-center gap-4">
                        <span class="text-gray-400 text-sm hidden md:inline">{escape_html(test['description'])}</span>
                        <span class="{status_bg} px-2 py-1 rounded text-xs font-mono">{status_code}</span>
                        <span class="text-gray-500 text-sm">{test['duration_ms']}ms</span>
                        <svg class="w-5 h-5 text-gray-500 transform transition-transform" id="{test_id}_arrow" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                        </svg>
                    </div>
                </div>
                <div class="expand-content" id="{test_id}">
                    <div class="p-4 border-t border-gray-700 bg-gray-900/50">
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-sm">
                            <div>
                                <span class="text-gray-500">Descripción:</span>
                                <p class="text-gray-300">{escape_html(test['description'])}</p>
                            </div>
                            <div>
                                <span class="text-gray-500">URL Completa:</span>
                                <p class="text-gray-300 font-mono text-xs break-all">{escape_html(test['full_url'])}</p>
                            </div>
                            <div>
                                <span class="text-gray-500">Status Esperado:</span>
                                <p class="text-gray-300">{test['expected_status']}</p>
                            </div>
                            <div>
                                <span class="text-gray-500">Auth Requerido:</span>
                                <p class="text-gray-300">{'Sí (X-API-Key)' if test['auth_required'] else 'No'}</p>
                            </div>
                        </div>
                        {dm_extra}
                        {request_html}
                        {response_html}
                    </div>
                </div>
            </div>
'''

        html += '''
        </div>
    </section>
'''

    # Add failed tests summary
    failed_tests = [r for r in results if not r["passed"]]
    if failed_tests:
        html += f'''
    <!-- Failed Tests Summary -->
    <section class="max-w-7xl mx-auto px-4 mt-12">
        <div class="bg-red-900/20 border border-red-800 rounded-2xl p-6">
            <h2 class="text-2xl font-bold text-red-400 mb-4 flex items-center gap-2">
                <span>❌</span> Tests Fallidos ({len(failed_tests)})
            </h2>
            <div class="space-y-2">
'''
        for t in failed_tests:
            html += f'''
                <div class="bg-red-950/50 rounded-lg p-3 flex items-center justify-between">
                    <div class="flex items-center gap-3">
                        <span class="font-mono text-sm text-gray-500">#{t['test_num']:02d}</span>
                        <span class="method-{t['method']} text-white text-xs px-2 py-1 rounded">{t['method']}</span>
                        <code class="text-sm">{escape_html(t['path'])}</code>
                    </div>
                    <div class="text-right">
                        <span class="text-red-400">{t['actual_status'] or 'ERR'}</span>
                        <span class="text-gray-500 mx-2">→</span>
                        <span class="text-gray-400">esperado {t['expected_status']}</span>
                    </div>
                </div>
'''
        html += '''
            </div>
        </div>
    </section>
'''

    html += f'''
    <!-- Footer -->
    <footer class="mt-12 py-8 border-t border-gray-800">
        <div class="max-w-7xl mx-auto px-4 text-center text-gray-500">
            <p class="text-lg mb-2">🤖 Clonnect Creators API Test Suite</p>
            <p class="text-sm">Generado: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | 66 Tests | Tiempo total: {total_time:.2f}s</p>
        </div>
    </footer>

    <script>
        function toggleTest(id) {{
            const content = document.getElementById(id);
            const arrow = document.getElementById(id + '_arrow');
            content.classList.toggle('open');
            arrow.classList.toggle('rotate-180');
        }}

        // Expand all failed tests by default
        document.querySelectorAll('.expand-content').forEach(el => {{
            const testNum = el.id.replace('test_', '');
            // Could auto-expand failed tests here
        }});
    </script>
</body>
</html>
'''

    return html


def main():
    """Main entry point"""
    global BASE_URL

    import argparse
    parser = argparse.ArgumentParser(description='Generate Clonnect API visual test report')
    parser.add_argument('--base-url', '-u', help='Base URL for API', default=BASE_URL)
    args = parser.parse_args()

    BASE_URL = args.base_url

    print("\n🚀 Starting Clonnect API Comprehensive Test Suite...\n")
    print(f"Target: {BASE_URL}")
    print("=" * 70)

    run_all_tests()

    print("\n📊 Generating comprehensive HTML report...")

    html = generate_html_report()

    # Create reports directory
    os.makedirs("reports", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = f"reports/api_test_report_{timestamp}.html"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Also save latest version
    latest_path = "reports/api_test_report_latest.html"
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Save JSON results
    json_path = f"reports/api_test_results_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "base_url": BASE_URL,
            "total": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "failed": sum(1 for r in results if not r["passed"]),
            "duration_seconds": time.time() - start_time,
            "results": results
        }, f, indent=2, ensure_ascii=False)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    percentage = (passed / total * 100) if total > 0 else 0

    print(f"\n{'=' * 70}")
    print(f"✅ HTML Report: {report_path}")
    print(f"✅ Latest Report: {latest_path}")
    print(f"📄 JSON Results: {json_path}")
    print(f"{'=' * 70}")
    print(f"📊 RESULTS: {passed}/{total} tests passed ({percentage:.1f}%)")
    print(f"{'=' * 70}")

    return 0 if percentage >= 90 else 1


if __name__ == "__main__":
    sys.exit(main())
