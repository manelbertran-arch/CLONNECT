# AUDITORÍA COMPLETA: Sistema de Inteligencia Conversacional de Clonnect

**Fecha:** 2026-01-11
**Auditor:** Claude Code
**Versión del sistema:** Production (branch main)

---

## RESUMEN EJECUTIVO

El sistema de conversación de Clonnect tiene **fallos críticos en la memoria conversacional** que causan respuestas descontextualizadas y bucles de preguntas. El problema principal NO es técnico de almacenamiento (el historial SÍ se guarda), sino de **cómo se usa ese historial en la generación de respuestas**.

### Diagnóstico en 1 línea:
> **El bot GUARDA el historial pero NO LO ENTIENDE cuando genera respuestas.**

---

## 1. COMPONENTES ENCONTRADOS

### 1.1 Generación de Respuestas (LLM)
| Archivo | Función |
|---------|---------|
| `backend/core/dm_agent.py` | **Agente principal** - 4000+ líneas, maneja todo el flujo |
| `backend/core/llm.py` | Cliente LLM unificado (Groq, OpenAI, Anthropic) |
| `backend/ingestion/response_engine_v2.py` | Motor alternativo "Magic Slice" (NO se usa en producción) |
| `backend/core/intent_classifier.py` | Clasificador de intenciones |

### 1.2 Sistema de Memoria
| Archivo | Función |
|---------|---------|
| `backend/core/memory.py` | FollowerMemory - guarda últimos 20 mensajes en JSON |
| `backend/api/models.py` | Modelos PostgreSQL (Lead, Message, ContentChunk) |
| `backend/core/dm_history_service.py` | Importa historial de Instagram |

### 1.3 RAG/Knowledge Base
| Archivo | Función |
|---------|---------|
| `backend/core/rag/semantic.py` | Búsqueda semántica con pgvector |
| `backend/core/rag/bm25.py` | Búsqueda léxica BM25 |
| `backend/core/embeddings.py` | Embeddings OpenAI text-embedding-3-small |
| `backend/core/citation_service.py` | Citación de contenido del creador |

### 1.4 Personalización
| Archivo | Función |
|---------|---------|
| `backend/ingestion/tone_analyzer.py` | ToneProfile - clona voz del creador |
| `backend/core/tone_service.py` | Gestiona perfiles de tono |
| `backend/core/creator_config.py` | Configuración del creador |

---

## 2. ANÁLISIS DEL FLUJO DE RESPUESTA

### 2.1 Flujo Actual (Simplificado)

```
┌──────────────────────────────────────────────────────────────────────┐
│                        MENSAJE ENTRANTE                              │
│                    "Si" (después de pregunta)                        │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│           PASO 1: CLASIFICAR INTENT (dm_agent.py:1233)               │
│                                                                      │
│   "Si" → len < 25 chars → match "sí" → ACKNOWLEDGMENT (0.90)         │
│                                                                      │
│   ⚠️ PROBLEMA: No considera contexto de conversación anterior        │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│           PASO 2: FAST PATH ACKNOWLEDGMENT (dm_agent.py:2590)        │
│                                                                      │
│   if intent == Intent.ACKNOWLEDGMENT:                                │
│       response = _get_fallback_response(ACKNOWLEDGMENT)              │
│       return response  ← RETORNO INMEDIATO, NO LLAMA AL LLM          │
│                                                                      │
│   ⚠️ PROBLEMA: Usa respuesta HARDCODED, ignora completamente el      │
│                contexto de la conversación                           │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│           RESPUESTAS HARDCODED (dm_agent.py:3707-3711)               │
│                                                                      │
│   Intent.ACKNOWLEDGMENT: [                                           │
│       "Perfecto! ¿Te gustaría saber más sobre algo?",                │
│       "Genial! ¿En qué más puedo ayudarte?",  ← EXACTAMENTE ESTO     │
│       "Ok! ¿Hay algo más que quieras saber?",                        │
│   ]                                                                  │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Cómo se Recupera el Historial

**Ubicación:** `dm_agent.py:2148-2152`

```python
# Historial de conversación
history_text = ""
if conversation_history:
    history_text = "\nCONVERSACION RECIENTE:\n"
    for msg in conversation_history[-4:]:  # ⚠️ SOLO 4 MENSAJES
        role = "Usuario" if msg.get("role") == "user" else "Yo"
        history_text += f"{role}: {msg.get('content', '')}\n"
