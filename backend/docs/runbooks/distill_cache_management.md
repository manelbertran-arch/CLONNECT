# Runbook: StyleDistillCache Management

**ARC3 Phase 1 — Operational Runbook**
**Última actualización:** 2026-04-19
**Feature flag:** `USE_DISTILLED_DOC_D` (default: **OFF**)
**Código:** `services/style_distill_service.py`
**Script batch:** `scripts/distill_style_prompts.py`
**Tabla DB:** `creator_style_distill`
**Modelo LLM:** OpenRouter (env `OPENROUTER_MODEL`, default: `google/gemma-4-31b-it`)

---

## Qué hace StyleDistillCache

Genera y almacena una versión comprimida del Doc D (style_prompt) de cada creador.

- Doc D original Iris: ~5535 chars → distilled_short: ~1500 chars (ratio ~27%)
- Compresión: elimina redundancias y meta-comentarios, preserva voz, ejemplos concretos y reglas de tono
- Storage: tabla `creator_style_distill` con clave `(creator_id, doc_d_hash, distill_prompt_version)`
- Lookup: O(1) por hash SHA-256 de los primeros 16 chars

**La distillation se genera OFFLINE (batch) y se sirve en runtime. El hot path nunca espera una llamada LLM.**

---

## 1. Cuándo re-distillar

### Señales que requieren re-distillar

| Señal | Descripción | Urgencia |
|-------|-------------|----------|
| Doc D del creador fue modificado | El hash cambia → miss automático en cache | Alta — distillar antes de activar |
| Distill cache miss rate > 5% sostenido | Hay turnos usando Doc D full en vez de distilled | Media |
| CCEE drop sostenido (> -5 puntos) sin otra causa | La distilled version puede haber capturado mal el Doc D | Alta |
| `DISTILL_PROMPT_VERSION` bumped | Se mejoró el prompt de distillation → regenerar todo | Alta |
| Creator nuevo o Doc D nuevo desde cero | No hay row en `creator_style_distill` | Alta |

### Gate para re-distillar (no hacerlo si...)

- El Doc D cambió < 10% en chars → evaluar si el cambio es de contenido o de formato
- La distillation actual tiene `quality_score >= 70` y `human_validated = true`
- Se está en mitad de un CCEE run activo — esperar a que termine

### Verificar estado actual de la cache

```sql
-- Ver todas las distillations actuales
SELECT
    c.name AS creator,
    d.doc_d_chars,
    d.distilled_chars,
    ROUND(100.0 * d.distilled_chars / d.doc_d_chars, 1) AS ratio_pct,
    d.distill_model,
    d.distill_prompt_version,
    d.quality_score,
    d.human_validated,
    d.created_at
FROM creator_style_distill d
JOIN creators c ON c.id = d.creator_id
ORDER BY d.created_at DESC;

-- Verificar si el hash del Doc D actual coincide con el cacheado
-- (requiere calcular SHA-256 del style_prompt actual y comparar con doc_d_hash)
SELECT creator_id, doc_d_hash, doc_d_chars, created_at
FROM creator_style_distill
ORDER BY created_at DESC;
```

---

## 2. Generar nueva distillation

### Comando estándar (un creator)

```bash
# Activar entorno virtual
source .venv/bin/activate

# Distillar un creator por UUID
python3.11 scripts/distill_style_prompts.py --creator-id <uuid>

# Con --force si ya existe y quieres regenerar
python3.11 scripts/distill_style_prompts.py --creator-id <uuid> --force

# Dry-run para verificar qué haría sin ejecutar
python3.11 scripts/distill_style_prompts.py --creator-id <uuid> --dry-run
```

Variables de entorno requeridas:
```bash
DATABASE_URL=<postgres_conn_string>
OPENROUTER_API_KEY=<key>
OPENROUTER_MODEL=google/gemma-4-31b-it  # opcional, es el default
```

### Distillar todos los creators activos

