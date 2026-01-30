"""Topics, interests, frustrations and objections for demo data."""

from typing import List, Dict, Any

# ============================================================================
# TOPICS (Tab 1: De qué hablan)
# ============================================================================

TOPICS: List[Dict[str, Any]] = [
    {"topic": "nutrición", "count": 89, "percentage": 44.5, "weight": 0.9},
    {"topic": "perder peso", "count": 76, "percentage": 38.0, "weight": 0.85},
    {"topic": "ayuno intermitente", "count": 67, "percentage": 33.5, "weight": 0.78},
    {"topic": "recetas", "count": 64, "percentage": 32.0, "weight": 0.75},
    {"topic": "ejercicio", "count": 52, "percentage": 26.0, "weight": 0.65},
    {"topic": "meal prep", "count": 41, "percentage": 20.5, "weight": 0.55},
    {"topic": "suplementos", "count": 34, "percentage": 17.0, "weight": 0.45},
    {"topic": "proteína", "count": 31, "percentage": 15.5, "weight": 0.42},
    {"topic": "ansiedad comida", "count": 29, "percentage": 14.5, "weight": 0.40},
    {"topic": "keto", "count": 23, "percentage": 11.5, "weight": 0.35},
    {"topic": "déficit calórico", "count": 21, "percentage": 10.5, "weight": 0.32},
    {"topic": "hidratación", "count": 18, "percentage": 9.0, "weight": 0.28},
    {"topic": "snacks saludables", "count": 16, "percentage": 8.0, "weight": 0.25},
    {"topic": "desayunos", "count": 15, "percentage": 7.5, "weight": 0.24},
    {"topic": "cenas ligeras", "count": 14, "percentage": 7.0, "weight": 0.22},
]

# ============================================================================
# PASSIONS (Tab 2: Qué les apasiona)
# ============================================================================

PASSIONS: List[Dict[str, Any]] = [
    {
        "topic": "transformaciones físicas",
        "count": 45,
        "percentage": 22.5,
        "description": "Les encanta ver antes y después",
    },
    {
        "topic": "recetas rápidas",
        "count": 58,
        "percentage": 29.0,
        "description": "Buscan soluciones prácticas para el día a día",
    },
    {
        "topic": "bienestar mental",
        "count": 37,
        "percentage": 18.5,
        "description": "Conexión mente-cuerpo",
    },
    {
        "topic": "batch cooking",
        "count": 32,
        "percentage": 16.0,
        "description": "Organización semanal de comidas",
    },
    {
        "topic": "testimonios reales",
        "count": 28,
        "percentage": 14.0,
        "description": "Historias de éxito inspiradoras",
    },
    {
        "topic": "tips rápidos",
        "count": 42,
        "percentage": 21.0,
        "description": "Consejos aplicables inmediatamente",
    },
]

# ============================================================================
# FRUSTRATIONS (Tab 3: Qué les frustra)
# ============================================================================

FRUSTRATIONS: List[Dict[str, Any]] = [
    {
        "frustration": "No tengo tiempo para cocinar sano",
        "count": 56,
        "percentage": 28.0,
        "quotes": [
            "Es que llego a casa reventada y no me apetece cocinar",
            "Con 3 hijos no tengo tiempo para preparar comida elaborada",
            "Trabajo todo el día y cuando llego solo quiero algo rápido",
        ],
        "suggestion": "Enfatiza recetas de 15 minutos y batch cooking",
    },
    {
        "frustration": "Las dietas no me funcionan",
        "count": 48,
        "percentage": 24.0,
        "quotes": [
            "He probado de todo y siempre acabo igual",
            "Siempre vuelvo a engordar lo que pierdo",
            "Me canso de contar calorías",
        ],
        "suggestion": "Posiciona como cambio de hábitos, no dieta restrictiva",
    },
    {
        "frustration": "No sé qué comer",
        "count": 42,
        "percentage": 21.0,
        "quotes": [
            "Me pierdo con tanta información contradictoria",
            "Cada día dicen algo diferente en redes",
            "No sé si lo que como es bueno o malo",
        ],
        "suggestion": "Ofrece plan semanal estructurado y simple",
    },
    {
        "frustration": "No veo resultados",
        "count": 35,
        "percentage": 17.5,
        "quotes": [
            "Llevo meses y no bajo de peso",
            "Hago ejercicio pero no noto cambios",
            "Me estanco siempre en el mismo peso",
        ],
        "suggestion": "Explica que los resultados llevan tiempo y ofrece seguimiento",
    },
    {
        "frustration": "Me aburro de comer siempre lo mismo",
        "count": 28,
        "percentage": 14.0,
        "quotes": [
            "Siempre como lo mismo y me canso",
            "No sé hacer platos variados",
            "La comida sana me parece aburrida",
        ],
        "suggestion": "Destaca variedad de recetas y sabores",
    },
]

