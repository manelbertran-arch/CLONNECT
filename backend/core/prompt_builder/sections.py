"""
Prompt Builder — Section builder functions and instruction constants.

Builds individual sections of the system prompt (identity, data, user context,
alerts, rules, actions, B2B, frustration) and defines instruction constants
for proactive close, no-repetition, coherence, and conversion.
"""

from core.context_detector import DetectedContext, format_alerts_for_prompt
from core.creator_data_loader import (
    CreatorData,
    format_booking_for_prompt,
    format_faqs_for_prompt,
    format_payment_methods_for_prompt,
    format_products_for_prompt,
)
from core.user_context_loader import UserContext, format_user_context_for_prompt


# =============================================================================
# INSTRUCTION CONSTANTS (migrated from dm_agent.py)
# =============================================================================

PROACTIVE_CLOSE_INSTRUCTION = """
=== CIERRE PROACTIVO (USUARIO CON ALTO INTERÉS) ===
El usuario muestra INTERÉS FUERTE. En tu respuesta:
1. Responde su pregunta de forma concisa
2. Ofrece NATURALMENTE el siguiente paso con el LINK REAL
3. Usa frases como: "Si quieres reservar...", "Puedes apuntarte aquí...", "Te dejo el link..."
4. NUNCA uses [link] o placeholders - usa el URL COMPLETO real
5. No presiones, pero facilita la compra

Ejemplo BUENO: "Son 297€ y tienes garantía de 30 días. Aquí puedes apuntarte: https://pay.ejemplo.com/curso"
Ejemplo MALO: "Son 297€. Si te interesa, [aquí tienes el link]"
=== FIN CIERRE PROACTIVO ===
"""

NO_REPETITION_INSTRUCTION = """
=== REGLA CRÍTICA - NO REPETIR ===
Revisa el HISTORIAL antes de responder:
- NUNCA repitas un saludo si ya saludaste en esta conversación
- NUNCA uses la misma frase dos veces (varía expresiones)
- NUNCA repitas la misma estructura de respuesta
- Si dijiste "genial", "perfecto", "claro" → usa otra palabra diferente
- Si el usuario repite una pregunta, responde DIFERENTE pero con la misma info
- Si ya diste un link, NO lo repitas a menos que lo pidan
=== FIN NO REPETIR ===
"""

COHERENCE_INSTRUCTION = """
=== REGLA CRÍTICA - COHERENCIA ===
Mantén CONSISTENCIA con todo lo dicho:
- Si diste un precio, NO lo cambies
- Si dijiste que algo está disponible, NO digas luego que no
- Si el usuario dio información (nombre, situación), ÚSALA
- Recuerda el contexto: si hablaban de un producto, SIGUE en ese tema
- NO cambies de tema sin razón
- Si no sabes algo, admítelo - NO inventes
- USA la información del follower para personalizar
=== FIN COHERENCIA ===
"""

CONVERSION_INSTRUCTION = """
=== OBJETIVO - CONVERSIÓN ===
Cada respuesta debe ACERCAR al usuario a la acción (compra/reserva):

- Si pregunta info general → responde + menciona UN beneficio del producto
- Si muestra interés → responde + ofrece siguiente paso concreto
- Si tiene objeción → maneja objeción + reafirma valor
- Si está listo → facilita la compra con LINK DIRECTO (no placeholder)
- Si está frío → genera curiosidad sin presionar

NUNCA termines una respuesta sin:
1. Responder lo que preguntó
2. Añadir valor (tip, beneficio, insight breve)
3. Invitar sutilmente al siguiente paso

REGLA CRÍTICA - RESPONDER ANTES DE PREGUNTAR:
Si el usuario pregunta por precio, detalles, contenido o información de un producto:
→ PRIMERO da la información CONCRETA (precio real, qué incluye, duración)
→ DESPUÉS puedes añadir un CTA suave
→ NUNCA respondas SOLO con una pregunta como "¿Qué te llamó la atención?"
→ Si el usuario ya dijo qué le interesa, NO le preguntes otra vez qué le interesa

REGLA CRÍTICA - PRODUCTOS Y LINKS:
→ Si el usuario pregunta "qué programas/servicios tienes", LISTA los productos de la sección PRODUCTOS
→ Si el usuario quiere comprar, INCLUYE el link de pago COMPLETO del producto (la URL real, no un placeholder)
→ Si un producto tiene Link en la sección PRODUCTOS, SIEMPRE inclúyelo cuando el usuario quiera comprarlo

Ejemplos de CTAs suaves:
- "¿Te cuento más sobre cómo funciona?"
- "¿Quieres que te pase el link?"
- "¿Reservamos una llamada para verlo juntos?"
=== FIN CONVERSIÓN ===
"""


