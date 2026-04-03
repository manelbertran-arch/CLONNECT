# Auditoría Forense — Sistema #3: Context Signals
**Fecha:** 2026-03-31  
**Auditor:** Claude Sonnet 4.6  
**Archivos auditados:**
- `core/context_detector/detectors.py`
- `core/context_detector/orchestration.py`
- `core/context_detector/models.py`
- `core/context_detector/__init__.py`
- `core/dm/phases/detection.py` (invocación)

---

## 1. DESCRIPCIÓN DEL SISTEMA

**¿Qué es?**  
El Context Detector analiza el mensaje del lead para extraer señales contextuales *factuales* — sin instrucciones de comportamiento. Produce un `DetectedContext` que se inyecta en el bloque Recalling del prompt.

**Señales detectadas:**
- B2B / colaboración empresarial
- Nombre del usuario (self-introduction)
- Intención + nivel de interés (delegado a `IntentClassifier`)
- Meta-mensaje (el lead referencia mensajes anteriores)
- Corrección (el lead corrige un malentendido)
- Tipo de objeción (precio / tiempo / confianza / necesidad)
- Sentimiento positivo

**Integración en pipeline:**  
`detection.py:115-122` → `detect_all(message, history)` → resultado almacenado en `DetectionResult.context_signals` → consumido en `context.py:712`.

---

## 2. PASO 1: ¿ES UNIVERSAL?

### Lenguajes declarados
El sistema declara soporte para **6 idiomas**: `es`, `ca`, `en`, `it`, `fr`, `pt`.

**¿Incluye catalán?** ✅ SÍ — todas las dicts tienen clave `"ca"`.  
**¿Incluye japonés?** ❌ NO — no hay `ja`, ni `zh`, `de`, `ar`, `ko`.

### Cobertura real por feature

| Feature | es | ca | en | it | fr | pt | ja/de/ar |
|---------|----|----|----|----|----|----|---------|
| B2B keywords | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| B2B intro pattern | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Meta-message | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Correction | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Objection type | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Name extraction | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Positive sentiment | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |

**Observación:** Las objeciones (price/time/trust/need) sólo tienen keywords para `es`, `ca`, `en`. Los creadores IT/FR/PT no recibirán `objection_type` aunque el lead objete claramente.

---

## 3. PASO 2: BUGS ENCONTRADOS

### BUG-CS1 — CRÍTICO: `build_context_notes()` hardcodeado en español
**Archivo:** `models.py:83-114`  
**Código:**
```python
notes.append(f"Este lead parece representar una empresa/marca...")
notes.append(f"El lead se llama {self.user_name}.")
notes.append("El lead hace referencia a mensajes anteriores.")
notes.append("El lead está corrigiendo algo que dijiste.")
notes.append(f"El lead tiene una objeción de {label}.")
```
```python
objection_labels = {
    "price": "precio",
    "time": "tiempo",
    "trust": "confianza",
    "need": "necesidad",
}
```
**Impacto:** Las notas contextuales inyectadas en el bloque Recalling del LLM están **siempre en español**, independientemente del idioma del creador. Un creador italiano o inglés recibirá el sistema en español, lo que puede desorientar al LLM sobre el idioma de respuesta esperado.

**Severidad:** Alta — afecta a todos los creadores no-ES.

---

### BUG-CS2 — MEDIO: Llamadas a stubs descartadas (dead code activo)
**Archivo:** `orchestration.py:103-104`  
```python
# Step 9. Backward compat: frustration/sarcasm stubs (always return empty)
detect_frustration(message, history)
detect_sarcasm(message)
```
Los resultados **no se asignan a nada**. Son stubs que devuelven objetos vacíos. El código llama funciones y descarta el resultado — es confuso y engañoso para quien lee el código. No es un bug funcional pero sí un code smell que puede llevar a creer que la detección activa está ocurriendo.

**Severidad:** Baja (no causa errores) — pero genera confusión.

---

### BUG-CS3 — MEDIO: B2B `company_context` fallbacks en español
**Archivo:** `detectors.py:254-259`  
```python
context_map = {
    "previous_work": "Cliente B2B con historial",
    "keyword": "Contexto B2B",
    "company_intro": "Empresa",
}
result.company_context = context_map.get(result.collaboration_type, "B2B")
```
Si el B2B se detecta por keyword pero no hay intro de empresa, el `company_context` será `"Cliente B2B con historial"` o `"Contexto B2B"` — strings en español inyectados en el prompt de cualquier creador independientemente del idioma.

**Severidad:** Media — afecta creadores EN/IT/FR/PT.

---

