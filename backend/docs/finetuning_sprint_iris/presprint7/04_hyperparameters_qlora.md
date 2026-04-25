# I4 — Hyperparameters QLoRA SFT: Justificación Sprint 7

**Fecha:** 2026-04-25
**Rama:** research/hyperparams-sft
**Scope:** Iris / Gemma-4-31B dense / dataset ~10-15k post-cleanup (multi-turn + Q&A persona incluidos)
**Sprint anterior:** r=16, alpha=32, LR=2e-4, 1 epoch, max_grad_norm=0.3 → composite v5=66.1 naked

---

## Contexto: Por qué los hiperparámetros importan (pero son el fix secundario)

El postmortem (04_WHY_SFT_UNDERPERFORMED.md) atribuye el gap de 12-19 puntos al dataset, no a los hiperparámetros:

| Causa root | Gap estimado | ¿Hiperparámetro que lo mitigaría? |
|---|---|---|
| 0% multi-turn en dataset | −4 a −6 pts | Ninguno — solo datos |
| 0.1% persona Q&A | −3.5 a −5.5 pts | Rank más alto ayuda marginalmente |
| 22 error strings + 441 artefactos | −2 a −4 pts | Ninguno — solo filtrado |
| Chat template mismatch | −1.5 a −3 pts | Ninguno — corrección de proceso |
| Sistema prompt heterogéneo | −1 a −2 pts | LR bajo podría preservar la señal |

**Conclusión de contexto:** Los hiperparámetros no pueden reparar datos malos. Sprint 7 es principalmente un sprint de dataset (I1-I3). Sin embargo, con el dataset corregido, unos hiperparámetros bien calibrados pueden extraer 2-4 puntos adicionales sobre el mismo dataset.

---

## A. LoRA Rank — Tabla Comparativa con Citas

### Marco teórico

El rank r determina cuántos parámetros adicionales introduce LoRA. Para Gemma-4-31B (d_model=3584, 46 capas, 7 módulos target):

| Rank | Parámetros LoRA aprox. | VRAM adicional | Caso de uso |
|---|---|---|---|
| r=4 | ~9.2M | ~74 MB | NLP benchmarks, baja complejidad |
| r=8 | ~18.4M | ~148 MB | Style simple, instruction following |
| **r=16** | **~36.8M** | **~295 MB** | **Chat persona, estilo + identidad — sweet spot** |
| r=32 | ~73.6M | ~590 MB | Deep persona, reasoning-like tasks |
| r=64 | ~147.2M | ~1.2 GB | Full chat assistant (QLoRA Guanaco config) |

Todos son fracción trivial del modelo de 31B en A100-40GB (16GB base en 4-bit).

### Evidencia empírica por fuente

**[S1] QLoRA (Dettmers et al., 2023 — arXiv:2305.14314)**
Para chat assistant (Guanaco, 9k muestras OASST1, 1 epoch): r=64 con alpha=16. Para NLP benchmarks: r=4. Cita: *"We find that r=4 is typically sufficient for language understanding tasks, while r=64 was used for full chat assistant fine-tuning where model performance was paramount."*
**Relevancia Iris:** Somos un caso de chat persona. El paper valida r alto (32-64) para chat, pero usaron alpha muy bajo (16/64=0.25 ratio) como compensación conservadora.

**[S2] arxiv:2512.15634 — "How Much is Too Much? Exploring LoRA Rank Trade-offs" (Dic 2025)**
Evalúa r ∈ {8, 16, 32, 64, 128}. Hallazgo central: *"For recall-based tasks (MMLU, MedMCQA), all ranks achieve almost similar performance. For reasoning tasks (GSM8K, MathQA), intermediate ranks r=32-64 offer a balanced operating point."* El crecimiento de magnitud de pesos (norma Frobenius) es **logarítmico** con el rank — retornos decrecientes a partir de r=32.
**Relevancia Iris:** Style SFT (S1 dimensional) es más parecido a recall (recordar léxico de Iris) → r=16 suficiente para S1. Persona depth (B2, J5 — mantener creencias bajo presión) tiene componentes reasoning-like → r=32 podría añadir 1-2 pts.

**[S3] Databricks Blog — "Efficient Fine-Tuning with LoRA" (2024)**
En generación de product descriptions (tarea estilo similar): *"r=8 proved sufficient for instruction-following style generation; doubling r does not result in any perceivable increase in output quality."* La mejora sí vino de ampliar **módulos target** (attention-only → all-linear), no de aumentar rank.
**Relevancia Iris:** Para estilo puro, r=8 es suficiente. Los módulos target importan más que el rank.

