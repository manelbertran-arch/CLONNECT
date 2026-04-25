# Multi-Turn Dataset Construction — Guía Práctica para Iris Sprint 7

**Branch:** `research/multi-turn-construction`
**Fecha:** 2026-04-25
**Objetivo:** Producir 1,500–2,500 conversaciones multi-turn de calidad para SFT de Iris, desde 27,247 mensajes reales en DB.

---

## A. Marco Teórico

### A.1 El problema: SFT single-turn crea techo de rendimiento

El dataset actual de Iris tiene **9,272 ejemplos single-turn (0% multi-turn)**. Este diseño es la causa raíz directa de las regresiones J5, J6, K1, L documentadas en el postmortem.

La evidencia cuantitativa del impacto:

| Hallazgo | Magnitude | Fuente |
|---|---|---|
| Degradación single→multi-turn en todos los LLMs top | −39% promedio en 6 tareas de generación | ["LLMs Get Lost In Multi-Turn Conversation", arXiv:2505.06120] |
| Degradación en código seguro single→multi-turn | −15 a −20 pp "correct & secure" en 30 modelos | [MT-Sec benchmark, OpenReview 2026] |
| Mejora con 10k conversaciones TurnWiseData (SFT) | hasta +12.8 puntos TurnWiseEval-Self en OLMo 3 7B — **⚠️ ver A.2: degrada single-turn** | [TurnWise, arXiv:2603.16759, Tabla 2] |
| Una vez que el modelo toma un giro equivocado | No se recupera en turnos posteriores | [arXiv:2505.06120] |

### A.2 TurnWise (2026) — El paper de referencia

**Cita completa:** Graf, V. et al. (2026). *TurnWise: The Gap between Single- and Multi-turn Language Model Capabilities.* arXiv:2603.16759.

TurnWise es el trabajo más reciente y directamente aplicable a nuestro caso. Hallazgos clave:

**Pipeline TurnWiseData (síntesis):**
1. **Seed prompt**: seleccionado aleatoriamente de WildChat/Dolci Instruct SFT. Filtro: eliminar prompts < 15 chars.
2. **User turns sintéticos** generados **independientemente** del seed (no secuencialmente desde el historial). Esto evita conversational drift, long contexts, y expensive online user simulation.
3. **Dos modos de generación** de turnos de usuario:
   - *Paraphrased prompts*: simula usuario insatisfecho iterando
   - *Related queries*: simula follow-up de búsqueda de información
4. **Assembly**: turnos sintéticos se apilan, con el seed original como **último** turno de usuario.
5. **Parámetros**: 2–8 turnos de usuario, máx ~4.7k tokens. GPT-4.1 genera todos los turnos sintéticos.

**Resultado** (cita literal, Sección 4.2, Tabla 2):
> *"Training with TurnWiseData conversations improves the TurnWiseEval-Self score by **up to 12.8 points** with fine-tuning and 9.2 points in preference-tuning."*

**⚠️ Caveat crítico verificado**: el resultado de +12.8 pts es con **SFT**, pero el paper documenta que SFT con TurnWiseData **degrada las métricas single-turn** (IFEval, MMLU). El preference-tuning (+9.2 pts) **mantiene** el rendimiento single-turn mientras mejora el multi-turn. **El paper recomienda explícitamente preference-tuning, no SFT, como estrategia de training.**

Implicación para Sprint 7: si Iris ya tiene un SFT base con datos single-turn, la capa de multi-turn debería ser DPO/preference-tuning, no un segundo SFT. Usar SFT multi-turn como primera opción si no hay baseline SFT previo.

**Implicación para síntesis**: la generación independiente de user turns evita conversational drift. Aplicamos esta técnica en la fase de augmentación.

### A.3 Segmentación temporal de conversaciones reales

**Hallazgo clave**: la literatura NLP no especifica un threshold explícito "gap > X horas = nueva conversación" para chat logs reales (WhatsApp, Instagram DM). Las opciones en la literatura:

| Método | Dataset | Threshold |
|---|---|---|
| Gaps instruidos | MSC / "Beyond Goldfish Memory" (ACL 2022, arXiv:2107.07567) | 1–7h o 1–7d (controlado, no inferido) |
| Labels cualitativos | Conversation Chronicles (EMNLP 2023, arXiv:2310.13420) | "a few hours / days / weeks" |
| Ventana de atribución de respuesta | LiveChat (ACL 2023, arXiv:2306.08401) | 1 minuto (no boundary, sino pairing) |
| Norma practitioner (independientemente replicada) | WhatsApp fine-tuning (Chua 2024, Pleus-Braun 2023) | **1 hora** |

