# PRESPRINT 7 — Integration Log

**Maintainer:** Manel Bertran  
**Branch activo:** `review/presprint7-veredicts`  
**Última actualización:** 2026-04-25 (post-Sesión 6 correcciones)

> Este documento integra los hallazgos cross-sesión del Presprint 7 (I1–I9).  
> Registra el status de errores de Sprint 6, patrones emergentes entre sesiones,  
> decisiones arquitectónicas pendientes y cobertura de la investigación vs. CCEE.

---

## Resumen Sesiones Presprint 7

| Sesión | Doc | Tema | Estado | Hallazgo Principal |
|---|---|---|---|---|
| S1 | `01_multi_turn_construction.md` | Dataset multi-turn | ✅ Completado + correcciones | Gemma-4 NO tiene {% generation %} — warning crítico. TurnWise +12.8 pp pero degrada single-turn. |
| **S2** | `02_persona_qa_synthesis.md` | Persona Q&A synthesis | ✅ Completado + 5 correcciones | J6 probes dinámicos vía LLM (n=3, Doc D[:1000]). Target absoluto 750-1000 pares. Alignment tax documentado. |
| **S3** | `03_adversarial_examples.md` | Adversarial belief drift | ✅ Completado + 7 correcciones | TYPE-8 Topic Pivot identificado como J5-crítico. TYPE-2/3/5 reasignados a G5. Matching CCEE verificado. |
| **S4** | `04_hyperparameters_qlora.md` | Hiperparámetros QLoRA | ✅ Completado + 6 correcciones | DOS fallos Sprint 6 (dataset + masking). DPO diferido Sprint 8. r=16 + sweep validation proactivo. |
| S5+S7 | `05_07_validation_methodology.md` | Metodología validación + métricas sustituto | ✅ | Definición de surrogate metrics para detección temprana. |
| **S6** | `06_chat_template_gemma4.md` | Chat template Gemma-4 | ✅ **DECISIÓN CERRADA** | Bug central Sprint 6 resuelto. Opción C validada por Google AI Docs. 3 líneas cambian. Loss esperada Sprint 7: 1.5–2.5. Pre-flight: `verify_sprint7_alignment.py`. |
| S8 | `08_base_model_evaluation.md` | Gemma-4 vs Qwen3-30B | ✅ | Gemma-4-31B preferred por bilingüismo CAT/ES y razonamiento. |
| S9 | `09_dataset_quality_gate.md` | Dataset Quality Gate | ✅ | 8 gates definidos con thresholds y script ejecutable. |

---

## Errores Sprint 6 — Status Consolidado

Numeración global que integra errores de proceso (E-xx) y dataset (D-xx) del postmortem.

| # | Error | Categoría | Severidad | Status | Sesión que lo abordó |
|---|---|---|---|---|---|
| #1 | **Masking roto** — TRL Issue #3781: `assistant_only_loss=True` + `use_liger_kernel=True` → silent failure, loss sobre tokens usuario/sistema | Proceso | 🔴 CRÍTICO | ⚠️ Verificar en Sprint 7 | S1, S4 |
| #2 | **Chat template mismatch** — train usa `<\|turn>model\n`, serve inyecta `<\|channel>thought\n<channel\|>` nunca visto en training | Proceso | 🔴 CRÍTICO | ✅ Plan documentado (S6 / I6) | S6 |
| #3 | **System prompt heterogéneo** — 46% system prompt corto, 54% ninguno en training | Proceso/Dataset | 🔴 HIGH | ✅ Plan: unificar a Doc D v2 completo | S2, S4 |
| #4 | **System prompt training ≠ production** (D-09) — Doc D v1 corto en training, Doc D v2 completo en serving | Dataset | 🔴 HIGH | ✅ Plan: Doc D v2 en todos los ejemplos | S2 |
| #5 | **Sin validation split** (D-07) — no hay señal de overfitting durante training | Dataset | 🟡 MEDIUM | ✅ Plan: 90/10 train/val split (S9 gate G-07) | S9 |
| #6 | **0% multi-turn samples** (D-01) — todo el dataset son intercambios single-turn | Dataset | 🔴 HIGH | ✅ Plan completo con threshold=60min, burst merge <5min | S1 |
| #7 | **22 error-string samples** (D-02) — respuestas tipo "[ERROR]", "[TIMEOUT]" en training | Dataset | 🔴 HIGH | ✅ Plan: filtro hard en quality gate | S9 |
| #8 | **0.1% persona Q&A responses** (D-03) — solo 10/9.272 ejemplos contienen un hecho factual de Iris | Dataset | 🔴 HIGH | ✅ Plan completo con matching CCEE verificado. Target 750-1000 pares Q&A. Cobertura J6 confirmada. | **S2** |
| #9 | **441 media/sticker responses** (D-06) — modelo aprende artefactos visuales inútiles | Dataset | 🟡 MEDIUM | ✅ Plan: filtro por `response_type` en quality gate | S9 |
| #10 | **1.352 duplicados exactos 14.6%** (D-05) — over-representation de patterns cortos muy frecuentes | Dataset | 🟡 MEDIUM | ✅ Plan: dedup + keep-1 per canonical | S9 |

