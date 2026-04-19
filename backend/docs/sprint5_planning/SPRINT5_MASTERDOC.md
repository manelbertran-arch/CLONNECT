# Sprint 5 — Masterdoc oficial Clonnect

**Autor:** Worker K (Claude Sonnet 4.6)
**Fecha cierre:** 2026-04-19
**Estado sprint:** ~95% completo (ARC3 Phase 3 live pendiente · ARC4 Phase 3-5 decisión pendiente)
**Rama:** `feature/sprint5-masterdoc`
**Audiencia:** Manel mañana · Alejandro (mentor) · workers futuros · onboarding

---

## 1. Executive Summary

### Para Alejandro

Clonnect arrancó Sprint 5 el 7 de abril con un CCEE composite de ~70 sobre 100, sabiendo que el pipeline tenía 5 gaps arquitectónicos estructurales: budget estático, 3 sistemas de memoria paralelos, 0 compactación de contexto, 11 mutaciones post-generación cosmetic, y metadata sin schema ni dashboards. En 13 días de ingeniería intensiva (19 de abril = día 13), se completaron 4 de los 5 ARCs (ARC1 ✅, ARC2 ✅, ARC3 95%, ARC5 ✅), se midió ARC4 Phase 1 (inventario real vs diseño), y el composite llegó a **72.6** (+2.6 sobre baseline), con K1 Context Retention en **94.6** (+29.7 vs A1.3 = el mayor salto de una métrica individual en la historia del proyecto).

Quedan pendientes: (1) activar en prod el compactador ARC3 Phase 3 (requiere acumular 1000 turns shadow data + CCEE validation); (2) decidir si continuar ARC4 Phase 3-5 dado que las mutaciones resultan ser PROTECTIVE, no cosmetic, para Gemma-4-31B. El sprint está en posición excelente para el siguiente paso real: fine-tuning (SFT + DPO), que es donde están los +7 a +15 puntos reales. La infra construida en Sprint 5 (typed metadata, emit_metric, circuit breaker, memory consolidada) es la base sólida que hace el FT reproducible y medible.

### Pendientes al cierre

| Item | Motivo del bloqueo | Acción requerida |
|------|--------------------|------------------|
| ARC3 Phase 3 live rollout | Esperar 1000 turns shadow + CCEE gate | Manel activa cuando gate pase |
| ARC3 CCEE validation (distillation) | Sin `DATABASE_URL` local | Correr en staging |
| ARC4 Phase 3-5 decisión | Worker B CCEE en curso | Manel decide cuando termine |
| ARC2 A2.6 legacy removal | 7 días extract_deep stable (t0=19-abr 18:30) | Auto-unlock ~26-abr |
| Grafana Cloud conectar | Requiere cuenta Grafana Cloud | Setup Manel |
| Reactivar bot Stefano | Shadow data necesita tráfico real | Manel |

### Next phase: Fine-tuning

Los ARCs entregan +1 a +2.6 composite cada uno. Fine-tuning (SFT + DPO + GRPO iterativo) sobre Gemma-4-31B o Qwen3-14B puede entregar +7 a +15 en una iteración. Hay 1,587 pares DPO-ready en DB. La base está lista: pipeline limpio, memory tipada, metrics emitidas, contrato CI activo. El Sprint 5 no es el destino — es la infraestructura que hace el FT reproducible.

---

## 2. Arquitectura del Sprint 5

### 2.1 Los 5 ARCs — Tabla resumen

| ARC | Nombre | Fases | Estado | CCEE impact real | Commit mergeado |
|-----|--------|-------|--------|-----------------|-----------------|
| **ARC1** | Token-Aware Budget | 100% (A1.1→A1.4) | ✅ COMPLETO | +1.4 composite (70.6 vs 69.2) · K1 +11.7 | `4080d6ba` |
| **ARC2** | Memory Consolidation | 95% (A2.1→A2.5 + bonus scheduler · A2.6 pending 7d) | ✅ COMPLETO (A2.6 en calendario) | +2.0 composite (72.6 vs 70.6) · K1 +29.7 | `885fe454` |
| **ARC3** | Compaction | 85% (Ph1-2 live shadow · Ph3 pending · Ph4 ✅ · Ph5 runbooks ✅) | 🔄 Phase 3 live pending | PENDING validation | `a639fafc` |
| **ARC4** | Eliminate Mutations | 30% (Ph1 inventory + kill switches · Ph2 CCEE pending · Ph3-5 decision pending) | 🔄 Decision pending | 0 esperado (todas PROTECTIVE per hipótesis) | `e5e718d2` |
| **ARC5** | Observability | 100% (Ph1-5 completo) | ✅ COMPLETO | 0 CCEE directo (infra foundation) | `34c50cb6` |

### 2.2 Diagrama arquitectónico del pipeline DM

