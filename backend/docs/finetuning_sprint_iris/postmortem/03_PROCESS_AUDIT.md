# Auditoría del Proceso — Training + Serving + Evaluation
**Fecha:** 2026-04-25  
**Rama:** feat/sft-postmortem-analysis

---

## 3.1 Configuración de Training

Fuente: `scripts/finetuning/train_modal.py` + logs de Modal (sprint 2026-04-24)

### Tabla de decisiones vs best practice

| Decisión | Valor usado | Best practice (2024-2026) | Veredicto |
|---|---|---|---|
| Modelo base | `unsloth/gemma-4-31B-it` | Modelo it (instruction-tuned) correcto para persona SFT | ✅ |
| GPU | **A100-40GB** | A100-80GB para 31B bf16 inference; 40GB requiere 4-bit | 🟡 Limitante |
| Quantization training | 4-bit NF4 | QLoRA estándar — aceptable para 31B en 40GB | ✅ |
| Quantization serving | **bf16 (sin quantize)** | Mismatch con training 4-bit — puede causar pequeñas divergencias | 🟡 |
| LoRA rank | r=16 | r=16-64 para chat/estilo — r=16 correcto para estilo, posiblemente bajo para persona facts | 🟡 |
| LoRA alpha | 32 (ratio 2x) | alpha=2×r es estándar (efectivo LR=1.0 en LoRA space) | ✅ |
| LoRA dropout | 0.05 | 0.0-0.1 rango normal para SFT; 0.05 aceptable | ✅ |
| Target modules | q,k,v,o,gate,up,down | Todos los módulos — máxima cobertura | ✅ |
| Learning rate | **2e-4** | 1e-4 a 3e-4 rango típico; 2e-4 en el límite alto para 1 epoch | 🟡 |
| LR scheduler | cosine | Estándar recomendado | ✅ |
| Optimizer | adamw_8bit | Estándar para QLoRA | ✅ |
| Batch size efectivo | 2×4=8 | 8-16 aceptable para 31B | ✅ |
| **Epochs** | **1** | **1-3 para SFT; 1 puede ser insuficiente para persona facts** | 🔴 |
| Max seq length | **2048** | **Dataset tiene P95=250 chars → 2048 suficiente; pero multi-turn necesitaría 4096+** | 🟡 |
| Warmup ratio | 0.03 | 3-5% estándar | ✅ |
| Weight decay | 0.01 | 0.01-0.1 rango; 0.01 conservador | ✅ |
| Max grad norm | 0.3 | 0.3-1.0; 0.3 agresivo (puede inhibir learning) | 🟡 |
| **Chat template** | **gemma-4-thinking, enable_thinking=False** | **Ver sección 3.3 — MISMATCH CRÍTICO** | 🔴 |
| train_on_responses_only | True | Correcto — no entrenar en user turns | ✅ |
| instruction_part | `<\|turn>user\n` | Correcto para gemma-4-thinking | ✅ |
| response_part | `<\|turn>model\n` | Correcto para gemma-4-thinking | ✅ |
| **eval_dataset** | **None** | **Recomendado siempre para detectar overfitting** | 🔴 |
| Validation split | **No** | **10-20% holdout mínimo** | 🔴 |
| Random seed | 3407 | Reproducible — correcto | ✅ |
| Report_to | none | No tracking de métricas en tiempo real | 🟡 |

### Leyenda
- ✅ Correcto / best practice
- 🟡 Aceptable pero subóptimo
- 🔴 Divergencia significativa vs best practice

---

## 3.2 Dinámica del Training

### Loss curve observada
```
Step 0:    train_loss ≈ 10.64  (inicio — plausible para cross-entropy sobre vocab ~260k tokens)
Step 1159: train_loss = 3.20   (final — loss ratio = 0.30)
```

### ¿Es saludable esta loss curve?

**Loss inicial (10.64):** Para un tokenizador con ~260k vocab tokens (Gemma-4), la pérdida esperada en inicio con weights aleatorios sería ln(260000) ≈ 12.5. Una loss inicial de 10.64 sugiere que el modelo pre-entrenado ya tiene información relevante (la loss arranca por debajo del random baseline). ✅ Normal.

