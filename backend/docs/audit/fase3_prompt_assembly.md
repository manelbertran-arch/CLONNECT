# Auditoría Fase 3 — Prompt Assembly (12 sistemas)

**Fecha:** 2026-03-31
**Auditor:** Claude Sonnet 4.6
**Commit base:** `909bff67`
**Commit cierre:** `6642b856`
**Estado:** COMPLETO — todos los fixes aplicados

---

## Tabla de estado final (post-fix)

| # | Sistema | Archivo principal | Flag | Bugs encontrados | Bugs corregidos | Paper principal | Recomendación |
|---|---------|-------------------|------|-----------------|-----------------|-----------------|---------------|
| 13 | Doc D Loader | `core/dm/compressed_doc_d.py` | — (integrado) | `MEMO_COMPRESSION_PROMPT` hardcodeado "Iris Bertran" + "fitness" en `memory_engine.py` | ✅ Convertido a `{creator_name}` placeholder — commit `cdc9...` | InCharacter ACL 2024 | **KEEP** |
| 14 | Compressed Doc D | `core/dm/compressed_doc_d.py` | `USE_COMPRESSED_DOC_D` | Identity line hardcodeada "fitness/wellness"; catchphrases ausentes; stop words en vocab | ✅ Identity fix: genérica; ✅ Catchphrases: `_get_catchphrases()` añadida — commit `1d555fe6` | RoleLLM ACL 2024, PersonaGym EMNLP 2025 | **KEEP** |
| 15 | Few-Shot Loader | `services/calibration_loader.py` | `ENABLE_FEW_SHOT` ← añadido | `max_examples=10` (papers dicen k=5); sin flag de control | ✅ Flag añadido; ✅ `max_examples=5` — commit `909bff67` | RoleLLM ACL 2024, ChatHaruhi arXiv 2308 | **KEEP** |
| 16 | ECHO System | `services/relationship_adapter.py` | `ENABLE_RELATIONSHIP_ADAPTER` | `emoji_target_ratio` computa valor nunca consumido → conflicto potencial con Style Normalizer | ✅ Documentado como unused — commit `6642b856` | CharacterEval ACL 2024 | **OPTIMIZE** (desactivado en Railway, activar solo con ablation) |
| 17 | Advanced Rules | `core/prompt_builder/sections.py` | `ENABLE_ADVANCED_PROMPTS=false` | Desactivado; contenido válido pero redundante con Doc D REGLAS CRÍTICAS | ✅ Evaluado: no activar (PersonaGym: prompts cortos > verbosos) — no-op correcto | PersonaGym EMNLP 2025 | **KEEP** (flag=false es correcto) |
| 18 | Citation Context | `services/citation_service.py` | `ENABLE_CITATIONS=true` | Ninguno identificado en este audit | — | N/A | **KEEP** |
| 19 | Friend/Family Override | `core/dm/phases/context.py` | implícito en `ENABLE_RELATIONSHIP_DETECTION` | `_rel_type` inyectaba strategy hints por relación → prompt injection; `lead_facts` siempre `[]` | ✅ `_rel_type=""` hardcodeado; ✅ parser `memory_context → lead_facts` — sesión previa | CharacterEval ACL 2024 | **KEEP** |
| 20 | Audio Context | `core/dm/phases/context.py` | implícito (metadata) | Sin flag para desactivar | Sin fix (fuera de scope) — ⚠️ pendiente | N/A | **KEEP** |
| 21 | Response Strategy | `core/dm/strategy.py` | implícito | `RECURRENTE` strategy usa "entusiasmo" para contextos empáticos (caso real_011) | Sin fix en este audit | N/A | **OPTIMIZE** |
| 36 | Length Hints | `core/dm/text_utils.py` | `ENABLE_LENGTH_HINTS` ← añadido | Sin flag; silently devuelve `""` si falta `length_by_intent.json` | ✅ Flag añadido — commit `909bff67` | Length control arXiv 2412 | **KEEP** |
| 37 | Question Hints | `core/dm/text_utils.py` | `ENABLE_QUESTION_HINTS` ← añadido | Sin flag; usaba `question_rate_pct` (IG corpus density) en vez de `has_question_msg_pct` (per-msg) | ✅ Flag añadido; ✅ Prefer `has_question_msg_pct` — commit `f3cc97d7` | — | **KEEP** |
| 40 | Style Analyzer | `core/style_analyzer.py` | `ENABLE_STYLE_ANALYZER=true` | Depende de que ECHO esté activo para tener efecto; si creator nuevo → perfil vacío → ECHO usa defaults | Sin fix (fuera de scope) | CharacterEval ACL 2024, PersonaGym EMNLP 2025 | **KEEP** |

