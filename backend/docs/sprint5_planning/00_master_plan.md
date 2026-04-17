# Sprint 5 — Master Plan (ARC1-ARC5)

**Autor:** Arquitecto Clonnect (AI)
**Fecha:** 2026-04-16
**Duración total:** 16 semanas (paralelizadas) / 20 semanas (serializadas)
**Basado en:** W7 §9 Track 2 (ARC1-ARC5)

---

## 0 · TL;DR

> **Objetivo:** Cerrar los 5 gaps arquitectónicos más costosos identificados en W7 vs Claude Code. Transformar Clonnect de un sistema con ~11 mutations post-gen, dual memory, 0 compaction y metadata orphan-heavy a un sistema disciplinado: token-aware budget, memory tipada, compaction inteligente, 0 mutations cosmetic, observability contract.
>
> **Sprint:** 5 ARCs interdependientes pero paralelizables. 16 semanas efectivas.
>
> **Target CCEE:** 70 baseline → 80+ post-ARC5 (**+10 puntos composite**).
>
> **Budget:** ~3.2 eng-months (worker time) + 0.8 ML-months (CCEE + validación Manel).

---

## 1 · Contexto: Por qué Sprint 5 y por qué ahora

### 1.1 Herencia

Sprint 4 entregó QW1-QW7 (quick wins):
- QW1: 30 metadata orphans eliminados ✅
- QW2: `USE_COMPRESSED_DOC_D` validado → stays off ✅
- QW3: security alerting live ✅
- QW5: persona compiler fix ✅
- QW6: emoji_rule wiring ✅

W7 (audit final) identificó que los **quick wins cubren síntomas, no estructura**. Los 5 gaps estructurales son:

| Gap | Decisión W7 §9 | Sprint ARC |
|---|---|---|
| Budget sin tipo ni caps por componente | A | ARC1 |
| Dual memory (3 sistemas conviviendo) | B | ARC2 |
| 0 estrategias de compaction | C | ARC3 |
| 11 mutations post-gen cosmetic | D | ARC4 |
| Metadata sin schema, 35 orphans, 0 dashboards | E | ARC5 |

### 1.2 Motivación por ARC (1-line)

1. **ARC1 (Token-Aware Budget):** Eliminar el tope `MAX_CONTEXT_CHARS=8000` estático por un budget proporcional por componente. Base para todo lo demás.
2. **ARC2 (Memory Consolidation):** Unificar 3 memorias en 1 tabla tipada con 5 tipos. Desbloquea K1 recall +10-15 puntos.
3. **ARC3 (Compaction):** StyleDistillCache + PromptSliceCompactor. Elimina el trade-off "Doc D completo vs truncado".
4. **ARC4 (Eliminate Mutations):** 9 de 11 mutations eliminadas. -700 LOC, +debugeability, voz más consistente.
5. **ARC5 (Observability):** Typed metadata + emit_metric + dashboards. Zero nuevos orphans, pipeline visible.

---

## 2 · Dependencias entre ARCs

### 2.1 Grafo de dependencias

```
                        ┌─────────┐
                        │  ARC5   │
                        │ Obs     │  (Phase 1-3 primero como
                        │ (3w)    │   backbone)
                        └────┬────┘
                             │ emit_metric available
        ┌──────────┬─────────┼─────────┬──────────┐
        ▼          ▼         ▼         ▼          ▼
  ┌──────────┐┌──────┐┌──────────┐┌──────┐┌──────────┐
  │  ARC1    ││ ARC2 ││  ARC3    ││ ARC4 ││  ARC5    │
  │ Budget   ││ Mem  ││ Compact  ││ Mut  ││ Obs      │
  │  (4w)    ││ (6w) ││  (3w)    ││ (4w) ││ Ph 4-5   │
  └────┬─────┘└──────┘└────┬─────┘└──────┘└──────────┘
       │                   │
       │   preferible       │
       └───────>┌───────────┘
               ARC3 consume ARC1's budget primitives
```

