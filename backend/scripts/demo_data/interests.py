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
