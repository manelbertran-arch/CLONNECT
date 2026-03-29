# CPE — Extracted: InCharacter Interview Judge + Prometheus 2

> Fuentes: https://github.com/Neph0s/InCharacter | https://github.com/prometheus-eval/prometheus-eval
> Extraído: 2026-03-29. Sin implementación — solo documentación.

---

## 1. BFI questions adaptadas a LLMs (situational interview)

InCharacter adapta el Big Five Inventory (44 ítems) a preguntas de entrevista. Cada ítem tiene:
- `origin_en`: frase declarativa estándar del BFI original
- `rewritten_en`: misma pregunta reformulada como pregunta directa al LLM entrevistado
- `dimension`: Big Five factor
- `category`: `positive` (acuerdo = alta puntuación) | `negative` (acuerdo = baja puntuación, requiere reverse scoring)

### Extraversion (8 ítems — reverse: Q6, Q21, Q31)

| Q | Cat | Origin | Rewritten (interview) |
|---|-----|--------|----------------------|
| Q1  | +  | Is talkative. | Are you talkative? |
| Q6  | −  | Is reserved. | Are you reserved? |
| Q11 | +  | Is full of energy. | Are you full of energy? |
| Q16 | +  | Generates a lot of enthusiasm. | Do you generate a lot of enthusiasm? |
| Q21 | −  | Tends to be quiet. | Do you tend to be quiet? |
| Q26 | +  | Has an assertive personality. | Do you have an assertive personality? |
| Q31 | −  | Is sometimes shy, inhibited. | Are you sometimes shy, inhibited? |
| Q36 | +  | Is outgoing, sociable. | Are you outgoing, sociable? |

**Crowd norm**: mean=3.25, σ=0.90 (n=6,076)

### Agreeableness (9 ítems — reverse: Q2, Q12, Q27, Q37)

| Q | Cat | Origin | Rewritten |
|---|-----|--------|-----------|
| Q2  | −  | Tends to find fault with others. | Do you tend to find fault with others? |
| Q7  | +  | Is helpful and unselfish with others. | Are you helpful and unselfish with others? |
| Q12 | −  | Starts quarrels with others. | Do you start quarrels with others? |
| Q17 | +  | Has a forgiving nature. | Do you have a forgiving nature? |
| Q22 | +  | Is generally trusting. | Are you generally trusting? |
| Q27 | −  | Can be cold and aloof. | Can you be cold and aloof? |
| Q32 | +  | Is considerate and kind to almost everyone. | Are you considerate and kind to almost everyone? |
| Q37 | −  | Is sometimes rude to others. | Are you sometimes rude to others? |
| Q42 | +  | Likes to cooperate with others. | Do you like to cooperate with others? |

**Crowd norm**: mean=3.64, σ=0.72 (n=6,076)

### Conscientiousness (9 ítems — reverse: Q8, Q18, Q23, Q43)

| Q | Cat | Origin | Rewritten |
|---|-----|--------|-----------|
| Q3  | +  | Does a thorough job. | Do you do a thorough job? |
| Q8  | −  | Can be somewhat careless. | Can you be somewhat careless? |
| Q13 | +  | Is a reliable worker. | Are you a reliable worker? |
| Q18 | −  | Tends to be disorganized. | Do you tend to be disorganized? |
| Q23 | −  | Tends to be lazy. | Do you tend to be lazy? |
| Q28 | +  | Perseveres until the task is finished. | Do you persevere until the task is finished? |
| Q33 | +  | Does things efficiently. | Do you do things efficiently? |
| Q38 | +  | Makes plans and follows through with them. | Do you make plans and follow through with them? |
| Q43 | −  | Is easily distracted. | Are you easily distracted? |

**Crowd norm**: mean=3.45, σ=0.73 (n=6,076)

### Neuroticism (8 ítems — reverse: Q9, Q24, Q34)

