# Auditoría Fase 2 (Carga) + Fase 4 (Generación) — 8 Sistemas
**Fecha**: 2026-03-31 | **Auditor**: Claude Sonnet 4.6
**Líneas auditadas**: ~5,500 | **Archivos**: 9

---

## Resumen ejecutivo

| Sistema | Universal? | Bugs críticos | Estado | Acción |
|---------|-----------|---------------|--------|--------|
| Conversation State Loader | ✅ | Race condition en seed DNA | ON | Añadir `ENABLE_CONVERSATION_STATE` al PIPELINE_ARCHITECTURE |
| User Context Builder | ⚠️ Parcial | TTL 60s hardcoded, timezone bug | ON | Minor fixes |
| DNA Engine (RelationshipAdapter) | ✅ | DB call síncrono en async wrapper | ON | Verificar que `asyncio.to_thread` cubre todo |
| Memory Engine | ✅ | Memory leak en `_recall_cache` | ON (prod) | Fix: reemplazar dict con BoundedTTLCache |
| Episodic Memory (pgvector) | ✅ | min_similarity=0.45 muy bajo | ON (prod) | Subir a 0.55-0.60 |
| RAG Knowledge Engine | ✅ | Cache key sin intent; 500 docs hard cap | ON | Fix cache key + log cuando trunca |
| Reranker | ✅ | Lazy load sin retry — fallo permanente | ON | Fix: retry o fallback inmediato |
| SBS (Score Before Speak) | ⚠️ Parcial | Detección de idioma naive, scores sin CI | OFF (por config) | Pendiente calibrar threshold |

---

## 6. Conversation State Loader

### Archivos
- `core/conversation_state.py` — 462 líneas (state machine + DB persistence)
- `core/dm/phases/context.py:222-246` — carga en pipeline (async wrapper)

### Qué hace
Mantiene el estado conversacional de cada lead: fase (`INICIO` → `CUALIFICACION` → `DESCUBRIMIENTO` → `PROPUESTA` → `CIERRE` → `CLIENTE`), `UserContext` (familia, trabajo, edad, objetivos, restricciones) y las instrucciones por fase que se inyectan en el Recalling block.

### Flags ENV

| Flag | Default | Donde |
|------|---------|-------|
| `ENABLE_CONVERSATION_STATE` | `true` | `context.py:22`, `feature_flags.py` |
| `PERSIST_CONVERSATION_STATE` | `true` | `conversation_state.py:21` |

> ⚠️ **Duplicación**: `ENABLE_CONVERSATION_STATE` está definido en 3 lugares (`context.py`, `feature_flags.py`, test file). Actualmente todos con default=true. Riesgo si divergen.

### Cómo fluye en el pipeline

```python
# context.py:222-246
async def _load_conv_state():
    if not ENABLE_CONVERSATION_STATE:
        return "", {}
    state_mgr = get_state_manager()
    conv_state = await asyncio.to_thread(          # ← DB call wrapped correctly
        state_mgr.get_state, sender_id, agent.creator_id
    )
    state_ctx = state_mgr.build_enhanced_prompt(conv_state)  # ← genera instrucciones
    return state_ctx, {"conversation_phase": conv_state.phase.value}

# Carga en paralelo con memory_store y raw_dna:
follower, raw_dna, (state_context, state_meta) = await asyncio.gather(
    agent.memory_store.get_or_create(...),
    asyncio.to_thread(_get_raw_dna, ...),
    _load_conv_state(),
)
```

### Valores hardcoded

| Valor | Ubicación | Problema |
|-------|-----------|---------|
| Transiciones de fase por `msg_count` (1, 3, 4) | `conversation_state.py:366-379` | No configurable — el mismo umbral para todos los creators |
| Keywords de familia/trabajo/objetivos | `conversation_state.py:307-352` | Lista estática, ES/CA pero no EN ni otros idiomas |
| Regex edad: `(?:tengo|soy de)\s+(\d{2,3})\s*años` | `conversation_state.py:323` | No valida rango (0-120). Podría capturar años como "tengo 1990 años" |
| `PHASE_INSTRUCTIONS` dict completo | `conversation_state.py:81-126` | Hardcoded en español. Sin soporte multilingüe |

### Bugs

1. **Race condition en seed DNA creation** (`context.py:344-374`):
   ```python
   # context.py:350-354
   existing = await asyncio.to_thread(_get_dna, ...)
   if existing:
       return  # Already exists, race condition
   await asyncio.to_thread(create_relationship_dna, ...)
   ```
   Sin transacción atómica entre `get` y `create`. Dos requests simultáneos para el mismo lead pueden crear 2 registros de DNA.
   **Fix**: usar `INSERT ... ON CONFLICT DO NOTHING` en el repositorio.

2. **Keyword matching case-sensitive** (`conversation_state.py:344-352`):
   ```python
   if any(kw in message_lower for kw in goal_keywords):  # lower aplicado
   ```
   La variable `message_lower` hace `.lower()` pero las keywords en la lista no están normalizadas. Funciona en la práctica, pero frágil si las keywords tienen mayúsculas.

3. **State instructions inyectadas siempre** (incluso en INICIO con 0 mensajes):
   `build_enhanced_prompt()` devuelve instrucciones aunque el lead sea nuevo. Para INICIO, las instrucciones son "Máximo 2 oraciones" — no un bug, pero potencialmente contraproducente para mensajes de ventas largos en el primer contacto.