**Loss final (3.20):** Equivale a una perplejidad de e^3.20 ≈ 24.5 tokens. Para respuestas DM cortas y coloquiales con vocabulario limitado, esto es razonable — no indica overfitting severo ni underfitting. ✅ Plausible.

**Ratio train_loss_final/initial = 0.30:** Una reducción del 70% en 1 epoch es agresiva pero dentro del rango para QLoRA con LR=2e-4. Podría indicar sobreajuste a los patrones más frecuentes del dataset (los 1.352 duplicados exactos contribuyen a bajar la loss artificialmente).

**Ausencia de validation loss:** Sin validation set, es imposible distinguir entre:
- El modelo aprendiendo representaciones generalizables ✅
- El modelo memorizando el training set 🔴

Esta es la omisión más crítica del proceso de training.

### Señales de posible overfitting
1. Los 1.352 duplicados exactos (14.6%) hacen que la loss baje fácilmente en esas muestras — sesgo hacia patterns repetitivos
2. 22 error strings entrenados → el modelo puede haber "memorizado" que esa cadena es válida
3. Sin validation loss, no podemos confirmar ni desmentir

---

## 3.3 Auditoría de Chat Template — MISMATCH CRÍTICO

### Training (enable_thinking=False)

```python
tokenizer = get_chat_template(tokenizer, chat_template="gemma-4-thinking")

# En formatting_prompts_func:
tokenizer.apply_chat_template(
    convo, 
    tokenize=False, 
    add_generation_prompt=False, 
    enable_thinking=False  # ← SIN thinking tokens
)
```

Formato resultante en training:
```
<bos><|turn>system
[system_content]
<turn|>
<|turn>user
[user_content]
<turn|>
<|turn>model
[assistant_content]    ← ESTO es lo que el modelo aprende a generar
<turn|>
```

### Serving (vLLM con permissive jinja template)

```jinja
{%- if add_generation_prompt -%}
{{ '<|turn>model\n' }}{{ '<|channel>thought\n<channel|>' }}
{%- endif -%}
```

Formato resultante en serving (add_generation_prompt=True):
```
...<|turn>user
[user_content]
<turn|>
<|turn>model
<|channel>thought
<channel|>           ← EL MODELO VE ESTO ANTES DE GENERAR
[model generates here]
```

### Análisis del mismatch

Durante training, el modelo aprendió la asociación:
```
... <|turn>model\n → [respuesta Iris]
```

Durante serving, la secuencia que ve justo antes de generar es:
```
... <|turn>model\n<|channel>thought\n<channel|> → ???
```

El modelo nunca vio `<|channel>thought\n<channel|>` durante el training (enable_thinking=False). Esta secuencia es parte del vocabulario del tokenizador pero es un token desconocido en el contexto de "qué viene después de <|turn>model\n".

**Consecuencias observadas:**
1. El modelo genera respuestas coherentes en la mayoría de casos (smoke tests pasan) → el mismatch no rompe la generación completamente
2. Pero puede causar inconsistencia en cómo el modelo procesa el contexto previo (el "thinking block vacío" altera la distribución de atención sobre el system prompt)
3. Esto es plausible como contribuyente al J6 cross_session = 0: el modelo FT bajo diferentes contextos RAG + thinking prefix puede activar diferentes "modos" de interpretación

**Severidad:** 🟡 MEDIUM — El modelo funciona, pero con comportamiento no determinista en el contexto de system prompts largos.

**Verificación definitiva:** Hacer serving con el mismo template exacto que training (enable_thinking=False, sin `<|channel>thought`) y medir CCEE de nuevo.

---

## 3.4 Auditoría del Setup de Serving

Fuente: `scripts/finetuning/serve_modal.py`

### Tabla comparativa training vs serving

| Parámetro | Training | Serving | Mismatch |
|---|---|---|---|
| GPU | A100-40GB | **A100-80GB** | Diferente — más VRAM en serving |
| Quantization | 4-bit NF4 (QLoRA) | **bf16 merged** | 🟡 Diferencia numérica pequeña |
| Max sequence | 2048 | **16384** | 🔴 Serving 8× más largo que training |
| Chat template | gemma-4-thinking + enable_thinking=False | **Permissive jinja + thinking prefix** | 🔴 MISMATCH |
| Batch size | 8 effective | N/A (online serving) | — |
| Sampling temp | 0.7 | **0.7 en CCEE** | ✅ |
| Max tokens | N/A | **100 (CCEE default)** | 🟡 (Iris escribe <100 chars en P75) |

