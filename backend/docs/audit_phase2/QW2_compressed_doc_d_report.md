# QW2 — Activar `USE_COMPRESSED_DOC_D` para Iris

**Sprint:** W-QuickWin 2 (Audit Phase 2)
**Date:** 2026-04-16
**Risk:** Medio (afecta calidad del bot en producción)
**Status:** **DECIDIDO — NO ACTIVAR**
**Decision driver:** Composite cae **-10.69 puntos** (threshold -5)

---

## TL;DR

| Métrica | Baseline (flag OFF) | Compressed (flag ON) | Delta |
|---|---|---|---|
| **Composite CCEE** (per-run avg) | **69.42** | **58.73** | **-10.69** ⚠️ |
| **v4 composite** | **68.8** | **62.5** | **-6.30** ⚠️ |

**Veredicto:** ambas métricas exceden el umbral de regresión (-5 puntos). Se recomienda **NO activar** el flag en producción. El ahorro de ~4K chars en prompt no compensa la pérdida de fidelidad de estilo y memoria.

---

## Contexto

El flag `USE_COMPRESSED_DOC_D` en `services/creator_style_loader.py:22` redirige `get_creator_style_prompt()` al camino de "Priority 0" (`core.dm.compressed_doc_d.build_compressed_doc_d`), devolviendo un Doc D comprimido de ~1.3K-1.6K caracteres en lugar de la personalidad completa (~38K chars para Iris).

```python
# services/creator_style_loader.py:20-24
# When true, use compressed Doc D (~1.3K chars) from CPE baseline metrics
# instead of the 38K personality extraction. Optimized for Qwen3-14B.
USE_COMPRESSED_DOC_D = os.getenv("USE_COMPRESSED_DOC_D", "false").lower() in (
    "true", "1", "yes",
)
```

**Objetivo hipotético:** reducir context pressure en Gemma-4-31B (~4K chars ahorrados) manteniendo calidad.

**Verificación previa (Paso 1):**
- Flag está en default `false`.
- `build_compressed_doc_d("iris_bertran")` devuelve 1577 chars (OK, contenido válido).
- Baseline conocido `sprint4_postfix2_31b.json`: composite 69.42 (3 runs × 50 cases, `gemma-4-31B-it`, judge `Qwen/Qwen3-30B-A3B`, multi-turn v5).

**Búsqueda de medición previa comparable (Paso 2):**
- 14 tests previos con compressed Doc D existen en `tests/ccee_results/iris_bertran/doc_d_gemma_*.json`, pero:
  - **Modelo distinto:** `gemma-4-26b-a4b-it` (no 31b).
  - **Provider distinto:** `google_ai_studio` (no `deepinfra`).
  - **Formato distinto:** métricas CPE (`l1_overall`, `l3_bleu4`) no comparables con composite CCEE v5.
- **Conclusión:** no hay medición previa fiable. Ejecutar CCEE.

---

## Preflight (Paso 3) — n=5, misma semilla

Ejecutado en background con seed `CCEE_SEED=42` para ambas ramas.

| Dim | Flag OFF | Flag ON | Delta |
|---|---|---|---|
| S1 Style Fidelity | 54.08 | 50.76 | -3.32 |
| S2 Response Quality | 63.21 | 61.37 | -1.84 |
| S3 Strategic Alignment | 79.38 | 61.98 | **-17.40** |
| S4 Adaptation | 55.16 | 54.08 | -1.08 |
| B Persona Fidelity | 65.00 | 71.67 | +6.67 |
| H Indistinguishability | 28.45 | 30.39 | +1.94 |
| J Cognitive Fidelity | 45.60 | 40.84 | -4.76 |
| **COMPOSITE** | **62.29** | **57.82** | **-4.47** |

- Preflight composite cae 4.47 puntos (banda "humana-decisión").
- Alta varianza por n=5. Señal coherente pero no concluyente.
- Se escala a CCEE completo (3×50) por potencia estadística.

**Artefactos:**
- `tests/ccee_results/iris_bertran/qw2_preflight_baseline.json`
- `tests/ccee_results/iris_bertran/qw2_preflight_compressed.json`

---

## Full CCEE (Paso 4) — 3 runs × 50 cases, multi-turn

### Configuración

Idéntica a `sprint4_postfix2_31b.json` salvo el flag:

- `--creator iris_bertran --runs 3 --cases 50 --multi-turn --v4-composite --with-prometheus-judge`
- Modelo: `google/gemma-4-31B-it`
- Judge: `Qwen/Qwen3-30B-A3B` (DeepInfra)
- Lead-sim: `Qwen/Qwen3-30B-A3B`
- mt_conversations=5, mt_turns=10
- `CCEE_SEED=42`
- `ENABLE_MEMORY_CONSOLIDATION=false` (aislamos el efecto del flag)