---

## Commits de este audit (cronológico)

| Commit | Descripción |
|--------|-------------|
| `909bff67` | Añadidos `ENABLE_FEW_SHOT`, `ENABLE_LENGTH_HINTS`, `ENABLE_QUESTION_HINTS`; `max_examples=5` |
| `cdc9...` | `MEMO_COMPRESSION_PROMPT` de-hardcodeado de "Iris Bertran" + "fitness" |
| `1d555fe6` | `_get_catchphrases()` + sección FRASES CARACTERÍSTICAS en Doc D; `_STOP_WORDS` ES/CA/PT |
| `f3cc97d7` | `has_question_msg_pct` preferred over `question_rate_pct` en text_utils, generation, postprocessing |
| `6642b856` | `emoji_target_ratio` en ECHO documentado como unused — Style Normalizer owns emoji |

---

## Detalles por sistema

### Sistema 13 — Doc D Loader

**Archivo:** `core/dm/compressed_doc_d.py` — `_load_profile_with_db_fallback()`
**Flag:** Ninguno (siempre activo, integrado en Compressed Doc D)

**Bugs encontrados:**
- `MEMO_COMPRESSION_PROMPT` en `services/memory_engine.py` contenía "Iris Bertran", "fitness/wellness", "pilates, barre, yoga" hardcodeados → rompía para cualquier otro creator

**Fix aplicado:**
```python
# Antes:
MEMO_COMPRESSION_PROMPT = """...la clienta de Iris Bertran...fitness/wellness..."""

# Después:
MEMO_COMPRESSION_PROMPT = """...el lead de {creator_name}..."""
# call site: creator_name = creator_id.replace("_", " ").title()
```

**Paper:** InCharacter (ACL 2024) — Description alone captures ~80% personality fidelity. Doc D es el driver principal.

**Recomendación: KEEP**

---

### Sistema 14 — Compressed Doc D

**Archivo:** `core/dm/compressed_doc_d.py` — `build_compressed_doc_d()`
**Flag:** `USE_COMPRESSED_DOC_D=true` (leído en `services/creator_style_loader.py`)

**Bugs encontrados:**
1. Identity line hardcodeada: `"creadora de contenido fitness/wellness"` → rompe para Stefano y otros creators
2. Sección de catchphrases ausente — RoleLLM dice que son el driver principal de lexical consistency
3. `top_50` vocabulario incluye stop words (ja, però, que) como si fueran característicos

**Fixes aplicados:**
1. Identity line ahora genérica: `f"Eres {creator_name}. Respondes DMs de Instagram y WhatsApp como si fueras tú"`
2. Añadida función `_get_catchphrases(metrics)` que filtra `_STOP_WORDS` (ES+CA+PT) y extrae vocab característico + openers
3. Nueva sección inyectada: `FRASES Y EXPRESIONES CARACTERÍSTICAS`
4. `_STOP_WORDS` set de 40+ stop words gramaticales

**Pendiente:**
- Vocabulary podría mejorarse con TF-IDF en lugar de top-frequency (fuera de scope de este audit)

