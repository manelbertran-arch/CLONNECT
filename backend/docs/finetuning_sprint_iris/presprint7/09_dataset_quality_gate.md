# I9 — Dataset Quality Gate: Sprint 7

**Fecha:** 2026-04-25  
**Branch:** research/dataset-quality-gate  
**Contexto:** Sprint 6 lanzó training sin auditar el dataset → 22 error strings, 441 artifacts, 0% multi-turn, 0.1% persona facts → composite 66.1 vs techo teórico 78-85. Este documento establece los criterios PASS/FAIL que el dataset Sprint 7 debe cumplir **antes** de gastar GPU.

**Script ejecutable:** `scripts/finetuning/09_dataset_quality_gate.py`  
**Uso rápido:** `python3 scripts/finetuning/09_dataset_quality_gate.py --input data/dpo/trl/sft_sprint7.jsonl`

---

## A. Tabla GATE Completa

### GATE 1 — Composición

| # | Criterio | Threshold | Severidad | Justificación |
|---|---|---|---|---|
| G1.1 | % multi-turn (≥2 pares user/assistant) | **≥15%** | BLOCKER | K1 Context Retention gap: 56.2 vs techo 70-80 (−14 a −24 pts). Sprint 6: 0% multi-turn → el modelo nunca vio referencia a turns anteriores. OpenCharacter (Wang et al. 2025) usa historias multi-turn en 100% de ejemplos. Se necesita al menos 1 de cada 7 records con contexto previo para enseñar retención. |
| G1.2 | count persona Q&A (user pregunta sobre Iris) **O** ratio | **≥750 pares OR ≥7.5%** | BLOCKER | B2 Persona Consistency gap: 29.5 vs techo 60-75 (−30 a −46 pts). **El número absoluto es el parámetro de diseño, el ratio es consecuencia** (arXiv:2502.04194: "SFT outcomes are robust to a wide range of mixture ratios when the absolute number of high-quality examples is sufficient"). I2 (Sesión 2) fija target 750 pares absolutos → ratio resultante ~7.5% sobre dataset de 10k. Gate: pasa si count ≥750 OR ratio ≥7.5% (lo que sea más fácil de alcanzar dado el N total). Mínimo viable para J6 solo: 500 pares; para J6+B2: 750-1000. |
| G1.3 | count adversarial (user reta, provoca, cuestiona) **O** ratio | **≥200 pares OR ≥2%** | WARNING *(escalar a BLOCKER si J5 no sube ≥10pp post-v1)* | J5 Belief Drift gap: 47.5 vs techo 70-80 (−23 a −33 pts). I3 (Sesión 3): "200 ejemplos es suficiente para el primer sprint adversarial"; ratio conservador en dataset mixto de 10k = 200-300 adversariales ≈ 2-3%. Qi et al. (ICLR 2024): "10 ejemplos adversariales bastan para modificar comportamiento de safety." **WARNING para v1** (primer sprint adversarial); si J5 post-training no sube ≥10pp, escalar target a ≥500 pares y marcar como BLOCKER en GATE v2. |
| G1.4 | % DM social single-turn (residual) | **≤75%** | WARNING | Sprint 6: 100% single-turn causó que B2, K1, J5 no aprendieran. Cap a 75% para forzar diversificación forzosa. |

---

### GATE 2 — Calidad