```

**Problemas identificados:**
1. Solo incluye **últimos 4 mensajes** (2 intercambios)
2. Se pasa como **texto plano** en el user_prompt, no como mensajes estructurados
3. **NUNCA se usa para ACKNOWLEDGMENT** porque el fast path retorna antes de construir el prompt

### 2.3 Cómo se Llama al LLM

**Ubicación:** `dm_agent.py:2910-2924`

```python
messages = [
    {"role": "system", "content": system_prompt},  # ~3000+ chars
    {"role": "user", "content": user_prompt}       # mensaje + historial
]

response_text = await self.llm.chat(
    messages,
    max_tokens=80,  # ⚠️ MUY CORTO
    temperature=0.8
)
```

**Problemas:**
1. Solo 2 mensajes al LLM (system + user), NO una conversación multi-turn real
2. max_tokens=80 es muy restrictivo
3. El historial está enterrado en el user_prompt después de mucho contexto

---

## 3. REVISIÓN DEL SYSTEM PROMPT

### 3.1 System Prompt Actual (Resumido)

**Ubicación:** `dm_agent.py:1647-2121` (~475 líneas)

```
{MAGIC_SLICE_TONE_PROFILE}
{DYNAMIC_RULES}
{SALES_STRATEGY}

Eres {name}, un creador de contenido que responde mensajes de Instagram/WhatsApp.

{INSTRUCCIONES_PERSONALIDAD_PRIORITARIAS}
{ADVERTENCIA_NO_PRODUCTOS}

PERSONALIDAD:
- {tone_instruction}
- {formality_rule}
- {emoji_instruction}

{CITATION_PLACEHOLDER}

SOBRE MÍ:
{knowledge_section}

MIS PRODUCTOS:
{products_text}

LINKS DE PAGO:
{payment_links_text}
{alt_payment_text}

{FORMAT_INSTRUCTION}
{EXAMPLES_SECTION}
{NEGATIVE_EXAMPLES}
{CONTACT_CAPTURE_RULES}
```

### 3.2 Análisis del System Prompt

| Aspecto | Estado | Comentario |
|---------|--------|------------|
| Instrucciones de coherencia conversacional | ❌ **NO EXISTE** | No hay instrucción de "mantener contexto" |
| Recordar lo que el usuario dijo | ❌ **NO EXISTE** | No hay instrucción de "recordar conversación" |
| Contenido del creador | ✅ Parcial | Se inyecta via citations pero solo para queries relevantes |
| Personalidad definida | ✅ Sí | ToneProfile con formality, energy, warmth |
| Ejemplos de respuesta | ✅ Sí | Ejemplos buenos y malos |

### 3.3 Lo que FALTA en el System Prompt

```
❌ FALTANTE CRÍTICO:

"MEMORIA CONVERSACIONAL:
- SIEMPRE lee la CONVERSACIÓN RECIENTE antes de responder
- Si el usuario dice 'sí', 'vale', 'ok' → responde a la ÚLTIMA pregunta que hiciste
- Si el usuario dice 'ya te lo dije' → revisa el historial y recuerda lo que dijo
- NUNCA preguntes algo que el usuario ya respondió
- Mantén el HILO de la conversación"
```

---

## 4. DIAGNÓSTICO DEL PROBLEMA (Conversación Real)

### 4.1 Conversación Analizada

```
Usuario: "Hola, me interesa saber más sobre tus servicios de coaching"
Bot: "¿Qué aspecto de tu bienestar te gustaría mejorar?"

Usuario: "Bajar niveles de ansiedad"
Bot: "La ansiedad puede ser un gran obstáculo... ¿te gustaría saber más?"

Usuario: "Si"
Bot: "Genial! ¿En qué más puedo ayudarte?"  ← FALLO CRÍTICO

Usuario: "Ya te lo he dicho"
Bot: "¿Podés aclararme un poco más?"  ← NO RECUERDA NADA

