# State of the Art: Commitment Tracker

**Date:** 2026-04-23
**Scope:** multi-turn commitment detection + persistence for persona-fidelity DM chatbot.
**Research threads:** dialogue state tracking (DST), belief tracking, promise/commitment extraction, entity-event tracking, long-term agent memory.

**Current implementation** (`backend/services/commitment_tracker.py`): hardcoded Spanish regex patterns (`te\s+(envío|mando|paso)`, `quedamos\s+el`, `mañana`, etc.) → `CommitmentModel` rows with `commitment_type` in {delivery, info_request, meeting, follow_up, promise}, `due_date` from temporal keyword lookup (mañana→+1d, etc.). Detection is `sender="assistant"` only; persistence is sync via `SessionLocal`; prompt injection via `get_pending_text()`. Flag `ENABLE_COMMITMENT_TRACKING` default True, **currently OFF in Railway**.

**Key anti-pattern:** 11 commitment regexes + 7 temporal regexes are **hardcoded Spanish**. No creator adaptation, no multilingual fallback, no evidence these patterns cover the real commitment vocabulary of `iris_bertran`. Migration target: vocab_meta-derived patterns OR LLM-as-extractor.

---

## 1. Papers (2024-2026)

| # | Paper | Venue / Date | Finding (quote ≤15 words) | Applicability |
|---|---|---|---|---|
| 1 | Hu et al. — Large Language Models as Zero-shot Dialogue State Tracker through Function Calling (FnCTOD) | ACL 2024 Main, May 2024 | "improves zero-shot DST, allowing adaptation to diverse domains without extensive data collection or model tuning" | HIGH — direct template for LLM-extractor of commitments via function-calling schema (replaces regex tree) |
| 2 | Tan et al. — In Prospect and Retrospect: Reflective Memory Management for Long-term Personalized Dialogue Agents (RMM) | ACL 2025 Long, Jul 2025 | "Prospective Reflection, which dynamically summarizes interactions across granularities into a personalized memory bank" | MEDIUM — our `get_pending_text()` is a prospective summary; retrospective RL refinement is deferrable |
| 3 | Xu et al. — A-MEM: Agentic Memory for LLM Agents | NeurIPS 2025, Feb 2025 | "dynamically organize memories in an agentic way" (Zettelkasten-style linking) | LOW-MEDIUM — over-engineered for our flat `commitments` table; revisit if we add cross-lead memory graphs |
| 4 | Bhat et al. — PARSE: LLM Driven Schema Optimization for Reliable Entity Extraction | EMNLP 2025 Industry Track, Oct 2025 | "JSON schemas themselves are a form of natural language understanding contract" | HIGH — validates hybrid regex+LLM+JSON-schema approach for reliable extraction in production |
| 5 | `[unverified]` Cohen/Singh multi-agent commitment semantics revisit — no 2024-2026 ACL/EMNLP paper found in searches | — | — | DISCARD — classical theory, not operationalizable for DM chatbot at this sprint |

Notes:
- "Ellis 2024" and "Nguyen 2025" promise-tracking papers listed as candidates were **not found** in web searches → dropped as unverified.
- 2024-2025 literature treats "commitment tracking" as a subset of DST / agent memory, not as an independent task. No dedicated benchmark exists for conversational commitment extraction in Spanish DMs.

---

## 2. Repositories (active, >500 stars, last 6 months)

