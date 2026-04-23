# Bot Question Analyzer — Descripción y Valor

**Fecha:** 2026-04-23
**Sistema:** Bot Question Analyzer
**Archivo principal:** `backend/core/bot_question_analyzer.py` (330 LOC)
**Entry points:** `get_bot_question_analyzer()`, `is_short_affirmation(msg)`
**Capa pipeline:** PRE-LLM (detection + prompt injection)
**Estado actual:** OFF en Railway (flag `ENABLE_QUESTION_CONTEXT=false`)

---

## 1. Qué hace

El Bot Question Analyzer resuelve un problema de turn-taking: cuando el lead responde con un mensaje corto ("Si", "Vale", "Ok", "Clar"), el LLM sin contexto genera una respuesta genérica tipo "¡Genial!" en vez de avanzar sobre lo que el bot preguntó. El módulo expone dos funciones:

1. **`is_short_affirmation(message: str) -> bool`**
   Detector de afirmaciones breves del lead. Usa un diccionario literal `AFFIRMATION_WORDS` con ~70 términos multilingual (ES, CA, IT, EN). Normaliza a `lower().strip()`, descarta mensajes >30 chars, y acepta 1–3 palabras cuyas raíces (sin `!.,?`) estén todas en el diccionario.

2. **`BotQuestionAnalyzer.analyze_with_confidence(bot_message) -> (QuestionType, float)`**
   Clasifica el último mensaje del bot en uno de 7 tipos (`PURCHASE`, `PAYMENT_METHOD`, `BOOKING`, `INTEREST`, `INFORMATION`, `CONFIRMATION`, `UNKNOWN`) mediante búsqueda regex por prioridad (compra primero para resolver ambigüedad cuando hay link). Si no hay `?` ni match, revisa `STATEMENT_EXPECTING_RESPONSE` (ofertas/precios/propuestas/reacciones) y devuelve `INTEREST` para cubrir statements que esperan feedback. Confianza por tipo: 0.92 (purchase) → 0.70 (confirmation) → 0.50 (unknown).

## 2. Casos de uso (prod)

`core/dm/phases/context.py` usa el analizador en dos puntos del pipeline:

- **Detection (L803):** si `is_short_affirmation(lead_msg)` y hay mensaje previo del bot → llama `analyze_with_confidence(last_bot_msg)` y escribe en `cognitive_metadata`: `question_context`, `question_confidence`, `is_short_affirmation`.
- **Injection (L1396):** si `question_confidence >= 0.7` y el tipo no es `unknown` → agrega una nota literal al prompt:
  ```
  purchase → "El lead confirma que quiere comprar/apuntarse."
  payment  → "El lead confirma el método de pago."
  booking  → "El lead confirma la reserva o cita."
  interest → "El lead confirma interés en tus servicios."
  information → "El lead pide más información."
  confirmation → "El lead confirma lo que le propusiste."
  ```

Ejemplo canónico (del docstring del módulo):
```
Bot: "¿Te gustaría saber más sobre el curso?"
Lead: "Si"
  └─ Sin contexto: ACKNOWLEDGMENT genérico → "¡Qué bueno!"
  └─ Con contexto: INTEREST @ 0.85 → inyecta "El lead confirma interés en tus servicios."
                   → LLM responde con info del curso en vez de ACK vacío
```

## 3. Valor hipótesis

**Problema que ataca:** *affirmation collapse* — el LLM base, sin señal explícita, trata "Si" como fin de turno y cierra con un ACK. Esto produce:
- Pérdida de momentum comercial (lead confirma interés → bot no envía link).
- Ruptura de turn-taking (bot pregunta → lead confirma → bot repregunta lo mismo).
- Dilución de coherencia (el "si" queda huérfano semánticamente).

