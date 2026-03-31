# AUDITORÍA SISTEMA #5: POOL MATCHING (Fast-Path)
**Fecha:** 2026-03-31 (revisado post-papers)
**Archivo principal:** `services/response_variator_v2.py`
**Llamado desde:** `core/dm/phases/detection.py:129-175`
**Flag:** `flags.pool_matching`
**Threshold:** `AGENT_THRESHOLDS.pool_confidence = 0.8` (env: `POOL_CONFIDENCE`)

---

## 1. ¿Qué es Pool Matching?

Pool Matching es el **fast-path de respuesta** de Clonnect: antes de invocar el LLM, el sistema clasifica el mensaje entrante en una categoría social (saludo, confirmación, risa, despedida, etc.) y, si la confianza supera 0.8, devuelve una respuesta pre-escrita del pool del creator. Para mensajes cortos (≤ 80 chars) que son puramente conversacionales — "hola!", "ok!", "jajaja", "👍" — el LLM no aporta valor diferencial y añade latencia y coste. Pool Matching hace el bypass. El sistema carga pools por-creator desde la extracción Doc D; si no existe extracción, usa pools de fallback genéricos neutros. La selección dentro del pool usa TF-IDF context-aware con fallback a random.choice() para pools pequeños.

---

## 2. Validación académica — ¿Debería existir este sistema?

### Veredicto: KEEP. Académicamente justificado.

**GPT Semantic Cache (arXiv 2411.05276, 2024):** El patrón de semantic caching para LLMs es válido y recomendado para producción. Cosine similarity sobre embeddings con threshold 0.85–0.95 da 61–68% cache hit rates con >97% precisión. Los mensajes fáticos/sociales (saludos, confirmaciones) son el caso ideal — tienen el espacio semántico más pequeño y el cache hit rate más alto.

**Apple Krites (Apple ML Research, 2024):** Cache semántico asíncrono verificado. Confirma que el fast-path para queries estables es producción-standard.

**"Faster Is Not Always Better" (ECIS 2018) + "Explaining the Wait" (ACM CUI 2024):** Para social/phatic turns, los usuarios esperan respuesta instantánea. Cualquier delay en "hola!" daña la satisfacción. Fast-path es correcto para esta categoría.

**IJCAI Survey (Tao et al., 2021):** Response selection en dialogue: el único método no recomendado es random.choice() puro (aparece solo como baseline a superar). Todo lo demás — TF-IDF, BM25, dense embeddings — es válido, con embeddings siendo el estado del arte.

### Conflicto con el principio de persona

El principio "persona se enseña con few-shot+DocD+fine-tuning, NUNCA con post-processing estadístico" NO aplica a Pool Matching. Los pools son respuestas pre-escritas **del creator** (extraídas del Doc D), no transformaciones estadísticas de una respuesta del LLM. Pool Matching devuelve palabras reales del creator — es retrieval puro. Esto es distinto a Style Normalization (que modifica el output del LLM).

---

## 3. Inventario de bugs — estado actual

### BUG-PM-01: ✅ ALREADY FIXED (en código actual)
**Singleton contamina pools entre creators**

El `__init__` ya no llama `_try_load_calibration()`. Comentario en código:
```python
# Generic fallback pools only — NO creator-specific calibration here.
# Loading calibration JSONs in __init__ caused non-deterministic cross-creator
# pool contamination (BUG-PM-01 fix).
self._setup_fallback_pools()
```
`get_pools_for_creator()` tiene la lógica correcta: si existe extracción para el creator, NUNCA cae al fallback global.

---

### BUG-PM-02: ✅ ALREADY FIXED (en código actual)
**TF-IDF dead code, selección era random**

`try_pool_response()` ahora llama `_select_context_aware()`:
```python
# v12: TF-IDF context-aware selection (BUG-PM-02 fix — was dead code).
response = self._select_context_aware(
    lead_message, candidates, category, turn_index=turn_index
)
```

**PAPER NOTE:** TF-IDF es correcto para pools con vocabulario variado. Para pools de mensajes muy cortos ("Hola! 😊" vs "Hey!"), TF-IDF da similitud cercana a cero porque no comparten términos. `_select_context_aware()` tiene el fallback correcto:
```python
if not self._vectorizer or not candidates or len(candidates) <= top_k:
    return random.choice(candidates) if candidates else ""
```
Para pools pequeños (≤3 candidatos) cae a random.choice() — aceptable. El estado del arte sería cosine similarity sobre embeddings (dense retrieval). **Deuda técnica documentada, no bug crítico.**

---

### BUG-PM-03: ✅ ALREADY FIXED (en código actual)
**Praise detection lógica invertida**

```python
if len(msg) < 30:   # correcto — fue > 30 (BUG-PM-03)
    return "praise", 0.85
```

---

### BUG-PM-04: ✅ FIXED HOY — "que crack" no universal
**Archivo:** `services/response_variator_v2.py` — praise_triggers

`"que crack"` es vocabulario Río de la Plata (Argentina/Uruguay). No es español neutro ni catalán. Eliminado. Añadidos triggers universales:

```python
# Antes:
praise_triggers = ["muy lindo", "estuvo genial", "eres hermoso", "que crack"]

# Después:
praise_triggers = [
    "muy lindo", "estuvo genial", "eres hermoso",
    "eres increíble", "lo mejor", "muy bueno", "muy buena",
]
```