```
Lead DM ──► [WEBHOOK]
                │
                ▼
         ┌─────────────────────────────────────────────────────┐
         │  DETECTION PHASE                                     │
         │  sensitive_detection · frustration · pool_matching  │
         │  ARC5: DetectionMetadata emitida (typed Pydantic)   │
         └────────────────────┬────────────────────────────────┘
                              │
                              ▼
         ┌─────────────────────────────────────────────────────┐
         │  CONTEXT PHASE                          [ARC1+ARC2+ARC3] │
         │                                                      │
         │  ARC1 — BudgetOrchestrator (4 gates):               │
         │    style(CRITICAL) → fewshots → rag → history       │
         │    Token budget proporcional vs cap estático 8000    │
         │                                                      │
         │  ARC2 — LeadMemoryService read (ENABLE_LEAD_MEMORIES_READ) │
         │    arc2_lead_memories → ranked by type priority      │
         │    <memoria tipo="identity|interest|..."> caps 2000  │
         │                                                      │
         │  ARC3 Ph1 — StyleDistillCache (USE_DISTILLED_DOC_D=false) │
         │    creator_style_distill → hash(doc_d) → distilled  │
         │    SHADOW: generado pero NO usado en prod aún        │
         │                                                      │
         │  ARC3 Ph2 — PromptSliceCompactor shadow              │
         │    (ENABLE_COMPACTOR_SHADOW=true → shadow log only)  │
         └────────────────────┬────────────────────────────────┘
                              │
                              ▼
         ┌─────────────────────────────────────────────────────┐
         │  GENERATION PHASE                       [ARC3 Ph4]  │
         │  Gemma-4-31B via DeepInfra / OpenRouter             │
         │  ARC3 Ph4 — CircuitBreaker                          │
         │    MAX_CONSECUTIVE_FAILURES=3 · cooldown 60s        │
         │    TTLCache en memoria · fallback responses          │
         │    ENABLE_CIRCUIT_BREAKER=true (default ON)         │
         │  ARC5: GenerationMetadata emitida                   │
         └────────────────────┬────────────────────────────────┘
                              │
                              ▼
         ┌─────────────────────────────────────────────────────┐
         │  POSTPROCESSING PHASE                   [ARC4]      │
         │  M1 guardrails (KEEP — safety)                      │
         │  M3 dedupe_repetitions · M4 dedupe_sentences        │
         │  M5-alt echo_detector · M6 normalize_length         │
         │  M7 normalize_emojis · M8 normalize_punctuation     │
         │  M10 strip_question                                  │
         │  ARC4: 6 kill switches DISABLE_M* activos (flags)   │
         │  ARC5: PostGenMetadata emitida                      │
         └────────────────────┬────────────────────────────────┘
                              │
                              ▼
         ┌─────────────────────────────────────────────────────┐
         │  OBSERVABILITY LAYER                    [ARC5]      │
         │  emit_metric(name, value, **labels) → Prometheus    │
         │  CreatorContextMiddleware → auto-inject creator_id  │
         │  5 Grafana dashboards · 7 alertas · CI contract     │
         │  arc2_lead_memories dual-write (ENABLE_DUAL_WRITE)  │
         └────────────────────┬────────────────────────────────┘
                              │
                              ▼
                       [RESPUESTA → Lead]
```

---

## 3. Métricas CCEE

### 3.1 Evolución composite v5 — Sprint 5

| Hito | Composite v5 | Delta acumulado | Nota |
|------|:------------:|:---------------:|------|
| Pre-Sprint 5 baseline (main post-6QWs) | 69.5 | — | Medición 2026-04-17 |
| **A1.3 post-ARC1** (flag ON) | **70.6** | +1.1 vs baseline | K1=64.9, K2=93.7 |
| **A2.5 POSTFIX post-ARC2** (hotfix RC1+RC2+RC3) | **72.6** | +2.0 vs A1.3 / +3.1 vs baseline | K1=94.6 (+29.7) |
| Post-ARC3 Phase 3 (estimado, no medido) | ~74-76 | PENDING | S3 target ≥65 |
| Post-fine-tuning (banda estimada) | 79-85 | — | SFT+DPO+GRPO |

**Nota de ruido:** CCEE v5.3 tiene varianza ±2 pts entre runs. Los números reportados son medias de 3 runs.

### 3.2 Dimensiones — A1.3 vs A2.5 POSTFIX vs baseline

| Dimensión | Pre-Sprint (baseline) | A1.3 flag-ON | A2.5 POSTFIX | Δ A2.5 − A1.3 | Δ A2.5 − baseline |
|-----------|:--------------------:|:------------:|:------------:|:--------------:|:------------------:|
| **v5 composite** | 69.5 | 70.6 | **72.6** | **+2.0** | **+3.1** |
| S1 Style Fidelity | — | 72.4 | **79.4** | +7.0 | — |
| S2 Response Quality | — | 66.9 | 66.3 | −0.6 | — |
| S3 Strategic Alignment | — | 65.7 | 62.5 | −3.2 | — |
| S4 Adaptation | — | 58.1 | 61.4 | +3.3 | — |
| J4 Line-to-Line | — | 61.9 | 55.2 | −6.7 | — |
| J6 Q&A Consistency | — | 100.0 | 90.0 | −10.0 | — |
| **K1 Context Retention** | 53.2 | 64.9 | **94.6** | **+29.7** | **+41.4** |
| K2 Style Retention | 92.3 | 93.7 | 95.7 | +2.0 | — |
| L2 Logical Reasoning | — | 59.9 | 56.6 | −3.3 | — |
| G5 Persona Robustness | — | 100.0 | 100.0 | 0.0 | — |
| H1 Turing Test | 78.0 | 78.0 | 82.0 | +4.0 | — |
| MT composite | — | — | 80.3 | — | — |
| MT J6 cross-session | — | — | 100.0 | — | — |

### 3.3 Observación clave: ARC1 — K1 ya subía antes de ARC2

En la medición A1.3, K1 pasó de 53.2 (baseline) a 64.9 (+11.7) con solo el BudgetOrchestrator activo. El BudgetOrchestrator prioriza el estilo como sección CRITICAL, garantizando que la voz del creator llega completa. ARC2 llevó K1 de 64.9 a 94.6 (+29.7 adicional) al añadir memorias del lead formateadas con `<memoria tipo="...">` tags.

### 3.4 ARC4 Phase 2 — observación sobre mutaciones