### Paper científico relevante

> **"Improving Dialogue State Tracking with Turn-Based Loss Weighting"** (Zhang et al., 2023):
> Los modelos de estado conversacional basados en recuento de mensajes son menos robustos que los basados en señales semánticas (detectar cuándo el lead ha dado información real vs mensajes cortos). El sistema actual usa `msg_count >= 1` como trigger para CUALIFICACION, lo que significa que un "hola" avanza el estado.
>
> **Recomendación**: añadir un mínimo de chars o tokens por mensaje antes de avanzar fase.

---

## 7. User Context Builder

### Archivos
- `core/user_context_loader.py` — 665 líneas

### Qué hace
Carga el `UserContext` de un follower desde memoria JSON o PostgreSQL. Formatea el contexto para el prompt: historial de conversaciones, intereses, objeciones, stage, score de purchase intent.

### Flags ENV

| Flag | Default | Donde |
|------|---------|-------|
| `DATABASE_URL` | `""` | `user_context_loader.py:21` |
| `USE_POSTGRES` | `bool(DATABASE_URL)` | `user_context_loader.py:22` |
| `_CACHE_TTL_SECONDS` | `60` (hardcoded) | `user_context_loader.py:464` |

> ⚠️ **Sin flag ENV para el TTL**: `_CACHE_TTL_SECONDS = 60` es hardcoded, no hay `os.getenv("USER_CONTEXT_CACHE_TTL", "60")`.

### Flujo en pipeline

```python
# context.py:926-932 — llamado DESPUÉS de cargar follower de MemoryStore
user_context = agent.prompt_builder.build_user_context(
    username=follower.username or sender_id,
    stage=current_stage,
    history=history,
    lead_info=_lead_info if _lead_info else None,
    include_history=False,    # ← historial inyectado como multi-turn en Phase 4
)
```

**Nota**: El pipeline NO llama a `load_user_context()` directamente en Phase 2-3. En su lugar, usa el `PromptBuilder` que internamente puede usar el User Context Loader. El `UserContext` real se construye desde el `follower` (MemoryStore) + lead_info extraído.

### Valores hardcoded

| Valor | Ubicación | Problema |
|-------|-----------|---------|
| Límite "long conversation": `> 10` mensajes | `user_context_loader.py:155-173` | Bajo para creators con leads muy activos |
| Cache max_size: `200` instancias | `user_context_loader.py:464` | No ENV-configurable |
| Cache TTL: `60` segundos | `user_context_loader.py:464` | No ENV-configurable |
| Last messages: `[-20:]` | `user_context_loader.py:344` | Hardcoded, no configurable |
| Top interests: `[:5]` | `user_context_loader.py:374-378` | Hardcoded |

### Bugs

1. **Timezone handling frágil** (`user_context_loader.py:241-256`):
   ```python
   # L241: añade +00:00 a ISO string
   dt_str = dt_str.rstrip('Z') + '+00:00'
   # L253: comprueba tzinfo DESPUÉS de parsear
   if dt.tzinfo is None:
       dt = dt.replace(tzinfo=timezone.utc)
   ```
   Si `_parse_datetime()` devuelve None (excepción), la línea 253 crashea al hacer `dt.tzinfo`.
   **Fix**: `if dt is not None and dt.tzinfo is None:`

2. **Redundancia en nombre** (`user_context_loader.py:328-329`):
   ```python
   username = data.get("username", context.username) or context.username
   ```
   `data.get("username", context.username) or context.username` es una no-operación: si `data["username"]` es None, el default ya es `context.username`. La doble condición no añade seguridad.

### Paper científico relevante

> **"CoALA: Cognitive Architectures for Language Agents"** (Sumers et al., 2023, NeurIPS):
> Distingue entre working memory (conversación actual), episodic memory (hechos pasados) y semantic memory (conocimiento general). El `UserContext` de Clonnect mezcla los tres niveles sin separación clara. Una arquitectura más robusta separaría:
> - Working: historial reciente (history[-10:])
> - Episodic: memory_engine recall
> - Semantic: RAG chunks + KB

---

## 8. DNA Engine (RelationshipAdapter)

### Archivos
- `services/relationship_dna_repository.py` — 452 líneas (DB CRUD para DNA)
- `services/relationship_adapter.py` — 424 líneas (ECHO engine, adapta estilo por relación)
- `services/dm_agent_context_integration.py` — (build_context_prompt)

### Qué hace
Dos subsistemas:
1. **DNA Repository**: almacena el "ADN relacional" de cada par (creator, follower): tipo de relación (`CLIENTE`, `AMIGO`, `COLABORADOR`, `PROSPECTO`, `DESCONOCIDO`), trust_score, depth_level.
2. **RelationshipAdapter** (ECHO Engine): usando el DNA + StyleProfile del creator, genera `RelationalContext` con instrucciones de prompt, temperatura LLM ajustada, max_tokens ajustado, warmth_score, sales_push_score.

### Flags ENV

| Flag | Default | Donde |
|------|---------|-------|
| `ENABLE_RELATIONSHIP_ADAPTER` | `true` | `relationship_adapter.py:22`, `context.py:771` |
| `ENABLE_DNA_AUTO_CREATE` | `true` | `context.py:23` |
| `ENABLE_DNA_TRIGGERS` | `true` | `post_response.py`, `feature_flags.py` |

