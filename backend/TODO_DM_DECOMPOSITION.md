# TODO: dm_agent_v2.py Decomposition

## Current State
- `core/dm_agent_v2.py` has ~2,756 lines
- Contains the DMAgentV2 class with the process_dm method and 6 internal phases
- This is the most critical module in the system (processes all DMs)

## Decomposition Plan (DO NOT execute without tests)
1. Write end-to-end tests that verify process_dm behavior
2. Extract phases into modules in core/dm/:
   - intent_router.py — _phase_detection
   - context_loader.py — _phase_memory_and_context
   - prompt_builder.py — _phase_prompt_construction (already partially in core/prompt_builder.py)
   - llm_caller.py — _phase_llm_generation
   - response_builder.py — _phase_postprocessing
   - orchestrator.py — process_dm thin wrapper
3. Verify that all tests still pass
4. Only then remove duplicate code

## Risk
High. This file is the heart of the system. Any error breaks ALL DMs.
