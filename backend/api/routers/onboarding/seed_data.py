"""Seed demo data and Stefano data injection endpoints."""

import logging
from typing import Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# =============================================================================
# STEFANO DATA - Pre-scraped from website
# =============================================================================

STEFANO_DATA = {
    "creator": {
        "name": "Stefano Bonanno",
        "tagline": "Te acompaño a sanar tu DOLOR y convertirlo en tu mayor FORTALEZA",
        "headline": "TRANSFORMA TU REALIDAD",
        "bio": """Coach, Terapeuta y Instructor de Movimiento y Respiración.

Después de años de sobreexigirme físicamente, descuidar mis emociones, tener patrones dependientes en relaciones y vivir inestabilidad financiera, una crisis me obligó a mirar hacia dentro. Esa crisis fue mi mayor regalo.

Hoy acompaño a otros en su viaje de transformación usando bioexistencia consciente, coaching cuántico, hipnosis, reprogramación inconsciente, breathwork y círculos de palabra.

El cambio constante produce una transformación, y al aplicarlo con conocimiento de leyes BIOLÓGICAS y espirituales, podrás desbloquear tu poder interior.""",
        "philosophy": "Trabajo con tres pilares: Mente Consciente (espacio seguro para expresión auténtica), Cuerpo Saludable (respiración y movimiento consciente), y Espíritu Libre (prácticas ancestrales + técnicas modernas).",
        "email": "coach@stefanobonanno.com",
        "phone": "695112016",
        "location": "Barcelona, España",
        "instagram": "@stefanobonanno",
        "website": "www.stefanobonanno.com",
    },
    "products": [
        {
            "id": "sintoma-plenitud",
            "name": "Del Síntoma a la Plenitud - Proceso 1:1",
            "description": """Programa personalizado de coaching 1:1 que combina coaching cuántico, reprogramación hipnótica y terapias holísticas para decodificar tus síntomas y lograr una transformación profunda.

Incluye:
• Análisis de síntomas y exploración de significados
• 3 sesiones de hipnosis para liberación emocional
• Sesiones de integración y coaching
• Soporte continuo por WhatsApp/email
• Acceso a dashboard personalizado con recursos

Duración: 3 meses
Sesiones: Semanales (12 sesiones totales)""",
            "price": 1497.0,
            "currency": "EUR",
            "duration": "3 meses",
            "type": "program",
            "category": "service",
            "product_type": "mentoria",
            "is_free": False,
            "includes": [
                "12 sesiones semanales",
                "3 sesiones de hipnosis",
                "Soporte WhatsApp",
                "Dashboard personalizado",
                "Recursos exclusivos",
            ],
        },
        {
            "id": "sesion-coaching",
            "name": "Sesión de Coaching Cuántico",
            "description": """Sesión individual de coaching cuántico para trabajar un tema específico. Ideal si necesitas claridad sobre una situación, desbloquear una creencia limitante o recibir guía en un momento de transición.

La sesión incluye:
• Exploración profunda del tema
• Técnicas de reprogramación
• Plan de acción concreto
• Seguimiento por mensaje

Duración: 90 minutos""",
            "price": 150.0,
            "currency": "EUR",
            "duration": "90 minutos",
            "type": "session",
            "category": "service",
            "product_type": "coaching",
            "is_free": False,
            "includes": [
                "Sesión de 90 min",
                "Técnicas de reprogramación",
                "Plan de acción",
                "Seguimiento por mensaje",
            ],
        },
        {
            "id": "discovery-call",
            "name": "Sesión Discovery Gratuita",
            "description": """Sesión de 30 minutos para conocernos, entender tu situación actual y ver si podemos trabajar juntos.

Sin compromiso. Solo una conversación honesta sobre dónde estás y dónde quieres llegar.

Reserva tu sesión y empecemos a transformar tu realidad.""",
            "price": 0.0,
            "currency": "EUR",
            "duration": "30 minutos",
            "type": "call",
            "category": "service",
            "product_type": "call",
            "is_free": True,
            "includes": [
                "Llamada de 30 min",
                "Análisis de situación",
                "Recomendación personalizada",
            ],
        },
        {
            "id": "challenge-11-dias",
            "name": "Fitpack Challenge 11 Días",
            "description": """Programa intensivo de 11 días diseñado para transformar tu energía, movimiento y mentalidad.

Incluye:
• Entrenamientos diarios al aire libre
• Sesiones de breathwork
• Comunidad de apoyo
• Acceso al grupo privado
• Material de apoyo

Más de 3,000 personas ya han pasado por este challenge.

Próxima edición: Consultar fechas""",
            "price": 97.0,
            "currency": "EUR",
            "duration": "11 días",
            "type": "challenge",
            "category": "product",
            "product_type": "curso",
            "is_free": False,
            "includes": [
                "11 entrenamientos",
                "Sesiones breathwork",
                "Comunidad privada",
                "Material de apoyo",
            ],
        },
        {
            "id": "taller-respira",
            "name": "Respira, Siente, Conecta - Taller Grupal",
            "description": """Experiencia transformadora que combina breathwork, meditación y baño de hielo.

Un espacio seguro para:
• Liberar tensiones acumuladas
• Conectar con tu cuerpo
• Superar límites mentales
• Conocer una comunidad consciente

Más de 1,000 personas han vivido esta experiencia.

Duración: 3 horas
Ubicación: Barcelona""",
            "price": 45.0,
            "currency": "EUR",
            "duration": "3 horas",
            "type": "workshop",
            "category": "service",
            "product_type": "sesion",
            "is_free": False,
            "includes": ["Sesión breathwork", "Meditación guiada", "Baño de hielo", "Comunidad"],
        },
        {
            "id": "podcast-sabios",
            "name": "Podcast Sabios y Salvajes",
            "description": """Episodios semanales donde comparto reflexiones, entrevistas y herramientas prácticas sobre desarrollo personal, bienestar y transformación consciente.

Disponible en Spotify y Apple Podcasts.""",
            "price": 0.0,
            "currency": "EUR",
            "type": "podcast",
            "category": "resource",
            "product_type": "podcast",
            "is_free": True,
            "includes": ["Episodios semanales", "Reflexiones prácticas", "Entrevistas exclusivas"],
        },
    ],
    "testimonials": [
        {
            "name": "Dafne Sandoval",
            "text": "Trabajar con Stefano transformó mi vida. Superé bloqueos, fortalecí mi relación conmigo misma y encontré claridad en momentos de confusión. Su enfoque es profundo pero accesible.",
            "program": "Proceso 1:1",
            "result": "Transformación profunda y empoderamiento",
        },
        {
            "name": "Eva González",
            "text": "Stefano me ayudó a desbloquear creencias que me frenaban. Sané patrones que arrastraba desde hace años. Su profesionalismo y cercanía hacen que te sientas en un espacio seguro.",
            "program": "Coaching Cuántico",
            "result": "Desbloqueo de creencias limitantes",
        },
        {
            "name": "Rocío Vargas",
            "text": "La terapia con Stefano marcó un antes y un después. Recuperé confianza en mí misma y me abrí a recibir. Cuatro meses de sesiones semanales que cambiaron mi perspectiva de vida.",
            "program": "Proceso 1:1",
            "result": "Recuperó confianza y apertura",
        },
        {
            "name": "Francisco Chiotta",
            "text": "Un espacio seguro y empático donde pude ser completamente auténtico. Stefano tiene un don para crear conexión genuina y guiarte hacia tu propia verdad.",
            "program": "Coaching Cuántico",
            "result": "Espacio seguro y conexión auténtica",
        },
        {
            "name": "Bianca Ioana Avram",
            "text": "Resultados rápidos y profundos. En pocas sesiones noté cambios significativos. La combinación de técnicas que usa Stefano es muy efectiva.",
            "program": "Proceso 1:1",
            "result": "Sanación profunda y rápida",
        },
        {
            "name": "Josh Feldberg",
            "text": "Llevo años trabajando con Stefano. Desde el bootcamp hasta el coaching individual, el apoyo ha sido integral. Ha sido clave en mi desarrollo personal y profesional.",
            "program": "Bootcamp + Coaching",
            "result": "Apoyo integral multi-año",
        },
    ],
    "faqs": [
        {
            "question": "¿Qué es el coaching cuántico?",
            "answer": "El coaching cuántico combina técnicas de coaching tradicional con principios de física cuántica y reprogramación del inconsciente. Trabajamos a nivel energético para transformar patrones limitantes y crear nuevas posibilidades en tu vida.",
        },
        {
            "question": "¿Cuánto dura un proceso de coaching?",
            "answer": "El proceso 'Del Síntoma a la Plenitud' tiene una duración de 3 meses con sesiones semanales. También ofrezco sesiones individuales para temas específicos.",
        },
        {
            "question": "¿Las sesiones son presenciales u online?",
            "answer": "Ofrezco ambas modalidades. Las sesiones presenciales son en Barcelona y las online las hacemos por videollamada. Ambas son igual de efectivas.",
        },
        {
            "question": "¿Qué incluye el Challenge de 11 Días?",
            "answer": "El Fitpack Challenge incluye 11 días de entrenamientos al aire libre, sesiones de breathwork, acceso a comunidad privada y material de apoyo. Es una experiencia transformadora para tu cuerpo y mente.",
        },
        {
            "question": "¿Cómo puedo empezar?",
            "answer": "El primer paso es agendar una Sesión Discovery gratuita de 30 minutos. Ahí hablamos de tu situación y vemos cuál es el mejor camino para ti. Sin compromiso.",
        },
    ],
    "methodology": {
        "pillars": ["Mente Consciente", "Cuerpo Saludable", "Espíritu Libre"],
        "approach": "Tres etapas: Consciencia (hacer visible lo invisible), Autenticidad (reconectar con tu ser genuino), Transformación (reprogramar patrones inconscientes)",
        "methods": [
            "Coaching cuántico",
            "Hipnosis",
            "Reprogramación inconsciente",
            "Breathwork",
            "Meditación",
            "Baño de hielo",
            "Círculos de palabra",
        ],
    },
    "tone_profile": {
        "formality": "informal",
        "energy": "high",
        "warmth": "very_warm",
        "uses_emojis": True,
        "common_emojis": ["🙏", "💪", "✨", "🔥", "❤️", "🌟"],
        "language": "es",
        "addressing": "tuteo",
        "style": "inspiracional, cercano, motivador, empático",
        "signature_phrases": [
            "Transforma tu realidad",
            "Del síntoma a la plenitud",
            "Tu dolor es tu mayor fortaleza",
            "Desbloquea tu poder interior",
        ],
    },
    "impact_numbers": {
        "individual_clients": 100,
        "challenge_participants": 3000,
        "workshop_participants": 1000,
    },
}


