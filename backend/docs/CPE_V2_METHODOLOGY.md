# CPE v2 — Clonnect Persona Evaluation Methodology

**Version**: 2.0
**Date**: 2026-03-31
**Author**: Manel Bertran (research lead)
**Status**: Active

---

## 1. Problem Statement

CPE v1 relied on LLM-as-judge (Prometheus 7B, GPT-4o-mini) for qualitative evaluation. This produced unreliable results in Spanish/Catalan:

- **Fleiss' Kappa ≈ 0.3** for LLM judges in non-English languages (Fu et al., EMNLP 2025)
- **σ = 0.40** across runs with GPT-4o-mini judge (our own data, 15 test cases)
- **ρ = 0.375** correlation with human judgment (our GPT-4o-mini vs Manel assessment)
- Prometheus 7B makes grammatical errors in Catalan, conflating language errors with persona fidelity
- Claude 3.5 Sonnet focuses on grammar instead of intent when evaluating Catalan text

**Consequence**: Ablation decisions based on CPE v1 Level 2 scores were optimizing noise, not signal.

---

## 2. Design Principles

1. **Reproducibility** — Same inputs → same outputs. No stochastic judges for decision-making.
2. **Zero cost** — All daily iteration metrics run locally, $0.
3. **Ground truth anchored** — Every metric compares against real creator data (7,059 messages).
4. **Statistically rigorous** — Every delta tested for significance before acting on it.
5. **Language agnostic** — No English-centric models for evaluation decisions.
6. **Complementary layers** — Multiple independent metrics that triangulate quality.

---

## 3. Metric Architecture

### Overview

| Level | Name | What it measures | Cost | Reproducible | Decision-grade |
|-------|------|-----------------|------|-------------|----------------|
| **L1** | Quantitative Style | Form: length, emoji, questions, language | $0 | Yes (deterministic) | Yes |
| **L2** | Shadow BERTScore | Semantic similarity to creator real responses | $0 | Yes (deterministic) | Yes |
| **L3** | Shadow Lexical | N-gram overlap, ROUGE-L, vocabulary | $0 | Yes (deterministic) | Yes |
| **L4** | BFI Personality | Big Five personality profile match | $0 local | Semi (judge variance) | Trend only |
| **L5** | Human Checklist | Objective quality: grammar, facts, coherence | $0 | Yes (binary items) | Yes |
| **L6** | LLM Judge | Multi-dimensional qualitative assessment | $0-$2.50 | No (stochastic) | **Informational only** |

### Decision Protocol

- **Ablation decisions** use L1 + L2 + L3 only (deterministic, reproducible)
- **L4** (BFI) tracks personality drift over time — not for per-ablation decisions
- **L5** (Human) is spot-check: 10 responses per config, binary checklist
- **L6** (LLM Judge) is kept for trend monitoring but **never** as sole decision criterion

---

## 4. Level 1 — Quantitative Style Match (Existing)

### What it measures
Surface-level text properties: character length, word count, emoji frequency, question marks, exclamation marks, vocabulary overlap, language distribution (ES/CA/mixed).

### How it works
Already implemented in `tests/cpe_level1_quantitative.py`. Computes per-metric divergence from creator baseline. Overall score = fraction of metrics within tolerance (30% for numeric, 20pp for boolean).

### Ground truth
50 test cases with real Iris responses from last 3 months of production data.

### Correlation with human judgment
Not formally measured, but tracks form fidelity directly. A response with correct length, emoji rate, and language is *necessary* for persona match (though not sufficient).

### Validity
Always valid. Pure computation, no model-dependent judgment.

### Thresholds
- **Overall ≥ 0.80**: Good form match (current Iris: 0.83)
- **Individual flag**: >30% divergence on any numeric metric
- **Significance**: Deterministic — any change in score is real, not noise

### Cost
$0 (pure computation, no API calls)

---

## 5. Level 2 — Shadow BERTScore (NEW)

### What it measures
Semantic similarity between bot-generated response and creator's real response for the same conversation turn.

### Scientific basis
- **BERTScore** (Zhang et al., ICLR 2020): Token-level cosine similarity using contextual embeddings. F1 variant correlates 0.59-0.72 with human judgments across languages.
- **Cross-lingual validity**: XLM-RoBERTa embeddings capture meaning across ES/CA without language-specific tuning (Conneau et al., ACL 2020).
- **CharacterEval** (Tu et al., ACL 2024): Used BERTScore as one of their objective metrics alongside subjective CharacterRM.