### Max seq length: 2048 (training) vs 16384 (serving)

El modelo fue entrenado con secuencias de máximo 2048 tokens. En serving, recibe system prompts de ~2000+ tokens (8093 tokens en CCEE pipeline). Esto significa que el sistema prompt en serving es del tamaño de la secuencia COMPLETA de training.

**Implicación:** El modelo nunca fue entrenado a atender a un contexto tan largo. Su capacidad de atención sobre tokens muy distantes en el input puede ser subóptima para los 8093 tokens de system prompt de producción.

**Contraevidence:** La arquitectura Gemma-4 fue pre-entrenada con contextos largos (>32K). El QLoRA SFT sobre 2048 tokens modifica los pesos de atención localmente pero no destruye la capacidad para contextos más largos — el modelo base ya sabía atender a contextos largos. La degradación sería gradual, no catastrófica.

---

## 3.5 Auditoría del Setup de Evaluación

### Comparabilidad baseline vs FT

| Parámetro | Baseline (69.5) | FT pipeline (66.4) | Comparable? |
|---|---|---|---|
| CCEE version | v5 | v5 | ✅ |
| Flags | v4-composite, v41-metrics, v5, v52-fixes | Iguales | ✅ |
| Cases | 50 stratified, CCEE_SEED=42 | 50 stratified, CCEE_SEED=42 | ✅ |
| Runs | 3 | 3 | ✅ |
| Judge | Qwen/Qwen3-30B-A3B (DeepInfra) | Mismo | ✅ |
| MT | 5 conversations × 10 turns | Mismo | ✅ |
| Temperature | 0.7 | 0.7 | ✅ |
| Max tokens | 100 | 100 | ✅ |
| **Doc D** | **version_id: 6c51ddb0, chars=2462** | **version_id: 942f850a, chars=1576** | 🔴 DIFERENTE |
| Embeddings | OpenAI 429 quota? | OpenAI 429 quota (confirmado) | 🟡 Ver análisis |

### Doc D mismatch (CRÍTICO)

El baseline 69.5 usó `doc_d_version_id=6c51ddb0` con 2.462 chars.  
El FT pipeline 66.4 usó `doc_d_version_id=942f850a` con 1.576 chars.

**El Doc D cambió entre la medición del baseline y la del FT.** La versión del FT es 36% más corta (1.576 vs 2.462 chars). Esto significa que el system prompt de producción en el CCEE del FT era materialmente diferente al del baseline.

**Impacto estimado:** Imposible cuantificar sin correr el baseline con el Doc D nuevo. Pero sabemos que el Doc D corto podría favorecer o perjudicar ciertas métricas. Cualquier comparación directa BL_pipeline vs FT_pipeline lleva este confound.

**Severity:** 🔴 HIGH — Invalida parcialmente la comparación directa. Para el análisis 4-way (naked vs pipeline), el Doc D diferente no afecta las comparaciones naked, solo las pipeline.

### Embeddings 429

Ambas mediciones (baseline y FT) tienen `ENABLE_SEMANTIC_MEMORY_PGVECTOR=true`, el mismo env mirror, y el mismo proveedor OpenAI. Si la quota estaba agotada en ambas, la comparación es válida — ambas corrieron en condiciones degradadas idénticas. Evidencia indirecta: J1=50.0 ("no multi-turn data") en AMBAS condiciones — si la memoria funcionase, J1 sería diferente.

### Seed y reproducibilidad de test cases

CCEE usa `CCEE_SEED=42` que hace `SELECT setseed(0.042) ... ORDER BY RANDOM()` en PostgreSQL. Los 50 cases deberían ser deterministas si la BD no cambia. Entre el 23 y el 25 de abril, la BD puede haber recibido nuevos mensajes. **No verificado — posible confound menor.**

---

## 3.6 Pipeline de Producción — Análisis del System Prompt

### Componentes del system prompt de producción

