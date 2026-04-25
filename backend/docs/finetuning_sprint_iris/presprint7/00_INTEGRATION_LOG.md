# PRESPRINT 7 — Integration Log

**Maintainer:** Manel Bertran  
**Branch activo:** `review/presprint7-veredicts`  
**Última actualización:** 2026-04-25 (post-Sesión 4+6 correcciones)

> Este documento integra los hallazgos cross-sesión del Presprint 7 (I1–I9).  
> Registra el status de errores de Sprint 6, patrones emergentes entre sesiones,  
> decisiones arquitectónicas pendientes y cobertura de la investigación vs. CCEE.
>
> **Regla para workers:** Leer este log ANTES de generar cualquier documento de sesión. Aplicar a sesiones 5–11.

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
| **S9** | `09_dataset_quality_gate.md` | Dataset Quality Gate | ✅ **post double-check: thresholds reconciliados** | 8 gates/26 criterios. G1.2: 750 pares OR 7.5% (no 10%). G1.3: WARNING v1 (no BLOCKER). Coherencia heurística documentada. Empírica: detecta 7 blockers Sprint 6. |

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
| **#11** | **Cero adversariales** — 0 ejemplos donde Iris mantiene posición bajo presión en los 9,272 DMs de training | Dataset | 🔴 HIGH | ✅ Plan completo con matching CCEE y reasignación de tipos. TYPE-8 Topic Pivot prioridad #1 para J5. | **S3** |

---

## Sprint 7 Architecture Consolidada (estado post-Sesiones 1–4)

| Componente | Decisión | Origen | Estado |
|---|---|---|---|
| Modelo base | Gemma4-31B dense (sujeto a revisión I8) | Sprint 6 | ⏳ Pendiente I8 |
| Arquitectura de training | **SFT-only** | Sesión 4 (I4) | ✅ DECIDIDO |
| Masking | CHANNEL_PREFIX en training labels (Opción C per I6) | Sesión 1 (I1) + I6 | ✅ DECIDIDO |
| LoRA rank | r=16, con sweep validation proactivo pre-full training | Sesión 4 (I4) | ✅ DEFAULT |
| LoRA alpha | α=32 (heurística Lightning AI/Unsloth — NO QLoRA canon) | Sesión 4 (I4) | ✅ DEFAULT |
| Learning rate | 2e-4, cosine scheduler, warmup_ratio=0.05 | Sesión 4 (I4) | ✅ DECIDIDO |
| Epochs | 1–3 según dataset; curriculum Q&A: epoch 1 todos, +1 selectivo Q&A si B2 no converge | Sesión 4 (I4) | ✅ DEFAULT |
| Forbidden flags | `use_liger_kernel`, `packing=True`, `IterableDataset` | Sesión 1 (I1) | ✅ BLOQUEADO |
| Dataset multi-turn | 1,600–2,400 conversaciones reales | Sesión 1 (I1) | ✅ TARGET |
| Dataset persona Q&A | 750–1,000 pares (38 preguntas core + 62 extras; 6 paráfrasis c/u) | Sesión 2 (I2) | ✅ TARGET |
| Dataset adversarial | 200–300 ejemplos (TYPE-8 priority para J5) | Sesión 3 (I3) | ✅ TARGET |
| DPO | **Diferido a Sprint 8** | Sesión 4 (I4) | ✅ DIFERIDO |
| Pre-flight check | `verify_sprint7_alignment.py` (5 checks go/no-go — bloqueante) | I6 + I4 | ✅ OBLIGATORIO |
| **Pre-flight dataset** | **`09_dataset_quality_gate.py` (26 criterios PASS/FAIL — bloqueante si cualquier BLOCKER falla)** | **I9** | **✅ OBLIGATORIO — ANTES de `verify_sprint7_alignment.py`** |
| Sweep | 3 configs proactivo × 50% steps sobre validation set antes del full training | Sesión 4 (I4) | ✅ PROTOCOLO |

---

## Patrones Emergentes

### Patrón 1 — DPO architecture decision — ✅ RESUELTO (Sesión 4)

**Observado en:** S1, S2, S3, S4  
**Descripción:** Todas las sesiones convergen hacia DPO/preference-tuning como necesario para al menos un componente del dataset, pero la decisión formal de cuándo activarlo requiere coordinación cross-sesión que no está completa.

