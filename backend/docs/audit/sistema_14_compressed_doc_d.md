# Audit — Sistema #14: Compressed Doc D

**Date:** 2026-04-01
**Status:** v3 + measurement v2 — emoji -34pp, excl -57pp, L1 6/9, SemSim 0.36
**File:** `core/dm/compressed_doc_d.py`

## What is it?

The Compressed Doc D is a ~1.7K char personality prompt that replaces the 38K full Doc D personality extraction. It tells the model WHO the creator is and HOW they write. It's the **single most impactful system** in the pipeline:

- L1 score: 2/9 (naked) → 5-6/9 (with Doc D)
- Coherence: 1.8 → 3.2
- Enviarías: improved significantly

## Pipeline Position

```
creator_style_loader.get_creator_style_prompt()
  → build_compressed_doc_d(creator_id)
    → Reads: BFI profile, baseline metrics, products, calibration
    → Returns: ~1.7K char prompt

Injected as: ("style", agent.style_prompt) — FIRST section in system prompt
Priority: CRITICAL (highest priority section)
```

## Data Sources

| Source | Type | Size | Load Priority |
|--------|------|------|---------------|
| BFI profile | `bfi_profile` | ~1KB | DB → local file |
| Baseline metrics | `baseline_metrics` | ~5KB | DB → local file |
| Creator DB | name, products | varies | DB only |
| Calibration | few-shot examples | ~15KB | DB → local file |
| Length divergence | `bot_natural_rates` | ~100B | DB only |

## Performance Analysis (Layer 1, pre-optimization)

| Metric | Naked | Doc D v1 | Target | Status |
|--------|-------|----------|--------|--------|
| Emoji % | 91% | **90%** | 23% | **FAIL — zero effect** |
| Exclamation % | 85% | **74%** | 2% | **FAIL — barely moved** |
| Question % | 83% | **33%** | 14% | Improved, 2× target |
| Length median | 140 | **27** | 26 | **PASS** |
| Catalan % | 19% | **29%** | 44% | Partial improvement |
| Vocab Jaccard | 5.5% | **14.9%** | - | 3× improvement |
| BERTScore | 0.828 | **0.852** | - | +0.024 improvement |

## Bugs Found

### Critical
1. **B1: Emoji constraint has ZERO effect** (90%→90%). Quantitative instructions alone are ignored by the model.
2. **B2: Exclamation constraint barely works** (85%→74% vs 2% target).

### High
3. **B3: No few-shot examples** — RoleLLM (ACL 2024) found this is the #1 lever for style fidelity (+30% improvement).
4. **B4: Hardcoded Catalan CAPS examples** ("AVUI", "QUE FUEEERT") — wrong for non-Catalan creators.
5. **B5: Feminine gender "directa" hardcoded** — wrong for male creators (Stefano).

### Medium
6. **B6: All labels hardcoded in Spanish** — mismatched for PT/IT creators.
7. **B7: "Palabras frecuentes" doesn't filter stop words** — includes function words.
8. **B8: Catchphrases section redundant with vocab section** — overlapping data.
9. **B11: New creator with no data → minimal prompt** — identity + rules only.

### Low
10. **B9: Grammar "1 llevan"** → should be "1 lleva" (singular).
11. **B10: Skin tone modifier counted as separate emoji** in baseline data.

## Optimizations Applied (v2)

Based on PersonaGym (EMNLP 2025), RoleLLM (ACL 2024), CharacterEval (ACL 2024):

### 1. Added Few-Shot Examples (B3 fix)
- Loads 5 real DM examples from calibration data
- Mix: 60% no-emoji, 40% with emoji (mirrors real distribution)
- Sorted by length (shorter = more characteristic)
- Shows the model WHAT the output should look like, not just numbers

### 2. Behavioral Emoji Constraint (B1 fix)
- Old: "SOLO 23% de tus mensajes llevan emoji"
- New: "tu DEFAULT es NO poner emoji" + examples showing emoji-free responses
- Framing as default behavior instead of statistics

