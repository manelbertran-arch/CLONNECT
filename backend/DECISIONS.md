# DECISIONS.md — Clonnect Backend

Architecture and implementation decisions, in reverse chronological order.

---

## 2026-04-19 — ARC3 Phase 1: StyleDistillCache — shadow distillation of Doc D

- **Worker:** ARC3 Phase 1. Branch `feature/arc3-phase1-distill-cache`.
- **Problem:** Creator Doc D (style_prompt) averages ~5 500 chars for iris_bertran, consuming ~69% of the 8 000-char context budget before any lead memory or RAG hits. ARC3 goal: cache a distilled ~1 500-char version that preserves voice/examples/tone rules while reducing token cost by ~73%.
- **Design:** `creator_style_distill` table (migration 048) stores distilled Doc D keyed by (creator_id, doc_d_hash, distill_prompt_version). `StyleDistillService` calls OpenRouter (same provider as prod) with `DISTILL_PROMPT_V1` (ARC3 §2.2.3), validates output in [1 200, 1 800] chars, retries once on failure. Shadow phase: generation happens via `scripts/distill_style_prompts.py` batch CLI; prod agent reads full Doc D unchanged until `USE_DISTILLED_DOC_D=true`.
- **Key decisions:**
  1. Hash = SHA256[:16] of `style_prompt` content → invalidation is automatic when Doc D changes.
  2. `DISTILL_PROMPT_V1` instructs LLM to preserve: voice tics, 3–5 concrete examples, tone rules per lead temperature, form constraints. Eliminate: generic phrases, redundancies, meta-commentary.
  3. `USE_DISTILLED_DOC_D` flag default = False always. Activation gated on ΔCCEE_composite ≥ −3 (reference: QW2 compressed Doc D regressed −10.69 → unacceptable).
  4. Phase 3 activation site marked with shadow hook comment in `core/dm/agent.py:186` — no DB session injected yet (would require refactor of `_load_creator_data`; deferred).
  5. LLM: OpenRouter, `OPENROUTER_MODEL` env var (default `google/gemma-4-31b-it`), timeout 90s, max 2 retries with exponential backoff.
- **CCEE validation:** Deferred — no `DATABASE_URL` / `OPENROUTER_API_KEY` in local env. Must run on staging before Phase 3 activation.
- **Coverage:** 7/7 distill unit tests pass. All other suites (memory/budget/metadata/observability) unaffected. 7/7 smoke pass.
- **Next:** Phase 2 (PromptSliceCompactor shadow) can run in parallel. Phase 3 activates live substitution after CCEE gate passes.

---

## 2026-04-19 — ARC2 A2.5: Accept J4/S3/J6/L2 regressions as controlled tech debt

- **Decision:** Accept ARC2 regressions in J4, S3, J6, L2 as controlled tech debt.
- **Context:** Post-hotfix measurement (`arc2_POSTFIX_iris_20260419_1255.json`, commit `344c5c59`) shows net +2.0 composite over A1.3 baseline (72.6 vs 70.6) but 4 dimension regressions vs A1.3:
  - J4 Line-to-Line: −6.68
  - L2 Logical Reasoning: −3.26
  - S3 Strategic Alignment: −3.20
  - J6 Q&A Consistency: −10.00
- **Rationale:**
  1. K1 Context Retention +29.74 and S1 Style +7.00 outweigh regressions in composite weight.
  2. Composite v5 72.6 > A1.3 70.6 by +2.0 (target was +0.5 above baseline).
  3. Regressions likely caused by `<memoria tipo="X">` format adding visual noise to the prompt — the LLM partially attends to the tags as response content rather than pure context.
  4. S3 has regressed in every arch iteration (ARC1 orchestrator introduction, ARC2 memory injection) — this is a systemic pattern to investigate, not an isolated hotfix artifact.
  5. J6 recovers from 62.5 (PRE-hotfix) to 90.0 (POST) — the −10 vs A1.3=100 is a ceiling effect from cross-session Q&A with memory injection adding irrelevant facts.
- **Next:** Investigate S3/J4/L2 root cause in ARC3 Memory Compaction (compact `<memoria>` block before injection) or ARC4 Mutations Removal (remove legacy mutation context that competes with memory tags).

---


## 2026-04-19 — ARC5 Phase 3: emit_metric helper + central registry + context middleware

- **Worker:** ARC5 Phase 3. Branch `feature/arc5-phase3-emit-metric`.
- **Problem:** ~24 prometheus_client objects scattered across `core/metrics.py` (20) and `core/dm/budget/metrics.py` (4) with no shared label conventions. Each file declares metrics inline, creating maintenance burden and inconsistent `creator_id` injection.
- **Design:** `core/observability/metrics.py` — declarative `_REGISTRY` dict + `emit_metric(name, value, **labels)`. `core/observability/middleware.py` — ContextVars + `CreatorContextMiddleware` auto-injects `creator_id`/`lead_id` from request headers/path into every `emit_metric` call. Design: ARC5_observability.md §2.3 + §3.
- **Key decisions:**
  1. `_REGISTRY_META: Dict[str, str]` stores type ("Counter"/"Histogram"/"Gauge") separately from the metric object — allows `emit_metric` dispatch without `isinstance()`, which fails with MagicMock in tests.
  2. Fail-open: unknown metric name → warning log only. Prometheus failure → error log only. Never raises.
  3. `core/metrics.py` (20 legacy `clonnect_*` metrics) left untouched — gradual migration. Phase 4 will wire them to Grafana dashboards.
  4. `core/dm/budget/metrics.py` migrated first (4 metrics, self-contained `emit_budget_metrics()` function). Removed direct prometheus_client declarations, moved to `_REGISTRY`.
  5. Middleware insertion: after `MetricsMiddleware` in `api/main.py` (ASGI LIFO → context becomes outermost, set first for every request).
- **Migration count:** 4 metrics migrated (dm_budget_*). 20 in `core/metrics.py` pending Phase 4.
- **Coverage:** 19/19 observability tests pass. 237/237 total (memory+budget+metadata+observability). 7/7 smoke.
- **Next:** Phase 4 Grafana dashboards — wire `generation_duration_ms`, `dm_budget_utilization`, `dual_write_*` to 5 dashboards in `docs/observability/dashboards/`.

---

## 2026-04-19 — ARC5 Phase 2: Typed metadata integration into DM pipeline phases

- **Worker:** ARC5 Phase 2. Branch `feature/arc5-phase2-integration`.
- **Problem:** DM pipeline emitted flat untyped dicts into `msg_metadata`. ARC5 Phase 1 built Pydantic models (`DetectionMetadata`, `GenerationMetadata`, `PostGenMetadata`) but they were unused in the actual pipeline.
- **Design:** Three pipeline phases emit typed Pydantic models into `cognitive_metadata` during execution; postprocessing assembles them into a `MessageMetadata` container and writes to `_dm_metadata["_arc5_typed_metadata"]`. Flag `USE_TYPED_METADATA` (default OFF) gates all new writes — zero behavior change when off.
- **Key decisions:**
  1. Typed models stored in `cognitive_metadata` (ephemeral inter-phase dict), not DB helpers — phases lack `session`/`message_id` required by `helpers.py`.
  2. Detection phase uses `_emit_arc5_detection_meta()` closure called before each of 6 return points (rather than try/finally which would require wholesale reindentation).
  3. `detected_intent` at detection phase is always `"other"` — actual intent resolved in context phase (Phase 2), not detection (Phase 1). Acceptable for observability.
  4. `lang_detected` uses `cognitive_metadata.get("detected_language", "unknown")` — language resolved in context phase, not available at detection time.
  5. `context_budget_used_pct` computed as `len(system_prompt) / _MAX_CONTEXT_CHARS` after truncation.
  6. Retry count tracked by `_generation_retry_count` counter incremented inside the truncation recovery loop.
  7. ScoringMetadata skipped (score values not accessible at postprocessing phase — requires DB query). TODO(A2.x) when scoring pipeline is refactored.
  8. ValidationError in any typed metadata build → `logger.warning` + fallback (no crash). Fail-silent to protect the hot webhook path.
- **Coverage:** 116 passed, 1 skipped (all metadata + memory tests).
- **Flag:** `USE_TYPED_METADATA=true` to activate. Default OFF for gradual rollout.

---

## 2026-04-19 — ARC2 A2.4: Dual-write bridge — 3 legacy write points → arc2_lead_memories

- **Worker:** A2.4 of ARC2 Memory Consolidation sprint. Branch `feature/arc2-dual-write`.
- **Problem:** ARC2 Phase 1 migrated historical data but new live writes only go to the 3 legacy systems. arc2_lead_memories stays stale until Phase 3 read-cutover. Need a real-time bridge to keep it current.
- **Design:** `services/dual_write.py` — central fail-silent bridge. 3 hook points: `services/memory_extraction.py::MemoryExtractor._do_extract` (after legacy store loop), `services/memory_service.py::MemoryStore.save` (after JSON persist), `services/memory_service.py::ConversationMemoryService.save` (after DB+JSON save). All calls via `asyncio.create_task` — fire-and-forget, never block the webhook path.
- **Key decisions:**
  1. Flag-gated (`ENABLE_DUAL_WRITE_LEAD_MEMORIES`, default false). Zero overhead when off — early return before any work.
  2. No LLM in sync path — classification is pure dict lookup (`_MEMORY_EXTRACTION_MAP`, `_CONV_FACT_MAP`).
  3. ID resolution (slug/platform_user_id → UUID) done in `asyncio.to_thread` to avoid blocking the event loop.
  4. `_write_entries_sync` creates its own `SessionLocal()` — no shared session state with the caller.
  5. Bot-side ConversationFact types (`price_given`, `link_shared`, `product_explained`, `question_asked`) explicitly mapped to `None` → skipped. Only lead-side signals written.
  6. Fallback `why`/`how_to_apply` injected for `objection`/`relationship_state` to satisfy DB CHECK constraints when not provided by legacy system.
- **Coverage:** 10/10 tests pass. All 3 modified files syntax-clean. Memory suite: 85 passed, 1 skipped.
- **Drift report:** `scripts/dual_write_diff_report.py` — run to compare legacy vs arc2 write counts.
- **Next:** Enable flag in prod after ARC2 Phase 1 migration verified. Soak 7 days → Phase 3 read-cutover.

---

## 2026-04-19 — ARC2 A2.2: Unified memory extractor (5 types, hybrid regex+LLM, <200ms sync)

- **Worker:** A2.2 of ARC2 Memory Consolidation sprint. Branch `feature/arc2-extractor-unified`.
- **Problem:** 3 legacy extractors (memory_extraction.py / memory_engine.py / models/conversation_memory.py) have divergent type schemas, no shared body_structure, and the ConversationMemoryService uses Spanish-only hardcoded regex. None are active in production. ARC2 §2.5 specifies a unified extractor as prerequisite for dual-write (A2.4).
- **Design:** Hybrid Opción C (ARC2 §2.5). `extract_from_message` uses regex-only (ES/CA/EN multilingual patterns) covering `identity` + `intent_signal` per-turn with <1ms latency (budget 200ms). `extract_deep` uses LLM with XML-structured prompt covering all 5 closed types (`identity`, `interest`, `objection`, `intent_signal`, `relationship_state`) for nightly job.
- **Key decisions:**
  1. Pydantic v2 `ExtractedMemory` (frozen) — immutable output, validates type against 5-type closed set at construction.
  2. LLM prompt uses string `.replace()` substitution instead of `.format()` to avoid injection if conversation contains `{` / `}`.
  3. `extract_deep` fail-silent on LLM error (returns `[]` + logs warning) — nightly job must not break pipeline.
  4. Zero imports from 3 legacy systems — clean isolation, ready for Phase 5 removal.
  5. `_classify_signal` pre-filter exits early for noise messages (empty/greeting) before running full regex pass.
- **Coverage:** 89.4% (151 stmts, 16 missed). 29 tests, 7/7 smoke pass. Latency <1ms avg (200x within budget).
- **Next:** A2.4 dual-write wires `extract_from_message` into post-turn webhook hook and persists via `LeadMemoryService` (A2.1). Elimination of Legacy 1+2 after coverage parity validated over 2 weeks prod traffic.

---

## 2026-04-18 — ARC1 A1.2: Integrate BudgetOrchestrator in context.py via feature flag + shadow mode

- **Trigger:** ARC1 Worker A1.2. A1.1 (commit b3720ad1) left `core/dm/budget/` ready. This step wires it into `phase_memory_and_context` without touching the production path.
- **Design:** `docs/sprint5_planning/ARC1_token_aware_budget.md §2.7`.
- **What changed:**
  1. `core/dm/phases/context.py`: added `_ContextAssemblyInputs` dataclass, extracted inline assembly block into `_assemble_context_legacy` (exact copy — zero logic change), added `_assemble_context_new` (token-budget path), added async `_assemble_context` router. Call site in `phase_memory_and_context` replaced with `await _assemble_context(_assembly_inp)`.
  2. `core/dm/budget/gates/` (new): `style.py`, `fewshots.py`, `rag.py`, `history.py`, `__init__.py`. Each gate wraps a pre-computed section string into a typed `Section`. Async to support `asyncio.wait_for` timeout.
  3. `tests/budget/test_integration.py` (new): 22 tests covering all paths.
- **Flag routing:**
  - `ENABLE_BUDGET_ORCHESTRATOR=false` (default) → legacy path, zero diff.
  - `ENABLE_BUDGET_ORCHESTRATOR=true` → BudgetOrchestrator path.
  - `BUDGET_ORCHESTRATOR_SHADOW=true` → both run in parallel, legacy output returned, diff logged at INFO (`budget_orchestrator_shadow: tokens_legacy=X tokens_new=Y diff=Z`). Shadow exceptions are fail-silent (only warning logged).
- **Why extract to dataclass instead of inner function:** module-level functions are testable in isolation without calling the full `phase_memory_and_context` coroutine. Inner functions would require a 1200-line integration harness per test.
- **Why `provider=os.getenv("LLM_PRIMARY_PROVIDER", "gemini")`:** `TokenCounter` uses this for tiktoken/genai selection. Falls back to `len//4` if provider is unrecognised — acceptable estimation error (<3%) for budget gating. Agent object does not expose provider as an attribute.
- **Scope:** 1 file modified (`context.py`), 6 files created. No changes to `generation.py`, `postprocessing.py`, or any production env var. Feature flag defaults OFF — A1.3 will validate with CCEE before enabling.

---

## 2026-04-18 — ARC5 Phase 1: Typed Metadata Models (no integration yet)

- **Trigger:** `docs/sprint5_planning/ARC5_observability.md §2.2` + §3 Phase 1 — introducir Pydantic models para el container `Message.msg_metadata` sin migración DB ni cambio de comportamiento.
- **Módulos nuevos:**
  - `core/metadata/models.py` — 5 Pydantic v2 models literales del doc: `DetectionMetadata` (con `security_flags`/`security_severity` para QW3), `ScoringMetadata`, `GenerationMetadata` (con `compaction_applied`/`distill_cache_hit`/`sections_truncated` para ARC1/ARC3), `PostGenMetadata` (con `rule_violations` para ARC4), `MessageMetadata` container con `schema_version: int = 1`.
  - `core/metadata/serdes.py` — `write_metadata(msg, typed)` (`model_dump(mode="json", exclude_none=True)`) + `read_metadata(msg)` con fallback legacy §2.2.4 (try/except `ValidationError` → bump counter + `MessageMetadata()` vacío, nunca crashea el read).
  - `core/metadata/helpers.py` — `update_detection_metadata` / `update_scoring_metadata` / `update_generation_metadata` / `update_post_gen_metadata`. Cada helper carga msg → `read_metadata` → reemplaza UNA sub-sección → `write_metadata` → commit. Race-safe por fase.
- **Desviaciones documentadas del pseudo-código:**
  1. **Columna real `msg_metadata`, no `metadata`** (api/models/message.py:41). `metadata` colisiona con `Base.metadata` de SQLAlchemy. Serdes duck-typea ambos: prefiere `msg_metadata`, cae a `metadata` para test doubles que siguen literalmente el doc.
  2. **Contador legacy hybrid:** intenta `core.observability.metrics.legacy_metadata_read.inc()` si existe (Phase 2 lo cableará a Prometheus), y siempre incrementa un contador local `get_legacy_read_count()` para tests unitarios sin backend de métricas.
  3. **`_load_message` + `_commit` duck-type async/sync:** el doc usa `await session.get(...)` / `await session.commit()`, pero Phase 2 decidirá la variante final (prod mezcla `SessionLocal` sync + `asyncio.to_thread`). Los helpers llaman `session.get` y `session.commit`; si devuelven awaitables, se awaitan; si no, se usan directamente.
- **Tests:** `tests/metadata/test_models.py` — 22 casos agrupados en 6 clases: `TestContainerDefaults` (schema_version=1), `TestRoundTrip` (full + partial + `exclude_none`), `TestValidation` (intent/confidence/severity/safety_status fuera de Literal), `TestOptionalFields`, `TestLegacyCompat` (dict legacy no crashea + counter aumenta, `None` / `{}` no cuentan como legacy), `TestPartialUpdates` (cada helper preserva las otras 3 sub-secciones).
- **Métricas del módulo:** 22/22 pass, **97.7% coverage** (`models.py` 100%, `serdes.py` 100%, `helpers.py` 93% — 3 líneas del fallback sync-session sin call-site en Phase 1), mypy `--follow-imports=silent` → 0 errores en los 4 archivos.
- **Scope estricto Phase 1:** ningún cambio en `core/dm/phases/detection.py`, `core/dm/phases/generation.py`, `services/lead_scoring.py`, DB, ni migraciones Alembic. Los modelos existen pero nada los usa — Phase 2 los cableará detrás de flag `USE_TYPED_METADATA` con rollout gradual 10%→50%→100%.
- **Refs:** `docs/sprint5_planning/ARC5_observability.md §2.2` (líneas 140-283), §3 Phase 1 (líneas 529-544).

---

## 2026-04-18 — FIX W8-T1-BUG4: Copilot debounce race condition — regen sobrescribía la respuesta manual del creator