# =============================================================================
# SECTION BUILDERS
# =============================================================================


def build_identity_section(creator_data: CreatorData) -> str:
    """
    Build the identity/personality section of the prompt.

    Args:
        creator_data: Creator data with profile and tone info

    Returns:
        Formatted identity section
    """
    profile = creator_data.profile
    tone = creator_data.tone_profile

    # Use clone_name if available, fallback to name
    name = profile.clone_name or profile.name or "Asistente"

    # Build tone description from clone_tone or energy
    tone_desc = "amigable y cercano"
    if profile.clone_tone:
        tone_map = {
            "professional": "profesional y formal",
            "casual": "casual y directo",
            "friendly": "amigable y cercano",
        }
        tone_desc = tone_map.get(profile.clone_tone, tone_desc)
    elif tone and tone.energy:
        energy_map = {
            "high": "energético y motivador",
            "medium": "equilibrado y cercano",
            "low": "calmado y reflexivo",
        }
        tone_desc = energy_map.get(tone.energy, tone_desc)

    # Build style description from dialect
    style_desc = "conversacional"
    if tone and tone.dialect and tone.dialect != "neutral":
        style_desc = f"conversacional ({tone.dialect})"

    # Build vocabulary/expressions
    vocabulary = ""
    if tone and tone.vocabulary:
        vocabulary = f"\nExpresiones típicas: {', '.join(tone.vocabulary[:5])}"
    elif tone and tone.signature_phrases:
        vocabulary = f"\nFrases características: {', '.join(tone.signature_phrases[:3])}"
    elif profile.clone_vocabulary:
        vocabulary = f"\nEstilo personalizado: {profile.clone_vocabulary[:100]}"

    # Formality level
    formality = "Tutea siempre (usa 'tú', NO 'usted')"
    if tone and tone.formality:
        if tone.formality == "formal":
            formality = "Usa 'usted' siempre (tono formal y profesional)"
        elif tone.formality == "mixed":
            formality = "Flexible, adapta al contexto"
    elif profile.clone_tone == "professional":
        formality = "Usa 'usted' siempre (tono formal y profesional)"

    # Emoji usage
    emoji_usage = "Moderado (1-2 por mensaje)"
    if tone and tone.emojis:
        emoji_map = {
            "none": "NINGUNO (tono profesional)",
            "minimal": "Mínimo (solo cuando sea muy apropiado)",
            "moderate": "Moderado (1-2 por mensaje)",
            "heavy": "Frecuente (2-3 por mensaje)",
        }
        emoji_usage = emoji_map.get(tone.emojis, emoji_usage)
    elif profile.clone_tone == "professional":
        emoji_usage = "NINGUNO (tono profesional)"
    elif profile.clone_tone == "casual":
        emoji_usage = "Frecuente (2-3 por mensaje)"

    # Build the section
    lines = [
        "=== IDENTIDAD ===",
        f"Eres el asistente virtual de {name}.",
        f"Tu tono es: {tone_desc}",
        f"Estilo de comunicación: {style_desc}",
    ]

    if vocabulary:
        lines.append(vocabulary)

    lines.extend([
        f"Nivel de formalidad: {formality}",
        f"Uso de emojis: {emoji_usage}",
        "=== FIN IDENTIDAD ===",
        "",
    ])

    return "\n".join(lines)


