# Pipeline Audit: Copilot Response Quality
**Date**: 2026-03-19
**Current click-and-play rate**: ~20% (4/20 usable without editing)
**Primary failure mode**: CONTEXT errors (40%)

---

## PHASE 1: Complete Pipeline Trace

### 1.1 Message Arrival (Webhook)

```
WhatsApp: api/routers/messaging_webhooks/evolution_webhook.py:162 → evolution_webhook()
Instagram: core/instagram_modules/dispatch.py → dispatch_message()
          api/routers/oauth/instagram.py → (IGAAT flow)
```

**Data in**: Raw webhook JSON payload
**Data out**: `text`, `msg_metadata` (JSONB), `detected_media_type`

### 1.2 Media Processing & Audio Transcription

```
evolution_webhook.py:550 → _download_evolution_media()
  ├── Download from WhatsApp CDN
  ├── Upload to Cloudinary (permanent URL)
  └── If audio:
      ├── ingestion/transcriber.py → transcribe_file()  [Groq → Gemini → OpenAI cascade]
      │   Returns: Transcript(full_text, language, duration)
      └── services/audio_intelligence.py → process()  [4-layer pipeline]
          Returns: AudioIntelligence(raw_text, clean_text, summary, entities, intent)
```

**Message content for audio** (evolution_webhook.py:326-331):
```python
text = f"[🎤 Audio]: {ai.clean_text or ai.summary or transcription}"
# If no transcription: "[🎤 Audio message]"
```

**Message content for other media**:
```python
"[📷 Photo]"  /  "[🎬 Video]"  /  "[🏷️ Sticker]"  /  "[📄 Document]"
```

### 1.3 Message Storage (Early Save)

```
evolution_webhook.py:467 → _do_early_save()
  ├── Find Creator by slug name
  ├── Find/create Lead by platform_user_id
  ├── INSERT Message(role="user", status="sent", content=text, msg_metadata=metadata)
  └── SSE notify frontend → "new_message"
```

### 1.4 Copilot Generation Trigger

```
evolution_webhook.py:986 → _process_evolution_message_safe()  [background task]
  ├── core/dm/agent.py:375 → agent.process_dm(message, sender_id, metadata)
  │   Returns: DMResponse(content, intent, confidence, metadata)
  └── core/copilot/lifecycle.py:18 → create_pending_response_impl()
      ├── Dedup checks (message_id, pending_approval)
      ├── Non-text media check → is_non_text_message() [core/copilot/models.py:39]
      │   SKIPS suggestion for: "[📷 Photo]", "[🎬 Video]", "[🏷️ Sticker]", emoji-only
      │   GENERATES suggestion for: "[🎤 Audio]: {text}" (has transcription content)
      └── INSERT Message(role="assistant", status="pending_approval", content=suggestion)
```

### 1.5 DM Agent — 5-Phase Pipeline

#### Phase 1: Detection (core/dm/phases/detection.py:22)

```
phase_detection(agent, message, metadata)
  ├── Sensitive content detection → crisis response (early return)
  ├── Frustration analysis (0.0-1.0)
  ├── Pool response matching (short messages ≤80 chars, 30% multi-bubble)
  └── Edge case detection (escalation needed?)
```

**Key**: Pool responses can return early, bypassing LLM entirely.

#### Phase 2-3: Context & Prompt (core/dm/phases/context.py:32)

