# 🔬 VERIFICACIÓN TOTAL DE SISTEMAS CLONNECT
## Test Masivo de Integración - La Hora de la Verdad

**Fecha:** 2026-02-12
**Branch:** main (a832087)
**Objetivo:** Verificar que TODOS los sistemas funcionan con data REAL de producción

---

## 📊 RESUMEN DE DATA EN PRODUCCIÓN

| Tabla | Registros | Sistema que la usa |
|-------|-----------|-------------------|
| messages | 5,226 | DM Agent, Copilot, Memory |
| leads | 249 | Lead Service, CRM, Nurturing |
| relationship_dna | 138 | DNA Triggers, Personalization |
| follower_memories | 246 | Memory Store, Context |
| conversation_states | 216 | State Machine, Funnel |
| calendar_bookings | 14 | Calendar Service, Booking |
| products | ~10+ | Product Manager, RAG |
| knowledge_base | ~20+ | RAG, Citation Service |

---

## 🧪 CATEGORÍA 1: MEMORIA Y CONTEXTO

### 1.1 FollowerMemoryDB (follower_memories)
**Tabla:** `follower_memories` (246 registros)
**Servicio:** `services/memory_service.py`, `core/dm_agent_v2.py`

**Campos a verificar:**
- username, name
- total_messages
- interests (JSON array)
- products_discussed (JSON array)
- purchase_intent_score
- is_lead, is_customer, status
- last_messages (últimos 20 mensajes)
- objections_raised, objections_handled

**PREGUNTAS TEST:**
```
Q1: "¿Cuántos mensajes hemos intercambiado?"
→ Bot debe usar: total_messages

Q2: "¿De qué productos hemos hablado antes?"
→ Bot debe usar: products_discussed

Q3: "¿Cuáles son mis intereses?"
→ Bot debe usar: interests

Q4: "¿Qué dudas tuve la última vez?"
→ Bot debe usar: objections_raised
```

### 1.2 ConversationStateDB (conversation_states)
**Tabla:** `conversation_states` (216 registros)
**Servicio:** `core/conversation_state.py`

**Campos a verificar:**
- phase (inicio, cualificacion, descubrimiento, propuesta, objeciones, cierre, escalar)
- message_count
- context (JSON con UserContext)

**PREGUNTAS TEST:**
```
Q1: "Quiero comprar" (después de varias interacciones)
→ Bot debe detectar: fase avanzada, no repetir pitch inicial

Q2: Mensaje frustrado después de muchos mensajes
→ Bot debe escalar según phase + message_count

Q3: Primera interacción con nuevo lead
→ Bot debe iniciar en phase="inicio"
```

### 1.3 ConversationEmbedding (conversation_embeddings)
**Tabla:** `conversation_embeddings`
**Servicio:** `core/semantic_memory.py`, pgvector

**PREGUNTAS TEST:**
```
Q1: "¿Qué me dijiste sobre mi negocio hace tiempo?"
→ Bot debe buscar semánticamente en histórico

Q2: "Recuerdas cuando hablamos de precios?"
→ Bot debe recuperar contexto de conversaciones pasadas
```

---

## 🧪 CATEGORÍA 2: LEADS Y CRM

### 2.1 Lead (leads)
**Tabla:** `leads` (249 registros)
**Servicio:** `services/lead_service.py`, `api/routers/leads.py`

**Campos a verificar:**
- status (nuevo, interesado, caliente, cliente, fantasma)
- score (0-100)
- purchase_intent (0.0-1.0)
- context (JSON)
- tags, email, phone, deal_value, source

**PREGUNTAS TEST:**
```
Q1: Lead con purchase_intent > 0.8
→ Sistema debe: notificar como HOT lead

Q2: Lead sin interacción en 7+ días
→ Sistema debe: marcar como fantasma, activar nurturing

Q3: Lead que menciona precio específico
→ Sistema debe: actualizar deal_value
```

### 2.2 LeadActivity (lead_activities)
**Tabla:** `lead_activities`
**Servicio:** `api/routers/leads.py`

**Campos a verificar:**
- activity_type (note, status_change, email, call, meeting, tag_added)
- description
- old_value, new_value

**PREGUNTAS TEST:**
```
Q1: Verificar timeline de lead específico
→ API debe retornar: historial completo de actividades

Q2: Cambio de status debe crear activity
→ Sistema debe: registrar old_value → new_value
```

### 2.3 LeadIntelligence (lead_intelligence)
**Tabla:** `lead_intelligence`
**Servicio:** `core/intelligence/engine.py`

**Campos a verificar:**
- engagement_score, intent_score, fit_score, urgency_score
- conversion_probability
- recommended_action, talking_points

