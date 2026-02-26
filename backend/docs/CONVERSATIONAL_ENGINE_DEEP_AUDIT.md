# CLONNECT — Auditoría Profunda del Motor Conversacional
*Fecha: 2026-02-26*

---

## RESUMEN: ¿Qué nivel de inteligencia tiene el bot?

- **Pipeline de 5 fases reales con paralelismo**: Las fases de memoria y contexto ejecutan 4 operaciones de I/O en paralelo (follower memory, DNA context, conversation state, raw DNA), reduciendo latencia de ~3.8s a ~1.2s. Esto no es teoría — está cronometrado en los logs con `[TIMING]`.
- **RAG híbrido con 3 capas**: Búsqueda semántica (OpenAI embeddings + pgvector) + BM25 lexical (pesos 0.7/0.3) + cross-encoder reranker. El cache de RAG dura 300 segundos por query+creator. Para Stefano, esto significa que "precio del coaching personalizado" y "cuánto cuesta el 1:1" obtienen el mismo resultado del cache si se hacen en < 5 minutos.
- **RelationshipDNA por follower**: Por cada persona que le escribe a Stefano, el sistema mantiene una ficha con: tipo de relación (FAMILIA, AMIGO, CLIENTE, DESCONOCIDO), trust score (0.0-1.0), vocabulario específico que usa esa persona, emojis recurrentes, temas recurrentes, y ejemplos dorados de intercambios pasados.
- **AutoLearning real**: Cuando Stefano edita una respuesta del bot, un LLM analiza la diferencia (bot vs. humano) y extrae una regla como `{"pattern": "shorten_response", "rule_text": "...", "example_bad": "...", "example_good": "..."}`. Esta regla se inyecta en futuros prompts. PERO: está desactivado por defecto (`ENABLE_AUTOLEARNING=false`).
- **Detección de amigos/familia con supresión de ventas**: Si el bot detecta que la persona es FAMILIA o INTIMA (via RelationshipTypeDetector), suprime completamente el comportamiento de adquisición. Stefano no recibirá un CTA de su madre preguntando "¿cuánto cuesta tu programa?"
- **Anti-alucinación multicapa**: 9 fixes secuenciales + guardrails de precios (tolerancia ±1€) + validación de URLs contra whitelist de dominios autorizados. Los links hallucinated se reemplazan por `[enlace removido]`.
- **La Memory Engine más sofisticada está desactivada**: `ENABLE_MEMORY_ENGINE=false`. El sistema tiene arquitectura para extracción de hechos con embeddings pgvector, decay Ebbinghaus, resolución de conflictos, y borrado GDPR — pero no está en producción.

---

## BLOQUE 1: EL MOTOR CONVERSACIONAL

### Cómo funciona el pipeline completo de un mensaje

El archivo principal es `dm_agent_v2.py` que actúa como hub de re-exportación. La implementación real vive en `core/dm/agent.py` y se ejecuta en 5 fases secuenciales:

**FASE 1 — Detección** (`core/dm/phases/detection.py`)

Antes de cualquier LLM, el pipeline ejecuta 4 comprobaciones de seguridad en orden:

1. **Sensitive Content Detection**: Si `ENABLE_SENSITIVE_DETECTION=true` (default), ejecuta `detect_sensitive_content(message)`. Si la confianza supera `AGENT_THRESHOLDS.sensitive_confidence` (0.7), registra la categoría. Si además supera `AGENT_THRESHOLDS.sensitive_escalation` (0.85), retorna directamente con `get_crisis_resources(language="es")` — sin LLM, sin pasar por el resto del pipeline.

2. **Frustration Detection**: Con `ENABLE_FRUSTRATION_DETECTION=true`, llama a `frustration_detector.analyze_message(message, sender_id, prev_messages)`. Si el nivel supera 0.3, lo registra en `cognitive_metadata`. En Fase 4, si supera 0.5, inyecta en el prompt: `"⚠️ NOTA: El usuario parece frustrado (nivel: X%). Responde con empatía..."`.

3. **Pool Response (fast path)**: Para mensajes de ≤ 80 caracteres que no mencionan ningún producto por nombre, intenta `response_variator.try_pool_response()`. Si la confianza supera `AGENT_THRESHOLDS.pool_confidence` (0.8), retorna la respuesta sin llamar al LLM. Con 30% de probabilidad, intenta multi-bubble (varias burbujas separadas). Este fast path elimina el costo de LLM para saludos comunes.

4. **Edge Case Detection**: `edge_case_handler.detect(message)` detecta casos extremos que requieren escalación y retorna con `suggested_response` preconfigurado.

**FASE 2-3 — Memoria y Contexto** (`core/dm/phases/context.py`)

Esta fase ejecuta primero la clasificación de intent (síncrona y rápida), luego lanza 4 operaciones en paralelo con `asyncio.gather()`:

```python
follower, dna_context, (state_context, state_meta), raw_dna = await asyncio.gather(
    agent.memory_store.get_or_create(creator_id, sender_id, username),
    build_context_prompt(creator_id, sender_id),   # DNA + PostCtx (2 queries)
    _load_conv_state(),                             # Conversation phase (1 query)
    asyncio.to_thread(_get_raw_dna, creator_id, sender_id),
)
```

Luego (secuencialmente por depender de los resultados anteriores):
- Si `ENABLE_MEMORY_ENGINE=false` (default): sin recall semántico de hechos
- Si `ENABLE_COMMITMENT_TRACKING=true` (default): carga compromisos pendientes del bot con ese lead
- Auto-create seed DNA si el follower tiene ≥ 2 mensajes y no hay DNA previo
- RAG: saltado para intents `{greeting, farewell, thanks, saludo, despedida}`. Para el resto, si `ENABLE_QUERY_EXPANSION=true`, expande la query (max 2 expansiones) antes de buscar. Busca con `top_k=3` (configurable en `AgentConfig.rag_top_k`).
- Detección de relación amigo/familia para suprimir comportamiento de ventas
- Construcción del prompt combinado en orden de prioridad (12 capas)

**FASE 4 — Generación LLM** (`core/dm/phases/generation.py`)

Determina estrategia de respuesta, carga learning rules/preference profile/gold examples (todos `false` por defecto), construye el prompt final, y llama a `generate_dm_response()`:

- **Primario**: Gemini 2.5 Flash-Lite (vía HTTP directo sin SDK, con circuit breaker: 2 fallos → 120s de cooldown)
- **Fallback**: GPT-4o-mini
- **Emergencia**: `llm_service.generate()` (cualquier proveedor configurado)
- `max_tokens=150` por defecto (ajustable por el ECHO Relationship Adapter)
- `temperature=0.7` por defecto (ajustable por el ECHO Relationship Adapter)
- Si `ENABLE_BEST_OF_N=false` (default): llamada única. Si true y en modo copilot: 3 candidatos en paralelo a T=[0.2, 0.7, 1.4]
- Si `ENABLE_SELF_CONSISTENCY=false` (default): sin validación de consistencia

**FASE 5 — Post-procesamiento** (`core/dm/phases/postprocessing.py`)

Aplicado secuencialmente al texto generado:

1. Detección de loop repetitivo: compara los primeros 50 chars con los últimos 3 mensajes del bot. Si hay match exacto, reemplaza por `"Contame más"`.
2. `validate_prices()` + `validate_links()` — anti-hallucination
3. `apply_all_response_fixes()` — 9 fixes secuenciales
4. Tone enforcement desde calibration (emoji rate, exclamation rate)
5. `process_questions()` — question remover
6. `get_reflexion_engine().analyze_response()` — análisis de calidad (no re-genera, solo registra)
7. Guardrails: precios, URLs, hallucination patterns, longitud > 2000 chars
8. `enforce_length()` — longitud contextual
9. `instagram_service.format_message()` — formato Instagram
10. Inyección de payment link si intent es `purchase_intent` y el producto está mencionado
11. Calcular nuevo `lead_stage` con `_update_lead_score()`
12. Tareas en background: guardar memoria, DNA triggers, nurturing auto-schedule, commitment tracking, memory extraction, escalation check

---

### Las estrategias de respuesta (árbol de decisión completo)

Implementado en `core/dm/strategy.py`. La función `_determine_response_strategy()` evalúa condiciones en orden de prioridad:

