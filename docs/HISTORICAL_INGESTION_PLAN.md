# Historical Ingestion Plan - Stefan's 6-Month Conversation Archive

## 1. Executive Summary

**Goal:** Process ALL of Stefan's (stefano_bonanno) 6 months of Instagram DM conversations through the Clonnect cognitive engine, transforming raw chat history into actionable intelligence.

**What gets generated:**
- **RelationshipDNA** per lead (relationship type, trust score, vocabulary rules, tone guidance)
- **ConversationState** per lead (sales funnel phase: INICIO through CIERRE)
- **Lead categorization and scoring** (nuevo/interesado/caliente/cliente/fantasma)
- **Fact tracking** (prices given, links shared, topics discussed)
- **WritingPatterns** update (punctuation, emojis, laughs, abbreviations, message lengths)

**Timeline estimate:**
- Data extraction from Instagram API: ~1-2 hours (rate-limited)
- Cognitive processing (all phases): ~35-45 minutes
- Validation: ~10 minutes
- **Total: ~2-3 hours**

---

## 2. Data Extraction Phase

### 2.1 Current Data Inventory

| Source | Location | Count | Notes |
|--------|----------|-------|-------|
| JSON follower files | `backend/data/followers/stefano_bonanno/` | 41 files | Mix of real leads + test fixtures |
| Conversation pairs | `backend/data/stefan_knowledge/conversation_pairs.json` | 500 pairs | Used for RAG knowledge base |
| PostgreSQL messages | `messages` table (joined with `leads`) | Variable | Synced via API + webhook |
| RelationshipDNA (existing) | `backend/data/relationship_dna/stefano_bonanno/` | ~9 files | Partial coverage |
| Dismissed leads | `dismissed_leads` table | Variable | Must be excluded from re-sync |

**Real vs Test data:** The 41 JSON files include test fixtures (`test_0.json` through `test_9.json`, `test_user_*.json`, `test_carlos_123.json`, etc.). These must be filtered out before processing. Estimated real conversations: ~20-25 files.

### 2.2 Instagram API Extraction

Use the existing sync script to pull the full 6-month window:

```bash
cd backend && \
CREATOR_ID=stefano_bonanno \
MAX_AGE_DAYS=180 \
CONSECUTIVE_403_LIMIT=10 \
DATABASE_URL=$DATABASE_URL \
railway run python scripts/sync_instagram_dms.py
```

**Key parameters:**
- Script: `backend/scripts/sync_instagram_dms.py`
- API: Instagram Graph API v21.0 (`https://graph.instagram.com/v21.0`)
- Rate limit: 180 req/hour (script uses 180, leaving 10% margin from the 200/hour API limit)
- `MAX_AGE_DAYS=180` -- 6 months lookback
- `START_FROM=0` -- process all conversations from the beginning
- Blacklist file: `backend/scripts/data/ig_403_blacklist.json` (conversations that return 403)

**Estimated scope:**
- ~200 total conversations (6 months)
- At 180 req/hour: ~1-2 hours for full extraction
- Each conversation requires: 1 request for messages + 1 request for user profile = 2 requests
- Will create `Lead` + `Message` records in PostgreSQL automatically

**What the sync script does per conversation:**
1. Fetches conversation messages from Instagram API
2. Creates or updates `Lead` record (username, full_name, profile_pic_url)
3. Creates `Message` records (deduped by `platform_message_id`)
4. Categorizes lead by history age (new/returning/existing_customer)
5. Generates link previews for URLs in messages
6. Respects dismissed_leads blocklist (migration 012)

### 2.3 Data Quality Checks

After extraction, run these verifications:

