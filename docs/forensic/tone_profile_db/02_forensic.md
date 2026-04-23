# Phase 2 — Forensic: line-by-line, 9 callsites, tests, git blame

> Target: `backend/core/tone_profile_db.py` (540 LOC)
> Branch: `forensic/tone-profile-db-20260423`

---

## 1. Line-by-line function → domain map

| Range | LOC | Identifier | Kind | Domain | Notes |
|---|---|---|---|---|---|
| 1–4 | 4 | module docstring | text | shared | **Stub** — mentions only `ToneProfiles`, omits chunks/posts |
| 6–8 | 3 | imports | code | shared | `logging`, `typing`, `datetime` |
| 10 | 1 | `logger` | code | shared | module logger |
| 12–14 | 3 | `_tone_cache` init | code | **A** (mis-placed in prologue) | `BoundedTTLCache(max_size=50, ttl_seconds=600)` — hardcoded |
| 17–24 | 8 | `_get_db_session()` | sync fn | **DEAD CODE** | Defined but never called; every consumer re-imports `get_db_session` directly from `api.database` |
| 27–78 | 52 | `save_tone_profile_db` | async fn | A | Upsert; writes cache via `.set()` |
| 81–114 | 34 | `get_tone_profile_db` | async fn | A | **Latent bug**: cache-hit path uses `_tone_cache[creator_id]` subscript — not supported by `BoundedTTLCache` |
| 117–144 | 28 | `get_tone_profile_db_sync` | sync fn | A | **Same latent bug** at line 124 |
| 147–178 | 32 | `delete_tone_profile_db` | async fn | A | Uses `.pop()` — OK |
| 181–198 | 18 | `list_profiles_db` | sync fn | A | `SELECT creator_id FROM tone_profiles` |
| 201–208 | 8 | `clear_cache` | sync fn | A | Uses `.pop()` / `.clear()` — OK |
| 210 | 1 | blank | — | shared | separator |
| 211–213 | 3 | `# === CONTENT CHUNKS ===` | banner | **B** | |
| 215–277 | 63 | `save_content_chunks_db` | async fn | B | Upsert by `(creator_id, chunk_id)`; bulk insert |
| 280–320 | 41 | `get_content_chunks_db` | async fn | B | Load all chunks for creator |
| 323–360 | 38 | `delete_content_chunks_db` | async fn | B | Optional `source_type` filter |
| 361–362 | 2 | blank | — | shared | separator |
| 363–365 | 3 | `# === INSTAGRAM POSTS ===` | banner | **C** | |
| 367–449 | 83 | `save_instagram_posts_db` | async fn | C | Parses hashtags/mentions; has extra `traceback.print_exc()` in except (diverges from B) |
| 452–492 | 41 | `get_instagram_posts_db` | async fn | C | `ORDER BY post_timestamp DESC` |
| 495–520 | 26 | `delete_instagram_posts_db` | async fn | C | Nuke all posts for creator |
| 523–540 | 18 | `get_instagram_posts_count_db` | sync fn | C | Cheap count (for admin/debug) |

**Sum check:** 4+3+1+3+8+52+34+28+32+18+8+1+3+63+41+38+2+3+83+41+26+18 + assorted blanks ≈ 540 ✓.

### Cross-domain dependencies INSIDE the file

```
                ┌──────────────────────────────┐
                │  Shared prologue (11 LOC)    │
                │  docstring / imports / logger│
                └──────────────┬───────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
   │  DOMAIN A   │      │  DOMAIN B   │      │  DOMAIN C   │
   │ tone        │      │ chunks      │      │ posts       │
   │  _tone_cache│      │             │      │             │
   │  save/get/  │      │ save/get/   │      │ save/get/   │
   │  del/list/  │      │ delete      │      │ del/count   │
   │  clear_cache│      │             │      │             │
   └──────┬──────┘      └──────┬──────┘      └──────┬──────┘
          │                    │                    │
          ▼                    ▼                    ▼
      ToneProfile         ContentChunk         InstagramPost
      (api.models)        (api.models)         (api.models)
```

**No function in one domain calls any function in another domain.** The three domains are **completely decoupled** at the call-graph level — their only connection is physical co-location in this file. The `_tone_cache` module attribute is only read/written by Domain A functions (confirmed by grep below).

