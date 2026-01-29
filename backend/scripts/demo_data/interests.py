"""
Topics, interests, and objections for fitness/nutrition niche
"""
import random

TOPICS = [
    # Nutrition
    "nutrición", "alimentación saludable", "dieta", "macros", "proteína",
    "carbohidratos", "grasas saludables", "calorías", "déficit calórico",

    # Specific diets
    "ayuno intermitente", "keto", "dieta mediterránea", "vegetariano",
    "vegano", "sin gluten", "bajo en carbohidratos",

    # Goals
    "perder peso", "ganar músculo", "definición", "volumen",
    "mantenimiento", "recomposición corporal", "tonificar",

    # Food
    "recetas fit", "meal prep", "snacks saludables", "desayunos",
    "cenas ligeras", "batidos proteicos", "suplementos",

    # Lifestyle
    "hábitos saludables", "motivación", "disciplina", "rutina",
    "descanso", "hidratación", "estrés", "sueño",

    # Training
    "entrenamiento", "ejercicio en casa", "gimnasio", "cardio",
    "fuerza", "HIIT", "yoga", "pilates",
]

OBJECTIONS = {
    "price": [
        "Es muy caro para mí ahora mismo",
        "No me lo puedo permitir",
        "¿Tienes algo más económico?",
        "Me parece un poco elevado el precio",
        "Tengo que pensarlo, es mucho dinero",
        "¿Se puede pagar a plazos?",
        "Ahora no puedo invertir tanto",
    ],
    "time": [
        "No tengo tiempo para cocinar",
        "Mi horario es muy complicado",
        "Trabajo muchas horas",
        "Con los niños no puedo",
        "Viajo mucho por trabajo",
        "No sé si podré seguirlo",
        "Ahora estoy muy liada",
    ],
    "doubt": [
        "No sé si funcionará para mí",
        "Ya he probado muchas cosas",
        "¿Realmente funciona?",
        "Tengo mis dudas",
        "No estoy segura",
        "He fallado otras veces",
    ],
    "trust": [
        "No te conozco mucho todavía",
        "¿Tienes testimonios?",
        "¿Qué resultados tienen otros?",
        "Necesito ver más antes de decidir",
    ],
}

OBJECTION_WEIGHTS = {
    "price": 0.35,
    "time": 0.28,
    "doubt": 0.22,
    "trust": 0.15,
}

# Simple objection keywords for segment detection
OBJECTION_KEYWORDS = {
    "price": "precio",
    "time": "tiempo",
    "doubt": "duda",
    "trust": "confianza",
}

# Competitor accounts for @mentions
COMPETITORS = [
    "@fitness_maria",
    "@nutritionist_ana",
    "@gym_carlos",
    "@healthy_laura",
    "@coach_pedro",
]

# Trending terms to include in messages
TRENDING_TERMS = [
    "ozempic",
    "ayuno 16:8",
    "proteína vegana",
    "creatina",
    "déficit calórico",
    "batch cooking",
]


def get_random_interests(count: int = 3) -> list[str]:
    """Get random interests for a follower"""
    return random.sample(TOPICS, min(count, len(TOPICS)))


def get_interests_with_weights(interests: list[str]) -> dict[str, float]:
    """Convert interest list to weighted dict for user_profiles"""
    return {topic: round(random.uniform(0.5, 1.0), 2) for topic in interests}


def get_random_objections(objection_type: str = None) -> tuple[str, str]:
    """Get random objection and its type"""
    if objection_type is None:
        # Weighted random selection
        types = list(OBJECTION_WEIGHTS.keys())
        weights = list(OBJECTION_WEIGHTS.values())
        objection_type = random.choices(types, weights=weights, k=1)[0]

    objection_text = random.choice(OBJECTIONS[objection_type])
    return objection_type, objection_text


