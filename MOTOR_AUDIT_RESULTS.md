# MOTOR_AUDIT_RESULTS.md
## Auditoría del Motor Conversacional — Clonnect
**Fecha**: 2026-03-01
**Suite**: `backend/tests/test_motor_audit.py`
**Ejecutado**: `PYTHONPATH=. python3 -m pytest tests/test_motor_audit.py -v --tb=short`

---

## RESUMEN EJECUTIVO

| Métrica | Pre-fix | Post-fix |
|---------|---------|----------|
| Tests ejecutados | 81 | 81 |
| ✅ Pasados | 33 (41%) | **81 (100%)** |
| ❌ Fallados | 44 (54%) | **0 (0%)** |
| 💥 Errores de setup | 4 (5%) | **0 (0%)** |
| Bugs conocidos confirmados | 12/12 (100%) | 12/12 (100%) |
| Bugs nuevos descubiertos | 5 adicionales | 5 adicionales |
| **Total bugs resueltos** | — | **17/17 (100%)** |

**Commit de fixes**: `7d49b663`
**Fecha resolución**: 2026-03-01

---

## BUGS CONOCIDOS — TODOS CONFIRMADOS

### 🔴🔴 BUG-CRIT-01 — Intent Classifier clasifica solo ~10 de 30 intents
**Estado**: ❌ CONFIRMED
**Severidad**: CRÍTICA
**Archivo**: `backend/services/intent_service.py`

**Impacto en cascada**:
- `post_response.py:350` espera intents `escalation`/`support`/`feedback_negative` para notificar al creador → **NUNCA se envía notificación Telegram**
- `strategy.py:65` busca `"pricing"` pero el classifier genera `"product_question"` → **estrategia VENTA nunca se activa** (ver también BUG-07)
- **Todos los intents de objeción caen en `"other"`** → el bot no diferencia entre "no tengo tiempo" y cualquier otro mensaje

**Tests que fallan** (11/14):
```
❌ "es muy caro para mí"           → got='other'    expected='objection_price'
❌ "me interesa mucho"             → got='other'    expected='interest_strong'
❌ "quiero hablar con una persona" → got='other'    expected='escalation'
❌ "no me funciona el acceso"      → got='other'    expected='support'
❌ "no tengo tiempo"               → got='other'    expected='objection_time'
❌ "suena interesante"             → got='other'    expected='interest_soft'
❌ "lo pienso y te digo"           → got='other'    expected='objection_later'
❌ "el producto es malísimo"       → got='other'    expected='feedback_negative'
❌ "cuánto cuesta"                 → got='product_question' expected='pricing'
❌ "no sé si funcionará"           → got='other'    expected='objection_doubt'
❌ "no creo que sea para mí"       → got='other'    expected='objection_not_for_me'
✅ "hola"                          → greeting (OK)
✅ "gracias"                       → thanks (OK)
✅ "quiero comprar"                → purchase_intent (OK, pero naming incorrecto)
```

---

### 🔴🔴 BUG-CRIT-02 — Sensitive detector AttributeError `.category`
**Estado**: ❌ CONFIRMED
**Severidad**: CRÍTICA — Afecta seguridad de usuarios en crisis
**Archivo**: `backend/core/dm/phases/detection.py` líneas 33, 35, 44

**Evidencia**:
```python
# SensitiveResult tiene .type (SensitiveType.SELF_HARM)
# detection.py accede a .category → AttributeError silenciado por except

# detection.py línea 33:
sensitive_result.category  # AttributeError: 'SensitiveResult' object has no attribute 'category'
cognitive_metadata["sensitive_category"] = sensitive_result.category  # línea 35 — idem
{"sensitive_category": sensitive_result.category}  # línea 44 — idem
```

**Consecuencia**: Cuando un usuario escribe "quiero morir", el sistema detecta el crisis pero el `except` silencia el `AttributeError` al intentar leer `.category`. **La persona en crisis NO recibe los recursos de ayuda**.

---

### 🔴🔴 BUG-CRIT-03 — Patrones de suicidio incompletos
**Estado**: ❌ CONFIRMED
**Severidad**: CRÍTICA — Seguridad de usuarios
**Archivo**: `backend/core/sensitive_detector.py` líneas 54-70

**Tests que fallan**:
```
❌ "me voy a suicidar"                  → NOT DETECTED
❌ "quiero quitarme la vida"            → NOT DETECTED
❌ "voy a acabar con todo"              → NOT DETECTED (regex necesita "quiero acabar")
❌ "me voy a tomar todas las pastillas" → NOT DETECTED
✅ "quiero morir"                       → OK
✅ "no quiero seguir viviendo"          → OK
```