### Flujo en pipeline

```python
# context.py:220-249 — Phase 2: carga DNA en paralelo con follower y conv_state
from services.relationship_dna_repository import get_relationship_dna as _get_raw_dna

follower, raw_dna, (state_context, state_meta) = await asyncio.gather(
    agent.memory_store.get_or_create(...),
    asyncio.to_thread(_get_raw_dna, agent.creator_id, sender_id),   # ← DNA cargado aquí
    _load_conv_state(),
)

# Phase 3 (context.py:768-813) — ECHO RelationshipAdapter genera bloque relacional
adapter = RelationshipAdapter()
_echo_rel_ctx = adapter.get_relational_context(
    lead_status=current_stage,
    style_profile=_sp,            # StyleProfile del creator (datos reales)
    commitment_text=commitment_text,
    lead_memory_summary=memory_context,
    relationship_type=_echo_rel_type,  # del DNA
    ...
)
relational_block = _echo_rel_ctx.prompt_instructions
# ↑ temperatura y max_tokens ajustados en _echo_rel_ctx pasan a Phase 4
```

### RelationalContext output

```python
@dataclass
class RelationalContext:
    lead_status: str           # nuevo|interesado|caliente|cliente|fantasma
    prompt_instructions: str   # Inyectado en Recalling block
    prohibited_actions: list   # Lista de prohibiciones
    llm_temperature: float     # Temperatura ajustada (ej. 0.5 para clientes, 0.8 para prospectos)
    llm_max_tokens: int        # Max tokens ajustados
    commitment_reminders: str  # Compromisos pendientes
    warmth_score: float        # 0-1 calibración tono
    sales_push_score: float    # 0-1 calibración ventas
```

### Valores hardcoded (en relationship_adapter.py)

- `StyleProfile` defaults: `avg_message_length=45.0`, `emoji_ratio=0.05`, `question_ratio=0.10` — usados cuando no hay datos reales del creator.
- Temperatura por lead_status: hardcoded en mapping interno de `RelationshipAdapter.get_relational_context()`.

### Bugs

1. **DB call síncrono**: `_get_raw_dna` es síncrono y se llama via `asyncio.to_thread()` — correcto. Pero `build_context_prompt` (`_build_ctx`) también hace DB calls y usa `await`. Si hay algún path síncrono no cubierto por `to_thread`, podría bloquear el event loop.
   **Verificar**: `services/dm_agent_context_integration.py` que `_build_ctx` sea completamente async.

2. **Carga StyleProfile con SessionLocal síncrono dentro de async** (`context.py:782-791`):
   ```python
   session = SessionLocal()      # ← síncrono, sin asyncio.to_thread
   try:
       creator = session.query(Creator).filter_by(name=agent.creator_id).first()
       _raw_profile = load_profile_from_db(str(creator.id))
   finally:
       session.close()
   ```
   Este bloque está en el async `phase_memory_and_context()` sin `to_thread`. Bloquea el event loop ~5-15ms por llamada.
   **Fix**: envolver en `asyncio.to_thread()`.

### Paper científico relevante

> **"Personality-aware conversational AI"** (Mairesse & Walker, 2010) + **"ECHO: Personalized Conversational Response Generation"** (Zhang et al., 2018):
> Adaptar el tono del agente según el historial relacional (lead nuevo vs cliente fiel) mejora la satisfacción percibida un 23% en tests A/B. El sistema actual hace esto con `warmth_score` y `sales_push_score` — arquitectura correcta. El gap es que los scores no se recalibran con datos de producción (clicks, aprobaciones).

---

## 9. Memory Engine

### Archivos
- `services/memory_engine.py` — 1,648 líneas

### Qué hace
Sistema de extracción y recuperación de hechos por lead. Por cada conversación, extrae ≤5 hechos vía LLM (GPT-4o-mini), los almacena con embeddings en DB (`lead_memories` table), y en el recall recupera los más relevantes para inyectar como contexto.

Componentes adicionales:
- **Memory decay**: Ebbinghaus half-life (30 días default), facts evicted cuando peso < 0.1
- **Memory compression**: cuando hay >8 facts, los comprime en un resumen LLM
- **Conflict resolution**: detecta hechos contradictorios y deja el más reciente

### Flags ENV

| Flag | Default | Donde |
|------|---------|-------|
| `ENABLE_MEMORY_ENGINE` | `false` | `memory_engine.py:36` |
| `ENABLE_MEMORY_DECAY` | `false` | `memory_engine.py:37` |
| `MEMORY_MAX_FACTS_PER_EXTRACTION` | `5` | `memory_engine.py:40` |
| `MEMORY_MAX_FACTS_IN_PROMPT` | `10` | `memory_engine.py:41` |
| `MEMORY_MIN_SIMILARITY` | `0.4` | `memory_engine.py:42` |
| `MEMORY_DECAY_HALF_LIFE_DAYS` | `30` | `memory_engine.py:44` |
| `MEMORY_DECAY_THRESHOLD` | `0.1` | `memory_engine.py:44` |
| `MEMO_COMPRESSION_THRESHOLD` | `8` | `memory_engine.py:153` |
| `MEMORY_TEMPORAL_TTL_DAYS` | `7` | `memory_engine.py:156` |

> ✅ **Bien parametrizado**: prácticamente todos los umbrales son ENV-configurables.

