# Neon Database Cost Audit — 2026-03-14

## Current Cost: €37/month for 2 beta users

## TL;DR

**415 Instagram media messages store base64-encoded thumbnails inline in `msg_metadata`, consuming 751 MB (25% of the entire database).** Stripping `thumbnail_base64` from these rows would save ~751 MB instantly. Combined with a REINDEX, the DB could shrink from 3 GB to under 1 GB.

---

## Database Overview

| Metric | Value |
|--------|-------|
| Provider | Neon (pooled via pgbouncer) |
| Region | eu-central-1 (AWS) |
| PostgreSQL | 17.8, aarch64 Linux |
| Total DB size | **2,998 MB (~3 GB)** |
| Active connections | 19 (8 idle, 3 idle-in-transaction) |
| max_connections | 901 |

## Storage Breakdown

### Top Tables (97.4% in 2 tables)

| Table | Total | Data | Indexes | Rows |
|-------|-------|------|---------|------|
| **messages** | **1,848 MB** | 328 MB | 124 MB | 59,205 |
| **conversation_embeddings** | **1,073 MB** | 27 MB | 335 MB | 42,534 |
| lead_memories | 43 MB | 720 kB | 43 MB | 2,931 |
| content_embeddings | 4.2 MB | 312 kB | 3.9 MB | 452 |
| conversation_summaries | 2.2 MB | 1.7 MB | 464 kB | 7,140 |
| Everything else | <2 MB each | — | — | — |

### The Smoking Gun: `thumbnail_base64`

**415 rows** in `messages.msg_metadata` contain base64-encoded image thumbnails from Instagram media messages. These are stored inline in JSONB:

| Metric | Value |
|--------|-------|
| Rows with `thumbnail_base64` | 415 |
| Total size | **751 MB** |
| Average per row | **1.9 million characters** |
| Largest single row | **38.5 million characters (29 MB)** |
| All other metadata combined | 3.7 MB |

**`thumbnail_base64` alone is 25% of the entire database.**

Distribution by creator:
- stefano_bonanno (user msgs): 214 rows, 491 MB
- iris_bertran (user msgs): 116 rows, 147 MB
- iris_bertran (bot msgs): 63 rows, 65 MB
- stefano_bonanno (bot msgs): 37 rows, 48 MB

### Messages Indexes (124 MB total)

| Index | Size |
|-------|------|
| messages_pkey | 57 MB |
| ix_messages_platform_message_id | 26 MB |
| ix_messages_lead_id_created_at | 16 MB |
| ix_messages_lead_id | 11 MB |
| ix_messages_user_by_lead | 8 MB |
| uq_messages_lead_platform_message_id | 5 MB |
| ix_messages_copilot_pending | 16 kB |

Note: `pg_total_relation_size` reports 1,848 MB because it includes TOAST storage (where the large JSONB values are stored).

### Conversation Embeddings Indexes (335 MB)

| Index | Size |
|-------|------|
| idx_conv_emb_embedding (HNSW vector) | **332 MB** |
| conversation_embeddings_pkey | 952 kB |
| ix_conversation_embeddings_follower_id | 688 kB |
| idx_conv_emb_creator_follower | 664 kB |
| ix_conversation_embeddings_creator_id | 464 kB |

The HNSW index is large relative to 42K vectors but typical for high-dimensional pgvector indexes.

## Message Volume Trends

| Month | Messages | Daily avg |
|-------|----------|-----------|
| Jun 2025 | 2,098 | 70 |
| Jul 2025 | 1,085 | 35 |
| Aug-Nov 2025 | ~500-2,500/mo | — |
| Dec 2025 | 12,077 | 390 |
| Jan 2026 | 15,806 | 510 |
| Feb 2026 | 14,979 | 535 |
| Mar 2026 (14d) | ~6,000 | 430 |

## Archivable Data

| Age | Rows | Estimated Size |
|-----|------|----------------|
| >60 days | 29,546 (49%) | ~357 MB |
| >30 days | 45,544 (76%) | ~492 MB |

