# Runbook: Compaction Tuning (PromptSliceCompactor + StyleDistillCache)

**ARC3 Phase 5 — Operational Runbook**
**Última actualización:** 2026-04-19
**Feature flags:** `ENABLE_COMPACTOR_SHADOW`, `USE_COMPACTION`, `USE_DISTILLED_DOC_D`
**Código:** `core/generation/compactor.py`, `services/style_distill_service.py`
**Shadow log:** tabla `context_compactor_shadow_log`

---

## 1. Cuándo intervenir

### Señales de que hay problema

| Señal | Tabla / Métrica | Acción |
|-------|-----------------|--------|
| Compaction aplicada > 30% sostenido 1h | `context_compactor_shadow_log` / Grafana alerta | Revisar ratios per-creator (§2) |
| `distill_applied = true` pero no hay mejora | Shadow log + CCEE | Re-validar distillation (§ distill runbook) |
| `divergence_chars` P95 > 2000 sostenido | `context_compactor_shadow_log` | Analizar secciones más truncadas (§3) |
| `reason = AGGRESSIVE_TRUNC` frecuente | Shadow log | Budget insuficiente — revisar `MAX_CONTEXT_CHARS` |
| `reason = CIRCUIT_BREAK` (whitelist_overflow) | Shadow log | CRÍTICO — whitelist sola excede budget (§5) |

### Qué revisar primero

```bash
# Tasa de compaction últimas 24h
python3.11 scripts/analyze_compactor_shadow.py --hours 24 --output md

# Por creator específico
python3.11 scripts/analyze_compactor_shadow.py --hours 24 --creator-id <UUID> --output md

# JSON para automatización
python3.11 scripts/analyze_compactor_shadow.py --hours 24 --output json | jq '.compaction_pct, .gate_pass'
```

**Gate Phase 3:** compaction_pct < 15% antes de activar `USE_COMPACTION=true`.

---

## 2. Ajustar ratios per-creator

### Ratios por defecto (ARC3 §2.3.2)

```python
DEFAULT_RATIOS = {
    "style_prompt":    0.35,   # Doc D — 35% del budget no-whitelist
    "lead_facts":      0.15,   # Nombre, intereses conocidos
    "lead_memories":   0.20,   # Memory recall (ARC2)
    "rag_hits":        0.15,   # Retrieval semántico
    "message_history": 0.10,   # Últimos N turnos
    "few_shots":       0.05,   # Ejemplos canónicos
}
# Budget total: MAX_CONTEXT_CHARS = 8000 chars
```

Ejemplo Iris con budget 8000 (asumiendo whitelist = 530 chars):
- non-whitelist budget = 7470 chars
- style_prompt cap = 2615 chars → si Doc D full = 5535 → StyleDistillCache triggered
- lead_memories cap = 1494 chars
- rag_hits cap = 1121 chars

### Override per-creator vía `creator_runtime_config`

**PENDING Phase 3 live rollout.** La columna `compaction_ratios` en `creator_runtime_config` no está activa aún. Por ahora, los ratios son globales (DEFAULT_RATIOS en `core/generation/compactor.py`).

Para cambiar ratios globales temporalmente (hotfix):

```bash
# 1. Editar el fichero
vi core/generation/compactor.py  # modificar DEFAULT_RATIOS dict

# 2. Syntax check
python3.11 -c "import ast; ast.parse(open('core/generation/compactor.py').read())"

# 3. Deploy vía git push (Railway auto-deploys main)
git add core/generation/compactor.py
git commit -m "fix(arc3): adjust DEFAULT_RATIOS — <motivo>"
git push origin main
```

**Una vez Phase 3 esté live**, usar SQL para override per-creator:

```sql
-- Ver config actual de un creator
SELECT id, name, compaction_ratios
FROM creator_runtime_config
WHERE creator_id = '<creator_uuid>';

-- Insertar o actualizar ratios para Iris (ejemplo: más style_prompt, menos rag)
INSERT INTO creator_runtime_config (creator_id, compaction_ratios)
VALUES (
    '<iris_uuid>',
    '{"style_prompt": 0.40, "lead_facts": 0.15, "lead_memories": 0.20,
      "rag_hits": 0.10, "message_history": 0.10, "few_shots": 0.05}'::jsonb
)
ON CONFLICT (creator_id) DO UPDATE
  SET compaction_ratios = EXCLUDED.compaction_ratios,
      updated_at = NOW();
```