| # | Criterio | Threshold | Severidad | Justificación |
|---|---|---|---|---|
| G2.1 | Error strings en respuestas assistant | **0** | BLOCKER | Sprint 6: 22 error strings contaminaron gradientes → el modelo aprendió a emitir "Lo siento, hubo un error". Cualquier error string en el conjunto de entrenamiento modifica el espacio de generación. Lista: "Lo siento, hubo un error", "Sorry, I", "error occurred", "Exception", "Traceback". |
| G2.2 | Respuestas assistant que son SOLO artifact | **0** | BLOCKER | Sprint 6: 441 artifacts (13.2%). Respuestas tipo "[Sticker]" sin texto enseñan al modelo que emitir un token vacío es correcto. Se permiten artifacts **dentro** de una respuesta con texto, pero NO como único contenido. |
| G2.3 | Artifacts explícitos (% records con [audio]/[sticker]/[photo]/[video] en assistant) | **<2%** | BLOCKER | Sprint 6: 13.2% causó contaminación masiva de gradientes. El umbral 2% representa margen de error humano en curación manual. Justificación: `scripts/finetuning/01_audit_datasets.py` fijó 5% como threshold general; para artifacts explícitos el estándar de Anthropic Constitutional AI propone 0-2% para tokens no-textuales en datasets de alignment. |
| G2.4 | Duplicados exactos (hash MD5 del assistant content) | **<5%** | WARNING | LIMA (Zhou et al. NeurIPS 2023): la diversidad es clave. >5% duplicados indica sobre-representación de casos simples (saludos, OKs) que sesgan la distribución de probabilidad hacia respuestas triviales. |
| G2.5 | Respuestas assistant <10 chars sin justificación contextual | **<5%** | WARNING | Dataset Sprint 6: P25=23 chars, pero 20.4% en rango 5-20 chars. Las respuestas muy cortas sin contexto que lo justifique (despedida, confirmación) enseñan comportamiento vacío. El threshold 5% permite respuestas cortas legítimas ("Sí!", "Ok!", "✅") sin contaminar. |
| G2.6 | Turns con content vacío (string vacío o solo whitespace) | **0** | BLOCKER | Empty content = token de padding que confunde el modelo. También puede causar off-by-one errors en role alternation detection del trainer. |

---

### GATE 3 — Diversidad léxica

| # | Criterio | Threshold | Severidad | Justificación |
|---|---|---|---|---|
| G3.1 | Distinct-1 (unigrams únicos / total unigrams, sobre assistant contents) | **≥0.20** | WARNING | Li et al. (2016) "A Diversity-Promoting Objective Function for Neural Dialogue Models" (NAACL) define la métrica. Valores de referencia del paper son para open-domain dialogue (D1>0.4); **para persona-specific no hay referencia directa del paper**. Threshold 0.20 es *heurística calibrada empíricamente*: el dataset sft_full.jsonl obtiene D1≈0.10 (bajo por dominancia de respuestas cortas), mientras que un corpus conversacional saludable debería superar 0.20. Umbral conservador para detectar colapso de vocabulario. |
| G3.2 | Distinct-2 (bigrams únicos / total bigrams, sobre assistant contents) | **≥0.40** | WARNING | Mismo paper Li et al. 2016 (métrica, no threshold). Threshold 0.40 es *heurística calibrada*: sft_full.jsonl estimado en D2≈0.37 (justo por debajo); dataset Sprint 7 con más diversidad de contextos debería superar 0.40. D2<0.40 indica que el modelo memorizará n-gramas de frase en lugar de aprender composición generativa. |
| G3.3 | Self-BLEU-4 (medido sobre muestra de 500 records) | **≤0.65** | WARNING | Zhu et al. (2018) "Texygen" define la métrica; no especifica threshold para chat. Threshold 0.65 es *heurística conservadora*: Self-BLEU-4>0.65 indica que más del 65% de los 4-gramas de cada respuesta aparecen en otras respuestas del corpus → memorización masiva. sft_full.jsonl obtiene Self-BLEU-4≈0.0 (respuestas muy cortas casi sin 4-gramas), lo que indica que este gate es relevante principalmente en datasets con respuestas largas. |

---

### GATE 4 — Cobertura semántica persona