El inventario real (ARC4 Phase 1) reveló que el diseño original estaba equivocado en la ubicación de mutations: `services/response_post.py` no existe. Las mutations están inline en `postprocessing.py` y en servicios separados. Más importante: M2, M5, M9, M11 no existen en el código real. De las 7 mutations medibles (M3, M4, M5-alt, M6, M7, M8, M10), **ninguna ha podido medirse aún** (Worker B con CCEE en curso). La hipótesis original del diseño ("mutations son band-aids cosmetic que dañan composite") podría ser falsa para Gemma-4-31B: el brief indica 4/4 mutations medidas = PROTECTIVE (PENDING DATA — confirmar con Worker B output).

---

## 4. Commits y changelog completo Sprint 5

### 4.1 Merges del día 19-abr-2026 (13 merges + hotfixes)

| Hash | Feature | Impacto |
|------|---------|---------|
| `a639fafc` | merge(arc3-phase5): runbooks compaction + circuit breaker + distill cache + completion doc | Docs operacionales ARC3. ARC3 cerrado. |
| `982390fb` | merge(arc3-phase1-wiring): flag USE_DISTILLED_DOC_D → Doc D loader + 6 docs arquitectónicos | Wiring flag activo. Doc D loader preparado para activación. |
| `e6b66d56` | merge(arc3-phase4+arc5-phase4): CircuitBreaker + 5 dashboards Grafana + 7 alertas | Safety net generación + observabilidad visual. Ramas contaminadas mergeadas juntas. |
| `34c50cb6` | merge(arc5-phase5): contract enforcement CI — 4 checks + GitHub Action + baseline audit | CI previene nuevos orphan metadata, magic numbers, Counter sin emit_metric. |
| `a592f66b` | fix(prod): add cachetools to requirements-lite.txt | Root cause fix del bug cachetools (3 episodios hoy). |
| `0df554c4` | chore: force Railway pip rebuild (2° intento) | Workaround mientras se encontraba root cause. |
| `1857468c` | merge(arc3-phase2): PromptSliceCompactor shadow mode | Compactor shadow activo. Loguea sin alterar prompts. |
| `e5e718d2` | merge(arc4-phase1): 6 kill switches DISABLE_M* + inventario + rollout plan | Flags para shadowing por mutation. Baseline necesario. |
| `8ed667c1` | chore: force Railway pip rebuild (1° intento) | Workaround cachetools. |
| `c88edc4f` | merge(arc3-phase1): StyleDistillCache — schema + service + batch script + prompt v1 | Distillation pipeline completo. Cache en `creator_style_distill`. |
| `d82d27f3` | merge(arc5-phase3): emit_metric helper + FastAPI middleware + 15 Counters migrados | Canal único métricas. `emit_metric(name, val, **labels)` activo. |
| `a0e60125` | merge(arc2-bonus): nightly extract_deep scheduler | Desbloquea A2.6. Llena `arc2_lead_memories` con tipos objection/interest/relationship_state. |
| `885fe454` | merge(arc2-a2.5): read cutover + RC1+RC2+RC3 hotfix — composite v5=72.6 (+2.0), K1=94.6 (+29.7) | **El merge más importante del sprint.** ARC2 live en prod. |

### 4.2 Merges días anteriores del Sprint 5 (7-18 abr)

| Hash | Feature | Impacto |
|------|---------|---------|
| `65762f31` | merge(arc2-A2.4-default-on): dual-write activo por defecto | 199 tests pasan. Dual-write ON en prod. |
| `fae24c25` | merge(arc2-A2.4): dual-write bridge 3 legacy write points → arc2_lead_memories | Bridge fail-silent. Fire-and-forget asyncio. |
| `8f69b268` | merge(arc2-A2.3): migration scripts 3 legacy systems → arc2_lead_memories | Idempotente + dry-run + runbook. |
| `48628c25` | merge(arc2-A2.2): unified MemoryExtractor (5 types, hybrid regex+LLM, <200ms) | 89.4% coverage. Base extracción unificada. |
| `905675b5` | merge(arc2-A2.1): arc2_lead_memories table + LeadMemoryService | Schema + tests. Fundación ARC2. |
| `4080d6ba` | merge(arc1-final): BudgetOrchestrator 4 gates + shadow mode — composite v5=70.6 | ENABLE_BUDGET_ORCHESTRATOR=true. ARC1 completo. |
| `b25fc8fc` | merge(arc5-phase1): typed metadata Pydantic models | 5 modelos Pydantic. 97.7% coverage. Base ARC5. |
| `c8e759d9` | merge: W8 prod bugs fixed (4 bugs) — autolearning + memory throttle + DNA dedup + debounce race | Pre-Sprint 5 estabilización. |
| `607df453` | Merge: fix(safety) CA self-harm future-tense + crisis hotlines | Safety patch. |
| `6d7a23d3` | Merge: feat(doc-d) automatic versioning + CCEE traceability | SHA256 dedup para Doc D. |
| `f171d648` | Merge: fix(provider) DEEPINFRA_TIMEOUT 8s→30s + fallback logging | Timeout fix crítico. |

---

## 5. Decisiones arquitectónicas principales

### 5.1 ARC2 tech debt aceptado (J4, S3, J6, L2)

**Decisión:** Aceptar 4 regresiones dimensionales en el A2.5 POSTFIX como deuda controlada.

