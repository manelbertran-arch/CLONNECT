# Investigación regresión composite -6.2 (P1 vs A2.5 POST-hotfix)

**Branch:** `feature/investigate-regression-sprint5`
**Date:** 2026-04-20
**Method:** Static code analysis + diff inspection + CCEE JSON comparison. Zero code changes.

---

## Datos

| Métrica | A2.5 POST | P1 | Δ |
|---------|-----------|-----|---|
| Composite v5 | 72.6 | 66.4 | **-6.2** |
| K Retention | 95.0 | 72.5 | **-22.5** |
| S2 Response Quality | 66.3 | 47.0 | **-19.3** |
| S1 Style | 79.4 | 72.3 | -7.1 |
| G5 Persona Robustness | 100.0 | 80.0 | **-20.0** |
| J_old | 54.5 | 29.5 | -25.0 |
| MT composite | 80.3 | 73.1 | -7.2 |

Sub-dimensions:
| Sub-dim | A2.5 | P1 | Δ |
|---------|------|-----|---|
| **K1 Context Retention** | 94.6 | 57.3 | **-37.3** |
| K2 Style Retention | 95.7 | 95.4 | -0.2 |
| J3 Prompt-to-line | 88.0 | 86.5 | -1.5 |
| J4 Line-to-line | 55.2 | 56.7 | +1.5 |
| L1 | 83.0 | 79.5 | -3.5 |
| L2 | 56.6 | 61.3 | +4.7 |
| L3 | 55.0 | 60.0 | +5.0 |

Protocol identical: 50×3+MT iris_bertran, OpenRouter Gemma-4-31B, DeepInfra judge Qwen3-30B-A3B, same doc_d version (8b8b75c6), same CCEE v5 flags.

---

## 1. Diff structural

**30 commits** between 885fe454..main. **83 files** changed, 51K insertions.

**9 hot path files** touched (core/dm/ + services/ + api/):

| File | Lines +/- | What changed |
|------|-----------|-------------|
| `core/dm/phases/context.py` | +155/-8 | ARC3 Phase 2 compactor shadow hook |
| `core/dm/phases/generation.py` | +62/-5 | ARC3 Phase 4 circuit breaker wrapping |
| `services/style_distill_service.py` | +378 | NEW: StyleDistillCache (ARC3 Phase 1) |
| `services/creator_style_loader.py` | +55 | ARC3 Phase 1 distill cache lookup |
| `core/dm/agent.py` | +23 | ARC3 Phase 1 distill wiring |
| `core/dm/phases/postprocessing.py` | +12/-6 | ARC4 kill switches (M3/M4/M5) |
| `core/dm/style_normalizer.py` | +8/-2 | ARC4 kill switches (M7/M8) |
| `services/length_controller.py` | +5 | ARC4 kill switch (M6) |
| `api/startup/handlers.py` | +18 | ARC2 nightly scheduler |

---

## 2. Hallazgo crítico: 2 flags DEFAULT ON

**ENABLE_CIRCUIT_BREAKER defaults to True** (`core/feature_flags.py:121`):
```python
enable_circuit_breaker: bool = field(
    default_factory=lambda: _flag("ENABLE_CIRCUIT_BREAKER", True)
)
```

**ENABLE_COMPACTOR_SHADOW defaults to True** (`core/feature_flags.py:129`):
```python
enable_compactor_shadow: bool = field(
    default_factory=lambda: _flag("ENABLE_COMPACTOR_SHADOW", True)
)
```

Neither is explicitly overridden in `config/env_ccee_gemma4_31b_full.sh`.

However, `CCEE_NO_FALLBACK=1` IS set in the CCEE env script. This disables the circuit breaker active path:

```python
# generation.py:480-484
_cb_active = (
    flags.enable_circuit_breaker           # True
    and not os.environ.get("CCEE_NO_FALLBACK")  # not "1" → False
    and os.environ.get("DISABLE_FALLBACK") != "true"
)
# _cb_active = False during CCEE
```

**Net effect during CCEE:**
- Circuit breaker: **DISABLED** (CCEE_NO_FALLBACK=1)
- Compactor shadow: **ACTIVE** (no override, defaults True)

---

## 3. Hot path analysis

### 3A. core/dm/phases/context.py (compactor shadow — ACTIVE during CCEE)

The diff restructures `_assemble_context` from early-return to single-return, adding an unconditional `asyncio.create_task`:

```python
# AFTER: runs on EVERY request regardless of flags
asyncio.create_task(
    _run_compactor_shadow(inp, actual_combined_chars=len(result[0]))
)
return result
```

`_run_compactor_shadow` when `enable_compactor_shadow=True`:
1. Imports `compactor.py` module (cached after first call)
2. Builds `SectionSpec` list from prompt sections (READ-ONLY on `inp`)
3. Runs `PromptSliceCompactor.pack()` — CPU work, ~1ms
4. `asyncio.to_thread(_log_shadow_compactor_sync, ...)` — **DB INSERT** to `context_compactor_shadow_log`

**Impact per CCEE run:** 200 background DB INSERTs (150 single-turn + 50 MT turns). These are fire-and-forget and execute AFTER the prompt is assembled and returned.

**Does it change the prompt?** NO — the task runs after `result` is computed.
**Does it change the response?** NO — LLM call is independent.
**Can it cause pool contention?** POSSIBLE — each INSERT opens a `SessionLocal()` connection. With pool_size=5+7=12 and rapid CCEE requests, background tasks could hold connections while the next request's context phase needs one.

### 3B. core/dm/phases/generation.py (circuit breaker — DISABLED during CCEE)

Circuit breaker wrapping is disabled via `CCEE_NO_FALLBACK=1`. The only residual effect is:
- `_cb_active = False` check (1 branch evaluation, negligible)
- The `try/except` around `generate_dm_response` is added, but `_breaker` is None so the except block just does `raise`

**Impact:** ZERO — confirmed by absence of fallback responses in P1 data.

### 3C. core/dm/agent.py (distill wiring — DISABLED)

```python
if style_prompt and _flags.use_distilled_doc_d:  # False by default
    ...
```

**Impact:** ZERO — entire block skipped when flag is False.

### 3D. postprocessing.py + style_normalizer.py + length_controller.py (ARC4 kill switches)

All 6 mutations (M3-M8) have `if flags.mN_disable_...: pass; elif original_condition:` structure. With kill switches defaulting to False, the `elif` path executes, which is functionally identical to the original `if` path.

**Impact:** ZERO — no behavioral change with default flags.

### 3E. api/startup/handlers.py (nightly extract_deep scheduler)

Registers a scheduler for nightly jobs. Does NOT execute during CCEE (scheduler runs on intervals, not per-request).

**Impact:** ZERO.

---

## 4. Análisis caso-por-caso

### Single-turn S2: ALL 50 cases worse

```
Aggregate: avg=-19.3, min=-42, max=-2, n=50
```

Top 6 worst cases (qualitative comparison):

| idx | user_msg | A2.5 bot (S2) | P1 bot (S2) |
|-----|----------|---------------|-------------|
| 44 | "Y yo me jodo" | "No diguis això cuca, ja veurem" (75.8) | "Vale, ja ho miro quan arribi" (33.6) |
| 45 | "Doncs 1,30 zumba i barre jajajajajja" | "ja m'estava espantant" (73.1) | "No passes, no passa res bb" (37.3) |
| 26 | "Vale ok" | "Va, ok. Ja em diré alguna cosa." (77.8) | "Ok, mami, espero el link!" (42.4) |
| 17 | "Sisisi porfiiinnn soleteee" | "Ostiaaa mare meva. Ja aviso a la Iris 😂" (76.1) | "Me flipa el plan, reina. Està anant tot super." (41.5) |
| 22 | "Gracies cuki anims a les 2" | "Sí, en carrusel queda top" (75.1) | "Ja m'ocupo jo de la corona" (41.2) |
| 19 | "De camiii" | "Ja m'estava quedant cega" (71.1) | "Ja ho tinc, m'encanta tot." (38.4) |

**Pattern:** P1 responses are in-character stylistically (Catalan, casual tone) but **less contextually relevant** — they hallucinate context ("espero el link", "m'ocupo de la corona") that doesn't exist in the conversation. A2.5 responses show better awareness of conversational context.

**Response lengths are NOT the issue:** A2.5 avg=24 chars, P1 avg=27 chars (P1 slightly longer).

### Multi-turn K1: catastrophic in conv 0 and 1

| Conv | A2.5 K1 | P1 K1 | Δ |
|------|---------|-------|---|
| 0 | 100.0 | 5.0 | **-95.0** |
| 1 | 100.0 | 36.7 | **-63.3** |
| 2 | 100.0 | 100.0 | 0.0 |
| 3 | 100.0 | 72.5 | -27.5 |
| 4 | 73.0 | 72.1 | -0.9 |