**Dimensiones CCEE potencialmente afectadas (hipótesis):**
| Dimensión | Impacto esperado | Por qué |
|-----------|------------------|---------|
| **L3 turn-taking** | ↑↑ | Resuelve mismatch bot_question → short_affirmation |
| **S2 response quality (coherence)** | ↑ | Nota anclada al intent evita ACKs huérfanos |
| **H2 dialogue flow** | ↑ | Reduce re-preguntas y loops de confirmación |
| **S3 strategic alignment** | ↑ leve | Prioridad `PURCHASE > INTEREST` facilita cierre comercial |
| **S1 style fidelity** | neutro/↓ leve | Nota es texto meta no-stylistic; podría romper tono si se inserta mal |

**Magnitud esperada:** sistema tactical, score menor que sistemas identity (Doc D, few-shots). Banda estimada **+0.5 a +2.0** en composite v5 si la hipótesis se confirma — justifica gate KEEP ≥ +1.0.

## 4. Por qué está OFF en Railway

**Commit responsable:** `dbf0cd11` (2026-04-03) — *"chore: turn OFF 16 unaudited systems pending forensic audit"*.

El flag `question_context` fue apagado junto a otros 15 sistemas (commitment_tracker, citations, length_hints, question_hints, style_analyzer, score_before_speak, response_fixes, clone_score, fact_tracking, few_shot, etc.) como parte del **lockdown forense**: cerrar la superficie de sistemas no auditados antes de medir baseline estable. No fue regresión medida — fue precaución arquitectónica.

**Estado en archivos de config:**
- `backend/config/env_prod_mirror_20260422.sh:46` → `export ENABLE_QUESTION_CONTEXT=false`
- `backend/config/env_ccee_gemma4.sh:100` → `export ENABLE_QUESTION_CONTEXT=false  # line 42 — pregunta anterior`
- Default en código: `true` (`core/dm/phases/context.py:22`, `core/feature_flags.py:42`)

**Consecuencia de la reclasificación (2026-04-23):**
Tras el scout `9ca9ea2a`, el sistema pasa de "no-optimizado-ON" a **"no-optimizado-OFF-por-flag"**. Código instanciado y funcional, pero ruta prod bloqueada por env var. Se audita igual porque el plan de medición requiere activar el flag en A/B.

## 5. Trayectoria histórica

| Commit | Fecha | Autor | Qué pasó |
|--------|-------|-------|----------|
| `690c0473` | 2026-01-11 | Claude | Creación — context-aware intent classification for short affirmations |
| `8a045a0b` | 2026-01-11 | Claude | 6 targeted improvements a intelligence |
| `70741299` | 2026-01-23 | Manel | fix: Payment link delivery + ACKNOWLEDGMENT detection |
| `b8cf8ce0` | 2026-02-15 | Manel | Phase 2 massive debug — tocado en 700+ issues globales |
| `dfb56803` | 2026-03-27 | Manel | feat: connect Question Context to pipeline — fix affirmation collapse (wiring formal a context.py) |
| `dbf0cd11` | 2026-04-03 | Manel | chore: turn OFF 16 unaudited systems (flag → false) |
| `9ca9ea2a` | 2026-04-23 | Manel | scout: reclasificación a "no-optimizado-OFF" |

**Edad:** 3.5 meses (primer commit 2026-01-11).
**Última vez optimizado:** 2026-03-27 (wiring a pipeline).
**Sin cambios desde el apagado:** 20 días → tests potencialmente desincronizados de cambios downstream.

## 6. Alcance de la auditoría

1. Forense línea a línea del analyzer + ambos callsites + flag gating.
2. Bugs: hardcoding, edge cases, consistencia, estado de tests.
3. Papers/repos: turn-taking 2024–2026, affirmation detection multilingual, question tracking.
4. Optimización data-derived (vocab + métricas + tests 9/10 ES/CA/EN).
5. Plan de medición CCEE 50×3 A/B (flag OFF vs ON), gates ±1.0 sobre baseline v5=67.7.

---

**STOP Phase 1.** Continuar con Phase 2 (forense línea a línea).