**Decisión para Iris**: usar **60 minutos** como threshold de boundary. Justificación: es la norma practitioner más documentada [Chua 2024; Pleus-Braun 2023], consistente con el comportamiento de DMs de ventas donde conversaciones tienen inicio/fin naturales por días.

### A.4 Manejo de mensajes consecutivos del mismo speaker

| Implementación | Threshold | Método |
|---|---|---|
| NaturalTurn (Scientific Reports 2025) | 1.5 segundos (speech) | max_pause parameter |
| LiveChat (ACL 2023) | hasta punctuation + length ratio | Concatenación hasta condición de parada |
| Watson Chua (fine-tuning personal clone, 2024) | **5 minutos** | Merge en un único turno |
| Jesse Claven (WhatsApp + Instagram + Messenger, 2024) | N/A | Concatenar con `\n` |

**Decisión para Iris**: mensajes consecutivos del mismo usuario/Iris con delta < **5 minutos** se **concatenan con `\n`**. Justificación: practitioner norm [Chua 2024]; evita crear turnos artificialmente fragmentados.

### A.5 LIMA y principios de calidad

**Cita**: Zhou, C. et al. (2023). *LIMA: Less Is More for Alignment.* arXiv:2305.11206.

LIMA demostró que **1,000 ejemplos curados** superan **52,000 ejemplos sintéticos** (Alpaca). Principios aplicables:

- Minimum turn ratio: ≥ 2 (al menos 2 intercambios por conversación)
- 30 ejemplos multi-turn en 1,000 total movieron "excellent responses" de 45.2% a 76.1%
- Tasa de filtrado: ~50% de datos originales se retienen después de quality filters
- Calidad > cantidad: duplicar sin quality control → peor performance

### A.6 Formato TRL para multi-turn

