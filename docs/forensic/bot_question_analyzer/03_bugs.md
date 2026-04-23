# Bot Question Analyzer — Bugs Detectados

**Metodología:** lectura estática + testing empírico (Python3.11 local) contra los entry points.

Severidad: **HIGH** = comportamiento falso en prod • **MED** = gap funcional o riesgo latente • **LOW** = cosmetic / edge theoric.

---

## BUG-1 [HIGH] — `"   "` (whitespace-only) → True afirmación falsa

**Prueba:**
```python
>>> is_short_affirmation("   ")
True
```

**Por qué:** `msg.lower().strip()` produce `""`. `"" in AFFIRMATION_WORDS` → False, pero `"".split()` → `[]`, `len([]) <= 3` → True, `all([]) = True` (vacuidad). Returns True.

**Impacto:** si alguien envía sólo espacios, entra la rama de detection. Pero como `last_bot` existirá normalmente y `q_type != UNKNOWN`, se inyecta la nota de contexto sin razón.

**Fix:** añadir early-return `if not msg: return False` DESPUÉS del `strip()`. La guarda previa `if not message` sólo filtra `None` y `""`, no `"   "`.

---

## BUG-2 [HIGH] — Punctuation-only (`"??"`, `"?"`, `"..."`, `"!!!"`) → True

**Prueba:**
```python
>>> is_short_affirmation("??")   # True
>>> is_short_affirmation("?")    # True
>>> is_short_affirmation("...")  # True
>>> is_short_affirmation("!!!")  # True
>>> is_short_affirmation("-")    # False (correcto — "-" no matchea al estar en rstrip)
```

**Por qué:** `rstrip('!.,?')` elimina todos los `!`, `.`, `,`, `?` finales. Para `"??"`, `w.rstrip(...) = ""`. El `all()` acepta `w == ''` → True.

**Impacto:** **crítico cuando el flag esté ON**. Un lead que responde "?" (pregunta de vuelta) o "..." (puntos suspensivos de escepticismo) sería tratado como afirmación, y se inyectaría al prompt "El lead confirma X", contradictoria con la intención real. Es exactamente la clase de colisión que CCEE marcaría en H Turing y S2 Coherence.

**Fix:** la guarda `w == ''` fue añadida para tolerar `"si !"` (palabra "si" seguida de espacio-bang), pero globalmente es tóxica. Alternativas:
1. Pre-filtro: `if re.fullmatch(r'[\s!.,?]+', msg): return False`.
2. Contar palabras no-vacías: `if not any(cleaned_words): return False`.

---

## BUG-3 [MED] — Emojis thumbs/check no cuentan como afirmación

**Prueba:**
```python
>>> is_short_affirmation("👍")   # False
>>> is_short_affirmation("👌")   # False
>>> is_short_affirmation("✅")   # False
>>> is_short_affirmation("si👍") # False (el emoji adherido a "si" rompe el match)
```

**Por qué:** `AFFIRMATION_WORDS` no tiene emojis. `"👍".lower().strip()` sigue siendo `"👍"`, no está en el set.

**Impacto:** gap funcional real en IG DMs. En el dataset iris_bertran un % no-trivial de "confirmaciones" son 👍/👌/🙌/💪/❤️ solas. Hoy caen por el predicado → se pierde contexto.

**Fix:** añadir `AFFIRMATION_EMOJIS = {'👍', '👌', '🙌', '✅', '💪', '🙏', '😊', '❤️', '🤙', '💯'}` y chequear `msg in AFFIRMATION_EMOJIS` como rama adicional. Requiere validar con corpus real (ver Phase 5 — data-derived).

---

## BUG-4 [MED] — Inconsistencia "sii" vs "siii" / alargamientos expresivos

**Prueba:**
```python
>>> is_short_affirmation("sii")    # False  ← no está en set
>>> is_short_affirmation("siii")   # True   ← está literal
>>> is_short_affirmation("siiii")  # True   ← está literal
>>> is_short_affirmation("siiiii") # False  ← no en set
>>> is_short_affirmation("sisi")   # False  ← gap obvio
```

**Por qué:** `AFFIRMATION_WORDS` lista literales `'siii', 'siiii'` pero no cubre el continuum (`'sii'`, `'siiiii'`, `'sisi'`). Código no tiene regex de alargamiento.

