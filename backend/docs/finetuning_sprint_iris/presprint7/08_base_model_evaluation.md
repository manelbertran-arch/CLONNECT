# I8: Evaluación Modelo Base — Sprint 7

**Fecha:** 2026-04-25
**Autor:** Claude Opus 4.6 + Manel Bertran
**Decisión requerida:** Mantener Gemma4-31B-it o cambiar a modelo alternativo
**Contexto:** Composite actual 66 vs techo 78-85, Sprint anterior con Gemma4-31B-it sobre Iris (catalán + español + code-switching bilingüe)

---

## A. Inventario de Modelos Candidatos

### Tier 1 — Caben cómodamente en A100-80GB con QLoRA

| # | Modelo | Params | Arquitectura | VRAM QLoRA (4-bit) | Licencia | Release | Multilingüe |
|---|--------|--------|--------------|--------------------|----------|---------|-------------|
| 1 | **Gemma 4 31B-it** (actual) | 31B dense | Hybrid local/global attention, p-RoPE, 256K ctx | ~22 GB | Apache 2.0 | Mar 2026 | 140+ langs, ES decente, CA más débil |
| 2 | **Qwen3-32B** | 32B dense | Transformer, 128K ctx, thinking/non-thinking | ~20 GB | Apache 2.0 | May 2025 | **119 langs incl. ES + CA explícito** |
| 3 | **Qwen3.6-27B** | 27B dense | Hybrid Gated DeltaNet + Attention, 262K ctx | ~18 GB | Apache 2.0 | 22 Abr 2026 | **201 langs; ES + CA confirmado** |
| 4 | **Llama 3.3 70B** | 70B dense | GQA, 128K ctx | ~46 GB | Llama Community | Dec 2024 | 8 langs; ES sí, CA débil |
| 5 | **Phi-4 14B** | 14B dense | Transformer estándar | ~10 GB | MIT | Dec 2024 | English-centric; ES limitado, CA nulo |

### Tier 2 — Caben pero con limitaciones o riesgos MoE

| # | Modelo | Total / Activos | Arquitectura | VRAM QLoRA | Licencia | Release | Nota |
|---|--------|-----------------|--------------|------------|----------|---------|------|
| 6 | **Llama 4 Scout** | 109B / 17B activos | MoE 16 expertos | ~71 GB (justo) | Llama 4 Community | Abr 2025 | QLoRA MoE inestable; bf16 LoRA recomendado |
| 7 | **Mistral Small 4** | 119B / 6B activos | MoE 128 expertos, 4 activos, 256K ctx | Cabe con QLoRA | Apache 2.0 | Mar 2026 | Solo 6B activos — poca capacidad para persona |
| 8 | **gpt-oss-120b** (OpenAI) | 117B / 5.1B activos | MoE, MXFP4 nativo | ~65 GB | Apache 2.0 | Ago 2025 | English-dominant; 5.1B activos insuficiente |

### Tier 3 — NO caben en 1x A100-80GB

| Modelo | Total / Activos | Por qué NO cabe | Licencia |
|--------|-----------------|------------------|----------|
| DeepSeek V3 | 671B / 37B | ~370 GB Q4, mínimo 8x A100 | MIT |
| DeepSeek V4-Pro | 1.6T / 49B | Multi-nodo obligatorio | MIT |
| Mistral Large 3 | 675B / 41B | ~370 GB Q4, 8x H100 mínimo | Apache 2.0 |
| Llama 4 Maverick | 400B / 17B | 128 expertos → modelo completo en memoria | Llama 4 |
| Command R+ | 104B dense | Non-commercial (CC-BY-NC) → **descalificado** | CC-BY-NC |
| GLM-5.1 | 744B / 40B | ~400 GB+ Q4 | MIT |

**Veredicto Tier:** Solo Tier 1 es viable para Sprint 7. Tier 2 introduce riesgo MoE sin beneficio claro (params activos <= 17B). Tier 3 fuera de alcance.

---