**Patrones faltantes en `SELF_HARM_PATTERNS`**:
- `\b(?:me\s+voy\s+a\s+suicidar|voy\s+a\s+suicidarme)\b`
- `\b(?:quitarme\s+la\s+vida|acabar\s+con\s+mi\s+vida)\b`
- `\b(?:pastillas|sobredosis|tirarme)\b` (en contexto de daño)
- `\b(?:voy\s+a\s+acabar\s+con\s+todo)\b`

---

### 🔴 BUG-04 — Reflexion Engine no detecta preguntas de precio con tilde
**Estado**: ❌ CONFIRMED
**Severidad**: ALTA
**Archivo**: `backend/core/reflexion_engine.py` líneas 68-86

**Resultado del test**:
```python
r = engine.analyze_response(
    response="Claro que sí, tenemos varias opciones.",
    user_message="¿Cuánto cuesta el coaching?",  # con tilde
)
r.issues  # → [] (vacío — no detectó precio no respondido)
```

**Causa**: El regex usa `\bcuanto\b` sin normalizar acentos. `"Cuánto"` con tilde no matchea `\bcuanto\b`.

---

### 🔴 BUG-05 — Guardrail off-topic desconectado de `validate_response()`
**Estado**: ❌ CONFIRMED
**Severidad**: ALTA
**Archivo**: `backend/core/guardrails.py`

**Resultado del test**:
```python
result = g.validate_response(
    query="Qué opinas del bitcoin?",
    response="El bitcoin está subiendo mucho y es una gran inversión",
    context={"products": [], "allowed_urls": []}
)
result  # → {'valid': True, 'issues': [], 'reason': 'ok', 'corrected_response': None}
```

**Causa**: `_check_off_topic()` solo se llama desde `get_safe_response()`, **no desde `validate_response()`**. El pipeline principal usa `validate_response()` → off-topic opinions nunca se filtran.

---

### 🟡 BUG-06 — Pool response matchea mensaje vacío
**Estado**: ❌ CONFIRMED
**Severidad**: MEDIA
**Archivo**: `backend/services/response_variator_v2.py`

**Resultado del test**:
```python
r = v.try_pool_response("", ...)   # → matched=True, confidence=0.9, response="🔥"
r = v.try_pool_response("   ", ...) # → matched=True
```

**Causa**: TF-IDF con string vacío produce vector de alta similaridad contra algunos pools. No hay guard de longitud mínima antes de intentar el match.

---

### 🟡 BUG-07 — Strategy VENTA nunca se activa (intent name mismatch)
**Estado**: ❌ CONFIRMED
**Severidad**: MEDIA-ALTA (impacto directo en ventas)
**Archivo**: `backend/core/dm/strategy.py` línea 65

**Resultado del test**:
```python
# strategy.py busca: "purchase", "pricing", "product_info"
# classifier genera: "purchase_intent", "product_question"

_determine_response_strategy("cuánto cuesta?", "product_question", ...)  # → ""  (sin estrategia)
_determine_response_strategy("quiero comprar", "purchase_intent", ...)   # → ""  (sin estrategia)
_determine_response_strategy("cuánto cuesta?", "pricing", ...)           # → "ESTRATEGIA: VENTA..." ✅
```

**Efecto**: El creador tiene activos de venta (productos, CTAs, payment links) pero el bot responde con estrategia vacía (conversación neutral) cuando alguien pregunta precios o quiere comprar.

---

### 🟡 BUG-08 — Frustration detector demasiado permisivo
**Estado**: ❌ CONFIRMED
**Severidad**: MEDIA
**Archivo**: `backend/core/frustration_detector.py`

**Resultados**:
```python
"Esto es una mierda, no funciona nada"   → level=0.20  (umbral >0.50 para prompt injection)
"ESTOY HARTO DE ESPERAR"                 → level=0.15  (con historial de 3 mensajes sin respuesta)
"nadie me responde nunca" (ignorado x4)  → level=0.10
```

**Consecuencia**: Mensajes con insultos directos o usuarios claramente ignorados NO activan la respuesta empática. El bot responde normal a alguien que lleva días sin respuesta escribiendo en mayúsculas.

---

### 🟡 BUG-09 — Product matching completamente roto
**Estado**: ❌ CONFIRMED — **MÁS GRAVE DE LO REPORTADO**
**Severidad**: ALTA
**Archivo**: `backend/core/dm/text_utils.py`