## Dead Tuples

| Table | Dead | Live | Last Autovacuum |
|-------|------|------|-----------------|
| messages | 4,579 | 59,205 | 2026-03-13 |
| lead_activities | 499 | 2,052 | 2026-02-15 |
| leads | 360 | 2,489 | 2026-03-14 |

Moderate bloat. `lead_activities` hasn't been vacuumed in a month.

## Small Tables (negligible cost)

| Table | Rows | Size |
|-------|------|------|
| llm_usage_log | 3,242 | 696 kB |
| learning_rules | 668 | 504 kB |
| preference_pairs | 636 | 440 kB |
| copilot_evaluations | 54 | 104 kB |
| rag_documents | 827 | 1.1 MB |

## Connection Analysis (affects scale-to-zero)

19 connections active:
- 8 idle
- 3 **idle in transaction** (prevent scale-to-zero!)
- 1 active
- 7 backend/null

The 3 idle-in-transaction connections are likely leaked from SQLAlchemy pool or background tasks. They prevent Neon compute from scaling to zero, keeping billing active 24/7.

---

## Cost Optimization Plan

### Phase 1: Immediate (saves ~800 MB, free to do)

**1a. Strip `thumbnail_base64` from msg_metadata (saves 751 MB)**
```sql
UPDATE messages
SET msg_metadata = msg_metadata - 'thumbnail_base64'
WHERE msg_metadata ? 'thumbnail_base64';
-- Then VACUUM FULL messages;
```
The thumbnails are already stored permanently in Cloudinary (`permanent_url` field exists). The base64 data is redundant.

**1b. Fix the code to stop saving `thumbnail_base64`**
Find where Instagram media processing stores base64 thumbnails and strip before saving.

**1c. REINDEX messages table (reclaim bloated indexes)**
```sql
REINDEX TABLE messages;
VACUUM FULL messages;
```

### Phase 2: Short-term (saves ~300-400 MB)

**2a. Archive messages >60 days old**
Move to `messages_archive` table or export to S3/Cloudinary. Keep last 30 days in hot storage.

**2b. Fix idle-in-transaction connections**
Add `idle_in_transaction_session_timeout = '60s'` to SQLAlchemy engine config. This allows Neon compute to scale to zero when idle.

**2c. Drop backup table**
```sql
DROP TABLE IF EXISTS leads_backup_20260204;
```

### Phase 3: Evaluate plan change

After Phase 1-2, expected DB size: **~1-1.5 GB** (down from 3 GB).

| Neon Plan | Price | Storage | Compute | Fits? |
|-----------|-------|---------|---------|-------|
| Free | $0 | 0.5 GB | 190 CU-h | No (need ~1 GB) |
| Launch | $19/mo | 10 GB | 300 CU-h | Yes |
| Scale | $69/mo | 50 GB | 750 CU-h | Overkill |

If currently on Scale ($69), downgrade to Launch ($19) after cleanup = **save $50/month**.

### Alternatives

| Option | Price | Pros | Cons |
|--------|-------|------|------|
| Neon Launch | $19/mo | Scale-to-zero, PITR, pgvector | Current provider |
| Supabase Free | $0/mo | 500 MB, pgvector, auth | Tight on storage |
| Supabase Pro | $25/mo | 8 GB, more compute | Migration effort |
| Railway Postgres | ~$5-10/mo | Already in Railway, no network latency | No scale-to-zero, no PITR |

---

## Estimated Savings

| Action | Saves | Effort |
|--------|-------|--------|
| Strip thumbnail_base64 | 751 MB | 1 SQL query |
| Stop saving thumbnails | Prevents regrowth | Code fix |
| REINDEX + VACUUM FULL | ~200-500 MB | 1 SQL command |
| Archive >60d messages | ~357 MB | Migration script |
| Fix idle-in-transaction | Enables scale-to-zero | Config change |
| Downgrade Neon plan | €50/month | Dashboard click |
| **Total** | **~1.5-2 GB freed, €50/mo saved** | |
