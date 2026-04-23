# Phase 1 — Description & value of `tone_profile_db.py`

> Branch: `forensic/tone-profile-db-20260423`
> Target: `backend/core/tone_profile_db.py` (540 LOC)
> Pipeline layer: **BOOTSTRAP** (tone) + **INGESTIÓN batch** (posts, chunks) — no hot path DM
> Railway flag: _none_ — always ON, not ablatable as a unit
> CEO decision: **SPLIT estructural** into 3 repositories (CEO 2026-Q2 plan accepted)

---

## TL;DR

The file is named `tone_profile_db.py` but exposes **three unrelated persistence domains** glued into a single module. Only one of them has anything to do with tone. The other two (Instagram posts, RAG content chunks) live there for historical reasons only. This phase documents what each domain does, the value it delivers, and why the current mixing is actively harmful.

---

## The three domains

### Domain A — `tone_profiles` (creator tone / personality)

**Lines:** 12–14 (cache stanza, mis-placed in prologue) + 17–209 (functions) = **196 LOC**
**Table:** `tone_profiles` (`api.models.ToneProfile`)
**Cache:** `_tone_cache = BoundedTTLCache(max_size=50, ttl_seconds=600)` — module-level
**Public surface (6 functions):**

| Function | Kind | Purpose |
|---|---|---|
| `save_tone_profile_db(creator_id, profile_data)` | async | Upsert tone profile JSON blob |
| `get_tone_profile_db(creator_id)` | async | Cached read |
| `get_tone_profile_db_sync(creator_id)` | sync | Same, for non-async callers (e.g. bootstrap) |
| `delete_tone_profile_db(creator_id)` | async | Delete + cache invalidate |
| `list_profiles_db()` | sync | Enumerate creator_ids with a profile |
| `clear_cache(creator_id=None)` | sync | Manual cache eviction |

**Value delivered:**
Personality persistence. The `profile_data` JSON is the source of truth for the creator's **tone signature** (voice, cadence, catch-phrases, vocab). On bootstrap it is read once and **injected into Doc D** — the persona block that anchors the LLM's identity during DM generation. Without this the clone reverts to a generic assistant.

**Pipeline phase:** **BOOTSTRAP / COLD PATH.**
Read at `DMResponderAgentV2` init (and by auto_configurator when refreshing persona). Not read per-message — Doc D is pre-built. This is why a tiny cache (50 creators × 10 min) is sufficient.

**Sensitivity (CLAUDE.md):**
Identity-defining. Must not be compressed/summarized/reordered (documented regression Sprint 2 & Sprint 5). The DAO layer only moves bytes, but any future `.get(...)` caller that re-shapes the blob is a latent Style-Fidelity regression.

---

### Domain B — `content_chunks` (RAG chunk persistence)

**Lines:** 211–360 (150 LOC — banner 211–213 + functions 214–360)
**Table:** `content_chunks` (`api.models.ContentChunk`)
**Cache:** _none_
**Public surface (3 functions):**

| Function | Kind | Purpose |
|---|---|---|
| `save_content_chunks_db(creator_id, chunks)` | async | Upsert chunk rows keyed by `(creator_id, chunk_id)` |
| `get_content_chunks_db(creator_id)` | async | Load all chunks for a creator |
| `delete_content_chunks_db(creator_id, source_type=None)` | async | Delete all, or by `source_type` (e.g. `youtube`, `instagram_post`) |

**Value delivered:**
Storage layer for the **RAG index**. Chunks carry `content`, `source_type`, `source_id`, `source_url`, `title`, `chunk_index`, `total_chunks`, and an `extra_data` JSONB (metadata — embeddings live on `content_chunks` via pgvector column, managed outside this module). Downstream retrieval (Self-RAG gate) reads these rows.

**Pipeline phase:** **INGESTIÓN BATCH.**
Written by ingestion v2 pipelines (Instagram + YouTube) during creator onboarding and on feed-webhook-triggered re-indexing. Never written from the hot DM path.

**Why no cache:** chunks are read in bulk and then embedded/indexed by a separate retrieval layer; per-creator round-trips are rare outside ingestion, and the payload is too large to cache at module scope.

---

### Domain C — `instagram_posts` (Instagram post content layer)

**Lines:** 363–540 (178 LOC — banner 363–365 + functions 366–540)
**Table:** `instagram_posts` (`api.models.InstagramPost`)
**Cache:** _none_
**Public surface (4 functions):**

| Function | Kind | Purpose |
|---|---|---|
| `save_instagram_posts_db(creator_id, posts)` | async | Upsert posts keyed by `(creator_id, post_id)`, parses hashtags/mentions from caption |
| `get_instagram_posts_db(creator_id)` | async | Load posts ordered by timestamp desc |
| `delete_instagram_posts_db(creator_id)` | async | Nuke all posts for a creator |
| `get_instagram_posts_count_db(creator_id)` | sync | Cheap count (used in admin/debug) |

**Value delivered:**
Raw post-level content lake for a creator. Feeds two downstream processes:
1. **Tone mining** — auto_configurator analyzes captions to refine the tone profile.
2. **RAG chunk generation** — ingestion splits captions into `content_chunks`.

It is the **source-of-truth content layer** between Instagram Graph API and everything derived from it (tone, chunks, quotes, citations).

