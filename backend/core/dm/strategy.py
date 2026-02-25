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
            "ESTRATEGIA: PERSONAL. Esta persona es cercana (familia/íntimo). "
            "Responde con cariño y naturalidad. Si pide ayuda, ayúdale. "
            "NUNCA vendas ni ofrezcas productos."
        )

    if is_friend:
        return (
            "ESTRATEGIA: PERSONAL. Esta persona es amigo/a. "
            "Responde relajado y natural. No vendas."
        )

    # Priority 2: Detect concrete help requests
    help_signals = [
        "ayuda", "problema", "no funciona", "no puedo", "error",
        "cómo", "como hago", "necesito", "urgente", "no me deja",
        "no entiendo", "explícame", "explicame", "qué hago", "que hago",
    ]
    if any(signal in msg_lower for signal in help_signals):
        return (
            "ESTRATEGIA: AYUDA. El usuario tiene una necesidad concreta. "
            "Responde DIRECTAMENTE a lo que necesita. NO saludes genéricamente. "
            "Si no sabes la respuesta exacta, pregunta detalles específicos."
        )

    # Priority 3: Product interest -> sales mode
    if intent_value in ("purchase", "pricing", "product_info"):
        return (
            "ESTRATEGIA: VENTA. El usuario muestra interés en productos/servicios. "
            "Da la información concreta que pide (precio, contenido, duración). "
            "Añade un CTA suave al final."
        )

    # Priority 4: First message -> greeting (but check for embedded needs)
    if is_first_message:
        # Check if first message contains a question or need
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

    # Priority 5: Ghost/reactivation
    if lead_stage in ("fantasma",):
        return (
            "ESTRATEGIA: REACTIVACIÓN. El usuario vuelve después de mucho tiempo. "
            "Muestra que te alegra verle. No seas agresivo con la venta."
        )

    # Default: natural conversation
    return ""
