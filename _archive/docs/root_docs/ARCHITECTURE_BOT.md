# Arquitectura del Bot - Clonnect

**Fecha:** 2026-01-24
**Versión:** 1.0

---

## Diagrama de Flujo

```
                          ┌──────────────────────────────────────────────────────────────┐
                          │                     INSTAGRAM WEBHOOK                        │
                          │              POST /instagram/webhook                         │
                          │         api/routers/instagram.py:250                         │
                          └─────────────────────────┬────────────────────────────────────┘
                                                    │
                                                    ▼
                          ┌──────────────────────────────────────────────────────────────┐
                          │                  1. ROUTING LAYER                            │
                          │         extract_page_id_from_payload()                       │
                          │         get_creator_by_page_id()                             │
                          │         get_handler_for_creator()                            │
                          └─────────────────────────┬────────────────────────────────────┘
                                                    │
                                                    ▼
                          ┌──────────────────────────────────────────────────────────────┐
                          │                  2. INSTAGRAM HANDLER                        │
                          │         core/instagram_handler.py                            │
                          │         handle_webhook() → process_message()                 │
                          └─────────────────────────┬────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                        3. DM AGENT                                                  │
│                              core/dm_agent.py:process_dm() (línea 4200)                             │
│                                                                                                     │
│  ┌───────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                           PRE-PROCESAMIENTO (FAST PATHS)                                      │  │
│  │                                                                                               │  │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                   │  │
│  │   │ Bot Paused  │    │Rate Limited │    │   GDPR      │    │Meta-Message │                   │  │
│  │   │  (4230)     │───▶│  (4247)     │───▶│  (4318)     │───▶│  (4344)     │                   │  │
│  │   │  ❌ STOP    │    │  ❌ STOP    │    │  ❌ STOP    │    │ FRUSTRATED  │                   │  │
│  │   └─────────────┘    └─────────────┘    └─────────────┘    │ SARCASM     │                   │  │
│  │                                                             │  ❌ STOP    │                   │  │
│  │                                                             └──────┬──────┘                   │  │
│  │                                                                    │                          │  │
│  │   ┌─────────────────────────────────────────────────────────────────────────────────────┐    │  │
│  │   │                        INTENT CLASSIFICATION (4392)                                  │    │  │
│  │   │                   _classify_intent(message, history)                                 │    │  │
│  │   │                                                                                      │    │  │
│  │   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │    │  │
│  │   │  │ESCALATION│ │ BOOKING  │ │INTEREST_ │ │  PRICE   │ │ PURCHASE │ │INTEREST_ │     │    │  │
│  │   │  │  (4398)  │ │ (4434)   │ │ STRONG   │ │ QUESTION │ │  INTENT  │ │  SOFT    │     │    │  │
│  │   │  │❌ STOP   │ │❌ STOP   │ │ (4465)   │ │ (4579)   │ │ (4679)   │ │ (4855)   │     │    │  │
│  │   │  │escalate  │ │booking   │ │❌ STOP   │ │❌ STOP   │ │❌ STOP   │ │❌ STOP   │     │    │  │
│  │   │  │response  │ │links     │ │payment   │ │price     │ │payment   │ │product   │     │    │  │
│  │   │  └──────────┘ └──────────┘ │links     │ │response  │ │link only │ │info      │     │    │  │
│  │   │                            └──────────┘ └──────────┘ └──────────┘ └──────────┘     │    │  │
│  │   │                                                                                      │    │  │
│  │   │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                               │    │  │
│  │   │  │LEAD_     │ │ THANKS   │ │  DIRECT  │ │  ANTI-   │                               │    │  │
│  │   │  │MAGNET    │ │ post-    │ │ PAYMENT  │ │HALLUCIN. │                               │    │  │
│  │   │  │ (4890)   │ │ booking  │ │ (Bizum)  │ │ (5000)   │                               │    │  │
│  │   │  │❌ STOP   │ │ (4928)   │ │ (4544)   │ │❌ STOP   │                               │    │  │
│  │   │  │free      │ │❌ STOP   │ │❌ STOP   │ │no RAG    │                               │    │  │
│  │   │  │content   │ │thanks    │ │method    │ │content   │                               │    │  │
│  │   │  └──────────┘ └──────────┘ │response  │ │→escalate │                               │    │  │
│  │   │                            └──────────┘ └──────────┘                               │    │  │
│  │   └─────────────────────────────────────────────────────────────────────────────────────┘    │  │
│  └───────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                    │                                                 │
│                                      (Si no hay FAST PATH)                                          │
│                                                    ▼                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                    LLM PROCESSING                                             │  │
│  │                                                                                               │  │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                   │  │
│  │   │ Build       │    │ Check       │    │ Chain of    │    │ LLM Call    │                   │  │
│  │   │ Prompts     │───▶│ Cache       │───▶│ Thought     │───▶│ (Groq)      │                   │  │
│  │   │ (5074)      │    │ (5163)      │    │ (5184)      │    │ (5309)      │                   │  │
│  │   │ system +    │    │ ❌ STOP    │    │ Complex     │    │ llama-3.3   │                   │  │
│  │   │ user        │    │ if HIT     │    │ queries     │    │ 70B         │                   │  │
│  │   └─────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘                   │  │
│  │                                                                    │                          │  │
│  └────────────────────────────────────────────────────────────────────┼──────────────────────────┘  │
│                                                                       │                             │
│                                                                       ▼                             │
│  ┌───────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                  POST-PROCESAMIENTO                                           │  │
│  │                                                                                               │  │
│  │   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                   │  │
│  │   │ Guardrails  │    │ Sanitize    │    │ Truncate    │    │Self-Consist.│                   │  │
│  │   │ (5322)      │───▶│ Response    │───▶│ (max 2      │───▶│ (5362)      │                   │  │
│  │   │ prices,     │    │ (5346)      │    │ sentences)  │    │ ONLY for    │                   │  │
│  │   │ URLs,       │    │ remove      │    │ (5349)      │    │ ESCALATION  │                   │  │
│  │   │ hallucin.   │    │ artifacts   │    │             │    │             │                   │  │
│  │   └─────────────┘    └─────────────┘    └─────────────┘    └──────┬──────┘                   │  │
│  │                                                                    │                          │  │
│  │   ┌─────────────┐    ┌─────────────┐                               │                          │  │
│  │   │ Translate   │    │ Cache       │◀──────────────────────────────┘                          │  │
│  │   │ if needed   │───▶│ Response    │                                                          │  │
│  │   │ (5428)      │    │ (5439)      │                                                          │  │
│  │   └─────────────┘    └─────────────┘                                                          │  │
│  └───────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                    │                                                 │
│                                                    ▼                                                 │
│                                           DMResponse                                                 │
└─────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                    │
                                                    ▼
                          ┌──────────────────────────────────────────────────────────────┐
                          │                  4. SEND RESPONSE                            │
                          │         instagram_handler.py → connector.send_message()      │
                          └──────────────────────────────────────────────────────────────┘
```

