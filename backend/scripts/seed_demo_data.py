#!/usr/bin/env python3
"""
Seed script to populate database with realistic demo data.

Usage:
    python scripts/seed_demo_data.py

This script is idempotent - it can be run multiple times safely.
It clears existing demo data before inserting new data.
"""

import sys
import os
import random
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from api.database import SessionLocal
from api.models import (
    Creator, Lead, Message, Product, KnowledgeBase,
    CalendarBooking, FollowerMemoryDB, ConversationStateDB,
    UserProfileDB,
)

# Import demo data modules
from scripts.demo_data.config import (
    CREATOR_ID, SEGMENT_DISTRIBUTION, PRODUCTS, TODAY_BOOKINGS,
    SEGMENT_CHARACTERISTICS,
)
from scripts.demo_data.names import (
    generate_full_name, generate_username, generate_email, generate_phone,
)
from scripts.demo_data.messages import (
    get_conversation_for_segment, generate_extended_conversation,
)
from scripts.demo_data.interests import (
    INTERESTS_WEIGHTS,
)


def main():
    """Main entry point for seed script."""
    print("\n" + "=" * 60)
    print("🌱 CLONNECT DEMO DATA SEED")
    print("=" * 60)

    db = SessionLocal()

    try:
        print("\n🗑️  Limpiando datos existentes...")
        clear_existing_data(db, CREATOR_ID)

        print("\n👤 Creando creador y productos...")
        creator = create_creator(db, CREATOR_ID)
        create_products(db, str(creator.id))

        print("\n👥 Generando 200 followers con distribución por segmento...")
        followers = create_followers(db, str(creator.id))

        print("\n🎯 Creando leads y conversation states...")
        create_leads_and_states(db, str(creator.id), followers)

        print("\n🧠 Creando user profiles...")
        create_user_profiles(db, str(creator.id), followers)

        print("\n💬 Generando mensajes de conversación...")
        create_messages(db, followers)

        print("\n📅 Creando bookings...")
        create_bookings(db, str(creator.id))

        print("\n📚 Creando knowledge base...")
        create_knowledge_base(db, str(creator.id))

        db.commit()

        print("\n" + "=" * 60)
        print("✅ SEED COMPLETADO!")
        print("=" * 60)
        print_summary(db, str(creator.id))

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        db.close()


def clear_existing_data(db: Session, creator_id: str):
    """Clear all demo data for the creator. Order matters due to foreign keys."""
    # Get creator by name to find UUID
    creator = db.query(Creator).filter(Creator.name == creator_id).first()

    if creator:
        creator_uuid = str(creator.id)
        print(f"   Encontrado creador existente: {creator_uuid}")

        # Delete in order respecting foreign keys
        msg_count = db.query(Message).filter(
            Message.lead_id.in_(
                db.query(Lead.id).filter(Lead.creator_id == creator.id)
            )
        ).delete(synchronize_session=False)
        print(f"   - Messages: {msg_count}")

        lead_count = db.query(Lead).filter(Lead.creator_id == creator.id).delete()
        print(f"   - Leads: {lead_count}")

        cs_count = db.query(ConversationStateDB).filter(
            ConversationStateDB.creator_id == creator_id
        ).delete()
        print(f"   - ConversationStates: {cs_count}")

        up_count = db.query(UserProfileDB).filter(
            UserProfileDB.creator_id == creator_id
        ).delete()
        print(f"   - UserProfiles: {up_count}")

        fm_count = db.query(FollowerMemoryDB).filter(
            FollowerMemoryDB.creator_id == creator_id
        ).delete()
        print(f"   - FollowerMemories: {fm_count}")

        booking_count = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id
        ).delete()
        print(f"   - Bookings: {booking_count}")

        product_count = db.query(Product).filter(
            Product.creator_id == creator.id
        ).delete()
        print(f"   - Products: {product_count}")

        kb_count = db.query(KnowledgeBase).filter(
            KnowledgeBase.creator_id == creator.id
        ).delete()
        print(f"   - KnowledgeBase: {kb_count}")

        db.delete(creator)
        print("   - Creator: 1")

        db.commit()
    else:
        print("   No hay datos previos para limpiar")