```sql
-- Total leads and messages synced
SELECT COUNT(*) as total_leads FROM leads WHERE creator_id = 'stefano_bonanno';
SELECT COUNT(*) as total_messages FROM messages m
JOIN leads l ON m.lead_id = l.id
WHERE l.creator_id = 'stefano_bonanno';

-- Messages per lead distribution
SELECT l.username, COUNT(m.id) as msg_count,
       MIN(m.created_at) as first_msg,
       MAX(m.created_at) as last_msg
FROM leads l
JOIN messages m ON m.lead_id = l.id
WHERE l.creator_id = 'stefano_bonanno'
GROUP BY l.username
ORDER BY msg_count DESC;

-- Check for gaps (conversations with suspiciously few messages)
SELECT l.username, COUNT(m.id) as msg_count
FROM leads l
LEFT JOIN messages m ON m.lead_id = l.id
WHERE l.creator_id = 'stefano_bonanno'
GROUP BY l.username
HAVING COUNT(m.id) < 2
ORDER BY l.username;

-- Verify no dismissed leads were re-created
SELECT dl.platform_user_id, l.id as lead_id
FROM dismissed_leads dl
LEFT JOIN leads l ON l.platform_user_id = dl.platform_user_id
WHERE dl.creator_id = 'stefano_bonanno' AND l.id IS NOT NULL;
```

**Reconciliation check** using existing `core/message_reconciliation.py`:
- Compares API message IDs vs database message IDs
- Detects missing messages (gaps)
- Lookback: `RECONCILIATION_LOOKBACK_HOURS = 24` (increase to cover 6 months)
- Max conversations per cycle: `MAX_CONVERSATIONS_PER_CYCLE = 20` (increase for batch)

**Handle 403 blacklisted conversations:**
- Some conversations return 403 (user blocked, account deleted, etc.)
- Tracked in `ig_403_blacklist.json` with `CONSECUTIVE_403_LIMIT=10`
- After 10 consecutive 403s, script pauses to avoid wasting API calls
- These conversations are skipped permanently

---

## 3. Processing Pipeline

### Phase 1: Lead Categorization (all leads)

**Module:** `core/lead_categorizer.py` (LeadCategory enum) + `core/lead_categorization.py` (calcular_categoria)
**Existing script:** `scripts/recategorize_leads.py` (can be run directly)

For each lead:
1. Load all messages from PostgreSQL
2. Run `calcular_categoria(messages)` which detects keywords:
   - **CALIENTE**: price words ("precio", "cuesta", "pagar", "comprar", "cuanto cuesta")
   - **INTERESADO**: interest words ("informacion", "me interesa", "como funciona")
   - **FANTASMA**: no response >7 days (based on `last_contact_at`)
   - **CLIENTE**: purchase confirmation keywords
   - **NUEVO**: default fallback
3. Update `lead.status` with the category value
4. Log category + reason for audit trail

**Run command:**
```bash
cd backend && railway run python scripts/recategorize_leads.py
# Or with dry-run first:
cd backend && railway run python scripts/recategorize_leads.py --dry-run
```

**Priority of evaluation (order matters):**
1. Cliente (final state -- already purchased)
2. Caliente (highest commercial priority)
3. Fantasma (inactive >7 days)
4. Interesado (showing curiosity)
5. Nuevo (default)

### Phase 2: Conversation State Reconstruction (all leads)

**Module:** `core/conversation_state.py` (ConversationPhase, ConversationStateDB)
**DB table:** `conversation_states` (model: `ConversationStateDB` in `api/models.py`)

The conversation state machine tracks the sales funnel:
```
INICIO -> CUALIFICACION -> DESCUBRIMIENTO -> PROPUESTA -> OBJECIONES -> CIERRE -> ESCALAR
```

For each conversation:
1. Create `ConversationState` with `phase=INICIO`
2. Load all messages sorted chronologically by `created_at`
3. For each message pair (user message + assistant response):
   - Detect intent from user message
   - Update phase based on intent signals:
     - Name/situation mentioned -> CUALIFICACION
     - Goal/interest expressed -> DESCUBRIMIENTO
     - Product interest -> PROPUESTA
     - Price/payment discussed -> OBJECIONES or CIERRE
     - Escalation requested -> ESCALAR
   - Update `UserContext` (name, situation, goal, constraints, product_interested, price_discussed, link_sent)
4. Persist final `ConversationStateDB` to PostgreSQL
5. Environment variable: `PERSIST_CONVERSATION_STATE=true` (default)

