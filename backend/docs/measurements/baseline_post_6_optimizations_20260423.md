# Baseline CCEE v5.3 — Post-6-Optimizations — 2026-04-23

**Fecha:** {{X: fecha ejecución}}  
**Branch:** prep/ccee-baseline-post-consolidation  
**Includes:** {{X: lista PRs/sistemas incluidos}}  
**Flags:** `--multi-turn --v4-composite --v41-metrics --v5 --v52-fixes`  
**Config:** 3 runs × 50 casos + 5 MT conv × 10 turns  
**Model:** Gemma 4 31B Dense (DeepInfra) — `config/env_ccee_gemma4_31b_full.sh`  
**JSON output:** `tests/ccee_results/iris_bertran/baseline_post_6_optimizations_20260423.json`  
**Baseline ref:** `tests/ccee_results/iris_bertran/ccee_v52_31b_baseline_merged.json` (v5=62.9, v4-style=57.49)

---

## Comando ejecutado

```bash
source config/env_ccee_gemma4_31b_full.sh && \
railway run python3 scripts/run_ccee.py \
  --creator iris_bertran \
  --runs 3 \
  --cases 50 \
  --multi-turn \
  --mt-conversations 5 \
  --mt-turns 10 \
  --v4-composite \
  --v41-metrics \
  --v5 \
  --v52-fixes \
  --compare tests/ccee_results/iris_bertran/ccee_v52_31b_baseline_merged.json \
  --output-md docs/measurements/baseline_post_6_optimizations_20260423.md \
  --save-as baseline_post_6_optimizations_20260423
```

---

## Resultados brutos

| Protocolo | Este baseline | Baseline v5.2 ref | Δ |
|-----------|:-------------:|:-----------------:|:---:|
| v5        | **{{X}}**     | 62.9              | **{{X}}** |
| v4-style  | **{{X}}**     | 57.49             | **{{X}}** |
| v4.1      | **{{X}}**     | —                 | — |

σ_intra (std 3 runs): **{{X}}**

### Per-run composites (v4-style)

| run1 | run2 | run3 | mean |
|:----:|:----:|:----:|:----:|
| {{X}} | {{X}} | {{X}} | {{X}} |

---

## Δ vs Baseline v5.2 (57.49 / 62.9)

| Dim | Baseline v5.2 | Este baseline | Δ | p-value | Cliff's d | Effect |
|-----|:-------------:|:-------------:|:-:|:-------:|:---------:|:------:|
| S1 Style Fidelity | 66.7 | {{X}} | **{{X}}** | {{X}} | {{X}} | {{X}} |
| S3 Strategic Alignment | 54.6 | {{X}} | **{{X}}** | {{X}} | {{X}} | {{X}} |
| B2 Persona Consistency | 38.5 | {{X}} | **{{X}}** | {{X}} | {{X}} | {{X}} |
| C3 Contextual Approp. | 21.0 | {{X}} | **{{X}}** | {{X}} | {{X}} | {{X}} |
| J6 Q&A Consistency | 82.5 | {{X}} | **{{X}}** | {{X}} | {{X}} | {{X}} |
| L1 Persona Tone | 80.5 | {{X}} | **{{X}}** | {{X}} | {{X}} | {{X}} |
| K2 Style Retention | 97.94 | {{X}} | **{{X}}** | {{X}} | {{X}} | {{X}} |
| H1 Turing Test | 80.0 | {{X}} | **{{X}}** | scalar | n/a | n/a |
| v4-style composite | 57.49 | {{X}} | **{{X}}** | {{X}} | {{X}} | {{X}} |
| v5 composite | 62.9 | {{X}} | **{{X}}** | scalar | n/a | n/a |

*Tabla generada automáticamente por `--compare --output-md`. Rellenar {{X}} con output del script.*

---

## Dimensiones primarias

### S1 Style Fidelity