def create_creator(db: Session, creator_id: str) -> Creator:
    """Create the demo creator."""
    creator = Creator(
        id=uuid.uuid4(),
        email="demo@fitpack.com",
        name=creator_id,
        api_key=f"demo_key_{uuid.uuid4().hex[:16]}",
        bot_active=False,  # Demo creator — activate manually
        copilot_mode=True,
        clone_tone="friendly",
        clone_style="Comunicación cercana y motivadora. Uso de emojis moderado. Enfoque en resultados.",
        clone_name="FitPack",
        welcome_message="¡Hola! 👋 Soy el asistente de FitPack. ¿En qué puedo ayudarte hoy?",
        onboarding_completed=True,
        clone_status="complete",
        product_price=297.0,
        knowledge_about={
            "business_name": "FitPack",
            "niche": "Nutrición y fitness",
            "target_audience": "Mujeres 25-45 que quieren mejorar su alimentación",
            "main_products": ["Curso Nutrición Completo", "Mentoría 1:1", "Plan 12 Semanas"],
            "unique_value": "Acompañamiento personalizado + método probado",
        },
    )
    db.add(creator)
    db.flush()
    print(f"   ✓ Creador: {creator.name} ({creator.id})")
    return creator


def create_products(db: Session, creator_id: str):
    """Create demo products."""
    # Get creator UUID
    creator = db.query(Creator).filter(Creator.name == CREATOR_ID).first()

    for product_data in PRODUCTS:
        product = Product(
            id=uuid.uuid4(),
            creator_id=creator.id,
            name=product_data["name"],
            description=product_data["description"],
            short_description=product_data["short_description"],
            price=product_data["price"],
            category=product_data["category"],
            product_type=product_data["product_type"],
            currency=product_data["currency"],
            is_active=True,
            price_verified=True,
            confidence=0.95,
        )
        db.add(product)

    db.flush()
    print(f"   ✓ Productos: {len(PRODUCTS)}")


