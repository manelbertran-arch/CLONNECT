# ARC4 Phase 1 — Mutations Inventory (Real State)

**Branch:** `feature/arc4-phase1-baseline-rules`
**Date:** 2026-04-19
**Author:** ARC4 Phase 1 analysis

---

## TL;DR — Discrepancias vs Design Doc

El design doc (`ARC4_eliminate_mutations.md §1.2`) asume que las 11 mutations están en
`services/response_post.py`. **Ese archivo no existe.** Las mutations están distribuidas:

| Design doc | Realidad |
|---|---|
| `services/response_post.py::_a2b` | Inline en `core/dm/phases/postprocessing.py:108-131` |
| `services/response_post.py::_a2c` | Inline en `core/dm/phases/postprocessing.py:133-163` |
| `services/response_post.py::_a3` (meta-questions) | A3 en código = echo detector (distinto) |
| `services/response_post.py::_length` | `services/length_controller.py::enforce_length` (496 LOC) |
| `services/response_post.py::_emoji` | `core/dm/style_normalizer.py::normalize_style()` emoji section |
| `services/response_post.py::_punct` | `core/dm/style_normalizer.py::normalize_style()` exclamation section |
| `services/response_post.py::_noask` | `services/question_remover.py::process_questions` (265 LOC) |
| `services/guardrails.py` | `core/guardrails.py` (342 LOC) |
| `services/pii_redactor.py` | **NO EXISTE** |
| M9 `normalize_casing` | **NO EXISTE** |
| M11 `insert_signature_tic` | **NO EXISTE** |

---

## Inventario Real: M1-M11

| # | Nombre (design doc) | Archivo real | Línea | LOC real | LOC doc | Risk | Flag actual | Callers | Tests |
|---|---|---|---|---|---|---|---|---|---|
| **M1** | `apply_guardrails` | `core/guardrails.py` | 1-342 | 342 | ~180 | 🔴 HIGH | `ENABLE_GUARDRAILS` | `postprocessing.py:343` | `tests/test_guardrails_voseo.py`, `tests/audit/test_audit_guardrails.py` |
| **M2** | `redact_pii` | — | — | 0 | ~95 | — | — | — | — |
| **M3** | `dedupe_repetitions_a2b` | `core/dm/phases/postprocessing.py` | 108-131 | ~24 inline | ~60 | 🟢 LOW | **NINGUNO** | self (postprocessing) | ninguno |
| **M4** | `dedupe_sentences_a2c` | `core/dm/phases/postprocessing.py` | 133-163 | ~31 inline | ~85 | 🟢 LOW | **NINGUNO** | self (postprocessing) | ninguno |
| **M5** | `remove_meta_questions_a3` | — | — | 0 | ~70 | — | — | — | — |
| **M5-alt** | `echo_detector` (A3) | `core/dm/phases/postprocessing.py` | 164-203 | ~40 inline | — | 🟢 LOW | **NINGUNO** | self (postprocessing) | ninguno |
| **M6** | `normalize_length` (`enforce_length`) | `services/length_controller.py` | 341-420+ | 496 | ~120 | 🟡 MEDIUM | **NINGUNO** | `postprocessing.py:368` | `tests/` (varios) |
| **M7** | `normalize_emojis` | `core/dm/style_normalizer.py` | 299-325 | ~27 | ~90 | 🟢 LOW | `ENABLE_STYLE_NORMALIZER` (shared) | `postprocessing.py:376` | ninguno |
| **M8** | `normalize_punctuation` | `core/dm/style_normalizer.py` | 277-297 | ~20 | ~55 | 🟢 LOW | `ENABLE_STYLE_NORMALIZER` (shared) | `postprocessing.py:376` | ninguno |
| **M9** | `normalize_casing` | — | — | 0 | ~40 | — | — | — | — |
| **M10** | `strip_question_when_not_asked` | `services/question_remover.py` | 1-265 | 265 | ~65 | 🟡 MEDIUM | `ENABLE_QUESTION_REMOVAL` ✅ | `postprocessing.py:245` | ninguno dedicado |
| **M11** | `insert_signature_tic` | — | — | 0 | ~75 | — | — | — | — |

