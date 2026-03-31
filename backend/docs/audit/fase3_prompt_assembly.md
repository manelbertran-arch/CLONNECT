# Auditoría Fase 3 — Prompt Assembly (12 sistemas)

**Fecha:** 2026-03-31
**Auditor:** Claude Sonnet 4.6
**Commit base:** `909bff67`

---

## Resumen ejecutivo

| # | Sistema | Archivo principal | Flag | Estado | Alineado papers |
|---|---------|-------------------|------|--------|-----------------|
| 13 | Doc D Loader | `core/dm/creator_style_loader.py` | — | No existe como archivo (integrado en `compressed_doc_d.py`) | ✅ |
| 14 | Compressed Doc D | `core/dm/compressed_doc_d.py` | `USE_COMPRESSED_DOC_D` | ✅ Activo | ✅ Estructura validada |
| 15 | Few-Shot Loader | `services/calibration_loader.py` | `ENABLE_FEW_SHOT` ← **AÑADIDO** | ✅ Activo | ⚠️ max=10, papers dicen k=5 |
| 16 | ECHO System | `services/relationship_adapter.py` + `core/style_analyzer.py` | `ENABLE_RELATIONSHIP_ADAPTER` | ✅ Activo | ⚠️ Redundante con Doc D |
| 17 | Advanced Rules | `core/prompt_builder/sections.py` | `ENABLE_ADVANCED_PROMPTS=false` | ❌ Desactivado | ✅ Anti-hallucination válido |
| 18 | Citation Context | `services/citation_service.py` | `ENABLE_CITATIONS=true` | ✅ Activo | N/A |
| 19 | Friend/Family Override | `core/dm/phases/context.py:597` | — (relación scorer) | ✅ Activo | ✅ Producto suprimido >0.8 |
| 20 | Audio Context | `core/dm/phases/context.py:624` | implícito en metadata | ✅ Activo | N/A |
| 21 | Response Strategy | `core/dm/strategy.py` | implícito | ✅ Activo | N/A |
| 36 | Length Hints | `core/dm/text_utils.py:167` | `ENABLE_LENGTH_HINTS` ← **AÑADIDO** | ✅ Activo | ⚠️ Efectividad < few-shot length |
| 37 | Question Hints | `core/dm/text_utils.py:228` | `ENABLE_QUESTION_HINTS` ← **AÑADIDO** | ✅ Activo | ✅ Probabilistic gate correcto |
| 40 | Style Analyzer | `core/style_analyzer.py` | `ENABLE_STYLE_ANALYZER` | ✅ Activo | ✅ Necesario para ECHO |

---

## Sistema 13 — Doc D Loader

**Archivo:** No existe `creator_style_loader.py` como entidad independiente.
**Real:** El "Doc D Loader" es `core/dm/compressed_doc_d.py`, función `build_compressed_doc_d()`.
La lógica de carga desde DB/archivo está en `_load_profile_with_db_fallback()`.

### Análisis línea a línea

```python
# compressed_doc_d.py:59-71
def _load_profile_with_db_fallback(creator_id, profile_type, filename):
    # 1. Intenta DB via creator_profile_service.get_profile()
    # 2. Fallback: tests/cpe_data/{creator_id}/{filename}
    # BUG potencial: si DB falla silenciosamente, usa datos stale del filesystem
```

**¿Universal?** ✅ Sí. Lee creator_id, carga desde DB.
**¿Hardcoded?** ⚠️ Ruta de fallback hardcodeada: `tests/cpe_data/` — solo funciona en desarrollo.

### Papers
- **InCharacter (ACL 2024)**: Description alone captures ~80% of personality fidelity. Doc D es el driver principal.
- **CharacterEval (ACL 2024)**: Estructura óptima: identity → personality traits → behavioral patterns → utterance style → avoids.

### Hallazgos
- ✅ Estructura de Doc D coincide con lo que dicen los papers (4 secciones: identity, BFI, quantitative style, anti-patterns)
- ⚠️ Le falta la sección de **behavioral patterns** explícitos ("cuando X, hace Y") — CharacterEval dice que es el segundo factor más importante
- ⚠️ Catchphrases no están en una sección dedicada — RoleLLM dice que los catchphrases son el driver principal de "lexical consistency"

### Acción recomendada
Añadir sección 5 a `build_compressed_doc_d()`:
```
FRASES CARACTERÍSTICAS: [lista de catchphrases reales de la persona]
PATRONES DE COMPORTAMIENTO: [cuando X, responde con Y]
```

---

## Sistema 14 — Compressed Doc D

