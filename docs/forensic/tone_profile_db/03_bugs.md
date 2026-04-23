# Phase 3 — Bug catalog

> Target: `backend/core/tone_profile_db.py` (540 LOC) + blast radius
> Branch: `forensic/tone-profile-db-20260423`
> Severities assigned by CEO.

---

## Bug index

| ID | Severity | Title | File:line(s) | Origin |
|---|---|---|---|---|
| **B-01** | 🔴 **CRÍTICA** | `TypeError` on every cache-hit read (BoundedTTLCache subscript) | `tone_profile_db.py:94, 124` | `9a553a74` (swap) on top of `c1bf3e97` (original subscript) |
| **B-02** | 🟠 **ALTA** | 7 Domain-A tests stale since BoundedTTLCache swap | `tests/test_tone_profile_db_audit.py` (7 cases) | `9a553a74` (2026-03-17) |
| **B-03** | 🟠 **ALTA** | File bundling: 3 domains + 1 DAO in one service | `tone_profile_db.py` (full file, 540 LOC) | `c1bf3e97` (2026-01-10) |
| **B-04** | 🟡 **MEDIA** | Domain B coverage: 2 tests (<9 target) | `tests/test_tone_profile_db_audit.py` (class `TestToneProfileDbIntegration`) | `bc7ac641c` (2026-02-07) |
| **B-05** | 🟡 **MEDIA** | Domain C coverage: 3 tests (<9 target) | `tests/test_tone_profile_db_audit.py` | `bc7ac641c` (2026-02-07) |
| **B-06** | 🟡 **MEDIA** | Private-name leak `_tone_cache` from admin endpoint | `api/routers/admin/debug.py:84` | `9a553a74` (2026-03-17) |
| **B-07** | 🟡 **MEDIA** | Hardcoded cache sizing `max_size=50, ttl_seconds=600` — no env vars | `tone_profile_db.py:14` | `9a553a74` (2026-03-17) |
| **B-08** | 🟢 **BAJA** | Dead code: `_get_db_session` (8 LOC, zero callers) | `tone_profile_db.py:17–24` | `c1bf3e97` (2026-01-10) |
| **B-09** | 🟢 **BAJA** | Module docstring mis-describes content (540 LOC, "ToneProfiles" only) | `tone_profile_db.py:1–4` | `c1bf3e97` (2026-01-10) |

Bonus side-effect of B-02: the 7 stale tests **mask** B-01 — they crash on subscript-write before they can ever exercise the subscript-read path. Fixing tests without fixing B-01 would finally expose B-01 as a red test.

---

## B-01 🔴 CRÍTICA — `TypeError` on cache-hit read

**Location:** `backend/core/tone_profile_db.py:94` (async) and `:124` (sync).

```python
# line 92-94 (async)
if creator_id in _tone_cache:
    logger.debug(f"ToneProfile for {creator_id} found in cache")
    return _tone_cache[creator_id]          # ← raises TypeError

# line 123-124 (sync)
if creator_id in _tone_cache:
    return _tone_cache[creator_id]          # ← raises TypeError
```

**Origin:**
- Subscript read was written on 2026-01-10 in `c1bf3e97` against a plain `dict` — benign at the time.
- On 2026-03-17, `9a553a74` replaced `_tone_cache: dict = {}` with `BoundedTTLCache(max_size=50, ttl_seconds=600)`. `BoundedTTLCache` implements `__contains__`, `__delitem__`, `__len__`, `.get()`, `.set()`, `.pop()`, `.clear()`, `.stats()` — but **not** `__getitem__`. Subscript reads silently became latent `TypeError`s.
- Neither the Mar-17 commit nor anything since updated these two reader sites.

**Severity rationale:**
- Triggers on **every cache hit inside the 10-min TTL** after any `save_tone_profile_db` or successful DB miss (which also `.set()`s the cache).
- Not inside a `try/except` — the error propagates to the caller (`DMResponderAgentV2.__init__`, `auto_configurator`, etc.).
- Masked in production because (a) callers of `get_tone_profile_db_sync` from `tone_service.py:32` happen during bootstrap, often after a cold cache where `in` returns False; (b) the 10-min TTL expires before repeated hits in quiet periods; (c) when it does fire, it may surface as a generic 500 during agent init that looks like a DB hiccup.
- Masked in tests because the 7 stale cache-write tests crash earlier on `AttributeError: __setitem__`.

**Reproducción (verificada en este worktree):**