**UserContext fields tracked:**
- `name`: Lead's name (detected from messages)
- `situation`: Personal context ("madre de 3", "trabaja mucho")
- `goal`: What they want ("bajar peso", "mas energia")
- `constraints`: Limitations ("poco tiempo", "bajo presupuesto")
- `product_interested`: Specific product they asked about
- `price_discussed`: Boolean -- was price mentioned?
- `link_sent`: Boolean -- was a link shared?
- `objections_raised`: List of objections detected

### Phase 3: RelationshipDNA Generation (leads with >=5 messages)

**Module:** `services/relationship_analyzer.py` (RelationshipAnalyzer)
**Model:** `models/relationship_dna.py` (RelationshipDNA dataclass)
**DB table:** `relationship_dna` (unique constraint on creator_id + follower_id)
**Existing migration script:** `scripts/migrate_dna.py`

**Threshold:** `MIN_MESSAGES_FOR_ANALYSIS = 5` (leads with fewer messages are skipped)

For each eligible lead:
1. Call `RelationshipAnalyzer.analyze(creator_id, follower_id, messages)`
2. Analyzer detects relationship type based on vocabulary indicators:
   - **INTIMA**: "amor", "te amo", "mi vida" + emojis: heart, kiss
   - **AMISTAD_CERCANA**: "hermano", "bro", "crack" + spiritual topics (circulo, retiro, meditacion)
   - **AMISTAD_CASUAL**: "crack", "tio", "maquina" + casual emojis
   - **CLIENTE**: "precio", "cuesta", "pagar", "programa", "curso"
   - **COLABORADOR**: Professional/business context detected
   - **DESCONOCIDO**: Default for new leads
3. Generate per-lead output:
   - `relationship_type`: One of the 6 types above
   - `trust_score`: 0.0-1.0 based on conversation depth and duration
   - `depth_level`: 0-4 based on message history depth
   - `vocabulary_uses`: Words/phrases TO use with this lead
   - `vocabulary_avoids`: Words/phrases to AVOID with this lead
   - `emojis`: Appropriate emojis for this relationship
   - `avg_message_length`: Target message length
   - `questions_frequency`: 0.0-1.0 how often to ask questions
   - `multi_message_frequency`: 0.0-1.0 how often to send multiple messages
   - `tone_description`: Text description of tone to use
   - `recurring_topics`: Frequently discussed topics
   - `private_references`: Inside jokes, shared memories
   - `bot_instructions`: Combined instructions for the DM agent
4. Save to `relationship_dna` table (upsert on creator_id + follower_id)

**Stale check:** Re-analyze if data is >30 days old (`STALE_DAYS = 30`) or if 10+ new messages since last analysis (`MESSAGE_INCREASE_THRESHOLD = 10`).

### Phase 4: Fact Extraction (all conversations)

For each conversation (all messages):

1. **PRICE_GIVEN detection** (regex on assistant messages):
   ```python
   # Patterns to detect
   r'\d+\s*euros?'          # "297 euros", "97 euros"
   r'\d+\s*\u20ac'          # "297€"
   r'\$\s*\d+'              # "$297"
   r'precio\s+(?:es\s+)?(?:de\s+)?\d+'  # "precio es 297"
   ```