### 2.2 Matriz de dependencias

| Dep ↓ / ARC → | ARC1 | ARC2 | ARC3 | ARC4 | ARC5 |
|---|---|---|---|---|---|
| **ARC1** (Budget) | — | Indep | Pref | Indep | Indep |
| **ARC2** (Memory) | Indep | — | Indep | Indep | Indep |
| **ARC3** (Compaction) | Pref | Indep | — | Indep | Indep |
| **ARC4** (Mutations) | Indep | Indep | Indep | — | Indep |
| **ARC5** (Observability) | Req(emit) | Req(emit) | Req(emit) | Req(emit) | — |

**Leyenda:**
- **Indep:** Puede arrancar sin bloqueo.
- **Pref:** Preferible pero no bloqueante.
- **Req(emit):** Requiere que ARC5 Phase 3 (emit_metric) esté live.

### 2.3 Dependencias críticas

**Bloqueante:**
- Ninguna ARC bloquea a otra dura (todas pueden degradarse a modo standalone).

**Preferible:**
- ARC5 Phase 1-3 primero → ARC1-ARC4 emiten métricas desde día 1.
- ARC1 antes de ARC3 → integración limpia de compactor con budget orchestrator.

**Externa:**
- Infra estable: Railway, Neon, Redis, Prometheus ya existen.
- DeepInfra (Gemma-4) budget disponible (~$200 CCEE).
- Manel availability: ~4h/semana reviews + approvals.

---

## 3 · Gantt Cronograma (16 semanas)

### 3.1 Plan paralelizado

```
Semana        1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
              │  │  │  │  │  │  │  │  │  │  │  │  │  │  │  │
ARC5 Ph1-3    ████████                          (backbone, paralelo con ARC1)
ARC1          ████████████                      (4w)
ARC2          ██████████████████                (6w, paralelo con ARC1+ARC3)
ARC3                            █████████       (3w, post ARC1)
ARC4                            ████████████    (4w, paralelo con ARC3)
ARC5 Ph4-5                              █████████  (dashboards tras métricas emitidas)
Integration                                   ██████ (2w final)
```

### 3.2 Semana-por-semana

| Semana | Actividad principal | Deliverables |
|---|---|---|
| **W1** | ARC5 Phase 1 (models) + ARC1 Phase 1 (design) | Pydantic models, ARC1 design doc |
| **W2** | ARC5 Phase 2 (per-phase typing) + ARC1 Phase 2 (orchestrator) | Typed writes, BudgetOrchestrator class |
| **W3** | ARC5 Phase 3 (emit_metric) + ARC1 Phase 3 (integration) + ARC2 Phase 1 (schema) | emit_metric live, ARC1 shadow mode, lead_memories table |
| **W4** | ARC1 Phase 4 (rollout 10-100%) + ARC2 Phase 2 (dual-write) | ARC1 in prod, ARC2 dual-write |
| **W5** | ARC3 Phase 1 (distill validation) + ARC2 Phase 3 (backfill) | Distilled versions validated, legacy backfilled |
| **W6** | ARC3 Phase 2 (shadow) + ARC4 Phase 1 (rules) + ARC2 Phase 4 (cutover) | Compactor shadow, prompt rules designed |
| **W7** | ARC3 Phase 3 (live rollout) + ARC4 Phase 2 (shadow) + ARC2 Phase 5 (legacy removal) | Compactor in prod, mutations shadowed, legacy removed |
| **W8** | ARC3 Phase 4 (breaker) + ARC4 Phase 3 (eliminate low-risk) | CircuitBreaker live, 6 mutations eliminated |
| **W9** | ARC3 Phase 5 (tuning) + ARC4 Phase 3 (continued) | ARC3 done, 2 more mutations eliminated |
| **W10** | ARC4 Phase 4 (medium-risk: M6, M10, M11) | 3 medium-risk mutations eliminated |
| **W11** | ARC4 Phase 5 (SafetyFilter refactor) | M1+M2 consolidated, ARC4 done |
| **W12** | ARC5 Phase 4 (dashboards 1-2) | Generation + Scoring dashboards live |
| **W13** | ARC5 Phase 4 (dashboards 3-5) | Memory, Compaction, CCEE dashboards live |
| **W14** | ARC5 Phase 5 (contract + orphan cleanup) | Contract test, 35 orphans resolved |
| **W15** | Integration testing + CCEE full sweep | Final CCEE per ARC combination |
| **W16** | Retrospective + runbook consolidation + handoff | Sprint closeout, docs published |