**PREGUNTAS TEST:**
```
Q1: Lead con alto engagement pero bajo intent
→ Sistema debe: recomendar acción de cualificación

Q2: Lead con alto conversion_probability
→ Sistema debe: priorizar en dashboard
```

---

## 🧪 CATEGORÍA 3: RELACIÓN Y PERSONALIZACIÓN

### 3.1 RelationshipDNAModel (relationship_dna)
**Tabla:** `relationship_dna` (138 registros)
**Servicio:** `services/relationship_analyzer.py`, `services/dna_update_triggers.py`

**Campos a verificar:**
- relationship_type (DESCONOCIDO, CASUAL, CERCANO, VIP, CLIENTE)
- trust_score (0.0-1.0)
- depth_level (0-5)
- vocabulary_uses, vocabulary_avoids
- emojis
- recurring_topics, private_references
- bot_instructions
- golden_examples

**PREGUNTAS TEST:**
```
Q1: Lead con relationship_type=CERCANO
→ Bot debe: usar tono más informal, emojis del array

Q2: Lead con vocabulary_avoids=["formal", "usted"]
→ Bot debe: evitar esas palabras

Q3: Lead con recurring_topics=["coaching", "negocios"]
→ Bot debe: referenciar esos temas naturalmente

Q4: Lead con golden_examples
→ Bot debe: imitar estilo de esos ejemplos
```

### 3.2 UserProfileDB (user_profiles)
**Tabla:** `user_profiles`
**Servicio:** `core/user_profiles.py`

**Campos a verificar:**
- preferences (language, response_style, communication_tone)
- interests (topic → weight)
- objections (list)
- interested_products

**PREGUNTAS TEST:**
```
Q1: Lead con preferred_language=en
→ Bot debe: responder en inglés

Q2: Lead con interests={coaching: 0.9, ebooks: 0.2}
→ Bot debe: priorizar coaching en recomendaciones
```

---

## 🧪 CATEGORÍA 4: PRODUCTOS Y CONOCIMIENTO

### 4.1 Product (products)
**Tabla:** `products`
**Servicio:** `core/products.py`, RAG

**Campos a verificar:**
- name, description, short_description
- category (product, service, resource)
- price, currency, is_free
- payment_link
- is_active
- source_url, price_verified, confidence

**PREGUNTAS TEST:**
```
Q1: "¿Cuánto cuesta la mentoría?"
→ Bot debe: dar precio EXACTO de products.price

Q2: "¿Tienes algo gratuito?"
→ Bot debe: filtrar por is_free=true

Q3: "¿Cómo puedo pagar?"
→ Bot debe: dar payment_link correcto

Q4: Producto con is_active=false
→ Bot NO debe: mencionarlo nunca
```

### 4.2 KnowledgeBase (knowledge_base)
**Tabla:** `knowledge_base`
**Servicio:** `services/knowledge_base.py`, RAG

**Campos a verificar:**
- question
- answer

**PREGUNTAS TEST:**
```
Q1: Pregunta que matchea con knowledge_base.question
→ Bot debe: usar knowledge_base.answer como fuente

Q2: "¿Cuál es tu experiencia?"
→ Bot debe: buscar en KB y citar
```

### 4.3 RAGDocument (rag_documents)
**Tabla:** `rag_documents`
**Servicio:** `core/rag/semantic.py`

**PREGUNTAS TEST:**
```
Q1: Pregunta técnica sobre contenido del creador
→ Bot debe: recuperar chunks relevantes

Q2: "¿Qué dijiste en tu último podcast?"
→ Bot debe: buscar en transcripciones indexadas
```

---

## 🧪 CATEGORÍA 5: CALENDARIO Y RESERVAS

### 5.1 BookingLink (booking_links)
**Tabla:** `booking_links`
**Servicio:** `core/calendar.py`

**Campos a verificar:**
- meeting_type (discovery, consultation, coaching)
- title, duration_minutes
- url
- price

**PREGUNTAS TEST:**
```
Q1: "¿Puedo agendar una llamada contigo?"
→ Bot debe: ofrecer booking_links disponibles

Q2: "¿Cuánto dura la sesión gratuita?"
→ Bot debe: dar duration_minutes de discovery call
```

### 5.2 CalendarBooking (calendar_bookings)
**Tabla:** `calendar_bookings` (14 registros)
**Servicio:** `api/routers/booking.py`

**Campos a verificar:**
- status (scheduled, completed, cancelled, no_show)
- scheduled_at
- guest_name, guest_email

**PREGUNTAS TEST:**
```
Q1: Lead con booking existente
→ Bot debe: recordar que ya tiene cita agendada

Q2: "¿Cuándo es mi llamada?"
→ Bot debe: dar scheduled_at del booking activo
```

