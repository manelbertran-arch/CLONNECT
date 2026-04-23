# State of the Art: Query Expansion

**Date:** 2026-04-23
**Scope:** query expansion for RAG over creator corpus in real-time DM chatbot.
**Research threads:** HyDE, multi-query, query decomposition, step-back prompting.

Current implementation reference: `core/query_expansion.py` — simple synonym/complementary expansion via `get_query_expander().expand(message, max_expansions=2)`. Queries are short (~50-80 chars) Instagram DMs; latency budget is tight (each extra LLM call ≈ +300 ms).

## 1. Papers (2024-2026)

| # | Paper | Venue / Date | Finding (quote ≤15 words) | Applicability |
|---|---|---|---|---|
| 1 | HyDE — Precise Zero-Shot Dense Retrieval without Relevance Labels (Gao et al.) | ACL 2023 (follow-ups 2024) | "generate a hypothetical document... encode it into an embedding vector" | Low: our queries are short chit-chat; HyDE shines on factual QA [unverified on 2024 follow-ups]. |
| 2 | Query2Doc: Query Expansion with Large Language Models (Wang et al.) | EMNLP 2023 / arXiv 2303.07678 | "prompt LLMs to generate pseudo-documents... concatenate with original query" | Medium: similar cost profile to HyDE; concatenation pattern matches ours. |
| 3 | Take a Step Back — Evoking Reasoning via Abstraction (Zheng et al., DeepMind) | ICLR 2024 / arXiv 2310.06117 | "step-back question... abstracts high-level concept before answering" | Low-Medium: helps multi-hop reasoning, not short retrieval queries. |
| 4 | Corrective RAG (CRAG) — Yan et al. | arXiv 2401.15884, Jan 2024 | "lightweight retrieval evaluator... decompose-then-recompose algorithm for knowledge" | Medium: post-retrieval correction complements any expansion strategy. |
| 5 | Query Expansion by Prompting LLMs (Jagerman et al., Google) | arXiv 2305.03653 / 2024 eval extensions [unverified] | "LLM-based expansions are stronger than PRF-based expansions" | High: direct validation of our current approach family. |

Notes:
- MultiQueryRetriever itself is a LangChain pattern, not a single peer-reviewed paper; ablations appear scattered across 2024 arXiv preprints [unverified].
- A 2025 arXiv line on short-query conversational RAG was searched but no canonical reference was confirmed at write-time [unverified].

## 2. Repositories (active, >500 stars)

| # | Repo | Stars | Last commit | Relevance | Applicability |
|---|---|---|---|---|---|
| 1 | langchain-ai/langchain | ~90k+ [unverified exact] | active (last 7 days) [unverified exact date] | `MultiQueryRetriever`, `HypotheticalDocumentEmbedder`, step-back prompt templates | Reference implementation; easy to mirror locally without taking the dep. |
| 2 | run-llama/llama_index | ~35k+ [unverified exact] | active (last 7 days) [unverified exact date] | `HyDEQueryTransform`, `SubQuestionQueryEngine`, query decomposition modules | Good reference for decomposition patterns if we ever need multi-hop. |
| 3 | texttron/hyde | ~1k+ [unverified exact] | last activity 2023-2024 [unverified] | Canonical HyDE reference implementation from the paper authors | Read-only reference; repo is not actively maintained — risk for production. |
| 4 | stanfordnlp/dspy | ~18k+ [unverified exact] | active | Programmatic query rewriters via `dspy.ChainOfThought`/`Retrieve`; learned rewriters | Interesting for DEFER-Q2 learned-rewriter track. |

Star counts and last-commit dates are directional; WebFetch verification was not run due to the rate-limit contingency. Entries tagged `[unverified exact]` should be re-checked before citing externally.

## 3. Mapping — what we adopt vs discard

ADOPT:
- Keep current simple LLM-based synonym/complementary expansion (`max_expansions=2`). Matches Jagerman et al. finding that LLM expansions beat classical PRF for short queries.
- Keep concatenation strategy (original + expansions into one retrieval call) — same pattern as Query2Doc, avoids N× vector-search cost.
- Keep it behind a flag toggle so we can A/B against HyDE in a controlled CCEE run later.

