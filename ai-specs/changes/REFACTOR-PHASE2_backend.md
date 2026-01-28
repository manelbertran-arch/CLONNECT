# Backend Implementation Plan: REFACTOR-PHASE2 Extract Services from dm_agent.py

## Overview

**Ticket**: REFACTOR-PHASE2
**Feature**: Extract services and business logic from dm_agent.py
**Architecture**: DDD Layered - Application Layer (Services) & Domain Layer

This plan follows ai-specs methodology:
- TDD (tests before implementation)
- Baby steps (one change at a time)
- Documentation before commit
- 90% test coverage minimum

## Current State

| File | Lines | Description |
|------|-------|-------------|
| dm_agent.py | 7,463 | Monolithic agent with RAG, LLM, Memory, DB |

## Target State

| File | Lines | Description |
|------|-------|-------------|
| dm_agent.py | <500 | Orchestration only |
| services/intent_service.py | ~150 | Intent classification |
| services/rag_service.py | ~800 | RAG logic |
| services/llm_service.py | ~600 | LLM integration |
| services/memory_service.py | ~500 | Conversation memory |
| services/lead_service.py | ~400 | Lead management |
| services/instagram_service.py | ~500 | Instagram API |

## Architecture Context

### Layer: Application (Services)
- **Components**: Business logic services
- **Pattern**: Service classes with single responsibility
- **Principle**: Dependency injection, testability

### Directory Structure
```
backend/
├── api/
│   └── main.py (446 lines) ✅
├── core/
│   └── dm_agent.py (<500 lines target)
├── services/
│   ├── __init__.py
│   ├── intent_service.py    # Intent classification ✅
│   ├── prompt_service.py    # Prompt building ✅
│   ├── memory_service.py    # Conversation memory ✅
│   ├── rag_service.py       # RAG/vector search ✅
│   ├── llm_service.py       # LLM calls (Groq/OpenAI/Anthropic) ✅
│   ├── lead_service.py      # Lead CRUD and scoring
│   └── instagram_service.py # Instagram API integration
└── tests/
    └── services/
        └── test_*.py        # Service tests
```

## Implementation Steps

### Step 0: Create Feature Branch ✅
```bash
git checkout -b refactor/phase2-extract-services
```

### Step 1: Analyze dm_agent.py
Identify code blocks for each service extraction.

### Step 2: Extract RAG Service (TDD)
1. Write tests FIRST for rag_service.py
2. Run tests (expect FAIL)
3. Create rag_service.py with RAG logic from dm_agent.py
4. Run tests (expect PASS)
5. Update dm_agent.py to use RAG service
6. Verify no regressions
7. Update documentation
8. Commit

### Step 3-6: Extract remaining services (TDD)
Same process for llm_service.py, memory_service.py, lead_service.py, instagram_service.py

### Step N+1: Update Documentation (BEFORE each commit)
- Update this plan with progress
- Update architecture docs if needed

## Progress Tracking

| Step | Service | Lines | Tests | Commit | Status |
|------|---------|-------|-------|--------|--------|
| 1 | Analysis | - | - | - | ✅ |
| 1.5 | intent_service.py | 184 | 8/8 | c2c9ddee | ✅ |
| 2 | prompt_service.py | 214 | 12/12 | ccea4e66 | ✅ |
| 3 | memory_service.py | 309 | 16/16 | 92dc7ee9 | ✅ |
| 4 | rag_service.py | 337 | 24/24 | 8ca9df10 | ✅ |
| 5 | llm_service.py | 414 | 22/22 | TDD | ✅ |
| 6 | lead_service.py | 263 | 20/20 | TDD | ✅ |
| 7 | instagram_service.py | 178 | 20/20 | TDD | ✅ |

**Total Services**: 7/7 complete
**Total Lines**: ~1,899
**Total Tests**: 122/122 passing

**Current**: dm_agent.py 7,489 lines
**Target**: dm_agent.py <500 lines

## Testing Checklist

- [x] All services have unit tests (122 tests)
- [x] All services can be imported
- [ ] Integration tests for agent
- [x] No regressions in existing functionality
- [x] 90% test coverage on new services

## Dependencies

- FastAPI
- SQLAlchemy
- Groq / OpenAI / Anthropic SDKs
- Sentence Transformers (RAG)
- pytest

## Notes

- Phase 1 completed: main.py 7,198 → 446 lines (94%)
- Same TDD methodology for Phase 2
- Each service extraction is independent
- Maintain backward compatibility

## Implementation Verification

```bash
# Verify syntax
python3 -m py_compile core/dm_agent.py services/*.py

# Verify imports
python -c "from core.dm_agent import DMResponderAgent; print('✅ OK')"

# Run tests
pytest tests/services/ -v --cov=services --cov-report=term-missing
```
