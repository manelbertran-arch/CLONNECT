# Auditoría Fase 6 — Background + Infraestructura Nueva
**Fecha:** 2026-03-31  
**Sistemas auditados:** 31, 32, 33, 34, 8, 38, 39, 40  
**Auditor:** Claude Sonnet 4.6 (línea a línea)

---

## Resumen ejecutivo

| Sistema | Universal | Bugs críticos | ENABLE flag | Estado |
|---------|-----------|---------------|-------------|--------|
| 31. Lead Score Update | ✅ | 1 menor | ❌ no en feature_flags | ⚠️ OK pero inconsistente |
| 32. Lead Categorization | ✅ | 0 | ✅ ENABLE_LEAD_CATEGORIZER | ⚠️ Paralelo a sistema 31 |
| 33. Follower Memory Save | ⚠️ parcial | 2 críticos | ❌ ninguno | 🔴 CRÍTICO |
| 34. Fact Tracking | ⚠️ parcial | 2 | ✅ ENABLE_FACT_TRACKING | ⚠️ DRY violation |
| 8. DNA Trigger Check | ✅ | 1 menor | ✅ ENABLE_DNA_TRIGGERS | ✅ OK |
| 38. Creator Profile Service | ✅ | 1 crítico | ❌ ninguno | ⚠️ Cache bug |
| 39. Auto-Provisioner | ⚠️ parcial | 3 | ❌ ninguno | ⚠️ Hardcodes |
| 40. Style Analyzer | ⚠️ parcial | 1 | ✅ ENABLE_STYLE_ANALYZER | ⚠️ Español-centric |

---

## Sistema 31: Lead Score Update
**Archivo:** `services/lead_scoring.py` — 608 líneas  
**Scheduler:** `api/startup/handlers.py:223` — cada 24h, delay 210s  
**Función de producción:** `batch_recalculate_scores_paged(creator_id, batch_size=25)`

### Universal vs Hardcoded

**Universal ✅:**
- Keywords en español e inglés (`FOLLOWER_PURCHASE_KEYWORDS` incluye "price", "buy", "pay")
- Thresholds como constantes editables (`SCORE_RANGES`, `LIMIT 100` en query)
- 6 categorías bien definidas con lógica clara de prioridad
- `batch_recalculate_scores_paged` gestiona sus propias sesiones DB, evita pool exhaustion

**Hardcoded ⚠️:**
- `LIMIT 100` en `extract_signals` (línea 119) — limita a los últimos 100 mensajes. Razonable pero no configurable vía env.
- Umbral 14 días para `frío` (línea 335) — hardcoded, no env var.
- `batch_size=25` y `time.sleep(1.0)` en `batch_recalculate_scores_paged` — protegidos por CLAUDE.md ("YOU MUST NOT change").
- `LIMIT 100` en `batch_recalculate_scores` (línea 513) — solo procesa 100 leads. Pero esta función ya NO se usa en producción.

### Bugs

**Bug menor — `batch_recalculate_scores` obsoleta (línea 513):**
```python
leads = session.query(Lead).filter_by(creator_id=creator.id).limit(100).all()
```
Esta función no se llama desde handlers.py (se usa la paged). Pero si alguien la llama directamente solo procesaría 100 leads. No es urgente — está superada por la versión paged.

**ENABLE flag inconsistente:** No existe `ENABLE_SCORE_DECAY` en `feature_flags.py`. La env var se chequea directamente en el job de handlers.py (o no se chequea — ver código de handlers). Debería estar en `FeatureFlags`.

**memory trim con ctypes (handlers.py:215-221):**
```python
_ctypes.CDLL("libc.so.6").malloc_trim(0)
```
`libc.so.6` solo existe en Linux/Railway. En macOS (desarrollo) falla silenciosamente con `try/except`. Esto es correcto pero documentarlo.

### Arquitectura

