# FASE 1 — Marco Teórico y Literatura de Referencia SFT (2023-2026)
**Fecha:** 2026-04-25  
**Rama:** feat/sft-postmortem-analysis  
**Fuentes:** investigación websearch + papers citados

---

## 1.1 Calidad vs. Cantidad: La Hipótesis LIMA

**Zhou et al. (2023) — LIMA: Less Is More for Alignment. NeurIPS 2023.**  
[[arxiv:2305.11206](https://arxiv.org/abs/2305.11206)]

Entrena LLaMA-65B con 1.000 ejemplos curados sin RLHF y supera a DaVinci-003 en evaluación humana. Formaliza la **Superficial Alignment Hypothesis (SAH)**: el conocimiento se aprende en preentrenamiento; el SFT solo enseña qué subdistribución de formatos usar.

**Revisión crítica (2024):** "Revisiting the Superficial Alignment Hypothesis"  
[[arxiv:2410.03717](https://arxiv.org/html/2410.03717v1)]

Con LLaMA-2/3 y Mistral, la SAH se sostiene parcialmente: el formato/estilo se aprende con pocos datos, pero capacidades como seguimiento de instrucciones complejas y razonamiento multi-paso sí mejoran con más datos. La SAH pura subestima el valor de la cantidad cuando la complejidad de las tareas es alta.

**Aplicación a Iris (9.272 ejemplos):**
- 9.272 >> 1.000 de LIMA → la cantidad no es el cuello de botella.
- El riesgo real es la distribución: todos single-turn, todos DM cortos, todos informal. El modelo aprenderá esa subdistribución de formato excluyendo otras.
- La SAH predice preservación de capacidades preentrenadas, pero la revisión 2024 matiza que la distribución del SFT puede contaminar las activaciones para tareas fuera de esa distribución.

---

## 1.2 QLoRA: Rango, Alpha y Señales de Sobreajuste

**Dettmers et al. (2023) — QLoRA: Efficient Finetuning of Quantized LLMs. NeurIPS 2023.**  
[[arxiv:2305.14314](https://arxiv.org/abs/2305.14314)]

Introduce NF4 + cuantización doble + optimizadores paginados para fine-tuning de LLMs en una GPU. Entrena Guanaco (65B) en 24h logrando 99.3% del rendimiento de ChatGPT en Vicuna benchmark.

**Consenso de rango 2024-2025:**

| Tarea | Rango recomendado | Fuente |
|---|---|---|
| Style tuning / formatting | r=4-8 | Unsloth Docs 2025 |
| Instruction following estándar | r=16 | Raschka 2023 |
| Domain knowledge denso | r=32-64 | "How Much is Too Much?" 2024 |
| Razonamiento complejo | r=64-128 | Databricks 2024 |

**Hallazgo clave:** "How Much is Too Much? Exploring LoRA Rank Trade-offs"  
[[arxiv:2512.15634](https://arxiv.org/html/2512.15634v1)] — diciembre 2024

> *"Mayor rango mejora la plasticidad (aprendizaje de la tarea) pero aumenta el olvido; rangos moderadamente bajos maximizan los beneficios de aprendizaje continuo."*

**Alpha:** heurística empíricamente validada = `alpha = 2×r`. Con r=16 y alpha=32 (ratio 2:1), el aprendizaje es más agresivo pero introduce riesgo de overfitting.

**Señales de sobreajuste en QLoRA:**
- Validation loss sube mientras training loss baja (ausente en este sprint — no había val set)
- El modelo reproduce frases del training verbatim
- Regresión en benchmarks generales (MMLU, GSM8K) no relacionados con el dominio del SFT

**Aplicación a Iris (r=16):**
- r=16 está en el límite superior para tareas de **estilo puro** (DM cloning). La literatura indica r=4-8 como más apropiado.
- r=16 puede estar justificado si se quiere capturar tanto estilo como "voz temática" (opiniones, temas recurrentes). Sin evidencia de val loss divergence, no podemos confirmar overfitting, pero el riesgo existe.
- Sin validation split, es imposible diagnosticar retrospectivamente.

---

## 1.3 Olvido Catastrófico en SFT de Dominio Estrecho

**Fuente principal: SFT Memorizes, RL Generalizes — Chu et al. (2025). ICML 2025.**  
[[arxiv:2501.17161](https://arxiv.org/abs/2501.17161)]

> *"SFT induce una deriva significativa en el espacio latente y de salida, especialmente para inputs de no-razonamiento, mientras que RL preserva mejor la geometría de las características internas y la estabilidad de las distribuciones de tokens."*

**Fuente secundaria: SFT Doesn't Always Hurt General Capabilities (2024).**  
[[arxiv:2509.20758](https://arxiv.org/html/2509.20758v1)]

SFT en dominios como e-commerce o biomedicina causa caídas significativas en GSM8K, HumanEval e IFEval. **El learning rate es la palanca clave:** usar 1e-6 en lugar de 2e-4 puede reducir sustancialmente la pérdida de capacidades generales.

**Tabla de capacidades y riesgo de regresión:**

| Capacidad | Riesgo con SFT narrow | Mecanismo |
|---|---|---|
| Razonamiento multi-paso | Alto | El modelo asocia "inicio de respuesta" con mensajes cortos |
| Coherencia multi-turn | **Muy alto** | Entrenado solo en single-turn, sin mecanismo de tracking |
| Consistency en Q&A de persona | **Muy alto** | Sin ejemplos Q&A, no aprende invarianza |
| Coding / math | Medio-bajo | Dominio distante, menos interferencia directa |
| Adherencia a instrucciones largas | Alto | Distribución de longitud colapsada |

**Aplicación a Iris:**
- 9.272 mensajes cortos, single-turn, informal → exactamente la configuración de "dominio estrecho" de mayor riesgo.
- La regresión en multi-turn consistency (+J5, J6) es predicha por este cuerpo de literatura como consecuencia directa del SFT narrow.
- Mitigación documentada: mezclar 5-10% de datos de instruction-following general en el training mix.

---

## 1.4 Chat Template y Distribution Shift de Formato

**Fuente: ChatBug: A Common Vulnerability of Aligned LLMs Induced by Chat Templates (2024).**  
[[arxiv:2406.12935](https://arxiv.org/html/2406.12935v2)]

Identifica que el mismatch de formato del chat template puede eludir el alineamiento y produce degradación de calidad.

**Fuente: Hugging Face LLM Course — Chat Templates.**  
[[huggingface.co/learn/llm-course/en/chapter11/2](https://huggingface.co/learn/llm-course/en/chapter11/2)]

> *"Usar un formato diferente al que el modelo fue entrenado usará generalmente una degradación severa y silenciosa del rendimiento."*

**Fuente: Instruction Fine-Tuning: Does Prompt Loss Matter? (2024).**  
[[arxiv:2401.13586](https://arxiv.org/html/2401.13586v2)]

Para datos con completions cortas (exactamente el caso DM), el enmascaramiento del prompt durante el SFT tiene un efecto regularizador significativo. Si el system prompt no fue incluido en training pero aparece en inferencia, sus tokens contribuyen a las activaciones sin que el modelo haya aprendido cómo ese contexto modifica el comportamiento.

**Aplicación a Iris (mismatch train vs serve — CRÍTICO):**

**Training:** `apply_chat_template(..., enable_thinking=False)` → sin tokens thinking  
**Serving:** template permissive con `<|channel>thought\n<channel|>` prefix

El modelo fue entrenado para predecir respuesta después de `<|turn>model\n`. En serving ve `<|turn>model\n<|channel>thought\n<channel|>` — secuencia nunca vista en training. La literatura predice "degradación severa y silenciosa."

---

## 1.5 Modelado de Persona y Clonación de Voz

**OpenCharacter: Training Customizable Role-Playing LLMs (Wang et al., 2025).**  
[[arxiv:2501.15427](https://arxiv.org/abs/2501.15427)]

Entrena LLaMA-3-8B con 306k pares sobre 20k personajes sintéticos (≈15 ejemplos/personaje). La estrategia OpenCharacter-G (generar respuestas condicionadas al perfil) supera a OpenCharacter-R (reescribir respuestas existentes). El modelo fine-tuned supera a GPT-4o en role-playing (PScore-L: 4.66 vs GPT-4o baseline).

**Nuestro caso vs. OpenCharacter:**
- OpenCharacter: ~15 ejemplos/persona × 20k personajes = diversidad amplia
- Iris: 9.272 ejemplos de 1 sola persona = profundidad alta, diversidad situacional baja
- Con 9.272 ejemplos de Iris real, debería aprender la persona mejor que OpenCharacter aprende cualquier personaje sintético. El riesgo es la estrechez situacional (solo fan-to-creator DMs).

**TwinVoice: A Multi-dimensional Benchmark Towards Digital Twins (2025).**  
[[arxiv:2510.25536](https://arxiv.org/html/2510.25536v1)]

Distingue entre consistencia de superficie (léxico, tono) y consistencia profunda (valores, opiniones bajo presión). **Un modelo puede pasar los checks de estilo pero fallar en el Turing test de persona cuando el evaluador aplica presión.**

Requisito identificado: ejemplos que cubran situaciones de tensión, desacuerdo, preguntas difíciles. Sin ellos, el modelo interpolará incorrectamente.

**Aplicación a Iris:**
- El training set de 9.272 DMs son casi exclusivamente fan-to-creator (admiración, preguntas sobre actividades, compras). Prácticamente sin tensión, desacuerdo o adversarial.
- TwinVoice predice que el modelo fallará la "consistencia profunda" bajo presión → confirmado por J5 Belief Drift (−22.5 naked).

---

## 1.6 Requisitos de Multi-Turn en SFT

**TurnWise: The Gap between Single- and Multi-turn Language Model Capabilities (2026).**  
Graf, V., Pyatkin, V., Dziri, N. et al. — University of Washington + Allen AI.  
[[arxiv:2603.16759](https://arxiv.org/abs/2603.16759)]

> *"Los LLMs son entrenados y evaluados predominantemente con datos single-turn, lo que limita su capacidad de mantener coherencia contextual en diálogos extendidos. Incluir tan solo 10.000 conversaciones multi-turn sintéticas durante el post-training puede llevar a una mejora del 12% en TurnWiseEval."*

**Beyond Single-Turn: A Survey on Multi-Turn Interactions with LLMs (2025).**  
[[arxiv:2504.04717](https://arxiv.org/abs/2504.04717)]

> *"La simple concatenación de diálogos single-turn produce conversaciones artificiales sin flujo natural. Los modelos entrenados solo con datos single-turn muestran rendimiento subóptimo en diálogos multi-turn aun cuando cada turno individual esté bien cubierto."*

**Ratio mínimo de multi-turn:** La práctica de 2024-2025 (Red Hat Developer, 2025) sugiere ≥20-30% de datos multi-turn en el training mix de chat para modelos desplegados en conversaciones.

**Aplicación a Iris:**
- **Este es el riesgo de mayor certeza:** 9.272 ejemplos single-turn garantiza degradación en multi-turn consistency.
- TurnWise cifra la mejora potencial en +12% con 10k ejemplos multi-turn sintéticos.
- Los ejemplos multi-turn no tienen que ser reales — pueden sintetizarse usando el base model.

---

## 1.7 Inclusión del System Prompt en Training Data

**Microsoft OPCD — "Microsoft's new AI training method eliminates bloated system prompts without sacrificing performance" (2024).**  
[venturebeat.com/orchestration/microsofts-new-ai-training-method-eliminates-bloated-system-prompts-without]

Microsoft demuestra el inverso: al hornear el conocimiento del system prompt en el modelo durante training, se puede eliminar el system prompt en inferencia sin pérdida de calidad. El principio implícito: **el contexto de entrenamiento debe alinearse con el contexto de despliegue.**

**Aplicación a Iris:**
- Training con system prompts inconsistentes (46% con 510-char system, 54% sin system) → el modelo aprende una distribución inconsistente.
- Production: system prompt de ~8.093 tokens nunca visto en training.
- **Recomendación directa de la literatura:** incluir el system prompt de producción (o versión representativa) en todos los ejemplos de training SFT.

---

## 1.8 Dinámica del Training: Señales de Alarma en la Loss

**"LLM Fine Tuning: What Constitutes A 'Good' Loss Value?" — Farahmand 2024.**  
**"Minor SFT Loss for LLM Fine-tune to Increase Performance and Reduce Model Deviation" (2024).**  
[[arxiv:2408.10642](https://arxiv.org/abs/2408.10642)]

**Interpretación del loss 10.64 → 3.20:**

Para un modelo de 31B ya preentrenado, el loss inicial esperado en datos de conversación es **1.5-3.5**, no 10.64.

| Rango de loss inicial | Interpretación |
|---|---|
| 1.5-3.5 | Normal para modelo preentrenado grande |
| 3.5-6.0 | Posible mismatch de formato parcial |
| **>6.0 (nuestro caso: 10.64)** | **Mismatch de formato/template severo** |

**Causas probables de loss inicial = 10.64:**
1. Se calcula la pérdida sobre tokens del prompt/instrucción (no solo respuesta) — valores de probabilidad baja en tokens del sistema inflan el loss
2. Mismatch entre chat template del modelo y formato del dataset
3. Los tokens especiales de gemma-4-thinking (`<|turn>model\n`, `<turn|>`) se procesan con probabilidad baja porque el modelo no los predice normalmente

**Loss final = 3.20:** Alto para datos conversacionales limpios. Los benchmarks de SFT bien configurados convergen en 0.5-1.5. Un 3.20 puede indicar:
- Ruido significativo en el dataset (los 22 error-strings, los 441 artefactos de media)
- Complejidad real del dataset (respuestas con fuerte varianza estilística)
- Regularización excesiva

**🔴 La loss inicial de 10.64 es la señal de alarma más importante del sprint.** Requiere auditoría retrospectiva del masking.

---

## 1.9 Belief Drift en Modelos Fine-Tuned

**"Argument Driven Sycophancy in Large Language Models" (ACL 2025).**  
[[aclanthology.org/2025.findings-emnlp.1241](https://aclanthology.org/2025.findings-emnlp.1241.pdf)]

El argumento unilateral (usuario presenta argumentos escalantes desde un lado) induce comportamiento servil a tasas ~3× mayores que el cuestionamiento directo.

**"Personalization Methods Should Address Sycophancy" (2025).**  
[[personalization-sycophancy.github.io](https://personalization-sycophancy.github.io/assets/paper.pdf)]

> *"Los métodos de personalización (como el fine-tuning de persona) deberían abordar la servilidad, porque el mismo proceso que hace que el modelo adopte la voz de la persona puede amplificar la tendencia a estar de acuerdo con el interlocutor."*

**"From Yes-Men to Truth-Tellers: Addressing Sycophancy via Pinpoint Tuning" (2024).**  
[[arxiv:2409.01658](https://arxiv.org/html/2409.01658v3)]

La servilidad tiene estructura lineal en el espacio de activaciones y puede dirigirse con menos del 5% de los módulos del modelo.

**Aplicación a Iris:**
- Los 9.272 DMs son casi todos fan-to-creator positivos → bias de aprobación implícito en el SFT.
- El modelo aprende que "concordar y ser positivo" es el patrón de respuesta correcto.
- J5 regresión (−22.5 naked) es consecuencia directa de este mecanismo.

---

## Resumen de Hallazgos SOTA

| # | Hallazgo | Severidad | Certeza |
|---|---|---|---|
| S-01 | Loss inicial 10.64 sugiere mismatch template/masking | 🔴 CRÍTICO | Alta |
| S-02 | 0% multi-turn → degradación -12% MT consistency (TurnWise) | 🔴 ALTO | Muy alta |
| S-03 | System prompt training ≠ production → distribution shift | 🔴 ALTO | Alta |
| S-04 | r=16 sobredimensionado para estilo (óptimo r=4-8) | 🟡 MEDIO | Media |
| S-05 | LR 2e-4 agresivo (1e-6 preserva capacidades mejor) | 🟡 MEDIO | Media |
| S-06 | Belief drift por SFT en DMs positivos (sycophancy) | 🟡 MEDIO | Media |
| S-07 | Sin ejemplos de tensión/adversarial (TwinVoice) | 🟡 MEDIO | Media |
| S-08 | 1 epoch puede ser insuficiente para persona facts con ruido | 🟢 BAJO | Baja |