# ============================================================================
# COMPETITION (Tab 4: Competencia)
# ============================================================================

COMPETITION: List[Dict[str, Any]] = [
    {
        "competitor": "@fitness_maria",
        "count": 19,
        "sentiment": "neutral",
        "context": [
            "Vi que @fitness_maria tiene un curso parecido",
            "@fitness_maria cobra menos pero tiene menos contenido",
            "¿En qué te diferencias de @fitness_maria?",
        ],
        "suggestion": "Diferénciate por el acompañamiento personalizado",
    },
    {
        "competitor": "@nutritionist_ana",
        "count": 12,
        "sentiment": "positive",
        "context": [
            "Me gusta el contenido de @nutritionist_ana también",
            "La sigo a ella y a ti, me complementáis",
        ],
        "suggestion": "Potencial colaboración o cross-promotion",
    },
    {
        "competitor": "@gym_carlos",
        "count": 8,
        "sentiment": "negative",
        "context": [
            "Me parece muy bro science lo que hace",
            "No me gusta su estilo, es muy agresivo",
        ],
        "suggestion": "Tu enfoque científico y cercano es diferenciador",
    },
    {
        "competitor": "@coachnutri_pedro",
        "count": 6,
        "sentiment": "neutral",
        "context": [
            "¿Conoces a @coachnutri_pedro?",
            "Él da consejos gratuitos",
        ],
        "suggestion": "Enfatiza el valor del acompañamiento premium",
    },
]

# ============================================================================
# TRENDS (Tab 5: Tendencias)
# ============================================================================

TRENDS: List[Dict[str, Any]] = [
    {"term": "ozempic", "this_week": 34, "last_week": 10, "growth": 240},
    {"term": "proteína vegana", "this_week": 23, "last_week": 12, "growth": 92},
    {"term": "creatina mujeres", "this_week": 18, "last_week": 8, "growth": 125},
    {"term": "déficit calórico", "this_week": 31, "last_week": 28, "growth": 11},
    {"term": "ayuno 16:8", "this_week": 45, "last_week": 38, "growth": 18},
    {"term": "conteo macros", "this_week": 15, "last_week": 9, "growth": 67},
    {"term": "gluten free", "this_week": 12, "last_week": 11, "growth": 9},
]

# ============================================================================
# CONTENT REQUESTS (Tab 6: Contenido que piden)
# ============================================================================

CONTENT_REQUESTS: List[Dict[str, Any]] = [
    {
        "topic": "Recetas para batch cooking",
        "count": 38,
        "questions": [
            "¿Tienes menú semanal para organizar mis tuppers?",
            "¿Cómo organizo mis comidas de la semana?",
            "Ideas para cocinar el domingo y tener toda la semana",
        ],
    },
    {
        "topic": "Ejercicios en casa sin material",
        "count": 31,
        "questions": [
            "¿Se puede entrenar bien en casa?",
            "No tengo pesas ni nada, ¿qué hago?",
            "Rutinas sin ir al gimnasio",
        ],
    },
    {
        "topic": "Cómo leer etiquetas",
        "count": 24,
        "questions": [
            "No entiendo los ingredientes de las etiquetas",
            "¿Qué es maltodextrina?",
            "¿Cómo sé si un producto es sano?",
        ],
    },
    {
        "topic": "Gestión del hambre emocional",
        "count": 21,
        "questions": [
            "¿Cómo controlo los antojos?",
            "Como por ansiedad, ¿qué hago?",
            "Por la noche me da hambre y arraso con todo",
        ],
    },
    {
        "topic": "Qué comer fuera de casa",
        "count": 18,
        "questions": [
            "¿Qué pido en un restaurante?",
            "Si como fuera, ¿rompo la dieta?",
            "Opciones sanas para cuando viajo",
        ],
    },
]

# ============================================================================
# PURCHASE OBJECTIONS (Tab 7: Por qué no compran)
# ============================================================================

