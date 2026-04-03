# Auditoría Forense — Phase 5: Postprocessing
**Fecha:** 2026-03-31
**Auditor:** Claude Sonnet 4.6
**Archivo principal:** `core/dm/phases/postprocessing.py` (506 líneas)
**Estado previo:** Nunca auditado individualmente

---

## 1. ¿Qué es este sistema?

Phase 5 es la **última capa antes de que la respuesta llegue al lead**. Todo lo que pasa aquí es visible al usuario final. Contiene 25 sistemas concatenados:

| # | Sistema | Flag | Estado default | Acción |
|---|---------|------|----------------|--------|
| A2 | Loop detection (exact duplicate) | — siempre activo — | ON | Log + flag, no reemplaza |
| A2b | Intra-response char repetition | — siempre activo — | ON | Trunca si >50% coverage |
| A2c | Sentence deduplication | — siempre activo — | ON | Deduplica si ≥3× |
| 7a | Output validation (links) | `ENABLE_OUTPUT_VALIDATION` | ON | Corrige links incorrectos |
| 7a2 | Response fixes | `ENABLE_RESPONSE_FIXES` | ON | Typos, formato, identidad |
| 7a2b3 | Blacklist replacement (Doc D) | — siempre activo — | ON | Palabras/emojis prohibidos |
| 7a2c | Question removal | `ENABLE_QUESTION_REMOVAL` | ON | Elimina preguntas genéricas |
| 7a3 | Reflexion | `ENABLE_REFLEXION` | OFF | Análisis calidad (legacy) |
| 7a4 | SBS (Score Before Speak) | `ENABLE_SCORE_BEFORE_SPEAK` | OFF | Retry si score < 0.7 |
| 7a4b | PPA (Post Persona Alignment) | `ENABLE_PPA` | OFF | Refinamiento persona |
| 7b | Guardrails | `ENABLE_GUARDRAILS` | ON | Precios, URLs, off-topic |
| 7b_len | Length enforcement | `ENABLE_LENGTH_CONTROLLER` | ON | Soft guidance por tipo msg |
| 7b2 | Style normalization | `ENABLE_STYLE_NORMALIZER` | ON | Emojis/exclamaciones desde calibración |
| 7c | Instagram formatting | — siempre activo — | ON | `format_message()` |
| 7d | Payment link injection | — condicional intent — | ON si purchase_intent | Inyecta link de pago |
| CS | CloneScore real-time | `ENABLE_CLONE_SCORE` | OFF | Score estilo (CPU) |
| 9 | Lead score update | — siempre activo — | ON | **Síncrono, bloquea** |
| 9a | Conversation state update | — siempre activo — | ON | Fire-and-forget |
| 9c | Email capture | `ENABLE_EMAIL_CAPTURE` | OFF | Captura email lead |
| bg | Background post-response | — siempre activo — | ON | Fire-and-forget |
| mem | Memory extraction | `ENABLE_MEMORY_ENGINE` | OFF | Fire-and-forget |
| echo | Commitment tracking | `ENABLE_COMMITMENT_TRACKING` | ON | Fire-and-forget |
| esc | Escalation notification | — siempre activo — | ON | Fire-and-forget |
| 10b | Message splitting | `ENABLE_MESSAGE_SPLITTING` | ON | Bubbles con delay |
| conf | Confidence scoring | — siempre activo — | ON | Multi-factor score |

---

## 2. Bugs encontrados

### BUG-PP-1: 8 flags duplicados — constantes de módulo vs singleton central (MEDIUM)
**Ubicación:** `postprocessing.py:24-33`

```python
# postprocessing.py — PATRÓN INCORRECTO
ENABLE_OUTPUT_VALIDATION = os.getenv("ENABLE_OUTPUT_VALIDATION", "true").lower() == "true"
ENABLE_RESPONSE_FIXES = os.getenv("ENABLE_RESPONSE_FIXES", "true").lower() == "true"
ENABLE_QUESTION_REMOVAL = os.getenv("ENABLE_QUESTION_REMOVAL", "true").lower() == "true"
ENABLE_REFLEXION = os.getenv("ENABLE_REFLEXION", "false").lower() == "true"
ENABLE_PPA = os.getenv("ENABLE_PPA", "false").lower() == "true"
ENABLE_SCORE_BEFORE_SPEAK = os.getenv("ENABLE_SCORE_BEFORE_SPEAK", "false").lower() == "true"
ENABLE_GUARDRAILS = os.getenv("ENABLE_GUARDRAILS", "true").lower() == "true"
ENABLE_EMAIL_CAPTURE = os.getenv("ENABLE_EMAIL_CAPTURE", "false").lower() == "true"
ENABLE_MESSAGE_SPLITTING = os.getenv("ENABLE_MESSAGE_SPLITTING", "true").lower() == "true"
ENABLE_LENGTH_CONTROLLER = os.getenv("ENABLE_LENGTH_CONTROLLER", "true").lower() == "true"
```

