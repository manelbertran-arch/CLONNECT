# Clonnect Refactoring Plan

## Current State (Audit Score: 42/80)

| Problem | Current | Target |
|---------|---------|--------|
| main.py | 7,198 lines | <500 lines |
| dm_agent.py | 7,463 lines | <800 lines |
| print() statements | 542 | 0 |
| bare except: | 20+ | 0 |

## Phase 0: Quick Fixes (Low Risk)

**Goal**: Improve code quality without changing logic.

### Task 0.1: Replace print() with logging
```bash
# Find all print statements
grep -rn "print(" backend/ --include="*.py" | head -20
```

Steps:
1. Add `import logging` at top of file
2. Add `logger = logging.getLogger(__name__)`
3. Replace `print(...)` with `logger.info(...)` or `logger.debug(...)`
4. Run tests after each file: `pytest tests/ -v`

### Task 0.2: Fix bare except clauses
```bash
# Find all bare except
grep -rn "except:" backend/ --include="*.py"
```

Replace `except:` with specific exceptions like `except Exception as e:`

## Phase 1: Extract from main.py

Target extractions from main.py (7,198 → <500 lines):

| New File | Functions to Extract |
|----------|---------------------|
| `routers/auth.py` | login, register, token refresh |
| `routers/users.py` | user CRUD operations |
| `routers/instagram.py` | IG connection, webhooks |
| `routers/campaigns.py` | campaign management |
| `routers/analytics.py` | stats, metrics endpoints |
| `routers/billing.py` | Stripe integration |

## Phase 2: Extract from dm_agent.py

Target extractions from dm_agent.py (7,463 → <800 lines):

| New File | Functions to Extract |
|----------|---------------------|
| `services/intent_classifier.py` | classify_intent, intent types |
| `services/memory_manager.py` | follower memory operations |
| `services/conversation_engine.py` | conversation state logic |
| `services/response_generator.py` | LLM response generation |
| `services/funnel_manager.py` | sales funnel progression |

## Phase 3: New Feature - Audience Intelligence

After refactoring, expose existing memory data:
- `/api/audience/segments` - Follower segments by intent
- `/api/audience/insights` - Aggregated audience analytics
- `/api/audience/export` - Export audience data

## Commands for Claude

When starting work, tell Claude:

```
Lee REFACTOR_PLAN.md y empieza con [Task X.X]
```

Example:
```
Lee REFACTOR_PLAN.md y empieza con Task 0.1: reemplazar print() por logging
```

## Progress Tracking

- [ ] Phase 0.1: Replace print() with logging
- [ ] Phase 0.2: Fix bare except clauses
- [ ] Phase 1: Extract routers from main.py
- [ ] Phase 2: Extract services from dm_agent.py
- [ ] Phase 3: Audience Intelligence API