**Papers:**
- **RoleLLM (ACL 2024)**: Catchphrases = driver principal de lexical consistency. k=5 few-shot óptimo.
- **PersonaGym (EMNLP 2025)**: Linguistic habits es la tarea más difícil para LLMs.
- **CharacterEval (ACL 2024)**: Behavioral patterns + utterance style son los campos de mayor correlación con human judgment (0.879).

**Recomendación: KEEP**

---

### Sistema 15 — Few-Shot Loader

**Archivo:** `services/calibration_loader.py` — `get_few_shot_section()`
**Flag:** `ENABLE_FEW_SHOT=true` (añadido en commit `909bff67`)

**Bugs encontrados:**
1. Sin flag de control — imposible desactivar en ablation study sin modificar código
2. `max_examples=10` — papers validan k=5 como óptimo

**Fixes aplicados:**
1. `ENABLE_FEW_SHOT` añadido a `feature_flags.py` y `context.py`
2. `max_examples=5`

**Lo que funciona bien:**
- Intent-stratified + semantic hybrid selection — correcto (valida RoleLLM + ChatHaruhi)
- Multi-turn messages[] format — correcto para todos los modelos modernos
- Real DMs del creator — no sintético (CharacterEval recomienda datos reales)

**Pendiente:**
- BM25 no implementado como signal adicional para lexical matching (papers lo recomiendan)

**Papers:**
- **RoleLLM (ACL 2024)**: k=5 via BM25 es el óptimo empírico. Más de 5 → hits diminishing returns.
- **Length control (arXiv 2412)**: La longitud de los few-shots fija implicit length prior — lever más efectivo.

**Recomendación: KEEP**

---

### Sistema 16 — ECHO System

**Compuesto por:**
1. `core/style_analyzer.py` — extrae métricas cuantitativas + perfil cualitativo vía LLM
2. `services/relationship_adapter.py` — combina StyleProfile con lead_status → RelationshipContext

**Flag:** `ENABLE_RELATIONSHIP_ADAPTER=false` en Railway (desactivado por interferencia -0.30 en CPE)

**Bugs encontrados:**
1. `emoji_target_ratio` computado en `RelationshipContext` pero nunca leído por `core/` → conflicto potencial con Style Normalizer (dos sistemas pretendiendo controlar emoji)

**Fix aplicado:**
- Comentario aclaratorio en `relationship_adapter.py:62`: "unused — Style Normalizer owns emoji control"
- No hay conflicto real mientras `ENABLE_RELATIONSHIP_ADAPTER=false`

**Lo que funciona bien:**
- Modo Doc D correcto: cuando hay Doc D, solo inyecta datos contextuales (no redefine estilo)
- 6 perfiles relacionales (nuevo, interesado, caliente, cliente, fantasma, amigo) bien definidos

**Papers:**
- **InCharacter (ACL 2024)**: Description ya capta ~80% fidelity. ECHO añade contexto relacional para el 20% restante.
- **CharacterEval (ACL 2024)**: Per-lead-type behavioral differences son importantes.

**Recomendación: OPTIMIZE** — Mantener desactivado hasta medir con ablation. Si se activa, resolver conflicto emoji antes.

---

### Sistema 17 — Advanced Rules (Anti-hallucination)

**Archivo:** `core/prompt_builder/sections.py` — `build_rules_section()`
**Flag:** `ENABLE_ADVANCED_PROMPTS=false` (default correcto)

**Bugs encontrados:**
- Ninguno de código. Contenido válido pero redundante con Doc D REGLAS CRÍTICAS.

**Fix aplicado:**
- Evaluado: mantener `false`. `build_rules_section()` añade ~400 chars de reglas que ya están en Doc D. PersonaGym demuestra que prompts más cortos = mejor fidelidad.

**Papers:**
- **PersonaGym (EMNLP 2025)**: Short structured descriptions outperform verbose 38K-char documents.

**Recomendación: KEEP** (flag=false es la configuración correcta)