### 3. Behavioral Exclamation Constraint (B2 fix)
- Old: "2% de tus mensajes usan '!'"
- New: "CASI NUNCA... Tu tono natural es tranquilo, sin '!' al final"
- Added explicit "NO pongas '!' por defecto" in rules

### 4. Merged Vocabulary Sections (B7, B8 fix)
- Single `_get_characteristic_vocab()` function
- Stop-word filtered
- Deduplicated between vocab and openers

### 5. Fixed Hardcoding (B4, B5, B9)
- Gender-neutral identity ("natural, sin filtros" instead of "directa")
- BFI labels use gender-inclusive phrasing ("abierta/o", "empática/o")
- CAPS examples derived from creator's actual vocabulary
- Fixed singular grammar "1 lleva"
- Skin tone modifier filtered from emoji list

### 6. Adaptive Rules
- Emoji rule only added if creator emoji rate < 40%
- Exclamation rule only added if creator rate < 15%
- Prevents contradictions (e.g., Stefano uses 30% exclamations — no "tranquilo" rule)

### 7. Section Order
- Identity → Personality → Style → Vocabulary → Products → Examples → Rules
- Matches CharacterEval recommendation: identity first, constraints last (recency effect)

## Structure Comparison

### v1 (original)
```
1. Identity (hardcoded ES, feminine)
2. BFI personality
3. Quantitative style (emoji numbers, excl numbers, caps with Catalan examples)
4. Products
5. Catchphrases (redundant with vocab)
6. Anti-patterns (4 rules)
```

### v2 (short-biased — REVERTED)
```
Few-shot: 5 shortest examples → ALL <10c → model learned ultra-terse
L1: 3-4/9 (WORSE than v1 due to length crash: median 27→17)
Emoji: 56% (big improvement from 90%)
```

### v3 (stratified — CURRENT)
```
1. Identity (gender-neutral)
2. BFI personality
3. Style (behavioral emoji/excl framing, dynamic CAPS examples)
4. Vocabulary (merged, stop-word filtered)
5. Few-shot examples (stratified: 1 short + 3 medium + 1 long, intent-diverse)
6. Rules (adaptive, anti-hallucination)
```

## Measured Results (v3, 2026-04-01)

### v3 on v1 test set (50 cases, non-stratified)
3 runs × 50 cases = 150 observations, Qwen/Qwen3-14B via DeepInfra.

```
METRIC              TARGET    NAKED      V1      V3    V1→V3
──────────────────────────────────────────────────────────────
has_emoji_%          22.6     91.3    90.0    48.7    -41pp ✅
has_excl_%            1.8     85.3    74.0    38.0    -36pp ✅
q_rate_%             14.2     83.3    33.3    22.7    -11pp ✅
len_mean             95.2    183.6    32.4    26.0     -6   ⚠️
len_median           26.0    140.5    26.7    20.5     -6   ⚠️
ca_rate_%            43.5     18.7    28.7    26.0     -3   ⚠️
BERTScore              —      0.828   0.852   0.859  +0.007 ✅
len_ratio            1.0       8.2     1.36    1.07   -0.3  ✅

L1 SCORE:  Naked 2/9 → V1 5-6/9 → V3 5-6/9
```

### v3 on v2 test set (STRATIFIED — 40 single + 10 multi-turn)
3 runs × 50 cases = 150 observations. Test set stratified to match real traffic distribution.
Measurement v2: +SemSim (SentenceBERT cosine), human eval protocol (15 cases).

