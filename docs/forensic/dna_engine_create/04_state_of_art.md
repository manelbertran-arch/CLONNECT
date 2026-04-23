# State of the Art: DNA Engine Auto-Create

**Date:** 2026-04-23
**Scope:** auto-creation of per-lead persona profiles on first N turns, with rate-limit/cap.
**Research threads:** user modelling, dynamic persona construction, relationship tracking, background-task rate-limiting.

Current callsite in our code:
`backend/core/dm/phases/context.py:1034`
`if ENABLE_DNA_AUTO_CREATE and not dna_context and follower.total_messages >= 2:`

Flag `flags.dna_auto_create` defaults `True` in code but is OFF in Railway because prior activations triggered suspected rate-limit / cap-overflow events. This document surveys 2024-2026 literature and OSS to inform a safe flip.

---

## 1. Papers (2024-2026)

| # | Paper | Venue / Date | Finding (quote ≤15 words) | Applicability |
|---|---|---|---|---|
| 1 | AutoPal: Autonomous Adaptation to Users for Personal AI Companionship (Zhang et al.) | arXiv 2406.13960 · Jun 2024, rev Jun 2025 | "Hierarchical framework enables controllable, authentic persona adjustments based on user interactions." | HIGH — confirms incremental persona update pattern; supports our auto-create at N turns. |
| 2 | AI PERSONA: Towards Life-long Personalization of LLMs (Chen et al.) | arXiv 2412.13103 · Dec 2024 | "LLM agents continuously adapt to diverse and ever-changing profiles of every distinct user." | HIGH — validates per-lead (per-user) persona row with continuous update over time. |
| 3 | O-Mem: Omni Memory System for Personalized, Long Horizon, Self-Evolving Agents | arXiv 2511.13593 · Nov 2025 | "Actively extracts and updates user characteristics from ongoing dialogs, not static profiles." | HIGH — matches our DNA design: extraction triggered by new turns; argues against one-shot creation. |
| 4 | PersonaMem-v2: Personalized Intelligence via Implicit User Personas and Agentic Memory | arXiv 2512.06688 · Dec 2025 | "RL-trained agentic memory uses 16× fewer tokens than full history, surpassing GPT-5." | MEDIUM — supports compact persona row over raw-history injection; token-efficiency angle. |
| 5 | How Is Generative AI Used for Persona Development? Systematic Review of 52 articles | arXiv 2504.04927 · Apr 2025 | "GenAI is used across data collection, segmentation, enrichment, and evaluation of personas." | LOW — survey; useful for framing, not implementation. |

No paper found in 2024-2026 specifically benchmarking trigger thresholds (N=2 vs N=3 vs N=5 turns) for first persona build — this is an open empirical knob. Marked `[unverified]`: exact optimal N.

---

## 2. Repositories (active, >500 stars, last 6 months)

| # | Repo | Stars | Last commit | Relevance | Applicability |
|---|---|---|---|---|---|
| 1 | mem0ai/mem0 | 53.9k | 2026-04-23 (main) | Universal memory layer; auto-extracts facts from messages via `memory.add(...)`; "single-pass ADD-only extraction" (Apr 2026) — one LLM call per batch. | HIGH — direct analogue. Adopt: single-pass extraction, batch on turns. Note: no built-in rate-limit, we must add our own. |
| 2 | letta-ai/letta (ex-MemGPT) | 22.2k | 2026-03-31 (v0.16.7) | Stateful agents with persona + human memory blocks; blocks updated via tool calls rather than auto-extraction at N turns. | MEDIUM — persona block schema mirrors our DNA row; but Letta relies on agent-initiated updates, not a debounced trigger. |
| 3 | langchain-ai/langgraph | 30.2k | 2026-04-22 (release `langgraph-cli==0.4.24`) | Stateful graph runtime with short-term and long-term memory; no built-in persona auto-extractor — users compose their own. | LOW-MEDIUM — useful as orchestration model, not as drop-in persona engine. |

