# Bot Question Analyzer — Plan de Medición CCEE A/B

**Fecha:** 2026-04-23
**Branch:** `forensic/bot-question-analyzer-20260423`
**Sistema bajo test:** Bot Question Analyzer (ver 01–05)
**Archivo modificado:** `backend/core/bot_question_analyzer.py` + `tests/unit/test_dm_agent_bot_question.py` + `backend/data/vocab/affirmation_vocab.json`
**Flag:** `ENABLE_QUESTION_CONTEXT` (env var en Railway)

---

## 1. Objetivo

Medir el impacto del Bot Question Analyzer sobre la calidad del clone midiendo composite CCEE v5 con el flag **OFF vs ON**, determinando si la hipótesis (resolver affirmation collapse mejora L3 turn-taking, S2 coherence, H2 flow) se sostiene empíricamente. El sistema estuvo OFF en Railway desde `dbf0cd11` (2026-04-03) por lockdown forense; este plan decide si debe volver a ON.

## 2. Hipótesis

**H1 (principal):** el analyzer mejora composite CCEE v5 en ≥ +1.0 pts sobre baseline v52-fixes (67.7).
**H0:** no hay efecto, o efecto ≤ +0.5 pts (ruido).
**H_neg:** regresión ≤ −1.0 pts (descartar — revert).

## 3. Baseline de referencia

| Métrica | Valor | Fuente |
|---------|-------|--------|
| Composite v5 | **67.7** | `docs/measurements/baseline_post_p4_live_v52_20260422.md` |
| σ_intra (3 runs) | 0.43 | ibid. |
| Fecha | 2026-04-22 | ibid. |
| Commit base | `5f641cf5` | ibid. |
| Test set | `tests/cpe_data/iris_bertran/test_set_v2_stratified.json` — 50 conversaciones, 42 CCEE-válidas | ibid. |
| Flags activos | `USE_COMPRESSED_DOC_D=false, ENABLE_SELL_ARBITER_LIVE=true, ENABLE_RERANKING=true, USE_COMPACTION=true` | ibid. |
| `ENABLE_QUESTION_CONTEXT` | **false** | env_prod_mirror_20260422.sh:46 |

## 4. Diseño experimental

### 4.1 Tipo de experimento
**A/B within-subject.** Mismo test set, mismos flags base, única variable manipulada: `ENABLE_QUESTION_CONTEXT`.

### 4.2 Arms

| Arm | `ENABLE_QUESTION_CONTEXT` | Descripción |
|-----|---------------------------|-------------|
| A (control) | `false` | Replica exacta del baseline 67.7 |
| B (treatment) | `true` | Analyzer activo (código optimizado del PR + vocab JSON) |

### 4.3 Réplicas
**3 runs × 50 casos = 150 mediciones por arm** (300 totales).
Justificación: σ_intra ≈ 0.43 → para detectar ΔN ≥ 1.0 con 95% confianza, 3 runs basta (Δ ≫ 2σ/√3).

### 4.4 Filtros de casos
Exclusiones heredadas del baseline:
- 8 casos con `[audio] / [sticker] / [image]` en ground_truth.
- Base efectiva CCEE: **42 conversaciones × 3 runs × 2 arms = 252 evaluaciones**.

### 4.5 Dimensiones target (monitorizadas)
| Dim | Nivel | Métrica principal |
|-----|-------|-------------------|
| **L3 turn-taking** | Primario | CCEE v5 L3 sub-score |
| **S2 response quality / coherence** | Primario | CCEE v5 S2 sub-score |
| **H2 dialogue flow** | Primario | CCEE v5 H Turing sub |
| Composite v5 | Primario | weighted aggregate |
| S1 style fidelity | Secundario (guard) | ensure NO regresión > −1.0 |
| S3 strategic alignment | Secundario | puede subir por purchase-priority |
| S4 adaptation | Secundario (guard) | |

## 5. Gates de decisión

| Resultado composite v5 (arm B − arm A) | Decisión | Acción |
|----------------------------------------|----------|--------|
| **Δ ≥ +1.0** | **KEEP** | Activar `ENABLE_QUESTION_CONTEXT=true` en Railway tras merge |
| −1.0 < Δ < +1.0 | **NEUTRAL** | No activar. Revisar sub-dimensiones. Si L3/S2/H2 suben pero composite plano → documentar y decidir manualmente |
| **Δ ≤ −1.0** | **REVERT** | Mantener OFF. Escalar como regresión. No mergear cambios |