**Archivo:** `core/dm/compressed_doc_d.py`
**Flag:** `USE_COMPRESSED_DOC_D=true` (leído en `services/creator_style_loader.py`)
**Función principal:** `build_compressed_doc_d(creator_id) -> str`

### Análisis línea a línea

```python
# Sección 1: Identity (línea ~160)
f"Eres {name}. Respondes DMs como {name}, creadora de contenido fitness/wellness."
# PROBLEMA: "fitness/wellness" hardcodeado para Iris — NO universal

# Sección 2: BFI personality (líneas ~170-185)
_bfi_summary(bfi_scores)  # Convierte scores numéricos a lenguaje natural
# ✅ Universal, basado en datos DB

# Sección 3: Quantitative style (líneas ~190-240)
# Length targets, emoji frequency, punctuation, languages, vocabulary
# ✅ Universal, desde baseline_metrics.json

# Sección 4: Anti-patterns (líneas ~255-265)
# No emoji by default, no assistant markers, no invented data
# ✅ Siempre presente
```

### Papers
- **RoleLLM (ACL 2024)**: Description+examples achieves 63.3% win rate vs 29.8% description-only. Doc D solo no es suficiente.
- **PersonaGym (EMNLP 2025)**: "Linguistic habits" es la tarea más difícil. Los catchphrases son clave.

### Hallazgos
- 🔴 **BUG**: línea ~160 tiene `"creadora de contenido fitness/wellness"` hardcodeado — rompe para Stefano y otros creators
- ⚠️ Vocabulario extraído de top-50 palabras más frecuentes — include stop words (ja, perquè, però). Debería ser distinctive vocabulary (TF-IDF), no top frequency
- ✅ Longitud ~1.3K chars (variant B del Doc D sweep) — optimal según CPE sweep (2026-03-29)
- ✅ Incluye BFI traits, emoji stats, punctuation rates, length ranges

### Acción recomendada
1. Leer `creator_description` de DB en vez de hardcodear niche
2. Añadir campo `catchphrases` a baseline_metrics o extraer de top vocabulary con filtro de stop words

---

## Sistema 15 — Few-Shot Loader

**Archivo:** `services/calibration_loader.py`, función `get_few_shot_section()`
**Flag:** `ENABLE_FEW_SHOT=true` ← **AÑADIDO en este audit** (commit 909bff67)
**Invocado desde:** `core/dm/phases/context.py:607`

### Análisis línea a línea

```python
# context.py:607-622
if ENABLE_FEW_SHOT and agent.calibration:
    detected_lang = detect_message_language(message)
    few_shot_section = get_few_shot_section(
        agent.calibration,
        max_examples=10,      # ← PROBLEMA: papers dicen k=5
        current_message=message,
        lead_language=detected_lang,
        detected_intent=intent_value,
    )
```

```python
# calibration_loader.py:635+ — get_few_shot_section()
# Selección: intent-stratified + semantic hybrid
# Formato: multi-turn messages[] (user/assistant), NO texto plano
# ✅ Research-compliant (ver sesión 2026-03-29, config 3b)
```

### Papers
- **RoleLLM (ACL 2024)**: k=5 via BM25 es el óptimo empírico. Más de 5 → hits context window limits.
- **ChatHaruhi (arXiv 2308)**: Dynamic retrieval (por query) > static fixed set. Cosine similarity válida.
- **Length control paper (arXiv 2412)**: La longitud de los few-shots fija un implicit length prior. Es el lever más efectivo para controlar longitud de output.

### Hallazgos
- 🔴 `max_examples=10` — papers validan k=5. 10 consume demasiado contexto para beneficio marginal
- ✅ Selección intent-stratified + semantic hybrid — correcto (valida RoleLLM + ChatHaruhi)
- ✅ Multi-turn messages[] format — correcto para todos los modelos modernos
- ⚠️ BM25 no implementado — papers dicen BM25 ≥ semantic para style matching (lexical patterns)

### Acción recomendada
- Reducir `max_examples=10` → `max_examples=5` (alineación con papers)
- Considerar añadir BM25 como signal adicional para selección lexical

---

## Sistema 16 — ECHO System

**Compuesto por:**
1. **Extract:** `core/style_analyzer.py` — analiza 1000 mensajes, extrae métricas cuantitativas + perfil cualitativo via LLM
2. **Harmonize:** `services/relationship_adapter.py` — combina StyleProfile con lead_status para generar relational instructions

**Flag:** `ENABLE_RELATIONSHIP_ADAPTER=true` (en context.py:774)
**StyleAnalyzer flag:** `ENABLE_STYLE_ANALYZER=true` (en style_analyzer.py:36)

