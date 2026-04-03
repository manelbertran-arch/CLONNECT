# Audit — Sistema #8: DNA Engine (Relationship DNA)

**Date:** 2026-04-01
**Status:** Audit complete — 10 functional tests (29 assertions, 0 failures)
**Files read (ALL lines):**
- `services/relationship_dna_service.py` (274 lines) — Service layer with caching
- `services/relationship_dna_repository.py` (459 lines) — CRUD + JSON fallback
- `services/bot_instructions_generator.py` (168 lines) — Prompt formatting
- `services/relationship_type_detector.py` (188 lines) — Rule-based type detection
- `services/relationship_analyzer.py` (557 lines) — Full conversation analysis
- `models/relationship_dna.py` (109 lines) — Data model + RelationshipType enum
- `services/dm_agent_context_integration.py:149-237` — `_format_dna_for_prompt()`

**Total: ~1,755 lines read**

## What is it?

Per-lead relationship classification that adapts the bot's communication style based on how the creator relates to each specific lead. Each lead gets a DNA record with:

- **Relationship type** (7 types): FAMILIA, INTIMA, AMISTAD_CERCANA, AMISTAD_CASUAL, CLIENTE, COLABORADOR, DESCONOCIDO
- **Trust score** (0.0-1.0): Based on relationship type + message count
- **Depth level** (0-4): Based on total message count (<10→0, 10-24→1, 25-49→2, 50-99→3, 100+→4)
- **Vocabulary uses/avoids**: Words the creator uses vs words the lead uses but creator doesn't
- **Emojis**: Emojis appropriate for this relationship
- **Recurring topics**: Detected from keyword matching
- **Golden examples**: Up to 3 real (lead, creator) message pairs
- **Bot instructions**: Generated text combining all of the above

## Pipeline Position

```
TWO CREATION PATHS:

SEED (auto-create at 2+ messages):
  context.py:339  → if ENABLE_DNA_AUTO_CREATE and no existing DNA and follower.total_messages >= 2
  context.py:343  → RelationshipTypeDetector().detect(history)  [rule-based, fast]
  context.py:358  → create_relationship_dna(type=detected, trust=confidence*0.3, depth=0)
  context.py:373  → asyncio.create_task(_create_seed_dna())  [fire-and-forget]
  ⚠️ Seed DNA has NO vocabulary, NO golden examples — only type + minimal trust

FULL ANALYSIS (periodic, on sufficient new messages):
  RelationshipDNAService.analyze_and_update_dna()
  → RelationshipAnalyzer.analyze(messages)  [full extraction]
  → vocabulary, emojis, topics, patterns, golden examples, bot_instructions
  ⚠️ Called via analyze_and_update_dna() but NOT triggered automatically in the DM pipeline

LOADING PATH (every DM):
  context.py:248  → asyncio.to_thread(_get_raw_dna, creator_id, sender_id)
  context.py:252  → _build_ctx(preloaded_dna=raw_dna)
  dm_agent_context_integration.py:127-131  → _format_dna_for_prompt(dna)
  → Injected into combined context string → passed as custom_instructions to PromptBuilder
```

## Data Sources

| Source | Path | Content |
|--------|------|---------|
| PostgreSQL | `relationship_dnas` table | Primary storage (7 types + 20 fields) |
| JSON files | `data/relationship_dna/{creator_id}/{follower_id}.json` | Fallback for local dev |
| In-memory cache | `BoundedTTLCache(max_size=500, ttl_seconds=300)` | 5-min cache per lead |

## Detection Pipeline (2 levels)

### Level 1: RelationshipTypeDetector (rule-based, used for seeding)

Weighted keyword/emoji scoring per type with thresholds:

| Type | Example keywords (weight) | Threshold |
|------|--------------------------|-----------|
| FAMILIA | hijo(5), mama(4), papa(4), abuelo(4) | 8 |
| INTIMA | amor(5), te amo(5), cariño(4), bebe(3) | 10 |
| AMISTAD_CERCANA | hermano(3), bro(3), meditacion(2) | 6 |
| AMISTAD_CASUAL | crack(3), tio(2), maquina(2) | 4 |
| CLIENTE | precio(3), cuesta(3), comprar(2), curso(2) | 6 |
| COLABORADOR | colaboracion(4), partnership(3), marca(2) | 5 |