```bash
python3.11 scripts/distill_style_prompts.py
# Procesa todos los creators con is_active=true y Doc D > 1500 chars
# Los que ya tienen cache son skipped automáticamente
```

### Interpretar el output del script

```
============================================================
DISTILLATION SUMMARY
============================================================
  Processed : 2
  Skipped   : 1
  Errors    : 0

PROCESSED:
  iris_bertran: 5535 → 1482 chars (27%)
  stefano: 2100 → 1354 chars (64%)
SKIPPED:
  test_creator: Doc D too short (800 < 1500 chars)
============================================================
```

Un ratio > 75% indica que el Doc D era corto y no hay mucho que comprimir. Aceptable.
Un ratio < 15% podría indicar que el distilled perdió contenido — verificar manualmente.

### Validación CCEE antes de activar

**Antes de activar `USE_DISTILLED_DOC_D=true` para cualquier creator:**

1. Correr CCEE v5.3 en 20 scenarios con `doc_d_full` (baseline)
2. Correr CCEE v5.3 en los mismos 20 scenarios con `doc_d_distilled`
3. **Gate de activación: ΔCCEE_composite ≥ -3 puntos**

Si el delta es peor que -3:
- Ajustar `DISTILL_PROMPT_V1` en `services/style_distill_service.py` (o `target_chars`)
- Re-distillar con `--force`
- Re-validar

Documentar resultados en `docs/sprint5_planning/ARC3_phase1_distill_validation.md`.

---

## 3. Prompt versioning

### Versión actual

`DISTILL_PROMPT_VERSION = 1` (definido en `services/style_distill_service.py:35`)

El prompt v1 está en la constante `DISTILL_PROMPT_V1` en el mismo fichero (línea 47).

### Cómo cambiar a v2 sin borrar v1

1. Añadir nueva constante en `services/style_distill_service.py`:
```python
DISTILL_PROMPT_V2 = """
... nuevo prompt ...
"""
DISTILL_PROMPT_VERSION: int = 2  # bump aquí
```

2. El cambio de version number causa que todas las lookups fallen (nuevo hash no existe → miss) y el script batch regenere todo.

3. Los rows v1 **no se borran automáticamente** — quedan en la tabla como historial. Se pueden usar para comparación.

4. Para borrar v1 manualmente después de validar v2:
```sql
DELETE FROM creator_style_distill WHERE distill_prompt_version = 1;
```

### A/B entre versiones (experimental)

Para comparar v1 vs v2 en producción:
- Activar `USE_DISTILLED_DOC_D=true` con v1 para 50% de turns (cuando sticky hash esté implementado)
- Generar v2 con `--prompt-version 2 --force`
- Correr CCEE comparativo
- Si v2 gana → bumpar `DISTILL_PROMPT_VERSION = 2` y hacer default

---

## 4. Invalidar cache

### Cuándo invalidar

- Doc D del creador cambió (el hash cambia automáticamente → miss natural → regeneración bajo demanda)
- Bug en una versión de distillation almacenada
- Quieres forzar regeneración sin esperar a que el Doc D cambie

### Borrar entries obsoletos para un creator

```sql
-- Borrar distillations antiguas (mantener solo la más reciente por creator)
DELETE FROM creator_style_distill
WHERE creator_id = '<uuid>'
  AND id NOT IN (
    SELECT id FROM creator_style_distill
    WHERE creator_id = '<uuid>'
    ORDER BY created_at DESC
    LIMIT 1
  );
```

### Borrar todas las distillations de un creator y regenerar

```sql
-- Paso 1: borrar
DELETE FROM creator_style_distill WHERE creator_id = '<uuid>';
```

```bash
# Paso 2: regenerar
python3.11 scripts/distill_style_prompts.py --creator-id <uuid>
```

### Limpiar distillations de versión antigua (cron recomendado)