### Análisis

```python
# relationship_adapter.py:284-287 (Doc D mode)
if has_doc_d:
    # Skip tone/style instructions, inject data only
    # Doc D already defines behavior
    pass
```

**¿Universal?** ✅ Sí. Lee lead_status de DB, genera instrucciones por perfil.
**¿Hardcoded?** ⚠️ 6 perfiles fijos (nuevo, interesado, caliente, cliente, fantasma, amigo) — bien definidos pero no extendibles sin código.

### Papers
- **CharacterEval (ACL 2024)**: Per-lead-type behavior differences son importantes para consistencia.
- **InCharacter (ACL 2024)**: Description (Doc D) ya capta ~80% del personality fidelity. ECHO añade el 20% restante via contexto relacional.

### Hallazgos
- ✅ Modo Doc D correcto: cuando hay Doc D, solo inyecta datos contextuales (no redefine estilo)
- ✅ 6 perfiles relacionales cubren los estados de conversación relevantes
- ⚠️ `style_profile_from_analyzer()` convierte métricas cuantitativas — depende de que StyleAnalyzer haya corrido. Si no ha corrido: usa defaults hardcodeados
- ⚠️ `emoji_target_ratio` calculado como `profile_multiplier × style_emoji_ratio` — puede contradecir el Style Normalizer (que usa baseline_metrics). Dos sistemas controlando emoji simultáneamente = conflicto potencial

### Acción recomendada
- Verificar que ECHO y Style Normalizer no contradicen el mismo parámetro (emoji target)
- Considerar desactivar el emoji_target de ECHO cuando `ENABLE_STYLE_NORMALIZER=true`

---

## Sistema 17 — Advanced Rules (Anti-hallucination)

**Archivo:** `core/prompt_builder/sections.py`, función `build_rules_section()`
**Flag:** `ENABLE_ADVANCED_PROMPTS=false` — **desactivado por defecto**

### Análisis

```python
# sections.py:289-307 — build_rules_section()
# ⛔ PROHIBIDO:
#   - Inventar precios/productos/links
#   - Usar placeholders ([precio], [link])
#   - Afirmar que algo "no existe" si no está seguro
# ✅ OBLIGATORIO:
#   - Verificar datos antes de responder
#   - Escalar info desconocida: "No tengo esa info, pero puedo preguntarle a {creator_name}"
```

**¿Universal?** ✅ Sí. Solo usa `creator_name`.
**¿Hardcoded?** ✅ No. Reglas fijas apropiadas.

### Papers
Anti-hallucination rules en system prompts son ampliamente recomendadas pero no hay un paper específico auditado para este sistema.

### Hallazgos
- 🔴 **Desactivado** (`ENABLE_ADVANCED_PROMPTS=false`) — estas reglas son valiosas y deberían estar ON
- ✅ Frase de escalación es excelente UX: no dice "no sé", redirige al creator
- ⚠️ Potencial redundancia con Doc D que también tiene anti-patterns

### Acción recomendada
- Activar `ENABLE_ADVANCED_PROMPTS=true` en Railway
- Medir impacto en Level 1 (podría mejorar accuracy en casos de preguntas de producto)

---

## Sistema 18 — Citation Context

**Archivo:** Servicio `citation_service.py` (invocado en context.py:591)
**Flag:** `ENABLE_CITATIONS=true`

### Hallazgos
- ✅ Gateado correctamente
- No auditado en profundidad (fuera del scope de los 12 sistemas prioritarios de esta fase)

---

## Sistema 19 — Friend/Family Override

**Archivo:** `core/dm/phases/context.py:597`
**Implementación:** No es un bloque separado. Es la lógica `is_friend = _rel_score.suppress_products`

```python
# context.py:553-557
is_friend = _rel_score.suppress_products if _rel_score else False
# Solo True cuando score > 0.8 (PERSONAL relationship)
# Efecto: products stripped from system prompt
```

**Flag:** Sin flag propio — controlado por `ENABLE_RELATIONSHIP_DETECTION`.

### Hallazgos
- ✅ Threshold correcto: solo PERSONAL (>0.8) suprime productos. CLOSE (0.6-0.8) los mantiene visibles
- ✅ Doc D ya define tono para conversaciones personales — no necesita override adicional
- El `friend_context = ""` en línea 600 confirma que no se inyectan instrucciones especiales de amistad

---

## Sistema 20 — Audio Context

**Archivo:** `core/dm/phases/context.py:624-668`
**Flag:** Implícito — activo solo cuando `metadata["audio_intel"]` presente