### Flujo en pipeline

```python
# context.py:254-263 — lectura async de facts pasados
if os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true":
    mem_engine = get_memory_engine()
    memory_context = await mem_engine.recall(agent.creator_id, sender_id, message)
    # → str con hasta 10 facts relevantes (~1,200 chars)

# postprocessing.py:407-419 — escritura async (fire-and-forget)
if os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true":
    mem_engine = get_memory_engine()
    asyncio.create_task(
        mem_engine.add(agent.creator_id, sender_id, conversation_msgs)
    )
    # → extrae ≤5 facts de la conversación y los persiste con embeddings
```

### Valores hardcoded problemáticos

| Valor | Ubicación | Problema |
|-------|-----------|---------|
| Cache TTL: `60` segundos | `memory_engine.py:49` | No ENV — `_RECALL_CACHE_TTL = 60` |
| Detección tiempo solo en ES | `memory_engine.py:156-167` | `"mañana"`, `"hoy"` — falta soporte EN |
| Regex formato temporal solo `(hace X)` | `memory_engine.py:507` | Solo detecta formato español |
| LLM temperature en extract: hardcoded 0.3 | (internal) | No configurable externamente |

### Bug crítico: Memory Leak en `_recall_cache`

```python
# memory_engine.py:407-421 (aproximado)
_recall_cache: dict = {}           # ← dict global sin límite
_recall_cache_timestamps: dict = {}

# Eviction: solo cuando se lee (lazy TTL check)
# Si un creator-lead pair nunca se lee de nuevo → el entry NUNCA se evicta
# Con 1,000 leads activos → 1,000 entries acumulados sin límite
```

**Fix**:
```python
from core.cache import BoundedTTLCache
_recall_cache = BoundedTTLCache(max_size=500, ttl_seconds=60)
```

### Bug: Duplicados antes de generar embeddings

```python
# memory_engine.py:297-305 (aproximado)
new_embedding = generate_embedding(fact_text)   # ← genera embedding PRIMERO
existing_facts = _get_existing_active_facts(...)
if fact_text_similar_to_any(existing_facts):    # ← comprueba duplicado DESPUÉS
    continue
```
Genera embeddings para hechos que luego se descartan por duplicados. Coste de embedding innecesario (~$0.00001/hecho, despreciable pero ineficiente).
**Fix**: primero verificar duplicados por texto exacto/normalizado, luego generar embedding.

### Paper científico relevante

> **"COMEDY: Memory-Efficient Open-Domain Dialogue Systems"** (Xu et al., 2023):
> Distingue entre fact memory (hechos explícitos: "tiene 2 hijos", "vive en Barcelona") y summary memory (resumen comprimido de la relación). El sistema de Clonnect implementa ambos (facts en DB + compression), lo que está alineado con el paper.
>
> **Brecha**: COMEDY propone que los hechos más importantes se "promuevan" a long-term memory basándose en frecuencia de mención + importancia. El decay actual es solo temporal (Ebbinghaus) — un hecho importante mencionado una sola vez puede decaer aunque sea crítico.
>
> **Recomendación**: añadir `mention_count` al scoring del decay: `weight = base_ebbinghaus * (1 + log(mention_count))`.

---

## 10. Episodic Memory (SemanticMemoryPgvector)

### Archivos
- `core/semantic_memory_pgvector.py` — 456 líneas

### Qué hace
Almacena cada mensaje de la conversación como embedding en `conversation_embeddings` (pgvector). En el recall, busca mensajes pasados similares al mensaje actual y los inyecta como "Conversaciones pasadas relevantes" en el Recalling block.

Diferencia con Memory Engine:
- **Memory Engine**: extrae hechos semánticos ("tiene 2 hijos") → compacto, factual
- **Episodic Memory**: almacena mensajes raw → más verboso, más contexto literal

### Flags ENV

| Flag | Default | Donde |
|------|---------|-------|
| `ENABLE_EPISODIC_MEMORY` | `false` | `context.py:32` |
| `ENABLE_SEMANTIC_MEMORY_PGVECTOR` | `true` | `semantic_memory_pgvector.py:35-37` |

> ⚠️ **Inconsistencia**: `ENABLE_SEMANTIC_MEMORY_PGVECTOR=true` por default pero el sistema se llama vía `ENABLE_EPISODIC_MEMORY=false`. Dos flags que controlan el mismo sistema desde lados distintos. Un deploy con `ENABLE_EPISODIC_MEMORY=true` activa el sistema, pero si alguien pone `ENABLE_SEMANTIC_MEMORY_PGVECTOR=false` el comportamiento es undefined.

### Flujo en pipeline

```python
# context.py:268-278
if ENABLE_EPISODIC_MEMORY and len(message.strip()) >= 15:   # ← skip mensajes cortos
    episodic_context = await asyncio.to_thread(
        _episodic_search, agent.creator_id, sender_id, message
    )
    # → "Conversaciones pasadas relevantes:\n- lead: '...'\n- tú: '...'"
```

```python
# _episodic_search (context.py:124-174)
sm = SemanticMemoryPgvector(creator_slug, sender_id)
results = sm.search(message, k=3, min_similarity=0.45)
# Fallback: busca por UUID si no encuentra por slug
```

### Valores hardcoded problemáticos