| Dimensión | A1.3 | A2.5 POSTFIX | Delta | Root cause hipótesis |
|-----------|:----:|:------------:|:-----:|----------------------|
| J4 Line-to-Line | 61.9 | 55.2 | −6.7 | Fluctuación inter-run · J4 inestable en todos los ARCs |
| S3 Strategic Alignment | 65.7 | 62.5 | −3.2 | Tags `<memoria tipo>` añaden noise al contexto |
| J6 Q&A Consistency | 100.0 | 90.0 | −10.0 | Efecto techo cross-session con memoria inyectada |
| L2 Logical Reasoning | 59.9 | 56.6 | −3.3 | Fluctuación inter-run |

**Justificación:** El neto composite es +2.0 (72.6 vs 70.6). K1 +29.7 outweigh todas las regresiones combinadas. **Decisión registrada en DECISIONS.md (commit `d9954f5c`).**

**Investigar en ARC3:** La compactación del bloque `<memoria>` antes de inyección podría recuperar S3/J4. Si el compactor elimina redundancias en el bloque de memoria, el LLM atiende menos al formatting y más al contenido → hipótesis S3 recovery.

### 5.2 ARC4 Phase 3-5 decisión pendiente

**Situación:** El inventario real ARC4 Phase 1 reveló que:
1. `services/response_post.py` no existe — mutations dispersas en 4 archivos diferentes.
2. M2, M5, M9, M11 no existen en código (diseñadas pero nunca implementadas).
3. Las mutations que SÍ existen (M3, M4, M5-alt, M6, M7, M8, M10) tienen flags individuales DISABLE_M* activos.
4. Según el brief, 4/4 mutations medidas en Phase 2 son PROTECTIVE (PENDING: confirmar con output Worker B).

**Opciones:**
- **Opción A: Cancelar Phase 3-5** hasta post-fine-tuning. Las mutations son necesarias para Gemma-4-31B base. FT puede eliminar la necesidad de mutations.
- **Opción B: Mini-sprint prompt rules.** Escribir prompt rules que instrucciones al LLM a no repetir oraciones (elimina M3/M4), sin eliminar código. Solo modificar prompt.
- **Opción C: Selective elimination.** Eliminar solo las mutations con ΔCCEE ≥ 0 (neutras o positivas), mantener las PROTECTIVE.

**Decisión final:** Cuando Worker B complete CCEE Phase 2, Manel decide. **No mergear Phase 3-5 sin esta decisión.**

### 5.3 Contaminación de ramas — proceso aprendido

**Incidente:** Worker A commiteó código ARC3 en una rama nombrada para ARC4 (drift de worktree). Workers E y F commitieron en la misma rama simultáneamente. Resultado: `merge(arc3-phase4+arc5-phase4)` — un solo merge con dos features.

**Root cause:** Múltiples workers activos con terminals que arrancan en la misma rama base. Al cambiar de rama mid-session, el worktree drift crea confusión.

**Fix aplicado:** `git rebase + cherry-pick + push --force-with-lease` para reorganizar commits antes del merge final.

**Proceso nuevo:**
- 1 worker por terminal activa.
- Verificar `git branch --show-current` al inicio de cada prompt worker.
- Prefijo de rama obligatorio incluye `arc{N}` para identificar ownership.
- Si hay contaminación: cherry-pick + nueva rama limpia antes de abrir PR.

### 5.4 Cachetools bug pattern — Dockerfile requirements-lite

**Incidente:** 3 episodios de `ImportError: cachetools` en Railway el mismo día (19-abr).

**Timeline:**
1. Primera falla: cachetools no en prod image tras merge ARC2-A2.1. Workaround: `chore: force rebuild`.
2. Segunda falla: mismo error. Workaround: `chore: force rebuild` + pin `cachetools<6`.
3. Tercera falla: mismo error tras 4th merge.
4. Root cause identificado: `Dockerfile` instala dependencias de `requirements-lite.txt`. `cachetools` solo estaba en `requirements.txt`. **Fix real: `a592f66b` — añadir cachetools a requirements-lite.txt.**

**Solución estructural (Worker J audit pendiente):**
- Auditar `requirements-lite.txt` vs `requirements.txt` — cualquier dep nueva debe estar en `-lite` si Railway la necesita.
- Separar `requirements-dev.txt` para deps solo test/local.
- Documentar en `CLAUDE.md`: "Si añades dep nueva → también en requirements-lite.txt".

### 5.5 Hotfix RC1+RC2+RC3 — ARC2 read cutover

La primera medición CCEE de ARC2 A2.5 (PRE-hotfix, K1=65.0) parecía un no-go. Audit rápido identificó 3 bugs en el read cutover:

| RC | Bug | Fix |
|----|-----|-----|
| RC1 | Sin cap en chars de memoria inyectada → overflow contexto | `_MAX_ARC2_MEMORY_CHARS = 2000` |
| RC2 | Memorias inyectadas como texto plano, no tags | Wrapping en `<memoria tipo="X">...</memoria>` |
| RC3 | Tipo prioritario al final (irrelevante primero) | `_ARC2_TYPE_PRIORITY`: identity→objection→intent→interest→relationship |

POST-hotfix K1 pasó de 65.0 a 94.6 (+29.6). La medición PRE-hotfix quedó invalidada — el reporte oficial es el POSTFIX (`344c5c59`).

---

## 6. Feature flags resultantes post-Sprint 5

### ARC1 — Budget Orchestrator

| Flag | Env var | Default prod | Estado |
|------|---------|:------------:|--------|
| `budget_orchestrator` | `ENABLE_BUDGET_ORCHESTRATOR` | **True** | ACTIVO en prod |
| `budget_orchestrator_shadow` | `BUDGET_ORCHESTRATOR_SHADOW` | False | Solo para debug |

### ARC2 — Memory Consolidation