Confidence = `min(0.95, 0.6 + (score - threshold) * 0.05)` when above threshold.

### Level 2: RelationshipAnalyzer (full analysis, 5+ messages required)

Extracts: type (via Level 1), trust score, depth level, vocabulary (frequency-based), emojis, topics, patterns, golden examples, bot instructions.

## Prompt Injection

Via `_format_dna_for_prompt()` in `dm_agent_context_integration.py`:
```
=== CONTEXTO DE RELACIÓN CON ESTE USUARIO ===
Relación: AMISTAD_CERCANA (Como un buen amigo, confianza alta)
Nivel de profundidad: confianza
Palabras que sueles usar con esta persona: hermano, crack, genial, bro, compa
Palabras que esta persona usa pero TÚ no: señor, estimado
Emojis típicos en esta relación: 🙏 💪 🔥
Tono: Cercano, fraternal, espiritual, de confianza
Temas frecuentes: meditacion, fitness

Guía de comunicación: Esta es una amistad cercana. Usa un tono fraternal...

Ejemplos de cómo respondes a esta persona:
  Usuario: Hola bro que tal
  Tú: Crack! Aqui andamos
=== FIN CONTEXTO RELACIÓN ===
```

### Size estimate
~300–800 chars (type + vocab + examples). Seed DNA without vocab/examples: ~100–200 chars.

## Bugs Found

### Critical

| ID | Bug | Evidence |
|----|-----|----------|
| **B1** | **Full analysis never triggered automatically** | `analyze_and_update_dna()` exists but is NOT called from the DM pipeline. The pipeline only does: (1) seed creation at 2 messages via `RelationshipTypeDetector` (fast, keyword-only) and (2) loading existing DNA. The full `RelationshipAnalyzer` with vocabulary extraction, golden examples, and topic detection is NEVER called unless explicitly invoked. Most leads get SEED DNA only (type + minimal trust, no vocabulary). |

### High

| ID | Bug | Evidence |
|----|-----|----------|
| **B2** | **Detector keywords are Spanish-only** | `INDICATORS` dict uses: "hijo", "mama", "amor", "precio", "hermano", "crack". Italian family ("mamma", "figlio"), Catalan ("fill", "mare"), English ("mom", "son") are NOT detected. Test confirms: Italian family messages → DESCONOCIDO. |
| **B3** | **`_extract_topics` hardcoded to 5 domains** | Line 318-336 of `relationship_analyzer.py`: topics limited to "circulos de hombres", "meditacion", "terapia", "negocios", "fitness". A makeup creator's topics (maquillaje, skincare) are invisible. Test confirms: makeup keywords → 0 topics. |
| **B4** | **Trust score disconnect between seed and full analysis** | Seed DNA: `trust = detector_confidence * 0.3` (e.g., 0.24 for confident FAMILIA). Full analysis: FAMILIA base trust = 0.95. A lead detected as FAMILIA with seed DNA gets trust 0.24, but full analysis would give 0.95. Huge gap means trust-dependent behavior (depth labels, prompt hints) is wrong for seed-only leads. |

### Medium

