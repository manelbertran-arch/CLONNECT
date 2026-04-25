# NOTES — Sprint 7 Execution Plan Derivation

**Generado:** 2026-04-25  
**Branch:** `planning/sprint7-execution`  
**Fuentes leídas:** 16 documentos (9 research + 1 audit + 1 fix + 1 baseline + 6 reviews) + 3 scripts verificados  
**Fase:** A (lectura completa) + B (cross-reference validation)

> Documento de trabajo interno. Contiene las 10 tablas estructuradas extraídas
> de las fuentes del Presprint 7 para derivar SPRINT7_EXECUTION_PLAN.md.

---

## Tabla 1 — Decisiones Arquitectónicas (D1–D11)

| ID | Decisión | Estado | Fuente Primaria | Fuente Review | Notas |
|---|---|---|---|---|---|
| D1 | Chat template: Opción C (CHANNEL_PREFIX en training + serving) | ✅ CONFIRMED | S6 `06_chat_template_gemma4.md` | `06_REVIEW.md` | `response_part="<\|turn>model\n<\|channel>thought\n<channel\|>"` — Google docs validan Opción C |
| D2 | Multi-turn threshold: 60 min, burst merge 5 min | ✅ CONFIRMED | S1 `01_multi_turn_construction.md` | `01_REVIEW.md` | Target 1600–2400 conversaciones, 70/30 real/synthetic |
| D3 | Base model: Gemma-4-31B-it | ✅ CONFIRMED (user override) | S8 `08_base_model_evaluation.md` | — | S8 recomendaba Qwen3-32B, usuario confirma Gemma-4 (2026-04-25) |
| D4 | LoRA rank: r=16 default, sweep proactivo r=8/16/32 | ✅ CONFIRMED | S4 `04_hyperparameters_qlora.md` | `04_REVIEW.md` | alpha=2r es heurística, no canon QLoRA |
| D5 | Target persona Q&A: 750–1000 pares | ✅ CONFIRMED | S2 `02_persona_qa_synthesis.md` | `02_REVIEW.md` | 100 preguntas en 9 categorías (B1–B9), J6 probes dinámicos |
| D6 | Target adversarial: 200–300 ejemplos | ✅ CONFIRMED | S3 `03_adversarial_examples.md` | `03_REVIEW.md` | 8 attack types, TYPE-8 nuevo |
| D7 | Tipos adversariales: TYPE-8 J5-crítico, TYPE-2/3/5 G5-territory | ✅ CONFIRMED | S3 `03_adversarial_examples.md` | `03_REVIEW.md` | J5-crítico: TYPE-1 (30%) + TYPE-8 (20%) + TYPE-6 (15%) |
| D8 | Curriculum learning: Phase 1 todos, Phase 2 Q&A selectivo si B2 no converge | ✅ ACCEPTED | S4 `04_hyperparameters_qlora.md` | `04_REVIEW.md` | `curriculum_phase_steps=150` para callback |
| D9 | DPO diferido a Sprint 8 (Sprint 7 = SFT-only) | ✅ CONFIRMED | S4 `04_hyperparameters_qlora.md` | `04_REVIEW.md` | — |
| D10 | Gate thresholds: absoluto OR ratio (reconciliado S2+S3) | ✅ CONFIRMED | S9 `09_dataset_quality_gate.md` | `05_REVIEW.md` | G1.2: ≥750 OR ≥7.5%, G1.3: ≥200 OR ≥2% |
| D11 | Doc D Versioning Protocol: freeze antes de medición | 🔴 URGENT | S11 `11_baseline_remeasure.md` | — | Full doc_d cambió 4% (36803c→35311c), compressed 50% (1576c→2360c) |

---

## Tabla 2 — Configuración Hiperparámetros Sprint 7

**Fuente:** S4 `04_hyperparameters_qlora.md` + `04_REVIEW.md` + `scripts/finetuning/02_sft_config.py` + `scripts/finetuning/train_modal.py`

