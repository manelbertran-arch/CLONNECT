# ARC4 Phase 2 — Shadow CCEE Runs: Per-Mutation Impact Results

**Branch:** `feature/arc4-phase2-shadow-runs`
**Date:** 2026-04-19
**Creator:** iris_bertran
**Model:** google/gemma-4-31b-it (OpenRouter)
**Runs:** 1 run × 30 cases × multi-turn (5 conv × 10 turns) + v5 scoring

---

## Contexto

ARC4 Phase 1 (commit `e5e718d2`) instaló 6 kill switches `DISABLE_M*` sobre las 7 mutations
reales del pipeline post-generación. Phase 2 mide el impacto aislado de desactivar cada una
para determinar el orden seguro de eliminación en Phase 3+.

**Mutations medidas:** M3, M4, M5-alt, M6, M7, M8, M10
**Mutations excluidas:** M1 (guardrails, KEEP por diseño), M2/M9/M11 (no existen en código)

---

## Baseline (todas las mutations activas)

| Métrica | Valor |
|---|---|
| **v5 composite** | **70.70** |
| v4 composite | 70.90 |
| v4.1 composite | 71.70 |
| K1 (memory continuity) | 90.84 |
| S3 (style fidelity) | 69.00 |
| Archivo | `arc4_shadow_baseline_all_on_20260419_1514.json` |

---

## Resultados por Mutation

| Mutation | Risk (Phase 1) | v5 sin mutation | Δ vs baseline | K1 sin | ΔK1 | S3 sin | ΔS3 | Clasificación |
|---|---|---|---|---|---|---|---|---|
| **M3** dedupe_repetitions | LOW | 67.20 | **-3.50** | 47.5 | -43.3 | 65.6 | -3.4 | 🔴 PROTECTIVE |
| **M4** dedupe_sentences | LOW | 67.40 | **-3.30** | 74.4 | -16.4 | 60.0 | -9.0 | 🔴 PROTECTIVE |
| **M5-alt** echo_detector | LOW | 66.00 | **-4.70** | 65.2 | -25.6 | 59.6 | -9.4 | 🔴 PROTECTIVE |
| **M6** normalize_length | MEDIUM | 68.40 | **-2.30** | 75.3 | -15.5 | 61.6 | -7.4 | 🔴 PROTECTIVE |
| **M7** normalize_emojis | LOW | 68.50 | **-2.20** | 58.3 | -32.6 | 61.9 | -7.1 | 🔴 PROTECTIVE |
| **M8** normalize_punctuation | LOW | 67.60 | **-3.10** | 49.2 | -41.6 | 57.4 | -11.6 | 🔴 PROTECTIVE |
| **M10** strip_question | MEDIUM | 71.00 | **+0.30** | 81.3 | -9.6 | 62.5 | -6.5 | 🟡 NEUTRAL |

### Reglas de clasificación aplicadas
- `Δ > +1.0` → **HARMFUL** (eliminar = ganancia directa)
- `-1.0 ≤ Δ ≤ +1.0` → **NEUTRAL** (eliminar = seguro con prompt rule backup)
- `Δ < -1.0` → **PROTECTIVE** (eliminar = regresión, necesita prompt rule validada)

---

## Hallazgos Clave

### 1. Ninguna mutation es HARMFUL
Esperábamos encontrar mutations que activamente dañaran la calidad. No hay ninguna. Todas
las mutations o protegen la calidad o son neutras.

### 2. M10 es el único candidato seguro de eliminar (NEUTRAL, Δ=+0.30)
`strip_question_when_not_asked` no aporta al composite v5. El ligero +0.3 sugiere que a veces
elimina preguntas que el evaluador preferiría ver. Candidato a eliminar en Phase 3 con
una prompt rule de backup.

### 3. K1 es el indicador más sensible
La dimensión K1 (memory continuity / respuesta consistente entre turns) colapsa cuando
se eliminan las mutations de deduplicación:

| Mutation | K1 baseline | K1 sin mutation | ΔK1 |
|---|---|---|---|
| M3 dedupe_reps | 90.84 | 47.5 | **-43.3** |
| M8 normalize_punct | 90.84 | 49.2 | **-41.6** |
| M7 normalize_emojis | 90.84 | 58.3 | -32.6 |
| M5 echo_detector | 90.84 | 65.2 | -25.6 |