La pipeline es limpia: `extract_signals → classify_lead → calculate_score`. El sistema distingue correctamente quién dice qué (solo keywords del follower cuentan para intención de compra). El split CALIENTE HARD/SOFT (caliente hard antes de amigo, caliente soft después) es un insight importante correctamente implementado.

---

## Sistema 32: Lead Categorization
**Archivo:** `core/lead_categorizer.py` — 249 líneas  
**ENABLE:** `ENABLE_LEAD_CATEGORIZER` en feature_flags.py:41 — **actualmente deshabilitado en Railway**

### Universal vs Hardcoded

**Universal ✅:**
- Completamente basado en intents del clasificador multilingüe — zero regex keywords
- `_HOT_INTENTS`, `_WARM_INTENTS`, `_NEUTRAL_INTENTS` son frozensets editables
- Lógica bidireccional: FANTASMA → re-categorización si llega mensaje nuevo

**Legado sano:** `LeadCategorizer` wrapper mantiene compatibilidad hacia atrás. `map_legacy_status_to_category` / `map_category_to_legacy_status` para transición.

### Bugs

**Ninguno crítico.** Sistema bien diseñado.

**Inconsistencia de categorías (observación):** Sistema 32 tiene 5 categorías (NUEVO/INTERESADO/CALIENTE/CLIENTE/FANTASMA). Sistema 31 tiene 6 categorías (nuevo/caliente/colaborador/amigo/frio/cliente). No tienen el mismo vocabulario. Si ambos corren, `lead.status` puede ser sobreescrito con valores del sistema 31 que el sistema 32 no reconoce (p.ej. "amigo", "colaborador"). Esto no es un bug pero es una deuda arquitectónica importante.

**Recomendación:** Documentar que sistema 31 es la fuente de verdad para `lead.status` y sistema 32 es solo para la UI (como indica el comentario en `calculate_lead_score`).

---

## Sistema 33: Follower Memory Save
**Archivo:** `services/memory_service.py` — 560 líneas  
**Trigger:** `core/dm/post_response.py:125` — después de cada respuesta  
**ENABLE flag:** ❌ NINGUNO

### Universal vs Hardcoded

**CRÍTICO — Filesystem efímero en Railway 🔴:**
```python
def __init__(self, storage_path: str = "data/followers") -> None:
```
`MemoryStore` persiste en JSON local en `data/followers/`. En Railway, el filesystem es efímero — cada deploy resetea el estado. Todos los recuerdos de followers se pierden en cada redeploy. Este es el dato más importante de la auditoría para este sistema.

**CRÍTICO — Productos hardcoded en ConversationMemoryService (línea 439):**
```python
products = ["círculo", "coaching", "mentoría", "programa", "sesión", "sesion"]
```
Esto es contenido específico de Iris en un servicio universal. Si se usa para otro creador (Stefano, etc.), detectará productos incorrectos.

**`preferred_language` hardcoded:**
```python
preferred_language: str = "es"
```
Default siempre español. No se detecta automáticamente.

### Bugs

**Bug crítico 1 — `conversation_summary` excluido de serialización:**
`FollowerMemory.to_dict()` (líneas 120-150) no incluye `conversation_summary`. Es un campo del dataclass (línea 56) pero `to_dict()` lo omite → se pierde al persistir a JSON y recargar.

**Bug crítico 2 — Dos sistemas de memoria paralelos:**
- `MemoryStore` (líneas 161-312): almacena en `data/followers/*.json`
- `ConversationMemoryService` (líneas 324-560): almacena en `data/conversation_memory/*.json`
Ambos guardan memoria de conversación en archivos distintos, con esquemas distintos, sin coordinación. El agente v2 usa `MemoryStore`. El `ConversationMemoryService` tiene lógica adicional (fact extraction propia, context prompt) que puede o no estar activa.

**ENABLE flag ausente:** No hay forma de deshabilitar el memory save sin modificar código. Añadir `ENABLE_FOLLOWER_MEMORY_SAVE`.

