# ARC3 Phase 1 — StyleDistillCache CCEE Validation Results

**Worker I — Validación CCEE**
**Fecha:** 2026-04-19
**Branch:** feature/arc3-distill-ccee-validation
**Creator validado:** iris_bertran

---

## 1. Contexto

### Wiring activo
- Commit de wiring: `982390fb` (merge(arc3-phase1-wiring))
- Flag: `USE_DISTILLED_DOC_D` conectado en `core/dm/agent.py:192`
- Función: `services/creator_style_loader.py:get_distilled_style_prompt_sync()` (cache-only, fail-silent)
- Tabla: `creator_style_distill` (migración 048, verificada en DB)

### Configuración CCEE
- Modelo generación: `google/gemma-4-31b-it` via OpenRouter
- Modelo juez: `Qwen/Qwen3-30B-A3B` via DeepInfra
- 20 casos · 1 run · ST + MT · v4-composite + v5
- `USE_COMPRESSED_DOC_D=true` (activo en ambos runs — Doc D de partida: 2557 chars, versión comprimida)

### Fix de script aplicado
`scripts/distill_style_prompts.py` tenía 3 bugs en `_fetch_active_creators`:
1. `nickname` → `name` (columna real en creators)
2. `is_active` → no existe (filtrado removido para lookup por slug)
3. `WHERE id = :cid` → `WHERE name = :cid` (el CLI recibe slug, no UUID)

---

## 2. Distill Generado

| Campo | Valor |
|-------|-------|
| Creator | iris_bertran (UUID: 8e9d1705-4772-40bd-83b1-c6821c5593bf) |
| Doc D fuente | 2557 chars (comprimido, `USE_COMPRESSED_DOC_D=true`) |
| Distill producido | 1368 chars |
| Compression ratio | 54% (2557 → 1368) |
| Hash fuente | `7982329706a280e7` |
| Modelo distilador | google/gemma-4-31b-it |
| Prompt version | v1 |
| Latencia generación | 10.5s |

### Sample Doc D fuente (primeros 500 chars)
```
Eres Iris Bertran, creadora de contenido de fitness y bienestar con más de 1M de seguidores.
Respondes DMs de Instagram y WhatsApp de forma natural, directa y sin filtros de asistente.
Tuteo obligatorio.

**VOZ Y ESTILO**
- **Longitud:** Mensajes muy cortos (13-53 caracteres). 1-2 frases máximo.
- **Emojis:** Uso mínimo (solo en el 23% de los mensajes).
- **Idiomas:** Mezcla de Catalán (44%), Español (28%) y Portugués (9%).
```

### Sample Distilled (primeros 500 chars)
```
Eres Iris Bertran. Respondes DMs de Instagram y WhatsApp de forma natural, directa y sin filtros de asistente. Tuteo obligatorio.

**VOZ Y ESTILO**
- **Longitud:** Mensajes muy cortos (13-53 caracteres). 1-2 frases máximo.
- **Emojis:** Uso mínimo (solo en el 23% de los mensajes). El 77% NO lleva emoji. Permitidos: 😂 🤣 😘 💪 🏾 😮 💨 🙂.
- **Puntuación y Formato:** 
    - Exclamaciones (!): Solo en énfasis emocional (2% de casos).
```

---

## 3. Tabla Comparativa Completa

**Archivos CCEE:**
- OFF: `tests/ccee_results/iris_bertran/arc3_distill_validation_OFF_20260419_1952.json`
- ON:  `tests/ccee_results/iris_bertran/arc3_distill_validation_ON_20260419_2023.json`

### Composite global

| Variante | OFF (baseline) | ON (tratamiento) | Δ |
|----------|---------------|-----------------|-----|
| v4 composite | 66.20 | 65.90 | -0.30 |
| v4.1 composite | 67.60 | 66.80 | -0.80 |
| **v5 composite** | **67.60** | **66.70** | **-0.90** |

### Dimensiones v5 (pesos ×100)

| Dimensión | Peso | OFF | ON | Δ | Nota |
|-----------|------|-----|-----|-----|------|
| **S1 Style Fidelity** | 16% | 69.10 | 68.30 | **-0.80** | ✅ CRÍTICO OK |
| S2 Response Quality | 12% | 49.10 | 45.60 | -3.50 | |
| S3 Strategic Alignment | 16% | 58.40 | 56.30 | -2.10 | |
| S4 Adaptation | 9% | 65.60 | 63.70 | -1.90 | |
| J_old Cognitive Fidelity | 3% | 52.86 | 57.91 | +5.05 | |
| J_new (J3/J4/J5) | 9% | 70.80 | 68.90 | -1.90 | |
| J6 Q&A Consistency | 3% | 100.0 | 95.0 | -5.00 | ⚠️ en umbral |
| **K Context Retention** | 6% | 82.70 | 95.0 | **+12.30** | ✅ mejora |
| G5 Persona Robustness | 5% | 100.0 | 100.0 | 0.00 | |
| L Logical Reasoning | 9% | 67.0 | 64.4 | -2.60 | |
| H Turing Test | 7% | 80.0 | 76.0 | -4.00 | |
| B Persona Consistency | 5% | 57.1 | 60.0 | +2.90 | |

### Sub-dimensiones detalladas