---

### Sistema 18 — Citation Context

**Archivo:** `services/citation_service.py`
**Flag:** `ENABLE_CITATIONS=true`

**Bugs encontrados:** Ninguno identificado.

**Recomendación: KEEP**

---

### Sistema 19 — Friend/Family Override

**Archivo:** `core/dm/phases/context.py`
**Flag:** Implícito en `ENABLE_RELATIONSHIP_DETECTION`

**Bugs encontrados (corregidos en sesión previa):**
1. `_rel_type` inyectaba hints de strategy basados en tipo de relación → prompt injection no controlado
2. `lead_facts` siempre era `[]` — parser de `memory_context` no ejecutaba

**Fixes aplicados (sesión previa):**
1. `_rel_type = ""` hardcodeado — cero prompt injection
2. Parser `memory_context string → lead_facts list` añadido en `context.py:264-284`

**Estado actual:**
- `is_friend = _rel_score.suppress_products` solo True cuando score > 0.8 (PERSONAL) — correcto
- `friend_context = ""` — Doc D ya define tono para conversaciones personales

**Papers:**
- **CharacterEval (ACL 2024)**: Behavioral consistency per relationship type importante.

**Recomendación: KEEP**

---

### Sistema 20 — Audio Context

**Archivo:** `core/dm/phases/context.py:624-668`
**Flag:** Ninguno (activo solo cuando `metadata["audio_intel"]` presente)

**Bugs encontrados:**
- Sin flag `ENABLE_AUDIO_CONTEXT` — imposible desactivar en ablation sin tocar código

**Fix aplicado:** Ninguno en este audit (fuera de scope inmediato)

**Lo que funciona bien:**
- Extrae entidades relevantes (personas, lugares, fechas, números, productos) — no vuelca audio crudo
- Fallback correcto para multimedia no-audio

**Recomendación: KEEP** — Añadir `ENABLE_AUDIO_CONTEXT` flag en próximo audit.

---

### Sistema 21 — Response Strategy

**Archivo:** `core/dm/strategy.py`
**Flag:** Implícito (siempre activo en generación)

**Bugs encontrados:**
- `RECURRENTE` strategy usa "reacciona con entusiasmo o curiosidad" — mal alineado para contextos empáticos (ej. real_011: audio sobre cervicales + plan Barcelona)

**Fix aplicado:** Ninguno en este audit

**Recomendación: OPTIMIZE** — Añadir detección de emotional_tone en audio_intel para condicionar strategy.

---

### Sistema 36 — Length Hints

**Archivo:** `core/dm/text_utils.py` — `get_data_driven_length_hint()`
**Flag:** `ENABLE_LENGTH_HINTS=true` (añadido en commit `909bff67`)

**Bugs encontrados:**
1. Sin flag de control
2. Devuelve `""` silenciosamente si `length_by_intent.json` no existe → no hint → longitud no controlada

**Fix aplicado:** Flag `ENABLE_LENGTH_HINTS` añadido.

**Limitación conocida:**
- Los hints de prompt tienen ~30-40% non-compliance según papers. Son el segundo lever, no el primero.
- El primer lever es la longitud de los few-shots (implicit length prior).

**Papers:**
- **Length control (arXiv 2412)**: Few-shot length sets implicit prior (mejor lever). Prompt instructions = segundo lever.

**Recomendación: KEEP** — Complementa los few-shots. Generar `length_by_intent.json` al onboarding de nuevos creators.

---

### Sistema 37 — Question Hints

**Archivo:** `core/dm/text_utils.py` — `get_data_driven_question_hint()`
**Flag:** `ENABLE_QUESTION_HINTS=true` (añadido en commit `909bff67`)

**Bugs encontrados:**
1. Sin flag de control
2. Usaba `question_rate_pct` (IG corpus, character-density) en vez de `has_question_msg_pct` (per-message binary, WhatsApp-calibrado)