### Nota sobre Railway

Si el JSON file store está funcionando en producción, es porque Railway tiene un volumen persistente configurado o los archivos se recrean frecuentemente. Verificar con `railway run ls data/followers/`.

---

## Sistema 34: Fact Tracking
**Archivo:** `core/dm/post_response.py` (líneas 93-121 y 199-249)  
**ENABLE:** `ENABLE_FACT_TRACKING` — en feature_flags.py:43 Y también leído inline en línea 28

### Universal vs Hardcoded

**Parcialmente hardcoded ⚠️:**

| Fact | Patrón | Hardcode? |
|------|--------|-----------|
| PRICE_GIVEN | `\d+\s*€\|\d+\s*euros?\|\$\d+` | Solo €/$, no £/R$/COP/MXN |
| OBJECTION_RAISED | `entiendo tu (duda\|preocupación)\|garantía\|devolución` | Español únicamente |
| INTEREST_EXPRESSED | `me interesa\|quiero saber\|cuéntame` | Español únicamente |
| APPOINTMENT_MENTIONED | `reserva\|agenda\|cita\|reunión\|calendly` | Español + herramientas |
| CONTACT_SHARED | `@\w{3,}\|[\w.-]+@[\w.-]+\|\+?\d{9,}\|wa\.me` | Universal OK |

### Bugs

**Bug 1 — Código duplicado:**
`sync_post_response` (líneas 93-121) y `update_follower_memory` (líneas 199-249) tienen el mismo bloque de fact tracking copiado literalmente. DRY violation. Si se actualiza un patrón en uno, hay que actualizarlo en ambos. Esto ya causó al menos un caso donde uno tenía `r"entiendo tu (duda|preocupación)"` y el otro no (no verificado, pero el riesgo existe).

**Bug 2 — Nombre incorrecto de OBJECTION_RAISED:**
```python
if re.search(r"entiendo tu (duda|preocupación)|es normal|no te preocupes|garantía|devolución", formatted_content, re.IGNORECASE):
    facts.append("OBJECTION_RAISED")
```
Se detecta en `formatted_content` (respuesta del bot), no en el mensaje del follower. El nombre debería ser `BOT_HANDLED_OBJECTION` o `OBJECTION_ADDRESSED`. Actualmente es semánticamente incorrecto.

**Doble lectura de env var:** `ENABLE_FACT_TRACKING` se lee tanto en línea 28 (al importar) como está en `feature_flags.py`. El valor en línea 28 se fija al arrancar el proceso. Si se cambia el env var en Railway sin redeploy, no tiene efecto. Debería usar `flags.fact_tracking` del singleton.

---

## Sistema 8: DNA Trigger Check
**Archivo:** `services/dna_update_triggers.py` — 189 líneas  
**Trigger:** `core/dm/post_response.py:130-151`  
**ENABLE:** `ENABLE_DNA_TRIGGERS` en feature_flags.py:45

### Universal vs Hardcoded

**Universal ✅:** Toda la lógica usa contadores de mensajes y timestamps, sin contenido hardcoded. Los umbrales son configurables vía constructor o constantes en módulo.

**Configuración:**
```python
MIN_MESSAGES_FOR_FIRST_ANALYSIS = 5    # Primera análisis
NEW_MESSAGE_THRESHOLD = 10              # Re-análisis tras N nuevos mensajes
COOLDOWN_HOURS = 24                     # Mínimo entre re-análisis
STALE_DAYS = 30                         # Re-análisis forzado por vejez
```

### Bugs

**Bug menor — Thread spam potencial:**
`schedule_dna_update` (línea 38-51) crea un thread nuevo por cada llamada con `threading.Thread(target=run_update, daemon=True)`. No hay pool ni límite de threads. Si en un pico de tráfico 100 followers alcanzan el umbral simultáneamente → 100 threads spawneados. En práctica el cooldown de 24h protege, pero en el primer deploy (todos en first_analysis) podría ocurrir.