---

## 🧪 CATEGORÍA 6: NURTURING Y AUTOMATIZACIÓN

### 6.1 NurturingSequence (nurturing_sequences)
**Tabla:** `nurturing_sequences`
**Servicio:** `core/nurturing.py`

**Campos a verificar:**
- type (welcome, follow_up, ghost_reactivation)
- steps (JSON array)
- is_active

**PREGUNTAS TEST:**
```
Q1: Nuevo lead entra
→ Sistema debe: activar welcome sequence

Q2: Lead inactivo 7+ días
→ Sistema debe: activar ghost_reactivation

Q3: Lead responde durante nurturing
→ Sistema debe: pausar secuencia, pasar a bot
```

---

## 🧪 CATEGORÍA 7: ANALYTICS E INTELIGENCIA

### 7.1 CreatorMetricsDaily (creator_metrics_daily)
**Tabla:** `creator_metrics_daily`
**Servicio:** `core/analytics/analytics_manager.py`

**Campos a verificar:**
- total_conversations, total_messages
- new_leads, leads_qualified, conversions
- revenue

**PREGUNTAS TEST:**
```
Q1: Dashboard debe mostrar métricas diarias
→ API debe: retornar datos agregados correctos

Q2: Comparación semana anterior
→ Sistema debe: calcular deltas correctamente
```

### 7.2 WeeklyReport (weekly_reports)
**Tabla:** `weekly_reports`
**Servicio:** `core/analytics/`

**PREGUNTAS TEST:**
```
Q1: Generar reporte semanal
→ Sistema debe: agregar métricas + generar insights LLM
```

---

## 🧪 CATEGORÍA 8: MENSAJES Y COPILOT

### 8.1 Message (messages)
**Tabla:** `messages` (5,226 registros)
**Servicio:** `api/routers/messages.py`, Copilot

**Campos a verificar:**
- role (user, assistant)
- content
- intent
- status (pending_approval, sent, edited, discarded)
- approved_by (creator, auto)

**PREGUNTAS TEST:**
```
Q1: Mensaje en copilot mode
→ Sistema debe: crear con status=pending_approval

Q2: Creator aprueba mensaje
→ Sistema debe: actualizar status=sent, approved_by=creator

Q3: Historial de conversación
→ API debe: retornar mensajes ordenados por created_at
```

---

## 🧪 CATEGORÍA 9: DETECCIÓN Y SEGURIDAD

### 9.1 Sensitive Detection
**Servicio:** `core/sensitive_detector.py`

**PREGUNTAS TEST:**
```
Q1: Mensaje con señales de autolesión
→ Bot debe: escalar inmediatamente, dar recursos de crisis

Q2: Mensaje con amenazas
→ Bot debe: escalar, notificar creador

Q3: Intento de phishing
→ Bot debe: bloquear, no compartir info personal
```

### 9.2 Frustration Detection
**Servicio:** `core/frustration_detector.py`

**PREGUNTAS TEST:**
```
Q1: "Ya te pregunté esto 3 veces!!!"
→ Bot debe: detectar frustración, ajustar tono

Q2: Múltiples mensajes cortos en secuencia
→ Bot debe: no enviar múltiples respuestas separadas
```

---

## 🧪 CATEGORÍA 10: POST-PROCESAMIENTO

### 10.1 Guardrails
**Servicio:** `core/guardrails.py`

**PREGUNTAS TEST:**
```
Q1: Bot intenta inventar precio
→ Guardrail debe: validar contra products.price

Q2: Bot intenta inventar URL
→ Guardrail debe: validar contra payment_links

Q3: Bot menciona producto que no existe
→ Guardrail debe: eliminar o corregir
```

### 10.2 Output Validator
**Servicio:** `core/output_validator.py`

**PREGUNTAS TEST:**
```
Q1: Respuesta > 400 chars
→ Validator debe: truncar

Q2: Respuesta con [LINK] placeholder
→ Validator debe: reemplazar con URL real

Q3: Respuesta con precio incorrecto
→ Validator debe: corregir o flag
```

### 10.3 Length Controller
**Servicio:** `services/length_controller.py`

**PREGUNTAS TEST:**
```
Q1: Pregunta simple "¿Precio?"
→ Bot debe: respuesta ultra-corta (<50 chars)

Q2: Pregunta compleja sobre metodología
→ Bot debe: respuesta más elaborada pero <200 chars
```

---

## 🧪 CATEGORÍA 11: PROVIDERS LLM

### 11.1 Scout Production
**Servicio:** `core/providers/deepinfra_provider.py`

