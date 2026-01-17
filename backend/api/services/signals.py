"""
Sistema Inteligente de Señales y Predicción de Venta
Analiza conversaciones para detectar intención de compra, producto de interés y predecir ventas.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

# =============================================================================
# SEÑALES DE INTENCIÓN DE COMPRA
# =============================================================================

PURCHASE_INTENT_SIGNALS = {
    # --- SEÑALES DE COMPRA (Alta intención) ---
    "precio_directo": {
        "keywords": ["cuánto cuesta", "cuanto cuesta", "precio", "vale", "cost", "cuánto es", "cuanto es", "qué precio", "que precio"],
        "weight": 30,
        "category": "compra",
        "emoji": "💰",
        "description": "Preguntó precio"
    },
    "formas_pago": {
        "keywords": ["pagar", "tarjeta", "transferencia", "plazos", "financiar", "cuotas", "bizum", "paypal"],
        "weight": 25,
        "category": "compra",
        "emoji": "💳",
        "description": "Preguntó formas de pago"
    },
    "disponibilidad": {
        "keywords": ["cuándo empieza", "cuando empieza", "plazas", "disponible", "fechas", "próxima edición", "proxima edicion", "hay sitio"],
        "weight": 20,
        "category": "compra",
        "emoji": "📅",
        "description": "Preguntó disponibilidad"
    },
    "urgencia": {
        "keywords": ["ahora", "ya", "hoy", "cuanto antes", "urgente", "rápido", "rapido", "necesito ya"],
        "weight": 25,
        "category": "compra",
        "emoji": "⚡",
        "description": "Mostró urgencia"
    },
    "compara_opciones": {
        "keywords": ["diferencia entre", "cuál me recomiendas", "cual me recomiendas", "mejor opción", "mejor opcion", "qué plan", "que plan"],
        "weight": 15,
        "category": "compra",
        "emoji": "🔄",
        "description": "Comparó opciones"
    },
    "link_pago": {
        "keywords": ["link", "enlace", "cómo pago", "como pago", "dónde compro", "donde compro", "pásame el link", "pasame el link", "envíame", "enviame"],
        "weight": 35,
        "category": "compra",
        "emoji": "🔗",
        "description": "Pidió link de pago"
    },
    "confirma_compra": {
        "keywords": ["quiero comprarlo", "me apunto", "lo quiero", "reservar", "inscribirme", "me interesa comprarlo", "voy a comprarlo", "lo cojo"],
        "weight": 40,
        "category": "compra",
        "emoji": "✅",
        "description": "Confirmó intención de compra"
    },

    # --- SEÑALES DE INTERÉS (Media intención) ---
    "pide_info": {
        "keywords": ["info", "información", "informacion", "detalles", "cuéntame más", "cuentame mas", "explícame", "explicame", "más info", "mas info"],
        "weight": 15,
        "category": "interes",
        "emoji": "ℹ️",
        "description": "Pidió información"
    },
    "como_funciona": {
        "keywords": ["cómo funciona", "como funciona", "qué incluye", "que incluye", "en qué consiste", "en que consiste", "qué es exactamente", "que es exactamente"],
        "weight": 15,
        "category": "interes",
        "emoji": "❓",
        "description": "Preguntó cómo funciona"
    },
    "resultados": {
        "keywords": ["resultados", "funciona de verdad", "testimonios", "casos de éxito", "casos de exito", "funciona realmente", "ejemplos"],
        "weight": 20,
        "category": "interes",
        "emoji": "📈",
        "description": "Preguntó por resultados"
    },
    "duracion": {
        "keywords": ["cuánto dura", "cuanto dura", "tiempo", "sesiones", "semanas", "meses", "duración", "duracion", "horas"],
        "weight": 15,
        "category": "interes",
        "emoji": "⏱️",
        "description": "Preguntó duración"
    },
    "para_quien": {
        "keywords": ["es para mí", "es para mi", "nivel", "principiantes", "requisitos", "necesito saber algo antes", "sin experiencia"],
        "weight": 10,
        "category": "interes",
        "emoji": "👤",
        "description": "Preguntó requisitos"
    },
    "situacion_personal": {
        "keywords": ["mi problema es", "mi problema", "necesito", "busco", "quiero lograr", "mi caso", "mi situación", "mi situacion", "tengo un problema"],
        "weight": 20,
        "category": "interes",
        "emoji": "💬",
        "description": "Compartió situación personal"
    },
    "garantia": {
        "keywords": ["garantía", "garantia", "devolucion", "devolución", "si no me gusta", "reembolso", "puedo cancelar"],
        "weight": 15,
        "category": "interes",
        "emoji": "🛡️",
        "description": "Preguntó por garantía"
    },

    # --- SEÑALES DE OBJECIÓN (Reducen intención) ---
    "objecion_precio": {
        "keywords": ["caro", "muy caro", "no puedo", "no tengo dinero", "mucho dinero", "es mucho", "fuera de mi presupuesto", "no me lo puedo permitir"],
        "weight": -20,
        "category": "objecion",
        "emoji": "💸",
        "description": "Objeción de precio"
    },
    "objecion_tiempo": {
        "keywords": ["no tengo tiempo", "muy ocupado", "ahora no puedo", "estoy liado", "no tengo hueco"],
        "weight": -15,
        "category": "objecion",
        "emoji": "⏰",
        "description": "Objeción de tiempo"
    },
    "postergacion": {
        "keywords": ["lo pienso", "después", "despues", "más adelante", "mas adelante", "ya veré", "ya vere", "luego", "otro momento", "déjame pensarlo"],
        "weight": -15,
        "category": "objecion",
        "emoji": "⏳",
        "description": "Postergación"
    },
    "desconfianza": {
        "keywords": ["funciona de verdad", "es real", "no sé si", "no se si", "será una estafa", "sera una estafa", "no me fío", "no me fio"],
        "weight": -10,
        "category": "objecion",
        "emoji": "🤔",
        "description": "Mostró desconfianza"
    },
    "experiencia_negativa": {
        "keywords": ["he probado otros", "no me funcionó", "no me funciono", "ya lo intenté", "ya lo intente", "otros no me sirvieron"],
        "weight": -10,
        "category": "objecion",
        "emoji": "👎",
        "description": "Experiencia negativa previa"
    },
    "no_interesado": {
        "keywords": ["no me interesa", "no gracias", "no quiero", "paso", "no es para mí", "no es para mi"],
        "weight": -30,
        "category": "objecion",
        "emoji": "🚫",
        "description": "No interesado"
    },
}

# =============================================================================
# SEÑALES DE PRODUCTO
# =============================================================================

PRODUCT_SIGNALS = {
    "curso": {
        "keywords": ["curso", "programa", "formación", "formacion", "aprender", "clases", "módulos", "modulos", "lecciones"],
        "display_name": "Curso/Programa",
        "default_price": 197,
        "emoji": "📚"
    },
    "coaching": {
        "keywords": ["coaching", "1 a 1", "1a1", "personal", "individual", "sesión", "sesion", "mentoría", "mentoria", "acompañamiento"],
        "display_name": "Coaching 1:1",
        "default_price": 297,
        "emoji": "🎯"
    },
    "membresia": {
        "keywords": ["membresía", "membresia", "mensual", "suscripción", "suscripcion", "comunidad", "acceso mensual"],
        "display_name": "Membresía",
        "default_price": 47,
        "emoji": "🔑"
    },
    "evento": {
        "keywords": ["evento", "taller", "workshop", "masterclass", "directo", "webinar", "seminario"],
        "display_name": "Evento/Taller",
        "default_price": 97,
        "emoji": "🎤"
    },
    "ebook": {
        "keywords": ["ebook", "guía", "guia", "pdf", "descargable", "libro", "manual"],
        "display_name": "Ebook/Guía",
        "default_price": 27,
        "emoji": "📖"
    },
    "consultoria": {
        "keywords": ["consultoría", "consultoria", "asesoría", "asesoria", "auditoría", "auditoria", "análisis", "analisis"],
        "display_name": "Consultoría",
        "default_price": 197,
        "emoji": "💼"
    },
}

# =============================================================================
# FUNCIÓN DE ANÁLISIS INTELIGENTE
# =============================================================================

def analyze_conversation_signals(messages: List[Any], lead_status: str = "nuevo") -> Dict[str, Any]:
    """
    Analiza todos los mensajes de una conversación y extrae señales inteligentes.

    Args:
        messages: Lista de objetos Message con 'role', 'content', 'created_at'
        lead_status: Estado actual del lead en el pipeline

    Returns:
        Diccionario con predicción de venta, señales detectadas, métricas
    """

    # Filtrar mensajes del usuario (lead)
    user_messages = [m for m in messages if m.role == "user"]
    bot_messages = [m for m in messages if m.role == "assistant"]

    if not user_messages:
        return _empty_analysis()

    # Concatenar todo el texto del lead para búsqueda de keywords
    all_text = " ".join([m.content.lower() if m.content else "" for m in user_messages])

    detected_signals = []
    total_score = 0
    categories = {"compra": [], "interes": [], "objecion": [], "comportamiento": []}

    # ===========================================
    # 1. DETECTAR SEÑALES DE INTENCIÓN
    # ===========================================
    for signal_name, signal_data in PURCHASE_INTENT_SIGNALS.items():
        keyword_found = None
        for keyword in signal_data["keywords"]:
            if keyword in all_text:
                keyword_found = keyword
                break

        if keyword_found:
            signal_entry = {
                "signal": signal_name,
                "keyword_found": keyword_found,
                "weight": signal_data["weight"],
                "category": signal_data["category"],
                "emoji": signal_data["emoji"],
                "description": signal_data["description"]
            }
            detected_signals.append(signal_entry)
            categories[signal_data["category"]].append(signal_entry)
            total_score += signal_data["weight"]

    # ===========================================
    # 2. DETECTAR PRODUCTO DE INTERÉS
    # ===========================================
    detected_product = None
    for product_name, product_data in PRODUCT_SIGNALS.items():
        keyword_found = None
        for keyword in product_data["keywords"]:
            if keyword in all_text:
                keyword_found = keyword
                break

        if keyword_found:
            detected_product = {
                "id": product_name,
                "name": product_data["display_name"],
                "keyword_found": keyword_found,
                "estimated_price": product_data["default_price"],
                "emoji": product_data["emoji"]
            }
            break

    # ===========================================
    # 3. SEÑALES DE COMPORTAMIENTO
    # ===========================================
    behavior_signals = _analyze_behavior(user_messages, bot_messages, messages)

    for signal in behavior_signals:
        detected_signals.append(signal)
        categories["comportamiento"].append(signal)
        total_score += signal["weight"]

    # ===========================================
    # 4. CALCULAR PROBABILIDAD Y CONFIANZA
    # ===========================================

    # Clamp entre 0-100
    probability = max(0, min(100, total_score))

    # Ajustar por estado del lead
    if lead_status == "cliente":
        probability = 100  # Ya compró
    elif lead_status == "caliente":
        probability = max(probability, 60)  # Mínimo 60% si está caliente
    elif lead_status == "fantasma" and probability > 30:
        probability = max(30, probability - 20)  # Reducir si es fantasma

    # Determinar confianza
    signal_count = len(detected_signals)
    if signal_count >= 5:
        confidence = "Alta"
    elif signal_count >= 3:
        confidence = "Media"
    else:
        confidence = "Baja"

    # ===========================================
    # 5. CALCULAR VALOR ESTIMADO
    # ===========================================
    estimated_value = 0
    if detected_product:
        estimated_value = round(detected_product["estimated_price"] * (probability / 100), 2)

    # ===========================================
    # 6. GENERAR SIGUIENTE PASO SUGERIDO
    # ===========================================
    next_step = _generate_next_step(categories, probability, detected_product, lead_status)

    # ===========================================
    # 7. MÉTRICAS DE COMPORTAMIENTO
    # ===========================================
    behavior_metrics = _calculate_behavior_metrics(user_messages, bot_messages, messages)

    return {
        "probabilidad_venta": probability,
        "producto_detectado": detected_product,
        "valor_estimado": estimated_value,
        "confianza_prediccion": confidence,
        "senales_detectadas": detected_signals,
        "senales_por_categoria": {
            "compra": categories["compra"],
            "interes": categories["interes"],
            "objecion": categories["objecion"],
            "comportamiento": categories["comportamiento"]
        },
        "total_senales": signal_count,
        "siguiente_paso": next_step,
        "metricas_comportamiento": behavior_metrics
    }


def _analyze_behavior(user_messages: List, bot_messages: List, all_messages: List) -> List[Dict]:
    """Analiza patrones de comportamiento del lead"""
    signals = []

    if not user_messages:
        return signals

    # 1. Tiempo de respuesta promedio
    avg_response_seconds = _calculate_avg_response_time(all_messages)
    if avg_response_seconds is not None:
        if avg_response_seconds < 3600:  # < 1 hora
            signals.append({
                "signal": "responde_rapido",
                "weight": 15,
                "category": "comportamiento",
                "emoji": "⚡",
                "description": "Responde rápido (<1h)",
                "detail": f"{int(avg_response_seconds/60)} min promedio"
            })
        elif avg_response_seconds > 86400:  # > 24 horas
            signals.append({
                "signal": "responde_lento",
                "weight": -10,
                "category": "comportamiento",
                "emoji": "🐢",
                "description": "Responde lento (>24h)",
                "detail": f"{int(avg_response_seconds/3600)} horas promedio"
            })

    # 2. Longitud de mensajes
    total_chars = sum(len(m.content or "") for m in user_messages)
    avg_length = total_chars / len(user_messages)

    if avg_length > 50:
        signals.append({
            "signal": "mensajes_largos",
            "weight": 10,
            "category": "comportamiento",
            "emoji": "📝",
            "description": "Mensajes detallados",
            "detail": f"{int(avg_length)} chars promedio"
        })
    elif avg_length < 10:
        signals.append({
            "signal": "mensajes_cortos",
            "weight": -5,
            "category": "comportamiento",
            "emoji": "📄",
            "description": "Mensajes muy cortos",
            "detail": f"{int(avg_length)} chars promedio"
        })

    # 3. Cantidad de preguntas
    question_count = sum(1 for m in user_messages if m.content and "?" in m.content)
    if question_count > 3:
        signals.append({
            "signal": "muchas_preguntas",
            "weight": 15,
            "category": "comportamiento",
            "emoji": "❓",
            "description": "Hace muchas preguntas",
            "detail": f"{question_count} preguntas"
        })

    # 4. Si inició la conversación
    if all_messages and all_messages[0].role == "user":
        signals.append({
            "signal": "inicio_conversacion",
            "weight": 10,
            "category": "comportamiento",
            "emoji": "👋",
            "description": "Inició la conversación"
        })

    # 5. Ratio de mensajes (engagement)
    if len(bot_messages) > 0:
        ratio = len(user_messages) / len(bot_messages)
        if ratio > 1.5:
            signals.append({
                "signal": "muy_participativo",
                "weight": 10,
                "category": "comportamiento",
                "emoji": "🔥",
                "description": "Muy participativo",
                "detail": f"Ratio {ratio:.1f}x"
            })

    return signals


def _calculate_avg_response_time(messages: List) -> Optional[float]:
    """Calcula tiempo promedio de respuesta del lead en segundos"""
    if len(messages) < 2:
        return None

    response_times = []

    for i in range(1, len(messages)):
        current = messages[i]
        previous = messages[i-1]

        # Solo medir cuando el lead responde al bot
        if current.role == "user" and previous.role == "assistant":
            if current.created_at and previous.created_at:
                diff = (current.created_at - previous.created_at).total_seconds()
                # Solo contar si es razonable (< 7 días)
                if 0 < diff < 604800:
                    response_times.append(diff)

    if response_times:
        return sum(response_times) / len(response_times)
    return None


def _calculate_behavior_metrics(user_messages: List, bot_messages: List, all_messages: List) -> Dict:
    """Calcula métricas detalladas de comportamiento"""

    avg_response = _calculate_avg_response_time(all_messages)
    avg_length = sum(len(m.content or "") for m in user_messages) / len(user_messages) if user_messages else 0
    question_count = sum(1 for m in user_messages if m.content and "?" in m.content)

    # Formatear tiempo de respuesta
    tiempo_respuesta = None
    if avg_response:
        if avg_response < 3600:
            tiempo_respuesta = f"{int(avg_response/60)} minutos"
        else:
            tiempo_respuesta = f"{int(avg_response/3600)} horas"

    return {
        "tiempo_respuesta_promedio": tiempo_respuesta,
        "tiempo_respuesta_segundos": avg_response,
        "longitud_mensaje_promedio": round(avg_length, 1),
        "cantidad_preguntas": question_count,
        "total_mensajes_lead": len(user_messages),
        "total_mensajes_bot": len(bot_messages),
        "ratio_participacion": round(len(user_messages) / len(bot_messages), 2) if bot_messages else 0
    }


def _generate_next_step(categories: Dict, probability: int, product: Optional[Dict], lead_status: str) -> Dict:
    """Genera el siguiente paso sugerido basado en el análisis"""

    has_objections = len(categories["objecion"]) > 0
    has_purchase_signals = len(categories["compra"]) > 0
    has_interest = len(categories["interes"]) > 0

    # Si ya es cliente
    if lead_status == "cliente":
        return {
            "accion": "upsell",
            "emoji": "🎁",
            "texto": "Cliente actual - considerar upsell o referidos",
            "prioridad": "baja"
        }

    # Si hay objeciones pendientes
    if has_objections:
        objecion = categories["objecion"][0]
        return {
            "accion": "resolver_objecion",
            "emoji": "🛠️",
            "texto": f"Resolver objeción: {objecion['description']}",
            "prioridad": "alta"
        }

    # Si probabilidad alta y señales de compra
    if probability >= 70 and has_purchase_signals:
        return {
            "accion": "enviar_link",
            "emoji": "🔗",
            "texto": "Lead muy caliente - enviar link de pago",
            "prioridad": "urgente"
        }

    # Si preguntó precio pero no hay otras señales de compra
    if any(s["signal"] == "precio_directo" for s in categories["compra"]):
        return {
            "accion": "presentar_valor",
            "emoji": "💎",
            "texto": "Presentar valor antes del precio final",
            "prioridad": "alta"
        }

    # Si hay interés pero no señales de compra
    if has_interest and not has_purchase_signals:
        return {
            "accion": "cualificar",
            "emoji": "🎯",
            "texto": "Cualificar necesidades y presentar solución",
            "prioridad": "media"
        }

    # Si probabilidad baja
    if probability < 30:
        return {
            "accion": "nutrir",
            "emoji": "🌱",
            "texto": "Lead frío - nutrir con contenido de valor",
            "prioridad": "baja"
        }

    # Default
    return {
        "accion": "seguimiento",
        "emoji": "📞",
        "texto": "Continuar conversación y detectar necesidades",
        "prioridad": "media"
    }


def _empty_analysis() -> Dict[str, Any]:
    """Retorna análisis vacío cuando no hay mensajes"""
    return {
        "probabilidad_venta": 0,
        "producto_detectado": None,
        "valor_estimado": 0,
        "confianza_prediccion": "Baja",
        "senales_detectadas": [],
        "senales_por_categoria": {
            "compra": [],
            "interes": [],
            "objecion": [],
            "comportamiento": []
        },
        "total_senales": 0,
        "siguiente_paso": {
            "accion": "esperar",
            "emoji": "⏳",
            "texto": "Esperando primera respuesta del lead",
            "prioridad": "baja"
        },
        "metricas_comportamiento": {
            "tiempo_respuesta_promedio": None,
            "tiempo_respuesta_segundos": None,
            "longitud_mensaje_promedio": 0,
            "cantidad_preguntas": 0,
            "total_mensajes_lead": 0,
            "total_mensajes_bot": 0,
            "ratio_participacion": 0
        }
    }