### 3.3 Buffer

Cada ARC tiene su propio buffer interno (semana 4 en ARC1, semana 4 en ARC2, etc). Este master plan **NO añade buffer adicional**. Si un ARC se retrasa, otros pueden absorber sin afectar total 16 semanas (gracias a paralelismo).

**Red lines:**
- Si **ARC1 se retrasa > 2 semanas** → ARC3 podría no tener budget orchestrator → Phase 2 de ARC3 opera con hard-code → degradación aceptable.
- Si **ARC2 se retrasa > 3 semanas** → ARC5 dashboard de memory arrancará con data mock hasta migration.
- Si **ARC5 Phase 1-3 se retrasa** → ARC1/ARC2/ARC3/ARC4 emiten via prometheus_client directo (legacy path) → consolidar en Phase 4.

### 3.4 Check-in gates

Gates **obligatorios** con Manel:

| Semana | Gate | Criterio de paso |
|---|---|---|
| **W2 viernes** | ARC1 design approval | Design doc v1 aprobado |
| **W4 viernes** | ARC1 rollout approval | CCEE no regresa > -3, rollout 100% OK |
| **W5 viernes** | ARC3 distill approval | Per-creator ΔCCEE ≥ -3 |
| **W7 viernes** | ARC2 cutover approval | Dual-write drift < 1% sostenido 7 días |
| **W9 viernes** | ARC3 compactor live approval | Doc D truncation ≤ 2%, CCEE estable |
| **W11 viernes** | ARC4 completion approval | 9 mutations eliminadas, CCEE ≥ -2 |
| **W14 viernes** | ARC5 contract gate | 0 orphans, CI check activo |
| **W16 final** | Sprint closeout | Todos ARCs cerrados, runbooks, retrospective |

**Si falla gate:**
- Documentar razón en `docs/sprint5_planning/gate_failures.md`.
- Decidir: iterate (stay on ARC) vs descope (continue with others).
- Manel aprueba cada descope.

---

## 4 · Trayectoria CCEE esperada

### 4.1 Baseline actual

| Creator × Model | CCEE composite | K1 recall | S3 recovery |
|---|---|---|---|
| Iris × Gemma-4-26B | 70.2 | 68 | 54 |
| Iris × Gemma-4-31B | 70.2 | 70 | 55 |
| Stefano × Gemma-4-26B | 68.5 | 66 | 52 |
| Stefano × Gemma-4-31B | 68.8 | 67 | 53 |

### 4.2 Proyección por ARC

| Hito | CCEE composite | Delta | Métrica principal |
|---|---|---|---|
| **Baseline** (2026-04-16) | 70.2 | — | K1 68 (recall), S3 54 (recovery) |
| **Post-ARC1** (W4) | 72-75 | +2-5 | Budget utilization 85% vs 105%. Menos truncation en style → mejor voz |
| **Post-ARC2** (W7) | 75-78 | +3 | K1 recall 78-82 (+10-14). Memory consistency boost |
| **Post-ARC3** (W9) | 77-80 | +2 | S3 recovery 65-70 (+11-15). Doc D no truncado |
| **Post-ARC4** (W11) | 77-80 | 0 a -2 | No mejora; validar que no regresa. -700 LOC |
| **Post-ARC5** (W14) | 77-80 | 0 | No cambio directo; foundation para iterar más rápido |
| **Post-integration** (W16) | 80+ | +3 | Sinergia: budget + memory + compact working together |