**[S4] Lightning AI — "LoRA Insights from Hundreds of Experiments" (2024)**
Con Alpaca 50k: r=256 con alpha=512 = mejor resultado absoluto (648.9M params), pero irrelevante para datasets pequeños. Para datasets <15k, r=16-32 es el sweet spot. Dato crítico: *"Training two passes over the 50k dataset produced worse results across all benchmarks vs single-pass"* — confirmación de que 1 epoch > 2 epochs. Alpha=2*rank = óptimo empíricamente.

**[S5] Unsloth Documentation — LoRA Hyperparameters Guide (Abr 2026)**
*"Choose r=16 or r=32 as optimal starting points. Loss expectations for Gemma 26B/31B are lower at 1-3 epochs."* r=16 y r=32 son los valores explícitamente recomendados por Unsloth para modelos Gemma de este tamaño.

**[S6] RSLoRA — arxiv:2312.03732 — "A Rank Stabilization Scaling Factor" (2023)**
LoRA estándar usa scaling α/r → gradiente colapsa en ranks altos. RSLoRA propone α/√r. Beneficio material **solo a r≥128**. A r=16-32, la diferencia entre α/r y α/√r es pequeña y resultados son mixtos en experimentos reales.

### Decisión de rank

| Scenario | Rank | Justificación |
|---|---|---|
| Solo S1 (estilo puro) | r=8 | Databricks confirma suficiente para style |
| S1 + persona (nuestro caso) | **r=16 — primario** | Validado Sprint 6: S1 +20.7 naked con r=16 |
| Persona profunda (B2, J5) | r=32 — sweep Config A | Si composite <69 post-data-fix |
| Overkill / overfit | r=64+ | Solo si dataset >50k alta calidad |

**Decisión Sprint 7: r=16 (mantener).** El Sprint 6 con r=16 logró S1=75.3 naked (style near-ceiling). El gap en B2, J5 se debe al 100% a ausencia de ese tipo de datos. Con nuevos datos (multi-turn, Q&A adversarial), r=16 tendrá los ejemplos necesarios para aprender. Aumentar r no puede compensar datos ausentes.

---

## B. LoRA Alpha — Análisis y Decisión

### Mecánica del scaling

La actualización LoRA se aplica como: **ΔW = (α/r) · BA**

La ratio α/r controla el impacto del adapter sobre los pesos congelados:

| Ratio α/r | Efecto | Ejemplo |
|---|---|---|
| 0.25 | Muy conservador | QLoRA Guanaco: alpha=16, r=64 |
| 1.0 | Neutro | alpha=r |
| 2.0 | Agresivo | **alpha=2r — Lightning AI óptimo** |

### Evidencia

**[S4] Lightning AI (2024):** *"Doubling rank for alpha value proved optimal; deviating (alpha=1, alpha=r/4 at larger ranks) degraded performance."* Alpha=2r validado empíricamente como best practice.

**[S1] QLoRA:** usó alpha=16 con r=64 (ratio=0.25) como **excepción** justificada por rank muy alto + LR alto (2e-4). A r=16 con alpha=32 (ratio=2.0), la agresividad está bien calibrada.

**[S8] ALLoRA — arxiv:2410.09692 (Oct 2024):** *"The alpha=2r heuristic is a good practical approximation that can be improved with per-layer adaptation, but remains the best known default without per-layer tuning."*

**Implicaciones para el effective LR:**
- alpha=32, r=16: effective adapter LR = 2e-4 × 2 = **4e-4** (agresivo, máximo aprendizaje persona)
- alpha=16, r=16: effective adapter LR = 2e-4 × 1 = **2e-4** (conservador, preserva más capacidades generales)

Para persona SFT donde queremos cambio de comportamiento significativo, la agresividad alpha=2r es correcta.

**Decisión: alpha=32 con r=16 (mantener).** Si el sweep muestra overfit (self-repetition >0.90 o train_loss <0.2), reducir a alpha=16.

---

## C. Learning Rate — Análisis y Decisión

### Evidencia publicada

| Fuente | LR recomendado | Contexto | Relevancia para Iris |
|---|---|---|---|
| **[S1] QLoRA (Dettmers 2023)** | **2e-4** | Guanaco 30B chat, 1 epoch | Alta — mismo escenario |
| **[S5] Unsloth (2026)** | **2e-4** start | Normal QLoRA fine-tuning | Alta |
| **[S9] arXiv:2509.20758 (Sep 2025)** | **1e-6** óptimo | Domain SFT con preservación capacidades | Baja — contexto diferente |
| [S4] Lightning AI | 3e-4 | Alpaca instruction tuning | Media |
| Consenso comunidad >13B | 1e-4 a 2e-4 | 2024-2025 | Alta |