| Parámetro | Valor Sprint 7 | Fuente | Notas |
|---|---|---|---|
| `r` (LoRA rank) | 16 (default), sweep {8, 16, 32} | S4, 04_REVIEW | Sweep proactivo 3 configs × 50% steps |
| `lora_alpha` | 32 (= 2r) | S4, 04_REVIEW | Heurística, no canon QLoRA [04_REVIEW corrección] |
| `lora_dropout` | 0.05 | S4, `02_sft_config.py:45` | Anti-overfit |
| `learning_rate` | 2e-4 | S4, `02_sft_config.py:120` | Unsloth default para Gemma 4 |
| `num_train_epochs` | 1 | S4, `02_sft_config.py:119` | Overfit risk con >1 en dataset estilístico |
| `warmup_ratio` | **0.05** | **S4 04_REVIEW** | ⚠️ INCONSISTENCIA: script tiene 0.03, S4 review dice 0.05 → review prevails |
| `per_device_train_batch_size` | 2 | `02_sft_config.py:113` | — |
| `gradient_accumulation_steps` | 4 | `02_sft_config.py:114` | Effective batch = 8 |
| `lr_scheduler_type` | cosine | `02_sft_config.py:121` | — |
| `optim` | adamw_8bit | `02_sft_config.py:124` | — |
| `weight_decay` | 0.01 | `02_sft_config.py:125` | — |
| `max_grad_norm` | 0.3 | `02_sft_config.py:126` | — |
| `max_seq_length` | 2048 | `02_sft_config.py:21` | Mensajes Iris cortos |
| `seed` | 3407 | `02_sft_config.py:139` | — |
| `save_steps` | 200 | `train_modal.py:117` | Modal version (Kaggle version: 500) |
| `response_part` | **`"<\|turn>model\n<\|channel>thought\n<channel\|>"`** | **S6, 06_REVIEW** | ⚠️ CRITICAL: scripts still have Sprint 6 value `"<\|turn>model\n"` → MUST UPDATE |
| `instruction_part` | `"<\|turn>user\n"` | S6, `02_sft_config.py:152` | — |
| `eval_dataset` | **90/5/5 split** | **S5 05_REVIEW** | ⚠️ Scripts have `None` → MUST ADD validation split |
| `eval_steps` | 100 | S5 `05_validation_methodology.md` | — |

### Sweep proactivo — 3 configuraciones [S4]

| Config | r | LR | Epochs | Steps | Coste est. |
|---|---|---|---|---|---|
| A (default) | 16 | 2e-4 | 1 | 100% | ~$3 |
| B (conservative) | 32 | 1e-4 | 2 | 50% | ~$3 |
| C (light) | 8 | 2e-4 | 3 | 50% | ~$1.5 |

---

## Tabla 3 — Gate Thresholds (Script Verificado)

**Fuente:** S9 `09_dataset_quality_gate.md` + `scripts/finetuning/09_dataset_quality_gate.py` (verificado)

| Gate | Criterio | Threshold | Severidad | Script Línea | Verificado |
|---|---|---|---|---|---|
| G1.1 | multi-turn ≥15% | 0.15 | BLOCKER | :391 | ✅ |
| G1.2 | persona Q&A ≥750 OR ≥7.5% | 750 / 0.075 | BLOCKER | :384 | ✅ [D10] |
| G1.3 | adversarial ≥200 OR ≥2% | 200 / 0.02 | WARNING | :387 | ✅ [D10] |
| G1.4 | DM single-turn ≤75% | 0.75 | WARNING | :394 | ✅ |
| G2.1 | error strings = 0 | 0 | BLOCKER | :440 | ✅ |
| G2.2 | solo-artifact = 0 | 0 | BLOCKER | :441 | ✅ |
| G2.3 | artifacts explícitos <2% | 0.02 | BLOCKER | :442 | ✅ |
| G2.4 | duplicados exactos <5% | 0.05 | WARNING | :443 | ✅ |
| G2.5 | respuestas <10chars <5% | 0.05 | WARNING | :444 | ✅ |
| G3.1 | Distinct-1 ≥0.20 | 0.20 | WARNING | :465 | ✅ |
| G3.2 | Distinct-2 ≥0.40 | 0.40 | WARNING | :466 | ✅ |
| G3.3 | Self-BLEU-4 ≤0.65 | 0.65 | WARNING | :467 | ✅ |
| G4.1 | categorías persona ≥5/6 | 5 | WARNING | :485 | ✅ |
| G4.2 | idioma ca+es ≥35% | 0.35 | WARNING | :486 | ✅ |
| G5.1 | coherencia ≥85% (heurística) | 0.85 | WARNING | :509 | ✅ |
| G6.1 | overlap CCEE eval = 0 | 0 | BLOCKER | :556 | ✅ (requiere --eval-set) |
| G6.2 | PII en assistant = 0 | 0 | BLOCKER | :525 | ✅ (soporta --pii-whitelist) |
| G8.1 | N mínimo ≥2,000 | 2000 | BLOCKER | :576 | ✅ |
| G8.2 | N máximo ≤30,000 | 30000 | WARNING | :577 | ✅ |
| G8.3 | P99 tokens ≤2,048 | 2048 | WARNING | :578 | ✅ |
| G8.4 | >1500 tokens <10% | 0.10 | WARNING | :579 | ✅ |