**Nota CCEE es ruidoso:** variance típica ±2 puntos. Los targets incluyen el ruido.

### 4.3 Trayectoria por métrica clave

| Métrica | Baseline | Post ARC1 | Post ARC2 | Post ARC3 | Post ARC5 |
|---|---|---|---|---|---|
| K1 (recall) | 68-70 | 70-72 | **78-82** | 78-82 | 80-82 |
| S3 (recovery) | 54-55 | 56-58 | 60-62 | **65-70** | 65-70 |
| Composite | 70 | 73 | 76 | 78 | **80** |
| Response length compliance | 72% | 72% | 72% | 72% | 88% (ARC4) |

### 4.4 Criterios de no-go

Si en cualquier punto:
- **ARC1 rollout:** CCEE composite regresa > -5 → rollback + iterate.
- **ARC2 cutover:** K1 recall regresa > -3 → rollback + investigar.
- **ARC3 live:** S3 recovery regresa > -5 → rollback distillation.
- **ARC4 per-mutation:** ΔCCEE > -2 en esa mutation → rollback esa mutation.
- **Overall post-W16:** composite < 75 → sprint falla, postmortem.

---

## 5 · Recursos

### 5.1 Compute / worker time

**Workers definidos en cada ARC:**

| ARC | Workers | Total worker-semanas |
|---|---|---|
| ARC1 | A1.1-A1.6 (6 workers) | 4 |
| ARC2 | A2.1-A2.6 (6 workers) | 6 |
| ARC3 | A3.1-A3.6 (6 workers) | 3 |
| ARC4 | A4.1-A4.4 (4 workers) | 4 |
| ARC5 | A5.1-A5.5 (5 workers) | 3 |
| **TOTAL** | 27 worker prompts | **20 worker-semanas serial** |

Con paralelismo (2-3 workers simultáneos), efectivo ~10-14 worker-semanas calendar-time.

**Modelos por worker type:**
- **Opus 4.6** (premium): A1.1, A2.1, A3.1, A4.2, A5.1 — diseño core, schema, prompt design.
- **Sonnet 4.6** (standard): todos los demás (integration, rollout, testing).
- **Haiku 4.5** (cheap): ninguno — el trabajo es non-trivial, no se justifica.

**Cost estimate (modelos):**
- Opus tokens: ~5M input + 1M output × 5 workers = ~$500.
- Sonnet tokens: ~15M input + 3M output × 22 workers = ~$750.
- **Total ~$1,250 en worker tokens.**

### 5.2 CCEE / DeepInfra

Per ARC run CCEE v5.3: 20 scenarios × 2 creators × 2 models = 80 generations.

| Ciclo CCEE | Frecuencia | Cost |
|---|---|---|
| Baseline pre-ARC | 1x | $5 |
| Per-phase validation | ~15 rounds (3 per ARC) | $75 |
| Per-mutation validation (ARC4) | 9 rounds | $45 |
| Integration testing | 5 rounds final | $25 |
| **TOTAL CCEE cost** | | **~$150** |

### 5.3 Manel time

| Actividad | Estimación | Por semana |
|---|---|---|
| Gate reviews (semana 2, 4, 5, 7, 9, 11, 14, 16) | 8 × 2h | ~1h/sem promedio |
| Per-creator tone_config decisions (ARC4 Phase 1) | 4h en W6 | — |
| Per-creator distillation approval (ARC3 Phase 1) | 2h en W5 | — |
| Ad-hoc clarifications worker prompts | 30min/sem × 16 | 0.5h/sem |
| Retrospective W16 | 4h | — |
| **TOTAL Manel** | ~40h | ~2.5h/sem |