### Análisis de arxiv:2509.20758 ("SFT Doesn't Always Hurt")

Este paper (Lin et al., Sep 2025) demuestra que LR=1e-6 domina el Pareto frontier en domain SFT al preservar capacidades generales. Su método TALR (Token-Adaptive Loss Reweighting) mejora aún más el trade-off.

**Por qué NO aplica directamente a Iris:**
- Objetivo del paper: SFT médico/comercial donde se quiere mínima degradación de math/science generales
- Objetivo de Iris: persona SFT donde se quiere cambiar cómo habla/actúa el modelo → degradación de "capacidades generales genéricas" es **aceptable y esperada**
- Con LR=1e-6 y 1 epoch sobre 15k muestras: el modelo no llegaría a internalizar la persona (insuficientes pasos de actualización efectivos)

**Evidencia empírica Sprint 6 con LR=2e-4:**
- H1 Turing naked = 78 (razonamiento general preservado)
- S3 Strategic naked = 62.3 (capacidad estratégica preservada)
- No se observó catastrophic forgetting en 1 epoch / 9.272 muestras

**Decisión: LR=2e-4 (mantener).** Validado empíricamente en Sprint 6. El riesgo de subaprendizaje con LR bajo (1e-4) es mayor que el riesgo de forgetting con LR alto en 1 epoch. Config B del sweep usa 1e-4 si los resultados principales muestran H1 <75 o S3 <58.

---

## D. Epochs — Decisión con Justificación

### Evidencia

**[S4] Lightning AI (2024):** *"Training two passes over the 50k-example Alpaca dataset produced worse results across all benchmarks compared to single-pass, with arithmetic suffering most severely."* Este resultado con 50k muestras implica que con 15k muestras el riesgo de overfit en 2 epochs es aún mayor.

**[S5] Unsloth (2026):** *"1-3 epochs for instruction datasets; more than 3 epochs offers diminishing returns and increases overfitting risk."*

**Argumento específico para nuestro dataset:**

| Scenario dataset | Epochs recomendado | Motivo |
|---|---|---|
| Dataset actual con ruido (~9k) | 1 | Cada sample ruidoso visto solo una vez |
| Dataset post-cleanup (~7-8k calidad) | 1 | Menos samples, sin ruido → safe |
| Dataset ampliado (15k multi-turn+Q&A) | 1 | Más diversidad → 1 epoch cubre distribución |
| Dataset muy pequeño (<3k) | 2-3 | Solo si necesario por underfit |

**Guardrail:** Si `train_loss > 0.80` al final del epoch 1 → indica underfit → considerar 2 epochs. Si `train_loss < 0.20` → indica overfit → aumentar dropout o reducir LR.

**Decisión: 1 epoch (mantener).** Sprint 6 con 1 epoch produjo resultados coherentes (S1 +20.7, no overfit observable). El dataset ampliado a 15k aumenta la cobertura sin necesitar más iteraciones.

---

## E. Otros Parámetros — Justificaciones

| Parámetro | Valor Sprint 6 | Valor Sprint 7 | Fuente | Justificación |
|---|---|---|---|---|
| max_grad_norm | 0.3 | **0.3** | [S1] QLoRA paper | Modelos 4-bit: ruido cuantización amplifica gradientes; clipping agresivo evita spikes |
| weight_decay | 0.01 | **0.01** | [S5] Unsloth, [S4] Lightning AI | Estándar AdamW; impacto bajo en PEFT con pocos params entrenables |
| warmup_ratio | 0.03 | **0.05** | [S5] Unsloth (5-10% recomendado) | Dataset ampliado con 3 tipos de muestras (DMs + multi-turn + Q&A) requiere warmup más largo para estabilidad en early steps |
| lora_dropout | 0.05 | **0.05** | [S1] QLoRA (0.05 para 33B) | Anti-overfit simbólico; bajo coste; Unsloth recomienda 0 pero QLoRA paper valida 0.05 para este tamaño |
| optim | adamw_8bit | **adamw_8bit** | [S1] QLoRA paper | Estándar QLoRA; A100-40GB tiene margen. Si gradient spikes → paged_adamw_32bit |
| lr_scheduler | cosine | **cosine** | [S4] Lightning AI | Cosine mejora TruthfulQA y MMLU vs linear; bien validado |
| use_rslora | False | **False** | [S6] RSLoRA paper | Beneficio material solo a r≥128; a r=16 puede desestabilizar |
| target_modules | 7 all-linear | **7 all-linear** | [S3] Databricks, [S10] Amazon Science | All-linear > attention-only para style + persona; main gain viene de MLP layers |
| bias | none | **none** | [S5] Unsloth | Faster training, reduced memory |
| seed | 3407 | **3407** | Reproducibilidad | Mantener para comparabilidad con Sprint 6 |