def create_followers(db: Session, creator_id: str) -> List[Dict[str, Any]]:
    """Create followers with segment distribution."""
    followers = []
    follower_index = 0

    for segment, count in SEGMENT_DISTRIBUTION.items():
        characteristics = SEGMENT_CHARACTERISTICS.get(segment, {})

        for i in range(count):
            first_name, last_name = generate_full_name()
            username = generate_username(first_name, follower_index)
            email = generate_email(first_name, last_name)
            phone = generate_phone()
            follower_id = f"ig_{uuid.uuid4().hex[:12]}"

            # Calculate dates based on segment
            days_since_first = random.randint(30, 180)
            days_since_last = random.randint(
                characteristics.get("days_since_last_contact", (0, 7))[0],
                characteristics.get("days_since_last_contact", (0, 7))[1]
            )

            first_contact = datetime.now() - timedelta(days=days_since_first)
            last_contact = datetime.now() - timedelta(days=days_since_last)

            # Message count based on segment
            msg_range = characteristics.get("message_count_range", (5, 15))
            total_messages = random.randint(msg_range[0], msg_range[1])

            # Purchase intent based on segment
            intent_range = characteristics.get("intent_range", (0.1, 0.5))
            purchase_intent = round(random.uniform(intent_range[0], intent_range[1]), 2)

            # Interests (random subset)
            all_interests = list(INTERESTS_WEIGHTS.keys())
            num_interests = random.randint(2, 5)
            interests = random.sample(all_interests, min(num_interests, len(all_interests)))

            # Products discussed
            products_discussed = random.sample(
                [p["name"] for p in PRODUCTS],
                random.randint(1, 3)
            )

            # Objections
            objections_raised = []
            objections_handled = []

            if segment == "price_objector":
                objections_raised = ["precio"]
            elif segment == "time_objector":
                objections_raised = ["tiempo"]
            elif segment in ["hot_lead", "customer"]:
                objections_raised = random.sample(["precio", "tiempo", "duda"], random.randint(1, 2))
                objections_handled = list(objections_raised)

            # Status mapping
            status = characteristics.get("status", "nuevo")

            # Is customer?
            is_customer = characteristics.get("is_customer", False)
            is_lead = segment in ["hot_lead", "warm_lead", "price_objector", "time_objector", "customer"]

            # Create FollowerMemory
            follower_memory = FollowerMemoryDB(
                id=uuid.uuid4(),
                creator_id=CREATOR_ID,
                follower_id=follower_id,
                username=username,
                name=f"{first_name} {last_name}",
                first_contact=first_contact.isoformat(),
                last_contact=last_contact.isoformat(),
                total_messages=total_messages,
                interests=interests,
                products_discussed=products_discussed,
                objections_raised=objections_raised,
                objections_handled=objections_handled,
                purchase_intent_score=purchase_intent,
                is_lead=is_lead,
                is_customer=is_customer,
                status=status,
                preferred_language="es",
                links_sent_count=random.randint(0, 3) if is_lead else 0,
                alternative_contact=email if random.random() > 0.7 else "",
                alternative_contact_type="email" if random.random() > 0.7 else "",
            )
            db.add(follower_memory)

            follower_data = {
                "follower_id": follower_id,
                "username": username,
                "name": f"{first_name} {last_name}",
                "email": email,
                "phone": phone,
                "segment": segment,
                "characteristics": characteristics,
                "first_contact": first_contact,
                "last_contact": last_contact,
                "total_messages": total_messages,
                "purchase_intent": purchase_intent,
                "interests": interests,
                "products_discussed": products_discussed,
                "objections_raised": objections_raised,
                "is_customer": is_customer,
                "is_lead": is_lead,
                "status": status,
            }
            followers.append(follower_data)
            follower_index += 1

    db.flush()
    print(f"   ✓ FollowerMemories: {len(followers)}")

    # Print segment distribution
    for segment, count in SEGMENT_DISTRIBUTION.items():
        print(f"      - {segment}: {count}")

    return followers


def create_leads_and_states(db: Session, creator_id: str, followers: List[Dict[str, Any]]):
    """Create leads and conversation states for qualifying followers."""
    creator = db.query(Creator).filter(Creator.name == CREATOR_ID).first()
    lead_count = 0
    state_count = 0

    for follower in followers:
        if not follower["is_lead"]:
            continue

        # Create Lead
        segment = follower["segment"]
        characteristics = follower["characteristics"]

        # Deal value based on product interest
        product_prices = {p["name"]: p["price"] for p in PRODUCTS}
        interested_product = follower["products_discussed"][0] if follower["products_discussed"] else "Curso Nutrición Completo"
        deal_value = product_prices.get(interested_product, 297.0)

        lead = Lead(
            id=uuid.uuid4(),
            creator_id=creator.id,
            platform="instagram",
            platform_user_id=follower["follower_id"],
            username=follower["username"],
            full_name=follower["name"],
            status=follower["status"],
            score=int(follower["purchase_intent"] * 100),
            purchase_intent=follower["purchase_intent"],
            context={
                "segment": segment,
                "interests": follower["interests"],
                "products_discussed": follower["products_discussed"],
                "objections": follower["objections_raised"],
            },
            first_contact_at=follower["first_contact"],
            last_contact_at=follower["last_contact"],
            email=follower["email"] if random.random() > 0.5 else None,
            phone=follower["phone"] if random.random() > 0.7 else None,
            deal_value=deal_value,
            source="instagram_dm",
            tags=[segment] + (["customer"] if follower["is_customer"] else []),
        )
        db.add(lead)
        lead_count += 1

        # Create ConversationState
        phase = characteristics.get("phase", "inicio")
        conv_state = ConversationStateDB(
            id=uuid.uuid4(),
            creator_id=CREATOR_ID,
            follower_id=follower["follower_id"],
            phase=phase,
            message_count=follower["total_messages"],
            context={
                "name": follower["name"],
                "product_interested": interested_product,
                "objections_raised": follower["objections_raised"],
                "price_discussed": "precio" in follower["objections_raised"] or segment == "hot_lead",
            },
        )
        db.add(conv_state)
        state_count += 1

    db.flush()
    print(f"   ✓ Leads: {lead_count}")
    print(f"   ✓ ConversationStates: {state_count}")


