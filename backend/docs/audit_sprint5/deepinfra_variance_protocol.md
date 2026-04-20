# DeepInfra Variance Protocol — Sesiones 2 & 3

**Worker:** DI-VAR  
**Branch:** `worker/deepinfra-variance`  
**Objetivo:** Medir varianza inter-sesión de CCEE usando DeepInfra directo (sin OpenRouter), para determinar si es un protocolo más estable para futuros A/Bs.

**Nomenclatura:** Cada "sesión" = 1 día de medición = 1 ejecución de run_ccee.py con `--runs 3`. Los 3 "runs" son internos a cada sesión (repeticiones dentro del mismo día para calcular std intra-sesión). La varianza que nos importa es **inter-sesión** (día 1 vs día 2 vs día 3).

---

## Contexto

OpenRouter introduce varianza extra por load balancing entre proveedores.  
Hipótesis: DeepInfra directo → menor varianza inter-sesión → mejores A/B stats.

Baseline OpenRouter conocido (mismo Doc D, mismo pipeline P0+P1):
- `distill_AB_OFF_20260419_2214.json` → **v5_composite = 66.4** (provider=openrouter, model=google/gemma-4-31b-it)

---

## Config

```bash
# Fuente: config/env_ccee_gemma4_31b_full.sh
LLM_PRIMARY_PROVIDER=deepinfra
DEEPINFRA_MODEL=google/gemma-4-31B-it   # nota: B mayúscula — verificado en DeepInfra API
ACTIVE_MODEL=gemma-4-31b-it
CCEE_NO_FALLBACK=1
# + todos los flags P0+P1 (23 sistemas) del env_ccee_gemma4_31b_full.sh
```

---

## Cómo ejecutar Sesiones 2 y 3 (Manel los lanza manualmente)

**IMPORTANTE:** Cada sesión debe ser en el mismo commit (`worker/deepinfra-variance`, HEAD al momento de lanzar sesión 1). Verificar con `git log --oneline -1`.

### Sesión 2 — Día 2 (2026-04-21)

```bash
cd ~/Clonnect/backend
git checkout worker/deepinfra-variance
git log --oneline -1   # verificar mismo commit que run 1

# Cargar env
source config/env_ccee_gemma4_31b_full.sh
export $(grep -v '^#' .env | grep DEEPINFRA_API_KEY | xargs)

# Lanzar
nohup .venv/bin/python3 -W ignore::FutureWarning -u scripts/run_ccee.py \
    --creator iris_bertran \
    --runs 3 --cases 50 \
    --multi-turn --v4-composite --v5 \
    --save-as "di_variance_s2_$(date +%Y%m%d_%H%M)" \
    > /tmp/di_variance_s2.log 2>&1 &

echo "PID: $! — tail -f /tmp/di_variance_s2.log"
```

Duración esperada: ~2.5h (3 runs × ~350s pipeline + MT + v5 judge). Monitorear con `tail -f /tmp/di_variance_s2.log`.

### Sesión 3 — Día 3 (2026-04-22)

```bash
cd ~/Clonnect/backend
git checkout worker/deepinfra-variance
git log --oneline -1   # verificar mismo commit

source config/env_ccee_gemma4_31b_full.sh
export $(grep -v '^#' .env | grep DEEPINFRA_API_KEY | xargs)

nohup .venv/bin/python3 -W ignore::FutureWarning -u scripts/run_ccee.py \
    --creator iris_bertran \
    --runs 3 --cases 50 \
    --multi-turn --v4-composite --v5 \
    --save-as "di_variance_s3_$(date +%Y%m%d_%H%M)" \
    > /tmp/di_variance_s3.log 2>&1 &

echo "PID: $! — tail -f /tmp/di_variance_s3.log"
```

---

## Análisis final (tras sesión 3)

Con los 3 JSONs `di_variance_s{1,2,3}_*.json` disponibles:

```python
import json, glob, numpy as np

files = sorted(glob.glob('tests/ccee_results/iris_bertran/di_variance_s*.json'))
scores = []
for f in files:
    d = json.load(open(f))
    v5 = d.get('v5_composite', {}).get('score')
    print(f'{f}: v5={v5}')
    if v5: scores.append(v5)

print(f'\nDeepInfra: mean={np.mean(scores):.1f}, std={np.std(scores):.2f}, '
      f'range={max(scores)-min(scores):.1f}')
print(f'OpenRouter known: OFF=66.4 (1 point), arc3_OFF=67.6 (1 point)')
print('Compare std — lower in DI → prefer DI for future A/Bs')
```

**Decisión umbral:** Si σ(DI) < σ(OR) estimado (±3-4 puntos), adoptar DeepInfra como protocolo estándar CCEE.

---

## Artefactos

- Sesión 1 (día 1): `tests/ccee_results/iris_bertran/di_variance_run1_20260420_1329.json` ← save-as histórico, sesión 1 se lanzó antes de fijar nomenclatura
- Sesión 2 (día 2): `tests/ccee_results/iris_bertran/di_variance_s2_YYYYMMDD_HHMM.json`
- Sesión 3 (día 3): `tests/ccee_results/iris_bertran/di_variance_s3_YYYYMMDD_HHMM.json`
- Reporte sesión 1: `docs/audit_sprint5/deepinfra_variance_run1.md`
- Este protocolo: `docs/audit_sprint5/deepinfra_variance_protocol.md`