```bash
$ cd backend && python3 -c "
from core import tone_profile_db as tpdb
tpdb._tone_cache.set('probe', {'data': 'x'})
r = tpdb.get_tone_profile_db_sync('probe')
print(repr(r))
"
# → TypeError: 'BoundedTTLCache' object is not subscriptable
```

**Fix propuesto (Phase 5, en el NUEVO `tone_profile_repo.py` tras split — no tocar archivo legacy):**

```python
# NEW: tone_profile_repo.py (reemplaza lines 91-94 y 122-124)
cached = _tone_cache.get(creator_id)
if cached is not None:
    logger.debug(f"ToneProfile for {creator_id} found in cache")
    return cached
```

`.get()` already encapsulates the "in cache and not expired" check (returns `None` on miss or TTL expiry) — eliminates the race between `__contains__` and subscript.

**Regression test (NEW, added in Phase 5 to `test_tone_profile_repo.py`):**

```python
def test_cache_hit_read_path_does_not_raise():
    """
    Regression test for the 2026-03-17 BoundedTTLCache swap bug.
    Before fix: .set() followed by a get within TTL raised TypeError.
    After fix: .set() followed by a get returns the cached value.
    """
    from core.data.tone_profile_repo import _tone_cache, get_tone_profile_sync
    _tone_cache.set("probe", {"data": "x"})
    result = get_tone_profile_sync("probe")
    assert result == {"data": "x"}
```

(Plus an async variant for `get_tone_profile_async`.)

---

## B-02 🟠 ALTA — 7 tests stale since 2026-03-17

