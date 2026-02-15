"""Configuration and constants for demo data generation."""

from typing import Dict, List, Any

# Creator ID for demo
CREATOR_ID = "fitpack_global"

# Segment distribution for 200 followers
SEGMENT_DISTRIBUTION: Dict[str, int] = {
    "hot_lead": 12,        # intent > 0.85, fase cierre, activos últimas 24h
    "warm_lead": 25,       # intent 0.5-0.7, fase propuesta/descubrimiento
    "price_objector": 30,  # objeción precio sin resolver
    "time_objector": 18,   # objeción tiempo sin resolver
    "ghost": 25,           # 7-21 días inactivo
    "engaged_fan": 35,     # 30+ mensajes, intent < 0.4
    "new": 30,             # < 5 mensajes, últimos 7 días
    "customer": 25,        # Ya compraron (revenue tracking)
}
# Total: 200

# Products catalog
PRODUCTS: List[Dict[str, Any]] = [
    {
        "name": "Curso Nutrición Completo",
        "description": "Curso completo de 12 semanas para transformar tu alimentación. Incluye plan de comidas, recetas y seguimiento semanal.",
        "short_description": "Transforma tu alimentación en 12 semanas",
        "price": 297.00,
        "category": "product",
        "product_type": "curso",
        "currency": "EUR",
    },
    {
        "name": "Mentoría 1:1 Premium",
        "description": "Mentoría personalizada con seguimiento diario por WhatsApp, 4 llamadas mensuales y plan 100% adaptado a ti.",
        "short_description": "Acompañamiento personalizado premium",
        "price": 497.00,
        "category": "service",
        "product_type": "mentoria",
        "currency": "EUR",
    },
    {
        "name": "Plan 12 Semanas",
        "description": "Plan de entrenamiento y nutrición de 12 semanas con vídeos explicativos y soporte por email.",
        "short_description": "Plan completo de 12 semanas",
        "price": 197.00,
        "category": "product",
        "product_type": "curso",
        "currency": "EUR",
    },
    {
        "name": "Mentoría Grupal",
        "description": "Mentoría en grupo reducido (máx 10 personas). 2 llamadas grupales semanales + comunidad privada.",
        "short_description": "Mentoría en grupo reducido",
        "price": 300.00,
        "category": "service",
        "product_type": "mentoria",
        "currency": "EUR",
    },
    {
        "name": "Ebook Recetas Fit",
        "description": "50 recetas saludables y deliciosas para toda la semana. Incluye lista de la compra y valores nutricionales.",
        "short_description": "50 recetas saludables",
        "price": 27.00,
        "category": "product",
        "product_type": "ebook",
        "currency": "EUR",
    },
]

# Weekly metrics
METRICS: Dict[str, Dict[str, Any]] = {
    "this_week": {
        "revenue": 4847.00,
        "sales_count": 12,
        "response_rate": 0.92,
        "hot_leads_count": 12,
        "messages_sent": 347,
        "messages_received": 289,
        "new_leads": 18,
    },
    "last_week": {
        "revenue": 3195.00,
        "sales_count": 9,
        "response_rate": 0.87,
        "hot_leads_count": 8,
        "messages_sent": 298,
        "messages_received": 241,
        "new_leads": 14,
    },
}

