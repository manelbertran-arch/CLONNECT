# SPRINT 7 — Execution Plan: SFT Gemma-4-31B-it para Iris

**Versión:** 1.0  
**Fecha:** 2026-04-25  
**Autor:** Derivado de 16+ documentos Presprint 7  
**Branch:** `planning/sprint7-execution`  
**Baseline:** BL_pipeline c0bcbd73 = 67.7 composite v5  
**Target:** composite ≥ 74 (Δ > +5)  
**Model:** Gemma-4-31B-it (D3 confirmado 2026-04-25)

> Cada dato tiene citación interna a su fuente. Sin citación = no incluido.
> Reviews overriden documentos originales donde hay conflicto.

---

## Tabla de Contenidos

1. [Objetivo y Scope](#1-objetivo-y-scope)
2. [Modelo Base y Justificación](#2-modelo-base-y-justificación)
3. [Dataset: Composición y Preparación](#3-dataset-composición-y-preparación)
4. [Quality Gate: Thresholds y Script](#4-quality-gate-thresholds-y-script)
5. [Chat Template: Opción C](#5-chat-template-opción-c)
6. [Hiperparámetros QLoRA](#6-hiperparámetros-qlora)
7. [Training Config y Script](#7-training-config-y-script)
8. [Masking y Alignment Verification](#8-masking-y-alignment-verification)
9. [Loss Monitoring y Abort Criteria](#9-loss-monitoring-y-abort-criteria)
10. [Validation Split y Eval Strategy](#10-validation-split-y-eval-strategy)
11. [Surrogate Metrics (4 Tiers)](#11-surrogate-metrics-4-tiers)
12. [Sweep Proactivo (3 Configs)](#12-sweep-proactivo-3-configs)
13. [CCEE Measurement Protocol](#13-ccee-measurement-protocol)
14. [Doc D Versioning Protocol (D11)](#14-doc-d-versioning-protocol-d11)
15. [Errores Sprint 6: Mitigaciones](#15-errores-sprint-6-mitigaciones)
16. [Fases de Ejecución y Timeline](#16-fases-de-ejecución-y-timeline)

---

## 1. Objetivo y Scope

**Objetivo:** SFT fine-tuning de Gemma-4-31B-it para clonar el estilo conversacional de Iris (@iraais5) en DMs de Instagram y WhatsApp.

**Scope Sprint 7:**
- SFT-only. DPO diferido a Sprint 8. [S4 `04_hyperparameters_qlora.md`, D9]
- Mono-creator: Iris Bertran (creator_id: `iris_bertran`)
- Bilingüe: Catalán + Español (con fallback English)
- Canal: DMs (Instagram + WhatsApp)

**Métricas target:**
- Composite v5 ≥ 74 (Δ > +5 vs baseline 67.7) [S11 `11_baseline_remeasure.md`]
- J6 Q&A Consistency: cerrar gap −75.0 [S2, `00_INTEGRATION_LOG.md`:136]
- J5 Belief Drift: cerrar gap −32.5 [S3, `00_INTEGRATION_LOG.md`:137]
- B2 Persona Consistency: cerrar gap −5.0 [S2, `00_INTEGRATION_LOG.md`:138]

**NO incluido:**
- DPO/GRPO (Sprint 8) [S4 D9]
- Multi-creator scaling
- Production deployment (post-Sprint 7)

---

## 2. Modelo Base y Justificación

**Modelo:** `unsloth/gemma-4-31B-it` [D3, user override 2026-04-25]

**Contexto:** S8 `08_base_model_evaluation.md` evaluó 16 modelos y recomendaba Qwen3-32B (score 8.65 vs Gemma4 7.30) por ventajas TRL auto-patch y chat template simple. Sin embargo, el usuario confirma Gemma-4-31B-it como modelo definitivo.

**Implicaciones de D3 = Gemma-4:**
- Requiere Opción C chat template (CHANNEL_PREFIX) [S6 `06_chat_template_gemma4.md`]
- NO tiene TRL auto-patch → masking manual con `train_on_responses_only` [S7 `08_base_model_evaluation.md`:79]
- Requiere `verify_sprint7_alignment.py` obligatorio pre-training [S6, `06_REVIEW.md`]
- Bug surface más alta que Qwen3 (Pattern 5, `00_INTEGRATION_LOG.md`:63-66)

**Infraestructura:**
- Training: Modal A100-40GB, QLoRA 4-bit (~22GB VRAM) [`train_modal.py`:43]
- Serving: Modal A100-80GB, merged bf16 (~60GB) [`serve_modal.py`:43]
- Evaluation: DeepInfra endpoint o Modal serve endpoint

---

## 3. Dataset: Composición y Preparación

### 3.1 Dataset Base

**Archivo actual:** `data/dpo/trl/sft_combined_audited.jsonl` (9,272 records) [A1 `A1_dataset_semantic_audit.md`]

**Hallazgos A1 que requieren acción:**

| Hallazgo | Count | Acción | Gate |
|---|---|---|---|
| Duplicados | 1,323 (14.3%) | Dedup keep-1 | G2.4 (<5% post-dedup) |
| Error strings | 22 | Eliminar | G2.1 (=0) |
| Non-text (media/sticker) | 818 | Eliminar | G2.2 (=0) |
| PII | 162 | Eliminar o redactar | G6.2 (=0, con --pii-whitelist) |
| System prompt 0% WhatsApp | ~50% records | Añadir Doc D v2 | Error #3, #4 |

[A1 `A1_dataset_semantic_audit.md`, S9 `09_dataset_quality_gate.md`]

### 3.2 Synthetic Data Targets

| Tipo | Target | Método | Fuente |
|---|---|---|---|
| Persona Q&A | 750–1,000 pares | OpenCharacter-G (100 preguntas × 9 categorías B1–B9) | S2 `02_persona_qa_synthesis.md`, D5 |
| Adversarial | 200–300 ejemplos | 8 attack types (TYPE-8 J5-critical prioritario) | S3 `03_adversarial_examples.md`, D6 |
| Multi-turn | ≥15% del total | Threshold 60 min, burst merge 5 min | S1 `01_multi_turn_construction.md`, D2 |

### 3.3 Persona Q&A Synthesis [S2]

**Método:** OpenCharacter-G [S2 `02_persona_qa_synthesis.md`]
- Input: Doc D[:1000] + 9 categorías (B1–B9: identitat, idioma, feina, valors, historia, relacions, productes, coaching, lifestyle)
- J6 probes: dinámicos, generados vía LLM (n=3, cached por creator_id) [S2, `02_REVIEW.md`]
- Validación 4 capas: NLI consistency + blacklist + style match + Doc D alignment [S2]
- Budget mínimo: ~500 pares (B1+B2+B3+B7: 38/100 preguntas) [S2, `00_INTEGRATION_LOG.md`:87-91]
- Budget completo: 750–1,000 pares [D5]

### 3.4 Adversarial Examples [S3]

**Taxonomía 8 tipos:** [S3 `03_adversarial_examples.md`, `03_REVIEW.md`]

| Type | Descripción | Prioridad | % Budget |
|---|---|---|---|
| TYPE-1 | Identity challenge ("ets un bot?") | J5-critical | 30% |
| TYPE-2 | Factual inconsistency | G5-territory | 5% |
| TYPE-3 | Emotional manipulation | G5-territory | 5% |
| TYPE-4 | Price/value challenge | — | 10% |
| TYPE-5 | Topic expertise test | G5-territory | 5% |
| TYPE-6 | Repeated pressure | J5-critical | 15% |
| TYPE-7 | Cross-language switch | — | 10% |
| **TYPE-8** | **Topic pivot (NEW)** | **J5-critical** | **20%** |

[S3 `03_adversarial_examples.md` Sección F.2, `03_REVIEW.md`]

### 3.5 Multi-turn Construction [S1]

- Threshold: 60 min entre mensajes = nuevo turno [D2]
- Burst merge: mensajes consecutivos <5 min del mismo usuario → merge [S1]
- Target ratio: 70% real conversations / 30% synthetic [S1 `01_multi_turn_construction.md`]
- TurnWise method: +12.8 pp SFT pero degrada single-turn → preference-tuning recomendado (Sprint 8) [S1, `01_REVIEW.md`]
- Gate G1.1: ≥15% multi-turn en dataset final [S9]

### 3.6 System Prompt Unification [Errors #3, #4]

- **OBLIGATORIO:** Todos los samples deben tener Doc D v2 como system prompt [S2, S4, `00_INTEGRATION_LOG.md`:35-36]
- Doc D path: `data/personality_extractions/iris_bertran/doc_d_bot_configuration.md`
- Freeze Doc D pre-training (D11) [S11]
- CRITICAL (CLAUDE.md): NO comprimir/resumir/reordenar Doc D — base models lo tratan como literal

### 3.7 Dataset Pipeline Esperado

```
sft_combined_audited.jsonl (9,272)
    → Dedup (keep-1)
    → Filter: error strings, non-text, PII
    → Add system prompt (Doc D v2) to WhatsApp records
    → Add: persona Q&A synthetic (750-1000)
    → Add: adversarial synthetic (200-300)
    → Multi-turn segmentation (60 min threshold)
    → 90/5/5 split (train/val/test)
    → Quality Gate (09_dataset_quality_gate.py)
    → sft_sprint7.jsonl (estimated ~8,000-9,500 records)
```

---

## 4. Quality Gate: Thresholds y Script

**Script:** `scripts/finetuning/09_dataset_quality_gate.py` (verificado 2026-04-25)

**Comando:**
```bash
python3 scripts/finetuning/09_dataset_quality_gate.py \
    --input data/dpo/trl/sft_sprint7.jsonl \
    --eval-set data/dpo/trl/sft_eval.jsonl \
    --pii-whitelist @iris_bertran @iraais5 \
    --report-out docs/finetuning_sprint_iris/sprint7/gate_report.md
```

### Gate Thresholds (21 checks, script-verified) [S9, `09_dataset_quality_gate.py`]

**BLOCKERS (training NO PUEDE proceder si falla):**

| Gate | Criterio | Threshold |
|---|---|---|
| G1.1 | multi-turn ≥15% | 0.15 |
| G1.2 | persona Q&A ≥750 OR ≥7.5% | 750 / 7.5% [D10] |
| G2.1 | error strings = 0 | 0 |
| G2.2 | solo-artifact = 0 | 0 |
| G2.3 | artifacts explícitos <2% | 0.02 |
| G6.1 | overlap CCEE eval = 0 | 0 |
| G6.2 | PII en assistant = 0 | 0 |
| G7.1–G7.4, G7.6 | format compliance (messages, roles, alternation) | 100% |
| G8.1 | N mínimo ≥2,000 | 2000 |

**WARNINGS (training permitido, documentar):**

| Gate | Criterio | Threshold |
|---|---|---|
| G1.3 | adversarial ≥200 OR ≥2% | 200 / 2% [D10] |
| G1.4 | DM single-turn ≤75% | 0.75 |
| G2.4 | duplicados exactos <5% | 0.05 |
| G2.5 | respuestas <10 chars <5% | 0.05 |
| G3.1 | Distinct-1 ≥0.20 | 0.20 |
| G3.2 | Distinct-2 ≥0.40 | 0.40 |
| G3.3 | Self-BLEU-4 ≤0.65 | 0.65 |
| G4.1 | categorías persona ≥5/6 | 5 |
| G4.2 | idioma ca+es ≥35% | 0.35 |
| G5.1 | coherencia ≥85% (heurística) | 0.85 |
| G7.5 | system prompt ≥95% | 0.95 |
| G8.2 | N máximo ≤30,000 | 30000 |
| G8.3 | P99 tokens ≤2,048 | 2048 |
| G8.4 | records >1500 tokens <10% | 0.10 |

**Decisión lógica del script:**
- FAIL = cualquier BLOCKER falla → NO training
- PASS_WITH_WARNINGS = ≤3 warnings fallidos → training OK, documentar
- PASS_DEGRADED = >3 warnings fallidos → training OK, revisar antes
- PASS = todo pasa

[S9 `09_dataset_quality_gate.md`, `09_dataset_quality_gate.py:594-605`]

---

## 5. Chat Template: Opción C

**Decisión:** Opción C — CHANNEL_PREFIX en training labels Y serving prompt [D1]

**Validado por:** Google Gemma-4 documentation [S6 `06_chat_template_gemma4.md`, `06_REVIEW.md`]

### Response Part (Sprint 7 corregido)

```python
CHANNEL_PREFIX = "<|channel>thought\n<channel|>"
RESPONSE_PART = f"<|turn>model\n{CHANNEL_PREFIX}"
# = "<|turn>model\n<|channel>thought\n<channel|>"
```

[S6 `06_chat_template_gemma4.md`, `verify_sprint7_alignment.py`:19-20]

### Training: masking boundary

```python
from unsloth.chat_templates import train_on_responses_only
trainer = train_on_responses_only(
    trainer,
    instruction_part="<|turn>user\n",
    response_part="<|turn>model\n<|channel>thought\n<channel|>",  # Sprint 7 FIX
)
```

[S6 `06_chat_template_gemma4.md`, contraste con Sprint 6: `02_sft_config.py:150-154`]

### Serving: generation prompt

```python
tokenizer.apply_chat_template(
    messages,
    add_generation_prompt=True,
    enable_thinking=False,  # Non-thinking mode para DM persona
)
# → termina en "<|turn>model\n<|channel>thought\n<channel|>"
```

[S6 `06_chat_template_gemma4.md`]

**CRITICAL:** Sprint 6 scripts (`02_sft_config.py:153`, `train_modal.py:130`) todavía tienen `response_part="<|turn>model\n"`. MUST UPDATE antes de Sprint 7 training. [NOTES Tabla 9, I1]

### ⚠️ Opción C — Parte 2 (descubierta en Smoke Training Sprint 7)

**Post-mortem Smoke v2-v4 (2026-04-26):** B1 implementó el `response_part` correcto pero omitió una segunda parte de Opción C: **prepend manual de `CHANNEL_PREFIX` a cada turno assistant en `formatting_prompts_func`**.

**Causa raíz:** con `enable_thinking=False` + `add_generation_prompt=False`, el template Gemma 4 NO añade `<|channel>thought\n<channel|>` a los turnos assistant en el texto de training (solo lo añade en inference con `add_generation_prompt=True`). Sin el prepend, `train_on_responses_only` no encuentra el boundary → 100% labels = -100 → todos los samples eliminados.

**Fix completo (commit `021f7fdc`, `training/sprint7-smoke`):**

```python
# En formatting_prompts_func — OBLIGATORIO para Opción C
CHANNEL_PREFIX = "<|channel>thought\n<channel|>"

def formatting_prompts_func(examples):
    convos = examples["conversations"] if "conversations" in examples else examples["messages"]
    aligned_convos = []
    for convo in convos:
        aligned = []
        for turn in convo:
            if turn.get("role") in ("assistant", "model"):
                turn = {**turn, "content": CHANNEL_PREFIX + turn["content"]}
            aligned.append(turn)
        aligned_convos.append(aligned)
    texts = [
        tokenizer.apply_chat_template(
            convo, tokenize=False, add_generation_prompt=False, enable_thinking=False
        ).removeprefix("<bos>")
        for convo in aligned_convos
    ]
    return {"text": texts}
```

**También:** `MAX_SEQ_LENGTH` debe ser 4096 (no 2048) porque Doc D ≈ 2044 tokens solo ya supera 2048 con cualquier turno adicional. [G8.3 WARN era el síntoma.]

**Referencia:** `verify_sprint7_alignment.py` líneas 47-52 mostraba este prepend en el check G1 — la verificación estaba documentada pero no implementada en `train_modal.py`.

---

## 6. Hiperparámetros QLoRA

**Fuente:** S4 `04_hyperparameters_qlora.md` + `04_REVIEW.md`, verificado contra scripts

| Parámetro | Valor | Notas |
|---|---|---|
| r (LoRA rank) | 16 | Default. Sweep: {8, 16, 32} [D4] |
| lora_alpha | 32 | = 2r. Heurística, no canon QLoRA [04_REVIEW] |
| lora_dropout | 0.05 | Anti-overfit [`02_sft_config.py:45`] |
| target_modules | q,k,v,o,gate,up,down_proj | All-linear para capturar style [`02_sft_config.py:50-53`] |
| bias | none | [`02_sft_config.py:47`] |
| use_rslora | False | Experimental, no usar v1 [`02_sft_config.py:49`] |
| load_in_4bit | True | QLoRA — ~22GB VRAM en A100 [`02_sft_config.py:22`] |

**Two Sprint 6 failures [S4, 04_REVIEW]:**
1. Dataset quality (error strings, no Q&A, no adversarial) → fixed by quality gate
2. Masking roto → fixed by Opción C response_part

[S4 `04_hyperparameters_qlora.md`, `04_REVIEW.md`]

---

## 7. Training Config y Script

### SFTConfig Sprint 7 (diff vs Sprint 6)

```python
SFTConfig(
    # === Unchanged from Sprint 6 ===
    dataset_text_field="text",
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,       # effective batch = 8
    num_train_epochs=1,
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    optim="adamw_8bit",
    weight_decay=0.01,
    max_grad_norm=0.3,
    logging_steps=10,
    save_strategy="steps",
    save_steps=200,
    save_total_limit=3,
    seed=3407,
    output_dir="/models/gemma31b-iris-sft-checkpoints",
    report_to="none",                    # o "wandb"

    # === CHANGED for Sprint 7 ===
    warmup_ratio=0.05,                   # was 0.03 [S4 04_REVIEW, I2]
    eval_strategy="steps",               # NEW [S5]
    eval_steps=100,                      # NEW [S5]

    # === FORBIDDEN (TRL bugs) ===
    # packing=False,                     # default, do NOT set True [#3728]
    # NO liger_kernel                    # [#3781]
    # NO max_length                      # [#3927]
    # NO dataset_kwargs={"stream":True}  # [#3768]
)
```

[S4, S5, S1, `02_sft_config.py`, `train_modal.py`, NOTES Tabla 2+4]

### Scripts que requieren actualización antes de Sprint 7

| Script | Cambio | Ref |
|---|---|---|
| `scripts/finetuning/02_sft_config.py:153` | `response_part` → add CHANNEL_PREFIX | I1 |
| `scripts/finetuning/02_sft_config.py:122` | `warmup_ratio` → 0.05 | I2 |
| `scripts/finetuning/02_sft_config.py:109` | `eval_dataset` → add val split | I5 |
| `scripts/finetuning/train_modal.py:130` | `response_part` → add CHANNEL_PREFIX | I1 |
| `scripts/finetuning/train_modal.py:108` | `warmup_ratio` → 0.05 | I2 |
| `scripts/finetuning/train_modal.py:103` | `eval_dataset` → add val split | I5 |
| `scripts/finetuning/train_modal.py:33-35` | Dataset file → `sft_sprint7.jsonl` | — |

---

## 8. Masking y Alignment Verification

### Pre-flight Obligatorio [S6, 06_REVIEW]

**Paso 1:** Ejecutar diagnóstico Sprint 6 (evidencia retrospectiva)
```bash
python3 scripts/finetuning/verify_sprint6_masking.py \
    --dataset data/dpo/trl/sft_combined_audited.jsonl \
    --n_samples 5
```
Requiere: `unsloth` + GPU. Confirma el bug Sprint 6. [`verify_sprint6_masking.py`]

**Paso 2:** Verificar alignment Sprint 7 (OBLIGATORIO antes de training)
```bash
python3 scripts/finetuning/verify_sprint7_alignment.py
```
Requiere: `unsloth` + GPU. 5 checks (G1–G5):
- G1: Channel prefix en training sequence
- G2: Channel prefix en inference prompt
- G3: Token IDs boundary consistentes
- G4: Masking boundary presente en training text
- G5: Channel prefix NO en user turn (sanity)

Pass: ≥4.5/5. [`verify_sprint7_alignment.py`]

**Paso 3:** Verificar masking visual post-trainer-init
```python
sample_labels = trainer.train_dataset[0]["labels"]
decoded = tokenizer.decode([
    tokenizer.pad_token_id if x == -100 else x for x in sample_labels
]).replace(tokenizer.pad_token, " ")
print(decoded[:500])
# Debe mostrar SOLO texto del assistant, NO user messages
```
[`02_sft_config.py:157-162`, S5 `05_validation_methodology.md`]

---

## 9. Loss Monitoring y Abort Criteria

### Loss Alert Table [S5 `05_validation_methodology.md`, `05_REVIEW.md`]

| Step | Rango OK | ALERTA | ABORT |
|---|---|---|---|
| 1 | 1.0–3.0 | — | > 12.0 |
| 10 | 1.5–2.5 | > 4.0 | — |
| 50 | 1.0–2.0 | > 5.0 | — |
| 100 | 0.8–1.8 | — | > 8.0 |
| Final | 0.5–1.5 | < 0.2 (overfit) | — |
| Any | — | — | > 12.0 |

**Referencia:** Sprint 6 loss = 10.64 → masking roto. Con masking correcto, loss esperada 1.5–2.5 en primeros 50 steps. [S5, 05_REVIEW]

### SFTDivergenceCallback [S5]

```python
from transformers import TrainerCallback

class SFTDivergenceCallback(TrainerCallback):
    def on_log(self, args, state, control, logs=None, **kwargs):
        loss = logs.get("loss")
        if not loss:
            return
        step = state.global_step
        if loss > 12.0:
            print(f"ABORT: loss {loss:.2f} > 12.0 at step {step}")
            control.should_training_stop = True
        elif step == 50 and loss > 5.0:
            print(f"ALERTA: loss {loss:.2f} > 5.0 at step 50")
        elif step == 100 and loss > 8.0:
            print(f"ABORT: loss {loss:.2f} > 8.0 at step 100")
            control.should_training_stop = True
```

---

## 10. Validation Split y Eval Strategy

### Split [S5 `05_validation_methodology.md`, A3]

| Set | % | Uso |
|---|---|---|
| Train | 90% | SFT training |
| Val | 5% | eval_steps=100, loss monitoring |
| Test | 5% | Post-training evaluation (held-out) |

**Resolución ambigüedad:** INTEGRATION_LOG dice 90/10; S5 (doc técnico de validación) dice 90/5/5. Se usa **90/5/5** porque S5 es el documento authoritative para validation methodology. [NOTES A2]

### Eval Strategy

```python
SFTConfig(
    eval_strategy="steps",
    eval_steps=100,          # [S5]
)
```

**Val loss divergence:** Si val_loss sube >20% vs train_loss durante 3 eval consecutivos → early stopping signal. [S5]

---

## 11. Surrogate Metrics (4 Tiers)

**Fuente:** S5 `05_validation_methodology.md` + `05_REVIEW.md`

| Tier | Métricas | Coste | Cuándo Ejecutar | Implementación |
|---|---|---|---|---|
| **T1** | L1 (avg response length) + chrF++ | $0 | Cada checkpoint | Post-training script |
| **T2** | BERTScore (P, R, F1) | $0 | Cada eval_steps=100 | `bert_score` library |
| **T3** | CCEE-Mini (20 cases random) | ~$0.15 | Post-sweep, pre-full | Subset de `03_ccee_measurement.sh` |
| **T4** | CCEE Full (50 cases × 3 runs) | ~$1.50 | Solo config ganadora | `03_ccee_measurement.sh` |

### CCEE-Mini Correlation Requirement [S5, 05_REVIEW]

**OBLIGATORIO:** Validar correlación CCEE-Mini ↔ CCEE-Full antes de usar Mini como gate.
- Coste: $0.30 (1 Mini + 1 Full en misma config)
- Si Pearson r < 0.8 → Mini no es gate, solo informativo
- Si r ≥ 0.8 → Mini puede sustituir Full para sweep elimination

---

## 12. Sweep Proactivo (3 Configs)

**Fuente:** S4 `04_hyperparameters_qlora.md`, `04_REVIEW.md`

| Config | r | LR | Epochs | Steps | Coste Est. |
|---|---|---|---|---|---|
| **A (default)** | 16 | 2e-4 | 1 | 100% | ~$3 |
| B (conservative) | 32 | 1e-4 | 2 | 50% | ~$3 |
| C (light) | 8 | 2e-4 | 3 | 50% | ~$1.5 |

### Sweep Protocol

1. **Config A:** Run full (100% steps). Baseline sweep. [S4]
2. **Configs B, C:** Run 50% steps. Si loss trajectory diverge significativamente de A → eliminate. [S4]
3. **Evaluate survivors** con CCEE-Mini (Tier 3). [S5]
4. **Winner** → CCEE Full (Tier 4). [S5]
5. **Curriculum learning** [D8]: Si B2 (Persona Consistency) no converge en config A → apply Phase 2 selective Q&A training.

**Coste total sweep:** ~$7.50 training + ~$0.60 CCEE-Mini (4 runs) + ~$1.50 CCEE Full = **~$9.60 total**

### Curriculum Learning [D8, S4]

```python
curriculum_phase_steps = 150  # [S4]
# Phase 1 (steps 0-150): all data (DM + Q&A + adversarial)
# Phase 2 (steps 150+): selective Q&A if B2 not converging
```

**EXPERIMENTAL:** No hay implementación verificada en scripts. Implementar como callback custom si B2 metric no mejora en primeros 150 steps. [NOTES A7]

---

## 13. CCEE Measurement Protocol

### Pre-measurement Checklist [S11, Feedback: CCEE Pre-launch]

1. ✅ Freeze Doc D (D11) — snapshot antes de medición
2. ✅ Verify model endpoint connectivity (DeepInfra o Modal serve)
3. ✅ Use `.venv/bin/python3` (no system python) [Feedback: CCEE Pre-launch]
4. ✅ Gemma needs `--override` flag if applicable [Feedback: CCEE Pre-launch]
5. ✅ Test 1 prompt round-trip before launching full CCEE

### CCEE Execution

```bash
# Smoke test (1 case)
bash scripts/finetuning/03_ccee_measurement.sh --cases 1

# CCEE-Mini (20 cases) — ~$0.15
bash scripts/finetuning/03_ccee_measurement.sh --cases 20

# CCEE Full (50 cases × 3 runs) — ~$1.50
bash scripts/finetuning/03_ccee_measurement.sh
```

### Comparison Base [S11]

| Condición | Composite v5 |
|---|---|
| BL_pipeline c0bcbd73 | **67.7** |
| Sprint 7 target | **≥ 74** (Δ > +5) |

### Gate

- **Sprint 7 PASS:** composite ≥ 74
- **Sprint 7 MARGINAL:** composite 70–74 (Δ +2.3 to +6.3) → revisar, posible Sprint 7.1
- **Sprint 7 FAIL:** composite < 70 → diagnose, do NOT proceed to Sprint 8

---

## 14. Doc D Versioning Protocol (D11)

**Fuente:** S11 `11_baseline_remeasure.md`

**Problema detectado:** Doc D cambió entre mediciones sin freeze → confound −1.8 pts en baseline comparison. [S11]

### Protocol

1. **ANTES de cada medición (pre-training o CCEE):**
   ```bash
   python3 scripts/doc_d_snapshot.py  # Si existe
   # O manualmente:
   cp data/personality_extractions/iris_bertran/doc_d_bot_configuration.md \
      data/personality_extractions/iris_bertran/doc_d_bot_configuration_sprint7_freeze.md
   git add data/personality_extractions/iris_bertran/doc_d_bot_configuration_sprint7_freeze.md
   git commit -m "freeze: Doc D Sprint 7 pre-training snapshot"
   ```

2. **DURANTE training:** No modificar `doc_d_bot_configuration.md`

3. **PARA medición post-training:** Usar el MISMO Doc D frozen para CCEE

4. **CRITICAL (CLAUDE.md):** NO comprimir, resumir, reordenar, o reescribir Doc D. Identity-defining signals son literales para base models sin fine-tuning.

---

## 15. Errores Sprint 6: Mitigaciones

**Fuente:** `00_INTEGRATION_LOG.md` Sección "Errores Sprint 6"

| # | Error | Sev. | Mitigación Sprint 7 | Status |
|---|---|---|---|---|
| 1 | Masking roto | 🔴 | response_part con CHANNEL_PREFIX [§5] | ⚠️ Scripts pendientes actualizar |
| 2 | Chat template mismatch | 🔴 | Opción C [§5] | ⚠️ Scripts pendientes actualizar |
| 3 | System prompt heterogéneo | 🔴 | Doc D v2 en todos samples [§3.6] | Pipeline step |
| 4 | System prompt train ≠ prod | 🔴 | Doc D v2 idéntico [§3.6] | Pipeline step |
| 5 | Sin validation split | 🟡 | 90/5/5 split [§10] | ⚠️ Scripts pendientes actualizar |
| 6 | 0% multi-turn | 🔴 | Threshold 60 min, gate G1.1 ≥15% [§3.5] | Pipeline step |
| 7 | 22 error strings | 🔴 | Filtro + gate G2.1 = 0 [§4] | ✅ Script verificado |
| 8 | 0.1% persona Q&A | 🔴 | Target 750–1000, gate G1.2 [§3.3] | Pipeline step |
| 9 | 441 media/sticker | 🟡 | Filtro + gate G2.2+G2.3 [§4] | ✅ Script verificado |
| 10 | 1352 duplicados 14.6% | 🟡 | Dedup + gate G2.4 <5% [§4] | Pipeline step |
| 11 | 0 adversarial | 🔴 | Target 200–300, gate G1.3 [§3.4] | Pipeline step |

---

## 16. Fases de Ejecución y Timeline

### FASE 0 — Pre-flight (Día 1, ~2h)

| Step | Acción | Verificación | Ref |
|---|---|---|---|
| 0.1 | Freeze Doc D snapshot | File committed | §14, D11 |
| 0.2 | Update `02_sft_config.py` response_part | `git diff` confirms | §5, I1 |
| 0.3 | Update `train_modal.py` response_part + warmup + eval | `git diff` confirms | §7, I1/I2/I5 |
| 0.4 | Run `verify_sprint7_alignment.py` (GPU) | ≥4.5/5 checks pass | §8 |
| 0.5 | Run `verify_sprint6_masking.py` (GPU) | Diagnóstico guardado | §8 |

### FASE 1 — Dataset Preparation (Día 1–2, ~4h)

| Step | Acción | Verificación | Ref |
|---|---|---|---|
| 1.1 | Dedup sft_combined_audited.jsonl (keep-1) | Count < 8,000 | §3.1 |
| 1.2 | Filter: error strings, non-text, PII | 0 remaining per category | §3.1 |
| 1.3 | Add Doc D v2 system prompt to WhatsApp records | 100% system prompt | §3.6 |
| 1.4 | Generate persona Q&A (750–1000 pares) | Count ≥ 750 | §3.3 |
| 1.5 | Generate adversarial examples (200–300) | Count ≥ 200 | §3.4 |
| 1.6 | Multi-turn segmentation (60 min threshold) | ≥15% multi-turn | §3.5 |
| 1.7 | 90/5/5 split | 3 files created | §10 |
| 1.8 | Run quality gate | PASS o PASS_WITH_WARNINGS | §4 |

### FASE 2 — Training: Config A (Día 2–3, ~3h GPU)

| Step | Acción | Verificación | Ref |
|---|---|---|---|
| 2.1 | Visual masking check post-trainer-init | Only assistant text visible | §8 |
| 2.2 | Launch Config A (r=16, LR=2e-4, 1 epoch, full steps) | Training starts | §12 |
| 2.3 | Monitor loss: step 1, 10, 50, 100 | Within alert table ranges | §9 |
| 2.4 | Check val loss at eval_steps=100 | No divergence >20% | §10 |
| 2.5 | Save LoRA adapter + merge 16-bit | Files on Modal volume | §7 |

### FASE 3 — Sweep: Configs B+C (Día 3, ~2h GPU)

| Step | Acción | Verificación | Ref |
|---|---|---|---|
| 3.1 | Launch Config B (r=32, LR=1e-4, 2 ep, 50% steps) | Loss trajectory OK | §12 |
| 3.2 | Launch Config C (r=8, LR=2e-4, 3 ep, 50% steps) | Loss trajectory OK | §12 |
| 3.3 | Eliminate divergent configs | ≤2 survivors | §12 |

### FASE 4 — Evaluation (Día 3–4, ~2h)

| Step | Acción | Verificación | Ref |
|---|---|---|---|
| 4.1 | Tier 1+2 (L1, chrF++, BERTScore) all survivors | Rankings generated | §11 |
| 4.2 | CCEE-Mini (20 cases) all survivors | Rankings consistent with T1+T2 | §11 |
| 4.3 | CCEE-Mini correlation check ($0.30) | Pearson r reported | §11 |
| 4.4 | CCEE Full winner config | composite ≥ 74 target | §13 |

### FASE 5 — Gate Decision (Día 4)

| Resultado | Acción |
|---|---|
| composite ≥ 74 | ✅ Sprint 7 PASS → proceed to Sprint 8 (DPO) |
| composite 70–74 | ⚠️ MARGINAL → diagnose, possible Sprint 7.1 |
| composite < 70 | ❌ FAIL → root cause analysis, do NOT proceed |

### Coste Total Estimado

| Item | Coste |
|---|---|
| GPU training (3 configs) | ~$7.50 |
| CCEE-Mini (4 runs) | ~$0.60 |
| CCEE Full (1 run) | ~$1.50 |
| CCEE-Mini correlation | ~$0.30 |
| **Total** | **~$9.90** |

---

## Apéndice A — Decisions Registry

| ID | Decisión | Estado | Fuente |
|---|---|---|---|
| D1 | Chat template Opción C | ✅ | S6, 06_REVIEW |
| D2 | Multi-turn 60 min | ✅ | S1, 01_REVIEW |
| D3 | Gemma-4-31B-it | ✅ (user override) | S8, user 2026-04-25 |
| D4 | r=16 default + sweep | ✅ | S4, 04_REVIEW |
| D5 | Q&A 750–1000 | ✅ | S2, 02_REVIEW |
| D6 | Adversarial 200–300 | ✅ | S3, 03_REVIEW |
| D7 | TYPE-8 J5-critical | ✅ | S3, 03_REVIEW |
| D8 | Curriculum learning | ✅ EXPERIMENTAL | S4, 04_REVIEW |
| D9 | DPO → Sprint 8 | ✅ | S4, 04_REVIEW |
| D10 | Gate: absolute OR ratio | ✅ | S9, 05_REVIEW |
| D11 | Doc D freeze protocol | 🔴 URGENT | S11 |

## Apéndice B — Patterns Emergentes (de INTEGRATION_LOG)

| # | Pattern | Fuente | Impacto Sprint 7 |
|---|---|---|---|
| P1 | Masking silencioso como riesgo sistemático | S1, S4, S6, S7 | verify_sprint7_alignment.py obligatorio |
| P2 | Sin matching con probes CCEE | S1–S4 | J6 probes dinámicos (S2 resuelve) |
| P5 | Coste estructural asimétrico (model choice) | S6, S7/S8 | Gemma-4 implica mayor bug surface |
| P8 | Threshold 0.85 MiniLM = false positives | A1 | Usar ≥0.92 + response-side para auditorías |

## Apéndice C — Source Documents Index

| Código | Documento | Líneas | Branch/Commit |
|---|---|---|---|
| S1 | `01_multi_turn_construction.md` | 667 | current |
| S2 | `02_persona_qa_synthesis.md` | 980 | `cd5536ca` |
| S3 | `03_adversarial_examples.md` | 736 | current |
| S4 | `04_hyperparameters_qlora.md` | 367 | current |
| S5 | `05_validation_methodology.md` | 703 | `d9fe2d2b` |
| S6 | `06_chat_template_gemma4.md` | 799 | `622f4656` |
| S8 | `08_base_model_evaluation.md` | 493 | current |
| S9 | `09_dataset_quality_gate.md` | 404 | current |
| S10 | `10_ccee_j6_logging_fix.md` | 160 | current |
| S11 | `11_baseline_remeasure.md` | 294 | `measurement/baseline-doc-d-aligned` |
| A1 | `A1_dataset_semantic_audit.md` | 489 | current |
| R1 | `01_REVIEW.md` | — | current |
| R2 | `02_REVIEW.md` | — | current |
| R3 | `03_REVIEW.md` | — | current |
| R4 | `04_REVIEW.md` | — | current |
| R5 | `05_REVIEW.md` | — | current |
| R6 | `06_REVIEW.md` | — | current |
| LOG | `00_INTEGRATION_LOG.md` | 169 | current |

**Scripts verificados:**

| Script | Líneas | Requiere GPU |
|---|---|---|
| `09_dataset_quality_gate.py` | 724 | No |
| `verify_sprint6_masking.py` | 154 | Sí |
| `verify_sprint7_alignment.py` | 148 | Sí |
| `02_sft_config.py` | 233 | Sí |
| `train_modal.py` | 155 | Sí (Modal) |

---

_Generado a partir de NOTES_PLAN_DERIVATION.md. Cada dato tiene citación interna._

---

**Patch v1.1 (2026-04-25):** Verificación post-Opus detectó D2 incorrecto. CCEE Full corregido a 50 cases × 3 runs ($1.50) basado en evidencia `03_ccee_measurement.sh:85` (--cases 50) y `:22` (NUM_RUNS default 3). Costes total recalculados de $13.40 → $9.90. Otras 4 divergencias verificadas confirmaron plan original correcto. Ver NOTES_PLAN_DERIVATION.md sección Verificación.

**Patch v1.2 (2026-04-26):** Smoke training descubrió que B1 (Opción C §5) era incompleto. El `response_part` era correcto pero faltaba el prepend manual de `CHANNEL_PREFIX` en `formatting_prompts_func`. Fix completo en commit `021f7fdc` branch `training/sprint7-smoke`. También: `MAX_SEQ_LENGTH` 2048 → 4096 (Doc D ≈ 2044 tokens excede 2048 con cualquier turno). Ver nota "Opción C — Parte 2" en §5.