## B. Análisis Multilingüe (Catalán / Español) por Modelo

### B.1 Estado del catalán en LLMs — realidad 2026

El catalán está **significativamente infrarrepresentado** vs español:
- Math reasoning en catalán es **3-4x peor** que en español en TODOS los modelos
- No existe benchmark de code-switching CA-ES (gap en la literatura)
- MGSM catalán: mejor modelo (Qwen2.5-7B) obtiene 0.096 vs 0.390 en español

### B.2 Benchmarks IberoBench — Comparación directa CA vs ES (0-shot)

**Lectura comprensiva (Belebele):**

| Modelo | Catalán | Español | Delta CA-ES |
|--------|---------|---------|-------------|
| Gemma 2-9B | **0.894** | **0.892** | +0.002 |
| Mistral Small 3-24B | 0.880 | 0.891 | -0.011 |
| Qwen2.5-7B | 0.799 | 0.833 | -0.034 |
| Llama 3.1-8B | 0.638 | 0.690 | -0.052 |
| Salamandra-7B-it (BSC) | 0.674 | 0.652 | +0.022 |

**Parafraseo (PAWS):**

| Modelo | Catalán | Español |
|--------|---------|---------|
| Mistral Small 3-24B | **0.706** | 0.663 |
| Gemma 2-9B | 0.679 | 0.669 |
| Qwen2.5-7B | 0.664 | 0.651 |
| Llama 3.1-8B | 0.655 | 0.652 |

**Detección ironía/sarcasmo (IroSvA, F1) — proxy relevante para persona:**

| Modelo | Catalán | Español |
|--------|---------|---------|
| Mistral Small 3-24B | **0.523** | 0.517 |
| Qwen2.5-7B | 0.490 | 0.500 |
| Gemma 2-9B | 0.467 | 0.466 |
| Llama 3.1-8B | 0.383 | 0.410 |

**Traducción (FLORES, BLEU):**

| Modelo | Catalán | Español |
|--------|---------|---------|
| Mistral Small 3-24B | **0.301** | 0.237 |
| Gemma 2-9B | 0.290 | 0.233 |
| Qwen2.5-7B | 0.195 | 0.193 |

### B.3 Benchmarks multilingüe de escala (modelos 30B+)

| Benchmark | Gemma 4 31B | Qwen3-32B (thinking) | Llama 3.3 70B |
|-----------|-------------|----------------------|----------------|
| MMMLU (multilingual avg) | **88.4%** | — | — |
| MMLU Pro (inglés) | 85.2% | 72.8% | 68.9% |
| MGSM (multilingual math) | — | — | **91.1%** |
| MMLU-ProX español | — | **72.8%** | — |

**Nota crítica sobre Qwen y catalán:** Qwen3-32B entrena explícitamente en 119 idiomas que incluyen catalán. Gemma 4 dice "140+ idiomas" pero sin confirmación explícita del nivel de cobertura catalana. La familia Qwen tiene el soporte multilingüe más diverso en este rango de parámetros.

**Caveat (post-review):** El claim "Qwen incluye catalán explícitamente" proviene del blog Qwen ("119 languages") pero la lista detallada de idiomas no se ha verificado en el paper técnico. El HuggingFace model card dice "100+". **Verificación recomendada antes de CCEE:** probar Qwen3-32B con 5-10 prompts en catalán coloquial (estilo Iris) y comparar coherencia/fluidez vs español. Si catalán falla notablemente → no evaluar más, mantener Gemma4.

### B.4 La Leaderboard (ACL 2025) — Catalán específico

Top performers para catalán en el subset de La Leaderboard (18 datasets CA):
- Gemma-2-9B (base e instruct) — líder consistente
- Qwen-2.5-IT 14B y 32B — competitivo
- EuroLLM-9B — top-3 en QA y razonamiento catalán

**Dato clave:** En los benchmarks disponibles (7-9B), la familia Gemma lidera en catalán general, pero la familia Qwen domina en benchmarks multilingüe a escala y tiene cobertura explícita de catalán en datos de entrenamiento.