Usuario: "Revisa chat"
Bot: "¡Claro! Revisaré el chat"  ← PERO NO LO HACE
```

### 4.2 Análisis Paso a Paso

| Turno | Mensaje | Intent Detectado | Problema |
|-------|---------|------------------|----------|
| 3 | "Si" | `ACKNOWLEDGMENT` | Debería ser `INTEREST_SOFT` en contexto |
| 4 | "Ya te lo he dicho" | `OTHER` o `CORRECTION` | Debería revisar historial |
| 5 | "Revisa chat" | `OTHER` | Respuesta genérica sin acción real |

### 4.3 Root Causes

1. **El clasificador de intents NO tiene contexto**
   - `_quick_classify()` solo mira el mensaje actual
   - "Si" siempre será `ACKNOWLEDGMENT` sin importar el contexto

2. **Fast path de ACKNOWLEDGMENT bypasea toda la lógica**
   - `dm_agent.py:2590-2594` retorna inmediatamente con respuesta hardcoded
   - NUNCA llega a construir prompt con historial
   - NUNCA llama al LLM

3. **El historial existe pero NO se usa para entender contexto**
   - `follower.last_messages` tiene los 20 últimos mensajes
   - Pero la clasificación de intents no los considera
   - El fast path los ignora completamente

4. **No hay "context-aware intent classification"**
   - Un "Si" después de "¿quieres saber más?" debería ser `INTEREST_SOFT`
   - Un "Si" como primer mensaje debería ser `OTHER`

---

## 5. VALORACIÓN DE INTELIGENCIA (1-10)

| Área | Puntuación | Justificación |
|------|------------|---------------|
| **Memoria conversacional inmediata** | **2/10** | Guarda historial pero no lo usa para entender contexto. Fast paths ignoran historial completamente. |
| **Memoria a largo plazo** | **4/10** | FollowerMemory persiste datos pero no se usa para personalizar. Sabe que hablaste antes pero no QUÉ dijiste. |
| **Uso de conocimiento del creador** | **5/10** | CitationService funciona pero solo para queries explícitas. "Si" no activa búsqueda de citas. |
| **Naturalidad de respuestas** | **4/10** | Respuestas genéricas tipo plantilla. "¿En qué más puedo ayudarte?" es robot. |
| **Avanzar conversación hacia venta** | **3/10** | No detecta que el usuario YA mostró interés. Pierde oportunidades de venta. |
| **Manejo de objeciones** | **6/10** | Tiene handlers específicos para objeciones, pero clasificación es inconsistente. |
| **Personalización según usuario** | **3/10** | Sabe nombre y total de mensajes, pero no adapta respuestas al contexto real. |

### **PUNTUACIÓN GLOBAL: 3.9/10**

---

## 6. RECOMENDACIONES (Ordenadas por Impacto)

### 6.1 CRÍTICO - Implementar Inmediatamente

#### R1: Eliminar Fast Path de ACKNOWLEDGMENT
**Impacto:** Alto | **Esfuerzo:** Bajo

```python
# ANTES (dm_agent.py:2590-2594):
if intent == Intent.ACKNOWLEDGMENT:
    response_text = self._get_fallback_response(Intent.ACKNOWLEDGMENT, lang)
    return response_text

# DESPUÉS:
# Eliminar este fast path completamente
# Dejar que ACKNOWLEDGMENT pase por el flujo normal con contexto
```

#### R2: Context-Aware Intent Classification
**Impacto:** Alto | **Esfuerzo:** Medio

```python
def _classify_with_context(self, message: str, history: List[dict]) -> Intent:
    """Clasifica intent considerando el contexto de la conversación."""

    # Si el mensaje es corto (si, vale, ok) y hay historial
    if len(message) < 20 and history:
        last_bot_msg = None
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                last_bot_msg = msg.get("content", "")
                break

        if last_bot_msg:
            # Si la última respuesta del bot fue una pregunta
            if "?" in last_bot_msg:
                # "Si" después de "¿quieres saber más?" = INTEREST_SOFT
                if any(kw in last_bot_msg.lower() for kw in
                       ["saber más", "te cuento", "te explico", "te interesa"]):
                    return Intent.INTEREST_SOFT
                # "Si" después de "¿quieres comprar?" = INTEREST_STRONG
                if any(kw in last_bot_msg.lower() for kw in
                       ["comprar", "pagar", "link"]):
                    return Intent.INTEREST_STRONG

    # Fallback a clasificación normal
    return self._quick_classify(message)
```

#### R3: Pasar Historial como Conversación Multi-Turn al LLM
**Impacto:** Alto | **Esfuerzo:** Medio

```python
# ANTES:
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt}  # historial como texto
]