### Cuándo ajustar ratios

**Creator con Doc D largo (ej. Iris, >4000 chars):**
- Subir `style_prompt` a 0.40-0.45
- Bajar `rag_hits` a 0.10 o `few_shots` a 0.03

**Creator con Doc D corto (ej. Stefano, <2000 chars):**
- Bajar `style_prompt` a 0.25
- Subir `lead_memories` a 0.25 o `rag_hits` a 0.20

**Regla:** la suma de todos los ratios debe ser exactamente 1.00.

---

## 3. Interpretación de `context_compactor_shadow_log`

### Queries de diagnóstico

```sql
-- Resumen últimas 24h
SELECT
    creator_id,
    COUNT(*) AS total_turns,
    SUM(CASE WHEN compaction_applied THEN 1 ELSE 0 END) AS compacted,
    ROUND(100.0 * SUM(CASE WHEN compaction_applied THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct,
    AVG(divergence_chars) AS avg_divergence
FROM context_compactor_shadow_log
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY creator_id
ORDER BY pct DESC;

-- Secciones más truncadas
SELECT
    section_name,
    COUNT(*) AS truncation_count
FROM context_compactor_shadow_log,
     jsonb_array_elements_text(sections_truncated) AS section_name
WHERE timestamp > NOW() - INTERVAL '24 hours'
GROUP BY section_name
ORDER BY truncation_count DESC;

-- Casos extremos (divergencia > 2000 chars)
SELECT timestamp, creator_id, actual_chars_before, shadow_chars_after,
       divergence_chars, reason
FROM context_compactor_shadow_log
WHERE divergence_chars > 2000
  AND timestamp > NOW() - INTERVAL '24 hours'
ORDER BY divergence_chars DESC
LIMIT 20;

-- Tasa de uso de distillation
SELECT
    COUNT(*) AS total,
    SUM(CASE WHEN distill_applied THEN 1 ELSE 0 END) AS distill_used,
    ROUND(100.0 * SUM(CASE WHEN distill_applied THEN 1 ELSE 0 END) / COUNT(*), 1) AS distill_pct
FROM context_compactor_shadow_log
WHERE timestamp > NOW() - INTERVAL '24 hours';
```

### Interpretación de `reason`

| Valor | Significa | Acción |
|-------|-----------|--------|
| `OK` | Sin compactación — todo cabe | Normal |
| `DISTILL_APPLIED` | StyleDistillCache usada, compactación exitosa | Verificar hit rate |
| `RATIO_CAPS` | Truncación por ratio caps — todas las secciones tienen ratio definido | Normal si < 15% |
| `AGGRESSIVE_TRUNC` | Truncación agresiva — alguna sección sin ratio o la suma excede aún | Revisar ratios |
| `CIRCUIT_BREAK` | Whitelist overflow — CRÍTICO (ver §5) | Investigar inmediatamente |

### Gate < 15% compaction rate

Si `compaction_pct > 15%`:
1. Ejecutar análisis con `scripts/analyze_compactor_shadow.py`
2. Identificar qué creator y qué sección está causando más truncación
3. Ajustar ratio para esa sección (§2)
4. Esperar 24h y re-medir antes de activar `USE_COMPACTION=true`

---

## 4. Deploy ratios / activar compaction en vivo

### Checklist pre-rollout

- [ ] Shadow mode activo (`ENABLE_COMPACTOR_SHADOW=true`) y acumulando datos
- [ ] Al menos 1000 turns en `context_compactor_shadow_log`
- [ ] `compaction_pct < 15%` (gate) → confirmado con `analyze_compactor_shadow.py`
- [ ] `reason = CIRCUIT_BREAK` nunca aparece en shadow log
- [ ] CCEE validado para distillation si `distill_applied > 0%` (ΔCCEE ≥ -3)
- [ ] Manel ha revisado y aprobado la activación

### Canary rollout recomendado

**PENDING Phase 3 live rollout** — sticky hashing per creator no está implementado aún.

Una vez implementado, secuencia recomendada:

```
Día 1: Stefano 10%   → verificar métricas 24h
Día 2: Stefano 25%   → verificar métricas
Día 3: Stefano 50% + Iris 10% → verificar
Día 5: Stefano 100% + Iris 50%
Día 7: Iris 100%
```

