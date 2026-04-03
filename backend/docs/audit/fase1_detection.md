# Audit Fase 1: Detection Phase (5 Systems)

**Date:** 2026-03-31
**Auditor:** Claude Opus 4.6
**Status:** 9 bugs FIXED, 12 remaining (documented below)
**Files audited:**
- `core/dm/phases/detection.py` (orchestrator)
- `core/sensitive_detector.py`
- `core/frustration_detector.py`
- `core/context_detector/` (detectors.py, models.py, orchestration.py)
- `services/response_variator_v2.py`
- `services/response_variator.py`
- `models/response_variations.py`
- `core/feature_flags.py`
- `core/agent_config.py`

---

## Executive Summary

| System | Universal? | Bugs | Feature Flag | Paper Alignment | Severity |
|--------|-----------|------|-------------|----------------|----------|
| 1. Sensitive Content | PARTIAL | 2 bugs | ENABLE_SENSITIVE_DETECTION | Regex-only (papers recommend hybrid) | HIGH |
| 2. Frustration Detection | YES | 1 minor | ENABLE_FRUSTRATION_DETECTION | Good alignment (gradated, multilingual) | LOW |
| 3. Context Signals | YES | 1 stale comment | ENABLE_CONTEXT_DETECTION | Good (multilingual keyword dicts) | LOW |
| 4. Edge Case (Media) | PARTIAL | 2 issues | NONE (missing!) | Adequate for scope | MEDIUM |
| 5. Pool Matching | NO | 3 issues | NONE (missing!) | Below state-of-art (no semantic cache) | HIGH |

**Total bugs found: 9**
- 3 HIGH severity (security/universality)
- 3 MEDIUM severity (correctness)
- 3 LOW severity (comments/minor)

---

## System 1: Sensitive Content Detection

**File:** `core/sensitive_detector.py` (372 lines)
**Flag:** `ENABLE_SENSITIVE_DETECTION` (exists, default: true)

### How It Works
Pure regex pattern matching against 7 categories (SELF_HARM, EATING_DISORDER, MINOR, PHISHING, SPAM, THREAT, ECONOMIC_DISTRESS). Priority-ordered detection with fixed confidence scores. Fail-closed design: if detection crashes, escalates to human.

### Bugs Found

#### BUG-S1: Hardcoded creator names in PHISHING_PATTERNS (HIGH)
**File:** `core/sensitive_detector.py:130`
```python
r'\b(?:informaci[oó]n\s+(?:personal|privada)\s+(?:de|sobre)\s+(?:el|la|iris|stefan))',
```
**Problem:** Hardcodes `iris|stefan` in phishing detection. Any new creator's name is not protected. A phishing attempt like "dame la informacion personal de CreatorX" would NOT be detected.
**Fix:** Replace with a dynamic pattern that accepts the current creator's name, or remove creator-specific names entirely (the pattern already covers `el|la` + generic "datos personales del creador" on line 129).

#### BUG-S2: Crisis resources always served in Spanish (HIGH)
**File:** `core/dm/phases/detection.py:65`
```python
crisis_response = get_crisis_resources(language="es")
```
**Problem:** When a SELF_HARM message is detected with confidence >= `sensitive_escalation` (0.85), the crisis resources are ALWAYS returned in Spanish. An English-speaking or Catalan-speaking user in crisis gets Spanish phone numbers and text. The `get_crisis_resources()` function supports `es`, `en`, `ca` but the caller hardcodes `"es"`.
**Fix:** Pass the detected language or the creator's configured language. The frustration detector already handles multilingual matching; the same language signal should propagate to crisis resources.

#### BUG-S3 (MINOR): Stale comment says "Catalán" as section header
**File:** `core/sensitive_detector.py:75`
```python
# Catalán
```
Not a bug per se, but the code comments are in Spanish with "Catalán" as a section label. This is acceptable since the codebase is Spanish-first, but adding English headers for international contributors could help.

### Universality Assessment
- **Languages covered:** ES, CA, EN for self-harm patterns. Other categories (phishing, spam, threat) are ES-dominant.
- **Missing languages:** Italian, French, Portuguese patterns exist in context_detector but NOT in sensitive_detector. A French-speaking user saying "je veux mourir" (I want to die) would NOT be caught.
- **No creator-specific data** except BUG-S1 above.