### 5.4 Infraestructura

| Recurso | Status | Cost adicional |
|---|---|---|
| Railway compute | ✅ existe | $0 |
| Neon PostgreSQL | ✅ existe | $0 |
| Redis (circuit breaker) | ✅ existe | $0 |
| Prometheus | ✅ existe | $0 |
| Grafana | ✅ existe | $0 |
| DeepInfra (CCEE) | ✅ budget approved | ~$150 |
| Claude API (workers) | ✅ budget approved | ~$1,250 |
| **TOTAL adicional** | | **~$1,400** |

Muy bajo — el ROI de +10 CCEE es órdenes de magnitud mayor.

---

## 6 · Riesgos macro del sprint

### R1 — CCEE v5.3 variance oculta regresión real — 🔴 HIGH

**Descripción:** CCEE ±2 puntos de ruido. Regresiones reales de -3 pueden aparecer como -1 en un run y -5 en otro.

**Mitigación:**
- Por ARC: **3 runs independientes** antes de aprobar cada rollout step.
- Reportar variance junto al mean.
- Human review Manel (10 turnos) como segundo check.

### R2 — Sprint se estira más allá de 16 semanas — 🟡 MEDIUM

**Descripción:** ARC2 (memory) es el más ambicioso. Si dual-write drift no converge, cutover se retrasa.

**Mitigación:**
- W7 W14 buffer (2 sem) en ARC2 interno.
- Descope path: ARC5 Phase 4-5 se puede mover a Sprint 6 sin impacto.
- Priorizar ARC1 + ARC2 + ARC3 sobre ARC4 + ARC5 si hay presión.

### R3 — Manel bandwidth — 🟡 MEDIUM

**Descripción:** Gates requieren review activo. Si Manel está en incident mode, gates se acumulan.

**Mitigación:**
- Gates son batch-able (1x/semana viernes).
- Pre-gate prep docs: reportes 1-page para decisión rápida.
- Si Manel indisponible: descope criterio "wait 2 days, proceed with assumption" con rollback plan.

### R4 — Deploy incidents durante el sprint — 🟡 MEDIUM

**Descripción:** 16 semanas es largo. Probable 1-2 prod incidents no relacionados (scoring bug, Instagram API change).

**Mitigación:**
- Buffer interno de cada ARC absorbe incidents menores.
- Si incident mayor: pause sprint 1-2 semanas, resume.
- Comunicar impacto a Manel.

### R5 — Dependencia no detectada entre ARCs — 🟢 LOW

**Descripción:** Documento asume ARCs independientes. Puede aparecer dependencia en implementation.

**Mitigación:**
- Weekly sync entre ARC owners (incluso si AI workers, entre Sonnet agents vía shared context).
- Documentar dependencias descubiertas en `docs/sprint5_planning/discovered_deps.md`.

### R6 — Base model upgrade (Gemma-4 → Gemma-5) mid-sprint — 🟢 LOW

**Descripción:** Si DeepInfra publica Gemma-5 antes de W16, re-baseline.

**Mitigación:**
- Lock a Gemma-4-26B y Gemma-4-31B durante el sprint.
- Upgrade es Sprint 6.

### R7 — Regulación / compliance cambio — 🟢 LOW

**Descripción:** GDPR u otro cambio puede afectar ARC2 (memory) o ARC4 (PII handling).

**Mitigación:**
- ARC2 schema incluye soft-delete + TTL desde día 1.
- SafetyFilter (ARC4 Phase 5) es compliance-ready.

---

## 7 · Success Criteria del Sprint 5

### 7.1 Must-have (block closeout)

