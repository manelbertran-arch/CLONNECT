# Migration to dm_agent_v2.py

## Phase 4: Migration Strategy

### Objective
Establish dm_agent_v2.py as the preferred agent architecture while maintaining production stability.

### Analysis

**Files importing dm_agent.py (13 total):**
- `api/main.py` - DMResponderAgent
- `api/routers/dm.py` - DMResponderAgent
- `api/routers/debug.py` - get_dm_agent, DMResponderAgent
- `api/routers/messaging_webhooks.py` - get_dm_agent
- `api/routers/products.py` - invalidate_dm_agent_cache
- `api/startup.py` - _dm_agent_cache_timestamp, get_dm_agent
- `core/instagram_handler.py` - DMResponderAgent, DMResponse
- `core/telegram_adapter.py` - DMResponderAgent, DMResponse
- `core/whatsapp.py` - DMResponderAgent
- `scripts/process_nurturing.py` - DMResponderAgent

**Helper functions in dm_agent.py NOT in v2:**
- `get_dm_agent()` - factory function with caching
- `invalidate_dm_agent_cache()` - cache management
- `DMResponse` - response dataclass (different from v2)
- `_dm_agent_cache_timestamp` - internal state

### Approach: Gradual Migration (Baby Steps)

**Strategy: Coexistence**
1. Keep dm_agent.py as production agent (stability)
2. Use dm_agent_v2.py for new features and A/B testing
3. Migrate gradually after production validation

**Why NOT immediate migration:**
- 13 files depend on dm_agent.py
- Helper functions not yet in v2
- Risk of breaking production

### Current Status

| Component | Lines | Status |
|-----------|-------|--------|
| dm_agent.py | 7,472 | Production (stable) |
| dm_agent_v2.py | 422 | Ready for new features |
| services/ | 2,015 | Shared by both |

### Success Criteria
- [x] dm_agent_v2.py created (422 lines)
- [x] 7 migration compatibility tests passing
- [x] Both agents can coexist
- [ ] Gradual migration (future phase)

### Next Steps (Future)
1. Add helper functions to dm_agent_v2.py
2. Create compatibility layer
3. A/B test with real traffic
4. Full migration when validated