Esto indica que las mutations de limpieza de texto no solo mejoran el estilo — también
previenen inconsistencias que el evaluador multi-turn detecta como falta de coherencia.

### 4. S3 (style fidelity) cae en todas las mutations
S3 baja entre -3.4 y -11.6 puntos al desactivar cualquier mutation. Las mutations son
los guardianes del estilo de Iris. Sin ellas, el modelo genera respuestas que divergen
del tono/estilo documentado.

### 5. M5-alt tiene el mayor impacto negativo (Δ=-4.7)
El echo detector previene que el bot copie literalmente el mensaje del lead. Sin él,
el evaluador detecta respuestas vacías o eco que dañan especialmente S3 (-9.4) y K1 (-25.6).

---

## Clasificación Final y Plan Phase 3 Rollout

### HARMFUL (eliminar = ganancia directa) — 0 mutations
*Ninguna mutation daña activamente la calidad. No hay eliminaciones "gratuitas".*

### NEUTRAL (eliminar seguro con prompt rule backup) — 1 mutation
| Priority | Mutation | Δ | Acción Phase 3 |
|---|---|---|---|
| **P1** | M10 strip_question | +0.30 | Diseñar prompt rule: "nunca termines con pregunta si el lead no ha preguntado" → validar con CCEE preflight → eliminar |

### PROTECTIVE (necesita prompt rule validada antes de eliminar) — 6 mutations
Ordenadas de menor a mayor impacto (menor riesgo primero):

| Priority | Mutation | Δ | ΔK1 | Acción Phase 3 |
|---|---|---|---|---|
| **P2** | M7 normalize_emojis | -2.20 | -32.6 | Prompt rule: "usa emojis con moderación (≤2 por mensaje)" → validar |
| **P3** | M6 normalize_length | -2.30 | -15.5 | Prompt rule: "respuestas de 1-3 frases, sin elaborar en exceso" → validar |
| **P4** | M8 normalize_punct | -3.10 | -41.6 | Prompt rule: "usa signos de exclamación con parsimonia (≤1 por mensaje)" → validar |
| **P5** | M4 dedupe_sentences | -3.30 | -16.4 | Prompt rule: "no repitas la misma idea en el mismo mensaje" → validar |
| **P6** | M3 dedupe_reps | -3.50 | -43.3 | Prompt rule: "no repitas palabras/frases consecutivas" → validar |
| **P7** | M5-alt echo_detector | -4.70 | -25.6 | Prompt rule: "nunca copies el mensaje del usuario literalmente" → validar (mayor riesgo) |

---

## Criterio Go/No-Go para Phase 3

Antes de eliminar cualquier mutation PROTECTIVE:
1. Diseñar la prompt rule sustituta
2. Validar con CCEE shadow (30 casos, misma config): `ΔCCEE_composite ≥ -1.0` vs baseline actual
3. Si pasa: eliminar el código de la mutation + activar la prompt rule
4. Si no pasa: refinar la prompt rule e iterar

Para M10 (NEUTRAL): validar solo que la prompt rule no regresa → eliminar directamente.

---

## Archivos de Datos

| Run | Archivo | v5 |
|---|---|---|
| Baseline | `arc4_shadow_baseline_all_on_20260419_1514.json` | 70.70 |
| Sin M3 | `arc4_shadow_without_m3_20260419_1544.json` | 67.20 |
| Sin M4 | `arc4_shadow_without_m4_20260419_1619.json` | 67.40 |
| Sin M5 | `arc4_shadow_without_m5_20260419_1651.json` | 66.00 |
| Sin M7 | `arc4_shadow_without_m7_20260419_1723.json` | 68.50 |
| Sin M8 | `arc4_shadow_without_m8_20260419_1757.json` | 67.60 |
| Sin M6 | `arc4_shadow_without_m6_20260419_1834.json` | 68.40 |
| Sin M10 | `arc4_shadow_without_m10_20260419_1905.json` | 71.00 |

---

## Next Steps (Phase 3)

1. **M10 primero** — diseñar prompt rule anti-pregunta → CCEE preflight → eliminar `services/question_remover.py` (265 LOC)
2. **M7 + M6** (LOW-MEDIUM, Δ < -2.5) — prompt rules de emoji/longitud → validar juntas o separadas
3. **M8 + M4 + M3** — prompt rules de puntuación/dedup → validar
4. **M5-alt last** — mayor impacto, prompt rule más difícil de especificar