| Sesión | Referencia DPO | Estado |
|--------|---------------|--------|
| S1 (I1) | TurnWise (2026): "SFT multi-turn degrada single-turn; preference-tuning no" | Paper recomienda DPO para multi-turn |
| S2 (I2) | Offline RL (Shea & Yu, 2023); datasets en formato compatible con DPO | Compatible |
| S3 (I3) v2 | **OPCIÓN A (SFT-only) / OPCIÓN B (SFT+DPO)** — decisión diferida correctamente a I4/I5 | ✅ Correcto |
| S4 (I4) | Define condición activación DPO y hyperparams, pero sin coordinar con datasets S2/S3 | Hyperparams OK, **coordinación cross-sesión pendiente** |

**Estado actual:** S3 correctamente declara OPCIÓN A/B sin decidir. S4 define hyperparams DPO pero hace la decisión sin coordinar con los datasets de pares de S2/S3. **S4 sigue sin abordar la coordinación cross-sesión — pendiente corrección.**

**Acción requerida en S5 (I5+I7):** La validation framework DEBE contemplar OPCIÓN A (SFT-only) y OPCIÓN B (SFT+DPO). Diseñar experimento de comparación A vs B antes del sprint. Considerar surrogate metrics que correlacionen con J5 específicamente (no solo composite).
**✅ RESOLUCIÓN (Sesión 4 corregida):** DPO explícitamente diferido a Sprint 8. Sprint 7 = SFT-only. Sprint 8 = SFT+DPO una vez composite naked ≥ 74 validado. Dataset I2/I3 (pares chosen/rejected) como prerequisito. Hiperparámetros DPO: LR=5e-6, β=0.1, epochs 1-2.


---

### Patrón 2 — Masking silencioso como vector de riesgo sistemático

**Observado en:** S1, S4, S6  
**Descripción:** Tres mecanismos independientes pueden comprometer silenciosamente el masking de training sin producir error visible: (1) TRL Issue #3781 (liger + assistant_only_loss), (2) chat template mismatch train/serve, (3) boundary strings incorrectos para el modelo target.  
**Riesgo:** Sprint 7 podría repetir Sprint 6 si no se verifican explícitamente los `assistant_masks` en los primeros batches.  
**Mitigation:** S4 recomienda inspección mandatory de `assistant_masks` en ≥3 ejemplos pre-training como gate go/no-go.

---

### Patrón 3 — Sesiones sin cross-checking — ✅ RESUELTO (Sesión 4)

**Observación:** Las versiones iniciales de los documentos de sesión (I4 en particular) contenían inconsistencias con Sesión 1 (ignorando el masking roto) y atribuciones incorrectas (QLoRA alpha=2r presentado como canon cuando QLoRA usa alpha=16 constante).

**Resolución:** Correcciones post-review al final de Sesión 4 han alineado los documentos. Inconsistencias identificadas y corregidas:
1. Atribución alpha=2r al QLoRA paper → corregido: heurística Lightning AI/Unsloth posterior
2. Fallo de masking omitido del contexto de hiperparámetros → corregido: sección "DOS Fallos" añadida
3. Ausencia de sección DPO → corregido: §F con decisión explícita y condición de activación Sprint 8
4. Sweep reactivo ("si composite <69") → corregido: §H sweep proactivo pre-full training
5. Cita r=16 para style sin marca de interpretación → corregido: ⚠️ marcado como interpretación
6. Epochs fijo en 1 sin justificación → corregido: rango 1–3 con tabla por escenario de dataset

**Lección:** Workers deben leer el integration log ANTES de generar su documento. Aplicar a sesiones 5–11: incluir en el prompt de cada sesión la lectura de este log como primer paso.

---

### Patrón 5 — Thresholds presentados como derivados de papers cuando son heurísticas