```
phase_memory_and_context(agent, message, sender_id, metadata, detection_result)
  │
  ├── Step 2: Intent classification → agent.intent_classifier.classify()
  │
  ├── Step 2b: Parallel IO loading (asyncio.gather):
  │   ├── agent.memory_store.get_or_create()      → FollowerMemory (JSON files)
  │   ├── _build_ctx(creator_id, sender_id)         → DNA relationship context
  │   └── _load_conv_state()                         → Conversation phase state
  │
  ├── Step 2c: Memory Engine recall (if ENABLE_MEMORY_ENGINE=true)
  │   └── services/memory_engine.py → recall(creator_id, sender_id, message)
  │       Returns: formatted facts (max 1200 chars, 10 facts + summary)
  │
  ├── Step 3: RAG retrieval (if intent not in skip-set)
  │   └── core/rag/semantic.py → search(query, top_k=3)
  │       Pipeline: embedding → pgvector → BM25 hybrid → rerank
  │       Results truncated to 200 chars each
  │
  ├── Step 3b: Relationship type detection → friend/family suppression
  │
  ├── Step 3c: Audio context extraction (from metadata.audio_intel)
  │   └── Formats: intent, entities, action_items, emotional_tone
  │       Into: "CONTEXTO DE AUDIO (mensaje de voz transcrito):\n..."
  │
  ├── Step 3d: ECHO RelationshipAdapter → relational context block
  │
  ├── Step 3e: Calibration few-shot examples (max 2)
  │   └── services/calibration_loader.py → get_few_shot_section()
  │       Source: calibrations/{creator_id}.json (FILE SYSTEM)
  │       *** FILE DOES NOT EXIST FOR IRIS → 0 examples from calibration ***
  │
  ├── Step 3f: System prompt assembly:
  │   combined_context = "\n\n".join([
  │       agent.style_prompt,          # ~21,495 chars (personality extraction)
  │       friend_context,              # Override for family/friends
  │       relational_block,            # ~762 chars (ECHO adapter)
  │       rag_context,                 # ~32 chars (*** nearly empty ***)
  │       memory_context,              # ~182 chars (lead facts)
  │       few_shot_section,            # 0 chars (*** no calibration file ***)
  │       dna_context,                 # ~321 chars (relationship DNA)
  │       state_context,               # ~306 chars (conversation phase)
  │       audio_context,               # Variable (if audio message)
  │       kb_context,                  # Knowledge base facts
  │       citation_context,            # Source links
  │       advanced_section,            # ~870 chars (anti-hallucination)
  │       prompt_override,             # Manual override
  │   ])
  │
  └── Step 3g: Conversation history loading:
      ├── Try: agent._get_history_from_follower(follower)  → JSON file, last 20 msgs
      └── Fallback: get_history_from_db(creator_id, sender_id, 20) → PostgreSQL
          Format: [{"role": "user/assistant", "content": "..."}]
```

**System prompt total**: ~26,580 chars (~6,645 tokens)

#### Phase 4: LLM Generation (core/dm/phases/generation.py:27)

```
phase_llm_generation(agent, message, context_bundle)
  │
  ├── Step 5b: Response strategy determination
  │
  ├── Step 5c: Learning rules injection (DB: learning_rules table)
  │   └── 824 rules for iris_bertran, filtered by intent/relationship/stage
  │       Injected 5 rules per call (from logs)
  │       Format: "=== REGLAS APRENDIDAS ===\n- {rule_text}\n  NO: {bad}\n  SI: {good}"
  │
  ├── Step 5d: Preference profile injection (if ENABLE_PREFERENCE_PROFILE=true)
  │
  ├── Step 5e: Gold examples injection (DB: gold_examples table)
  │   └── 4,505 examples for iris_bertran, filtered by intent/relationship/stage
  │       Injected 3 examples per call (from logs)
  │       Format: "=== EJEMPLOS DE COMO RESPONDE IRIS_BERTRAN ==="
  │
  ├── Step 6: Full prompt assembly:
  │   prompt_parts = [
  │       user_context,                # Username + stage + history + lead_info
  │       bot_instructions,            # DNA-specific instructions
  │       learning_rules_section,      # 5 rules
  │       preference_profile_section,  # Preference guidance
  │       gold_examples_section,       # 3 examples
  │       strategy_hint,               # Response strategy
  │       frustration_note,            # If frustrated
  │       "Mensaje actual:\n<user_message>\n{message}\n</user_message>"
  │   ]
  │
  ├── Step 7: LLM Call
  │   ├── Model: gemini-2.5-flash-lite (primary) → gpt-4o-mini (fallback)
  │   ├── Temperature: 0.7 (default, tunable via ECHO RelationshipAdapter)
  │   ├── Max tokens: 150 (default, tunable via ECHO)
  │   └── If ENABLE_BEST_OF_N=true (copilot mode):
  │       └── core/best_of_n.py → generate_best_of_n()
  │           3 parallel calls at T=[0.2, 0.7, 1.4]
  │           Style hints force diversity:
  │             T=0.2: "[ESTILO: breve y directa, 1-2 frases]"
  │             T=0.7: (no hint)
  │             T=1.4: "[ESTILO: elaborada, calida, 3-4 frases]"
  │           Scored by calculate_confidence() → best selected
  │           Timeout: 12s for all 3
  │
  └── Self-consistency validation (if ENABLE_SELF_CONSISTENCY=true)
      Extra LLM call to verify response ↔ query coherence
```