- [ ] ARC1 BudgetOrchestrator live al 100%, CCEE sin regresión.
- [ ] ARC2 single-source-of-truth en `lead_memories`, legacy systems removed.
- [ ] ARC3 StyleDistillCache + PromptSliceCompactor + CircuitBreaker en prod.
- [ ] ARC4 9 mutations eliminadas, SafetyFilter live.
- [ ] ARC5 typed metadata + emit_metric + 5 dashboards + contract test.
- [ ] CCEE composite: Iris ≥ 77, Stefano ≥ 75 (ambos creators, ambos modelos).
- [ ] 0 production incidents atribuibles al sprint (cada ARC con rollback plan intacto).
- [ ] Retrospective documentada.

### 7.2 Nice-to-have

- [ ] CCEE composite Iris ≥ 80 (stretch goal).
- [ ] Latency P95 reducida vs baseline (por -700 LOC ARC4).
- [ ] Runbooks completos per ARC.
- [ ] Patrones reutilizables documentados (sticky hash, feature flag infra).

### 7.3 Non-goals

- No frontend changes (frontend repo separado, no afectado).
- No OAuth/webhook changes (lo prohíbe CLAUDE.md).
- No cambios a scheduler/scoring batch timing.
- No cambios a BLOCKED_MODELS list.

---

## 8 · Comunicación & tracking

### 8.1 Artifacts

**Daily:** Workers loggean progreso en `docs/sprint5_planning/daily_log.md` (append-only).

**Weekly:** Resumen en `docs/sprint5_planning/week_{N}_summary.md`.

**Per-gate:** Report en `docs/sprint5_planning/gate_{N}_{arc}_report.md` con:
- Status (pass/fail).
- CCEE results.
- Manel decision (approved / iterate / descope).

**Per-worker:** Cada worker prompt ejecutado logs en sus propios deliverables (ver ARCs).

### 8.2 Channels

- **Slack #sprint5-clonnect:** Updates diarios workers, alertas, CCEE results.
- **Email Manel:** Gate reviews (lunes + viernes).
- **GitHub PRs:** Tag `sprint-5-arcN` per PR, link a ARC doc.
- **Linear/Jira:** No — se usan ARC docs directamente.

### 8.3 Retrospective (W16)

Template de retro en `docs/sprint5_planning/retrospective_template.md` con secciones:
- What went well per ARC.
- What didn't.
- Lessons learned (tech + process).
- Metrics delivered vs projected.
- Next sprint candidates.

---

## 9 · Post-sprint: ¿Qué sigue?

### 9.1 Sprint 6 candidates (post-W16)

**Tier 1 (follow-up directo):**
- Expand ARC2 memory types según aprendizaje (quizás añadir tipo `plan`).
- Automate StyleDistillCache re-generation on Doc D change.
- Migrate legacy metadata (ARC5 opcional).

**Tier 2 (nuevos gaps):**
- W7 Track 3: Internacionalización (ES/CA/EN per-message routing).
- W7 Track 4: Creator onboarding flow automation.
- W7 Track 5: Lead segmentation beyond scoring (cohort analysis).

**Tier 3 (platform):**
- Migrate a Gemma-5 si disponible.
- Async message batching para scoring.
- GraphQL API para frontend mobile.

### 9.2 Deprecation timeline

- **W16 + 3 meses:** Eliminar legacy paths residuales (feature flags tras 3 meses estables).
- **W16 + 6 meses:** Eliminar `services/response_post_deprecated.py`.
- **W16 + 12 meses:** Re-evaluar ARC4 rules (si violation_rate > 5%, iterar).

---

## 10 · Checklist final de arranque

Antes de iniciar W1:

- [ ] Este master plan aprobado por Manel.
- [ ] ARC1-ARC5 docs revisados por Manel.
- [ ] Budget Claude API + DeepInfra confirmado ($1,400 total).
- [ ] Canal Slack #sprint5-clonnect creado.
- [ ] Baseline CCEE ejecutado y archivado (`tests/ccee_results/sprint5_baseline/`).
- [ ] Branch naming convention: `sprint5/arcN-<feature>`.
- [ ] Scripts de cron y scheduler no tocados sin authorization (per CLAUDE.md).
- [ ] Team (workers) coordinados con ownership clara.

