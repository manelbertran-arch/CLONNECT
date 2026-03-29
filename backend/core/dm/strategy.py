"""
Response strategy determination for DM Agent V2.

Determines HOW the LLM should approach a response based on:
- Relationship type (family, friend, follower)
- Help signals in the message
- Purchase intent
- First message vs returning
- Ghost/reactivation
"""


def _determine_response_strategy(
    message: str,
    intent_value: str,
    relationship_type: str,
    is_first_message: bool,
    is_friend: bool,
    follower_interests: list,
    lead_stage: str,
    history_len: int = 0,
) -> str:
    """Determine response strategy to inject as LLM guidance.

    Returns a short instruction string that tells the LLM HOW to approach
    the response (not what to say). This prevents the bot from using generic
    greetings when the user clearly needs help, or selling to family.

    Strategies:
    - help: User has a concrete need/question -> answer it directly
    - personal: Family/close friend -> warm, no selling
    - greeting: First contact, no specific need -> welcome naturally
    - sales: Showing product interest -> inform + soft CTA
    - reactivation: Returning after long absence -> re-engage
    """
    msg_lower = message.lower().strip()

    # Priority 1: Family/close friends -> personal mode, never sell
    if relationship_type in ("FAMILIA", "INTIMA"):
        return (
            "ESTRATEGIA: PERSONAL-FAMILIA. Esta persona es cercana (familia/íntimo). "
            "REGLAS: 1) NUNCA vendas ni ofrezcas productos/servicios. "
            "2) Responde al CONTENIDO concreto del mensaje, no con reacciones genéricas. "
            "3) Comparte detalles reales de tu vida si vienen al caso. "
            "4) Ultra-breve: 5-30 chars máximo. "
            "5) Si preguntan algo, responde directamente sin florituras."
        )

    if is_friend:
        return (
            "ESTRATEGIA: PERSONAL-AMIGO. Esta persona es amigo/a. "
            "REGLAS: 1) No vendas. 2) Responde al contenido concreto, no genérico. "
            "3) Ultra-breve. 4) Comparte detalles si vienen al caso."
        )

    # Shared help signals used in Priority 2 and Priority 4
    help_signals = [
        "ayuda", "problema", "no funciona", "no puedo", "error",
        "cómo", "como hago", "necesito", "urgente", "no me deja",
        "no entiendo", "explícame", "explicame", "qué hago", "que hago",
    ]

    # Priority 2: BUG-12 fix — First message takes priority over generic help signals
    # so "Hola, necesito ayuda" gives BIENVENIDA + AYUDA, not just AYUDA
    if is_first_message:
        # Check if first message contains a question or help need
        if "?" in message or any(s in msg_lower for s in help_signals):
            return (
                "ESTRATEGIA: BIENVENIDA + AYUDA. Es el primer mensaje y contiene una pregunta. "
                "Saluda brevemente y responde a su necesidad en la misma respuesta."
            )
        return (
            "ESTRATEGIA: BIENVENIDA. Primer mensaje del usuario. "
            "Saluda brevemente y pregunta en qué puedes ayudar. "
            "NO hagas un saludo genérico largo."
        )

    # Priority 2b: Returning user with conversation history — prevent new-lead openers
    # This fires when history is substantial enough to confirm a prior relationship.
    # Prohibits "¿Que te llamó la atención?" / "Que t'ha cridat l'atenció?" patterns
    # that the model uses by default for leads tagged as "nuevo" in the prompt.
    if history_len >= 4 and not is_first_message:
        return (
            "ESTRATEGIA: RECURRENTE. Esta persona ya te conoce y tiene historial contigo. "
            "REGLAS CRÍTICAS: "
            "1) NO preguntes '¿Que te llamó la atención?' ni '¿Que t'ha cridat l'atenció?' ni variantes — NUNCA. "
            "2) NO saludes como si fuera la primera vez. "
            "3) Responde con naturalidad y espontaneidad usando el contexto de la conversación. "
            "4) Muestra energía y personalidad de Iris: reacciona con entusiasmo o curiosidad según el contexto, "
            "usa apelativos (nena, tia, flor, cuca, reina) — NUNCA la palabra 'flower'."
        )

    # Priority 3: Detect concrete help requests (returning users)
    if any(signal in msg_lower for signal in help_signals):
        return (
            "ESTRATEGIA: AYUDA. El usuario tiene una necesidad concreta. "
            "Responde DIRECTAMENTE a lo que necesita. NO saludes genéricamente. "
            "Si no sabes la respuesta exacta, pregunta detalles específicos."
        )

    # Priority 4: Product interest -> sales mode
    if intent_value in ("purchase", "pricing", "product_info", "purchase_intent", "product_question"):
        return (
            "ESTRATEGIA: VENTA. El usuario muestra interés en productos/servicios. "
            "Da la información concreta que pide (precio, contenido, duración). "
            "Añade un CTA suave al final."
        )

    # Priority 5: Ghost/reactivation
    if lead_stage in ("fantasma",):
        return (
            "ESTRATEGIA: REACTIVACIÓN. El usuario vuelve después de mucho tiempo. "
            "Muestra que te alegra verle. No seas agresivo con la venta."
        )

    # Default: natural conversation
    return ""