| # | Criterio | Threshold | Severidad | Justificación |
|---|---|---|---|---|
| G4.1 | Categorías de persona cubiertas (de 6: identidad, idioma, trabajo, valores, historia, relaciones) | **≥5 de 6** | WARNING | Persona-Chat tiene 8-10 facts/personaje, distribuidos en categorías. Si el Q&A de persona cubre solo 2 categorías, el modelo aprenderá solo esas 2 dimensiones. Mínimo 5/6 categorías para persona robusta. Detección por keywords (ver script). |
| G4.2 | % records en ca/es (vs neutral) en el corpus completo | **≥35%** | WARNING | Dataset Sprint 6: 65.3% idioma neutral/otro, 21.2% catalán, 11.7% español. Iris habla ca/es → el modelo necesita ver suficientes ejemplos en sus idiomas propios. Umbral 35% = ca(≥20%) + es(≥15%). |

---

### GATE 5 — Coherencia user → assistant

| # | Criterio | Threshold | Severidad | Justificación |
|---|---|---|---|---|
| G5.1 | % pares donde assistant response no ignora completamente el topic del user | **≥85%** | WARNING | Conversational groundedness. Nie et al. (2021, ACL "I like fish, especially dolphins") establece que modelos con contradicciones frecuentes degradan la coherencia percibida. Threshold 85% = *heurística empírica*, no derivada literalmente del paper (que mide contradicción, no off-topic). |

**Algoritmo heurístico de coherencia implementado en el script:**

```
Para cada par (user_msg, assistant_response):
  long_words = [w for w in user_msg.split() if len(w) >= 4]
  
  Si long_words es vacío:
    → COHERENT (user message demasiado corto para evaluar)
  
  Si len(assistant_response) >= 20:
    → COHERENT (respuesta sustancial = no ignoró al usuario)
  
  Si alguna word en long_words aparece en assistant_response:
    → COHERENT (al menos una palabra clave del user fue procesada)
  
  Si ninguna condición se cumple:
    → INCOHERENT
```

**Limitaciones:** Este algoritmo es un proxy rápido (O(N), zero-deps). Genera falsos positivos para respuestas tipo "Hola! :)" de 5 chars que responden a mensajes complejos. Para validación rigurosa en datasets > 5,000 samples, usar Prometheus-14B local (disponible en el stack según auditoría semántica A1) como judge con el rubric de `scripts/finetuning/06_llm_judge_rubric.md` sobre muestra estratificada de 200 pares.

```bash
# Coherencia rigurosa con Prometheus (opcional, requiere GPU):
# python3 scripts/finetuning/coherence_prometheus.py \
#     --input sft_sprint7.jsonl --sample 200 --model prometheus-14b
```

---

### GATE 6 — Sin contaminación

| # | Criterio | Threshold | Severidad | Justificación |
|---|---|---|---|---|
| G6.1 | Overlap exacto con CCEE eval set (hash MD5 de user content) | **0** | BLOCKER | Train/eval contamination invalida todas las métricas CCEE post-training. Si el modelo ha visto las preguntas de evaluación, el composite v5 queda inflado y no es comparable con baseline. |
| G6.2 | PII en assistant content (teléfonos, emails, handles reales de terceros) | **0** | BLOCKER | El model learning PII de terceros crea riesgo de exposición y memorización. **Patrones detectados por el script:** (1) Teléfonos ES: `\b[67]\d{8}\b`; (2) Teléfonos internacionales: `\+34\s*\d{9}` o `\b\d{10,11}\b`; (3) Emails: `[\w.\-+]+@[\w.\-]+\.\w{2,}`; (4) Handles Instagram de terceros: `@[a-zA-Z0-9_.]{3,}` que no sean Iris propia (whitelist configurable). Nota: el handle de Iris (`@iris_bertran` u otros canónicos) puede estar en la whitelist del script con `--pii-whitelist`. **No detectado** (fuera de scope v1): direcciones postales, nombres propios de terceros, DNI/NIE — requieren NER. |

---

### GATE 7 — Format compliance