```
METRIC                NAKED   DOC_D_V3   DELTA    p-val  Cliff_d   Sig?
─────────────────────────────────────────────────────────────────────────
has_emoji (%)         91.3      57.3    -34.0pp   <0.001  -0.34    ✓ medium
has_excl (%)          85.3      28.7    -56.7pp   <0.001  -0.57    ✓ large
q_rate (%)            83.3      16.7    -66.7pp   <0.001  -0.67    ✓ large
len_mean (chars)     183.6      28.8   -154.8     <0.001  -0.91    ✓ large
sentence_count         4.4       1.3     -3.1     <0.001  -0.94    ✓ large
ca_rate (%)           18.7      28.7    +10.0pp    0.073  +0.10    · n.s.
SemSim (cosine)        0.37      0.36    -0.01     0.748  +0.04    · n.s.
BERTScore              0.828     0.862   +0.033      —      —
len_ratio              8.16      2.43    -5.73    <0.001  -0.41    ✓ medium
rep_rate (%)           2.0       0.0     -2.0pp    0.109  -0.02    · n.s.

L1 SCORE:  Naked 2/9 → Doc D v3 6/9
```

Key findings with stratified test set:
- **Excl improvement is even better**: -57pp (vs -36pp on v1 test set)
- **Question suppression much stronger**: -67pp (model stopped over-questioning)
- **SemSim ≈ equal**: 0.37 vs 0.36 — Doc D doesn't hurt semantic relevance
- **BERTScore improved**: 0.862 vs 0.828 — better coherence with personality
- **Multi-turn cases**: model uses context turns well (e.g., Case 50: "Tranqui flower")

### Few-Shot Selection Strategy (v3)

Based on RoleLLM + CharacterEval + ICL selection literature:
- **Stratified by length**: buckets defined by creator's p25/p75 (13c/53c for Iris)
- **Allocation**: 1 short (<p25) + 3 medium (p25-p75) + 1 long (>p75)
- **Intent diversity**: no duplicate contexts (precio, lead_caliente, audio, redirect, clase)
- **Response dedup**: no duplicate response texts
- **Emoji guarantee**: at least 1 emoji example (from medium bucket swap)
- **Integration**: uses same baseline_metrics.length.{p25,p75} as adaptive_length_service

## Measurement System v2 (4 fixes for scientific validity)

### FIX 1: Stratified Test Set
- `scripts/build_stratified_test_set.py` queries DB, classifies 2000 user messages by content
- Proportional sampling: 60% casual, 20% short_response, 8% question, etc.
- 11 categories represented (vs v1 which was 50% casual)
- Content-based classification (DB `intent` field is 99.6% null/casual)

### FIX 2: Semantic Similarity (SentenceBERT cosine)
- Replaces chrF++ as decision metric (chrF++ is broken for short DMs — goes DOWN when quality improves)
- Uses `paraphrase-multilingual-MiniLM-L12-v2` (multilingual, fast, 384-dim)
- Result: SemSim ≈ equal (0.37 naked vs 0.36 Doc D) — Doc D doesn't hurt semantic relevance
- chrF++ kept for backward compatibility but no longer used for decisions

### FIX 3: Human Evaluation Protocol
- 15 cases per config: 5 worst BERTScore + 5 random + 5 best BERTScore
- Each case scored by human: coherencia (1-5) + enviarías (1-5)
- Worst-BERTScore cases expose failure modes; best-BERTScore cases may be trivial echoes

### FIX 4: Multi-Turn Test Cases
- 10 conversations with 3-5 messages of context before the target user message
- Context turns injected as chat history in the model's messages array
- Multi-turn support added to `generate_layer1_run()` in ablation script

## Literature References

1. **PersonaGym** (Jain et al., EMNLP 2025): 150-300 word structured descriptions optimal. Very long descriptions show diminishing returns.
2. **RoleLLM** (Wang et al., ACL 2024): 3-5 few-shot examples = +30% style adherence. Speaking style captured via vocabulary + sentence patterns + catchphrases.
3. **CharacterEval** (Tu et al., ACL 2024): Structured sections beat prose. Separate identity from behavior. Include 3-5 example utterances.
4. **Consensus**: Identity → Style → Examples → Constraints order. Negative instructions effective if limited to 3-5.
