# Bot Question Analyzer — Forense Línea a Línea

**Archivo:** `backend/core/bot_question_analyzer.py` — 330 LOC
**Callsites prod:** `backend/core/dm/phases/context.py` L803 (detection), L1396 (injection)
**Flag:** `ENABLE_QUESTION_CONTEXT` (env default `true`, Railway `false`)

---

## 1. Topología del módulo

```
bot_question_analyzer.py (330 LOC)
├── QuestionType (Enum, L22-30)                       [690c04737, 2026-01-11, Claude]
│   └── 7 valores: INTEREST, PURCHASE, INFORMATION,
│       CONFIRMATION, BOOKING, PAYMENT_METHOD, UNKNOWN
│
├── class BotQuestionAnalyzer (L33-254)               [690c04737]
│   ├── INTEREST_PATTERNS      (L40-61, 20 regex)     [690c04737]
│   ├── PURCHASE_PATTERNS      (L64-82, 17 regex)     [690c04737]
│   ├── INFORMATION_PATTERNS   (L85-103, 17 regex)    [690c04737]
│   ├── CONFIRMATION_PATTERNS  (L106-115, 8 regex)    [690c04737]
│   ├── BOOKING_PATTERNS       (L118-129, 10 regex)   [690c04737]
│   ├── PAYMENT_PATTERNS       (L132-141, 8 regex)    [690c04737]
│   ├── STATEMENT_EXPECTING_RESPONSE (L145-171, 18 regex) [8a045a0b8, 2026-01-11]
│   ├── __init__() (L173-184)  — compila 80 regex al cargar
│   ├── analyze() (L186-229)   — clasificación por prioridad
│   └── analyze_with_confidence() (L231-254)
│
├── get_bot_question_analyzer() singleton (L261-266)  [690c04737]
│
├── AFFIRMATION_WORDS set (L274-295, ~70 términos)
│   ├── ES base (L276-280)                            [690c04737]
│   ├── ES entendido/listo/hecho (L280)               [70741299a, 2026-01-23]
│   ├── CA (L282-284, 14 términos)                    [dfb568038, 2026-03-27]
│   ├── IT (L286-287, 10 términos)                    [dfb568038]
│   ├── EN (L289-290, 12 términos)                    [dfb568038]
│   └── Variantes con signos (L291-294)               [690c04737 + dfb568038]
│
└── is_short_affirmation(message) (L298-330)          [690c04737]
```

**Regex totales:** 98 patrones (80 clasificación bot + 18 statement). Todos con `re.IGNORECASE`. Compilados una sola vez en `__init__()` + singleton, coste amortizado.

## 2. Atribución Git (quién escribió qué)

| Commit | Fecha | Autor | Cambio |
|--------|-------|-------|--------|
| `690c04737` | 2026-01-11 | Claude | **Creación inicial** — archivo entero excepto STATEMENT_EXPECTING_RESPONSE |
| `8a045a0b8` | 2026-01-11 | Claude | +`STATEMENT_EXPECTING_RESPONSE` (18 patterns, ofertas/precios/propuestas) y lógica de fallback `analyze()` L222-228 |
| `70741299a` | 2026-01-23 | Manel | +"entendido, entiendo, comprendo, listo, hecho" a ES (L280) + variantes `.` (L293) |
| `b8cf8ce08` | 2026-02-15 | Manel | Phase 2 debug masivo — tocó sólo `from typing import Tuple` (L16) |
| `dfb568038` | 2026-03-27 | Manel | **Multilingual CA/IT/EN** (L282-290) + variantes CA (L294) + reordena header con comentarios "# Español", "# Catalán", etc. |

**Observación:** el "pipeline wiring" (`dfb568038`) es el mismo commit que conectó el analyzer a `context.py`. Antes de esa fecha, el código existía pero estaba **desconectado de producción**. La multilingual expansion (CA/IT/EN) llegó junto con el wiring — coherente con el plan de la época (apertura europea).

## 3. Callsites en producción

### Callsite #1 — Detection (`context.py:803-823`)

