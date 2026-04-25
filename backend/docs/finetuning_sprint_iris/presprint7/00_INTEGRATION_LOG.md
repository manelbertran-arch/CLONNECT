# PRESPRINT 7 — Integration Log

**Maintainer:** Manel Bertran  
**Branch activo:** `review/presprint7-veredicts`  
**Última actualización:** 2026-04-25 (post-Sesión 7 review)

> Este documento integra los hallazgos cross-sesión del Presprint 7 (I1–I9).  
> Registra el status de errores de Sprint 6, patrones emergentes entre sesiones,  
> decisiones arquitectónicas pendientes y cobertura de la investigación vs. CCEE.

---

## Resumen Sesiones Presprint 7

| Sesión | Doc | Tema | Estado | Hallazgo Principal |
|---|---|---|---|---|
| S1 | `01_multi_turn_construction.md` | Dataset multi-turn | ✅ Completado + correcciones | Gemma-4 NO tiene {% generation %} — warning crítico. TurnWise +12.8 pp pero degrada single-turn. |
| **S2** | `02_persona_qa_synthesis.md` | Persona Q&A synthesis | ✅ Completado + 5 correcciones | J6 probes dinámicos vía LLM (n=3, Doc D[:1000]). Target absoluto 750-1000 pares. Alignment tax documentado. |
| S3 | `03_adversarial_examples.md` | Adversarial belief drift | ⚠️ Completado — matching J5 pendiente | FT naked −22.5 J5 por sesgo aprobación en DMs fan→creator. 6 tipos adversariales. |
| S4 | `04_hyperparameters_qlora.md` | Hiperparámetros QLoRA | ✅ Completado + 6 correcciones | Masking roto potencialmente el mayor error Sprint 6. r=32 recomendado, no r=16. |
| **S5** | `05_validation_methodology.md` | Validation + surrogate metrics | ✅ Completado + 5 correcciones | Loss inicial correcta 1–3 (masking OK). Sprint 6 (10.64) = masking roto. Alertas: >5.0 step 50, ABORT >8.0 step 100. |
| S6 | `06_chat_template_gemma4.md` | Chat template Gemma-4 | ✅ | Gemma-4-thinking NO tiene boundary strings estándar → riesgo masking silencioso. |
| **S7/S8** | `08_base_model_evaluation.md` | Gemma-4 vs Qwen3-32B | ✅ + review | 16 modelos evaluados. Qwen3-32B default por TRL auto-patch + catalán explícito. Gate invertido: Gemma4 solo si >+2.0 pp. |
| S9 | `09_dataset_quality_gate.md` | Dataset Quality Gate | ✅ | 8 gates definidos con thresholds y script ejecutable. |

---

## Errores Sprint 6 — Status Consolidado

| # | Error | Severidad | Status | Sesión |
|---|---|---|---|---|
| #1 | **Masking roto** — TRL Issue #3781 | 🔴 CRÍTICO | ⚠️ Verificar. **S7:** Qwen3 TRL auto-patch elimina riesgo. | S1, S4, S7 |
| #2 | **Chat template mismatch** train/serve | 🔴 CRÍTICO | ✅ Plan S6. **S7:** Qwen3 elimina completamente. | S6, S7 |
| #3 | **System prompt heterogéneo** | 🔴 HIGH | ✅ Plan: unificar Doc D v2 | S2, S4 |
| #4 | **System prompt train ≠ prod** | 🔴 HIGH | ✅ Plan: Doc D v2 en todos | S2 |
| #5 | **Sin validation split** | 🟡 MEDIUM | ✅ Plan: 90/10 train/val | S9 |
| #6 | **0% multi-turn** | 🔴 HIGH | ✅ Plan: threshold=60min | S1 |
| #7 | **22 error-string samples** | 🔴 HIGH | ✅ Filtro quality gate | S9 |
| #8 | **0.1% persona Q&A** | 🔴 HIGH | ✅ Target 750-1000 pares Q&A | S2 |
| #9 | **441 media/sticker** | 🟡 MEDIUM | ✅ Filtro response_type | S9 |
| #10 | **1.352 duplicados 14.6%** | 🟡 MEDIUM | ✅ Dedup + keep-1 | S9 |

---

## Patrones Emergentes

### Patrón 1 — Masking silencioso como riesgo sistemático

**Observado en:** S1, S4, S6, S7  
Tres mecanismos independientes comprometen masking sin error visible. **Update S7:** Con Qwen3-32B, TRL auto-patch elimina 2 de 3 riesgos.

### Patrón 2 — Sin matching con probes CCEE

S1-S4 diseñan training data sin verificar probes CCEE. S2 resuelto (J6 matching verificado). S3 pendiente (J5).