### BUG-CS4 — DISEÑO: Sarcasmo NO detectado (delegado al LLM sin señal)
**Archivo:** `detectors.py:336-339`  
```python
def detect_sarcasm(message: str):
    """Stub — sarcasm detection removed (LLM handles natively)."""
    from .models import SarcasmResult
    return SarcasmResult()
```
El sarcasmo en español informal ("sí, claro, qué buena idea...") es **no detectado**. La racionale es que el LLM lo maneja nativamente. Esto es parcialmente cierto, pero:
1. Sin una señal explícita en el prompt, el LLM puede malinterpretar sarcasmo sutil.
2. El sarcasmo en español informal (ironía, hipérbole) es especialmente difícil para modelos entrenados mayoritariamente en inglés.
3. La literatura (Ghosh & Veale, 2016; Riloff et al., 2013) muestra F1 de ~0.65-0.75 para detección automática de sarcasmo — no trivial.

**Pregunta específica:** ¿Detecta sarcasmo en `"Sí, claro, como si fuera tan fácil"` (español informal)?  
**Respuesta:** **No.** `detect_sarcasm` devuelve `SarcasmResult(is_sarcastic=False)` siempre.

**Severidad:** Media — trade-off consciente, pero sin documentación de la decisión ni monitoring de casos fallidos.

---

### BUG-CS5 — BAJO: Sentimiento positivo incompleto (sólo ES/CA/EN)
**Archivo:** `orchestration.py:91-99`  
```python
positive_patterns = [
    r"\bgracias\b", r"\bgràcies\b", r"\bthanks?\b",
    r"\bgenial\b", r"\bperfecto\b", r"\bexcelente\b",
    r"\bincre[ií]ble\b", r"\bme encanta\b", r"\bgreat\b",
    r"\bperfecte\b", r"\bfantàstic\b",
]
```
Faltan: `merci`, `grazie`, `ottimo`, `parfait`, `formidable`, `obrigado/obrigada`, `incrível`.

**Severidad:** Baja — sentimiento positivo sólo es informativo, no altera el flujo.

---

### BUG-CS6 — BAJO: `_DIALECT_TO_LANG` en detection.py sólo tiene 3 idiomas
**Archivo:** `detection.py:16-21`  
```python
_DIALECT_TO_LANG = {
    "catalan": "ca", "catala": "ca", "català": "ca",
    "english": "en", "anglès": "en", "ingles": "en",
    "castellano": "es", "español": "es", "spanish": "es",
    "neutral": "es",
}
```
Si un creador tiene dialect `"italian"`, `"french"`, o `"portuguese"` — el fallback es `"es"` y recibe recursos de crisis en español. Este bug fue parcialmente corregido en la auditoría anterior (BUG-S2 fix), pero sólo añadió ES/CA/EN.

**Severidad:** Baja para el portafolio actual (creadores principalmente ES/CA), media a largo plazo.

---

### BUG-CS7 — BAJO: `OBJECTION_KEYWORDS` incompleto (IT/FR/PT sin cobertura)
**Archivo:** `detectors.py:124-153`  
Las categorías `price`, `time`, `trust`, `need` sólo tienen keywords para `es`, `ca`, `en`. Un lead italiano que dice `"troppo caro"` o `"non posso permettermelo"` no generará `objection_type = "price"`.

**Severidad:** Baja para el portafolio actual, media si se expande a IT/FR/PT.

---

## 4. PASO 3: ¿ES CORRECTO EL COMPORTAMIENTO?

### Sarcasmo en español informal — test manual

| Mensaje | Resultado esperado | Resultado real |
|---------|-------------------|----------------|
| `"Sí claro qué buena idea"` | `is_sarcastic=True` | `SarcasmResult(False)` — stub |
| `"Anda que no es caro para nada..."` | sarcasmo implícito | no detectado |
| `"Claro que sí, como si no tuviera nada mejor que hacer"` | sarcasmo | no detectado |

**Conclusión:** El sarcasmo en español informal **no se detecta en ningún caso**. El LLM es la única defensa — y es suficiente para ironía obvia, pero falla en sarcasmo sutil o culturalmente específico.

### B2B — test de señales universales

| Mensaje | Idioma | Detecta B2B? |
|---------|--------|-------------|
| `"Soy María de Zara, colaboración"` | es | ✅ |
| `"Sóc la Laura de Nike"` | ca | ✅ |
| `"I'm John from Google"` | en | ✅ |
| `"Sono Marco di Gucci"` | it | ✅ |
| `"Je suis Sophie de L'Oréal"` | fr | ✅ |
| `"Meu nome é Ana da Natura"` | pt | ✅ |
| `"私はSonyのTanakaです"` | ja | ❌ — no detecta |

**Conclusión:** B2B detection es sólida para los 6 idiomas soportados. El patrón `[name] de/from/di/da [company]` cubre los casos principales correctamente.