**Impacto:** inconsistencia — tests aleatorios darán resultados contradictorios según el número exacto de íes. Coste oportunidad: muchas afirmaciones reales son alargadas ("siiiii", "okkkk", "perfeeecto").

**Fix:** después de chequear `msg in AFFIRMATION_WORDS`, aplicar una normalización ligera: colapsar repeticiones ≥3 a 1 (`r'(.)\1{2,}' → r'\1'`). Ej: `"siiiii" → "si"`, `"okkkk" → "ok"`. Validar que no rompe casos útiles.

---

## BUG-5 [MED] — Hardcoded vocab no data-derived

**Observación:** `AFFIRMATION_WORDS` es un `set` literal en código (~70 términos). No se lee de DB, JSON ni archivo per-creator.

**Compara con el resto del pipeline:** `length_by_intent.json`, `baseline_metrics`, `vocab_meta` (preference_pairs, gold_examples) son data-derived. Este módulo es el outlier.

**Impacto:**
- Cualquier cambio requiere deploy.
- No se puede per-creator (si un creador escribe primariamente en IT, no hay override).
- No se puede A/B vocab sin tocar código.

**Fix aplicado (Phase 5 refactor):** zero hardcoding lingüístico.
- **Eliminado** `AFFIRMATION_WORDS` hardcoded.
- **Eliminado** JSON estático `data/vocab/affirmation_vocab.json` (la primera iteración del PR lo había introducido — también es hardcoding aunque esté fuera del .py).
- **Añadido** consumo de `personality_docs.vocab_meta.affirmations` via `services.calibration_loader._load_creator_vocab(creator_id)` (reusa infra existente).
- **Fallback universal** cuando vocab mined no está poblado: sólo emojis Unicode convencionales (9 glyphs cross-culture). Sin listas por idioma.
- **Blocker operacional:** el worker de mining (fuera de este PR) debe poblar `vocab_meta.affirmations` per-creator. Sin eso, el analyzer degrada graciosamente a emoji-only.

---

## BUG-6 [MED] — `is_short_affirmation` acepta 3 palabras consecutivas de afirmación

**Prueba:**
```python
>>> is_short_affirmation("ok ok")           # True
>>> is_short_affirmation("si claro vale")   # True
>>> is_short_affirmation("perfecto genial") # True
```

**Por qué:** la regla `len(words) <= 3` permite combinaciones raras. No necesariamente bug; pero semánticamente "ok ok ok" puede ser impaciencia/enojo y no confirmación. La nota inyectada sería contradictoria.

**Impacto:** LOW a MED. Empírico: poco frecuente. Pero contraintuitivo para lectores del código.

**Fix:** no cambiar el umbral; añadir guard específica contra repeticiones inmediatas (detectar `dup_consecutive_tokens >= 2` y marcar como `NEUTRAL`).

---

## BUG-7 [MED] — Prioridad `INTEREST` sobre `INFORMATION` captura falsos positivos

**Prueba:**
```python
>>> a.analyze("¿Qué te interesa?").value
'interest'  # ← debería ser 'information' (pregunta abierta)
```

**Por qué:** orden de chequeo `[PURCHASE, PAYMENT, BOOKING, INTEREST, INFORMATION, CONFIRMATION]`. El regex `r'te interesa'` de INTEREST matchea "qué te interesa" antes de llegar al check de INFORMATION.

**Impacto:** MED. Nota inyectada "El lead confirma interés en tus servicios." es semánticamente inadecuada cuando el bot preguntó "¿qué te interesa?" y el lead respondió "si" (en realidad rebotó genéricamente). Distorsiona S2/L3.

**Fix:** añadir heuristic: si el mensaje contiene `¿qué|what` + verbo interrogativo abierto, clasificar como `INFORMATION` **antes** de INTEREST. O bien, mover `INFORMATION` delante de `INTEREST` en el orden.

---

## BUG-8 [HIGH] — Test `test_flag_exists` roto desde refactor de febrero

**Archivo:** `backend/tests/unit/test_dm_agent_bot_question.py:11-14`
```python
def test_flag_exists(self):
    from core.dm_agent_v2 import ENABLE_QUESTION_CONTEXT
    assert isinstance(ENABLE_QUESTION_CONTEXT, bool)
```