**Nota:** el run compressed NO activó `--v5 --v41-metrics` (omitidos por prisa; el baseline sí los tenía). Como consecuencia `v5_composite` en el JSON compressed es `{}`. La comparación v4 sigue siendo válida (mismas dimensiones S1-S4 + J_old/J_new + K + G5) y la comparación de `composites[]` per-run (CCEE basic, 32/44 params) también.

### Resultados — composites por run

```
Baseline:   [69.63, 70.43, 68.19]  avg 69.42
Compressed: [58.92, 58.26, 59.01]  avg 58.73
Delta:                                 -10.69
```

Los 3 runs compressed están entre -10.4 y -12.2 puntos del baseline. **Regresión consistente**, no ruido de varianza.

### Resultados — v4 composite (weighted)

| Dim | Weight | Base | Comp | Delta |
|---|---|---|---|---|
| S1 Style Fidelity | 0.20 | 74.4 | 56.9 | **-17.5** |
| S2 Response Quality | 0.15 | 68.8 | 63.7 | -5.1 |
| S3 Strategic Align. | 0.20 | 56.7 | 69.5 | **+12.8** |
| S4 Adaptation | 0.12 | 57.4 | 60.3 | +2.9 |
| J_old Memory Recall | 0.05 | 54.9 | 17.5 | **-37.4** |
| J_new | 0.13 | 71.0 | 68.5 | -2.5 |
| K Context Retention | 0.08 | 79.6 | 71.4 | -8.2 |
| G5 Persona Robust. | 0.07 | 100.0 | 70.0 | **-30.0** |
| **v4 COMPOSITE** | — | **68.8** | **62.5** | **-6.3** |

### Lectura por dimensión

**Regresiones graves (→ bloqueo):**

1. **S1 Style Fidelity -17.5** — el Doc D completo codifica patrones léxicos específicos de Iris (slang, muletillas, fillers) que el Doc D comprimido reemplaza por reglas cuantitativas generales ("longitud máx 53 chars", "23% emojis"). El modelo pierde pattern matching fino y genera plantillas genéricas. Observable en las cases de evaluación: bot usa frases repetidas ("Jajaja, me flipa la propuesta", "Tienes alguna hora en mente?") en lugar de alinear con la respuesta real de Iris.

2. **J_old Memory Recall -37.4** — el Doc D completo parece retener mejor el contexto de follower/conversación cuando se genera respuesta; el comprimido, al ser más abstracto, lleva al modelo a ignorar señales de memoria. Un bot que no recuerda al follower es una de las regresiones más visibles en producción.

3. **G5 Persona Robustness -30.0** — en escenarios adversariales multi-turn, el Doc D comprimido cede antes (break-character rate sube 30%). La compresión descarta los guardrails de persona que están en el Doc D completo.

**Ganancias (→ insuficientes para compensar):**

1. **S3 Strategic +12.8** — el comprimido tiene reglas más concisas sobre "no responder como asistente" y "no inventar precios/horarios", que el modelo sigue mejor porque no se diluyen en 38K chars. Validado con ganancia en `contextual_appropriateness` en preflight.

2. **S4 Adaptation +2.9** — mejora marginal, probable correlato del S3.

**Neutro:** S2 (-5.1, límite), J_new (-2.5, dentro de varianza).

### Lectura por peso

Las dimensiones con **peso mayor** (S1 0.20, S3 0.20, S2 0.15, J_new 0.13, S4 0.12) absorben casi todo el delta. El tradeoff es:

- **S1** (peso 0.20) aporta `-17.5 × 0.20 = -3.50` puntos al composite
- **J_old** (peso 0.05) aporta `-37.4 × 0.05 = -1.87` puntos
- **G5** (peso 0.07) aporta `-30.0 × 0.07 = -2.10` puntos
- **S3** (peso 0.20) aporta `+12.8 × 0.20 = +2.56` puntos

Suma de las regresiones dominantes (S1+J_old+G5+K+S2) = **-7.5 pts**
Suma de las ganancias (S3+S4) = **+2.91 pts**
**Net: -4.6 v4 / -6.3 v4 observado** — coherente con la medición.

### Observación cualitativa: generación

Comparando 5 cases de evaluación humana (`[5] Cases for human evaluation`):

**Con compressed ON:**
> User: "Vale ja mho mirare tranqilament i a ver que"
> Real: "Silla rosa? O madrid lo que tu quieras"
> Bot: "Jajaja, me flipa la propuesta. Tienes alguna hora en mente?"

**Con compressed OFF:**
> User: "Vale ja mho mirare tranqilament i a ver que"
> Real: "Silla rosa? O madrid lo que tu quieras"
> Bot: "¡Ay, qué planazo, nena!\nMe encanta la idea de regalarse tiempo juntas."

