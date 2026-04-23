# State of the Art: Few-Shot Injection

**Date:** 2026-04-23
**Scope:** per-turn dynamic few-shot selection from creator corpus for persona-fidelity DM chatbot.
**Research threads:** in-context learning demonstration selection, persona-conditioned few-shot, semantic-intent hybrid retrieval, k-shot calibration.

Context: the current pipeline loads `max_examples=5` per-turn via `services/calibration_loader.get_few_shot_section(...)` using an intent-stratified + semantic hybrid selector over the creator's calibration dialogue history (RoleLLM ACL 2024 style). Activation is flag-gated (`flags.few_shot`). Examples are 100% creator-derived; zero hardcoded linguistic content. This document evaluates whether any 2024-2026 advance supersedes that design.

## 1. Papers (2024-2026)

| # | Paper | Venue / Date | Finding (quote ≤15 words) | Applicability |
|---|---|---|---|---|
| 1 | RoleLLM: Benchmarking, Eliciting, and Enhancing Role-Playing Abilities (Wang et al.) | ACL Findings 2024 | "Role-specific knowledge extraction" via few-shot role prompting imitates speaking style. | Foundational — intent-stratified + semantic k=5 hybrid we already use traces to this work. KEEP. |
| 2 | Revisiting Demonstration Selection Strategies in ICL (Peng, Ding, Yuan et al.) — TopK + ConE | ACL 2024 (long paper) | "Demonstration choice is both data- and model-dependent" — positive correlation with test-sample understanding. | Validates hybrid selector. ConE (confidence-based re-ranker) could tune k dynamically. DEFER-Q2. |
| 3 | Many-Shot In-Context Learning (Agarwal et al.) | NeurIPS 2024 Spotlight (arXiv 2404.11018) | "Hundreds or thousands of examples" yield substantial gains over few-shot for complex tasks. | Low applicability: DM persona fidelity is not a reasoning-heavy task; context-budget and style-dilution dominate. DISCARD for turn-level; revisit only post fine-tuning. |
| 4 | In-Context Learning with Iterative Demonstration Selection (Qin et al.) — IDS | EMNLP Findings 2024 | "Iteratively selects examples that are diverse but strongly correlated with the test sample." | Diversity+correlation is what our intent-stratified+semantic already delivers in one shot. DISCARD (no iterative loop worth its latency cost on Railway). |
| 5 | DSPy MIPROv2 — A Comparative Study of Teleprompters (Soylu et al.) | arXiv 2412.15298 (Dec 2024) | "Jointly optimises instructions and few-shot examples via bootstrap + Bayesian optimisation." | Offline compile-time optimiser over labelled set — not a per-turn selector. Relevant for calibration-building pipeline, not for the real-time chain. DEFER-Q2. |

Notes on k=5. RoleLLM (2024) empirically settled on small k for role-playing/style imitation; the abstract and related literature do not publish a universal optimum. Peng et al. (2024) show k is "data- and model-dependent", which means no static k is globally optimal, but also that raising k without selection quality is usually harmful (style dilution, attention washout). Agarwal et al. (2024) show that scaling to hundreds of shots only helps on reasoning/structured tasks with long context — not on style-fidelity dialogue where identity signals must be preserved literally (see CLAUDE.md rule on not compressing/reordering identity signals).

## 2. Repositories (active, >500 stars, last 6 months)

| # | Repo | Stars | Last commit | Relevance | Applicability |
|---|---|---|---|---|---|
| 1 | `stanfordnlp/dspy` | 34.0k | 2026-04-21 (Isaac Miller, `chore: refresh uv.lock`) | BootstrapFewShot / MIPROv2 optimise few-shot example sets offline over a metric. Exactly complements our per-turn selector at compile-time. | ADOPT (Q2) as calibration-pack optimiser; not as a runtime dep. |
| 2 | `langchain-ai/langchain` | 135k | 2026-04-23 (OpenAI v1.2.0 release) | Ships `SemanticSimilarityExampleSelector`, `MaxMarginalRelevanceExampleSelector`, `NGramOverlapExampleSelector`. Mature reference implementations. | DISCARD as dep (our selector is already equivalent + intent-stratified), but KEEP as reference for MMR variant. |
| 3 | `guidance-ai/guidance` | 21.4k | 2026-04-10 (R. Edgar, GPU build fix) | Constrained generation + in-prompt demo composition. Interesting for output shape constraints, not for selection quality. | DISCARD for few-shot selection scope. |

`microsoft/promptflow` was evaluated and set aside: last visible release is Jan 2025 with no confirmed commit within the 6-month window, and its value is IDE/orchestration rather than per-turn selection.

## 3. Mapping — what we adopt vs discard

ADOPT:
- Keep intent-stratified + semantic hybrid selector with k=5 as the runtime path. Matches RoleLLM 2024 and is consistent with Peng et al. 2024 finding that selection quality beats scale.
- Treat the creator's calibration set as the authoritative source; do not mix in hardcoded exemplars (coherent with CLAUDE.md identity-signal rule and QW2 compressed-Doc-D regression evidence).
- Instrument per-turn logging of `(intent_detected, k_actual, retrieved_example_ids, semantic_scores)` so we can measure whether k≠5 ever correlates with quality deltas on CPE v2.