```
COMPONENTE              | Chars típicos | Propósito original          | ¿Necesario con FT?
------------------------|---------------|------------------------------|-------------------
Style prompt (persona)  | ~1500         | Definir quién es Iris        | Parcialmente — FT ya lo sabe
Doc D                   | 1576          | Detalles profundos de persona| Parcialmente
Few-shot examples       | ~800          | Ejemplos de tono             | Probablemente NO
RAG context             | ~300-800      | KB hits relevantes           | Sí, para info actualizada
Relational block        | ~200          | Contexto del lead            | Sí
State context           | ~100          | Estado de la conversación    | Sí
Anti-echo instructions  | ~50           | Evitar repetición            | Sí
```

**Tamaño total estimado:** 4.500-8.000 chars → ~1.125-2.000 tokens.

**Hallazgo del ContextHealth WARNING:** El scorer reportó repetidamente `style(92%)` — el bloque de estilo consume el 92% del context budget. Esto confirma que el system prompt es dominado por el bloque de persona/estilo (style_prompt + Doc D + few-shots).

### ¿Qué componentes son conflictivos con el modelo FT?

| Componente | Conflicto con FT | Evidencia |
|---|---|---|
| Style prompt | Redundante — FT internalizó esto | S1 naked=75.3 sin prompt |
| Doc D | Potencialmente conflictivo — FT tiene su versión internalizada | J6_cross_session=0 pipeline |
| Few-shot examples | Conflictivo — override del comportamiento aprendido | C2 baja pipeline |
| RAG context | **Causa directa de J6 varianza** | RAG distinto por sesión → J6=0 |
| Relational block | Necesario — el FT no tiene esta info | S4 sube con pipeline +5.9 |
| Anti-echo | Redundante — G4 echo rate ya bajo con FT | G4=1.78 FT naked |

---

## 3.7 Gaps Identificados vs Best Practice

| ID | Gap | Severity | Impacto observado |
|---|---|---|---|
| G-01 | **Sin validation split** | 🔴 | No detectamos overfitting/underfitting |
| G-02 | **Sin validation loss en training** | 🔴 | No podemos distinguir generalización vs memorización |
| G-03 | **0% multi-turn samples** | 🔴 | K1 −21.6, J5 −22.5, J6 indirecto |
| G-04 | **Sin system prompt en training data** | 🔴 | Distribution shift, J6 cross_session=0 |
| G-05 | **0.1% persona Q&A responses** | 🔴 | J6 cross_session=0 |
| G-06 | **Chat template mismatch train vs serve** | 🔴 | Comportamiento no determinista en RAG contexts |
| G-07 | **Doc D diferente en baseline vs FT evaluation** | 🔴 | Comparación parcialmente inválida |
| G-08 | **1 epoch sin búsqueda de hiperparámetros** | 🟡 | Puede ser insuficiente para persona facts |
| G-09 | **22 error strings en training data** | 🟡 | Potencial contaminación de comportamiento |
| G-10 | **441 media/sticker en training data** | 🟡 | Modelo aprende artefactos como respuestas válidas |
| G-11 | **Sin holdout test set** | 🟡 | No podemos verificar overfitting post-training |
| G-12 | **Sin hyperparameter search** | 🟡 | LR, rank subóptimos posible |
| G-13 | **A100-40GB para training vs 80GB para serving** | 🟡 | Posibles diferencias numéricas menores |
| G-14 | **Sin adversarial examples en training** | 🟡 | J5 belief drift regresión |
| G-15 | **Sin dedup train↔eval** | 🟡 | Riesgo de contaminación |
| G-16 | **Max seq length 2048 vs system prompt serving ~2000+ tokens** | 🟡 | Atención sobre system prompt no entrenada |
| G-17 | **Sin evaluation intermedia por epoch** | 🟢 | No habría cambiado con 1 epoch |
| G-18 | **Sin cross-validation** | 🟢 | Coste computacional prohibitivo para 31B |

---

## Conclusión Fase 3

Los gaps más impactantes son G-03, G-04, G-05 (datos de entrenamiento) y G-06 (template mismatch). 

Los gaps de proceso (G-01, G-02, G-07) no causaron la regresión directamente, pero nos impidieron detectarla durante el training.

G-09 y G-10 (contaminación del dataset) explican por qué el modelo emite `[🏷️ Sticker]` como respuesta y podría emitir el error string en contextos adversariales.