| Prioridad | Condición | Estrategia devuelta |
|-----------|-----------|---------------------|
| 1 | `relationship_type in ("FAMILIA", "INTIMA")` | **PERSONAL**: Responde con cariño. NUNCA vendas. |
| 2 | `is_friend == True` | **PERSONAL**: Amigo/a, responde relajado. No vendas. |
| 3 | Mensaje contiene help signals: `["ayuda", "problema", "no funciona", "no puedo", "error", "cómo", "como hago", "necesito", "urgente", "no me deja", "no entiendo", "explícame", "qué hago"]` | **AYUDA**: Responde DIRECTAMENTE. NO saludes genéricamente. |
| 4 | `intent_value in ("purchase", "pricing", "product_info")` | **VENTA**: Da información concreta + CTA suave. |
| 5 | `is_first_message AND ("?" in message OR help_signals)` | **BIENVENIDA + AYUDA**: Saluda brevemente + responde necesidad. |
| 6 | `is_first_message` | **BIENVENIDA**: Saluda + pregunta en qué ayudar. No genérico largo. |
| 7 | `lead_stage == "fantasma"` | **REACTIVACIÓN**: Muestra alegría. No vendas agresivo. |
| Default | Ninguna condición | Conversación natural (string vacío, sin instrucción adicional) |

La estrategia se inyecta directamente en el prompt antes del mensaje del usuario, nunca después. El resultado (primeras palabras hasta el primer punto) se registra en `cognitive_metadata["response_strategy"]`.

---

### Clasificación de intents (lista completa)

El clasificador de intents es `services/intent_service.py`. Los intents son un enum `Intent` con los siguientes valores (visibles en el código via `NON_CACHEABLE_INTENTS` y el dashboard):

| Intent | Descripción | Ejemplos de señales | Acción del bot |
|--------|-------------|---------------------|----------------|
| `greeting` / `saludo` | Saludo inicial | "hola", "buenos días" | RAG saltado, pool response activo |
| `farewell` / `despedida` | Despedida | "adiós", "hasta luego" | RAG saltado |
| `thanks` | Agradecimiento | "gracias", "te lo agradezco" | RAG saltado |
| `purchase_intent` / `purchase` | Intención de compra clara | "quiero comprar", "cómo pago" | Payment link inyectado automáticamente; score +0.85 |
| `interest_strong` | Interés fuerte | "me interesa mucho", "quiero apuntarme" | Escalación notificada si score ≥ 0.8; score set a 0.75 |
| `interest_soft` | Interés suave | "cuéntame más", "qué es esto" | Score set a 0.50 |
| `question_product` | Pregunta de producto | "qué incluye", "cómo funciona el programa" | RAG activo con top_k=3 |
| `pricing` | Pregunta de precio | "cuánto cuesta", "precio" | RAG activo; Reflexion verifica que haya precio en respuesta |
| `objection_price` | Objeción por precio | "es muy caro", "no puedo pagarlo" | No cacheable; score -0.10 |
| `objection_time` | Objeción por tiempo | "no tengo tiempo ahora" | No cacheable |
| `objection_doubt` | Duda sobre el producto | "no sé si funcionará" | No cacheable |
| `objection_later` | Aplazamiento | "después", "ahora no" | No cacheable |
| `objection_works` | Duda si funciona | "¿de verdad funciona?" | No cacheable |
| `objection_not_for_me` | "No es para mí" | "no creo que sea para mí" | No cacheable |
| `escalation` | Pide hablar con humano | "quiero hablar con una persona" | Notificación Telegram al creador; no cacheable |
| `support` | Problema técnico | "no me llega el acceso", "falla" | Notificación Telegram; no cacheable |
| `feedback_negative` | Feedback negativo | "estoy decepcionado", "no me gusta" | Notificación Telegram |
| `other` | No clasificado | Fallback | No cacheable; siempre regenera |

---

### Detección de frustración

Implementado en `frustration_detector` (módulo separado, instanciado en el agente). El sistema analiza el mensaje actual más los mensajes previos del usuario (`prev_messages` del historial).

**Umbrales exactos:**
- `> 0.3` → Se registra en `cognitive_metadata["frustration_level"]` y se loguea como `INFO`
- `> 0.5` → Se inyecta en el prompt de la Fase 4: `"⚠️ NOTA: El usuario parece frustrado (nivel: X%). Responde con empatía y ofrece ayuda concreta."`

El detector de frustración es un módulo externo (`agent.frustration_detector`) con método `analyze_message(message, sender_id, prev_messages)` que retorna `(frustration_signals, frustration_level)`. La implementación interna del detector no está en los archivos auditados directamente, pero los umbrales de activación sí están en `detection.py`.

**Ejemplo Stefano**: Si un seguidor de Stefano escribe "ya te he preguntado tres veces y nadie me responde", el nivel de frustración superaría 0.5 y el LLM recibiría instrucción explícita de responder con empatía prioritariamente.

---

### Chain of Thought

Implementado en `core/reasoning/chain_of_thought.py`. Es un módulo standalone que NO está integrado en el pipeline principal de DM (Fases 1-5). Existe como clase `ChainOfThoughtReasoner` con singleton `get_chain_of_thought_reasoner()`.

**Cuándo se activa** (método `_is_complex_query()`):
- Keywords de salud: `["lesión", "enfermedad", "médico", "embarazo", "diabetes", "alergia", "dolor", "síntoma", "tratamiento", "medicamento", ...]`
- Keywords de producto complejo: `["comparar", "diferencia", "mejor opción", "qué incluye", "requisitos"]`
- Longitud ≥ `MIN_WORDS_FOR_COMPLEX = 50` palabras

**Qué hace**:
1. Determina el tipo: `"health"`, `"product"`, o `"general"`
2. Construye un prompt con secciones `[RAZONAMIENTO]` y `[RESPUESTA]`
3. Para salud: añade disclaimer si la respuesta no incluye "consulta" o "médico"
4. Temperatura: 0.5 (más determinista que el DM estándar)
5. Max tokens: 500

**Confianza devuelta**: 0.85 si encontró pasos de razonamiento, 0.6 si no.

**Estado real**: El módulo está completo y funcional, pero la integración con el pipeline DM principal no se observa en el código auditado. Está disponible como herramienta pero no se activa automáticamente en cada mensaje.

---

### Best-of-N

Implementado en `core/best_of_n.py`. Controlado por `ENABLE_BEST_OF_N=false` (default desactivado). Solo activo cuando el creador tiene copilot mode habilitado.

**Configuración exacta:**
- **N = 3 candidatos** a temperaturas `[0.2, 0.7, 1.4]`
- Cada temperatura tiene un style hint diferente:
  - T=0.2: `"[ESTILO: responde de forma breve y directa, máximo 1-2 frases cortas]"`
  - T=0.7: Sin hint (respuesta balanceada)
  - T=1.4: `"[ESTILO: responde de forma más elaborada, cálida y expresiva, 3-4 frases con personalidad]"`
- Timeout global: `BEST_OF_N_TIMEOUT=12` segundos
- Los 3 candidatos se generan en **paralelo** con `asyncio.gather()`

**Criterio de selección**: Cada candidato se puntúa con `calculate_confidence(intent, response_text, response_type, creator_id)`. Se ordena por confianza descendente. El mejor (rank=1) es el seleccionado.

**Persistencia**: Los candidatos se serializan en `msg_metadata["best_of_n"]` para auditoría, incluyendo temperatura, confianza, modelo y latencia de cada uno.

---

### Guardrails (lista completa)

Implementados en `core/guardrails.py` (clase `ResponseGuardrail`) y también en `core/output_validator.py` (más detallado). Activados por `ENABLE_GUARDRAILS=true` (default).

| Guardrail | Qué detecta | Qué hace cuando se activa |
|-----------|-------------|--------------------------|
| **Precio hallucinated** | Precios en respuesta (regex: `\d+€`, `€\d+`, `\d+ euros`, `$\d+`) que no coinciden con ningún producto conocido (tolerancia ±1€) | Registra warning; si hay respuesta corregida la aplica; si `should_escalate=True`, usa fallback genérico |
| **URL no autorizada** | URLs en respuesta que no pertenecen a dominios whitelist | Reemplaza URL por `[enlace removido]`; whitelist incluye: stripe.com, hotmart.com, gumroad.com, calendly.com, cal.com, instagram.com, wa.me, t.me, youtube.com, revolut.me, paypal.com, clonnectapp.com + dominios extraídos de productos del creador |
| **Promise to call back** | Regex: `te?\s+llamo\s+en\s+\d+\s*(minutos?|horas?)` | Marca como `Potential hallucination` |
| **Promise to email now** | Regex: `te?\s+env[íi]o?\s+(un\s+)?email\s+ahora` | Marca como `Potential hallucination` |
| **Physical address** | Regex: `nuestra?\s+direcci[oó]n\s+(f[íi]sica|postal)\s*:` | Marca como `Potential hallucination` |
| **Off-topic opinion** | Mensajes sobre bitcoin, crypto, política, religión, aborto, drogas, armas, guerra (regex con word boundaries) donde el bot da opinión en lugar de redirigir | Reemplaza respuesta por `"Ese tema está fuera de mi área de especialidad. ¿Te cuento en qué sí puedo ayudarte? 😊"` |
| **Respuesta excesivamente larga** | `len(response) > 2000` | Registra issue |
| **Producto desconocido** | Bot menciona nombre de producto no reconocido en catálogo (soft check) | Warning (no falla validación) |
| **Missing booking link** | Intent fuerte + mención de "reservar/agendar" + sin URL en respuesta | Auto-añade booking link del creador |
| **Missing payment link** | Purchase intent fuerte + sin URL | Auto-añade payment link del producto destacado |

