# Audit — Sistema #7: User Context Builder

**Date:** 2026-04-01
**Status:** Audit complete — 10 functional tests (21 assertions, 0 failures)
**File:** `core/user_context_loader.py` (666 lines)
**Lines read:** ALL (1–666)

## What is it?

Loads a complete user profile from 3 data sources and formats it for LLM prompt injection:
1. **FollowerMemory (JSON files)** — `data/followers/{creator_id}/{follower_id}.json`
2. **UserProfile (JSON files)** — via `core/user_profiles.get_user_profile()`
3. **Lead table (PostgreSQL)** — via `api.models.Lead` ORM

Produces a `UserContext` dataclass with: identity (name, username), preferences (language, tone, style), interests, products_discussed, objections_raised, scores (purchase_intent, engagement), CRM status (from Lead table), conversation history (last 20 messages), computed flags (is_first_message, is_returning_user, days_since_last_contact).

## Pipeline Position

```
Two code paths exist:

PATH A (MAIN PIPELINE — dm_agent_v2):
  context.py:242  → agent.memory_store.get_or_create() → FollowerMemory (JSON)
  context.py:920  → builds _lead_info dict from follower object fields
  context.py:934  → agent.prompt_builder.build_user_context() → PromptBuilder (prompt_service.py)
  ⚠️ user_context_loader.py IS NOT CALLED in this path

PATH B (PROMPT BUILDER MODULE — core/prompt_builder/):
  orchestration.py:183 → load_user_context() → user_context_loader.py
  orchestration.py:102 → build_user_section() → format_user_context_for_prompt()
  ⚠️ This path is used by build_prompt_from_ids() convenience function

PATH C (TESTS + DEBUG):
  tests/academic/ → imports UserContext dataclass for test setup
  api/routers/debug.py → may use prompt_builder
```

## Critical Finding: DEAD CODE PATH

**The main DM pipeline (PATH A) does NOT call `user_context_loader.py`.** It uses:
- `MemoryStore.get_or_create()` (JSON-backed follower memory) for raw data
- `PromptBuilder.build_user_context()` from `services/prompt_service.py` for formatting
- Manual `_lead_info` dict construction at `context.py:920-932`

This means:
- `format_user_context_for_prompt()` → **NOT used in production DMs**
- `format_conversation_history_for_prompt()` → **NOT used in production DMs**
- `build_user_context_prompt()` → **NOT used in production DMs**
- `_load_from_user_profile()` → **NOT used in production DMs** (UserProfile data is lost)
- `_load_from_lead_table()` → **NOT used in production DMs** (Lead CRM data is lost)

The production pipeline only gets data from FollowerMemory JSON files (PATH A). The richer context from UserProfile and Lead table is only available through PATH B, which isn't the main code path.

## Data Flow Detail

### Source 1: FollowerMemory (JSON) — `_load_from_follower_memory()`
```
data/followers/{creator_id}/{follower_id}.json
  → username, name, interests, products_discussed, objections_raised
  → purchase_intent_score, engagement_score, is_lead, is_customer
  → conversation_summary, total_messages, first_contact, last_contact
  → last_messages (last 20, as ConversationMessage list)
  → preferred_language (if available)
```
**On Railway:** JSON files don't persist between deploys. This source is often empty.

### Source 2: UserProfile (JSON) — `_load_from_user_profile()`
```
core/user_profiles.get_user_profile(follower_id, creator_id)
  → preferences.language, response_style, communication_tone
  → interests (weighted dict → sorted top 5)
  → objections (merged with existing)
```
**Issue:** This data is NOT loaded in the main pipeline (PATH A).

### Source 3: Lead table (PostgreSQL) — `_load_from_lead_table()`
```
SELECT * FROM leads WHERE creator_id = :creator_uuid AND platform_user_id = :follower_id
  → LeadInfo: id, status, score, purchase_intent, deal_value, tags, source, notes, email, phone
  → Override: full_name → context.name, username → context.username
  → Status mapping: "cliente" → is_customer=True, "caliente"/"colaborador" → is_lead=True
```
**Issue:** This rich CRM data is NOT loaded in the main pipeline (PATH A).

## Prompt Injection (when PATH B is used)

Via `format_user_context_for_prompt()`:
```
=== CONTEXTO DEL USUARIO ===
- Nombre: Maria
- Idioma preferido: ca
- Prefiere respuestas cortas y directas
- Intereses: nutricion, fitness, recetas
- Productos que le interesan: curso 8 semanas, pack proteinas
- Objeciones mencionadas: precio, tiempo
- Estado: LEAD CALIENTE, VIP, sensible al precio
- Usuario que vuelve despues de 14 dias
```