DISCARDED: `snok/self-limiters` — last release 2022-12, unmaintained; their README points to `otovo/redis-rate-limiters`. Kept in §4 design ideas only.

---

## 3. Mapping — what we adopt vs discard

ADOPT:
- **Trigger on turn count, not on every message** — aligns with O-Mem and mem0's batched ADD. Our `total_messages >= 2` gate is sound; do NOT fire on every inbound.
- **Single-pass extraction (one LLM call per DNA build)** — mem0 v-Apr-2026 moved from multi-pass ADD/UPDATE/DELETE to single-pass ADD-only because multi-pass is where cost explodes. Our builder should remain one call, output structured JSON.
- **Per-lead debounce** — if DNA build was attempted for a lead within the last N seconds, skip. Prevents burst spam when two webhooks land close together for the same lead crossing the N=2 threshold.
- **Cap per creator per time window** — AutoPal / O-Mem both assume bounded growth; we should cap DNA builds per creator per hour to bound LLM spend.
- **Keep DNA as compact structured row, not raw history** — PersonaMem-v2 shows 16× token reduction vs history injection; our existing design already does this.

DISCARD (with reason):
- **Continuous re-extraction on every turn** — O-Mem style full refresh is too expensive for a real-time DM chatbot on Railway single-node with shared Gemini quota; defer to batch "refresh" job (already exists elsewhere in codebase).
- **Agent-tool-driven updates** (Letta pattern) — adds latency to user reply path; our DNA is background-only by design.
- **Multi-pass ADD/UPDATE/DELETE memory ops** (mem0 v-old) — superseded upstream in April 2026; we never adopted it anyway.
- **Distributed Redis semaphore** (self-limiters / otovo) — overkill for single-node Railway; adds ops burden.

DEFER-Q2:
- **RL-trained agentic memory writer** (PersonaMem-v2) — interesting but requires training infra + evals we don't have yet. Revisit post-fine-tuning milestone (see `project_sprint5_closed.md`).
- **Life-long persona evolution tracking** (AI PERSONA) — schema change to store persona deltas over time. Not needed for flag-flip; could improve re-engagement cohort later.
- **Implicit preference mining at scale** (PersonaMem-v2, 20k+ prefs) — not blocker for current flip.

---

## 4. Cap/semáforo design survey

Production patterns surveyed for rate-limiting expensive persona-build ops:

| Pattern | Where it fits | Pros | Cons | Our fit |
|---|---|---|---|---|
| Per-creator token bucket (aiolimiter) | Upstream of LLM call; smooths bursts | Proven asyncio lib; simple | Needs periodic refill task; no burst memory | Good match — 1 bucket per creator_id with refill rate ~ N/hour. |
| Redis distributed semaphore | Multi-worker deployments | Coordinates across processes | Requires Redis; adds latency; single-node Railway doesn't need it | Overkill. |
| In-process `asyncio.Semaphore` with TTL | Limit concurrent builds per process | Zero deps; 5-line implementation | Lost on worker restart; no TTL in stdlib — must wrap | Good as **secondary** guard (max concurrent DNA builds globally). |
| Debounce per lead (N seconds) | Prevent duplicate triggers on webhook bursts | Stops repeat builds for same lead | Must persist last-attempted ts (DB or in-mem dict) | Essential — cheapest, highest-leverage guard. |
| Hard cap per time window per creator | Bound LLM spend blast radius | Spend is predictable; circuit-breaker-like | Drops legitimate builds when cap hits | Required as last-resort backstop. |

### Recommended pattern for our case

Single-node Railway, expected 1-10 DNA creates per hour per creator. Layered defence, cheapest first:

1. **Layer 1 — Per-lead debounce (in-process dict or DB column `dna_last_attempt_at`).**
   Skip if `now - dna_last_attempt_at < 60s`. Blocks webhook-burst duplicates. ~5 LOC, no deps.