| ID | Bug | Evidence |
|----|-----|----------|
| **B5** | **All prompt labels and instructions in Spanish** | `_format_dna_for_prompt()`: "CONTEXTO DE RELACIÓN", "Palabras que sueles usar", "Nivel de profundidad". `BASE_INSTRUCTIONS`: "Usa un tono cálido, cercano y protector". `_describe_tone()`: "Familiar, cálido, protector". `BotInstructionsGenerator.generate()`: "USA estas palabras", "EVITA estas palabras". All Spanish for all creators including Italian Stefano. |
| **B6** | **`_extract_vocabulary_uses` regex excludes Italian characters** | Line 239: `re.findall(r"\b[a-záéíóúüñàèòïç]{3,}\b", msg.lower())`. Missing Italian accented chars like ì, ù (e.g., "più", "perché"). Also missing German ö/ä/ü and Portuguese ã/õ. Vocab extraction partially fails for non-ES/CA languages. However, test shows "amico" IS detected (common Latin chars), so impact is partial. |
| **B7** | **Seed DNA is fire-and-forget** | Line 373: `asyncio.create_task(_create_seed_dna())`. No await, no error handling beyond a debug log inside the task. If creation fails (DB timeout, race condition), the seed is lost silently. Next DM will try again (good), but cognitive_metadata already says `dna_seed_created=True` (misleading). |
| **B8** | **300s cache TTL may miss rapid relationship evolution** | `BoundedTTLCache(ttl_seconds=300)`. If DNA is updated (e.g., by full analysis), cached version persists for up to 5 minutes. During that time, the old relationship type/vocabulary is used. |
| **B9** | **`detect_with_history` hysteresis may mask real changes** | Lines 159-187 of detector: if previous type was non-DESCONOCIDO and new detection is uncertain, keeps previous type with confidence 0.5. A lead that was incorrectly classified as INTIMA will stay INTIMA even when evidence points to DESCONOCIDO. |

### Low

| ID | Bug | Evidence |
|----|-----|----------|
| **B10** | **Golden examples only from first 3 qualifying pairs** | Line 553: `if len(examples) >= 3: break`. Takes first 3 short exchanges, not the most representative. A conversation that starts with small talk but evolves into deep discussion only captures the small talk. |
| **B11** | **`_extract_topics` overlaps with RAG** | Topics like "fitness" or "negocios" are also in RAG knowledge base. Double injection: DNA says "Temas frecuentes: fitness" and RAG provides fitness product details. Redundant but not harmful. |
| **B12** | **FAN_ACTIVO and LEAD_FRIO types exist in model docstring but not in enum** | `RelationshipType` enum has 7 values, but docstring in `relationship_dna.py:22-29` mentions examples that include FAN_ACTIVO. The summary in the batch audit listed FAN_ACTIVO/LEAD_FRIO but they don't exist as valid types. |
| **B13** | **Repository `get_or_create` doesn't handle prefix normalization for create** | Lines 329-341 of repository: creates with the raw `follower_id`, even though lookup tried both `ig_X` and `X`. Could create duplicate records if called with different ID formats. `IntegrityError` handler in `create_relationship_dna` partially mitigates this. |
| **B14** | **`list_relationship_dnas_by_creator` limited to 100** | Line 399: `.limit(100)`. If a creator has >100 leads with DNA, only first 100 returned. Admin view would be incomplete. |

## Functional Tests (10 groups, 29 assertions)

All PASS. Tests designed to verify bugs and edge cases:

```
TEST 1: Detector — ES keywords work, IT keywords missing
  PASS: ES familia detected — confirms detector works for Spanish
  PASS: IT familia NOT detected — confirms B2

TEST 2: Detector — CLIENTE detection from price keywords
  PASS: CLIENTE detected from price keywords

TEST 3: Detector — < 2 messages returns DESCONOCIDO
  PASS: single message → DESCONOCIDO
  PASS: confidence = 0.3

TEST 4: BASE_INSTRUCTIONS all in Spanish
  PASS: FAMILIA instruction is Spanish — confirms B5 (×7 types)

TEST 5: BotInstructionsGenerator — vocabulary truncation
  PASS: vocabulary_uses truncated to 5 words
  PASS: exactly 5 use words in output

TEST 6: Analyzer — vocab extraction is language-agnostic
  PASS: Catalan word 'flower' detected (frequency-based)
  PASS: Italian word 'amico' detected — vocab extraction works cross-language

TEST 7: Analyzer — _extract_topics hardcoded to specific domains
  PASS: makeup topics NOT detected — confirms B3
  PASS: fitness detected

TEST 8: Analyzer — golden examples filter media
  PASS: audio message filtered out
  PASS: photo message filtered out
  PASS: text example included

TEST 9: Seed DNA trust_score calculation
  PASS: seed trust for DESCONOCIDO is very low (0.09)
  PASS: seed trust for confident detection still low (0.24)
  PASS: analyzer trust for FAMILIA is high (0.95)
  PASS: trust disconnect confirmed — confirms B4

TEST 10: _format_dna_for_prompt labels all Spanish
  PASS: header in Spanish (×4 label checks) — confirms B5
```