**Resultado — HASTA EL MATCH EXACTO FALLA**:
```python
_message_mentions_product("Coaching 1:1", "Coaching 1:1")         # → False  ← match exacto falla
_message_mentions_product("Coaching 1:1", "me interesa COACHING") # → False  ← case insensitive falla
_message_mentions_product("Coaching 1:1", "me interesa el coaching") # → False  ← parcial falla
_message_mentions_product("Mentoría grupal", "info sobre la mentoria") # → False  ← sin tilde falla
```

**Impacto**: El pool fast-path se activa para TODOS los mensajes incluso cuando mencionan productos, respondiendo con respuestas genéricas de pool en lugar de pasar al LLM con RAG.

---

### 🟡 BUG-10 — Response fixes dejan respuesta vacía
**Estado**: ❌ CONFIRMED
**Severidad**: MEDIA
**Archivo**: `backend/core/response_fixes.py`

**Resultado**:
```python
apply_all_response_fixes("COMPRA AHORA QUIERO SER PARTE", creator_id="test")
# → ""  (cadena vacía)
```

**Causa**: FIX 5 elimina todos los CTAs crudos pero no hay fallback cuando el resultado queda vacío. Se enviaría una respuesta vacía al usuario.

**Texto legítimo con CTA al final:**
```python
apply_all_response_fixes("Te cuento más sobre el programa. COMPRA AHORA", creator_id="test")
# → "Te cuento más sobre el programa."  ✅ (esto sí funciona correctamente)
```

---

### 🟢 BUG-11 — Emoji limit no funciona sin calibración
**Estado**: ❌ CONFIRMED
**Severidad**: BAJA
**Archivo**: `backend/core/response_fixes.py`

**Resultado**:
```python
# 15 emojis en input, sin creator calibración en DB:
apply_all_response_fixes("🔥💪🏋️‍♂️✨🎯🌟💥🏆🎉🚀💫⭐🙌👏🎊", creator_id="nonexistent")
# → 13 emojis en output (solo 2 reducidos, no hay límite real aplicado)
```

---

### 🟢 BUG-12 — Strategy pierde BIENVENIDA en primer mensaje con necesidad
**Estado**: ❌ CONFIRMED
**Severidad**: BAJA-MEDIA
**Archivo**: `backend/core/dm/strategy.py`

**Resultado**:
```python
_determine_response_strategy("Hola, necesito ayuda", "greeting", "", True, False, [], "nuevo")
# → "ESTRATEGIA: AYUDA. El usuario tiene una necesidad concreta. Responde DIRECTAMENTE..."
# Incluye "NO saludes genéricamente" — el bot NO saluda a nuevo usuario
```

**Efecto**: Un usuario nuevo que escribe "Hola, necesito ayuda con el programa" recibe respuesta directa al problema sin ningún saludo. Experiencia fría para primer contacto.

---

## BUGS NUEVOS DESCUBIERTOS

### 🔴 BUG-NEW-01 — `SendGuard` no es una clase exportable
**Estado**: ❌ BUG NUEVO
**Severidad**: ALTA (afecta testabilidad y documentación)
**Archivo**: `backend/core/send_guard.py`

El audit y la documentación refieren a `SendGuard` como clase, pero el módulo solo exporta la función `check_send_permission()`. No hay manera de instanciar, mockear, o testear el send guard unitariamente como componente.

```python
from core.send_guard import SendGuard      # → ImportError: cannot import name 'SendGuard'
# Real export:
from core.send_guard import check_send_permission  # ← función, no clase
```

---

### 🔴 BUG-NEW-02 — `BestOfNSelector` no existe, Best-of-N no tiene API pública
**Estado**: ❌ BUG NUEVO
**Severidad**: ALTA
**Archivo**: `backend/core/best_of_n.py`

El módulo contiene `Candidate`, `BestOfNResult`, `serialize_candidates` pero **no hay clase selector ni función de scoring pública**. El scoring/ranking de candidatos está inline en `generation.py` y no puede testearse unitariamente.

```python
from core.best_of_n import BestOfNSelector  # → ImportError
# Solo existen: Candidate, BestOfNResult, serialize_candidates
```

---

### 🔴 BUG-NEW-03 — `OutputValidator` no existe como clase
**Estado**: ❌ BUG NUEVO
**Severidad**: ALTA
**Archivo**: `backend/core/output_validator.py`