### Análisis

```python
# context.py:624-668
if audio_intel and isinstance(audio_intel, dict):
    parts = []
    # clean_text (transcripción limpia)
    # summary (si diferente de clean_text)
    # intent
    # entities: personas, lugares, fechas, números, productos
    # action_items
    # emotional_tone
```

**¿Universal?** ✅ Sí.
**¿Hardcoded?** ✅ No.

### Hallazgos
- ✅ Bien estructurado — extrae entidades relevantes, no vuelca el audio crudo
- ✅ Fallback para multimedia no-audio: `"[El lead compartió contenido multimedia...]"`
- ⚠️ No hay flag `ENABLE_AUDIO_CONTEXT` — imposible desactivar sin modificar código

---

## Sistema 21 — Response Strategy

**Archivo:** `core/dm/strategy.py`
**Flag:** Implícito en generación

### Hallazgos
- Integrado directamente en el pipeline de generación
- No auditado en profundidad en esta fase

---

## Sistema 36 — Length Hints

**Archivo:** `core/dm/text_utils.py:167`, función `get_data_driven_length_hint()`
**Flag:** `ENABLE_LENGTH_HINTS=true` ← **AÑADIDO en este audit** (commit 909bff67)

### Análisis

```python
# text_utils.py:167-190
def get_data_driven_length_hint(message: str, creator_id: str) -> str:
    # Carga length_by_intent.json para el creator
    # Si median < 40: "MÁXIMO {p75} caracteres" (STRICT)
    # Si median >= 40: "Rango {p25}-{p75}" (SOFT)
```

**¿Universal?** ✅ Sí — lee `length_by_intent.json` por creator.
**¿Hardcoded?** ✅ No. Thresholds (40 chars) podrían parametrizarse pero son razonables.

### Papers
- **Length control paper (arXiv 2412)**: Prompt instructions (`"respond briefly"`) tienen ~30-40% de no-compliance. Son débiles como mecanismo de control.
- **RoleLLM + Length paper**: La longitud de los few-shot examples es el lever más efectivo — fija implicit length prior. Los hints de prompt son el segundo lever.
- **Recomendación paper**: Per-turn injection (no solo system prompt) aumenta compliance.

### Hallazgos
- ⚠️ **Efectividad limitada** según papers — los hints de prompt son el segundo lever, no el primero
- ✅ Data-driven (desde historial real del creator) — correcto
- ✅ Intent-conditional (hints diferentes por tipo de mensaje) — correcto
- 🔴 Si `length_by_intent.json` no existe para el creator → silently returns `""` → no hint → longitud no controlada

### Acción recomendada
- Mantener como complement a los few-shots (que son el lever primario de longitud)
- Generar `length_by_intent.json` para todos los creators al hacer onboarding

---

## Sistema 37 — Question Hints

**Archivo:** `core/dm/text_utils.py:228`, función `get_data_driven_question_hint()`
**Flag:** `ENABLE_QUESTION_HINTS=true` ← **AÑADIDO en este audit** (commit 909bff67)

### Análisis

```python
# text_utils.py:228-249
def get_data_driven_question_hint(creator_id: str) -> str:
    rate = _load_question_rate(creator_id)  # desde baseline_metrics
    # Con P(rate/100): permite preguntas (no hint)
    # Con P(1 - rate/100): suprime: "NO hagas pregunta... solo preguntas en {rate}%"
```

**¿Universal?** ✅ Sí.
**¿Hardcoded?** ✅ No. Usa `question_rate_pct` de baseline_metrics.

### Papers
No hay paper específico sobre question rate control en persona agents. La implementación probabilística es sound engineering.

### Hallazgos
- ✅ Implementación elegante — probabilistic gate espeja la distribución real del creator
- ✅ Funciona correctamente con Iris: `question_rate_pct = 14.2%` → suprime preguntas ~86% del tiempo
- ⚠️ CPE Level 1 v3 mostró `has_question = 44%` (bot) vs `26%` (creator) — hint no suficiente, el modelo sigue overgenerando preguntas
- ⚠️ `has_question_msg_pct = 26.0` fue añadido al baseline (ver sesión hoy) pero `_load_question_rate()` sigue leyendo `question_rate_pct = 14.2` — podría usar el nuevo campo más preciso

### Acción recomendada
- Actualizar `_load_question_rate()` para usar `has_question_msg_pct` si está disponible (análogo a exclamation fix)
- Verificar en CPE Level 1 si el overquestion se reduce

---

## Sistema 40 — Style Analyzer