| Param | run1 | run2 | run3 | mean | Δ vs ref |
|-------|------|------|------|------|:--------:|
| A1 Length | {{X}} | {{X}} | {{X}} | {{X}} | {{X}} |
| A2 Emoji | {{X}} | {{X}} | {{X}} | {{X}} | {{X}} |
| A3 Exclamations | {{X}} | {{X}} | {{X}} | {{X}} | {{X}} |
| A4 Questions | {{X}} | {{X}} | {{X}} | {{X}} | {{X}} |
| A5 Vocabulary | {{X}} | {{X}} | {{X}} | {{X}} | {{X}} |
| A6 Language | {{X}} | {{X}} | {{X}} | {{X}} | {{X}} |
| A7 Fragmentation | {{X}} | {{X}} | {{X}} | {{X}} | {{X}} |
| A8 Formality | {{X}} | {{X}} | {{X}} | {{X}} | {{X}} |
| A9 Catchphrases | {{X}} | {{X}} | {{X}} | {{X}} | {{X}} |

**S1 mean**: {{X}} (Δ={{X}} vs ref 66.7)

### B2 Persona Consistency

Score: **{{X}}** (ref=38.5, Δ={{X}})  
Evaluador: Qwen3-30B-A3B, 50 casos

### L1 Persona Tone

Score: **{{X}}** (ref=80.5, Δ={{X}})  
MT: 5 conv × 10 turns

### H1 Turing Test

Score: **{{X}}%** (ref=80.0, Δ={{X}})  
Método: {{X: MT DB-backed / ST Qwen3}}

---

## Dimensiones secundarias

### S3 Strategic Alignment

| run1 | run2 | run3 | mean | Δ vs ref (54.6) |
|:----:|:----:|:----:|:----:|:---------------:|
| {{X}} | {{X}} | {{X}} | {{X}} | **{{X}}** |

### J6 Q&A Consistency

Score: **{{X}}** (ref=82.5, Δ={{X}})  
MT: 5 conv × 10 turns

### C3 Contextual Appropriateness

Score: **{{X}}** (ref=21.0, Δ={{X}})  
Evaluador: Qwen3-30B-A3B, 50 casos

### K2 Style Retention

Score: **{{X}}** (ref=97.94, Δ={{X}})  
MT: 5 conv × 10 turns

---

## Wilcoxon + Cliff's Delta

```
[output automático de --compare — pegar aquí]
{{X}}
```

---

## Gates aplicados por sistema

| Sistema | Flag env | ON/OFF | Δ observado |
|---------|----------|:------:|:-----------:|
| Doc D | siempre ON | ✓ | — |
| USE_COMPRESSED_DOC_D | USE_COMPRESSED_DOC_D=true | ON | {{X}} |
| Style Normalizer | ENABLE_STYLE_NORMALIZER=true | ON | {{X}} |
| RAG Semantic | ENABLE_RAG=true | ON | {{X}} |
| RAG Reranker | ENABLE_RERANKING=false | OFF | — |
| Memory Engine (ARC2) | ENABLE_MEMORY_ENGINE=true | ON | {{X}} |
| Episodic Memory | ENABLE_EPISODIC_MEMORY=true | ON | {{X}} |
| Context Detection | ENABLE_CONTEXT_DETECTION=true | ON | {{X}} |
| Frustration Detection | ENABLE_FRUSTRATION_DETECTION=true | ON | {{X}} |
| DNA Triggers | ENABLE_DNA_TRIGGERS=true | ON | {{X}} |
| SalesIntentResolver | ENABLE_SELL_ARBITER_LIVE=true | ON | {{X}} |
| Style Anchor | ENABLE_STYLE_ANCHOR=true | ON | {{X}} |
| Question Remover | ENABLE_QUESTION_REMOVAL=true | ON | {{X}} |
| Memory Consolidation | ENABLE_MEMORY_CONSOLIDATION=true | ON | {{X}} |
| Gold Examples | ENABLE_GOLD_EXAMPLES=false | OFF | — |
| Length Hints | (no flag) | OFF | — |

---

## Conclusión y tracker final

**Resultado:** v5={{X}}, v4-style={{X}}, σ={{X}}

**Veredicto Wilcoxon:** {{X: IMPROVES / HURTS / NO_EFFECT}} (p={{X}}, Cliff's d={{X}})

### Regresiones (Δ < -1.0)
{{X: ninguna / listado}}

### Mejoras confirmadas (Δ > +1.0)
{{X: listado}}

### Sistemas a revisar post-medición
{{X: basado en regresiones}}

---

*Generado: 2026-04-23 — Para rellenar post-ejecución CCEE 50×3*