### B.5 Modelos específicos catalán (BSC)

Salamandra-7B-it (Barcelona Supercomputing Center):
- Optimizado para catalán → xnli_ca 57.04 vs Qwen 49.8
- Pero solo 7B params, por debajo de Gemma/Qwen en tareas generales
- **No viable como base para fine-tuning de persona** — demasiado pequeño, sin instruct-tuning robusto

---

## C. Análisis Técnico — Compatibilidad de Stack

### C.1 Matriz de compatibilidad completa

| | QLoRA+bnb | Unsloth | vLLM | Modal A100 | TRL/PEFT | HF Inference |
|---|---|---|---|---|---|---|
| **Gemma 4 31B** | SI | SI (1.5x, -60% VRAM) | SI (day-0) | SI | SI | SI |
| **Qwen3-32B** | SI | SI | SI | SI | SI | SI (DeepInfra/Together) |
| **Qwen3.6-27B** | SI | SI | SI (vllm>=0.19) | SI | SI | Pendiente (muy nuevo) |
| **Llama 3.3 70B** | SI (justo) | SI (2x, -70% VRAM) | SI | SI | SI | SI |
| **Phi-4 14B** | SI | SI | SI | SI | SI | SI |

**Todos los candidatos Tier 1 son full-compatible con el stack actual.**

### C.2 VRAM budget detallado en A100-80GB

```
Componente              Gemma4-31B    Qwen3-32B     Llama3.3-70B
─────────────────────────────────────────────────────────────────
Modelo base (NF4)       ~15.5 GB      ~16.0 GB      ~35.0 GB
LoRA adapters (r=64)     ~0.4 GB       ~0.4 GB       ~0.8 GB
Optimizer (8-bit AdamW)  ~1.5 GB       ~1.5 GB       ~2.5 GB
Activaciones (bs=2)      ~6-8 GB       ~6-8 GB       ~8-12 GB
Gradientes               ~0.5 GB       ~0.5 GB       ~1.0 GB
CUDA overhead            ~2-3 GB       ~2-3 GB       ~2-3 GB
─────────────────────────────────────────────────────────────────
TOTAL estimado           ~26-29 GB     ~27-30 GB     ~49-54 GB
Headroom libre           ~51-54 GB     ~50-53 GB     ~26-31 GB
─────────────────────────────────────────────────────────────────
Veredicto                HOLGADO       HOLGADO       FACTIBLE (bs=1-2)
```

Con Unsloth (60-70% reducción):

```
Con Unsloth             Gemma4-31B    Qwen3-32B     Llama3.3-70B
─────────────────────────────────────────────────────────────────
VRAM real               ~22 GB        ~20-24 GB     ~36-42 GB
Max context (bs=1)      40K+ tokens   40K+ tokens   ~6.9K (vanilla), 89K (Unsloth)
```

### C.3 Alertas técnicas