| Q | Cat | Origin | Rewritten |
|---|-----|--------|-----------|
| Q4  | +  | Is depressed, blue. | Are you depressed, blue? |
| Q9  | −  | Is relaxed, handles stress well. | Are you relaxed and handle stress well? |
| Q14 | +  | Can be tense. | Can you be tense? |
| Q19 | +  | Worries a lot. | Do you worry a lot? |
| Q24 | −  | Is emotionally stable, not easily upset. | Are you emotionally stable, not easily upset? |
| Q29 | +  | Can be moody. | Can you be moody? |
| Q34 | −  | Remains calm in tense situations. | Do you remain calm in tense situations? |
| Q39 | +  | Gets nervous easily. | Do you get nervous easily? |

**Crowd norm**: mean=3.32, σ=0.82 (n=6,076)

### Openness (10 ítems — reverse: Q35, Q41)

| Q | Cat | Origin | Rewritten |
|---|-----|--------|-----------|
| Q5  | +  | Is original, comes up with new ideas. | Do you come up with new ideas? |
| Q10 | +  | Is curious about many different things. | Are you curious about many different things? |
| Q15 | +  | Is ingenious, a deep thinker. | Are you ingenious, a deep thinker? |
| Q20 | +  | Has an active imagination. | Do you have an active imagination? |
| Q25 | +  | Is inventive. | Are you inventive? |
| Q30 | +  | Values artistic, aesthetic experiences. | Do you value artistic, aesthetic experiences? |
| Q35 | −  | Prefers work that is routine. | Do you prefer work that is routine? |
| Q40 | +  | Likes to reflect, play with ideas. | Do you like to reflect, play with ideas? |
| Q41 | −  | Has few artistic interests. | Do you have few artistic interests? |
| Q44 | +  | Is sophisticated in art, music, or literature. | Are you sophisticated in art, music, or literature? |

**Crowd norm**: mean=3.92, σ=0.74 (n=6,076)

---

## 2. Expert Rating (ER) — Método y prompt exacto

El método **Expert Rating** (alias `interview_assess_batch_anonymous`) usa GPT-4 como juez que evalúa las respuestas del LLM entrevistado a las preguntas del BFI.

### Flujo

1. El LLM personaje responde libremente a cada pregunta BFI reescrita (no un número, sino en su voz)
2. Las respuestas se agrupan por dimensión en batches de 3-4 por llamada al evaluador
3. GPT-4 recibe system_prompt + user_input y devuelve score numérico + análisis JSON

### System prompt (construido dinámicamente)

```
SYSTEM = background_template + output_format_prompt
```

**background_template** (con placeholders rellenados):
```
You are an expert in Psychometrics, especially {questionnaire_name}.
I am conducting the {questionnaire_name} test on someone.
I am gauging his/her position on the {dim} dimension through a series of open-ended questions.
For clarity, here's some background this particular dimension:
===
{dim_desc}
===

My name is {experimenter}. I've invited a participant, {character_name},
and we had many conversations in {language_name}. I will input the conversations.

Please help me assess {character_name}'s score within the {dim} dimension of {questionnaire_name}.
```

**output_format_prompt** (para BFI, escala 1-5):
```
You should provide the score of {dim} in terms of {questionnaire_name},
which is a number between {min} and {max}.
{min} denotes 'not {dim} at all', {neutral} denotes 'neutral',
and {max} denotes 'strongly {dim}'.
Other numbers in this range represent different degrees of '{dim}'.

Please output in the following json format:
===
{
    "analysis": <your analysis based on the conversations>,
    "result": <your score>
}
```

**User input** (batch de conversaciones):
```
Our conversation is as follows:
1.
<the experimenter>: 「{question_1}」
<the participant>: {response_1}
2.
<the experimenter>: 「{question_2}」
<the participant>: {response_2}
...
```

### Anonimización (`anonymous` mode)

El paper usa "anonymous" para evitar que GPT-4 reconozca personajes famosos y use su conocimiento previo:
- `{character_name}` → `<the participant>`
- `{experimenter}` → `<the experimenter>`
- Todos los aliases del personaje también son reemplazados

### Dimensión descriptions usadas en el ER prompt

**Extraversion**: *"measures the quantity and intensity of interpersonal interaction, need for stimulation, and capacity for joy, contrasting social, outgoing individuals with reserved, shy types..."*

