# Forensic — `dm_strategy` (2026-04-23)

**Branch:** `forensic/dm-strategy-20260423`
**Creator target:** `iris_bertran`
**Scope:** refactor surgical del router de política conversacional PRE-LLM (`backend/core/dm/strategy.py`) + callsite en `generation.py`, alineado con el principio "todo dato lingüístico se DESCUBRE del content mining del creator, NUNCA se preasigna".
**Estado:** PR listo para medición CCEE. NO mergeado. NO tocando Railway.

---

## Índice de documentos

| Doc | Contenido | Tamaño aprox |
|-----|-----------|--------------|
| [`01_description.md`](./01_description.md) | Qué hace `strategy.py`, 7 ramas P1-P7 + default, valor al pipeline, dimensiones CCEE v5 afectables | 6 KB |
| [`02_forensic.md`](./02_forensic.md) | Línea a línea + git blame de 7 commits clave, distribución real en dataset (P4=90%), upstream 8 params, downstream metadata + prompt injection | 17 KB |
| [`03_bugs.md`](./03_bugs.md) | 14 bugs con severidad CRÍTICA/ALTA/MEDIA/BAJA, reproducción y fix; principio §1.1 vocab_meta mined vs identidad calibrations; bootstrap 1-time | 15 KB |
| [`04_state_of_art.md`](./04_state_of_art.md) | 5 papers 2024-2026 (Conversation Routines, Proactive Dialogues, ToMAgent, ACT, Soft-Prompt Persona) + 3 repos (Rasa, LangGraph, DSPy); alineación SOA y deuda Q2-Q4 2026 | 11 KB |
| [`05_optimization.md`](./05_optimization.md) | Implementación Fase 5: vocab_meta lookup, flag, 4 métricas Prometheus, gate NO_SELL, signature cleanup, 22 tests passing, bootstrap idempotente | 11 KB |
| [`06_measurement_plan.md`](./06_measurement_plan.md) | Plan CCEE 50×3 E1 (inmediato) + E2 (Q2 2026), 9 pasos pre-CCEE secuenciales, gates KEEP/REVERT/INCONCLUSIVE, observabilidad canario durante Arm B | 10 KB |

---

## Resumen ejecutivo

### Problema

`strategy.py` (117 LOC) inyecta guidance al LLM en 90% de los mensajes vía rama P4 RECURRENTE. Tres hallazgos críticos:

1. **Name leak + vocab Iris hardcoded** (L86, L89-90, commit `f561819c4`): "personalidad de Iris", apelativos `nena/tia/flor/cuca/reina`, anti-bug `NUNCA la palabra 'flower'`. Imposible onboardear otros creators.
2. **Doble hardcoding** (`context.py:1222` + `generation.py:197,199`, commit `9752df768`): desactiva P1 FAMILIA y P2 AMIGO 27 días sin CCEE pre/post.
3. **Overlap VENTA vs resolver S6 NO_SELL**: 5 casos concretos donde strategy inyecta "añade CTA" mientras resolver dice "no vendas" → LLM recibe señales opuestas.

### Solución (PR `forensic/dm-strategy-20260423`)

- **Vocab mined**: apelativos / openers_to_avoid / anti_bugs_verbales / help_signals desde `personality_docs[doc_type='vocab_meta']` DB via `services.calibration_loader._load_creator_vocab`. Fallback universal (hint neutro) cuando vocab vacío. Cero defaults Iris.
- **Flag** `ENABLE_DM_STRATEGY_HINT` (default True).
- **Gate VENTA/NO_SELL** en `generation.py`: suprime hint P6 VENTA cuando `cognitive_metadata["sell_directive"]=="NO_SELL"`. No cambia signatura de `_determine_response_strategy`.
- **4 métricas Prometheus**: `dm_strategy_branch_total`, `hint_injected_total`, `vocab_source{mined|fallback}`, `gate_blocked_total`.
- **Signature cleanup**: elimina dead param `follower_interests`, añade `creator_id`+`creator_display_name`.
- **Bootstrap 1-time**: `scripts/bootstrap_vocab_meta_iris_strategy.py` (idempotente, `--dry-run`) siembra `personality_docs` de Iris con los valores previamente hardcoded. No auto-ejecutable.
- **22 tests** passing en `tests/test_dm_strategy_forensic.py`.

### Fuera de scope (diferido E2 Q2 2026)