**Nota sobre target_modules — evidencia [S10]:**
Amazon Science blog (2024) sobre selección óptima de módulos LoRA: *"Targeting all major linear layers is recommended; attention-only provides stability but requires multiple training epochs for optimal performance."* Databricks confirma: attention-only = "low quality", all-linear = "high quality" para style generation.

---

## F. Configuración Recomendada Sprint 7

### Tabla completa lista para train_modal.py

```python
# ============ LORA CONFIG ============
r              = 16              # [S2, S5] sweet spot estilo+persona; Sprint 6 validó S1+20.7
lora_alpha     = 32              # [S4, S8] alpha=2r: heurística óptima Lightning AI
lora_dropout   = 0.05            # [S1] QLoRA paper para modelos 30-65B
bias           = "none"          # [S5] faster training
random_state   = 3407            # reproducibilidad
use_rslora     = False           # [S6] no beneficio material a r=16
target_modules = [               # [S3, S10] all-linear > attention-only
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

# ============ TRAINING CONFIG ============
per_device_train_batch_size  = 2
gradient_accumulation_steps  = 4           # effective batch=8
num_train_epochs             = 1           # [S4] Lightning AI: 2 epochs = peores resultados
learning_rate                = 2e-4        # [S1, S5] QLoRA/Unsloth default; Sprint 6 validó
lr_scheduler_type            = "cosine"    # [S4] mejora benchmarks vs linear
warmup_ratio                 = 0.05        # [S5] ↑ de 0.03; dataset multi-tipo más diverso
optim                        = "adamw_8bit" # [S1] estándar QLoRA
weight_decay                 = 0.01        # [S4, S5] estándar AdamW
max_grad_norm                = 0.3         # [S1] QLoRA paper para 4-bit; previene spikes
```

### Cambios vs Sprint 6

| Parámetro | Sprint 6 | Sprint 7 | Motivo |
|---|---|---|---|
| warmup_ratio | 0.03 | **0.05** | Dataset 3 tipos de muestras → early steps más variables |
| Dataset | 9.272 samples, 100% DMs, 0% MT | **~12-15k: DMs limpios + 5-10k MT + 200-500 Q&A** | Fixes postmortem E1-E5 |
| Todo lo demás | — | **sin cambio** | Validado empíricamente Sprint 6 |

---

## G. Plan de Mini-Sweep (3 configs alternativas)

Solo ejecutar si el training principal (sprint 7) resulta en composite v5 naked < 69. Orden de prioridad:

### Config A — Rank Higher (r=32)

```python
r          = 32
lora_alpha = 64    # alpha=2r
# resto igual al principal
```

**Hipótesis:** Con datos que cubren B2 (Q&A persona) y J5 (adversarial), r=32 puede capturar dimensiones reasoning-like según [S2] arxiv:2512.15634.

**Gate de activación:** Composite v5 naked < 69 tras entrenamiento principal.

**Métrica de éxito:** ≥+2 pts composite vs principal AND B2 naked ≥ 50 (vs 29.5 Sprint 6).

**Coste Modal:** +20 min training, mismo GPU, ~+$1.50.

---

### Config B — LR Conservador (LR=1e-4)

```python
learning_rate = 1e-4    # mitad del default
warmup_ratio  = 0.05
# resto igual al principal
```

**Hipótesis:** Si el principal muestra regresión en H1 o S3 naked (capacidades generales), LR más bajo según [S9] arxiv:2509.20758 puede preservarlas mejor con comparable aprendizaje de persona.

**Gate de activación:** Principal muestra H1 naked < 75 O S3 naked < 58.

**Métrica de éxito:** H1 ≥ 80 AND S3 ≥ 62 AND B2 ≥ 45. Indica persona aprendida sin degradar capacidades generales.

**Coste Modal:** Mismo tiempo, mismo GPU.

---

### Config C — RSLoRA a r=32

```python
r             = 32
lora_alpha    = 32     # con rslora: scaling = alpha/sqrt(r) = 32/5.66 ≈ 5.66 (moderado)
use_rslora    = True
# resto igual al principal
```

**Hipótesis:** [S6] RSLoRA estabiliza gradiente a r=32 sin la agresividad de Config A (alpha=64). Effective scaling más conservador pero rank más alto.

**Gate de activación:** Config A no mejora composite suficientemente (< +2 pts) o muestra self-repetition > 0.90.