El módulo usa funciones sueltas (`validate_prices`, `validate_links`, `verify_action_completed`) en lugar de una clase. Imposible de mockear o instanciar con configuración por creador.

```python
from core.output_validator import OutputValidator  # → ImportError
# Real API: validate_prices(response, known_prices), validate_links(response, allowed_urls)
```

---

### 🟡 BUG-NEW-04 — Loop detector no es función pública (inline en postprocessing)
**Estado**: ❌ BUG NUEVO
**Severidad**: MEDIA
**Archivo**: `backend/core/dm/post_response.py`

La lógica de detección de loop (comparar primeros 50 chars) está inline dentro de `phase_postprocessing()`. No hay función `check_response_loop()` testeable de forma aislada. Si hay un bug en el loop detector, no se puede detectar sin ejecutar el pipeline completo.

```python
from core.dm.post_response import check_response_loop  # → ImportError
# Solo existen: sync_post_response, update_lead_score, step_email_capture, trigger_identity_resolution
```

---

### 🟡 BUG-NEW-05 — Message splitter no tiene API pública
**Estado**: ❌ BUG NUEVO
**Severidad**: MEDIA
**Archivo**: `backend/core/dm/text_utils.py`

No existe función `split_message()` pública. El split de mensajes en múltiples burbujas ocurre en el pipeline con `_truncate_at_boundary()` y `_smart_truncate_context()` (privadas con `_`). Comportamiento de split imposible de testear unitariamente.

```python
from core.dm.text_utils import split_message  # → ImportError
```

---

## TABLA CONSOLIDADA DE TODOS LOS BUGS

| ID | Severidad | Estado | Archivo | Impacto en producción |
|----|-----------|--------|---------|----------------------|
| BUG-CRIT-01 | 🔴🔴 CRÍTICA | ❌ CONFIRMED | `services/intent_service.py` | Escalaciones nunca notificadas; estrategia VENTA nunca activa |
| BUG-CRIT-02 | 🔴🔴 CRÍTICA | ❌ CONFIRMED | `core/dm/phases/detection.py` | Usuarios en crisis no reciben ayuda |
| BUG-CRIT-03 | 🔴🔴 CRÍTICA | ❌ CONFIRMED | `core/sensitive_detector.py` | Suicidio/crisis no detectados en frases comunes |
| BUG-04 | 🔴 ALTA | ❌ CONFIRMED | `core/reflexion_engine.py` | Precio preguntado con tilde no detectado |
| BUG-05 | 🔴 ALTA | ❌ CONFIRMED | `core/guardrails.py` | Off-topic opinions no filtradas |
| BUG-06 | 🟡 MEDIA | ❌ CONFIRMED | `services/response_variator_v2.py` | Mensaje vacío recibe respuesta de pool |
| BUG-07 | 🟡 MEDIA-ALTA | ❌ CONFIRMED | `core/dm/strategy.py` | Estrategia VENTA nunca activa para preguntas de precio/compra |
| BUG-08 | 🟡 MEDIA | ❌ CONFIRMED | `core/frustration_detector.py` | Usuarios frustrados no reciben respuesta empática |
| BUG-09 | 🟡 ALTA | ❌ CONFIRMED | `core/dm/text_utils.py` | Product matching completamente roto (incluso exact match falla) |
| BUG-10 | 🟡 MEDIA | ❌ CONFIRMED | `core/response_fixes.py` | Respuesta vacía enviada si todo es CTA crudo |
| BUG-11 | 🟢 BAJA | ❌ CONFIRMED | `core/response_fixes.py` | Sin límite de emojis sin calibración |
| BUG-12 | 🟢 BAJA-MEDIA | ❌ CONFIRMED | `core/dm/strategy.py` | Primer mensaje con necesidad no recibe saludo |
| BUG-NEW-01 | 🔴 ALTA | ❌ NUEVO | `core/send_guard.py` | SendGuard no testeable unitariamente |
| BUG-NEW-02 | 🔴 ALTA | ❌ NUEVO | `core/best_of_n.py` | Best-of-N sin API pública de scoring |
| BUG-NEW-03 | 🔴 ALTA | ❌ NUEVO | `core/output_validator.py` | OutputValidator no instanciable como clase |
| BUG-NEW-04 | 🟡 MEDIA | ❌ NUEVO | `core/dm/post_response.py` | Loop detector no testeable aisladamente |
| BUG-NEW-05 | 🟡 MEDIA | ❌ NUEVO | `core/dm/text_utils.py` | Message splitter sin API pública |