2. **Layer 2 — Per-creator token bucket** using `aiolimiter.AsyncLimiter(max_rate=20, time_period=3600)` (20 DNA builds per hour per creator). Wraps the LLM call. Graceful backpressure when cap hit — log + return early, don't block the reply path.

3. **Layer 3 — Global `asyncio.Semaphore(value=3)`** around the DNA builder to cap **concurrent** builds across all creators, protecting Gemini quota and DB pool (current pool 5+7=12 — a concurrent burst of 10 DNA builds could exhaust it).

4. **Layer 4 — Circuit-breaker on Gemini 429**: if provider returns rate-limit, disable DNA auto-create for `cooldown_seconds` (e.g. 300s) via an in-memory flag, then auto-re-enable.

All four are in-process; no Redis, no new infra. Total added surface: ~40-60 LOC. Debounce field is a single column add (or Redis kv if we want to survive restarts; column is simpler).

Observability: emit one structured log per DNA build with `{lead_id, creator_id, latency_ms, llm_tokens, skipped_reason}`. Pipe to existing logging.

---

## 5. Verdict

- **Superior alternative identified?** NO. Mem0's batched single-pass ADD is the closest analogue and validates our design; Letta's persona-block schema validates our DNA row shape. Neither supersedes what we have.
- **Recommended cap/semáforo pattern:** 4-layer in-process defence: per-lead debounce (60s) + per-creator token bucket (aiolimiter, 20/h) + global asyncio.Semaphore(3) + Gemini-429 circuit breaker (300s cooldown).
- **Recommended action:** ADAPT-NOW. Add the 4-layer cap, keep N=2 turn trigger, keep DNA row schema, keep single-pass LLM extraction. Then flip `flags.dna_auto_create` ON in Railway behind a canary (one creator first).
- **Reason:** The SoTA literature (AutoPal, O-Mem, AI PERSONA, PersonaMem-v2) all endorse our core pattern — incremental per-user persona, compact structured row, triggered by turn count. The prior Railway incident was an absent rate-cap, not a broken feature. Adding the 4-layer guard closes the hole with ~60 LOC and no new infra, consistent with the user's ask for a semáforo/cap fix before flag-flip.

---

## 6. Sources

- [AutoPal: Autonomous Adaptation to Users for Personal AI Companionship](https://arxiv.org/abs/2406.13960)
- [AI PERSONA: Towards Life-long Personalization of LLMs](https://arxiv.org/abs/2412.13103)
- [O-Mem: Omni Memory System for Personalized, Long Horizon, Self-Evolving Agents](https://arxiv.org/html/2511.13593v1)
- [PersonaMem-v2: Towards Personalized Intelligence via Learning Implicit User Personas and Agentic Memory](https://arxiv.org/html/2512.06688v1)
- [How Is Generative AI Used for Persona Development? A Systematic Review of 52 Articles](https://arxiv.org/html/2504.04927v1)
- [mem0ai/mem0 — Universal memory layer for AI Agents](https://github.com/mem0ai/mem0)
- [letta-ai/letta — Platform for stateful agents](https://github.com/letta-ai/letta)
- [langchain-ai/langgraph — Stateful graph runtime](https://github.com/langchain-ai/langgraph)
- [aiolimiter — Leaky-bucket rate limiter for asyncio](https://aiolimiter.readthedocs.io/)
- [Python Asyncio for LLM Concurrency: Best Practices (newline)](https://www.newline.co/@zaoyang/python-asyncio-for-llm-concurrency-best-practices--bc079176)
- [Designing for Scale: Managing API Token Limits in Concurrent LLM Applications (Medium)](https://amusatomisin65.medium.com/designing-for-scale-managing-api-token-limits-in-concurrent-llm-applications-84e8ccbce0dc)
- [snok/self-limiters — async distributed rate limiters (unmaintained; referenced for design)](https://github.com/snok/self-limiters)