**Nota:** G6.1 requiere `--eval-set` y usa MD5 hash de `user_content` para detección de overlap. Post-A1 (Pattern 8), se recomienda response-side verification adicional para futuras auditorías, pero el script actual no lo implementa.

---

## Tabla 4 — Flags Prohibidos y Bugs TRL

**Fuente:** S1 `01_multi_turn_construction.md` Sección H + `01_REVIEW.md`

| Flag / Bug | TRL Issue | Efecto | Fuente |
|---|---|---|---|
| `liger_kernel=True` | #3781 | Corrompe loss computation → lecturas falsas | S1 Sección H, 01_REVIEW |
| `packing=True` | #3728 | Cross-contamination entre samples, masking roto | S1 Sección H |
| `dataset_kwargs={"stream": True}` | #3768 | IterableDataset pierde shuffle → orden determinístico | S1 Sección H |
| `max_length` (param name wrong) | #3927 | Silently truncates, confunde con `max_seq_length` | S1 Sección H |

### Config segura Sprint 7 [S1, 01_REVIEW]
```python
SFTConfig(
    packing=False,           # OBLIGATORIO — #3728
    dataset_text_field="text",
    # NO liger_kernel        — #3781
    # NO max_length           — #3927 (usar max_seq_length)
    # NO dataset_kwargs stream — #3768
)
```

---

## Tabla 5 — Loss Alerts

**Fuente:** S5 `05_validation_methodology.md` + `05_REVIEW.md`

| Step | Rango Esperado | ALERTA si | ABORT si | Fuente |
|---|---|---|---|---|
| Step 1 | 1.0–3.0 | — | > 12.0 | S5 |
| Step 10 | 1.5–2.5 | > 4.0 | — | S5 |
| Step 50 | 1.0–2.0 | > 5.0 | — | S5 |
| Step 100 | 0.8–1.8 | — | > 8.0 | S5 |
| Final | 0.5–1.5 | — | — | S5 |
| Cualquier step | — | — | > 12.0 | S5 |
| Final | — | < 0.2 (overfitting) | — | `02_sft_config.py:175` |

**Referencia Sprint 6:** Loss = 10.64 → masking roto (S5, 05_REVIEW confirmó que 1.5–2.5 es correcto con masking funcional).

### SFTDivergenceCallback [S5]
```python
class SFTDivergenceCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        loss = logs.get("loss")
        if loss and loss > 12.0:
            control.should_training_stop = True  # ABORT
        if state.global_step == 50 and loss and loss > 5.0:
            print(f"ALERTA: loss {loss} > 5.0 at step 50")
        if state.global_step == 100 and loss and loss > 8.0:
            control.should_training_stop = True  # ABORT
```

---

## Tabla 6 — Errores Sprint 6 + Mitigaciones Sprint 7

**Fuente:** `00_INTEGRATION_LOG.md` Sección "Errores Sprint 6"