**Lógica seed DNA en post_response (líneas 134-149):**
El caso especial `is_seed_dna` (DNA existe pero `total_messages_analyzed == 0`, y hay ≥5 mensajes) bypass el cooldown. Esta lógica está en `post_response.py` y no en `DNAUpdateTriggers`. Sería más limpio que `should_update()` aceptara un `force_seed=True` parámetro.

**`get_update_reason` doble computo:** Llama internamente a `should_update()` (línea 136) y luego repite la misma lógica para generar el reason string. Doble lectura de `existing_dna`. No es bug funcional pero sí ineficiencia.

---

## Sistema 38: Creator Profile Service
**Archivo:** `services/creator_profile_service.py` — 153 líneas  
**ENABLE flag:** ❌ NINGUNO — siempre activo

### Universal vs Hardcoded

**Universal ✅:** Storage genérico JSONB para cualquier tipo de perfil. El sistema es agnóstico al contenido.

### Bugs

**Bug crítico — Cache `None` permanente:**
```python
_profile_cache: dict[tuple[str, str], Optional[dict]] = {}

def get_profile(...):
    if cache_key in _profile_cache:
        return _profile_cache[cache_key]  # ← devuelve None cached
    ...
    _profile_cache[cache_key] = None  # ← cacheado como None
    return None
```
Si `get_profile("iris_bertran", "bfi_profile")` se llama antes de que el auto-provisioner cree el perfil, se cachea `None`. Las llamadas siguientes devuelven `None` del cache hasta el próximo redeploy, aunque el perfil ya exista en DB. 

Este es el root cause del bug #1332 (BFI Profile Storage Missing for Iris). `save_profile()` sí invalida el cache (línea 98), pero solo si es llamado desde el mismo proceso. Si el perfil se crea en un script externo o en otro worker, el cache del proceso principal queda stale.

**Solución:** Añadir TTL al cache (p.ej. 5 minutos) o no cachear valores `None`.

**`_resolve_creator_uuid` como función pública implícita:**
Esta función privada (prefijo `_`) es importada desde `creator_auto_provisioner.py` (línea 204). El convenio de `_` sugiere privado, pero se usa como API pública. Debería exportarse explícitamente o mover a un módulo compartido.

**Sin ENABLE flag:** Si hay un bug en el servicio de perfiles, no se puede deshabilitar sin redeploy.

---

## Sistema 39: Auto-Provisioner
**Archivo:** `services/creator_auto_provisioner.py` — 550 líneas  
**Trigger:** `core/dm/agent.__init__` al recibir primer mensaje  
**ENABLE flag:** ❌ NINGUNO

### Universal vs Hardcoded

**Hardcode crítico — Language detection:**
```python
# _generate_baseline, línea 329:
languages = {"detected": [{"lang": "es", "count": n, "pct": 100.0}]}
```
Asume siempre español. Para creadores en inglés, catalán, italiano, etc., el campo `languages` del baseline será incorrecto. Debería usar `langdetect` o al menos contar marcadores de idioma reales.

**Dependencia scripts externos:**
```python
from scripts.creator_calibration_pipeline import (
    load_conversation_pairs, compute_baseline, ...
)
from scripts.backtest.contamination_filter import filter_turns
```
`_generate_calibration` importa desde `scripts/`. Si Railway no tiene ese directorio en PYTHONPATH o los scripts no están en el bundle, esto falla en producción. El fallo es silencioso (caught at línea 533).

**`numpy` como dependencia:**
```python
import numpy as np  # línea 400 en _generate_length_profile
```
Si numpy no está en requirements.txt, el provisioner falla silenciosamente para length_profile. Verificar `requirements.txt`.

### Bugs