---

### Reflexion Engine

Implementado en `core/reflexion_engine.py`. Es un análisis **rule-based** (sin LLM), activado por `ENABLE_REFLEXION=true` (default).

**Umbrales exactos:**
- `MAX_RESPONSE_LENGTH = 300` chars (para preguntas simples)
- `MIN_RESPONSE_LENGTH = 20` chars
- `IDEAL_RESPONSE_LENGTH = 150` chars
- Repetición: > 60% overlap de palabras de 4+ chars con respuestas previas (compara hasta las últimas 5)

**5 checks que realiza:**
1. **Longitud**: `< 20` chars → "Respuesta demasiado corta". `> 300` chars con pregunta de usuario `< 50` chars → "Respuesta muy larga para pregunta simple"
2. **Pregunta no respondida**: Si usuario preguntó y la respuesta contiene ≥ 2 signos `?` sin `!` → "Posible evasión"
3. **Repetición**: Overlap > 60% con últimas 5 respuestas del bot → "Alta repetición"
4. **Apropiado para la fase**: En fase `inicio` no mencionar precios; en `propuesta` incluir precio si habla de producto; en `cierre` incluir CTA o link
5. **Precio preguntado no respondido**: Si usuario preguntó precio y respuesta no contiene `\d+€` → issue

**Severidad**: 1 issue → `low`, 2 issues → `medium`, ≥ 3 issues → `high`.

**Estado actual**: Solo registra issues en `cognitive_metadata["reflexion_issues"]`. No re-genera la respuesta automáticamente.

---

### Control de calidad de respuesta

**9 response fixes** aplicados en `apply_all_response_fixes()` en este orden:
1. **FIX 1**: `fix_price_typo()` — `"297?"` → `"297€"` (regex: `\d+\?\s`)
2. **FIX 3**: `fix_broken_links()` — `"://www."` → `"https://www."`
3. **FIX 4**: `fix_identity_claim()` — `"Soy Stefano"` → `"Soy el asistente de Stefano"` (para que el bot no se haga pasar por el creador)
4. **FIX 5**: `clean_raw_ctas()` — Elimina CTAs crudos en MAYÚSCULAS: `QUIERO SER PARTE`, `COMPRA AHORA`, `INSCRÍBETE YA`, `LINK EN MI BIO`, `SWIPE UP`, etc.
5. **FIX 6**: `hide_technical_errors()` — Oculta `ERROR:`, `Exception:`, `Traceback`, `NoneType`, etc.
6. **FIX 7**: `apply_blacklist_filter()` — Elimina frases de lista negra de la extracción de personalidad del creador
7. **FIX 8**: `apply_emoji_limit()` — Limita emojis según `max_emojis_per_message` de la calibración
8. **FIX 9**: `remove_catchphrases()` — Elimina muletillas LLM: "¿Qué te llamó la atención?", "¿Qué te trajo por acá?", "Contame qué te trae por acá", "Contame de lo que comparto"

**Timing service**: `min_delay=2.0s`, `max_delay=30.0s`, calcula delay como `think_time(1-3s) + reading_time(len/200) + typing_time(len/50)` con ±20% variación aleatoria. Horario activo: 8:00-23:00 Europe/Madrid. Fuera de horario: 10% de probabilidad de responder igualmente.

**Send Guard** (`core/send_guard.py`): ÚLTIMO control antes de enviar. Un mensaje solo se envía si:
1. `approved=True` (creator aprobó en dashboard), O
2. `creator.copilot_mode=False AND creator.autopilot_premium_enabled=True`

Si ninguna condición se cumple, lanza `SendBlocked` exception con log `CRITICAL`.

---

### Cuándo escala a humano

El sistema notifica al creador vía Telegram en 4 casos (`check_and_notify_escalation()`):

1. **`intent == "escalation"`**: Usuario pidió explícitamente hablar con una persona → `"Usuario solicitó hablar con una persona real"`
2. **`intent == "support"`**: Usuario reportó problema técnico → `"Usuario reportó un problema o necesita soporte"`
3. **`intent == "feedback_negative"`**: Feedback negativo → `"Usuario expresó insatisfacción o feedback negativo"`
4. **HOT LEAD**: `purchase_intent_score ≥ 0.8 AND intent == "interest_strong"` → `"🔥 HOT LEAD - Intención de compra: XX%"`

La notificación incluye: creator_id, follower_username, razón, último mensaje (máx 500 chars), resumen de conversación, score de purchase intent, total de mensajes, y productos discutidos.

---

## BLOQUE 2: SISTEMA DE MEMORIA

### Tipos de memoria (lista completa)

| Tipo | Qué guarda | De dónde viene | TTL / Límite | Dónde se almacena | Cuando se usa |
|------|-----------|----------------|-------------|-------------------|---------------|
| **Conversation Buffer** | Últimos 20 mensajes (user+assistant) con timestamps y facts | `sync_post_response()` después de cada turno | 20 mensajes en memoria; persiste como JSON | Fichero JSON en `data/followers/{creator_id}/{follower_id}.json` | Cada mensaje — forma el historial del LLM |
| **FollowerMemory** | Perfil completo por follower (ver sección siguiente) | Creado en primer contacto, actualizado en cada turno | Indefinido (archivo JSON) | JSON + (futuro) PostgreSQL | Cargado en Fase 2 para contexto del LLM |
| **RelationshipDNA** | DNA de la relación específica creator-follower | Auto-creado desde msg≥2; LLM análisis a msg≥5 | Indefinido (PostgreSQL) | Tabla `relationship_dna` | Cargado en Fase 2 para personalizar prompt |
| **Conversation State** | Fase conversacional (inicio, propuesta, cierre, etc.) | `get_state_manager()` por turno | Sin TTL explícito | PostgreSQL | Cargado en Fase 2 para contexto |
| **RAG Cache** | Resultados de búsqueda semántica para una query | `semantic_rag.search()` | `RAG_CACHE_TTL = 300s` (5 min) | In-memory dict por proceso | Cada búsqueda RAG — evita re-embedding |
| **Copilot Mode Cache** | Si el creator tiene copilot mode activo | DB query `creator.copilot_mode` | `_CACHE_TTL = 60s` | In-memory dict en `CopilotService` | Antes de cada envío |
| **Memory Engine** (DESACTIVADO) | Hechos extraídos por LLM con embeddings | LLM post-respuesta (fire-and-forget) | `DECAY_HALF_LIFE_BASE_DAYS = 30 días`; threshold `DECAY_THRESHOLD = 0.1` | Tabla `lead_memories` (pgvector) | NO activo — `ENABLE_MEMORY_ENGINE=false` |

---

### Memoria por follower (perfil individual)

La clase `FollowerMemory` (en `core/memory.py`, deprecada) y el equivalente activo en `core/dm/agent.py` guardan estos campos:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `follower_id` | str | ID de plataforma (Instagram user ID) |
| `creator_id` | str | Creator al que pertenece |
| `username` | str | @username de Instagram |
| `name` | str | Nombre real si se conoce |
| `first_contact` | str (ISO) | Primera vez que escribió |
| `last_contact` | str (ISO) | Última interacción |
| `total_messages` | int | Total de mensajes intercambiados |
| `interests` | List[str] | Intereses detectados (máx 5 usados en prompt) |
| `products_discussed` | List[str] | Productos mencionados en conversación (máx 5) |
| `objections_raised` | List[str] | Objeciones expresadas (máx 5) |
| `purchase_intent_score` | float | Score 0.0-1.0 de intención de compra |
| `engagement_score` | float | `min(1.0, total_messages / 20)` |
| `is_lead` | bool | True si tiene intent strong al menos una vez |
| `is_customer` | bool | True si ha comprado |
| `needs_followup` | bool | Flag manual de seguimiento |
| `preferred_language` | str | Idioma detectado (default: "es") |
| `conversation_summary` | str | Resumen textual (hasta 200 chars en prompt) |
| `last_messages` | List[Dict] | Últimos 20 mensajes con role, content, timestamp, y facts |

