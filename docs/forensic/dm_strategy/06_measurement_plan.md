# Fase 6 — Plan de medición CCEE

**Objetivo:** validar empíricamente los cambios de Fase 5 (PR `forensic/dm-strategy-20260423`) antes de merge a main, mediante CCEE 50×3 hot-path A/B sobre el baseline actual, más un plan E2 diferido Q2 2026 para el eje estilo portado al resolver S6.

**Creator target:** `iris_bertran` (único creator con bucket etiquetado y métricas CCEE v5 actualizadas).
**Baseline de referencia:** `backend/tests/ccee_results/iris_bertran/baseline_post_p4_live_20260422.json` (CCEE v5, 50 casos, 3 runs, composite v5 = **67.7**, B2 Persona Fidelity = **28.5**).

---

## 1. Experimento E1 — inmediato, dataset existente n=50

### 1.1 Arms

| Arm | Código | Configuración |
|-----|--------|---------------|
| **A** baseline | `main` actual (pre-Fase 5) | `ENABLE_DM_STRATEGY_HINT` no existe (hint ON always); L89-90 Iris hardcoded activo; `help_signals` ES inline; sin gate NO_SELL; sin métricas Prometheus strategy |
| **B** post-Fase 5 | `forensic/dm-strategy-20260423` merged | `ENABLE_DM_STRATEGY_HINT=true` (default); vocab_meta Iris bootstrapped via script; gate NO_SELL activo; métricas 4 counters emitiendo; L89-90 neutralizados; `help_signals` data-derived |

### 1.2 Método estadístico

- **CCEE 50×3 runs** por arm (50 casos del bucket × 3 runs = 150 observaciones por arm).
- **Test:** Wilcoxon signed-rank (paired, por caso) sobre composite v5, B2, S1, L1.
- **Effect size:** Cliff's delta (non-parametric, robusto ante no-normalidad).
- **σ intra-arm:** reportar desviación entre los 3 runs como proxy de estabilidad.
- **CCEE_NO_FALLBACK=1** obligatorio para detectar degradaciones LLM.

### 1.3 Dimensiones y objetivos

**Primarias** (mueven la decisión):
| Dim | Nombre | Baseline (Arm A) | Target (Arm B) | Mecanismo |
|-----|--------|------------------|----------------|-----------|
| B2 | Persona Fidelity | 28.5 | ≥ 30.0 (+1.5) | P4 limpio de "Iris" leak + apelativos creator-agnostic |
| S1 | Style Fidelity | (referir baseline_run.json) | mejora o estable | anti-bugs verbales via vocab_meta |
| L1 | Persona Tone | (referir baseline) | mejora o estable | `creator_display_name` dinámico |

**Secundarias** (monitorizar, no gate):
| Dim | Nombre | Expectativa |
|-----|--------|-------------|
| S3 | Strategic Alignment | estable — wording del hint inalterado para Iris post-bootstrap |
| H1 | Turing Test | estable o leve mejora — efecto compuesto |
| J6 | Judge Overall | debe seguir a B2+S1+L1 |

### 1.4 Gates de decisión E1

Aplicados sobre los resultados CCEE v5 comparando Arm B vs Arm A:

| Resultado | Condición | Acción |
|-----------|-----------|--------|
| **KEEP** | Δcomposite_v5 ≥ **+1.5** Y ninguna dimensión crítica con Δ < -2 | Merge PR a main |
| **REVERT** | Δcomposite_v5 ≤ **-1.5** O cualquier dimensión crítica con Δ < -3 | NO merge; revertir bootstrap; re-análisis |
| **INCONCLUSIVE** | Δcomposite_v5 ∈ (-1.5, +1.5) Y no hay regresión >2 | NO merge; análisis dimensión por dimensión; posible re-run con judge distinto o sub-bucket diferente |

**Dimensiones críticas:** B2, S1, L1, H1 (las 4 primarias + Turing).

### 1.5 Observación crítica para interpretar E1

De la **distribución medida en Fase 2** sobre el bucket real:
- **P4 RECURRENTE absorbe 90%** de los 50 casos (45/50).
- **Default (sin hint)** = 8% (4/50).
- **P6 VENTA heurístico** = 2% (1/50).
- **P1/P2/P3/P5/P7 = 0%** en este bucket.