### Gates adicionales (tripwires)
| Trigger | Acción |
|---------|--------|
| S1 style fidelity Δ ≤ −1.0 | REVERT aunque composite suba (no comprometer identity) |
| Cualquier dimensión individual Δ ≤ −2.0 | REVERT |
| σ_intra run B > 1.0 (ruido alto) | Repetir con 5 runs |
| Error rate > 5% en run B | Investigar antes de concluir |

## 6. Protocolo operacional

### 6.1 Pre-condiciones (antes de medir)

- [ ] PR `forensic/bot-question-analyzer-20260423` creado contra main. **NO mergeado.**
- [ ] Tests 15/15 passing en CI local (`pytest tests/unit/test_dm_agent_bot_question.py`).
- [ ] Verificar que el worktree está sincronizado con `main` actual (posible rebase si pasan días).
- [ ] Confirmar que baseline 67.7 sigue representativo (re-correr arm A con 1 run de sanity; si Δ > 0.5 vs 67.7, recalibrar baseline).
- [ ] Railway estado actual capturado (snapshot env vars).

### 6.1.bis Blocker NUEVO — vocab_meta poblado per-creator

**Razón:** este PR refactoriza el analyzer a zero-hardcoding. Sin `personality_docs.vocab_meta.affirmations` poblado, el analyzer degrada a fallback universal (solo emojis) y el arm B no puede detectar "si / vale / ok" en texto. La medición sería un falso negativo.

**Checklist obligatorio antes de arm B:**

- [ ] Iris Bertran: verificar `SELECT content::json->'affirmations' FROM personality_docs WHERE creator_id IN (SELECT id::text FROM creators WHERE name='iris_bertran') AND doc_type='vocab_meta' LIMIT 1` devuelve lista no-vacía.
- [ ] Stefano: verificar lo mismo para `stefano` (o el slug correspondiente).
- [ ] Si cualquiera retorna NULL / [] → ejecutar el worker de mining **antes** de proceder:
  - Opción A: extender `scripts/bootstrap_vocab_metadata.py` para mining `affirmations`.
  - Opción B: nuevo script `scripts/mine_affirmations.py` (worker out-of-scope de este PR).
  - Opción C: manual seed temporal con tokens observados empíricamente en DMs recientes (solo para unblock medición; re-mined después).
- [ ] Validación post-mining: `get_metrics()["vocab_source.mined"]` debería dominar en los test runs (≥80%), `vocab_source.empty` ≈ 0.

**Si el mining worker no está listo para arm B:** la medición se aborta o se realiza con seed manual documentado. No activar `ENABLE_QUESTION_CONTEXT=true` en Railway en ningún caso hasta que Iris tenga al menos ~20 tokens afirmativos mined.

### 6.2 Ejecución arm A (control, flag OFF)

```bash
# checkout del baseline (commit 5f641cf5) en un entorno de evaluación aislado
export ENABLE_QUESTION_CONTEXT=false
# ... otros flags idénticos al baseline ...
python3 tests/run_ccee.py \
    --creator iris_bertran \
    --test-set test_set_v2_stratified.json \
    --runs 3 \
    --tag arm_a_flag_off \
    --composite v5 \
    --v52-fixes
```

Output esperado: `tests/ccee_results/iris_bertran/bqa_arm_a_YYYYMMDD.json` con 3 runs.

### 6.3 Ejecución arm B (treatment, flag ON)

```bash
# checkout del PR branch
git checkout forensic/bot-question-analyzer-20260423
export ENABLE_QUESTION_CONTEXT=true    # ← ÚNICA diferencia respecto a arm A
# ... mismos flags ...
python3 tests/run_ccee.py \
    --creator iris_bertran \
    --test-set test_set_v2_stratified.json \
    --runs 3 \
    --tag arm_b_flag_on \
    --composite v5 \
    --v52-fixes
```

Output: `tests/ccee_results/iris_bertran/bqa_arm_b_YYYYMMDD.json`.

### 6.4 Análisis

```bash
python3 scripts/analyze_ab.py \
    --arm-a tests/ccee_results/iris_bertran/bqa_arm_a_YYYYMMDD.json \
    --arm-b tests/ccee_results/iris_bertran/bqa_arm_b_YYYYMMDD.json \
    --dimensions L3,S2,H2,S1,composite_v5 \
    --output docs/measurements/bqa_ab_result_YYYYMMDD.md
```

Output esperado (una tabla como):
```
| Dim          | Arm A (OFF) | Arm B (ON) | Δ    | σ_A  | σ_B  | Gate |
|--------------|-------------|------------|------|------|------|------|
| composite_v5 | 67.72       | 69.14      | +1.42 | 0.41 | 0.38 | KEEP |
| L3           | 63.1        | 66.4       | +3.3 | 0.6  | 0.7  | ✓   |
| S2           | 67.2        | 68.0       | +0.8 | 0.3  | 0.4  | ✓   |
| H2 (Turing)  | 71.0        | 72.1       | +1.1 | 0.5  | 0.6  | ✓   |
| S1           | 62.4        | 62.1       | −0.3 | 0.4  | 0.5  | OK  |
```