## Paper Cross-References (2024-2026)

### Core Papers

| # | Paper | Venue | Key Technique | Relevance to DNA Engine |
|---|-------|-------|---------------|------------------------|
| 1 | **MemoryBank** (Zhong et al.) | AAAI 2024 | Ebbinghaus Forgetting Curve — memories decay/reinforce based on time + significance | Trust score should decay for inactive leads. Currently static once set. |
| 2 | **LD-Agent** (Li et al.) | NAACL 2025 | 3 decoupled modules: event perception, persona extraction, response generation | Maps to our detection→DNA→generation pipeline. Each module independently tunable. |
| 3 | **RMM** (Tan et al.) | ACL 2025 | Prospective + Retrospective reflection — multi-granularity summarization + RL-based retrieval refinement | Golden examples should be session-level summaries, not raw first-3 pairs (B10). |
| 4 | **MapDia** (Wu et al.) | CoNLL 2025 | Memory-aware Proactive Dialogue — identifies interpersonal memories and proactively references them | `private_references` field exists but is never populated. MapDia shows this is the highest-value signal for relationship-aware dialogue. |
| 5 | **PersonaMem** (Jiang et al.) | COLM 2025 | Benchmark for dynamic user profiling — tests trait internalization, preference tracking, personalized generation | Even GPT-4.1 only achieves ~50% on dynamic profile tracking. Our explicit structured memory (DNA) may outperform pure prompting. |
| 6 | **Mem-PAL** (Huang et al.) | AAAI 2026 | Relational edges between memory fragments → memory graph per user | Our flat DNA fields could be connected: vocabulary→relationship_type→golden_examples as a retrievable subgraph. |
| 7 | **PersonaTree** (Zhao et al.) | Preprint 2026 | Biopsychosocial hierarchical tree: Social + Psychological + Biological dimensions per user | Replaces flat 7-type enum with structured subtree: Social (type, frequency), Psychological (tone, trust), Biological (language). |
| 8 | **Memoria** (Sarin et al.) | IEEE 2025 | Weighted knowledge graph + session summarization. 87.1% accuracy, 38.7% latency reduction | Weighted KG approach is production-ready. Could integrate with our pgvector setup. |
| 9 | **AdaMem** (Yan et al.) | Preprint 2026 | 4 memory types: working, episodic, persona, graph. Question-conditioned retrieval with relation-aware expansion | Maps cleanly: working=current turn, episodic=session history, persona=DNA, graph=cross-lead connections. |
| 10 | **MindMemory** (Zhang et al.) | ChineseCSCW 2024 | Theory of Mind — infers user's mental model, personality portraits that refresh continuously | A CLIENTE using informal language → transitioning to AMISTAD. ToM catches this before explicit signals. |

### GitHub Repos

| # | Repo | Stars | Architecture | Relevance |
|---|------|-------|-------------|-----------|
| 1 | **mem0ai/mem0** | ~51.7k | Multi-level memory (user, session, agent). Relevance+importance+recency scoring | Clean per-user namespace API. More general-purpose than our domain-specific DNA. |
| 2 | **letta-ai/letta** (MemGPT) | ~21.8k | Stateful agents with memory blocks. DialogueThread + MemoryThread split | "Human" block stores per-user facts that agent self-edits. Closest to our DNA auto-update model. |
| 3 | **MemoriLabs/Memori** | ~12.9k | SQL-native, 3NF schema with semantic triples, relationships. 81.95% on LoCoMo | Explicit relationship schema — most aligned with our relationship tracking. Uses ~1,294 tokens/query (67% less than competitors). |
| 4 | **memodb-io/memobase** | ~2.7k | User-profile-centric. FastAPI+Postgres+Redis. Batch-process chats into profile updates. <100ms latency | Closest to our DNA design: structured per-user profile that evolves over time. Configurable profile schema. |
| 5 | **zhongwanjun/MemoryBank-SiliconFriend** | ~420 | Ebbinghaus forgetting curve. Per-user personality summaries in JSON. LoRA fine-tuned for empathy | Direct implementation of Paper #1. Memory decay/reinforcement is the key missing feature in our system. |