---

## 1. Entry Point

### Webhook Instagram
- **Archivo:** `backend/api/routers/instagram.py`
- **Función:** `instagram_webhook_receive()` (línea 250)
- **Endpoint:** `POST /instagram/webhook`
- **Qué hace:**
  1. Recibe payload de Meta
  2. Verifica firma (X-Hub-Signature-256)
  3. Extrae page_id del payload
  4. Busca creator asociado al page_id
  5. Verifica si bot está activo
  6. Delega a InstagramHandler

---

## 2. Capas de Pre-procesamiento

### 2.1 Bot Active Check
- **Archivo:** `dm_agent.py:4216-4238`
- **Función:** Verificación directa
- **Qué hace:** Verifica si el bot está pausado por el creador
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta si cortocircuita:** Respuesta vacía (no envía nada)
- **Riesgo:** Ninguno - comportamiento esperado

### 2.2 Rate Limiter
- **Archivo:** `dm_agent.py:4243-4265`
- **Función:** `rate_limiter.check_limit()`
- **Qué hace:** Previene spam y controla costes
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta si cortocircuita:** "Dame un momento, estoy procesando varios mensajes..."
- **Riesgo:** BAJO - Protección necesaria

### 2.3 GDPR Consent Check
- **Archivo:** `dm_agent.py:4317-4321`
- **Función:** `_check_gdpr_consent()`
- **Qué hace:** Verifica consentimiento del usuario (si está habilitado)
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta si cortocircuita:** Mensaje de solicitud de consentimiento
- **Riesgo:** Ninguno - Compliance legal