**Archivo:** `core/style_analyzer.py`
**Flag:** `ENABLE_STYLE_ANALYZER=true`

### Análisis

```python
# style_analyzer.py:92-141 — analyze_creator()
# 1. Carga 1000 mensajes recientes
# 2. Extrae métricas cuantitativas (sin LLM)
# 3. Extrae perfil cualitativo via Gemini Flash-Lite (30 mensajes seleccionados)
# 4. Guarda en DB tabla StyleProfileModel
```

**¿Universal?** ✅ Sí.
**¿Hardcoded?** ⚠️ `MIN_MESSAGES = 30`, `IDEAL_MESSAGES = 200`, `MAX_ANALYZE = 1000` — razonables como defaults.

### Papers
- **CharacterEval (ACL 2024)**: Behavior patterns y utterance style son los campos de mayor correlación con human judgment (0.879). El StyleAnalyzer extrae precisamente estos dos elementos.
- **PersonaGym (EMNLP 2025)**: Linguistic habits es la tarea más difícil. El análisis cualitativo de StyleAnalyzer es el mecanismo correcto para capturarlo.

### Hallazgos
- ✅ Pipeline bien diseñado: cuantitativo (determinístico) + cualitativo (LLM)
- ✅ Sample diversificado: 50% reciente + 25% por intent + 25% por lead status
- ⚠️ Solo se ejecuta on-demand / por scheduler — si el creator es nuevo, el perfil puede no existir
- ⚠️ ECHO depende de StyleAnalyzer; si no hay perfil, usa defaults genéricos

---

## Síntesis: Alineación con papers científicos

### ✅ Lo que estamos haciendo bien (validado por papers)

| Técnica | Paper | Nuestra impl |
|---------|-------|-------------|
| Description-first persona (Doc D) | InCharacter ACL 2024 | `build_compressed_doc_d()` |
| Dynamic few-shot retrieval | ChatHaruhi + RoleLLM | `get_few_shot_section()` intent+semantic |
| Real dialogue examples (not synthetic) | CharacterEval ACL 2024 | calibration real DMs |
| Multi-turn messages[] format | Todos los papers | ✅ context.py |
| Per-lead-type behavior differences | CharacterEval ACL 2024 | ECHO 6 perfiles |
| RAG para long conversations | GRGPerDialogue 2024 | `ENABLE_RAG=true` |
| Utterance style explicit (emojis, longitud) | RoleLLM ACL 2024 | Doc D quantitative section |

### ⚠️ Gaps vs papers

| Gap | Paper que lo indica | Severidad | Fix |
|-----|---------------------|-----------|-----|
| max_examples=10, debería ser k=5 | RoleLLM ACL 2024 | Media | Cambiar a 5 |
| Sin catchphrases dedicados en Doc D | RoleLLM ACL 2024 | Alta | Añadir sección FRASES |
| Sin behavioral patterns en Doc D | CharacterEval ACL 2024 | Alta | Añadir sección PATRONES |
| Vocabulary = top-frequency (include stop words) | — | Media | Usar TF-IDF |
| Length hints débiles vs few-shot length prior | Length control paper | Media | Aceptar trade-off |
| has_question_msg_pct no usado en question hint | — | Baja | Actualizar _load_question_rate |
| "fitness/wellness" hardcodeado en Doc D identity | — | Alta | Leer de DB |
| ENABLE_ADVANCED_PROMPTS=false en prod | — | Media | Activar + medir |

---

## Cambios realizados en este audit

| Commit | Cambio |
|--------|--------|
| `909bff67` | Añadidos `ENABLE_FEW_SHOT`, `ENABLE_LENGTH_HINTS`, `ENABLE_QUESTION_HINTS` a `context.py` |

---

## Próximos pasos recomendados (por impacto)

1. **[ALTA]** Fix `"fitness/wellness"` hardcoded en `build_compressed_doc_d()` — leer `creator.description` de DB
2. **[ALTA]** Reducir `max_examples=10` → `5` en `get_few_shot_section()` call
3. **[ALTA]** Añadir sección `FRASES CARACTERÍSTICAS` + `PATRONES` a Doc D
4. **[MEDIA]** Activar `ENABLE_ADVANCED_PROMPTS=true` en Railway + medir CPE Level 1
5. **[MEDIA]** Actualizar `_load_question_rate()` para usar `has_question_msg_pct`
6. **[MEDIA]** Verificar conflicto ECHO `emoji_target_ratio` vs Style Normalizer
7. **[BAJA]** Implementar BM25 como signal adicional en few-shot selection