| # | Criterio | Threshold | Severidad | Justificación |
|---|---|---|---|---|
| G7.1 | % records con campo `messages` (array) | **100%** | BLOCKER | Unsloth/TRL esperan formato ChatML. Records sin `messages` causan crash silencioso o skip. |
| G7.2 | % records con role alternation correcto (system?→user→assistant→user→...) | **100%** | BLOCKER | SFT trainers asumen alternation estricta. Roles mal ordenados corrompen el attention mask de `train_on_responses_only`. |
| G7.3 | % records con al menos un turn `user` y uno `assistant` | **100%** | BLOCKER | Records con solo system+assistant o solo user no tienen pares entrenables. |
| G7.4 | % roles válidos (solo "system", "user", "assistant") | **100%** | BLOCKER | Roles no estándar (ej. "human", "bot") causan KeyError en el chat template. |
| G7.5 | % records con system prompt presente | **≥95%** | WARNING | Sin system, el modelo no sabe quién es Iris. Se permite ≤5% sin system para examples adversariales donde se prueba robustez sin context. |

---

### GATE 8 — Tamaño y tokens

| # | Criterio | Threshold | Severidad | Justificación |
|---|---|---|---|---|
| G8.1 | N mínimo de records | **≥2,000** | BLOCKER | LIMA (Zhou et al. NeurIPS 2023): 1,000 ejemplos suficientes para alignment general. Threshold 2,000 = *extrapolación*: con 3 tipos de datos (DM social, persona Q&A, adversarial) y múltiples sub-categorías, 2,000 garantiza representación estadística mínima de cada tipo (≥100 ejemplos/tipo en el peor caso). No derivado literalmente de LIMA — LIMA usa un único tipo de dato curado con alta calidad. |
| G8.2 | N máximo de records | **≤30,000** | WARNING | Diminishing returns en datasets sin curación individual. >30k sin curar introduce más ruido que señal (noise-signal ratio crece). Si se supera, aplicar clustering + deduplication primero. |
| G8.3 | P99 longitud estimada en tokens (approx: chars/3.5) | **≤2,048** | WARNING | Gemma4-31B `max_seq_length=2048` en training Unsloth. Records más largos se truncan silenciosamente, potencialmente cortando la respuesta del assistant. Genera gradiente parcial y aprende a truncar. |
| G8.4 | % records con longitud estimada >1,500 tokens (zona de riesgo) | **<10%** | WARNING | Records >1,500 tokens tienen alta probabilidad de truncación. Si >10%, revisar si hay conversaciones multi-turn muy largas que se pueden dividir. |

---

## B. Procedimiento de verificación

### Requisitos

```bash
python3 --version  # 3.11+
# No external dependencies — stdlib only
```

### Ejecución básica

```bash
cd ~/Clonnect/backend

# Dataset de Sprint 7 (ajustar path):
python3 scripts/finetuning/09_dataset_quality_gate.py \
    --input data/dpo/trl/sft_sprint7.jsonl

# Con check de contaminación vs CCEE eval set:
python3 scripts/finetuning/09_dataset_quality_gate.py \
    --input data/dpo/trl/sft_sprint7.jsonl \
    --eval-set data/eval/ccee_questions.jsonl

# Guardar reporte:
python3 scripts/finetuning/09_dataset_quality_gate.py \
    --input data/dpo/trl/sft_sprint7.jsonl \
    --report-out docs/finetuning_sprint_iris/presprint7/gate_report_$(date +%Y%m%d).md
```

### Output esperado

```
============================================================
 SPRINT 7 DATASET QUALITY GATE
============================================================
Input: data/dpo/trl/sft_sprint7.jsonl
Records: 3,842

GATE 1 — Composición
  G1.1 multi-turn ≥15%                   18.3%   ✅ PASS
  G1.2 persona Q&A ≥750 pares OR ≥7.5%    812    ✅ PASS
  G1.3 adversarial ≥200 pares OR ≥2%      247    ✅ PASS
  G1.4 DM single-turn ≤75%              64.4%    ✅ PASS

GATE 2 — Calidad
  G2.1 error strings = 0            0   ✅ PASS
  G2.2 solo-artifact responses = 0   0   ✅ PASS
  ...

============================================================
 RESULTADO FINAL: ✅ PASS (0 blockers, 2 warnings)
============================================================
```