def create_user_profiles(db: Session, creator_id: str, followers: List[Dict[str, Any]]):
    """Create user profiles with weighted interests."""
    profile_count = 0

    for follower in followers:
        # Build weighted interests
        interests_with_weights = {}
        for interest in follower["interests"]:
            base_weight = INTERESTS_WEIGHTS.get(interest, 0.3)
            # Add some randomness
            weight = min(1.0, max(0.1, base_weight + random.uniform(-0.1, 0.1)))
            interests_with_weights[interest] = round(weight, 2)

        # Build objections list
        objections = []
        for obj in follower["objections_raised"]:
            objections.append({
                "type": obj,
                "context": f"Objeción de {obj} detectada en conversación",
                "timestamp": follower["last_contact"].isoformat(),
            })

        # Interested products
        interested_products = []
        for product_name in follower["products_discussed"]:
            interested_products.append({
                "name": product_name,
                "first_interest": follower["first_contact"].isoformat(),
                "interest_count": random.randint(1, 5),
            })

        profile = UserProfileDB(
            id=uuid.uuid4(),
            creator_id=CREATOR_ID,
            user_id=follower["follower_id"],
            preferences={
                "language": "es",
                "response_time": random.choice(["morning", "afternoon", "evening"]),
                "communication_style": random.choice(["formal", "casual", "friendly"]),
            },
            interests=interests_with_weights,
            objections=objections,
            interested_products=interested_products,
            interaction_count=follower["total_messages"],
            last_interaction=follower["last_contact"],
        )
        db.add(profile)
        profile_count += 1

    db.flush()
    print(f"   ✓ UserProfiles: {profile_count}")


def create_messages(db: Session, followers: List[Dict[str, Any]]):
    """Create message history for each follower."""
    # Get all leads
    leads = {lead.platform_user_id: lead for lead in db.query(Lead).all()}

    total_messages = 0

    for follower in followers:
        lead = leads.get(follower["follower_id"])
        if not lead:
            continue

        # Get conversation template for this segment
        segment = follower["segment"]
        base_conversation = get_conversation_for_segment(segment, random.randint(0, 100))

        # Extend to target length
        target_length = follower["total_messages"]
        conversation = generate_extended_conversation(base_conversation, target_length)

        # Calculate message timestamps
        first_contact = follower["first_contact"]
        last_contact = follower["last_contact"]
        total_duration = (last_contact - first_contact).total_seconds()

        for i, msg in enumerate(conversation):
            # Calculate timestamp for this message
            if len(conversation) > 1:
                progress = i / (len(conversation) - 1)
            else:
                progress = 0

            msg_time = first_contact + timedelta(seconds=total_duration * progress)

            # Add some randomness to timing
            msg_time += timedelta(minutes=random.randint(-30, 30))

            message = Message(
                id=uuid.uuid4(),
                lead_id=lead.id,
                role=msg["role"],
                content=msg["content"],
                intent=msg.get("intent"),
                status="sent",
                created_at=msg_time,
            )
            db.add(message)
            total_messages += 1

    db.flush()
    print(f"   ✓ Messages: {total_messages}")