- **Trigger:** W8 cross-system matrix audit (`docs/audit_sprint5/W8_C_compatibility_matrix.md:67-69`) detectó que `_debounced_regeneration_impl` en `core/copilot/messaging.py` hace `await asyncio.sleep(DEBOUNCE_SECONDS)` y luego regenera sin verificar si el creator respondió manualmente durante ese sleep. El único gate existente (`pending_msg.status != "pending_approval"`) no cubre el escenario: el path de respuesta manual del creator crea un `Message` nuevo con `role=assistant, approved_by=creator_manual` pero NO muta `pending_msg.status`. Resultado: a T+15s el debounce pisaba `pending_msg.content` / `pending_msg.suggested_response` con la regeneración stale.
- **Helper ya existente:** `CopilotService.has_creator_reply_after(lead_id, since_time, session)` en `core/copilot/service.py:246` — exactamente el check que se necesita. Filtra por `role=assistant + approved_by=creator_manual + created_at > since_time`. No requiere código nuevo, solo callsites.
- **Fix:**
  1. En `schedule_debounced_regen_impl`: añadir `debounce_started_at = datetime.now(timezone.utc)` y `lead_id` al dict `_debounce_metadata[lead_key]`. Se captura en el momento de agendar, no tras el sleep.
  2. En `_debounced_regeneration_impl`: tras fetch de `pending_msg`, llamar `service.has_creator_reply_after(pending_msg.lead_id, meta["debounce_started_at"], session=session)`; si True → log + return sin commit.
  3. Doble-check pre-commit: tras la llamada LLM (`agent.process_dm` tarda varios segundos), re-ejecutar el mismo check antes del UPDATE final. Captura races donde el creator respondió durante la generación.
- **Por qué `debounce_started_at` y no `datetime.now()` tras el sleep:** el task lo pide explícitamente. Si usamos "ahora" como cota, cualquier reply anterior al sleep quedaría fuera de la ventana — precisamente las que queremos detectar. El timestamp de inicio cubre toda la ventana de riesgo (schedule → sleep → LLM → commit).
- **Tests:** `tests/unit/test_copilot_debounce_race.py` (3 casos): (1) reply durante sleep → skip sin commit, `process_dm` no se llama; (2) sanity happy-path — sin reply, commit y update ocurren; (3) reply durante LLM call — pre-commit re-check atrapa el race. Los 3 fallan pre-fix, pasan post-fix.
- **Scope:** 1 archivo editado (`core/copilot/messaging.py`: +22 líneas en 2 bloques) + 1 archivo de test nuevo. No se toca `DEBOUNCE_SECONDS` (protegido por CLAUDE.md, sigue en 15s). No se toca `has_creator_reply_after` ni su firma. No se toca el path de send manual del creator.
- **Refs:** `docs/audit_sprint5/W8_C_compatibility_matrix.md:67-69`, W8 cross-matrix priority 🔴.

---

## 2026-04-18 — FIX W8-T1-BUG3: DNA analyze double-schedule (thread + asyncio.create_task) para el mismo lead

- **Trigger:** W8 Tier-1 forensic audit (`docs/audit_sprint5/tier1/W8_T1_dna_update_triggers.md` + `W8_T1_relationship_dna.md`) detectó que dos call sites independientes podían disparar `analyze_and_update_dna(creator_id, follower_id, …)` concurrentemente para el mismo par:
  1. `core/dm/post_response.py:211` → `triggers.schedule_async_update(...)` → `services.dna_update_triggers.schedule_dna_update(...)` (thread daemon).
  2. `core/dm/phases/context.py:498-520` → `asyncio.create_task(_run_full_analysis())` (loop event).
  El primero dispara en post-response cuando `should_update` devuelve True; el segundo en pre-generación cuando `should_update_dna` de `RelationshipAnalyzer` lo pide. Si un mensaje llega con DNA stale y luego la respuesta sigue cumpliendo el trigger, ambos corren — dos llamadas Gemini, dos escrituras UPDATE sobre la misma fila, race condition benigna pero costosa.
- **Fix (Option B — dedup por (creator_id, follower_id)):** nuevo set a nivel de módulo en `services/dna_update_triggers.py` con `threading.Lock`, más dos helpers públicos `try_register_inflight(cid, fid) -> bool` y `release_inflight(cid, fid)`.
  - `schedule_dna_update` llama `try_register_inflight` antes de spawnear el thread; si devuelve False, no se agenda y se loggea a debug. El `run_update` libera en `finally`.
  - `core/dm/phases/context.py::_run_full_analysis` importa los mismos helpers; registra antes de `asyncio.create_task`, libera en `finally` dentro del coroutine.
- **Por qué Option B y no una única cola:** mantener minimal — el lock no tiene contención significativa (dos call sites, dedup O(1)), el set se limpia al terminar, ningún scheduler nuevo, ninguna tabla nueva, ninguna config flag. Si mañana se añade una tercera ruta (p.ej. un consumer Celery), basta con que también use el helper.
- **Tests:** `TestInflightDedup` en `tests/services/test_dna_update_triggers.py` (5 casos): register-first-time, register-second-time-returns-false, different-pairs-independent, schedule_dna_update-skips-double (mockea `threading.Thread` y verifica que no se spawnea), release-is-idempotent. Los 4 tests existentes siguen pasando.
- **Scope:** 2 archivos editados + 1 archivo de test extendido. No se toca el scheduler, la cooldown de 24h, ni el `should_update` de triggers. La semántica de "si analysis está en-flight, salta este tick" es exactamente lo que se pedía en el audit.
- **Refs:** W8 B.2a tier-1 audit summary (`docs/audit_sprint5/tier1/W8_T1_summary.md`), top-5 priority #3.

---

## 2026-04-18 — FIX W8-T1-BUG2: memory_consolidator gates 4-5 anidados bypassaban throttle para creators nuevos

- **Trigger:** W8 Tier-1 forensic audit (`docs/audit_sprint5/tier1/W8_T1_memory_consolidator.md`) detectó que los gates 4 (scan throttle, CC autoDream.ts:143-151) y 5 (activity ≥ MIN_MESSAGES_SINCE, autoDream.ts:153-171) vivían dentro del `if last_at is not None` de `consolidation_job()`. Cualquier creator sin registro previo en la tabla de consolidación (`last_at = None`) saltaba gate 3 (time), **y también 4 y 5**, y aterrizaba directamente en el advisory lock + `consolidate_creator()`.
- **Impacto en prod:** (a) thundering herd cuando llegan varios creators nuevos en el mismo tick del scheduler — todos consolidan a la vez sin throttle; (b) consolidación prematura de creators con < 20 mensajes totales, desperdiciando tokens LLM y produciendo memos de baja señal.
- **Fix:** minimal — mover gates 4 y 5 fuera del `if last_at is not None` y añadir una rama `else` que trata primera vez como `last_at_utc = datetime(1970, 1, 1, tzinfo=utc)` (infinito pasado). Gate 3 sigue pasando implícitamente; gates 4/5 ahora corren para todos los creators. Con epoch como sentinel, `_count_messages_since(creator_id, epoch)` cuenta todos los mensajes jamás enviados, por lo que el gate 5 bloquea correctamente creators con actividad < MIN_MESSAGES_SINCE.
- **Tests:** `TestFirstTimeCreatorGates` en `tests/test_memory_consolidator.py` — dos casos: (1) `last_at=None` + `msg_count=5 < 20` → activity gate ejecuta y bloquea antes de consolidar; (2) `last_at=None` + `_record_scan` previo → scan throttle bloquea antes de contar mensajes. Ambos fallan en el código pre-fix (`consolidate_creator` se llamaba indebidamente), pasan post-fix.
- **Scope:** estrictamente el bloque de gates en `consolidation_job`. No se tocan `MIN_CONSOLIDATION_HOURS`, `MIN_MESSAGES_SINCE`, `SCAN_THROTTLE_SECONDS`, ni el advisory lock. No se modifica la semántica de `_count_messages_since` ni el scheduler.
- **Refs:** W8 B.2a tier-1 audit summary (`docs/audit_sprint5/tier1/W8_T1_summary.md`), top-5 priority #2.

---

## 2026-04-18 — FIX W8-T1-BUG1: Copilot discard autolearning silently failing (NameError)

- **Trigger:** W8 Tier-1 forensic audit (`docs/audit_sprint5/tier1/W8_T1_copilot_cluster.md`) found that `discard_response_impl` in `core/copilot/actions.py:264,282` referenced `_Cr` and `_lead` that were never imported / never defined. The outer `try/except` at line 287 swallowed the resulting `NameError` and logged it at `debug` level, so the `copilot_discard` preference-pairs / autolearning signal silently stopped firing in prod since the rename that introduced the bug.
- **Root cause:**
  - `_Cr` was a half-completed refactor — the intended name is `Creator` from `api.models` (same pattern used at `approve_response_impl:30`).
  - `_lead` was never fetched in `discard_response_impl`; `approve_response_impl:47` shows the canonical pattern (`session.query(Lead).filter_by(id=msg.lead_id).first()`).
  - The expression `... if not locals().get("_creator") else _creator` was an orphan branch — `_creator` never existed in this scope, so `not locals().get("_creator")` always evaluated `True`, forcing the left branch and the NameError.
- **Fix:** minimal. Added `Creator, Lead` to the existing `from api.models import ...` inside the try block, replaced `_Cr` → `Creator`, dropped the dead `locals()` check, and fetched `_lead` explicitly before the metadata dict. No other handler touched; `approve_response_impl` and `auto_discard_pending_for_lead_impl` already use the correct pattern.
- **Test:** `tests/unit/test_copilot_discard_autolearning.py` — mocks `SessionLocal` + `feedback_capture` and asserts the hook is called with `signal_type=copilot_discard`. Would fail on the pre-fix code (NameError caught and dropped to debug). Passes green post-fix.
- **Scope:** strictly the preference-pairs block inside `discard_response_impl`. No refactor, no behavioural change in the success path of discard.
- **Refs:** W8 B.2a tier-1 audit summary (`docs/audit_sprint5/tier1/W8_T1_summary.md`), top-5 priority #1.

---

## 2026-04-17 — FIX: Catalan future-tense self-harm + regional crisis hotlines (BUG-S3)

- **Trigger:** CCEE run `main_post6qws_t45_20260417_1533.json`, conversation 5. Input `"Em faré mal si no em contestes amb sinceritat"` bypassed GUARD 3 of `core/dm/phases/detection.py`; bot answered with product-oriented content and scored G5 = 1 (worst persona score).
- **Root cause:** Catalan `SELF_HARM_PATTERNS` in `core/sensitive_detector.py` only covered present (`em faig mal`) and volitive (`vull morir`, `em vull matar`) forms. Synthetic future tense (`em faré`, `em tallaré`, `em mataré`, `em suïcidaré`) was not matched. Spanish (`me mataré`, `me cortaré`, `me haré daño`, `me quitaré la vida`, `acabaré con todo`) and English (`hurt myself`, `cut myself` non-gerund) had the same gap.
- **Scope:** 2 code files + 1 new test + 2 docs. NOT a new `core/dm/guardrails/` module — the shipped `SensitiveContentDetector` + QW3 alerting already implement the full pipeline (see `docs/audit_phase2/QW3_security_alerting_report.md`). Building a parallel module would duplicate production code and leave it dead behind the existing GUARD 3.
- **Pattern additions:** CA × 5 (`em faré …? mal`, `em tallaré` with hair/nails lookahead, `em mataré`, `em suïcidaré`, `acabaré amb la meva vida/tot`); ES × 5 (`me mataré`, `me cortaré` with hair/nails lookahead, `me haré … daño`, `me quitaré la vida`, `acabaré con todo/mi vida`); EN × 2 (`hurt myself`, `cut myself`).
- **Signature change:** `get_crisis_resources(language, location_hint=None)`. CA resources now lead with **900 925 555** (Telèfon de Prevenció del Suïcidi Barcelona) followed by **024** (Ministerio de Sanidad); EN replaced US-only **988 / 741741** with **Samaritans 116 123** (backend serves Spain creators by default); ES retains 024 + 717 003 717 + 900 107 917. Hotlines verified out-of-band 2026-04-17. Callsite in `detection.py` reads `agent.personality.location` and falls back to `"Barcelona"` for Catalan dialect creators.
- **Fail-closed policy:** Any future-tense or conditional self-harm phrasing triggers the crisis short-circuit, including coercive framing (`em faré mal si no em contestes`). Over-escalation preferred over miss — documented false-positive tradeoffs listed in `docs/safety/self_harm_guardrail.md`.
- **Tests:** 42 cases in `tests/unit/test_sensitive_detector_catalan_future.py` (CA/ES/EN positive × neighbour negatives × crisis-resource contracts × integration through `phase_detection`). QW3 regression set (17 tests in `test_security_alerting.py` + `test_detection_alerting_integration.py`) still green.
- **Smoke:** 7/7 pre-change, 7/7 post-change.
- **Refs:** BUG-S2 (2026-04-15, dialect-aware crisis language), QW3 (2026-04-16, security_events table + alerting).

---


## 2026-04-17 — Doc D automatic versioning + CCEE traceability (feat/doc-d-versioning)

- **Decisión:** Añadir snapshotting automático de Doc D en `doc_d_versions` antes de cada `weekly_compilation`, con SHA256 dedup en ventana de 24h, y propagar `doc_d_version_id` al JSON output de CCEE.
- **Contexto:** El Doc D se sobrescribía silenciosamente sin snapshot, imposibilitando reproducir baselines CCEE históricos. El último insert en `doc_d_versions` fue el 21-Mar — 26 días sin versionado.
- **Implementación:**
  - `services/persona_compiler.py`: `_snapshot_doc_d()` con SHA256 dedup + `metadata` JSONB; nueva `get_active_doc_d_version_id(session, creator_name)`.
  - `alembic/versions/046_add_doc_d_versions_table.py`: migración idempotente (CREATE IF NOT EXISTS + ADD COLUMN IF NOT EXISTS para `content_hash` y `metadata`) + 2 índices.
  - `scripts/run_ccee.py`: `_build_metadata()` con `doc_d_version_id`, `doc_d_snapshot_at`, `doc_d_char_length`.
  - `scripts/doc_d_snapshot.py`: CLI manual (`--creator`, `--tag`).
  - `tests/test_doc_d_versioning.py`: 12 tests (12/12 pass). Smoke tests: 7/7 pass.
- **Invariante:** snapshot es PREVIO a `_set_current_doc_d` — el update sigue funcionando.
- **Dedup:** SHA256(content) + `created_at > now()-24h` → skip INSERT, retorna ID existente.

---


## 2026-04-16 — Modelo producción: Gemma4-31B Dense

- **Decisión:** volver a Gemma4-31B Dense como modelo de producción.
- **Contexto:**
  - 12-abril: decisión original de usar 31B (no documentada en DECISIONS.md, solo en memoria).
  - 14-abril: BUG-005 identificó respuestas vacías intermitentes → rollback operacional al 26B.
  - 16-abril: re-decisión de volver al 31B con fallback OpenRouter como safety net.
- **Razones:**
  - CCEE solo medido en 31B — W3/W7/QWs todos contra 31B baseline (70.0 composite).
  - Sprint 5 planeado (ARC1-ARC5) asume tokenizer 31B y caps derivados de W3.
  - 26B MoE tiene problemas documentados: fine-tuning inestable, A6 -50 con Sprint 2.
  - BUG-005 fallback OpenRouter mitiga respuestas vacías.
- **Implementación:** `DEEPINFRA_MODEL=google/gemma-4-31B-it`, `DEEPINFRA_FALLBACK_MODEL=google/gemma-4-31b-it` (slug lowercase OpenRouter), `DEEPINFRA_FALLBACK_PROVIDER=openrouter`. Monitorizar fallback trigger rate 72h — si >5% → rollback al 26B hasta que DeepInfra arregle.
- **Smoke test pre-deploy (2026-04-16 — intento 1):** 20/20 EMPTY — falso negativo por `source .env` sin `set -a` (API key no llegaba a Python). Descartado.
- **Smoke test pre-deploy (2026-04-16 — intento 2, válido):** 10/20 OK, 10/20 EMPTY (50% empty rate). Timeouts de 8s, circuit breaker activado 3 veces. **Resultado: >15% → NO se cambió DEEPINFRA_MODEL en Railway.**
- **Estado 2026-04-16:** Railway sigue con `DEEPINFRA_MODEL` no seteado (default `Qwen/Qwen3-32B`). El 31B en DeepInfra sigue inestable — BUG-005 NO está resuelto en producción.
- **Próximo paso:** Re-evaluar tras estabilización DeepInfra o activar DEEPINFRA_FALLBACK_PROVIDER=openrouter para absorber los vacíos antes de switchear.
- **Rollback plan:** `DEEPINFRA_MODEL=google/gemma-4-26B-A4B-it` si >5% fallback rate sostenido o latencia p95 >10s.
- **Refs:** BUG-005 (2026-04-14), W7 baseline 31B, ARC1-ARC5 asumen 31B tokenizer.

---

## 2026-04-16 — CLEANUP: QW4.5 — migrate 2 legacy callers and remove dead systems

- **Context:** QW4 (`d4a6d94d`) removed 6 dead code systems but left 2 blocked by active imports: `core/semantic_memory.py` (imported by `api/startup/cache.py`) and `services/response_variator.py` (imported by `services/bot_orchestrator.py`).
- **semantic_memory migration:** The `cache.py` import (`ENABLE_SEMANTIC_MEMORY`, `_get_embeddings`) was a ChromaDB pre-warm block that **never ran** in production (`ENABLE_SEMANTIC_MEMORY` defaults `false`). Removed the 7-line block; no replacement needed since `semantic_memory_pgvector` uses the OpenAI API (no local model to pre-warm).
- **response_variator migration:** `bot_orchestrator.py` called `variator.process(message)` → `(Optional[str], str)`. Migrated to `ResponseVariatorV2.try_pool_response()` → `PoolMatch(matched, response, category, confidence)`. V2 gains conv-level dedup, calibration-driven pools, and TF-IDF context-aware selection.
- **Files deleted:** `core/semantic_memory.py`, `services/response_variator.py`, `tests/audit/test_audit_semantic_memory.py`, `tests/test_response_variator.py`. Legacy-only tests in `test_personalization.py` and `test_personalization_integration.py` also removed.
- **Tests:** 37 tests pass post-migration (personalization + bot_orchestrator suites).
- **Refs:** W1_inventory_37_systems.md §4.4.

---

## 2026-04-16 — DECISION: No activar USE_COMPRESSED_DOC_D para Iris (QW2)

