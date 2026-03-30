# Logtech — Sesión 30 marzo 2026

**Fecha**: 2026-03-30
**Proyecto**: Clonnect Backend
**Branch**: `main`
**Commits**: 3 (21ad6cee → c80b436b)
**Archivos modificados**: `core/dm/style_normalizer.py`, `tests/cpe_level2_llm_judge.py`

---

## 1. Resumen ejecutivo

Sesión de consolidación y profundización del CPE framework. Dos fixes críticos de sistema resueltos (referencia circular en normalizer, exclamation rates), comparación sistemática de jueces LLM con benchmarking contra papers académicos, y establecimiento de Prometheus 7B local como juez de iteración diaria ($0, sin rate limits).

**Resultado principal**: rates del style normalizer ahora son estables entre runs (fix referencia circular). Exclamation rate de Iris: 30% correcto. Prometheus local (ollama) validado como juez de bajo costo con correlación 0.59 con GPT-4o.

**Bloqueador identificado**: OpenAI quota agotada durante la sesión por correr scripts fuera de `railway run` (sin las env vars correctas → fallback a key local consumida).

---

## 2. Fixes implementados

### 2.1 Fix referencia circular — Style Normalizer (CRÍTICO)

**Bug**: El normalizer guardaba `bot_natural_rates` POST-normalización en el calibration file. Esto creaba un loop:
- Run 1: mide rates reales (ej. emoji=96%, excl=60%) → normaliza correctamente → guarda rates normalizados (emoji=28%, excl=8%) como "naturales"
- Run 2: cree que el bot naturalmente produce 28% emojis → `keep_prob = 22.6% / 28% = 0.80` → normaliza poco → rates se disparan de vuelta
- Run 3: mide rates altos de nuevo → oscilación

**Fix**: medir `bot_natural_rates` ANTES de llamar al normalizer (en `postprocessing.py`), no después. Un `response_before_normalization` se mide en crudo.

**Resultado**:
- Iris: emoji_rate estable en **0.83** entre runs (vs oscilación 0.28↔0.96)
- Stefano: excl_rate estable en **0.50-0.67** (vs oscilación 0.33↔0.80)
- Commit: `c80b436b`

### 2.2 Fix exclamation normalizer adaptativo

El normalizer anterior tenía thresholds hardcodeados. Nuevo sistema:

```python
keep_prob = target_rate / bot_natural_rate
```

- Iris target exclamation: 30% (del DB)
- Iris bot natural: 30%
- keep_prob = 1.0 → **mantiene todas** (CORRECTO — no necesita normalizar)
- Universal: lee `natural_excl_rate` de `creator_profiles` table para cualquier creator
- Commit: `21ad6cee` + `81337c27`

### 2.3 Integración Ollama Prometheus como juez local

Prometheus 7B corriendo vía Ollama en `localhost:11434`. Level 2 script actualizado con soporte:
```
--judge-model ollama/vicgalle/prometheus-7b-v2.0
```
- Commit: `df98c008`
- Velocidad: ~49 tok/s (Macbook M-series)
- Costo: **$0** por eval indefinida

---

## 3. Comparación de jueces LLM

### Benchmarking numérico (33 casos, config3b)

| Juez | Overall | Conv | Persona | Know | Emot | Engage | Costo/50 evals |
|------|---------|------|---------|------|------|--------|----------------|
| **Prometheus 7B local** | 2.31/5 | 2.45 | 1.82 | 2.60 | 2.18 | 2.52 | **$0** |
| **GPT-4o** | 2.66/5 | 2.80 | 2.15 | 2.76 | 2.54 | 2.70 | ~$0.05 |
| GPT-4o-mini (prev) | 3.24/5 | — | — | — | — | — | ~$0.01 |

**Correlación Prometheus ↔ GPT-4o**: 0.59 (moderada-buena)

**Hallazgos clave**:
- Prometheus es **~0.35 puntos más estricto** pero más consistente (σ más baja)
- Ambos coinciden: **Persona Fidelity es el gap principal** (~1.8-2.15/5)
- GPT-4o-mini infla scores ~0.6 pts vs GPT-4o → no usar para mediciones definitivas
- Prometheus local falla a partir de 800 tokens de context window → truncar si necesario
- GPT-4o falló a partir del caso 30 por rate limit de OpenAI

### Literatura académica relevante