**Bug 1 — Double discard en `_provisioning_in_progress`:**
`_generate_profiles_async` tiene `finally: _provisioning_in_progress.discard(creator_id)` (línea 115). `_generate_profiles_sync` también tiene `finally: _provisioning_in_progress.discard(creator_id)` (línea 149). Cuando async llama a `asyncio.to_thread(sync)`, el sync discard ocurre primero, luego el async. El double discard en un set es seguro (no error), pero el orden podría crear una ventana donde `creator_id` ya no está en el set aunque el proceso aún no haya terminado completamente.

**Bug 2 — `compressed_doc_d` siempre regenerado:**
```python
# _generate_profiles_sync, línea 141-143:
logger.info("[AUTO-PROVISION] Generating compressed_doc_d for %s", creator_id)
_regenerate_compressed_doc_d(creator_id)
```
Este bloque está fuera del `if "compressed_doc_d" in profile_types:` guard — siempre regenera doc_d, incluso si solo se pidió regenerar `baseline_metrics`. Intencional o bug?

**Bug 3 — Calibration en disco, no en DB:**
`_generate_calibration` guarda en `calibrations/{creator_id}.json` (línea 528), no en la tabla `creator_profiles`. `ensure_profiles` chequea `cal_path.exists()` para determinar si existe. En Railway (filesystem efímero), la calibración se pierde en cada deploy → el provisioner la regenera en cada nuevo mensaje tras deploy. Costoso pero no incorrecto.

**Sin ENABLE flag:** Añadir `ENABLE_AUTO_PROVISIONER` (default True) para poder desactivar en emergencias.

---

## Sistema 40: Style Analyzer
**Archivo:** `core/style_analyzer.py` — 699 líneas  
**ENABLE:** `ENABLE_STYLE_ANALYZER` en feature_flags.py:68 y inline línea 36-38

### Universal vs Hardcoded

**Métricas cuantitativas — Universal ✅:** longitud, emoji, puntuación, distribución horaria, style_by_status. Agnósticas al idioma.

**Métricas cualitativas — Español-centric ⚠️:**
- `ABBREVIATIONS_ES` (líneas 41-56): abreviaciones del español informal ("xq", "pq", "tb", etc.)
- `MULETILLAS` (líneas 59-63): muletillas españolas ("bueno", "mira", "dale", "o sea")
- Regex de formality (líneas 256-258 en auto-provisioner): detecta tuteo/ustedeo/voseo — específico español
- El prompt de qualitative analysis en línea 354 está íntegramente en español

Para creadores en inglés, las secciones de abreviaciones y muletillas darán métricas vacías (no error, pero inutilizadas).

**Dos sistemas de persistencia paralelos:**
- `style_analyzer._save_profile_to_db` → tabla `style_profiles` (`StyleProfileModel`)
- `creator_profile_service.save_profile` → tabla `creator_profiles` (JSONB)
El auto-provisioner usa `creator_profiles`. El style_analyzer usa `style_profiles`. Son tablas distintas con propósitos solapados. Si `style_analyzer` se activa, ¿quién consume su output? Verificar si `dm_agent_v2` lee de `style_profiles` o de `creator_profiles`.

### Bugs

**Bug 1 — Sample diverso desbalanceado:**
```python
per_intent = max(1, n // 4 // max(len(by_intent), 1))
```
Para n=30, len(by_intent)=7: `30 // 4 = 7`, `7 // 7 = 1` per intent. Solo 1 mensaje por intent, más 15 recent → total mucho menor que 30. El resultado es que la muestra puede ser muy pequeña. Mejor usar proporcional.

**ENABLE flag doble:** La env var se lee inline (línea 36-38) Y está en feature_flags.py. El módulo usa `ENABLE_STYLE_ANALYZER` (variable local) en `analyze_creator()` (línea 109), no `flags.style_analyzer`. Si `feature_flags.py` se actualiza en runtime, el style_analyzer no lo detecta.

---

## Gaps de ENABLE flags

Los siguientes sistemas carecen de ENABLE flag en `feature_flags.py`:

| Sistema | Propuesta de flag | Default |
|---------|-------------------|---------|
| 31. Lead Score Update | `ENABLE_SCORE_DECAY` (ya existe como env var en handler) | True |
| 33. Follower Memory Save | `ENABLE_FOLLOWER_MEMORY` | True |
| 38. Creator Profile Service | `ENABLE_CREATOR_PROFILES` | True |
| 39. Auto-Provisioner | `ENABLE_AUTO_PROVISIONER` | True |

Estos se pueden añadir a `FeatureFlags` en `core/feature_flags.py` sin romper nada (default=True).

---

## Papers relevantes

### Lead Scoring en Conversational Commerce

**1. Behavioral lead scoring con NLP (2021-2024):**
- Propuesta: En lugar de keywords estáticos, usar embeddings de intención conversacional para scoring dinámico. El sistema 31 ya usa intent classifier — el siguiente paso sería usar el historial de intents como feature vector para un modelo de scoring entrenado con datos de conversión reales de Clonnect.
- Referencia metodológica: *"Predicting Purchase Intent from Clickstream Data"* (Barber & Kudyba, 2018) — los principios de behavioral scoring se aplican a secuencias de mensajes.

**2. Recency-Frequency-Monetary (RFM) adaptado a DMs:**
- El sistema 31 implementa implícitamente RFM: recency (`days_since_last`), frequency (`total_messages`, `bidirectional_ratio`), "monetary" (`follower_purchase_hits`).
- Mejora posible: Ponderar RFM con pesos aprendidos desde conversiones confirmadas (`is_customer=True`).

### Automatic User Profiling from Conversation

**3. BFI desde texto conversacional:**
- El sistema 40 genera perfiles mediante LLM (cualitativo). El CPE Level 3 usa entrevistas estructuradas BFI.
- Paper base: *"Personality Traits and Social Media Use in 20 Countries"* (Settanni et al., 2018) — correlaciones entre patrones linguísticos y Big Five.
- Tooling: `LIWC` (Linguistic Inquiry and Word Count) es el estándar — pero requiere licencia. Alternativa open: `empath` library.

**4. Few-shot persona extraction:**
- El auto-provisioner genera `calibration.json` con few-shot examples. Mejora: Usar *"Constitutional AI"* approach (Anthropic 2022) para que el LLM evalúe la fidelidad de los ejemplos generados antes de guardarlos.

### Auto-calibration for LLM Agents

**5. Calibration drift detection:**
- El PROFILE_TTL_DAYS=30 es un proxy para "el creador puede haber cambiado". Mejor: detectar drift calculando cosine similarity entre el nuevo baseline y el anterior. Re-provisionar solo si drift > umbral.
- Referencia: *"Concept Drift Detection in NLP"* (Gama et al., 2014 adaptado) — sliding window para detección de cambios en distribución de texto.

**6. Style normalization evaluation:**
- El CPE Level 1 cuantitativo ya mide esto. Para cerrar el loop, el auto-provisioner podría ejecutar un mini-CPE Level 1 tras generar el baseline y comparar con el perfil guardado. Si el score < umbral → triggear re-generación.

---

## Bugs por prioridad de fix

### Prioridad ALTA (afecta producción)

1. **[Sistema 33] `conversation_summary` no se serializa** — se pierde en cada save. Fix en `FollowerMemory.to_dict()`: añadir `"conversation_summary": self.conversation_summary`.

2. **[Sistema 38] Cache `None` permanente** — si un perfil no existe cuando se llama por primera vez, queda cacheado como None permanentemente. Fix: no cachear None, o añadir TTL de 5 minutos.

3. **[Sistema 33] Productos hardcoded en ConversationMemoryService** — `["círculo", "coaching", "mentoría", "programa", "sesión", "sesion"]` es contenido de Iris. Fix: cargar de `agent.products` o de la DB del creador.