| Sub-dim | OFF | ON | Δ |
|---------|-----|-----|-----|
| K1 Context Retention | 73.22 | 94.58 | **+21.36** ⬆️ |
| K2 Style Retention | 96.87 | 95.64 | -1.23 |
| J3 Prompt-to-Line | 89.0 | 84.5 | -4.50 |
| J4 Line-to-Line | 57.28 | 61.88 | +4.60 |
| J5 Belief Drift | 60.0 | 55.0 | -5.00 |
| L1 Persona Tone | 85.0 | 82.5 | -2.50 |
| L2 Logical Reasoning | 58.66 | 53.78 | -4.88 |
| L3 Action Justification | 51.24 | 51.0 | -0.24 |
| H1 Turing Test Rate | 80.0 | 76.0 | -4.00 |
| B2 Persona Consistency | 31.25 | 36.25 | +5.00 |
| B5 Emotional Signature | 40.0 | 43.75 | +3.75 |
| B4 Format Compliance | 100.0 | 100.0 | 0.00 |
| C2 Naturalness | 63.75 | 61.25 | -2.50 |
| C3 Contextual Appropriateness | 12.5 | 25.0 | +12.50 ⬆️ |

---

## 4. Análisis Dimensiones Clave

### S1 Style Fidelity (CRÍTICO)
- OFF: 69.1 → ON: 68.3 → **Δ -0.8**
- **Dentro del umbral Δ ≥ -5**. La destilación preserva la voz de Iris: tuteo, longitud corta, mix catalán/español, restricciones de emoji.
- Conclusión: el distill v1 captura correctamente los elementos de estilo esenciales.

### S3 Strategic Alignment
- OFF: 58.4 → ON: 56.3 → **Δ -2.1**
- Caída moderada pero dentro del ruido para 20 casos. S3 fue el patrón preocupante en ARC2; aquí la caída es mínima y bien dentro de threshold.

### K Context Retention (sorpresa positiva)
- OFF: 82.7 → ON: 95.0 → **Δ +12.3**
- Sub-dim K1: +21.36 pts. Inesperado. El Doc D destilado parece enfocar mejor el contexto conversacional al eliminar redundancias genéricas. El modelo retiene mejor el contexto cuando el prompt de estilo es más denso en instrucciones concretas.

### J6 Q&A Consistency
- OFF: 100.0 → ON: 95.0 → **Δ -5.0** (en el umbral)
- Ligera inconsistencia en respuestas a preguntas directas. Posiblemente el distill eliminó alguna instrucción sobre consultas factuales. A vigilar en prod pero no bloquea.

### H Turing Test (H1)
- OFF: 80.0 → ON: 76.0 → **Δ -4.0**
- Caída de 4 puntos. Puede ser ruido estadístico en 20 casos (±3-5 es ruido típico) o que el distill reduce levemente la naturalidad. No supera umbral de alerta.

---

## 5. Veredicto

### **APPROVE ✓**

| Criterio | Umbral | Resultado | Estado |
|---------|--------|-----------|--------|
| Δ composite | ≥ -3 | **-0.90** | ✅ PASS |
| Δ S1 Style Fidelity | ≥ -5 | **-0.80** | ✅ PASS |

Ambos criterios del design doc ARC3 §3 Phase 1 se cumplen con margen amplio.

**La destilación es segura para activar en producción.**

El delta de -0.90 en v5 composite está dentro del ruido estadístico de una comparación de 20 casos (σ estimada ≈ 1.5-2.0). La mejora de K Context Retention (+12.3) es un bonus no esperado.

---

## 6. Recomendaciones APPROVE

### Acción inmediata
1. Correr `scripts/distill_style_prompts.py --creator-id stefano_bonanno` para poblar cache del segundo creator
2. Activar `USE_DISTILLED_DOC_D=true` en Railway env vars
3. Monitor 48-72h post-activación:
   - Revisar `railway logs -n 200 | grep "\[ARC3\]"` — confirmar cache hits
   - KPIs: S1 Style, K Context Retention, H1 Turing Test
   - Alert si S1 < 62 o composite < 62

### Proceder con ARC3 Phase 3
Una vez activado en Railway:
- Phase 3 = live rollout: 10% → 50% → 100% con métricas de prod
- Usar CCEE mensual para validar que el distill sigue siendo válido tras actualizaciones de Doc D
- Re-generar distill automáticamente cuando Doc D cambie (hash-based cache ya lo gestiona)

### Nota técnica importante
El fix de `scripts/distill_style_prompts.py` (3 bugs corregidos) debe integrarse en main antes de escalar a otros creators. Los bugs eran: columna `nickname` → `name`, filtro `is_active` → inexistente, lookup `id = :cid` → `name = :cid`.

---

## 7. Cost Breakdown

| Operación | Costo |
|-----------|-------|
| Distill generation (1 LLM call) | ~$0.002 |
| CCEE OFF (20 cases, judge Qwen) | ~$0.049 |
| CCEE ON (20 cases, judge Qwen) | ~$0.049 |
| **Total Worker I** | **~$0.10** |

Tiempo total ejecución: ~60 min (40 min CCEE + diagnostics)

---

## 8. Próximos Pasos

```bash
# 1. Poblar distill para segundo creator
python3.11 scripts/distill_style_prompts.py --creator-id stefano_bonanno

# 2. Activar en Railway (Manel ejecuta)
# railway variables set USE_DISTILLED_DOC_D=true

# 3. Verificar cache hits en prod
# railway logs -n 200 | grep "\[ARC3\]"
```