Criterio no-go (rollback inmediato):
- CCEE composite regresa > -5 puntos vs baseline
- Error rate > 2x baseline
- Latencia P95 > +200ms respecto a baseline

### Activar compaction (cuando Phase 3 esté lista)

```bash
# Railway: setear variable de entorno
railway variables --set USE_COMPACTION=true

# Verificar en logs
railway logs -n 50 | grep -i "compactor\|compaction"
```

### Kill switch

```bash
# Desactivar compaction inmediatamente
railway variables --set USE_COMPACTION=false
# El siguiente deploy la desactiva. Para efecto inmediato, hacer deploy manual:
railway up
```

**Sin rollback de datos** — el compactor no persiste nada en prod (solo el shadow log).

---

## 5. Troubleshooting

### "Prompt cut mid-sentence" — texto cortado

**Síntoma:** Las respuestas del creador parecen responder a un contexto incompleto. Especialmente se nota en respuestas que deberían recordar algo de Doc D pero no lo hacen.

**Diagnóstico:**
```sql
-- Ver si style_prompt está siendo truncado agresivamente
SELECT sections_truncated, reason, divergence_chars
FROM context_compactor_shadow_log
WHERE sections_truncated @> '["style_prompt"]'::jsonb
  AND timestamp > NOW() - INTERVAL '6 hours'
ORDER BY divergence_chars DESC
LIMIT 10;
```

**Causa más probable:** ratio `style_prompt` demasiado bajo para este creator.

**Solución:** Subir ratio `style_prompt` en creator_runtime_config (§2).

---

### "Latency spike" — P95 subió

**Síntoma:** Latencia P95 aumentó > 200ms tras activar compaction.

**Diagnóstico:**
```sql
-- Ver si hay muchas rondas de truncación agresiva (costosas en CPU)
SELECT reason, COUNT(*) FROM context_compactor_shadow_log
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY reason;
```

**Causa más probable:** `AGGRESSIVE_TRUNC` frecuente — el compactor está en el paso 6 (más caro) porque los ratio caps del paso 5 no son suficientes.

**Solución:** Ajustar ratios para que la mayoría de turnos terminen en paso 5 o antes.

---

### "Lost DNA examples" — el clone perdió ejemplos de respuesta

**Síntoma:** Las respuestas ya no usan los ejemplos concretos de estilo del Doc D.

**Diagnóstico:** Verificar que `style_prompt` tiene la mayor prioridad (priority=2 en `_build_compactor_sections`). Si se está truncando, StyleDistillCache debería estar activo.

```sql
-- ¿Está usando distillation para este creator?
SELECT distill_applied, COUNT(*)
FROM context_compactor_shadow_log
WHERE creator_id = '<uuid>'
  AND timestamp > NOW() - INTERVAL '24 hours'
GROUP BY distill_applied;
```

Si `distill_applied = false` pero el Doc D está siendo truncado → la distillation no tiene cache populado.

**Solución:**
```bash
python3.11 scripts/distill_style_prompts.py --creator-id <uuid>
```

---

### `reason = CIRCUIT_BREAK` — whitelist overflow

**Síntoma:** Entradas en shadow log con `reason = CIRCUIT_BREAK` (no confundir con CircuitBreaker de generación).

**Esto indica que las secciones whitelist (`system_instructions`, `guardrails`, `persona_identity`, `current_user_msg`, `tone_directive`) suman más que MAX_CONTEXT_CHARS=8000.**

**Es un estado patológico.** Causas posibles:
- `current_user_msg` extraordinariamente largo (>7000 chars) — ej. lead envió un essay
- Bug en ensamblado que duplicó alguna sección whitelist

**Acción:**
1. Buscar el turn concreto y el lead_id
2. Verificar qué mensaje causó el overflow
3. Si es `current_user_msg` largo: añadir truncación defensiva al message input (fuera del compactor)
4. Si es bug: investigar el ensamblado en `core/dm/phases/context.py`

---

## Referencias

- Diseño ARC3: `docs/sprint5_planning/ARC3_compaction.md` §2.3
- Script de análisis: `scripts/analyze_compactor_shadow.py`
- Feature flags: `core/feature_flags.py` (ENABLE_COMPACTOR_SHADOW, USE_COMPACTION)
- Código compactor: `core/generation/compactor.py`
- Integración context: `core/dm/phases/context.py:600-685`