Ambos están off-topic (el user habla sobre mirar algo tranquilamente; respuesta real pregunta sobre color de silla). **Pero** el comprimido responde con plantillas repetidas ("me flipa la propuesta", "tienes alguna hora en mente") en 4 de 5 cases. El modelo pierde diversidad y cae a un patrón "seguro" que no es Iris.

---

## Decisión (umbrales QW2)

| Regla | Valor | Cumple |
|---|---|---|
| Composite cae >5 puntos → NO activar | -10.69 | ✓ |
| Composite cae 2-5 puntos → decisión humana | | — |
| Composite cae <2 puntos o sube → activar | | — |

**Decisión: NO activar `USE_COMPRESSED_DOC_D` en producción.**

La regresión de -10.69 es:
- **Consistente** (3/3 runs por debajo del baseline más bajo)
- **Concentrada en dimensiones críticas** (S1 estilo, J memoria, G5 persona)
- **No compensada** por la ganancia en S3 Strategic (+12.8)

---

## Trabajo futuro (no-gating)

La hipótesis "comprimir Doc D para ahorrar context" es válida, pero el **método actual** (CPE metrics + BFI → 1.5K chars) pierde demasiada señal en dimensiones clave. Dos caminos:

1. **Comprimido híbrido:** mantener el resumen cuantitativo + añadir **exemplars reales** (~10 mensajes de Iris representativos del distributional fingerprint) y **guardrails de persona** (5-10 frases "never-say" / "always-react-with"). Esto aborda S1 y G5 sin volver a los 38K.

2. **Compresión por dimensiones:** medir qué secciones del Doc D completo aportan más a S1 y G5, y comprimir solo las secciones de baja densidad de información. Requiere análisis por ablaciones.

3. **Re-evaluar con Qwen3-14B:** el comentario del código `"# Optimized for Qwen3-14B"` sugiere que la compresión pudo diseñarse para un modelo más pequeño. Con Gemma-4-31B no hace falta comprimir (suficiente capacidad). Documentar explícitamente en el docstring.

**No se propone ninguna acción inmediata adicional** más allá de mantener el flag en default `false`.

---

## PR diff (NO aplicado)

No es necesario un PR de código: el flag ya está en default `false` y funciona como se espera. Lo único que procede es **documentar la decisión** en el código para futura lectura:

```diff
--- a/services/creator_style_loader.py
+++ b/services/creator_style_loader.py
@@ -18,8 +18,14 @@ logger = logging.getLogger(__name__)

-# When true, use compressed Doc D (~1.3K chars) from CPE baseline metrics
-# instead of the 38K personality extraction. Optimized for Qwen3-14B.
+# When true, use compressed Doc D (~1.3K chars) from CPE baseline metrics
+# instead of the 38K personality extraction. Originally optimized for Qwen3-14B.
+#
+# DO NOT enable for production with Gemma-4-31B:
+#   Validated 2026-04-16 (QW2 CCEE): composite regresses -10.69 points
+#   (69.42 → 58.73, 3 runs × 50 cases, iris_bertran). S1 Style -17.5,
+#   J_old Memory -37.4, G5 Persona -30.0. S3 improves +12.8 but does not
+#   compensate. See docs/audit_phase2/QW2_compressed_doc_d_report.md.
 USE_COMPRESSED_DOC_D = os.getenv("USE_COMPRESSED_DOC_D", "false").lower() in (
     "true", "1", "yes",
 )
```

Este cambio es puramente documental y se puede aplicar directamente al final del sprint de Audit Phase 2 si se desea; no afecta ningún path de producción.

---

## Artefactos y trazabilidad

| Archivo | Descripción |
|---|---|
| `tests/ccee_results/iris_bertran/qw2_preflight_baseline.json` | Preflight flag OFF (n=5, composite 62.29) |
| `tests/ccee_results/iris_bertran/qw2_preflight_compressed.json` | Preflight flag ON (n=5, composite 57.82) |
| `tests/ccee_results/iris_bertran/qw2_full_compressed.json` | Full CCEE flag ON (3×50, composite 58.73, v4=62.5) |
| `tests/ccee_results/iris_bertran/sprint4_postfix2_31b.json` | Baseline full CCEE flag OFF (3×50, composite 69.42, v4=68.8) |
| `logs/qw2_preflight_*.log`, `logs/qw2_full_compressed_*.log` | Execution logs |

---

## Checklist QW2

- [x] **Paso 1** — Verificado estado del flag (default `false`, getter OK).
- [x] **Paso 2** — Buscada medición previa comparable (14 tests CPE distintos: modelo/provider/formato no apto).
- [x] **Paso 3** — Preflight 1×5 matched seed. Delta -4.47 (banda humana-decisión; escalamos).
- [x] **Paso 4** — Full CCEE 3×50 multi-turn. Delta **-10.69** (exceso claro).
- [x] **Paso 5** — Report + PR diff propuesto (solo documentación). **NO activar.**