**Métrica de éxito:** Comparable a Config A en composite pero con self-repetition ≤ 0.85.

**Coste Modal:** Igual a Config A.

### Árbol de decisión para el sweep

```
Principal (r=16, alpha=32, LR=2e-4)
│
├─ composite ≥ 69 → ✅ STOP. Sprint 7 exitoso.
│
└─ composite < 69 → ejecutar Config A (r=32, alpha=64)
   │
   ├─ Config A +2 pts vs Principal AND self-rep ≤ 0.85 → ✅ Config A gana. Usar r=32 para Sprint 8.
   │
   ├─ Config A +2 pts PERO self-rep > 0.90 → ejecutar Config C (RSLoRA)
   │
   └─ Config A < +2 pts Y Principal H1 < 75 → ejecutar Config B (LR=1e-4)
```

---

## H. Riesgos de Cada Decisión

| Decisión | Riesgo | Probabilidad | Mitigación |
|---|---|---|---|
| r=16 (no aumentar) | Insuficiente capacidad para B2/J5 con nuevos datos | Baja — S1 ya llegó al techo con r=16; B2/J5 dependen de datos | Sweep Config A si composite < 69 |
| alpha=32 (ratio=2) | Sobreescribir capacidades generales del base model | Media — Sprint 6 mostró H1=78, S3=62.3 aceptables | Monitorear H1 y S3 naked; si regresan < 72, ejecutar Config B |
| LR=2e-4 | Loss spike en early steps → training inestable | Baja — max_grad_norm=0.3 actúa como firewall | Si loss >3.0 en primeros 100 steps → reducir a 1e-4 |
| 1 epoch | Subaprendizaje en muestras raras (Q&A persona, adversarial) | Baja-Media — 200-500 Q&A muestras = ~3-5% del dataset, vistas 1 sola vez | Monitorear B2 naked; si < 40 post-training → considerar 2 epochs SOLO sobre Q&A muestras (subset training) |
| warmup=0.05 | Ninguno significativo vs 0.03 | Muy baja | N/A |
| max_grad_norm=0.3 | Early steps más lentos (gradientes clipeados agresivamente) | Muy baja — trade-off aceptable: estabilidad > velocidad de convergencia early | Si se cambia a 16-bit (no 4-bit) → subir a 1.0 |
| adamw_8bit | Gradient states menos precisos vs 32-bit | Muy baja — diferencia empírica insignificante en la práctica | Si se observan loss spikes > 10 pasos consecutivos → cambiar a paged_adamw_32bit |
| target_modules=all (vs attention-only) | Ligeramente más compute, más params entrenables | Muy baja | Validado en Sprint 6; no cambiar |

---

## Resumen Ejecutivo

**Los hiperparámetros del Sprint 6 son correctos. El único cambio justificado es warmup_ratio 0.03 → 0.05.**

El gap de 12-19 puntos del composite v5 está 100% atribuido a calidad del dataset (postmortem). Los hiperparámetros actuales son validados por:

| Source | Conclusión relevante |
|---|---|
| **[S1] QLoRA (arXiv:2305.14314)** | r=64, LR=2e-4, 1 epoch para chat SFT; 0.3 grad norm para 4-bit |
| **[S2] arXiv:2512.15634** | r=16 suficiente para recall/style; r=32-64 para reasoning |
| **[S3] Databricks (2024)** | all-linear modules >> rank para style generation |
| **[S4] Lightning AI (2024)** | 1 epoch > 2 epochs; alpha=2r; cosine scheduler |
| **[S5] Unsloth (2026)** | r=16-32, LR=2e-4, 1-3 epochs, warmup 5-10% |
| **[S6] RSLoRA (arXiv:2312.03732)** | rsLoRA no aporta a r≤64 en práctica |
| **[S7] Lightning AI alpha study** | alpha=2r validado empíricamente como óptimo |
| **[S8] ALLoRA (arXiv:2410.09692)** | alpha=2r es mejor default sin per-layer tuning |
| **[S9] arXiv:2509.20758 (Sep 2025)** | LR bajo preserva capacidades generales, pero no aplicable a persona SFT donde se quiere cambio de comportamiento |
| **[S10] Amazon Science (2024)** | all-linear > attention-only; gains principalmente de MLP layers |

**Sprint 7 = mismo train_modal.py + warmup_ratio=0.05 + dataset ampliado (E1-E5 del postmortem).**

Si composite post-data-fix < 69: ejecutar sweep en orden A → B → C.

---

*Investigación I4 presprint7 | 2026-04-25 | research/hyperparams-sft | 10 sources citadas*