1. **vLLM deprecando bitsandbytes** para inferencia (RFC #39583). Impacto: para serving en producción, usar AWQ/GPTQ en vez de bnb. NO afecta a training.
2. **Script actual usa A100-40GB** (`train_modal.py` línea 42). Con r=64 y batch=2, Gemma4-31B necesita A100-80GB. Cambiar a `gpu="A100-80GB"`.
3. **Qwen3.5-27B** tiene quantization degradation conocida — QLoRA NO recomendado (Unsloth docs). Qwen3.6-27B hereda el riesgo.

### C.4 Integración con Clonnect actual

Qwen3-32B ya está en producción:
- `llm_models.py:38` → `DEEPINFRA_MODEL = "Qwen/Qwen3-32B"`
- `llm_models.py:43` → `TOGETHER_MODEL = "Qwen/Qwen3-32B"`
- Inferencia confirmada funcionando en DeepInfra y Together

Esto significa: si el modelo fine-tuned es Qwen3-32B, el serving de producción ya tiene path validado.

### C.5 TRL Auto-patch Advantage (añadido post-review)

**Hallazgo crítico de la revisión:** TRL tiene auto-patching del chat template para `assistant_only_loss=True` en familias known. Modelos soportados (TRL docs, `get_training_chat_template()`):

> DeepSeek-V3, GPT-OSS, LLaMA 3, Qwen2.5, **Qwen3**

**Gemma4 NO está en esta lista.**

| Aspecto | Gemma4 (actual) | Qwen3 (challenger) |
|---|---|---|
| `{% generation %}` keywords | Ausentes (descubierto Sesión 1) | Auto-patcheado por TRL |
| Chat template | `<\|turn>model\n<\|channel>thought\n<channel\|>` (complejo) | `<\|im_start>assistant\n` (simple) |
| Tokens nuevos en template | Sí (`<\|channel>`) | No |
| Patches manuales requeridos | Sí (Opción C de Sesión 6) | No |
| Compat TRL `assistant_only_loss` | Manual | Auto-patch |
| Bug surface en Sprint 7 | **ALTA** | **BAJA** |

**Implicación directa:** Cambiar a Qwen3 elimina toda la complejidad de Sesión 6 (Opción C, CHANNEL_PREFIX, scripts de verificación, bug Unsloth strip_thinking). El bug central de Sprint 6 (#1 masking roto, #2 chat template mismatch) simplemente desaparece con Qwen3.

Fuente: HuggingFace TRL docs — `sft_trainer.md`, función `get_training_chat_template()`.

### C.6 Thinking Mode Qwen3 (añadido post-review)

Qwen3 también tiene thinking mode: genera bloques `<think>...</think>` antes de la respuesta. Para Iris (DM social), thinking es innecesario y potencialmente perjudicial (latencia, tokens basura, riesgo de fuga de razonamiento interno).

**Recomendación:** thinking OFF, consistente con la decisión Gemma4 `enable_thinking=False`.

```python
tokenizer.apply_chat_template(messages, enable_thinking=False)
```

En Qwen3, `enable_thinking=False` activa el modo `/no_think`: el modelo responde directamente sin bloques `<think>`. Verificar que los outputs del smoke test no contengan tags `<think>` antes de proceder al training completo.

### C.7 Modal A100-80GB — Confirmación (añadido post-review)

**Por qué A100-80GB y no A100-40GB:**
- Modelo base NF4 (~16 GB) + LoRA adapters + optimizer + activaciones + gradientes = ~27-30 GB
- A100-40GB deja solo ~10-13 GB de headroom — insuficiente para batch_size=2 + seq_len=2048 con gradients
- A100-80GB deja ~50 GB de headroom — cómodo para experimentar batch/context/rank

Ambos modelos (Gemma4 y Qwen3) necesitan A100-80GB para training con r=32+ y batch=2. El coste Modal es idéntico (Modal puede auto-upgrade 40GB→80GB al mismo precio).

---

## D. Análisis Cualitativo — Persona Modeling

### D.1 Benchmarks de persona existentes

**PersonaGym (EMNLP 2025):** 200 personas, 10K preguntas, 5 métricas (1-5):

| Modelo | Linguistic Habits | Persona Consistency | PersonaScore |
|--------|-------------------|---------------------|-------------|
| GPT-4.5 | 4.14 | 4.70 | **4.51** |
| LLaMA-3-8b | 3.97 | 4.77 | **4.49** |
| DeepSeek-V3 | **4.26** | 4.66 | **4.48** |
| LLaMA-3.3-70b | 3.92 | 4.56 | **4.36** |

**Hallazgo clave:** Linguistic Habits es la dimensión más débil universalmente. El tamaño del modelo NO predice linealmente la calidad de persona — LLaMA-3-8b empata con GPT-4.5 en PersonaScore.

**OpenCharacter (2025):** Fine-tuning de 8B en datos de persona **supera a GPT-4o** en todos los escenarios:

| Modelo | Expected Action | Linguistic Habits | PersonaScore |
|--------|-----------------|-------------------|-------------|
| LLaMA-3 70B Instruct | 4.73 | 4.38 | **4.72** |
| OpenCharacter-8B (fine-tuned) | 4.70 | 4.32 | **4.66** |
| gpt-4o | 4.81 | 3.75 | **4.60** |

**Implicación directa para Clonnect:** El fine-tuning de un modelo mediano (8-32B) en datos de persona específicos es la estrategia correcta. El modelo base importa menos que la calidad del dataset y el proceso de fine-tuning.

**TwinVoice (2025):** Persona Tone y Memory Recall son los bottlenecks más difíciles. Lexical Fidelity y Opinion Consistency son los puntos fuertes. Incluso GPT-5 solo logra 2.13/5 en generative persona score.

### D.2 Relevancia para Iris específicamente

Los desafíos de Iris son:
1. **Code-switching CA-ES** — requiere modelo con representación fuerte de ambos idiomas
2. **Estilo casual informal** — abreviaciones, emojis, sin puntuación formal
3. **Tone consistency** — mantener personalidad a lo largo de conversación
4. **Vocabulario catalán coloquial** — no formal/literario

De estos, (1) favorece **Qwen** (cobertura explícita CA+ES) sobre Gemma (CA implícito). Los puntos (2-4) dependen más del dataset SFT que del modelo base, como confirma OpenCharacter.

### D.3 Code-switching — gap en la literatura

**No existe benchmark publicado para code-switching CA-ES en LLMs.** LinCE cubre ES-EN, HI-EN, NE-EN pero no CA-ES. CALCS 2025 no produjo benchmark CA-ES. Esto significa:

- No podemos comparar modelos en code-switching con benchmarks externos
- Nuestro CCEE v5 es el único evaluador disponible para esta capacidad
- La decisión se basa en proxy (cobertura de entrenamiento en CA y ES) más que en evidencia directa

---

## E. Comparación Head-to-Head: Gemma4-31B vs Alternativas

### E.1 Gemma 4 31B — Strengths

| Dimensión | Evaluación | Evidencia |
|-----------|------------|-----------|
| Capacidad general | Excelente | MMMLU 88.4% (#16 global), MMLU Pro 85.2% |
| Español | Fuerte | 140+ langs, MMMLU implica buen ES |
| Catalán | Medio-bajo | No confirmado explícitamente; familia Gemma2-9B lidera Belebele CA pero no extrapolable a 31B |
| Stack compatibility | Perfecto | Unsloth day-0, vLLM, config existente |
| Riesgo migración | **Cero** | Ya configurado en `02_sft_config.py` y `train_modal.py` |
| Contexto | 256K nativo | Sobrado para producción (~16K) |

### E.2 Qwen3-32B — Strengths

| Dimensión | Evaluación | Evidencia |
|-----------|------------|-----------|
| Capacidad general | Muy buena | MMLU-ProX ES 72.8% (thinking), TRL reference model |
| Español | Fuerte | 119 langs, MMLU-ProX medido directamente |
| Catalán | **Mejor que Gemma** | Entrenamiento explícito en 119 langs incluyendo catalán |
| Stack compatibility | Perfecto | Unsloth, vLLM, TRL; ya en producción Clonnect |
| Riesgo migración | **Bajo** | Config similar, chat template distinto |
| Thinking modes | Ventaja única | Non-thinking mode = respuestas directas sin razonamiento (ideal para persona DM) |
| TRL auto-patch | **Ventaja estructural** | `assistant_only_loss` funciona out-of-the-box (sección C.5) |
| Contexto | 128K | Suficiente para producción |

### E.3 Qwen3.6-27B — Strengths and Risks

| Dimensión | Evaluación | Evidencia |
|-----------|------------|-----------|
| Calidad/param | Potencialmente la mejor | Supera Qwen3.5-397B MoE en coding benchmarks |
| Catalán | Excelente (201 langs) | Cobertura máxima |
| **RIESGO CRÍTICO** | Alto | Lanzado hace 3 días (22 Abr 2026), QLoRA no validado comunidad, posible degradación quantización heredada de Qwen3.5 |

### E.4 Llama 3.3 70B — Strengths and Weaknesses

| Dimensión | Evaluación | Evidencia |
|-----------|------------|-----------|
| Capacidad bruta | La más alta del grupo | 70B dense, MGSM multilingual 91.1% |
| Español | Bueno | 1 de 8 idiomas oficiales |
| Catalán | **Débil** | NO en los 8 idiomas oficiales |
| VRAM | **Justo** | 46-54 GB QLoRA, bs=1-2 máximo |
| Riesgo migración | **Medio** | Funciona pero sin margen para experimentar batch/context |
| Licencia | Restrictiva vs Apache | Llama Community License (< 700M MAU) |

### E.5 Scoring comparativo (0-10) — actualizado post-review

| Criterio (peso) | Gemma4-31B | Qwen3-32B | Qwen3.6-27B | Llama3.3-70B |
|-----------------|------------|-----------|-------------|--------------|
| Catalán (20%) | 6 | **8** | **9** | 4 |
| Español (10%) | 8 | **8** | 8 | 7 |
| Code-switching proxy (10%) | 6 | **8** | **9** | 4 |
| Bug surface / TRL compat (15%) | 4 | **10** | 7 | 8 |
| VRAM headroom (10%) | **9** | **9** | **10** | 5 |
| Stack compat (10%) | **10** | **10** | 7 | 9 |
| Riesgo migración inv. (10%) | **10** | 8 | 4 | 6 |
| Persona capacity (10%) | 8 | 8 | 7 | **9** |
| Licencia (5%) | **10** | **10** | **10** | 7 |
| **TOTAL PONDERADO** | **7.30** | **8.65** | **7.55** | **6.10** |

Cambio vs versión original: se añadió "Bug surface / TRL compat" (15%) redistribuyendo peso de Catalán (25→20%), Español (15→10%), Code-switching (15→10%). Gemma4 baja de 7.75→7.30 por la penalización de bug surface. Qwen3-32B sube de 8.35→8.65.

---

## F. Recomendación Final

### Decisión: Evaluar ambos en paralelo. Qwen3-32B como default a menos que Gemma4 lo supere claramente.

**Confianza: MEDIA-ALTA (75%)**

Justificación:

1. **Qwen3-32B tiene ventaja estructural en catalán:** cobertura explícita en datos de entrenamiento vs implícita en Gemma4. Para Iris, que escribe 40-60% en catalán con code-switching, esto es material.

2. **Qwen3-32B tiene ventaja estructural en bug surface:** TRL auto-patch para `assistant_only_loss` (sección C.5). Elimina toda la complejidad de Sesión 6 — Opción C, CHANNEL_PREFIX, scripts verificación, bug strip_thinking. El masking funciona out-of-the-box.

3. **El coste de evaluación es bajo:** misma VRAM (~20 vs ~22 GB), mismo stack (Unsloth + TRL + vLLM), Qwen ya en producción Clonnect. La migración del config es ~30 minutos.

4. **El coste de NO evaluar es potencialmente alto:** si el techo del composite está parcialmente limitado por la capacidad base en catalán, el gap 66 → 78 podría no cerrarse solo con mejor SFT.

5. **Gemma4 no se abandona:** es el modelo de control. Si Gemma4 supera a Qwen3 significativamente, mantenerlo justifica asumir la complejidad extra.

### Estrategia concreta:

```
FASE 1:  SFT Gemma4-31B (plan actual, ya configurado)
         → CCEE v5 → Composite_Gemma

FASE 1B: SFT Qwen3-32B (config paralelo, cambios mínimos)
         → CCEE v5 → Composite_Qwen

GATE (recalibrado post-review):
  Qwen3 es DEFAULT dado menor bug surface (TRL auto-patch + chat template simple).
  
  - Gemma4 - Qwen3 > +2.0 puntos → mantener Gemma4 (justifica la complejidad extra)
  - Gemma4 - Qwen3 < +2.0 puntos → adoptar Qwen3 (menor bug surface gana)
  - Qwen3 > Gemma4             → adoptar Qwen3 (winner técnico Y estructural)
```

**Justificación del gate invertido:** El coste estructural de mantener Gemma4 (patches manuales de chat template, riesgo de bugs ocultos en masking, menor cobertura TRL oficial) es un coste continuo que no aparece en el composite pero afecta la fiabilidad del sprint. Qwen3 solo pierde si Gemma4 demuestra superioridad clara (+2.0 pp) que compense ese coste.

### Por qué NO las otras opciones:

- **Qwen3.6-27B:** Demasiado nuevo (3 días). Sin validación comunitaria de QLoRA. Posible degradación de quantización heredada de Qwen3.5. **Revisitar en Sprint 8** cuando haya datos.
- **Llama 3.3 70B:** Catalán débil (no es idioma oficial), VRAM justa (sin margen experimental), licencia más restrictiva. El beneficio de 70B dense no compensa para un caso bilingüe CA-ES.
- **Phi-4 14B:** Demasiado pequeño y English-centric.
- **MoE (Scout, Mistral Small 4, gpt-oss):** Params activos 5-17B insuficientes para absorción de persona. Fine-tuning MoE inestable con QLoRA.

---

## G. Plan de Migración: Gemma4 → Qwen3-32B (si aplica)

### G.1 Cambios en `02_sft_config.py`

```python
# ANTES (Gemma4)
MODEL_NAME = "unsloth/gemma-4-31B-it"
chat_template = "gemma-4-thinking"
instruction_part = "<|turn>user\n"
response_part = "<|turn>model\n"
enable_thinking = False

# DESPUÉS (Qwen3)
MODEL_NAME = "unsloth/Qwen3-32B"
chat_template = "qwen3"
instruction_part = "<|im_start|>user\n"
response_part = "<|im_start|>assistant\n"
enable_thinking = False  # /no_think mode para persona DM
```

### G.2 Cambios en `train_modal.py`

```python
# Línea 42: A100-40GB → A100-80GB (necesario para r=64 en ambos modelos)
gpu="A100-80GB"

# Línea 54: MODEL_NAME
MODEL_NAME = "unsloth/Qwen3-32B"

# Línea 81: chat_template
tokenizer = get_chat_template(tokenizer, chat_template="qwen3")

# Líneas 128-129: train_on_responses_only markers
trainer = train_on_responses_only(
    trainer,
    instruction_part="<|im_start|>user\n",
    response_part="<|im_start|>assistant\n",
)
```

### G.3 Cambios en inferencia/serving

- DeepInfra: ya desplegado como `Qwen/Qwen3-32B` — reutilizar endpoint existente
- Si fine-tuned custom: deploy LoRA adapter sobre Qwen3-32B base en Modal/vLLM
- Quantización para serving: AWQ o GPTQ (no bitsandbytes — deprecándose en vLLM)

### G.4 Esfuerzo estimado

| Tarea | Tiempo |
|-------|--------|
| Adaptar SFT config | 30 min |
| Test run (100 steps) para validar setup | 2h (incluye download modelo) |
| SFT completo Qwen3-32B | 4-8h (similar a Gemma4) |
| CCEE evaluation | 2h |
| **Total incremental** | **~1 día** |

---

## H. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Qwen3-32B no mejora catalán vs Gemma4 | Media (40%) | Bajo — volvemos a Gemma4 | A/B test con CCEE; decisión basada en datos |
| Chat template Qwen causa problemas con dataset | Baja (15%) | Medio | Test run 100 steps antes de full train |
| Qwen3-32B thinking mode interfiere con persona | Baja (20%) | Alto | `enable_thinking=False` + verificar outputs sin `<think>` tags |
| A100-80GB no disponible en Modal al momento de entrenar | Baja (10%) | Alto | Reservar con anticipación; fallback H100 |
| Overfit diferente en Qwen (curva loss distinta) | Media (30%) | Medio | Monitorizar loss curve; comparar con Gemma4 baseline |
| Qwen3.6 supera a Qwen3 semanas después | Media (50%) | Bajo | Aceptado; evaluar en Sprint 8 |
| vLLM depreca bnb antes de terminar sprint | Muy baja (5%) | Bajo | Solo afecta inference, no training; usar AWQ |
| Claim "catalán explícito" en Qwen no se confirma | Baja (20%) | Medio | Pre-flight: 5-10 prompts CA coloquial antes de CCEE |

---

## I. Fuentes

### Modelos y specs
1. [Gemma 4 31B-it HuggingFace](https://huggingface.co/google/gemma-4-31B-it)
2. [Qwen3-32B HuggingFace](https://huggingface.co/Qwen/Qwen3-32B)
3. [Qwen3.6-27B HuggingFace](https://huggingface.co/Qwen/Qwen3.6-27B)
4. [Llama 3.3 70B HuggingFace](https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct)
5. [Mistral Small 4 HuggingFace](https://huggingface.co/mistralai/Mistral-Small-4-119B-2603)
6. [gpt-oss-120b HuggingFace](https://huggingface.co/openai/gpt-oss-120b)
7. [DeepSeek V4-Pro HuggingFace](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro)

### Benchmarks multilingüe
8. [IberBench: LLM Evaluation on Iberian Languages (2025)](https://arxiv.org/html/2504.16921)
9. [IberoBench (COLING 2025)](https://aclanthology.org/2025.coling-main.699/)
10. [La Leaderboard (ACL 2025)](https://aclanthology.org/2025.acl-long.1561/)
11. [MMLU-ProX Multilingual Benchmark](https://mmluprox.github.io/)
12. [MMMLU Leaderboard](https://llm-stats.com/benchmarks/mmmlu)
13. [CatalanBench (EleutherAI lm-evaluation-harness)](https://github.com/EleutherAI/lm-evaluation-harness/pull/2154)
14. [Salamandra Technical Report](https://arxiv.org/pdf/2502.08489)

### Persona/Style benchmarks
15. [PersonaGym (EMNLP 2025)](https://arxiv.org/html/2407.18416)
16. [OpenCharacter (2025)](https://arxiv.org/html/2501.15427v1)
17. [TwinVoice Benchmark](https://arxiv.org/html/2510.25536v1)
18. [BehaviorChain (ACL 2025)](https://aclanthology.org/2025.findings-acl.813.pdf)

### Stack técnico
19. [Unsloth Supported Models](https://unsloth.ai/docs/get-started/unsloth-model-catalog)
20. [Unsloth Gemma 4 Fine-tuning Guide](https://unsloth.ai/docs/models/gemma-4/train)
21. [vLLM Supported Models](https://docs.vllm.ai/en/latest/models/supported_models/)
22. [vLLM RFC: Deprecate bitsandbytes](https://github.com/vllm-project/vllm/issues/39583)
23. [Modal GPU Docs & Pricing](https://modal.com/docs/guide/gpu)
24. [TRL v1.0 Release](https://huggingface.co/blog/trl-v1)
25. [GPU Requirements Cheat Sheet 2026](https://www.spheron.network/blog/gpu-requirements-cheat-sheet-2026/)
26. [Qwen3 Technical Report](https://arxiv.org/abs/2505.09388)
27. [Gemma 4 Apache 2.0 Blog](https://opensource.googleblog.com/2026/03/gemma-4-expanding-the-gemmaverse-with-apache-20.html)

### Añadidas post-review
28. [TRL SFTTrainer docs — get_training_chat_template()](https://huggingface.co/docs/trl/sft_trainer) — auto-patch para Qwen3, no para Gemma4
29. [TRL Issue #3781 — assistant_only_loss + liger_kernel silent failure](https://github.com/huggingface/trl/issues/3781)