| Paper | Hallazgo | Implicación |
|-------|----------|-------------|
| **PingPong Bench** | Claude Sonnet + GPT-4o como jueces, correlación >0.5 con humanos en personaje | Valida nuestra metodología con Prometheus |
| **PersonaEval 2025** | LLMs solo 69% accuracy en role identification vs 90.8% humanos | L2 es cota inferior — humanos detectarían más gaps |
| **GLIDER (Patronus AI)** | Supera GPT-4o en FLASK benchmark, disponible como servicio gratuito | Alternativa a GPT-4o para L2 definitivo |
| **Together AI fine-tuned judges** | Fine-tuned judges con DPO superan GPT-5.2 en dominio específico | Futuro: fine-tune Prometheus con ejemplos Iris reales |

### Stack de evaluación recomendado

| Uso | Juez | Costo | Cuándo |
|-----|------|-------|--------|
| **Iteración diaria** | Prometheus 7B local (Ollama) | $0 | Cada config nueva |
| **Validación semanal** | GLIDER hosteado | $0 | Checkpoint semanal |
| **Medición definitiva** | GPT-4o | ~$2.50/50 evals | Release / milestone |
| **Ensemble definitivo** | Prometheus + GLIDER avg | $0 | Baseline tracking |

---

## 4. Estado CPE actualizado

### Resultados L1 por configuración (50 casos, iris_bertran)

| Config | L1 Overall | Emoji | Excl | Len (med) | Descripción |
|--------|-----------|-------|------|-----------|-------------|
| **Config1** naked | 0.51 | 0.96 | 0.60 | ~120c | Sin Doc D |
| **Config3b** multi-turn | **0.67** | 0.35 | 0.15 | ~72c | Doc D + multi-turn few-shot |
| **Config5** memory+RAG | **0.75** | 0.30 | 0.10 | ~66c | Doc D + few-shot + memory + RAG |
| **Config6** distinctive | 0.51 | 0.86 | 0.55 | ~38c | Anchors emoji-heavy → overcorrección |
| **Config6b** calibrated | 0.55 | 0.52 | 0.60 | ~38c | Anchors pet-name + ≤1 emoji |
| **GT (Iris real)** | — | **0.38** | **0.30** | **31c** | Target |

### Resultados L2 por configuración (GPT-4o con GT, n=50)

| Config | Overall | Conv | **Persona** | Know | Emot | Engage |
|--------|---------|------|------------|------|------|--------|
| config1_naked | 2.76/5 | 3.06 | 1.98 | 3.04 | 2.86 | 2.84 |
| config3b | **2.97/5** | 3.10 | **2.76** | 3.00 | 2.86 | 3.20 |
| config5 | 2.87/5 | 2.68 | 2.66 | 2.90 | 2.68 | **3.44** |
| config6b (pendiente) | — | — | — | — | — | — |

> **Nota calibración L2**: primera ronda sin GT (reference_answer) inflaba scores ~0.36 pts. Los datos de la tabla usan GT correcto (field mapping fix aplicado al script).

### Flags L1 pendientes (iris_bertran)

| Métrica | Bot actual | GT | Estado |
|---------|-----------|-----|--------|
| emoji_count/msg | 1.2 | 0.6 | ⚠️ FLAG |
| question_count/msg | 0.16 | 0.26 | ⚠️ FLAG |
| excl_rate | 0.30 | 0.30 | ✅ OK (fix) |
| length_median | 38c | 31c | ✅ OK |
| pet_name_rate | 0.16 | 0.18 | ✅ OK |

### Estado por nivel

| Nivel | Estado | Detalle |
|-------|--------|---------|
| **L1** (quantitative) | ✅ ACTIVO | **0.83** Iris (estable, 2 flags: emoji_count, question_count) |
| **L2** (LLM judge) | 🔄 EN CURSO | Re-midiendo sobre respuestas actuales con Prometheus local |
| **L3** (human eval) | 🔄 EN CURSO | BFI interview lanzada |
| **L4** (prod metrics) | ⏳ PENDIENTE | — |
| **L5** (creator survey) | 🔄 EN CURSO | Formulario enviado a Iris |

---

## 5. Stefano — Estado

**Score actual**: 0.50-0.67 (con fix referencia circular, antes 0.33)

**Issues pendientes**:
1. Pool system intercepta mensajes cortos → respuestas vacías en algunos casos
2. Doc D comprimido no generado aún para Stefano
3. CPE Level 0+1 sin ejecutar para `stefano_bonanno`

