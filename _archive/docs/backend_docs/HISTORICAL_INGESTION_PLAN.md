# Historical Data Ingestion Plan: Stefan's DM Conversations
**Date:** 2026-02-07
**Creator:** stefano_bonanno
**Objective:** Process 6 months of historical Instagram DMs through the Cognitive Engine to generate RelationshipDNA, extract facts, establish conversation states, and build lead scoring for all existing followers.

---

## 1. Executive Summary

Stefan (stefano_bonanno) has approximately 6 months of Instagram DM history stored across multiple data sources. This data has never been processed through the cognitive engine modules (lead categorization, DNA generation, fact extraction, conversation state tracking, etc.). Processing this historical data will:

1. **Generate RelationshipDNA** for each active lead (personalization profiles)
2. **Extract facts** (prices shared, links given, products discussed)
3. **Reconstruct conversation states** (funnel phases for each lead)
4. **Score and categorize leads** based on actual conversation history
5. **Build writing pattern baselines** from Stefan's real responses
6. **Populate semantic memory** for better RAG retrieval

---

## 2. Data Sources Inventory

### 2.1 JSON Follower Files
- **Location:** `data/followers/stefano_bonanno/`
- **Count:** ~41 JSON files
- **Content per file:** follower_id, username, name, message history, interests, products_discussed, purchase_intent_score, timestamps
- **Format:** One file per follower with full conversation history

### 2.2 PostgreSQL Database
- **Tables:** leads, messages, follower_memories
- **Content:** CRM data, message records, lead status
- **Note:** May have more recent data than JSON files