def create_bookings(db: Session, creator_id: str):
    """Create calendar bookings."""
    booking_count = 0
    now = datetime.now()

    # Today's bookings
    for booking_data in TODAY_BOOKINGS:
        time_parts = booking_data["time"].split(":")
        scheduled_at = now.replace(
            hour=int(time_parts[0]),
            minute=int(time_parts[1]),
            second=0,
            microsecond=0
        )

        booking = CalendarBooking(
            id=uuid.uuid4(),
            creator_id=CREATOR_ID,
            follower_id=f"ig_{uuid.uuid4().hex[:12]}",
            meeting_type=booking_data["type"].lower().replace(" ", "_"),
            platform="calendly",
            status="scheduled",
            scheduled_at=scheduled_at,
            duration_minutes=30,
            guest_name=booking_data["name"],
            guest_email=booking_data["email"],
            guest_phone=booking_data.get("phone", ""),
            notes=f"Interesado en: {booking_data['product']}",
        )
        db.add(booking)
        booking_count += 1

    # Future bookings (next 7 days)
    for i in range(10):
        future_date = now + timedelta(days=random.randint(1, 7))
        hour = random.choice([9, 10, 11, 14, 15, 16, 17, 18])
        scheduled_at = future_date.replace(hour=hour, minute=random.choice([0, 30]))

        first_name, last_name = generate_full_name()
        email = generate_email(first_name, last_name)

        booking = CalendarBooking(
            id=uuid.uuid4(),
            creator_id=CREATOR_ID,
            follower_id=f"ig_{uuid.uuid4().hex[:12]}",
            meeting_type=random.choice(["discovery", "follow_up", "demo", "closing"]),
            platform="calendly",
            status="scheduled",
            scheduled_at=scheduled_at,
            duration_minutes=random.choice([30, 45, 60]),
            guest_name=f"{first_name} {last_name}",
            guest_email=email,
        )
        db.add(booking)
        booking_count += 1

    db.flush()
    print(f"   ✓ Bookings: {booking_count}")


def create_knowledge_base(db: Session, creator_id: str):
    """Create FAQ knowledge base entries."""
    creator = db.query(Creator).filter(Creator.name == CREATOR_ID).first()

    faqs = [
        ("¿Qué incluye el curso de nutrición?", "El curso incluye 12 semanas de plan alimenticio, más de 50 recetas, vídeos explicativos, lista de la compra semanal y seguimiento personalizado."),
        ("¿Cuánto cuesta la mentoría?", "La mentoría 1:1 Premium tiene un precio de 497€. Incluye seguimiento diario por WhatsApp y 4 llamadas mensuales."),
        ("¿Puedo pagar en cuotas?", "Sí, ofrecemos pago en 3 cuotas sin intereses para todos nuestros programas."),
        ("¿Cuánto tiempo tardan en verse resultados?", "Los primeros cambios se notan en 2-3 semanas. Para resultados significativos, recomendamos al menos 8-12 semanas de constancia."),
        ("¿El programa sirve para vegetarianos?", "Sí, tenemos versiones adaptadas para vegetarianos y veganos con alternativas proteicas de origen vegetal."),
        ("¿Necesito ir al gimnasio?", "No es necesario. El programa incluye opciones de entrenamiento en casa sin material."),
        ("¿Qué horarios tienes para las mentorías?", "Trabajo de lunes a viernes de 9:00 a 19:00. Las llamadas las agendamos según tu disponibilidad."),
        ("¿Hay garantía de devolución?", "Sí, ofrecemos garantía de 14 días. Si no estás satisfecho/a, te devolvemos el dinero sin preguntas."),
        ("¿Puedo combinar el curso con ejercicio?", "¡Por supuesto! El programa está diseñado para complementar cualquier tipo de actividad física."),
        ("¿Sirve para perder peso rápido?", "Nos enfocamos en pérdida de peso saludable y sostenible, típicamente 0.5-1kg por semana."),
        ("¿Qué pasa si tengo intolerancias?", "Adaptamos el plan a cualquier intolerancia o alergia alimentaria."),
        ("¿Incluye recetas para toda la familia?", "Sí, las recetas están pensadas para que toda la familia pueda disfrutarlas."),
        ("¿Cómo es el seguimiento semanal?", "Cada semana revisamos tu progreso, ajustamos el plan si es necesario y resolvemos dudas."),
        ("¿Puedo empezar en cualquier momento?", "Sí, puedes empezar cuando quieras. El acceso es inmediato tras el pago."),
        ("¿El acceso al curso es de por vida?", "Sí, una vez comprado tienes acceso de por vida incluyendo todas las actualizaciones."),
        ("¿Hacéis envíos internacionales?", "Al ser productos digitales, puedes acceder desde cualquier parte del mundo."),
        ("¿Qué métodos de pago aceptáis?", "Aceptamos tarjeta, PayPal, Bizum y transferencia bancaria."),
        ("¿Puedo hablar contigo antes de comprar?", "¡Claro! Puedes escribirme por aquí o agendar una llamada de descubrimiento gratuita."),
        ("¿Hay comunidad de alumnos?", "Sí, tenemos un grupo privado de Telegram donde compartimos tips, recetas y motivación."),
        ("¿Qué diferencia hay entre curso y mentoría?", "El curso es autogestionado con seguimiento semanal. La mentoría incluye acompañamiento diario y llamadas personalizadas."),
    ]

    for question, answer in faqs:
        kb_entry = KnowledgeBase(
            id=uuid.uuid4(),
            creator_id=creator.id,
            question=question,
            answer=answer,
        )
        db.add(kb_entry)

    db.flush()
    print(f"   ✓ KnowledgeBase: {len(faqs)}")