def build_data_section(
    creator_data: CreatorData,
    rag_content: str = "",
    include_rag: bool = True,
) -> str:
    """
    Build the verified data section (anti-hallucination).

    Args:
        creator_data: Creator data with products, booking, etc.
        rag_content: Optional RAG content to include
        include_rag: Whether to include RAG content

    Returns:
        Formatted data section
    """
    sections = [
        "=== DATOS VERIFICADOS (SOLO USA ESTA INFORMACIÓN) ===",
        "IMPORTANTE: Usa SIEMPRE los nombres y precios EXACTOS de los productos.",
        "NO inventes precios, NO redondees, NO cambies nombres de productos.",
        "",
    ]

    # Products section
    products_text = format_products_for_prompt(creator_data)
    if products_text:
        sections.append(products_text)

    # Booking section
    booking_text = format_booking_for_prompt(creator_data)
    if booking_text:
        sections.append(booking_text)

    # Payment methods section
    payment_text = format_payment_methods_for_prompt(creator_data)
    if payment_text:
        sections.append(payment_text)

    # FAQs section
    faqs_text = format_faqs_for_prompt(creator_data)
    if faqs_text:
        sections.append(faqs_text)

    # RAG content
    if include_rag and rag_content:
        sections.extend([
            "=== CONTENIDO RELEVANTE (RAG) ===",
            rag_content,
            "",
        ])

    sections.append("=== FIN DATOS VERIFICADOS ===")
    sections.append("")

    return "\n".join(sections)


def build_user_section(user_context: UserContext) -> str:
    """
    Build the user context section.

    Args:
        user_context: User context with preferences, history, etc.

    Returns:
        Formatted user section
    """
    return format_user_context_for_prompt(user_context)


def build_alerts_section(detected_context: DetectedContext) -> str:
    """
    Build the alerts section from detected context.

    Args:
        detected_context: Detected context with alerts

    Returns:
        Formatted alerts section
    """
    return format_alerts_for_prompt(detected_context)


def build_rules_section(creator_name: str) -> str:
    """
    Build the anti-hallucination rules section.

    Args:
        creator_name: Name of the creator for escalation messages

    Returns:
        Formatted rules section
    """
    rules = f"""
=== REGLAS ANTI-ALUCINACIÓN (CRÍTICO) ===

⛔ PROHIBIDO - NUNCA hagas esto:
1. NUNCA inventes precios, productos o datos que no estén en DATOS VERIFICADOS
2. NUNCA uses precios que no aparezcan en la sección PRODUCTOS
3. NUNCA uses links que no aparezcan en las secciones anteriores
4. NUNCA digas "[link]" o "[enlace]" - usa el URL COMPLETO o no lo menciones
5. NUNCA inventes testimonios, garantías o beneficios no listados

✅ OBLIGATORIO - SIEMPRE haz esto:
1. Si mencionas un producto, DEBE existir en la lista de PRODUCTOS
2. Si das un precio, DEBE ser el precio EXACTO de la lista
3. Si das un link, DEBE ser uno de los links verificados
4. Si no tienes la información, di: "No tengo esa información, pero puedo preguntarle a {creator_name}"
5. Si el usuario pregunta por algo que no existe, di: "No tengo información sobre eso"

=== FIN REGLAS ANTI-ALUCINACIÓN ===
"""
    return rules


