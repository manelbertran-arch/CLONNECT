"""Static pages and utility endpoints"""
import os

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(tags=["static"])

VERSION = "1.0.0"


@router.get("/api")
def api_info():
    """API info - moved to /api to let root serve frontend"""
    return {
        "name": "Clonnect Creators API",
        "version": VERSION,
        "description": "Tu clon de IA para responder DMs de Instagram",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
        "privacy": "/privacy",
        "terms": "/terms",
    }


@router.get("/")
async def serve_root():
    """Serve frontend index.html for root"""
    _static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
    index_path = os.path.join(_static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"error": "Frontend not found"}


# =============================================================================
# LEGAL PAGES (Privacy & Terms)
# =============================================================================

@router.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    """Privacy Policy page"""
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Política de Privacidad - Clonnect Creators</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; line-height: 1.6; color: #333; }
        h1 { color: #1a1a2e; border-bottom: 2px solid #4a4e69; padding-bottom: 10px; }
        h2 { color: #4a4e69; margin-top: 30px; }
        .updated { color: #666; font-size: 0.9em; }
        a { color: #4a4e69; }
    </style>
</head>
<body>
    <h1>Política de Privacidad</h1>
    <p class="updated">Última actualización: Diciembre 2024</p>

    <h2>1. Información que Recopilamos</h2>
    <p>Clonnect Creators recopila la siguiente información:</p>
    <ul>
        <li><strong>Datos de conversación:</strong> Mensajes enviados a través de Instagram, Telegram o WhatsApp para proporcionar respuestas automatizadas.</li>
        <li><strong>Identificadores de usuario:</strong> IDs de plataforma para mantener el contexto de la conversación.</li>
        <li><strong>Datos de interacción:</strong> Intenciones detectadas, productos de interés y estado de la conversación.</li>
    </ul>

    <h2>2. Uso de la Información</h2>
    <p>Utilizamos la información recopilada para:</p>
    <ul>
        <li>Proporcionar respuestas automatizadas personalizadas</li>
        <li>Mejorar la calidad de las interacciones</li>
        <li>Generar métricas agregadas para el creador de contenido</li>
        <li>Detectar y prevenir abusos del servicio</li>
    </ul>

    <h2>3. Compartición de Datos</h2>
    <p>No vendemos ni compartimos datos personales con terceros, excepto:</p>
    <ul>
        <li>Con el creador de contenido cuyo bot estás usando</li>
        <li>Proveedores de servicios esenciales (hosting, LLM)</li>
        <li>Cuando sea requerido por ley</li>
    </ul>

    <h2>4. Retención de Datos</h2>
    <p>Los datos de conversación se retienen por un máximo de 90 días para mantener el contexto.
    Puedes solicitar la eliminación de tus datos en cualquier momento.</p>

    <h2>5. Derechos GDPR</h2>
    <p>Si eres residente de la UE, tienes derecho a:</p>
    <ul>
        <li><strong>Acceso:</strong> Solicitar una copia de tus datos</li>
        <li><strong>Rectificación:</strong> Corregir datos inexactos</li>
        <li><strong>Supresión:</strong> Solicitar la eliminación de tus datos</li>
        <li><strong>Portabilidad:</strong> Recibir tus datos en formato estructurado</li>
        <li><strong>Oposición:</strong> Oponerte al procesamiento de tus datos</li>
    </ul>
    <p>Para ejercer estos derechos, contacta al creador de contenido o envía un email con tu solicitud.</p>

    <h2>6. Seguridad</h2>
    <p>Implementamos medidas de seguridad técnicas y organizativas para proteger tus datos,
    incluyendo encriptación en tránsito y almacenamiento seguro.</p>

    <h2>7. Cookies</h2>
    <p>Esta API no utiliza cookies. Las plataformas de mensajería (Instagram, Telegram, WhatsApp)
    tienen sus propias políticas de cookies.</p>

    <h2>8. Cambios a esta Política</h2>
    <p>Podemos actualizar esta política ocasionalmente. Los cambios significativos serán comunicados
    a través de los canales apropiados.</p>

    <h2>9. Contacto</h2>
    <p>Para preguntas sobre esta política de privacidad, contacta al creador de contenido
    que utiliza este servicio.</p>

    <p style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd;">
        <a href="/">← Volver al inicio</a> | <a href="/terms">Términos de Servicio</a>
    </p>
</body>
</html>"""


@router.get("/terms", response_class=HTMLResponse)
def terms_of_service():
    """Terms of Service page"""
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Términos de Servicio - Clonnect Creators</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; line-height: 1.6; color: #333; }
        h1 { color: #1a1a2e; border-bottom: 2px solid #4a4e69; padding-bottom: 10px; }
        h2 { color: #4a4e69; margin-top: 30px; }
        .updated { color: #666; font-size: 0.9em; }
        a { color: #4a4e69; }
    </style>
</head>
<body>
    <h1>Términos de Servicio</h1>
    <p class="updated">Última actualización: Diciembre 2024</p>

    <h2>1. Aceptación de los Términos</h2>
    <p>Al interactuar con un bot de Clonnect Creators, aceptas estos términos de servicio.
    Si no estás de acuerdo, por favor no utilices el servicio.</p>

    <h2>2. Descripción del Servicio</h2>
    <p>Clonnect Creators proporciona respuestas automatizadas mediante inteligencia artificial
    en nombre de creadores de contenido. El servicio:</p>
    <ul>
        <li>Responde mensajes directos de forma automatizada</li>
        <li>Proporciona información sobre productos y servicios del creador</li>
        <li>Facilita la comunicación inicial antes de intervención humana</li>
    </ul>

    <h2>3. Naturaleza del Bot</h2>
    <p><strong>Importante:</strong> Las respuestas son generadas por inteligencia artificial,
    no directamente por el creador de contenido. Aunque el bot está entrenado para representar
    al creador, las respuestas pueden no reflejar exactamente sus opiniones.</p>

    <h2>4. Uso Aceptable</h2>
    <p>Al usar el servicio, te comprometes a NO:</p>
    <ul>
        <li>Enviar contenido ilegal, ofensivo o spam</li>
        <li>Intentar manipular o engañar al sistema de IA</li>
        <li>Usar el servicio para actividades fraudulentas</li>
        <li>Intentar extraer información del sistema o realizar ataques</li>
        <li>Suplantar la identidad de otras personas</li>
    </ul>

    <h2>5. Limitaciones del Servicio</h2>
    <p>El servicio se proporciona "tal cual". No garantizamos:</p>
    <ul>
        <li>Disponibilidad ininterrumpida del servicio</li>
        <li>Precisión completa de las respuestas de IA</li>
        <li>Tiempos de respuesta específicos</li>
    </ul>

    <h2>6. Propiedad Intelectual</h2>
    <p>El contenido generado por el bot pertenece al creador de contenido.
    La tecnología de Clonnect Creators está protegida por derechos de autor.</p>

    <h2>7. Privacidad</h2>
    <p>El uso de tus datos está regido por nuestra <a href="/privacy">Política de Privacidad</a>.
    Al usar el servicio, consientes el procesamiento de datos según dicha política.</p>

    <h2>8. Compras y Transacciones</h2>
    <p>Si realizas compras a través de enlaces proporcionados por el bot:</p>
    <ul>
        <li>Las transacciones se procesan a través de plataformas de terceros (Stripe, Hotmart)</li>
        <li>Los términos de compra del creador y la plataforma de pago aplican</li>
        <li>Clonnect Creators no es responsable de disputas de compra</li>
    </ul>

    <h2>9. Limitación de Responsabilidad</h2>
    <p>En la máxima medida permitida por la ley, Clonnect Creators no será responsable por:</p>
    <ul>
        <li>Daños indirectos, incidentales o consecuentes</li>
        <li>Pérdida de datos o interrupción del servicio</li>
        <li>Acciones tomadas basándose en respuestas del bot</li>
    </ul>

    <h2>10. Modificaciones</h2>
    <p>Nos reservamos el derecho de modificar estos términos en cualquier momento.
    El uso continuado del servicio constituye aceptación de los términos modificados.</p>

    <h2>11. Terminación</h2>
    <p>Podemos suspender o terminar el acceso al servicio si violas estos términos,
    sin previo aviso ni responsabilidad.</p>

    <h2>12. Ley Aplicable</h2>
    <p>Estos términos se rigen por las leyes aplicables en la jurisdicción del creador de contenido.</p>

    <h2>13. Contacto</h2>
    <p>Para preguntas sobre estos términos, contacta al creador de contenido que utiliza este servicio.</p>

    <p style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd;">
        <a href="/">← Volver al inicio</a> | <a href="/privacy">Política de Privacidad</a>
    </p>
</body>
</html>"""


# =============================================================================
# PROMETHEUS METRICS
# =============================================================================

@router.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format.
    Scrape this endpoint with Prometheus server.

    Example prometheus.yml config:
    ```
    scrape_configs:
      - job_name: 'clonnect-creators'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/metrics'
    ```
    """
    from core.metrics import get_content_type, get_metrics
    return Response(content=get_metrics(), media_type=get_content_type())