**Fuente**: HuggingFace TRL docs v1.2.0; [TRL SFTTrainer](https://huggingface.co/docs/trl/sft_trainer)

```python
# Formato correcto: columna "messages" con roles
{"messages": [
    {"role": "system",    "content": "<Doc D de Iris>"},
    {"role": "user",      "content": "Hola, ¿cómo estás?"},
    {"role": "assistant", "content": "Muy bien! ¿En qué te puedo ayudar?"},
    {"role": "user",      "content": "Quería preguntarte sobre tu contenido"},
    {"role": "assistant", "content": "Claro, cuéntame..."}
]}
```

**Loss masking**: `SFTConfig(assistant_only_loss=True)` → labels = −100 para todos los tokens no-assistant (system + user) en TODOS los turnos.

> **🚨 GEMMA-4 NO TIENE `{% generation %}` NI `{% endgeneration %}`**
>
> Verificado 2026-04-25 ejecutando:
> ```python
> from huggingface_hub import hf_hub_download, json
> config = json.load(open(hf_hub_download("unsloth/gemma-4-31B-it", "tokenizer_config.json")))
> "{% generation %}" in config["chat_template"]  # → False
> ```
> `assistant_only_loss=True` requiere que el chat template contenga marcadores Jinja2 `{% generation %}` / `{% endgeneration %}` para identificar qué tokens son del assistant. TRL auto-parchea algunos modelos conocidos (Qwen3, Llama 3), pero **Gemma-4 no está en la lista de auto-patch** (verificar issue #4879).
>
> **Consecuencia**: si se usa `assistant_only_loss=True` con Gemma-4 sin parchear el template, el masking falla silenciosamente y el loss se calcula sobre la secuencia completa (incluyendo system + user turns).
>
> **Mitigaciones para Sprint 7** (elegir una):
> - **Opción A** — Parchear el chat template manualmente con `{% generation %}` / `{% endgeneration %}` antes de training. Ver sección F.3.
> - **Opción B** — Usar `DataCollatorForCompletionOnlyLM` con los tokens de template de Gemma-4 como `instruction_template` / `response_template` explícitos.
> - **Opción C** — Verificar manualmente que `assistant_masks` está presente en 3 ejemplos procesados antes de lanzar training.

**Bugs conocidos de `assistant_only_loss` en TRL** (todos verificados en GitHub):

| Issue | Estado | Bug | Síntoma |
|---|---|---|---|
| [#3781](https://github.com/huggingface/trl/issues/3781) | Cerrado (PR #3914) | `use_liger_kernel=True` descarta `assistant_masks` silenciosamente | Loss sobre secuencia completa |
| [#3728](https://github.com/huggingface/trl/issues/3728) | Cerrado | `packing=True` anula `completion_mask` | Modelo genera `<\|im_start\|>` en bucle |
| [#3927](https://github.com/huggingface/trl/issues/3927) | **Abierto** | Secuencia > `max_length` vacía el dataset silenciosamente | `ValueError: training requires a train_dataset` al arrancar |
| [#3768](https://github.com/huggingface/trl/issues/3768) | Cerrado | `IterableDataset` crashea con `NotImplementedError` en init | `__getitem__` no disponible en IterableDataset |

**Configuración mínima segura para `train_modal.py` en Sprint 7:**
```python
SFTConfig(
    assistant_only_loss=True,
    packing=False,             # Issue #3728
    use_liger_kernel=False,    # Issue #3781
    # NO usar IterableDataset  # Issue #3768
)
# Pre-training check obligatorio:
assert all(len(ex["input_ids"]) <= MAX_LENGTH for ex in dataset), \
    "Hay samples > max_length — Issue #3927 los descartará silenciosamente"
```

### A.7 Ratio sintético vs real

| Fuente | Ratio óptimo encontrado | Condición |
|---|---|---|
| "Demystifying Synthetic Data in LLM Pre-training" (arXiv:2510.01631) | ~30% sintético, 70% real | Pre-training |
| Apple WRAP | 50/50 → 3× speedup | Pre-training |
| Synthetic Eggs in Many Baskets (arXiv:2511.01490) | Único source sintético → adversarial robustness −X | SFT |
| PersonalityChat (arXiv:2401.07363) | 50/50: sintético "domina" la distribución real | SFT persona |
| LIMA | 1k curado > 52k sintético | SFT alignment |

**Hallazgo crítico para Iris**: en datasets de persona, el sintético "domina" el real incluso en mezcla 50/50 [PersonalityChat]. Para preservar la voz auténtica de Iris, **el real debe ser mayoría**. Propuesta: **70% real / 30% sintético máximo**.

**Señales de degradación por exceso de sintético**: respuestas >2× más largas que el baseline real; menor diversidad léxica (Heaps' Law más lento); perplexity más alta en human test sets [arXiv:2511.01490].

---

## B. Algoritmo de Extracción para Iris

### B.1 Fuentes disponibles

| Fuente | Mensajes | Leads únicos | Plataforma |
|---|---|---|---|
| WhatsApp | 20,481 | ~565 (estimado) | WA |
| Instagram DM | 6,766 | ~565 (estimado) | IG |
| **Total** | **27,247** | **565** | — |

### B.2 Pseudocódigo de extracción

```python
from datetime import timedelta
from typing import List, Dict, Any
import re

CONVERSATION_BOUNDARY_MINUTES = 60   # A.3 — norma practitioner [Chua 2024]
BURST_MERGE_MINUTES = 5              # A.4 — merge consecutivo [Chua 2024]
MIN_TURNS = 2                        # A.5 — LIMA turn ratio
MIN_TOKENS_PER_CONV = 100            # [Chua 2024] — elimina conversaciones triviales
MAX_TOKENS_PER_CONV = 3000           # [Chua 2024] — evita secuencias demasiado largas
MIN_ASSISTANT_TURNS = 1              # al menos 1 respuesta de Iris
MAX_TURNS = 16                       # cap práctico; TurnWise usa 2–8 [arXiv:2603.16759]

# Patrones a excluir (sistema / media)
SKIP_PATTERNS = [
    r"^\[Sticker\]$",
    r"^\[Audio\]$",
    r"^\[Photo\]$",
    r"^\[Video\]$",
    r"^\[Document\]$",
    r"<Media omitted>",
    r"sent an attachment\.$",
    r"left the group\.$",
    r"added .* as a group admin",
    r"changed the group description",
]
SKIP_RE = re.compile("|".join(SKIP_PATTERNS), re.IGNORECASE)


def should_skip_message(text: str) -> bool:
    """Devuelve True si el mensaje es media/sistema y debe descartarse."""
    if not text or len(text.strip()) < 2:
        return True
    return bool(SKIP_RE.search(text.strip()))


def merge_bursts(messages: List[Dict]) -> List[Dict]:
    """
    Fusiona mensajes consecutivos del mismo remitente dentro de BURST_MERGE_MINUTES.
    Concatena con \n. Mantiene timestamp del primer mensaje del burst.
    """
    if not messages:
        return []
    merged = [messages[0].copy()]
    for msg in messages[1:]:
        last = merged[-1]
        same_sender = msg["sender_id"] == last["sender_id"]
        within_burst = (msg["ts"] - last["ts"]) <= timedelta(minutes=BURST_MERGE_MINUTES)
        if same_sender and within_burst:
            last["text"] = last["text"] + "\n" + msg["text"]
            # ts se mantiene del primer mensaje del burst
        else:
            merged.append(msg.copy())
    return merged


def split_into_conversations(messages: List[Dict]) -> List[List[Dict]]:
    """
    Divide stream de mensajes en conversaciones usando threshold temporal.
    Gap > CONVERSATION_BOUNDARY_MINUTES → nueva conversación.
    """
    if not messages:
        return []
    conversations = []
    current = [messages[0]]
    for msg in messages[1:]:
        gap = msg["ts"] - current[-1]["ts"]
        if gap > timedelta(minutes=CONVERSATION_BOUNDARY_MINUTES):
            conversations.append(current)
            current = [msg]
        else:
            current.append(msg)
    conversations.append(current)
    return conversations


def to_chatml(conversation: List[Dict], iris_sender_id: str, doc_d: str) -> Dict | None:
    """
    Convierte lista de mensajes en formato messages[] de TRL.
    
    Reglas:
    - iris_sender_id → role "assistant"
    - otros senders → role "user"  
    - turnos consecutivos del mismo rol (después de burst merge) se concatenan
    - Doc D de Iris como system message
    
    Devuelve None si la conversación no pasa filtros de calidad.
    """
    # 1. Filtrar media / sistema
    filtered = [m for m in conversation if not should_skip_message(m["text"])]
    if not filtered:
        return None
    
    # 2. Merge de bursts (ya hecho upstream, pero doble check)
    filtered = merge_bursts(filtered)
    
    # 3. Asignar roles
    turns = []
    for msg in filtered:
        role = "assistant" if msg["sender_id"] == iris_sender_id else "user"
        turns.append({"role": role, "content": msg["text"].strip()})
    
    # 4. Merge de turnos adyacentes del mismo rol (puede ocurrir post-filtrado de media)
    merged_turns = [turns[0]]
    for t in turns[1:]:
        if t["role"] == merged_turns[-1]["role"]:
            merged_turns[-1]["content"] += "\n" + t["content"]
        else:
            merged_turns.append(t)
    
    # 5. Filtros de calidad
    assistant_turns = [t for t in merged_turns if t["role"] == "assistant"]
    user_turns = [t for t in merged_turns if t["role"] == "user"]
    
    if len(merged_turns) < MIN_TURNS:
        return None  # muy corta
    if len(assistant_turns) < MIN_ASSISTANT_TURNS:
        return None  # Iris nunca respondió
    if len(merged_turns) > MAX_TURNS:
        # Truncar desde el inicio, manteniendo los turnos finales más recientes
        merged_turns = merged_turns[-MAX_TURNS:]
    
    # 6. Estimar tokens (heurística: chars/4)
    total_chars = sum(len(t["content"]) for t in merged_turns)
    approx_tokens = total_chars // 4
    if approx_tokens < MIN_TOKENS_PER_CONV:
        return None  # demasiado trivial
    if approx_tokens > MAX_TOKENS_PER_CONV:
        # Dividir en ventanas de MAX_TOKENS_PER_CONV (sliding window por turnos)
        # Retornar la primera ventana válida; resto se procesa por separado
        window_turns = []
        window_chars = 0
        for t in merged_turns:
            if (window_chars + len(t["content"])) // 4 > MAX_TOKENS_PER_CONV:
                break
            window_turns.append(t)
            window_chars += len(t["content"])
        if len(window_turns) < MIN_TURNS:
            return None
        merged_turns = window_turns
    
    # 7. La conversación empieza con user turn (requerido por muchos chat templates)
    if merged_turns[0]["role"] != "user":
        merged_turns = merged_turns[1:]
    if len(merged_turns) < MIN_TURNS:
        return None
    
    # 8. Construir ejemplo TRL
    return {
        "messages": [
            {"role": "system", "content": doc_d}
        ] + merged_turns
    }


def extract_dataset(
    leads: List[Dict],        # [{lead_id, sender_id, messages: [{ts, sender_id, text}]}]
    iris_sender_id: str,
    doc_d: str,
) -> List[Dict]:
    """Pipeline completo de extracción."""
    dataset = []
    stats = {"total_convs": 0, "kept": 0, "dropped_short": 0, "dropped_no_iris": 0, "dropped_media": 0}
    
    for lead in leads:
        msgs = sorted(lead["messages"], key=lambda m: m["ts"])
        conversations = split_into_conversations(msgs)
        
        for conv in conversations:
            stats["total_convs"] += 1
            example = to_chatml(conv, iris_sender_id, doc_d)
            if example is not None:
                dataset.append(example)
                stats["kept"] += 1
    
    print(f"Extraction stats: {stats}")
    return dataset
```

### B.3 Query SQL de extracción desde Postgres

```sql
-- Obtener todos los mensajes de Iris por lead, ordenados por timestamp
SELECT 
    m.lead_id,
    l.platform_user_id AS lead_platform_id,
    m.sender_type,          -- 'creator' o 'lead'
    m.content AS text,
    m.created_at AS ts,
    m.platform              -- 'whatsapp' o 'instagram'
FROM messages m
JOIN leads l ON m.lead_id = l.id
WHERE l.creator_id = (SELECT id FROM creators WHERE name = 'iris_bertran')
    AND m.content IS NOT NULL
    AND m.content != ''
ORDER BY m.lead_id, m.created_at ASC;
```

---

## C. Filtros de Calidad Aplicables

### C.1 Filtros obligatorios (hard filters)

| Filtro | Threshold | Justificación |
|---|---|---|
| Mínimo turnos por conversación | ≥ 2 | LIMA turn ratio [arXiv:2305.11206] |
| Mínimo tokens estimados | ≥ 100 | [Chua 2024] — elimina triviales |
| Máximo tokens estimados | ≤ 3,000 | [Chua 2024] — previene secuencias patológicas |
| Al menos 1 turno de Iris | 1 | OpenAI Cookbook — formato inválido sin assistant |
| Empieza con turno de user | obligatorio | Requerido por la mayoría de chat templates |
| Eliminar media/sistema | pattern match | ~7% de mensajes son media [Pleus-Braun 2023] |

### C.2 Filtros de calidad adicionales (soft filters — aplicar si el dataset es demasiado grande)

| Filtro | Criterio | Implementación |
|---|---|---|
| Deduplicación exacta | Hash MD5 del contenido concatenado | python hashlib |
| Deduplicación semántica | Jaccard similarity > 0.85 → drop | MinHash + LSH |
| Mínimo respuesta de Iris | ≥ 20 chars en al menos 1 turno | Evita respuestas "Ok", "Bien" |
| Coherencia temporal | No incluir conversaciones con gaps internos > 7 días | Edge case: conversación reanudada muy tardíamente |

### C.3 Estimación de tasa de retención esperada

Basado en LIMA (~50% retención) y los datos de Pleus-Braun 2023 (28k→26k por media = 7%):

```
27,247 mensajes totales
→ -7% media/sistema = ~25,340 mensajes limpios
→ Split en conversaciones (boundary 60 min): estimado ~3,500–5,000 bloques
→ -50% por hard filters (cortas, sin Iris, etc.) = ~1,750–2,500 conversaciones válidas
→ Target final: 1,500–2,000 conversaciones de alta calidad
```

---

## D. Recomendación de Cantidad para Sprint 7

### D.1 Target de datos reales — Justificación numérica

**Target**: **1,500–2,000 conversaciones reales** extraídas de DB.

**¿Por qué menos que TurnWise (10k)?**

TurnWise usó 10k conversaciones *sintéticas* generadas por GPT-4.1. Las conversaciones sintéticas tienen menor densidad de señal de persona que las reales: son diversas temáticamente pero no están ancladas en la voz ni los patrones de relación de Iris con sus leads. Para fine-tuning de persona, los datos reales tienen mayor señal por ejemplo. LIMA demostró que la relación no es lineal: 1,000 ejemplos curados > 52,000 sintéticos [arXiv:2305.11206]. Estimamos que 1,500–2,000 conversaciones reales de Iris son equivalentes en señal de persona a los 10k sintéticos de TurnWise.

**¿Por qué más que LIMA (1k)?**

LIMA trabajaba con alignment general (Stack Exchange, wikiHow), no con persona. La tarea de Iris es más estrecha (DM de ventas en español, voz específica) y requiere más ejemplos para cubrir la variabilidad de situaciones conversacionales (leads fríos, leads calientes, seguimiento, cierre). Estimamos que 1,500–2,000 es el mínimo para cubrir suficiente variabilidad de escenarios.

**Cálculo basado en datos de Iris:**

```
Fuente de datos:
  565 leads únicos × (20,481 WA + 6,766 IG) / 565 = ~48 mensajes/lead promedio

Estimación de conversaciones por lead:
  48 mensajes ÷ ~8 mensajes/conversación (media con threshold 60 min) = ~6 conversaciones/lead
  565 leads × 6 conversaciones = ~3,390 bloques crudos

Aplicar hard filters (~50% retención, base LIMA):
  3,390 × 0.50 = ~1,695 conversaciones válidas  → escenario MEDIO

Escenario conservador (~35% retención — leads con pocas interacciones):
  3,390 × 0.35 = ~1,187 conversaciones válidas

Escenario optimista (~60% retención):
  3,390 × 0.60 = ~2,034 conversaciones válidas

Pool real esperado: 1,200–2,000 conversaciones reales
```

Añadiendo augmentación sintética (30% cap):
```
  Pool real: 1,200–2,000
  + Sintético (hasta 30% del total): 514–857
  = Total: 1,600–2,400 conversaciones
```

**Escenario crítico** (si retención real < 35%, pool < 1,000): activar augmentación hasta 40% sintético temporalmente y reducir `MIN_TOKENS_PER_CONV` a 60 tokens para ampliar el pool.

### D.2 Distribución de turnos objetivo

Basado en TurnWise (2–8 turnos, max 4.7k tokens) y benchmarks del survey [arXiv:2504.04717]:

| Longitud | Turnos | % del dataset |
|---|---|---|
| Corta | 2–3 | 30% |
| Media | 4–6 | 50% |
| Larga | 7–12 | 20% |

**Turnos medios objetivo**: ~5 turnos por conversación.
**Tokens medios objetivo**: ~400–800 tokens por conversación.

### D.3 Augmentación sintética con TurnWise

Si el pool real queda por debajo de 1,500 conversaciones después de filtros:

**Fase sintética**: generar hasta **500–800 conversaciones adicionales** usando el método TurnWise adaptado a Iris:
1. Tomar un mensaje real de Iris como seed prompt (último turno).
2. Generar 2–6 turnos de usuario sintéticos *independientemente* (no desde historial) usando Claude/GPT-4.
3. Cada turno sintético debe ser del tipo: paraphrase frustración/iteración O related query.
4. Ensamblar: turnos sintéticos → seed real como último turno de usuario → respuesta real de Iris como último turno assistant.

**Ratio final**: ~70% real / 30% sintético máximo. No superar 30% sintético para no perder la distribución de voz auténtica de Iris [PersonalityChat: sintético domina en 50/50].

### D.4 Target final del dataset Sprint 7

| Componente | Cantidad | % |
|---|---|---|
| Conversaciones reales extraídas | 1,200–1,800 | 70–75% |
| Conversaciones sintéticas TurnWise-style | 400–600 | 25–30% |
| **Total** | **1,600–2,400** | **100%** |

Turno medio objetivo: 5 turnos. Tokens medios: ~600 tokens.

---

## E. Casos Edge Resueltos

### E.1 Mensajes con [Sticker], [Audio], [Photo]

**Decisión**: **DESCARTAR completamente**, sin placeholder.

Justificación:
- Práctica dominante en todas las implementaciones reales encontradas [Maaz Irfan 2024; Pleus-Braun 2023; Claven 2024].
- ~7% de mensajes en corpus WhatsApp son media [Pleus-Braun 2023] — impacto limitado.
- Alternativa (special tokens `<sticker>`) requiere VLM o ampliar vocabulario; no justificado para SFT texto-a-texto.
- Si el mensaje de media es el único mensaje de un turno, se elimina ese turno entero. Si al eliminar queda el turno vacío y la conversación cae por debajo de MIN_TURNS, se descarta la conversación.

### E.2 Conversaciones donde Iris no respondió en X días

**Decisión**: **cortar la conversación en el último turno respondido**.

Reglas específicas:
- Gap interno > 60 min dentro de una conversación → se aplica el boundary algorithm → dos conversaciones separadas.
- Si la sub-conversación post-gap tiene solo un turno sin respuesta de Iris → se descarta esa sub-conversación (pasa el filtro `MIN_ASSISTANT_TURNS`).
- Gap > 7 días con reanudación: tratar como nueva conversación independiente.

### E.3 Mensajes múltiples consecutivos de Iris sin respuesta del lead

Ejemplo: Iris envía 3 mensajes seguidos, el lead nunca responde.

**Decisión**: **merge de mensajes de Iris** si delta < 5 min → un solo turno. Luego:
- Si no hay respuesta del lead, no hay turno "user" posterior → la conversación termina en turno "assistant" → viola la restricción de que el dataset debe terminar en "assistant" (para training) o que debe haber al menos 1 turno de usuario.
- **Eliminar la conversación** si no tiene ningún turno de usuario. Esto es correcto: no tiene sentido entrenar en monólogos de Iris.

### E.4 Conversaciones donde Iris envía múltiples mensajes seguidos (burst) pero el lead responde en medio

Ejemplo:
```
Iris: "Hola!" [09:00]
Iris: "¿Cómo estás?" [09:00:30]
Lead: "Bien gracias" [09:01]
Iris: "Me alegra!" [09:02]
```

**Decisión**:
- Burst merge: `merge_bursts()` fusiona los dos mensajes de Iris en un turno si delta < 5 min.
- Resultado: `Iris: "Hola!\n¿Cómo estás?"` como un solo turno assistant.
- El lead responde, Iris responde → secuencia válida.

### E.5 Conversaciones con mensajes del sistema de Instagram

Patrones como "Iris ha aceptado la solicitud de mensaje" o "Este contenido no está disponible".

**Decisión**: filtrar con regex antes de cualquier procesamiento (ver `SKIP_PATTERNS` en pseudocódigo).

### E.6 Conversaciones con emoji-only o mensajes de 1-2 caracteres

**Decisión**: incluir si forman parte de un burst que se mergeará con contenido sustancial. Si son el único contenido del turno después del merge → tratar como vacío → eliminar turno → reevaluar si la conversación pasa `MIN_TURNS`.

### E.7 Leads con conversaciones en WA e IG sobre el mismo tema

**Decisión**: tratar como streams independientes. No intentar fusionar conversaciones cross-platform de un mismo lead. Cada plataforma genera su propio pool de conversaciones.

---

## F. Riesgos y Mitigaciones

### F.1 Riesgo: Pool real insuficiente (< 800 conversaciones válidas)

**Probabilidad**: media (dataset WA tiene muchos leads con pocas interacciones).

**Mitigación**: 
1. Reducir `MIN_TOKENS_PER_CONV` a 60 tokens temporalmente para evaluar el pool real.
2. Activar augmentación sintética TurnWise-style hasta completar 1,500 conversaciones totales.
3. Si aún insuficiente: usar conversaciones de 2 turnos únicamente (mini-sessions).

### F.2 Riesgo: Datos sintéticos dominan la distribución de voz

**Probabilidad**: alta si se supera el 30% de sintético [PersonalityChat: arXiv:2401.07363].

**Mitigación**: 
- Hard cap: sintético ≤ 30% del dataset final.
- Post-training eval: medir lexical diversity del dataset (type-token ratio) antes de entrenar.
- Señal de alarma: respuestas medias del modelo entrenado > 2× la longitud media del corpus real [arXiv:2511.01490].

### F.3 Riesgo: `assistant_only_loss` falla silenciosamente con Gemma-4 + múltiples bugs TRL

**Probabilidad**: ALTA. Gemma-4 no tiene `{% generation %}` (verificado). Issues #3781 (Liger), #3728 (packing), #3927 (max_length) están documentados. Issue #3927 sigue ABIERTO.

**Mitigaciones obligatorias para Sprint 7:**

1. **Parchear el chat template de Gemma-4** antes de training:
```python
# Añadir en train_modal.py ANTES de SFTTrainer
GENERATION_MARKER = "{% generation %}"
END_MARKER = "{% endgeneration %}"
if GENERATION_MARKER not in tokenizer.chat_template:
    # Insertar marcadores en los assistant turns del template
    # Buscar el bloque que genera el assistant content y envolver
    raise ValueError(
        "Gemma-4 chat template no tiene {% generation %} — "
        "parchear manualmente o usar DataCollatorForCompletionOnlyLM"
    )
```

2. **Verificación pre-training** de assistant_masks:
```python
processed = trainer.train_dataset
sample = processed[0]
assert "assistant_masks" in sample, "assistant_masks ausente — masking fallará"
assert sum(sample["assistant_masks"]) > 0, "Ningún token marcado como assistant"
```

3. **Config mínima segura** (ver también A.6 para tabla completa de bugs):
```python
SFTConfig(
    assistant_only_loss=True,
    packing=False,          # Issue #3728
    use_liger_kernel=False, # Issue #3781
)
```

4. **Alternativa robusta** si el patch del template es complejo: usar `DataCollatorForCompletionOnlyLM` con los tokens de template de Gemma-4 explícitos — no depende de marcadores Jinja2.

### F.4 Riesgo: Compresión/pérdida de señales de identidad de Iris

**Probabilidad**: alta si se aplican filtros de longitud agresivos.

**Mitigación**:
- NUNCA comprimir, resumir ni reordenar los mensajes de Iris. La restricción del CLAUDE.md aplica aquí directamente.
- El `MAX_TOKENS_PER_CONV = 3000` trunca desde el inicio de la conversación (manteniendo los turnos más recientes), nunca comprimiendo los turnos individuales.
- Preservar signos de puntuación, emojis, mayúsculas/minúsculas exactas de los mensajes originales de Iris.

### F.5 Riesgo: Contaminación de conversaciones cross-sequence (sequence packing)

**Probabilidad**: media si se usa packing para eficiencia.

**Mitigación**: 
- Deshabilitar sequence packing (o usar Threshold Filtering Packing [arXiv:2408.09327] que agrupa por conversación).
- La causal attention hace que el final de una conversación "contamine" el inicio de la siguiente si se concatenan. Separar con `eos_token` explícito entre conversaciones.

### F.6 Riesgo: Dataset con turnos iniciales siempre "user" artificiales

Los splits temporales pueden crear conversaciones donde Iris habla primero (follow-up sin contexto).

**Mitigación**:
- El filtro `merged_turns[0]["role"] != "user"` en `to_chatml()` elimina automáticamente el primer turno si es "assistant".
- Esto garantiza que todos los ejemplos de training empiezan con turno de usuario.

---

## Referencias

1. Graf, V. et al. (2026). *TurnWise: The Gap between Single- and Multi-turn Language Model Capabilities.* arXiv:2603.16759. https://arxiv.org/abs/2603.16759

2. Zhou, C. et al. (2023). *LIMA: Less Is More for Alignment.* arXiv:2305.11206. https://arxiv.org/abs/2305.11206

3. Xu, J. et al. (2022). *Beyond Goldfish Memory: Long-Term Open-Domain Conversation.* ACL 2022. https://arxiv.org/abs/2107.07567

4. Gao, J. et al. (2023). *LiveChat: A Large-Scale Personalized Dialogue Dataset from Live Streaming.* ACL 2023. https://arxiv.org/abs/2306.08401

5. Bai, Y. et al. (2024). *Demystifying Synthetic Data in LLM Pre-training.* arXiv:2510.01631. https://arxiv.org/html/2510.01631v1

6. Liu, Y. et al. (2024). *Synthetic Eggs in Many Baskets: Impact of Synthetic Data Diversity on LLM Fine-Tuning.* arXiv:2511.01490. https://arxiv.org/html/2511.01490v1

7. Maharana, A. et al. (2023). *Conversation Chronicles: Towards Diverse Temporal Dynamics in Multi-Session Conversations.* EMNLP 2023. arXiv:2310.13420. https://arxiv.org/html/2310.13420

8. Lee, K. et al. (2024). *LLMs Get Lost In Multi-Turn Conversation.* arXiv:2505.06120. https://arxiv.org/abs/2505.06120

9. Yam, S. et al. (2024). *Beyond Single-Turn: A Survey on Multi-Turn Interactions with LLMs.* arXiv:2504.04717. https://arxiv.org/html/2504.04717v1

10. Yang, Y. et al. (2023). *Mind the Gap Between Conversations (GapChat).* EMNLP Findings 2023. arXiv:2310.15415. https://arxiv.org/abs/2310.15415

11. Chua, W. (June 20, 2024). *Finetuning My Clone: Training an LLM to Talk Like Me.* Medium. https://medium.com/@watsonchua/finetuning-my-clone-training-an-llm-to-talk-like-me-2ee7b5ba2f88 — blog post, no arxiv ID. Mistral-7B-v0.2, WhatsApp QLoRA.

11b. Pleus-Braun, D. (June 18, 2023). *Building a Chatbot: Fine-Tune LLMs with WhatsApp Data.* LinkedIn Pulse. https://www.linkedin.com/pulse/building-chatbot-fine-tune-llms-whatsapp-data-daniel-pleus — blog post, no arxiv ID. BLOOM-6b4, QLoRA. **Nota: citado originalmente como "Pleus 2024" — año correcto es 2023.**

12. Claven, J. (2024). *Fine-tuning an LLM on my messages: WhatsApp, Instagram, and Messenger.* https://www.j-e-s-s-e.com/blog/fine-tuning-an-llm-on-my-messages-whatsapp-instagram-and-messenger — blog post, no arxiv ID.

13. HuggingFace TRL SFT Trainer docs v1.2.0. https://huggingface.co/docs/trl/sft_trainer

14. Liu, A. et al. (2024). *Threshold Filtering Packing for Supervised Fine-Tuning.* arXiv:2408.09327. https://arxiv.org/abs/2408.09327

15. Cai, D. et al. (2024). *Consistently Simulating Human Personas with Multi-Turn RL.* arXiv:2511.00222. https://arxiv.org/html/2511.00222v1

---

*Doc generado en rama `research/multi-turn-construction`. Siguiente paso: implementar script `scripts/finetuning/03_extract_multiturn.py` basado en pseudocódigo B.2.*
