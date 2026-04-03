# DECISIONS.md — Clonnect Backend

Architecture and implementation decisions, in reverse chronological order.

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