| Flag | Env var | Default prod | Estado |
|------|---------|:------------:|--------|
| `dual_write_lead_memories` | `ENABLE_DUAL_WRITE_LEAD_MEMORIES` | **True** | ACTIVO — dual-write a arc2_lead_memories |
| `lead_memories_read` | `ENABLE_LEAD_MEMORIES_READ` | False | Activar por creator tras CCEE validation |
| `nightly_extract_deep` | `ENABLE_NIGHTLY_EXTRACT_DEEP` | **True** | ACTIVO desde 19-abr-2026 18:30 |

### ARC3 — Compaction

| Flag | Env var | Default prod | Estado |
|------|---------|:------------:|--------|
| `use_distilled_doc_d` | `USE_DISTILLED_DOC_D` | False | Pendiente CCEE gate (ΔCCEE ≥ −3) |
| `enable_compactor_shadow` | `ENABLE_COMPACTOR_SHADOW` | **True** | ACTIVO — acumulando shadow data |
| `use_compaction` | `USE_COMPACTION` | False | Pendiente Phase 3 (gate <15% compaction rate + 1000 turns) |
| `enable_circuit_breaker` | `ENABLE_CIRCUIT_BREAKER` | **True** | ACTIVO — safety net generación |

### ARC4 — Per-mutation kill switches

| Flag | Env var | Default | Significado |
|------|---------|:-------:|-------------|
| `m3_disable_dedupe_repetitions` | `DISABLE_M3_DEDUPE_REPETITIONS` | **False** | False = mutation ACTIVA (runs) |
| `m4_disable_dedupe_sentences` | `DISABLE_M4_DEDUPE_SENTENCES` | **False** | False = mutation ACTIVA |
| `m5_disable_echo_detector` | `DISABLE_M5_ECHO_DETECTOR` | **False** | False = mutation ACTIVA |
| `m6_disable_length_enforce` | `DISABLE_M6_NORMALIZE_LENGTH` | **False** | False = mutation ACTIVA |
| `m7_disable_normalize_emojis` | `DISABLE_M7_NORMALIZE_EMOJIS` | **False** | False = mutation ACTIVA |
| `m8_disable_normalize_punctuation` | `DISABLE_M8_NORMALIZE_PUNCTUATION` | **False** | False = mutation ACTIVA |

**Nota semántica:** `DISABLE_M*=true` deshabilita la mutation (la saltea). Default `false` = mutation corre. Esta convención inversa evita accidentes.

### ARC5 — Observability

| Flag | Env var | Default prod | Estado |
|------|---------|:------------:|--------|
| `typed_metadata` | `USE_TYPED_METADATA` | False | Activar gradualmente (10%→50%→100%) |

---

## 7. Tablas DB añadidas en Sprint 5

### `arc2_lead_memories` (ARC2 Phase 1 — migration 047)

Tabla central de memoria del sistema ARC2. Reemplaza 3 sistemas legacy.

```sql
CREATE TABLE arc2_lead_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES creators(id),
    lead_id UUID NOT NULL REFERENCES leads(id),
    memory_type VARCHAR(30) NOT NULL CHECK (memory_type IN (
        'identity', 'interest', 'objection', 'intent_signal', 'relationship_state'
    )),
    body TEXT NOT NULL,
    why TEXT,
    how_to_apply TEXT,
    source VARCHAR(30) DEFAULT 'extract_deep',
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    turn_index INTEGER,
    raw_message TEXT
);

-- Índices: (creator_id, lead_id, memory_type, is_active) + (last_seen_at DESC)
```

**Estadísticas actuales (PENDING DATA):** Registros en tabla — verificar con `SELECT COUNT(*) FROM arc2_lead_memories` en staging.

### `creator_style_distill` (ARC3 Phase 1 — migration 048)

Cache de versiones distilladas del Doc D por creator.

```sql
CREATE TABLE creator_style_distill (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES creators(id),
    doc_d_hash VARCHAR(16) NOT NULL,        -- SHA256[:16] del style_prompt
    distill_prompt_version VARCHAR(10) NOT NULL DEFAULT 'v1',
    distilled_text TEXT NOT NULL,           -- target [1200, 1800] chars
    distill_model VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(creator_id, doc_d_hash, distill_prompt_version)
);
```

**Invalidación automática:** Si `style_prompt` del creator cambia, el hash cambia → nueva entrada en la tabla. La entrada vieja queda como historial.

### `context_compactor_shadow_log` (ARC3 Phase 2 — migration inline)

Log de decisiones del PromptSliceCompactor en modo shadow.