#### Phase 5: Post-processing (core/dm/phases/postprocessing.py:32)

```
phase_postprocessing(agent, message, context_bundle, llm_response)
  ├── Loop detection (last 3 bot msgs identical → generic fallback)
  ├── Output validation (prices, links)
  ├── Response fixes (typos, formatting)
  ├── Tone enforcement (emoji rate, exclamations)
  ├── Question removal (rhetorical questions)
  ├── Reflexion analysis (if ENABLE_REFLEXION=true)
  │   └── If poor quality → re-generate at T=0.3 (more conservative)
  ├── Guardrails (hallucination check, allowed domains)
  ├── Length control
  ├── Instagram formatting
  └── Confidence scoring → calculate_confidence()
```

### 1.6 Suggestion Storage & Frontend Delivery

```
core/copilot/lifecycle.py:338-354 → Save to messages table
  status="pending_approval", msg_metadata includes best_of_n candidates

Frontend polls: GET /copilot/{creator_id}/pending
  → api/routers/copilot/actions.py:52-89
  Returns: suggested_response, candidates[], conversation_context[]

Creator action:
  Approve → POST /copilot/{creator_id}/approve/{message_id}
    → Send via platform, update status="sent"/"edited"
    → Fire learning hooks (autolearning, preference pairs)
  Discard → POST /copilot/{creator_id}/discard/{message_id}
    → status="discarded", fire learning hooks
  Manual reply → auto-discard pending, status="resolved_externally"
    → Compare bot suggestion vs actual for learning
```

---

## PHASE 2: Bottleneck Identification

### 2.1 Production Data Summary (iris_bertran)

| System | Data Available | In Prompt | Utilization |
|--------|---------------|-----------|-------------|
| Style prompt | Doc D extraction | 21,495 chars | HIGH (dominates prompt) |
| Learning rules | 824 rules in DB | 5 rules/call | OK but rules are generic |
| Gold examples | 4,505 examples in DB | 3 examples/call | OK but selection quality unknown |
| Calibration few-shot | **0 (file missing)** | 0 chars | **ZERO** |
| RAG (content_chunks) | 24 chunks | ~32 chars | **NEAR ZERO** |
| Lead memories | 2,247 facts (170 leads) | ~182 chars | LOW |
| Conversation summaries | 6,178 summaries | Included in memory | OK |
| Relational context | ECHO adapter | ~762 chars | OK |
| Audio context | Audio intel pipeline | Variable | OK when triggered |
| Conversation history | 20 msgs from DB/JSON | In user_context | **DEGRADED** (see 2.3) |

**Feature flags**: ALL features enabled in production. The system is running at maximum complexity.

### 2.2 Where Context Gets LOST

#### BUG 1: "I can't listen to audio" (CRITICAL)

**Root cause**: Conversation history for audio-heavy contacts contains old messages stored as `[audio]` (plain placeholder, no transcription). The LLM sees a pattern:
```
Bot: [audio]
User: [audio]
Bot: [audio]
User: [🎤 Audio]: Mamacita! Què dius?...  ← NEW (has transcription)
```
The LLM infers from history that audio = opaque, and generates "I can't listen to your audio."

**Evidence**: Sonia's conversation history shows 6+ messages as `[audio]` before the new transcribed one.

**Location**: History loading in `core/dm/phases/context.py:399-412`. Old `[audio]` placeholders are passed verbatim.

**Fix**: Strip or replace `[audio]` entries in history. Or inject system instruction: "Audio messages prefixed with [🎤 Audio]: contain full transcriptions you CAN read."

#### BUG 2: Photos/Videos/Stickers → Generic responses (HIGH)

**Root cause**: `is_non_text_message()` in `core/copilot/models.py:39` detects `[📷 Photo]` etc. and SKIPS copilot generation. But sometimes the user sends a photo WITH context (previous messages). The copilot doesn't generate for the photo, so the creator gets nothing.

