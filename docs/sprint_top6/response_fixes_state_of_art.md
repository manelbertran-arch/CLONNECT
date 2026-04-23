# State of the Art: Response Fixes

**Date:** 2026-04-23
**Scope:** post-LLM text-repair chain for DM chatbot, creator-aware, rule-based.
**Research threads:** output sanitisation, structured-output repair, post-processor cascades.

## 1. Papers (2024-2026)

| # | Paper | Venue / Date | Finding (quote ≤15 words) | Applicability |
|---|---|---|---|---|
| 1 | Harnessing Large Language Models as Post-hoc Correctors (Zhong, Zhou, Mottin) | arXiv 2402.13414, Feb 2024 (rev. Jun 2024) | "LlmCorr, a training-free framework… propose corrections… at a minimal cost." | ADOPT-as-evidence (validates post-hoc repair as legitimate class; our chain is the rule-based analog) |
| 2 | When Can LLMs Actually Correct Their Own Mistakes? A Critical Survey of Self-Correction of LLMs (Kamoi et al.) | TACL 2024 / arXiv 2406.01297 | "No prior work demonstrates successful self-correction with feedback from prompted LLMs." | ADOPT (direct argument against a learned/LLM self-editor for our use — rules win when no external signal) |
| 3 | JSONSchemaBench: A Rigorous Benchmark of Structured Outputs for Language Models (Geng, Cooper, Moskal et al.) | arXiv 2501.10868, Jan 2025 | "Constrained decoding has emerged as the dominant technology… for enforcing structured outputs." | DEFER-Q2 (constrained decoding dominates for schemas; not applicable to DM free-text but relevant long-term) |
| 4 | JSON Whisperer: Efficient JSON Editing with LLMs (Duanis, Greenstein-Messica, Habba) | arXiv 2510.04717, Oct 2025 | "Current approaches regenerate entire structures for each edit, resulting in computational inefficiency." | ADOPT-as-evidence (diff/patch generation beats full rewrite — matches our idempotent, minimal-edit chain) |
| 5 | Context-Enhanced Granular Edit Representation for Efficient and Accurate ASR Post-editing (Vejsiu, Zheng, Chen, Han) | arXiv 2509.14263, Sep 2025 | "Baseline full rewrite models have inference inefficiencies… generate the same redundant text." | ADOPT-as-evidence (granular edit ops + deterministic expansion = same architecture pattern as our chain) |

## 2. Repositories (active, >500 stars)

