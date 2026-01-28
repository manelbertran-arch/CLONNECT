# Backend Implementation Plan: REFACTOR-PHASE1 Extract Routers

## Overview

**Ticket**: REFACTOR-PHASE1
**Feature**: Extract endpoints from main.py to dedicated routers
**Architecture**: DDD Layered - Presentation Layer (FastAPI Routers)

This plan follows ai-specs methodology:
- TDD (tests before implementation)
- Baby steps (one change at a time)
- Documentation before commit
- 90% test coverage minimum

## Architecture Context

### Layer: Presentation
- **Components**: FastAPI APIRouter modules
- **Pattern**: Extract by URL prefix
- **Principle**: Pure code movement, NO logic changes

### Directory Structure
```
backend/api/
├── main.py              # FastAPI app setup only (<500 lines target)
├── routers/
│   ├── __init__.py
│   ├── auth.py          # /api-keys/*
│   ├── dm.py            # /dm/*
│   ├── webhooks.py      # Payment/calendar webhooks
│   ├── gdpr.py          # /gdpr/*
│   ├── telegram.py      # /telegram/*
│   ├── content.py       # /content/*
│   ├── admin.py         # /admin/*
│   ├── creator.py       # /creator/*
│   ├── bot.py           # /bot/*
│   ├── ai.py            # AI/Grok endpoints
│   ├── debug.py         # /debug/*
│   ├── health.py        # /health/*
│   └── static.py        # Static pages
├── models/              # Pydantic models (Phase 1.5)
├── utils/               # Helper functions (Phase 1.5)
└── tests/
    └── routers/
        └── test_*.py    # Router tests
```

## Implementation Steps

### Step 0: Create Feature Branch ✅
```bash
git checkout -b refactor/phase1-extract-routers
```

### Step 1: Write Router Import Tests (TDD)
```bash
# Create test file FIRST
touch backend/tests/routers/test_routers_import.py
# Write tests for all routers
# Run tests (should FAIL - routers don't exist yet or aren't tested)
pytest backend/tests/routers/ -v
```

### Step 2: Extract Router [name]
For each router:
1. Write endpoint tests FIRST
2. Create router file
3. Move endpoints (change @app to @router)
4. Update main.py imports
5. Run tests (should PASS)
6. Update documentation
7. Commit

### Step N+1: Update Documentation (BEFORE each commit)
- Update this plan with progress
- Update api-spec.yml if API changed
- Update PROGRESS.md

## Progress Tracking

| Step | Router | Lines | Endpoints | Tests | Commit | Status |
|------|--------|-------|-----------|-------|--------|--------|
| 1 | auth.py | -177 | 5 | ✅ | c4ac81e8 | ✅ complete |
| 2 | dm.py | -701 | 14 | ✅ | 3a288d86 | ✅ complete |
| 3 | webhooks.py | -161 | 5 | ✅ | c35e9da3 | ✅ complete |
| 4 | gdpr.py | -131 | 6 | ✅ | 69ac07a8 | ✅ complete |
| 5 | telegram.py | -323 | 10 | ✅ | 2c60a434 | ✅ complete |
| 6 | content.py | -561 | 12 | ✅ | 60604e87 | ✅ complete |
| 7 | admin.py | -335 | 10 | ✅ | b40ff05e | ✅ complete |
| 8 | creator.py | -143 | 6 | ✅ | c81a4691 | ✅ complete |
| 9 | bot.py | -63 | 3 | ✅ | 2d8433a7 | ✅ complete |
| 10 | ai.py | -655 | 3 | ✅ | 6e790d24 | ✅ complete |
| 11 | debug.py | -575 | 8 | ✅ | cfcc0665 | ✅ complete |
| 12 | health.py | -233 | 3 | ✅ | e464832f | ✅ complete |
| 13 | static.py | -240 | 5 | ✅ | e464832f | ✅ complete |
| - | duplicates | -375 | - | - | various | ✅ removed |

**Current**: 7,198 → 2,525 lines (65% reduction)
**Target**: <500 lines

## Testing Checklist

- [x] All routers import without errors
- [x] All routers have `routes` attribute
- [x] Main app imports correctly
- [x] Key endpoints registered in app
- [ ] 90% test coverage achieved

## Tests

### Current Test Coverage
- `tests/routers/test_routers_import.py` - 15 smoke tests

### Test Commands
```bash
# Run all router tests
pytest backend/tests/routers/ -v

# Check coverage
pytest backend/tests/ --cov=backend/api/routers --cov-report=term-missing
```

## Error Response Format

```json
{
  "detail": "Error message"
}
```

## Dependencies

- FastAPI
- SQLAlchemy
- Pydantic
- pytest

## Technical Debt

- Initial extractions done without TDD (tests added retroactively)
- Coverage below 90% target
- All future changes MUST follow TDD

## Implementation Verification

```bash
# Verify syntax
python3 -m py_compile backend/api/main.py backend/api/routers/*.py

# Verify imports
python -c "from api.main import app; print('✅ Import OK')"

# Run tests
pytest backend/tests/routers/ -v

# Check coverage
pytest --cov=backend/api/routers --cov-report=term-missing
```

## Notes

- English only for code and commits
- Baby steps: one router at a time
- NO logic changes during extraction
- Update this file BEFORE each commit