PURCHASE_OBJECTIONS: List[Dict[str, Any]] = [
    {
        "objection": "precio",
        "count": 52,
        "percentage": 26.0,
        "pending": 30,
        "resolved": 22,
        "quotes": [
            "Es mucho dinero para mí ahora mismo",
            "No me lo puedo permitir",
            "¿No tienes algo más barato?",
            "Es caro comparado con otros cursos",
        ],
        "suggestion": "Ofrece pago en 3 cuotas sin intereses",
        "resolution_rate": 0.42,
    },
    {
        "objection": "tiempo",
        "count": 38,
        "percentage": 19.0,
        "pending": 18,
        "resolved": 20,
        "quotes": [
            "No tengo tiempo para nada",
            "Mi día es una locura",
            "Entre el trabajo y los niños...",
            "No sé si podré seguir el programa",
        ],
        "suggestion": "Enfatiza que son solo 15-20 min/día",
        "resolution_rate": 0.53,
    },
    {
        "objection": "duda",
        "count": 28,
        "percentage": 14.0,
        "pending": 15,
        "resolved": 13,
        "quotes": [
            "¿Esto funciona de verdad?",
            "Ya probé otros cursos y no me sirvieron",
            "No sé si es para mí",
            "¿Cómo sé que no es otra estafa?",
        ],
        "suggestion": "Comparte testimonios de clientes similares",
        "resolution_rate": 0.46,
    },
    {
        "objection": "luego",
        "count": 34,
        "percentage": 17.0,
        "pending": 25,
        "resolved": 9,
        "quotes": [
            "Ahora no es buen momento",
            "Después de verano lo empiezo",
            "En enero me pongo las pilas",
            "Cuando termine este proyecto me apunto",
        ],
        "suggestion": "Crea urgencia con bonus limitado en el tiempo",
        "resolution_rate": 0.26,
    },
    {
        "objection": "pareja",
        "count": 15,
        "percentage": 7.5,
        "pending": 8,
        "resolved": 7,
        "quotes": [
            "Tengo que consultarlo con mi pareja",
            "Mi marido controla las finanzas",
            "A ver qué dice mi novio",
        ],
        "suggestion": "Ofrece call conjunta o materiales para compartir",
        "resolution_rate": 0.47,
    },
]

# ============================================================================
# PERCEPTION (Tab 8: Qué piensan de ti)
# ============================================================================

PERCEPTION: List[Dict[str, Any]] = [
    {
        "aspect": "expertise",
        "positive": 67,
        "negative": 3,
        "quotes_positive": [
            "Se nota que sabes mucho del tema",
            "Muy profesional todo lo que haces",
            "Me encanta que expliques el porqué de las cosas",
            "Tus explicaciones son muy claras",
        ],
        "quotes_negative": [
            "A veces muy técnica para mí",
            "Me pierdo cuando usas términos científicos",
        ],
    },
    {
        "aspect": "precio",
        "positive": 34,
        "negative": 41,
        "quotes_positive": [
            "Vale cada euro que pagué",
            "Es una inversión que merece la pena",
            "Comparado con lo que gasté antes, es barato",
        ],
        "quotes_negative": [
            "Un poco caro para mi presupuesto",
            "Ojalá tuvieras descuento de estudiante",
            "Es más caro que la competencia",
        ],
    },
    {
        "aspect": "atención",
        "positive": 78,
        "negative": 5,
        "quotes_positive": [
            "Respondes super rápido",
            "Me encanta que contestes todo personalmente",
            "Se nota que te importamos",
            "El seguimiento es increíble",
        ],
        "quotes_negative": [
            "A veces tarda en responder",
            "Los fines de semana no contestas",
        ],
    },
    {
        "aspect": "contenido",
        "positive": 82,
        "negative": 4,
        "quotes_positive": [
            "El contenido es muy completo",
            "Las recetas son deliciosas y fáciles",
            "Me encanta la variedad",
        ],
        "quotes_negative": [
            "Algunas recetas llevan ingredientes difíciles de encontrar",
            "Podrías incluir más opciones veganas",
        ],
    },
]

# ============================================================================
# INTERESTS WITH WEIGHTS (for UserProfile)
# ============================================================================

INTERESTS_WEIGHTS: Dict[str, float] = {
    "nutrición": 0.92,
    "perder peso": 0.85,
    "ayuno intermitente": 0.78,
    "recetas rápidas": 0.75,
    "batch cooking": 0.68,
    "ejercicio en casa": 0.62,
    "proteína": 0.58,
    "meal prep": 0.55,
    "snacks saludables": 0.48,
    "suplementos": 0.45,
    "hidratación": 0.42,
    "déficit calórico": 0.38,
    "macros": 0.35,
    "keto": 0.32,
    "ayuno 16:8": 0.30,
    "bienestar mental": 0.28,
    "transformación física": 0.25,
}

# ============================================================================
# OBJECTION TYPES
# ============================================================================

OBJECTION_TYPES: List[str] = [
    "OBJECTION_PRICE",
    "OBJECTION_TIME",
    "OBJECTION_DOUBT",
    "OBJECTION_LATER",
    "OBJECTION_PARTNER",
    "OBJECTION_COMPETITION",
    "OBJECTION_TRUST",
    "OBJECTION_RESULTS",
]