2. **LINK_SHARED detection** (regex on assistant messages):
   ```python
   # URL pattern (already exists in sync script)
   r'https?://[^\s<>"{}|\\^`\[\]]+'
   ```
   - Filter out CDN URLs (`cdninstagram.com`, `fbcdn.net`)
   - Track which links were shared and when

3. **Topics discussed** (keyword extraction from user messages):
   - Products mentioned (cross-reference with creator's product catalog)
   - Personal topics (health, fitness, mindset, business)
   - Objections raised (price, time, doubt)

4. **Build fact timeline per lead:**
   ```json
   {
     "lead_id": "abc123",
     "facts": [
       {"type": "TOPIC", "value": "programa fitness", "date": "2025-09-15"},
       {"type": "PRICE_GIVEN", "value": "297 euros", "date": "2025-09-16"},
       {"type": "LINK_SHARED", "value": "https://example.com/programa", "date": "2025-09-16"},
       {"type": "OBJECTION", "value": "price_concern", "date": "2025-09-17"}
     ]
   }
   ```

### Phase 5: Writing Pattern Analysis (Stefan's messages only)

**Model:** `models/writing_patterns.py` (WritingPatterns dataclass)
**Current baseline:** 3,056 messages analyzed (noted in model docstring)

1. Collect ALL of Stefan's assistant/outgoing messages from PostgreSQL:
   ```sql
   SELECT m.content FROM messages m
   JOIN leads l ON m.lead_id = l.id
   WHERE l.creator_id = 'stefano_bonanno'
   AND m.sender = 'assistant'
   AND m.content IS NOT NULL AND m.content != '';
   ```

2. Calculate **capitalization patterns:**
   - `starts_upper_pct`: % messages starting with uppercase
   - `starts_lower_pct`: % messages starting with lowercase
   - `all_caps_pct`: % messages in ALL CAPS

3. Calculate **punctuation patterns:**
   - `ends_exclamation_pct`, `ends_question_pct`, `ends_period_pct`
   - `ends_emoji_pct`, `uses_ellipsis_pct`
   - `double_exclamation_pct`, `double_question_pct`

4. Calculate **laugh patterns:**
   - `laugh_frequency_pct`: % messages containing a laugh
   - `laugh_patterns`: Dict mapping pattern to count (e.g., `{"jaja": 45, "jajaja": 32, "haha": 5}`)
   - `preferred_laugh`: Most common laugh style

5. Calculate **emoji patterns:**
   - `emoji_frequency_pct`: % messages containing any emoji
   - `top_emojis`: Top 10 most used emojis
   - Position analysis: `emoji_at_start_pct`, `emoji_at_end_pct`, `emoji_middle_pct`

6. Extract **abbreviations** used (Dict[str, str] mapping abbreviation to full form)

7. Calculate **length stats:**
   - `length_mean`, `length_median`, `length_mode`

8. Extract **common responses** (exact repeated messages for templating)

9. Extract **common openers** (first messages in conversations) and **common closers** (last messages)

10. Update `WritingPatterns` model with the full 6-month dataset (replacing the 3,056-message baseline)

### Phase 6: Lead Scoring

For each lead, calculate a composite score (0-100):

| Signal | Weight | Source |
|--------|--------|--------|
| Purchase intent keywords | 30% | Phase 1 (lead_categorizer) |
| Conversation depth | 20% | Phase 2 (conversation_state phase) |
| Recency (days since last message) | 20% | Messages table |
| Engagement (message count) | 15% | Messages table |
| Relationship depth | 15% | Phase 3 (RelationshipDNA trust_score) |

**Priority classifications:**
- **Hot leads** (score > 70): Immediate action required
- **Warm leads** (score 40-70): Nurturing sequences
- **Cold leads** (score < 40): Low priority
- **Ghosts** (>7 days inactive, any score): Reactivation candidates

Output: Update `lead.score` in PostgreSQL + generate priority ranking report.

### Phase 7: Validation

Quality assurance on the processing results.

1. **Select 10 random conversations** with >=10 messages each
2. For each conversation:
   - Take a real user message from the middle of the conversation
   - Generate a bot response using the DM agent with the loaded RelationshipDNA + ConversationState
   - Compare with Stefan's actual response
3. **Calculate similarity metrics:**
   - Jaccard similarity (word overlap)
   - Cosine similarity (TF-IDF vectors)
   - Tone match (formal/informal classification agreement)
   - Length ratio (generated vs actual message length)
4. **Report quality metrics:**
   - Mean similarity score across 10 conversations
   - Per-conversation breakdown
   - Flag conversations where similarity < 0.3 for manual review

---

## 4. Script Architecture

### Main Script: `scripts/batch_process_historical.py`

```
batch_process_historical.py
|
+-- extract_data()               # Phase 0: Ensure all data is synced from Instagram API
|   +-- calls sync_instagram_dms.py logic with MAX_AGE_DAYS=180
|   +-- runs reconciliation check
|   +-- outputs: lead count, message count, gap report
|
+-- categorize_leads()           # Phase 1: Run lead categorization
|   +-- uses core/lead_categorizer.py (LeadCategory)
|   +-- uses core/lead_categorization.py (calcular_categoria)
|   +-- updates Lead.status in DB
|
+-- reconstruct_states()         # Phase 2: Build conversation states
|   +-- uses core/conversation_state.py (ConversationPhase, UserContext)
|   +-- replays messages chronologically per lead
|   +-- persists ConversationStateDB to PostgreSQL
|
+-- generate_dna()               # Phase 3: Generate RelationshipDNA
|   +-- uses services/relationship_analyzer.py (RelationshipAnalyzer)
|   +-- threshold: MIN_MESSAGES_FOR_ANALYSIS = 5
|   +-- saves to relationship_dna table
|
+-- extract_facts()              # Phase 4: Extract facts from conversations
|   +-- regex-based price, link, topic detection
|   +-- builds per-lead fact timeline
|
+-- analyze_patterns()           # Phase 5: Writing pattern analysis
|   +-- collects all Stefan assistant messages
|   +-- updates models/writing_patterns.py
|
+-- score_leads()                # Phase 6: Calculate composite lead scores
|   +-- combines signals from phases 1-3
|   +-- updates Lead.score in DB
|
+-- validate_quality()           # Phase 7: Quality validation
|   +-- samples 10 conversations
|   +-- generates bot responses, compares with actual
|   +-- outputs similarity report
|
+-- generate_report()            # Final summary report
    +-- per-phase statistics
    +-- lead distribution by category
    +-- hot leads list
    +-- ghost leads list
    +-- quality metrics