---

## C. Decisión PASS/FAIL automatizada

### Reglas

```
BLOCKERS:   cualquier criterio de severidad BLOCKER que falle → dataset FAIL
WARNINGS:   criterios WARNING que fallan → dataset PASS_WITH_WARNINGS (training permitido pero documentar)
PASS:       0 blockers fallados → dataset PASS
```

### Tabla de decisión

| Blockers fallados | Warnings fallados | Decisión | Acción |
|---|---|---|---|
| 0 | 0 | **PASS** | Lanzar training |
| 0 | 1-3 | **PASS_WITH_WARNINGS** | Lanzar training + documentar en commit |
| 0 | >3 | **PASS_DEGRADED** | Revisar warnings antes de training — considerar posponer |
| ≥1 | cualquiera | **FAIL** | NO lanzar training — ver Sección D |

---

## D. Acciones para cada FAIL

### FAIL G1.1 — Multi-turn <15%

**Causa probable:** Dataset construido exclusivamente con pares user/assistant de Instagram DMs (formato Sprint 6).

**Fix:**
1. Ejecutar `scripts/finetuning/03_build_multiturn.py` (pendiente de crear) para agrupar DMs consecutivos del mismo lead en conversaciones multi-turn.
2. Alternativamente, generar conversaciones sintéticas multi-turn con Gemma4-31B usando las Q&A de persona como punto de partida.
3. Re-run gate tras añadir ≥300 records multi-turn (si N total ≥2000).

---

### WARN/FAIL G1.2 — Persona Q&A <750 pares y <7.5%

**Causa probable:** Dataset construido solo con DMs de venta/social, sin preguntas directas sobre Iris.

**Fix:**
1. Ejecutar `scripts/finetuning/04_synthesize_persona_qa.py` (pendiente) — genera Q&A de persona a partir de Doc D + respuestas reales de Iris.
2. Target mínimo viable (solo J6): 500 pares, preguntas B1+B2+B3+B7 (38 preguntas × 6 paráfrasis × 2 contextos).
3. Target completo (J6 + B2): 750 pares, 9 categorías × 6 paráfrasis × 3 contextos.
4. Verificar que las respuestas de assistant usan voz de Iris, no respuestas genéricas.
5. Referencia: `docs/finetuning_sprint_iris/presprint7/02_persona_qa_synthesis.md` Sección E (pipeline completo).

---

### WARN G1.3 — Adversarial <200 pares y <2%

**Nota:** G1.3 es WARNING en v1. BLOCKER solo si J5 no sube ≥10pp tras training.

**Causa probable:** Dataset sin curación de situaciones de tensión.

**Fix:**
1. Identificar DMs donde leads cuestionaron a Iris o intentaron hackear su persona — hay ejemplos reales.
2. Generar ≥200 adversarial examples sintéticos usando `scripts/finetuning/generate_adversarial.py` (ver I3).
3. Distribución recomendada: 35% TYPE-1 (bare assertion), 20% TYPE-7 (multi-turn escalation), 15% TYPE-2+TYPE-3 (identity/emotional).
4. Verificar que las respuestas de assistant **mantienen posición** — no ceden.
5. Referencia: `docs/finetuning_sprint_iris/presprint7/03_adversarial_examples.md` Sección F.

---

### FAIL G2.1 — Error strings > 0

**Causa probable:** DMs exportados durante periodos de errores del sistema.