---

## Análisis de Discrepancias

### Mutations que NO existen (diseñadas pero no implementadas)

**M2 — `redact_pii`:**
- Design doc asume `services/pii_redactor.py` con 95 LOC.
- Realidad: `core/sensitive_detector.py` detecta contenido sensible en el INPUT (crisis,
  abuso), NO redacta PII del output. El campo `pii_redacted_types: []` en postprocessing.py:587
  siempre es vacío, confirmando que la redacción PII nunca se aplica.
- **Acción ARC4:** No hay que eliminar nada. El riesgo de compliance existe (LLM podría
  filtrar email/teléfono del creador) — registrar como deuda técnica de seguridad separada.

**M5 — `remove_meta_questions_a3`:**
- Design doc asume función en `services/response_post.py::_a3`.
- Realidad: El bloque A3 en postprocessing.py es un **echo detector** (detecta si el bot
  copió el mensaje del lead con Jaccard ≥ 0.55 y lo sustituye con pool de respuestas cortas).
- `core/response_fixes.py::remove_catchphrases` existe pero está **DEPRECATED** y no se llama
  desde `apply_all_response_fixes()` (comentario: "merged into question_remover.py").
- La remoción de catchphrases/meta-questions vive actualmente en `BANNED_QUESTIONS` de
  `services/question_remover.py` (parte de M10).
- **Acción ARC4:** M5 como mutation independiente no existe. El echo detector (A3) sí existe
  y tiene valor propio. Separar su análisis de M5.

**M9 — `normalize_casing`:**
- No existe ninguna función de normalización de casing en el pipeline post-gen.
- No hay `_tone_config.casing_rule` implementado.
- **Acción ARC4:** Diseñar prompt rule directamente, sin eliminar código.

**M11 — `insert_signature_tic`:**
- No existe ninguna función de inserción de tic verbal.
- No hay `tic_usage_rate` ni mecanismo de tracking.
- **Acción ARC4:** Solo diseñar la prompt rule (ya que la mutation a eliminar no existe).

---

### Mutations que existen pero con nombre/ubicación diferente

**M5-alt — Echo Detector (A3):**
- No es "remove meta questions" — es detección de eco (bot repite lo que dijo el lead).
- Threshold actual: Jaccard ≥ 0.55 (`ECHO_JACCARD_THRESHOLD` env var).
- Flag actual: **NINGUNO** — siempre activo.
- **ARC4 Phase 1:** Añadir `DISABLE_M5_ECHO_DETECTOR` flag.
- **Decisión REPLACE vs KEEP:** A3 echo detector es defensivo, no cosmético. Más cercano
  a M1 (guardrails) que a M3/M4 (cosmetic). Reconsiderar si KEEP o REPLACE.

**M7 y M8 — style_normalizer (compartido):**
- Ambas mutations viven en `core/dm/style_normalizer.py::normalize_style()`.
- Tienen UN solo flag compartido: `ENABLE_STYLE_NORMALIZER`.
- Para aislarlas en shadow testing, necesitan flags individuales:
  - `DISABLE_M7_NORMALIZE_EMOJIS`
  - `DISABLE_M8_NORMALIZE_PUNCTUATION`
- **Nota:** M8 en realidad solo normaliza exclamaciones (`!` → `.`), no puntuación general.
  El nombre "normalize_punctuation" del design doc era demasiado amplio.

---

## LOC Real vs Estimado