---

## Patrones Emergentes

### Patrón 1 — Masking silencioso como vector de riesgo sistemático

**Observado en:** S1, S4, S6  
**Descripción:** Tres mecanismos independientes pueden comprometer silenciosamente el masking de training sin producir error visible: (1) TRL Issue #3781 (liger + assistant_only_loss), (2) chat template mismatch train/serve, (3) boundary strings incorrectos para el modelo target.  
**Riesgo:** Sprint 7 podría repetir Sprint 6 si no se verifican explícitamente los `assistant_masks` en los primeros batches.  
**Mitigation:** S4 recomienda inspección mandatory de `assistant_masks` en ≥3 ejemplos pre-training como gate go/no-go.

---

### Patrón 2 — Sin matching con probes CCEE

**Descripción:** Las sesiones de investigación (I1–I9) diseñan training data para mejorar métricas CCEE, pero la mayoría no han verificado cómo CCEE genera concretamente los probes que miden esas métricas. El riesgo es invertir en training data que no activa los probes reales.

**Status por sesión y métrica:**

| Sesión | Métrica objetivo | Matching con implementación CCEE | Status |
|---|---|---|---|
| S1 (multi-turn) | J2, L, K | Parcial — multi-turn genera conversaciones pero no se analizó cómo score_j2 evalúa | ⚠️ Pendiente |
| **S2 (persona Q&A)** | **J6, B2** | **✅ RESUELTO** — `generate_qa_probes()` verificado en `multi_turn_generator.py` | **✅ Resuelto** |
| S3 (adversarial) | J5 | Sin matching — I3 diseña 6 tipos adversariales pero no ha verificado qué genera `generate_belief_shift_message()` | ⏳ S3 pendiente |
| S4 (hyperparams) | Composite | N/A — hiperparámetros afectan todo, no hay probe específico | ✅ N/A |

**Detalle del matching J6 (S2 — RESUELTO):**

La función `generate_qa_probes()` en `core/evaluation/multi_turn_generator.py` genera probes **dinámicamente** via LLM a partir de los primeros 1000 chars del Doc D, con `n_probes=3` por defecto, cacheados por `creator_id`.

Probes de **fallback** hardcoded (cuando el LLM falla):
```python
fallback_prompts = [
    "Te gusta lo que haces?",       # cubre B6 (valores)
    "Cuál es tu pasión principal?",  # cubre B2 (trabajo/fitness)
    "De dónde eres?",                # cubre B3 (ubicación)
]
```

Probes de **ejemplo** en el prompt del generador:
```
"T'agrada el fitness?"       → "Sí, és la seva passió"        (cubre B2)
"De dónde eres?"             → "Barcelona/Catalunya"           (cubre B3)
"Quin idioma prefereixes?"   → "Català i castellà"             (cubre B7)
```

