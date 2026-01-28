# Migration to dm_agent_v2.py

## Phase 4: Migration to dm_agent_v2.py

### Objective
Replace all imports of `dm_agent.py` (legacy, 7,472 lines) with `dm_agent_v2.py` (new, 422 lines).

### Approach
1. Identify all files importing dm_agent.py
2. Write tests to verify migration works (TDD)
3. Change imports using alias for compatibility
4. Verify all tests pass
5. Document changes
6. Commit

### Files to Modify
- Any file importing `from core.dm_agent import DMResponderAgent`

### Change Pattern
```python
# FROM (legacy):
from core.dm_agent import DMResponderAgent

# TO (new with alias for compatibility):
from core.dm_agent_v2 import DMResponderAgentV2 as DMResponderAgent
```

### Success Criteria
- [ ] All imports updated
- [ ] All tests pass
- [ ] No regressions
- [ ] Documentation updated