Los `facts` por mensaje son uno o más de: `PRICE_GIVEN`, `LINK_SHARED`, `PRODUCT_EXPLAINED`, `OBJECTION_RAISED`, `INTEREST_EXPRESSED`, `APPOINTMENT_MENTIONED`, `CONTACT_SHARED`, `QUESTION_ASKED`, `NAME_USED`.

---

### Memoria de conversación (estado entre mensajes)

El `get_state_manager()` gestiona el estado de fase de conversación. Las fases existen como enum (`phase.value`) e incluyen: `inicio`, `propuesta`, `cierre`, y posiblemente otras. Se carga desde PostgreSQL en Fase 2.

El método `build_enhanced_prompt(conv_state)` convierte el estado en texto de contexto que se inyecta en el prompt del sistema.

**Historial de mensajes**: El agente carga los últimos mensajes del follower con `_get_history_from_follower(follower)` — estos son los `last_messages` del FollowerMemory (máx 20). Este es el historial que ve el LLM en cada turno.

---

### RelationshipDNA

La tabla `relationship_dna` (PostgreSQL) almacena el DNA específico de cada relación creator-follower:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `relationship_type` | String(50) | `FAMILIA`, `INTIMA`, `AMISTAD_CERCANA`, `amigo`, `DESCONOCIDO`, etc. |
| `trust_score` | Float | Confianza 0.0-1.0 |
| `depth_level` | Integer | Profundidad de relación 0-N |
| `vocabulary_uses` | JSON (list) | Palabras/expresiones que usa esta persona |
| `vocabulary_avoids` | JSON (list) | Palabras que evitar con esta persona |
| `emojis` | JSON (list) | Emojis recurrentes en esta relación |
| `avg_message_length` | Integer | Longitud promedio de mensajes |
| `questions_frequency` | Float | Con qué frecuencia hace preguntas |
| `multi_message_frequency` | Float | Con qué frecuencia envía múltiples mensajes seguidos |
| `tone_description` | Text | Descripción textual del tono de la relación |
| `recurring_topics` | JSON (list) | Temas que aparecen repetidamente |
| `private_references` | JSON (list) | Referencias privadas entre ellos |
| `bot_instructions` | Text | Instrucciones específicas para el bot con este lead |
| `golden_examples` | JSON (list) | Ejemplos de respuestas ideales pasadas |
| `total_messages_analyzed` | Integer | Mensajes analizados para construir este DNA |
| `last_analyzed_at` | DateTime | Última actualización del análisis |

**Cómo se construye**:
- A partir de msg ≥ 2 y sin DNA previo → `_create_seed_dna()` async (confianza inicial = `det_confidence × 0.3`)
- A partir de msg ≥ 5 con seed DNA → `triggers.schedule_async_update()` con los últimos 30 mensajes
- Full analysis: `RelationshipAnalyzer().analyze()` → LLM extrae tipo, trust, vocabulario, tono, temas, instrucciones, golden examples

**Cómo se usa**: Se inyecta en el prompt como `dna_context` (post Fase 2) y como `bot_instructions` específicas para ese lead en Fase 4.

---

### Compromisos y follow-ups

El **ECHO Engine** (Sprint 4) incluye un `CommitmentTracker`:
- **Detección**: Después de cada respuesta del bot, `tracker.detect_and_store(response_text, creator_id, lead_id)` analiza el texto buscando promesas implícitas (regex o LLM — implementación en `services/commitment_tracker.py` no auditada completamente).
- **Uso**: Al inicio del siguiente turno con ese lead, `tracker.get_pending_text(sender_id)` carga los compromisos pendientes que se inyectan en el `relational_block` del prompt.
- **Estado**: Activo por defecto (`ENABLE_COMMITMENT_TRACKING=true`).

**Ejemplo Stefano**: Si el bot escribió "te mando más info sobre el programa mañana", eso quedará registrado como commitment pendiente y en el siguiente mensaje de ese follower, el bot sabrá que tiene una promesa pendiente.

**Nurturing auto-schedule**: Después de ciertos intents, el sistema crea follow-ups automáticos via `should_schedule_nurturing(intent, has_purchased, creator_id)` → `manager.schedule_followup(...)`. Los tipos de secuencia dependen del intent detectado.

---

### Límites de memoria

| Parámetro | Valor exacto | Fuente |
|-----------|-------------|--------|
| Historial en memoria (FollowerMemory) | 20 mensajes (user+assistant) | `follower.last_messages[-20:]` en `sync_post_response()` |
| Intereses en prompt | 5 máximo | `follower.interests[:5]` en context.py |
| Objeciones en prompt | 5 máximo | `follower.objections_raised[:5]` |
| Productos discutidos en prompt | 5 máximo | `follower.products_discussed[:5]` |
| Resumen de conversación en prompt | 200 chars | `follower.conversation_summary[:200]` |
| Mensajes analizados para DNA | 30 últimos | `follower.last_messages[-30:]` en DNA trigger |
| Cache de agente (instancia cargada) | 600 segundos | `AGENT_CACHE_TTL=600` |
| Cache de copilot mode | 60 segundos | `_CACHE_TTL=60` en CopilotService |
| Cache de RAG | 300 segundos (5 min) | `RAG_CACHE_TTL=300` |
| Contexto total del sistema (prompt) | ~48.000 chars máx | `AGENT_MAX_CONTEXT_CHARS=48000` |
| Hechos de Memory Engine en prompt | 10 máximo | `MEMORY_MAX_FACTS_IN_PROMPT=10` |
| Hechos por extracción LLM | 5 máximo | `MEMORY_MAX_FACTS_PER_EXTRACTION=5` |
| Half-life decay de memoria | 30 días | `MEMORY_DECAY_HALF_LIFE_DAYS=30` |
| Pool de conexiones DB por worker | 5 base + 5 overflow | `pool_size=5, max_overflow=5` en database.py |

---

## BLOQUE 3: PERSONALIZACIÓN POR CREADOR Y POR FOLLOWER

### El perfil de tono del creador

La clase `ToneProfile` en `ingestion/tone_analyzer.py` captura todos estos aspectos del creador:

| Dimensión | Valores posibles | Descripción |
|-----------|-----------------|-------------|
| `formality` | muy_formal, formal, neutral, informal, muy_informal | Nivel de formalidad |
| `energy` | muy_alta, alta, media, baja, muy_baja | Energía en la comunicación |
| `warmth` | muy_calido, calido, neutral, distante, muy_distante | Calidez / cercanía |
| `directness` | muy_directa, directa, media, indirecta, muy_indirecta | Qué tan directo es |
| `signature_phrases` | List[str] | Frases exactas que usa: "vamos crack", "a tope" |
| `common_greetings` | List[str] | Saludos habituales: "Hey!", "Hola guapo/a" |
| `common_closings` | List[str] | Despedidas: "Un abrazo", "Nos vemos" |
| `filler_words` | List[str] (max 6 en prompt) | Muletillas: "pues", "bueno", "mira" |
| `uses_emojis` | bool | Si usa emojis |
| `favorite_emojis` | List[str] | Los emojis que más usa |
| `emoji_frequency` | ninguna, baja, media, alta, muy_alta | Frecuencia de emojis |
| `uses_caps_emphasis` | bool | Si usa MAYÚSCULAS para énfasis |
| `uses_ellipsis` | bool | Si usa puntos suspensivos... |
| `average_message_length` | muy_corta, corta, media, larga, muy_larga | Longitud media de mensajes |
| `uses_line_breaks` | bool | Si separa ideas en párrafos |
| `primary_language` | es, en, pt, fr, de, it | Idioma principal |
| `dialect` | neutral, rioplatense, mexicano, español | Dialecto detectado |
| `uses_anglicisms` | bool | "cool", "random", "flow" |
| `regional_expressions` | List[str] (max 4) | Expresiones regionales |
| `asks_questions` | bool | Si pregunta al seguidor habitualmente |
| `uses_humor` | bool | Si usa humor |
| `main_topics` | List[str] | Temas principales del contenido |
| `values_expressed` | List[str] | Valores que transmite |

**Generación de la sección de prompt**: `to_system_prompt_section()` produce instrucciones compactas como:
- Para dialecto `rioplatense`: `"VOSEO OBLIGATORIO: vos/tenés/podés/querés/contame/escribime/agendá. PROHIBIDO: tú/tienes/puedes/quieres/cuéntame/escríbeme/usted."`
- Para Stefano (Barcelona, perfil fitness): probablemente `dialect="español"` con tuteo natural