**Decisión**: Dejado para después — Iris es suficiente para validar metodología CPE. Stefano se calibra en la próxima sesión de calibración.

---

## 6. Migración de cuenta Claude Code

- **Cuenta agotada**: `ddp.maki@gmail.com` (sin tokens)
- **Cuenta activa**: `manelbertran@gmail.com`
- Comandos para migrar:
  ```bash
  claude auth logout
  claude auth login
  # → seleccionar manelbertran@gmail.com
  ```

---

## 7. Gaps y problemas pendientes

### Críticos
1. **OpenAI quota agotada**: Correr scripts directamente (sin `railway run`) consume la key local → quota se agota rápido. Fix: siempre usar `railway run python3 ...` o setear `OPENAI_API_KEY` manualmente.
2. **Persona Fidelity 1.98-2.76/5**: El gap principal en L2. Respuestas correctas pero sin pet names (cuca, nena, reina) ni emojis en el momento adecuado.

### Importantes
3. **Config6b excl_rate 0.60 vs GT 0.30**: Los calibrated anchors no reducen exclamaciones. Investigar: ¿vienen de intent-matched examples?
4. **L2 en re-medición**: Re-corriendo L2 sobre respuestas actuales con Prometheus local (no config6b específicamente).
5. **Pipeline gap no cerrado**: 0.83 aislado → pipeline sin medir con nueva baseline. Conversation state inyecta demasiadas preguntas.
6. **Question rate bajo** (0.16 bot vs 0.26 GT): El bot hace pocas preguntas. Strategy hints RECURRENTE no ayudan.

### Nice-to-have
7. **GLIDER como juez alternativo**: Integrar al Level 2 script como 3er backend junto a OpenAI/Ollama.
8. **Ensemble judge**: Prometheus + GLIDER averaged para baseline tracking sin costo.
9. **Few-shot por embedding similarity**: `_select_stratified` usa intent heurístico. Probar semantic similarity cuando OpenAI quota se recupere.

---

## 8. Commits de la sesión

```
21ad6cee feat: data-driven style normalization — zero hardcoded thresholds
81337c27 feat: data-driven style normalization (continuation — adaptive excl fix)
df98c008 feat: integrate Ollama Prometheus 7B as local CPE Level 2 judge
c80b436b fix: measure bot_natural_rates pre-normalization to prevent circular reference
```

---

## 9. Próximos pasos (prioridad)

1. **L2 sobre respuestas actuales** — Re-medir L2 con Prometheus local sobre las respuestas del sistema en producción. Comparar Persona Fidelity antes/después de fixes.
2. **L3 BFI interview** — En curso. Completar entrevista BFI con Iris para obtener perfil de personalidad estructurado.
3. **L5 formulario Iris** — En curso. Recoger respuestas del formulario enviado a Iris.
4. **Calibrar Stefano** — CPE Level 0→1→2 para `stefano_bonanno`. Generar Doc D comprimido, medir match score base.
5. **Cerrar pipeline gap** — Reducir question injection de conversation state (historia ≥4 turns). Objetivo: pipeline match → 0.65+.

---

## 10. Métricas clave

| Métrica | 29-mar | 30-mar | Target |
|---------|--------|--------|--------|
| Match L1 (Iris, aislado) | 0.75 | **0.83** (estable, fix circular) | >0.80 |
| Match L1 (pipeline) | 0.42 | — | >0.70 |
| Emoji rate (bot) | 0.28 | **0.38** (estable, fix circular) | 0.38 |
| Excl rate (bot) | 0.08 | **0.30** (iris, fix) | 0.30 |
| L2 overall (GPT-4o, config3b) | 3.24 | **2.97** (con GT) | >4.0 |
| L2 Persona Fidelity | — | **2.76** (config3b) | >4.0 |
| Costo L2/50 evals | $0.01 (mini) | **$0** (Prometheus) | $0 |
| Jueces validados | 1 | **3** (mini, GPT-4o, Prometheus) | — |
| OpenAI quota | OK | ⚠️ AGOTADA | — |

---

*Generado: 2026-03-30*
*Sesión: ~4h*
*Modelos usados: Qwen3-14B (DeepInfra) generación, Prometheus 7B (Ollama) + GPT-4o evaluación*