**Observado en:** S9 (post double-check)  
**Descripción:** I9 presentó thresholds de Distinct-1 (0.20), Distinct-2 (0.40), Self-BLEU-4 (0.65), coherencia (85%), N≥2,000 como "justificados por papers" cuando los papers solo definen las **métricas**, no los thresholds. Los thresholds son heurísticas empíricas calibradas sobre el dataset de Sprint 6.  
**Corrección aplicada:** I9 v2 añade explícitamente "heurística empírica, no derivada literalmente del paper" a cada threshold de Gate 3 y Gate 8.  
**Lección:** Distinguir siempre: (a) papers que definen métricas vs (b) papers que justifican valores específicos. Solo (b) son citas legítimas de threshold. En ausencia de (b), marcar como heurística calibrada.  
**Patrón anterior (S4, S5):** Números sin fuente trazable. Pattern now extends to "fuente correcta, valor no derivado de ella".

---

### Patrón 4 — Sin matching con probes CCEE ✅ RESUELTO COMPLETO

**Descripción:** Las sesiones de investigación diseñaban training data para mejorar métricas CCEE sin verificar cómo CCEE genera concretamente los probes. Riesgo: invertir en data que no activa los probes reales.

**Status por sesión y métrica:**

| Sesión | Métrica objetivo | Matching con implementación CCEE | Status |
|---|---|---|---|
| S1 (multi-turn) | J2, L, K | Parcial — multi-turn genera conversaciones pero no se analizó cómo score_j2 evalúa | ⚠️ Pendiente |
| **S2 (persona Q&A)** | **J6, B2** | **✅ RESUELTO** — `generate_qa_probes()` verificado en `multi_turn_generator.py` | **✅ Resuelto** |
| **S3 (adversarial)** | **J5** | **✅ RESUELTO** — TYPE-8 Topic Pivot mapeado a `generate_belief_shift_message()` (msgs 15-40 chars, topic shifts). TYPE-2/3/5 reasignados a G5 (FT ya 80.0) | **✅ Resuelto** |
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

**Detalle matching J5 (S3 — resuelto al leer código):**

`generate_belief_shift_message()` en `core/evaluation/multi_turn_generator.py` genera mensajes 15-40 chars: "Pero eso no es lo que dijiste antes", "Oye cambiando de tema...", "En realidad he oído que eso no funciona". J5 evalúa si el modelo acknowledges el shift y permanece en personaje. **No mide resistencia a jailbreaks elaborados** — eso es G5.

| Tipo adversarial | J5-relevante | G5-relevante |
|-----------------|:-----------:|:-----------:|
| TYPE-8 Topic Pivot (NUEVO) | ✅ Alta | ❌ |
| TYPE-1 Bare Assertion | ✅ Alta | ✅ Media |
| TYPE-6 False Premise | ✅ Alta | ✅ Media |
| TYPE-2/3/5 (Identity/Emotional/Authority) | ❌ | ✅ Alta — G5 FT ya 80.0 |

**Lección codificada:** workers DEBEN leer el código CCEE real antes de proponer taxonomías de datos sintéticos.

---

## Hallazgos Cuantitativos Clave

*(Actualizado post-Sesión 3)*

### Hallazgos J5 (Sesión 3)

- **TYPE-8 Topic Pivot** es el tipo adversarial MÁS relevante para J5. Descubierto leyendo `generate_belief_shift_message()`. Sin este tipo, los adversariales v1 impactarían G5 (ya 80.0) con mínimo efecto en J5.
- **TYPE-2/3/5** (Identity, Emotional, Authority) mueven G5 — G5 FT naked ya 80.0. Sobre-cobertura.
- **Sprint 7 debe priorizar TYPE-8 + TYPE-1 + TYPE-7** para J5 (en ese orden).
- Los **probes J5 son cortos (15-40 chars)**, topic shifts y contradicciones en-contexto.
- **Punto de partida 200-300 adversariales.** Si J5 no mueve +5pp, incrementar a 600-1000.

*(Sección Q&A añadida post-Sesión 2)*

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


### Sesión 4 (I4 — Hyperparameters)

- **Sprint 7 architecture: SFT-only** (DPO diferido Sprint 8)
- Hiperparámetros: r=16, α=32, LR=2e-4, 1–3 epochs, cosine, warmup=0.05
- Único cambio vs Sprint 6: warmup_ratio 0.03→0.05
- Pre-flight bloqueante: verificar masking + `verify_sprint7_alignment.py`
- Curriculum: Q&A 1 epoch; +1 epoch selectivo Q&A si B2 no converge
- **DOS fallos simultáneos Sprint 6:** dataset ruidoso + masking roto → gap 12–19 pts no atribuible a ninguna causa singular
- alpha=2r es heurística Lightning AI/Unsloth, NO del QLoRA canónico (que usa alpha=16 constante)