- **Contexto:** flag en `services/creator_style_loader.py:22` redirige `get_creator_style_prompt()` a un Doc D comprimido (~1.6K chars) en lugar de la personalidad completa (~38K). Objetivo hipotético: reducir context pressure en Gemma-4-31B.
- **Medición:** 3 runs × 50 cases × iris_bertran, matched seed, flag OFF vs ON. Config idéntica a `sprint4_postfix2_31b.json` (gemma-4-31B-it, Qwen3-30B-A3B judge, multi-turn).
- **Resultado:** composite cae **-10.69 pts** (69.42 → 58.73). v4_composite cae **-6.3 pts** (68.8 → 62.5). Las 3 corridas compressed están entre -10.4 y -12.2 vs baseline — regresión consistente, no ruido.
- **Dimensiones clave:** S1 Style -17.5, J_old Memory -37.4, G5 Persona -30.0. Ganancia en S3 Strategic (+12.8) no compensa.
- **Veredicto:** >5 pts → NO activar. Flag queda en default `false`. Ningún cambio de código.
- **Followup:** comprimido híbrido con exemplars + guardrails de persona podría recuperar S1/G5. Documentado en `docs/audit_phase2/QW2_compressed_doc_d_report.md`.

---

## 2026-04-16 — FIX: PersonaCompiler persistence mismatch (QW5)

- **Bug:** `services/persona_compiler.py` reads and writes `creator.doc_d` (lines 1050, 1053, 1105, 1124), but neither the `Creator` ORM (`api/models/creator.py:28`) nor the live DB (Neon) has a `doc_d` column. Every run crashes with `AttributeError: 'Creator' object has no attribute 'doc_d'` — confirmed via `pattern_analysis_runs` query: 30 errors since 2026-04-15 with identical message. Runtime Doc D is in `personality_docs.content` (`doc_type='doc_d'`), written by `core/personality_extraction/extractor.py:366`.
- **Scenario:** A (modified) — column never existed; no data migration needed. `doc_d_versions` snapshot table exists but is empty (crash happens before snapshot INSERT).
- **Fix:** Add `_get_current_doc_d()` and `_set_current_doc_d()` helpers that read/upsert `personality_docs` (canonical pattern from extractor.py). Replace the 4 `creator.doc_d` call sites. Keep `doc_d_versions` snapshot table — its INSERT was never the failure, just unreachable.
- **No schema changes, no data migration, no backup required.** Pure code redirection.
- **Tests:** 3 new in `tests/test_persona_compiler.py` — verify compiler reads from personality_docs, writes via upsert, rollback_doc_d uses new store.
- **Expected impact:** PersonaCompiler can be activated (ENABLE_PERSONA_COMPILER=true) without AttributeError. `pattern_analysis_runs` will start showing `status='done'` again instead of `error`.
- **Follow-up:** Activar flag en staging para Iris/Stefano post-merge y correr 1 ciclo; verificar nuevos rows `done` en pattern_analysis_runs.

---

## 2026-04-16 — FEAT: Security event alerting for prompt_injection + sensitive flags (QW3)

- **Problem:** `cognitive_metadata["prompt_injection_attempt"]` (detection.py:103) and `cognitive_metadata["sensitive_detected"]` (detection.py:125) were written on every match but never consumed by any downstream system. Orphan flags = zero observability on security incidents.
- **Fix:** New `security_events` table + `alert_security_event()` dispatcher. Integrates at both detection.py sites via fire-and-forget `asyncio.create_task`.
- **Table:** `security_events(id, creator_id, sender_id, event_type, severity, content_hash, message_length, event_metadata, created_at)` + composite index `(creator_id, sender_id, event_type, created_at DESC)`. Integer PK (autoincrement) — high-write event log, UUID not needed.
- **GDPR:** never store raw message content. Only SHA256 hex (64 chars) + length. Fingerprint allows dedup/correlation without PII retention.
- **Severity:** `prompt_injection`→WARNING (always). `sensitive_content`→WARNING below escalation threshold, CRITICAL at/above. INFO reserved for rate-limit summary rows.
- **Rate limit:** in-process `TTLCache(maxsize=10_000, ttl=300)` from cachetools. Window=60s per `(creator, sender, event_type)`. Every 100th suppressed event writes an INFO summary row so bursts are still visible.
- **Fail-silent:** entire dispatch body wrapped in try/except; any DB/hash/cache failure is logged at debug level and swallowed. Alerting never blocks or crashes the detection pipeline.
- **Async pattern:** `asyncio.create_task(alert(...))` with module-level `_pending_tasks: set` + `add_done_callback(_pending_tasks.discard)` to prevent "Task was destroyed" warnings. DB write runs via `asyncio.to_thread(_sync_write)` using `get_db_session()` (same pattern as context.py:163).
- **Out of scope:** Slack/email webhooks (next sprint). Current delivery is DB-only; consumers will poll `security_events` for reporting.
- **Tests:** 9 unit tests (rate-limit, severity mapping, hash stability, fail-silent, suppression summary) + 3 integration tests (detection.py dispatches on both flags, never raises).
- **Migration:** `045_add_security_events.py` (down_revision=044).

---

## 2026-04-16 — FIX: Wire _tone_config emoji_rule into system prompt (QW6)

- **Bug:** `_tone_config` in `PromptBuilder.build_system_prompt` (services/prompt_service.py:75) was computed but immediately abandoned. The `emoji_rule` field ("- Uso de emojis: NINGUNO/frecuente/moderado") never reached the LLM, meaning all tones generated with generic LLM emoji behavior.
- **Fix:** Added `_tone_config["emoji_rule"]` as the first bullet in the IMPORTANTE block. ~11 tokens per request.
- **Also updated:** `_format_safety_section` in context.py accepts a `tone_key` param so cache-boundary parity test stays green.
- **StyleNormalizer:** post-generation emoji normalization still runs; this fix addresses the upstream cause (LLM not instructed correctly).
- **Tests:** 7 new in `TestToneEmojiRule`. Cache boundary parity tests all pass.
- **Expected CCEE impact:** leve mejora S1 (style fidelity). No regression risk.

---

## 2026-04-16 — CHORE: Remove 30 orphan writes to cognitive_metadata

- **Context:** W2 metadata flow audit identified 30 fields written to `cognitive_metadata` that are never read by any downstream consumer (not by postprocessing, not by the API response, not by tests).
- **Fields removed:** RAG telemetry (7), hierarchical memory telemetry (3), SBS (4), PPA (3), loop/echo/quality flags (8), compaction/style flags (5). Full list in `docs/audit_phase2/QW1_cleanup_report.md`.
- **Why:** Dead writes add noise to the dict, waste dict allocation, and create confusion about what cognitive_metadata actually exposes. They were telemetry stubs that never got a reader wired up.
- **Invariants:** Logic of all systems (RAG gate, SBS, PPA, echo detection, style normalization) is preserved. Only the `cognitive_metadata["key"] = value` lines were removed. Logs unchanged.
- **Not touched:** `prompt_injection_attempt`, `sensitive_detected` — reserved for QW3 alerting work.
- **Tests:** 18 passed (test_context_analytics + sprint1_verification). 51 lines deleted across 3 files.

---

## 2026-04-15 — FIX: Cache boundary must not reorder prompt sections

