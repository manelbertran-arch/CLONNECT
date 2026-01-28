# Backend Implementation Plan: REFACTOR-PHASE1 Extract Routers from main.py

## Overview
Refactoring main.py from 7,198 lines to <500 lines by extracting endpoint groups into separate router modules. Following DDD principles and clean architecture.

## Architecture Context
- Layer: Presentation (FastAPI routers)
- Source: backend/api/main.py (7,198 lines)
- Target: Multiple router files in backend/api/routers/
- Pattern: Extract endpoints by URL prefix, maintain same signatures

## Progress Tracking
| Date | Router | Lines Removed | Commit | Endpoints |
|------|--------|---------------|--------|-----------|
| 2026-01-28 | auth.py | -177 | c4ac81e8 | 5 API key endpoints |
| 2026-01-28 | dm.py | -701 | 3a288d86 | 14 DM endpoints |
| 2026-01-28 | webhooks.py | -161 | c35e9da3 | 5 webhooks |
| 2026-01-28 | gdpr.py | -131 | 69ac07a8 | 6 GDPR endpoints |
| 2026-01-28 | telegram.py | -323 | 2c60a434 | 10 Telegram endpoints |
| 2026-01-28 | content.py | -561 | 60604e87 | 12 RAG content endpoints |
| 2026-01-28 | admin.py | -335 | b40ff05e | 10 Admin panel endpoints |
| 2026-01-28 | creator.py | -143 | c81a4691 | 6 Creator config endpoints |
| **Total** | | **-2,532** | | **68 endpoints** |

Current: 7,198 → 4,666 lines (35% reduction)

## Remaining Extractions
| Priority | Router | Endpoints Est. | Status |
|----------|--------|----------------|--------|
| 1 | telegram.py | 10 | DONE |
| 2 | content.py | 12 | DONE |
| 3 | admin.py (consolidate) | 10 | DONE |
| 4 | creator.py | 6 | DONE |

## Implementation Steps per Extraction

### Step N: Extract [router_name]
1. **Identify**: grep -n "/prefix/" backend/api/main.py
2. **Create file**: backend/api/routers/[name].py
3. **Move code**: Copy endpoints exactly (change @app to @router)
4. **Update main.py**: Add import and include_router()
5. **Fix imports**: Check other files that import from main.py
6. **Verify syntax**: python3 -m py_compile [files]
7. **Run tests**: pytest tests/ -v --tb=short
8. **Verify startup**: python -c "from api.main import app"
9. **Commit**: Follow format below

## Commit Message Format
```
refactor: extract [prefix] endpoints to routers/[name].py

- Move N endpoints from main.py to routers/[name].py
- No logic changes

Lines changed:
- main.py: XXXX -> YYYY (-ZZZ)
- routers/[name].py: 0 -> ZZZ
```

## Testing Checklist
- [ ] python3 -m py_compile passes for all modified files
- [ ] pytest tests/ -v passes
- [ ] Server starts: uvicorn api.main:app
- [ ] No import errors: python -c "from api.main import app"

## Notes
- English only for code and commits
- Baby steps: one router at a time
- NO logic changes during extraction
- Update this file after each extraction