### How it works

```
Input:
  - reference: creator's real response (ground_truth from test set)
  - candidate: bot's generated response

Model: xlm-roberta-large (771M params, 100 languages including ES and CA)

Output per pair:
  - Precision: avg max-cosine-similarity of candidate tokens to reference
  - Recall: avg max-cosine-similarity of reference tokens to candidate
  - F1: harmonic mean of P and R

Aggregate:
  - BERTScore-F1 = mean(F1 across all test cases)
  - BERTScore-P = mean(Precision across all test cases)
  - BERTScore-R = mean(Recall across all test cases)
```

### Ground truth
50 test cases: each has `test_input` (follower message) + `ground_truth` (Iris's real response) + `bot_response` (pipeline output).

### Correlation with human judgment
- BERTScore: Pearson ρ = 0.59-0.72 with human judgments (Zhang et al., 2020)
- Cross-lingual: Pearson ρ = 0.59 for non-English languages (same paper)
- Superior to BLEU (ρ = 0.25) and ROUGE-L (ρ = 0.35) for paraphrase detection

### Validity conditions
- **Valid when**: Comparing responses to the same input where a "correct" response exists
- **NOT valid when**: Multiple equally valid responses exist (creative/open-ended). BERTScore will undervalue valid alternatives that differ lexically from reference.
- **Mitigation**: Complement with L3 lexical metrics and L1 quantitative for triangulation.

### Thresholds
- **BERTScore-F1 ≥ 0.70**: Strong semantic match (creator-grade response)
- **BERTScore-F1 0.55-0.70**: Acceptable — correct intent, different phrasing
- **BERTScore-F1 < 0.55**: Poor — different meaning or missing key content
- **Significance**: Bootstrap 95% CI with 1000 resamples. Delta significant if CIs don't overlap.

### Cost
$0 (local model, ~2 seconds for 50 test cases on M-series Mac with MPS)

### Implementation
`tests/cpe_bertscore.py`

---

## 6. Level 3 — Shadow Lexical Metrics (NEW)

### What it measures
Surface-level textual overlap between bot and creator responses. Complements BERTScore (semantic) with lexical precision.

### Metrics

| Metric | Formula | Paper | What it captures |
|--------|---------|-------|-----------------|
| **BLEU-4** | Modified n-gram precision (1-4 grams) with brevity penalty | Papineni et al., ACL 2002 | Exact phrase match |
| **ROUGE-L** | Longest Common Subsequence / reference length | Lin, ACL 2004 | Shared structure |
| **Vocabulary Overlap** | Jaccard(bot_words, creator_words) | — | Shared vocabulary |
| **Length Ratio** | len(bot) / len(creator) | — | Response length calibration |
| **Character N-gram F1** | chrF++ (character 6-gram F1) | Popović, WMT 2015 | Morphological similarity (good for agglutinative languages) |

### Ground truth
Same 50 test cases as L2.

### Correlation with human judgment
- BLEU: ρ = 0.25 with human (weak alone, useful in ensemble)
- ROUGE-L: ρ = 0.35 with human (moderate)
- chrF++: ρ = 0.52 for morphologically rich languages (Popović, 2015)

### Why include if BERTScore is better?
1. **Deterministic** — No model loading variance
2. **Interpretable** — "BLEU=0.15 means almost no exact phrases match"
3. **Fast** — Milliseconds, no GPU needed
4. **Complementary** — BERTScore can say "semantically similar" but miss that the bot uses completely different vocabulary. Lexical metrics catch this.

### Thresholds
- **BLEU-4 ≥ 0.10**: Good for open-ended dialogue (BLEU is harsh for generation)
- **ROUGE-L ≥ 0.25**: Reasonable structural overlap
- **Vocab Overlap ≥ 0.15**: Shared word usage
- **Length Ratio 0.7–1.3**: Within 30% of creator length
- **chrF++ ≥ 0.30**: Good character-level similarity

### Cost
$0 (pure computation)

### Implementation
Included in `tests/cpe_shadow_comparison.py`

---

## 7. Level 4 — BFI Personality Match (Existing, Reframed)

### What it measures
Whether the bot exhibits the same Big Five personality profile as the creator.

### How it works
Already implemented in `tests/cpe_level3_bfi_interview.py`. 44 BFI questions → bot responses → Expert Rating by judge → cosine similarity with creator's real BFI.

### Reframing for CPE v2
- **Demoted from decision-grade to trend-tracking**
- Reason: Expert Rating step uses LLM judge, which introduces stochastic variance
- Use: Track personality drift across pipeline versions. If cosine drops below 0.85, investigate.

### Ground truth
Iris's real BFI: E=4.4, A=4.0, O=3.5, C=3.1, N=2.8

### Thresholds
- **Cosine ≥ 0.90**: Excellent personality match
- **Cosine 0.85-0.90**: Acceptable
- **Cosine < 0.85**: Personality drift — investigate
- **MAE ≤ 0.50**: Good (current: 0.64 — needs improvement)

### Cost
$0 with Prometheus local, ~$0.05 with GPT-4o

---

## 8. Level 5 — Human Checklist (NEW)

### What it measures
Objective quality aspects that Manel can evaluate without being the creator.

### What Manel CAN evaluate
- Grammatical correctness (ES/CA)
- Factual accuracy (prices, schedules, class info)
- Coherence with conversation history
- Absence of AI-sounding patterns ("Como asistente...", "Aquí tienes...")
- Appropriate language (ES/CA/mixed) for the context
- Response length appropriateness
- Emoji usage appropriateness

### What Manel CANNOT evaluate
- "Does this sound like Iris?" — Only Iris can judge persona fidelity
- Tone nuances that require knowing Iris personally
- Whether the emotional response "feels right" for Iris specifically

### Checklist format (binary — yes/no per item)

For each bot response, evaluate:

| # | Item | Yes/No |
|---|------|--------|
| 1 | **Grammar correct** — No spelling/grammar errors in ES or CA | |
| 2 | **Language match** — Response uses the same language as the follower's message | |
| 3 | **Facts correct** — No fabricated prices, schedules, or class names | |
| 4 | **No hallucination** — Doesn't claim to know things the creator wouldn't | |
| 5 | **Coherent** — Logically follows the conversation history | |
| 6 | **Not robotic** — No "Como asistente", numbered lists, or AI patterns | |
| 7 | **Length appropriate** — Similar length to what a human would write in DM | |
| 8 | **Emoji appropriate** — Emojis match the tone (not forced, not missing when expected) | |
| 9 | **No AI disclosure** — Doesn't reveal being a bot | |
| 10 | **Would fool a follower** — A follower wouldn't suspect this is automated | |

### Scoring
```
Manel Score = count(Yes) / 10
```

### Statistical protocol
- Evaluate **20 responses per configuration** (min for 95% CI ±10pp)
- Randomize presentation order (don't evaluate all from same config sequentially)
- Blind evaluation: don't show which config generated the response
- Report: mean ± 95% CI

### Formula for required sample size
```
n = (z² × p × (1-p)) / E²
where z=1.96 (95% CI), p=0.5 (worst case), E=0.10 (±10pp precision)
n = (3.84 × 0.25) / 0.01 = 96 ≈ 100 total across configs

With 5 configs × 20 responses = 100 total evaluations
```

### Cost
$0 (Manel's time, ~30 min for 20 responses)

### Implementation
`docs/manel_evaluation_checklist.html` — Standalone HTML page with randomized presentation

---

## 9. Level 6 — LLM Judge (Existing, Demoted)

### What it measures
Multi-dimensional qualitative assessment across 5 dimensions (conversational ability, persona fidelity, knowledge accuracy, emotional intelligence, engagement).

### Status in CPE v2
**INFORMATIONAL ONLY** — Not used for ablation decisions.

### Why demoted
- Fleiss' Kappa ≈ 0.3 in ES/CA (Fu et al., 2025)
- Prometheus 7B makes grammatical errors in Catalan
- σ = 0.40 across runs (our data)
- GPT-4o focuses on grammar over intent in Catalan

### When to use
- Track trends over pipeline versions
- Identify potential issues for human investigation
- Pre-screen before Manel checklist
- Never as sole criterion for keep/remove decisions

---

## 10. Composite CPE v2 Score

### Formula

```
CPE_v2 = 0.25 × L1_norm + 0.35 × L2_norm + 0.20 × L3_norm + 0.20 × L5_norm

Where:
  L1_norm = overall_quantitative_match (already 0-1)
  L2_norm = BERTScore_F1 (already 0-1)
  L3_norm = mean(BLEU_4/0.30, ROUGE_L/0.50, chrF/0.60, clip_to_1)
  L5_norm = manel_checklist_score (already 0-1)
```

### Why these weights
- **L2 (BERTScore) 35%**: Highest correlation with human judgment (ρ=0.59), captures semantic intent
- **L1 (Quantitative) 25%**: Proven reliable, captures form fidelity
- **L3 (Lexical) 20%**: Complements BERTScore with exact match
- **L5 (Human) 20%**: Ground truth quality, but smaller sample size

### Interpretation
- **CPE_v2 ≥ 0.70**: Production-ready clone
- **CPE_v2 0.55-0.70**: Acceptable with known gaps
- **CPE_v2 < 0.55**: Needs work before deployment

---

## 11. Ablation Protocol

### Objective
Isolate the effect of each pipeline system on clone quality.

### Statistical framework

**Problem**: LLM generation is stochastic (temperature, sampling). A single run cannot distinguish system effect from random variance.

**Solution**: Multiple runs + statistical testing.

### Protocol

1. **Baseline**: Run CPE v2 (L1+L2+L3) on current production config. **5 runs**.
2. **Ablation**: Disable one system. Run CPE v2 on modified config. **5 runs**.
3. **Compare**: Paired Wilcoxon signed-rank test on per-test-case BERTScore-F1.

### Why 5 runs?
- With 50 test cases × 5 runs = 250 paired observations
- Power analysis: detects Cohen's d ≥ 0.25 with 80% power at α=0.05
- Practical: 5 runs × 50 cases × ~2s/case = ~8 minutes per config with Qwen3-14B

### Step-by-step

```
For each system S to ablate:
  1. Set temperature=0.7 (production default), seed=None
  2. Run baseline config 5 times → 5 × 50 = 250 (input, response) pairs
  3. Disable system S
  4. Run ablated config 5 times → 250 (input, response) pairs
  5. For each of the 50 test cases:
     a. Compute mean BERTScore-F1 across 5 runs (baseline)
     b. Compute mean BERTScore-F1 across 5 runs (ablated)
  6. Wilcoxon signed-rank test on 50 paired means
  7. Compute effect size (Cliff's delta)
  8. Decision rule:
     - p < 0.05 AND |Cliff's delta| > 0.20 → System has real effect
     - p ≥ 0.05 OR |Cliff's delta| ≤ 0.20 → No detectable effect (candidate for removal)
```

### Ablation order (prioritized by suspicion)

Based on pipeline audit (session 2026-03-31):

| Priority | System | Reason for suspicion |
|----------|--------|---------------------|
| 1 | Style Normalizer | Known emoji conflict (P0 bug), high-impact post-processing |
| 2 | Few-shot Loader | Neutral-to-negative in v1 ablations, high token cost |
| 3 | Length Hints | 3 overlapping length systems, unclear which helps |
| 4 | Memory Engine | Neutral in v1, adds complexity |
| 5 | RAG | Neutral in v1 for casual conversations |
| 6 | Question Hints | Bot under-asks (0.16 vs 0.26 target) |
| 7 | Pool Responses | Intercepts short messages, unknown effect |

### Reporting

For each ablation, report:
```
System: [name]
Baseline BERTScore-F1: X.XXX ± Y.YYY (mean ± std across runs)
Ablated BERTScore-F1:  X.XXX ± Y.YYY
Delta: +/-X.XXX
p-value (Wilcoxon): X.XXXX
Cliff's delta: X.XX
L1 change: X.XX → X.XX
Decision: KEEP / REMOVE / INVESTIGATE
```

---

## 12. Shadow Mode Protocol

### Data source

The copilot system generates natural preference pairs:
- Bot generates `suggested_response` (stored in `messages.suggested_response`)
- Creator responds independently (stored in `messages.content`)
- `copilot_action` tracks outcome: approved, edited, discarded, resolved_externally

### Audit query

```sql
-- Count usable shadow pairs by type
SELECT
    copilot_action,
    COUNT(*) as count,
    AVG(confidence_score) as avg_confidence,
    MIN(created_at) as earliest,
    MAX(created_at) as latest
FROM messages
WHERE role = 'assistant'
  AND suggested_response IS NOT NULL
  AND copilot_action IS NOT NULL
GROUP BY copilot_action
ORDER BY count DESC;
```

### Pair quality tiers

| Tier | Source | Signal strength | Use for |
|------|--------|----------------|---------|
| **A (Gold)** | `edited` — creator modified bot response | Strongest: shows exactly what was wrong | DPO training, metric calibration |
| **B (Strong)** | `resolved_externally` — creator replied independently | Strong: complete divergence | BERTScore calibration, DPO |
| **C (Weak positive)** | `approved` — creator accepted as-is | Weak positive: bot was good enough | Positive examples only |
| **D (Negative)** | `discarded` — creator rejected entirely | Negative signal only | Negative examples for DPO |

### Shadow → DPO pipeline

```
1. Export preference_pairs where action_type IN ('edited', 'divergence')
2. Filter: both chosen AND rejected non-empty, len(chosen) > 10
3. Format as DPO triples:
   {
     "prompt": user_message + conversation_context,
     "chosen": creator's response,
     "rejected": bot's suggestion
   }
4. Quality filter: exclude pairs where BERTScore(chosen, rejected) > 0.90
   (too similar — not informative for DPO)
5. Export as JSONL to data/dpo/
```

### Shadow → Evaluation metrics

For each shadow pair:
1. **BERTScore(bot_suggestion, creator_real)** — semantic distance
2. **BLEU-4(bot_suggestion, creator_real)** — lexical overlap
3. **Length ratio** — response length calibration
4. **Language match** — did bot use same language as creator?

Track these over time to measure improvement:
```
shadow_quality_score = mean(BERTScore_F1) over rolling 7-day window
```

---

## 13. Human-in-the-Loop Integration

### Manel's role

Manel evaluates **objective quality** (grammar, facts, coherence). NOT persona fidelity ("does it sound like Iris").

### When to use
- After each significant pipeline change
- Before deploying a new config to production
- As tiebreaker when L1/L2/L3 disagree

### Workflow

1. Generate 20 bot responses from the test set (randomized)
2. Present in `manel_evaluation_checklist.html` (blind — no config label)
3. Manel marks 10-item binary checklist per response
4. Compute Manel Score = mean(yes_count / 10)
5. Compare across configs using Fisher's exact test

### Integration with automatic metrics

```
If L1 improves AND L2 improves AND L3 improves:
  → Automatically accept change (Manel spot-checks post-deploy)

If L1 improves but L2 degrades (or vice versa):
  → Manel evaluates 20 responses from each config
  → Decision based on Manel Score

If all metrics are within noise:
  → Don't change anything. The system is the same.
```

---

## 14. Continuous Improvement Pipeline

### Cycle

```
┌─────────────────────────────────────┐
│ 1. MEASURE: Run CPE v2 full suite   │
│    L1 + L2 + L3 + (L5 if needed)   │
├─────────────────────────────────────┤
│ 2. IDENTIFY: Find biggest gap       │
│    - Which L2 category is lowest?   │
│    - Which L1 metric is flagged?    │
│    - Which test cases fail worst?   │
├─────────────────────────────────────┤
│ 3. HYPOTHESIZE: What system fix     │
│    would improve the gap?           │
│    Log in DECISIONS.md              │
├─────────────────────────────────────┤
│ 4. FIX: Implement the change        │
│    (Follow 4-phase workflow)        │
├─────────────────────────────────────┤
│ 5. RE-MEASURE: Run CPE v2 again     │
│    Same test set, 5 runs            │
├─────────────────────────────────────┤
│ 6. CONFIRM: Statistical test        │
│    p < 0.05 AND |d| > 0.20?        │
│    YES → Keep change                │
│    NO  → Revert change              │
└─────────────────────────────────────┘
```

### Avoiding the noise trap

**Rule**: Never act on a delta that isn't statistically significant.

| Situation | Action |
|-----------|--------|
| Delta > 0, p < 0.05, d > 0.20 | Accept change |
| Delta > 0, p ≥ 0.05 | Do NOT accept — could be noise |
| Delta < 0, p < 0.05 | Revert change — real regression |
| Delta ≈ 0, p ≥ 0.05 | No effect detected — simpler config preferred |

### When to consider DPO vs pipeline engineering

| Condition | Action |
|-----------|--------|
| CPE_v2 < 0.55 | Pipeline engineering first (bigger gains, faster iteration) |
| CPE_v2 0.55-0.70, L2 stagnant | Consider DPO if ≥200 shadow pairs available |
| CPE_v2 ≥ 0.70, L5 < 0.80 | Human review reveals specific patterns → targeted fix |
| CPE_v2 ≥ 0.70, L5 ≥ 0.80 | Pipeline is mature. DPO for final polish. |

### "Done" criteria

The clone is production-ready when:
1. **CPE_v2 ≥ 0.70** (composite score)
2. **L1 ≥ 0.80** (form match)
3. **L2 BERTScore-F1 ≥ 0.65** (semantic match)
4. **L5 Manel Score ≥ 0.80** (8/10 checklist items pass on average)
5. **L4 BFI cosine ≥ 0.85** (personality profile match)
6. **No P0 flags** (no hallucination, no AI disclosure, no wrong language)

---

## 15. Implementation Files

| File | Purpose | Status |
|------|---------|--------|
| `tests/cpe_level1_quantitative.py` | L1 Quantitative Style | Existing ✅ |
| `tests/cpe_bertscore.py` | L2 Shadow BERTScore | New 🆕 |
| `tests/cpe_shadow_comparison.py` | L3 Shadow Lexical + Shadow audit | New 🆕 |
| `tests/cpe_level3_bfi_interview.py` | L4 BFI Personality | Existing ✅ |
| `docs/manel_evaluation_checklist.html` | L5 Human Checklist | New 🆕 |
| `tests/cpe_level2_llm_judge.py` | L6 LLM Judge (informational) | Existing ✅ |
| `tests/cpe_ablation_runner.py` | Automated ablation protocol | New 🆕 |

### Quick commands

```bash
# Full CPE v2 suite (except human eval)
railway run python3.11 tests/cpe_level1_quantitative.py --creator iris_bertran
railway run python3.11 tests/cpe_bertscore.py --creator iris_bertran
railway run python3.11 tests/cpe_shadow_comparison.py --creator iris_bertran

# Ablation (5 runs, disable style_normalizer)
railway run python3.11 tests/cpe_ablation_runner.py --creator iris_bertran \
  --disable style_normalizer --runs 5

# Shadow mode audit
railway run python3.11 tests/cpe_shadow_comparison.py --creator iris_bertran --audit-only

# Human eval
open docs/manel_evaluation_checklist.html
```

---

## 16. References

1. Zhang et al. (2020). "BERTScore: Evaluating Text Generation with BERT." ICLR 2020. — BERTScore methodology, cross-lingual correlation ρ=0.59.
2. Tu et al. (2024). "CharacterEval: A Chinese Benchmark for Role-Playing Conversational Agent Evaluation." ACL 2024. — 4-dimension framework, CharacterRM.
3. Samuel et al. (2024). "PersonaGym: Evaluating Persona Agents and LLMs." EMNLP 2025. — 5-task framework, PersonaScore, dual evaluator.
4. Wang et al. (2024). "InCharacter: Evaluating Personality Fidelity in Role-Playing Agents." ACL 2024. — BFI interview method, 80.7% accuracy.
5. Kim et al. (2024). "Prometheus 2: An Open Source Language Model Specialized in Evaluating Other Language Models." ICLR 2024. — Pearson 0.6-0.7 with GPT-4 in English.
6. Fu et al. (2025). "On the Reliability of LLM-as-Judge." EMNLP 2025. — Fleiss' Kappa ≈ 0.3 in 25 non-English languages.
7. Papineni et al. (2002). "BLEU: a Method for Automatic Evaluation of Machine Translation." ACL 2002. — BLEU metric.
8. Lin (2004). "ROUGE: A Package for Automatic Evaluation of Summaries." ACL 2004. — ROUGE-L metric.
9. Popović (2015). "chrF: character n-gram F-score for automatic MT evaluation." WMT 2015. — chrF metric, good for morphologically rich languages.
10. Conneau et al. (2020). "Unsupervised Cross-lingual Representation Learning at Scale." ACL 2020. — XLM-RoBERTa multilingual model.
11. PersoDPO (2026). "Persona-Aligned DPO without Human Annotation." arXiv. — Automatic preference pairs for persona DPO.
12. Cliff (1993). "Dominance Statistics: Ordinal Analyses to Answer Ordinal Questions." — Cliff's delta effect size.

---

*This methodology replaces CPE v1. All ablation decisions from this point forward must use CPE v2 metrics.*