Conv 0 K1=5 means the bot almost completely forgot prior context. Conv 2 is unaffected (K1=100). High variance across conversations.

---

## 5. Hipótesis por commit

### ARC3 Phase 2 compactor shadow (1857468c)

**Probabilidad: MEDIA-ALTA**

**Hipótesis:** The unconditional `asyncio.create_task` on every request, combined with DB INSERTs from `_log_shadow_compactor_sync`, causes connection pool contention during CCEE's rapid-fire requests. When the next request's context phase can't get a DB connection in time, memory/DNA/state lookups fail silently (all have `except: return ""` patterns), resulting in thinner prompts → less relevant responses.

**Evidencia:**
- `enable_compactor_shadow` defaults True, NOT overridden in CCEE env
- Each request triggers `asyncio.to_thread(SessionLocal() → INSERT → commit → close)`
- pool_size=5+7=12 connections total
- 200 shadow INSERTs during full CCEE run
- Context phase has fail-silent patterns: `_read_arc2_memories_sync` returns "", `_get_raw_dna` returns None, etc.
- P1 responses show LESS conversational context awareness (hallucinating non-existent topics)

**Counter-evidence:**
- Tasks are fire-and-forget; CCEE runs sequentially with evaluation pauses between cases
- Each INSERT should complete in <200ms (fast enough to not pile up)
- The compactor task runs AFTER prompt assembly, not concurrently

### ARC3 Phase 4 CircuitBreaker (e6b66d56/ec5fd413)

**Probabilidad: BAJA**

**Hipótesis:** Circuit breaker tripping in MT conversations after consecutive short responses.

**Evidencia:**
- `enable_circuit_breaker` defaults True
- Responses <3 chars recorded as failures; 3 consecutive → trip → fallback

**Counter-evidence:**
- `CCEE_NO_FALLBACK=1` sets `_cb_active=False` → circuit breaker DISABLED during CCEE
- Zero fallback responses found in P1 data
- Zero responses <3 chars in single-turn data

### ARC3 Phase 1 wiring (982390fb)

**Probabilidad: BAJA**

**Hipótesis:** Distill cache DB lookup adds latency even with flag OFF.

**Evidencia:**
- New code in `agent.py:190-213`

**Counter-evidence:**
- `use_distilled_doc_d` defaults False → entire block skipped
- No import, no DB query, no side effect when flag is False

### ARC5 emit_metric middleware (d82d27f3)

**Probabilidad: BAJA**

**Hipótesis:** Middleware adds overhead to each request.

**Evidencia:**
- `emit_metric` calls migrated to unified channel

**Counter-evidence:**
- `git diff 885fe454..main -- api/main.py` shows NO changes to api/main.py
- No middleware added in hot path files
- emit_metric changes are in observability code, not DM pipeline

### ARC2 nightly extract_deep (a0e60125)

**Probabilidad: MUY BAJA**

**Hipótesis:** Scheduler registration adds import overhead.

**Evidencia:**
- New scheduler code in `api/startup/handlers.py`

**Counter-evidence:**
- Scheduler registers a timer, doesn't execute per-request
- CCEE runs don't trigger scheduled jobs
- No changes to DM pipeline imports

---

## 6. Evidencia que NO encontré

1. **Zero fallback responses** in P1 single-turn data (eliminates CB trip)
2. **Zero prompt content changes** when all new feature flags are OFF
3. **Zero CCEE runner code changes** between 885fe454 and main
4. **Identical CCEE metadata** (model, judge, doc_d version, protocol flags)
5. **No temperature or max_tokens changes** in generation.py between commits

---

## 7. Veredicto preliminar

### Culpable más probable: ARC3 Phase 2 compactor shadow (commit 1857468c)

**Razón:** Es el ÚNICO cambio que ejecuta código nuevo en cada request durante CCEE. Todos los demás están gated por flags OFF o desactivados por `CCEE_NO_FALLBACK`. El compactor shadow:
1. Crea un `asyncio.create_task` incondicional en cada request
2. Hace un DB INSERT (via `asyncio.to_thread → SessionLocal()`) en cada request
3. Puede causar contención en el connection pool (5+7=12 connections) durante las 200 requests del CCEE