**PREGUNTAS TEST:**
```
Q1: DeepInfra disponible
→ Sistema debe: usar Scout via DeepInfra

Q2: DeepInfra falla (rate limit)
→ Sistema debe: fallback a Groq automáticamente

Q3: Ambos fallan
→ Sistema debe: usar respuesta fallback predefinida
```

### 11.2 Fine-tuned Model
**Servicio:** `core/providers/together_provider.py`

**PREGUNTAS TEST:**
```
Q1: ENABLE_FINETUNED_MODEL=true
→ Sistema debe: usar modelo fine-tuned

Q2: Fine-tuned falla
→ Sistema debe: fallback a Scout base
```

---

## 📋 SCRIPT DE VERIFICACIÓN

```python
"""
verify_all_systems.py - Test masivo de integración
"""

import asyncio
import os
from datetime import datetime
from typing import Dict, List

# Categorías y tests
TESTS = {
    "1_MEMORIA": [
        ("¿Cuántos mensajes hemos intercambiado?", "total_messages"),
        ("¿De qué productos hemos hablado?", "products_discussed"),
        ("¿Cuáles son mis intereses?", "interests"),
    ],
    "2_LEADS": [
        ("Lead con intent > 0.8", "hot_lead_detection"),
        ("Lead inactivo 7+ días", "ghost_detection"),
    ],
    "3_DNA": [
        ("Lead CERCANO - tono informal", "relationship_type"),
        ("Vocabulario personalizado", "vocabulary_uses"),
    ],
    "4_PRODUCTOS": [
        ("¿Cuánto cuesta la mentoría?", "price_accuracy"),
        ("¿Tienes algo gratuito?", "free_filter"),
        ("¿Cómo puedo pagar?", "payment_link"),
    ],
    "5_CALENDARIO": [
        ("¿Puedo agendar una llamada?", "booking_offer"),
        ("¿Cuándo es mi llamada?", "booking_recall"),
    ],
    "6_SEGURIDAD": [
        ("Mensaje con señales crisis", "sensitive_escalation"),
        ("Frustración detectada", "frustration_handling"),
    ],
    "7_GUARDRAILS": [
        ("Precio inventado", "price_validation"),
        ("URL inventada", "link_validation"),
    ],
    "8_PROVIDERS": [
        ("DeepInfra OK", "primary_provider"),
        ("Fallback Groq", "fallback_chain"),
    ],
}

async def run_all_tests():
    """Ejecutar todos los tests y generar reporte."""
    results = {}

    for category, tests in TESTS.items():
        results[category] = []
        for test_input, expected in tests:
            # Aquí iría la lógica de test
            result = await run_single_test(test_input, expected)
            results[category].append(result)

    return results

async def run_single_test(test_input: str, expected: str) -> Dict:
    """Ejecutar un test individual."""
    # Implementación del test
    pass

if __name__ == "__main__":
    asyncio.run(run_all_tests())
```

---

## ✅ CHECKLIST DE VERIFICACIÓN

### Memoria y Contexto
- [ ] FollowerMemory se carga correctamente
- [ ] total_messages refleja conversación real
- [ ] products_discussed se actualiza con cada mención
- [ ] ConversationState persiste entre sesiones
- [ ] Semantic memory encuentra contexto histórico

### Leads y CRM
- [ ] Lead status se actualiza automáticamente
- [ ] purchase_intent se calcula correctamente
- [ ] Hot leads generan notificación
- [ ] Ghost leads activan nurturing
- [ ] Activities se registran en timeline

### RelationshipDNA
- [ ] DNA se genera para cada lead
- [ ] relationship_type se clasifica correctamente
- [ ] vocabulary_uses se aplica en respuestas
- [ ] golden_examples influyen en estilo
- [ ] bot_instructions se inyectan en prompt

### Productos
- [ ] Precios son EXACTOS (no inventados)
- [ ] payment_links son correctos
- [ ] is_active=false no se menciona
- [ ] Productos se recuperan via RAG

### Calendario
- [ ] booking_links se ofrecen correctamente
- [ ] Bookings existentes se recuerdan
- [ ] Disponibilidad se verifica

### Seguridad
- [ ] Contenido sensible escala inmediatamente
- [ ] Frustración se detecta y maneja
- [ ] Guardrails bloquean alucinaciones
- [ ] Precios se validan contra DB

### Providers
- [ ] DeepInfra funciona como primary
- [ ] Groq funciona como fallback
- [ ] Fine-tuned model disponible
- [ ] Latencia < 2s promedio

---

*Documento generado: 2026-02-12*
*Para ejecutar tests: python -m scripts.verify_all_systems*