El inventario B1+B2+B3+B7 (38 preguntas) cubre el 100% del espacio de probes generables por J6 (limitado a los primeros 1000 chars del Doc D = sección identidad + idioma + trabajo).

**Acción para S3:** Leer `generate_belief_shift_message()` y `score_j5_belief_drift()` en `multi_turn_scorer.py`. Mapear los 6 tipos adversariales del I3 contra los probes reales de J5 antes de diseñar el training data.

---

## Hallazgos Cuantitativos Clave

*(Añadido post-Sesión 2)*

### Segmentación del inventario Q&A por impacto en métricas

| Segmento | Preguntas | Métrica afectada | Budget mínimo | Budget completo |
|---|---|---|---|---|
| **B1+B2+B3+B7** | 38/100 | J6 directo + B2 parcial | ~500 pares | 500 pares |
| **B4+B5+B6+B8+B9** | 62/100 | B2 (persona consistency) | — | 250-500 pares |
| **Total** | 100 | J6 + B2 | **~500** | **750–1.000** |

**Implicación de budget apretado:**

Si el presupuesto de generación/validación es limitado, un **mínimo viable de ~500 pares** (38 preguntas × 6 paráfrasis × 2 contextos = 456, redondeando a 500) permite mover **solo J6** desde 25.0 hacia el target ≥80.

Para mover también **B2** (28.0 → 60–75), se requiere el target completo de 750–1000 pares que cubre las 9 categorías.

### Ratio resultante (consecuencia, no objetivo)

| Budget | Pares Q&A | % del mix total | Métrica principal movida |
|---|---|---|---|
| Mínimo viable | ~500 | ~5.1% | J6 |
| Target S7 | 750 | ~7.5% | J6 + B2 |
| Ceiling S7 | 1.000 | ~9.7% | J6 + B2 (sólido) |

El ratio no es el parámetro de diseño — el número absoluto de pares lo es. *Referencia: arXiv:2502.04194 "SFT outcomes are robust to a wide range of mixture ratios when the absolute number of high-quality examples is sufficient."*

---

### Sesión 6 (I6 — Chat Template Alignment) — ✅ DECISIÓN CERRADA

**Bug central Sprint 6 resuelto.** Diagnóstico confirmado por HuggingFace tokenizer, Google AI Docs, Unsloth.

| Elemento | Valor |
|---|---|
| Bug diagnosticado | Training sin CHANNEL_PREFIX; serving lo inyecta → C3 leakage, J6 pipe −8.2 |
| Loss inicial Sprint 6 | 10.64 = 2.4×10⁻⁵ prob/token (cuasi-entropía uniforme vocab 256k) |
| Loss explicada por | Template mismatch — modelo veía `<\|channel>thought\n<channel\|>` nunca visto en training |
| Fix (Opción C) | CHANNEL_PREFIX en assistant turns antes de apply_chat_template |
| Validación Google | *"add the empty channel to your training prompts"* — Google AI Docs oficial |
| Código cambia | 3 líneas (formatting_prompts_func + response_part) |
| Serving | Sin cambios — template permissivo actual correcto |
| Loss esperada Sprint 7 | 1.5–2.5 step 1 → 0.8–1.5 final |

**Tabla de alertas go/no-go Sprint 7** (supersede alertas de Sesión 5):

| Step | Umbral | Acción |
|---|---|---|
| Step 1 | > 12.0 | 🔴 ABORT |
| Step 10 | > 4.0 | 🟠 REVISAR dataset prep |
| Step 50 | > 5.0 | 🔴 ALERTA masking |
| Step 100 | > 8.0 | 🔴 ABORT |
| Final | 0.8–1.5 | ✅ Saludable |

**Pre-flight obligatorio Sprint 7:**
```bash
python3 scripts/finetuning/verify_sprint7_alignment.py  # 5 checks go/no-go
```

**Corrección Sesión 5:** "loss inicial 12.4–12.6" era incorrecto (= entropía uniforme). Correcto: 1.5–2.5 con masking bien configurado.