| Mutation | LOC real | LOC estimado | Diferencia |
|---|---|---|---|
| M1 guardrails | 342 | ~180 | +162 |
| M2 pii_redactor | 0 | ~95 | -95 (no existe) |
| M3 A2b | ~24 | ~60 | -36 |
| M4 A2c | ~31 | ~85 | -54 |
| M5 meta-questions | 0 | ~70 | -70 (no existe) |
| M5-alt echo A3 | ~40 | — | no estimado |
| M6 length_controller | 496 | ~120 | +376 |
| M7 emoji (style_norm) | ~27 | ~90 | -63 |
| M8 punct (style_norm) | ~20 | ~55 | -35 |
| M9 casing | 0 | ~40 | -40 (no existe) |
| M10 question_remover | 265 | ~65 | +200 |
| M11 signature_tic | 0 | ~75 | -75 (no existe) |

**Total real:** ~1,245 LOC (incluyendo M1 y todo lo no-eliminable)
**Total real eliminable (M3-M10 sin M1):** ~897 LOC
**Estimado design doc:** ~935 LOC total

---

## Flags Existentes vs Nuevos Necesarios

### Flags ya existentes (reutilizar)

| Mutation | Flag existente | Env var |
|---|---|---|
| M1 | `flags.guardrails` | `ENABLE_GUARDRAILS` |
| M7+M8 | `ENABLE_STYLE_NORMALIZER` | `ENABLE_STYLE_NORMALIZER` |
| M10 | `flags.question_removal` | `ENABLE_QUESTION_REMOVAL` |

### Flags nuevos añadidos (ARC4 Phase 1)

| Mutation | Flag nuevo | Env var | Default |
|---|---|---|---|
| M3 | `flags.m3_intra_repetition` | `DISABLE_M3_DEDUPE_REPETITIONS` | false |
| M4 | `flags.m4_sentence_dedupe` | `DISABLE_M4_DEDUPE_SENTENCES` | false |
| M5-alt | `flags.m5_echo_detector` | `DISABLE_M5_ECHO_DETECTOR` | false |
| M6 | `flags.m6_length_enforce` | `DISABLE_M6_NORMALIZE_LENGTH` | false |
| M7 | — | `DISABLE_M7_NORMALIZE_EMOJIS` | false |
| M8 | — | `DISABLE_M8_NORMALIZE_PUNCTUATION` | false |

---

## Mutations Dead Code / Candidatas Inmediatas

**M5 `remove_catchphrases` en `core/response_fixes.py:347-379`:**
- Función marcada como DEPRECATED con comentario explícito.
- NO se llama desde `apply_all_response_fixes()`.
- Es dead code — candidata a eliminar en Phase 3 sin impacto CCEE.

**M9 `normalize_casing` y M11 `insert_signature_tic`:**
- No existen → solo diseñar prompt rules, no hay código que eliminar.

---

## Callers por Mutation (Pipeline)

Todas las mutations activas son invocadas desde `core/dm/phases/postprocessing.py::phase_postprocessing()`:

```
phase_postprocessing()
├── A2b (M3 dedupe_repetitions) — línea 108-131 — inline
├── A2c (M4 dedupe_sentences)  — línea 133-163 — inline
├── A3  (M5-alt echo_detector)  — línea 164-203 — inline
├── flags.output_validation     — línea 206
├── flags.response_fixes → apply_all_response_fixes() — línea 218
├── flags.blacklist_replacement → apply_blacklist_replacement() — línea 231
├── flags.question_removal → process_questions() (M10) — línea 244
├── flags.guardrails → agent.guardrails.validate_response() (M1) — línea 343
├── enforce_length() (M6)       — línea 368
└── normalize_style() (M7+M8)  — línea 376
```

---

## Próximos Pasos

1. **CCEE baseline** — Medir composite con todas las mutations activas (`arc4_baseline_all_mutations_on_*`)
2. **Shadow tests** — 9 runs individuales con `DISABLE_M*=true` (LOW risk primero)
3. **Análisis** — `ARC4_per_mutation_ccee_impact.md`
4. **Prompt rules** — `ARC4_prompt_rules_v1.md` (ya disponible)
5. **Rollout plan** — `ARC4_phase1_rollout_plan.md` (ya disponible)
