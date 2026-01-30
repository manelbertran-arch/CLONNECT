"""Message templates for realistic conversation generation."""

import random
from typing import List, Dict, Any

# Intent types matching the system
INTENT_TYPES = [
    "GREETING", "INTEREST_SOFT", "INTEREST_STRONG", "QUESTION_PRODUCT",
    "QUESTION_PRICE", "QUESTION_GENERAL", "OBJECTION_PRICE", "OBJECTION_TIME",
    "OBJECTION_DOUBT", "OBJECTION_LATER", "READY_TO_BUY", "THANK_YOU",
    "OFF_TOPIC", "COMPLAINT", "TESTIMONIAL_REQUEST", "PAYMENT_QUESTION",
]

# ============================================================================
# HOT LEAD CONVERSATION TEMPLATES
# ============================================================================

HOT_LEAD_TEMPLATES: List[List[Dict[str, Any]]] = [
    # Template 1: Direct buyer
    [
        {"role": "user", "content": "Hola! Vi tu reel sobre el ayuno y me interesa mucho", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Hola! Me alegra que te haya gustado 😊 ¿Qué es lo que más te llamó la atención?"},
        {"role": "user", "content": "Quiero perder peso de forma saludable, llevo años probando dietas", "intent": "INTEREST_SOFT"},
        {"role": "assistant", "content": "Te entiendo perfectamente. ¿Cuántos kilos te gustaría perder y en qué tiempo?"},
        {"role": "user", "content": "Unos 8kg, antes del verano si es posible", "intent": "INTEREST_SOFT"},
        {"role": "assistant", "content": "Es totalmente posible con el enfoque correcto. Tengo un programa de 12 semanas que podría ser perfecto para ti."},
        {"role": "user", "content": "¿De qué va exactamente?", "intent": "QUESTION_PRODUCT"},
        {"role": "assistant", "content": "Es un curso completo que incluye plan de alimentación, recetas, y seguimiento semanal. Todo adaptado a tu ritmo de vida."},
        {"role": "user", "content": "Suena bien. ¿Cuánto cuesta?", "intent": "QUESTION_PRICE"},
        {"role": "assistant", "content": "Son 297€ por todo el programa. Incluye acceso de por vida y actualizaciones."},
        {"role": "user", "content": "Es un poco caro para mí ahora mismo...", "intent": "OBJECTION_PRICE"},
        {"role": "assistant", "content": "Entiendo. Piensa que son menos de 25€ al mes durante un año, y los resultados son para siempre. Además, puedo ofrecerte 3 cuotas sin intereses."},
        {"role": "user", "content": "¿3 cuotas? Eso sí me viene mejor", "intent": "INTEREST_STRONG"},
        {"role": "assistant", "content": "Sí, serían 99€ al mes durante 3 meses. ¿Te gustaría empezar?"},
        {"role": "user", "content": "Vale, lo quiero. ¿Me pasas el link de pago?", "intent": "READY_TO_BUY"},
    ],
    # Template 2: Quick decision
    [
        {"role": "user", "content": "Hola! Una amiga me recomendó tu curso", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Hola! Qué bien, ¿quién es tu amiga?"},
        {"role": "user", "content": "Laura, hizo tu programa el año pasado y está increíble", "intent": "INTEREST_SOFT"},
        {"role": "assistant", "content": "¡Ah, Laura! Sí, tuvo unos resultados espectaculares. ¿Tú también buscas transformarte?"},
        {"role": "user", "content": "Sí, quiero lo mismo que ella. Cuéntame qué incluye", "intent": "QUESTION_PRODUCT"},
        {"role": "assistant", "content": "El curso incluye 12 semanas de plan alimenticio, +50 recetas, vídeos explicativos y seguimiento semanal."},
        {"role": "user", "content": "Perfecto. ¿Precio?", "intent": "QUESTION_PRICE"},
        {"role": "assistant", "content": "297€ acceso completo. Laura me dijo que le cambió la vida."},
        {"role": "user", "content": "Me fío de ella. ¿Puedo empezar ya?", "intent": "READY_TO_BUY"},
        {"role": "assistant", "content": "¡Claro! Te paso el link de pago y esta misma semana empezamos."},
        {"role": "user", "content": "Genial, mándamelo!", "intent": "READY_TO_BUY"},
    ],
    # Template 3: Resolved time objection
    [
        {"role": "user", "content": "Hola, me interesa tu mentoría pero trabajo mucho", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Hola! Muchos de mis clientes trabajan a jornada completa. ¿Cuántas horas libres tienes al día?"},
        {"role": "user", "content": "Como mucho 1 hora, y eso con suerte", "intent": "OBJECTION_TIME"},
        {"role": "assistant", "content": "Perfecto, con 30-45 minutos al día es suficiente. El programa está diseñado para gente ocupada."},
        {"role": "user", "content": "¿En serio? ¿Y funciona igual?", "intent": "INTEREST_SOFT"},
        {"role": "assistant", "content": "Sí, tengo testimonios de madres trabajadoras que lo han conseguido. ¿Te paso algunos?"},
        {"role": "user", "content": "Sí porfa, quiero verlos", "intent": "TESTIMONIAL_REQUEST"},
        {"role": "assistant", "content": "Mira, aquí tienes 3 casos de personas con situaciones similares a la tuya..."},
        {"role": "user", "content": "Wow, increíble. Creo que sí puedo hacerlo", "intent": "INTEREST_STRONG"},
        {"role": "assistant", "content": "¡Claro que puedes! ¿Quieres que te cuente cómo funciona?"},
        {"role": "user", "content": "Sí, y dime el precio también", "intent": "QUESTION_PRICE"},
        {"role": "assistant", "content": "La mentoría 1:1 son 497€. Incluye seguimiento diario por WhatsApp y 4 llamadas al mes."},
        {"role": "user", "content": "Ok, lo hablé con mi pareja y adelante", "intent": "READY_TO_BUY"},
    ],
]

# ============================================================================
# WARM LEAD CONVERSATION TEMPLATES
# ============================================================================

WARM_LEAD_TEMPLATES: List[List[Dict[str, Any]]] = [
    [
        {"role": "user", "content": "Hola! Acabo de ver tu story sobre nutrición", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Hola! ¿Qué parte te llamó más la atención?"},
        {"role": "user", "content": "Lo de las proteínas, no sabía que eran tan importantes", "intent": "INTEREST_SOFT"},
        {"role": "assistant", "content": "Sí, son fundamentales. ¿Actualmente llevas algún control de tu alimentación?"},
        {"role": "user", "content": "No mucho, como lo que puedo cuando puedo", "intent": "OFF_TOPIC"},
        {"role": "assistant", "content": "Es muy común. ¿Te gustaría aprender a organizarte mejor?"},
        {"role": "user", "content": "Sí, pero no sé por dónde empezar", "intent": "INTEREST_SOFT"},
        {"role": "assistant", "content": "Tengo un curso que te enseña exactamente eso, paso a paso."},
        {"role": "user", "content": "¿Qué incluye?", "intent": "QUESTION_PRODUCT"},
        {"role": "assistant", "content": "Plan de comidas, recetas fáciles, lista de la compra y seguimiento semanal."},
        {"role": "user", "content": "Suena bien, lo voy a pensar", "intent": "OBJECTION_LATER"},
    ],
    [
        {"role": "user", "content": "Hola! Quiero empezar a comer mejor", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Genial! ¿Hay algún objetivo específico que tengas en mente?"},
        {"role": "user", "content": "Perder barriga, tengo mucha grasa acumulada", "intent": "INTEREST_SOFT"},
        {"role": "assistant", "content": "Es uno de los objetivos más comunes. ¿Has intentado algo antes?"},
        {"role": "user", "content": "Sí, mil dietas pero ninguna me funciona", "intent": "OBJECTION_DOUBT"},
        {"role": "assistant", "content": "Normal, las dietas restrictivas no funcionan a largo plazo. Mi enfoque es diferente."},
        {"role": "user", "content": "¿Cómo es tu enfoque?", "intent": "QUESTION_PRODUCT"},
        {"role": "assistant", "content": "Se basa en crear hábitos sostenibles, no en prohibir alimentos. ¿Te cuento más?"},
        {"role": "user", "content": "Sí, me interesa", "intent": "INTEREST_SOFT"},
    ],
]

# ============================================================================
# GHOST CONVERSATION TEMPLATES (last message from bot, no response)
# ============================================================================

GHOST_TEMPLATES: List[List[Dict[str, Any]]] = [
    [
        {"role": "user", "content": "Hola, vi tu post sobre recetas rápidas", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Hola! Sí, las recetas de 15 minutos son las favoritas. ¿Cocinas mucho en casa?"},
        {"role": "user", "content": "Intento pero no tengo tiempo", "intent": "OBJECTION_TIME"},
        {"role": "assistant", "content": "Por eso hice esas recetas, pensando en gente ocupada como tú."},
        {"role": "user", "content": "Ya, pero es que mi día es una locura", "intent": "OBJECTION_TIME"},
        {"role": "assistant", "content": "Te entiendo. ¿Te gustaría que te mande algunas recetas que puedes hacer en 10 minutos?"},
        # No response - ghost
    ],
    [
        {"role": "user", "content": "Hola! Me interesa tu programa", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Hola! Genial, ¿qué te gustaría saber?"},
        {"role": "user", "content": "¿Cuánto cuesta?", "intent": "QUESTION_PRICE"},
        {"role": "assistant", "content": "El programa completo son 297€. Incluye todo lo necesario para transformar tu alimentación."},
        {"role": "user", "content": "Es mucho dinero para mí ahora", "intent": "OBJECTION_PRICE"},
        {"role": "assistant", "content": "Entiendo. Puedo ofrecerte pago en 3 cuotas de 99€. ¿Te viene mejor así?"},
        {"role": "user", "content": "Lo tengo que pensar", "intent": "OBJECTION_LATER"},
        {"role": "assistant", "content": "Claro, tómate tu tiempo. ¿Quieres que te cuente qué resultados han tenido otros clientes?"},
        # No response - ghost
    ],
]

# ============================================================================
# OBJECTION CONVERSATION TEMPLATES
# ============================================================================

OBJECTION_TEMPLATES: Dict[str, List[List[Dict[str, Any]]]] = {
    "price": [
        [
            {"role": "user", "content": "Hola! Me interesa tu curso pero es caro", "intent": "GREETING"},
            {"role": "assistant", "content": "¡Hola! Entiendo tu preocupación. ¿Cuánto tenías pensado invertir?"},
            {"role": "user", "content": "No sé, menos de 100€", "intent": "OBJECTION_PRICE"},
            {"role": "assistant", "content": "Entiendo. El curso son 297€ pero son menos de 25€ al mes si lo piensas así."},
            {"role": "user", "content": "Ya pero ahora mismo no puedo", "intent": "OBJECTION_PRICE"},
            {"role": "assistant", "content": "¿Y si te ofrezco pagarlo en 3 cuotas sin intereses?"},
            {"role": "user", "content": "Aún así es mucho, ya veré más adelante", "intent": "OBJECTION_LATER"},
        ],
        [
            {"role": "user", "content": "Me parece muy caro comparado con otros cursos", "intent": "OBJECTION_PRICE"},
            {"role": "assistant", "content": "¿Con qué cursos lo has comparado?"},
            {"role": "user", "content": "Vi uno por 50€ en Udemy", "intent": "OBJECTION_PRICE"},
            {"role": "assistant", "content": "Entiendo. La diferencia es que aquí tienes seguimiento personalizado y acceso directo a mí."},
            {"role": "user", "content": "Ya pero sigue siendo mucho dinero", "intent": "OBJECTION_PRICE"},
            {"role": "assistant", "content": "Piensa en lo que gastas cada mes en comida basura o en cosas que no te acercan a tu objetivo..."},
            {"role": "user", "content": "Tienes razón pero no me lo puedo permitir ahora", "intent": "OBJECTION_PRICE"},
        ],
    ],
    "time": [
        [
            {"role": "user", "content": "No tengo tiempo para hacer ningún programa", "intent": "OBJECTION_TIME"},
            {"role": "assistant", "content": "¿Cuántas horas trabajas al día?"},
            {"role": "user", "content": "10-12 horas, llego muerta a casa", "intent": "OBJECTION_TIME"},
            {"role": "assistant", "content": "Entiendo perfectamente. Por eso el programa solo requiere 20-30 minutos al día."},
            {"role": "user", "content": "Ni eso tengo, de verdad", "intent": "OBJECTION_TIME"},
            {"role": "assistant", "content": "¿Y si te dijera que con las recetas del programa ahorrarás tiempo porque ya no tendrás que pensar qué comer?"},
            {"role": "user", "content": "Suena bien pero no sé si podré cumplir", "intent": "OBJECTION_DOUBT"},
        ],
    ],
}

# ============================================================================
# CUSTOMER CONVERSATION TEMPLATES
# ============================================================================

CUSTOMER_TEMPLATES: List[List[Dict[str, Any]]] = [
    [
        {"role": "user", "content": "Hola! Acabo de terminar la semana 12 del curso", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Enhorabuena! ¿Cómo te sientes?"},
        {"role": "user", "content": "Increíble! He perdido 7kg y me siento con mucha energía", "intent": "THANK_YOU"},
        {"role": "assistant", "content": "¡Qué maravilla! Me alegro muchísimo. ¿Te gustaría continuar con la mentoría?"},
        {"role": "user", "content": "Sí, quiero seguir contigo", "intent": "INTEREST_STRONG"},
        {"role": "assistant", "content": "Perfecto. Te cuento las opciones de continuidad que tenemos..."},
    ],
    [
        {"role": "user", "content": "Gracias por todo! El programa me ha cambiado la vida", "intent": "THANK_YOU"},
        {"role": "assistant", "content": "¡Gracias a ti por confiar! ¿Me dejarías un testimonio para ayudar a otros?"},
        {"role": "user", "content": "Claro que sí, te lo mando ahora", "intent": "THANK_YOU"},
        {"role": "assistant", "content": "¡Genial! Y si conoces a alguien que le pueda interesar, tengo un descuento especial por recomendación."},
    ],
]

# ============================================================================
# NEW FOLLOWER TEMPLATES
# ============================================================================

NEW_TEMPLATES: List[List[Dict[str, Any]]] = [
    [
        {"role": "user", "content": "Hola! Acabo de descubrirte y me encanta tu contenido", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Hola! Muchas gracias 😊 ¿Qué contenido te ha gustado más?"},
        {"role": "user", "content": "Los reels sobre nutrición, son muy claros", "intent": "INTEREST_SOFT"},
    ],
    [
        {"role": "user", "content": "Hola! Una pregunta rápida", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Hola! Dime, ¿en qué puedo ayudarte?"},
    ],
    [
        {"role": "user", "content": "Hola 👋", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Hola! ¿Qué tal? ¿En qué te puedo ayudar?"},
    ],
]

# ============================================================================
# ENGAGED FAN TEMPLATES (many messages, low intent)
# ============================================================================

ENGAGED_FAN_TEMPLATES: List[List[Dict[str, Any]]] = [
    [
        {"role": "user", "content": "Hola! Me encantan tus recetas", "intent": "GREETING"},
        {"role": "assistant", "content": "¡Gracias! ¿Cuál has probado últimamente?"},
        {"role": "user", "content": "La de la tortilla de claras, brutal", "intent": "THANK_YOU"},
        {"role": "assistant", "content": "¡Es de mis favoritas! ¿Qué otros platos te gustan?"},
        {"role": "user", "content": "Todos los de batch cooking", "intent": "INTEREST_SOFT"},
        {"role": "assistant", "content": "Tengo un ebook con 50 recetas de batch cooking, ¿te interesaría?"},
        {"role": "user", "content": "Ahora no puedo comprarlo, pero me lo apunto", "intent": "OBJECTION_LATER"},
        {"role": "assistant", "content": "Sin problema, aquí estaré cuando quieras 😊"},
        {"role": "user", "content": "Por cierto, ¿has visto lo de la proteína vegana?", "intent": "OFF_TOPIC"},
        {"role": "assistant", "content": "Sí, es un tema interesante. ¿Tú eres vegana?"},
        {"role": "user", "content": "No, pero me interesa reducir la carne", "intent": "OFF_TOPIC"},
    ],
]


def get_conversation_for_segment(segment: str, index: int = 0) -> List[Dict[str, Any]]:
    """Get a conversation template for a specific segment."""
    templates = {
        "hot_lead": HOT_LEAD_TEMPLATES,
        "warm_lead": WARM_LEAD_TEMPLATES,
        "ghost": GHOST_TEMPLATES,
        "price_objector": OBJECTION_TEMPLATES.get("price", []),
        "time_objector": OBJECTION_TEMPLATES.get("time", []),
        "customer": CUSTOMER_TEMPLATES,
        "new": NEW_TEMPLATES,
        "engaged_fan": ENGAGED_FAN_TEMPLATES,
    }

    segment_templates = templates.get(segment, NEW_TEMPLATES)
    if not segment_templates:
        return NEW_TEMPLATES[0]

    # Use index to cycle through templates
    template_index = index % len(segment_templates)
    return segment_templates[template_index]


def generate_extended_conversation(
    base_conversation: List[Dict[str, Any]],
    target_length: int
) -> List[Dict[str, Any]]:
    """Extend a conversation to reach target message count."""
    if len(base_conversation) >= target_length:
        return base_conversation[:target_length]

    extended = list(base_conversation)

    # Filler exchanges to extend conversation
    fillers = [
        [
            {"role": "user", "content": "¿Y eso cómo funciona exactamente?", "intent": "QUESTION_GENERAL"},
            {"role": "assistant", "content": "Te lo explico paso a paso..."},
        ],
        [
            {"role": "user", "content": "Ah vale, tiene sentido", "intent": "INTEREST_SOFT"},
            {"role": "assistant", "content": "¿Tienes alguna otra duda?"},
        ],
        [
            {"role": "user", "content": "Una cosa más...", "intent": "QUESTION_GENERAL"},
            {"role": "assistant", "content": "Dime, te escucho"},
        ],
        [
            {"role": "user", "content": "Gracias por la info", "intent": "THANK_YOU"},
            {"role": "assistant", "content": "De nada, aquí estoy para lo que necesites"},
        ],
        [
            {"role": "user", "content": "¿Cuánto tiempo lleva ver resultados?", "intent": "QUESTION_GENERAL"},
            {"role": "assistant", "content": "Normalmente en 2-3 semanas ya empiezas a notar cambios"},
        ],
    ]

    while len(extended) < target_length:
        filler = random.choice(fillers)
        for msg in filler:
            if len(extended) < target_length:
                extended.append(msg)

    return extended