---

## Decisiones Arquitectónicas Pendientes

| ID | Decisión | Opciones | Estado | Sesión(es) relevante(s) |
|---|---|---|---|---|
| **D1 (SFT/DPO)** | **SFT vs DPO — Sprint 7 SFT-only, Sprint 8 SFT+DPO** | **✅ RESUELTA (Sesión 4)** | **S4** |
| **D2 (r y α)** | **Rank r=16/α=32 default + sweep proactivo 3 configs** | **✅ PARCIALMENTE (Sesión 4)** | **S4** |
| D3 | Modelo base — Gemma-4-31B | ⏳ Pendiente Sesión 8 (I8) | S8 |
| D4 | Cantidad target dataset | ⚠️ Refinada por S1+S2+S3 | S1-S3 |
| D1 | Chat template Sprint 7 | C: Opción C — CHANNEL_PREFIX en training labels + response_part actualizado; serving sin cambios | ✅ DECIDIDO — Opción C (Google AI Docs: "add empty channel to training prompts"). | S6 |
| D2 | Multi-turn extraction threshold | A: 60 min (recomendado S1); B: 90 min; C: conversation-level split | ✅ DECIDIDO — 60 min por Chua 2024 + Pleus 2024 | S1 |
| D3 | Base model Sprint 7 | A: Gemma-4-31B; B: Qwen3-30B; C: Gemma-4-27B | ⚠️ PENDIENTE — S8 recomienda Gemma-4-31B pero no hay veredito final | S8 |
| D4 | Rank LoRA (r) | A: r=16 (Sprint 6, subóptimo); B: r=32 (recomendado S4); C: r=64 (QLoRA paper) | ⚠️ PENDIENTE — S4 recomienda r=32 pero no confirmado | S4 |
| D5 | Q&A target | 750-1,000 pares (38 preguntas core + 62 extras) | ✅ RESUELTA (Sesión 2) | S2 |
| D6 | Adversarial target | 200-300 ejemplos | ✅ RESUELTA (Sesión 3) | S3 |
| D7 | Reasignación tipos adversariales | TYPE-8 priority para J5 | ✅ RESUELTA (Sesión 3) | S3 |
| **D8** | **Curriculum learning persona Q&A** | **NUEVA: Epoch 1 todos + Epoch 2 selectivo Q&A si B2 no converge** | **✅ ACEPTADA, pendiente confirmación S2** | S4 |
| **D6** | **Cantidad target adversarial** | **Punto de partida: 200-300. Escalar a 600-1000 si J5 ≤ +5pp.** | **⚠️ Empírica iterativa post-CCEE** | **S3** |
| **D7** | **Reasignación tipos adversariales** | **TYPE-8 #1, TYPE-1 #2, TYPE-7 #3 para J5. TYPE-2/3/5 reducidos.** | **⚠️ Pendiente ajuste post-CCEE primera ronda** | **S3** |
| **D10** | **Thresholds GATE reconciliados con I2/I3** | G1.2: 750 OR 7.5% (no 10%); G1.3: 200 OR 2% WARNING v1 (no 5% BLOCKER). Coherente con I2 (target absoluto 750 pares) e I3 (200-300 punto de partida). | ✅ RESUELTO — post double-check S9 | S9 |

**Contexto D6:** 200-300 punto de partida (TYPE-8 30%, TYPE-1 30%, TYPE-7 15%, TYPE-6 15%). Si J5 no mueve +5pp: incrementar a 600-1000. El número correcto lo determina CCEE, no la literatura.

**Contexto D7:** TYPE-8 = modela probes CCEE directamente (`generate_belief_shift_message()`, 15-40 chars). TYPE-2/3/5 son G5-territory (FT naked G5=80.0, no urgente). Ajustar tras primera ronda CCEE.

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
| **J5 Belief Drift** | **−32.5** 🔴 | S3 (adversarial) | ✅ Plan + matching CCEE verificado (TYPE-8 prioritario) |
| B2 Persona Consistency | −5.0 | S2 (persona Q&A) | ✅ Plan definido |
| L Multi-turn | −2.5 | S1 (multi-turn) | ✅ |
| H1 Turing | −6.0 | Implícito en S1+S2 | ⚠️ Sin acción específica |
| K Context | −3.1 | S1 (multi-turn) | ✅ |