### Gap Analysis: Our System vs. Literature

| Capability | Papers/Repos | Our Status (Post-Fix) |
|-----------|-------------|----------------------|
| Per-relationship vocabulary adaptation | RoleLLM, Mem0 | **IMPLEMENTED** — frequency-based, language-agnostic (B7 fix) |
| Multilingual relationship detection | PersonaMem, Memori | **IMPLEMENTED** — ES/IT/CA/EN keywords in detector (B2 fix) |
| Trust-modulated communication | SPC, MemoryBank | **IMPLEMENTED** — seed trust aligned with full analysis (B4 fix) |
| Dynamic topic extraction | MapDia, Memobase | **IMPLEMENTED** — curated seeds + frequency extraction (B3 fix) |
| Memory forgetting/reinforcement | MemoryBank, Memoria | **MISSING** — trust_score is static once set, no decay |
| Interpersonal shared-experience memory | MapDia | **MISSING** — `private_references` field exists but never populated |
| Hierarchical memory structure | PersonaTree, AdaMem | **MISSING** — flat fields, no tree/graph structure |
| Cross-lead transfer learning | Mem-PAL | **MISSING** — each lead is independent, no pattern sharing |
| Theory of Mind inference | MindMemory | **MISSING** — detection is keyword-based, not mental-model-based |

## Fixes Implemented (2026-04-01)

### Session 1: Bug Fixes (7 bugs)

| Fix | File | Change |
|-----|------|--------|
| DNA-01 | `relationship_dna_service.py` | Unbounded `Dict` cache → `BoundedTTLCache(500, ttl=300)` |
| DNA-02 | `dna_update_triggers.py` | `threading.Thread` → retry loop (2 attempts, 2s backoff) with per-attempt logging |
| DNA-03 | `relationship_analyzer.py` | Removed 50-line legacy type detection fallback. Single path: `RelationshipTypeDetector` |
| DNA-04 | `relationship_dna_repository.py` | `get_or_create` now tries both `follower_id` and `ig_{id}` formats |
| DNA-05 | `relationship_dna_service.py` | Cache invalidation: `in` + `del` → atomic `cache.pop()` |
| DNA-06 | `relationship_analyzer.py` | Added `[📍 Location]`, `[📄 Document]`, `[📎 File]`, `[👤 Contact]`, `[🔗 Link]`, `[GIF]` to media filter |
| DNA-07 | `relationship_analyzer.py` | Hardcoded 20-word Spanish vocab → frequency-based extraction (2+ occurrences, minus stopwords). Language-agnostic |

### Session 2: Optimizations (4 bugs from deep audit)

| Fix | File | Change |
|-----|------|--------|
| B2 | `relationship_type_detector.py` | Added IT/CA/EN keywords to all 6 INDICATORS types. ~60 new keywords total |
| B3 | `relationship_analyzer.py` | `_extract_topics`: hardcoded 5-domain dict → curated seeds (15 domains) + dynamic frequency extraction. Language-agnostic |
| B4 | `core/dm/phases/context.py` | Seed trust: `confidence * 0.3` → per-type base trust (`_SEED_TRUST` dict). FAMILIA=0.85, CLIENTE=0.25, DESCONOCIDO=0.10 |
| B6 | `relationship_analyzer.py` | Regex `[a-záéíóúüñàèòïç]` → `[a-záéíóúüñàèòïçìùöäãõ]`. Adds IT ì/ù, DE ö/ä, PT ã/õ |