El voseo también puede aplicarse post-generación via `apply_voseo()` en `text_utils.py`, que convierte 20 patrones específicos (tú→vos, tienes→tenés, puedes→podés, cuéntame→contame, etc.).

---

### Cómo adapta la respuesta según el lead stage

El sistema V3 usa 6 categorías flat con comportamientos diferenciados:

| Status | Score | Estrategia del bot | Ejemplo (Stefano) |
|--------|-------|-------------------|-------------------|
| `cliente` | 75-100 | Tratamiento premium, no vender lo que ya compró | "¡Santi! ¿Cómo va el programa?" |
| `caliente` | 45-85 | Info concreta + CTA suave; payment link si purchase_intent | "El coaching 1:1 incluye... [link pago]" |
| `colaborador` | 30-60 | Respuesta profesional, explorar la propuesta | "Cuéntame más sobre el proyecto que tienes en mente" |
| `amigo` | 15-45 | Sin ventas, conversación natural | "Jaja, qué bueno verte por aquí, ¿qué cuentas?" |
| `nuevo` | 0-25 | Bienvenida + calificación suave | "¡Hola! Cuéntame, ¿en qué puedo ayudarte?" |
| `frío` | 0-10 | Estrategia REACTIVACIÓN | "¡Qué alegría verte de nuevo! Hacía tiempo..." |

El `current_stage` determina también el tono del `relational_block` generado por el ECHO Relationship Adapter, que ajusta `llm_max_tokens` y `llm_temperature` dinámicamente.

---

### Qué sabe de cada follower individual

**Datos explícitos** (del Lead en PostgreSQL):
- `username`, `full_name`, `profile_pic_url` (CDN URL de Instagram)
- `status` (6 categorías), `score` (0-100), `purchase_intent` (0.0-1.0)
- `email` (capturado si lo comparte), `phone` (ídem)
- `notes` (texto libre del creador), `tags` (array: "vip", "interested", "price_sensitive")
- `deal_value` (valor potencial en euros), `source` ("instagram_dm", "story_reply", "ad_click")
- `first_contact_at`, `last_contact_at`, `score_updated_at`

**Datos inferidos** (del FollowerMemory JSON):
- `interests` — detectados de temas que menciona
- `products_discussed` — qué productos ha preguntado
- `objections_raised` — qué objeciones ha expresado
- `purchase_intent_score` — calculado turno a turno
- `conversation_summary` — resumen generado
- `preferred_language` — detectado del idioma que usa

**Datos de RelationshipDNA** (PostgreSQL):
- Tipo de relación con ese creador específico
- Trust score individual
- Vocabulario específico de esa relación
- Emojis de esa relación
- Temas recurrentes entre ellos
- Instrucciones específicas del bot para ese lead
- Golden examples (respuestas ideales pasadas)

**Datos del LeadIntelligence** (PostgreSQL — tabla separada):
- `engagement_score`, `intent_score`, `fit_score`, `urgency_score`, `overall_score`
- `conversion_probability`, `predicted_value`, `churn_risk`
- `best_contact_time`, `best_contact_day`
- `interests`, `objections`, `products_interested`, `content_engaged`
- `recommended_action`, `recommended_product`, `talking_points`

---

### Personalidad extraída de posts de Instagram

El `PersonalityExtractor` ejecuta un pipeline de 5 fases:
- **Fase 0**: Limpieza de datos — extrae conversaciones desde DB con mínimo 1 mensaje
- **Fase 1**: Formatting — `generate_doc_a()` formatea todas las conversaciones
- **Fase 2**: Lead Analysis — `analyze_all_leads()` + `generate_doc_b()`
- **Fase 3**: Personality Profiling — 3 llamadas LLM en paralelo:
  - Call 1: Identity + Catchphrases
  - Call 2: Tone map (7 contextos conversacionales)
  - Call 3: Sales method + Limitations
  - También: análisis estadístico local (sin LLM) de `WritingStyle` y `CreatorDictionary`
- **Fase 4**: Bot Configuration — `generate_doc_d()` produce la configuración completa del bot
- **Fase 5**: Copilot Rules — `generate_doc_e()` produce reglas para el copilot

Los documentos resultantes (Doc D y Doc E) se persisten en la tabla `personality_docs` (PostgreSQL) porque Railway tiene filesystem efímero. Doc D define HOW el bot escribe; Doc E define reglas de corrección para el copilot.

---

## BLOQUE 4: INTELIGENCIA DE LEADS

### El algoritmo de scoring (paso a paso)

El sistema V3 es determinista en 3 pasos (`services/lead_scoring.py`):

**PASO 1: Extracción de señales** (`extract_signals(session, lead)`)

Analiza todos los mensajes del historial distinguiendo `role="user"` (follower) vs `role="assistant"` (bot/creator):

- `follower_purchase_hits`: keywords como "precio", "cuánto cuesta", "comprar", "pagar", "contratar" (SOLO en mensajes del follower)
- `follower_interest_hits`: "me interesa", "quiero saber", "cómo funciona", "detalles" (SOLO follower)
- `follower_scheduling_hits`: "reservar", "agendar", "cita", "sesión", "disponibilidad" (SOLO follower)
- `follower_negative_hits`: "no me interesa", "muy caro", "no gracias", "después" (SOLO follower)
- `follower_social_hits` + `creator_social_hits`: social keywords en cada lado ("jaja", "amigo", "abrazo", "crack")
- `collaboration_hits`: "collab", "colaborar", "proyecto juntos" (ambos lados)
- `bidirectional_ratio`: `min(follower_msgs, creator_msgs) / max(follower_msgs, creator_msgs)`
- `days_since_last`: días desde última interacción
- `story_replies`: mensajes de respuesta a story (via metadata o texto)
- `short_reactions`: mensajes de ≤ 5 chars

**PASO 2: Clasificación** (`classify_lead(signals)`)

Árbol de decisión en 7 niveles de prioridad (primer match gana):
1. `is_existing_customer` → `cliente`
2. `follower_purchase_hits >= 2` → `caliente`
3. `purchase_hits >= 1 AND scheduling_hits >= 1` → `caliente`
4. `strong_intents >= 2 AND purchase_hits >= 1` → `caliente`
5. `collaboration_hits >= 2` → `colaborador`
6. Amigo A: social_ambos_lados AND total_msgs >= 6 AND bidir >= 0.3 → `amigo`
7. Amigo B: bidir >= 0.5 AND total_msgs >= 20 → `amigo`
8. Amigo C: follower_social >= 2 AND story_replies >= 1 AND purchase_hits == 0 → `amigo`
9. Amigo D: (reactions+stories)/follower_msgs >= 0.5 AND purchase_hits == 0 AND social >= 1 → `amigo`
10. `days_since_last >= 14 AND total_msgs >= 2` → `frío`
11. `interest_hits >= 2` → `caliente` (soft)
12. `interest_hits >= 1 AND purchase_hits >= 1` → `caliente` (soft)
13. `scheduling_hits >= 1 AND interest_hits >= 1` → `caliente` (soft)
14. Default → `nuevo`

**PASO 3: Score dentro del rango** (`calculate_score(status, signals)`)

Rangos fijos por categoría:
- `cliente`: 75-100
- `caliente`: 45-85
- `colaborador`: 30-60
- `amigo`: 15-45
- `nuevo`: 0-25
- `frío`: 0-10

Dentro del rango, el factor de calidad (0.0-1.0) ajusta la posición:
- Para `caliente`: base 0.5, +0.1 por cada purchase_hit (max +0.2), +0.075 por scheduling (max +0.15), +0.05 por strong_intent (max +0.1), -0.15 si hay hits negativos
- Para `amigo`: base 0.3, +0.03 por social_hit (max +0.3), +0.005 por mensaje (max +0.2), +0.1 si bidir >= 0.6

---

### Señales que detecta en cada mensaje

Clasificadas por who says it (follower vs. creator):