Dead code: `_get_db_session` (lines 17–24) is defined and orphaned. Zero callers inside the file, zero callers outside. Was presumably intended as a shared helper for all three domains, but every function chose to inline its own `from api.database import get_db_session` instead.

---

## 2. The 9 productive callsites

| # | Importer file | Domain(s) | Imports | Notes |
|---|---|---|---|---|
| 1 | `backend/core/tone_service.py` | **A** only | `get_tone_profile_db_sync`, `save_tone_profile_db`, `clear_cache`, `list_profiles_db`, `delete_tone_profile_db` | Clean single-domain consumer; drives tone bootstrap |
| 2 | `backend/core/auto_configurator.py` | **C** only | `get_instagram_posts_db` (×2) | Clean single-domain; uses posts to refine tone |
| 3 | `backend/ingestion/v2/instagram_ingestion.py` | **B + C** (mixed) | `delete_instagram_posts_db`, `delete_content_chunks_db`, `save_instagram_posts_db`, `save_content_chunks_db` | Multi-domain import — the mixing in the file matches the mixing at the call site |
| 4 | `backend/ingestion/v2/youtube_ingestion.py` | **B** only | `delete_content_chunks_db`, `save_content_chunks_db` | YouTube only writes chunks, no posts |
| 5 | `backend/services/feed_webhook_handler.py` | **B + C** | `save_instagram_posts_db`, `save_content_chunks_db` | On IG feed webhook: persist post + re-chunk |
| 6 | `backend/api/routers/ingestion_v2/instagram_ingest.py` | **B + C** | `get_content_chunks_db`, `get_instagram_posts_count_db` | Read-only router (status/debug endpoint) |
| 7 | `backend/api/routers/ingestion_v2/youtube.py` | **B** only | `get_content_chunks_db` | Read-only router |
| 8 | `backend/api/routers/onboarding/setup.py` | **B + C** | `delete_content_chunks_db`, `delete_instagram_posts_db` | Onboarding wipe |
| 9 | `backend/api/routers/admin/debug.py` | **A** only (PRIVATE) | `_tone_cache` (underscore-prefixed module attribute) → calls `.stats()` | **Privacy leak** — reaches into a private name to expose cache stats in `/admin/debug/memory` |

### Per-domain consumer count

| Domain | Distinct consumers | Details |
|---|---|---|
| A (tone_profiles) | **2** | `tone_service.py` (public API), `admin/debug.py` (`_tone_cache` private) |
| B (content_chunks) | **6** | `instagram_ingestion`, `youtube_ingestion`, `feed_webhook_handler`, `routers/ingestion_v2/instagram_ingest`, `routers/ingestion_v2/youtube`, `routers/onboarding/setup` |
| C (instagram_posts) | **5** | `auto_configurator`, `instagram_ingestion`, `feed_webhook_handler`, `routers/ingestion_v2/instagram_ingest`, `routers/onboarding/setup` |

### Callsites by domain-coupling shape

| Shape | Count | Callers |
|---|---|---|
| Single-domain (A) | 2 | `tone_service`, `admin/debug` |
| Single-domain (B) | 2 | `youtube_ingestion`, `routers/ingestion_v2/youtube` |
| Single-domain (C) | 1 | `auto_configurator` |
| Multi-domain (B + C) | 4 | `instagram_ingestion`, `feed_webhook_handler`, `routers/ingestion_v2/instagram_ingest`, `routers/onboarding/setup` |
| Multi-domain (A + B + C) | 0 | — (no consumer ever needs all three) |

**Key insight for Phase 5 shim:** no consumer needs A + B + C together, but **four consumers do need B + C in one import line**. The shim must re-export both domains' symbols through `core.tone_profile_db` so those 4 callers keep compiling unchanged. Alternatively they can migrate to two import lines from the new repos — but per the constraint "9 importers no cambian", the shim keeps them untouched.

### Correction to the task statement

The task brief listed `creator_data_loader` as a callsite. **Verified false**: `grep "tone_profile_db" backend/core/creator_data_loader.py` returns zero matches. The real 9th callsite is that the `ingestion_v2` router directory contains **two** distinct files (`instagram_ingest.py` + `youtube.py`), each importing separately. Net count still 9.