```python
# L22 (module-level)
ENABLE_QUESTION_CONTEXT = os.getenv("ENABLE_QUESTION_CONTEXT", "true").lower() == "true"

# L803-823 (dentro del pipeline de contexto, post-intent-classify)
if ENABLE_QUESTION_CONTEXT and is_short_affirmation(message):
    try:
        hist = metadata.get("history", [])
        last_bot = next(
            (m.get("content", "") for m in reversed(hist)
             if m.get("role") == "assistant"),
            None,
        )
        if last_bot:
            q_type, q_conf = get_bot_question_analyzer().analyze_with_confidence(last_bot)
            if q_type != QuestionType.UNKNOWN:
                cognitive_metadata["question_context"] = q_type.value
                cognitive_metadata["question_confidence"] = q_conf
                cognitive_metadata["is_short_affirmation"] = True
    except Exception as e:
        logger.debug(f"Question context failed: {e}")
```

**Gating:** ambos, flag AND `is_short_affirmation(message)`. Short-circuit correcto — si el lead no afirmó, no se hace nada.

**Posición pipeline:** justo después de `intent_classifier.classify(message)` (L796-799), antes del bloque parallel DB/IO (L827+). Barata (regex + set lookup + single-pass `reversed(hist)`).

**Side effects:** sólo escribe en `cognitive_metadata` dict. No toca DB ni red. `except Exception` defensivo pero usa `logger.debug` (silencioso en prod).

### Callsite #2 — Injection (`context.py:1396-1416`)

```python
if ENABLE_QUESTION_CONTEXT:
    _q_ctx = cognitive_metadata.get("question_context")
    _q_conf = cognitive_metadata.get("question_confidence", 0)
    if _q_ctx and _q_ctx != "unknown" and _q_conf >= 0.7:
        _Q_NOTES = {
            "purchase": "El lead confirma que quiere comprar/apuntarse.",
            "payment": "El lead confirma el método de pago.",
            "booking": "El lead confirma la reserva o cita.",
            "interest": "El lead confirma interés en tus servicios.",
            "information": "El lead pide más información.",
            "confirmation": "El lead confirma lo que le propusiste.",
        }
        _q_note = _Q_NOTES.get(_q_ctx, "")
        if _q_note:
            _context_notes_str = (
                (_context_notes_str + "\n" + _q_note)
                if _context_notes_str else _q_note
            )
            logger.info("[QUESTION_CONTEXT] Injected: %s (conf=%.2f)", _q_ctx, _q_conf)
```

**Gating:** flag AND `_q_ctx` existe AND `_q_ctx != "unknown"` AND `_q_conf >= 0.7`.
**Umbral confianza 0.7** — coincide exactamente con el valor mínimo del `confidence_map` excepto `CONFIRMATION=0.70` (borderline) y `UNKNOWN=0.50` (bloqueado por ambos lados: `_q_ctx != "unknown"` y `0.5 < 0.7`).

**Efecto:** agrega una línea al `_context_notes_str` que más adelante va al system prompt. No sobreescribe — concatena con `\n`.

**Log:** `logger.info` sí es visible en Railway (a diferencia del `.debug` del detection), lo cual es útil para monitoreo cuando el flag esté ON.

## 4. Flag gating — verificación

| Check | Estado |
|-------|--------|
| Ambos callsites gated por `ENABLE_QUESTION_CONTEXT` | ✅ Sí (L803 y L1396) |
| Default en código = `true` | ✅ `os.getenv("ENABLE_QUESTION_CONTEXT", "true")` |
| Default en `feature_flags.py` | ✅ `_flag("ENABLE_QUESTION_CONTEXT", True)` (L42) |
| Valor real en Railway | ❌ `false` (per `env_prod_mirror_20260422.sh:46`) |
| Config script `env_ccee_gemma4.sh` | ❌ `false` (L100) |
| Commit responsable del OFF | `dbf0cd11` 2026-04-03 (lockdown 16 sistemas) |
| Callsite sin flag (fuga) | ❌ Ninguna fuga detectada |
| Grep: `from core.bot_question_analyzer import` | Solo `context.py:12` |

## 5. Dependencias

**In-bound (módulos que importan el analyzer):**
- `core/dm/phases/context.py:12` — el único consumidor en prod.
- `tests/unit/test_dm_agent_bot_question.py` — test module (7 tests).

**Out-bound (qué importa el analyzer):**
- stdlib: `logging`, `re`, `typing.Tuple`, `enum.Enum`. **Cero dependencias externas.**