### 2.4 Meta-Message Detection
- **Archivo:** `dm_agent.py:4341-4389`
- **Función:** `_detect_meta_message()`
- **Qué hace:** Detecta referencias a la conversación misma
- **Acciones detectadas:**
  - `USER_FRUSTRATED` → ❌ CORTOCIRCUITA con respuesta empática hardcoded
  - `SARCASM_DETECTED` → ❌ CORTOCIRCUITA con respuesta empática hardcoded
  - `REVIEW_HISTORY` → Inyecta contexto al mensaje, continúa
  - `REPEAT_REQUESTED` → Inyecta contexto al mensaje, continúa
  - `IMPLICIT_REFERENCE` → Inyecta contexto al mensaje, continúa
- **Puede cortocircuitar:** ✅ SÍ (USER_FRUSTRATED, SARCASM_DETECTED)
- **Respuesta si cortocircuita:**
  - Frustración: "Perdona si no te he entendido bien. Cuéntame de nuevo qué necesitas..."
  - Sarcasmo: "Entiendo que estás frustrado. Perdona si no te he ayudado bien..."
- **Riesgo:** ALTO - Respuestas genéricas que no resuelven el problema real

### 2.5 Intent Classification
- **Archivo:** `dm_agent.py:4391-4395`
- **Función:** `_classify_intent(message, history)`
- **Qué hace:** Determina la intención del usuario
- **Puede cortocircuitar:** ❌ NO directamente
- **Riesgo:** MEDIO - Si clasifica mal, todo el flujo se desvía

### 2.6 ESCALATION Handler
- **Archivo:** `dm_agent.py:4398-4431`
- **Trigger:** `intent == Intent.ESCALATION`
- **Qué hace:** Usuario quiere hablar con humano
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta:** `_get_escalation_response()` + notificación al creador
- **Riesgo:** BAJO - Comportamiento esperado

### 2.7 BOOKING Handler
- **Archivo:** `dm_agent.py:4434-4462`
- **Trigger:** `intent == Intent.BOOKING`
- **Qué hace:** Usuario quiere agendar llamada
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta:** Links de reserva (Calendly, etc.)
- **Riesgo:** BAJO - Funcionalidad útil

### 2.8 INTEREST_STRONG Handler
- **Archivo:** `dm_agent.py:4465-4516`
- **Trigger:** `intent == Intent.INTEREST_STRONG`
- **Qué hace:** Usuario quiere comprar
- **Puede cortocircuitar:** ✅ SÍ (si hay payment links)
- **Respuesta:** Links de pago directos
- **Riesgo:** BAJO - Conversión directa

### 2.9 Direct Payment Question Handler
- **Archivo:** `dm_agent.py:4544-4577`
- **Trigger:** Usuario pregunta por Bizum, transferencia, Revolut, PayPal
- **Qué hace:** Responde con método de pago alternativo
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta:** Datos del método de pago alternativo
- **Riesgo:** BAJO - Útil para conversión

### 2.10 Price Question Handler
- **Archivo:** `dm_agent.py:4579-4677`
- **Trigger:** Keywords de precio ("cuánto cuesta", "precio", etc.)
- **Qué hace:** Responde directamente con precio del producto
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta:** Precio formateado del producto
- **Riesgo:** MEDIO - Puede dar precio incorrecto si product matching falla

### 2.11 Direct Purchase Intent Handler
- **Archivo:** `dm_agent.py:4679-4849`
- **Trigger:** `is_direct_purchase_intent(message)` (y no es THANKS)
- **Qué hace:** Usuario dice "quiero comprar", "lo quiero", etc.
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta:** Solo el link de pago, muy corta
- **Riesgo:** BAJO - Conversión directa

