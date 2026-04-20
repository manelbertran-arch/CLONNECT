# S5 A/B Scorer Audit — Clasificación OUTPUT vs METADATA

**Fecha:** 2026-04-20  
**Propósito:** Verificar que las dimensiones del CCEE v5 no leen `typed_metadata` / `emit_metric` / campos ARC5 que solo existen en post-Sprint 5, lo que contaminaría el delta agregado.

---

## Metodología

Inspección manual de cada scorer en:
- `core/evaluation/ccee_scorer.py`
- `core/evaluation/multi_turn_scorer.py`
- `core/evaluation/m_prometheus_judge.py`
- `scripts/run_ccee.py`

Búsquedas ejecutadas:
```bash
grep -rn "typed_metadata|emit_metric|arc5_|meta\[" core/evaluation/
# → 0 resultados
```

---

## Clasificación por dimensión

| Dimensión | Tipo | Inputs reales | Evidencia (archivo:línea) | Válida pre-S5 |
|-----------|------|---------------|--------------------------|----------------|
| **S1 Style Fidelity** | OUTPUT_BASED | `bot_responses[]`, `style_profile` (DB) | `ccee_scorer.py:198` | ✅ |
| **S2 Response Quality** | OUTPUT_BASED | `bot_responses[]`, `test_cases.user_input`, `test_cases.ground_truth` | `ccee_scorer.py:468` | ✅ |
| **S3 Strategic Alignment** | OUTPUT_BASED | `bot_responses[]`, `strategy_map` (DB) | `ccee_scorer.py:595` | ✅ |
| **S4 Adaptation** | OUTPUT_BASED | `bot_responses[]`, `test_cases.trust_score` (desde DB histórico, no pipeline) | `ccee_scorer.py:692` | ✅ |
| **H1 Turing Test** | OUTPUT_BASED | `bot_response` (texto), `ground_truth` (texto), `user_message` (texto) | `m_prometheus_judge.py:418` | ✅ |
| **H2 Style Fingerprint** | OUTPUT_BASED | `bot_responses[]`, `style_profile` (DB) | `ccee_scorer.py:1215` | ✅ |
| **B1 OCEAN Alignment** | OUTPUT_BASED | `bot_responses[]` (análisis léxico), `style_profile` (DB) | `ccee_scorer.py:1067` | ✅ |
| **B2/B5 LLM Judge** | OUTPUT_BASED | `bot_response` (texto), `test_case` data | `m_prometheus_judge.py:evaluate_all_params` | ✅ |
| **B4 Knowledge Boundaries** | OUTPUT_BASED | `bot_responses[]` (detección hallucinations) | `ccee_scorer.py:1134` | ✅ |
| **J3 Prompt-to-Line** | OUTPUT_BASED | `conversation.history` (bot turns generados), `doc_d` (DB) | `multi_turn_scorer.py:133` | ✅ |
| **J4 Line-to-Line** | OUTPUT_BASED | `conversation.history` (bot turns) | `multi_turn_scorer.py:270` | ✅ |
| **J5 Belief Drift** | OUTPUT_BASED | `conversation.history`, `belief_shift_turn` (generado por MT generator) | `multi_turn_scorer.py:397` | ✅ |
| **J6 QA Consistency** | OUTPUT_BASED | `conversation.history`, probe turns (inyectados por MT generator), `doc_d` (DB) | `multi_turn_scorer.py:1135` | ✅ |
| **K1 Context Retention** | OUTPUT_BASED | `conversation.history` (keyword overlap early vs late bot turns) | `multi_turn_scorer.py:591` | ✅ |
| **K2 Style Retention** | OUTPUT_BASED | `conversation.history`, `style_profile` (DB) | `multi_turn_scorer.py:801` | ✅ |
| **G5 Persona Robustness** | OUTPUT_BASED | `conversation.history`, `is_adversarial` metadata (inyectado por MT generator, no bot pipeline) | `multi_turn_scorer.py:985` | ✅ |
| **L1 Persona Tone** | OUTPUT_BASED | `conversation.history`, `doc_d` (DB), `exemplar_generator` | `multi_turn_scorer.py:1522` | ✅ |
| **L2 Logical Reasoning** | OUTPUT_BASED | `conversation.history` | `multi_turn_scorer.py:1654` | ✅ |
| **L3 Action Justification** | OUTPUT_BASED | `conversation.history` | `multi_turn_scorer.py:1794` | ✅ |

---

## Veredicto: NINGUNA dimensión es METADATA_BASED

Resultado de la búsqueda exhaustiva:
```
grep -rn "typed_metadata|emit_metric|arc5_|\.metadata\b" core/evaluation/
→ 0 resultados relevantes
```

Los scorers leen exclusivamente:
1. **Texto de respuestas del bot** — generado por el bot pipeline en cada run
2. **Datos del test case** — `user_input`, `ground_truth`, `trust_score` — vienen de la DB histórica de DMs reales, NO del pipeline
3. **Perfiles del creador** — `style_profile`, `strategy_map`, `adaptation_profile`, `compressed_doc_d` — de la DB, consistentes entre pre y post Sprint 5
4. **Metadata de conversaciones MT** — `is_adversarial`, `is_qa_probe`, `belief_shift_turn` — inyectados por el MT generator (instrumento, no sujeto)

---

## Dimensiones a EXCLUIR del análisis agregado

**Ninguna por razón de contaminación de metadata.** Todas son válidas para la comparación pre vs post Sprint 5.

---

## Confounds conocidos (NO contaminación, SÍ diferencias legítimas)

Estas diferencias son reales y forman parte del "impacto Sprint 5" medido:

| Confound | Pre-Sprint 5 | Post-Sprint 5 | Dimensiones afectadas |
|----------|-------------|----------------|----------------------|
| **Doc D length** | 1576 chars (compressed) | 2557 chars (full) | S1, J3, G5, L1 |
| **Memory system** | `ENABLE_MEMORY_ENGINE=true` (old engine) | ARC2 Lead Memories (nuevo) | K1, J3, J6 |
| **Budget Orchestrator** | NO (ARC1 no existe) | `ENABLE_BUDGET_ORCHESTRATOR=true` | S1, S4 (indirrecto) |
| **Context compactor** | NO (ARC3 no existe) | `ENABLE_COMPACTOR_SHADOW=true` | K1, K2 |

Estos confounds son el Sprint 5 — son exactamente lo que se mide.

---

## Recálculo composite fair

Dado que **ninguna dimensión está contaminada**, el composite naive = composite fair.

El informe `s5_aggregate_ab_results.md` reportará un único composite (no necesita dos versiones).

Sin embargo, para máxima transparencia se reportarán los confounds por dimensión para que Manel pueda interpretar qué parte del delta es atribuible a qué componente de Sprint 5.

---

## Verificación empírica pendiente

Cuando el JSON pre-Sprint 5 esté disponible, verificar:
- [ ] Ninguna dimensión da exactamente 0.0 o null (excl. B1 OCEAN que puede ser N/A por diseño)
- [ ] K1 > 30 (si memory engine funciona, debe retener algo)
- [ ] S1 > 50 (bot debe reflejar estilo aunque con doc_d más corto)
- [ ] H1 > 40 (bot debe ser indistinguible en algunos casos incluso pre-Sprint 5)