**Sin embargo:** La evidencia es circumstancial, no definitiva. El shadow task es fire-and-forget y ejecuta DESPUÉS de que el prompt está ensamblado. La calidad del response depende del prompt, no del shadow task.

**Confianza: MEDIA** — el efecto del pool contention es plausible pero no demostrable sin instrumentación adicional.

### Hipótesis alternativa: OpenRouter routing variance

La regresión en S2 es UNIVERSAL (50/50 cases peores, delta min=-2). Esto es estadísticamente imposible por ruido (p < 10^-15). Sin embargo, si OpenRouter rutea a un GPU instance diferente a las 23:00 vs 13:00, el modelo podría generar respuestas sistemáticamente diferentes. Esta hipótesis requiere un re-run para validar.

---

## 8. Multi-turn K1 analysis detallado

| Conv | K1 A2.5 | K1 P1 | G5 A2.5 | G5 P1 | J6 A2.5 | J6 P1 |
|------|---------|-------|---------|-------|---------|-------|
| 0 | 100.0 | 5.0 | 100.0 | 60.0 | 100.0 | 100.0 |
| 1 | 100.0 | 36.7 | 100.0 | 80.0 | 100.0 | 100.0 |
| 2 | 100.0 | 100.0 | 100.0 | 80.0 | 100.0 | 100.0 |
| 3 | 100.0 | 72.5 | 100.0 | 80.0 | 0.0 | 100.0 |
| 4 | 73.0 | 72.1 | 100.0 | 100.0 | 100.0 | 100.0 |

Conv 0 K1=5 (catastrophic) + G5=60 suggests the bot broke persona AND forgot context. This is consistent with either:
- Connection pool exhaustion causing empty context injection (shadow DB writes)
- LLM generating off-topic responses due to model variance

---

## 9. Próximo paso recomendado

**Opción A (recomendada, 90 min):** Re-run CCEE on current main with these env overrides:
```bash
export ENABLE_COMPACTOR_SHADOW=false
export ENABLE_CIRCUIT_BREAKER=false
```
If composite ≥ 70, the compactor shadow is confirmed as culpable. If composite ≈ 66, the regression is environmental (OpenRouter variance).

**Opción B (si A no es concluyente):** Revert commit 1857468c (compactor shadow merge) to a new branch and run CCEE:
```bash
git revert 1857468c --no-commit
# + CCEE run
```

**Opción C (6h, si B no resuelve):** Binary bisect across 30 commits with CCEE at each point.

---

## Appendix: Commits between A2.5 POST-hotfix and main

30 commits total. Bold = hot path changes:

| # | Hash | Description |
|---|------|-------------|
| 1 | f27a5163 | **feat(arc5-phase3): emit_metric helper** |
| 2 | 0ee3df70 | feat(arc2-bonus): nightly extract_deep scheduler |
| 3 | a0e60125 | merge(arc2-bonus) |
| 4 | d82d27f3 | **merge(arc5-phase3): emit_metric** |
| 5 | c73fc912 | **feat(arc3-phase1): StyleDistillCache** |
| 6 | 93bbad86 | analyze(arc4-phase1): baseline |
| 7 | c88edc4f | **merge(arc3-phase1)** |
| 8 | 8ed667c1 | chore: pip rebuild |
| 9 | e5e718d2 | merge(arc4-phase1): kill switches |
| 10 | 27f6978f | **feat(arc3-phase2): PromptSliceCompactor** |
| 11 | **1857468c** | **merge(arc3-phase2): compactor shadow** |
| 12 | 0df554c4 | chore: pip rebuild |
| 13 | a592f66b | fix(prod): cachetools |
| 14 | 8ee21b12 | feat(arc5-phase5): CI checks |
| 15 | **ec5fd413** | **feat(arc3-phase4): CircuitBreaker** |
| 16 | 34c50cb6 | merge(arc5-phase5) |
| 17 | **e6b66d56** | **merge(arc3-phase4+arc5-phase4)** |
| 18 | 55da863e | **feat(arc3-phase1-wiring): distill** |
| 19 | 5ba45506 | docs(arc3-phase1-wiring) |
| 20 | **982390fb** | **merge(arc3-phase1-wiring)** |
| 21-30 | ... | docs, requirements audit, distill validation |

Note: The distill validation at commit 6084c25a measured composite=67.6 (distill OFF), confirming the regression was already present at that point. The gap from 67.6 to P1's 66.4 is within CCEE noise (±2).