```

### Parallelization Strategy

```
Phase 0 (extract)     -----[sequential, rate-limited]----->
                                                           |
Phase 1 (categorize)  -----[parallel per lead]----------->+
Phase 3 (DNA)         -----[parallel per lead]----------->+ (can run with Phase 1)
Phase 4 (facts)       -----[parallel per lead]----------->+ (can run with Phase 1)
                                                           |
Phase 2 (states)      -----[sequential per conversation]-->  (must replay chronologically)
                                                           |
Phase 5 (patterns)    -----[sequential, aggregation]------>  (needs all Stefan messages)
                                                           |
Phase 6 (scoring)     -----[depends on 1, 2, 3]---------->
Phase 7 (validation)  -----[depends on all above]--------->
```

- **Phases 1, 3, 4** can run in parallel (per-lead, independent operations)
- **Phase 2** must be sequential per conversation (chronological replay order matters)
- **Phase 5** needs all Stefan messages collected (aggregation step)
- **Phase 6** depends on outputs from Phases 1, 2, and 3
- **Phase 7** depends on all previous phases being complete

### CLI Interface

```bash
# Full pipeline
python scripts/batch_process_historical.py --creator stefano_bonanno

# Individual phases
python scripts/batch_process_historical.py --creator stefano_bonanno --phase extract
python scripts/batch_process_historical.py --creator stefano_bonanno --phase categorize
python scripts/batch_process_historical.py --creator stefano_bonanno --phase states
python scripts/batch_process_historical.py --creator stefano_bonanno --phase dna
python scripts/batch_process_historical.py --creator stefano_bonanno --phase facts
python scripts/batch_process_historical.py --creator stefano_bonanno --phase patterns
python scripts/batch_process_historical.py --creator stefano_bonanno --phase score
python scripts/batch_process_historical.py --creator stefano_bonanno --phase validate

# Dry-run (no writes)
python scripts/batch_process_historical.py --creator stefano_bonanno --dry-run

# Resume from a specific phase (skip completed phases)
python scripts/batch_process_historical.py --creator stefano_bonanno --resume-from dna