**Pipeline phase:** **INGESTIÓN BATCH + WEBHOOK.**
Written by Instagram ingestion v2 and the feed webhook handler when a creator posts new content. Read by auto_configurator and the admin/debug endpoints. Not read from the DM hot path.

---

## Why the current mixing is actively problematic

1. **Discoverability.** A developer looking for Instagram post persistence will not find it under `tone_profile_db.py`. The file name misrepresents the content, so `grep` for `InstagramPost` lands in a file named after a different domain.
2. **LOC budget.** 540 LOC **violates the project 500-LOC ceiling** for a single file. The only reason the file is this large is that it carries three domains that never needed to coexist.
3. **Inventory pipeline reclassification.** The pipeline-DM inventory (branch `inventory/pipeline-dm-consolidated`) lists this file under DM pipeline because of `tone_profiles`. But `instagram_posts` and `content_chunks` are batch/ingestion — they have nothing to do with DM response latency or behavior. Splitting lets the inventory classify each correctly: `tone_profiles` stays near BOOTSTRAP, the other two move to a **Data layer / ingestion** bucket.
4. **Testing blast radius.** The current test file asserts behaviors across all three domains. Seven of eighteen tests are stale because they assume `_tone_cache` is a plain `dict` (it is a `BoundedTTLCache`) — the failures in the `tone_profiles` cache contract prevent clean signal on the other two domains. Splitting isolates test ownership per domain.
5. **Cache scope creep.** The module-level `_tone_cache` is only touched by Domain A, but lives at module scope so any future cache added for posts or chunks collides semantically. A per-repo cache pattern is cleaner.
6. **Error handling drift.** Each domain swallows exceptions to `return 0 / [] / False / None`, but the contract is inconsistent: `save_instagram_posts_db` does `traceback.print_exc()` in addition to `logger.error`, while the tone and chunk variants do not. This divergence is invisible today because the three sit in one file and feel uniform — separation forces each repo to declare its own error contract.
7. **Hardcoding.** `BoundedTTLCache(max_size=50, ttl_seconds=600)` at module scope cannot be tuned per environment without editing source. This is a symptom of one-file-three-domains: no natural place for a `TONE_CACHE_*` env block.
8. **Zero module docstring.** 540 LOC with no module docstring means a reader has to parse the `# ====` banner comments to realize the file is a three-domain union. That is the whole problem in one visual artifact.

---

## LOC reconciliation (540 = 196 + 150 + 178 + 16)

| Range | LOC | Content | Bucket |
|---|---|---|---|
| 1–11 | 11 | docstring stub + imports + logger + blanks | shared prologue |
| 12–14 | 3 | cache comment + import + init | **Domain A** (mis-placed in prologue) |
| 15–16 | 2 | blanks | shared |
| 17–209 | 193 | `_get_db_session` + tone functions | **Domain A** |
| 210 | 1 | blank | shared |
| 211–213 | 3 | `# === CONTENT CHUNKS ===` banner | **Domain B** (banner) |
| 214–360 | 147 | chunk functions | **Domain B** |
| 361–362 | 2 | blanks | shared |
| 363–365 | 3 | `# === INSTAGRAM POSTS ===` banner | **Domain C** (banner) |
| 366–540 | 175 | post functions | **Domain C** |

**Sum:** 196 + 150 + 178 + 16 = 540 ✓. No fourth block.

Findings flagged here (formalised in Phase 3): the 4-line module docstring only mentions `ToneProfiles` (mis-represents the file); `_get_db_session` (lines 17–24) is defined but never called — every function re-imports `get_db_session` directly from `api.database`.

---

## Inventory reclassification (post-Phase 5)

| Bucket | Before split | After split | Delta |
|---|---|---|---|
| Pipeline DM, no-optimized-ON | 49 (incl. "Tone Profile DB") | 49 (incl. "tone_profile_repo") | **0** — internal cleanup only |
| Data / Ingestion layer | N | N + 2 (`content_chunks_repo`, `instagram_posts_repo`) | **+2** |

Rationale: `tone_profile_repo` stays in the DM inventory because it is read at `DMResponderAgentV2` init to build Doc D; it is BOOTSTRAP but still DM-pipeline scope. `content_chunks_repo` and `instagram_posts_repo` are pure ingestion/batch with no DM-time consumer — retrieval at DM time reads the RAG index via a separate layer, not via these repos. The indirect chain `instagram_posts → auto_configurator → tone_profiles → Doc D` is batch-refresh, not per-DM, so the producers correctly move to the Data layer.

---

## Post-refactor shape (preview for Phase 5)

| New file | Domain | ~LOC | Notes |
|---|---|---|---|
| `backend/core/data/tone_profile_repo.py` | Domain A | ~150 | Owns `_tone_cache` + env-tunable sizing |
| `backend/core/data/instagram_posts_repo.py` | Domain C | ~180 | Stateless DAO |
| `backend/core/data/content_chunks_repo.py` | Domain B | ~180 | Stateless DAO |
| `backend/core/tone_profile_db.py` | shim | ~30 | `from .data.* import *` — backward compat for the 9 callsites |

The shim keeps the 9 productive callsites unchanged in Phase 5; migration of imports is a separate follow-up.

---

## STOP — End of Phase 1.