### 2.3 Knowledge Base
- **Location:** `data/stefan_knowledge/conversation_pairs.json`
- **Count:** 2,000+ conversation pairs
- **Content:** Real Q&A exchanges (user question + Stefan's response)
- **Usage:** Already indexed in RAG, but can be used for writing pattern analysis

### 2.4 Sync Script
- **Location:** `scripts/sync_instagram_dms.py`
- **Purpose:** Can pull fresh DMs from Instagram API
- **Reconciliation:** `core/message_reconciliation.py` handles dedup

---

## 3. Processing Pipeline

### Phase 1: Data Collection & Normalization (Pre-processing)

```
┌──────────────────────────────────────────────────┐
│  STEP 1: Collect all conversation data            │
│  - Load 41 JSON follower files                    │
│  - Query PostgreSQL for additional messages        │
│  - Deduplicate using message_reconciliation        │
│  - Sort all messages chronologically               │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│  STEP 2: Normalize message format                 │
│  - Ensure consistent {role, content, timestamp}   │
│  - Identify Stefan's messages (role=assistant)     │
│  - Identify follower messages (role=user)          │
│  - Flag media-only messages                        │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────┐
│  STEP 3: Build conversation windows               │
│  - Group messages into conversation sessions       │
│  - Session boundary: 4+ hours gap                  │
│  - Each window = one "conversation"                │
│  - Metadata: start_time, end_time, message_count   │
└──────────────────────────────────────────────────┘
```

### Phase 2: Lead Categorization

For each follower, process their full message history through `lead_categorizer`:

```python
from core.lead_categorizer import get_lead_categorizer

categorizer = get_lead_categorizer()
for follower in all_followers:
    messages = follower.all_messages  # chronological
    is_customer = check_if_purchased(follower)
    category, score, reason = categorizer.categorize(messages, is_customer)
    # Store: follower_id -> (category, score, reason)
```

**Expected output:**
- Each follower categorized as NUEVO/INTERESADO/CALIENTE/CLIENTE/FANTASMA
- Score and reason for categorization
- Update `leads` table with new status

### Phase 3: Conversation State Reconstruction

For each follower, replay conversations to determine current funnel phase:

```python
from core.conversation_state import get_state_manager

state_mgr = get_state_manager()
for follower in all_followers:
    for window in conversation_windows:
        # Simulate state transitions based on message content
        state = state_mgr.process_history(
            follower_id=follower.follower_id,
            creator_id="stefano_bonanno",
            messages=window.messages
        )
    # Final state = current funnel phase
```

**Expected output:**
- Each follower mapped to a funnel phase
- Phase transitions history
- Store in `conversation_states` table

### Phase 4: RelationshipDNA Generation

For followers with sufficient history (5+ messages), generate DNA:

```python
from services.relationship_analyzer import RelationshipAnalyzer
from services.dna_update_triggers import get_dna_triggers

analyzer = RelationshipAnalyzer()
triggers = get_dna_triggers()

for follower in followers_with_5plus_messages:
    messages = follower.all_messages[-20:]  # Last 20 for DNA
    dna = analyzer.analyze(
        creator_id="stefano_bonanno",
        follower_id=follower.follower_id,
        messages=messages
    )
    # Store DNA in relationship_dna table
```

**Expected output per follower:**
- trust_level (0.0-1.0)
- communication_preferences (formal/informal, long/short)
- topics_of_interest (products, topics discussed)
- purchase_readiness (0.0-1.0)
- engagement_style (active/passive, questioner/listener)
- recommended_approach (next best action)

### Phase 5: Fact Extraction

Extract all facts from conversation history:

```python
import re
from models.conversation_memory import ConversationMemory

FACT_PATTERNS = {
    "PRICE_GIVEN": r"\d+\s*€|\d+\s*euros?|\$\d+",
    "LINK_SHARED": r"https?://\S+",
    "PRODUCT_MENTIONED": None,  # Match against product catalog
    "APPOINTMENT_SET": r"mañana|lunes|martes|miércoles|jueves|viernes|a las \d+",
    "CONTACT_SHARED": r"@\w+|[\w.-]+@[\w.-]+\.\w+|\+?\d{9,}",
}

for follower in all_followers:
    facts = []
    for msg in follower.all_messages:
        for fact_type, pattern in FACT_PATTERNS.items():
            if pattern and re.search(pattern, msg["content"], re.IGNORECASE):
                facts.append({
                    "type": fact_type,
                    "message": msg["content"][:200],
                    "timestamp": msg["timestamp"],
                    "role": msg["role"]
                })
    # Store facts per follower
```

**Expected output:**
- All prices shared in conversations
- All links shared
- Products mentioned per follower
- Contact info exchanged
- Appointments/commitments made

### Phase 6: Writing Pattern Analysis

Analyze Stefan's historical responses for writing patterns:

```python
from models.writing_patterns import WritingPatterns

stefan_messages = []
for follower in all_followers:
    for msg in follower.all_messages:
        if msg["role"] == "assistant":
            stefan_messages.append(msg)

patterns = WritingPatterns.analyze(stefan_messages)
# avg_length, emoji_frequency, common_phrases, etc.
```

**Expected output:**
- Updated writing_patterns model with 6 months of data
- Response time distribution
- Message length distribution by context
- Most used phrases and vocabulary

### Phase 7: Lead Scoring Update

Recalculate lead scores based on full history:

```python
from services import LeadService

lead_service = LeadService()
for follower in all_followers:
    for msg in follower.user_messages:
        intent = intent_classifier.classify(msg["content"])
        score = lead_service.calculate_intent_score(
            current_score=follower.purchase_intent_score,
            intent=intent.value,
            has_direct_purchase_keywords=check_purchase_keywords(msg)
        )
        follower.purchase_intent_score = score
    # Store final score
```

### Phase 8: Validation & Reporting

```python
# Generate ingestion report
report = {
    "total_followers_processed": len(all_followers),
    "total_messages_processed": total_msg_count,
    "categories": {cat: count for cat, count in category_counts.items()},
    "dna_generated": dna_count,
    "facts_extracted": total_facts,
    "avg_score": avg_purchase_intent,
    "processing_time": elapsed_time,
}
```

---

## 4. Resource Estimates

| Resource | Estimate |
|----------|----------|
| Followers to process | ~41 (from JSON files) |
| Total messages | ~2,000-5,000 |
| DB queries | ~200 (reads) + ~200 (writes) |
| LLM calls | 0 (all rule-based processing) |
| Processing time | ~5-15 minutes |
| Storage impact | ~50MB additional DB data |

**Note:** This pipeline is entirely rule-based (no LLM calls needed). All modules use pattern matching, scoring algorithms, and deterministic rules.

---

## 5. Execution Order

```
Phase 1: Data Collection        ──── 2 min (I/O bound)
Phase 2: Lead Categorization    ──── 1 min (CPU)
Phase 3: State Reconstruction   ──── 2 min (CPU)
Phase 4: DNA Generation         ──── 3 min (CPU + DB writes)
Phase 5: Fact Extraction        ──── 1 min (regex)
Phase 6: Writing Patterns       ──── 1 min (analysis)
Phase 7: Lead Scoring           ──── 1 min (calculation)
Phase 8: Validation             ──── < 1 min
                                ─────────────
TOTAL ESTIMATED:                ~12 minutes
```

---

## 6. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Data corruption | Run on copy of data first; PostgreSQL transactions |
| Duplicate processing | Deduplicate by message timestamp + content hash |
| Score overwrites | Store original scores before updating; allow rollback |
| Missing data | Log all follower IDs with incomplete data |
| API rate limits | No API calls needed - all local processing |
| Memory usage | Process followers in batches of 10 |
| DB locks | Use short transactions; no long-running locks |

---

## 7. Pre-requisites

1. **Database access:** Valid `DATABASE_URL` environment variable
2. **JSON files present:** `data/followers/stefano_bonanno/` accessible
3. **Modules available:** All cognitive modules importable
4. **Backup:** Database backup before running
5. **Environment:** Run in Railway environment or with `.env` loaded

---

## 8. Post-Ingestion Verification

After processing, verify with these queries:

```bash
# Check lead categories
curl "https://www.clonnectapp.com/api/dm/leads/stefano_bonanno" | jq '.[] | .status'

# Check DNA generated
curl "https://www.clonnectapp.com/api/debug/agent-config/stefano_bonanno"

# Check conversation states
SELECT phase, COUNT(*) FROM conversation_states
WHERE creator_id = 'stefano_bonanno' GROUP BY phase;

# Check facts extracted
SELECT follower_id, COUNT(*) as fact_count
FROM conversation_facts
WHERE creator_id = 'stefano_bonanno' GROUP BY follower_id;
```

---

## 9. Script Location

The batch processing script is at:
`scripts/batch_process_historical.py`

Run with:
```bash
cd backend
python scripts/batch_process_historical.py --creator stefano_bonanno --dry-run
python scripts/batch_process_historical.py --creator stefano_bonanno --execute
```