| Categoría | Keywords exactas | Quién | Peso en scoring |
|-----------|-----------------|-------|----------------|
| **Compra directa** | "precio", "cuánto", "cuanto", "cuesta", "comprar", "pagar", "contratar", "inscribirme", "quiero comprar", "cómo pago", "método de pago", "transferencia", "price", "cost", "buy", "purchase", "pay" | FOLLOWER únicamente | Alto — activa `caliente HARD` con 2+ hits |
| **Interés suave** | "me interesa", "quiero saber", "necesito", "me gustaría", "cuéntame más", "cómo funciona", "qué incluye", "info", "información", "detalles", "interesado", "interested", "tell me more" | FOLLOWER únicamente | Medio — solo `caliente SOFT` tras amigo |
| **Scheduling** | "reservar", "agendar", "cita", "sesión", "horario", "disponibilidad", "calendario", "fecha", "hora", "call", "meeting", "appointment", "schedule", "book" | FOLLOWER únicamente | Medio-alto — combinado con purchase → caliente |
| **Social/amistad** | "jaja", "jeje", "amigo", "hermano", "bro", "crack", "capo", "leyenda", "abrazo", "tío", "pana", "compa", "love you" | AMBOS — bilateral requerido para `amigo` | Diferenciador clave |
| **Colaboración** | "collab", "colaborar", "colaboración", "proyecto juntos", "partners", "together", "alianza" | AMBOS | 2+ hits → `colaborador` |
| **Objeción/negativo** | "no me interesa", "caro", "muy caro", "no gracias", "después", "ahora no", "not interested", "too expensive" | FOLLOWER únicamente | Negativo — -0.15 quality en caliente |

---

### Categorías de audiencia que identifica

El sistema V3 identifica 6 segmentos flat:

| Categoría | Definición operacional | Acción recomendada |
|-----------|----------------------|-------------------|
| **cliente** | `status == "cliente"` — no auto-degradable | Fidelización, upsell, referencias |
| **caliente** | Purchase/scheduling/interest signals claros | Cierre activo, enviar info, payment link |
| **colaborador** | ≥ 2 hits collaboration keywords | Propuesta de proyecto, meeting |
| **amigo** | Bidirectionality social + volumen | No vender; conversación natural |
| **nuevo** | Default sin señales fuertes | Calificación suave, bienvenida |
| **frío** | Sin actividad ≥ 14 días con historial previo | Reactivación |

La `LeadIntelligence` (tabla separada) enriquece esto con scores adicionales: `engagement_score`, `intent_score`, `fit_score`, `urgency_score`, y predicciones como `conversion_probability`, `churn_risk`, `best_contact_time`.

---

### Accionables que genera

1. **Notificación Telegram** (automática en tiempo real): HOT LEAD, escalación, support, feedback negativo
2. **Payment link injected**: Cuando intent es `purchase_intent` y el producto está mencionado — el link se añade automáticamente al final de la respuesta
3. **Booking link injected**: Cuando se menciona reservar/agendar y no hay URL en la respuesta
4. **Nurturing sequences**: Auto-schedule de follow-ups según intent post-respuesta
5. **Email capture**: Si `ENABLE_EMAIL_CAPTURE=true` (default: false), añade pregunta de email en momentos estratégicos
6. **DNA update scheduled**: Cuando se cumplen condiciones (seed DNA + ≥5 msgs), el análisis completo se programa en background
7. **Copilot dashboard**: El creador ve un panel gamificado con XP, niveles, reglas aprendidas, y métricas de aprobación

---

## BLOQUE 5: QUÉ HACE CON LA DATA DEL CREADOR

### Fuentes de datos (pipeline de ingestion)

El pipeline de ingestion V2 (`ingestion/v2/pipeline.py`) procesa estas fuentes:

| Fuente | Estado | Qué extrae |
|--------|--------|-----------|
| **Website scraping** | Activo | Bio, FAQs, tono de comunicación, productos (precio, descripción, URL de pago) |
| **Product detection** | Activo | Sistema de señales para detectar páginas de servicio; sanity checks antes de guardar |
| **Instagram posts** | Activo | Tono de voz, vocabulario, emojis, dialecto (via `ToneAnalyzer` + LLM) |
| **YouTube** | Ruta de API existe (`api/routers/ingestion_v2/youtube.py`) | Estado: no auditado completamente |
| **Conversaciones DM** | Activo | `PersonalityExtractor` analiza historial de DMs para extraer perfil de personalidad |
| **Knowledge base manual** | Activo | `add_knowledge()`, `add_knowledge_batch()`, `clear_knowledge()` — API para añadir info factual estructurada |

El resultado del pipeline incluye: `pages_scraped`, `products_detected`, `products_verified`, `rag_docs_saved`, `bio`, `faqs`, `tone`, y la lista de errores. Se ejecuta cleanup previo: borra productos y docs RAG anteriores antes de guardar los nuevos.

---

### Anti-alucinación (mecanismos exactos)

El sistema tiene **múltiples capas independientes** de anti-alucinación:

1. **Output Validator** (`core/output_validator.py`): Activo en postprocessing. Extrae precios del texto con 6 regex patterns. Compara contra `known_prices` del creator (±1€ tolerancia). Si hay precio no reconocido → `should_escalate=True` → respuesta de fallback genérica.

2. **Link Validator**: Extrae URLs con regex. Verifica contra whitelist de dominios (14 dominios por defecto + dominios de productos del creador). URLs no autorizadas → `corrected = corrected.replace(url, "[enlace removido]")`.

3. **Guardrails** (`core/guardrails.py`): Segunda capa de validación de precios y URLs, más hallucination patterns específicos (promesas de llamar, promesas de email, dirección física).

4. **Response Fixes** (`core/response_fixes.py`): FIX 4 previene que el bot diga "Soy Stefano" (se convierte a "Soy el asistente de Stefano"). FIX 5 elimina CTAs crudos del RAG. FIX 9 elimina catchphrases hallucinated típicas del LLM.

5. **Citation context** (`core/citation_service.py`): Carga fuentes de información verificadas para que el LLM pueda atribuir correctamente.

6. **Advanced rules section** (`core/prompt_builder.py`, función `build_rules_section()`): Sección del prompt con reglas anti-alucinación inyectadas directamente.

7. **Pool response fast path**: Para saludos simples, usa respuestas de un pool pre-verificado sin LLM.

---

### Cómo busca en el conocimiento

Pipeline de búsqueda en `core/rag/semantic.py`:

```
Query -> [Cache hit? -> return]
      -> Step 1: Semantic search (OpenAI text-embedding-3-small + pgvector cosine similarity)
      -> Step 2: BM25 hybrid fusion (si ENABLE_BM25_HYBRID=true, default: true)
            - Reciprocal Rank Fusion: score = sum(1/(k+rank))
            - Pesos: HYBRID_SEMANTIC_WEIGHT=0.7, HYBRID_BM25_WEIGHT=0.3
            - initial_top_k = min(top_k*2, 12) si reranking activo
      -> Step 3: Cross-encoder reranking (si ENABLE_RERANKING=true, default: true)
            - Modelo cross-encoder descargado localmente
            - +100-200ms de latencia
      -> Return top_k=3 resultados finales
```

**Fallback**: Si OpenAI embeddings no disponibles (sin `OPENAI_API_KEY`), usa búsqueda de texto plano `_fallback_search()`.

**Skipping**: Intents `{greeting, farewell, thanks, saludo, despedida}` → RAG saltado completamente. Esto se comprueba en `context.py` antes de llamar a `semantic_rag.search()`.

**Cache**: `_rag_cache[f"{creator_id}:{query}"]` con TTL de 300 segundos. Para Stefano, si dos followers preguntan "precio coaching" en menos de 5 minutos, el segundo obtiene resultado del cache sin llamada a OpenAI embeddings.

---

### Re-indexación

El knowledge base se actualiza mediante:
1. **Ingestion V2 completa**: Borra todos los docs RAG del creator, re-scraped el website, guarda nuevos documentos con embeddings regenerados.
2. **`add_knowledge()` / `add_knowledge_batch()`**: APIs para añadir documentos individuales o en lote (regenera embedding para cada doc).
3. **`clear_knowledge()`**: Borra todo el knowledge base de un creator.

No hay re-indexación automática periódica en el código auditado. Es un proceso manual o triggered por el creador.

---

## BLOQUE 6: AUTOLEARNING EN PROFUNDIDAD

### Tipos de reglas que aprende