| # | Repo | Stars | Last commit/release | Relevance | Applicability |
|---|---|---|---|---|---|
| 1 | langchain-ai/langgraph | 30.2k | active 2026 (6,761 commits on main) | Stateful agent persistence with checkpointers (Redis/Postgres/SQLite); "comprehensive memory" short+long term | HIGH reference architecture; we already have equivalent (`CommitmentModel` + SessionLocal). Do NOT migrate framework — adopt pattern of short-term (thread) vs long-term (store) separation |
| 2 | letta-ai/letta (ex-MemGPT) | 22.2k | v0.16.7 on 2026-03-31 | Stateful agents with self-editing memory blocks; MemGPT paper has 13k+ derivative stars | MEDIUM — self-editing memory is overkill for commitments (they're append-only + status-transition). Idea worth stealing: agent marks its own commitment fulfilled via tool-call |
| 3 | RasaHQ/rasa | 21.1k | v3.6.21 on 2025-01-14 (maintenance mode) | `tracker_store.py` = dialogue state persistence with SQL/Mongo/Redis backends; no commitment primitive | LOW — Rasa is in maintenance; team moved to CALM. Our tracker store pattern already matches |

Discarded from candidate list:
- **ConvLab-3**: not verified in active-repo search; deprioritized.
- **TRADE / T5-DST derivatives**: pre-LLM-era DST, superseded by FnCTOD/LDST.

---

## 3. Mapping — what we adopt vs discard

### ADOPT (sprint-top6, pre-flag-flip)

- **Hybrid detection pipeline (regex-first, LLM-fallback)**: keep regex as fast path for ~70% high-confidence cases; route low-confidence / novel-phrasing turns to LLM extractor with JSON schema (PARSE pattern). Cost-bounded: LLM call only when regex fails AND bot turn contains future-tense/imperative heuristic.
- **JSON-schema commitment contract** (PARSE-inspired): define `{type: enum[delivery|info_request|meeting|follow_up|promise], due_iso: str|null, subject: str, confidence: float}` so the LLM extractor output validates and fails closed on malformed data.
- **vocab_meta migration for regex patterns**: move the 11 Spanish patterns from hardcoded constants into a `commitment_patterns` section in `vocab_meta_{creator_id}`. Mine from creator's historical DMs (we already have `bootstrap_vocab_meta_*` scripts). Per-creator, per-language, zero-hardcoding compliant.
- **Function-calling zero-shot DST (FnCTOD)** as the LLM-fallback implementation — schema-as-function-signature, LLM returns a tool call, we parse JSON. Supports any language without retraining.
- **Prospective summarization for `get_pending_text()`** (RMM-inspired, lightweight): current format is already prospective. Keep as-is. Skip retrospective-RL refinement.

### DISCARD

- **Full migration to LangGraph/Letta**: framework cost is not justified. We already have equivalent persistence via `CommitmentModel`. Reference their patterns, don't adopt the runtime.
- **A-MEM Zettelkasten cross-linking**: commitments are per-lead flat records; graph structure adds complexity with no fidelity gain.
- **Cohen/Singh multi-agent commitment logic**: theoretical; not operationalizable in DM chatbot this quarter.
- **Pure LLM-only extraction**: adds ~300-600ms latency to every bot turn and costs per-message. Regex-first hybrid is Pareto-optimal.
- **Full retraining / fine-tuned DST model**: blocked by Sprint 5 constraints on identity-signal preservation (CLAUDE.md rule); DST fine-tuning is orthogonal but we avoid extra FT experiments pre-persona-FT.

### DEFER-Q2

- **Retrospective reflection (RMM)** on commitment retrieval: online RL refinement of which pending commitments to surface. Wait until we have >30 days of commitment hit/miss telemetry.
- **Multi-lingual extension** (CA, EN): once vocab_meta-per-creator is in place, extending to other locales is config-only. Defer until a non-ES creator onboards.
- **Self-editing memory** (Letta-style agent marking own commitments fulfilled via tool-call): defer until bot has tool-use in prompt. Current arch has no tool-call loop.
- **Commitment-aware scoring**: weight pending-commitment-overdue signal in lead_scoring. Out of scope for commitment tracker; owned by scoring service.

---

## 4. Verdict

- **Superior alternative identified?** YES — but only as an additive layer, not a replacement.
- **Recommended action:** ADAPT-NOW before activation. Do NOT flip `ENABLE_COMMITMENT_TRACKING=true` on Railway until the two migrations below land.
- **Reason:** Current impl has two gating defects:
  1. Hardcoded ES patterns violate zero-linguistic-hardcoding constraint + guarantee coverage gaps for creator-specific phrasing.
  2. No LLM fallback means novel commitments ("te bajo el PDF al Drive", "apunto en calendario", creator slang) silently miss → false-negative reminders in prompt → fidelity regression risk.

### Verdict questions answered

**Q1: Is there a 2024-2026 advance our impl should adopt before activation?**
YES — FnCTOD (ACL 2024) for zero-shot commitment extraction via function-calling, and PARSE (EMNLP 2025) for JSON-schema-reliable structured output. Both are directly compatible with our `Gemma/Gemini` provider stack. The advance is **hybrid regex+LLM**, not LLM-only. Pure-LLM has latency and cost issues; pure-regex has coverage issues. Adopt hybrid.

**Q2: vocab_meta with creator-specific triggers OR small multilingual LLM classifier call?**
**BOTH, in sequence.**
- **Path A (ship first, low-risk):** migrate the 11 Spanish patterns out of `commitment_tracker.py` and into `vocab_meta_{creator_id}.commitment_patterns`, mined from creator DM history via `scripts/bootstrap_vocab_meta_*.py`. Zero latency cost, zero new dependencies, compliant with zero-hardcoding. Covers the ~70% high-frequency cases.
- **Path B (ship second, behind sub-flag `COMMITMENT_LLM_FALLBACK`):** add LLM extractor (Gemini-Flash / Gemma-4) invoked only when regex yields zero matches AND bot-turn contains a future-tense heuristic. Cost-bounded: expected ~15-25% of turns, ~200-400ms p50 added latency on those turns only. Use FnCTOD-style function-calling with PARSE-style JSON schema.

Path A is the minimum for activation. Path B is the completeness layer; can ship within same sprint if latency budget allows.

---

## 5. Sources

- [Large Language Models as Zero-shot Dialogue State Tracker through Function Calling (FnCTOD)](https://arxiv.org/abs/2402.10466)
- [In Prospect and Retrospect: Reflective Memory Management for Long-term Personalized Dialogue Agents (RMM)](https://aclanthology.org/2025.acl-long.413/)
- [A-MEM: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110)
- [PARSE: LLM Driven Schema Optimization for Reliable Entity Extraction](https://arxiv.org/abs/2510.08623)
- [Towards LLM-driven Dialogue State Tracking (LDST)](https://aclanthology.org/2023.emnlp-main.48.pdf)
- [LangGraph — stateful agent orchestration](https://github.com/langchain-ai/langgraph)
- [LangGraph Persistence docs](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Letta (ex-MemGPT) — stateful agents with persistent memory](https://github.com/letta-ai/letta)
- [RasaHQ/rasa — tracker_store.py](https://github.com/RasaHQ/rasa/blob/main/rasa/core/tracker_store.py)
- [Towards Lifelong Dialogue Agents via Timeline-based Memory Management (NAACL 2025)](https://aclanthology.org/2025.naacl-long.435/)
- [Memory OS of AI Agent (EMNLP 2025)](https://aclanthology.org/2025.emnlp-main.1318.pdf)