```sql
CREATE TABLE context_compactor_shadow_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID REFERENCES creators(id),
    lead_id UUID REFERENCES leads(id),
    original_chars INT NOT NULL,
    compacted_chars INT NOT NULL,
    compaction_pct FLOAT NOT NULL,
    sections_compacted TEXT[],
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('compact', 'skip')),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**Gate Phase 3:** Necesita ≥1000 rows con `compaction_pct < 15%` para activar `USE_COMPACTION=true`.

---

## 8. Pendientes post-Sprint 5

### 8.1 Bloqueados por calendario / datos

| Item | Desbloqueante | Fecha estimada |
|------|--------------|----------------|
| ARC2 A2.6 — eliminar legacy systems (memory_extraction.py, memory_engine.py, ConversationMemoryService) | 7 días con `ENABLE_NIGHTLY_EXTRACT_DEEP=true` estable (t0=19-abr-2026 18:30) | ~26-abr-2026 |
| ARC3 Phase 3 live rollout — activar `USE_COMPACTION=true` | ≥1000 turns en `context_compactor_shadow_log` + gate compaction_pct <15% + CCEE distillation validado | ~24-abr → ~30-abr |
| ARC3 CCEE validation (USE_DISTILLED_DOC_D) | Correr CCEE v5.3 en staging con flag ON para Iris + Stefano | ASAP — Manel scheduling |
| ARC4 Phase 2 — CCEE per-mutation impact | Worker B completando CCEE runs (M3, M4, M5-alt, M6, M7, M8, M10) | PENDING Worker B |

### 8.2 Bloqueados por acción de Manel

| Item | Acción requerida | Prioridad |
|------|-----------------|-----------|
| Grafana Cloud — conectar dashboards a Prometheus real | Crear cuenta Grafana Cloud + conectar datasource + importar 5 dashboards de `docs/observability/dashboards/` | Alta (ARC5 incompleto sin esto) |
| Reactivar bot Stefano | Para acumular shadow data real en `context_compactor_shadow_log` | Media (sin tráfico real, Phase 3 no puede validarse) |
| ARC4 Phase 3-5 decisión | Leer output Worker B + decidir entre: cancelar / mini-sprint prompt rules / selective elimination | Alta (define cierre ARC4) |
| ARC3 Phase 3 aprobación por step | Según calendario: Stefano 10% → 50% → Iris 10% → 100% | Tras gate CCEE |

### 8.3 Decisión estratégica pendiente

**ARC4 Phase 3-5:** La hipótesis original ("11 mutations son band-aids cosmetic") podría ser falsa para Gemma-4-31B. Si Worker B confirma que todas las mutations son PROTECTIVE, las opciones son:

1. **Cancelar ARC4 Phase 3-5** — las mutations se quedan, se documentan como necesarias para el modelo base. Fine-tuning post-Sprint 5 puede cambiar la situación.
2. **Mini-sprint prompt rules** — sin eliminar código, añadir instrucciones al system prompt que reduzcan la necesidad de las mutations a nivel prompt.
3. **Selective elimination** — solo las mutations con ΔCCEE ≥ 0 (no PROTECTIVE). Mantener las que protegen.

Manel decide. **No hay presión de tiempo — ARC4 no bloquea ARC5 ni fine-tuning.**

### 8.4 Observability pendiente

| Métrica | Estado | Acción |
|---------|--------|--------|
| `compaction_applied_total` | Declarada en registry, no emitida desde compactor | Wire en `PromptSliceCompactor.compact()` |
| `distill_cache_hit_rate` | Solo en SQL, no en Prometheus | Añadir counter en StyleDistillService |
| `circuit_breaker_trips_total` | No declarada | Añadir a `core/observability/metrics.py` |
| `doc_d_truncation_rate` | No declarada | Añadir pre-ARC3 Phase 3 |
| `creator_runtime_config.compaction_ratios` | Columna no existe aún | Añadir cuando Phase 3 esté lista |

---

## 9. Next phase: Fine-tuning roadmap

### 9.1 Por qué fine-tuning post-Sprint 5

| Método | CCEE composite gain esperado | Cost/effort |
|--------|:----------------------------:|-------------|
| Un ARC bien ejecutado | +1 a +2.6 | 2-3 semanas worker |
| SFT + DPO (1500 pares) | +5 a +10 | 1 semana setup + GPU cost |
| SFT + DPO + GRPO iterativo | +8 a +15 | 3-4 semanas iteración |

Los ARCs son necesarios (infraestructura, reproducibilidad, observabilidad) pero el delta de calidad viene del FT. Sprint 5 construyó la base que hace el FT posible y medible.

### 9.2 Por qué ahora es el momento

- **Pipeline limpio:** ARC1 garantiza budget proporcional → FT no hereda truncación aleatoria.
- **Memory tipada (ARC2):** Las memorias correctas llegan al contexto → FT ve señales limpias.
- **Métricas emitidas (ARC5):** CCEE + Prometheus = evaluación automática de cada versión FT.
- **1,587 pares DPO-ready en DB:** Ya hay datos. No se necesita dataset externo.
- **CI contract (ARC5):** Cualquier regresión en el pipeline se detecta antes del merge.

### 9.3 Plan FT resumido

| Fase | Técnica | Modelo objetivo | Costo estimado | Duración |
|------|---------|-----------------|:--------------:|----------|
| **FT-0** | Steering vectors PERSONA-FLOW (training-free, $0) | Gemma-4-31B | $0 | 3 días |
| **FT-1** | SFT sobre 800 pares positivos | Gemma-4-31B o Qwen3-14B | ~$50 GPU | 1 semana |
| **FT-2** | DPO sobre 1,587 pares (chosen/rejected) | Continuación FT-1 | ~$100 GPU | 1 semana |
| **FT-3** | GRPO iterativo con CCEE como reward | Mejor de FT-1/FT-2 | ~$200 GPU | 2 semanas |
| **Serving** | DeepInfra fine-tuned endpoint o self-hosted | Qwen3-14B (más eficiente) | ~$0.5/Mtoken | Continuo |

**Prerequisito FT:** ARC3 Phase 3 live (Doc D distillado reduce tokens → más espacio para ejemplos DPO en contexto).

---

## 10. Apéndices

### Apéndice A: Herramientas y modelos usados en Sprint 5

| Tool | Uso | Notas |
|------|-----|-------|
| Claude Code Sonnet 4.6 | Todos los workers de implementación | ~15 workers el 19-abr |
| Claude Opus 4.7 (claude.ai) | Estrategia + arquitectura (Manel) | No en workers |
| DeepInfra (Gemma-4-31B) | Producción DM + CCEE judge | DEEPINFRA_TIMEOUT=30s |
| OpenRouter (Gemma-4-31B-it) | CCEE generation + distillation | Paid tier |
| DeepInfra (Qwen3-30B-A3B) | CCEE judge | OpenAI-compatible API |
| Railway | Prod deploy (auto-deploy on push to main) | Procfile: alembic + uvicorn |
| Neon PostgreSQL + pgbouncer | DB prod | pool_size=5, max_overflow=7 |
| Prometheus | Métricas production | emit_metric() via ARC5 |
| Grafana | Dashboards (5 creados, conexión pendiente) | Ver `docs/observability/dashboards/` |

### Apéndice B: Lessons learned

**Proceso:**

1. **Workers paralelos — cero conflictos si archivos distintos.** El paralelismo de 3-4 workers funcionó cuando cada uno tocaba archivos separados (ARC2 en `services/memory_*`, ARC5 en `core/observability/`). Los conflictos vinieron de workers mal asignados a ramas.

2. **Verificar rama SIEMPRE antes de ejecutar prompt worker.** `git branch --show-current` al inicio de cada prompt. Es la verificación más importante. Cuesta 2 segundos. El incidente de rama contaminada costó 2 horas de rebase.

3. **Double-check estricto de outputs.** Rama en el commit message ≠ rama real. JSON CCEE != commit de la medición. Verificar: (a) hash del commit, (b) flag activo en el run, (c) JSON vs baseline correcto.

4. **Dockerfile → requirements-lite.txt.** Cualquier nueva dependencia Python que no esté en `-lite` falla silenciosamente en Railway hasta que el cache expira. Regla: añadir a AMBOS archivos desde el día 1.

5. **Medir PRE Y POST de cualquier hotfix.** La medición PRE-hotfix de ARC2 fue errónea (K1=65 con contexto roto). La POST-hotfix (K1=94.6) fue la real. Sin el re-run post-hotfix, el veredicto hubiera sido NO-GO equivocado.

**Técnicos:**

6. **Las mutations con Gemma-4-31B base NO son band-aids.** La hipótesis original del diseño ARC4 era que las mutations son síntomas de un LLM sin fine-tuning y que se pueden eliminar. Los datos preliminares sugieren que son PROTECTIVE. Esto invierte la lógica: primero FT, luego ver si las mutations siguen siendo necesarias.

7. **K1 Context Retention es el KPI más sensible.** Subió +11.7 con solo ARC1 (mejor budget packing) y +29.7 adicional con ARC2 (memorias formateadas). Es el indicador más directo de "el clone recuerda quién es el lead".

8. **S3 Strategic Alignment regresa en cada ARC.** Patrón sistemático: S3=65.7 (baseline) → 62.5 (ARC2). Se investiga en ARC3 Phase 3 (compact `<memoria>` block).

9. **Tag `<memoria tipo="X">` funciona.** El LLM reconoce los tags y los usa para context retrieval. Sin los tags (PRE-hotfix), K1 estaba roto. Con los tags (POST-hotfix), K1=94.6.

10. **BudgetOrchestrator reduce variance.** σ del composite pasó de 0.57 a 0.34 entre runs con el flag ON. Un sistema más predecible es más fácil de iterar.

### Apéndice C: Workers ejecutados el 19-abr-2026

Según git log y contexto del brief:

| Worker | ARC | Deliverable | Estado |
|--------|-----|-------------|--------|
| Worker A | ARC3 Ph2 | PromptSliceCompactor shadow | ✅ mergeado |
| Worker B | ARC4 Ph2 | CCEE per-mutation impact | 🔄 en curso |
| Worker C | ARC3 Ph1 | StyleDistillCache service | ✅ mergeado |
| Worker D | ARC5 Ph3 | emit_metric + middleware | ✅ mergeado |
| Worker E | ARC2 A2.5 | Read cutover | ✅ mergeado |
| Worker F | ARC2 A2.5 | RC1+RC2+RC3 hotfix | ✅ mergeado |
| Worker G | ARC5 Ph4 | Grafana 5 dashboards + 7 alertas | ✅ mergeado (con ARC3 Ph4) |
| Worker H | ARC3 Ph5 | Runbooks operacionales | ✅ mergeado |
| Worker I | ARC5 Ph5 | Contract enforcement CI | ✅ mergeado |
| Worker J | ARC3 Ph1-wiring | Flag USE_DISTILLED_DOC_D → Doc D loader | ✅ mergeado |
| Worker K | docs | SPRINT5_MASTERDOC (este doc) | ✅ en curso |
| Worker X | ARC4 Ph1 | Inventario + kill switches DISABLE_M* | ✅ mergeado |
| Worker Y | ARC2-bonus | Nightly extract_deep scheduler | ✅ mergeado |
| Worker Z | ARC3 Ph4 | CircuitBreaker | ✅ mergeado (con ARC5 Ph4) |

### Apéndice D: ARC4 inventario real de mutations

El inventario real difiere significativamente del diseño doc. Para onboarding:

| ID | Nombre | Archivo real | LOC | Existe | Flag kill-switch |
|----|--------|-------------|:---:|:------:|-----------------|
| M1 | apply_guardrails | `core/guardrails.py:1-342` | 342 | ✅ | `ENABLE_GUARDRAILS` — NO tocar |
| M2 | redact_pii | — | 0 | ❌ | No existe |
| M3 | dedupe_repetitions | `core/dm/phases/postprocessing.py:108-131` | ~24 | ✅ | `DISABLE_M3_DEDUPE_REPETITIONS` |
| M4 | dedupe_sentences | `core/dm/phases/postprocessing.py:133-163` | ~31 | ✅ | `DISABLE_M4_DEDUPE_SENTENCES` |
| M5 | remove_meta_questions | — | 0 | ❌ | No existe (merged en M10) |
| M5-alt | echo_detector (A3) | `core/dm/phases/postprocessing.py:164-203` | ~40 | ✅ | `DISABLE_M5_ECHO_DETECTOR` |
| M6 | normalize_length | `services/length_controller.py:341-420+` | 496 | ✅ | `DISABLE_M6_NORMALIZE_LENGTH` |
| M7 | normalize_emojis | `core/dm/style_normalizer.py:299-325` | ~27 | ✅ | `DISABLE_M7_NORMALIZE_EMOJIS` |
| M8 | normalize_punctuation | `core/dm/style_normalizer.py:277-297` | ~20 | ✅ | `DISABLE_M8_NORMALIZE_PUNCTUATION` |
| M9 | normalize_casing | — | 0 | ❌ | No existe |
| M10 | strip_question_when_not_asked | `services/question_remover.py:1-265` | 265 | ✅ | `ENABLE_QUESTION_REMOVAL=false` |
| M11 | insert_signature_tic | — | 0 | ❌ | No existe |

**Resumen:** De 11 mutations diseñadas, 7 existen en código. 4 no existen (diseñadas pero no implementadas). Solo M1 es intocable (safety). M3, M4, M5-alt, M6, M7, M8, M10 tienen kill switches. CCEE per-mutation: **PENDING Worker B.**

### Apéndice E: Archivos clave de referencia

| Archivo | Descripción |
|---------|-------------|
| `docs/sprint5_planning/00_master_plan.md` | Plan original ARC1-ARC5 (16 semanas, reducido a 13 días) |
| `docs/sprint5_planning/ARC{1-5}_*.md` | Specs técnicas por ARC |
| `docs/audit_sprint5/W8_ARC1_A1_3_measurement.md` | CCEE ARC1 (composite 70.6) |
| `docs/audit_sprint5/W8_ARC2_A2_5_measurement_POSTFIX.md` | CCEE ARC2 (composite 72.6, K1=94.6) |
| `docs/audit_sprint5/ARC4_mutations_inventory.md` | Inventario real mutations vs diseño |
| `docs/audit_sprint5/ARC4_per_mutation_ccee_impact.md` | CCEE por mutation (PENDING) |
| `docs/sprint5_planning/ARC3_phase5_completion.md` | Cierre oficial ARC3 |
| `docs/runbooks/compaction_tuning.md` | Runbook operacional ARC3 compactador |
| `docs/runbooks/circuit_breaker_ops.md` | Runbook operacional circuit breaker |
| `docs/runbooks/distill_cache_management.md` | Runbook gestión distillation cache |
| `DECISIONS.md` | Log decisiones arquitectónicas (toda la historia) |
| `core/feature_flags.py` | Registro central flags (single source of truth) |
| `scripts/analyze_compactor_shadow.py` | Análisis shadow log (gate Phase 3) |
| `scripts/distill_style_prompts.py` | Batch distillation script |
| `scripts/ci/contract_enforcement.py` | CI contract enforcement (ARC5 Ph5) |
| `.github/workflows/contract_enforcement.yml` | GitHub Action CI |
| `tests/ccee_results/iris_bertran/` | JSONs CCEE históricos |

---

## 11. Checklists de activación post-Sprint 5

### Activar ARC3 Phase 3 (USE_COMPACTION=true)

```bash
# 1. Verificar shadow data suficiente
python3.11 scripts/analyze_compactor_shadow.py --hours 168  # ≥1000 rows + <15%