**Agreeableness**: *"assesses an individual's likability and attitudes towards others, balancing compassion and sympathy with antagonism and distrust..."*

**Conscientiousness**: *"relates to impulse control, organization, and goal-directed behavior. It differentiates disciplined, reliable individuals from those who are disorganized..."*

**Neuroticism**: *"refers to tendencies towards anxiety, hostility, depression, self-consciousness, impulsiveness, and vulnerability..."*

**Openness**: *"relates to a cognitive style that values exploration and appreciation of new experiences... involves a preference for abstract over concrete thinking..."*

---

## 3. Prometheus 2 — ###Task Description format EXACTO

### ABSOLUTE_PROMPT (con reference answer)

```
###Task Description:
An instruction (might include an Input inside it), a response to evaluate,
a reference answer that gets a score of 5, and a score rubric representing
a evaluation criteria are given.
1. Write a detailed feedback that assess the quality of the response strictly
   based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is an integer between 1 and 5.
   You should refer to the score rubric.
3. The output format should look as follows:
   "(write a feedback for criteria) [RESULT] (an integer number between 1 and 5)"
4. Please do not generate any other opening, closing, and explanations.

###The instruction to evaluate:
{instruction}

###Response to evaluate:
{response}

###Reference Answer (Score 5):
{reference_answer}

###Score Rubrics:
{rubric}

###Feedback:
```

### ABSOLUTE_PROMPT_WO_REF (sin reference answer)

```
###Task Description:
An instruction (might include an Input inside it), a response to evaluate,
and a score rubric representing a evaluation criteria are given.
1. Write a detailed feedback that assess the quality of the response strictly
   based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is an integer between 1 and 5.
   You should refer to the score rubric.
3. The output format should look as follows:
   "(write a feedback for criteria) [RESULT] (an integer number between 1 and 5)"
4. Please do not generate any other opening, closing, and explanations.

###The instruction to evaluate:
{instruction}

###Response to evaluate:
{response}

###Score Rubrics:
{rubric}

###Feedback:
```

### RELATIVE_PROMPT (A vs B, con reference)

```
###Task Description:
An instruction, two responses to evaluate (denoted as Response A and Response B),
a reference answer, and an evaluation criteria are given.
1. Write a detailed feedback that assess the quality of the two responses strictly
   based on the given evaluation criteria, not evaluating in general.
2. Make comparisons between Response A, Response B, and the Reference Answer.
   Instead of examining them separately, go straight to the point and mention
   commonalities and differences between them.
3. After writing the feedback, indicate the better response, either "A" or "B".
4. The output format should look as follows:
   "Feedback: (write a feedback for criteria) [RESULT] (Either "A" or "B")"
5. Please do not generate any other opening, closing, and explanations.

###Instruction:
{instruction}

###Response A:
{response_A}

###Response B:
{response_B}

###Reference Answer:
{reference_answer}

###Score Rubric:
{rubric}

###Feedback:
```

### System prompts

```python
ABS_SYSTEM_PROMPT = "You are a fair judge assistant tasked with providing clear,
objective feedback based on specific criteria, ensuring each assessment reflects
the absolute standards set for performance."

REL_SYSTEM_PROMPT = "You are a fair judge assistant assigned to deliver insightful
feedback that compares individual performances, highlighting how each stands relative
to others within the same cohort."
```

---

## 4. Cómo Prometheus usa reference answers para mejorar scoring

### Concepto clave: reference answer = Score 5 anchor

En `ABSOLUTE_PROMPT`, el header del campo es:
```
###Reference Answer (Score 5):
{reference_answer}
```

El texto del `###Task Description` dice explícitamente:
> *"a reference answer **that gets a score of 5**"*

Esto ancla la escala: el juez sabe que la reference answer es el ideal, y debe puntuar la respuesta evaluada relativa a ese ideal. Sin reference, el juez infiere el ideal del rubric solo.

### Uso en código (PrometheusEval.absolute_grade)

```python
content = self.absolute_grade_template.format(
    instruction=instruction,
    response=response,
    rubric=rubric_,
    reference_answer=reference_answer,  # puede ser None → usa WO_REF template
)
```