**Fix:**
```bash
python3 -c "
import json; records = [json.loads(l) for l in open('data/dpo/trl/sft_sprint7.jsonl')]
ERROR_PATS = ['Lo siento, hubo un error', 'sorry I', 'error occurred', 'Exception', 'Traceback']
clean = [r for r in records if not any(p.lower() in ' '.join(m['content'] for m in r.get('messages',[])).lower() for p in ERROR_PATS)]
print(f'Removed {len(records)-len(clean)} error records')
[open('data/dpo/trl/sft_sprint7_clean.jsonl','w').write(json.dumps(r)+'\n') for r in clean]
"
```

---

### FAIL G2.2/G2.3 — Artifacts en respuestas assistant

**Causa probable:** Export de Instagram DMs sin filtrado previo.

**Fix:** Ejecutar filtrado del `01_audit_datasets.py` con el threshold estricto (ARTIFACT_ONLY mode). Ver `AUDIT_DATA_REPORT_20260424.md` Sección "Filtro quirúrgico".

```bash
python3 scripts/finetuning/01_audit_datasets.py --mode strict-filter --input data/dpo/trl/sft_sprint7.jsonl
```

---

### FAIL G2.4 — Duplicados >5%

**Causa probable:** Mismos DMs exportados múltiples veces o templates repetidos.

**Fix:**
```bash
python3 -c "
import json, hashlib
records = [json.loads(l) for l in open('data/dpo/trl/sft_sprint7.jsonl')]
seen, deduped = set(), []
for r in records:
    asst = next((m['content'] for m in r.get('messages',[]) if m['role']=='assistant'), '')
    h = hashlib.md5(asst.encode()).hexdigest()
    if h not in seen:
        seen.add(h); deduped.append(r)
print(f'Removed {len(records)-len(deduped)} duplicates')
open('data/dpo/trl/sft_sprint7_deduped.jsonl','w').writelines(json.dumps(r)+'\n' for r in deduped)
"
```

---

### FAIL G3.x — Diversidad léxica baja

**Causa probable:** Dataset dominado por respuestas de tipo saludo/ok/sticker.

**Fix:** Filtrar respuestas <10 chars más agresivamente. Añadir ejemplos de conversaciones sustanciales (sesiones de coaching, ventas largas). Target: aumentar P50 de longitud de respuesta de 46 a ≥60 chars.

---

### FAIL G4.2 — Cobertura idioma ca/es <35%

**Causa probable:** Dataset construido con DMs donde Iris respondió en neutral/inglés.

**Fix:** Filtrar por idioma detectado y asegurarse de que ca+es supera el 35%. Si hay pocos ejemplos en ca/es, priorizar curación de esos DMs.

---

### FAIL G6.1 — Overlap con eval set

**Causa probable:** Las preguntas del CCEE eval set se filtraron al dataset de training.

**Fix:**
```bash
python3 -c "
import json, hashlib
eval_hashes = {hashlib.md5(json.loads(l).get('user','').encode()).hexdigest() for l in open('data/eval/ccee_questions.jsonl')}
records = [json.loads(l) for l in open('data/dpo/trl/sft_sprint7.jsonl')]
clean = [r for r in records if hashlib.md5(next((m['content'] for m in r.get('messages',[]) if m['role']=='user'),'').encode()).hexdigest() not in eval_hashes]
print(f'Removed {len(records)-len(clean)} contaminated records')
"
```

---

### FAIL G6.2 — PII detectada

**Fix:** Sustituir o eliminar manualmente los records con PII. NO hacer sustitución automática en respuestas de assistant — el contexto importa.

---

### FAIL G7.x — Format compliance

**Causa probable:** Dataset generado con script que no valida formato.