### 6.5 Activación (post-KEEP)

```bash
# SOLO si gate KEEP confirmado
railway variables set ENABLE_QUESTION_CONTEXT=true --service backend
railway deployment list | head -3
# Monitor logs 10min post-deploy
railway logs -n 200 | grep "\[QUESTION_CONTEXT\]"   # debe aparecer "Injected: ..."
railway logs -n 200 | grep "\[BQA\]"                # debug del analyzer
```

**Validación post-activación:**
- [ ] Al menos 10 injections `[QUESTION_CONTEXT] Injected: ...` en primeros 30 min de tráfico orgánico.
- [ ] 0 excepciones relacionadas al analyzer en logs.
- [ ] Monitoring composite diario en `copilot_evaluations` estable o al alza durante 7 días.

## 7. Cronograma

| Paso | Duración estimada | Dependencias |
|------|------------------|--------------|
| PR review + tests CI | 30 min | Phase 7 PR creation |
| Sanity run arm A (1 run, 50 casos) | ~15 min | PR green |
| Full arm A (3 runs) | ~45 min | Sanity verde |
| Full arm B (3 runs) | ~45 min | Arm A completo |
| Análisis + doc | 20 min | Ambos arms listos |
| Decisión gate | Inmediata | Análisis |
| Activación Railway (si KEEP) | 5 min + 30 min monitor | Merge PR |
| **Total** | **~2h 30min** activas | — |

## 8. Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Baseline drift (67.7 ya no representativo) | Media | Correr 1 run sanity arm A; si Δ > 0.5 vs baseline histórico, recalibrar |
| Analyzer rompe pipeline en casos no cubiertos por tests | Baja | 12/12 tests verdes + callsites no modificados; log de excepciones captura falla silenciosa |
| Efecto < +1.0 pero L3/S2 mejoran aisladamente | Media | Gate NEUTRAL permite análisis granular antes de decidir |
| S1 regresa (nota inyectada altera tono) | Baja | Tripwire específico: S1 Δ ≤ −1.0 → REVERT |
| Interaction con otros sistemas OFF | Baja | Arm A/B difieren **sólo** en el flag; otros flags inmutables |
| Vocab JSON no llega a Railway | Baja | Embedded fallback cubre; monitorear `[BQA] vocab JSON load failed` en logs |

## 9. Out-of-scope (futuro)

- Medición per-subdimension L3a (start-of-turn) vs L3b (backchannel).
- A/B del umbral `0.7` (testear `0.6` y `0.8`).
- Per-creator vocab overrides (requiere más de 1 creador con volumen suficiente).
- `PRICE_DISCLOSED` QuestionType nuevo (señal empírica primero).
- Fallback LLM en `UNKNOWN` (sólo si CCEE revela coverage pobre).

## 10. Artefactos generados

Tras la medición completa:
- `tests/ccee_results/iris_bertran/bqa_arm_a_YYYYMMDD.json`
- `tests/ccee_results/iris_bertran/bqa_arm_b_YYYYMMDD.json`
- `docs/measurements/bqa_ab_result_YYYYMMDD.md` — veredicto + evidencia
- (Si KEEP) commit `chore: enable ENABLE_QUESTION_CONTEXT=true in Railway post-CCEE` en main separado.

## 11. Resumen ejecutivo

- **Experimento:** A/B within-subject, 3 runs × 50 casos, única variable `ENABLE_QUESTION_CONTEXT`.
- **Gate KEEP:** composite v5 Δ ≥ +1.0 y sin tripwires.
- **Gate REVERT:** composite Δ ≤ −1.0 o S1 Δ ≤ −1.0 o cualquier dim Δ ≤ −2.0.
- **Blocker 1 (flag):** activar `ENABLE_QUESTION_CONTEXT=true` en el entorno de medición **antes** de correr arm B. En Railway sólo se activa **después** de gate KEEP y merge de PR.
- **Blocker 2 (vocab_meta NUEVO):** `personality_docs.vocab_meta.affirmations` debe estar poblado para **Iris** y **Stefano** antes de arm B. Sin mining, el analyzer cae a fallback universal (solo emojis) y la medición subestima el impacto real.
- **No modifica Railway ahora.** Todo se hace en entorno de evaluación local/CI.

---

**STOP Phase 6.** Continuar con Phase 7 (PR).