# Limit to specific leads
python scripts/batch_process_historical.py --creator stefano_bonanno --leads "mauriciosperanza93,fiorelllap"
```

---

## 5. Resource Requirements

### API Limits

| API | Limit | Estimated Usage | Cost |
|-----|-------|----------------|------|
| Instagram Graph API | 200 req/hour (180 used) | ~400 requests (200 convos x 2) | Free |
| OpenAI GPT-4 (validation) | Per token | ~10 validation responses | ~$0.50 |
| OpenAI embeddings | $0.0001/1K tokens | Optional (for similarity) | ~$0.10 |
| **Total estimated API cost** | | | **< $1** |

### Database Impact

| Resource | Estimated Size | Notes |
|----------|---------------|-------|
| Lead records | ~200 rows | One per conversation |
| Message records | ~5,000-10,000 rows | All messages across 6 months |
| ConversationState records | ~200 rows | One per lead |
| RelationshipDNA records | ~50-80 rows | Only leads with >=5 messages |
| PostgreSQL storage | ~50MB | Messages + metadata |
| pgvector embeddings | ~100MB | If embedding generation is added |

### Compute

| Phase | CPU | Memory | Disk I/O |
|-------|-----|--------|----------|
| Data extraction | Low (network-bound) | ~100MB | Moderate (DB writes) |
| Lead categorization | Low (regex) | ~50MB | Low |
| State reconstruction | Low | ~100MB | Low |
| DNA generation | Low (regex + heuristics) | ~100MB | Low |
| Fact extraction | Low (regex) | ~50MB | Low |
| Pattern analysis | Low (statistics) | ~200MB | Low |
| Lead scoring | Low | ~50MB | Low |
| Validation | Medium (LLM calls) | ~200MB | Low |

### Time Estimates

| Phase | Estimated Time | Parallelizable | Bottleneck |
|-------|---------------|----------------|------------|
| Phase 0: Data extraction | 1-2 hours | No | Instagram API rate limit (180/hr) |
| Phase 1: Lead categorization | 2-5 min | Yes (per lead) | None |
| Phase 2: State reconstruction | 5-10 min | Per-lead yes | Sequential replay per conversation |
| Phase 3: DNA generation | 5-15 min | Yes (per lead) | None |
| Phase 4: Fact extraction | 2-5 min | Yes (per lead) | None |
| Phase 5: Pattern analysis | 1-2 min | No (aggregation) | None |
| Phase 6: Lead scoring | 1-2 min | Yes (per lead) | Depends on phases 1-3 |
| Phase 7: Validation | 5-10 min | Per-conversation | LLM response time |
| **Total** | **~2-3 hours** | | **Dominated by API extraction** |

---

## 6. Risk Mitigation

### Checkpoint and Resume

Each phase saves a checkpoint file on completion:

```json
// backend/data/batch_checkpoints/stefano_bonanno.json
{
  "creator_id": "stefano_bonanno",
  "started_at": "2026-02-07T10:00:00Z",
  "phases_completed": ["extract", "categorize", "states"],
  "phases_pending": ["dna", "facts", "patterns", "score", "validate"],
  "last_phase_completed_at": "2026-02-07T11:15:00Z",
  "leads_processed": 187,
  "errors": []
}
```

On failure, use `--resume-from <phase>` to skip completed phases.

### Rate Limiting

- Instagram API: Existing `core/instagram_rate_limiter.py` handles throttling
- 180 req/hour with automatic backoff when approaching limit
- Exponential backoff on 429 (Too Many Requests) responses
- Consecutive 403 tracking with `CONSECUTIVE_403_LIMIT=10`

### Database Safety

- All write operations wrapped in database transactions
- Rollback on error (no partial writes per lead)
- Upsert pattern for RelationshipDNA (unique constraint on creator_id + follower_id)
- Dismissed leads blocklist respected (table: `dismissed_leads`, migration 012)

### Dry-Run Mode

```bash
python scripts/batch_process_historical.py --creator stefano_bonanno --dry-run
```

- Reads all data and runs all analysis
- Prints what WOULD be written (category, score, DNA type)
- Does NOT modify any database records
- Useful for reviewing results before committing

### Logging and Progress

- Python `logging` module (not print statements, per CLAUDE.md standards)
- Progress tracking: `Processing lead 45/187 (mauriciosperanza93) - Phase 3: DNA`
- Per-phase summary: leads processed, errors, time elapsed
- Error details logged with full traceback
- Output log file: `backend/logs/batch_process_YYYYMMDD_HHMMSS.log`

### Data Integrity Checks

- Before processing: verify `leads` table has expected count
- After extraction: compare API conversation count vs DB lead count
- After categorization: verify no lead has NULL status
- After DNA: verify all leads with >=5 messages have a RelationshipDNA record
- After scoring: verify all leads have a score between 0-100

---

## 7. Expected Outputs

### Per Lead

| Output | Table/Model | Fields Updated |
|--------|------------|---------------|
| Category | `leads.status` | nuevo/interesado/caliente/cliente/fantasma |
| Score | `leads.score` | 0-100 composite score |
| ConversationState | `conversation_states` | phase, user_context, price_discussed, link_sent |
| RelationshipDNA | `relationship_dna` | relationship_type, trust_score, depth_level, vocabulary_uses, vocabulary_avoids, emojis, bot_instructions |
| Fact timeline | New: `lead_facts` or JSON | type, value, date per fact |

### Per Lead Detail (example)

```json
{
  "lead": "mauriciosperanza93",
  "status": "interesado",
  "score": 65,
  "conversation_state": {
    "phase": "DESCUBRIMIENTO",
    "user_context": {
      "name": "Mauricio",
      "goal": "mejorar fisico",
      "product_interested": "programa online"
    }
  },
  "relationship_dna": {
    "relationship_type": "AMISTAD_CASUAL",
    "trust_score": 0.6,
    "depth_level": 2,
    "vocabulary_uses": ["crack", "tio", "genial"],
    "vocabulary_avoids": ["amor", "te quiero"],
    "emojis": ["💪", "🔥", "👍"],
    "bot_instructions": "Tono casual y motivador. Usa 'crack' y 'tio'. No seas demasiado formal."
  },
  "facts": [
    {"type": "TOPIC", "value": "entrenamiento", "date": "2025-10-15"},
    {"type": "LINK_SHARED", "value": "https://example.com/programa", "date": "2025-10-20"}
  ]
}
```

### Aggregate Outputs

| Output | Description |
|--------|-------------|
| **WritingPatterns** | Updated with full 6-month dataset (replacing 3,056-message baseline) |
| **Hot leads list** | Leads with score > 70, sorted by score descending |
| **Ghost leads list** | Leads with >7 days inactive, candidates for reactivation |
| **Conversion funnel** | Count of leads per ConversationPhase (INICIO through CIERRE) |
| **Relationship distribution** | Count of leads per RelationshipType |
| **Quality validation report** | Similarity scores for 10 sampled conversations |

### Summary Report (generated at end)

```
============================================================
HISTORICAL INGESTION REPORT - stefano_bonanno
Date: 2026-02-07
============================================================