Implicaciones:
1. **E1 mide casi exclusivamente el fix P4**: wording limpio sin "Iris"/"flower"/apelativos hardcoded, más el `creator_display_name` dinámico.
2. **Casos FAMILIA/AMIGO = 0%** en el bucket → el portado al resolver (BUG-004) es **invisible en E1**. Cero señal, ni positiva ni negativa. Esto es esperado y no cambia el gate.
3. **Gate NO_SELL contribución ≈ 0** en E1: con solo 1 caso VENTA y sin disparo NO_SELL del resolver en el bucket, la métrica `dm_strategy_gate_blocked_total` será ~0. La correctitud del gate se verifica por tests unitarios, no por CCEE.
4. **Interpretación si Δ es pequeño pero no negativo**: fix P4 funcionó (eliminamos riesgo universalidad), pero la ganancia en Iris es marginal porque el bootstrap reestablece casi el mismo wording operativo. **Este resultado es un KEEP razonable** si B2 se mantiene o mejora ligeramente — la principal ganancia es habilitar otros creators + preparar infra para E2.

### 1.6 Harness — configuración exacta

**Dataset bucket:**
```
backend/tests/cpe_data/iris_bertran/test_set_v2_stratified.json   # n=50, source de casos
backend/tests/ccee_results/iris_bertran/baseline_post_p4_live_20260422.json  # baseline Arm A a comparar
```

**Env file:** `backend/config/env_ccee_gemma4_31b_full.sh`
- Modelo: `google/gemma-4-31B-it` via DeepInfra
- Judge: `Qwen/Qwen3-30B-A3B`
- Flags P0 (10 sistemas) + P1 (8 sistemas) ON
- `USE_TEMPLATE_SYSTEM=true`

**Comando canónico** (Arm B run, ejecutar 3 veces con semillas distintas para σ):
```bash
source backend/config/env_ccee_gemma4_31b_full.sh
export ENABLE_DM_STRATEGY_HINT=true
export CCEE_NO_FALLBACK=1

# Run 1
railway run python3 backend/scripts/run_ccee.py \
    --creator iris_bertran \
    --runs 3 \
    --compare backend/tests/ccee_results/iris_bertran/baseline_post_p4_live_20260422.json \
    --output backend/tests/ccee_results/iris_bertran/forensic_dm_strategy_arm_b_run1.json
```

**Arm A**: el JSON baseline ya existe (`baseline_post_p4_live_20260422.json`). No requiere re-ejecución. `run_ccee.py --compare` produce los deltas contra este archivo automáticamente.

**Variance:** 3 runs por arm (ya configurado via `--runs 3` dentro del script). Reportar σ intra-arm en el resultado final.

---

## 2. Pasos pre-CCEE — secuencial, ejecutable post-merge

**Precondiciones**: Fase 5 mergeada a `main`, Railway deploy exitoso, smoke tests verdes.

### Paso 1 — Merge PR `forensic/dm-strategy-20260423`

Revisión manual + merge to `main`. Railway despliega automático (push a `main`).

**Verificación:** `railway deployment list` muestra nuevo deploy `SUCCESS` con commit del PR.

### Paso 2 — Smoke test post-deploy

```bash
curl -s -w "\nHTTP:%{http_code}" https://www.clonnectapp.com/health
railway logs -n 200 2>&1 | grep -v "SCORING-V3" | grep -i "error\|traceback" | head
```

**Esperado:** HTTP 200, sin errores nuevos en logs. Si hay errores, abortar y rollback del commit.

### Paso 3 — Bootstrap dry-run

```bash
railway run python3 backend/scripts/bootstrap_vocab_meta_iris_strategy.py --dry-run
```

**Esperado (primer run en Railway):**
```
INFO No existing vocab_meta row for iris_bertran; will INSERT.
INFO   apelativos: inserted (5 entries)
INFO   anti_bugs_verbales: inserted (1 entries)
INFO   openers_to_avoid: inserted (2 entries)
INFO   help_signals: inserted (15 entries)
INFO [DRY RUN] would insert vocab_meta for creator iris_bertran (...)
```

**Si ya había vocab_meta row existente** (bootstrap previo o Worker mining): output muestra `appended N new entries (kept M existing)` o `already covered — no-op`. Ambos casos OK.

### Paso 4 — Revisar output dry-run

Confirmar:
- Nombre de creator correcto.
- 4 claves (`apelativos`, `anti_bugs_verbales`, `openers_to_avoid`, `help_signals`) listadas.
- Si alguna ya existía, las listas se merge-an sin pérdida.
- No hay excepciones ni mensajes ERROR.

**Si dry-run falla:** investigar antes de ejecutar real (no forzar).

### Paso 5 — Bootstrap real

```bash
railway run python3 backend/scripts/bootstrap_vocab_meta_iris_strategy.py
```

**Esperado:** `INFO Inserted vocab_meta for iris_bertran.` o `INFO Updated vocab_meta for iris_bertran.` dependiendo de si había fila previa. Salida sin traceback.