| # | Error | Sev. | Mitigación Sprint 7 | Fuente | Verificado en Script |
|---|---|---|---|---|---|
| 1 | Masking roto (TRL #3781) | 🔴 | `response_part` con CHANNEL_PREFIX [D1] | S1, S4, S7 | ⚠️ Scripts aún tienen Sprint 6 value |
| 2 | Chat template mismatch train/serve | 🔴 | Opción C: CHANNEL_PREFIX en ambos [D1] | S6, S7 | ⚠️ Scripts NO actualizados |
| 3 | System prompt heterogéneo | 🔴 | Unificar Doc D v2 en todos los samples | S2, S4 | N/A (dataset prep) |
| 4 | System prompt train ≠ prod | 🔴 | Doc D v2 idéntico en training y producción | S2 | N/A (dataset prep) |
| 5 | Sin validation split | 🟡 | 90/5/5 train/val/test split [S5] | S9 | ⚠️ Scripts tienen `eval_dataset=None` |
| 6 | 0% multi-turn | 🔴 | Threshold 60 min, target ≥15% [D2, G1.1] | S1 | N/A (dataset prep) |
| 7 | 22 error-string samples | 🔴 | Quality gate G2.1: error strings = 0 | S9 | ✅ `09_dataset_quality_gate.py:440` |
| 8 | 0.1% persona Q&A | 🔴 | Target 750–1000 pares [D5, G1.2] | S2 | ✅ `09_dataset_quality_gate.py:384` |
| 9 | 441 media/sticker | 🟡 | Quality gate G2.2+G2.3 | S9 | ✅ `09_dataset_quality_gate.py:441-442` |
| 10 | 1352 duplicados 14.6% | 🟡 | Dedup + keep-1, gate G2.4 <5% | S9 | ✅ `09_dataset_quality_gate.py:443` |
| 11 | 0 adversarial examples | 🔴 | Target 200–300 [D6, G1.3] | S3 | ✅ `09_dataset_quality_gate.py:387` |

---

## Tabla 7 — Hallazgos A1 (Auditoría Semántica)

**Fuente:** `A1_dataset_semantic_audit.md`

| Hallazgo | Valor | Impacto | Acción Sprint 7 |
|---|---|---|---|
| Total samples | 9,272 | Base del dataset | — |
| CCEE contamination | **REFUTED** (0/16 share turn) | Score impact ≤1 punto | No acción requerida |
| Duplicados | 14.3% (1,323 records) | Sesgo repetición | Dedup en pipeline, gate G2.4 |
| Error strings | 22 | Training en error responses | Filtro, gate G2.1 |
| Non-text (media/sticker) | 818 | Training en placeholders | Filtro, gate G2.2 |
| PII detections | 162 | Privacy risk | Filtro, gate G6.2 + `--pii-whitelist @iris_bertran` |
| System prompt gap | 0% WhatsApp / 100% IG | Inconsistencia doc_d | Unificar Doc D v2 [Error #3] |
| Voice patterns | cuca 3.7%, baby 2.8%, reina 1.8% | Style signal | Preservar (no filtrar) |

### Pattern 8 — Threshold Similarity [A1]
Cosine similarity > 0.85 con MiniLM produce 33% false positives en texto corto CA/ES coloquial. Para futuras auditorías: ≥ 0.92 + response-side verification.

---

## Tabla 8 — Baseline Measurements (Sprint 7 Comparison Base)

**Fuente:** S11 `11_baseline_remeasure.md` (branch `measurement/baseline-doc-d-aligned`)

| Condición | Composite v5 | Commit/Config | Notas |
|---|---|---|---|
| **BL_pipeline c0bcbd73** | **67.7** | c0bcbd73 | **Sprint 7 comparison baseline** |
| BL_naked v2 | 60.4 | — | Sin pipeline (modelo base raw) |
| FT_pipeline | 66.4 | — | Sprint 6 fine-tuned con pipeline |
| FT_naked | 66.1 | — | Sprint 6 fine-tuned sin pipeline |
| Doc D drift confound | −1.8 pts | — | Moderate, not critical |

**Sprint 7 target:** composite ≥ 74 (Δ > +5 vs BL_pipeline 67.7)

### D11 — Doc D Versioning Protocol [S11]
- Full doc_d cambió 4% (36803c → 35311c) — confound menor
- Compressed doc_d cambió 50% (1576c → 2360c) — confound medio
- **OBLIGATORIO:** freeze Doc D antes de iniciar medición pre-training
- Snapshot path: `data/personality_extractions/iris_bertran/doc_d_bot_configuration.md`

---

## Tabla 9 — Inconsistencias Detectadas (Cross-Reference)

| # | Inconsistencia | Fuente A | Fuente B | Resolución |
|---|---|---|---|---|
| I1 | `response_part` en scripts = `"<\|turn>model\n"` (Sprint 6 bug) | `02_sft_config.py:153`, `train_modal.py:130` | S6 06_REVIEW: debe ser `"<\|turn>model\n<\|channel>thought\n<channel\|>"` | **BLOCKER:** actualizar scripts antes de training |
| I2 | `warmup_ratio` = 0.03 en scripts | `02_sft_config.py:122`, `train_modal.py:108` | S4 04_REVIEW: 0.05 | Review prevails → 0.05 |
| I3 | D3 en INTEGRATION_LOG: "PENDIENTE (Qwen3 default)" | `00_INTEGRATION_LOG.md:115` | User override 2026-04-25: Gemma-4 CONFIRMED | User override prevails |
| I4 | Dataset count: 5,739 (script comment) vs 9,272 (A1 audit) | `02_sft_config.py:4` | `A1_dataset_semantic_audit.md` | 9,272 es el count actual. Comment obsoleto. |
| I5 | `eval_dataset=None` en ambos scripts | `02_sft_config.py:109`, `train_modal.py:103` | S5 05_REVIEW: 90/5/5 split obligatorio | **BLOCKER:** añadir validation split |
| I6 | Split ratio: 90/10 (INTEGRATION_LOG) vs 90/5/5 (S5) | `00_INTEGRATION_LOG.md:37` | `05_validation_methodology.md` | S5 es doc técnico → 90/5/5 prevails |
| I7 | Patterns count: user dice "8 patrones" | User message | INTEGRATION_LOG documenta 4 (P1, P2, P5, P8) | Documentar solo patterns confirmados en log |
| I8 | S2, S5, S6, S11 no en branch actual | Branch `planning/sprint7-execution` | Commits cd5536ca, d9fe2d2b, 622f4656, `measurement/baseline-doc-d-aligned` | Contenido recuperado vía `git show` — NO BLOCKER |

---

## Tabla 10 — Ambigüedades y Decisiones de Derivación

| # | Ambigüedad | Decisión Tomada | Justificación |
|---|---|---|---|
| A1 | D3: S8 recomienda Qwen3 pero usuario confirma Gemma-4 | Usar Gemma-4-31B-it | User override explícito. Implica: mantener Opción C, verify scripts, higher bug surface |
| A2 | Split: INTEGRATION_LOG dice 90/10 vs S5 dice 90/5/5 | 90/5/5 (train/val/test) | S5 `05_validation_methodology.md` es el doc técnico de validación — más detallado y authoritative |
| A3 | warmup_ratio: script 0.03 vs S4 review 0.05 | 0.05 | Reviews override originals. S4 04_REVIEW es la corrección autorizada |
| A4 | Dataset en scripts referencia 5,739 pero actual es 9,272 | Plan basado en ~9,272 pre-filtro | Sprint 7 dataset será: base 9,272 - filtros + synthetic Q&A + adversarial |
| A5 | S9 G5 dice "naive + Prometheus" pero script implementa solo heurística | Documentar gap: G5 script es heurística, LLM judge es manual follow-up | Script proporciona señal rápida. Prometheus requiere infra adicional |
| A6 | CCEE-Mini: S5 propone 20 cases pero no existe script dedicado | Plan: usar CCEE full subset (20 random) como CCEE-Mini proxy | $0.15 por run × 20 cases. Validar correlación antes de usar como gate |
| A7 | Curriculum learning callback: S4 dice `curriculum_phase_steps=150` | Incluir en plan pero marcar como EXPERIMENTAL | No hay implementación verificada en scripts |

---

## Verificación Scripts (A.5)

### `scripts/finetuning/09_dataset_quality_gate.py` — ✅ VERIFIED
- 724 líneas, ejecutable sin GPU
- 21 gates en 8 categorías (G1–G8, excl. G6 parcial sin --eval-set)
- Soporta `--pii-whitelist` y `--eval-set`
- Thresholds verificados contra S9 doc — **100% match**
- Bug anterior (NameError `pii_whitelist_set`) ya corregido (línea 687)

### `scripts/finetuning/verify_sprint6_masking.py` — ✅ VERIFIED
- 154 líneas, requiere `unsloth` + GPU
- 4 secciones: template output, inference template, token IDs, Sprint 7 aligned
- Confirma Sprint 6 bug: `<|turn>model\n` vs `<|turn>model\n<|channel>thought\n<channel|>`
- Diagnóstico retrospectivo — ejecutar antes de Sprint 7 como evidencia

### `scripts/finetuning/verify_sprint7_alignment.py` — ✅ VERIFIED
- 148 líneas, requiere `unsloth` + GPU
- 5 checks: G1 (channel in training), G2 (channel in inference), G3 (token IDs match), G4 (masking boundary), G5 (sanity: no channel in user)
- RESPONSE_PART ya definido correctamente: `"<|turn>model\n<|channel>thought\n<channel|>"`
- Pass threshold: ≥4.5/5 → VERIFIED, ≥3 → PARTIAL, <3 → FAILED

---

## Ficheros No En Branch Actual

| Fichero | Localización | Método Acceso |
|---|---|---|
| `02_persona_qa_synthesis.md` | Commit `cd5536ca` | `git show cd5536ca:backend/docs/finetuning_sprint_iris/presprint7/02_persona_qa_synthesis.md` |
| `05_validation_methodology.md` | Commit `d9fe2d2b` | `git show d9fe2d2b:backend/docs/finetuning_sprint_iris/presprint7/05_validation_methodology.md` |
| `06_chat_template_gemma4.md` | Commit `622f4656` | `git show 622f4656:backend/docs/finetuning_sprint_iris/presprint7/06_chat_template_gemma4.md` |
| `11_baseline_remeasure.md` | Branch `measurement/baseline-doc-d-aligned` | `git show measurement/baseline-doc-d-aligned:backend/docs/finetuning_sprint_iris/presprint7/11_baseline_remeasure.md` |

---

## Surrogate Metrics — 4 Tiers [S5]

| Tier | Métricas | Coste | Cuándo |
|---|---|---|---|
| Tier 1 | L1 (avg response length) + chrF++ | $0 | Cada checkpoint |
| Tier 2 | BERTScore (precision, recall, F1) | $0 | Cada eval_steps=100 |
| Tier 3 | CCEE-Mini (20 cases subset) | ~$0.15 | Post-sweep, pre-full |
| Tier 4 | CCEE Full (95+ cases) | ~$4-5 | Solo config ganadora |

**CCEE-Mini correlation:** S5 + 05_REVIEW requieren validar correlación Mini↔Full ($0.30 coste) antes de usar Mini como gate. Sin validación, Mini es informativa pero no decisoria.

---

## Smoke Tests Pre-Training [S5, S6]

| Test | Tipo | Obligatorio | Fuente |
|---|---|---|---|
| Masking verification | Format | ✅ OBLIGATORIO | S5, S6 |
| Format check (role alternation) | Format | ✅ | S5 |
| Language check (CA/ES ratio) | Content | ✅ | S5 |
| Forgetting check | Post-train | ✅ | S5 |
| `verify_sprint6_masking.py` | Diagnostic | Recomendado | S6 |
| `verify_sprint7_alignment.py` | Pre-flight | ✅ OBLIGATORIO | S6 |

---

## Verificación Post-Opus (2026-04-25)

Sesión Sonnet verificó 5 divergencias entre plan y memoria usuario.

| # | Divergencia | Veredicto | Comando evidencia |
|---|---|---|---|
| D1 | Distribución adversarial | Plan correcto | grep TYPE 03_adversarial_examples.md |
| D2 | CCEE Full cases | **Plan incorrecto** | grep --cases 03_ccee_measurement.sh |
| D3 | Modal hardware | Plan correcto | sed -n '40,50p' train_modal.py |
| D4 | Gaps J6/J5/B2 | Plan correcto | sed -n '130,145p' INTEGRATION_LOG.md |
| D5 | Pattern count | Plan correcto | grep "### Patrón" INTEGRATION_LOG.md |

**Acción aplicada:** Patch v1.1 corrige D2. Otras 4 sin cambios.

**Lección metodológica:** Worker Opus generó "95+ cases, $4-5" sin cita verificable. Future workers must cite source line, not infer.

---

_Fin de NOTES_PLAN_DERIVATION.md_