# Weekly insights for dashboard
WEEKLY_INSIGHTS: Dict[str, Dict[str, Any]] = {
    "content": {
        "topic": "ayuno intermitente",
        "count": 67,
        "percentage": 33.5,
        "quotes": [
            "¿Es verdad que el ayuno de 16 horas es mejor?",
            "¿Puedo tomar café durante el ayuno?",
            "¿El ayuno sirve para ganar músculo?",
        ],
        "suggestion": "Crea un post o reel explicando los básicos del ayuno intermitente",
    },
    "trend": {
        "term": "ozempic",
        "count": 34,
        "growth": "+245%",
        "quotes": [
            "¿Qué opinas del ozempic para adelgazar?",
            "Una amiga está tomando ozempic...",
            "¿Es seguro el ozempic?",
        ],
        "suggestion": "Posiciónate como alternativa natural y sostenible",
    },
    "product": {
        "product_name": "Mentoría grupal",
        "count": 28,
        "potential_revenue": 8400.00,
        "quotes": [
            "¿Tienes algo en grupo? Es que sola no me motivo",
            "¿Hacéis sesiones grupales?",
            "Me interesaría algo más económico pero con seguimiento",
        ],
        "suggestion": "Crea mentoría grupal a €300/persona",
    },
    "competition": {
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
}

# Today's bookings
TODAY_BOOKINGS: List[Dict[str, Any]] = [
    {
        "time": "09:30",
        "name": "Ana Martínez",
        "type": "Llamada descubrimiento",
        "product": "Mentoría 1:1 Premium",
        "email": "ana.martinez@gmail.com",
        "phone": "+34612345678",
    },
    {
        "time": "11:00",
        "name": "Pedro Sánchez",
        "type": "Seguimiento",
        "product": "Curso Nutrición Completo",
        "email": "pedro.sanchez@hotmail.com",
        "phone": "+34623456789",
    },
    {
        "time": "14:00",
        "name": "Laura Vega",
        "type": "Demo producto",
        "product": "Plan 12 Semanas",
        "email": "laura.vega@gmail.com",
        "phone": "+34634567890",
    },
    {
        "time": "17:30",
        "name": "Diego Torres",
        "type": "Cierre",
        "product": "Mentoría 1:1 Premium",
        "email": "diego.torres@outlook.com",
        "phone": "+34645678901",
    },
    {
        "time": "19:00",
        "name": "Sofía Ruiz",
        "type": "Onboarding",
        "product": "Curso Nutrición Completo",
        "email": "sofia.ruiz@gmail.com",
        "phone": "+34656789012",
    },
]

# Segment characteristics for data generation
SEGMENT_CHARACTERISTICS: Dict[str, Dict[str, Any]] = {
    "hot_lead": {
        "intent_range": (0.85, 0.98),
        "phase": "cierre",
        "message_count_range": (15, 30),
        "days_since_last_contact": (0, 1),
        "has_objection_resolved": True,
        "status": "caliente",
    },
    "warm_lead": {
        "intent_range": (0.50, 0.70),
        "phase": "propuesta",
        "message_count_range": (8, 20),
        "days_since_last_contact": (1, 4),
        "has_objection_resolved": False,
        "status": "interesado",
    },
    "price_objector": {
        "intent_range": (0.40, 0.65),
        "phase": "objeciones",
        "message_count_range": (10, 25),
        "days_since_last_contact": (2, 7),
        "objection_type": "precio",
        "status": "interesado",
    },
    "time_objector": {
        "intent_range": (0.35, 0.60),
        "phase": "objeciones",
        "message_count_range": (8, 20),
        "days_since_last_contact": (2, 7),
        "objection_type": "tiempo",
        "status": "interesado",
    },
    "ghost": {
        "intent_range": (0.30, 0.55),
        "phase": "descubrimiento",
        "message_count_range": (5, 15),
        "days_since_last_contact": (7, 21),
        "status": "fantasma",
    },
    "engaged_fan": {
        "intent_range": (0.10, 0.40),
        "phase": "cualificacion",
        "message_count_range": (30, 80),
        "days_since_last_contact": (0, 5),
        "status": "activo",
    },
    "new": {
        "intent_range": (0.05, 0.25),
        "phase": "inicio",
        "message_count_range": (1, 5),
        "days_since_last_contact": (0, 7),
        "status": "nuevo",
    },
    "customer": {
        "intent_range": (0.90, 1.0),
        "phase": "cierre",
        "message_count_range": (20, 50),
        "days_since_last_contact": (0, 30),
        "is_customer": True,
        "status": "cliente",
    },
}

# Hot leads for TodayMission
HOT_LEADS_DATA: List[Dict[str, Any]] = [
    {
        "name": "María García",
        "username": "maria_fit_23",
        "last_message": "¿Me pasas el link de pago?",
        "hours_ago": 2,
        "product": "Curso Nutrición Completo",
        "deal_value": 297.00,
        "context": "Madre de 2. Ya resolvió objeción de tiempo. Lista para comprar.",
        "action": "Envíale el link de pago ahora",
    },
    {
        "name": "Carlos Ruiz",
        "username": "carlos_running",
        "last_message": "Vale, lo quiero. ¿Aceptas Bizum?",
        "hours_ago": 5,
        "product": "Mentoría 1:1 Premium",
        "deal_value": 497.00,
        "context": "Preparando maratón. Alto compromiso demostrado.",
        "action": "Confirma Bizum y cierra la venta",
    },
    {
        "name": "Laura Fernández",
        "username": "laura_healthy",
        "last_message": "Perfecto, me lo pienso esta noche",
        "hours_ago": 8,
        "product": "Plan 12 Semanas",
        "deal_value": 197.00,
        "context": "Quiere perder 5kg para su boda en 3 meses.",
        "action": "Seguimiento mañana a primera hora",
    },
    {
        "name": "Pablo Hernández",
        "username": "pablo_gym",
        "last_message": "¿Hay opción de pago en cuotas?",
        "hours_ago": 3,
        "product": "Mentoría 1:1 Premium",
        "deal_value": 497.00,
        "context": "Interesado pero presupuesto ajustado.",
        "action": "Ofrece 3 cuotas de 166€",
    },
    {
        "name": "Carmen López",
        "username": "carmen_vida_sana",
        "last_message": "Me encanta todo lo que incluye!",
        "hours_ago": 4,
        "product": "Curso Nutrición Completo",
        "deal_value": 297.00,
        "context": "Muy entusiasmada. Solo necesita el empujón final.",
        "action": "Envía testimonio de cliente similar",
    },
    {
        "name": "Javier Moreno",
        "username": "javi_fitness",
        "last_message": "¿Cuándo empezamos?",
        "hours_ago": 1,
        "product": "Plan 12 Semanas",
        "deal_value": 197.00,
        "context": "Ya decidido. Quiere empezar esta semana.",
        "action": "Envía link y confirma fecha inicio",
    },
    {
        "name": "Elena Jiménez",
        "username": "elena_nutri",
        "last_message": "Ok, lo hablé con mi pareja y adelante",
        "hours_ago": 6,
        "product": "Mentoría 1:1 Premium",
        "deal_value": 497.00,
        "context": "Consultó con su pareja. Luz verde.",
        "action": "Cierra venta ahora",
    },
    {
        "name": "Miguel Álvarez",
        "username": "miguel_strong",
        "last_message": "¿Tienes hueco para empezar la semana que viene?",
        "hours_ago": 7,
        "product": "Mentoría Grupal",
        "deal_value": 300.00,
        "context": "Prefiere grupo por tema económico.",
        "action": "Confirma plaza en próximo grupo",
    },
    {
        "name": "Isabel Romero",
        "username": "isa_healthy_life",
        "last_message": "Genial, mándame cómo pagar",
        "hours_ago": 2,
        "product": "Curso Nutrición Completo",
        "deal_value": 297.00,
        "context": "Decisión tomada tras ver testimonios.",
        "action": "Envía link de pago inmediatamente",
    },
    {
        "name": "Antonio Navarro",
        "username": "antonio_fit",
        "last_message": "Me has convencido, vamos a ello",
        "hours_ago": 4,
        "product": "Plan 12 Semanas",
        "deal_value": 197.00,
        "context": "Resolvió dudas sobre el método.",
        "action": "Procesa venta y agenda onboarding",
    },
    {
        "name": "Lucía Díaz",
        "username": "lucia_wellness",
        "last_message": "Sí, quiero la mentoría individual",
        "hours_ago": 5,
        "product": "Mentoría 1:1 Premium",
        "deal_value": 497.00,
        "context": "Comparó con grupal, prefiere individual.",
        "action": "Confirma detalles y cierra",
    },
    {
        "name": "Andrés Martín",
        "username": "andres_deportista",
        "last_message": "¿El ebook lo puedo comprar ya?",
        "hours_ago": 3,
        "product": "Ebook Recetas Fit",
        "deal_value": 27.00,
        "context": "Compra pequeña, puede ser puerta de entrada.",
        "action": "Vende ebook + menciona upsell",
    },
]