### 2.12 INTEREST_SOFT Handler
- **Archivo:** `dm_agent.py:4855-4885`
- **Trigger:** `intent == Intent.INTEREST_SOFT` con productos disponibles
- **Qué hace:** Muestra info del producto destacado
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta:** Descripción + precio del producto
- **Riesgo:** MEDIO - Puede no ser lo que el usuario preguntó

### 2.13 LEAD_MAGNET Handler
- **Archivo:** `dm_agent.py:4890-4923`
- **Trigger:** `intent == Intent.LEAD_MAGNET`
- **Qué hace:** Usuario pide contenido gratuito
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta:** Link al lead magnet o "no tengo contenido gratuito"
- **Riesgo:** BAJO

### 2.14 THANKS Post-Booking Handler
- **Archivo:** `dm_agent.py:4928-4997`
- **Trigger:** `intent == Intent.THANKS` después de mostrar booking links
- **Qué hace:** Detecta contexto de agradecimiento post-reserva
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta:** "¡Perfecto! Ahí te espero..."
- **Riesgo:** BAJO

### 2.15 Anti-Hallucination RAG Check
- **Archivo:** `dm_agent.py:5000-5062`
- **Trigger:** Intent requiere RAG pero no hay contenido relevante
- **Qué hace:** Escala al creador si no hay info en RAG
- **Puede cortocircuitar:** ✅ SÍ
- **Respuesta:** Escalación al humano
- **Riesgo:** ALTO - Puede escalar innecesariamente si RAG tiene problemas

---

## 3. LLM

### Cuándo se llama
- **Condición:** Solo si ningún fast path anterior respondió
- **Archivo:** `dm_agent.py:5309`

### Qué recibe el LLM

**Estructura de mensajes:**
```python
messages = [
    {"role": "system", "content": system_prompt},
    # Últimos 10 mensajes del historial (5 intercambios)
    {"role": "user", "content": "mensaje anterior 1"},
    {"role": "assistant", "content": "respuesta anterior 1"},
    # ...
    {"role": "user", "content": "mensaje actual"}
]
```

**System Prompt incluye:**
1. Personalidad del creador (clone_tone, clone_vocabulary)
2. Lista de productos con precios y links
3. Instrucciones de categoría (product/service/resource)
4. Tone profile (dialect, expressions)
5. Citation section (contenido RAG relevante)
6. Contexto del usuario (nombre, idioma, productos discutidos)
7. Semantic memory context
8. Instrucciones de conversión (NO_REPETITION, COHERENCE, PROACTIVE_CLOSE)

**Parámetros LLM:**
```python
response_text = await self.llm.chat(
    messages,
    max_tokens=80,      # CORTO - 1-2 frases máximo
    temperature=0.8,    # Más natural, menos robótico
)
```

### Chain of Thought
- **Archivo:** `dm_agent.py:5184-5204`
- **Cuándo:** Si `cot_reasoner.is_complex_query(message)` es True
- **Triggers:**
  - Keywords de salud (lesión, dolor, enfermedad...)
  - Query >50 palabras
  - Comparaciones entre productos
- **Efecto:** Genera respuesta con razonamiento paso a paso

---

## 4. Post-procesamiento

### 4.1 Guardrails
- **Archivo:** `dm_agent.py:5321-5342`
- **Función:** `guardrail.get_safe_response()`
- **Qué hace:**
  - Verifica precios correctos
  - Valida URLs permitidas
  - Detecta alucinaciones
- **Puede modificar respuesta:** ✅ SÍ

### 4.2 Sanitize Response
- **Archivo:** `dm_agent.py:5346`
- **Función:** `sanitize_llm_response()`
- **Qué hace:** Elimina artefactos del LLM ([RESPUESTA], texto basura, etc.)
- **Puede modificar respuesta:** ✅ SÍ

### 4.3 Truncate Response
- **Archivo:** `dm_agent.py:5349`
- **Función:** `truncate_response(max_sentences=2)`
- **Qué hace:** Corta a máximo 2 frases
- **Puede modificar respuesta:** ✅ SÍ (AGRESIVAMENTE)