---

## 3. BoundedTTLCache scope — is there cross-domain creep?

**No cross-domain reads or writes today.**

- `_tone_cache` is referenced **only** by Domain A functions inside the file (`save_tone_profile_db`, `get_tone_profile_db`, `get_tone_profile_db_sync`, `delete_tone_profile_db`, `clear_cache`).
- Outside the file, `_tone_cache` is imported **once** (by `api/routers/admin/debug.py`) — it calls `.stats()` for the admin memory endpoint. Domain A still.
- Zero Domain B or Domain C code touches the cache.

**Verdict:** The cache is already Domain A-scoped. The "creep" today is visual/structural (the cache lives at module scope in a file that also hosts B and C), not behavioural. Post-split the cache moves inside `tone_profile_repo.py`; `admin/debug.py` updates its import to `from core.data.tone_profile_repo import _tone_cache` (or a public accessor). No other callers change.

The shim at `core/tone_profile_db.py` must therefore also re-export `_tone_cache` for backward compat — **and** we should introduce a public `get_tone_cache_stats()` accessor to fix the private-name leak from `admin/debug.py` as an opportunistic cleanup in Phase 5.

---

## 4. Tests — 18 total, 7 stale (confirmed)

Test file: `backend/tests/test_tone_profile_db_audit.py`.
Result of `pytest` in this worktree: **11 passed, 7 failed** (exactly matches the scout claim).

| # | Test | Domain | Status | Why |
|---|---|---|---|---|
| 1 | `TestToneProfileDbImports::test_imports_and_cache_exists` | A | **STALE** | `assert isinstance(_tone_cache, dict)` — false since `_tone_cache` is `BoundedTTLCache` |
| 2 | `TestToneProfileDbImports::test_clear_cache_specific_key` | A | **STALE** | `_tone_cache["x"] = y` → `AttributeError: __setitem__` |
| 3 | `TestToneProfileDbImports::test_clear_cache_all` | A | **STALE** | same |
| 4 | `TestToneProfileDbSave::test_save_new_profile` | A | pass | Uses `.pop()` / `.get()` — compatible with BoundedTTLCache |
| 5 | `TestToneProfileDbSave::test_save_returns_false_on_exception` | A | pass | No cache access |
| 6 | `TestToneProfileDbLoad::test_get_from_cache` | A | **STALE** | `_tone_cache["cached_creator"] = cached_data` → AttributeError |
| 7 | `TestToneProfileDbLoad::test_get_returns_none_when_not_cached_and_no_db` | A | pass | `.pop()` only |
| 8 | `TestToneProfileDbLoad::test_sync_get_from_cache` | A | **STALE** | subscript assign |
| 9 | `TestToneProfileDbErrorHandling::test_get_returns_none_on_import_error` | A | pass | `.pop()` only |
| 10 | `TestToneProfileDbErrorHandling::test_delete_returns_false_on_error` | A | pass | no cache |
| 11 | `TestToneProfileDbErrorHandling::test_list_profiles_returns_empty_on_error` | A | pass | no cache |
| 12 | `TestToneProfileDbErrorHandling::test_sync_get_returns_none_on_error` | A | pass | `.pop()` |
| 13 | `TestToneProfileDbErrorHandling::test_get_instagram_posts_count_returns_zero_on_error` | **C** | pass | no cache |
| 14 | `TestToneProfileDbIntegration::test_clear_cache_then_get_returns_none` | A | **STALE** | subscript assign |
| 15 | `TestToneProfileDbIntegration::test_delete_clears_cache` | A | **STALE** | subscript assign |
| 16 | `TestToneProfileDbIntegration::test_content_chunks_returns_empty_on_error` | **B** | pass | no cache |
| 17 | `TestToneProfileDbIntegration::test_delete_content_chunks_returns_zero_on_error` | **B** | pass | no cache |
| 18 | `TestToneProfileDbIntegration::test_get_instagram_posts_returns_empty_on_error` | **C** | pass | no cache |

### Per-domain test coverage

| Domain | Tests | Passing | Stale |
|---|---|---|---|
| A (tone_profiles) | 15 | 8 | **7** |
| B (content_chunks) | 2 | 2 | 0 |
| C (instagram_posts) | 3 | 3 | 0 |