DATA EXTRACTION
  Conversations fetched: 187
  Messages synced: 6,432
  403 blacklisted: 13
  Extraction time: 1h 23m

LEAD CATEGORIZATION
  Nuevo: 45 (24%)
  Interesado: 72 (39%)
  Caliente: 23 (12%)
  Cliente: 15 (8%)
  Fantasma: 32 (17%)

CONVERSATION STATES
  INICIO: 38
  CUALIFICACION: 42
  DESCUBRIMIENTO: 51
  PROPUESTA: 28
  OBJECIONES: 15
  CIERRE: 10
  ESCALAR: 3

RELATIONSHIP DNA
  Eligible leads (>=5 msgs): 68
  INTIMA: 2
  AMISTAD_CERCANA: 8
  AMISTAD_CASUAL: 25
  CLIENTE: 18
  COLABORADOR: 3
  DESCONOCIDO: 12

LEAD SCORING
  Hot (>70): 18
  Warm (40-70): 45
  Cold (<40): 124

WRITING PATTERNS
  Messages analyzed: 3,216 (Stefan's outgoing)
  Preferred laugh: jaja (67%)
  Emoji usage: 42% of messages
  Top emojis: 🔥 💪 🙏 ❤️ 😄
  Mean message length: 47 chars

VALIDATION
  Mean similarity: 0.72
  Best match: fiorelllap (0.89)
  Worst match: ig_123456789 (0.41)

TOTAL TIME: 2h 15m
============================================================
```

---

## 8. Post-Processing Actions

### Immediate Actions (automated)

1. **Ghost reactivation:** For leads classified as FANTASMA with score > 30:
   - Queue reactivation message via `scripts/process_nurturing.py`
   - Use RelationshipDNA to personalize the reactivation tone
   - Respect time-of-day preferences if detected

2. **Hot lead alerts:** For leads with score > 70:
   - Send notification to Stefan via Telegram (if configured)
   - Generate suggested follow-up message using ConversationState context
   - Priority flag in the frontend Leads dashboard

3. **RAG index update:**
   - Update conversation pairs in `data/stefan_knowledge/conversation_pairs.json`
   - Re-index for retrieval-augmented generation
   - Include newly extracted facts and relationship context

### Manual Actions (Stefan reviews)

1. **Review hot leads list** -- prioritize follow-up within 24 hours
2. **Review ghost leads** -- decide which to reactivate vs dismiss
3. **Spot-check RelationshipDNA** -- verify relationship types are correct for close contacts
4. **Review validation report** -- flag any conversations where bot quality is low

### Ongoing Maintenance

- **Incremental sync:** The webhook system (`core/webhook_routing.py`) handles real-time new messages
- **Periodic reconciliation:** `core/message_reconciliation.py` runs every 5 minutes
- **DNA refresh:** Re-analyze when `MESSAGE_INCREASE_THRESHOLD = 10` new messages accumulated
- **Cache warming:** `api/startup.py` pre-loads conversations/leads on startup (refreshes every 20s)

---

## 9. File Reference

| File | Purpose |
|------|---------|
| `backend/scripts/sync_instagram_dms.py` | Instagram DM sync (data extraction) |
| `backend/scripts/recategorize_leads.py` | Lead recategorization (Phase 1) |
| `backend/core/lead_categorizer.py` | LeadCategory enum + CATEGORY_CONFIG |
| `backend/core/lead_categorization.py` | calcular_categoria function |
| `backend/core/conversation_state.py` | ConversationPhase, UserContext, state machine |
| `backend/services/relationship_analyzer.py` | RelationshipAnalyzer.analyze() |
| `backend/models/relationship_dna.py` | RelationshipDNA dataclass + RelationshipType enum |
| `backend/services/relationship_dna_service.py` | RelationshipDNA persistence service |
| `backend/services/relationship_dna_repository.py` | RelationshipDNA DB repository |
| `backend/models/writing_patterns.py` | WritingPatterns dataclass |
| `backend/core/message_reconciliation.py` | Message gap detection and reconciliation |
| `backend/core/instagram_rate_limiter.py` | API rate limiting |
| `backend/core/webhook_routing.py` | Real-time webhook message routing |
| `backend/api/models.py` | SQLAlchemy models (Lead, Message, ConversationStateDB) |
| `backend/data/followers/stefano_bonanno/` | 41 JSON follower files |
| `backend/data/relationship_dna/stefano_bonanno/` | Existing DNA JSON files |
| `backend/data/stefan_knowledge/conversation_pairs.json` | 500 conversation pairs |
| `backend/scripts/migrate_dna.py` | RelationshipDNA migration script |

---

## 10. Prerequisites Checklist

Before running the batch process:

- [ ] `DATABASE_URL` environment variable set (or Railway context available)
- [ ] Instagram access token valid and not expired for stefano_bonanno
- [ ] At least 200 API calls available in the current hour window
- [ ] PostgreSQL database accessible with sufficient storage (~150MB free)
- [ ] `alembic upgrade head` has been run (migrations 011-014 applied)
- [ ] `dismissed_leads` table exists (migration 012)
- [ ] `conversation_states` table exists
- [ ] `relationship_dna` table exists
- [ ] Backup of current database taken (`scripts/backup_db.py`)
- [ ] Dry-run completed successfully with no errors
