# I4 — Hyperparameters QLoRA SFT: Justificación Sprint 7

**Fecha:** 2026-04-25 (revisado fin de Sesión 4)
**Rama:** research/hyperparams-sft
**Scope:** Iris / Gemma-4-31B dense / dataset ~10-15k post-cleanup (multi-turn + Q&A persona incluidos)
**Sprint anterior:** r=16, alpha=32, LR=2e-4, 1 epoch, max_grad_norm=0.3 → composite v5=66.1 naked

---

## Contexto: DOS Fallos Simultáneos en Sprint 6

> **CORRECCIÓN RESPECTO A POSTMORTEM INICIAL:** El postmortem (04_WHY_SFT_UNDERPERFORMED.md) atribuía el gap "100% al dataset". Sprint 6 tuvo DOS fallos simultáneos que no podemos desacoplar sin un run de control.

### Fallo (a): Dataset ruidoso

0% multi-turn, 0.1% persona Q&A, 22 error-strings, 441 artefactos media. Auditado en FASES 2-3 del postmortem.

### Fallo (b): Masking probablemente roto (documentado en Sesión I6 — 06_chat_template_gemma4.md y Sesión 1 — 01_multi_turn_construction.md § A.6)

El Sprint 6 usó `train_on_responses_only` con los boundary strings:
```python
instruction_part = "<|turn>user\n"
response_part    = "<|turn>model\n"
```

Durante **serving**, el template Gemma-4 `gemma-4-thinking` inyecta automáticamente:
```
<|turn>model\n<|channel>thought\n<channel|>   ← secuencia NUNCA vista en training
```

El modelo aprendió a predecir `{response}` directamente después de `<|turn>model\n`. En serving vio `<|turn>model\n<|channel>thought\n<channel|>` — contexto no visto. La literatura (ChatBug 2024) predice degradación severa y silenciosa en este escenario.