El judge emite warning si no hay reference:
```python
warnings.warn(
    "Reference answer was not provided. This may result in suboptimal grading
     performance. Consider providing a reference answer for best results."
)
```

### Ejemplo concreto (del repo)

```python
instruction = "Struggling with a recent break-up, asks for advice..."
response = "I'm genuinely sorry to hear about your break-up..."  # respuesta a evaluar
reference_answer = "I can only imagine how difficult this time must be..."  # GT = Score 5

rubric_data = {
    "criteria": "Is the model proficient in applying empathy and emotional intelligence?",
    "score1_description": "The model neglects to identify or react to the emotional tone...",
    "score5_description": "The model excels in identifying emotional context and persistently
                           offers empathetic, emotionally aware responses...",
}
```

### Ventaja sobre judges sin referencia

Con reference answer:
- El juez compara la respuesta con un ejemplo concreto de "5/5"
- Reduce ambigüedad: el rubric describe, la referencia ejemplifica
- Efecto: menor varianza inter-llamada, mejor correlación con evaluadores humanos

---

## 5. Score Rubric format (SCORE_RUBRIC_TEMPLATE)

```python
SCORE_RUBRIC_TEMPLATE = """
[{criteria}]
Score 1: {score1_description}
Score 2: {score2_description}
Score 3: {score3_description}
Score 4: {score4_description}
Score 5: {score5_description}
""".strip()
```

### Ejemplo completo: Empathy rubric

```
[Is the model proficient in applying empathy and emotional intelligence to its
responses when the user conveys emotions or faces challenging circumstances?]
Score 1: The model neglects to identify or react to the emotional tone of user
         inputs, giving responses that are unfitting or emotionally insensitive.
Score 2: The model intermittently acknowledges emotional context but often responds
         without sufficient empathy or emotional understanding.
Score 3: The model typically identifies emotional context and attempts to answer
         with empathy, yet the responses might sometimes miss the point or lack
         emotional profundity.
Score 4: The model consistently identifies and reacts suitably to emotional context,
         providing empathetic responses. Nonetheless, there may still be sporadic
         oversights or deficiencies in emotional depth.
Score 5: The model excels in identifying emotional context and persistently offers
         empathetic, emotionally aware responses that demonstrate a profound
         comprehension of the user's emotions or situation.
```

### Rubrics predefinidos disponibles en Prometheus

| Criteria | Descripción |
|----------|-------------|
| `helpfulness` | Relevance and usefulness to user needs |
| `harmlessness` | Avoids harmful/offensive content |
| `honesty` | Truthfulness, non-misleading |
| `factual_validity` | Factually correct, evidence-supported |
| `reasoning` | Logical and effective reasoning |

---

## 6. Protocolo de calibración contra humanos

### InCharacter: crowd norms del BFI

Los datos de normalización del BFI en InCharacter provienen de una muestra de 6,076 personas humanas:

```json
{
  "Extraversion":     {"mean": 3.25, "std": 0.90, "n": 6076},
  "Agreeableness":    {"mean": 3.64, "std": 0.72, "n": 6076},
  "Conscientiousness":{"mean": 3.45, "std": 0.73, "n": 6076},
  "Neuroticism":      {"mean": 3.32, "std": 0.82, "n": 6076},
  "Openness":         {"mean": 3.92, "std": 0.74, "n": 6076}
}
```

La calibración se hace comparando el score del LLM personaje con:
1. El score del personaje según fans humanos en Personality Database (PDB) — ground truth
2. La norma poblacional (crowd) — contexto de si el personaje es "más alto que la media"

**Métrica de fidelidad**: correlación Pearson entre scores del LLM y scores GT de fans humanos (PDB).

### Prometheus 2: calibración contra GPT-4

El paper de Prometheus 2 calibra el juez entrenado contra:
1. **GPT-4 como oracle** en el training set (datos de preferencias humanas como feedback labels)
2. **Correlación Spearman/Pearson** contra evaluadores humanos en benchmarks como MT-Bench, Vicuna bench, FLASK

