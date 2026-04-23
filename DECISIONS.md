# Decisions

This file tracks all non-trivial technical decisions made during this project.
See `rules/common/decisions.md` for the logging format and rules.

---

## [Date] — Initial Stack Selection
**Chosen:** [Fill in]  
**Alternatives:** [Fill in]  
**Why:** [Fill in]  
**Trade-offs:** [Fill in]  
**Revisit if:** [Fill in]  

---

## 2026-04-23 — Split `core/tone_profile_db.py` into 3 domain repos

**Chosen:** Split into `core/data/{tone_profile_repo,content_chunks_repo,instagram_posts_repo}.py`; keep `core/tone_profile_db.py` as a ≤60-LOC shim re-exporting 14 names + 1 new public accessor. Branch: `forensic/tone-profile-db-20260423`. Not merged.
**Alternatives:** (1) leave as-is (violates 500-LOC cap, file name mis-describes); (2) split but no shim (breaks 9 importers — violates BC constraint).
**Why:** file mixed three unrelated aggregates (tone profiles, RAG chunks, IG posts) in one 540-LOC service under a name that only described the first; bundling masked a critical cache-subscript bug (B-01) and kept 7 tests stale since 2026-03-17. Shim keeps the 9 existing importers unchanged.
**Trade-offs:** brief dual-source-of-truth through the shim until callers migrate; per-repo tests must also cover what used to be co-located.
**Revisit if:** all 9 importers migrate off the shim → remove `core/tone_profile_db.py` entirely.

---

## 2026-04-23 — Tone cache stampede protection — deferred, not Phase 5 scope

**Chosen:** No single-flight protection in this PR. `_tone_cache.get()` is not wrapped in a `threading.Condition` or `asyncio.Lock`.
**Alternatives:** adopt `cachetools @cached(lock=Condition())`-style gating now.
**Why:** uvicorn runs single-worker (per Worker-3 note); today concurrent misses for the same `creator_id` do not race in practice. Adding a lock wrapper changes behaviour and falls outside Phase 5 scope ("no Railway changes").
**Trade-offs:** if Railway ever moves to multi-worker (`--workers >1`), N concurrent miss requests for the same creator will fan out N parallel DB reads. Cheap today, expensive at scale.
**Revisit if:** uvicorn is upgraded to multi-worker, OR creator count > 500 with sustained bootstrap traffic, OR CCEE monitoring shows tone-profile fetch latency spikes.

---

## 2026-04-23 — Inventory reclassification after tone_profile_db split

**Chosen:** Post-split, `tone_profile_repo.py` stays in the pipeline-DM inventory (BOOTSTRAP phase, feeds Doc D). `content_chunks_repo.py` and `instagram_posts_repo.py` move to the Data / Ingestion layer and leave the pipeline-DM inventory.
**Alternatives:** keep all three in pipeline-DM (preserves historical count); move all three to Data layer (loses the tone→Doc D coupling signal).
**Why:** only `tone_profile_repo.py` is read during agent init to build the prompt. The other two are batch/ingestion producers — consumed indirectly via auto_configurator (tone) or via a separate retrieval layer (RAG), never read at DM time.
**Trade-offs:** net-zero change to the pipeline-DM no-optimized-ON count (49 → 49); +2 systems tracked in the Data layer.
**Revisit if:** a DM-time code path ever reads content_chunks or instagram_posts directly.

---

## 2026-04-23 — Prometheus metrics for new repos — deferred

**Chosen:** No new Prometheus counters added in this PR.
**Alternatives:** register `tone_profile_cache_hits_total`, `content_chunks_upserts_total`, `instagram_posts_saves_total` via the central `core/observability/metrics.py` registry.
**Why:** adding metric names to the central registry touches a shared file outside the refactor scope; the split PR should stay minimal. Metrics are pull-based and non-behavioural, so there is no BC risk in adding them later.
**Revisit if:** the measurement plan in Phase 6 requires runtime cache-hit visibility beyond `get_tone_cache_stats()`, or if the tone-profile fetch path ever enters the hot DM loop.

---