**Idempotencia:** re-ejecutar el comando debe logear `INFO No changes required (fully idempotent, already seeded).` y salir con exit code 0.

### Paso 6 — Verificar Prometheus vocab_source

Esperar ~5 minutos de tráfico real en Railway, luego:
```bash
# Via Prometheus query (si dashboard público disponible)
sum by (source) (dm_strategy_vocab_source{creator_id="iris_bertran",vocab_type="apelativos"})
```

**Esperado:** `source=mined` > 0 para los 4 vocab_types (apelativos, anti_bugs_verbales, openers_to_avoid, help_signals). Ratio `mined / (mined+fallback)` debe ser > 0.8 para Iris.

**Si `fallback > 20%`** significa que la ruta DB lookup falló silenciosamente (logger.debug); revisar:
- `personality_docs[doc_type='vocab_meta']` tiene la fila correcta (`psql` o Supabase dashboard).
- `_load_creator_vocab` no lanza excepción (check `/admin/logs`).
- `creator_id` slug correcto (`iris_bertran`, no UUID).

### Paso 7 — Confirmar flag

```bash
railway variables get ENABLE_DM_STRATEGY_HINT 2>&1
# Si no está set: default = True via feature_flags.py:57
# Para set explícito:
railway variables set ENABLE_DM_STRATEGY_HINT=true
```

### Paso 8 — Ejecutar Arm B CCEE 50×3

```bash
source backend/config/env_ccee_gemma4_31b_full.sh
export ENABLE_DM_STRATEGY_HINT=true
export CCEE_NO_FALLBACK=1
export CCEE_RUN_TAG=forensic_dm_strategy_arm_b

railway run python3 backend/scripts/run_ccee.py \
    --creator iris_bertran \
    --runs 3 \
    --compare backend/tests/ccee_results/iris_bertran/baseline_post_p4_live_20260422.json \
    --output backend/tests/ccee_results/iris_bertran/forensic_dm_strategy_arm_b.json
```

Duración estimada: ~40-60 min (Gemma 4 31B + Qwen3 judge, 150 observaciones).

### Paso 9 — Análisis + aplicar gate