- Portado de las 4 guidelines estilo al `sell_arbitration/arbitration_layer` (BUG-004, BUG-008). Requiere bucket FAMILIA/AMIGO etiquetado n=10-20 casos.
- Mining automático de vocab desde content del creator. Worker separado.
- Consolidación naming intents (`purchase`/`purchase_intent`), SOFT_MENTION overlap, CIERRE sin intent.

### Medición

- **E1 (inmediato)**: CCEE 50×3 Arm A vs Arm B sobre `baseline_post_p4_live_20260422.json`, Wilcoxon + Cliff's delta, gate KEEP si Δcomposite_v5 ≥ +1.5 sin regresión >2 en B2/S1/L1/H1.
- **E2 (diferido)**: mide portado al resolver post bucket ampliado.

### Riesgos conocidos

1. Ganancia Iris marginal (bootstrap preserva operativa) → KEEP por ganancia universalidad extra-CCEE.
2. `_build_recurrent_hint` puede emitir texto ligeramente distinto al original → mitigación via Paso 3 dry-run.
3. Casos C y E del overlap VENTA (SOFT_MENTION, CIERRE sin intent) documentados como known gaps Q3 2026.

---

## Artefactos

**Código modificado:**
- `backend/core/dm/strategy.py` (117→293 LOC, rewrite)
- `backend/core/dm/phases/generation.py` (+88 LOC: callsite + gate + métricas + log estructurado)
- `backend/core/feature_flags.py` (+1 flag)
- `backend/core/observability/metrics.py` (+4 metric specs)
- `DECISIONS.md` (entrada 2026-04-23, 5 decisiones A-E)

**Código nuevo:**
- `backend/scripts/bootstrap_vocab_meta_iris_strategy.py` (182 LOC, 1-time migration)
- `backend/tests/test_dm_strategy_forensic.py` (305 LOC, 22 unit tests)

**Documentación:**
- `docs/forensic/dm_strategy/{01..06,README}.md` (7 archivos, ~75 KB total)

---

## Verificación Fase 5

```bash
# All ast.parse OK
python3 -c "import ast; [ast.parse(open(p).read()) for p in (
    'backend/core/dm/strategy.py',
    'backend/core/dm/phases/generation.py',
    'backend/core/feature_flags.py',
    'backend/core/observability/metrics.py',
    'backend/scripts/bootstrap_vocab_meta_iris_strategy.py',
    'backend/tests/test_dm_strategy_forensic.py',
)]"

# 22 tests passing
cd backend && python3 -m pytest tests/test_dm_strategy_forensic.py
# ============================== 22 passed in 0.03s ==============================

# Flag accessible, metrics registered
python3 -c "from core.feature_flags import flags; from core.observability.metrics import emit_metric; \
  print('flag:', flags.dm_strategy_hint); \
  emit_metric('dm_strategy_branch_total', creator_id='test', branch='P4')"
# flag: True
```

---

## Checklist de activación post-merge

Ver detalle en `06_measurement_plan.md §2` (9 pasos secuenciales).

Resumen:
- [ ] Merge PR `forensic/dm-strategy-20260423` → `main`
- [ ] Railway auto-deploy verificado con smoke test (`curl /health` + logs limpios)
- [ ] `railway run python3 backend/scripts/bootstrap_vocab_meta_iris_strategy.py --dry-run` — revisar output
- [ ] `railway run python3 backend/scripts/bootstrap_vocab_meta_iris_strategy.py` — ejecutar real
- [ ] Prometheus `dm_strategy_vocab_source{source=mined} / total` > 80% para Iris
- [ ] `railway variables get ENABLE_DM_STRATEGY_HINT` → `true` (default)
- [ ] Ejecutar Arm B CCEE (`run_ccee.py --runs 3 --compare baseline_post_p4_live_20260422.json`)
- [ ] Aplicar gate §1.4 de `06_measurement_plan.md` (KEEP / REVERT / INCONCLUSIVE)
- [ ] Documentar resultado en `docs/measurements/forensic_dm_strategy_e1_result.md`

---

**Autor:** Manel Bertran Luque (con forensic asistido por Claude Opus 4.7)
**PR:** `forensic/dm-strategy-20260423` → `main` (NO mergeado)
**Related:** Scout previo `docs/audit/no_optimized_on_scout_20260423.md`