Estos 10 flags también existen en `core/feature_flags.py` (la detección consolidó sus flags en la última auditoría). Consecuencias:
1. **No aparecen en `flags.to_dict()`** → invisibles para observabilidad y ablación
2. **Módulo-level constants** → se leen 1 vez al import, no se pueden cambiar sin reiniciar
3. **Inconsistencia**: `detection.py` usa `flags.xxx`, `postprocessing.py` usa constantes locales

**Fix:** Reemplazar todas las constantes locales por `from core.feature_flags import flags` y usar `flags.xxx`.

---

### BUG-PP-2: `detection.language` no existe — siempre cae en `"ca"` (HIGH — Universalidad)
**Ubicación:** `postprocessing.py:230, 257`

```python
detected_language=detection.language if hasattr(detection, "language") else "ca",
```

`DetectionResult` (en `core/dm/models.py`) no tiene campo `language`:
```python
@dataclass
class DetectionResult:
    frustration_level: float = 0.0
    frustration_signals: Any = None
    context_signals: Any = None
    pool_response: Optional["DMResponse"] = None
    cognitive_metadata: Dict[str, Any] = field(default_factory=dict)
```

Resultado: el `hasattr` SIEMPRE falla → `detected_language` es siempre `"ca"`.

**Impacto real:**
- SBS y PPA (ambos desactivados en prod) usarían siempre Catalán
- Para Stefano (IT) y leads en inglés: el scorer de alineación evaluaría contra patrones catalanes
- Cuando SBS/PPA se activen: scores erróneos → posibles false retries

**Fix:** El lenguaje detectado vive en `context_signals` (DetectedContext) o en `cognitive_metadata`. La corrección correcta es:
```python
detected_language = (
    (detection.context_signals.detected_language if detection.context_signals and hasattr(detection.context_signals, "detected_language") else None)
    or cognitive_metadata.get("detected_language", "ca")
)
```

O más pragmáticamente: leer `cognitive_metadata.get("detected_language", "ca")` que es donde el context_detector lo depositaría.

---

### BUG-PP-3: 3 flags inline no están en el registro central (MEDIUM)
**Ubicación:** `postprocessing.py:349, 409, 424`

```python
if os.getenv("ENABLE_CLONE_SCORE", "false").lower() == "true":    # línea 349
if os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true":  # línea 409
if os.getenv("ENABLE_COMMITMENT_TRACKING", "true").lower() == "true":  # línea 424
```

Ninguno está en `feature_flags.py`. Especialmente `ENABLE_COMMITMENT_TRACKING` con default `"true"` es peligroso: corre en producción, tracking todos los commits, sin que aparezca en `flags.to_dict()` ni en el ablation runner.

**Fix:** Añadir a `feature_flags.py` y referenciar con `flags.xxx`.

---

### BUG-PP-4: Step 9a — sync DB calls sin `asyncio.to_thread()` (HIGH)
**Ubicación:** `postprocessing.py:365-373`

```python
# Step 9a: Update conversation state machine (fire-and-forget)
try:
    from core.conversation_state import get_state_manager
    state_mgr = get_state_manager()
    conv_state = state_mgr.get_state(sender_id, agent.creator_id)        # ← DB call síncrono
    state_mgr.update_state(conv_state, message, intent_value, formatted_content)  # ← DB call síncrono
except Exception as e:
    logger.debug(f"[STATE] update failed: {e}")
```

`get_state()` y `update_state()` son operaciones síncronas que hacen I/O a PostgreSQL. Ejecutarlas directamente en el event loop async **bloquea** el event loop para todo el proceso durante el tiempo del round-trip DB (típicamente 2-20ms, pero hasta 200ms bajo contención).

Viola explícitamente la regla de CLAUDE.md:
> "Background jobs: always use `asyncio.to_thread()` for sync DB operations in async context."

El mismo patrón fue el BUG que se fixeó en el DNA Engine durante la auditoría de fase2_4 (commit `4c9f8b5e`).

**Fix:**
```python
await asyncio.to_thread(
    lambda: state_mgr.update_state(
        state_mgr.get_state(sender_id, agent.creator_id),
        message, intent_value, formatted_content
    )
)
```

