# Clonnect Refactoring Progress

> Last updated: 2026-01-28

## Overall Score

| Metric | Before | Current | Target | Status |
|--------|--------|---------|--------|--------|
| Audit Score | 42/80 | 42/80 | 62/80 | 🔴 |
| main.py lines | 7,198 | 7,198 | <500 | 🔴 |
| dm_agent.py lines | 7,463 | 7,463 | <800 | 🔴 |
| print() statements | 542 | 514 | 0 | 🟡 |
| bare except: | 20+ | 20+ | 0 | 🔴 |

## Phase 0: Quick Fixes

### Task 0.1: Replace print() with logging

| File | Prints Before | Prints After | Status |
|------|---------------|--------------|--------|
| screenshot_service.py | 15 | 0 | ✅ |
| llm.py | 8 | 0 | ✅ |
| dm_agent.py | ~200 | ~200 | 🔴 Pending |
| main.py | ~150 | ~150 | 🔴 Pending |
| onboarding.py | ~80 | ~80 | 🔴 Pending |
| admin.py | ~50 | ~50 | 🔴 Pending |
| Other files | ~39 | ~39 | 🔴 Pending |

**Commits completed**: 2
**Prints converted**: 28 / 542 (5.2%)

### Task 0.2: Fix bare except clauses

| File | Bare Excepts | Status |
|------|--------------|--------|
| Not started | - | 🔴 |

## Phase 1: Extract from main.py

| New Router | Endpoints | Lines | Status |
|------------|-----------|-------|--------|
| routers/auth.py | login, register, token | ~300 | 🔴 |
| routers/users.py | user CRUD | ~400 | 🔴 |
| routers/instagram.py | IG webhooks | ~500 | 🔴 |
| routers/campaigns.py | campaign mgmt | ~600 | 🔴 |
| routers/analytics.py | stats endpoints | ~400 | 🔴 |
| routers/billing.py | Stripe | ~300 | 🔴 |

## Phase 2: Extract from dm_agent.py

| New Service | Functions | Lines | Status |
|-------------|-----------|-------|--------|
| services/intent_classifier.py | classify_intent | ~500 | 🔴 |
| services/memory_manager.py | memory ops | ~800 | 🔴 |
| services/conversation_engine.py | state logic | ~600 | 🔴 |
| services/response_generator.py | LLM calls | ~400 | 🔴 |

## Phase 3: Audience Intelligence

| Endpoint | Description | Status |
|----------|-------------|--------|
| /api/audience/segments | Follower segments | 🔴 |
| /api/audience/insights | Analytics | 🔴 |
| /api/audience/export | Export data | 🔴 |

---

## Commands to Check Progress

```bash
# Count remaining prints
grep -rn "print(" backend/ --include="*.py" | wc -l

# Count bare excepts
grep -rn "except:" backend/ --include="*.py" | grep -v "except " | wc -l

# Check file sizes
wc -l backend/api/main.py backend/core/dm_agent.py

# Run tests
pytest tests/ -v --tb=short
```

## Legend

- 🔴 Not started / Critical
- 🟡 In progress / Warning
- 🟢 Completed / Good
- ✅ Done