### Size estimate
~100–400 chars. Only non-default fields are included. Returns empty string `""` when no special context exists.

## Bugs Found

### Critical

| ID | Bug | Evidence |
|----|-----|----------|
| **B1** | **Module is dead code in the main DM pipeline** | `grep -rn "user_context_loader" core/dm/ services/` returns ZERO hits. The main pipeline at `context.py:934` uses `prompt_service.PromptBuilder.build_user_context()` instead, which has a simpler format (no CRM tags, no preferences, no VIP detection). UserProfile + Lead table data is NEVER injected into production DMs. |

### High

| ID | Bug | Evidence |
|----|-----|----------|
| **B2** | **Duplicate user context systems** | Two parallel systems do the same job: (A) `user_context_loader.py` (666 lines, 3 sources, rich formatting) and (B) `prompt_service.PromptBuilder.build_user_context()` (60 lines, 1 source, minimal formatting). PATH A is more complete but unused. PATH B is used but weaker — no CRM tags, no preference detection, no VIP/price-sensitive flags, no returning-user detection. |
| **B3** | **Lead table CRM data never reaches the LLM** | `_load_from_lead_table()` loads status, tags, deal_value, notes, email, phone — but since the module isn't called in PATH A, this data is lost. The `_lead_info` dict built at `context.py:920-932` pulls from FollowerMemory only, missing CRM-specific fields like tags ("vip"), deal_value, notes. |

### Medium

| ID | Bug | Evidence |
|----|-----|----------|
| **B4** | **All labels hardcoded in Spanish** | "CONTEXTO DEL USUARIO", "Nombre", "Intereses", "LEAD CALIENTE", "PRIMER MENSAJE - Dar bienvenida", "Usuario que vuelve despues de N dias". Italian creator Stefano's leads get Spanish metadata labels. |
| **B5** | **`is_price_sensitive()` checks Spanish "precio" only** | Line 193: `"precio" in self.objections_raised`. Won't detect IT "prezzo", CA "preu", EN "price", PT "preco". Confirmed by test: `objections_raised=['prezzo']` → `is_price_sensitive() = False`. |
| **B6** | **`get_display_name()` defaults to Spanish "amigo"** | Line 152: `return "amigo"`. For Italian creators should be "amico", for English "friend". Confirmed by test: `UserContext(creator_id='stefano').get_display_name() == 'amigo'`. |
| **B7** | **`is_returning_user` threshold hardcoded at 7 days** | Line 455: `days_since_last_contact >= 7`. No evidence this threshold is correct for DM engagement patterns. Some creators have daily engagement; 2-3 days absence may already signal "returning". Not configurable. |

### Low