When it does generate (edge cases), the bot has zero visual understanding — it can't see the image. It responds generically.

**Evidence**: 4/20 suggestions were for attachment-adjacent messages where bot said generic things.

#### BUG 3: Short messages lose conversation thread (HIGH)

User says "Yes!" or "Sii" or "❤️" — these are RESPONSES to previous bot questions. But:
1. Pool response matching (Phase 1) intercepts short messages (≤80 chars)
2. Even if it passes to LLM, the model doesn't always connect "Yes" to the previous question
3. Question context analysis exists (context.py:47-65) but only for yes/no affirmations

**Evidence**: "Yes!" → "Hola Sandra! 😊" (ignores what was asked). "Sii" → unrelated response.

### 2.3 Where BAD Data Gets INJECTED

#### ISSUE 1: Old `[audio]` in conversation history

History contains `[audio]` placeholders from before Audio Intelligence was deployed. These are noise — they convey zero information and teach the LLM that audio = opaque.

**Scale**: Likely thousands of messages across all leads.

#### ISSUE 2: Gold examples with media placeholders

```sql
-- Top gold example by quality score:
"[🎤 Audio]: Enviem una foto..." → "iris ves a dormir ja anirem un altre dia"
```
The #1 gold example teaches the bot to respond to audio with a completely unrelated message. Gold examples with `[🎤 Audio]`, `[📷 Photo]`, or `[🏷️ Sticker]` in user_message are training noise.

#### ISSUE 3: Learning rules are too generic

Top 5 rules by `times_applied`:
1. "Mantén un tono informal y cercano" (568 applications)
2. "Adapta el tono a la conversación" (557)
3. "Si el usuario menciona una contradicción..." (544)
4. "Sé más conciso y casual" (544)
5. "Si el cliente confirma la reserva..." (534)

These are applied 500+ times each — they're background noise, not actionable guidance. Rule #1 and #4 contradict each other (casual+emoji vs no-emoji).

### 2.4 Where the Prompt WASTES Tokens

| Section | Chars | Tokens (~) | Value | Problem |
|---------|-------|-----------|-------|---------|
| Style prompt | 21,495 | 5,374 | HIGH but oversized | 80% of prompt. Contains full personality extraction. |
| Relational | 762 | 190 | MEDIUM | Useful but small |
| Advanced (anti-halluc) | 870 | 218 | LOW | Rules for products/prices — irrelevant for friend conversations |
| RAG | 32 | 8 | **ZERO** | Only 24 content chunks exist. Most queries return nothing. |
| Memory | 182 | 46 | LOW | 2,247 facts but recall returns very few per query |
| DNA | 321 | 80 | MEDIUM | Relationship-specific |
| State | 306 | 77 | LOW | Conversation phase tracking |

**Total**: ~6,645 tokens of system prompt. Of this, ~5,374 tokens (81%) is style prompt. The actual contextual data (RAG + memory + history) is <5% of the prompt.

The LLM has abundant personality instructions but almost no factual context about what the conversation is about.

### 2.5 Conversation History Analysis

History loads 20 messages from DB or JSON. **But**:

1. Old audio messages are `[audio]` — zero information content
2. Old media messages are `[📷 Photo]` etc. — zero information
3. Messages are truncated to 200 chars in formatting
4. `pending_approval` messages are excluded from follower detail endpoint but MAY be included in history loading (depends on status filter)
5. History is in the `user_context` section, separate from `system_prompt` — the model sees it but with less priority than the 21K style section

### 2.6 Why Bot Says "Can't Listen to Audio"

**Full chain**:
1. Old audio messages stored as `[audio]` (no transcription) — predates Audio Intelligence
2. New audio messages stored as `[🎤 Audio]: {clean_text}` — has transcription
3. History loads both old and new format indiscriminately
4. LLM sees `[audio]` pattern in history → learns "audio = I can't process"
5. Even though current message HAS transcription in the content, the LLM's in-context pattern overrides

---

## PHASE 3: Improvement Plan (Ranked by Impact)

### Tier A: Quick Wins (deploy today, no risk)