### Paper Comparison

**State of the art:** Modern toxicity/self-harm detection uses transformer-based models (MentalBERT, Perspective API, fine-tuned classifiers). These achieve 90%+ F1 on crisis content. Regex achieves ~70-80% recall with high false-negative risk due to paraphrasing ("ya no aguanto mas", "esto no tiene sentido" evade patterns).

**References:**
- [Perspective API](https://perspectiveapi.com/) — Google's multilingual toxicity classifier. Free API, supports 20+ languages.
- [LLM-based suicide intervention chatbot (Frontiers, 2025)](https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2025.1634714/full) — GPT-4 based, graduated response protocols.
- [Sensitive Content Classification (arXiv 2411.19832)](https://arxiv.org/html/2411.19832v2) — Holistic resource showing ML outperforms keywords.
- [ML for detecting eating disorders (Frontiers, 2024)](https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2024.1319522/full) — Systematic review showing NLP/ML superiority over keyword lists.

**Recommendation:** Keep regex as fast first-pass (0ms latency, no API cost), but add Perspective API or a local lightweight classifier as second-pass for messages that don't trigger regex but are longer than ~15 words. This is especially important for SELF_HARM where false negatives have real safety consequences.

### Strengths
- Fail-closed design (line 76-90) is excellent security practice
- Priority ordering (self_harm > threat > phishing > spam) is correct
- Fixed high confidence (0.95 for self_harm) avoids threshold tuning issues
- Pattern coverage for ES self-harm is comprehensive

---

## System 2: Frustration Detection

**File:** `core/frustration_detector.py` (367 lines)
**Flag:** `ENABLE_FRUSTRATION_DETECTION` (exists, default: true)

### How It Works
Multilingual keyword matching (ES, CA, EN) with a gradated 0-3 level system. Uses working-string dedup to prevent double-counting. Profanity amplifies existing signals (x1.3) but does NOT trigger alone. History analysis adds +0.2 for escalating patterns across last 3 messages.

### Bugs Found

#### BUG-F1: Duplicate flag declaration (MEDIUM)
**File:** `core/dm/agent.py:87` AND `core/dm/phases/detection.py:37`
```python
# agent.py:87
ENABLE_FRUSTRATION_DETECTION = os.getenv("ENABLE_FRUSTRATION_DETECTION", "true").lower() == "true"
# detection.py:37
ENABLE_FRUSTRATION_DETECTION = os.getenv("ENABLE_FRUSTRATION_DETECTION", "true").lower() == "true"
```
**Problem:** The flag is declared in both files AND in `core/feature_flags.py:30`. Three declarations of the same flag. If someone changes the env var, all three react the same way, but it's maintenance debt. The `core/feature_flags.py` singleton should be the single source of truth.
**Fix:** Import from `core.feature_flags.flags.frustration_detection` in both files.

### Universality Assessment
- **Fully universal.** No hardcoded creator names, no hardcoded personas.
- **Languages:** ES, CA, EN with extensible structure.
- **Missing:** IT, FR, PT not covered (context_detector covers 6 languages, frustration only 3).

### Paper Comparison

**State of the art:** Modern frustration detection uses BERT+BiLSTM hybrids achieving <200ms latency with emotion classification. Our regex approach is faster (sub-1ms) but less nuanced.

**References:**
- [BERT BiLSTM for emotion detection (Nature Scientific Reports, 2025)](https://www.nature.com/articles/s41598-025-15501-y) — Hybrid model, real-time, 25% CSAT improvement.
- [Chatbot sentiment analysis reducing escalations by 40% (Medium)](https://medium.com/@webelightsolutions/how-ai-chatbots-with-sentiment-analysis-can-reduce-support-escalations-by-40-7ac7b8cf9f4a)

**Our approach is BETTER than papers suggest for this use case because:**
1. We don't need emotion classification — we need binary frustration signal
2. Sub-1ms latency vs 200ms for transformer models
3. The gradated 0-3 level system with history tracking is a pragmatic design
4. Profanity-as-amplifier (not trigger) is linguistically correct for ES/CA informal speech

### Strengths
- Working-string dedup (line 221) prevents double-counting — clever
- Profanity amplifier design (line 229-236) is linguistically sound
- Escalation patterns (line 26-37) always force level 3 — correct
- History-based escalation detection (line 239-257)
- In-memory conversation history with 20-message cap (line 315)

---

## System 3: Context Signals

**Files:** `core/context_detector/` (4 files, ~550 lines total)
**Flag:** `ENABLE_CONTEXT_DETECTION` (exists, default: true)

### How It Works
Detects B2B context, user names, meta-messages ("ya te lo dije"), corrections, objection types (price/time/trust/need), and interest level. All signals are factual observations injected into the Recalling block — no behavior instructions.

### Bugs Found

#### BUG-C1: Stale NOTE in detection.py (LOW)
**File:** `core/dm/phases/detection.py:108`
```python
# NOTE: context_signals stored on result but not consumed in generation phase
```
**Problem:** This comment is WRONG. Context signals ARE consumed in `core/dm/phases/context.py:712`:
```python
_csig = getattr(detection, "context_signals", None)
```
The context notes are extracted and injected into the prompt. The stale comment could mislead a developer into thinking this code is dead.
**Fix:** Remove or correct the NOTE.

#### BUG-C2: Stale NOTE about intent_override (LOW)
**File:** `core/dm/phases/detection.py:53`
```python
cognitive_metadata["intent_override"] = "media_share"  # NOTE: written, not consumed downstream
```
**Problem:** `media_share` IS referenced in `core/conversation_mode.py:28` and `core/lead_categorizer.py:70`. And `is_media_placeholder` IS consumed in `core/dm/phases/context.py:661`. The NOTE is misleading.
**Fix:** Update or remove the NOTE.

### Universality Assessment
- **Excellent universality.** 6 languages (ES, CA, EN, IT, FR, PT) with extensible dict structure.
- **No hardcoded creator data.** All keyword dicts are language-keyed, not creator-keyed.
- **Context notes are in Spanish** (`build_context_notes()` in models.py:83-114 generates notes like "Este lead parece representar una empresa/marca"). These notes go into the Recalling block which is Spanish. This is acceptable if the system prompt is always Spanish, but may need i18n if the system expands.

### Paper Comparison

The B2B detection, objection classification, and meta-message detection don't have direct paper equivalents because they're domain-specific to conversational commerce. The approach of using factual observations (not behavior instructions) aligns with best practices from persona-based chatbot research:

- [Persona-Aware LLM Framework (ACL Findings, 2025)](https://aclanthology.org/2025.findings-acl.5.pdf) — Separating factual context from behavior.
- [EmoAgent: Safeguarding Human-AI Interaction (EMNLP, 2025)](https://aclanthology.org/2025.emnlp-main.594.pdf)

### Strengths
- Clean separation: detectors produce facts, Doc D defines behavior
- Language-extensible via dict structure (add a key, done)
- Dead stubs for backward compat (frustration, sarcasm) prevent import crashes
- B2B detection with company name extraction is sophisticated

---

## System 4: Edge Case Detection (Media Placeholders)

**File:** `core/dm/phases/detection.py:16-33` (MEDIA_PLACEHOLDERS set)
**Flag:** **NONE** (missing!)

### How It Works
A static set of 22 known placeholder strings sent by Instagram/WhatsApp when users share media. If the message matches exactly (case-insensitive, stripped), it sets `metadata["is_media_placeholder"] = True` and `cognitive_metadata["intent_override"] = "media_share"`.

### Bugs Found

#### BUG-E1: No feature flag (MEDIUM)
**Problem:** No `ENABLE_MEDIA_DETECTION` or `ENABLE_EDGE_CASE_DETECTION` flag exists. This system cannot be disabled for ablation testing or if it causes issues.
**Fix:** Add `ENABLE_MEDIA_PLACEHOLDER_DETECTION` to `core/feature_flags.py`.

#### BUG-E2: Incomplete language coverage (MEDIUM)
**File:** `core/dm/phases/detection.py:16-33`
```python
MEDIA_PLACEHOLDERS = {
    "sent an attachment", ...  # English
    "envió un archivo adjunto", ...  # Spanish
}
```
**Problem:** Only EN and ES placeholders. Missing:
- **Catalan:** "va enviar un fitxer adjunt", "va enviar una foto", "va compartir un reel"
- **French:** "a envoyé une pice jointe", "a envoyé une photo"
- **Italian:** "ha inviato un allegato", "ha inviato una foto"
- **Portuguese:** "enviou um anexo", "enviou uma foto"

These are the actual strings Instagram sends in localized versions. If a user's Instagram app is in Catalan or French, the placeholder won't be caught, and the LLM will see "va enviar una foto" as normal text.

**Fix:** Add platform-verified placeholder strings for all supported languages.

### Universality Assessment
- **Partial.** EN + ES only. No IT/FR/PT/CA.
- **No creator-specific data.** Pure platform strings.

### Paper Comparison

No direct academic papers on media placeholder detection (it's a platform engineering concern, not NLP). However, edge case handling research from 2024 emphasizes:
- [Edge Cases in AI Chatbots (Akhtar Solutions)](https://www.akhtarsitsolutions.com/agentic-ai-chatbots-edge-cases/) — Testing edge cases reduces complaints by 80%.
- [10 Critical Edge Cases for Voice AI (Chanl)](https://www.chanl.ai/blog/critical-edge-cases-voice-ai) — Media handling is a known edge case category.

**Our approach is sound:** exact-match against known strings is the correct technique (no NLP needed). The implementation just needs broader language coverage.

---

## System 5: Pool Matching (POOL_CONFIDENCE)

**Files:**
- `services/response_variator_v2.py` (653 lines) — main implementation
- `services/response_variator.py` (253 lines) — legacy v1
- `models/response_variations.py` — Stefan-specific pools
**Flag:** **NONE** (missing!)
**Threshold:** `AGENT_THRESHOLDS.pool_confidence = 0.8` (configurable via env)

### How It Works
Fast-path response for simple messages (<=80 chars). Classifies message into categories (greeting, confirmation, thanks, laugh, etc.) and returns a pre-written response from a pool. Uses TF-IDF for context-aware selection, conversation-level dedup, question-aware targeting, and extraction pools from Doc D personality calibrations.

### Bugs Found

#### BUG-P1: Hardcoded Stefan fallback pools (HIGH)
**File:** `services/response_variator_v2.py:114-179`
```python
fallback = {
    "greeting": ["Hola! ...", "Hola hermano!", ...],
    "meeting_request": ["Imposible bro, me explota la agenda jaja", ...],
    ...
}
```
**Problem:** When no calibration exists for a creator, the fallback pools use Stefan's persona ("hermano", "bro", "crack", "Imposible bro"). A female wellness creator would get masculine-coded pool responses. The comment on line 186-187 acknowledges this:
```python
# Stefan's fallback entries. Calibration pools are creator-specific
# and mixing in generic "hermano/bro" responses breaks persona.
```
But the fallback still fires when no calibration exists.

**Fix:** Fallback pools should be neutral/generic (no gendered language, no persona-specific slang). Or: disable pool matching entirely when no calibration exists for a creator.

#### BUG-P2: Legacy v1 ResponseVariator uses STEFAN_RESPONSE_POOLS (MEDIUM)
**File:** `services/response_variator.py:11,18`
```python
from models.response_variations import STEFAN_RESPONSE_POOLS
self.pools = pools or STEFAN_RESPONSE_POOLS
```
**Problem:** The legacy v1 variator is hardcoded to Stefan. If any code path still uses v1 (import check needed), it will always return Stefan responses.

**Fix:** Verify if v1 is still imported anywhere. If not, mark as deprecated/delete.

#### BUG-P3: No feature flag for pool matching (MEDIUM)
**Problem:** Pool matching cannot be disabled independently. The only way to disable it is to remove `response_variator` from the agent, which requires code changes.
**Fix:** Add `ENABLE_POOL_MATCHING` to `core/feature_flags.py`.

#### BUG-P4: Category detection is Spanish/Catalan-only (MEDIUM)
**File:** `services/response_variator_v2.py:396-525`
```python
meeting_triggers = ["quedar", "quedamos", "vernos", ...]  # Spanish only
greetings = ["hola", "hey", "buenas", ...]  # Spanish + English basic
cancel_triggers = ["no podre venir", "no puedo venir", "no puc venir", ...]  # ES + CA only
```
**Problem:** Category detection keywords are predominantly Spanish/Catalan. An English-only user saying "let's meet up" won't trigger `meeting_request`. "sounds great!" won't trigger `celebration`.

**Fix:** Add EN/IT/FR/PT triggers for each category, similar to how context_detector uses multilingual dicts.

#### BUG-P5: 30% random multi-bubble injection (LOW)
**File:** `core/dm/phases/detection.py:139`
```python
if _rng.random() < 0.30:
```
**Problem:** 30% of pool matches randomly attempt multi-bubble. This is not configurable and the randomness makes behavior non-deterministic during testing.
**Fix:** Make the multi-bubble probability configurable via env or calibration.

### Universality Assessment
- **NOT universal.** Stefan-specific fallbacks, Spanish-dominant category detection.
- The extraction pool system (v12) IS universal — it loads per-creator from Doc D.
- The problem is the fallback layer when no extraction exists.

### Paper Comparison

**State of the art:** Modern dialogue systems use semantic caching (GPTCache, vector-similarity matching) to identify when a pre-computed response can be reused. Our TF-IDF approach is a lightweight version of this.

**References:**
- [GPTCache: Semantic Cache for LLM Applications (ResearchGate)](https://www.researchgate.net/publication/376404523_GPTCache_An_Open-Source_Semantic_Cache_for_LLM_Applications_Enabling_Faster_Answers_and_Cost_Savings) — Embedding-based matching.
- [Semantic Caching for LLM Applications (JSAER, 2024)](https://jsaer.com/download/vol-11-iss-9-2024/JSAER2024-11-9-155-164.pdf)

**Our approach is pragmatic:** TF-IDF + category detection for short messages (<80 chars) is appropriate. These are social/conversational messages where a pool response is adequate. The real gap is universality of the fallback pools, not the matching algorithm.

### Strengths
- Conversation-level dedup (v10.3) prevents repetition
- Question-aware selection (v9.3) targets real question frequency
- Extraction pools from Doc D (v12) are fully creator-specific
- Sales context exclusion (line 498-499) prevents pool responses for purchase intents
- 80-char length guard (detection.py:125) correctly limits pool to short messages

---

## Missing Feature Flags Summary

| System | Flag Needed | Priority |
|--------|------------|----------|
| Media Placeholder Detection | `ENABLE_MEDIA_PLACEHOLDER_DETECTION` | MEDIUM |
| Pool Matching | `ENABLE_POOL_MATCHING` | HIGH |
| Multi-bubble probability | `POOL_MULTI_BUBBLE_RATE` (float, default 0.30) | LOW |

---

## Consolidated Bug List (by severity)

### HIGH
1. **BUG-S1:** Hardcoded `iris|stefan` in PHISHING_PATTERNS (`sensitive_detector.py:130`)
2. **BUG-S2:** Crisis resources always served in Spanish (`detection.py:65`)
3. **BUG-P1:** Stefan fallback pools fire for all creators (`response_variator_v2.py:114-179`)

### MEDIUM
4. **BUG-F1:** Triplicate flag declaration for ENABLE_FRUSTRATION_DETECTION
5. **BUG-E1:** No feature flag for media placeholder detection
6. **BUG-E2:** Media placeholders missing CA/FR/IT/PT languages
7. **BUG-P2:** Legacy v1 variator hardcoded to STEFAN_RESPONSE_POOLS
8. **BUG-P3:** No feature flag for pool matching
9. **BUG-P4:** Category detection keywords Spanish/Catalan-only

### LOW
10. **BUG-C1:** Stale NOTE says context_signals not consumed (it is)
11. **BUG-C2:** Stale NOTE says intent_override not consumed (it is)
12. **BUG-P5:** 30% multi-bubble rate not configurable

---

## Fixes Applied (2026-03-31)

### HIGH — All 3 fixed
1. **BUG-S1 FIXED:** Phishing regex now matches `creador[a]?|due[ñn][oa]|propietari[oa]|admin` instead of `iris|stefan`
2. **BUG-S2 FIXED:** Crisis language derived from `agent.personality["dialect"]` via `_DIALECT_TO_LANG` mapping
3. **BUG-P1 FIXED:** Fallback pools neutralized (no hermano/bro/crack/posta). `get_pools_for_creator` returns empty when extraction record exists but category missing.

### MEDIUM — All 3 fixed
4. **BUG-E1 FIXED:** Added `ENABLE_MEDIA_PLACEHOLDER_DETECTION` flag
5. **BUG-P3 FIXED:** Added `ENABLE_POOL_MATCHING` flag
6. **BUG-F1 FIXED:** Triplicate flags consolidated to `core.feature_flags` singleton

### Re-audit findings — 3 additional bugs fixed
7. **ReDoS FIXED:** `sensitive_detector.py:161,169` — `.*` replaced with `.{0,80}` / `.{0,60}` bounded quantifiers
8. **Memory leak FIXED:** `frustration_detector.py` — Conversation history capped at 5000 entries with FIFO eviction
9. **Memory leak FIXED:** `response_variator_v2.py` — Used responses dict capped at 5000 conversations with FIFO eviction

### Verification
- All 6 modified files pass `ast.parse` syntax check
- Smoke tests: 7/7 pass (before AND after)
- Manual tests: phishing regex catches generic patterns, rejects false positives
- Manual tests: crisis resources return correct language for catalan/english/spanish
- Manual tests: no persona-specific words in fallback pools
- Manual tests: ReDoS attack completes in <1ms (was unbounded)
- Manual tests: memory cap holds at 5000 entries

---

## Remaining Issues (not fixed, backlog)

### Medium-term (next sprint)
1. **Expand media placeholders** to CA/FR/IT/PT.
2. **Expand pool category detection** to multilingual.
9. **Evaluate Perspective API** as secondary classifier for sensitive content.
10. **Clean up stale NOTEs** (BUG-C1, BUG-C2).

### Long-term (backlog)
11. **Add FR/IT/PT patterns to sensitive_detector.py** (currently ES/CA/EN only).
12. **Add FR/IT/PT patterns to frustration_detector.py** (currently ES/CA/EN only).
13. **Deprecate/remove v1 ResponseVariator** if unused.
14. **Investigate semantic caching** (embedding-based pool matching vs TF-IDF).

---

## Paper References

### Toxicity / Sensitive Content Detection
- [Perspective API](https://perspectiveapi.com/) — Free multilingual toxicity classifier, 20+ languages
- [Sensitive Content Classification (arXiv 2411.19832)](https://arxiv.org/html/2411.19832v2) — Holistic evaluation showing ML > keywords
- [ML for Eating Disorder Detection (Frontiers Psychiatry, 2024)](https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2024.1319522/full)
- [LLM-based Suicide Intervention Chatbot (Frontiers Psychiatry, 2025)](https://www.frontiersin.org/journals/psychiatry/articles/10.3389/fpsyt.2025.1634714/full)
- [Regex vs AI Detection (Nightfall AI)](https://www.nightfall.ai/blog/regex-vs-ai-based-detection)

### Frustration / Emotion Detection
- [BERT BiLSTM for Emotion Detection (Nature Sci Reports, 2025)](https://www.nature.com/articles/s41598-025-15501-y)
- [Chatbot Sentiment Analysis Reducing Escalations (Medium)](https://medium.com/@webelightsolutions/how-ai-chatbots-with-sentiment-analysis-can-reduce-support-escalations-by-40-7ac7b8cf9f4a)

### Fast-Path Caching / Pool Responses
- [GPTCache: Semantic Cache (ResearchGate)](https://www.researchgate.net/publication/376404523_GPTCache_An_Open-Source_Semantic_Cache_for_LLM_Applications_Enabling_Faster_Answers_and_Cost_Savings)
- [Semantic Caching for LLMs (JSAER 2024)](https://jsaer.com/download/vol-11-iss-9-2024/JSAER2024-11-9-155-164.pdf)

### Edge Cases / Persona Safety
- [EmoAgent: Safeguarding Human-AI Interaction (EMNLP 2025)](https://aclanthology.org/2025.emnlp-main.594.pdf)
- [Edge Cases in AI Chatbots (Akhtar Solutions)](https://www.akhtarsitsolutions.com/agentic-ai-chatbots-edge-cases/)
- [Persona-Aware LLM Framework (ACL Findings 2025)](https://aclanthology.org/2025.findings-acl.5.pdf)
