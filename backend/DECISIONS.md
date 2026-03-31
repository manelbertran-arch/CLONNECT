# DECISIONS.md — Clonnect Backend

Architecture and implementation decisions, in reverse chronological order.

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