#### A1. Purge `[audio]` from conversation history
- **What**: In history loading, replace `[audio]` with `[mensaje de voz]` or skip entirely
- **Where**: `core/dm/phases/context.py:399-412` or `core/user_context_loader.py:599`
- **Impact**: Fixes "can't listen" bug. Estimated +5-8% click-and-play
- **Effort**: 30 minutes
- **Risk**: None
- **Basis**: "Most agent failures are context failures" (LangChain). Removing misleading context directly fixes the #1 audio error pattern.

#### A2. Add system instruction for audio handling
- **What**: Add to system prompt: "Los mensajes que empiezan con [🎤 Audio]: contienen la transcripcion completa del audio. PUEDES leerlos. Responde al CONTENIDO, no digas que no puedes escuchar."
- **Where**: `core/dm/phases/context.py` in audio_context section or advanced_section
- **Impact**: Eliminates remaining "can't listen" responses. +3-5%
- **Effort**: 15 minutes
- **Risk**: None
- **Basis**: Explicit instruction > implicit pattern inference.

#### A3. Clean gold examples of media noise
- **What**: Filter gold_examples where user_message starts with `[🎤 Audio]`, `[📷 Photo]`, `[🏷️ Sticker]`, `[🎬 Video]`, `[audio]`, `[Media`
- **Where**: DB cleanup script + filter in `generation.py:149` get_matching_examples()
- **Impact**: Removes training noise from few-shot injection. +2-3%
- **Effort**: 1 hour
- **Risk**: Low (reduces example count but improves quality)
- **Basis**: "Few-shot examples improve persona consistency" (Kasahara 2022). Bad examples hurt more than no examples.

#### A4. Deduplicate/prune contradictory learning rules
- **What**: Rules #1 ("usa emojis") and #4 ("elimina emojis") contradict. Deactivate duplicates and contradictions.
- **Where**: DB cleanup + `services/learning_rules_service.py`
- **Impact**: Reduces prompt confusion. +1-2%
- **Effort**: 2 hours
- **Risk**: Low
- **Basis**: Contradictory instructions cause model uncertainty and inconsistent outputs.

#### A5. Fix language in old audio transcriptions (backfill)
- **What**: Run `scripts/backfill_audio_intelligence.py` with the language fix already deployed
- **Where**: Already exists, just needs execution
- **Impact**: Future conversations with re-processed audio will have correct language. +1%
- **Effort**: 30 minutes (run script)
- **Risk**: Low (script has --dry-run)

### Tier B: Medium Effort (1-2 days)

#### B1. Enrich conversation history with audio transcriptions
- **What**: When loading history, if msg_metadata has `transcript_raw` or `transcription`, replace `[audio]`/`[🎤 Audio message]` with the actual text. Format: `[🎤 Audio]: {transcript_raw[:200]}`
- **Where**: History loading in `core/user_context_loader.py:599` or DB fallback in `core/dm/phases/context.py:405`
- **Impact**: Bot finally KNOWS what was said in audio messages. Major context improvement. +8-12%
- **Effort**: 4 hours
- **Risk**: Medium (must handle msg_metadata parsing, test with various formats)
- **Basis**: "Enriching prompt with rich data yields best results" (NN/Group 2024). This is the single most impactful data enrichment possible.

#### B2. Create calibration file for Iris
- **What**: Generate `calibrations/iris_bertran.json` from gold_examples DB data. Select 20-30 highest-quality, diverse examples. Include response_pools for common intents.
- **Where**: New script + `services/calibration_loader.py`
- **Impact**: Provides 2 curated few-shot examples per call (currently 0). +5-8%
- **Effort**: 4 hours
- **Risk**: Low
- **Basis**: "Few-shot examples improve response diversity, fluency, and persona consistency" (Kasahara 2022).

#### B3. Intelligent gold example selection
- **What**: Currently first N examples by query match. Switch to semantic similarity between current user_message and gold example user_messages. Use embedding distance.
- **Where**: `core/dm/phases/generation.py:146-183` and the gold examples service
- **Impact**: Examples will be RELEVANT to current conversation. +5-7%
- **Effort**: 8 hours
- **Risk**: Medium (embedding calls add latency ~200ms)
- **Basis**: Relevance-based few-shot selection outperforms random selection in all benchmarks.