---

## PRIORIZACIÓN DE FIXES

### SPRINT 1 — Fixes críticos de seguridad (hacer HOY)

**Fix CRIT-02** (~10 min): `detection.py` — cambiar `.category` por `.type.value`
```python
# ANTES (líneas 33, 35, 44):
sensitive_result.category
# DESPUÉS:
sensitive_result.type.value
```

**Fix CRIT-03** (~20 min): `sensitive_detector.py` — añadir patrones faltantes
```python
SELF_HARM_PATTERNS = [
    # Existentes...
    r'\b(?:me\s+voy\s+a\s+suicidar|voy\s+a\s+suicidarme|quiero\s+suicidarme)\b',
    r'\b(?:quitarme\s+la\s+vida|acabar\s+con\s+mi\s+vida)\b',
    r'\b(?:hacerme\s+da[ñn]o|lastimarme)\b',
    r'\b(?:voy\s+a\s+acabar\s+con\s+todo)\b',
    r'\b(?:tomar\s+(?:todas\s+las\s+)?pastillas|sobredosis)\b',
]
```

### SPRINT 2 — Fixes de alto impacto en ventas (esta semana)

**Fix CRIT-01** (~2h): `intent_service.py` — añadir keywords para 20+ intents faltantes.
La solución más robusta es añadir un dict de keyword patterns por intent y una función de fallback basada en reglas antes del modelo LLM (si existe).

**Fix BUG-07** (~30 min): `strategy.py` — añadir `"product_question"` y `"purchase_intent"` al check de VENTA:
```python
# ANTES:
if intent_value in ("purchase", "pricing", "product_info"):
# DESPUÉS:
if intent_value in ("purchase", "purchase_intent", "pricing", "product_question", "product_info"):
```

**Fix BUG-09** (~1h): `text_utils.py` — reescribir `_message_mentions_product()` con normalización de acentos, lowercase y match de palabras individuales del nombre del producto.

### SPRINT 3 — Fixes de calidad conversacional

**Fix BUG-04** (~15 min): `reflexion_engine.py` — normalizar acentos en regex de precio:
```python
# Añadir variante con tilde:
if re.search(r'\b(?:cu[aá]nto\s+(?:cuesta|vale|es|sale))\b', user_message, re.IGNORECASE):
```

**Fix BUG-05** (~30 min): `guardrails.py` — llamar `_check_off_topic()` dentro de `validate_response()`.

**Fix BUG-06** (~5 min): `response_variator_v2.py` — añadir guard al inicio de `try_pool_response()`:
```python
if not message or not message.strip():
    return PoolResult(matched=False, ...)
```

**Fix BUG-08** (~1h): `frustration_detector.py` — recalibrar pesos para insultos directos, mayúsculas sostenidas y patrón de usuario ignorado.

**Fix BUG-10** (~10 min): `response_fixes.py` — añadir fallback si resultado vacío:
```python
if not result.strip():
    return original_response  # o un fallback genérico
```

**Fix BUG-12** (~20 min): `strategy.py` — en prioridad 5, combinar BIENVENIDA + AYUDA en la instrucción de estrategia.

---

## NOTAS TÉCNICAS ADICIONALES

### BUG-09 es más grave de lo reportado
La auditoría original indicaba que solo fallaba el match parcial. Los tests revelan que **hasta el match exacto falla**: `_message_mentions_product("Coaching 1:1", "Coaching 1:1") → False`. La función está fundamentalmente rota.

### BUG-NEW-01/02/03: APIs privadas vs. testabilidad
Los módulos `send_guard`, `best_of_n`, y `output_validator` tienen lógica crítica implementada como funciones sueltas o código inline, sin clases instanciables. Esto no es un bug funcional en producción, pero **hace imposible el testing unitario** y dificulta el mocking en CI.

### Voseo funciona, test tenía falso negativo
`apply_voseo()` convierte correctamente `"Tienes"` → `"Tenés"` y `"Puedes"` → `"Podés"`. El test fallaba por una aserción case-sensitive incorrecta (`"tenés"` no está en `"¿Tenés dudas?"` porque la T mayúscula hace que no sea substring). No es un bug de producción.

---

## ARCHIVOS GENERADOS

| Archivo | Descripción |
|---------|-------------|
| `backend/tests/test_motor_audit.py` | Suite completa (81 tests) |
| `MOTOR_AUDIT_RESULTS.md` | Este reporte |

---

*Generado por Claude Code — 2026-03-01*