---

### BUG-PM-05: ✅ ALREADY FIXED (en código actual)
**Overlapping triggers entre encouragement y empathy**

`"difícil"` y `"cuesta"` eliminados de encouragement triggers. Comentario en código:
```python
# "difícil"/"cuesta" removed: they overlap with empathy and route there instead.
# Empathy (0.60) falls below min_confidence → those messages go to LLM, which
# is correct — emotional struggle needs context, not a canned "Vamos con toda!".
```
Los mensajes de lucha emocional ahora van siempre al LLM. Correcto.

---

### BUG-PM-06: 🟡 WON'T FIX — Double threshold (decisión de diseño)
**Diseño intencional, no bug.**

El gate interno (`min_confidence=0.7`) y el externo (`AGENT_THRESHOLDS.pool_confidence=0.8`) sirven propósitos distintos:
- Gate interno: API contract de `try_pool_response()`. Bloquea empathy (0.60) para que ningún caller reciba matches de baja confianza.
- Gate externo: umbral de producción configurado en AGENT_THRESHOLDS. Añade margen adicional para la detección phase.

La redundancia para `encouragement` (0.75 > 0.7 pero < 0.8) es intencional: pasa la API pero la producción lo bloquea. Si se quiere activar encouragement en producción, se baja `POOL_CONFIDENCE` a 0.75 sin cambiar código. Documentado.

---

### BUG-PM-07: ✅ FIXED HOY — Fallback pools con dialectos LatAm
**Archivo:** `services/response_variator_v2.py` — `_setup_fallback_pools()`

Reemplazado expresiones Río de la Plata con español neutro:

| Antes | Después | Razón |
|-------|---------|-------|
| `"Jaja morí"` | `"Jajajaja 😄"` | "morí" es LatAm hipérbole |
| `"Vamos con toda!"` | `"Ánimo! 💪"` | LatAm, no España |
| `"Me hiciste reir jaja"` | `"Me hiciste reír jaja"` | Corrección ortográfica |
| `"Jajaja que bueno"` | `"Jajaja qué bueno"` | Tilde correcta |

---

## 4. Nueva deuda técnica encontrada en auditoría

### NEW-PM-08: TF-IDF subóptimo para social messages (deuda técnica)
**Severidad:** BAJA (funcional, no roturas)

TF-IDF es sparse retrieval basado en frecuencia de términos. Para mensajes como "hola!" vs pool entries como "Hola! 😊", "Hey!", "Buenas!" — no hay términos comunes entre query y candidatos → similitud ≈ 0 para todos → selección efectivamente random.

**Papers:** Dense retrieval (embedding cosine similarity) supera TF-IDF en social/short dialogue (ACM TOIS 2024, Apple Krites 2024). El estado del arte es top-1 por similitud embedding, threshold ≥ 0.85.

**Impacto actual:** el fallback a `random.choice()` cuando `len(candidates) <= top_k` (=3) es correcto para pools pequeños. Para pools grandes, TF-IDF puede dar rankings sin sentido.

**Recomendación:** cuando ECHO calibration produce pools per-creator, mantener TF-IDF como aproximación. Migración futura: `sentence-transformers` para embedding similarity dentro del pool. No es urgente — el sistema es funcional.

---

## 5. Universalidad post-fixes

| Layer | Iris (CA/ES) | Stefano (IT) | Lead nuevo | Estado |
|-------|-------------|--------------|------------|--------|
| Fallback pools | Neutro ✅ | Neutro ✅ | Neutro ✅ | Fixed (PM-07) |
| Extraction pools | Doc D Iris ✅ | Doc D Stefano ✅ | LLM fallback ✅ | OK |
| Praise triggers | Universal ✅ | Universal ✅ | Universal ✅ | Fixed (PM-04) |
| Encouragement triggers | Neutro ✅ | Neutro ✅ | Neutro ✅ | Fixed (PM-05) |
| Cross-creator leak | Eliminado ✅ | Eliminado ✅ | Eliminado ✅ | Fixed (PM-01) |

---

## 6. Resumen ejecutivo

| Bug ID | Severidad | Estado | Commit |
|--------|-----------|--------|--------|
| BUG-PM-01 | CRÍTICO | ✅ Pre-fixed | anterior |
| BUG-PM-02 | CRÍTICO | ✅ Pre-fixed | anterior |
| BUG-PM-03 | ALTO | ✅ Pre-fixed | anterior |
| BUG-PM-04 | MEDIO | ✅ Fixed hoy | this session |
| BUG-PM-05 | MEDIO | ✅ Pre-fixed | anterior |
| BUG-PM-06 | BAJO | 🟡 WON'T FIX (diseño intencional) | — |
| BUG-PM-07 | BAJO | ✅ Fixed hoy | this session |
| NEW-PM-08 | BAJO | 📋 Deuda técnica documentada | future |

**VEREDICTO FINAL: KEEP. Sistema validado académicamente. Todos los bugs críticos y altos corregidos. Listo para ablación.**

Papers: GPT Semantic Cache (arXiv 2411.05276), Apple Krites (2024), IJCAI Survey (Tao et al. 2021), ACM TOIS Dense Retrieval (2024), ACM CUI "Explaining the Wait" (2024).