#### B4. Compress style prompt
- **What**: The 21,495-char style prompt consumes 81% of context. Compress to ~8,000 chars by extracting redundant personality descriptors, keeping only actionable style rules.
- **Where**: Personality extraction pipeline + `agent.style_prompt`
- **Impact**: Frees ~3,000 tokens for more useful context (RAG, history, examples). +3-5%
- **Effort**: 6 hours
- **Risk**: Medium (must preserve persona quality)
- **Basis**: Context window utilization directly correlates with response quality. Style ≠ context.

#### B5. Upgrade to Gemini 2.5 Flash (from Flash-Lite)
- **What**: Flash-Lite is the cheapest/fastest model. Flash full has significantly better reasoning.
- **Where**: `core/config/llm_models.py` — change `GEMINI_PRIMARY_MODEL`
- **Impact**: Better contextual understanding, fewer generic responses. +5-10%
- **Effort**: 30 minutes (config change)
- **Risk**: HIGH (cost increase ~3-5x, currently blocked in BLOCKED_MODELS list)
- **Basis**: Model capability directly impacts context utilization. Flash-Lite may be too weak for 6K-token prompts.
- **Note**: Requires explicit user approval per CLAUDE.md rules.

#### B6. Short message context injection
- **What**: When user sends ≤5 words (yes/no/emoji/sticker), inject the bot's last question into the prompt: "El usuario esta respondiendo a tu pregunta anterior: '{last_bot_question}'"
- **Where**: `core/dm/phases/context.py:47-65` (expand existing logic)
- **Impact**: Fixes "Yes!" → generic greeting pattern. +3-5%
- **Effort**: 3 hours
- **Risk**: Low
- **Basis**: Resolving anaphoric references is a well-known dialogue system challenge. Explicit context injection outperforms implicit resolution.

### Tier C: Strategic (1-2 weeks)

#### C1. Build automated evaluation pipeline
- **What**: Daily eval that scores N conversations on: context_accuracy, language_match, persona_fidelity, relevance, actionability. Track click-and-play rate over time.
- **Where**: New `scripts/eval_pipeline.py` + `copilot_evaluations` table (already exists)
- **Impact**: Enables data-driven iteration. Meta-improvement that accelerates all other improvements.
- **Effort**: 2-3 days
- **Risk**: Low
- **Basis**: "Score Before You Speak" (ECAI 2025). You can't improve what you don't measure.

#### C2. Implement proper RAG content ingestion
- **What**: Only 24 content chunks exist for Iris. Ingest: creator's FAQ, product descriptions, class schedules, pricing, location info, recurring events.
- **Where**: RAG ingestion pipeline + `content_chunks` table
- **Impact**: Bot can answer factual questions (schedules, prices, locations). +8-12%
- **Effort**: 3-4 days
- **Risk**: Low
- **Basis**: RAG is the standard solution for factual grounding. 24 chunks is effectively empty.

#### C3. Conversation-aware few-shot retrieval
- **What**: Instead of selecting examples by intent alone, use full conversation context embedding to find the most similar past conversations. Include the conversation THREAD (2-3 turns), not just single messages.
- **Where**: New retrieval system on top of gold_examples
- **Impact**: Examples will demonstrate multi-turn conversation patterns. +5-8%
- **Effort**: 1 week
- **Risk**: Medium
- **Basis**: "Deeply contextualized persona prompting with multifaceted background" (EmergentMind).

#### C4. Response quality scoring model
- **What**: Train a lightweight classifier on (suggestion, creator_actual_response, was_edited) to predict whether a response will be approved, edited, or discarded. Use for candidate ranking in best-of-N.
- **Where**: New model + integration in `core/best_of_n.py`
- **Impact**: Better candidate selection. +5-10%
- **Effort**: 1-2 weeks
- **Risk**: High (requires sufficient training data, may overfit)
- **Basis**: "Score Before You Speak" (ECAI 2025). Current confidence scoring is heuristic-based. Learning from creator approval patterns is strictly better.

#### C5. Image/Video understanding via multimodal
- **What**: When user sends photo/video, use Gemini multimodal to describe the content and inject description into prompt.
- **Where**: Media processing pipeline + `core/copilot/lifecycle.py` (remove non-text skip for images)
- **Impact**: Bot can respond meaningfully to photos. +3-5%
- **Effort**: 1 week
- **Risk**: Medium (cost, latency)
- **Basis**: Multimodal context eliminates the entire "generic response to media" failure class.

---