### 4.4 Clean Placeholders
- **Archivo:** `dm_agent.py:5352-5353`
- **Función:** `clean_response_placeholders()`
- **Qué hace:** Reemplaza placeholders con links reales
- **Puede modificar respuesta:** ✅ SÍ

### 4.5 Truncate Payment Response
- **Archivo:** `dm_agent.py:5356`
- **Función:** `truncate_payment_response()`
- **Qué hace:** Extra brevedad para respuestas de pago
- **Puede modificar respuesta:** ✅ SÍ

### 4.6 Self-Consistency Check
- **Archivo:** `dm_agent.py:5358-5425`
- **Cuándo:** Solo para `Intent.ESCALATION`
- **Qué hace:** Genera múltiples samples y verifica consistencia
- **Si baja confianza:** Usa fallback "Déjame confirmarlo con [creador]..."
- **Problema:** CASI DESACTIVADO - solo 1 intent lo usa

### 4.7 Translation
- **Archivo:** `dm_agent.py:5428-5436`
- **Cuándo:** Si idioma detectado ≠ idioma del usuario
- **Función:** `translate_response()`

### 4.8 Cache Response
- **Archivo:** `dm_agent.py:5438-5442`
- **Cuándo:** Si intent es cacheable
- **Función:** `response_cache.set()`

---

## 5. Puntos Críticos de Fallo

| # | Capa | Línea | Puede secuestrar | Tipo de respuesta | Riesgo |
|---|------|-------|------------------|-------------------|--------|
| 1 | Bot Paused | 4230 | ✅ | Vacía (no envía) | BAJO |
| 2 | Rate Limiter | 4247 | ✅ | Hardcoded genérica | BAJO |
| 3 | USER_FRUSTRATED | 4353 | ✅ | Hardcoded empática | **ALTO** |
| 4 | SARCASM_DETECTED | 4380 | ✅ | Hardcoded empática | **ALTO** |
| 5 | ESCALATION | 4398 | ✅ | Escalación template | BAJO |
| 6 | BOOKING | 4434 | ✅ | Links de reserva | BAJO |
| 7 | INTEREST_STRONG | 4465 | ✅ | Links de pago | BAJO |
| 8 | Direct Payment | 4544 | ✅ | Método de pago | BAJO |
| 9 | Price Question | 4579 | ✅ | Precio formateado | MEDIO |
| 10 | Direct Purchase | 4679 | ✅ | Solo link | BAJO |
| 11 | INTEREST_SOFT | 4855 | ✅ | Info producto | MEDIO |
| 12 | LEAD_MAGNET | 4890 | ✅ | Link gratuito | BAJO |
| 13 | THANKS post-book | 4928 | ✅ | Agradecimiento | BAJO |
| 14 | Anti-Hallucination | 5000 | ✅ | Escalación | **ALTO** |
| 15 | Cache HIT | 5168 | ✅ | Respuesta cacheada | MEDIO |
| 16 | Guardrails | 5338 | ✅ Modifica | Respuesta sanitizada | MEDIO |
| 17 | Truncate | 5349 | ✅ Modifica | Respuesta cortada | **ALTO** |
| 18 | Self-Consistency | 5390 | ✅ (solo ESCALATION) | Fallback genérico | BAJO |

---

## 6. Análisis de Riesgos

### RIESGO ALTO: Respuestas que "secuestran" sin entender

#### 6.1 USER_FRUSTRATED / SARCASM_DETECTED (líneas 4353, 4380)
```python
# PROBLEMA: Respuesta hardcoded que no resuelve nada
if action == "USER_FRUSTRATED":
    response_text = "Perdona si no te he entendido bien. Cuéntame de nuevo..."
```
**Ejemplo de fallo:**
- Usuario: "Ya te dije 3 veces que quiero el precio del curso avanzado"
- Bot: "Perdona si no te he entendido bien. Cuéntame de nuevo qué necesitas"
- **Debería:** Dar el precio del curso avanzado

#### 6.2 Anti-Hallucination Escalation (línea 5000)
```python
# PROBLEMA: Escala si no encuentra RAG, aunque la info esté en productos
if not citation_section:
    return escalation_response  # "Te paso con el creador..."
```
**Ejemplo de fallo:**
- Usuario: "¿Tienes algo sobre nutrición?"
- RAG no tiene contenido de nutrición indexado
- Bot: "Te paso con el creador..." (ESCALA)
- **Debería:** "No tengo contenido específico de nutrición, pero tengo X e Y"

