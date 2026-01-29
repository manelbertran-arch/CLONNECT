"""
Configuration for demo data generation
"""

CREATOR_ID = "fitpack_global"

# Distribution of 200 followers across segments
SEGMENT_DISTRIBUTION = {
    "hot_lead": 12,      # Ready to buy
    "warm_lead": 25,     # Interested but not urgent
    "price_objector": 30, # Price objection
    "time_objector": 18,  # Time objection
    "ghost": 25,         # No response 7+ days
    "engaged_fan": 35,   # Active fans without purchase
    "new": 30,           # Less than 3 messages
    "customer": 25,      # Already purchased
}

# Products for fitpack_global
PRODUCTS = [
    {
        "id": "prod_fitpack_plan",
        "name": "Plan FitPack 12 Semanas",
        "description": "Programa completo de nutrición y entrenamiento personalizado",
        "price": 197.0,
        "currency": "EUR",
        "category": "programa",
        "is_active": True,
    },
    {
        "id": "prod_recetas_ebook",
        "name": "eBook 50 Recetas Fit",
        "description": "Recetas saludables y fáciles para toda la semana",
        "price": 27.0,
        "currency": "EUR",
        "category": "ebook",
        "is_active": True,
    },
    {
        "id": "prod_consulta_1h",
        "name": "Consulta Nutricional 1h",
        "description": "Sesión personalizada de nutrición y objetivos",
        "price": 75.0,
        "currency": "EUR",
        "category": "servicio",
        "is_active": True,
    },
    {
        "id": "prod_reto_21",
        "name": "Reto 21 Días",
        "description": "Desafío intensivo para crear hábitos saludables",
        "price": 47.0,
        "currency": "EUR",
        "category": "programa",
        "is_active": True,
    },
    {
        "id": "prod_menu_semanal",
        "name": "Menú Semanal Personalizado",
        "description": "Plan de comidas adaptado a tus objetivos",
        "price": 35.0,
        "currency": "EUR",
        "category": "servicio",
        "is_active": True,
    },
]

# Booking link templates
BOOKING_LINKS = [
    {
        "id": "link_consulta_gratis",
        "title": "Consulta Gratuita 15min",
        "meeting_type": "discovery",
        "duration_minutes": 15,
        "platform": "calendly",
        "price": 0.0,
    },
    {
        "id": "link_consulta_1h",
        "title": "Consulta Nutricional 1h",
        "meeting_type": "consultation",
        "duration_minutes": 60,
        "platform": "calendly",
        "price": 75.0,
    },
]