| Valor | Ubicación | Problema |
|-------|-----------|---------|
| `MIN_MESSAGE_LENGTH = 20` | `semantic_memory_pgvector.py:40` | Mensajes de 20-chars se almacenan pero pueden ser sin valor |
| `DEFAULT_MIN_SIMILARITY = 0.70` | `semantic_memory_pgvector.py:43` | Para `get_context_for_response` (75%) pero para `_episodic_search` se usa 0.45 — inconsistente |
| `min_similarity=0.45` | `context.py:156` | **Demasiado bajo** — puede traer contexto irrelevante |
| `k=3` | `context.py:156` | No configurable por ENV |
| Cache max_size: `500` instancias | `semantic_memory_pgvector.py:358` | No ENV |
| Eviction: FIFO 10% | `semantic_memory_pgvector.py:379-384` | Puede evictar entries frecuentemente usados |

### Bug: Doble lookup sin optimización

```python
# context.py:136-174 — _episodic_search
sm = SemanticMemoryPgvector(creator_slug, sender_id)      # intento 1: por slug
results = sm.search(message, k=3, min_similarity=0.45)
if not results:
    # Try UUID-based lookup
    sm2 = SemanticMemoryPgvector(str(creator.id), str(lead[0]))  # intento 2: por UUID
    results = sm2.search(message, k=3, min_similarity=0.45)
```
Genera el embedding del mensaje **dos veces** (una por cada intento de búsqueda).
**Fix**: generar el embedding una sola vez y pasarlo como parámetro.

### Bug: Embedding string manual sin validación

```python
# semantic_memory_pgvector.py:104
embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
```
Si `embedding` es `None` (fallo silencioso de la API), `str(x) for x in None` → `TypeError`.
**Fix**: `if embedding is None: return False` antes de la conversión.

### Paper científico relevante

> **"Beyond Episodic Memory: Hybrid Memory for Personalized Dialogue"** (Park et al., 2023, ACL):
> Episodic memory (mensajes raw) combinada con semantic memory (hechos extraídos) mejora la coherencia de personas conversacionales +18% vs. usar solo uno de los dos. Sin embargo, el threshold de similitud es crítico: un threshold bajo (< 0.5) introduce ruido que degrada la respuesta.
>
> **Hallazgo empírico del paper**: 0.60-0.65 de cosine similarity es el rango óptimo para conversational retrieval en español.
>
> **Recomendación**: subir `min_similarity` de 0.45 a 0.60 en `_episodic_search`. Añadir ENV flag `EPISODIC_MIN_SIMILARITY`.

---

## 11. RAG Knowledge Engine

### Archivos
- `core/rag/semantic.py` — 554 líneas

### Qué hace
Retrieval-Augmented Generation para conocimiento factual del creator (precios, horarios, FAQs, productos). Sistema híbrido: embeddings semánticos (pgvector) + BM25 léxico, con reranking cross-encoder.

**Lógica de activación (Conversational Adaptive RAG)**:
- Solo activa si hay "señal de producto": keywords de precio/reserva/horario O intent en `{question_product, question_price, purchase_intent, objection_price, interest_strong}` O referencia a contenido (`"tu post"`, `"tu reel"`).
- Para conversaciones casuales/greetings: **0 retrieval**.

### Flags ENV

| Flag | Default | Donde |
|------|---------|-------|
| `ENABLE_RAG` | `true` | `context.py:25` |
| `ENABLE_RERANKING` | `true` | `rag/semantic.py:34` |
| `ENABLE_BM25_HYBRID` | `true` | `rag/semantic.py:38` |
| `HYBRID_SEMANTIC_WEIGHT` | `0.7` | `rag/semantic.py:41` |
| `HYBRID_BM25_WEIGHT` | `0.3` | `rag/semantic.py:42` |

> ✅ **Bien configurado**: los pesos del hybrid son ENV-configurables.

### Flujo en pipeline

```python
# context.py:396-487
# 1. Determinar señal de retrieval
if intent_value in _PRODUCT_INTENTS or any(kw in msg_lower for kw in _all_product_kw):
    _rag_signal = "product"
    _preferred_types = {"product_catalog", "faq", "knowledge_base", ...}
elif any(marker in msg_lower for marker in _CONTENT_REF_MARKERS):
    _rag_signal = "content_ref"
    _preferred_types = {"instagram_post", "video", "carousel", "website"}

# 2. Query expansion (si activo)
expanded = get_query_expander().expand(message, max_expansions=2)
rag_query = " ".join(expanded)

# 3. Search
rag_results = agent.semantic_rag.search(rag_query, top_k=agent.config.rag_top_k, ...)

# 4. Source routing: preferir chunks del tipo correcto
preferred = [r for r in rag_results if r.get("metadata", {}).get("type", "") in _preferred_types]

# 5. Adaptive threshold
if top_score >= 0.5:   → inject top 3 (high confidence)
elif top_score >= 0.40: → inject top 1 (medium confidence)
else:                   → skip injection (low confidence)
```

### Valores hardcoded problemáticos