Adicionalmente, el bug TRL `assistant_only_loss=True` + `use_liger_kernel=True` (Issue #3781) produce **silent failure**: los `assistant_masks` se descartan y el loss se calcula sobre la secuencia completa incluyendo tokens de usuario y sistema. Si Sprint 6 usó ambos flags, el modelo se entrenó sobre información que no debería haber visto.

### Consecuencia para la interpretación de hiperparámetros

**No podemos atribuir el gap de 12-19 puntos a hiperparámetros subóptimos porque no sabemos cuál era la loss REAL del Sprint 6.** La loss inicial de 10.64 (documentada) podría reflejar el aprendizaje sobre la secuencia completa (masking roto), no solo las respuestas.

**Sprint 7 debe verificar masking ANTES de evaluar hiperparámetros:**
1. Inspeccionar `assistant_masks` en 3 ejemplos post-`train_on_responses_only` — confirmar que tokens de usuario/sistema son −100
2. Verificar que boundary strings coinciden con el template Gemma-4 actualizado (ver I6)
3. Solo después de confirmar masking correcto, interpretar la loss de training como señal válida de aprendizaje

### Tabla de causas actualizada

| Causa root | Gap estimado | ¿Hiperparámetro que lo mitigaría? | ¿Desacoplable? |
|---|---|---|---|
| 0% multi-turn en dataset | −4 a −6 pts | Ninguno — solo datos | No |
| 0.1% persona Q&A | −3.5 a −5.5 pts | Rank más alto, marginalmente | No |
| 22 error strings + 441 artefactos | −2 a −4 pts | Ninguno — solo filtrado | No |
| **Masking roto (train/serve mismatch)** | **desconocido — potencialmente el mayor** | **Ninguno — es un bug de proceso** | **No** |
| Chat template mismatch | −1.5 a −3 pts | Ninguno | No |
| Sistema prompt heterogéneo | −1 a −2 pts | LR bajo preserva señal marginalmente | No |

**Los hiperparámetros son el vector de mejora más pequeño dado el estado actual del sistema.** El orden correcto es: verificar masking → limpiar dataset → elegir hiperparámetros.

---

## A. LoRA Rank — Tabla Comparativa con Citas

### Marco teórico

Para Gemma-4-31B (d_model=3584, 46 capas, 7 módulos target):

| Rank | Parámetros LoRA aprox. | VRAM adicional | Caso de uso |
|---|---|---|---|
| r=4 | ~9.2M | ~74 MB | NLP benchmarks |
| r=8 | ~18.4M | ~148 MB | Style simple, instruction following |
| **r=16** | **~36.8M** | **~295 MB** | **Chat persona — sweet spot actual** |
| r=32 | ~73.6M | ~590 MB | Persona profunda, reasoning-like |
| r=64 | ~147.2M | ~1.2 GB | Full chat assistant (QLoRA Guanaco original) |

### Evidencia empírica por fuente

**[S1] QLoRA (Dettmers et al., 2023 — arXiv:2305.14314)**
Para chat assistant (Guanaco, 9k OASST1, 1 epoch): **r=64**. Para NLP benchmarks: r=4. Cita directa: *"We find that r=4 is typically sufficient for language understanding tasks, while r=64 was used for full chat assistant fine-tuning where model performance was paramount."*
⚠️ El paper canónico para chat SFT usa r=64, NO r=16. Nuestra elección de r=16 es un compromiso de recursos, no una recomendación del paper.

**[S2] arxiv:2512.15634 — "How Much is Too Much? Exploring LoRA Rank Trade-offs" (Dic 2025)**
Evalúa r ∈ {8, 16, 32, 64, 128} sobre Q&A y reasoning benchmarks. Cita directa relevante: *"For recall-based tasks (MMLU, MedMCQA), all ranks achieve almost similar performance. For reasoning tasks (GSM8K, MathQA), intermediate ranks (r = 32–64) offer a balanced operating point between representational capacity and stability, achieving robust performance."*

⚠️ **Nota de interpretación:** El paper NO evalúa style SFT ni persona SFT. La afirmación de que "r=16 es suficiente para style" porque style es análogo a recall es una **interpretación propia** de estos resultados, no una cita directa del paper. Rathore et al. trabajan con Q&A de conocimiento y matemáticas, no con DMs conversacionales de persona.

**[S3] Databricks Blog — "Efficient Fine-Tuning with LoRA" (2024)**
Product description generation: *"r=8 proved sufficient; doubling r does not result in any perceivable increase in output quality."* La mejora real vino de ampliar target modules, no de aumentar rank.

**[S4] Lightning AI — "LoRA Insights from Hundreds of Experiments" (2024)**
*"Training two passes over the 50k dataset produced worse results across all benchmarks vs single-pass."* Dato crítico sobre epochs. Para <15k muestras, r=16-32 es el sweet spot de facto por limitación de los experimentos reportados.

**[S5] Unsloth Documentation — LoRA Hyperparameters Guide (Abr 2026)**
*"Choose r=16 or r=32 as optimal starting points."* Gemma 26B/31B específicamente mencionados.

**[S6] RSLoRA — arxiv:2312.03732 (2023)**
Beneficio material del α/√r scaling solo a r≥128. A r=16-32, resultados mixtos en experimentos reales.

### Decisión de rank

**Decisión Sprint 7: r=16 (mantener) — CON LA CONDICIÓN de que Sprint 7 ya cambia dos variables simultáneamente (masking + dataset). Aislar el efecto del rank requiere Sprint 8.**

Si en Sprint 8 (con masking y datos ya correctos) el composite sigue < 74, entonces r=32 es el siguiente experimento limpio.

---

## B. LoRA Alpha — Análisis y Decisión

### Mecánica del scaling

**ΔW = (α/r) · BA**

| Ratio α/r | Efecto | Quién lo usa |
|---|---|---|
| 0.25 | Muy conservador | **QLoRA paper canónico** (alpha=16 constante, r=64) |
| 1.0 | Neutro | alpha=r |
| 2.0 | Agresivo | **Lightning AI / Unsloth — heurística posterior popular** |

### Corrección de atribución crítica

> ⚠️ **CORRECCIÓN:** La versión anterior afirmaba alpha=2r "según el consenso 2026 y Lightning AI". Esto mezcla dos fuentes con posiciones distintas y omite que QLoRA canónico usa una estrategia opuesta.

**[S1] QLoRA (Dettmers 2023, arXiv:2305.14314):** usa alpha=**16 CONSTANTE** para todos los modelos (7B, 33B, 65B) con r=64. Ratio resultante: 16/64 = **0.25** — muy conservadora. El paper canónico NO prescribe ni menciona la heurística α=2r.

**La heurística α=2r viene de fuentes posteriores:**
- **[S4] Lightning AI (2024):** experimentos propios con Alpaca dataset donde alpha=2r dio mejores resultados en sus condiciones específicas
- **[S5] Unsloth (2026):** menciona alpha=r o alpha=2r como opciones sin prescribir una como universal
- **[S8] ALLoRA (arXiv:2410.09692, Oct 2024):** *"The alpha=2r heuristic is a good practical approximation that can be improved with per-layer adaptation, but remains only an approximation."*

**Mantenemos alpha=32 con r=16 siguiendo la heurística empírica popular de Lightning AI / Unsloth, NO por mandato del QLoRA canónico.** El setting original QLoRA (alpha=16 constante, ratio=1.0 a r=16) sería igualmente válido y más conservador.

**Implicaciones del effective LR:**
- alpha=32, r=16 → effective adapter LR = 2e-4 × 2 = **4e-4**
- alpha=16, r=16 → effective adapter LR = 2e-4 × 1 = **2e-4** (más fiel al QLoRA original)

**Decisión: alpha=32 (mantener) por heurística popular, no por canon.** Si overfit (self-repetition >0.90 o loss <0.15) → reducir alpha a 16.

---

## C. Learning Rate — Análisis y Decisión

| Fuente | LR | Contexto | Relevancia para Iris |
|---|---|---|---|
| **[S1] QLoRA (2023)** | **2e-4** | Guanaco 30B chat, 1 epoch | Alta |
| **[S5] Unsloth (2026)** | **2e-4** (SFT), **5e-6** (DPO/RL) | Normal QLoRA | Alta |
| **[S9] arXiv:2509.20758 (Sep 2025)** | **1e-6** | Domain SFT preservando caps. generales | Baja — contexto diferente |
| [S4] Lightning AI | 3e-4 | Alpaca instruction | Media |

### Análisis de arxiv:2509.20758

Lin et al. (Sep 2025) demuestran que LR=1e-6 domina el Pareto frontier en domain SFT cuando preservar capacidades generales es el objetivo.

**Por qué NO aplica directamente a persona SFT:**
- Su objetivo: preservar math/science generales mientras se aprende dominio médico/comercial
- Nuestro objetivo: cambiar radicalmente cómo habla y actúa el modelo → degradación de "capacidades genéricas" es aceptable

Con LR=1e-6 y 1 epoch sobre 15k muestras: pasos de actualización efectivos insuficientes para internalizar la persona.

**Decisión: LR=2e-4 (mantener).** El sweep proactivo (sección H) incluye Config B con LR=1e-4 para comparar.

---

## D. Epochs — Decisión con Justificación

### Evidencia

**[S4] Lightning AI:** 2 epochs sobre Alpaca 50k = peores resultados en TODOS los benchmarks. Con 15k muestras, el riesgo de overfit en 2 epochs es proporcionalmente mayor.

**[S5] Unsloth:** *"1-3 epochs para instruction datasets; más de 3 = retornos decrecientes + overfit."* El rango es **1-3**, no fijo en 1.

### Justificación para el dataset Sprint 7 específico

| Escenario de dataset | Epochs | Razonamiento |
|---|---|---|
| Dataset original sin limpiar (~9k, ruidoso) | 1 | Ruido visto una sola vez |
| Dataset post-cleanup solo (~7-8k, curado) | **1-2** | Menos ruido → 2 epochs tiene menor riesgo; dataset más pequeño puede justificar segunda pasada |
| Dataset ampliado (15k: DMs+MT+Q&A) | 1 | Más diversidad; 1 epoch cubre distribución |
| Solo subset Q&A persona (200-500 muestras) | 3 | Muy pequeño → necesita más exposición para internalización |

**Razonamiento crítico para Q&A persona:** Con 200-500 muestras de Q&A en un dataset de 15k total, estos ejemplos representan ~3% del dataset. En 1 epoch, el modelo los ve solo una vez. Si B2 sigue bajo post-Sprint 7, considerar **curriculum learning**: 2 epochs solo sobre el subset Q&A en vez de segunda pasada completa (evita reinforcing de errores en los DMs).

**Guardrail:**
- `train_loss < 0.15` al final de epoch 1 → overfit → NO añadir epochs
- `train_loss > 0.80` → underfit → considerar 2 epochs o reducir LR
- `validation_loss` en plateau tras epoch 1 → sin beneficio de añadir epochs

**Decisión Sprint 7: 1 epoch para el full dataset, con opción de 2 epochs si el dataset post-cleanup resulta <5k muestras de alta calidad o si validation loss no converge suficientemente en epoch 1.**

---

## E. Otros Parámetros

| Parámetro | Sprint 6 | Sprint 7 | Fuente | Justificación |
|---|---|---|---|---|
| max_grad_norm | 0.3 | **0.3** | [S1] QLoRA paper | 4-bit: ruido cuantización amplifica gradientes; 0.3 previene spikes (estándar QLoRA, no arbitrario) |
| weight_decay | 0.01 | **0.01** | [S5] Unsloth, [S4] Lightning AI | Estándar AdamW; impacto bajo en PEFT |
| warmup_ratio | 0.03 | **0.05** | [S5] Unsloth (5-10% rango) | Dataset 3 tipos heterogéneos → early steps más variables; warmup más largo mejora estabilidad |
| lora_dropout | 0.05 | **0.05** | [S1] QLoRA (0.05 para 33B) | Unsloth recomienda 0; QLoRA paper valida 0.05 a este tamaño; bajo coste |
| optim | adamw_8bit | **adamw_8bit** | [S1] QLoRA estándar | A100-40GB con margen. Gradient spikes persistentes → paged_adamw_32bit |
| lr_scheduler | cosine | **cosine** | [S4] Lightning AI | Mejora benchmarks vs linear |
| use_rslora | False | **False** | [S6] RSLoRA paper | Sin beneficio material a r≤64 |
| target_modules | 7 all-linear | **7 all-linear** | [S3] Databricks, [S10] Amazon Science | All-linear > attention-only; gains en MLP layers |
| bias | none | **none** | [S5] Unsloth | Faster training |
| seed | 3407 | **3407** | Reproducibilidad | Comparabilidad con Sprint 6 |

---

## F. DPO Hyperparameters — Decisión explícita sobre sí/no

Las investigaciones I2 (Q&A persona) e I3 (adversarial) sugieren DPO en cascada después del SFT para reforzar consistencia de persona y resistencia adversarial.

### Hiperparámetros DPO de referencia

| Parámetro | Valor | Fuente | Diferencia vs SFT |
|---|---|---|---|
| LR | **5e-6** | [S5] Unsloth ("5e-6 para RL/DPO") | 40× más bajo que SFT (2e-4) |
| β (temperatura KL) | **0.1** | Rafailov et al. 2023 (arXiv:2305.18290) | No existe en SFT |
| epochs | **1-2** | Práctica DPO; más epochs → reward hacking | Igual o más conservador que SFT |
| batch size | 4-8 | Práctica DPO | Mayor que SFT (estabilizar el ratio) |
| warmup_ratio | 0.1 | Práctica DPO | Más largo que SFT |
| optim | paged_adamw_32bit | Práctica DPO estabilidad | Más conservador que adamw_8bit |

El **LR=5e-6 en DPO no es un error**: DPO ajusta preferencias sutiles sobre el SFT ya entrenado. LR alto destruiría el aprendizaje de estilo conseguido en la fase SFT. La asimetría LR_SFT >> LR_DPO (factor ~40×) es intencional y documentada.

### Decisión: DPO NO en Sprint 7

**Justificación explícita:**

1. **Masking de Sprint 6 probablemente roto:** El postmortem concluye "NO hacer DPO sobre el SFT actual — el baseline SFT está contaminado. DPO amplificará el ruido, no la señal." Esta conclusión sigue siendo válida para Sprint 7 hasta que el SFT correcto esté validado.

2. **Dataset de preferencias no construido:** DPO requiere pares (chosen, rejected) sobre Q&A persona y adversarial. Este dataset depende de que I2 e I3 estén completos. No podemos hacer DPO sin este trabajo previo.

3. **Variable isolation:** Sprint 7 ya cambia dos variables (masking + dataset). Añadir DPO introduce una tercera variable no desacoplable.

**Condición de activación DPO para Sprint 8:** composite naked ≥ 74 Y (B2 < 50 O J5 < 60) Y dataset I2/I3 construido.

---

## G. Configuración Recomendada Sprint 7

### Config de referencia para train_modal.py

```python
# ============ LORA CONFIG ============
r              = 16              # [S5] sweet spot; [S1] paper canónico usa r=64 para chat
lora_alpha     = 32              # [S4,S8] heurística empírica alpha=2r (NOT QLoRA canon, que usa 16)
lora_dropout   = 0.05            # [S1] QLoRA para 30-65B
bias           = "none"
random_state   = 3407
use_rslora     = False           # [S6] sin beneficio a r=16
target_modules = [               # [S3,S10] all-linear > attention-only
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

# ============ TRAINING CONFIG ============
per_device_train_batch_size  = 2
gradient_accumulation_steps  = 4           # effective batch=8
num_train_epochs             = 1           # [S4] 2 epochs = peores resultados en todos benchmarks
learning_rate                = 2e-4        # [S1,S5] QLoRA/Unsloth default chat SFT
lr_scheduler_type            = "cosine"    # [S4] mejora vs linear
warmup_ratio                 = 0.05        # [S5] ↑ de 0.03; dataset multi-tipo más heterogéneo
optim                        = "adamw_8bit"
weight_decay                 = 0.01
max_grad_norm                = 0.3         # [S1] QLoRA para 4-bit; previene gradient spikes
```

**PREREQUISITO BLOQUEANTE antes de lanzar:** verificar masking correcto (§ Contexto) y template Gemma-4 alineado (I6). Si la verificación falla, NO lanzar el training.

### Cambios vs Sprint 6

| Parámetro | Sprint 6 | Sprint 7 | Motivo |
|---|---|---|---|
| warmup_ratio | 0.03 | **0.05** | Dataset 3 tipos heterogéneos |
| Dataset | 9.272 samples, 0% MT, ruidoso | ~12-15k: DMs limpios + 5-10k MT + 200-500 Q&A | Fixes postmortem E1-E5 |
| Masking/template | Probablemente roto | **Verificado previamente (I6)** | Fix proceso crítico |
| Todo lo demás | — | Sin cambio | Validado empíricamente |

---

## H. Sweep Proactivo (antes del training completo)

> **CAMBIO vs versión anterior:** El sweep no es reactivo ("si composite <69"). Con un dataset radicalmente distinto al Sprint 6, se validan los hiperparámetros ANTES del training completo sobre un validation set.

### Protocolo

1. Separar 10% del dataset como validation set (estratificado: DMs / multi-turn / Q&A persona)
2. Entrenar las 3 configs durante solo **50% del total de steps** sobre el 90% restante
3. Comparar por validation loss + métrica surrogate de estilo (A1 length match rápido)
4. Entrenar al completo solo la config ganadora

### Las 3 configs

**Config A — Sprint 6 baseline corregido**
```python
r=16, lora_alpha=32, learning_rate=2e-4, num_train_epochs=1
```
Hipótesis: Con masking correcto y datos limpios, los hiperparámetros originales deberían dar composite >74. Si no superan 69, el problema es estructural, no de hiperparámetros.

**Config B — More capacity, lower LR, more exposure**
```python
r=32, lora_alpha=64, learning_rate=1e-4, num_train_epochs=2
```
Hipótesis: [S2] r=32-64 para reasoning-like tasks (B2, J5). [S9] LR más bajo preserva capacidades generales. 2 epochs para más exposición al subset Q&A persona (~3% del dataset).

**Config C — Minimal capacity, more epochs**
```python
r=8, lora_alpha=16, learning_rate=2e-4, num_train_epochs=3
```
Hipótesis: [S3] Databricks confirma r=8 suficiente para style. 3 epochs compensan la menor capacidad. Si B2/J5 mejoran igual con r=8, Sprint 8 entrena más rápido y barato.

### Métrica de selección

| Métrica | Peso | Cómo medir |
|---|---|---|
| Validation loss | 40% | Directo del trainer |
| A1 length match surrogate | 30% | Longitud media generada vs. media de Iris en validation set |
| Perplexity en 20 prompts conocidos | 30% | `model.generate()` + log-perplexity manual |

Si dos configs están dentro del 5% → elegir la más simple (menor rank, menos epochs).

---

## I. Riesgos de Cada Decisión

| Decisión | Riesgo | Probabilidad | Mitigación |
|---|---|---|---|
| r=16 | Insuficiente capacidad para B2/J5 incluso con datos correctos | Baja-Media | Sweep Config B (r=32) antes del full training |
| alpha=32 (heurística popular) | Sobreescribir capacidades generales | Media | Monitorear H1 naked y S3 naked; si H1 <72 o S3 <58 → alpha=16 |
| LR=2e-4 | Loss spike en early steps | Baja (max_grad_norm=0.3 actúa de firewall) | Si loss >3.0 en primeros 100 steps → reducir a 1e-4 |
| 1 epoch | Subaprendizaje de Q&A persona (3% del dataset, vista una vez) | Media | Curriculum option: 2 epochs solo sobre subset Q&A si B2 <40 post-training |
| NO hacer DPO | Gap en B2/J5 persiste después de SFT correcto | Media | Activar DPO Sprint 8 con pares I2/I3 si composite ≥74 pero B2 <50 o J5 <60 |
| Sweep proactivo | Coste extra (~1.5× un run completo) | N/A — es por diseño | Justificado vs. coste de run completo fallido por hiperparámetros subóptimos |
| Masking no verificado | Repeat del fallo silencioso Sprint 6 | Alta si se salta | **BLOQUEAR el training si la verificación de masking falla** |

---

## Resumen Ejecutivo

**Sprint 7 no es un sprint de hiperparámetros. Es un sprint de proceso y datos.**

El único cambio justificado en hiperparámetros respecto a Sprint 6 es `warmup_ratio: 0.03 → 0.05`.

Los cambios imprescindibles son de proceso: verificar masking, alinear template Gemma-4 (I6), construir dataset limpio (I1-I3).

**DPO:** NO en Sprint 7. Condición de activación para Sprint 8: composite naked ≥ 74 AND (B2 <50 OR J5 <60) AND dataset I2/I3 construido.

**Sweep:** proactivo (3 configs × 50% steps sobre validation set) antes del training completo.

### Fuentes citadas

| ID | Source | Hallazgo clave |
|---|---|---|
| S1 | QLoRA (Dettmers 2023, arXiv:2305.14314) | r=64 para chat; alpha=16 CONSTANTE (no α=2r); max_grad_norm=0.3; LR=2e-4 |
| S2 | arXiv:2512.15634 (Dic 2025) | Cita directa: r=32-64 para reasoning; r=16 para style es **interpretación** |
| S3 | Databricks Blog (2024) | r=8 suficiente para style; all-linear > attention-only |
| S4 | Lightning AI Experiments (2024) | 1 epoch > 2; alpha=2r heurística empírica; cosine scheduler |
| S5 | Unsloth Docs (2026) | r=16-32; warmup 5-10%; LR=2e-4 SFT, 5e-6 DPO; rango 1-3 epochs |
| S6 | RSLoRA (arXiv:2312.03732) | Beneficio material solo a r≥128 |
| S7 | Lightning AI alpha study | alpha=2r empíricamente óptimo en Alpaca (heurística, no universal) |
| S8 | ALLoRA (arXiv:2410.09692, Oct 2024) | alpha=2r es buena aproximación, no mandato |
| S9 | arXiv:2509.20758 (Sep 2025) | LR=1e-6 preserva caps. generales — contexto domain SFT, no persona SFT |
| S10 | Amazon Science Blog (2024) | all-linear > attention-only; gains principalmente en MLP layers |
| — | Rafailov et al. 2023 (arXiv:2305.18290) | DPO β=0.1 default |
| — | ChatBug 2024 | Chat template mismatch → degradación severa silenciosa |

---

*Revisado fin de Sesión 4 | 2026-04-25 | research/hyperparams-sft*
*Correcciones aplicadas: (1) DOS fallos Sprint 6 no desacoplables; (2) alpha attribution corregida — QLoRA usa alpha=16 constante, α=2r es heurística posterior; (3) sección DPO añadida con decisión explícita; (4) sweep proactivo no reactivo; (5) epochs range 1-3, no fijo en 1; (6) cita de rank marcada como interpretación*