**Observations for Phase 5:**
- **All 7 stale tests are Domain A.** B and C are healthy but thin (only 2 and 3 tests respectively).
- Domain B and C each need more coverage (target 9/10 per constraint). Currently 2 and 3.
- The 7 stale tests can be fixed by replacing dict-subscript with `.set()` / `.pop()`; the `isinstance(dict)` assertion becomes `isinstance(BoundedTTLCache)`.
- There is a **latent production bug** at `tone_profile_db.py:94` and `:124` — the cache-hit read path uses subscript `_tone_cache[creator_id]`, which raises `TypeError: 'BoundedTTLCache' object is not subscriptable`. Reproduced locally; it triggers whenever a cache hit occurs (within the 10-min TTL after any `.set()`). This bug is **not caught by any existing test** because the stale tests crash earlier on the subscript-write side. This is flagged for Phase 3 and will be fixed in Phase 5.

---

## 5. Git blame — when and why the domains got mixed

| Date | Commit | Message | Impact |
|---|---|---|---|
| 2026-01-10 | `c1bf3e97` | **Add PostgreSQL persistence for ToneProfile, ContentChunk, InstagramPost** | **Root cause.** Three SQLAlchemy models + one service file (528 LOC) created in a single commit by Claude. Commit body: "Created tone_profile_db.py service with CRUD operations for **all 3 tables**." The mixing was intentional at birth — one service file was chosen over three for speed of delivery, and the name only reflected the first model. |
| 2026-01-10 | `6c2569f8` | Fix: use `Any` instead of `any` in type hint | cosmetic |
| 2026-01-10 | `0264a352` | Rename `ContentChunk.metadata` → `extra_data` | Touched Domain B only but edit went through the shared file |
| 2026-01-26 | `f75cbdd9` | Add full Instagram comments data | Domain C expansion |
| 2026-01-28 | `edc365de` | Refactor bare `except` in 8 core files | **Blanket** error-handling pass; applied uniform `except Exception` to all 3 domains simultaneously — cemented the inconsistency instead of differentiating it |
| 2026-01-31 | `d7328f9f` | Add YouTube ingestion endpoint | Domain B expansion (YouTube → chunks) |
| 2026-02-15 | `b8cf8ce0` | Phase 2 massive debug — 700+ issues across 330 files | Blanket fix pass; no separation |
| 2026-03-17 | `9a553a74` | **bounded caches + memory leak fix** | Replaced `_tone_cache: dict = {}` with `BoundedTTLCache`. **Did not update tests** (7 went stale) and **did not update production subscript reads** at lines 94 & 124 (latent TypeError). Domain A only but edit happened in the shared file, increasing its LOC footprint. |

### Why mixed (root cause synthesis)

1. **Single-shot authorship.** The initial commit created three models, three tables, and three DAO surfaces in one file as an expedient shortcut. The file name was aliased to the first model, not to the aggregate.
2. **Never revisited separately.** All subsequent touches were either blanket fixes (bare except, massive debug) or single-model tweaks that slipped through the co-located code instead of prompting a split.
3. **No ownership boundary.** With three domains in one file, there is no natural owner for refactors. The cache bounding (Mar 17) changed Domain A's contract but left A's own tests and half of A's own production code behind — because nobody was just "the tone DAO owner".

The CEO decision in Q2 planning to split now aligns with all three root causes.

---

## 6. Phase 5 shim export requirements (derived here, built in Phase 5)

For the 9 importers to keep working unchanged, `backend/core/tone_profile_db.py` must re-export, at minimum:

**Domain A (7 names):**
`save_tone_profile_db`, `get_tone_profile_db`, `get_tone_profile_db_sync`, `delete_tone_profile_db`, `list_profiles_db`, `clear_cache`, `_tone_cache`

**Domain B (3 names):**
`save_content_chunks_db`, `get_content_chunks_db`, `delete_content_chunks_db`

**Domain C (4 names):**
`save_instagram_posts_db`, `get_instagram_posts_db`, `delete_instagram_posts_db`, `get_instagram_posts_count_db`

**Total: 14 re-exports** from the 3 new repos.

---

## STOP — End of Phase 2.