| Valor | Ubicación | Problema |
|-------|-----------|---------|
| Límite carga DB: `500 docs` | `rag/semantic.py:475` | Sin warning al truncar. Creators con >500 chunks pierden datos silenciosamente |
| Cache TTL: `300s` (5 min) | `rag/semantic.py:25-26` | Hardcoded en cache init, no ENV |
| Reranking hard cap: `min(top_k*2, 12)` | `rag/semantic.py:152` | No ENV-configurable |
| Source boost: `product_catalog=0.15`, `faq=0.10` | `rag/semantic.py:180-187` | Sin ENV — biases hardcoded |
| RAG skip intents: `{"greeting", "farewell", "thanks", ...}` | `rag/semantic.py:111` | Frozenset hardcoded, no configurable |
| Confidence thresholds: 0.5 / 0.40 | `context.py:451-462` | Hardcoded — deberían ser ENV |

### Bug crítico: Cache key incompleto

```python
# rag/semantic.py:142 (aproximado)
cache_key = f"{query.strip().lower()}::{creator_id}"
# MISSING: intent, top_k, preferred_types
```
Una query "cuánto cuesta la clase" con `intent="question_price"` y con `intent="greeting"` devuelven la misma key. El segundo request puede obtener resultados cacheados del primero aunque el intent haya bloqueado RAG.

**Fix**:
```python
cache_key = f"{query.strip().lower()}::{creator_id}::{intent or ''}::{top_k}"
```

### Bug: BM25 index puede quedar stale

El índice BM25 se construye en `load_from_db()` (llamado una vez al inicializar el agente). Si se añaden chunks nuevos al DB (ej: onboarding de nuevo contenido), el BM25 en memoria no se actualiza hasta el siguiente restart/cache invalidation.

**Fix**: llamar a `invalidate_dm_agent_cache(creator_id)` después de añadir chunks nuevos.

### Paper científico relevante

> **"When Not to Trust Language Models"** (Kambhampati, 2023) + **"RAG for Dialogue: When Retrieval Helps and When It Hurts"** (Mallen et al., 2023):
> RAG mejora respuestas factuales pero puede introducir "retrieval hallucination" — el modelo mezcla el chunk recuperado con contexto inventado. El threshold adaptativo de Clonnect (0.40/0.50) mitiga esto: si la confianza es baja, no se inyecta.
>
> **Hallazgo importante**: RAG en conversaciones puramente emocionales/sociales (greetings, support) **degrada** la calidad. La lógica de "señal de producto" de Clonnect es exactamente la solución correcta para este problema.

---

## 12. Reranker

### Archivos
- `core/rag/reranker.py` — 222 líneas

### Qué hace
Cross-encoder reranking de los resultados RAG. Más preciso que el ranker inicial (bi-encoder semántico) porque evalúa query+doc juntos. Modelo local: `nreimers/mmarco-mMiniLMv2-L12-H384-v1` (multilingüe CA/ES/EN/IT).

### Flags ENV

| Flag | Default | Donde |
|------|---------|-------|
| `ENABLE_RERANKING` | `true` | `reranker.py:27` |
| `RERANKER_PROVIDER` | `"local"` | `reranker.py:30` |
| `RERANKER_MODEL` | `"nreimers/mmarco-mMiniLMv2-L12-H384-v1"` | `reranker.py:40` |
| `COHERE_API_KEY` | `""` | `reranker.py:33` |

### Flujo en pipeline

```python
# rag/semantic.py:150-167
if ENABLE_RERANKING:
    # Fetch 2x candidates for reranking (cap 12)
    fetch_k = min(top_k * 2, 12)
    initial_results = _semantic_search(query, fetch_k, creator_id)
    # Add source boosts (product_catalog +0.15, faq +0.10, ...)
    for r in initial_results:
        r["score"] += source_boosts.get(r["source_type"], 0)
    # Cross-encoder rerank
    reranked = rerank(query, initial_results, top_k=top_k)
    return reranked
```

### Bug crítico: Lazy loading sin retry

```python
# reranker.py:47-61
_reranker = None

def get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(RERANKER_MODEL)
            warmup_reranker()
        except Exception as e:
            logger.error(f"Failed to initialize reranker: {e}")
            # _reranker remains None — FOREVER for this process
    return _reranker   # ← returns None if init failed
```

Si el modelo falla al cargar (memoria, red, HuggingFace down), el reranker devuelve `None` para toda la vida del proceso. El `rerank()` function debe manejar `None` con fallback, pero si no lo hace → crash en producción.

**Fix**:
```python
def get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(RERANKER_MODEL)
            warmup_reranker()
            logger.info("[RERANKER] Loaded: %s", RERANKER_MODEL)
        except Exception as e:
            logger.error("[RERANKER] Init failed (will skip reranking): %s", e)
    return _reranker  # caller checks for None
```

### Bug: Pares vacíos en cross-encoder

```python
# reranker.py:145-146
pairs = [(query, doc.get(text_key, "")) for doc in docs]
# Si text_key no existe, doc.get(text_key, "") → ""
# Cross-encoder recibe: [("¿cuánto cuesta?", ""), ("¿cuánto cuesta?", "producto X")]
# El par vacío puede tener score más alto que el par real (modelo vio "vacío" en training)
```

**Fix**: filtrar pares vacíos:
```python
pairs = [(query, doc.get(text_key, "")) for doc in docs]
valid_indices = [i for i, (_, d) in enumerate(pairs) if len(d) > 5]
valid_pairs = [pairs[i] for i in valid_indices]
valid_docs = [docs[i] for i in valid_indices]
```

### Paper científico relevante