---

## 5. PASO 4: PAPERS Y ALINEAMIENTO ACADÉMICO

### Detección de B2B / intención empresarial
- **Relevante:** Liu et al. (2019) *"BERT for e-commerce intent classification"* — el patrón de intro estructurada `[name] de [company]` es un heurístico sólido sin LLM, alineado con literatura de slot-filling para diálogos de negocio.
- **Gap:** No hay scoring de confianza para B2B (binario `is_b2b`). Los papers recomiendan confidence scores para intent detection.

### Context-aware dialogue
- **Relevante:** Dhingra et al. (2016) *"End-to-End Dialogue Systems Using Soft KB Lookup"* — justifica el uso de señales contextuales (B2B, corrección, meta-mensajes) como `context_notes` inyectadas al LLM.
- **Alineado:** El diseño fact/behavior separation (observaciones ≠ instrucciones) sigue buenas prácticas de separación de concerns en sistemas de diálogo.

### Sarcasmo
- **Riloff et al. (2013):** Sarcasmo implica contraste positivo-situación negativa → difícil sin contexto externo. El LLM como único detector es arriesgado.
- **Ghosh & Veale (2016):** Modelos LSTM alcanzan F1=0.72 en sarcasmo inglés. Para español informal (registro coloquial, irony markers dialectales) la precisión baja significativamente.
- **Recomendación académica:** Añadir al menos detección de patrones de sarcasmo léxico español ("sí claro", "anda que", "como no", "cómo no") como señal de apoyo al LLM.

### Multilingual intent detection
- **Conneau et al. (2020) XLM-RoBERTa:** Los modelos multilingüales tienen rendimiento desigual por idioma — el español obtiene mejores resultados que el italiano o el portugués en zero-shot transfer. El sistema regex compensa correctamente esta limitación con dicts explícitas por idioma.

---

## 6. PASO 5: RENDIMIENTO Y EFICIENCIA

| Aspecto | Status |
|---------|--------|
| Llamadas LLM en `detect_all` | 0 — pure regex/rule-based ✅ |
| Latencia esperada | <1ms para mensajes típicos ✅ |
| Dead code (`detect_frustration`/`detect_sarcasm` sin asignar) | ❌ — confuso |
| Caching de detecciones | No aplica — stateless ✅ |

---

## 7. PASO 6: RECOMENDACIONES

### CRÍTICO (fix ahora)

**FIX-CS1:** `build_context_notes()` debe generar notas en inglés (lengua franca del LLM) o ser configurable por idioma del creador. Las notas en español en un creador inglés pueden sesgar el LLM hacia responder en español.

**Propuesta:**
```python
# Usar inglés como lengua franca del LLM (más robusto)
# o pasar creator_lang como parámetro a build_context_notes()
notes.append(f"Lead appears to represent a company/brand ({self.company_context}).")
notes.append(f"Lead's name is {self.user_name}.")
```

### MEDIO (próxima iteración)

**FIX-CS2:** Eliminar las llamadas a stubs sin asignar (`orchestration.py:103-104`). Son dead code activo que confunde.

**FIX-CS3:** `context_map` en `detect_b2b()` — usar inglés o tags neutrales.

**FIX-CS4:** Añadir `_DIALECT_TO_LANG` entries para `it`, `fr`, `pt` en `detection.py`.

### BAJO (backlog)

**FIX-CS5:** Añadir patrones léxicos de sarcasmo español informal como señal de apoyo (no bloqueante — sólo annotation).

**FIX-CS6:** Completar `OBJECTION_KEYWORDS` para IT/FR/PT.

**FIX-CS7:** Completar `positive_patterns` para IT/FR/PT.

---

## 8. VEREDICTO FINAL

| Dimensión | Score | Notas |
|-----------|-------|-------|
| Universalidad | 6/10 | 6 idiomas pero B2B context notes siempre en ES |
| Corrección funcional | 8/10 | B2B, meta, correction, objection funcionan bien |
| Sarcasmo | 2/10 | Stub — delegado al LLM sin señal explícita |
| Alineamiento académico | 7/10 | Buena separación fact/behavior; gap en sarcasmo |
| Mantenibilidad | 7/10 | Dicts extensibles pero dead stubs confunden |

**Recomendación:** **OPTIMIZE** — el sistema es funcional y arquitectónicamente sólido (dicts extensibles, fact/behavior separation), pero tiene un bug de universalidad crítico (`build_context_notes` en español) y un gap de sarcasmo que el LLM sólo compensa parcialmente.

**Fix prioritario:** BUG-CS1 (`build_context_notes` → lengua franca inglés).

---

*Auditoría completada: 2026-03-31*