**Verificación:**
```bash
$ grep -n "ENABLE_QUESTION_CONTEXT" backend/core/dm_agent_v2.py
# (sin resultados — refactor ae7adf52 movió el flag a core/dm/phases/context.py)
```

**Impacto:** test probablemente falla silenciosamente o pasa por re-export accidental (hay que ejecutar). La cobertura del flag es inefectiva.

**Fix:** `from core.dm.phases.context import ENABLE_QUESTION_CONTEXT`.

---

## BUG-9 [LOW] — Singleton no thread-safe

**Código:** L258-266.
```python
_analyzer_instance = None
def get_bot_question_analyzer() -> BotQuestionAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = BotQuestionAnalyzer()
    return _analyzer_instance
```

**Riesgo:** si dos requests simultáneos llaman el getter al mismo tiempo, ambos pueden entrar en el `if` y compilar 2 instancias. Como `BotQuestionAnalyzer.__init__()` es puro (solo compila regex), el peor caso es 2× coste de init → estado inconsistente NO ocurre. **Bug teórico**.

**Fix:** al ser benigno, no urge. Si se toca, envolver en `threading.Lock()` o usar `functools.cache` en un constructor wrapper.

---

## BUG-10 [LOW] — No validación del umbral 0.7 contra `CONFIRMATION=0.70`

**Código:**
- Detection mapea `CONFIRMATION → 0.70`.
- Injection exige `_q_conf >= 0.7`.

Python compara `0.70 >= 0.7` → True (ambos son `float 0.7`). **No hay bug.** Pero es una cliff: si alguien sube a `0.75` el umbral, `CONFIRMATION` se silenciaría silenciosamente. Documentar como *frontier*.

---

## BUG-11 [LOW] — Statement "son solo 50€" → INTEREST semánticamente cuestionable

**Prueba:**
```python
>>> a.analyze("son solo 50€").value
'interest'  # nota inyectada: "El lead confirma interés en tus servicios."
```

**Contexto:** el lead acaba de ver el precio. Si dice "ok", el contexto real es "acepta el precio y quiere avanzar" — más cercano a `PURCHASE` que a `INTEREST`.

**Impacto:** baja-media. No es wrong per se (interés sigue siendo válido), pero subóptimo. Podría beneficiarse de un tipo nuevo `PRICE_DISCLOSED`.

**Fix:** fuera del scope de este PR. Registrar como mejora futura.

---

## BUG-12 [LOW] — Tests sin cobertura multilingual ni edge cases

Ver Phase 2 §7. El test file cubre 3 casos ES y 0 casos CA/IT/EN/edge. La multilingual expansion (`dfb568038`, 2026-03-27) añadió código sin añadir tests.

**Fix (Phase 5):** elevar a 9/10 casos cubriendo ES + CA + IT + EN + edges (emoji, `""`, `"   "`, `"?"`, statement-expecting).

---

## Resumen priorizado

| # | Severidad | Bug | Fix Phase |
|---|-----------|-----|-----------|
| 1 | HIGH | `"   "` → True | 5 |
| 2 | HIGH | Punct-only → True | 5 |
| 8 | HIGH | Test flag importa módulo equivocado | 5 |
| 3 | MED | Emoji-only no afirma | 5 |
| 4 | MED | Alargamiento "sii" inconsistente | 5 |
| 5 | MED | Vocab hardcoded no data-derived | 5 |
| 7 | MED | Prioridad INTEREST > INFORMATION false positive | 5 |
| 6 | MED | "ok ok" triple aceptado | 5 (nota) |
| 10 | LOW | Threshold cliff 0.7/0.70 | N/A |
| 9 | LOW | Singleton race | N/A |
| 11 | LOW | statement precio → INTEREST | futuro |
| 12 | LOW | Tests sin multilingual | 5 |

**Conclusión:** 3 HIGH, 5 MED, 4 LOW. Los HIGH afectan directamente la validez de las notas inyectadas y comprometerían la lectura CCEE si el flag se activa sin fix. Los MED son gaps funcionales.

---

**STOP Phase 3.** Continuar con Phase 4 (papers + repos).