```sql
-- Borrar distillations con versión < (versión actual - 3)
-- Ajustar :current_version según DISTILL_PROMPT_VERSION actual
DELETE FROM creator_style_distill
WHERE distill_prompt_version < :current_version - 3;
```

### Forzar regeneración de todas las distillations

```bash
# Regenera todos los creators, sobrescribiendo cache existente
python3.11 scripts/distill_style_prompts.py --force
# Tiempo estimado: 3-5s por creator (LLM call ~90s timeout, suele responder en 3-8s)
# Con 3 creators: ~15-30s total
```

---

## 5. Monitoreo diario

### Métricas objetivo

| Métrica | Target | Alerta si |
|---------|--------|-----------|
| Cache hit rate | > 95% | < 95% sostenido 30 min |
| Distill latency lookup (DB) | < 20ms p95 | > 50ms |
| LLM distill call latency (offline) | < 30s | > 90s (timeout) |
| Ratio distilled/original | 25-65% | > 80% (poco comprimido) o < 15% (sospechoso) |
| CCEE delta post-distill | ≥ -3 puntos | < -3 puntos |

### Queries de monitoreo diario

```sql
-- ¿Se están usando las distillations? (shadow log)
SELECT
    DATE_TRUNC('hour', timestamp) AS hora,
    SUM(CASE WHEN distill_applied THEN 1 ELSE 0 END) AS distill_used,
    COUNT(*) AS total_turns,
    ROUND(100.0 * SUM(CASE WHEN distill_applied THEN 1 ELSE 0 END) / COUNT(*), 1) AS hit_pct
FROM context_compactor_shadow_log
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY hora
ORDER BY hora DESC;

-- Estado de distillations por creator
SELECT
    c.name AS creator,
    d.doc_d_chars,
    d.distilled_chars,
    ROUND(100.0 * d.distilled_chars / d.doc_d_chars, 1) AS ratio_pct,
    d.quality_score,
    d.created_at,
    NOW() - d.created_at AS age
FROM creator_style_distill d
JOIN creators c ON c.id = d.creator_id
ORDER BY d.created_at DESC;
```

### Logs a monitorear

```bash
# Ver distill cache hits/misses en tiempo real
railway logs -n 200 | grep "StyleDistillCache"

# Hit normal:
# [INFO] StyleDistillCache HIT: creator=xxx hash=abc123 version=1 → 1482 chars

# Miss (normal si Doc D cambió):
# [INFO] StyleDistillCache MISS: creator=xxx hash=def456 version=1 force=False — calling LLM

# Error en LLM call:
# [ERROR] StyleDistillService: LLM error on attempt 1/2: ...
```

### Dashboard Grafana (cuando esté configurado)

Paneles relevantes en `ops/grafana/dashboards/`:
- `distill_cache_hit_rate` — gauge, target > 95%
- Logs panel filtrando `StyleDistillCache`

---

## Límites y consideraciones de escala

- **3 creators actuales:** batch completo < 30s
- **100+ creators (futuro):** considerar Gemini Flash en lugar de Gemma-4-31B para abaratar el batch (~10x más barato, suficiente calidad para distillation)
- **Cron nocturno recomendado:** ejecutar `distill_style_prompts.py` cada noche a las 3am UTC para capturar cambios en Doc D del día anterior
- **Doc D actualizado hoy:** el batch del día siguiente lo recoge. Si necesitas inmediato, ejecutar manualmente con `--creator-id`

---

## Referencias

- Diseño ARC3: `docs/sprint5_planning/ARC3_compaction.md` §2.2
- Validación Phase 1: `docs/sprint5_planning/ARC3_phase1_distill_validation.md`
- Código servicio: `services/style_distill_service.py`
- Script batch: `scripts/distill_style_prompts.py`
- Feature flag: `core/feature_flags.py:108-114` (`USE_DISTILLED_DOC_D`)
- Schema DB: `docs/sprint5_planning/ARC3_compaction.md` §2.2.2
