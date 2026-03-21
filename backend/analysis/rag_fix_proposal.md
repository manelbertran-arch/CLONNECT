# RAG Embeddings Bug — Fix Proposal

**Date**: 2026-03-21
**Status**: PROPOSAL — not yet executed

---

## Bug Trace

### The Problem

`content_chunks` table stores chunks with `creator_id = 'iris_bertran'` (slug).
But `_embed_new_chunks()` receives a UUID from `refresh_all_active_creators()`.
The SQL `WHERE cc.creator_id = :creator_id` with UUID finds 0 rows.
Result: **0 embeddings generated for 93 existing chunks.**

### Root Cause Chain

```
refresh_all_active_creators()                     [content_refresh.py:242]
  creator_ids = [(str(c.id), c.name) for c in creators]
                   ^^^^^^^^ UUID

  for creator_uuid, creator_name in creator_ids:  [content_refresh.py:251]
      refresh_creator_content(creator_uuid)        [content_refresh.py:253]
                              ^^^^^^^^^^^^ UUID passed

refresh_creator_content(creator_id)                [content_refresh.py:30]
  # creator_id is UUID here
  ingest_instagram_v2(creator_id=creator_id, ...)  [content_refresh.py:108-109]
                      ^^^^^^^^^^^^^^^^^^^ UUID → ingestion creates chunks with UUID

  _embed_new_chunks(creator_id)                    [content_refresh.py:131]
                    ^^^^^^^^^^ UUID → queries WHERE cc.creator_id = UUID
```

**BUT**: The 93 existing chunks were created earlier via a different path (onboarding, manual ingestion) that used `creator.name` (slug). So:

- **93 existing chunks**: `creator_id = 'iris_bertran'` (slug)
- **_embed_new_chunks query**: `WHERE cc.creator_id = '{uuid}'` (UUID)
- **Result**: 0 matches, 0 embeddings

### Double Mismatch

The search side also has a mismatch:

```
agent.semantic_rag.search(..., creator_id=agent.creator_id)  [context.py:199]
                                          ^^^^^^^^^^^^^^^^ slug ('iris_bertran')
  -> search_similar(creator_id=creator_id)                   [semantic.py:200-202]
      -> WHERE e.creator_id = :creator_id                    [embeddings.py:276]
                               ^^^^^^^^^ slug
```

So even if embeddings were generated with UUID, the search uses slug.
The system is inconsistent: **chunks stored with slug, embeddings stored with UUID, search queries by slug.**

### Affected Files

| File | Line | What it does | creator_id format |
|------|------|-------------|-------------------|
| `content_refresh.py:242` | `str(c.id)` | Entry point for scheduled refresh | UUID |
| `content_refresh.py:108` | `ingest_instagram_v2(creator_id=creator_id)` | Passes to ingestion | UUID (from caller) |
| `content_refresh.py:131` | `_embed_new_chunks(creator_id)` | Queries chunks for embedding | UUID (from caller) |
| `content_refresh.py:140` | `_hydrate_rag_for_creator(creator_id)` | Loads RAG docs | UUID (from caller) |
| `ingestion/v2/instagram_ingestion.py:424` | `'creator_id': creator_id` | Chunk creation | Whatever caller passes |
| `core/tone_profile_db.py:238` | `ContentChunk.creator_id == creator_id` | DB save/lookup | Whatever caller passes |
| `core/embeddings.py:214` | `"creator_id": creator_id` | Store embedding | Whatever caller passes |
| `core/embeddings.py:276` | `WHERE e.creator_id = :creator_id` | Search embeddings | Whatever caller passes |
| `core/dm/phases/context.py:199` | `creator_id=agent.creator_id` | RAG search at runtime | Slug |

---

## Proposed Fix

### Strategy: Use slug (creator name) consistently

The slug is used by:
- The DM agent at search time (`agent.creator_id` = slug)
- The 93 existing chunks in the DB
- All manual/onboarding ingestion paths

The fix is to pass `creator_name` (slug) instead of `creator_uuid` in `refresh_all_active_creators()`.

### Diff

**File: `services/content_refresh.py`**

```diff
--- a/services/content_refresh.py
+++ b/services/content_refresh.py
@@ -248,8 +248,9 @@ async def refresh_all_active_creators() -> Dict:

     logger.info(f"[CONTENT-REFRESH] Starting refresh for {len(creator_ids)} active creators")

-    for creator_uuid, creator_name in creator_ids:
+    for _creator_uuid, creator_name in creator_ids:
         try:
-            result = await refresh_creator_content(creator_uuid)
+            # Use slug (creator name), not UUID — chunks and search both use slug
+            result = await refresh_creator_content(creator_name)

             if result["success"]:
```

That's it. One line change: `refresh_creator_content(creator_uuid)` -> `refresh_creator_content(creator_name)`.

### Why This Works

1. `refresh_creator_content()` already handles slug input (line 64-72):
   ```python
   creator = db.query(Creator).filter(
       or_(
           Creator.name == creator_id,                              # slug path
           Creator.id == creator_id if len(creator_id) > 20 else False,  # UUID path
       )
   ).first()
   ```

2. The slug propagates to:
   - `ingest_instagram_v2(creator_id=creator_name)` -> chunks saved with slug
   - `_embed_new_chunks(creator_name)` -> queries with slug, finds the 93 chunks
   - `store_embedding(chunk_id, creator_id=creator_name, ...)` -> embeddings stored with slug
   - `_hydrate_rag_for_creator(creator_name)` -> RAG loaded with slug

3. At search time, `agent.creator_id` is already slug -> `search_similar(creator_id=slug)` -> matches embeddings stored with slug.

### What About Existing Embeddings?

If any embeddings were previously stored with UUID (from a prior refresh cycle that succeeded), they won't be found by slug-based search. A one-time migration may be needed:

```sql
-- Check if any embeddings use UUID format
SELECT creator_id, COUNT(*)
FROM content_embeddings
GROUP BY creator_id;

-- If UUIDs found, normalize to slug:
UPDATE content_embeddings ce
SET creator_id = c.name
FROM creators c
WHERE ce.creator_id = c.id::text
  AND ce.creator_id != c.name;
```

### Risk Assessment

- **Blast radius**: Only affects content refresh scheduler (runs every 24h)
- **Reversible**: Yes — changing back to UUID is trivial
- **Regression risk**: LOW — the function already handles slug via `or_(Creator.name == creator_id, ...)`
- **Testing**: Run `refresh_creator_content('iris_bertran')` with `--dry-run` after fix

---

## Verification Plan

After applying fix:

1. **Check chunk format**: `SELECT DISTINCT creator_id FROM content_chunks LIMIT 10;` — should show slugs
2. **Check embedding format**: `SELECT DISTINCT creator_id FROM content_embeddings LIMIT 10;` — should show slugs
3. **Manual test**: Call `_embed_new_chunks('iris_bertran')` — should find the 93 un-embedded chunks
4. **Search test**: RAG search with `creator_id='iris_bertran'` should return results with embeddings
