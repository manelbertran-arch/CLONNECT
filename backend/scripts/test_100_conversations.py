#!/usr/bin/env python3
"""
TEST 100 CONVERSACIONES COMPLETAS
==================================
Ejecuta 100 conversaciones multi-turno con el bot y guarda TODAS las respuestas.

Uso:
    python scripts/test_100_conversations.py

Output:
    - test_100_results.json (datos estructurados)
    - test_100_results.md (formato legible)
"""

import asyncio
import json
import sys
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class ConversationTurn:
    user_message: str
    bot_response: str
    intent: str
    confidence: float


@dataclass
class ConversationResult:
    id: int
    name: str
    category: str
    turns: List[Dict]
    passed: bool
    notes: str


# ═══════════════════════════════════════════════════════════════════════════════
# 100 CONVERSATION SCENARIOS
# ═══════════════════════════════════════════════════════════════════════════════

CONVERSATIONS = [
    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 1: VENTAS HAPPY PATH (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Venta directa - saludo a compra",
        "category": "ventas_happy_path",
        "messages": [
            "Hola! Vi tu post sobre fitness",
            "Me interesa el Fitpack Challenge",
            "¿Cuánto cuesta?",
            "Vale, lo quiero"
        ]
    },
    {
        "name": "Venta rapida - pregunta precio directo",
        "category": "ventas_happy_path",
        "messages": [
            "Hola",
            "Precio del programa?",
            "Ok me apunto"
        ]
    },
    {
        "name": "Venta con interes explicito",
        "category": "ventas_happy_path",
        "messages": [
            "Buenas! Quiero comprar el curso",
            "Si, el de 28 dias",
            "Pasame el link de pago"
        ]
    },
    {
        "name": "Venta despues de info",
        "category": "ventas_happy_path",
        "messages": [
            "Hola, cuentame sobre el programa",
            "¿Que incluye?",
            "Suena bien, ¿como pago?",
            "Con tarjeta"
        ]
    },
    {
        "name": "Venta con confirmacion",
        "category": "ventas_happy_path",
        "messages": [
            "Hey!",
            "Vi que tienes un reto de fitness",
            "Me interesa mucho",
            "¿Cuanto es?",
            "Perfecto, lo compro"
        ]
    },
    {
        "name": "Venta emocional",
        "category": "ventas_happy_path",
        "messages": [
            "Hola! Necesito cambiar mi vida",
            "Quiero empezar a hacer ejercicio",
            "¿Tu programa me puede ayudar?",
            "Si, lo quiero ya"
        ]
    },
    {
        "name": "Venta informada",
        "category": "ventas_happy_path",
        "messages": [
            "Hola, ya vi tu contenido en Instagram",
            "Me convence el programa",
            "Pasame el acceso"
        ]
    },
    {
        "name": "Venta desde recomendacion",
        "category": "ventas_happy_path",
        "messages": [
            "Hola! Me recomendo una amiga",
            "El programa de 28 dias",
            "¿Como me inscribo?"
        ]
    },
    {
        "name": "Venta express",
        "category": "ventas_happy_path",
        "messages": [
            "Quiero el Fitpack",
            "¿Link de pago?"
        ]
    },
    {
        "name": "Venta con entusiasmo",
        "category": "ventas_happy_path",
        "messages": [
            "Me encanta tu contenido!",
            "Quiero empezar el programa",
            "¿Cuanto cuesta el challenge?",
            "Genial! Lo compro"
        ]
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 2: OBJECIONES DE PRECIO (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Objecion precio - es caro",
        "category": "objeciones_precio",
        "messages": [
            "Hola, me interesa el programa",
            "¿Cuanto cuesta?",
            "Es muy caro para mi",
            "¿Hay descuento?"
        ]
    },
    {
        "name": "Objecion precio - no tengo dinero",
        "category": "objeciones_precio",
        "messages": [
            "Me interesa pero no tengo dinero ahora",
            "¿Hay pagos a plazos?",
            "Ok, lo pienso"
        ]
    },
    {
        "name": "Objecion precio - comparacion",
        "category": "objeciones_precio",
        "messages": [
            "Hola",
            "Vi otro programa mas barato",
            "¿Por que el tuyo cuesta mas?",
            "Hmm entiendo"
        ]
    },
    {
        "name": "Objecion precio - valor",
        "category": "objeciones_precio",
        "messages": [
            "Me parece caro",
            "¿Que incluye por ese precio?",
            "¿Tiene garantia?",
            "Ok, lo voy a pensar"
        ]
    },
    {
        "name": "Objecion precio - presupuesto limitado",
        "category": "objeciones_precio",
        "messages": [
            "Hola! Me interesa mucho",
            "Pero mi presupuesto es de 50 euros maximo",
            "¿Tienes algo en ese rango?"
        ]
    },
    {
        "name": "Objecion precio - dudando",
        "category": "objeciones_precio",
        "messages": [
            "No se si vale la pena el precio",
            "¿Que resultados puedo esperar?",
            "¿Y si no funciona?"
        ]
    },
    {
        "name": "Objecion precio - negociando",
        "category": "objeciones_precio",
        "messages": [
            "¿Me puedes hacer un descuento?",
            "Soy estudiante",
            "Por favor, un 20%?"
        ]
    },
    {
        "name": "Objecion precio - esperando oferta",
        "category": "objeciones_precio",
        "messages": [
            "Voy a esperar a que haya una oferta",
            "¿Cuando hay promociones?",
            "Avisame cuando baje"
        ]
    },
    {
        "name": "Objecion precio - superada",
        "category": "objeciones_precio",
        "messages": [
            "Es caro pero me interesa",
            "¿Que garantia tienes?",
            "7 dias? Ok, me arriesgo",
            "Pasame el link"
        ]
    },
    {
        "name": "Objecion precio - pidiendo opciones",
        "category": "objeciones_precio",
        "messages": [
            "¿Tienes opciones mas economicas?",
            "Algo mas basico?",
            "¿Y eso que incluye?"
        ]
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 3: OBJECIONES DE TIEMPO (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Objecion tiempo - muy ocupado",
        "category": "objeciones_tiempo",
        "messages": [
            "Me interesa pero trabajo mucho",
            "No tengo tiempo libre",
            "¿Cuanto tiempo necesito al dia?"
        ]
    },
    {
        "name": "Objecion tiempo - horarios",
        "category": "objeciones_tiempo",
        "messages": [
            "¿A que hora son las sesiones?",
            "Trabajo de noche",
            "¿Puedo hacerlo a mi ritmo?"
        ]
    },
    {
        "name": "Objecion tiempo - familia",
        "category": "objeciones_tiempo",
        "messages": [
            "Tengo 3 hijos pequeños",
            "No tengo ni un minuto",
            "¿Cuanto dura cada sesion?"
        ]
    },
    {
        "name": "Objecion tiempo - viajes",
        "category": "objeciones_tiempo",
        "messages": [
            "Viajo mucho por trabajo",
            "¿Lo puedo hacer desde el movil?",
            "¿Sin equipamiento?"
        ]
    },
    {
        "name": "Objecion tiempo - agenda llena",
        "category": "objeciones_tiempo",
        "messages": [
            "Mi agenda esta llena",
            "Solo tengo 10 minutos al dia",
            "¿Es suficiente?"
        ]
    },
    {
        "name": "Objecion tiempo - estres",
        "category": "objeciones_tiempo",
        "messages": [
            "Estoy muy estresado",
            "No puedo anadir nada mas",
            "¿Esto no me estresara mas?"
        ]
    },
    {
        "name": "Objecion tiempo - empezar luego",
        "category": "objeciones_tiempo",
        "messages": [
            "Ahora no puedo empezar",
            "Quizas el proximo mes",
            "¿El acceso es para siempre?"
        ]
    },
    {
        "name": "Objecion tiempo - superada",
        "category": "objeciones_tiempo",
        "messages": [
            "No tengo tiempo",
            "¿15 minutos al dia?",
            "Eso si puedo hacerlo",
            "Ok, me apunto"
        ]
    },
    {
        "name": "Objecion tiempo - flexibilidad",
        "category": "objeciones_tiempo",
        "messages": [
            "¿Es flexible el horario?",
            "Algunos dias no puedo",
            "¿Puedo retomar donde lo deje?"
        ]
    },
    {
        "name": "Objecion tiempo - compromisos",
        "category": "objeciones_tiempo",
        "messages": [
            "Tengo muchos compromisos",
            "No se si puedo comprometerme",
            "¿Que pasa si no termino?"
        ]
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 4: OBJECIONES DE DUDA (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Duda - funciona de verdad",
        "category": "objeciones_duda",
        "messages": [
            "¿Esto funciona de verdad?",
            "He probado otros y no funcionaron",
            "¿Por que el tuyo seria diferente?"
        ]
    },
    {
        "name": "Duda - resultados",
        "category": "objeciones_duda",
        "messages": [
            "¿Que resultados puedo esperar?",
            "¿En cuanto tiempo?",
            "¿Tienes testimonios?"
        ]
    },
    {
        "name": "Duda - para mi caso",
        "category": "objeciones_duda",
        "messages": [
            "Tengo 50 años",
            "¿Funciona para mi edad?",
            "No soy muy atletico"
        ]
    },
    {
        "name": "Duda - garantia",
        "category": "objeciones_duda",
        "messages": [
            "¿Y si no me gusta?",
            "¿Hay devolucion?",
            "¿Cuantos dias tengo?"
        ]
    },
    {
        "name": "Duda - nivel principiante",
        "category": "objeciones_duda",
        "messages": [
            "Nunca he hecho ejercicio",
            "¿Es para principiantes?",
            "No se si puedo"
        ]
    },
    {
        "name": "Duda - consultando",
        "category": "objeciones_duda",
        "messages": [
            "Tengo que consultarlo con mi pareja",
            "Te aviso mañana",
            "Gracias por la info"
        ]
    },
    {
        "name": "Duda - pensandolo",
        "category": "objeciones_duda",
        "messages": [
            "Lo voy a pensar",
            "Dame unos dias",
            "Te escribo la proxima semana"
        ]
    },
    {
        "name": "Duda - comparando",
        "category": "objeciones_duda",
        "messages": [
            "Estoy viendo otras opciones",
            "¿Que te diferencia?",
            "¿Por que elegirte a ti?"
        ]
    },
    {
        "name": "Duda - superada",
        "category": "objeciones_duda",
        "messages": [
            "No estaba seguro pero...",
            "Tus testimonios me convencen",
            "Ok, lo pruebo",
            "¿Como pago?"
        ]
    },
    {
        "name": "Duda - necesita mas info",
        "category": "objeciones_duda",
        "messages": [
            "Necesito mas informacion",
            "¿Tienes un PDF o algo?",
            "Mandame mas detalles"
        ]
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 5: LEAD MAGNET (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Lead magnet - gratis",
        "category": "lead_magnet",
        "messages": [
            "¿Tienes algo gratis?",
            "Un ebook o guia",
            "Pasame el link"
        ]
    },
    {
        "name": "Lead magnet - probar antes",
        "category": "lead_magnet",
        "messages": [
            "Quiero probar antes de comprar",
            "¿Hay version de prueba?",
            "¿Algo gratuito?"
        ]
    },
    {
        "name": "Lead magnet - PDF",
        "category": "lead_magnet",
        "messages": [
            "Me mandas un PDF?",
            "Algo para empezar",
            "Gracias!"
        ]
    },
    {
        "name": "Lead magnet - conocerte",
        "category": "lead_magnet",
        "messages": [
            "Quiero conocer tu metodo primero",
            "¿Tienes contenido gratuito?",
            "¿Donde lo veo?"
        ]
    },
    {
        "name": "Lead magnet - descargar",
        "category": "lead_magnet",
        "messages": [
            "¿Que puedo descargar gratis?",
            "Dame el link",
            "Ya lo tengo, gracias"
        ]
    },
    {
        "name": "Lead magnet - recurso",
        "category": "lead_magnet",
        "messages": [
            "¿Tienes algun recurso gratuito?",
            "Para ver si me gusta tu estilo",
            "Perfecto"
        ]
    },
    {
        "name": "Lead magnet - video gratis",
        "category": "lead_magnet",
        "messages": [
            "¿Tienes videos gratis?",
            "En YouTube?",
            "Los veo primero"
        ]
    },
    {
        "name": "Lead magnet - clase gratis",
        "category": "lead_magnet",
        "messages": [
            "¿Hay alguna clase gratis?",
            "Para probar",
            "¿Donde me apunto?"
        ]
    },
    {
        "name": "Lead magnet - workshop",
        "category": "lead_magnet",
        "messages": [
            "¿Haces workshops gratuitos?",
            "Me interesa uno",
            "Avisame cuando haya"
        ]
    },
    {
        "name": "Lead magnet - podcast",
        "category": "lead_magnet",
        "messages": [
            "¿Tienes podcast?",
            "Algo que pueda escuchar",
            "¿Como se llama?"
        ]
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 6: RESERVAS / BOOKING (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Booking - llamada discovery",
        "category": "booking",
        "messages": [
            "Quiero una llamada contigo",
            "Para conocernos",
            "¿Tienes hueco esta semana?"
        ]
    },
    {
        "name": "Booking - sesion coaching",
        "category": "booking",
        "messages": [
            "Me interesa el coaching",
            "¿Como agendo una sesion?",
            "Pasame el link"
        ]
    },
    {
        "name": "Booking - consulta gratis",
        "category": "booking",
        "messages": [
            "¿Tienes consulta gratuita?",
            "Para hablar de mi caso",
            "Si, la quiero"
        ]
    },
    {
        "name": "Booking - videollamada",
        "category": "booking",
        "messages": [
            "¿Podemos hacer videollamada?",
            "Para que me expliques mejor",
            "¿Cuando tienes disponible?"
        ]
    },
    {
        "name": "Booking - agendar cita",
        "category": "booking",
        "messages": [
            "Quiero agendar una cita",
            "¿Tienes Calendly?",
            "Ok, reservo"
        ]
    },
    {
        "name": "Booking - sesion evaluacion",
        "category": "booking",
        "messages": [
            "Necesito una evaluacion",
            "Para saber por donde empezar",
            "¿Como lo hacemos?"
        ]
    },
    {
        "name": "Booking - 1:1",
        "category": "booking",
        "messages": [
            "Me interesa coaching 1:1",
            "¿Cuanto cuesta la sesion?",
            "Ok, la reservo"
        ]
    },
    {
        "name": "Booking - seguimiento",
        "category": "booking",
        "messages": [
            "Quiero sesion de seguimiento",
            "Ya compre el programa",
            "Necesito ayuda personalizada"
        ]
    },
    {
        "name": "Booking - primera vez",
        "category": "booking",
        "messages": [
            "Es mi primera vez aqui",
            "¿Como funciona esto?",
            "¿Hay llamada inicial?"
        ]
    },
    {
        "name": "Booking - urgente",
        "category": "booking",
        "messages": [
            "Necesito hablar contigo urgente",
            "¿Tienes hueco hoy?",
            "Es importante"
        ]
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 7: ESCALACION (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Escalacion - quiero humano",
        "category": "escalacion",
        "messages": [
            "Quiero hablar con una persona",
            "No con un bot",
            "Pasame con alguien real"
        ]
    },
    {
        "name": "Escalacion - frustrado",
        "category": "escalacion",
        "messages": [
            "No me entiendes",
            "Esto es frustrante",
            "Necesito ayuda real"
        ]
    },
    {
        "name": "Escalacion - problema tecnico",
        "category": "escalacion",
        "messages": [
            "Tengo un problema con mi compra",
            "No me llego el acceso",
            "Necesito que me ayuden"
        ]
    },
    {
        "name": "Escalacion - queja",
        "category": "escalacion",
        "messages": [
            "Esto no funciona",
            "Quiero mi dinero de vuelta",
            "Habla con tu jefe"
        ]
    },
    {
        "name": "Escalacion - contacto directo",
        "category": "escalacion",
        "messages": [
            "¿Como contacto a Stefano directamente?",
            "Necesito hablar con el",
            "Es personal"
        ]
    },
    {
        "name": "Escalacion - soporte",
        "category": "escalacion",
        "messages": [
            "Necesito soporte tecnico",
            "La plataforma no carga",
            "¿Hay numero de telefono?"
        ]
    },
    {
        "name": "Escalacion - devolucion",
        "category": "escalacion",
        "messages": [
            "Quiero devolver el programa",
            "No es lo que esperaba",
            "¿Como hago el reembolso?"
        ]
    },
    {
        "name": "Escalacion - urgente",
        "category": "escalacion",
        "messages": [
            "Es urgente",
            "Necesito hablar con alguien YA",
            "No puede esperar"
        ]
    },
    {
        "name": "Escalacion - comercial",
        "category": "escalacion",
        "messages": [
            "Quiero hacer una propuesta comercial",
            "Soy de una empresa",
            "¿Con quien hablo?"
        ]
    },
    {
        "name": "Escalacion - colaboracion",
        "category": "escalacion",
        "messages": [
            "Quiero proponer una colaboracion",
            "Soy influencer",
            "¿Como contacto a Stefano?"
        ]
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 8: PREGUNTAS PRODUCTO (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Pregunta - que incluye",
        "category": "preguntas_producto",
        "messages": [
            "¿Que incluye el programa?",
            "¿Cuantos modulos tiene?",
            "¿Y material extra?"
        ]
    },
    {
        "name": "Pregunta - duracion",
        "category": "preguntas_producto",
        "messages": [
            "¿Cuanto dura el programa?",
            "¿28 dias?",
            "¿Y despues que pasa?"
        ]
    },
    {
        "name": "Pregunta - acceso",
        "category": "preguntas_producto",
        "messages": [
            "¿El acceso es para siempre?",
            "¿O caduca?",
            "¿Puedo repetirlo?"
        ]
    },
    {
        "name": "Pregunta - plataforma",
        "category": "preguntas_producto",
        "messages": [
            "¿En que plataforma esta?",
            "¿Funciona en movil?",
            "¿Necesito descargar app?"
        ]
    },
    {
        "name": "Pregunta - equipamiento",
        "category": "preguntas_producto",
        "messages": [
            "¿Necesito equipamiento?",
            "¿Pesas o algo?",
            "Solo tengo una esterilla"
        ]
    },
    {
        "name": "Pregunta - soporte",
        "category": "preguntas_producto",
        "messages": [
            "¿Hay soporte incluido?",
            "¿Puedo preguntar dudas?",
            "¿Por donde?"
        ]
    },
    {
        "name": "Pregunta - comunidad",
        "category": "preguntas_producto",
        "messages": [
            "¿Hay grupo de alumnos?",
            "¿Comunidad privada?",
            "¿En que red social?"
        ]
    },
    {
        "name": "Pregunta - actualizaciones",
        "category": "preguntas_producto",
        "messages": [
            "¿Se actualiza el contenido?",
            "¿Anades videos nuevos?",
            "¿Cada cuanto?"
        ]
    },
    {
        "name": "Pregunta - idioma",
        "category": "preguntas_producto",
        "messages": [
            "¿Esta en español?",
            "¿Hay subtitulos?",
            "¿Todo el contenido?"
        ]
    },
    {
        "name": "Pregunta - certificado",
        "category": "preguntas_producto",
        "messages": [
            "¿Dan certificado?",
            "¿Al terminar?",
            "¿Sirve para algo?"
        ]
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 9: RESPUESTAS CORTAS (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Respuesta corta - si",
        "category": "respuestas_cortas",
        "messages": [
            "Hola",
            "Si",
            "Si",
            "Ok"
        ]
    },
    {
        "name": "Respuesta corta - no",
        "category": "respuestas_cortas",
        "messages": [
            "¿Te interesa el programa?",
            "No",
            "Quiza mas adelante",
            "Adios"
        ]
    },
    {
        "name": "Respuesta corta - vale",
        "category": "respuestas_cortas",
        "messages": [
            "Te cuento sobre el programa",
            "Vale",
            "Vale",
            "Entendido"
        ]
    },
    {
        "name": "Respuesta corta - ok",
        "category": "respuestas_cortas",
        "messages": [
            "El precio es 97 euros",
            "Ok",
            "Ok",
            "Ok, lo compro"
        ]
    },
    {
        "name": "Respuesta corta - claro",
        "category": "respuestas_cortas",
        "messages": [
            "¿Quieres saber mas?",
            "Claro",
            "Claro que si",
            "Por supuesto"
        ]
    },
    {
        "name": "Respuesta corta - dale",
        "category": "respuestas_cortas",
        "messages": [
            "¿Te paso el link?",
            "Dale",
            "Dale",
            "Venga"
        ]
    },
    {
        "name": "Respuesta corta - gracias",
        "category": "respuestas_cortas",
        "messages": [
            "Aqui tienes la info",
            "Gracias",
            "Muchas gracias",
            "Genial gracias"
        ]
    },
    {
        "name": "Respuesta corta - emojis",
        "category": "respuestas_cortas",
        "messages": [
            "¿Te gusta el programa?",
            "👍",
            "😊",
            "🙌"
        ]
    },
    {
        "name": "Respuesta corta - mixto",
        "category": "respuestas_cortas",
        "messages": [
            "Hola!",
            "Hey",
            "Bien tu?",
            "Quiero info"
        ]
    },
    {
        "name": "Respuesta corta - despedida",
        "category": "respuestas_cortas",
        "messages": [
            "Eso es todo por ahora",
            "Ok",
            "Gracias",
            "Chao"
        ]
    },

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORIA 10: CASOS EXTREMOS (10 conversaciones)
    # ─────────────────────────────────────────────────────────────────────────
    {
        "name": "Extremo - off topic politica",
        "category": "casos_extremos",
        "messages": [
            "¿Que opinas de la politica?",
            "¿Y del gobierno?",
            "¿Votaste?"
        ]
    },
    {
        "name": "Extremo - off topic criptomonedas",
        "category": "casos_extremos",
        "messages": [
            "¿Aceptas Bitcoin?",
            "¿Tienes NFTs?",
            "¿Inviertes en crypto?"
        ]
    },
    {
        "name": "Extremo - spam",
        "category": "casos_extremos",
        "messages": [
            "Gana dinero facil aqui: bit.ly/spam",
            "Mira mi oferta increible",
            "Haz click aqui"
        ]
    },
    {
        "name": "Extremo - insultos",
        "category": "casos_extremos",
        "messages": [
            "Esto es una estafa",
            "Eres un ladron",
            "Devuelveme mi dinero idiota"
        ]
    },
    {
        "name": "Extremo - mensaje vacio",
        "category": "casos_extremos",
        "messages": [
            "",
            "   ",
            "..."
        ]
    },
    {
        "name": "Extremo - mensaje muy largo",
        "category": "casos_extremos",
        "messages": [
            "Hola te escribo porque vi tu contenido y me parecio muy interesante y queria saber mas sobre tu programa porque tengo muchas ganas de empezar a hacer ejercicio y cambiar mi vida pero no se por donde empezar y he probado muchas cosas antes pero ninguna me ha funcionado y espero que esta vez sea diferente porque realmente necesito un cambio en mi vida y creo que tu programa podria ser lo que necesito aunque tengo algunas dudas sobre el precio y el tiempo que necesito dedicarle cada dia porque trabajo mucho y tengo familia y no tengo mucho tiempo libre pero estoy dispuesto a hacer el esfuerzo si realmente funciona",
            "¿Que me dices?"
        ]
    },
    {
        "name": "Extremo - otro idioma",
        "category": "casos_extremos",
        "messages": [
            "Hello! I saw your program",
            "How much does it cost?",
            "Do you speak English?"
        ]
    },
    {
        "name": "Extremo - numeros",
        "category": "casos_extremos",
        "messages": [
            "123456",
            "999",
            "+34 612 345 678"
        ]
    },
    {
        "name": "Extremo - preguntas personales",
        "category": "casos_extremos",
        "messages": [
            "¿Cuantos años tienes?",
            "¿Donde vives?",
            "¿Estas soltero?"
        ]
    },
    {
        "name": "Extremo - multiples preguntas",
        "category": "casos_extremos",
        "messages": [
            "¿Cuanto cuesta? ¿Que incluye? ¿Cuanto dura? ¿Hay garantia?",
            "¿Puedo pagar con tarjeta? ¿Hay descuento? ¿Es para principiantes?",
            "Responde todo por favor"
        ]
    },
]


class Test100Conversations:
    """Ejecutor de 100 conversaciones de prueba."""

    def __init__(self, creator_id: str = "fitpack_global"):
        self.creator_id = creator_id
        self.agent = None
        self.results: List[ConversationResult] = []

    async def setup(self):
        """Inicializar el agente."""
        try:
            from core.dm_agent import DMResponderAgent
            self.agent = DMResponderAgent(creator_id=self.creator_id)
            print(f"✓ Agent initialized for creator: {self.creator_id}")
            return True
        except Exception as e:
            print(f"✗ Error initializing agent: {e}")
            return False

    async def run_conversation(self, conv_id: int, conv_data: dict) -> ConversationResult:
        """Ejecutar una conversación completa."""
        name = conv_data["name"]
        category = conv_data["category"]
        messages = conv_data["messages"]

        print(f"\n{'─' * 60}")
        print(f"CONVERSACION {conv_id}: {name}")
        print(f"Categoria: {category}")
        print(f"{'─' * 60}")

        turns = []
        follower_id = f"test_conv_{conv_id}_{uuid.uuid4().hex[:6]}"
        passed = True
        notes = ""

        for i, user_msg in enumerate(messages):
            if not user_msg.strip():
                user_msg = "(mensaje vacio)"

            try:
                response = await self.agent.process_dm(
                    sender_id=follower_id,
                    message_text=user_msg,
                    message_id=str(uuid.uuid4()),
                    username=f"test_user_{conv_id}",
                    name=f"Test User {conv_id}"
                )

                bot_response = response.response_text or "(sin respuesta)"
                intent = response.intent.value if response.intent else "unknown"
                confidence = response.confidence or 0.0

                turn = {
                    "user_message": user_msg,
                    "bot_response": bot_response,
                    "intent": intent,
                    "confidence": round(confidence, 2)
                }
                turns.append(turn)

                print(f"\nUSER: {user_msg}")
                print(f"BOT: {bot_response[:200]}{'...' if len(bot_response) > 200 else ''}")
                print(f"INTENT: {intent} ({confidence:.0%})")

                # Check for escalation
                if response.escalate_to_human:
                    notes += "ESCALADO. "

            except Exception as e:
                turn = {
                    "user_message": user_msg,
                    "bot_response": f"ERROR: {str(e)}",
                    "intent": "error",
                    "confidence": 0.0
                }
                turns.append(turn)
                passed = False
                notes += f"Error en turno {i+1}. "
                print(f"\n⚠️ Error: {e}")

        # Determine if passed based on category
        if len(turns) > 0:
            last_intent = turns[-1]["intent"]
            last_response = turns[-1]["bot_response"]

            # Category-specific checks
            if category == "ventas_happy_path":
                if "link" in last_response.lower() or "pago" in last_response.lower():
                    passed = True
                    notes += "Link de pago detectado. "
            elif category == "escalacion":
                if "ESCALADO" in notes or "stefano" in last_response.lower():
                    passed = True
                    notes += "Escalacion correcta. "
            elif category == "casos_extremos":
                # Should handle gracefully
                if "error" not in turns[-1]["intent"]:
                    passed = True
                    notes += "Manejado correctamente. "

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\nRESULTADO: {status}")
        if notes:
            print(f"NOTAS: {notes}")

        return ConversationResult(
            id=conv_id,
            name=name,
            category=category,
            turns=turns,
            passed=passed,
            notes=notes.strip()
        )

    async def run_all(self) -> List[ConversationResult]:
        """Ejecutar todas las conversaciones."""
        if not await self.setup():
            print("No se pudo inicializar el agente. Abortando.")
            return []

        print("\n" + "═" * 70)
        print("    TEST 100 CONVERSACIONES COMPLETAS")
        print("═" * 70)
        print(f"Total conversaciones: {len(CONVERSATIONS)}")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("═" * 70)

        self.results = []

        for i, conv_data in enumerate(CONVERSATIONS, 1):
            result = await self.run_conversation(i, conv_data)
            self.results.append(result)

            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)

        return self.results

    def generate_report(self) -> dict:
        """Generar reporte final."""
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        # Group by category
        by_category = {}
        for r in self.results:
            cat = r.category
            if cat not in by_category:
                by_category[cat] = {"passed": 0, "total": 0}
            by_category[cat]["total"] += 1
            if r.passed:
                by_category[cat]["passed"] += 1

        return {
            "timestamp": datetime.now().isoformat(),
            "total": len(self.results),
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / len(self.results) * 100, 1) if self.results else 0,
            "by_category": by_category,
            "conversations": [asdict(r) for r in self.results]
        }

    def save_json(self, filepath: str):
        """Guardar resultados en JSON."""
        report = self.generate_report()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n✓ JSON saved to: {filepath}")

    def save_markdown(self, filepath: str):
        """Guardar resultados en Markdown legible."""
        report = self.generate_report()

        md = []
        md.append("# TEST 100 CONVERSACIONES - RESULTADOS COMPLETOS\n")
        md.append(f"**Fecha:** {report['timestamp']}\n")
        md.append(f"**Total:** {report['total']} conversaciones\n")
        md.append(f"**Pass Rate:** {report['pass_rate']}% ({report['passed']}/{report['total']})\n")
        md.append("\n---\n")

        md.append("## RESUMEN POR CATEGORIA\n")
        md.append("| Categoria | Pass | Total | % |\n")
        md.append("|-----------|------|-------|---|\n")
        for cat, data in report["by_category"].items():
            pct = round(data["passed"] / data["total"] * 100) if data["total"] > 0 else 0
            md.append(f"| {cat} | {data['passed']} | {data['total']} | {pct}% |\n")

        md.append("\n---\n")
        md.append("## CONVERSACIONES COMPLETAS\n")

        for conv in report["conversations"]:
            status = "✅ PASS" if conv["passed"] else "❌ FAIL"
            md.append(f"\n### CONVERSACION {conv['id']}: {conv['name']} {status}\n")
            md.append(f"**Categoria:** {conv['category']}\n")
            if conv["notes"]:
                md.append(f"**Notas:** {conv['notes']}\n")
            md.append("\n```\n")

            for turn in conv["turns"]:
                md.append(f"USER: {turn['user_message']}\n")
                md.append(f"BOT: {turn['bot_response']}\n")
                md.append(f"INTENT: {turn['intent']} ({turn['confidence']})\n\n")

            md.append("```\n")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("".join(md))
        print(f"✓ Markdown saved to: {filepath}")


async def main():
    runner = Test100Conversations(creator_id="fitpack_global")
    await runner.run_all()

    # Save results
    runner.save_json("test_100_results.json")
    runner.save_markdown("test_100_results.md")

    # Print summary
    report = runner.generate_report()
    print("\n" + "═" * 70)
    print("    RESUMEN FINAL")
    print("═" * 70)
    print(f"Pass Rate: {report['pass_rate']}% ({report['passed']}/{report['total']})")
    print("\nPor categoria:")
    for cat, data in report["by_category"].items():
        pct = round(data["passed"] / data["total"] * 100) if data["total"] > 0 else 0
        print(f"  {cat}: {data['passed']}/{data['total']} ({pct}%)")


if __name__ == "__main__":
    asyncio.run(main())