DISCARD:
- Many-Shot ICL at turn time. Persona/style fidelity is not reasoning; padding the prompt with many examples dilutes style density and inflates Gemini/DeepInfra token spend with no proven CPE gain. Revisit only post fine-tuning.
- Iterative Demonstration Selection (IDS). Extra LLM round-trips per turn violate the Railway latency budget and duplicate what our one-shot hybrid already does.
- LangChain as a runtime dependency. We already implement the equivalent of `SemanticSimilarityExampleSelector` + intent filter. Adding the dep buys zero and widens the attack surface.

DEFER-Q2:
- DSPy BootstrapFewShot / MIPROv2 as an **offline** compile-time pass over the creator calibration set: bootstrap a small pool of high-metric (CPE v2) exemplars per intent, then let the runtime selector choose k=5 from that curated pool. This is an improvement to the corpus the selector draws from, not a replacement for the selector itself.
- TopK + ConE confidence re-ranking (Peng et al. 2024): if CPE v2 logs reveal the selector sometimes picks low-confidence demos, a cheap post-retrieval re-ranker could trim bad picks without raising k.
- Dynamic-k: evaluate `k ∈ {3, 5, 7}` bucketed by `(len(current_message_tokens), detected_intent_complexity)`. Only ship if CPE v2 deltas are consistent across ≥3 creators; otherwise k=5 stays.

## 4. Verdict

- Superior alternative identified? **NO** for the runtime per-turn path. **YES (complementary, not replacing)** for an offline calibration-pack optimiser (DSPy MIPROv2 / BootstrapFewShot).
- Recommended action: **KEEP-AS-IS** at runtime. **DEFER-Q2** for (a) offline MIPROv2 curation of the example pool and (b) instrumentation-driven dynamic-k A/B.
- Reason: our chain already implements the 2024 consensus (intent-stratified + semantic hybrid, small k≈5, per-creator data-derived). The only 2024-2026 advances that would win are compile-time curation (DSPy family) and confidence-gated re-ranking (ConE) — both additive, neither urgent, and neither safe to ship without CPE v2 measurement discipline (consistent with the anti-compression identity-signal rule and Sprint 5 closure criteria).

### Explicit answers to the verdict questions

(a) Learned example selectors (LENS, EPR, vote-k, RDES): **DEFER-Q2**. These are trained retrievers that require a labelled preference signal per creator; we do not yet have enough per-creator CPE v2 data to train one per clone without overfitting. Peng et al. (2024) explicitly find selection is model-dependent, so a learned selector tuned on one base model would not transfer cleanly through a fine-tuning step. Revisit after fine-tuning lands.

(b) Compositional / think-then-respond few-shot: **DISCARD (for now)**. CCoT (Mitra et al., CVPR 2024) targets multimodal compositional benchmarks; think-then-respond inflates latency and risks injecting a reasoning-voice into the clone's output — directly contradicts persona literalism. If we ever want it, put it behind a separate flag for sales arbitration, not the default path.

(c) Is k=5 still optimal, or should we adapt dynamically (k=3 short / k=7 complex)? **KEEP-AS-IS now, DEFER-Q2 for dynamic-k**. Evidence: (i) RoleLLM 2024 empirically used small k for role fidelity; (ii) Peng et al. 2024 show k is data-and-model-dependent — an argument *against* fixing a new constant like 7, not for raising k blindly; (iii) Many-Shot ICL (Agarwal et al. 2024) gains are task-class-specific (reasoning), not style-fidelity; (iv) our own identity-signal rule from CLAUDE.md plus the QW2 compressed-Doc-D regression (-10.69 composite) show that anything that perturbs identity density tends to regress. Dynamic-k is a legitimate experiment, but it must be gated on CPE v2 measurement across ≥3 creators before replacing the static-5 default.

## 5. Sources

- [RoleLLM: Benchmarking, Eliciting, and Enhancing Role-Playing Abilities of Large Language Models (ACL 2024 Findings)](https://aclanthology.org/2024.findings-acl.878/)
- [RoleLLM arXiv 2310.00746](https://arxiv.org/abs/2310.00746)
- [Revisiting Demonstration Selection Strategies in In-Context Learning (Peng et al., ACL 2024)](https://aclanthology.org/2024.acl-long.492/)
- [Revisiting Demonstration Selection Strategies — arXiv 2401.12087](https://arxiv.org/abs/2401.12087)
- [Many-Shot In-Context Learning (Agarwal et al., NeurIPS 2024 Spotlight)](https://arxiv.org/abs/2404.11018)
- [In-Context Learning with Iterative Demonstration Selection (Qin et al., EMNLP Findings 2024)](https://aclanthology.org/2024.findings-emnlp.438/)
- [A Comparative Study of DSPy Teleprompter Algorithms (arXiv 2412.15298)](https://arxiv.org/html/2412.15298v1)
- [DSPy Optimizers documentation](https://dspy.ai/learn/optimization/optimizers/)
- [MIPROv2 API reference](https://dspy.ai/api/optimizers/MIPROv2/)
- [stanfordnlp/dspy on GitHub](https://github.com/stanfordnlp/dspy)
- [langchain-ai/langchain on GitHub](https://github.com/langchain-ai/langchain)
- [guidance-ai/guidance on GitHub](https://github.com/guidance-ai/guidance)