---

### BUG-PP-5: Duplicate label "Step 7b" (LOW — documentación)
**Ubicación:** `postprocessing.py:270, 304`

```python
# Step 7b: Apply guardrails validation      (línea 270)
# Step 7b: Apply soft length guidance ...   (línea 304)
```

Dos sistemas diferentes con el mismo identificador. El segundo debería ser "Step 7c" o similar. Indica que el sistema de step-numbering está desactualizado respecto al código actual.

---

### BUG-PP-6: A2 loop detection — sólo compara con el último mensaje, no ventana (LOW)
**Ubicación:** `postprocessing.py:58-61`

```python
last_bot_msgs = [m["content"] for m in history if m.get("role") == "assistant"][-1:]
```

Detecta `"A" → "A"` pero no `"A" → "B" → "A" → "B"` (patrón alternante). La decisión de LOG ONLY fue deliberada (comentario explicativo presente). No es un bug crítico, es una limitación documentada.

---

## 3. Universalidad

| Dimensión | Iris (CA) | Stefano (IT) | Leads EN | Veredicto |
|-----------|-----------|--------------|----------|-----------|
| A2/A2b/A2c repetition | ✅ | ✅ | ✅ | Universal |
| Response fixes | ✅ | ✅ | ✅ | Universal |
| Blacklist (Doc D) | Datos de Iris | Datos de Stefano | — | Universal (data-driven) |
| Question removal | Calibración Iris | Calibración Stefano | Fallback 10% | Universal |
| Style normalization | Calibración Iris | Calibración Stefano | Fallback | Universal |
| **SBS/PPA detected_language** | ✅ "ca" OK | ❌ "ca" wrong | ❌ "ca" wrong | **BUG-PP-2** |
| Guardrails | ✅ | ✅ | ✅ | Universal |
| Payment link injection | ✅ | ✅ | ✅ | Universal |
| Conversation state update | ✅ OK | ✅ OK pero **bloquea** | ✅ OK pero **bloquea** | **BUG-PP-4** |

---

## 4. Sistemas por estado para ablación

| Sistema | Flag en registry? | Ablatable? | Notas |
|---------|-------------------|------------|-------|
| A2/A2b/A2c | NO — siempre activo | Sólo desactivable comentando código | Debería tener flag |
| Output validation | `output_validation` en flags ✅ | ✅ | Pero código usa constante local |
| Response fixes | `response_fixes` en flags ✅ | ✅ | Pero código usa constante local |
| Question removal | `question_removal` en flags ✅ | ✅ | Pero código usa constante local |
| Guardrails | `guardrails` en flags ✅ | ✅ | Pero código usa constante local |
| Message splitting | `message_splitting` en flags ✅ | ✅ | Pero código usa constante local |
| Commitment tracking | ❌ no en registry | ❌ no ablatable via runner | Default TRUE silencioso |
| Clone score | ❌ no en registry | ❌ | Default FALSE OK |
| Memory engine | ❌ no en registry | ❌ | Default FALSE OK |

---

## 5. Resumen ejecutivo de bugs

| Bug | Severidad | Impacto | Fix |
|-----|-----------|---------|-----|
| BUG-PP-1: 10 flags duplicados (constantes vs singleton) | MEDIUM | Invisibles para ablación/observabilidad | Usar `flags.xxx` |
| **BUG-PP-2: detection.language siempre "ca"** | HIGH | SBS/PPA dan scores erróneos para Stefano/EN | Leer de context_signals o cognitive_metadata |
| BUG-PP-3: 3 flags inline no en registry | MEDIUM | Commitment tracking invisible | Añadir a feature_flags.py |
| **BUG-PP-4: Step 9a sync DB en event loop** | HIGH | Bloquea event loop 2-200ms por request | asyncio.to_thread() |
| BUG-PP-5: Duplicate "Step 7b" label | LOW | Documentación confusa | Renombrar |
| BUG-PP-6: A2 ventana=1 sólo | LOW | No detecta loops alternantes | Diseño deliberado, OK |

**2 bugs HIGH, 2 bugs MEDIUM, 2 bugs LOW.**

---

## 6. Recomendación

**NOT READY** como está. BUG-PP-4 bloquea el event loop en cada request — debe corregirse antes de ablación.
BUG-PP-2 afecta SBS/PPA que están desactivados en prod, pero deben estar correctos antes de activarlos.
BUG-PP-1 y PP-3 son deuda técnica que impide la ablación sistemática.