#### 6.3 Truncate Response (línea 5349)
```python
# PROBLEMA: Corta agresivamente a 2 frases, puede perder info crucial
response_text = truncate_response(response_text, max_sentences=2)
```
**Ejemplo de fallo:**
- LLM genera: "El curso cuesta 297€. Incluye acceso de por vida, comunidad privada, y soporte 24/7. El link es: https://..."
- Después de truncar: "El curso cuesta 297€. Incluye acceso de por vida"
- **Se pierde:** El link de compra

---

## 7. Recomendaciones

### 7.1 Dar más control al LLM

**Problema:** Demasiados fast paths con respuestas hardcoded.

**Solución:** Convertir fast paths en "context injection" en lugar de cortocircuitos:

```python
# ANTES (cortocircuita):
if action == "USER_FRUSTRATED":
    return DMResponse(response_text="Perdona si no te he entendido...")

# DESPUÉS (inyecta contexto, deja que LLM responda):
if action == "USER_FRUSTRATED":
    system_prompt += """
    ALERTA: El usuario está frustrado porque no le hemos entendido.
    - Revisa el historial para encontrar qué preguntó antes
    - Responde DIRECTAMENTE a su pregunta original
    - Sé empático pero RESUELVE su problema, no solo te disculpes
    """
    # Continuar al LLM
```

### 7.2 Mejorar Anti-Hallucination

**Problema:** Escala si no hay RAG, aunque la info esté en productos.

**Solución:**
```python
if not citation_section:
    # ANTES de escalar, verificar si podemos responder con productos
    if self._can_answer_from_products(message_text):
        # Continuar al LLM con productos como contexto
        pass
    else:
        # Ahora sí escalar
        return escalation_response
```

### 7.3 Truncate más inteligente

**Problema:** Corta sin verificar si hay info crítica.

**Solución:**
```python
def smart_truncate(response: str, max_sentences: int = 2) -> str:
    # NO truncar si contiene:
    # - URLs (links de pago)
    # - Precios
    # - Información de reserva
    if "http" in response or "€" in response or "reserv" in response.lower():
        return response[:400]  # Límite de caracteres en lugar de frases
    return truncate_response(response, max_sentences)
```

### 7.4 Activar Reflexion para objeciones

**Problema:** Las objeciones complejas reciben respuestas genéricas.

**Solución:** Ver AUDITORIA_COGNITIVA_BOT.md - activar Reflexion después de línea 5200.

---

## 8. Resumen de Archivos Clave

| Archivo | Tamaño | Función | Líneas clave |
|---------|--------|---------|--------------|
| `api/routers/instagram.py` | 24KB | Entry point webhook | 250-327 |
| `core/instagram_handler.py` | 24KB | Handler por creator | 137-355 |
| `core/dm_agent.py` | **272KB** | AGENTE PRINCIPAL | 4200-5500 |
| `core/intent_classifier.py` | 18KB | Clasificación intent | Todo |
| `core/reasoning/chain_of_thought.py` | 11KB | CoT | Todo |
| `core/reasoning/reflexion.py` | 10KB | Auto-mejora | Todo |
| `core/reasoning/self_consistency.py` | 11KB | Validación | Todo |
| `core/rag/reranker.py` | 4KB | Cross-Encoder | Todo |
| `core/guardrails.py` | 12KB | Validación respuestas | Todo |

---

## 9. Métricas de Flujo

De cada 100 mensajes procesados (estimación):

| Destino | % | Descripción |
|---------|---|-------------|
| Fast Paths (sin LLM) | ~40% | Booking, payment, price, escalation |
| Cache HIT | ~15% | Respuestas cacheadas |
| LLM Call | ~45% | Procesamiento completo |

De los LLM calls:
| Post-procesamiento | % afectados |
|-------------------|-------------|
| Guardrails modifica | ~5% |
| Truncate modifica | ~60% |
| Self-Consistency override | <1% |
| Translation | ~10% |
