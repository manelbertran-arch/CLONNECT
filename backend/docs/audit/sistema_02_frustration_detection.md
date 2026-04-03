# Sistema #2 — Frustration Detection: Auditoría Forense

**Archivo principal:** `core/frustration_detector.py`
**Integración:** `core/dm/phases/detection.py` líneas 98–111
**Flag:** `flags.frustration_detection`
**Auditor:** Claude Sonnet 4.6 | Fecha: 2026-03-31

---

## 1. ¿Qué hace exactamente?

`FrustrationDetector.analyze_message()` ejecuta 10 pasos en secuencia:

1. **Escalation check** — substring match contra `ESCALATION_PATTERNS` → fuerza level=3
2. **Signal matching** (multilingual, dedup vía working-string) → score acumulado
3. **Explicit count regex** ("3 veces", "4 times") → +0.3
4. **Profanity amplifier** → ×1.3 solo si ya hay score > 0
5. **History escalation** (últimos 3 mensajes, ≥2 señales → +0.2)
6. **Repeated questions** (overlap léxico con historial → +0.2×n, cap 0.4)
7. **CAPS detection** (ratio >0.5, solo si >10 letras → +0.15)
8. **Excess question marks** (>1 signo `?` → +0.05 por exceso, cap 0.15)
9. **Negative markers** (legacy regex, peso reducido → +0.05×n, cap 0.10)
10. **Level mapping** → 0 (<0.3) / 1 (<0.6) / 2 (<0.8) / 3 (≥0.8)

Retorna `(FrustrationSignals, float)`. `signals.level` (int 0–3) y `signals.reasons` (lista de strings) son los datos v2. El resultado se inyecta como nota factual en el bloque *Recalling*, NO como instrucción de comportamiento en el prompt de usuario.

---

## 2. ¿Es universal? Test empírico

```
IT explicit "Sei inutile, non capisci niente"  → level=0 score=0.00  ← BUG
IT repetition "Quante volte te lo devo dire?"   → level=0 score=0.00  ← BUG
IT failure "Non funziona, non mi aiuti"         → level=0 score=0.00  ← BUG
IT escalation "Voglio parlare con una persona"  → level=0 score=0.00  ← BUG
IT profanity+failure "Cazzo non funziona"       → level=0 score=0.00  ← BUG

CA explicit "Estic fart, no entens res"         → level=2 score=0.75  ✓
ES explicit "Estoy harto de esperar"            → level=1 score=0.50  ✓
EN explicit "I'm fed up with this"              → level=1 score=0.50  ✓
```

**Veredicto: NO es universal.** Para Stefano Bonanno (creador italiano), todas las frustraciones de sus fans en italiano se procesan como level=0.

---

## 3. Bugs identificados

### BUG-F1 ⚠️ CRÍTICO — Italiano completamente ausente

**Síntoma:** Todo mensaje en italiano → level=0, score=0.00, sin importar intensidad.

**Causa:** Tres catálogos no tienen cobertura italiana:
- `ESCALATION_PATTERNS` — tiene `es`, `ca`, `en`. Sin `it`.
- `FRUSTRATION_SIGNALS` — claves `"es"`, `"ca"`, `"en"`. Sin `"it"`.
- `PROFANITY_AMPLIFIERS` — `joder/hostia/merda` (es/ca), `fuck/shit` (en). Sin `cazzo`, `vaffanculo`, `stronzo`, `porco`.

**Impacto:** Stefano Bonanno tiene fans italianos. "Sei inutile, non capisci niente" → level=0. El clon responde como si todo estuviera bien.

**Fix necesario:** Añadir `"it"` a `FRUSTRATION_SIGNALS` y `ESCALATION_PATTERNS`. Extender `PROFANITY_AMPLIFIERS` con profanity italiano.

---

### BUG-F2 ⚠️ MODERADO — Price keywords solo es/en en `_count_repeated_questions`

**Síntoma:**
```python
price_keywords = {"precio", "cuesta", "coste", "vale", "euros", "dinero", "price", "cost"}
```
No incluye:
- Catalán: `preu`, `costa` (ej. "quant costa?")
- Italiano: `prezzo`, `quanto`, `costo`, `euro`

**Impacto:** Fan catalán que pregunta el precio 3 veces → repetition no detectada. Fan italiano ídem.

---

### BUG-F3 ⚠️ MODERADO — Stopwords incompletas para CA/IT

`_count_repeated_questions` filtra stopwords:
```python
stopwords = {
    "el", "la", "los", "las", "un", "una", "de", "en", "que", "y", "a",  # es
    "the", "is", "it", "to", "and", "i",  # en
}
```

No tiene catalán (`per`, `amb`, `però`, `però`, `fins`, `sobre`) ni italiano (`il`, `lo`, `gli`, `le`, `di`, `in`, `che`, `e`, `mi`, `si`). Las stopwords italianas se cuentan como palabras de contenido → el overlap semántico queda distorsionado, reduciendo la sensibilidad para CA/IT.

---

### BUG-F4 🟡 MENOR — `NEGATIVE_MARKERS` incompleto para CA/IT

```python
NEGATIVE_MARKERS = [
    r'\bno\b', r'\bnunca\b', r'\bnada\b', r'\bmal\b', r'\bpeor\b',
    r'\bproblema\b', r'\berror\b', r'\bfallo\b',           # ← es
    r'\bdon\'?t\b', r'\bcan\'?t\b', r'\bwon\'?t\b', r'\bnot\b',
    r'\bbad\b', r'\bworse\b', r'\bproblem\b', r'\bwrong\b', # ← en
]
```

Ausentes:
- Catalán: `mai` (nunca), `pitjor` (peor), `fallada` (fallo), `res` (nada en contexto negativo)
- Italiano: `mai`, `peggio`, `sbagliato`, `errore`, `nulla`