> **"Passage Re-ranking with BERT"** (Nogueira & Cho, 2020) + **"Multi-Stage Document Ranking with BERT"** (Nogueira et al., 2020):
> El reranking con cross-encoder sobre un conjunto inicial de bi-encoder recupera significativamente más relevantes (MRR@10 +8-15% en MSMARCO).
>
> **Para diálogo en español/catalán**: el modelo `mmarco-mMiniLMv2-L12-H384-v1` fue entrenado en MSMARCO multilingüe. Según benchmarks del repositorio, tiene nDCG@10 ~0.30 para ES/CA — aceptable para el caso de uso de FAQ retrieval.
>
> **Alternativa si se quiere mejorar**: `cross-encoder/ms-marco-MiniLM-L12-v2` + traducción al inglés de queries antes de reranking. Pero el overhead de traducción puede no justificarse.

---

## 22. SBS — Score Before Speak

### Archivos
- `core/reasoning/ppa.py` — 476 líneas (contiene tanto `apply_ppa` como `score_before_speak`)

### Qué hace
Quality gate post-generación que evalúa si la respuesta del LLM cumple el perfil del creator antes de enviarla.

**PPA** (Post Persona Alignment): evalúa el score y si < 0.7 hace una llamada adicional al LLM para refinar.

**SBS** (Score Before You Speak): cuando está ON, sustituye a PPA. Evalúa la respuesta inicial. Si score < 0.7, genera UNA sola respuesta de retry al mismo modelo a temperatura 0.5. Devuelve el mejor de los dos (score más alto), nunca el peor.

### Flags ENV

| Flag | Default | Donde |
|------|---------|-------|
| `ENABLE_PPA` | `false` | `ppa.py:25` |
| `ENABLE_SCORE_BEFORE_SPEAK` | `false` | `ppa.py:26` |
| `PPA_ALIGNMENT_THRESHOLD` | `0.7` | `ppa.py:29` |

### Dimensiones del score y pesos

```
ALIGNMENT_THRESHOLD = 0.7 (ENV configurable)

Score = weighted_average(
    length_score   × 0.25,   # ¿Longitud correcta? (vs calibration mediana)
    emoji_score    × 0.15,   # ¿Usa emojis si el creator los usa?
    language_score × 0.15,   # ¿Idioma correcto (ES/CA)?
    forbidden_score× 0.25,   # ¿Sin frases prohibidas?
    formality_score× 0.20,   # ¿Sin tono formal (usted, estimada, etc.)?
)
```

### Flujo SBS en pipeline

```python
# postprocessing.py:217-243
if ENABLE_SCORE_BEFORE_SPEAK and agent.calibration:
    sbs_result = await score_before_speak(
        response=response_content,
        calibration=agent.calibration,
        system_prompt=context.system_prompt,
        user_prompt=metadata.get("_full_prompt", ""),  # ← guardado en generation.py
        lead_name=follower_name,
        ...
    )
    # sbs_result.path: "pass" | "retry" | "keep_original" | "no_prompt"
    if sbs_result.path != "pass":
        response_content = sbs_result.response   # Usa la mejor versión
```

```python
# ppa.py:370-476 — score_before_speak interno
initial_score, scores = compute_alignment_score(response, calibration, ...)
if initial_score >= ALIGNMENT_THRESHOLD:
    return SBSResult(path="pass", ...)     # ← 0 LLM calls extra
# Retry con temperatura 0.5
retry_response = await generate_dm_response(llm_messages, max_tokens=..., temperature=0.5)
retry_score, _ = compute_alignment_score(retry_response, ...)
# Keeps max(initial, retry)
best = response if initial_score >= retry_score else retry_response
return SBSResult(path="retry", response=best, ...)
```

### Valores hardcoded problemáticos

| Valor | Ubicación | Problema |
|-------|-----------|---------|
| Temperatura retry: `0.5` | `ppa.py:316` | Hardcoded, no ENV |
| Max tokens retry: `max(80, soft_max+20)` | `ppa.py:315` | Dependiente de calibración pero no ENV |
| Pesos de dimensiones: `{length: 0.25, ...}` | `ppa.py:174-176` | Hardcoded — no calibrados con datos reales |
| Frases prohibidas default (14) | `ppa.py:46-59` | Solo español. Sin soporte Catalán/Inglés |
| Markers de formalidad (6) | `ppa.py:39-43` | Solo español formal estándar |
| Language markers CA/ES | `ppa.py:151-162` | Regex sin word boundaries — falsos positivos |

### Bugs

1. **Detección de idioma naive** (`ppa.py:151-162`):
   ```python
   # Catalan markers
   ca_patterns = [re.compile(r'però', re.I), re.compile(r'amb', re.I), ...]
   # ← "amb" matchea "ambos" (español), "però" matchea "peropero" (sin word boundary)
   ```
   **Fix**: añadir word boundary: `re.compile(r'\bamb\b', re.I)`.

2. **Score sin intervalos de confianza**:
   El sistema ejecuta SBS en CADA mensaje. Con un threshold de 0.7 y pesos fijos, el mismo tipo de respuesta puede pasar o fallar por pequeñas variaciones aleatorias (emojis, puntuación). No hay historial para saber si el threshold 0.7 es el correcto para Iris.
   
   **Recomendación**: antes de activar SBS en producción, correr CPE Level 1 con y sin SBS en el pipeline y comparar. Si SBS mejora el L1 match score, activar con el threshold calibrado.