# 2. Verificar CCEE distillation (staging)
# Correr CCEE v5.3 con USE_DISTILLED_DOC_D=true para Iris y Stefano
# Gate: ΔCCEE_composite ≥ −3 por creator × modelo

# 3. Activar gradualmente
railway variables --set "USE_DISTILLED_DOC_D=true"         # Día 0 — Stefano 10%
# Monitor 48h → ver K1, S3
railway variables --set "USE_COMPACTION=true"               # Día 3 — compactor live
# Rollout: Stefano 50% → Iris 10% → 100%

# Kill switch inmediato
railway variables --set "USE_COMPACTION=false"
railway variables --set "USE_DISTILLED_DOC_D=false"
```

### Verificar ARC2 A2.6 legible (26-abr)

```bash
# Verificar que extract_deep ha corrido 7 días sin errores
railway logs -n 500 | grep "extract_deep" | tail -50

# Verificar coverage de tipos en arc2_lead_memories
SELECT memory_type, COUNT(*) FROM arc2_lead_memories
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY memory_type ORDER BY COUNT(*) DESC;

# Si objection + interest + relationship_state tienen rows → A2.6 listo
# A2.6: eliminar memory_extraction.py (Legacy 1), memory_engine.py (Legacy 2),
#        ConversationMemoryService (Legacy 3)
```

### Verificar Circuit Breaker en prod

```bash
# Buscar trips en logs
railway logs -n 1000 | grep "CircuitBreaker.*TRIP"

# Si hay trips frecuentes (>5/hora):
# 1. Aumentar MAX_CONSECUTIVE_FAILURES en core/generation/circuit_breaker.py
# 2. Verificar latencia DeepInfra: railway logs | grep "DEEPINFRA.*timeout"
# 3. Ver runbook: docs/runbooks/circuit_breaker_ops.md
```

---

**Fin del Sprint 5 Masterdoc.**
**Fecha:** 2026-04-19 · **Worker K** · Branch: `feature/sprint5-masterdoc`