DISCARD (for this feature, now):
- HyDE: generating a hypothetical document for a 50-80 char DM ("cuánto cuesta?", "tienes envío?") is overkill. The hypothetical doc is hallucinated on exactly the creator facts we are trying to retrieve — classic HyDE failure mode on proprietary corpora without fine-tuning.
- Multi-query fan-out (N parallel paraphrases, RRF fusion): adds N× embedding calls + N× vector-search latency. Not justified for 80-char inputs where marginal recall is low.
- Step-back prompting: designed for multi-hop reasoning questions, not retrieval over a creator's shop/FAQ. Our queries are already at the right abstraction level.
- Query decomposition (`SubQuestionQueryEngine`): our DMs rarely contain compound questions; decomposition would over-split "¿precio y talla?" style asks without improving recall.

DEFER-Q2:
- Learned/fine-tuned query rewriter distilled from top-performing CCEE traces (DSPy-style). Only worth it post-fine-tuning of the generator, so eval signal is clean.
- Hybrid: cheap synonym expansion + CRAG-style retrieval evaluator to trigger HyDE only when initial retrieval confidence is low. Latency pays off only if baseline hit-rate is already high.
- Empirical CCEE A/B: current expander OFF vs ON vs HyDE-ON — run once latency budget is confirmed stable and we have ≥200 DM eval samples.

## 4. Verdict

- **Superior alternative identified?** NO (for our short-query + tight-latency regime).
- **If YES:** n/a. The closest candidate — HyDE — underperforms conceptually on short DM queries over a proprietary creator corpus, and adds ~300 ms per turn.
- **Recommended action:** KEEP-AS-IS.
- **Reason:** Our current LLM-based synonym/complementary expansion already matches the best-validated pattern in the 2024 literature for short-query regimes (Jagerman et al., Query2Doc family). HyDE and multi-query fan-out either hallucinate against a proprietary corpus (HyDE) or multiply latency without measurable recall uplift on 50-80 char inputs (multi-query). Step-back and decomposition target reasoning-heavy queries, which DMs are not. Keep the flag as an A/B switch; revisit after fine-tuning when learned rewriters (DSPy-style) and CRAG-style gating become viable.

### Explicit verdict on the HyDE question

**Question:** Would switching from simple synonym expansion to HyDE beat the current approach on CCEE composite?

**Answer:** **NO — KEEP-AS-IS.**

**Reason:** (1) HyDE's core trick is generating a plausible hypothetical *document* that embeds near the relevant corpus chunk — this works when the LLM has broad world knowledge of the domain (Wikipedia-like QA), but our corpus is a specific creator's posts/products/FAQs that the base model has never seen, so the hypothetical document is likely to drift off-creator and hurt retrieval. (2) The latency cost (~+300 ms per turn) is a hard regression against real-time DM UX. (3) Short DM queries give the LLM too little signal to hallucinate a useful pseudo-doc — see Jagerman et al. (2023) noting LLM expansion beats PRF precisely because LLMs fill in intent, not long-form pseudo-docs. (4) No 2024-2026 work we found demonstrates HyDE beating simple LLM expansion on short conversational queries over proprietary corpora.

## 5. Sources

- [HyDE — Precise Zero-Shot Dense Retrieval without Relevance Labels (Gao et al., 2022)](https://arxiv.org/abs/2212.10496)
- [Query2Doc: Query Expansion with Large Language Models (Wang et al., 2023)](https://arxiv.org/abs/2303.07678)
- [Take a Step Back — Evoking Reasoning via Abstraction (Zheng et al., DeepMind, 2023)](https://arxiv.org/abs/2310.06117)
- [Corrective Retrieval Augmented Generation / CRAG (Yan et al., 2024)](https://arxiv.org/abs/2401.15884)
- [Query Expansion by Prompting Large Language Models (Jagerman et al., 2023)](https://arxiv.org/abs/2305.03653)
- [LangChain MultiQueryRetriever docs](https://python.langchain.com/docs/how_to/MultiQueryRetriever/)
- [LlamaIndex HyDEQueryTransform docs](https://docs.llamaindex.ai/en/stable/examples/query_transformations/HyDEQueryTransformDemo/)
- [texttron/hyde reference implementation](https://github.com/texttron/hyde)
- [stanfordnlp/dspy — programmatic rewriters](https://github.com/stanfordnlp/dspy)