| pattern_type | Qué representa | Cómo lo detecta | Cómo lo aplica |
|-------------|---------------|----------------|----------------|
| `shorten_response` | Bot responde demasiado largo | Creator edita recortando; LLM detecta `length_delta < -10` | Regla en prompt: "responder más brevemente en contexto X" |
| `tone_more_casual` | Bot demasiado formal | Creator usa lenguaje más informal en edición | Regla de tono informal inyectada en prompt |
| `remove_question` | Bot hace pregunta innecesaria | `orig_questions > edit_questions` en diff | Regla: no preguntar en contexto Y |
| `add_greeting` | Bot olvidó saludar | Creator añade saludo en edición | Regla de saludo para ese contexto |
| `remove_emoji` / `add_emoji` | Uso incorrecto de emojis | `orig_emojis > edit_emojis` o viceversa | Regla de emoji para ese intent |
| `tone_more_formal` | Bot demasiado informal | Edición más formal | Regla de formalidad |
| `restructure` | Orden incorrecto de información | Reescritura estructural | Regla de estructura |
| `personalize` | Falta de personalización | Creator añade nombre o referencia personal | Regla de personalización |
| `remove_cta` | CTA inapropiado | Creator elimina call-to-action | No usar CTA en ese contexto |
| `soften_pitch` | Ventas demasiado agresivas | Creator suaviza la propuesta | Regla de soft pitch |
| `complete_rewrite` | Respuesta completamente incorrecta | Overlap < 30% entre original y edición | Regla de fondo para ese intent/stage |
| `other` | No clasificable | LLM no identifica patrón claro | Regla genérica |

---

### El flujo de aprendizaje

```
Creator action (approve/edit/discard/manual_override/resolved_externally)
    |
    v
analyze_creator_action() [fire-and-forget, never raises]
    |
    +-- approved -> reinforce existing rules (update_rule_feedback, was_helpful=True)
    |
    +-- edited -> si |len_diff| >= 3 chars Y texto cambia:
    |       _llm_extract_rule(bot_vs_creator) -> JSON {rule_text, pattern, example_bad, example_good}
    |       _store_rule(confidence=0.5)
    |
    +-- discarded ->
    |       _llm_extract_rule(bot_vs_discard_reason) -> JSON
    |       _store_rule(confidence=0.6)
    |
    +-- resolved_externally ->
    |       _llm_extract_rule(bot_vs_creator_bypassed) -> JSON
    |       _store_rule(confidence=0.7)
    |
    +-- manual_override ->
            _llm_extract_rule(bot_vs_manual) -> JSON
            _store_rule(confidence=0.65)
```

Las reglas se guardan en tabla `learning_rules` con campos: `rule_text`, `pattern`, `applies_to_relationship_types`, `applies_to_message_types`, `applies_to_lead_stages`, `example_bad`, `example_good`, `confidence`, `times_applied`, `times_helped`, `is_active`.

Cuando `ENABLE_LEARNING_RULES=true` (default: false), en Fase 4 de cada mensaje se cargan las reglas aplicables al intent/relationship/stage actual y se inyectan en el prompt como:
```
=== REGLAS APRENDIDAS (del propio creador) ===
- [rule_text]
  NO: "[example_bad]"
  SI: "[example_good]"
=== FIN REGLAS ===
```

---

### Gold Examples y Preference Pairs

**Gold Examples** (tabla `gold_examples`):
- Pares (user_message, creator_response) de alta calidad
- Campos: `intent`, `lead_stage`, `relationship_type`, `source`, `quality_score` (0.0-1.0), `times_used`, `times_helpful`, `expires_at`
- Se usan como few-shot examples en el prompt cuando `ENABLE_GOLD_EXAMPLES=true` (default: false)
- Generan formato: `Lead: "mensaje" \n Stefano: "respuesta"`

**Preference Pairs** (tabla `preference_pairs`):
- Pares (chosen, rejected) de respuestas del bot
- Incluyen: `user_message`, `chosen`, `rejected`, `intent`, `lead_stage`, `action_type`, `chosen_temperature`, `rejected_temperature`, `chosen_confidence`, `rejected_confidence`, `confidence_delta`, `edit_diff`
- Se generan en el proceso de análisis por lotes (`PatternAnalysisRun`) donde un LLM-as-Judge analiza grupos de pares y extrae learning rules
- La tabla `pattern_analysis_runs` trackea cada run: `pairs_analyzed`, `rules_created`, `groups_processed`, `status`

**Preference Profile** (`ENABLE_PREFERENCE_PROFILE=false` por defecto): `compute_preference_profile()` + `format_preference_profile_for_prompt()` produce una sección del prompt basada en el historial de preferencias del creador.

---

### Gamificación

El dashboard de autolearning (`api/routers/autolearning/dashboard.py`) tiene un sistema completo de gamificación:

**Niveles (XP threshold → Nombre → Emoji)**:
| XP | Nivel | Emoji |
|----|-------|-------|
| 0 | Bebé | 👶 |
| 25 | Novato | 🐣 |
| 100 | Aprendiz | 📘 |
| 250 | Capaz | 💪 |
| 500 | Hábil | 🎯 |
| 1000 | Experto | ⭐ |
| 2000 | Maestro | 🏆 |
| 5000 | Tu gemelo | 🤖 |

**XP por acción** (no explícito en el código auditado, inferido del sistema — los valores exactos estarían en la query del dashboard).

**Logros (11 total)**:
- `first_approval`: Aprobar primera sugerencia
- `ten_approvals` / `fifty_approvals`: Rachas de aprobación
- `first_edit` / `first_rule` / `five_rules`: Progreso en aprendizaje
- `streak_3` / `streak_7`: Racha de días consecutivos usando copilot
- `level_3` / `level_5`: Alcanzar niveles específicos
- `autopilot_ready`: Un intent alcanza status "ready" para autopilot

**Streak**: Calculado contando días consecutivos donde hubo acciones de copilot (approved/edited/discarded), empezando desde hoy o ayer. Máximo histórico consultado: 60 días.

---

## TABLA MAESTRA: Capacidades del motor con estado

| Sistema | Capacidad específica | Estado | Notas |
|---------|---------------------|--------|-------|
| Pipeline | 5 fases secuenciales con paralelismo en Fase 2-3 | ✅ Activo | 4 operaciones IO en paralelo: ~1.2s vs ~3.8s secuencial |
| Detection | Sensitive content detection | ✅ Activo | Umbral: confidence ≥ 0.7 (log), ≥ 0.85 (escalación) |
| Detection | Frustration detection | ✅ Activo | Log > 0.3, prompt injection > 0.5 |
| Detection | Pool response fast path | ✅ Activo | Mensajes ≤ 80 chars sin producto mencionado |
| Detection | Multi-bubble response | ✅ Activo | 30% probabilidad cuando pool matches |
| Context | Intent classification | ✅ Activo | Enum de ~17 intents |
| Context | Query expansion | ✅ Activo | Max 2 expansiones via `get_query_expander()` |
| Context | RAG semantic (OpenAI embeddings + pgvector) | ✅ Activo | text-embedding-3-small, top_k=3 |
| Context | RAG BM25 hybrid | ✅ Activo | Pesos 0.7/0.3, RRF fusion |
| Context | Cross-encoder reranking | ✅ Activo | ENABLE_RERANKING=true por defecto |
| Context | RAG cache | ✅ Activo | TTL=300s por query+creator |
| Context | RelationshipDNA loading | ✅ Activo | PostgreSQL, seed a ≥2 msgs, full analysis a ≥5 |
| Context | Commitment tracking (ECHO) | ✅ Activo | ENABLE_COMMITMENT_TRACKING=true |
| Context | Conversation state phases | ✅ Activo | inicio/propuesta/cierre via StateManager |
| Context | Relationship type detection (amigo/familia) | ✅ Activo | Suprime ventas para FAMILIA/INTIMA |
| Context | Audio message intelligence | ✅ Activo | Enriquece prompt con entidades/acciones del audio |
| Generation | Gemini 2.5 Flash-Lite primario | ✅ Activo | Con circuit breaker (2 fallos → 120s cooldown) |
| Generation | GPT-4o-mini fallback | ✅ Activo | Automático si Gemini falla |
| Generation | Strategy determination | ✅ Activo | 7 estrategias (PERSONAL/AYUDA/VENTA/BIENVENIDA/REACTIVACIÓN) |
| Generation | ECHO Relationship Adapter | ✅ Activo | Ajusta max_tokens y temperature dinámicamente |
| Generation | Learning rules injection | ⚠️ Desactivado | ENABLE_LEARNING_RULES=false por defecto |
| Generation | Preference profile injection | ⚠️ Desactivado | ENABLE_PREFERENCE_PROFILE=false |
| Generation | Gold examples (few-shot) | ⚠️ Desactivado | ENABLE_GOLD_EXAMPLES=false |
| Generation | Best-of-N (3 candidatos) | ⚠️ Desactivado | ENABLE_BEST_OF_N=false; solo en modo copilot |
| Generation | Self-consistency validation | ⚠️ Desactivado | ENABLE_SELF_CONSISTENCY=false |
| Generation | Chain of Thought | ⚠️ Parcial | Módulo completo, no integrado en pipeline DM principal |
| Postprocessing | Loop detection (A2 fix) | ✅ Activo | Compara primeros 50 chars con últimas 3 respuestas |
| Postprocessing | Price validation | ✅ Activo | Tolerancia ±1€, 6 patrones regex |
| Postprocessing | Link validation + removal | ✅ Activo | Whitelist 14 dominios + dominios del creator |
| Postprocessing | 9 response fixes | ✅ Activo | Price typo, identity claim, CTA raw, catchphrase, emoji limit |
| Postprocessing | Tone enforcement | ✅ Activo | Si hay calibration: emoji/excl/question rates |
| Postprocessing | Question remover | ✅ Activo | ENABLE_QUESTION_REMOVAL=true |
| Postprocessing | Reflexion analysis | ✅ Activo | 5 checks, registra issues — NO re-genera |
| Postprocessing | Guardrails (precios, URLs, hallucinations) | ✅ Activo | 4 tipos de detección |
| Postprocessing | Message splitting | ✅ Activo | ENABLE_MESSAGE_SPLITTING=true |
| Postprocessing | Payment link auto-injection | ✅ Activo | Solo si intent = purchase_intent y producto mencionado |
| Postprocessing | CloneScore real-time | ⚠️ Desactivado | ENABLE_CLONE_SCORE=false |
| Postprocessing | Email capture | ⚠️ Desactivado | ENABLE_EMAIL_CAPTURE=false |
| Memory | FollowerMemory JSON (20 msgs, 9 fact types) | ✅ Activo | Persiste en filesystem JSON |
| Memory | DNA auto-create y updates | ✅ Activo | Seed a ≥2 msgs, async updates |
| Memory | Memory Engine (pgvector facts) | ⚠️ Desactivado | ENABLE_MEMORY_ENGINE=false; tabla lead_memories existe |
| Memory | Memory decay (Ebbinghaus) | ⚠️ Desactivado | ENABLE_MEMORY_DECAY=false |
| Safety | Send Guard | ✅ Activo | ÚLTIMO control: bloquea envío sin aprobación |
| Safety | Sensitive content escalation | ✅ Activo | Crisis resources si confidence ≥ 0.85 |
| Safety | Timing (2-30s delay, 8-23h) | ✅ Activo | Simula velocidad humana |
| Personalization | ToneProfile (20+ dimensiones) | ✅ Activo | Dialecto, voseo, filler words, emojis, energía |
| Personalization | Calibration (emoji/exclamation rates) | ✅ Activo | enforce_tone() post-LLM |
| Personalization | Bot configurator (Doc D) | ✅ Activo | Pipeline 5 fases, persiste en PostgreSQL |
| Lead scoring | V3 6 categorías flat | ✅ Activo | Determinista, 3 pasos: signals→classify→score |
| Lead scoring | LeadIntelligence (predictivo) | ✅ Activo | Tabla con conversion_probability, churn_risk |
| AutoLearning | Action tracking (approve/edit/discard) | ✅ Activo | Siempre registrado en PreferencePair |
| AutoLearning | LLM rule extraction | ⚠️ Desactivado | ENABLE_AUTOLEARNING=false |
| AutoLearning | Rule injection in DM | ⚠️ Desactivado | ENABLE_LEARNING_RULES=false |
| AutoLearning | Pattern analysis batch (LLM-as-Judge) | ✅ Activo | PatternAnalysisRun |
| AutoLearning | Gamification dashboard | ✅ Activo | 8 niveles, 11 logros, streak |