| # | Repo | Stars | Last release / commit | Relevance | Applicability |
|---|---|---|---|---|---|
| 1 | [guardrails-ai/guardrails](https://github.com/guardrails-ai/guardrails) | 6.7k | v0.10.0, Apr 3, 2026 | Validator framework wrapping LLM output with rule + ML checks, including fix/reask actions | ADOPT-as-pattern (confirms the "chain of validators + fixers pre-guardrails" architecture is industry-standard) |
| 2 | [jxnl/instructor](https://github.com/jxnl/instructor) | 12.8k | v1.15.1, Apr 3, 2026 | Structured outputs via Pydantic + retry-on-validation-fail loop | DISCARD for our use (schema-focused, DM text is free-form; but retry-on-fail pattern noted) |
| 3 | [mangiucugna/json_repair](https://github.com/mangiucugna/json_repair) | 4.7k | v0.59.4, Apr 15, 2026 | Rule-based repair of malformed JSON from LLM output; pure Python, deterministic | ADOPT-as-pattern (exact template: deterministic rule chain for LLM output repair, idempotent, no ML) |
| 4 | [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | 34k | v3.2.0, Apr 21, 2026 | Declarative LM programs with assertions/suggestions and automated prompt/pipeline optimisation | DEFER-Q2 (Assert/Suggest primitives could replace bespoke chain long-term; heavy migration cost) |

All four verified via live GitHub pages on 2026-04-23; star counts and release dates current as of fetch.

## 3. Mapping — what we adopt vs discard

ADOPT (already in our implementation, justified by SOTA):
- **Rule-based, idempotent, data-driven chain** — matches `json_repair` template exactly: deterministic transforms over LLM output, no ML dependency, each transform safe to re-apply. Kamoi 2024 provides the negative evidence (LLM self-correction fails without external signal), so rules are the correct class.
- **Creator-aware parameterisation via DB vocab** — aligns with the zero-hardcoding constraint in our CLAUDE.md (identity signals must not be compressed) and keeps the chain one-per-creator-profile, not one-per-creator-hardcoded.
- **Placement before guardrails** — matches the Guardrails AI framework's "fixers before validators" pattern: normalise first, then guard. Inverting the order would cause guardrails to flag fixable artefacts as violations.
- **Granular edit ops vs full rewrite** — Vejsiu 2025 (CEGER) and Duanis 2025 (JSON Whisperer) independently argue that structured edit patches beat full-rewrite models on both accuracy and cost. Our chain is the extreme case of this (pure patches, no LLM in the repair loop).

DISCARD (with reason):
- **LLM-as-editor (self-refine style, Madaan 2023 / LlmCorr 2024)**: Kamoi 2024 survey shows intrinsic self-correction improves reliably only with external feedback; we have none at this stage of the pipeline (guardrails run after). Also adds latency and a second model call per turn — violates our DM-latency budget.
- **Constrained decoding / logit-masking (Outlines, lm-format-enforcer, JSONSchemaBench focus)**: wrong abstraction for DM free text. These enforce schemas, not stylistic hygiene; and Gemini API doesn't expose logits anyway.
- **Instructor-style Pydantic retry loops**: aimed at schema conformance; DM output is free text. No gain.
- **Hardcoded linguistic rules** (explicitly prohibited by project instructions): would embed ES/CA surface strings in code, contradicting the creator-vocab-from-DB approach.

DEFER-Q2:
- **DSPy Assert/Suggest primitives**: principled replacement for ad-hoc chain — each fix becomes a declarative constraint, optimiser can tune phrasing. Migration cost is non-trivial; revisit after fine-tuning lands and we can co-optimise prompt + fix chain.
- **Constrained-decoding upgrade path**: if we ever move to a self-hosted open model, Guidance/Outlines-style logit control is strictly more principled than post-hoc repair for any structural fix. Keep as known upgrade.
- **A/B measurement of chain contribution per fix**: we currently toggle the whole chain. A longer-term instrumentation goal is per-fix counters so we know which transforms actually help on CCEE composite.

## 4. Verdict

### Key verdict question — would a small learned editor (distilled 2B, creator-specific edit pairs) beat the rule chain on CCEE composite?

**NO.**

Three independent reasons:

1. **Project-level prior**: our own Sprint 2 and Sprint 5 ablations (see `CLAUDE.md` identity-preservation warning, and `docs/audit_sprint5/s5_off_components_decision_matrix.md`) showed that lossy transforms over identity-defining signals cause measurable regressions (-10.9 Style Fidelity, -10.0 Turing, -6.8 Adaptation). A learned editor is by definition lossy and non-deterministic; on free-text DM output with no constrained target, it will rewrite more than we want.
2. **Literature-level prior**: Kamoi et al. (TACL 2024) explicitly concludes that LLM self/assisted correction does not reliably improve outputs without external feedback. A 2B distilled editor is closer to "prompted LLM corrector" than to "verified rule" — the same failure mode applies.
3. **Cost**: a learned editor adds ~50-200ms latency per turn (even for a 2B on GPU), a second failure mode (editor hallucination), and a training/evaluation pipeline we'd have to maintain. Current chain is O(few ms), deterministic, and free.

A learned editor becomes plausible **only** in one configuration: (a) we have fine-tuned the base model on creator data and locked its style distribution, and (b) the editor is trained on (pre-fix, post-fix) pairs produced by the rule chain itself, to distil it into one forward pass. That is strictly an optimisation, not a quality win — expected delta on CCEE composite ≈ 0 with added risk. Do not pursue before Q2 review.

### Summary

- Superior alternative identified? **NO** for this deployment.
- Recommended action: **KEEP-AS-IS**. Activate the flag per sprint plan; measure per `quick_decide_response_fixes.md` gates; do not expand scope.
- Reason: the rule-based, idempotent, creator-aware chain is the architecture class that current literature (Kamoi 2024, Duanis 2025, Vejsiu 2025) and OSS practice (`json_repair`, Guardrails AI) converge on for deterministic output hygiene without external feedback. Superior alternatives either need signals we don't have (logits, external validators) or introduce non-determinism into an identity-critical path, which our own ablation history has already shown is dangerous pre-fine-tuning.

## 5. Sources

- [Harnessing Large Language Models as Post-hoc Correctors — arXiv 2402.13414](https://arxiv.org/abs/2402.13414)
- [When Can LLMs Actually Correct Their Own Mistakes? A Critical Survey of Self-Correction of LLMs — arXiv 2406.01297](https://arxiv.org/abs/2406.01297)
- [JSONSchemaBench: A Rigorous Benchmark of Structured Outputs for Language Models — arXiv 2501.10868](https://arxiv.org/abs/2501.10868)
- [JSON Whisperer: Efficient JSON Editing with LLMs — arXiv 2510.04717](https://arxiv.org/abs/2510.04717)
- [Context-Enhanced Granular Edit Representation for Efficient and Accurate ASR Post-editing — arXiv 2509.14263](https://arxiv.org/abs/2509.14263)
- [guardrails-ai/guardrails on GitHub](https://github.com/guardrails-ai/guardrails)
- [jxnl/instructor on GitHub](https://github.com/jxnl/instructor)
- [mangiucugna/json_repair on GitHub](https://github.com/mangiucugna/json_repair)
- [stanfordnlp/dspy on GitHub](https://github.com/stanfordnlp/dspy)
- Internal: `docs/audit_sprint5/s5_off_components_decision_matrix.md` (project-level priors on lossy transforms over identity signals)
- Internal: `docs/sprint_top6/quick_decide_response_fixes.md` (activation plan, gates, rollback)
