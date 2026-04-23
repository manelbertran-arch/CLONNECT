# CCEE Execution — Post-6-Optimizations Baseline

**Branch:** prep/ccee-baseline-post-consolidation  
**Fecha prevista:** post-consolidación 6 PRs  
**Creator:** iris_bertran  
**Protocolo:** v5.2 (--v5 --v52-fixes) + v4.1 (--v41-metrics) + v4-composite + multi-turn

---

## Prerequisitos

1. Los 6 PRs de optimización están mergeados en `main`
2. Railway ha desplegado el build limpio
3. Conectividad DeepInfra verificada: `curl https://api.deepinfra.com/v1/openai/models -H "Authorization: bearer $DEEPINFRA_API_KEY" | python3.11 -m json.tool | grep gemma`
4. Baseline de referencia disponible: `tests/ccee_results/iris_bertran/baseline_post_p4_live_v52_20260422.json`

---

## Comando de Ejecución Final

```bash
cd ~/Clonnect/backend && \
source config/env_ccee_gemma4_31b_full.sh && set -a && source .env && set +a && \
export CCEE_NO_FALLBACK=1 && \
python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
  --creator iris_bertran --runs 3 --cases 50 \
  --multi-turn --mt-conversations 5 --mt-turns 10 \
  --v4-composite --v41-metrics --v5 --v52-fixes \
  --save-as baseline_post_6_optimizations_20260423 \
  --compare tests/ccee_results/iris_bertran/baseline_post_p4_live_v52_20260422.json \
  2>&1 | tee /tmp/baseline_post_6_optimizations_20260423.log
```

**Flags obligatorios:** `--v4-composite --v41-metrics --v5 --v52-fixes` (los 4, siempre juntos)  
**Python:** `python3.11` (NO 3.14)  
**CCEE_NO_FALLBACK:** `1` (exportado explícitamente)  
**Tiempo estimado:** ~90–120 min (3 runs × 50 cases + 5 MT conv × 10 turns + Qwen3 judging)

---

## Qué activa `env_ccee_gemma4_31b_full.sh`

| Grupo | Sistemas |
|-------|---------|
| Modelo | `google/gemma-4-31B-it` vía DeepInfra |
| P0 (10 sistemas) | Doc D, StyleNorm, FewShot, PoolMatch, IntentScore, MemoryEngine, DNA, ConvState, LengthHints, Guardrails |
| P1 Injection (8) | ContextDetect, FrustrationDetect, SensitiveDetect, RelDetect, RAG (1 result), EpisodicMemory, Citations |
| P1 PostProc (5) | QuestionRemoval, OutputValidation, ResponseFixes, MessageSplitting, BlacklistReplacement |
| Extras | StyleAnchor ON, Compaction ON, **CCEE_NO_FALLBACK=1** |
| Confirmados OFF | GoldExamples, RelAdapter, PreferenceProfile, ScoreBeforeSpeak, PPA, Echo |

---

## compare_with_baseline() — Dimensiones cubiertas

Activado por `--compare`. Calcula Δ + Wilcoxon + Cliff's delta para:

| Dimensión | n muestras | Wilcoxon? |
|-----------|:----------:|:---------:|
| S1 Style Fidelity | 50×runs per-case | ✓ |
| S3 Strategic Alignment | 50×runs per-case | ✓ |
| B2 Persona Consistency | 50 Prometheus per-case | ✓ |
| C3 Contextual Approp. | 50 Prometheus per-case | ✓ |
| J6 Q&A Consistency | 5 per-conversation | ✓ mínimo |
| L1 Persona Tone | 5 per-conversation | ✓ mínimo |
| K2 Style Retention | 5 per-conversation | ✓ mínimo |
| H1 Turing Test | scalar | Δ only |
| v4-style composite | 3 per-run | ✓ |
| v5 composite | scalar | Δ only |

---

## Output

- **JSON:** `tests/ccee_results/iris_bertran/baseline_post_6_optimizations_20260423.json`
- **Log:** `/tmp/baseline_post_6_optimizations_20260423.log`
- **Template doc:** `docs/measurements/baseline_post_6_optimizations_20260423.md` (rellenar {{X}} con resultados del JSON)

---

## Baseline de referencia (`baseline_post_p4_live_v52_20260422.json`)

| Protocolo | Score | σ |
|-----------|:-----:|:---:|
| v5 | 67.7 | 0.43 |
| v4-style | 68.0 | — |

Dimensiones clave: S1=64.1, S2=67.2, S3=76.2, S4=63.3, J3=82.5, J4=64.0, J5=67.5, J6=35.0, K1=68.1, K2=86.4, G5=60.0, H1=82.0, B2=28.5, B5=49.0

---

## Si DeepInfra no responde

```bash
python3.11 -c "
import os, requests
r = requests.get(
    'https://api.deepinfra.com/v1/openai/models',
    headers={'Authorization': f'bearer {os.environ[\"DEEPINFRA_API_KEY\"]}'},
    timeout=10
)
print(r.status_code, 'gemma' in r.text)
"
```

Si falla: NO lanzar. Investigar token / quota antes de consumir 120 min de run.