def print_summary(db: Session, creator_id: str):
    """Print summary of generated data."""
    creator = db.query(Creator).filter(Creator.name == CREATOR_ID).first()

    print("\n" + "-" * 60)
    print("📊 RESUMEN DE DATOS GENERADOS")
    print("-" * 60)

    # Counts
    followers = db.query(FollowerMemoryDB).filter_by(creator_id=CREATOR_ID).count()
    leads = db.query(Lead).filter_by(creator_id=creator.id).count()
    messages = db.query(Message).filter(
        Message.lead_id.in_(db.query(Lead.id).filter(Lead.creator_id == creator.id))
    ).count()
    bookings = db.query(CalendarBooking).filter_by(creator_id=CREATOR_ID).count()
    products = db.query(Product).filter_by(creator_id=creator.id).count()
    profiles = db.query(UserProfileDB).filter_by(creator_id=CREATOR_ID).count()
    states = db.query(ConversationStateDB).filter_by(creator_id=CREATOR_ID).count()
    kb = db.query(KnowledgeBase).filter_by(creator_id=creator.id).count()

    print(f"\n👥 Followers:          {followers}")
    print(f"🎯 Leads:              {leads}")
    print(f"💬 Messages:           {messages}")
    print(f"📅 Bookings:           {bookings}")
    print(f"📦 Products:           {products}")
    print(f"🧠 UserProfiles:       {profiles}")
    print(f"🔄 ConversationStates: {states}")
    print(f"📚 KnowledgeBase:      {kb}")

    # Segment distribution
    print("\n📊 DISTRIBUCIÓN POR SEGMENTO:")
    for segment, expected in SEGMENT_DISTRIBUTION.items():
        print(f"   {segment:20}: {expected}")

    # Hot leads
    hot_leads = db.query(Lead).filter_by(creator_id=creator.id, status="caliente").all()
    hot_leads_value = sum(l.deal_value or 0 for l in hot_leads)
    print(f"\n🔥 Hot Leads: {len(hot_leads)} (Valor potencial: €{hot_leads_value:,.2f})")

    # Customers
    customers = db.query(FollowerMemoryDB).filter_by(
        creator_id=CREATOR_ID, is_customer=True
    ).count()
    print(f"💰 Clientes: {customers}")

    print("\n" + "-" * 60)
    print("✅ Verifica en el dashboard:")
    print("   → /dashboard (Página Hoy)")
    print("   → /tu-audiencia")
    print("   → /personas")
    print("   → /inbox")
    print("-" * 60 + "\n")


if __name__ == "__main__":
    main()