class SeedDemoRequest(BaseModel):
    """Request para sembrar datos demo cuando Instagram esta rate limited."""

    creator_id: str
    force: bool = False  # Si es true, crea datos aunque ya existan


@router.post("/seed-demo")
async def seed_demo_data(request: SeedDemoRequest):
    """
    Seed demo data for a creator when Instagram is rate limited.

    Creates:
    - 8 demo leads with various purchase intents
    - 3 demo products
    - Marks onboarding as completed
    - Activates the bot

    Use this when manual-setup fails due to Instagram rate limiting.
    """
    errors = []
    details = {"leads_created": 0, "products_created": 0}

    try:
        import random
        import uuid as uuid_module
        from datetime import datetime, timedelta

        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Product

        if not DATABASE_URL or not SessionLocal:
            return {"success": False, "error": "Database not configured"}

        session = SessionLocal()
        try:
            # Get or create creator
            creator = session.query(Creator).filter_by(name=request.creator_id).first()
            if not creator:
                creator = Creator(
                    id=uuid_module.uuid4(),
                    name=request.creator_id,
                    email=f"{request.creator_id}@clonnect.io",
                    bot_active=True,
                    onboarding_completed=True,
                    copilot_mode=True,
                )
                session.add(creator)
                session.commit()
                logger.info(f"[SeedDemo] Created new creator: {request.creator_id}")

            creator_uuid = creator.id

            # Create demo products
            demo_products = [
                {
                    "name": "Consultoría 1:1",
                    "price": 150.0,
                    "description": "Sesión de consultoría personalizada de 1 hora",
                },
                {
                    "name": "Curso Online",
                    "price": 97.0,
                    "description": "Acceso completo al curso con materiales",
                },
                {
                    "name": "Mentoría Grupal",
                    "price": 49.0,
                    "description": "Sesión grupal mensual con Q&A",
                },
            ]

            for prod in demo_products:
                existing = (
                    session.query(Product)
                    .filter_by(creator_id=creator_uuid, name=prod["name"])
                    .first()
                )
                if not existing or request.force:
                    if existing and request.force:
                        session.delete(existing)
                    new_product = Product(
                        id=uuid_module.uuid4(),
                        creator_id=creator_uuid,
                        name=prod["name"],
                        price=prod["price"],
                        description=prod["description"],
                        is_active=True,
                    )
                    session.add(new_product)
                    details["products_created"] += 1

            # NOTE: Demo leads DISABLED - only load real Instagram DMs

            # Mark onboarding as completed and activate bot
            creator.onboarding_completed = True
            creator.bot_active = True

            session.commit()
            logger.info(
                f"[SeedDemo] Created {details['leads_created']} leads and {details['products_created']} products for {request.creator_id}"
            )

            return {
                "success": True,
                "creator_id": request.creator_id,
                "details": details,
                "onboarding_completed": True,
                "bot_activated": True,
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[SeedDemo] Error: {e}")
        return {"success": False, "creator_id": request.creator_id, "error": str(e)}


@router.post("/inject-stefano-data")
async def inject_stefano_data():
    """
    Inject pre-scraped Stefano Bonanno data into the system.

    This endpoint:
    1. Creates real products from stefanobonanno.com
    2. Creates realistic demo leads with conversations
    3. Creates demo messages/conversations
    4. Generates ToneProfile based on his style
    5. Indexes all content in RAG for bot responses
    6. Marks onboarding as completed
    7. Activates the bot

    Use this for demos when Instagram is rate-limited.
    """
    creator_id = "stefano_auto"
    details = {
        "products_created": 0,
        "leads_created": 0,
        "messages_created": 0,
        "rag_documents": 0,
        "tone_profile": False,
    }
    errors = []

    try:
        import json
        import random
        import uuid as uuid_module
        from datetime import datetime, timedelta

        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message, Product

        if not DATABASE_URL or not SessionLocal:
            return {"success": False, "error": "Database not configured"}

        session = SessionLocal()
        try:
            # ================================================================
            # STEP 1: Get or create creator
            # ================================================================
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                creator = Creator(
                    id=uuid_module.uuid4(),
                    name=creator_id,
                    email="coach@stefanobonanno.com",
                    bot_active=True,
                    onboarding_completed=True,
                    copilot_mode=True,
                    clone_name="Stefano Bonanno",
                    clone_tone="inspirational",
                )
                session.add(creator)
                session.commit()
                logger.info(f"[InjectStefano] Created creator: {creator_id}")
            else:
                creator.clone_name = "Stefano Bonanno"
                creator.email = "coach@stefanobonanno.com"

            creator_uuid = creator.id

            # ================================================================
            # STEP 2: Delete existing data for clean injection
            # ================================================================
            # Delete existing messages for this creator's leads
            existing_leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
            msg_count = 0
            for lead in existing_leads:
                msg_count += session.query(Message).filter_by(lead_id=lead.id).delete()
            lead_count = session.query(Lead).filter_by(creator_id=creator_uuid).delete()
            prod_count = session.query(Product).filter_by(creator_id=creator_uuid).delete()
            session.commit()

            logger.warning(
                f"[InjectStefano] Deleted existing data: {msg_count} messages, "
                f"{lead_count} leads, {prod_count} products"
            )

            # ================================================================
            # STEP 3: Create REAL products from website
            # ================================================================
            for prod_data in STEFANO_DATA["products"]:
                new_product = Product(
                    id=uuid_module.uuid4(),
                    creator_id=creator_uuid,
                    name=prod_data["name"],
                    description=prod_data["description"],
                    price=prod_data["price"],
                    currency=prod_data.get("currency", "EUR"),
                    # Taxonomy fields
                    category=prod_data.get("category", "product"),
                    product_type=prod_data.get("product_type", "otro"),
                    is_free=prod_data.get("is_free", False),
                    is_active=True,
                )
                session.add(new_product)
                details["products_created"] += 1

            # ================================================================
            # STEP 4: Create realistic leads with conversations
            # ================================================================
            demo_conversations = [
                {
                    "lead": {
                        "name": "Carlos Méndez",
                        "username": "carlos_wellness",
                        "platform": "instagram",
                        "intent": 0.9,
                        "status": "hot",
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": "Hola Stefano! Vi tu contenido sobre coaching cuántico y me interesa mucho. ¿Cómo funciona el proceso 1:1?",
                        },
                        {
                            "role": "assistant",
                            "content": "¡Hola Carlos! 🙏 Qué bueno que te resuene el coaching cuántico. El proceso 'Del Síntoma a la Plenitud' es un viaje de 3 meses donde trabajamos juntos semanalmente. Combinamos coaching cuántico, hipnosis y reprogramación del inconsciente. ¿Qué te gustaría transformar en tu vida? ✨",
                        },
                        {
                            "role": "user",
                            "content": "Llevo tiempo sintiéndome estancado en mi carrera y relaciones. ¿Cuánto cuesta el programa?",
                        },
                        {
                            "role": "assistant",
                            "content": "Entiendo perfectamente ese sentimiento de estancamiento. El programa completo de 3 meses es €1497 e incluye 12 sesiones semanales, 3 sesiones de hipnosis, soporte por WhatsApp y acceso a recursos exclusivos. ¿Te gustaría agendar una sesión discovery gratuita de 30 min para conocernos? 💪",
                        },
                    ],
                },
                {
                    "lead": {
                        "name": "Laura Torres",
                        "username": "laura_fit",
                        "platform": "instagram",
                        "intent": 0.7,
                        "status": "hot",
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": "Hola! Me interesa el Challenge de 11 días, ¿cuándo es el próximo?",
                        },
                        {
                            "role": "assistant",
                            "content": "¡Hola Laura! 🔥 El Fitpack Challenge es una experiencia increíble. Más de 3,000 personas ya lo han vivido. Son 11 días de entrenamientos al aire libre, breathwork y comunidad. Cuesta €97 e incluye todo el material. Te escribo por privado las fechas disponibles 💪",
                        },
                        {
                            "role": "user",
                            "content": "Genial! También vi que haces talleres de respiración, ¿me cuentas más?",
                        },
                        {
                            "role": "assistant",
                            "content": "'Respira, Siente, Conecta' es una experiencia de 3 horas donde combinamos breathwork, meditación y baño de hielo 🧊 Es muy transformador. Cuesta €45 y lo hacemos en Barcelona. ¿Te apuntas a la próxima? ✨",
                        },
                    ],
                },
                {
                    "lead": {
                        "name": "Ana Martínez",
                        "username": "ana_coach",
                        "platform": "instagram",
                        "intent": 0.95,
                        "status": "hot",
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": "Stefano, necesito ayuda. Estoy pasando por un momento muy difícil y siento que necesito un cambio profundo.",
                        },
                        {
                            "role": "assistant",
                            "content": "Ana, gracias por compartir esto conmigo 🙏 Los momentos difíciles muchas veces son el inicio de grandes transformaciones. Mi trabajo es acompañarte a convertir ese dolor en tu mayor fortaleza. ¿Quieres que agendemos una sesión discovery gratuita para hablar de tu situación? ❤️",
                        },
                        {"role": "user", "content": "Sí, por favor. ¿Cómo puedo reservar?"},
                        {
                            "role": "assistant",
                            "content": "Perfecto Ana. La sesión discovery es de 30 minutos, sin compromiso. Solo para conocernos y ver si hay conexión para trabajar juntos. Te dejo el enlace para agendar: [link]. Estoy aquí para ti ✨",
                        },
                    ],
                },
                {
                    "lead": {
                        "name": "Miguel Ángel",
                        "username": "miguelangel_bcn",
                        "platform": "instagram",
                        "intent": 0.5,
                        "status": "warm",
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": "Hola, ¿qué es exactamente el coaching cuántico?",
                        },
                        {
                            "role": "assistant",
                            "content": "¡Hola Miguel Ángel! 🌟 El coaching cuántico combina técnicas de coaching tradicional con principios de física cuántica y reprogramación del inconsciente. Trabajamos a nivel energético para transformar patrones limitantes. Es como reprogramar el software de tu mente para crear nuevas posibilidades. ¿Hay algo específico que te gustaría cambiar en tu vida?",
                        },
                    ],
                },
                {
                    "lead": {
                        "name": "Sofía Navarro",
                        "username": "sofia_yoga",
                        "platform": "instagram",
                        "intent": 0.6,
                        "status": "warm",
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": "Vi que haces sesiones de breathwork. ¿Qué beneficios tiene?",
                        },
                        {
                            "role": "assistant",
                            "content": "¡Hola Sofía! El breathwork es una herramienta muy poderosa 🌬️ Te ayuda a liberar tensiones acumuladas, procesar emociones y conectar con tu cuerpo de una forma profunda. En el taller 'Respira, Siente, Conecta' lo combinamos con meditación y baño de hielo. Es una experiencia que te marca. ¿Has hecho breathwork antes?",
                        },
                    ],
                },
                {
                    "lead": {
                        "name": "Pedro García",
                        "username": "pedro_wellness",
                        "platform": "whatsapp",
                        "intent": 0.4,
                        "status": "warm",
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": "Hola Stefano, un amigo me recomendó tu trabajo. ¿Podrías explicarme qué haces?",
                        },
                        {
                            "role": "assistant",
                            "content": "¡Hola Pedro! Qué bien que llegues por recomendación 🙏 Soy coach y terapeuta. Acompaño a personas a transformar su realidad trabajando con mente, cuerpo y espíritu. Uso coaching cuántico, hipnosis, breathwork y otras técnicas. Mi enfoque es convertir tu dolor en tu mayor fortaleza. ¿Qué te gustaría trabajar?",
                        },
                    ],
                },
                {
                    "lead": {
                        "name": "Elena Ruiz",
                        "username": "elena_mindful",
                        "platform": "instagram",
                        "intent": 0.3,
                        "status": "cold",
                    },
                    "messages": [
                        {
                            "role": "user",
                            "content": "Hola, ¿tienes algún recurso gratuito para empezar?",
                        },
                        {
                            "role": "assistant",
                            "content": "¡Hola Elena! 🌟 Claro que sí. Tengo el podcast 'Sabios y Salvajes' en Spotify donde comparto mucho contenido. También puedes suscribirte a mi newsletter y te envío una guía de planificación anual gratis. ¿Te interesa algún tema en particular?",
                        },
                    ],
                },
                {
                    "lead": {
                        "name": "Roberto Sánchez",
                        "username": "roberto_coach",
                        "platform": "instagram",
                        "intent": 0.2,
                        "status": "cold",
                    },
                    "messages": [
                        {"role": "user", "content": "Interesante tu contenido 👍"},
                        {
                            "role": "assistant",
                            "content": "¡Gracias Roberto! 🙏 Me alegra que resuene contigo. Si alguna vez quieres profundizar en algún tema o tienes preguntas, aquí estoy. ¡Un abrazo! ✨",
                        },
                    ],
                },
            ]

            for conv in demo_conversations:
                lead_data = conv["lead"]
                platform_user_id = f"stefano_{lead_data['username']}"

                new_lead = Lead(
                    id=uuid_module.uuid4(),
                    creator_id=creator_uuid,
                    platform=lead_data["platform"],
                    platform_user_id=platform_user_id,
                    username=lead_data["username"],
                    full_name=lead_data["name"],
                    purchase_intent=lead_data["intent"],
                    status=lead_data["status"],
                    score=int(lead_data["intent"] * 100),
                    first_contact_at=datetime.utcnow() - timedelta(days=random.randint(5, 30)),
                    last_contact_at=datetime.utcnow() - timedelta(hours=random.randint(1, 72)),
                )
                session.add(new_lead)
                session.flush()  # Get the ID
                details["leads_created"] += 1

                # Add messages
                for i, msg in enumerate(conv["messages"]):
                    new_message = Message(
                        id=uuid_module.uuid4(),
                        lead_id=new_lead.id,
                        role=msg["role"],
                        content=msg["content"],
                        status="sent",
                        created_at=datetime.utcnow() - timedelta(hours=len(conv["messages"]) - i),
                    )
                    session.add(new_message)
                    details["messages_created"] += 1

            # ================================================================
            # STEP 5: Update creator settings
            # ================================================================
            creator.bot_active = True
            creator.onboarding_completed = True
            creator.clone_name = STEFANO_DATA["creator"]["name"]

            # Store tone profile as JSON in a field if available
            tone_data = STEFANO_DATA["tone_profile"]

            session.commit()
            logger.info(
                f"[InjectStefano] Created {details['products_created']} products, {details['leads_created']} leads, {details['messages_created']} messages"
            )

        finally:
            session.close()

        # ================================================================
        # STEP 6: Index content in RAG
        # ================================================================
        try:
            from core.rag import get_hybrid_rag

            rag = get_hybrid_rag()

            # Index products
            for prod in STEFANO_DATA["products"]:
                doc_id = f"stefano_product_{prod['id']}"
                content = f"""Producto: {prod['name']}
Precio: €{prod['price']}
Duración: {prod['duration']}
Descripción: {prod['description']}
Incluye: {', '.join(prod['includes'])}"""
                rag.add_document(
                    doc_id=doc_id,
                    text=content,
                    metadata={
                        "creator_id": creator_id,
                        "source_type": "product",
                        "product_id": prod["id"],
                        "price": prod["price"],
                    },
                )
                details["rag_documents"] += 1

            # Index testimonials
            for i, test in enumerate(STEFANO_DATA["testimonials"]):
                doc_id = f"stefano_testimonial_{i}"
                content = f"""Testimonio de {test['name']} sobre {test['program']}:
"{test['text']}"
Resultado: {test['result']}"""
                rag.add_document(
                    doc_id=doc_id,
                    text=content,
                    metadata={"creator_id": creator_id, "source_type": "testimonial"},
                )
                details["rag_documents"] += 1

            # Index FAQs
            for i, faq in enumerate(STEFANO_DATA["faqs"]):
                doc_id = f"stefano_faq_{i}"
                content = f"""Pregunta: {faq['question']}
Respuesta: {faq['answer']}"""
                rag.add_document(
                    doc_id=doc_id,
                    text=content,
                    metadata={"creator_id": creator_id, "source_type": "faq"},
                )
                details["rag_documents"] += 1

            # Index methodology
            meth = STEFANO_DATA["methodology"]
            doc_id = "stefano_methodology"
            content = f"""Metodología de Stefano Bonanno:
Pilares: {', '.join(meth['pillars'])}
Enfoque: {meth['approach']}
Métodos: {', '.join(meth['methods'])}"""
            rag.add_document(
                doc_id=doc_id,
                text=content,
                metadata={"creator_id": creator_id, "source_type": "methodology"},
            )
            details["rag_documents"] += 1

            # Index bio
            bio = STEFANO_DATA["creator"]
            doc_id = "stefano_bio"
            content = f"""Sobre Stefano Bonanno:
{bio['bio']}

Filosofía: {bio['philosophy']}

Contacto: {bio['email']} | {bio['phone']}
Ubicación: {bio['location']}
Web: {bio['website']}
Instagram: {bio['instagram']}"""
            rag.add_document(
                doc_id=doc_id,
                text=content,
                metadata={"creator_id": creator_id, "source_type": "bio"},
            )
            details["rag_documents"] += 1

            logger.info(f"[InjectStefano] Indexed {details['rag_documents']} documents in RAG")

        except Exception as e:
            errors.append(f"RAG indexing failed: {str(e)}")
            logger.error(f"[InjectStefano] RAG error: {e}")

        # ================================================================
        # STEP 7: Save ToneProfile
        # ================================================================
        try:
            from core.tone_service import save_tone_profile
            from ingestion.tone_analyzer import ToneProfile

            tone = STEFANO_DATA["tone_profile"]
            profile = ToneProfile(
                creator_id=creator_id,
                formality=tone["formality"],
                energy=tone["energy"],
                warmth=tone["warmth"],
                uses_emojis=tone["uses_emojis"],
                emoji_frequency="high",
                common_emojis=tone["common_emojis"],
                signature_phrases=tone["signature_phrases"],
                vocabulary_level="medium",
                sentence_length="medium",
                primary_language=tone["language"],
                main_topics=["coaching", "bienestar", "transformación", "breathwork"],
                analyzed_posts_count=50,
            )
            await save_tone_profile(profile)
            details["tone_profile"] = True
            logger.info(f"[InjectStefano] ToneProfile saved")

        except Exception as e:
            errors.append(f"ToneProfile failed: {str(e)}")
            logger.error(f"[InjectStefano] ToneProfile error: {e}")

        return {
            "success": True,
            "creator_id": creator_id,
            "details": details,
            "errors": errors if errors else None,
            "products": [p["name"] for p in STEFANO_DATA["products"]],
            "message": "Stefano data injected successfully! Dashboard should show real products and leads.",
        }

    except Exception as e:
        logger.error(f"[InjectStefano] Error: {e}")
        import traceback

        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}