Nota: `no`, `problema`, `mal` tienen overlap accidental con italiano, así que la cobertura no es cero — pero es parcial e implícita.

---

### BUG-F5 🟡 MENOR — Mensaje fail-closed hardcodeado en español + nombre incorrecto

En `core/dm/phases/detection.py` líneas 84–88 (path: `except Exception` de sensitive detection):

```python
creator_name = getattr(agent, "creator_id", "el creador")  # ← slug, no display name
result.pool_response = DMResponse(
    content=(
        f"Ahora mismo no puedo responderte bien. "
        f"Le paso tu mensaje a {creator_name} directamente 🙏"  # ← siempre español
    ),
```

Dos problemas:
1. `creator_id` es el slug (`stefano_bonanno`), no el display name (`Stefano`). El fan recibe: "Le paso tu mensaje a stefano_bonanno".
2. Mensaje en español duro incluso para creadores italianos/catalanes/ingleses.

El fix de BUG-S2 (sesión anterior) corrigió el path de crisis resources, pero NO este path de exception handler.

---

### BUG-F6 🟢 COSMÉTICO — History scan sin working-string dedup

El paso 5 (history escalation) escanea patrones de todas las lenguas sobre cada mensaje histórico sin aplicar el mecanismo de working-string. Un mensaje histórico con `"estoy harto de esperar"` y `"harto de esperar"` como substrings contaría dos señales. Dado el cap de `+0.2` total del bloque de history, el impacto es acotado.

---

## 4. Análisis de diseño vs papers

| Principio | Paper | Implementación | Estado |
|-----------|-------|---------------|--------|
| Frustración gradada (0–N niveles) | Niculescu et al. "Emotion Detection in Dialogue" — gradated rather than binary | Levels 0–3 con thresholds calibrados | ✓ MEJOR |
| Profanity = amplificador, no trigger | Schuller et al. "Recognizing Affect in Spontaneous Speech" — profanity correlates with emotional arousal but not frustration per se | ×1.3 solo si score>0; profanity alone → level=0 | ✓ CORRECTO |
| Escalation patterns como override | Mohammed & Yeasin "User Intent Detection" — explicit human-request as hard signal | ESCALATION_PATTERNS → forced level=3 | ✓ CORRECTO |
| Cross-turn escalation | Mohammad et al. "SemEval Sentiment Analysis" — sentiment tracking across turns | history[-3:] → +0.2 si ≥2 señales | ✓ ALINEADO |
| No API cost | Eficiencia operacional | Rule-based sub-1ms | ✓ MEJOR QUE MODELOS |
| Multilingüismo | Todos los papers asumen multilingual pipeline | es/ca/en sí, **it NO** | ✗ GAP |

---

## 5. Cobertura lingüística

| Lengua | ESCALATION | SIGNALS | PROFANITY | Price KW | Stopwords | NEGATIVE_MARKERS |
|--------|-----------|---------|-----------|----------|-----------|-----------------|
| Español | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Catalán | ✓ | ✓ | ✓ | ✗ | ✗ | ✗ |
| Inglés | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Italiano | ✗ | ✗ | parcial | ✗ | ✗ | parcial |

---

## 6. Comportamiento correcto confirmado

Los siguientes comportamientos funcionan según diseño:

- **Dedup working-string**: `"estoy harto de esperar harto"` → score=0.50 (solo cuenta una vez) ✓
- **Profanity solo**: `"Joder"` → level=0 ✓
- **CAPS + señal**: `"NO ME FUNCIONA NADA"` → level=1 (CAPS + no funciona) ✓
- **Falso positivo inocente**: `"No tengo el producto todavia"` → score=0.05, level=0 ✓
- **Memory LRU cap**: `_MAX_TRACKED_CONVERSATIONS = 5000` — previene crecimiento ilimitado ✓
- **History window**: Bounded a últimos 20 mensajes por conversación ✓
- **Singleton**: Instancia única reutilizada por todos los workers del mismo proceso ✓

---

## 7. Resumen de bugs

| ID | Severidad | Descripción | Archivo | Fix |
|----|-----------|-------------|---------|-----|
| F1 | CRÍTICO | Italiano completamente ausente | `frustration_detector.py` | Añadir `it` a SIGNALS + ESCALATION + PROFANITY |
| F2 | MODERADO | Price keywords sin CA/IT | `frustration_detector.py:336` | Añadir `preu`, `costa`, `prezzo`, `quanto`, `costo` |
| F3 | MODERADO | Stopwords incompletas | `frustration_detector.py:331` | Añadir ca/it stopwords |
| F4 | MENOR | NEGATIVE_MARKERS incompleto | `frustration_detector.py:160` | Añadir ca/it negatives |
| F5 | MENOR | Fail-closed mensaje hardcodeado ES + slug como nombre | `detection.py:84` | Resolver dialect + usar display name |
| F6 | COSMÉTICO | History scan sin dedup | `frustration_detector.py:252` | Bajo impacto, bajo en prioridad |

---

## 8. Recomendación

**ESTADO: KEEP + FIX F1 (obligatorio) + F2/F3 (opcional)**

El diseño central es sólido y superior a usar un modelo LLM para detección de frustración (costo, latencia). Los mecanismos de dedup, profanity-as-amplifier e historia están bien implementados para es/ca/en.

El único problema crítico es que **Italian = cero cobertura**. Con Stefano Bonanno en producción, esto significa que toda frustración italiana pasa invisible. F1 bloquea producción para ese creador.

F2 y F3 son mejoras de calidad para CA/IT que no rompen nada pero reducen falsos negativos en detección de repetición.

F5 es un bug residual del parche BUG-S2 de la sesión anterior — el exception handler quedó sin actualizar.