---

## Próximas Sesiones Esperadas

| Sesión | Doc | Tema | Notas clave |
|--------|-----|------|-------------|
| **S5** | **I5+I7** | **Validation framework + dataset audit** | **Debe contemplar OPCIÓN A (SFT-only) y OPCIÓN B (SFT+DPO). Surrogate metrics J5-específicas (no solo composite). Verificar compatibilidad volúmenes I1+I2+I3.** |
| S6 | I6 | Chat template Gemma-4 | Confirmar que fix resuelve mismatch `<\|turn>model\n` vs `<\|channel>thought\n`. |
| S7 | Integration | Cierre decisiones D3/D5/D6/D7, OPCIÓN A vs B | Sesión de coordinación Manel + AI antes del sprint. |

---

## Hallazgos Cuantitativos Clave — Sesión 9 (Dataset Quality Gate)

*(Añadido post double-check I9)*

**Validación empírica del gate contra Sprint 6 dataset (`sft_combined_audited.jsonl`, N=9,272):**

| Gate | Criterio | Sprint 6 resultado | Veredicto |
|---|---|---|---|
| G1.1 | multi-turn ≥15% | 0.0% | ❌ BLOCKER |
| G1.2 | persona Q&A ≥750 OR ≥7.5% | 0.9% (83 pares) | ❌ BLOCKER |
| G1.3 | adversarial ≥200 OR ≥2% (WARNING v1) | 0.0% | ⚠️ WARN |
| G2.1 | error strings = 0 | 22 | ❌ BLOCKER |
| G2.2 | solo-artifact = 0 | 27 | ❌ BLOCKER |
| G2.3 | artifacts <2% | 4.3% | ❌ BLOCKER |
| G6.2 | PII = 0 | 19 | ❌ BLOCKER |
| **Total** | | | **❌ FAIL (6 blockers)** |

**Implicación:** Si este gate hubiera existido antes de Sprint 6, el training **no habría arrancado**. El gate es condición necesaria, no suficiente — no garantiza que el dataset sea bueno, pero garantiza que los errores de Sprint 6 no se repitan.

**Pre-flight Sprint 7 — Secuencia obligatoria:**
```bash
# Step 1: Dataset quality gate (antes de cualquier otra cosa)
python3 scripts/finetuning/09_dataset_quality_gate.py \
    --input data/dpo/trl/sft_sprint7.jsonl \
    --eval-set data/eval/ccee_questions.jsonl \
    --report-out docs/finetuning_sprint_iris/presprint7/gate_report_pre_training.md
# Si exit 1 → NO proceder. Iterar dataset.

# Step 2: Alineación config (post gate PASS)
python3 scripts/finetuning/verify_sprint7_alignment.py
```

---

## Próximos Pasos

| Acción | Responsable | Dependencia |
|---|---|---|
| ~~Verificar `generate_belief_shift_message()` — matching S3 vs J5~~ | ~~S3 review~~ | ✅ COMPLETADO en S3 v2 |
| Decidir D5 (target Q&A budget) | Manel | Presupuesto inference Sprint 7 |
| Decidir D3 (base model) | Manel | Benchmark comparativo S8 |
| Decidir D4 (rank LoRA r) | Manel | Post-verificación masking |
| Implementar quality gate S9 antes de training | Sprint 7 | S9 script aprobado |
| Decidir OPCIÓN A vs B (SFT vs SFT+DPO) | Manel + S5 | Validation framework S5 |
| Ajustar D7 (tipos adversariales) post-CCEE primera ronda | Manel | CCEE run post-FT |
| **Ejecutar `verify_sprint7_alignment.py` (5 checks go/no-go)** | Sprint 7 | ✅ S6 script listo |
| Integrar CHANNEL_PREFIX en `train_modal.py` (3 líneas — sección E del I6) | Sprint 7 | ✅ S6 config exacta |