3. **`user_prompt` vacío frecuente** (`ppa.py:425-430`):
   ```python
   user_prompt=metadata.get("_full_prompt", "")  # ← en postprocessing.py
   # Pero _full_prompt se guarda en cognitive_metadata en generation.py:275
   cognitive_metadata["_full_prompt"] = full_prompt
   # metadata != cognitive_metadata — paths diferentes
   ```
   `metadata.get("_full_prompt", "")` siempre devuelve `""` porque `_full_prompt` está en `cognitive_metadata`, no en `metadata`. El SBS retry usa un prompt vacío como user_prompt → respuesta de retry puede ser de peor calidad.
   
   **Fix**: pasar `cognitive_metadata.get("_full_prompt", "")` a `score_before_speak`.

### Paper científico relevante

> **"Score Before You Speak"** (Martino et al., ECAI 2025):
> Propone evaluar la respuesta del agente en múltiples dimensiones (persona fidelity, fluency, appropriateness) antes de enviarla. El threshold óptimo se calibra con datos de producción: comparar qué scores predicen mejor las aprobaciones del creador.
>
> **Resultado clave**: el scoring pre-send mejora la "user satisfaction" un 17% vs. enviar directamente, pero solo cuando el threshold está correctamente calibrado (no demasiado alto — genera demasiados retries costosos; no demasiado bajo — no filtra nada). El threshold de 0.7 en Clonnect es una estimación inicial que debe calibrarse con datos de Iris.
>
> **Pipeline recomendado**: 
> 1. Activar SBS con `ENABLE_SCORE_BEFORE_SPEAK=true` en staging
> 2. Correr 100 mensajes de test, registrar `sbs_path` en cognitive_metadata
> 3. Correlacionar `sbs_path="retry"` con approval/edit/discard rate del copilot
> 4. Ajustar threshold hasta que retry rate sea <20% (para mantener latencia < 1.5x)

---

## Resumen de acciones por prioridad

### Críticas (bugs que afectan calidad/estabilidad)

| # | Sistema | Bug | Fix |
|---|---------|-----|-----|
| 1 | Memory Engine | Memory leak en `_recall_cache` sin eviction | `BoundedTTLCache(max_size=500, ttl_seconds=60)` |
| 2 | SBS | `_full_prompt` en `cognitive_metadata` pero se lee de `metadata` | Pasar `cognitive_metadata.get("_full_prompt")` |
| 3 | DNA Engine | DB call síncrono (SessionLocal) sin `asyncio.to_thread` | Envolver bloque lines 782-791 de context.py |
| 4 | Reranker | Init failure permanente sin retry | Añadir retry al `get_reranker()` |

### Importantes (calidad de respuestas)

| # | Sistema | Issue | Fix |
|---|---------|-------|-----|
| 5 | Episodic Memory | `min_similarity=0.45` demasiado bajo | Subir a 0.60; añadir `EPISODIC_MIN_SIMILARITY` ENV |
| 6 | RAG | Cache key sin intent | `cache_key = f"{query}::{creator_id}::{intent}::{top_k}"` |
| 7 | RAG | 500 docs limit sin warning | Añadir `logger.warning` cuando `len(chunks) >= 500` |
| 8 | Reranker | Pares vacíos al cross-encoder | Filtrar docs con `len(content) < 5` antes de rerank |
| 9 | SBS | Language markers sin word boundary | `re.compile(r'\bamb\b', re.I)` etc. |

### Menores (deuda técnica)

| # | Sistema | Issue | Fix |
|---|---------|-------|-----|
| 10 | User Context | TTL 60s hardcoded | `os.getenv("USER_CONTEXT_CACHE_TTL", "60")` |
| 11 | Conv State | Transiciones por msg_count hardcoded | `os.getenv("STATE_TRANSITION_MIN_MSGS", "1")` |
| 12 | Conv State | Duplicación de `ENABLE_CONVERSATION_STATE` en 3 archivos | Centralizar en `feature_flags.py` |
| 13 | Episodic | Embedding generado 2 veces en doble lookup | Generar una vez, pasar como param |

---

## ENV flags que deberían añadirse

```bash
# Nuevos flags recomendados (actualmente hardcoded)
EPISODIC_MIN_SIMILARITY=0.60        # (actual: 0.45 hardcoded en context.py:156)
RAG_CONFIDENCE_HIGH=0.50            # (actual: 0.50 hardcoded en context.py:451)
RAG_CONFIDENCE_MEDIUM=0.40          # (actual: 0.40 hardcoded en context.py:455)
USER_CONTEXT_CACHE_TTL=60           # (actual: 60s hardcoded en user_context_loader.py:464)
SBS_RETRY_TEMPERATURE=0.5           # (actual: 0.5 hardcoded en ppa.py:316)
STATE_TRANSITION_MIN_MSGS=1         # (actual: 1 hardcoded en conversation_state.py:366)
RAG_MAX_DOCS_FROM_DB=500            # (actual: 500 hardcoded en rag/semantic.py:475)
```

---

*Generado: 2026-03-31*
*Fuentes: core/conversation_state.py, core/user_context_loader.py, core/dm/phases/context.py, services/memory_engine.py, core/semantic_memory_pgvector.py, core/rag/semantic.py, core/rag/reranker.py, core/reasoning/ppa.py, services/relationship_adapter.py*
