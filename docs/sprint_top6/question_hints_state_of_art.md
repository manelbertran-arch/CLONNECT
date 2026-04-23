# State of the Art: Question Hints

**Date:** 2026-04-23
**Scope:** runtime question-suppression hint injection for persona-fidelity DM chatbot.
**Research threads:** style control, prompt steering, question calibration.

## 1. Papers (2024-2026)

| # | Paper | Venue / Date | Finding (quote ≤15 words) | Applicability |
|---|---|---|---|---|
| 1 | Persona Vectors: Monitoring and Controlling Character Traits in Language Models (Chen, Arditi, Sleight, Evans, Lindsey) | arXiv 2507.21509, Jul 2025 | "These vectors can be used to monitor fluctuations in the Assistant's personality at deployment time." | DEFER-Q2 (activation steering is more surgical than prompt hint but needs logit access we don't have on Gemini) |
| 2 | Modeling Future Conversation Turns to Teach LLMs to Ask Clarifying Questions (Zhang, Knox, Choi) | ICLR 2025, arXiv 2410.13788 | "LLM's best response may be to ask a clarifying question to elicit more information." | DISCARD (trains a question-ask policy via SFT — we do opposite: suppress over-questioning at runtime without FT) |
| 3 | Consistently Simulating Human Personas with Multi-Turn Reinforcement Learning (Abdulhai, Cheng, Clay, Althoff, Levine, Jaques) | arXiv 2511.00222, Oct 2025 | "off-the-shelf LLMs often drift from their assigned personas, contradict earlier statements" | ADOPT-as-evidence (validates persona drift problem; but their fix is multi-turn RL, we use runtime hint) |
| 4 | Controllable Text Generation for Large Language Models: A Survey (Liang et al.) | arXiv 2408.12599, Aug 2024 | Key methods include "prompt engineering, latent space manipulation, and decoding-time intervention." | ADOPT (places our prompt-injection hint in the "prompt engineering + decoding-time" family — legitimate CTG technique) |
| 5 | The Instruction Gap: LLMs get lost in Following Instruction (Tripathi, Allu, Ahmed) | arXiv 2601.03269, Dec 2025 | "models excel at general tasks but struggle with precise instruction adherence required for enterprise deployment" | ADOPT-as-risk (confirms a single directive may be unreliably followed — justifies stochastic injection + measurement) |

## 2. Repositories (active, >500 stars)

| # | Repo | Stars | Last release / commit | Relevance | Applicability |
|---|---|---|---|---|---|
| 1 | [guidance-ai/guidance](https://github.com/guidance-ai/guidance) | 21.4k | v0.3.2 Mar 18, 2026 | Token-level control of LM output; constraint steering without fine-tune | DEFER-Q2 (requires logit access; Gemini API does not expose — so not usable today, but is the canonical upgrade path) |
| 2 | [dottxt-ai/outlines](https://github.com/dottxt-ai/outlines) | 13.7k | v1.2.12 Mar 3, 2026 | Structured generation with regex/CFG constraints | DISCARD (aimed at structured outputs like JSON; not a style/question-rate controller, wrong abstraction) |
| 3 | [noamgat/lm-format-enforcer](https://github.com/noamgat/lm-format-enforcer) | ~2k | v0.11.2 Aug 9, 2025 | Format enforcement via logit masking at decode time | DISCARD (same as Outlines — format, not persona style; and needs logit access) |

## 3. Mapping — what we adopt vs discard

ADOPT (already in our implementation or immediate Phase-1 add):
- Prompt-injection hint with a single negative directive is a canonical "prompt engineering + decoding-time intervention" technique per CTG survey (Liang 2024). No change.
- Data-driven target rate (creator mined baseline) aligns with persona-fidelity literature showing off-the-shelf LLMs drift from assigned personas (Abdulhai 2025) — our baseline-rate approach gives us a concrete drift signal to close.
- Stochastic injection with `p = 1 - creator/bot` is defensible given documented unreliability of single-shot negative instructions (Tripathi 2025) — hedging via probability prevents over-correction and matches a rate rather than a hard rule.

DISCARD (with reason):
- SFT a clarifying-question policy (Zhang 2024, ICLR 2025): solves the opposite problem (generate better questions) and requires fine-tuning, which is explicitly off-limits per project instructions until post-FT phase.
- Format-enforcement libs (Outlines, lm-format-enforcer): wrong abstraction — they constrain output shape (JSON/regex), not stylistic question density. Also require logit access unavailable on our Gemini endpoint.
- Multi-turn RL for persona consistency (Abdulhai 2025, PerMix-RLVR 2604.08986): expensive training pipeline; zero-hardcoding runtime hint is cheaper and revertible.

DEFER-Q2 (known gap, documented for future):
- Persona-vector activation steering (Chen 2507.21509) is a strictly more principled mechanism than a prompt directive — it edits hidden state on the "question-asking" axis directly. Requires logit/activation access and a probe for the trait. Revisit when we own weights (post-FT) or migrate to a self-hosted open model.
- Guidance-style token-level control (`guidance-ai/guidance`): would let us mask `?` / pregunta-lead tokens with a probability schedule instead of a prompt hint. Same blocker — needs logit access. Becomes viable if/when we move to vLLM or local inference.
- Learned question-rate controller (e.g. small classifier predicting "should this message contain a question?" from draft + context, trained on creator corpus): strictly dominates a single-prompt directive if we have enough per-creator data. Not critical now; document as Q2 candidate.

## 4. Verdict

- Superior alternative identified? YES (in principle), NO (reachable today).
- If YES: **persona-vector activation steering** (Chen et al. 2025) — edit the model's hidden state along a learned "ask-a-question" direction instead of injecting a textual directive; gives continuous, calibrated control rather than a binary stochastic switch. Secondary alternative: logit-masking of question-lead tokens via Guidance.
- Recommended action: **KEEP-AS-IS** for Sprint Top6; **DEFER-Q2** the activation-steering and logit-control upgrades.
- Reason: both superior alternatives require model internals (activations or logits) that the Gemini API does not expose. Our current prompt-injection hint with data-driven stochastic rate matching is the best mechanism available to a closed-API deployment, is consistent with the CTG survey's "prompt engineering + decoding-time intervention" family, and is cheaper/reversible compared to the RL and SFT alternatives in the literature. Upgrade becomes worthwhile only after fine-tuning or migration to an inference stack where we own logits/activations.

## 5. Sources

- [Persona Vectors: Monitoring and Controlling Character Traits in Language Models — arXiv 2507.21509](https://arxiv.org/abs/2507.21509)
- [Modeling Future Conversation Turns to Teach LLMs to Ask Clarifying Questions — arXiv 2410.13788](https://arxiv.org/abs/2410.13788)
- [Consistently Simulating Human Personas with Multi-Turn Reinforcement Learning — arXiv 2511.00222](https://arxiv.org/abs/2511.00222)
- [Controllable Text Generation for Large Language Models: A Survey — arXiv 2408.12599](https://arxiv.org/abs/2408.12599)
- [The Instruction Gap: LLMs get lost in Following Instruction — arXiv 2601.03269](https://arxiv.org/abs/2601.03269)
- [guidance-ai/guidance on GitHub](https://github.com/guidance-ai/guidance)
- [dottxt-ai/outlines on GitHub](https://github.com/dottxt-ai/outlines)
- [noamgat/lm-format-enforcer on GitHub](https://github.com/noamgat/lm-format-enforcer)
- [Anthropic — Persona Vectors research page](https://www.anthropic.com/research/persona-vectors)