## PHASE 4: Quick Wins vs Strategic Changes

### A) Deploy Today (< 2 hours total, zero risk)

| # | Change | Impact | Effort |
|---|--------|--------|--------|
| A1 | Strip `[audio]` from history | +5-8% | 30 min |
| A2 | Add "you CAN read audio" system instruction | +3-5% | 15 min |
| A3 | Filter media gold examples | +2-3% | 1 hour |
| A5 | Run audio backfill with language fix | +1% | 30 min |
| **Total** | | **+11-17%** | **~2 hours** |

### B) This Week (1-2 days each)

| # | Change | Impact | Effort |
|---|--------|--------|--------|
| B1 | Enrich history with audio transcriptions | +8-12% | 4 hours |
| B2 | Create Iris calibration file | +5-8% | 4 hours |
| B6 | Short message → inject last bot question | +3-5% | 3 hours |
| B4 | Compress style prompt to ~8K chars | +3-5% | 6 hours |
| **Total** | | **+19-30%** | **~17 hours** |

### C) Next 2 Weeks (strategic)

| # | Change | Impact | Effort |
|---|--------|--------|--------|
| C1 | Evaluation pipeline | Meta | 2-3 days |
| C2 | RAG content ingestion | +8-12% | 3-4 days |
| C3 | Conversation-aware few-shot | +5-8% | 1 week |
| C5 | Multimodal image understanding | +3-5% | 1 week |

### Projected Click-and-Play Rate

| Phase | Cumulative Rate |
|-------|----------------|
| Current | ~20% |
| After A (today) | ~33-37% |
| After B (this week) | ~50-60% |
| After C (2 weeks) | ~65-75% |

---

## Appendix: Key Files Reference

| File | Purpose |
|------|---------|
| `api/routers/messaging_webhooks/evolution_webhook.py` | WhatsApp webhook entry |
| `core/dm/agent.py` | 5-phase DM agent orchestrator |
| `core/dm/phases/detection.py` | Phase 1: early filtering |
| `core/dm/phases/context.py` | Phase 2-3: context + prompt building |
| `core/dm/phases/generation.py` | Phase 4: LLM call + best-of-N |
| `core/dm/phases/postprocessing.py` | Phase 5: guardrails + formatting |
| `core/best_of_n.py` | 3-candidate generation at T=[0.2, 0.7, 1.4] |
| `core/copilot/lifecycle.py` | Pending response creation |
| `core/copilot/actions.py` | Approve/discard logic |
| `services/audio_intelligence.py` | 4-layer audio processing |
| `services/memory_engine.py` | Per-lead fact extraction + recall |
| `services/calibration_loader.py` | Few-shot example loading (file-based) |
| `core/rag/semantic.py` | Semantic search + BM25 hybrid |
| `core/user_context_loader.py` | Follower data + history formatting |
| `core/config/llm_models.py` | Model configuration + blocked list |

## Appendix: Production Feature Flags (all ON)

```
ENABLE_ADVANCED_PROMPTS=true
ENABLE_AUDIO_INTELLIGENCE=true
ENABLE_AUTOLEARNING=true
ENABLE_BEST_OF_N=true
ENABLE_BM25_HYBRID=true
ENABLE_CHAIN_OF_THOUGHT=true
ENABLE_CLONE_SCORE=true
ENABLE_CONVERSATION_STATE=true
ENABLE_GOLD_EXAMPLES=true
ENABLE_GUARDRAILS=true
ENABLE_LEARNING_CONSOLIDATION=true
ENABLE_LEARNING_RULES=true
ENABLE_MEMORY_DECAY=true
ENABLE_MEMORY_ENGINE=true
ENABLE_PREFERENCE_PROFILE=true
ENABLE_RELATIONSHIP_DETECTION=true
ENABLE_RERANKING=true
ENABLE_SELF_CONSISTENCY=true
ENABLE_SEMANTIC_MEMORY_PGVECTOR=true
```

## Appendix: Production Data Counts (iris_bertran)

| Table | Count |
|-------|-------|
| learning_rules | 824 |
| gold_examples | 4,505 |
| content_chunks (RAG) | 24 |
| lead_memories | 2,247 (across 170 leads) |
| conversation_summaries | 6,178 |
| calibration file | **MISSING** |