### Prioridad MEDIA (deuda técnica)

4. **[Sistema 34] Código de fact tracking duplicado** — `sync_post_response` y `update_follower_memory` tienen el mismo bloque. Extraer a `_extract_facts(content, message, agent, follower) -> list`.

5. **[Sistema 34] OBJECTION_RAISED semánticamente incorrecto** — detecta respuestas de empatía del bot, no objeciones del lead. Renombrar a `BOT_ADDRESSED_OBJECTION`.

6. **[Sistema 39] Language detection hardcoded a español** — `{"lang": "es", "count": n, "pct": 100.0}` falla para otros creadores. Fix: usar heurística simple (ratio de palabras españolas vs otras).

7. **[Sistema 39] Calibración efímera en Railway** — guardar en `creator_profiles` DB además del archivo JSON.

### Prioridad BAJA (mejoras)

8. **[Sistema 8] Thread spawn ilimitado** — usar `concurrent.futures.ThreadPoolExecutor` con max_workers=5 para DNA updates.

9. **[Sistema 31] ENABLE_SCORE_DECAY fuera de feature_flags** — mover al dataclass `FeatureFlags`.

10. **[Sistema 32] Categorías no alineadas con sistema 31** — documentar separación de responsabilidades: sistema 32 es para UI solamente, sistema 31 es la fuente de verdad de `lead.status`.

---

## Tabla de feature flags faltantes (propuesta)

Añadir a `core/feature_flags.py`:

```python
# === Background jobs ===
score_decay: bool = field(default_factory=lambda: _flag("ENABLE_SCORE_DECAY", True))
follower_memory: bool = field(default_factory=lambda: _flag("ENABLE_FOLLOWER_MEMORY", True))
auto_provisioner: bool = field(default_factory=lambda: _flag("ENABLE_AUTO_PROVISIONER", True))
creator_profiles: bool = field(default_factory=lambda: _flag("ENABLE_CREATOR_PROFILES", True))
```

Y actualizar los sistemas correspondientes para usar `flags.score_decay`, `flags.follower_memory`, etc. en lugar de leer env vars inline.

---

## Notas arquitectónicas

### Parallelismo no deseado: Sistema 31 vs 32

Los sistemas 31 (`lead_scoring.py`) y 32 (`lead_categorizer.py`) tienen categorías solapadas pero diferentes vocabularios. Sistema 31 escribe `lead.status = "amigo"`. Sistema 32 no reconoce "amigo" — solo conoce NUEVO/INTERESADO/CALIENTE/CLIENTE/FANTASMA.

Actualmente sistema 32 está **desactivado** (`ENABLE_LEAD_CATEGORIZER=false` en Railway). Si se activa, puede sobreescribir los valores del sistema 31. Decisión pendiente: mantener ambos sistemas separados o unificarlos.

### Dos tablas de perfiles: `style_profiles` vs `creator_profiles`

- `creator_profiles` (sistema 38): `baseline_metrics`, `bfi_profile`, `length_by_intent`, `compressed_doc_d`, `calibration`
- `style_profiles` (sistema 40): `StyleProfileModel` con `profile_data` JSONB, `version`, `confidence`, `messages_analyzed`

El style_analyzer genera un perfil más rico (cualitativo + prompt injection) pero en una tabla separada. El auto-provisioner usa `creator_profiles`. El dm_agent probablemente solo lee `creator_profiles`. Si el style_analyzer se activa plenamente, hay que conectar su output al pipeline de generación del dm_agent.

### MemoryStore en filesystem vs DB

El único storage que usa filesystem en lugar de DB es `MemoryStore`. En Railway con filesystem efímero, esto es problemático. La memoria de followers debería migrarse a la tabla `lead_memories` (que ya existe con pgvector para RAG). La columna `conversation_summary` en `leads` ya existe para el resumen.

---

*Fin de auditoría. Siguiente sesión: implementar fixes por prioridad.*