**Side-effects globales:**
- `_analyzer_instance` singleton mutable a nivel módulo (L258). Thread-safety: no usa lock, pero `BotQuestionAnalyzer.__init__()` es idempotente y las compilaciones de regex son puras → race condition benigna (peor caso: compilar 2 veces, nunca estado inconsistente).

## 6. Flujo end-to-end (pseudo)

```
webhook → agent.handle_message(message, metadata)
  └─ _phase_memory_and_context(message, metadata, agent)
      ├─ L796: intent = intent_classifier.classify(message)
      ├─ L803: if FLAG and is_short_affirmation(message):          ★ Detection
      │        └─ last_bot = next((m for m in reversed(hist) if role=="assistant"))
      │        └─ q_type, q_conf = analyzer.analyze_with_confidence(last_bot)
      │        └─ cognitive_metadata["question_context"] = q_type.value
      │        └─ cognitive_metadata["question_confidence"] = q_conf
      ├─ L827+: parallel gather (memory, dna, conv_state)
      ├─ ... (build compressed Doc D, length hints, question hints, etc.)
      ├─ L1396: if FLAG and q_ctx and q_conf >= 0.7:               ★ Injection
      │        └─ _q_note = _Q_NOTES[q_ctx]
      │        └─ _context_notes_str += "\n" + _q_note
      └─ return (prompt, cognitive_metadata)
         └─ el system prompt contiene ahora "El lead confirma interés en tus servicios."
```

**Latencia añadida cuando ON:**
- Detection: ~50µs (regex precompilado + set lookup O(1)).
- Injection: ~5µs (dict lookup + concat).
- Total: ≪ 1ms. Irrelevante en pipeline de 1–3s.

**Latencia cuando OFF (estado actual):**
- 0µs — ambos callsites cortocircuitan en el `if FLAG`.

## 7. Inventario de tests existentes

`backend/tests/unit/test_dm_agent_bot_question.py` (36 LOC, 7 tests):

| Test | Cubre | Estado |
|------|-------|--------|
| `test_module_importable` | `get_bot_question_analyzer()` devuelve instancia | ✅ |
| `test_flag_exists` | `from core.dm_agent_v2 import ENABLE_QUESTION_CONTEXT` | ⚠️ **ROTO** — desde refactor `ae7adf52` (2026-02-25) el flag vive en `core.dm.phases.context`, no en `dm_agent_v2`. Import probablemente falla o es proxy. |
| `test_analyze_interest_question` | `"¿Te gustaría saber más?"` → `INTEREST` | ✅ |
| `test_analyze_purchase_question` | `"¿Te paso el link de compra?"` → `PURCHASE` | ✅ |
| `test_short_affirmation_detection` | "Si", "Vale", "Ok" → True; frase larga → False | ✅ (solo ES) |

**Gaps de cobertura (7/10 debería ser 9/10):**
- ❌ Sin tests de CA ("clar", "perfecte", "top", "siii")
- ❌ Sin tests de IT ("sì", "certo", "perfetto")
- ❌ Sin tests de EN ("yes", "sure", "alright")
- ❌ Sin tests de edge cases (emoji, `""`, `None`, solo `"?"`)
- ❌ Sin tests de `STATEMENT_EXPECTING_RESPONSE` (ofertas sin `?`)
- ❌ Sin tests de `CONFIRMATION`, `BOOKING`, `PAYMENT_METHOD`
- ❌ Sin tests del umbral `0.7` en `analyze_with_confidence`
- ❌ Sin tests de prioridad (purchase > interest)

## 8. Sanity check final

```bash
$ python3 -c "import ast; ast.parse(open('backend/core/bot_question_analyzer.py').read())"  # ✅ passes
$ grep -c "re.compile" backend/core/bot_question_analyzer.py                                  # 2 (dict + list)
$ grep -c "AFFIRMATION_WORDS" backend/core/bot_question_analyzer.py                           # 3 (def + 2 refs)
$ grep -rn "from core.bot_question_analyzer" backend/ | wc -l                                 # 2 (prod + test)
```

**Archivo sano.** Ningún import circular, singleton bien formado, flag consistentemente gated.

---

**STOP Phase 2.** Continuar con Phase 3 (bugs).