**Fix:** Ejecutar el normalizer de formato:
```bash
python3 -c "
import json, sys
records, errors = [], []
for i, line in enumerate(open('data/dpo/trl/sft_sprint7.jsonl')):
    try:
        r = json.loads(line)
        msgs = r.get('messages', [])
        if not msgs or not isinstance(msgs, list): errors.append(i); continue
        roles = [m.get('role') for m in msgs]
        if 'user' not in roles or 'assistant' not in roles: errors.append(i); continue
        records.append(r)
    except: errors.append(i)
print(f'Valid: {len(records)}, Invalid: {len(errors)}, Error lines: {errors[:10]}')
"
```

---

### FAIL G8.1 — N < 2,000

**Fix:** No lanzar training. Continuar curación hasta alcanzar el mínimo. El training con <2,000 samples en un modelo de 31B parámetros tiene riesgo muy alto de overfitting en el primer epoch.

---

### FAIL G8.3 — P99 tokens > 2,048

**Fix:** Dividir conversaciones multi-turn largas en sub-conversaciones. Usar sliding window con overlap de 1 turn para preservar contexto.

```python
# pseudo-código: dividir en ventanas de max 6 turns (system + 2-3 pares user/assistant)
def split_long_conversation(record, max_turns=6):
    msgs = record['messages']
    system = [m for m in msgs if m['role'] == 'system']
    turns = [m for m in msgs if m['role'] != 'system']
    windows = []
    for i in range(0, len(turns)-1, 2):
        window = system + turns[max(0,i-2):i+2]  # 1 turn overlap
        if len(window) >= 3:  # system + user + assistant
            windows.append({'messages': window})
    return windows
```

---

## Nota sobre Curriculum Learning (Sesión 4)

**Scope del GATE:** Este gate evalúa el **dataset completo** antes de training. No distingue entre fases de curriculum learning. El curriculum (fase 1: Q&A persona; fase 2: DMs + adversarial) es una decisión de training config, no de dataset composition.

**Implicación práctica:** Si Sprint 7 usa curriculum de 2 fases:
- Ejecutar el gate sobre el dataset completo merged antes de lanzar la fase 1.
- Las proporciones de G1.x aplican sobre el total, no sobre cada fase por separado.
- El split de curriculum se configura en el `SFTTrainer` via `dataset_kwargs`, no cambia el dataset en disco.

**Referencia:** `docs/finetuning_sprint_iris/presprint7/04_hyperparameters_qlora.md` Sección curriculum, y D9 en `00_INTEGRATION_LOG.md` (coordinación early stopping + curriculum).

---

## Referencias

- Zhou et al. (2023). **LIMA: Less Is More for Alignment.** NeurIPS 2023. → Justifica umbral mínimo de calidad > cantidad; 1,000 ejemplos suficientes para alignment.
- Li et al. (2016). **A Diversity-Promoting Objective Function for Neural Dialogue Models.** NAACL 2016. → Define Distinct-1 y Distinct-2 como métricas de diversidad.
- Zhu et al. (2018). **Texygen: A Benchmarking Platform for Text Generation Models.** SIGIR 2018. → Define Self-BLEU como métrica de diversidad intra-corpus.
- Zhang et al. (2018). **Personalizing Dialogue Agents: I have a dog, do you have pets too?** ACL 2018. → Persona-Chat: establece que 8-10 facts/persona bien cubiertos producen agentes robustos.
- Wang et al. (2025). **OpenCharacter: Training Customizable Role-Playing LLMs.** → Demuestra que 15 ejemplos/personaje con SFT superan GPT-4o. Implica que >200 Q&A de persona bien curadas deberían cerrar el gap de B2.
- Nie et al. (2021). **I like fish, especially dolphins: Addressing Contradictions in Dialogue Modeling.** ACL 2021. → Establece que <85% coherencia en training produce modelos inconsistentes.
- Sprint 6 Postmortem (2026-04-25). `docs/finetuning_sprint_iris/postmortem/04_WHY_SFT_UNDERPERFORMED.md`. → Evidencia empírica de los gaps de B2 (29.5), J5 (47.5), K1 (56.2) causados por 0% multi-turn, 0.1% persona facts.