---

## LO MÁS SORPRENDENTE DEL SISTEMA

- **El stack de anti-alucinación es doble y redundante**: `output_validator.py` y `guardrails.py` hacen esencialmente la misma validación de precios y URLs de forma independiente. Si Stefano tiene el coaching a 297€ y el LLM alucina "197€", ambas capas lo detectan con tolerancia ±1€. La corrección de URLs va más allá: no solo valida — reemplaza el texto literalmente con `[enlace removido]`.

- **El voseo está implementado a nivel de código, no solo de prompt**: `apply_voseo()` en `text_utils.py` tiene 20 pares de regex específicos para convertir tuteo a voseo argentino después de la generación. Esto significa que aunque el LLM genere "puedes empezar mañana", el código lo convierte a "podés empezar mañana". Esto no depende de que el LLM recuerde las instrucciones.

- **La estrategia de respuesta suprime ventas para amigos/familia ANTES del LLM**: En Fase 2, antes de construir el prompt, si `is_friend=True`, los productos se eliminan de `prompt_products = [] if is_friend else agent.products`. El LLM literalmente no recibe la lista de productos para no tentarse a venderlos. Además, se inyecta el contexto de amigo/familia explícitamente.

- **El circuit breaker de Gemini tiene 120 segundos de cooldown**: Después de 2 fallos consecutivos, el sistema espera 2 minutos antes de intentar Gemini de nuevo. Durante ese tiempo, GPT-4o-mini recibe todo el tráfico. El estado del circuit breaker es **in-memory por worker** — no se comparte entre procesos gunicorn.

- **El loop detector opera en 50 chars**: Si el bot genera la misma respuesta (mismos primeros 50 chars) que alguno de los últimos 3 mensajes que envió, la reemplaza automáticamente por "Contame más". Esto previene que el bot entre en un ciclo repetitivo sin que el creador lo note.

- **La Memory Engine tiene decay Ebbinghaus pero está desactivada**: El sistema tiene implementado un algoritmo de decaimiento de memoria basado en la curva de olvido de Ebbinghaus con `half_life=30 días`. Los hechos de alta importancia tardarían más en decaer. Todo esto existe en `services/memory_engine.py` pero `ENABLE_MEMORY_ENGINE=false`.

- **Best-of-N inyecta style hints para forzar diversidad**: Los 3 candidatos no son simplemente temperaturas diferentes — cada uno recibe un estilo injected en el system prompt (`[ESTILO: responde de forma breve...]`, vacío, `[ESTILO: responde más elaborado...]`). Esto previene que T=0.7 y T=1.4 generen respuestas casi idénticas en modelos deterministas.

---

## LOS GAPS MÁS IMPORTANTES

- **Memory Engine desactivada = sin memoria semántica real**: El sistema actual solo mantiene los últimos 20 mensajes en un JSON. Si Stefano habla con el mismo follower sobre una lesión de rodilla hoy, y ese follower vuelve en 3 semanas, el bot no recordará la conversación (los 20 msgs ya habrán sido desplazados). La Memory Engine con pgvector + decay haría esto posible, pero está desactivada.

- **AutoLearning desactivado = sin aprendizaje real en producción**: `ENABLE_AUTOLEARNING=false` significa que cuando Stefano edita una respuesta del bot en el dashboard, se guarda en `PreferencePair` (tabla) pero el LLM de extracción de reglas nunca se ejecuta. El sistema acumula datos de entrenamiento sin procesarlos.

- **Chain of Thought no conectado al pipeline principal**: Existe `ChainOfThoughtReasoner` completo con detección de complejidad, razonamiento por tipos, y generación de respuestas. Pero no hay ningún hook en `phase_llm_generation.py` que lo active. Para que Stefano responda mejor preguntas complejas sobre lesiones, habría que integrar explícitamente este módulo.

- **Reflexion Engine solo registra, no corrige**: El análisis detecta cuando la respuesta es demasiado larga, cuando no incluye precio habiendo sido preguntado, o cuando hay repetición. Pero el resultado (`r_result.needs_revision`) solo se guarda en `cognitive_metadata`. El bot **no re-genera** la respuesta aunque `severity == "high"`. Es un sistema de telemetría, no de auto-corrección.

- **El DNA tarda en construirse y la calidad inicial es baja**: El seed DNA se crea con confianza inicial de `det_confidence × 0.3` — apenas 30% de la confianza del detector. El análisis completo requiere ≥5 mensajes y se ejecuta de forma asíncrona. Los primeros 4 mensajes de cualquier follower de Stefano tienen DNA de bajísima calidad, y la actualización puede tardar horas si hay cola.

- **La segmentación de leads no es predictiva, sino reactiva**: El scoring V3 es excelente para clasificar lo que ya pasó, pero no predice qué vas a pasar. La `LeadIntelligence` tiene campos `conversion_probability` y `churn_risk`, pero no está claro cuándo se actualiza automáticamente. Si Stefano tiene 500 leads, ¿cuál es el próximo que va a convertir?

- **El Send Guard es un bloqueo duro sin retry**: Si un mensaje pasa todos los guardrails pero llega al Send Guard sin aprobación explícita y sin `autopilot_premium_enabled=True`, lanza una excepción `SendBlocked`. No hay retry automático, no hay encolado, no hay notificación al creador de que hay mensajes bloqueados pendientes de revisar.