## Post-Fix Functional Tests (44 assertions)

```
TEST 1: New lead, zero DNA -> seed creation (4/4 PASS)
  PASS: 0 messages -> DESCONOCIDO
  PASS: 1 message -> DESCONOCIDO
  PASS: 2 msgs with family keywords -> FAMILIA
  PASS: confidence > 0.4 (seed threshold)

TEST 2: DNA loading and formatting (4/4 PASS)
  PASS: type injected in prompt
  PASS: vocabulary injected
  PASS: emojis injected
  PASS: golden example injected

TEST 3: Relationship type evolution (2/2 PASS)
  PASS: Phase 1: generic -> DESCONOCIDO
  PASS: Phase 2: price talk -> CLIENTE

TEST 4: FAMILIA tone adaptation + multilingual (5/5 PASS)
  PASS: FAMILIA hint text present
  PASS: depth label = cercanos/intimos
  PASS: IT FAMILIA detected (B2 fix)
  PASS: CA FAMILIA detected (B2 fix)
  PASS: EN FAMILIA detected (B2 fix)

TEST 5: DNA update triggers (5/5 PASS)
  PASS: No DNA + 5 msgs -> first analysis
  PASS: No DNA + 3 msgs -> no trigger
  PASS: 50 msgs (10 new) -> trigger
  PASS: 45 msgs (5 new, recent date) -> no trigger
  PASS: Reason is new_messages_15

TEST 6: Cache isolation between leads (5/5 PASS)
  PASS: Lead A = FAMILIA
  PASS: Lead B = CLIENTE
  PASS: No cross-contamination
  PASS: After clearing A, B survives
  PASS: After clearing A, A gone

TEST 7: Catalan vocabulary extraction (2/2 PASS)
  PASS: CA: germa extracted
  PASS: CA: meditacio topic (dynamic)

TEST 8: English support (4/4 PASS)
  PASS: EN FAMILIA detected
  PASS: EN CLIENTE detected
  PASS: EN INTIMA detected
  PASS: EN vocab extracted

TEST 9: Golden examples extraction and injection (3/3 PASS)
  PASS: Golden examples extracted
  PASS: Audio filtered
  PASS: Examples in prompt

TEST 10: BoundedTTLCache TTL and eviction (6/6 PASS)
  PASS: Before expiry: key exists
  PASS: After expiry: key evicted
  PASS: After overflow: newest exists
  PASS: After overflow: eviction happened
  PASS: Production cache: max_size=500
  PASS: Production cache: ttl=300s

BONUS: Dynamic topics + Trust alignment (4/4 PASS)
  PASS: Makeup topics detected (B3 fix)
  PASS: Dynamic topic ceramica detected
  PASS: FAMILIA seed trust = 0.85
  PASS: DESCONOCIDO seed trust = 0.10

TOTAL: 44/44 PASS
```

## Remaining Recommendations (Not Yet Implemented)

### Priority 1: Memory decay (from MemoryBank paper)
Add Ebbinghaus-style decay to `trust_score`: leads who haven't interacted in 30+ days get trust reduced by 10% per month. Reinforced on each interaction.

### Priority 2: Populate `private_references` (from MapDia paper)
Extract shared experiences from conversation history. When lead and creator discuss a specific event ("aquel retiro en Ibiza"), store it as a private reference for proactive mention.

### Priority 3: Hierarchical memory structure (from PersonaTree)
Replace flat DNA fields with a 3-level tree: L1 Social (type, frequency), L2 Psychological (tone, trust, emotional patterns), L3 Linguistic (vocabulary, emojis, language preference).

### Priority 4: Cross-lead pattern transfer
If creator treats all AMISTAD_CERCANA leads similarly (uses "hermano", "crack"), extract a per-type template and apply to new leads of that type before DNA is populated.

Use the same formula for seed and full analysis: seed should use `base_scores[detected_type]` instead of `confidence * 0.3`.