# Arguments used to handle objections
ARGUMENTS_BY_OBJECTION = {
    "precio": [
        "valor_vs_precio",
        "roi_inversion",
        "comparativa_alternativas",
        "pago_fraccionado",
        "garantia_satisfaccion",
    ],
    "tiempo": [
        "recetas_rapidas",
        "meal_prep_domingo",
        "plan_adaptado_horarios",
        "minimalismo_efectivo",
        "priorizar_salud",
    ],
    "duda": [
        "testimonios_reales",
        "casos_similares",
        "metodo_probado",
        "soporte_continuo",
        "ajustes_personalizados",
    ],
    "confianza": [
        "credenciales_experiencia",
        "resultados_clientes",
        "comunidad_activa",
        "transparencia_proceso",
    ],
}


def get_arguments_for_objections(objections: list[str]) -> list[str]:
    """Get arguments that could handle given objections"""
    arguments = []
    for obj in objections:
        if obj in ARGUMENTS_BY_OBJECTION:
            # Pick 1-2 arguments for each objection
            args = random.sample(
                ARGUMENTS_BY_OBJECTION[obj],
                k=min(random.randint(1, 2), len(ARGUMENTS_BY_OBJECTION[obj]))
            )
            arguments.extend(args)
    return list(set(arguments))  # Remove duplicates


# Notes templates by segment
NOTES_TEMPLATES = {
    "hot_lead": [
        "Muy interesada, lista para comprar. Seguimiento inmediato.",
        "Ha preguntado por el link de pago 2 veces. Prioridad alta.",
        "Quiere empezar esta semana. Enviar info completa.",
        "Contacto caliente. Cerrar antes del viernes.",
    ],
    "warm_lead": [
        "Interesada pero necesita más información. Enviar testimonios.",
        "Ha preguntado por el programa, pendiente de responder dudas.",
        "Buen engagement, cultivar relación antes de proponer.",
        "Potencial cliente, necesita nurturing.",
    ],
    "price_objector": [
        "Interesada pero el precio es barrera. Ofrecer financiación.",
        "Ha mencionado presupuesto limitado. Mostrar valor ROI.",
        "Comparando con alternativas más baratas. Diferenciación.",
    ],
    "time_objector": [
        "Le gusta pero dice no tener tiempo. Plan express.",
        "Trabaja muchas horas, adaptar recetas rápidas.",
        "Viaja mucho, necesita plan flexible.",
    ],
    "ghost": [
        "No responde desde hace 2 semanas. Reactivar con contenido.",
        "Dejó de contestar después de preguntar precio.",
        "Ghosteó después de mostrar interés inicial.",
    ],
    "engaged_fan": [
        "Fan activa, interactúa mucho pero no compra.",
        "Le encanta el contenido, convertir en lead.",
        "Muy engaged, momento de proponer.",
    ],
    "customer": [
        "Cliente satisfecha, pedir testimonio.",
        "Resultados excelentes, potencial para upsell.",
        "Terminó programa con éxito. Ofrecer continuidad.",
    ],
}


def get_notes_for_segment(segment: str) -> str | None:
    """Get random notes for a segment (40% chance of having notes)"""
    if random.random() > 0.4:
        return None
    templates = NOTES_TEMPLATES.get(segment, [])
    return random.choice(templates) if templates else None


# Instagram CDN-style profile pic URLs (placeholder pattern)
PROFILE_PIC_PATTERNS = [
    "https://instagram.fmad3-4.fna.fbcdn.net/v/t51.2885-19/{user_id}_profile_pic.jpg",
    "https://scontent-mad1-1.cdninstagram.com/v/t51.2885-19/s150x150/{user_id}_profile.jpg",
]


def get_profile_pic_url(follower_id: str) -> str | None:
    """Generate fake Instagram profile pic URL (80% have one)"""
    if random.random() > 0.8:
        return None
    pattern = random.choice(PROFILE_PIC_PATTERNS)
    return pattern.format(user_id=follower_id.replace("ig_", ""))
