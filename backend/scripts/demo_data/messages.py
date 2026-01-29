"""
Message templates by segment for realistic conversations
"""
import random

# User messages by segment
USER_MESSAGES = {
    "hot_lead": [
        "¿Me pasas el link de pago?",
        "¿Cómo puedo comprar el plan?",
        "Quiero empezar ya, ¿cómo lo hago?",
        "Estoy lista para apuntarme",
        "¿Aceptas Bizum?",
        "Vale, me apunto. ¿Qué tengo que hacer?",
        "Perfecto, ¿cuál es el siguiente paso?",
        "Me has convencido, vamos a ello",
        "¿Puedo empezar esta semana?",
        "Quiero el plan de 12 semanas",
    ],
    "warm_lead": [
        "Me interesa mucho lo que haces",
        "¿Cómo funciona exactamente el programa?",
        "¿Qué incluye el plan?",
        "He visto tus resultados y me gustaría saber más",
        "¿Cuánto tiempo se tarda en ver resultados?",
        "¿Es personalizado?",
        "Llevo tiempo siguiéndote y creo que es el momento",
        "¿Tienes hueco para nuevos clientes?",
        "Me encantaría probar tu método",
        "¿Hacéis seguimiento?",
    ],
    "price_objector": [
        "Me parece un poco caro...",
        "¿No tienes algo más barato?",
        "Ahora mismo no me lo puedo permitir",
        "¿Se puede pagar en varios plazos?",
        "Tengo que pensarlo, es mucho dinero",
        "¿Por qué es tan caro?",
        "He visto otros más baratos",
        "No sé si vale la pena la inversión",
        "¿Hay algún descuento?",
        "Cuando pueda permitírmelo te escribo",
    ],
    "time_objector": [
        "No tengo tiempo para cocinar",
        "Mi horario es imposible",
        "Entre el trabajo y los niños...",
        "¿Cuánto tiempo hay que dedicarle?",
        "Ahora estoy muy liada",
        "Viajo mucho y no puedo seguir un plan",
        "¿Funciona si solo puedo dedicarle 30 min?",
        "Trabajo de noche, ¿se puede adaptar?",
        "No tengo tiempo ni para mí",
        "Quizás más adelante cuando tenga más tiempo",
    ],
    "ghost": [
        "Hola, me interesa",
        "¿Qué precio tiene?",
        "Ok, lo miro",
        "Gracias",
        "Ya te digo algo",
        "Lo consulto con mi pareja",
        "Dame unos días",
        "Ahora no puedo hablar",
    ],
    "engaged_fan": [
        "¡Me encanta tu contenido!",
        "Siempre aprendo mucho contigo",
        "¿Qué opinas de...?",
        "He probado tu receta y está buenísima",
        "Eres una inspiración",
        "Gracias por todo lo que compartes",
        "¿Podrías hablar sobre...?",
        "Me motivas mucho",
        "Tu último post me ha ayudado mucho",
        "Sigo todos tus consejos",
    ],
    "new": [
        "Hola!",
        "Buenas!",
        "Hola, te acabo de descubrir",
        "Me ha salido tu perfil y me ha gustado",
    ],
    "customer": [
        "¡Gracias! El plan está genial",
        "Ya he perdido 3 kilos",
        "Las recetas son muy fáciles",
        "Estoy muy contenta con el programa",
        "¿Puedo repetir el plan?",
        "¿Tienes algo para después?",
        "Lo recomendaré a mis amigas",
        "Ha sido la mejor inversión",
    ],
}

# Bot responses (generic)
BOT_RESPONSES = [
    "¡Hola! Me alegro de que me escribas 😊",
    "¡Genial! Te cuento cómo funciona...",
    "Claro, el programa incluye...",
    "Entiendo perfectamente, es una inversión importante",
    "Muchas personas empezaron igual que tú",
    "¿Qué te gustaría conseguir exactamente?",
    "Te explico las opciones que tenemos...",
    "¡Gracias por confiar en mí!",
    "Cualquier duda que tengas, aquí estoy",
    "¿Te puedo ayudar en algo más?",
]

# Follow-up questions for engagement
FOLLOW_UP_QUESTIONS = [
    "¿Cuál es tu objetivo principal?",
    "¿Has intentado otros métodos antes?",
    "¿Qué es lo que más te cuesta?",
    "¿Tienes alguna restricción alimentaria?",
    "¿Cuánto tiempo llevas queriendo cambiar?",
    "¿Qué te ha llamado la atención de mi método?",
]


def get_messages_for_segment(segment: str, count: int = 5) -> list[dict]:
    """
    Generate a realistic conversation for a segment.
    Returns list of {"role": "user"|"assistant", "content": str}
    """
    user_msgs = USER_MESSAGES.get(segment, USER_MESSAGES["new"])

    conversation = []

    # Start with user message
    conversation.append({
        "role": "user",
        "content": random.choice(user_msgs)
    })

    # Alternate bot and user
    for i in range(count - 1):
        if i % 2 == 0:
            # Bot response
            conversation.append({
                "role": "assistant",
                "content": random.choice(BOT_RESPONSES)
            })
        else:
            # User response
            conversation.append({
                "role": "user",
                "content": random.choice(user_msgs)
            })

    return conversation


def get_last_message_for_segment(segment: str) -> tuple[str, str]:
    """
    Get appropriate last message based on segment.
    Returns (role, content) - who sent the last message
    """
    if segment == "hot_lead":
        # Hot leads: user asking for payment link
        return "user", random.choice([
            "¿Me pasas el link?",
            "¿Cómo pago?",
            "Quiero empezar ya",
            "Vale, vamos a ello",
        ])
    elif segment == "ghost":
        # Ghosts: bot sent last message, no response
        return "assistant", random.choice([
            "¿Sigues interesada? 😊",
            "¿Has podido pensarlo?",
            "¿Te puedo ayudar en algo?",
            "¿Qué tal va todo?",
        ])
    elif segment == "customer":
        # Customers: happy feedback
        return "user", random.choice([
            "¡Mil gracias! Estoy encantada",
            "El plan está siendo genial",
            "Ya noto los cambios",
        ])
    else:
        # Others: varied
        role = random.choice(["user", "assistant"])
        if role == "user":
            return role, random.choice(USER_MESSAGES.get(segment, USER_MESSAGES["new"]))
        else:
            return role, random.choice(BOT_RESPONSES)