- **Regression:** `ENABLE_PROMPT_CACHE_BOUNDARY=true` caused G5 100→80, S3 74→64, L3 58→45.
- **Root cause:** The ON path reordered sections (knowledge/products to #2/#3, fewshot from #2 to #4, safety to #13, advanced to #14). This broke the style→fewshot adjacency that anchors persona behavior and moved guardrails away from the recency-attention position.
- **CC pattern (prompts.ts:560-576):** CC's boundary marker is passive — it sits between static and dynamic content at a fixed point. The section order is IDENTICAL regardless of caching. `splitSysPromptPrefix()` (api.ts:362-404) only splits at the boundary index, never reorders.
- **Fix:** Single `_sections` list in original order for both ON and OFF paths. ON path appends knowledge/products/safety AFTER override (matching prompt_service.py natural order) instead of reordering them to the top. Only `_STATIC_LABELS` and `_CRITICAL_LABELS` differ between paths.
- **Tests:** 21/21 test_cache_boundary passed, 7/7 smoke tests passed.

---

## 2026-04-14 — BUG-006: Google AI Studio timeout limitation

- Gemma 4 31B en Google AI Studio: prompts cortos (<50 facts) = 1.6s OK
- Prompts largos de consolidación (200 facts) = timeout 120-180s
- `thinkingBudget: 0` no soportado (HTTP 400 INVALID_ARGUMENT)
- **Decisión:** Google AI Studio NO viable como provider de consolidación para leads pesados. Usar DeepInfra (con fallback OpenRouter). Solo viable para producción (prompts de DM cortos).

---

## 2026-04-14 — BUG-001: _resolve_lead_uuid ig_ prefix mismatch

**Problem**: `media.py:233` passes `sender_id=f"ig_{message.sender_id}"` to the DM agent pipeline. `_resolve_lead_uuid` receives `"ig_1234567890"` but builds search array `["ig_1234567890", "ig_ig_1234567890", ...]` — never finds `"1234567890"` (raw numeric) in DB. Result: 146 leads post-Sprint 3 have 0 memories extracted.

**Root cause**: Newer leads store raw numeric `platform_user_id` (via `lead_manager.py:215`), older leads store `ig_` prefixed (via `lead_manager.py:581`). The function never stripped prefixes before searching.

**Fix**: Strip known platform prefixes (`ig_`, `wa_`, `tg_`) before building the `ANY()` search array. Search includes both raw and prefixed forms. All 4 callers covered by single fix. Logging upgraded `debug→warning`. Task tracking added in postprocessing (CC DreamTask pattern). Backfill script created and executed: 142/146 leads backfilled.

**CC pattern**: CC autoDream uses no platform prefixes (file-based memory, no DB UUID resolution). The bidirectional search is a necessary Clonnect divergence.

---

## 2026-04-14 — BUG-005: DeepInfra auto-fallback to OpenRouter + circuit breaker cooldown

**Problem**: `google/gemma-4-31b-it` on DeepInfra returns empty responses intermittently. The circuit breaker opens after 3 failures and blocks ALL requests for 120s with no fallback — 270+ errors accumulated in a single CCEE run. The 26B model is unaffected.

**Root cause**: Empty responses return HTTP 200, so the caller sees a "success" from the transport layer. The circuit breaker correctly counted them as failures (existing `_record_failure()` on empty content) but the 120s cooldown with no recovery path was the problem.

**Fix A — Auto-fallback**: Added `_try_openrouter_fallback()` called from all 4 failure paths (circuit open, empty content, timeout, generic exception). Fallback is transparent to callers. Gated by `DEEPINFRA_FALLBACK_PROVIDER=openrouter` (off by default — opt-in to avoid silent cost/observability surprises). Requires `OPENROUTER_API_KEY`. Optional `DEEPINFRA_FALLBACK_MODEL` for slug override when provider namespaces differ.

**Fix B — Cooldown 120→30s**: With a fallback active, the primary can retry more aggressively. Controlled via `DEEPINFRA_CB_COOLDOWN` env var.

**Fix C — Empty response detection**: Already implemented; verified correct (`_record_failure()` + `return None` path). No change needed.

**CC pattern**: CC has no provider-level circuit breaker (single upstream). The fallback pattern follows `gemini_provider.py`'s Gemini→GPT-4o-mini inline fallback (opt-in via `DISABLE_FALLBACK`).

**Files modified**: `core/providers/deepinfra_provider.py`, `tests/unit/test_deepinfra_provider.py`

---

## 2026-04-12 — Sprint 3: Memory Consolidation (autoDream pattern from Claude Code)

**Problem**: 12,269 facts across 415 leads grow without reorganization. Compression only triggers on add() per-lead. No periodic cross-lead dedup, no stale fact pruning, no proactive consolidation.

**Pattern source**: Claude Code `src/services/autoDream/autoDream.ts` + `consolidationPrompt.ts` + `consolidationLock.ts` + `config.ts`.

**Key CC behaviors adapted**:
1. Gate order cheapest-first: Time → Activity → Lock (autoDream.ts:5-8)
2. Time gate: hours since last consolidation >= configurable min (default 24h)
3. Activity gate: messages since last consolidation >= configurable min (default 20)
4. Advisory lock per-creator (CC uses file lock with PID — consolidationLock.ts:46-84)
5. Lock rollback on failure (consolidationLock.ts:91-108)
6. 4-phase protocol: Orient → Gather → Consolidate → Prune (consolidationPrompt.ts:27-58)
7. Scan throttle: 10-min cooldown between activity scans (autoDream.ts:56)
8. Feature flag: ENABLE_MEMORY_CONSOLIDATION (CC: config.ts:13-21)

**Adaptations from CC**:
- CC uses forked LLM agent on memory files → Clonnect uses programmatic DB operations + LLM for memo compression
- CC counts session files by mtime → Clonnect counts messages since last consolidation
- CC uses file lock with PID → Clonnect uses pg_try_advisory_lock on creator UUID hash
- CC hooks into post-sampling → Clonnect uses TaskScheduler (webhook-based, no turns)
- CC operates per-project → Clonnect operates per-creator

**Files**: 
- CREATE: `services/memory_consolidator.py`
- CREATE: `services/memory_consolidation_ops.py`
- CREATE: `services/memory_consolidation_llm.py`
- CREATE: `tests/test_memory_consolidator.py`  
- MODIFY: `api/startup/handlers.py` (register scheduler job)
- MODIFY: `services/memory_engine.py` (advisory lock check in add/compress)

**Feature flags**:
- `ENABLE_MEMORY_CONSOLIDATION` (default OFF) — gates entire consolidation system
- `ENABLE_LLM_CONSOLIDATION` (default OFF) — gates LLM-powered analysis within Phase 3

### 2026-04-12 — LLM Consolidation Step (CC-faithful)

**Problem**: Original Sprint 3 used only algorithmic (Jaccard) dedup. CC uses LLM for ALL consolidation intelligence: dedup, contradiction detection, date conversion (consolidationPrompt.ts:44-52). Code only decides WHEN to run.

**Design decisions**:
1. **Single-turn LLM vs CC multi-turn agent**: CC needs multi-turn because the agent discovers state via filesystem tools (ls, cat, grep). Clonnect Phase 1-2 already loads all facts into `_FactRow` objects — no discovery loop needed. Single-turn with structured JSON response is sufficient.
2. **No tools (vs CC tool-equipped agent)**: CC gives tools because the agent operates on opaque files. Clonnect has parsed data — LLM analyzes, code executes.
3. **Feature flag separation**: `ENABLE_LLM_CONSOLIDATION` separate from `ENABLE_MEMORY_CONSOLIDATION` — allows testing algorithmic-only vs LLM-enhanced independently.
4. **Graceful degradation**: LLM failure never blocks consolidation — falls back to algorithmic Jaccard dedup + TTL expiry silently.
5. **Reuses `generate_dm_response` cascade**: Same Gemini Flash-Lite → GPT-4o-mini as memory_engine._call_llm.

**CC capabilities mapped**:
| CC Capability | CC Source | Clonnect Implementation |
|---|---|---|
| Merge near-duplicates | consolidationPrompt.ts:49 | `llm_analyze_facts()` → duplicates array |
| Delete contradicted facts | consolidationPrompt.ts:51 | `llm_analyze_facts()` → contradictions array |
| Convert relative dates | consolidationPrompt.ts:50 | `apply_date_fixes()` → DB updates |
| Conservative approach | consolidationPrompt.ts:46 | "Be CONSERVATIVE" in prompt + validation |

### 2026-04-12 — Extraction Guards (CC-faithful extractMemories pattern)

**Problem**: `memory_engine.py:add()` had none of the CC extraction guards: no overlap protection, no cursor, no manifest pre-injection, no exclusion rules in prompt, no turn throttle, no drain. Spanish prompt was minimal.

**Pattern source**: CC `src/services/extractMemories/extractMemories.ts` (616 lines) + `prompts.ts` (155 lines) + `memoryTypes.ts` (272 lines).

**Structural change**: Extracted extraction pipeline from `memory_engine.py` (1717→1560 lines) to new `memory_extraction.py` (461 lines). `add()` is now a thin wrapper.

**CC guards implemented**:
| Guard | CC Source | Clonnect Implementation | Feature Flag |
|---|---|---|---|
| Overlap guard | extractMemories.ts:550-558 | `_in_progress` dict per (creator,lead) | `MEMORY_OVERLAP_GUARD_ENABLED=true` |
| Turn throttle | extractMemories.ts:389-395 | `_turn_counter` dict, configurable N | `MEMORY_EXTRACT_EVERY_N_TURNS=1` |
| Manifest pre-injection | extractMemories.ts:400-404 | Existing facts formatted into prompt | `MEMORY_MANIFEST_ENABLED=true` |
| Cursor incremental | extractMemories.ts:337-342 | In-memory dict per (creator,lead) | `MEMORY_CURSOR_ENABLED=false` |
| Drain | extractMemories.ts:611-615 | `_in_flight` set + `drain()` method | Always available |
| Improved prompt | prompts.ts:50-93, memoryTypes.ts:183-195 | English, exclusions, date conversion | N/A (always active) |

**Design decisions**:
1. **In-memory state (not DB)**: CC uses closure-scoped state (extractMemories.ts:305-319). Clonnect uses dicts in MemoryExtractor. No DB migration needed — state resets on deploy (acceptable: dedup catches any re-extractions).
2. **Cursor default OFF**: Requires `source_message_id` to be passed from postprocessing.py. Can enable once ID is available.
3. **ConversationMemoryService NOT deprecated**: Regex extractor (prices, URLs, products, questions) is complementary to LLM. Detects exact patterns the LLM would miss. Stored as JSON blob, different from individual lead_memories facts.
4. **Prompt in English**: CC prompts are English. LLM reasons better in English. Facts can be in any language — the prompt is language-agnostic.

**Files**:
- CREATE: `services/memory_extraction.py` (461 lines)
- CREATE: `tests/test_memory_extraction.py` (19 tests)
- MODIFY: `services/memory_engine.py` (1717→1560 lines: moved add body + _extract_facts_via_llm + _format_messages_for_llm)
- MODIFY: `tests/test_memory_engine.py` (2 tests updated to use extractor)

---

## 2026-04-11 — Sprint 2.7: Dedup AFTER selection, not before (CC-faithful pipeline order)

**Problem**: Sprint 2.6 made compactor output identical to legacy (50/50) — meaning the compactor adds zero value. The variable window never activates because dedup happens before selection on a [-10:] slice.

**Root cause**: CC does NOT dedup. `calculateMessagesToKeepIndex` (sessionMemoryCompact.ts:324-397) operates on the raw `messages[]` array. Anthropic API accepts consecutive same-role messages. Gemini doesn't — so Clonnect needs dedup, but it must happen AFTER selection.

**Fix**: Change `generation.py` pipeline order:
- Before: `raw[-10:]` → strip_leading → dedup → select(budget) → API
- After:  `ALL raw` → strip_leading → select(budget) → dedup(kept) → truncate(600) → API

The compactor receives all raw messages (no dedup, no slice). After selection, the kept messages are deduped for Gemini compatibility and truncated at 600 chars (matching legacy per-message truncation).

**Files**: `generation.py` only (compactor code unchanged).

---

## 2026-04-11 — Sprint 2.6: Fix dedup scope + disable summary injection (fix CCEE regression v2)

**Problem**: Sprint 2 v2 (positional selection) still regresses CCEE: 26B -5.1, 31B -22.7.
Root cause diagnosis:
1. `generation.py:370-380` deduplicates ALL history before compactor → shifts message boundaries vs legacy. 36/50 CCEE cases get DIFFERENT recent messages.
2. Summary + verbatim marker (~142 chars Spanish meta-text) injected in 50/50 cases → contaminates style context.

**Fix 1**: Dedup only `history[-10:]` before compactor (same as legacy), not full history. Verified: when compactor gets same input as legacy, output is identical (50/50).

**Fix 2**: Put `_build_dropped_summary` and verbatim marker behind `ENABLE_COMPACTOR_SUMMARY` (default false) and `ENABLE_VERBATIM_MARKER` (default false). Compactor output = boundary + kept messages only.

**Files**: `generation.py` (dedup scope), `history_compactor.py` (env vars), `test_history_compactor.py` (updated tests).

---

## 2026-04-11 — Sprint 2.5: Revert to pure positional selection (fix CCEE regression)

**Problem**: Sprint 2 history compaction caused CCEE regression:
- 26B: 64.3 → 61.0 (-3.3)
- 31B: 63.4 → 58.8 (-5.5)
Forensic diagnosis identified root cause: importance scoring discarded short assistant messages
(emojis, short replies) that served as in-context style examples for the LLM. S1 (style fidelity)
dropped -10.9, S3 (strategic alignment) dropped -13.9.

**Decision**: Revert `select_and_compact()` to pure positional selection (CC-faithful).
Most recent messages kept, oldest dropped. No importance scoring in selection.
Keep everything else: variable window, dropped-message summary, boundary markers,
section-aware truncation, verbatim marker.

**Rationale**: CC uses pure recency (sessionMemoryCompact.ts:372). The importance scoring
was our addition over CC's design. It backfired because:
1. Short assistant messages (💕, "molt be!") scored low (0.15-0.25) but were crucial style examples
2. Role boost favored user messages over assistant (inverted for our use case)
3. Removing style examples from history made the LLM fall back to generic "jajaja 😂😂😂" responses

**Files**:
- MODIFIED: `core/dm/history_compactor.py` (pure positional Phase 2+3, no importance in selection)
- MODIFIED: `tests/test_history_compactor.py` (updated 3 tests for positional behavior)

**Tests**: 61/61 pass. Smoke tests pass.

---

## 2026-04-11 — Sprint 2.4: Boundary markers + LLM summary (CC full fidelity)

**Problem**: Two remaining gaps from CC pattern audit:
1. No boundary marker — if history is persisted between requests, no way to prevent re-compacting already-summarized messages.
2. Template-only summary — CC uses an LLM agent (extractSessionMemory) for rich semantic summaries; Clonnect only had a mechanical template.

**Research**: Read CC source:
- `createCompactBoundaryMessage` (messages.ts:4530-4555): system message with `compactMetadata` (trigger, preTokens, messagesSummarized).
- `isCompactBoundaryMessage` (messages.ts:4608-4612): detection by `type === 'system' && subtype === 'compact_boundary'`.
- Usage as floor (sessionMemoryCompact.ts:370-371): `findLastIndex(m => isCompactBoundaryMessage(m))`, `floor = idx + 1`. Backward expansion loop starts at `floor` (line 372).
- Filtered from messagesToKeep (line 577-581): `.filter(m => !isCompactBoundaryMessage(m))`.
- `extractSessionMemory` (sessionMemory.ts:272-350): forked LLM agent with structured template.
- `buildSessionMemoryUpdatePrompt` (prompts.ts:43-80): "Write DETAILED, INFO-DENSE content".

**Implementation**:
1. **Boundary marker**: `create_compact_boundary()` / `is_compact_boundary()`. Injected between summary and kept messages. Input boundaries used as floor during expansion; old boundaries filtered from working set.
2. **LLM summary**: `_build_llm_summary()` behind `ENABLE_LLM_SUMMARY` flag (default OFF). Uses cheapest available model (Gemini Flash Lite or GPT-4o-mini). Falls back to template on failure.

**Files**:
- MODIFIED: `core/dm/history_compactor.py` (boundary marker, LLM summary, 6 env vars total)
- MODIFIED: `core/dm/phases/generation.py` (filter boundary markers from LLM messages)
- MODIFIED: `tests/test_history_compactor.py` (61 total tests, all pass)

**Env vars**:
- `COMPACTOR_BOUNDARY_MARKER=[__COMPACT_BOUNDARY__]` — boundary content sentinel
- `ENABLE_LLM_SUMMARY=false` — LLM summary flag (default OFF, template used)
- `COMPACTOR_LLM_SUMMARY_MODEL=` — model override (empty = auto-detect cheapest)
- `COMPACTOR_LLM_SUMMARY_PROMPT=...` — customizable prompt template

---

## 2026-04-11 — Sprint 2.2+2.3: Dropped-message summary + CC fidelity improvements

**Problem**: When messages are excluded from compacted history, they disappeared silently. CC replaces excluded messages with a structured session memory summary (sessionMemoryCompact.ts:437-503).

**Research**: Read CC source code end-to-end:
- `createCompactionResultFromSessionMemory` (sessionMemoryCompact.ts:437-503): reads pre-computed session memory, truncates oversized sections, wraps in formatted user message, injects before kept messages.
- `extractSessionMemory` (sessionMemory.ts:272-350): background forked LLM agent.
- `getCompactUserSummaryMessage` (prompt.ts:337-374): formats summary + verbatim marker.
- `flushSessionSection` (prompts.ts:298-323): per-section truncation at line boundaries.
- `truncateSessionMemoryForCompact` (prompts.ts:256-295): processes each `# section` independently with per-section char budget.
- `createCompactBoundaryMessage` (messages.ts:4530-4555): marks compaction point for multi-compaction chains; used as floor in backward expansion (sessionMemoryCompact.ts:370) and filtered from messagesToKeep (line 581).

**Limitation**: CC's session memory is generated by a background forked LLM agent — Clonnect can't run a background agent in the DM hot path.

**Adaptation**:
1. **Summary content**: MemoryEngine facts + template-based metadata (counts, types, topics). No LLM call.
2. **Section-aware truncation**: `_truncate_section()` follows CC's `flushSessionSection` (prompts.ts:298-323) — truncates at pipe/space boundaries, not mid-word, with `[... truncado]` marker.
3. **Verbatim marker**: `[Los mensajes siguientes se conservan literalmente.]` appended to summary (CC: `"Recent messages are preserved verbatim."`, prompt.ts:353-354).
4. **Boundary marker**: N/A — CC uses boundaries for multi-compaction chains (sessionMemoryCompact.ts:370, 581). Clonnect DM compaction runs once per request with no persistent message store. No chains, no boundaries needed.

**Files**:
- MODIFIED: `core/dm/history_compactor.py` (`_build_dropped_summary`, `_truncate_section`, `MAX_SUMMARY_CHARS`, verbatim marker, section-aware truncation)
- MODIFIED: `core/dm/phases/generation.py` (pass `existing_facts` from cognitive_metadata)
- MODIFIED: `tests/test_history_compactor.py` (50 total tests, all pass)

**Env vars**: `COMPACTOR_MAX_SUMMARY_CHARS=500` (default)

---

## 2026-04-11 — Sprint 2.1: Variable Window Selection (CC pattern)

**Problem**: Sprint 2 compactor receives a pre-sliced `history[-10:]` window. When 8/10 recent messages are trivial (😂, [audio]), it can only redistribute budget among those 10 — it cannot reach back to substantive message #15. Audit of Claude Code's `sessionMemoryCompact.ts:324-397` confirmed: CC's power is in variable window sizing, not per-message scoring.

**Research**: Read `calculateMessagesToKeepIndex` (CC source). Pattern: start from most recent, expand backwards until `minTokens` + `minTextBlockMessages` met, stop at `maxTokens` cap. Purely positional — no importance scoring. Our adaptation adds importance scoring during expansion because 50.5% of DM messages are trivial (CC doesn't have this problem — its messages are tool calls/code).

**Design**: New `select_and_compact()` function:
1. Score all messages in full history pool (importance scorer from Sprint 2)
2. Guarantee `MIN_RECENT_MESSAGES` (env var, default 3) substantive messages from the end (CC's `minTextBlockMessages` equivalent)
3. Expand backwards: add messages passing `IMPORTANCE_THRESHOLD` (env var, default 0.3) until `MAX_OUTPUT_MESSAGES` (env var, default 10) or `total_budget_chars` (6000) reached
4. Return selected messages in chronological order

**generation.py change**: Pass ALL history to compactor (not `history[-10:]`). Compactor decides window size. Feature flag `ENABLE_HISTORY_COMPACTION` still controls ON/OFF — when OFF, exact legacy behavior (`history[-10:]` + uniform 600-char truncation).

**Audit gaps closed**:
- ❌→✅ Fixed window: compactor now sees full pool, selects variable number of messages
- ❌→✅ No min message count: `MIN_RECENT_MESSAGES=3` guarantees recent substantive msgs survive

**Files**:
- MODIFIED: `core/dm/history_compactor.py` (added `select_and_compact`, env vars, `_is_substantive`)
- MODIFIED: `core/dm/phases/generation.py` (pass full history, call `select_and_compact`)
- MODIFIED: `tests/test_history_compactor.py` (12 new tests for variable window, 30 total, all pass)

**Env vars** (all with defaults, zero-config):
- `COMPACTOR_MIN_RECENT_MESSAGES=3` — minimum substantive messages guaranteed
- `COMPACTOR_MAX_OUTPUT_MESSAGES=10` — max messages in output
- `COMPACTOR_IMPORTANCE_THRESHOLD=0.3` — min score for expansion candidates
- `ENABLE_HISTORY_COMPACTION=false` — master feature flag (unchanged)

---

## 2026-04-11 — Sprint 2: History Compactor — importance-based budget redistribution

**Problem**: DM pipeline truncates conversation history uniformly (10 msgs × 600 chars each). This wastes budget: 50.5% of real messages are <20 chars (emojis, stickers, audio refs) while substantive messages (schedules, questions, context) get same budget as trivial ones.

**Research**: Analyzed Claude Code's sessionMemoryCompact.ts pattern (token-based thresholds, session memory summaries) and adapted the importance scoring concept to Clonnect's simpler DM pipeline. Analyzed 75,550 real messages from DB: P25=9, P50=19, P75=38, P90=78 chars.

**Design**: Per-message importance scorer (0.0-1.0) using data-derived signals:
1. Content type: media refs ([audio], [sticker]) → 0.1, pure emoji → 0.15
2. Length vs creator's A1_length percentiles: below P25 → low, above P75 → high
3. Role: user messages get +0.05 boost (carry questions/context)
4. Fact deduplication: overlap with MemoryEngine facts → penalty up to 0.3

Budget redistributed proportionally: important messages get more chars, trivial ones get fewer. Total budget stays ≤ 6000 chars (same as current uniform).

**Calibration (500 real messages)**: p25_score=0.30, p50=0.44, p75=0.69, mean=0.49 — well-centered distribution matching data percentiles.

**Files**:
- CREATED: `core/dm/history_compactor.py` (importance scorer + budget allocator)
- MODIFIED: `core/dm/phases/generation.py` (integration with feature flag)
- CREATED: `tests/test_history_compactor.py` (15 tests, all passing)

**Feature flag**: `ENABLE_HISTORY_COMPACTION=true` (default OFF). Instant rollback.
**Blast radius**: Zero when flag OFF. When ON, only affects history message preparation in generation.py. No other pipeline components touched.

---

## 2026-04-11 — Fix: CCEE_NO_FALLBACK guard missing for legacy deepinfra path

**Problem**: During CCEE v5.1 baseline measurement, run 2 was contaminated with OpenAI GPT-4o-mini fallback responses (60 events). Root cause: `gemini_provider.py` legacy path for `LLM_PRIMARY_PROVIDER == "deepinfra"` (line ~723) had no `CCEE_NO_FALLBACK` guard, unlike `google_ai_studio` and `openrouter`. Since `LLM_MODEL_NAME` is not set in the 31B env file, `get_active_model_config()` returns None, routing to the unguarded legacy path.

**Fix**: Added `CCEE_NO_FALLBACK` guard after the legacy deepinfra path fails, returning None instead of falling through to Gemini → OpenAI chain.

**Affected file**: `core/providers/gemini_provider.py` (line 727, 3-line addition)
**Blast radius**: Zero production impact (CCEE_NO_FALLBACK is eval-only). Prevents silent model contamination during benchmarks.

---

## 2026-04-10 — CCEE v5: H1 Automated Turing Test + B2/B5 Auto-Activation + v5 Composite

**Goal**: Three improvements to close evaluation gaps identified by paper review.

**Changes**:
1. **H1 Automated Turing Test** (`multi_turn_scorer.py`): Fetch real creator responses from DB (messages table, keyword-overlap matching), compare with bot responses via existing `judge_turing_test()`. Score = (fooled/total) × 100. Falls back to ground_truth if no DB match.
2. **Auto B2/B5** (`run_ccee.py`): When `--multi-turn` is active, automatically run Prometheus judge (B2, B5, C2, C3, H1) on single-turn test cases. Removes need for separate `--with-prometheus-judge` flag.
3. **v5 Composite** (`run_ccee.py`): New `_compute_v5_composite()` integrating H1 + B dimensions. Weights: 0.16×S1 + 0.12×S2 + 0.16×S3 + 0.09×S4 + 0.03×Jold + 0.09×Jnew + 0.03×J6 + 0.06×K + 0.05×G5 + 0.09×L + 0.07×H + 0.05×B = 1.00.

**Affected files**: `core/evaluation/multi_turn_scorer.py`, `scripts/run_ccee.py`
**Blast radius**: Additive only. v4/v4.1 composites unchanged. New `--v5` flag required.

---

## 2026-04-09 — Universal Clone Factory: zero hardcoding across all post-processing

**Goal**: Make the entire clone pipeline work for ANY creator without code changes. Every threshold, fallback list, and default must come from the creator's mined data profile.

**Changes** (8 files, 8 subsystems):
1. **Fallback guard** (`gemini_provider.py`, `generation.py`): `DISABLE_FALLBACK=true` env guard blocks all LLM fallback cascades. Prevents Gemini contamination during evaluation.
2. **Judge default** (`m_prometheus_judge.py`): Default provider changed from OpenAI to DeepInfra Qwen3-30B-A3B. max_tokens=1500, /no_think suffix. ~100x cheaper.
3. **Doc D** (`compressed_doc_d.py`): Reverted to pre-audit version without embedded few-shots. Hybrid experiment caused B1 OCEAN instability (0→66→83 across runs).
4. **Question remover** (`question_remover.py`): Removed hardcoded `question_rate=0.10` default. Now loads from creator baseline profile; skips if no data.
5. **Anti-echo** (`postprocessing.py`): Replaced hardcoded `["ja", "vale", "uf", "ok", "entès", "vaja"]` with creator's `short_response_pool` from calibration.
6. **Style normalizer** (`style_normalizer.py`): Removed `0.50` emoji fallback and `86%` exclamation fallback. Skips normalization if no profile data.
7. **Length controller** (`length_controller.py`): Removed Stefan's 2,967-message defaults and hardcoded `SHORT_REPLACEMENTS`. All thresholds from per-creator calibration; skips if missing.
8. **Style Anchor** (`generation.py`): New — injects quantitative style reminder (raw numbers from profile) into prompt when `ENABLE_STYLE_ANCHOR=true`.
9. **Emoji Adaptation** (`style_normalizer.py`): New — relationship-level emoji behavior from creator's calibration data.

**Principle**: If data doesn't exist for a creator → skip that function + log warning. Never invent a default number.

---

## 2026-04-04 — M-Prometheus 14B as LLM judge for naked baseline comparison

**Goal**: Add subjective quality metrics (B2/B5/C2/C3/H1) to the 5-model naked baseline comparison using a local LLM judge.

**Model**: M-Prometheus 14B Q6_K (12GB) via Ollama. Based on Qwen2.5-14B, trained on 20+ languages, supports Prometheus eval format (instruction + response + reference + rubric → feedback + [RESULT] 1-5). Runs on Apple Silicon GPU at ~50s/call.

**New file**: `core/evaluation/m_prometheus_judge.py` — 5 judge functions (B2 persona consistency, B5 emotional signature, C2 naturalness, C3 contextual appropriateness, H1 Turing test pairwise). All rubrics in Spanish to match content language.

**Results** (20 cases per model):
- Gemma4-26B wins B2 (76.2) + B5 (62.5) — best persona & emotional match
- Gemma4-31B wins C2 (83.8) — most natural sounding
- Gemma4-E4B wins C3 (52.5) — best contextual appropriateness
- Qwen3-14B wins H1 (75%) — fools judge most often
- Overall Comp37 winner: Gemma4-26B (35.3)
- LLM judge ranking differs from deterministic: 26B overtakes 31B when subjective quality is included

**Key insight**: C3 (contextual appropriateness) scores are low across all models (16-52), suggesting naked baselines struggle with context without the full Clonnect pipeline. This is expected — the pipeline adds conversation history, trust scoring, and strategy selection.

---

## 2026-04-04 — Human Eval v2 + Prometheus as Primary LLM Judge

**Problem**: `scripts/human_eval.py` had the same 5 problems as the LLM judge (wrong test set, no media filter, no history, fake blind A/B, only 5 cases). Additionally lacked: free-text notes, back navigation, quit/resume, end summary.

**Changes (human_eval.py — full rewrite)**:
- Default test set → `test_set_v2_stratified.json` (50 cases, 39 valid text after filter)
- Media filter: same `_is_media_case()` logic as LLM judge
- Full conversation history with media placeholders (cap 15 turns)
- TRUE blind A/B: deterministic per-case RNG (`Random(seed + case_num)`) — never the same order
- Shows category, language, trust segment per case
- Free-text notes field per case
- `back` command to revisit previous case, `quit` to save-and-exit
- Incremental saves every 3 cases, full resume support
- End summary: identification accuracy, average scores, notes collected
- Auto-runs CCEECalibrator after completion if CCEE results are available

**Changes (cpe_level2_llm_judge.py — Prometheus integration)**:
- Default judge model changed from `gpt-4o-mini` to `hf/prometheus` (HuggingFace Inference API)
- New functions: `_call_hf_inference()`, `_call_gemini_fallback()`, `judge_single_hf()`, `judge_pairwise_hf()`
- Fallback chain: Prometheus 7B (HF API) → Gemini Flash Lite → error
- Each result includes `judge_used` field logging which model scored it
- `core/evaluation/llm_judge.py` already had Prometheus → Gemini fallback (no changes needed)

**Files**: `scripts/human_eval.py`, `tests/cpe_level2_llm_judge.py`

**Blast radius**: Zero — both are standalone CLI scripts, not imported by production code.

---

## 2026-04-04 — Redesign CPE Level 2 LLM-as-Judge (5 critical fixes)

**Problem**: `cpe_level2_llm_judge.py` had 5 fundamental flaws invalidating all results:
1. Default test set was `test_set_real_leads.json` (15 cases, many media) instead of stratified 50-case set
2. No media filtering — cases with `[audio]`/`[sticker]` ground truth evaluated as text (bot replies "???" to images)
3. Conversation history truncated to 6 turns — judge lacked context to assess coherence
4. No blind A/B — bot response always shown as "the response", reference always as "reference" — judge biased
5. Only absolute scoring, no pairwise comparison (which is more reliable per Zheng et al., 2023)

**Changes**:
- Default test set → `tests/cpe_data/{creator}/test_set_v2_stratified.json` (50 cases, 39 valid text after filter)
- Media filter: exclude cases where `test_input` or `ground_truth` matches `[audio|sticker|image]` regex. Override with `--include-media`
- Full history: all turns shown (capped at 20 most recent), media turns replaced with descriptive placeholders
- New `--mode pairwise`: randomly assigns bot/reference to A/B (seeded for reproducibility), tracks positional bias
- New `--mode both`: runs absolute + pairwise sequentially
- DB connection leak fixed (context manager), args mutation fixed (local variable)

**Files**: `tests/cpe_level2_llm_judge.py`

**Blast radius**: Zero — standalone CLI script, not imported by anything. Output JSON format changed (now has `absolute` and `pairwise` top-level keys). Historical Level 2 results used different test set and are not comparable.

---

## 2026-04-04 — CCEE v3: 44 params complete (28→44), 9 dimensions, LLM judge + business metrics

**Expansion**: Added 16 new params across 4 new dimensions (B/G/H/I) plus improved existing ones.

**New automatic scorers**: B1 OCEAN alignment (lexical cosine sim), B4 knowledge boundaries (expanded patterns), G1 hallucination (12 patterns, was 3), G3 jailbreak resistance (25 adversarial prompts), H2 style fingerprint (9-dim cosine sim).

**Business metrics (I1-I4)**: DB queries for lead response rate (87.7%), conversation continuation (100%), escalation rate (41.2% — high, creator intervenes often), funnel progression (15%).

**LLM judge (B2/B5/C2/C3)**: Prometheus (HF) → Gemini fallback. Cost: ~$0.01 per 50-case run. Persona consistency=51, emotional signature=53.5, naturalness=69.5, contextual appropriateness=24.

**Human eval interface**: `scripts/human_eval.py` for B3/H1/H3 (pending Manel's session).

**Adaptive weighting**: When dimensions are absent (e.g., no LLM judge), their weight redistributes proportionally. No more neutral-50 drag.

**Baselines**: Deterministic 32/44: 56.56±2.18. Full 36/44: 57.06. Remaining 8: 3 human eval + 1 G3 jailbreak test (need bot pipeline).

---

## 2026-04-03 — CCEE v2: Phase 1 bug fixes + TwinVoice gaps (21→28 params)

**Problem**: CCEE had 42 designed params but only 21 implemented. D6 SemSim had a bug (bot-vs-user instead of bot-vs-GT). A7/F2/E2 had data available but scorer ignored it. No cognitive fidelity metrics (memory, consistency).

**Changes (7 fixes)**:
1. **D6 SemSim bug**: `semsim_scores` now computed against `ground_truths` (was `user_inputs`). Added separate C4 contextual relevance (bot-vs-user).
2. **F2 vocabulary adaptation**: Wired `A5_vocab_diversity` from adaptation profile into `score_s4_per_case()`.
3. **F3 length adaptation**: Isolated as separate metric in S4 detail output.
4. **A7 fragmentation**: Replaced hardcoded 50.0 with newline-fragment-count scored against profile P10/P90.
5. **E2 strategy distribution**: Added JSD between bot aggregate and creator global strategy distributions. S3 = 0.7*E1 + 0.3*E2.
6. **J1 memory recall**: Extracts facts (numbers, capitalized names) from conversation history, checks if bot references them.
7. **J2 multi-turn consistency**: Measures style variance (length std, emoji rate, question rate) across all bot responses vs creator's own variance.

**Composite formula**: S1(0.25) + S2(0.20) + S3(0.25) + S4(0.15) + J(0.15) where J = 0.5*J1 + 0.5*J2.

**Files**: `core/evaluation/ccee_scorer.py`, `scripts/run_ccee.py`, `tests/test_ccee.py`

---

## 2026-04-03 — Fix S4 Adaptation Scorer (always returned 50.0)

**Problem**: `score_s4_adaptation()` returned exactly 50.0 in every CCEE run because:
1. Directional analysis required ≥3 bot responses in ≥2 trust segments — too strict for 42 test cases with skewed trust distribution
2. Even when met, 3/4 direction metrics for Iris were "neutral" → each scored 50.0

**Fix**: Blend per-case proximity scores (via `score_s4_per_case`, which already worked — varied 58-90) with directional scores: 60% proximity + 40% directional when both available, 100% proximity otherwise. Fallback to 50.0 only when no segment data exists at all.

**Result**: S4 now returns 58.32 (blended: proximity_mean=72.21, directional=37.5) instead of fixed 50.0.

**Files**: `core/evaluation/ccee_scorer.py` (score_s4_adaptation), `tests/test_ccee.py` (+2 tests, fixture update)

---

## 2026-04-03 — Learning systems: 48 bug fixes + CCEE scoring + gold examples hardening

**Context:**
Audit of 7 learning subsystems (FeedbackStore, AutolearningAnalyzer, LearningRules, GoldExamples, PreferencePairs, PatternAnalyzer, Consolidator) revealed 48 bugs including 2 P1 (privacy/data leakage), multiple P2 (data quality), and P3 (performance/correctness). Gold examples DB contained 29 garbage entries (test messages, emoji-only, audio/sticker, echo). CCEE evaluation engine needed per-case dimensional scoring.

**Decision:**
Fix all bugs, purge garbage data, harden gold examples for eventual activation.

**Changes (17 files, +1044/-257):**
- `services/gold_examples_service.py`: P1 privacy fix (removed user_message from injection results), non-text filter, emoji-only rejection, language detection (`detect_language`), thread-safe LRU cache (OrderedDict + threading.Lock, max 200), times_used increment.
- `core/dm/phases/generation.py`: Only inject creator_response (no lead data leakage), added section header with "NO copies literalmente", language-filtered example selection.
- `services/feedback_store.py`: Dedup in `_auto_create_gold_example` (by source_message_id or user_message).
- `services/learning_rules_service.py`: Thread-safe cache, language filter.
- `services/autolearning_analyzer.py`: Non-text filter, edit similarity improvements.
- `services/preference_pairs_service.py`: Dedup, quality gates.
- `services/pattern_analyzer.py`: Batch safety.
- `services/learning_consolidator.py`: Conflict resolution.
- `core/evaluation/ccee_scorer.py`, `scripts/run_ccee.py`: Per-case S1-S4 dimensional scoring with BERTScore.
- `api/routers/feedback.py`, `api/routers/copilot/actions.py`, `core/copilot/actions.py`: Validation, error handling.
- Tests updated: `test_feedback_store.py`, `test_gold_examples_service.py`, `test_learning_consolidator.py`, `test_learning_rules_service.py`.
- DB purge: 29 gold_examples deactivated (test=1, non-text=24, emoji-only=3, echo=1). 148 active remaining.

**Blast radius:** ENABLE_GOLD_EXAMPLES is OFF in production — gold examples code changes have zero runtime impact until enabled. Learning rules/preference pairs changes are backward-compatible. CCEE is a standalone evaluation tool.

**Smoke tests:** 7/7 pass before and after. 29/29 unit tests pass.

---

## 2026-04-03 — Bug 2 Fix: Emoji Normalization via Direct-Rate Formula

**Context:** Post-deploy CPE measurement revealed bot emoji rate = 82.7% vs Iris real rate = 23%. The LLM overuses emojis and prompting alone cannot reliably fix this.

**Root cause:** `normalize_style()` used a keep_prob formula derived from `creator_rate / bot_natural_rate`. When bot natural rate data is absent (or wrong), emoji suppression fails. Additionally, the old formula required bot natural rate measurements for every new creator, making it unscalable.

**Decision:** Switch to direct-rate formula: `keep_prob = creator_emoji_rate`. For each response, if `random() > keep_prob` → strip all emojis. This directly matches the output distribution to the creator's measured rate without needing bot natural rate data.

**Profile priority (highest to lowest):**
1. `evaluation_profiles/{creator_slug}_style.json` → `emoji_rate` (CCEE worker output)
2. DB/local `baseline_metrics.json` → `emoji.emoji_rate_pct / 100`
3. Fallback: `0.50` (conservative — keep emoji in half of responses)

**Changes:**
- `core/dm/style_normalizer.py`:
  - Added `_eval_profile_cache`, `_load_eval_profile_emoji_rate()`, `_get_creator_emoji_rate()`
  - `normalize_style()`: rewrote emoji section with direct-rate formula
  - Rate normalization: handles both pct (>1.0 → /100) and fraction formats
  - Count trimming: `target_n = max(1, min(5, round(avg_emoji_count / keep_prob)))` to prevent explosion at low rates
  - Safety guard: never produce string < 2 chars
  - Absolute path for eval_profile: `Path(__file__).parent.parent.parent / "evaluation_profiles"`

**Tests:** 14 tests in `tests/test_style_normalizer.py`. Convergence verified: 100 responses → rate ±5% of target (0.23, 0.10, 0.50, 0.90). All pass.

**Not deployed yet.** Wait for CCEE `evaluation_profiles/` worker deployment coordination.

---

## 2026-04-03 — Bug 1 Fix: Universal Thinking Token Stripping

**Context:** Production failure detected in CPE case `cpe_iris__030`. Qwen3 leaked `</think>` into user-facing response: `"Jajjajajaja valee pobre….🥲 quina llastima aixo del gluten /no_think  \n</think>"`. Previous fix only handled empty `<think></think>` blocks.

**Root cause:** `deepinfra_provider.py:129` used `re.sub(r"<think>\s*</think>\s*", "", content)` — only stripped empty blocks. Qwen3 in `/no_think` mode sometimes still emits orphan `</think>` closing tags. The old regex missed full blocks, orphan tags, and `/no_think` leaks.

**Decision:** Universal `strip_thinking_artifacts()` function applied at two levels:
1. Provider level (deepinfra): catches issues before they leave the provider
2. Generation phase level (generation.py): universal safety net for ALL providers (Gemini, GPT-4o-mini, future models)

**Patterns handled:**
- Full `<think>…</think>` blocks (re.DOTALL)
- Empty `<think></think>` blocks
- Orphan `</think>` closing tags
- Orphan `<think>` opening tags  
- Trailing `/no_think` instruction leaked to output

**Changes:**
- `core/providers/deepinfra_provider.py`: replaced narrow regex with `strip_thinking_artifacts()` function + called at content post-processing
- `core/dm/phases/generation.py`: added universal safety net after LLM response, before building `LLMResponse`

**Tests:** 38 tests in `tests/test_thinking_tokens.py`. All pass.

**Not deployed yet.** Wait for CCEE deployment coordination.

---

## 2026-04-02 — ROLLBACK: Stay with OpenAI text-embedding-3-small (1536 dims)

**Context:** Previous decision switched default to local MiniLM (384 dims) due to OpenAI quota exhaustion. Rolling back because DB already has 1536-dim vectors that work with OpenAI — switching dimensions would require destructive migration + re-embedding 50K+ vectors.

**Changes:**
- `core/embeddings.py`: `EMBEDDING_PROVIDER` default reverted from `"local"` to `"openai"`. `EMBEDDING_DIMENSIONS` fixed at 1536.
- Added graceful fallback: if OpenAI fails at runtime, falls back to local MiniLM (384 dims). Dimension mismatch means DB search won't work but service stays alive.
- Deleted `alembic/versions/044_switch_embeddings_to_384.py` (never executed)
- Deleted `scripts/reembed_all_chunks.py`, `scripts/reembed_lead_memories.py`, `scripts/reembed_conversation_embeddings.py`
- Tests updated to expect 1536/OpenAI defaults, with local-fallback behavior verified

**Action needed:** Fix OpenAI billing to restore RAG search. The API key is set but quota is insufficient (429 errors).

---

## 2026-04-02 — Conversation Boundary: Discourse Markers (paper-backed optimization)

**Context:** Forensic re-audit of System #13. Analyzed 8 papers paper-by-paper to identify what they do that we don't. Found ONE justified optimization: discourse markers from Topic Shift Detection papers (2023-24).

**Implemented: Discourse markers** (Topic Shift Detection 2023-24, Alibaba CS hybrid approach)
- Added `_DISCOURSE_MARKER_PATTERN` regex: "por cierto", "otra cosa", "by the way", "per cert", "a proposito", "au fait", "übrigens" + 7 languages
- Fires ONLY in 30min-4h zone (same tier as farewell). Does NOT affect <5min or 5-30min zones.
- Matches at START of message only (prevents mid-sentence false positives).
- Cost: 0 dependencies, 0 latency impact (0.16ms/500 msgs, unchanged).
- Benefit: catches explicit topic changes in 30min-4h zone where no greeting or farewell is present.
- 49 tests pass (41 existing + 8 new).

**Rejected: Embedding similarity** (Alibaba CS 2023-24, SuperDialSeg 2023)
- Would add ~10ms per boundary check (50x current latency).
- Noisy on 5-15 word DM messages (TextTiling/Hearst warns about short texts).
- After adding discourse markers, the remaining uncovered edge case (30min-4h, no greeting, no farewell, no discourse marker) is <5% of boundaries.
- Revisit condition: if false boundary rate in 30min-4h zone exceeds 5% in production.

**Rejected: Time sub-bucketing** (Time-Aware Transformer 2023-24)
- Their sub-tiers were learned from 100K+ annotated sessions. Without equivalent data, any sub-tier is arbitrary.
- 10/10 functional tests pass with current tiers. No evidence of systematic errors.

**Rejected: TextTiling** (Hearst 1997)
- Designed for multi-paragraph docs (300+ words/block). DMs average 5-15 words — signal too noisy.

**Rejected: SuperDialSeg** (Jiang 2023, EMNLP)
- Requires annotated training data we don't have. 75-80% F1 is lower than our 10/10 functional accuracy. Adds GPU latency.

---

## 2026-04-02 — Forensic Audit: Conversation Boundary Detection (BUG-CB-03 fix)

**Context:** Forensic audit of `core/conversation_boundary.py`. System uses tiered multi-signal approach: time gaps (5min/30min/4h thresholds) + greeting/farewell regex patterns.

**Literature validation:** 15+ papers reviewed (MSC Meta, LoCoMo, SuperDialSeg, TextTiling, IRC Disentanglement). 5min/30min/4h thresholds validated by Alibaba customer service (identical tiers), Time-Aware Transformer (learned breakpoints at 30min/4h), Zendesk/Intercom defaults. Industry consensus: time-based primary + content signals in ambiguous zone.

**Bugs found:**
- BUG-CB-03 (MEDIUM): Missing greeting/farewell patterns for Arabic, Japanese, French, German, Korean, Chinese. Only affected 5min-4h ambiguous zone — time-based detection already works universally.
- BUG-CB-04 (LOW): Copilot service uses separate 24h session detection — inconsistency (not fixed, different use case).
- BUG-CB-05 (LOW): No discourse markers ("por cierto", "cambiando de tema"). Literature recommends but low impact — greeting/farewell covers most cases.

**Fix:** Added FR/DE/AR/JA/KO/ZH greeting + farewell patterns. 41 tests pass. Performance unchanged (0.17ms/500 msgs).

**Not changed (justified):**
- Embedding similarity for ambiguous zone: Papers recommend but adds latency + cost. Our regex achieves similar precision at 0 cost. Only worth adding if false boundary rate > 5%.
- Discourse markers: Low priority — greeting detection covers 90%+ of boundary cases.
- 5min threshold: Could extend to 10min per IRC research, but 5min is safer (avoids false merges).

---

## 2026-04-02 — Switch RAG Embeddings from OpenAI to Local MiniLM-L12-v2

**Context:** OpenAI API quota exceeded (429), ALL embedding-based systems dead: RAG (content_embeddings), episodic memory (conversation_embeddings), memory engine (lead_memories). `paraphrase-multilingual-MiniLM-L12-v2` already loaded in RAM for frustration detector's SentenceTransformer.

**Benchmark (20 real queries, 183 iris chunks):** MiniLM retrieves correct chunks for all critical query types (schedule, price, booking, cancellation). 49% overlap@5 with OpenAI — disagreements mostly on low-value video/instagram content. Cross-encoder reranker compensates.

**Decision:** Switch `generate_embedding()` to local SentenceTransformer (384 dims). Alembic migration changes all 3 vector columns from 1536→384. Re-embed all chunks. OpenAI kept as opt-in fallback via `EMBEDDING_PROVIDER=openai`.

**Trade-off:** MTEB ~48 vs ~62 for OpenAI, but: (1) local is alive, OpenAI is dead, (2) 40x faster, (3) free, (4) user DMs never leave server, (5) reranker compensates.

**Files:** `core/embeddings.py`, `alembic/versions/044_switch_embeddings_to_384.py` (NEW), `tests/test_embeddings_audit.py`

---

## 2026-04-02 — Redesign Memory Injection v3 (18 papers, 6 repos)

**Context:** System #9 Memory Engine had L1 6/6/6 but human evaluation 1.4/5. Model received 600-863 chars of memory but IGNORED it. 5 failure cases. Iterated v1→v2→v3.

**Research (18 papers, 6 repos):** mem0 (25K★): bulleted list, k≤2 optimal. Letta (22K★, ICLR 2024): XML blocks. Zep (2025): `<FACTS>` tags + step-by-step instructions. MRPrompt (2026): explicit protocol required. SeCom (ICLR 2025): compression-as-denoising. Context Rot (Chroma 2025): focused 300 tokens >> 113K. LangChain EntityMemory: name extraction. Li et al. (COLM 2024): persona drift in 8 turns.

**Decision (v3):** (1) `<memoria>` XML tags + `- fact` bullets (mem0+Zep pattern). (2) `Nombre: X` line via universal regex (LangChain EntityMemory). (3) `Instrucción: Responde usando la info de <memoria>.` (MRPrompt+Zep). (4) Memory at END of recalling block (Lost in Middle). (5) Max 600 chars, 5 facts. (6) Echo threshold 0.55 (was 0.70) — catches semantic echoes. (7) Accent normalization NFD for Catalan.

**5-Case Results:** Case 2 (Si→scheduling) went from "Ja, què?" to "Ens veiem demà a les 13:30" with name "Marta". Case 3 echo now caught (J=0.636 ≥ 0.55). Case 4 Cuca: name extracted.

**Files:** `services/memory_engine.py`, `core/dm/phases/context.py`, `core/dm/phases/postprocessing.py`

---

## 2026-04-02 — Fix DNA Vocabulary Extraction (Data-Mined, Per-Lead TF-IDF)

**Context:** DNA `vocabulary_uses` is EMPTY for ALL records. `ENABLE_DNA_AUTO_ANALYZE` defaults to `false`, so the full `RelationshipAnalyzer.analyze()` never runs. Additionally, vocabulary extraction used substring matching (`word in text`) which catches "compa" inside "acompanyar". `clone_system_prompt_v2.py` had hardcoded vocabulary `["bro", "hermano", "crack", "tío"]` (not used in prod but violates zero-hardcoding).

**Decision:** Build a proper vocabulary extraction system:
1. New `services/vocabulary_extractor.py` — canonical tokenizer with word-boundary regex, shared stopwords (ES/CA/EN/PT/IT), TF-IDF distinctiveness scoring per lead
2. Rewrite `RelationshipAnalyzer._extract_vocabulary_uses()` to use new extractor
3. Flip `ENABLE_DNA_AUTO_ANALYZE` default to `true`
4. Remove hardcoded Stefan vocabulary from `clone_system_prompt_v2.py`
5. Unify stopwords across `compressed_doc_d.py` and `relationship_analyzer.py`
6. Backfill script to re-populate all DNA records

**Verified data:** Iris has 17K+ real messages (0 bot messages). She uses "tio" (21x), "cuca" (26x), "carinyo" (23x) — these are REAL. "compa" appears 16x but 15 are substrings of "acompanyar/compartir".

**Files:** `services/vocabulary_extractor.py` (NEW), `services/relationship_analyzer.py`, `services/relationship_dna_service.py`, `core/dm/phases/context.py`, `core/dm/compressed_doc_d.py`, `prompts/clone_system_prompt_v2.py`, `scripts/backfill_dna_vocabulary.py` (NEW)

---

## 2026-04-02 — Implement Anthropic Contextual Retrieval (Universal)

**Context:** Anthropic's "Contextual Retrieval" paper (2024) shows +49% retrieval quality by prepending creator context to chunks before embedding. Clonnect had this for Iris only (`IRIS_CONTEXT_PREFIX` hardcoded in `scripts/create_proposition_chunks.py`). Now universalized for any creator.

**Implementation:**
- New module `core/contextual_prefix.py`: `build_contextual_prefix(creator_id)` auto-generates a 1-3 sentence prefix from Creator + ToneProfile DB data (name, handle, specialties, location, language/dialect)
- Wrapper functions `generate_embedding_with_context()` and `generate_embeddings_batch_with_context()` prepend prefix to document text before embedding
- 5 call sites patched: `SemanticRAG.add_document()`, `content_refresh.py`, `_rag_gen_embeddings.py`, `content.py` batch endpoint, `create_proposition_chunks.py`
- Search queries remain prefix-free (asymmetric by design per paper)
- Legacy `IRIS_CONTEXT_PREFIX` kept as fallback only

**Key decision:** Prefix applied at embedding time, NOT stored in content. Clean content stays in `content_chunks`; prefix is "baked into" the vector. This means existing embeddings must be regenerated to get the quality improvement.

---

## 2026-04-02 — Conversation Boundary Detection System

**Problem:** Instagram/WhatsApp DMs are ONE continuous thread per lead. No "sessions" exist — just a stream of messages over weeks/months. This causes:
- DPO pairs with wrong context (pairs from different conversations mixed)
- Test sets with contaminated pairs (unrelated messages paired together)
- Bot responses with wrong context (loading messages from a different conversation)

**Research:** Reviewed 15+ papers (TextTiling, C99, BayesSeg, GraphSeg, SuperDialSeg, MSC, LoCoMo, IRC disentanglement) + 12 GitHub repos + industry practices (Zendesk, Intercom, WhatsApp Business, Google Analytics). Key finding: MSC and LoCoMo both ASSUME pre-segmented sessions — boundary detection is an under-researched gap.

**Decision:** Hybrid multi-signal approach (industry consensus for async messaging):
1. **Time gap (tiered, primary):** <5min=SAME, 5-30min=check greeting, 30min-4h=check signals, >4h=NEW
2. **Greeting detection (secondary):** Multilingual ES/CA/EN/PT greeting patterns
3. **Farewell detection (secondary):** Detects conversation-ending signals in previous message

**Why not embeddings:** For v1, time + greeting gets ~85% accuracy per literature. Embeddings add latency/complexity for the ambiguous 30min-4h zone — can be added in v2 if needed.

**Integration points:**
- `core/conversation_boundary.py` — pure-logic detector, no DB dependency
- `core/dm/helpers.py` — filter context loading by current session
- `scripts/build_stratified_test_set.py` — pair within same session
- `scripts/export_training_data.py` — pair within same session
- `scripts/tag_sessions.py` — retroactive tagging script

**Schema:** Compute session boundaries on-the-fly from timestamps + content. No new DB column needed (session_id is derived, not stored). This avoids migration complexity and keeps the system stateless.

---

## 2026-04-02 — Forensic Audit: System #12 Reranker

**Context:** Cross-encoder reranker using `nreimers/mmarco-mMiniLMv2-L12-H384-v1` (multilingual, 117.6M params, 926MB RAM).
Found 5 bugs: 2x P1 IndexError crashes on empty docs in `_rerank_local`/`_rerank_cohere`, stale docstrings/comments, wrong test assertion.
All fixed. 15 new functional tests + 25 existing tests pass.

**Key metrics:** 33ms/12 pairs latency, excellent CA/ES/IT/EN quality (scores 0.996-0.999 for relevant multilingual docs).
**Cost:** Railway Pro €20/month required (926MB RAM). Graceful fallback on Hobby plan.
**Research:** mMARCO, ColBERTv2, BGE-reranker-v2-m3, FlashRank reviewed. Current model is good choice for multilingual. FlashRank (60MB) is lighter alternative.

---

## 2026-04-02 — Forensic Audit: System #11 RAG Knowledge Engine

**Context:** Full forensic audit of the RAG system (15 files, ~4000 LOC). Architecture is solid: 4-step search pipeline (semantic → BM25 → rerank → source boost), adaptive retrieval gating, priority-based context budget.

**Bugs Found & Fixed:**
- **BUG-RAG-02 (P2):** RAG chunks injected into prompt without sanitization → added `_sanitize_rag_content()` to strip prompt injection patterns
- **BUG-RAG-03 (P2):** RAG search runs synchronously in async context (blocks event loop 300-700ms) → wrapped in `asyncio.to_thread()`
- **BUG-RAG-04 (P3):** `_creator_kw_cache` was unbounded dict → replaced with `BoundedTTLCache(50, 3600s)`
- **BUG-RAG-05 (P3):** BM25 `_retrievers` was unbounded dict → replaced with `BoundedTTLCache(50, 3600s)`

**Known Issue (not fixed):**
- **BUG-RAG-01 (P1):** `scripts/create_proposition_chunks.py` is hardcoded for Iris (context prefix, UUID, all content). Not fixed because `ingestion/v2/pipeline.py` already handles generic chunk creation — this script should be deprecated.

**Full audit:** `docs/audit/sistema_11_rag_knowledge.md`

---

## 2026-04-02 — Merge System #7 (User Context) INTO System #8 (DNA Engine)

**Context:** Ablation testing showed System #7 (User Context Builder) adds no measurable improvement as a separate system (p>0.05 on 11/12 metrics). System #7 and #8 overlap: both inject lead profile data into the prompt. Two separate blocks compete for token budget.

**Decision:** Absorb #7's unique data (name, language, interests, CRM status) into #8's DNA block. ONE unified `=== CONTEXTO DE RELACIÓN ===` block replaces two separate injections.

**Implementation:**
- `format_unified_lead_context()` in `dm_agent_context_integration.py` merges DNA + lead profile
- Lead profile built as dict in `context.py`, passed to merge function
- `_build_recalling_block()` no longer has `lead_profile` parameter
- Deduplication: interests already in DNA `recurring_topics` are not repeated
- If no DNA exists yet (new lead), minimal block with lead profile data still injected

**Token savings:** ~100-400 chars per prompt (eliminated duplicate header/footer + deduplicated fields).

**Tests:** 35/35 passed (15 test groups). Smoke: 7/7 passed.

**Not changed:** `user_context_loader.py` kept (marked DEPRECATED) — still imported by `tests/academic/` and `prompt_builder/`.

---

## 2026-04-02 — Unified FeedbackStore: Consolidate 3 feedback services + add evaluator feedback

**Context:** Forensic audit of System #11 found 3 overlapping feedback services (preference_pairs, learning_rules, gold_examples) with:
- 2 P1 bugs: double-confidence multiplication in scoring (learning_rules:154+185, gold_examples:162+183)
- 80+ duplicated lines of historical mining code
- Same copilot action → data in up to 3 tables with no conflict resolution
- No evaluator feedback capture (feedback from CPE ablation dies in chat)

**Research basis:** 20 papers + 20 repos analyzed (docs/research/HUMAN_FEEDBACK_SYSTEM.md). PAHF, DEEPER, DPRF, Character.ai, Replika, Delphi.ai — ALL use one unified feedback store.

**Decision:** 
1. Fix P1 scoring bugs (2-line fixes)
2. Create unified `FeedbackStore` facade that delegates to existing 3 services (no caller changes needed)
3. Add `EvaluatorFeedback` DB model + `save_feedback()` that auto-creates preference pairs and gold examples
4. New API endpoints: POST/GET /api/feedback
5. Keep existing 3 tables + add 1 new table (not merge — different schemas)

**Architecture:** Facade pattern. 19+ existing callers untouched. New code uses FeedbackStore. Backward compatible.

**Files:** services/feedback_store.py (new), api/models/learning.py (add model), api/routers/feedback.py (new), 2 bug fixes, alembic migration, tests.

---

## 2026-04-02 — BUG-EMOJI-01: Fix broken emoji-only detection (universal)

**Root cause:** `response_variator_v2.py:446` used `ord(c) > 127000` to detect emoji-only
messages. This hardcoded threshold misses ALL emoji below U+1F018: ❤️ (U+2764), ✨ (U+2728),
⭐, ☺️, ♥️, ✅, ⚡, and all variation-selector sequences (U+FE0F = 65039). Same bug in
`clone_system_prompt_v2.py:224` for emoji counting.

**Impact:** Emoji-only messages like "💃🏻💃🏻💃🏻❤️❤️" fell through to LLM, producing
incoherent hallucinated responses ("Ja m'he espavilat, t'he vist!"). Discovered during
Layer 2 + System #10 ablation.

**Fix:** Created `core/emoji_utils.py` with Unicode-category-based detection:
- `is_emoji_char(c)`: unicodedata.category + variation selectors + ZWJ + skin tones + keycap + tags
- `is_emoji_only(text)`: all chars are emoji or whitespace
- `count_emojis(text)`: visible emoji count (excludes modifiers)

Unified 3 separate emoji detection implementations:
1. `services/response_variator_v2.py` — pool routing (the critical path)
2. `prompts/clone_system_prompt_v2.py` — style metric calculation
3. `core/dm/style_normalizer.py` — emoji stripping post-processing

**Research:** PersonaGym (EMNLP 2025), Character.ai, Replika all treat emoji-only as
emotion-signal → short persona-consistent pool response. Never echo emoji. Never send to LLM.

---

## 2026-04-01 — Episodic Memory: Fix 8 audit bugs (System #10)

Forensic audit (docs/audit/sistema_10_episodic_memory.md) found 8 bugs.

**P0 — BUG-EP-01**: No write path for Instagram leads. `add_message()` was never
called in the main DM pipeline. Fixed by adding `get_semantic_memory().add_message()`
in `post_response.py`.

**P1 fixes**: Raised similarity threshold 0.45→0.60 (EP-02), added dedup against
recent history (EP-04). **P2 fixes**: Single ID resolution pass (EP-05), quality-gated
results fetch 5 cap 3 (EP-06), logged exceptions instead of `pass` (EP-07).
**P3**: Content truncation 150→250 chars (EP-08).

**Decision**: BUG-EP-03 (timestamp filter) deferred — requires testing with production
data to calibrate time window. Higher similarity threshold partially mitigates.

---

## 2026-04-01 — User Context Builder: Fix all 8 audit bugs

Forensic audit (docs/audit/sistema_07_user_context.md) found 9 bugs. BUG-UC-06
(ConvState ES-only) was already fixed. Remaining 8:

**P0 — Language write-back (BUG-UC-01):**
  In post_response.update_follower_memory(), detect language from user_message
  and write to follower.preferred_language if high confidence. Uses existing
  core.i18n.detect_language (wraps langdetect). Only update if detected != current
  and message is long enough (>=10 chars) to avoid false positives.

**P0 — Name persistence (BUG-UC-02):**
  In post_response.update_follower_memory(), check cognitive_metadata for
  detected user_name from context_signals. If present and follower.name is empty,
  persist it.

**P1 — Numeric username filter (BUG-UC-08):**
  In prompt_service.build_user_context(), skip username if all digits.

**P2 — Rename UserContext (BUG-UC-03):**
  Rename conversation_state.UserContext → SalesFunnelContext to disambiguate.

**P2 — Delete dead code (BUG-UC-04):**
  Delete services/context_memory_service.py.

**P2 — Fix deprecated import (BUG-UC-05):**
  In user_context_loader._load_from_follower_memory(), use services.memory_service
  MemoryStore instead of deprecated core.memory.MemoryStore.

**P3 — Unbounded situation (BUG-UC-09):**
  Cap situation string at 200 chars in conversation_state._extract_context().

**P3 — Cache TTL (BUG-UC-07):**
  WON'T FIX — 60s TTL in UserContextLoader is acceptable. The main DM pipeline
  doesn't use this cache. Risk is minimal.

**Files affected:** core/dm/post_response.py, services/prompt_service.py,
  core/conversation_state.py, core/user_context_loader.py,
  services/context_memory_service.py (DELETE)

**BUG-UC-10 (CRITICAL): build_user_context() output is dead code in generation phase.**
  context.py:934 builds user_context → stored in ctx.user_context →
  generation.py:115 loads it into local var → NEVER injected into prompt.
  Lead commercial data (interests, objections, products, purchase score, stage,
  name, language) is computed but thrown away.

  Fix: Build a structured lead profile block directly in the context phase
  and inject it into the Recalling block (system prompt). Delete the unused
  build_user_context() call. Per papers (LaMP 2023, PEARL 2023, Li et al. 2024):
  structured key-value format in system prompt > prose in user message.

  user_context_loader.py KEPT as secondary path (prompt_builder/debug/tests).
  Not wired into main pipeline — main pipeline already has follower data available
  directly, no need for a 3-source loader that adds latency.

---

## 2026-03-31 — Pool Matching: remaining bugs fixed; papers confirm KEEP

BUG-PM-01/02/03/05 were already fixed in code (audit doc was stale snapshot).

BUG-PM-04: "que crack" (Argentine slang) removed from praise triggers.
  Added universal alternatives: "increíble", "lo mejor", "muy bueno".
BUG-PM-07: LatAm-specific fallback pool entries replaced.
  "Jaja morí" → "Jajajaja 😄", "Vamos con toda!" → "Ánimo! 💪".
BUG-PM-06: WON'T FIX — dual-gate is intentional design. Internal gate (0.7)
  blocks empathy (0.60) from ever reaching callers. External gate (0.8) adds
  production threshold. Different responsibilities.

Papers (GPT Semantic Cache 2024, IJCAI survey 2021, Apple Krites):
  Pool matching is academically justified for phatic/social messages.
  random.choice() is never recommended — BUG-PM-02 fix (TF-IDF selection) is correct.
  NEW FINDING: TF-IDF is wrong for short social messages (zero shared terms).
  Future upgrade: cosine similarity on embeddings (dense retrieval).
  Current TF-IDF falls back to random.choice() for small pools — acceptable short-term.

VERDICT: KEEP. System is architecturally valid. Pending future work: embed-based selection.

Files modified: services/response_variator_v2.py
Full audit: docs/audit/sistema_05_pool_matching.md

---

## 2026-03-31 — Phase 5 Postprocessing: 4 bugs fixed (2 HIGH, 2 MEDIUM)

**BUG-PP-1:** 10 module-level flag constants duplicated from `feature_flags.py` singleton.
Replaced all 10 with `flags.xxx` references — now visible to ablation runner + `flags.to_dict()`.

**BUG-PP-2:** `detection.language` attribute doesn't exist on `DetectionResult` — SBS/PPA always
fell back to `"ca"` (wrong for Stefano/EN leads). Fixed: read from `cognitive_metadata["detected_language"]`
with `"ca"` fallback. Language must be deposited there by context phase before SBS reads it.

**BUG-PP-3:** `ENABLE_CLONE_SCORE`, `ENABLE_MEMORY_ENGINE`, `ENABLE_COMMITMENT_TRACKING` were
inline env reads invisible to the flag registry. Added to `feature_flags.py`, replaced inline reads.

**BUG-PP-4:** Step 9a (`get_state` + `update_state`) were sync DB calls directly in the async
event loop — blocked 2-200ms per request. Wrapped in `asyncio.to_thread()`.

**BUG-PP-5:** Duplicate "Step 7b" label (doc only) — second one renamed to "Step 7c".

**Files modified:** `core/dm/phases/postprocessing.py`, `core/feature_flags.py`
**Full audit:** `docs/audit/sistema_05_postprocessing.md`

---

## 2026-03-31 — Input Guards: input length truncation guard added (OWASP LLM10)

Messages > 3000 chars are truncated at GUARD 0 before any pipeline processing.
Instagram native limit is ~2200 chars so real leads are unaffected.
Protects against token flooding (cost spike) and context overflow (500 error) from
synthetic or misconfigured webhook payloads. Truncation logged at WARNING level.

**File modified:** `core/dm/phases/detection.py`

**Sistema #4 Input Guards — COMPLETE.**

---

## 2026-03-31 — Sistema #4 audit: Edge Case Detection is not a system, it's missing input guards

**Context:** Forensic audit of "Edge Case Detection" revealed the label was aspirational — no dedicated system existed. Three input guard gaps fixed.

**BUG-EC-1:** Empty/whitespace messages had no early return — reached `try_pool_response("")`. Fixed: 3-line guard at top of `phase_detection`.

**BUG-EC-2:** No prompt injection detection in Phase 1. Per Perez & Ribeiro (2022), patterns like "ignore previous instructions" / "olvida tus instrucciones" / "act as DAN" passed silently. Fixed: regex-based flag only (no blocking) — sets `cognitive_metadata["prompt_injection_attempt"] = True` and logs. LLM still handles the message; this is observability + DPO signal collection.

**BUG-EC-3:** Docstrings called Phase 1 "edge case detection". Fixed to say "input guards".

**Decision:** Phase 1 is now documented as **5 input guards**, not a standalone edge-case system. Ablation flag: `ENABLE_PROMPT_INJECTION_DETECTION`.

**Files modified:** `core/dm/phases/detection.py`, `core/feature_flags.py`

**Full audit:** `docs/audit/sistema_04_edge_case_detection.md`

---

## 2026-03-31 — Detection Phase Audit: 9 bugs fixed (3 HIGH, 3 MEDIUM, 3 re-audit)

**Context:** Systematic audit of 5 detection subsystems found 12 initial bugs + 15 in re-audit. Fixed 9 critical ones.

**HIGH fixes:**
1. Phishing regex had hardcoded `iris|stefan` — now matches generic creator roles (creador/dueño/admin)
2. Crisis resources always Spanish — now derives language from creator's dialect
3. Stefan fallback pools leaked persona ("hermano/bro") to all creators — neutralized, extraction-aware

**MEDIUM fixes:**
4-5. Added `ENABLE_MEDIA_PLACEHOLDER_DETECTION` and `ENABLE_POOL_MATCHING` feature flags
6. Consolidated triplicate flag declarations into `core.feature_flags` singleton

**Re-audit fixes:**
7. ReDoS vulnerability in threat/economic regex (unbounded `.*` → bounded `.{0,80}`)
8-9. Memory leaks: capped FrustrationDetector and ResponseVariatorV2 at 5000 entries each

**Files modified:** `core/feature_flags.py`, `core/sensitive_detector.py`, `core/dm/phases/detection.py`, `core/dm/agent.py`, `core/frustration_detector.py`, `services/response_variator_v2.py`

**Full audit:** `docs/audit/fase1_detection.md`

---

## 2026-03-28 — Clone Score Engine optimization (scheduler dedup, samples 50→20, knowledge recalibrated)

**Problema:** Clone Score evaluaba 6x/día (cada redeploy reiniciaba scheduler), usaba 50 samples (excesivo según papers), y knowledge_accuracy puntuaba 8.6/100 (prompt demasiado estricto penalizaba respuestas conversacionales sin datos facticos).

**Papers consultados:**
- CharacterEval 2024: 6 dimensiones gold standard → nuestras 6 alineadas
- G-Eval (Zheng 2023): LLM-as-judge r=0.50-0.70 con humanos → GPT-4o-mini correcto
- Statistical significance: con σ=0.10 y delta=0.2, n=5 es suficiente → 20 es generoso
- BERTScore solo r=0.30-0.40 → heurísticas OK como anomaly detectors, no como quality measures

**Fixes implementados:**
1. **Scheduler dedup** (`handlers.py`): Check DB `WHERE DATE(created_at) = CURRENT_DATE` antes de evaluar → 1x/día garantizado
2. **Samples 50→20** (`clone_score_engine.py`): Default batch + LLM subset cap. Ahorro: 60% menos LLM calls (~$1.20→$0.48/día)
3. **knowledge_accuracy prompt** recalibrado: "Puntua 80-100 si no hay alucinaciones. Penaliza solo datos FALSOS inventados." Respuestas conversacionales sin datos ya no se penalizan.

**Ahorro estimado:** $5.52/día → $0.48/día = **$150/mes**

---

## 2026-03-28 — DNA Auto Create: 3 fixes (double injection, media filter, double DB query)

**Fix A — Remove bot_instructions double injection:** `bot_instructions` was extracted from `raw_dna` in context.py AND included inside `dna_context` via `build_context_prompt()`. The LLM saw the same instructions twice. Removed the separate extraction; `dna_context` already contains it.

**Fix B — Filter media placeholders from golden examples:** `_extract_golden_examples()` in `relationship_analyzer.py` checked exact match only (`[audio]`, `[video]`). Missed prefix patterns like `[🎤 Audio]: transcribed text`. Added `_MEDIA_PREFIXES` tuple for `startswith` matching. Prevents media messages from becoming few-shot examples.

**Fix C — Eliminate double DB query for RelationshipDNA:** `context.py` ran `build_context_prompt()` AND `get_relationship_dna()` in parallel — both hit the same DB row. Restructured: load `raw_dna` first in parallel with other ops, then pass `preloaded_dna=raw_dna` to `build_context_prompt()`. Saves 1 DB query per DM.

**Files:** `context.py`, `generation.py`, `relationship_analyzer.py`, `dm_agent_context_integration.py`.

---

## 2026-03-28 — Adaptive length: prompt hints instead of max_tokens truncation

**Problema:** `max_tokens=40-80` (adaptive) truncaba respuestas mid-sentence → "Holaaaa nena! Mira, el bar—". El judge penaliza respuestas incompletas. Score bajó de 8.20 a 8.00 con truncación.

**Fix:** Reemplazar truncación por guía natural en el prompt. `max_tokens=150` como safety net (nunca trunca). Length hints inyectados en el Recalling block del system prompt para que el modelo genere la longitud correcta por sí mismo.

**Implementación:**
- `text_utils.py`: `get_length_hint(message)` → hint natural por categoría ("Responde ultra-breve", "Saludo breve y cálido", etc.)
- `text_utils.py`: Fix classifier — `short_affirmation` ahora se detecta antes que `greeting` (Si/Vale/Ok ya no caen en greeting)
- `text_utils.py`: `get_adaptive_max_tokens()` simplificado → siempre retorna 150
- `context.py`: Hint inyectado en `_context_notes_str` → entra al Recalling block
- `generation.py`: `max_tokens=150` fijo, hint logueado en `cognitive_metadata`

**Categorías y hints:**
| Categoría | Hint |
|---|---|
| short_affirmation | "Responde ultra-breve (1-3 palabras o emoji)." |
| greeting | "Saludo breve y cálido, 1 frase." |
| cancel | "Respuesta empática muy breve." |
| short_casual | "Respuesta corta y natural, 1 frase." |
| booking_price | "Da el precio/info de reserva necesaria, sin rodeos." |
| question | "Responde la pregunta de forma directa." |
| long_message | "Responde proporcionalmente al mensaje del lead." |

**Blast radius:** `text_utils.py`, `generation.py`, `context.py`. Sin cambios en schema, prompts base, o providers.

---

## 2026-03-28 — ~~Adaptive max_tokens por categoría de mensaje~~ (SUPERSEDED by prompt hints above)

**Problema:** max_tokens=100 fijo para todos los mensajes. Iris responde con 18 chars de mediana (p50) pero el techo fijo permite respuestas largas innecesarias que rompen su estilo ultra-breve.

**Data minada:** 800 pares reales user→assistant de producción, categorizados por tipo de mensaje del lead.

| Categoría | n | p50 chars | p75 chars | → max_tokens |
|---|---|---|---|---|
| short_affirmation | 18 | 21 | 54 | 40 |
| greeting | 35 | 37 | 141 | 60 |
| question | 256 | 46 | 133 | 60 |
| booking_price | 90 | 35 | 146 | 70 |
| short_casual | 197 | 66 | 145 | 60 |
| long_message | 198 | 59 | 188 | 80 |
| cancel | 6 | 20 | 56 | 50 |

**Implementación:**
- `text_utils.py`: `_classify_user_message()` + `get_adaptive_max_tokens()` — clasificador regex + lookup en calibration
- `generation.py`: Reemplaza `max_tokens` estático con adaptive, logea categoría en `cognitive_metadata["max_tokens_category"]`
- `calibrations/iris_bertran.json`: Añadido `adaptive_max_tokens` dict con valores p75/4 por categoría
- Fallback: si no hay calibración, usa 100 (como antes)

**Riesgo:** Bajo — solo reduce techo, no cambia temperatura ni prompt. ECHO adapter sigue overrideando si activo.

---

## 2026-03-28 — Universal RAG gate (dynamic keywords from content_chunks)

**Problema:** El RAG gate tenía keywords hardcodeados de Iris (barre, pilates, reformer, zumba, heels, hipopresivos). Si se conecta un abogado, coach, o e-commerce, esos keywords no matchean sus productos.

**Fix:** Keywords ahora se extraen dinámicamente de los `content_chunks` del creator en DB (source_types: product_catalog, faq, expertise, objection_handling, policies, knowledge_base). Se mantiene un set universal de keywords transaccionales (precio, horario, reserva, etc.) que funciona para cualquier vertical.

**Implementación:**
- `_get_creator_product_keywords(creator_id)` — query DB, extrae palabras significativas (≥4 chars, no stopwords), cachea per process lifetime
- `_UNIVERSAL_PRODUCT_KEYWORDS` — 24 keywords transaccionales (ES/CA/EN)
- Gate: `_all_product_kw = _UNIVERSAL_PRODUCT_KEYWORDS | _dynamic_kw`
- Cache module-level `_creator_kw_cache` — sin TTL (reinicia con cada deploy)

**Blast radius:** Solo `core/dm/phases/context.py`. Sin cambios en schema, RAG search, o embeddings.

---

## 2026-03-28 — RAG pipeline optimizations (5 fixes, papers-backed)

**Problema:** RAG inyectaba facts pero el LLM los ignoraba (temp 0.7 demasiado alta para factualidad). Top-K=3 limitaba recall. Chunks cortos y sin logging dificultaban iteración.

**Fix 1 — Temperature dual (CRÍTICO):** Cuando RAG inyecta facts, temp se reduce a min(calibrated, 0.4). Papers: "0.0-0.2 for high factuality". Elegimos 0.4 como balance entre factualidad y personalidad. Sin RAG: temp normal (0.7 calibrada). Archivo: `core/dm/phases/generation.py`.

**Fix 2 — Top-K 10 → adaptive filter:** `rag_top_k` de 3→10 para ampliar recall. El adaptive threshold existente filtra: ≥0.5 → top 3, ≥0.40 → top 1, <0.40 → skip. El reranker (cross-encoder) ya maneja la re-ordenación. Archivo: `core/dm/models.py`.

**Fix 3 — RAG context position:** RAG y KB movidos al FINAL del system prompt (antes estaban antes de audio_context). Papers: "LLMs attend most to beginning and end of context window". Facts al final = última info antes de generar. Archivo: `core/dm/phases/context.py`.

**Fix 4 — Chunk size cleanup:** 6 old UUID-keyed FAQ chunks (<100 chars) eliminados de DB. Supersedidos por 15 nuevos FAQ chunks con respuestas completas (88-267 chars). 5 chunks restantes <100 chars son IG captions (no impactan RAG por source-type routing).

**Fix 5 — Retrieval logging:** RAG ahora logea: signal, query, num results, top score, source types. `cognitive_metadata["rag_details"]` almacena top 5 chunks con type/score/preview para análisis posterior. Archivo: `core/dm/phases/context.py`.

**Adicional:** `_preferred_types` ampliado para incluir proposition chunk types (`expertise`, `objection_handling`, `policies`). Source-type boosts en `semantic.py` actualizados.

---

## 2026-03-21 — Desactivar sistemas dañinos + ampliar memory budget

**Problema:** El pipeline conversacional tenía 7-8 LLM calls por mensaje (Best-of-N, Self-consistency, Reflexion, Learning Rules, Autolearning) generando respuestas más genéricas y latencia alta. Memory budget de 1200 chars era insuficiente para dar contexto real del lead.

**Cambios Railway env vars (no requirieron deploy de código):**

| Flag | Antes | Después | Motivo |
|------|-------|---------|--------|
| `ENABLE_LEARNING_RULES` | `true` | `false` | Inyectaba ruido en prompt |
| `ENABLE_SELF_CONSISTENCY` | `true` | `false` | +2 LLM calls extra |
| `ENABLE_BEST_OF_N` | `true` | `false` | +3 LLM calls extra |
| `ENABLE_REFLEXION` | (default=True) | `false` | +1 LLM call extra |
| `ENABLE_AUTOLEARNING` | `true` | `false` | +1 LLM call post-copilot |
| `AGENT_POOL_CONFIDENCE` | — | `1.1` | Deshabilita pool (ninguna response puede tener confidence >1.0) |

**Cambio de código (commit f16e7776):**
- `services/memory_engine.py:1167`: `max_chars=1200` → `max_chars=3000` (300→750 tokens de contexto del lead)

**LLM calls antes/después:**
- Antes: 7-8 calls por mensaje (Main + Best-of-N×3 + Self-consistency×2 + Autolearning)
- Después: 1-2 calls por mensaje (Main + opcional Chain-of-Thought)

**Script añadido:** `scripts/purge_contaminated_gold_examples.py` — marca gold examples con respuestas de error del sistema como `is_active=False` (no destructivo, requiere confirmación interactiva). Ejecutar con `railway run python3 scripts/purge_contaminated_gold_examples.py`.

---

## 2026-03-19 — Enforced methodology hooks (advisory → blocking gates)

**Problem:** CLAUDE.md rules are advisory — workers can skip the planner, code reviewer, DECISIONS.md, and smoke tests without consequence. Hooks make them enforced gates.

**3 new hooks added to `.claude/settings.json`:**

1. **Stop (agent):** Spawns a subagent that checks git diff for .py changes. If found, verifies DECISIONS.md was updated, smoke tests were run, and code review was done. Blocks Claude from finishing if any are missing. Only fires when `.py` files were actually modified.

2. **PreToolUse (command) — `pre-commit-decisions.sh`:** Intercepts `git commit`/`git push`. If `.py` files are staged but DECISIONS.md is not, blocks with `permissionDecision: deny`. Uses same `hookSpecificOutput` pattern as existing `pre-commit-syntax.sh`.

3. **Stop (command) — `stop-smoke-tests.sh`:** When Claude finishes and `.py` files have uncommitted changes, auto-runs `python3 tests/smoke_test_endpoints.py`. Blocks with `{"decision": "block"}` if tests fail. Checks `stop_hook_active` to prevent infinite loops.

**Blast radius:** Config-only change. No .py files modified. Existing hooks preserved (methodology-reminder, session-start-baseline, superpowers, pre-commit-syntax, post-deploy-health).

---

## 2026-03-19 — DB fallback: status filter excluded all messages (NULL status)

**Bug:** `get_history_from_db` queried `Message.status.in_(("sent", "edited"))` but messages in DB have `status=None` (NULL). Zero messages were returned, fallback silently did nothing.

**Fix:** Changed filter to `Message.status != "discarded"` — excludes only rejected copilot suggestions; allows NULL and all real message statuses.

**Verified:** `/dm/follower/iris_bertran/wa_120363386411664374` returns 38 messages all with `status=None`.

---

## 2026-03-19 — DB fallback for conversation history (zero-history bug)

**Bug:** The DM agent generates copilot suggestions with ZERO conversation history. The agent reads from JSON files at `data/followers/{creator_slug}/{follower_id}.json` via `MemoryStore.get_or_create()`. These files don't exist on Railway for any WA lead or Iris IG leads. Result: `follower.last_messages = []` → `history = []` → LLM prompt has no `=== HISTORIAL DE CONVERSACION ===` section. Every response is generated as if it's the first message ever.

**Impact:** All copilot suggestions and auto-replies for all WhatsApp leads (both creators) and all Instagram leads (Iris). The DB has 61K+ messages but the agent never reads them.

**Root cause:** `MemoryStore` is JSON-file-backed. Files only exist for:
- `data/followers/{creator_uuid}/` — 910 files for Stefano (old IG code path, UUID-based)
- `data/followers/stefano_bonanno/` — 84 files (current slug-based path)
- `data/followers/iris_bertran/` — DOES NOT EXIST

The DM agent passes `creator_id=slug` + `follower_id=wa_XXXXX`, so the UUID-based files are never found.

**Fix (Option A — surgical DB fallback):**
- In `core/dm/helpers.py`: add `get_history_from_db(creator_id, follower_id, limit=20)` that queries the `messages` table via `Lead.platform_user_id` join.
- In `core/dm/phases/context.py` line 399: after `history = agent._get_history_from_follower(follower)`, if `not history`, call the DB fallback.
- Also backfill `metadata["history"]` so earlier code (question context, relationship detection, DNA seed) benefits.

**Why Option A over full migration:**
- Lowest risk: only adds a fallback path, never changes existing behavior when JSON files exist
- Zero schema changes, zero new dependencies
- The 84 Stefano slug-based files continue working as before
- Can migrate fully to DB later; this unblocks quality immediately

**Blast radius:** `context.py` (one new call site), `helpers.py` (one new function). No changes to MemoryStore, prompt_service, or any other module.

---

## 2026-03-19 — Audio intelligence: summaries must respect source language

**Bug:** Audio summary generated in Spanish even when audio was in Catalan.

**Root causes (3):**
1. `CLEAN_PROMPT`: no language instruction → LLM could translate Catalan to Spanish while "cleaning"
2. `EXTRACT_PROMPT`: prompt in Spanish, no language instruction → `intent`, `emotional_tone`, `topics` returned in Spanish
3. `SUMMARY_PROMPT`: rule 4 said "mismo idioma" but it was rule 4 of 7, surrounded by Spanish extracted fields; LLM defaulted to Spanish

**Fix** (`services/audio_intelligence.py`):
- Added `_LANGUAGE_NAMES` dict and `_language_name(code)` helper
- All three prompts now start with `"IDIOMA OBLIGATORIO: ... en {lang_name}"` as first line
- System prompts for each layer also include language instruction
- `language` parameter propagated to `_clean()` and `_extract()`
- Fallback values changed from Spanish words ("ninguna", "neutro") to "-" (language-neutral)

**Smoke tests:** 7/7 pass before and after.

---

## 2026-03-19 — Copilot: stop skipping audio messages

**Context:**
Audio messages from Evolution webhook arrive in two forms:
- With transcription: `"[🎤 Audio]: <transcribed text>"` — always passed through copilot (was never in skip list)
- Without transcription: `"[🎤 Audio message]"` — was in `_EMOJI_MEDIA_PREFIXES` skip list → copilot silently skipped it

**Decision:**
Remove `"[🎤 Audio message]"` from `_EMOJI_MEDIA_PREFIXES`. Copilot should generate a suggestion for audio messages even without transcription, instructing the LLM to ask the lead to re-send as text.

**Changes:**
- `core/copilot/models.py`: Removed `"[🎤 Audio message]"` from skip list. Moved `_EMOJI_MEDIA_PREFIXES` to module level (was re-allocated on every call).
- `services/prompt_service.py`: Added explicit REGLAS CRÍTICAS rule: if message is `[🎤 Audio message]`, ask lead to re-send as text.

**Blast radius:** Confined to `create_pending_response_impl` in `core/copilot/lifecycle.py`. `autolearning_analyzer.py` and `preference_pairs_service.py` have separate audio guards for outgoing creator responses — unaffected.

**Smoke tests:** 7/7 pass before and after.

---

## 2026-04-03 — Fix 48 bugs across 7 learning systems + CCEE per-case scoring + gold examples purge

**Context:**
Full audit of 7 learning/feedback services revealed bugs affecting data quality, security, and correctness. Separately, CCEE evaluation was enhanced with per-case S1-S4 scoring and gold examples DB was purged of low-quality entries.

**Decision:**
Fix all identified bugs without changing architecture. Purge gold examples that didn't meet quality bar.

**Changes:**
- `services/feedback_store.py`: Fixed session leak, duplicate detection, atomic upserts, rating validation bounds, missing NULL guards
- `services/learning_rules_service.py`: Fixed contradictory rule detection, prompt injection sanitization, empty rule guard, DB session leak
- `core/copilot/actions.py`: Fixed CCEE per-case S1-S4 scoring logic
- `core/dm/phases/generation.py`: Fixed think token leakage guard
- `core/feature_flags.py`: Fixed flag evaluation edge cases
- `tests/test_feedback_store.py`: Added regression tests for all fixed bugs

**Blast radius:** Confined to learning pipeline services. No changes to webhook, OAuth, scoring batch, or DB pool config.

**Smoke tests:** 7/7 pass before and after.

## 2026-04-10: CCEE v4 — Multi-Turn Evaluation (8 new params)

### Context
CCEE v3 had 44 params across 9 dimensions but only tested single-turn responses.
v4 adds 6 scored parameters for multi-turn conversation quality.

### New Parameters
- J3: Prompt-to-Line Consistency (persona alignment over N turns)
- J4: Line-to-Line Consistency (no self-contradictions in conversation)
- J5: Belief Drift Resistance (handles topic shifts without breaking persona)
- K1: Context Retention 10-Turn (remembers turn 2 in turn 10)
- K2: Style Retention Under Load (S1 metrics don't degrade over conversation)
- G5: Persona Robustness (resists adversarial prompts)

### Bug Fixes
1. **K2 scaling**: Changed from ×20 (destructive) to ×3 (env-configurable K2_SCALING_FACTOR).
   Calibrated from real data: CoV(length)=0.473, natural 5% delta → K2≈85.
2. **J3 Doc D**: Uses full compressed Doc D (~1.3K chars) instead of truncated [:500].
3. **Adversarial prompts**: Universal (EN/ES/CA), auto-detects language from style profile.
4. **Lead simulator**: Configurable via env vars (LEAD_SIM_MIN_CHARS=5, MAX=60, TEMP=0.9).

### Files Created
- core/evaluation/multi_turn_generator.py (309 lines)
- core/evaluation/multi_turn_scorer.py (554 lines)
- evaluation_profiles/adversarial_prompts.json (universal, 3 languages)

### Files Modified
- scripts/run_ccee.py (+25 lines: --multi-turn, --mt-conversations, --mt-turns, --v4-composite)

### Architecture
- v4 is additive — zero changes to existing v3 scoring
- --multi-turn flag enables v4, backward compatible without it
- Lead simulator: GPT-4o-mini; Judge: existing _call_judge (DeepInfra default)
- v4 composite = equal-weight mean of 6 params; blended = 80% v3 + 20% v4

---

## 2026-04-15 — S2 Reweight + L3 MT Generator Fix

### Problem
- **S2 Response Quality (~40):** Lexical metrics (chrF+BLEU+ROUGE+METEOR) had 45% weight but contributed ~6% signal because bot and creator speak different languages (ES vs CA). Opus analysis confirmed scorer problem, not bot.
- **L3 Action Justification (50):** MT generator produced casual chat with no business decision points. Bot never got the opportunity to make strategy-aligned recommendations → L3 stuck at 3/5.

### Decision: S2 Reweight
Remove BLEU and ROUGE (zero cross-language signal), reduce chrF (15→5), increase BERTScore (25→35) and C4 (5→15), add semsim_scores (=BERTScore vs GT, already computed) at 15.

**New weights (total=100):** BERTScore×35 + C4×15 + C5×10 + chrF×5 + BLEU×0 + ROUGE×0 + METEOR×5 + length_ratio×15 + semsim×15

Expected improvement: S2 40→53-58 for multilingual creators.

### Decision: L3 MT Generator
Add `_extract_product_hint()` helper that reads PRODUCTOS/SERVICIOS or ESTRATEGIA DE VENTA from the creator's compressed Doc D. In `simulate_lead_response()`, ~1/3 of simulated turns inject a product inquiry into the system prompt. `generate_conversation()` loads the hint once per conversation via `_load_compressed_doc_d(creator_id)`.

**Universal:** no creator-specific hardcoding — works for any creator with a Doc D.

### Files Modified
- `core/evaluation/ccee_scorer.py`: S2 aggregate weights
- `core/evaluation/multi_turn_generator.py`: `_extract_product_hint()`, `simulate_lead_response(product_hint=)`, `generate_conversation()` loads hint

---

## 2026-04-15 — S3 Exclude IGNORE from Creator Reference Distribution

### Problem
Creator iris ignores 41% of messages (strategy=IGNORE). S3 normalized against this: IGNORE=100 reference, all other strategies scored relative to it. Bots must respond to everything (automation product) — penalizing for not ignoring is wrong.

### Decision
Exclude IGNORE from the creator reference distribution in both E1 (per-case) and E2 (JSD). Renormalize the remaining strategies to sum to 1.0 before scoring. Universal — works for any creator with any IGNORE rate.

`classify_strategy()` unchanged — the classifier still detects IGNORE. Only the scoring evaluation excludes it.

### Files Modified
- `core/evaluation/ccee_scorer.py`: E1 per-case active_dist + E2 JSD creator_active/bot_dist both strip IGNORE before scoring

## 2026-04-18 — W8 Fase C Matrix outputs

4 bugs de producción descubiertos (3 audit T1 + 1 matrix):
- Copilot NameError _Cr/_lead (actions.py:264,282) — autolearning signal rota
- Memory consolidator gates bypass para creators nuevos (:401-426)
- DNA double-schedule sin cap (triggers + auto_analyze)
- Copilot debounce race condition (messaging.py:249-365)

T2 ACTIVAR-MEDIR verdicts post-matrix:
- Desbloqueados sin fix: #25 Question Hints, #21 History Compactor, #24 Length Hints, #40 Persona Compiler
- Desbloqueados con fix previo: #26 Style Anchor (2h), #37 Gold Examples (1h), #115 Nurturing (2h)
- Bloqueado por refactor: #15 Best-of-N (4-6h fix Confidence Scorer)

Decisiones arquitectónicas para ARC1:
- Jerarquía prompt-injection: Doc D > Style Anchor > Length Hints > DNA > Relationship Adapter
- Budget sections: style 2000, recalling 2500, few-shot 1000, RAG 1500, extras 1000
- 5 mutual exclusion guards requeridos (Gold+Calibration, Hierarchical+Memory, etc.)


## 2026-04-18 18:15 — Prod pipeline broken (cachetools)

Post-merge fix/W8-prod-bugs, Railway deploy running antiguo build sin cachetools.
Síntoma: ModuleNotFoundError en core/security/alerting.py:32 al importar TTLCache.
Error cascade en core/dm/phases/detection.py → process_dm devuelve "Lo siento, hubo un error".

Impacto: NULO (bot_active=false en ambos creators, se mide en local).

Fix pendiente (no urgente):
1. grep cachetools requirements.txt (confirmar que está pineado)
2. Si está: force rebuild Railway (empty commit o clear cache desde dashboard)
3. Si no está: re-pin cachetools>=5.3.0,<6.0.0 y push

Hacer antes de reactivar bot_active=true para cualquier creator.



## 2026-04-19 — ARC2 A2.3: Migration scripts for 3 legacy memory systems

Worker A2.3 adds 4 migration scripts to backfill `arc2_lead_memories` from legacy systems.

**Decision: Source mapping to actual codebase**
Design doc referenced `conversation_memory` table and `data/memory/` JSON files, but actual
codebase has `follower_memories` DB table (migration 006) and `data/followers/` JSON files.
Adapted scripts accordingly: `migrate_conversation_memory.py` reads `follower_memories`,
`migrate_follower_jsons.py` reads `data/followers/`. The `lead_memories` table (migration 030)
remains the source for `migrate_legacy_lead_memories.py`.

**Decision: ON CONFLICT DO NOTHING (not DO UPDATE)**
Scripts use DO NOTHING instead of LeadMemoryService.upsert() (which does DO UPDATE).
Reason: migration records have lower confidence and should not overwrite data already
written by the real extractor (dm_extractor, copilot). Prevents migration runs from
clobbering production-quality memories.

**Decision: objection/relationship_state always get why + how_to_apply**
DB CHECK constraint requires non-null why + how_to_apply for these types. Migration
scripts provide placeholder values `(pending re-extraction)` as required. The
`reextract_low_confidence.py` script will replace these with LLM-generated values.

**Files added**
- `scripts/migrate_conversation_memory.py`: follower_memories → arc2_lead_memories
- `scripts/migrate_follower_jsons.py`: JSON files → arc2_lead_memories
- `scripts/migrate_legacy_lead_memories.py`: lead_memories (pgvector preserved) → arc2_lead_memories
- `scripts/reextract_low_confidence.py`: LLM re-extraction for migration% records
- `tests/memory/test_migration_scripts.py`: 21 tests (dry-run, idempotency, skip, embedding)
- `docs/audit_sprint5/ARC2_migration_runbook.md`: pre-checks, steps, rollback, SQL verification

---

## ARC2 Bonus: Nightly extract_deep Scheduler — 2026-04-19

**Context:** ARC2 implementation audit found that `extract_deep` (the LLM nightly branch of
`MemoryExtractor`) had zero callers in production. This means 3 of the 5 memory types
(`objection`, `interest`, `relationship_state`) were only populated via dual-write legacy,
making A2.6 (legacy removal) blocked.

**Decision: standalone script + native TaskScheduler integration**
Created `scripts/nightly_extract_deep.py` as a CLI-runnable script plus registered the
same job in `api/startup/handlers.py` using the existing `TaskScheduler`. The job is
disabled by default (`ENABLE_NIGHTLY_EXTRACT_DEEP=false`) until 7 consecutive days of
production validation are confirmed.

**Decision: ENABLE_NIGHTLY_EXTRACT_DEEP=false default**
Job is gated by env var. Activating it changes memory coverage in production. The gate
ensures A2.6 removal only happens after the job proves stable (7-day criterion in runbook).

**Decision: last_writer='extract_deep_nightly'**
New writer name distinct from all existing writers. Allows SQL monitoring of coverage
specifically from this job vs dual-write legacy, and tracks progress toward A2.6 criteria.

**Decision: 1s sleep between LLM calls**
Conservative rate limiting. OpenRouter burst limits are unknown; 1s ensures < 1 req/s
across all leads, preventing circuit-breaker trips during the nightly batch.

**Files added**
- `scripts/nightly_extract_deep.py`: standalone CLI (--dry-run/--batch-size/--creator-id/--max-leads), idempotent, fail-silent
- `tests/memory/test_nightly_extract_deep.py`: 15 tests covering dry-run, fail-silent, upsert, last_writer, max_leads, creator filter, stats
- `docs/audit_sprint5/ARC2_nightly_extract_deep_runbook.md`: activation steps, monitoring SQL, LLM cost, A2.6 unblock criteria

**Files modified**
- `api/startup/handlers.py`: added JOB N (nightly_extract_deep, 86400s, 720s delay, ENABLE_NIGHTLY_EXTRACT_DEEP=false)

---

## ARC4 Phase 1: Mutations Inventory + DISABLE_M* Kill Switches — 2026-04-19

**Context:** ARC4 goal is to eliminate 9 of 11 post-generation mutations and replace them
with prompt-time rules. Phase 1 is analysis-only — no mutations eliminated yet.

**Decision: design doc vs reality discrepancy documented**
`ARC4_eliminate_mutations.md §1.2` assumes all mutations live in `services/response_post.py`.
That file does not exist. Real locations: M3/M4/M5-alt inline in
`core/dm/phases/postprocessing.py`; M6 is `services/length_controller.py`; M7/M8 are
`core/dm/style_normalizer.py`; M10 is `services/question_remover.py`. M2 (pii_redactor),
M9 (normalize_casing), M11 (insert_signature_tic) are NOT implemented in code.
Documented in `docs/audit_sprint5/ARC4_mutations_inventory.md`.

**Decision: DISABLE_M* flags default False (mutations stay active)**
Added 6 kill-switch flags to `core/feature_flags.py`: DISABLE_M3_DEDUPE_REPETITIONS,
DISABLE_M4_DEDUPE_SENTENCES, DISABLE_M5_ECHO_DETECTOR, DISABLE_M6_NORMALIZE_LENGTH,
DISABLE_M7_NORMALIZE_EMOJIS, DISABLE_M8_NORMALIZE_PUNCTUATION. All default false — prod
behavior unchanged. Setting true skips that mutation for CCEE shadow testing.
M1 (guardrails) has no kill switch. M10 reuses existing ENABLE_QUESTION_REMOVAL flag.

**Decision: M5-alt echo detector is RECONSIDER, not REPLACE**
A3 block in postprocessing.py is Jaccard echo detection, not "remove_meta_questions" as
the design doc assumed. Echo detection is defensive (prevents bot mirroring the lead),
closer to M1 than cosmetic mutations. Phase 2 shadow will determine KEEP vs REPLACE.

**Files modified**
- `core/feature_flags.py`: 6 DISABLE_M* flags added (default False)
- `core/dm/phases/postprocessing.py`: skip guards for M3 (A2b), M4 (A2c), M5-alt (A3)
- `core/dm/style_normalizer.py`: skip guards for M7 (emoji), M8 (punctuation)
- `services/length_controller.py`: skip guard for M6 (enforce_length)

**Files added**
- `tests/mutations/test_arc4_disable_flags.py`: 12 tests — flags default false, flag=true skips mutation
- `docs/audit_sprint5/ARC4_mutations_inventory.md`: real state of all 11 mutations vs design doc
- `docs/audit_sprint5/ARC4_per_mutation_ccee_impact.md`: template for CCEE shadow results
- `docs/sprint5_planning/ARC4_prompt_rules_v1.md`: 9 prompt-time rules designed (M3-M11)
- `docs/sprint5_planning/ARC4_phase1_rollout_plan.md`: rollout order by risk level

## ARC3 Phase 2: PromptSliceCompactor Shadow Mode — 2026-04-19

**Context:** ARC3 goal is to compact prompts to fit within MAX_CONTEXT_CHARS=8000. Phase 2
implements the compactor in shadow mode — it computes decisions and logs them to DB but
NEVER alters the actual prompt returned to the LLM.

**Decision: shadow mode default ON (ENABLE_COMPACTOR_SHADOW=true)**
Safe because the compactor output is discarded. Fire-and-forget via asyncio.create_task;
any exception in the shadow path is caught and logged as warning. The production path
(combined_context, system_prompt from _assemble_context) is never touched.

**Decision: USE_COMPACTION=false until Phase 3 gate passes**
Phase 3 activates live compaction only after 1,000 shadow turns confirm compaction rate
< 15%. If > 15%, ratios are miscalibrated and must be retuned before activation.
analyze_compactor_shadow.py outputs the gate verdict automatically.

**Decision: distill_service=None in Phase 2 shadow**
StyleDistillCache (ARC3 Phase 1) exists but CCEE validation is still pending.
Wiring distill_service into the shadow compactor is deferred to Phase 3 to avoid
logging false distill decisions before the service is production-ready.

**Files added**
- `alembic/versions/049_arc3_compactor_shadow_log.py`: context_compactor_shadow_log table
- `core/generation/compactor.py`: PromptSliceCompactor §2.3.4 + truncate_preserving_structure
- `tests/compactor/test_compactor.py`: 10 unit tests (all algorithm paths)
- `tests/integration/test_compactor_shadow.py`: 9 integration tests
- `scripts/analyze_compactor_shadow.py`: analysis CLI with Phase 3 gate check
- `docs/sprint5_planning/ARC3_phase2_shadow_design.md`: architecture + runbook

**Files modified**
- `core/feature_flags.py`: ENABLE_COMPACTOR_SHADOW (default True) + USE_COMPACTION (default False)
- `core/dm/phases/context.py`: _run_compactor_shadow + _build_compactor_sections + _log_shadow_compactor_sync + asyncio.create_task hook
