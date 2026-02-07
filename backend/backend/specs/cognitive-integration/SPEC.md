# SPEC: Cognitive Module Integration into dm_agent_v2

## Context

Auditoría completa del repositorio encontró 18 módulos cognitivos (5,800+ líneas) 
construidos y testeados pero NO conectados al DM agent de producción (`core/dm_agent_v2.py`).

## Problem

- 85% del código cognitivo está inactivo
- Módulos valiosos (sensitive_detector, output_validator, reflexion_engine) no se usan
- El bot responde sin validación de calidad, sin detección de contenido sensible
- No hay fact tracking ni state machine de conversación

## Solution

Integrar 15 módulos en 4 fases usando feature flags, siguiendo metodología specs-driven:
- Baby steps: 1 módulo = 1 commit
- TDD: Test primero
- Extract, don't rewrite: Importar módulos existentes

## Success Criteria

- [ ] 20 feature flags (5 existentes + 15 nuevos)
- [ ] 15 test files nuevos
- [ ] dm_agent_v2.py < 1,400 líneas
- [ ] Todos los tests pasan
- [ ] 30 módulos en pipeline (15 existentes + 15 nuevos)

## Implementation Phases

### P0: Security (Steps 1-3)
- sensitive_detector → Pre-pipeline
- output_validator → Post-LLM
- response_fixes → Post-LLM

### P1: Quality (Steps 4-7)
- question_remover → Post-LLM
- bot_question_analyzer → Phase 2
- query_expansion → Phase 2
- reflexion_engine → Post-LLM

### P2: Intelligence (Steps 8-12)
- lead_categorizer → Phase 2
- conversation_state → Phase 2
- conversation_memory → Phase 5
- chain_of_thought → Phase 4
- prompt_builder (advanced) → Phase 3

### P3: Personalization (Steps 13-15)
- dna_update_triggers → Phase 5
- relationship_type_detector → Phase 2
- vocabulary_extractor → Phase 5

## Risks

- Módulos con default=false requieren testing manual:
  - ENABLE_CONVERSATION_STATE (añade DB queries)
  - ENABLE_ADVANCED_PROMPTS (cambia system prompt)
  - ENABLE_RELATIONSHIP_DETECTION (procesamiento extra)
  - ENABLE_VOCABULARY_EXTRACTION (requiere 5+ mensajes)

## References

- Auditoría: Claude chat 2025-02-07
- Metodología: ai-specs/specs/base-standards.mdc