### Patrón 5 — Decisión arquitectónica con coste estructural asimétrico (post-S7)

**Observado en:** S6, S7/S8  
Cambiar de modelo no es solo benchmark delta — implica eliminar o crear bug surface. S6 documenta complejidad Gemma4 (Opción C, CHANNEL_PREFIX, verify scripts). S7 evidencia simplicidad Qwen3 (TRL auto-patch, 0 patches). **Implicación:** gates deben ponderar coste estructural, no solo composite delta.

---

## Sprint 7 Architecture: Gemma4 vs Qwen3 (post-S7 review)

| Componente | Si Gemma4 (actual) | Si Qwen3 (alternativa) |
|---|---|---|
| Masking | Opción C manual | Auto-patch TRL |
| Chat template | `<\|turn>model\n<\|channel>thought\n<channel\|>` | `<\|im_start>assistant\n` |
| Tokens nuevos | Sí (`<\|channel>`) | No |
| Patches requeridos | Sí (Sesión 6) | No |
| Bug surface | Alta | Baja |
| Errores S6 eliminados | 0 | #1 (masking) + #2 (template) |

---

## Hallazgos Cuantitativos Clave

### Segmentación inventario Q&A (S2)

| Segmento | Preguntas | Budget mínimo | Budget completo |
|---|---|---|---|
| B1+B2+B3+B7 | 38/100 | ~500 pares | 500 pares |
| B4+B5+B6+B8+B9 | 62/100 | — | 250-500 pares |
| **Total** | 100 | **~500** | **750–1.000** |

### Bug surface Qwen3 vs Gemma4 (S7)

- Qwen3 evita 100% del bug surface de Gemma4 chat template
- Coste evaluación paralela: 1 día / ~$8
- Si Qwen3 >= Gemma4: simplificación masiva de Sprint 7 architecture

---

## Decisiones Arquitectónicas Pendientes

| ID | Decisión | Estado | Sesión |
|---|---|---|---|
| D1 | Chat template Sprint 7 | ⚠️ PENDIENTE. Si Qwen3 → se resuelve auto. | S6, S7 |
| D2 | Multi-turn threshold | ✅ DECIDIDO — 60 min | S1 |
| **D3** | **Base model Sprint 7** | **⚠️ PENDIENTE — evaluación paralela Gemma4 vs Qwen3. Gate invertido: Qwen3 default a menos que Gemma4 > +2.0 pp.** | **S7/S8** |
| D4 | Rank LoRA (r) | ⚠️ PENDIENTE — r=32 recomendado | S4 |
| D5 | Target persona Q&A | ⏳ PENDIENTE — 500 (J6) vs 750-1000 (J6+B2) | S2 |

**Contexto D3 (post-S7 review):**
- 16 modelos evaluados, 29 fuentes citadas
- Argumento técnico: TRL auto-patch Qwen3 (Gemma4 no soportado), chat template simple, elimina Sesión 6 complejidad
- Gate: `Gemma4 - Qwen3 > +2.0 → Gemma4` / `< +2.0 → Qwen3` / `Qwen3 > Gemma4 → Qwen3`
- Pre-flight: verificar catalán Qwen3 con 5-10 prompts antes de CCEE

---

## Cobertura Research vs. Métricas CCEE

| Métrica CCEE | Gap (FT_pipe) | Sesión | Status |
|---|---:|---|---|
| S1 Style Fidelity | +12.1 | S1 | ✅ |
| S3 Strategic Alignment | −0.8 | S4 | ⚠️ Parcial |
| **J6 Q&A Consistency** | **−75.0** 🔴 | **S2** | **✅** |
| **J5 Belief Drift** | **−32.5** 🔴 | S3 | ⚠️ Matching pendiente |
| B2 Persona Consistency | −5.0 | S2 | ✅ |
| L Multi-turn | −2.5 | S1 | ✅ |
| H1 Turing | −6.0 | S1+S2 | ⚠️ Sin acción |
| K Context | −3.1 | S1 | ✅ |

---

## Próximos Pasos

| Acción | Responsable | Dependencia |
|---|---|---|
| Verificar `generate_belief_shift_message()` matching S3 vs J5 | S3 review | Ninguna |
| **D3: Pre-flight catalán Qwen3 (5-10 prompts)** | **Sprint 7 FASE 1** | **Config adaptado** |
| **D3: Evaluación paralela Gemma4 vs Qwen3** | **Sprint 7 FASE 1/1B** | **Pre-flight OK** |
| Decidir D5 (target Q&A budget) | Manel | Presupuesto inference |
| Decidir D4 (rank LoRA r) | Manel | Post-verificación masking |
| Implementar quality gate S9 | Sprint 7 | Script aprobado |