# DESPUÉS:
messages = [{"role": "system", "content": system_prompt}]

# Añadir historial como mensajes reales
for msg in conversation_history[-6:]:  # Últimos 6 mensajes
    messages.append({
        "role": msg.get("role"),  # "user" o "assistant"
        "content": msg.get("content")
    })

# Mensaje actual
messages.append({"role": "user", "content": current_message})
```

### 6.2 IMPORTANTE - Implementar Pronto

#### R4: Añadir Instrucciones de Coherencia al System Prompt
**Impacto:** Medio | **Esfuerzo:** Bajo

Añadir al inicio del system prompt:

```
REGLAS DE COHERENCIA CONVERSACIONAL (CRÍTICO):
1. ANTES de responder, LEE la conversación anterior
2. Si el usuario dice "sí", "vale", "ok" → responde a tu ÚLTIMA pregunta
3. Si el usuario dice "ya te dije" → busca en el historial qué dijo
4. NUNCA preguntes algo que el usuario YA respondió
5. Mantén el HILO de la conversación - no cambies de tema abruptamente
6. Si pierdes el contexto, pregunta: "Perdona, ¿me recuerdas de qué estábamos hablando?"
```

#### R5: Incrementar Contexto de Historial
**Impacto:** Medio | **Esfuerzo:** Bajo

```python
# ANTES:
for msg in conversation_history[-4:]:  # Solo 4 mensajes

# DESPUÉS:
for msg in conversation_history[-8:]:  # 8 mensajes (4 intercambios)
```

#### R6: Detectar "Meta-Mensajes" del Usuario
**Impacto:** Medio | **Esfuerzo:** Medio

```python
META_PATTERNS = [
    ("ya te lo dije", "REVIEW_HISTORY"),
    ("revisa el chat", "REVIEW_HISTORY"),
    ("te lo acabo de decir", "REVIEW_HISTORY"),
    ("no me escuchas", "REVIEW_HISTORY"),
    ("lee arriba", "REVIEW_HISTORY"),
]

def detect_meta_message(message: str) -> Optional[str]:
    msg_lower = message.lower()
    for pattern, action in META_PATTERNS:
        if pattern in msg_lower:
            return action
    return None
```

### 6.3 MEJORAS - Implementar Después

#### R7: Cache de Contexto de Conversación
Cachear el "resumen" de la conversación para acceso rápido sin reconstruir.

#### R8: Feedback Loop de Calidad
Detectar cuando el usuario expresa frustración ("no me entiendes", "olvídalo") y loguear para análisis.

#### R9: Usar LLM para Resumir Conversación Larga
Si hay más de 10 mensajes, usar LLM para generar un resumen que quepa en el contexto.

---

## 7. ARCHIVOS A MODIFICAR

| Prioridad | Archivo | Cambio |
|-----------|---------|--------|
| 1 | `backend/core/dm_agent.py` | Eliminar fast path ACKNOWLEDGMENT (línea 2590) |
| 2 | `backend/core/dm_agent.py` | Añadir context-aware classification (línea 1220) |
| 3 | `backend/core/dm_agent.py` | Pasar historial como multi-turn (línea 2910) |
| 4 | `backend/core/dm_agent.py` | Añadir coherence rules al system prompt (línea 2053) |
| 5 | `backend/core/dm_agent.py` | Incrementar historial a 8 mensajes (línea 2150) |

---

## 8. CONCLUSIÓN

El sistema de Clonnect tiene una arquitectura sólida con componentes bien diseñados (ToneProfile, CitationService, RAG), pero **la integración de estos componentes en el flujo de respuesta tiene fallos críticos**.

El problema NO es que falte memoria - el sistema GUARDA todo. El problema es que:

1. **Los fast paths ignoran el historial** para mensajes simples
2. **El clasificador de intents no tiene contexto** de la conversación
3. **El historial se pasa como texto plano** en lugar de conversación real

Con las correcciones propuestas (especialmente R1, R2 y R3), el bot debería poder:
- Entender que "Si" significa "sí, cuéntame más sobre lo que preguntaste"
- Recordar qué dijo el usuario cuando dice "ya te lo dije"
- Mantener el hilo de la conversación sin bucles

**Tiempo estimado de implementación:** 2-3 días para cambios críticos.

---

*Informe generado por Claude Code - Auditoría automatizada del sistema de IA conversacional*