1. Cargar `forensic_dm_strategy_arm_b.json` y comparar con baseline (el script emite tabla Wilcoxon + Cliff's delta automático).
2. Aplicar gate §1.4:
   - **KEEP** → merge ya realizado, cerrar PR, documentar resultados en `docs/measurements/forensic_dm_strategy_e1_result.md`.
   - **REVERT** → `git revert <merge_commit>` + `git push`; rollback bootstrap via script opuesto; abrir issue post-mortem.
   - **INCONCLUSIVE** → NO merge adicional, dimensión por dimensión análisis, posible re-run con judge distinto o sub-bucket diferente.

---

## 3. Observabilidad durante Arm B

Monitorear durante los 3 runs del CCEE:

### 3.1 Distribución de ramas

```
sum by (branch) (dm_strategy_branch_total{creator_id="iris_bertran"})
```

**Esperado** (coincide con Fase 2 §3.2):
- `branch=RECURRENTE` ≈ 90%
- `branch=DEFAULT` ≈ 8%
- `branch=VENTA` ≈ 2%
- resto < 1%

**Si la distribución desvía** >15 pp (absolutos) de lo esperado, alerta: posiblemente hay un bug en la lógica de precedencia o el bucket cambió.

### 3.2 Cobertura vocab mined

```
sum by (vocab_type, source) (dm_strategy_vocab_source{creator_id="iris_bertran"})
```

**Esperado:** por vocab_type, `mined > 80%` del total.

**Abortar el run y regenerar bootstrap si:**
- `fallback > 20%` para cualquier vocab_type.
- `mined = 0` para un vocab_type esperado.

### 3.3 Gate NO_SELL

```
sum (dm_strategy_gate_blocked_total{creator_id="iris_bertran",reason="no_sell_overlap"})
```

**Esperado en el bucket actual:** ~0 (sólo 1 caso VENTA, y ese caso no tiene DNA FAMILIA etiquetado). El gate es correcto defensivamente pero no tiene impacto medible en E1.

### 3.4 Hint injection rate

```
rate = hint_injected_total / branch_total
```

**Esperado:** ≈ 92% (100% - 8% default). Los casos `default` no inyectan hint. Los demás sí, salvo gate bloqueos (≈0 en este bucket).

---

## 4. Experimento E2 — diferido Q2 2026

### 4.1 Pre-requisitos

1. **E1 KEEP**: Fase 5 merged y estable en Railway.
2. **Bucket ampliado**: worker separado construye bucket `iris_bertran_family_bucket_v1.json` con ~10-20 casos etiquetados con `dna_relationship_type ∈ {FAMILIA, INTIMA, AMISTAD_CERCANA}`.
3. **Portado al ArbitrationLayer implementado**: nuevo PR fuera de este scope que añade `aux_text` al resolver cuando `directive==NO_SELL ∧ dna ∈ {FAMILIA, INTIMA, AMISTAD_CERCANA}` con las 4 guidelines de estilo (brevedad data-derived char_p25/p75, concreción, directness, compartir detalles).

### 4.2 Arms

| Arm | Código | Configuración |
|-----|--------|---------------|
| **A'** | `main` post-E1 (Fase 5 merged) | Resolver sin `aux_text` estilo; strategy.py dormant P1/P2 |
| **B'** | PR portado-arbitration-layer | Resolver emite `aux_text` con 4 guidelines estilo para NO_SELL + family DNA |

### 4.3 Dataset E2

`iris_bertran_family_bucket_v1.json` — a construir por worker mining + labeling manual. Tamaño mínimo n=10, óptimo n=20 con distribución:
- FAMILIA: ~40%
- INTIMA: ~20%
- AMISTAD_CERCANA: ~40%

### 4.4 Gates E2

Mismos criterios que E1 pero aplicados sobre un composite "family only" (judge scoring exclusivo sobre casos con DNA ∈ family set):

| Resultado | Condición | Acción |
|-----------|-----------|--------|
| **KEEP** | Δ**B2_family** ≥ **+5** Y Δ**S1_family** ≥ **0** (no regresión) | Merge portado PR |
| **REVERT** | Δ**B2_family** ≤ **-2** O regresión en Turing | NO merge portado |
| **INCONCLUSIVE** | Δ pequeña | Análisis cualitativo judge comments |

Thresholds más estrictos que E1 porque el portado debería producir un efecto grande en el sub-bucket correcto. Una ganancia pequeña en casos labeled significaría que el portado no está fit para producción.

### 4.5 E2 es NO bloqueante de E1

E1 puede mergearse y correr independientemente. E2 es una mejora incremental que agrega cobertura al eje estilo FAMILIA/AMIGO pero no invalida el baseline E1.

---

## 5. Resumen ejecutivo Fase 6

### Secuencia de ejecución

1. **E1 inmediato** post-Fase 5 merge:
   - 9 pasos pre-CCEE (Paso 1 merge → Paso 8 ejecutar Arm B → Paso 9 gate).
   - Duración total: ~1-2 horas wall-clock.
   - Riesgo: bajo. Bootstrap idempotente, gate NO_SELL verificado por tests, distribución P4 90% coincide con baseline.

2. **E2 diferido Q2 2026**:
   - Depende de bucket FAMILIA/AMIGO ampliado (worker separado).
   - Portado al ArbitrationLayer en PR separado.
   - Mide eje estilo que hoy es invisible en CCEE.

### Observabilidad como early warning

Las 4 métricas Prometheus (`branch_total`, `hint_injected_total`, `vocab_source`, `gate_blocked_total`) son el **canario** durante Arm B. Permiten abortar el run antes de desperdiciar 40 min de compute si el bootstrap no fue efectivo o la distribución de ramas cambió inesperadamente.

### Resultados esperados E1 (hipótesis)

- Δcomposite_v5 entre **+0.5 y +2.5** (ganancia modesta dominada por "cero cambio operacional" para Iris post-bootstrap + preparación infra).
- Δ**B2 Persona Fidelity**: estable o ligera mejora (+0 a +2). Fix de name leak "Iris" es neutral para Iris (nombre correcto) pero elimina el techo asymptotic para otros creators.
- **KEEP probable**. Si INCONCLUSIVE, el análisis cualitativo debe evaluar ganancia universalidad (Stefano, Q3 onboarding) como factor extra-CCEE que justifica merge.

### Riesgo identificado

Si Arm B muestra regresión significativa en S1/L1, la causa más probable es:
- `_build_recurrent_hint` construye texto ligeramente diferente incluso con vocab mined idéntico al hardcoded previo (cambios de puntuación, orden de reglas).
- Mitigación: Paso 3 dry-run antes del real permite detectar diferencias; si regresión, ajustar wording del template en `_build_recurrent_hint` para match exacto con L84-91 original post-vocab-sustitution.

---

**STOP Fase 6.** Plan secuencial de 9 pasos listo para ejecución post-merge. E1 inmediato sobre bucket existente. E2 documentado como deuda Q2 2026 con pre-requisitos explícitos. ¿Procedo con Fase 7 (README índice + PR)?