| ID | Bug | Evidence |
|----|-----|----------|
| **B8** | **60s cache TTL** | Line 464: `BoundedTTLCache(max_size=200, ttl_seconds=60)`. If a lead sends rapid follow-ups, context may be stale for up to 60s. Moot since module is dead code (B1), but would matter if re-activated. |
| **B9** | **Sync file I/O in `_load_from_follower_memory()`** | Line 324: `with open(file_path, "r") as f: data = json.load(f)`. Synchronous read inside what should be an async pipeline. On Railway (no JSON files), this is a no-op. But locally with many leads, could block. |
| **B10** | **`_parse_datetime` date-only edge case** | `_parse_datetime('2024-01-15')` produces datetime without timezone (Python's fromisoformat ignores appended `+00:00` for date-only). `_calculate_days_since` compensates (line 254: `dt.replace(tzinfo=timezone.utc)`), so no practical impact. |
| **B11** | **`has_tag()` creates list comprehension every call** | Line 185: `tag.lower() in [t.lower() for t in self.lead_info.tags]`. Allocates a new list each time. Minor — tags list is small. |
| **B12** | **"medium" conversation length band too wide** | Lines 158-163: 4-10 messages = "medium". This is a very wide band. A 4-message conversation is qualitatively different from a 10-message one. Not configurable. |

## Functional Tests (10 groups, 21 assertions)

All PASS. Tests designed to verify bugs and edge cases:

```
TEST 1: is_price_sensitive ES-only hardcoded
  PASS: IT price objection ('prezzo') missed — confirms B5
  PASS: ES price objection ('precio') works

TEST 2: get_display_name fallback is ES-only
  PASS: fallback is Spanish 'amigo' — confirms B6

TEST 3: format_user_context labels are ES-only
  PASS: header is Spanish 'CONTEXTO DEL USUARIO' — confirms B4
  PASS: lead label is Spanish 'LEAD CALIENTE' — confirms B4

TEST 4: first-message instruction is ES-only
  PASS: first msg instruction 'Dar bienvenida' in Spanish — confirms B4

TEST 5: returning user after 7 days
  PASS: is_returning_user True at 10 days
  PASS: days_since_last_contact = 10
  PASS: is_returning_user False at 6 days — confirms threshold at 7

TEST 6: language only injected when != es
  PASS: ES language NOT in prompt (default suppressed)
  PASS: CA language IS in prompt ('Idioma preferido: ca')

TEST 7: empty context returns empty string
  PASS: short conversation with no special data returns ''

TEST 8: conversation_history truncates at 200 chars
  PASS: message truncated with '...'
  PASS: truncated content is 203 chars (200 + '...')

TEST 9: LeadInfo.from_db_row handles None fields
  PASS: None id → '', None status → 'nuevo', None tags → [], None deal_value → 0.0

TEST 10: load_user_context smoke test (no DB)
  PASS: returns UserContext for nonexistent creator
  PASS: is_first_message = True for new user
  PASS: display_name = 'amigo' for unknown user
```

## Paper Cross-References

### User Modeling in Dialogue (2024-2025)

1. **PersonaChat / PersonalDialog (Zhang et al., ACL 2018; Jandaghi et al., EMNLP 2024)**:
   - User persona attributes improve response quality by +15-20% human preference.
   - **Our gap:** The persona data EXISTS in user_context_loader but doesn't reach the LLM (B1). The main pipeline uses a minimal format without CRM tags, preferences, or computed flags.

2. **COMEDY (Kim et al., COLING 2025)**:
   - User-specific compressed memories outperform retrieval of raw facts for long conversations.
   - **Our system:** `conversation_summary` field exists but is only populated in FollowerMemory JSON (source 1). Rarely available on Railway where JSON doesn't persist.

3. **PUMA (Ahn et al., ACL Findings 2024)**:
   - Proposes 6-dimension user profiles for personalized dialogue: demographics, interests, habits, personality, social, goals.
   - **Our coverage:** name (demographics), interests, products_discussed (interests), engagement_score (social), purchase_intent (goals). Missing: habits, personality of the LEAD (not creator).

4. **UP5 (Li et al., ACL 2024)**:
   - User profiling should be dynamic (updated per conversation) not static.
   - **Our system:** Static per session (60s cache). FollowerMemory JSON may be stale on Railway.

5. **RecMind (Wang et al., NAACL 2024)**:
   - Hierarchical user representation: short-term (current session) → medium-term (recent history) → long-term (stable preferences).
   - **Our gap:** user_context_loader conflates all time horizons into one flat structure. `is_returning_user` is the only temporal signal. No distinction between "what they said today" vs "what they always prefer".

### Specific Recommendations from Literature

| Paper | Recommendation | Our Status |
|-------|---------------|------------|
| PersonaChat | Inject user persona into system prompt | BROKEN (B1 — module not called) |
| PUMA | 6-dimension profile | Partial (4/6 dimensions) |
| UP5 | Dynamic profile updates | Static (60s cache, JSON may be stale) |
| RecMind | Hierarchical time horizons | Flat (no temporal distinction) |
| COMEDY | Compressed user summaries | Field exists, rarely populated |

## Recommendations

### Priority 1: Fix the dead code problem (B1 + B2)

Two options:
- **Option A:** Replace PATH B's `PromptBuilder.build_user_context()` with a call to `user_context_loader.format_user_context_for_prompt()` inside `context.py`. This activates all 3 data sources.
- **Option B:** Merge the best parts of `user_context_loader` into the existing `context.py:920-932` flow. Add Lead table query + UserProfile loading + VIP/price-sensitive flags.

Option A is simpler; Option B avoids adding another module call.

### Priority 2: Internationalize labels (B4, B5, B6)

Create a small language map keyed by creator's primary language:
```python
_LABELS = {
    "es": {"header": "CONTEXTO DEL USUARIO", "name": "Nombre", ...},
    "it": {"header": "CONTESTO UTENTE", "name": "Nome", ...},
    "ca": {"header": "CONTEXT DE L'USUARI", "name": "Nom", ...},
}
```

### Priority 3: Make `is_returning_user` configurable (B7)

Replace hardcoded `>= 7` with `RETURNING_USER_DAYS = int(os.getenv("RETURNING_USER_DAYS", "7"))`.