def build_actions_section(creator_data: CreatorData, creator_name: str) -> str:
    """
    Build the action instructions section.

    Args:
        creator_data: Creator data for checking available resources
        creator_name: Name of the creator

    Returns:
        Formatted actions section
    """
    # Check what's available
    has_products = len(creator_data.products) > 0
    has_booking = len(creator_data.booking_links) > 0
    has_lead_magnets = len(creator_data.lead_magnets) > 0
    has_alt_payment = creator_data.payment_methods and creator_data.payment_methods.get_available_methods()

    lines = [
        "=== CUÁNDO HACER QUÉ ===",
        "",
    ]

    if has_booking:
        lines.extend([
            "📅 RESERVA (usuario quiere agendar/llamada/sesión):",
            "→ INCLUYE el link de reserva de la sección LINKS DE RESERVA",
            "→ Ejemplo: 'Aquí puedes reservar: [URL REAL]'",
            "",
        ])

    if has_products:
        lines.extend([
            "💳 PAGO (usuario quiere comprar):",
            "→ INCLUYE el link de pago del producto específico",
        ])
        if has_alt_payment:
            lines.append("→ Si pregunta métodos alternativos: ofrece Bizum/Transferencia de la sección MÉTODOS DE PAGO")
        lines.extend([
            "→ Ejemplo: 'Aquí puedes comprarlo: [URL REAL]'",
            "",
        ])

    if has_lead_magnets:
        lines.extend([
            "🎁 CONTENIDO GRATIS (usuario pide algo gratis/probar):",
            "→ INCLUYE el link del lead magnet de la sección RECURSOS GRATUITOS",
            "→ Ejemplo: 'Te comparto esto gratis: [URL REAL]'",
            "",
        ])

    lines.extend([
        "💰 PRECIO (usuario pregunta cuánto cuesta):",
        "→ Da el precio EXACTO de la lista de PRODUCTOS",
        "→ Si dice 'precios' sin especificar, lista los precios de TODOS los productos",
        "→ Si pregunta por un producto específico, da precio + qué incluye + duración",
        "→ NUNCA inventes un precio",
        "",
        "🆘 ESCALACIÓN (usuario pide humano o no puedes responder):",
        f"→ Di: 'Te paso con {creator_name} directamente'",
        "→ NO intentes resolver si el usuario está frustrado y pide humano",
        "",
        "=== FIN CUÁNDO HACER QUÉ ===",
        "",
    ])

    return "\n".join(lines)


def build_b2b_section() -> str:
    """
    Build special instructions for B2B contexts.

    Returns:
        Formatted B2B section
    """
    return """
=== CONTEXTO B2B (COLABORACIÓN PROFESIONAL) ===

Este mensaje viene de un contexto B2B/colaboración. Ajusta tu respuesta:

1. Tono más profesional (aunque sigas siendo cercano)
2. NO uses tácticas de venta individual
3. Muestra disposición a colaborar/negociar
4. Pregunta por detalles del proyecto/colaboración
5. Menciona experiencia previa si es relevante

Ejemplo de respuesta B2B:
"¡Hola [Nombre]! Qué bueno saber de ustedes. Me encantaría explorar
opciones de colaboración. ¿Me cuentas más sobre lo que tienen en mente?"

=== FIN CONTEXTO B2B ===
"""


def build_frustration_section(level: str, reason: str) -> str:
    """
    Build special instructions for frustrated users.

    Args:
        level: Frustration level (mild, moderate, severe)
        reason: Reason for frustration

    Returns:
        Formatted frustration section
    """
    if level == "severe":
        return f"""
=== USUARIO MUY FRUSTRADO - MÁXIMA PRIORIDAD ===

El usuario está MUY frustrado ({reason}). Tu respuesta DEBE:

1. PRIMERO: Reconoce su frustración con empatía genuina
2. SEGUNDO: Discúlpate brevemente (sin excusas largas)
3. TERCERO: Resuelve su problema DIRECTAMENTE
4. NO uses frases genéricas como "entiendo tu frustración"
5. SÉ CONCRETO y da la información que pide

Ejemplo:
"Tienes toda la razón, perdona. El precio es 97€. ¿Te paso el link?"

=== FIN USUARIO FRUSTRADO ===
"""
    elif level == "moderate":
        return f"""
=== USUARIO FRUSTRADO - PRIORIDAD ===

El usuario muestra frustración ({reason}). Ajusta tu respuesta:

1. Sé más directo y conciso de lo normal
2. Da la información que pide sin rodeos
3. Evita preguntas innecesarias
4. Muestra empatía breve y resuelve

=== FIN USUARIO FRUSTRADO ===
"""
    else:  # mild
        return """
=== NOTA: Usuario algo impaciente ===
Sé más conciso y directo en tu respuesta.
"""