---

## Decisiones Arquitectónicas Pendientes

| ID | Decisión | Opciones | Estado | Sesión(es) relevante(s) |
|---|---|---|---|---|
| D1 | Chat template Sprint 7 | C: Opción C — CHANNEL_PREFIX en training labels + response_part actualizado; serving sin cambios | ✅ DECIDIDO — Opción C (Google AI Docs: "add empty channel to training prompts"). | S6 |
| D2 | Multi-turn extraction threshold | A: 60 min (recomendado S1); B: 90 min; C: conversation-level split | ✅ DECIDIDO — 60 min por Chua 2024 + Pleus 2024 | S1 |
| D3 | Base model Sprint 7 | A: Gemma-4-31B; B: Qwen3-30B; C: Gemma-4-27B | ⚠️ PENDIENTE — S8 recomienda Gemma-4-31B pero no hay veredito final | S8 |
| D4 | Rank LoRA (r) | A: r=16 (Sprint 6, subóptimo); B: r=32 (recomendado S4); C: r=64 (QLoRA paper) | ⚠️ PENDIENTE — S4 recomienda r=32 pero no confirmado | S4 |
| **D5** | **Cantidad target persona Q&A** | **A: Mínimo viable ~500 pares (mueve solo J6); B: Target 750-1000 pares (mueve J6 + B2)** | **⏳ PENDIENTE — depende de presupuesto y prioridades de sprint** | **S2** |

**Contexto D5:**
- Opción A (~500 pares): 38 preguntas B1+B2+B3+B7 × 6 paráfrasis × 2 contextos. Foco en J6 (25.0 → ≥80). Coste estimado: ~1.800 llamadas LLM para generación + validación.
- Opción B (750-1.000 pares): 100 preguntas × 6 paráfrasis × 3 contextos. Foco en J6 + B2 (28.0 → 45-55). Coste estimado: ~5.400 llamadas LLM + validación humana ~80 samples.
- Decisión debe tomarse en la integration phase de Sprint 7, una vez confirmados el presupuesto de inference y el target de métricas prioritarias.

---

## Cobertura Research vs. Métricas CCEE

| Métrica CCEE | Gap actual (FT_pipe) | Sesión que la aborda | Status cobertura |
|---|---:|---|---|
| S1 Style Fidelity | +12.1 (ya mejora) | S1 (multi-turn) | ✅ |
| S3 Strategic Alignment | −0.8 | S4 (hyperparams) | ⚠️ Parcial |
| **J6 Q&A Consistency** | **−75.0** 🔴 | **S2 (persona Q&A)** | **✅ Completo** |
| **J5 Belief Drift** | **−32.5** 🔴 | S3 (adversarial) | ⚠️ Matching pendiente |
| B2 Persona Consistency | −5.0 | S2 (persona Q&A) | ✅ Plan definido |
| L Multi-turn | −2.5 | S1 (multi-turn) | ✅ |
| H1 Turing | −6.0 | Implícito en S1+S2 | ⚠️ Sin acción específica |
| K Context | −3.1 | S1 (multi-turn) | ✅ |

---

## Próximos Pasos

| Acción | Responsable | Dependencia |
|---|---|---|
| Verificar `generate_belief_shift_message()` — matching S3 adversarial vs J5 real | S3 review | Ninguna |
| Decidir D5 (target Q&A budget) | Manel | Presupuesto inference Sprint 7 |
| Decidir D3 (base model) | Manel | Benchmark comparativo S8 |
| Decidir D4 (rank LoRA r) | Manel | Post-verificación masking |
| Implementar quality gate S9 antes de training | Sprint 7 | S9 script aprobado |
| **Ejecutar `verify_sprint7_alignment.py` (5 checks go/no-go)** | Sprint 7 | ✅ S6 script listo |
| Integrar CHANNEL_PREFIX en `train_modal.py` (3 líneas — sección E del I6) | Sprint 7 | ✅ S6 config exacta |