**Fixes aplicados:**
1. Flag `ENABLE_QUESTION_HINTS` añadido
2. `_load_question_rate()` actualizado en `text_utils.py`, `generation.py`, `postprocessing.py`: prefer `has_question_msg_pct` — commit `f3cc97d7`

**Diagnóstico CPE Level 1:**
- Antes del fix: bot genera preguntas en 44% de mensajes vs creator target 26%
- Después: pendiente re-run post-fix

**Recomendación: KEEP**

---

### Sistema 40 — Style Analyzer

**Archivo:** `core/style_analyzer.py`
**Flag:** `ENABLE_STYLE_ANALYZER=true`

**Bugs encontrados:**
- Si creator nuevo → perfil vacío → ECHO usa defaults genéricos (no un bug, pero riesgo de onboarding)

**Fix aplicado:** Ninguno (comportamiento aceptable con fallbacks)

**Lo que funciona bien:**
- Pipeline dual: cuantitativo (determinístico) + cualitativo (LLM)
- Sample diversificado: 50% reciente + 25% por intent + 25% por lead status

**Papers:**
- **CharacterEval (ACL 2024)**: Behavior patterns + utterance style = mayor correlación con human judgment (0.879).
- **PersonaGym (EMNLP 2025)**: Linguistic habits es la tarea más difícil — StyleAnalyzer la captura correctamente.

**Recomendación: KEEP**

---

## Síntesis: Alineación con papers científicos

### ✅ Validado por papers

| Técnica | Paper | Implementación |
|---------|-------|----------------|
| Description-first persona (Doc D) | InCharacter ACL 2024 | `build_compressed_doc_d()` |
| k=5 few-shot retrieval | RoleLLM ACL 2024 | `max_examples=5` post-fix |
| Dynamic retrieval (intent+semantic) | ChatHaruhi + RoleLLM | `get_few_shot_section()` |
| Real dialogue examples (no sintéticos) | CharacterEval ACL 2024 | calibration real DMs |
| Per-lead-type behavioral differences | CharacterEval ACL 2024 | ECHO 6 perfiles |
| Utterance style cuantitativo (emoji, longitud) | RoleLLM ACL 2024 | Doc D quantitative section |
| Catchphrases como lexical anchor | RoleLLM ACL 2024 | Doc D sección FRASES CARACTERÍSTICAS (nuevo) |
| Short structured persona > verbose | PersonaGym EMNLP 2025 | Doc D ~1.3K chars, ENABLE_ADVANCED_PROMPTS=false |
| Probabilistic per-message style gating | Style Normalizer | exclamation + question + emoji normalizers |

### ⚠️ Gaps pendientes (priorizado por impacto)

| Gap | Paper | Severidad | Acción |
|-----|-------|-----------|--------|
| Vocabulary TF-IDF vs top-frequency en Doc D | — | Media | Mejora futura al generar baseline |
| `length_by_intent.json` no generado para todos los creators | Length control 2412 | Media | Script de onboarding |
| ECHO `emoji_target_ratio` activo si ECHO se reactiva | — | Media | Disable antes de activar ECHO |
| `RECURRENTE` strategy no adapta tono empático | — | Media | Condicionar por `emotional_tone` en audio_intel |
| BM25 en few-shot selection | RoleLLM ACL 2024 | Baja | Mejora futura |
| Sin flag `ENABLE_AUDIO_CONTEXT` | — | Baja | Añadir en próximo audit |

---

## Resumen de recomendaciones

| Recomendación | Sistemas |
|---------------|---------|
| **KEEP** (sin cambios) | Doc D Loader, Compressed Doc D, Few-Shot Loader, Advanced Rules (flag=false), Citation Context, Friend Override, Audio Context, Length Hints, Question Hints, Style Analyzer |
| **OPTIMIZE** | ECHO System (activar solo con ablation + resolver emoji conflict), Response Strategy (tono empático) |
| **REMOVE** | Ninguno |