**Location:** `backend/tests/test_tone_profile_db_audit.py` — 7 test methods (IDs in Phase-2 doc: tests #1, #2, #3, #6, #8, #14, #15). All Domain A.

**Origin:** `bc7ac641c` (2026-02-07 — tests written against `dict` contract) remained correct until `9a553a74` (2026-03-17 — cache swapped to `BoundedTTLCache` with no `__setitem__`) silently invalidated them.

**Observed failure (reproducido):**

```
$ python3 -m pytest tests/test_tone_profile_db_audit.py -q
...
FAILED test_imports_and_cache_exists  # isinstance(_tone_cache, dict) False
FAILED test_clear_cache_specific_key  # _tone_cache["x"] = y → AttributeError: __setitem__
FAILED test_clear_cache_all           # same
FAILED test_get_from_cache            # same
FAILED test_sync_get_from_cache       # same
FAILED test_clear_cache_then_get_returns_none  # same
FAILED test_delete_clears_cache       # same
11 passed, 7 failed
```

**Fix propuesto (Phase 5):**
Move these 7 tests into the new `backend/tests/test_tone_profile_repo.py` and rewrite with `.set()` / `.pop()` / `BoundedTTLCache` semantics. The 3 assertions that check cache-dict behaviour become `BoundedTTLCache` contract assertions. Delete `test_tone_profile_db_audit.py` in the same commit.

Example rewrite of test #1:

```python
# OLD (stale)
from core.tone_profile_db import _tone_cache
assert isinstance(_tone_cache, dict)

# NEW
from core.cache import BoundedTTLCache
from core.data.tone_profile_repo import _tone_cache
assert isinstance(_tone_cache, BoundedTTLCache)
assert _tone_cache.max_size >= 1
assert _tone_cache.ttl_seconds > 0
```

---

## B-03 🟠 ALTA — File bundling (3 domains + 1 DAO) — root structural bug

**Location:** `backend/core/tone_profile_db.py` (full file, 540 LOC — violates the 500-LOC ceiling).

**Origin:** `c1bf3e97` (2026-01-10) — commit body: *"Created tone_profile_db.py service with CRUD operations for **all 3 tables**"*. Three models, one service, one mis-leading name. Never revisited for separation; subsequent touches were blanket passes (bare-except cleanup, massive debug, bounded caches).

**Severity rationale:**
- Blocks discoverability (`grep InstagramPost` lands in a file named after a different domain).
- Blocks correct inventory classification (Phase 1: pipeline DM bucket forced to carry two batch/ingestion concerns).
- Amplifies every other bug on this list: because the file is one unit, fixes that should be scoped to Domain A (cache swap) leak commit history and CI churn across Domains B and C.

**Fix propuesto (Phase 5 — the whole point of this branch):**
Split into `backend/core/data/tone_profile_repo.py` (≤200 LOC), `instagram_posts_repo.py` (≤200 LOC), `content_chunks_repo.py` (≤200 LOC); keep `backend/core/tone_profile_db.py` as a ≤40-LOC shim that re-exports the 14 names. See **Annex A**.

---

## B-04 🟡 MEDIA — Domain B (content_chunks) under-tested

**Location:** Only 2 tests exercise Domain B:
- `TestToneProfileDbIntegration::test_content_chunks_returns_empty_on_error`
- `TestToneProfileDbIntegration::test_delete_content_chunks_returns_zero_on_error`

Both tests only cover the **error-path** (DB unavailable → safe default). Zero tests cover happy path (`save` upserts, `get` returns rows, `delete_content_chunks_db` with `source_type` filter, etc.).

**Origin:** `bc7ac641c` (2026-02-07) — test file was written biased to Domain A.

**Fix propuesto (Phase 5):** Add 7+ tests in `backend/tests/test_content_chunks_repo.py`. See **Annex B**.

---

## B-05 🟡 MEDIA — Domain C (instagram_posts) under-tested

**Location:** Only 3 tests exercise Domain C (2 error-path, 1 count):
- `test_get_instagram_posts_count_returns_zero_on_error`
- `test_get_instagram_posts_returns_empty_on_error`
- (implicit count-path in the count test)

Zero tests cover hashtag/mention parsing, upsert logic, `ORDER BY post_timestamp DESC`, `delete` returning row count, or the `traceback.print_exc()` divergent error handler.

**Origin:** `bc7ac641c` (2026-02-07).

**Fix propuesto (Phase 5):** Add 6+ tests in `backend/tests/test_instagram_posts_repo.py`. See **Annex B**.

---

## B-06 🟡 MEDIA — Private-name leak `_tone_cache`

**Location:** `backend/api/routers/admin/debug.py:84`.

```python
try:
    from core.tone_profile_db import _tone_cache
    caches["tone_cache"] = _tone_cache.stats()
except Exception as e:
    caches["tone_cache"] = str(e)
```

**Origin:** `9a553a74` (2026-03-17) — the same commit that introduced `BoundedTTLCache` added this admin dashboard hook reaching into a private (underscore-prefixed) module attribute. Encapsulation broken at inception of the cache.

**Severity rationale:**
- Breaks the "leading underscore = private" convention.
- Couples admin telemetry to the module's internal storage shape — any Phase 5 rename (e.g. moving `_tone_cache` from module scope to a class attribute) would silently break admin debug.
- Not directly user-visible but the admin endpoint is read by ops during incidents — an uncaught change could blank a critical panel.

**Fix propuesto (Phase 5):**
1. Add a **public** accessor to `tone_profile_repo.py`:
   ```python
   def get_tone_cache_stats() -> dict:
       """Public accessor for admin/debug telemetry. Exposes cache stats without leaking the private instance."""
       return _tone_cache.stats()
   ```
2. Re-export from the shim for backward compat.
3. Update `api/routers/admin/debug.py:84` to `from core.data.tone_profile_repo import get_tone_cache_stats` and call it.
4. The shim still re-exports `_tone_cache` itself (in case any future caller imports it), but the admin endpoint goes through the public name.

---

## B-07 🟡 MEDIA — Hardcoded cache sizing

**Location:** `backend/core/tone_profile_db.py:14`.

```python
_tone_cache = BoundedTTLCache(max_size=50, ttl_seconds=600)
```

**Origin:** `9a553a74` (2026-03-17). Values chosen at swap time with no operational knob.

**Severity rationale:**
- Tuning requires code edit + deploy. During an incident you cannot bump cache size from Railway dashboard.
- 50 creators × 10 min is suitable for today's tenancy but at creator count > 50 (Q2 pipeline adds Stefano, others) cache thrashes.
- Violates the project constraint "Cero hardcoding".

**Fix propuesto (Phase 5), en `tone_profile_repo.py`:**

```python
import os
TONE_CACHE_MAX_SIZE = int(os.getenv("TONE_CACHE_MAX_SIZE", "50"))
TONE_CACHE_TTL_SECONDS = int(os.getenv("TONE_CACHE_TTL_SECONDS", "600"))
_tone_cache = BoundedTTLCache(
    max_size=TONE_CACHE_MAX_SIZE,
    ttl_seconds=TONE_CACHE_TTL_SECONDS,
)
```

Defaults match today's behaviour (no Railway change needed). Knobs available if needed.

**Not to be changed on Railway in this branch** per constraint; just expose the env vars.

---

## B-08 🟢 BAJA — Dead code `_get_db_session`

**Location:** `backend/core/tone_profile_db.py:17–24` (8 LOC).

```python
def _get_db_session():
    """Get database session using context manager."""
    try:
        from api.database import get_db_session
        return get_db_session()
    except Exception as e:
        logger.error(f"Failed to get DB session: {e}")
        return None
```

**Origin:** `c1bf3e97` (2026-01-10). Intended as a shared helper for all 3 domains; every downstream function instead chose `from api.database import get_db_session` inline. Zero internal and zero external callers (grep-verified).

**Severity rationale:** Noise, not harm. But the helper returns a context manager from a try/except that swallows to `None`, which would be a latent bug if anyone ever started calling it (they'd get `None` and `.query()` on NoneType). Removing it now prevents a future footgun.

**Fix propuesto (Phase 5):** Delete the function; no new file carries it over.

---

## B-09 🟢 BAJA — Module docstring mis-describes content

**Location:** `backend/core/tone_profile_db.py:1–4`.

```python
"""
Tone Profile Database Service - PostgreSQL persistence for ToneProfiles.
Replaces JSON file-based storage with proper database persistence.
"""
```

540 LOC and 3 domains: docstring only mentions one. Contributes to the "developers don't realise this file also owns posts and chunks" failure mode.

**Origin:** `c1bf3e97` (2026-01-10).

**Fix propuesto (Phase 5):**
- New files each get an accurate domain-scoped docstring (≥6 lines covering: purpose, DB model, tests, env vars).
- Legacy shim docstring declares itself as deprecated back-compat surface, lists the 3 new repos, and flags that callers should migrate.

---

## Annex A — Shim export table (14 names for Phase 5)

The legacy `backend/core/tone_profile_db.py` (≤40 LOC shim after split) MUST re-export the following so the 9 importers keep working unchanged:

| # | Name | Source repo (new) | Consumers that import this name |
|---|---|---|---|
| 1 | `save_tone_profile_db` | `core/data/tone_profile_repo.py` | `tone_service.py` |
| 2 | `get_tone_profile_db` | `core/data/tone_profile_repo.py` | _(indirect via sync variant)_ |
| 3 | `get_tone_profile_db_sync` | `core/data/tone_profile_repo.py` | `tone_service.py` |
| 4 | `delete_tone_profile_db` | `core/data/tone_profile_repo.py` | `tone_service.py` |
| 5 | `list_profiles_db` | `core/data/tone_profile_repo.py` | `tone_service.py`, `mega_test_w2.py` |
| 6 | `clear_cache` | `core/data/tone_profile_repo.py` | `tone_service.py`, `mega_test_w2.py` |
| 7 | `_tone_cache` | `core/data/tone_profile_repo.py` | `api/routers/admin/debug.py` (legacy — Phase 5 migrates it to `get_tone_cache_stats()`) |
| 8 | `save_content_chunks_db` | `core/data/content_chunks_repo.py` | `instagram_ingestion.py`, `youtube_ingestion.py`, `feed_webhook_handler.py` |
| 9 | `get_content_chunks_db` | `core/data/content_chunks_repo.py` | `routers/ingestion_v2/instagram_ingest.py`, `routers/ingestion_v2/youtube.py` |
| 10 | `delete_content_chunks_db` | `core/data/content_chunks_repo.py` | `instagram_ingestion.py`, `youtube_ingestion.py`, `routers/onboarding/setup.py` |
| 11 | `save_instagram_posts_db` | `core/data/instagram_posts_repo.py` | `instagram_ingestion.py`, `feed_webhook_handler.py` |
| 12 | `get_instagram_posts_db` | `core/data/instagram_posts_repo.py` | `auto_configurator.py` |
| 13 | `delete_instagram_posts_db` | `core/data/instagram_posts_repo.py` | `instagram_ingestion.py`, `routers/onboarding/setup.py` |
| 14 | `get_instagram_posts_count_db` | `core/data/instagram_posts_repo.py` | `routers/ingestion_v2/instagram_ingest.py`, `mega_test_w2.py` |

**Plus 1 new public accessor introduced in Phase 5:**
- `get_tone_cache_stats()` (new, for admin/debug — fixes B-06 without forcing the 9 legacy importers to change).

**Shim shape (preview for Phase 5):**

```python
"""
DEPRECATED — backward-compat shim.

This module has been split into three domain-scoped repositories:
  - core.data.tone_profile_repo      (tone profiles, BOOTSTRAP / Doc D)
  - core.data.content_chunks_repo    (RAG chunks, INGESTIÓN batch)
  - core.data.instagram_posts_repo   (IG post content lake, INGESTIÓN batch)

Existing imports through `core.tone_profile_db` continue to work via the
re-exports below. New code MUST import from the domain-specific repo.
"""
from core.data.tone_profile_repo import (  # noqa: F401
    save_tone_profile_db,
    get_tone_profile_db,
    get_tone_profile_db_sync,
    delete_tone_profile_db,
    list_profiles_db,
    clear_cache,
    _tone_cache,
    get_tone_cache_stats,
)
from core.data.content_chunks_repo import (  # noqa: F401
    save_content_chunks_db,
    get_content_chunks_db,
    delete_content_chunks_db,
)
from core.data.instagram_posts_repo import (  # noqa: F401
    save_instagram_posts_db,
    get_instagram_posts_db,
    delete_instagram_posts_db,
    get_instagram_posts_count_db,
)
```

---

## Annex B — Test coverage plan post-split (target: 27+ tests vs 18 today)

### `backend/tests/test_tone_profile_repo.py` (Domain A) — target **9+ tests**

Reuse (rewritten against BoundedTTLCache contract): **15 existing Domain A cases** (11 pass as-is + 7 stale rewritten — but we will consolidate duplicates).

Final set (9):

1. `test_cache_is_bounded_ttl_cache` (was #1 — rewritten for new contract)
2. `test_clear_cache_specific_key` (was #2 — rewritten)
3. `test_clear_cache_all` (was #3 — rewritten)
4. `test_save_new_profile` (was #4)
5. `test_save_returns_false_on_exception` (was #5)
6. `test_get_from_cache` (was #6 — rewritten)
7. `test_sync_get_from_cache` (was #8 — rewritten)
8. **NEW — `test_cache_hit_read_path_does_not_raise`** (regression test for B-01)
9. **NEW — `test_cache_env_vars_respected`** (regression for B-07 — monkey-patch `TONE_CACHE_MAX_SIZE` and re-import)

Error-path tests #7, #9, #10, #11, #12, #14, #15 kept but consolidated by using `pytest.mark.parametrize` to avoid duplication.

### `backend/tests/test_content_chunks_repo.py` (Domain B) — target **9+ tests**

1. `test_save_new_chunks_inserts_rows` (happy path upsert insert)
2. `test_save_existing_chunks_updates_rows` (happy path upsert update — verifies `(creator_id, chunk_id)` key)
3. `test_save_preserves_metadata_jsonb` (covers the `extra_data` rename history — regression for `0264a352`)
4. `test_get_returns_all_chunks_for_creator` (happy path read)
5. `test_get_returns_empty_on_error` (existing)
6. `test_delete_all_chunks_for_creator` (happy path delete all)
7. `test_delete_only_source_type_filter` (verifies the `source_type=` argument; regression for YouTube vs IG separation)
8. `test_delete_returns_zero_on_error` (existing)
9. `test_save_returns_zero_on_error` (NEW — error path for save)

### `backend/tests/test_instagram_posts_repo.py` (Domain C) — target **9+ tests**

1. `test_save_new_posts_inserts_rows`
2. `test_save_existing_posts_updates_rows` (upsert on `(creator_id, post_id)`)
3. `test_save_parses_hashtags_from_caption` (covers the `caption.split()` parser; regression trap for unicode/emoji edge cases)
4. `test_save_parses_mentions_from_caption`
5. `test_save_handles_malformed_timestamp_gracefully` (verifies `dateutil.parser` exception path — does not raise)
6. `test_get_returns_posts_ordered_by_timestamp_desc`
7. `test_get_returns_empty_on_error` (existing)
8. `test_delete_all_posts_for_creator`
9. `test_get_count_returns_zero_on_error` (existing, count-only)

### Total test delta

| File | Before | After | Delta |
|---|---|---|---|
| `test_tone_profile_db_audit.py` (deleted) | 18 | 0 | −18 |
| `test_tone_profile_repo.py` (new) | 0 | 9+ | +9 |
| `test_content_chunks_repo.py` (new) | 0 | 9+ | +9 |
| `test_instagram_posts_repo.py` (new) | 0 | 9+ | +9 |
| **Total** | **18** | **27+** | **+9** |

All 27 green in CI = Phase 5 acceptance gate.

---

## STOP — End of Phase 3.