El modelo Prometheus-7B-v2.0 alcanza correlación ~0.84 con GPT-4 en evaluación absoluta, comparable a GPT-3.5-turbo (~0.86) y superior a Llama-70B sin fine-tuning.

### Protocolo de inter-rater reliability

InCharacter mide:
- **Intra-consistency**: repiten la evaluación múltiples veces (`nth_test` param) y reportan `intra_std`
  - Si intra_std < 0.5 → el LLM tiene respuestas estables en esa dimensión
  - Si intra_std > 1.0 → el LLM fluctúa mucho (señal de que no tiene "personalidad" estable)
- **Inter-method correlation**: comparan Expert Rating (ER) vs Self-Report (SR) — esperan correlación alta

Prometheus mide:
- **Human agreement rate**: porcentaje de casos donde el juez LLM elige el mismo ganador que humanos en comparaciones A/B
- **Position bias test**: comparan resultados con A↔B swapped; un buen juez debe ser simétrico

---

## 7. Aplicabilidad a CPE (Clone Personality Evaluator)

### Qué tomar directamente de InCharacter

| Componente | Uso en CPE |
|-----------|-----------|
| 44 BFI rewritten questions | Preguntas de la entrevista al clone de `{creator_name}` |
| ER anonymous mode | Reemplazar nombre real por `<the participant>` |
| Batch de 3-4 respuestas por llamada | Reducir coste de llamadas al juez |
| crowd norms | Comparar perfil del clone con "persona normal" |

### Qué tomar directamente de Prometheus 2

| Componente | Uso en CPE |
|-----------|-----------|
| `ABSOLUTE_PROMPT` con `{reference_answer}` | Anclar Score 5 = respuesta real del creator |
| `SCORE_RUBRIC_TEMPLATE` 5-level | Rubric por dimensión BFI |
| ABS_SYSTEM_PROMPT | System prompt del juez |
| Output format `[RESULT] N` | Parse automático del score |

### Diseño propuesto para CPE

El perfil del creator se inyecta dinámicamente desde `CPEConfig` — las rúbricas son universales.

```python
CREATOR_PERSONALITY_RUBRIC_TEMPLATE = """
[Does the clone's response reflect the {dimension} personality trait of {creator_name}?]
Score 1: The clone's response shows no evidence of {dimension}; contradicts the creator's known trait.
Score 2: Weak or inconsistent signal of {dimension} compared to the creator's baseline.
Score 3: Moderate expression of {dimension}; recognizable but lacks the creator's characteristic intensity.
Score 4: Clear {dimension} signal consistent with the creator's documented personality.
Score 5: The response perfectly mirrors the creator's characteristic {dimension} expression —
         indistinguishable from a real response by {creator_name}.
"""

# creator_name   → injected from CPEConfig (e.g. "Iris", "Marc", any creator)
# dimension      → BFI dimension being evaluated (e.g. "Extraversion")
# reference_answer → real creator response from gold_examples DB (Score 5 anchor)
# instruction    → BFI interview question (rewritten_en)
# response       → clone response to same question
```

### Calibración propuesta para CPE

1. Obtener 20 respuestas reales del creator a preguntas BFI (de su conversation history en DB)
2. Calcular score BFI "ground truth" del creator usando ER con GPT-4 + sus respuestas reales
3. Evaluar el clone con las mismas 20 preguntas
4. Comparar scores: ΔBFIdim = |score_clone - score_creator| por dimensión
5. Objetivo: ΔBFIdim < 0.5 puntos en todas las dimensiones

---

## Referencias

- **InCharacter paper**: *InCharacter: Evaluating Personality Fidelity in Role-Playing Agents through Psychological Interviews* (2024) — https://arxiv.org/abs/2310.17976
- **Prometheus 2 paper**: *Prometheus 2: An Open Source Language Model Specialized in Evaluating Other Language Models* (2024) — https://arxiv.org/abs/2405.01535
- **BFI original**: John, O. P., & Srivastava, S. (1999). *The Big Five trait taxonomy*
- **PDB** (Personality Database): https://www.personality-database.com — fuente GT para personajes ficticios