**Firma Manel (approval):** __________________ Fecha: __________

---

## Appendix A — Glosario rápido

- **ARC:** Architecture sprint — Sprint 5 tracks estructurales (vs QW quick wins).
- **CCEE v5.3:** Clonnect Clone Evaluation — harness oficial con 20 scenarios, K1-K10 + S1-S5.
- **Doc D:** Style prompt del creador (voz, tono, ejemplos).
- **emit_metric:** Canal único de publicación de métricas a Prometheus (ARC5).
- **Typed metadata:** Pydantic models para `messages.metadata` (ARC5).
- **Budget Orchestrator:** Asigna token budget por componente del prompt (ARC1).
- **StyleDistillCache:** LLM-distilled versions del Doc D, precomputadas offline (ARC3).
- **SafetyFilter:** Único componente post-gen superviviente tras ARC4 (consolida guardrails + PII).
- **Sticky hash:** Hash determinístico de lead_id para A/B sampling consistente.

## Appendix B — Lista completa de docs Sprint 5

```
docs/sprint5_planning/
├── 00_master_plan.md                       (este doc)
├── ARC1_token_aware_budget.md              (~820 líneas)
├── ARC2_memory_consolidation.md            (~700 líneas)
├── ARC3_compaction.md                      (~900 líneas)
├── ARC4_eliminate_mutations.md             (~800 líneas)
├── ARC5_observability.md                   (~800 líneas)
│
├── week_N_summary.md                       (x16, durante sprint)
├── daily_log.md                            (append-only)
├── gate_N_ARC_report.md                    (x8, per gate)
├── discovered_deps.md                      (si aparecen)
├── gate_failures.md                        (si aparecen)
│
├── ARC3_phase1_distill_validation.md       (output worker A3.2)
├── ARC3_phase2_shadow_analysis.md          (output worker A3.3)
├── ARC3_phase3_rollout_log.md              (output worker A3.4)
├── ARC4_phase1_prompt_rules.md             (output worker A4.2)
├── ARC4_phase2_shadow_analysis.md          (output worker A4.3)
├── ARC4_per_mutation_results.md            (output worker A4.1)
├── ARC4_final_ccee_report.md               (output worker A4.1)
├── ARC5_phase2_rollout.md                  (output worker A5.2)
│
├── ARC1_retrospective.md                   (end-of-arc)
├── ARC2_retrospective.md
├── ARC3_retrospective.md
├── ARC4_retrospective.md
├── ARC5_retrospective.md
└── retrospective_template.md               (plantilla sprint retro)
```

## Appendix C — Referencias externas

- `docs/audit_phase2/W7_FULL_CROSS_SYSTEM_60.md` — Audit base (§9 Sprint plan).
- `docs/audit_phase2/W1_inventory_37_systems.md` — Inventario sistemas.
- `docs/audit_phase2/W2_metadata_flow.md` — Flujo metadata.
- `docs/audit_phase2/W3_token_analytics_real.md` — Token measurements.
- `docs/audit_phase2/W4_cc_memory_deep_dive.md` — CC memory patterns.
- `docs/audit_phase2/W5_cc_gating_deep_dive.md` — CC getAttachments.
- `docs/audit_phase2/W6_cc_compaction_deep_dive.md` — CC compaction strategies.
- `docs/CRUCE_REPO_VS_CLONNECT.md` — Clonnect vs CC architecture cruce.
- `DECISIONS.md` — Log de decisiones históricas (sprint 4 + sprint 5).
- `CLAUDE.md` — Reglas del repo (4-phase workflow, rate limits, BLOCKED_MODELS).
- MEMORY — QW2 decision record (USE_COMPRESSED_DOC_D off).

---

**Fin del Master Plan. Go/no-go decision next.**
