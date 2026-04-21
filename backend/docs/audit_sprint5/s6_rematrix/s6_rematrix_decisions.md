# S6 Re-Matriz — Fase 8: Agregación y Decisiones

**Fecha:** 2026-04-21 | **Auditor:** Opus 4.6 | **Branch:** `audit/s6-rematrix`

---

## 1. Resumen Ejecutivo

**Veredicto: Sprint 5 resolvió la mayoría de interacciones W8 por separación (ARC1) y desactivación, pero NO atacó el problema estructural más grave — 4 mecanismos independientes de sell/don't-sell sin arbitraje. Esto genera 3 Tipo 1 activos (R.4, R.5, C.8) que degradan consistencia comercial.**

Sprint 5 mejoró el pipeline significativamente (Δv5 = +4.3, σ×3 reducción). ARC1 BudgetOrchestrator separó secciones que antes competían, ARC2 consolidó memoria, y las desactivaciones (ECHO, Gold Examples, Lead Categorizer, SBS/PPA) eliminaron regresiones medidas. De los 10 bugs de interacción W8, 1 se resolvió (W8 1.1 downgraded) y 5 quedaron DORMANT por desactivación.

**Pero 4 bugs W8 persisten activos** (W8 2.10, 3.1, 3.4, 3.5) y **10 hallazgos nuevos** fueron detectados en S6 — incluyendo los 3 Tipo 1 de sell/don't-sell, el bug de contabilidad del BudgetOrchestrator, y la clasificación dual de intent.

### Top 3 hallazgos críticos post-Sprint 5

1. **Sell/Don't-Sell Fragmentation** — 4 mecanismos (DNA, Conv State, Frustration, Scorer) deciden independientemente si vender. 3 combinaciones producen instrucciones directamente contradictorias (R.4, R.5, C.8). El modelo resuelve ad-hoc por atención posicional. **Impacto: inconsistencia comercial, riesgo de alucinación de productos.**

2. **ARC1 Budget Accounting Bug** — Recalling block carga 400 tokens al presupuesto pero pasa 500-1000 tokens reales. El prompt es 5-15% sobre presupuesto sistemáticamente. Toda la competición entre secciones HIGH está distorsionada.

3. **Dual Intent Classification** — `classify_intent_simple()` (detection) y `agent.intent_classifier.classify()` (context) producen clasificaciones divergentes sin reconciliación. Context Detection's `interest_level` usa la simple; RAG/Calibration usan la completa.

### Recomendación estratégica

**Resolver los 3 bloqueantes rápidos (sell arbitration, T5.1 ordering, P2 payment link) ANTES de iniciar fine-tuning.** Estimación: 5-7 días. Justificación completa en Sección 10.

### Métrica de éxito

Con los 3 fixes aplicados, el próximo CCEE debería mostrar: (a) SBS/PPA con Δ positivo (tras fix T5.1), (b) cero alucinaciones de producto en escenarios FAMILIA/PERSONAL, (c) consistencia sell/don't-sell en edge cases.

---

## 2. Bloqueantes Activos Post-Sprint 5

### BLQ-1: Sell/Don't-Sell Fragmentation (3× Tipo 1)

| ID | Sistemas | Contradicción | Evidencia |
|----|---------|---------------|-----------|
| R.4 | DNA × Conv State | "NUNCA vender" vs "Presenta producto" | dm_agent_context_integration.py:173 vs conversation_state.py:108 |
| R.5 | Conv State × Frustration | "Presenta producto" vs "No vendas ahora" | conversation_state.py:108 vs context.py:1375 |
| C.8 | Conv State × Scorer | "Presenta producto" pero products removed del prompt | conversation_state.py:108 vs relationship_scorer.py:135 |

**Por qué Sprint 5 NO lo resolvió:** Sprint 5 se centró en separación por ARC1 (secciones), ARC2 (memoria), y desactivaciones. Los 4 mecanismos de sell están DENTRO del recalling block — ARC1 no arbitra intra-sección. Conv State no lee frustration ni DNA; Scorer no lee Conv State.

**Impacto CCEE estimado:** Δ +1.0-2.0 en S4 Adaptation y H Turing (consistencia comercial es un factor clave en ambas métricas).

**Propuesta de fix:** Función `resolve_sell_intent()` que recibe los 4 signals y produce UNA directiva. Prioridad: Sensitive > Frustration ≥ DNA > Scorer > Conv State. Inyectar solo la directiva ganadora.
**Esfuerzo:** 2-3 días (nueva función + integración en context.py).

### BLQ-2: ARC1 Budget Accounting Bug

**Mecanismo:** `effective_tok = min(actual_tokens, cap_tokens)` (orchestrator.py:93). Para non-CRITICAL sin compressor, content pasa sin truncar pero budget carga solo el cap. Recalling cap=400, contenido real 500-1000.

**Por qué Sprint 5 NO lo resolvió:** ARC1 fue diseñado con caps conservadores. El bug no fue detectado porque el prompt no falla — simplemente está sobre-presupuesto silenciosamente.

**Impacto CCEE estimado:** Indirecto. El over-budget desplaza secciones legítimas y reduce headroom para RAG. Δ estimado del fix: +0.3-0.5 (mejor selección de secciones).

**Propuesta:** Opción A: truncar recalling a cap (pierde contenido). Opción B: aumentar cap a 800 y reducir presupuesto total. Opción C: añadir sub-arbitraje intra-recalling. **DECISIÓN HUMANA REQUERIDA** — las 3 opciones tienen trade-offs distintos. Opción C es la más correcta pero más costosa (3-5 días). Opción B es el quick-win (0.5 días).

### BLQ-3: Dual Intent Classification

**Mecanismo:** orchestration.py:61 (`classify_intent_simple`) y context.py:797 (`agent.intent_classifier.classify`) producen resultados independientes.

**Por qué Sprint 5 NO lo resolvió:** La dualidad existía pre-Sprint 5 y no fue identificada.

**Impacto CCEE estimado:** Bajo directo, pero amplifica cascadas G.1 (Intent→Calibration) y G.2 (Intent→RAG). Δ estimado: +0.2-0.4.

**Propuesta:** Backpatch el resultado del clasificador completo a `ctx.interest_level` después de context.py:797. 0.5-1 día.

### BLQ-4: Memory × Scorer XML Parsing Frágil (X.2)

**Mecanismo:** context.py:1169-1185 regex-parsea `memory_context` (formato ARC2 XML) para extraer facts. No strip XML tags.

**Por qué Sprint 5 NO lo resolvió:** ARC2 cambió el formato a XML pero el scorer no se actualizó.

**Impacto CCEE estimado:** Bomba de tiempo. Si ARC2 format cambia, scorer rompe silenciosamente → relationship scoring degrada → product suppression falla.

**Propuesta:** Reemplazar regex con parser XML-aware. 0.5 días.

---

## 3. Bugs W8 con Estado Post-Sprint 5

| # W8 | Bug | Estado S6 | Propuesta si PERSISTE |
|------|-----|-----------|-----------------------|
| 1.1 | Doc D × DNA competencia | **RESUELTO** — downgraded a Tipo 3 (ARC1 + has_doc_d) | — |
| 2.1 | Memory × Episodic redundancia | **DORMANT** (#7 OFF) | Si re-enable: cross-source dedup obligatorio |
| 2.2 | Episodic duplicates | **DORMANT** (#7 OFF) | Mismo requisito |
| 2.6 | Calibration × StyleRetriever dual injection | **DORMANT** (#28 OFF) | Guard exclusión mutua antes de re-enable |
| 2.10 | Memory × Commitment dedup | **PERSISTE** | ARC2 nightly auto-mark fulfilled (Fase 6 propuesta) |
| 3.1 | Doc D × Calibration coherence | **PERSISTE** | Validation pipeline post-mining. Bajo coste. |
| 3.4 | Doc D × Length Controller | **PERSISTE** | LC siempre gana (postproc). Aceptable por diseño. |
| 3.5 | Calibration × Anti-Echo pool vacío | **PERSISTE** | Fallback pool default si creator sin calibration |
| 3.11 | Style Loader × PersonaCompiler | **DORMANT** (#27 OFF) | Snapshot + rollback automático antes de re-enable |
| 4.1 | Triple memory injection | **DORMANT** (#7 OFF) | Cross-source dedup en `_build_recalling_block()` |
| P1 | Debounce race condition | **PERSISTE** | Fix en copilot/messaging.py race. 1 día. |
| P2 | Payment link post-LC | **PERSISTE** (= T5.2) | Mover 7d antes de 7c. 0.5 días. |
| P3 | Intent override media_share | **PERSISTE** | Propagar override en IntentService. 0.5 días. |

**Score:** 1 RESUELTO, 5 DORMANT, 7 PERSISTEN (4 bugs interacción + 3 producción).

---

## 4. Redundancias y Duplicaciones

**Activas:**

| ID | Par | Tipo | Propuesta |
|----|-----|------|-----------|
| R.1 | Memory × DNA (interests/topics) | Tipo 2 parcial, LOW | Dedup en `_build_recalling_block()` — eliminar interests de memory si ya en DNA. 0.5 días. |
| R.3 | Memory × Commitment | Tipo 2, LOW (W8 2.10) | ARC2 nightly auto-fulfillment de commitments. 1 día. |
| M.26 | Guardrails × Output Validator (URLs) | Tipo 2 parcial, LOW | Aceptable — Validator es narrow (links), Guardrails es broad (safety). No eliminar ninguno. |

**Latentes (DORMANT, condición de resurgimiento):**

| ID | Par | Condición de activación | Riesgo |
|----|-----|------------------------|--------|
| S.5 | Calibration × StyleRetriever | `ENABLE_GOLD_EXAMPLES=true` | W8 2.6 dual injection resurge. Guard obligatorio. |
| R.16 | Memory × Episodic | `ENABLE_EPISODIC_MEMORY=true` | W8 4.1 triple injection. Cross-source dedup obligatorio. |

**Redundancia funcional confirmada:** Lead Categorizer vs Conv State — ambos clasifican fase del lead. MANTENER OFF permanente (Fase 7).

---

## 5. Acoplamientos Implícitos Peligrosos (Tipo 3 MEDIUM)

| # | Par | Riesgo | Propuesta de explicitar | Esfuerzo |
|---|-----|--------|------------------------|----------|
| X.2 | Memory × Scorer | Scorer regex-parsea XML de ARC2 | Parser XML-aware en context.py:1169 | 0.5d |
| S.2 | Doc D × Calibration | Coherencia no validada entre CRITICAL sections | Validation CI check post-mining | 1d |
| G.1 | Intent → Calibration | Wrong intent → wrong few-shots | Backpatch simple→full intent | 0.5d |
| G.2 | Intent → RAG | Wrong intent → wrong product retrieval | Misma fix que G.1 | (incluido) |
| G.6 | Calibration × Anti-Echo | Empty pool = echo pass-through | Default fallback pool universal | 0.5d |
| C.4 | Context × Intent dual | 2 clasificadores sin reconciliación | Backpatch resultado completo a ctx | (incluido en G.1) |

**Prioridad:** X.2 (bomba de tiempo) > G.1+G.2+C.4 (cascade fix, un solo cambio) > G.6 > S.2 (CI tooling).

---

## 6. Candidatos de Revalidación Tras Fix

### SBS/PPA — Prioridad ALTA

| Campo | Valor |
|-------|-------|
| Estado actual | OFF, Δ neutro (medición limitada) |
| Causa OFF | T5.1: regeneración bypasea M3+M4+M5 (Δ combinado -11.50) |
| Fix requerido | Reordenar steps en postprocessing.py: SBS antes de anti-echo chain |
| Esfuerzo fix | 0.5-1 día |
| CCEE post-fix | 50×3+MT obligatorio |
| Δ esperado | Positivo (alignment scoring como quality gate) |

### Gold Examples — Prioridad MEDIA

| Campo | Valor |
|-------|-------|
| Estado actual | OFF, Δ -0.70 (bugs P1 ya corregidos) |
| Causa OFF | Bugs P1 (corregidos) + dual injection sin guard (W8 2.6) |
| Fix requerido | Guard exclusión mutua vs Creator Style Loader |
| Esfuerzo fix | 1-2 días |
| CCEE post-fix | 50×3+MT obligatorio |
| Δ esperado | Incierto — depende de calidad guard |

**Orden:** SBS primero (fix más claro, potencial más alto), Gold Examples segundo.

---

## 7. Arquitectura Post-FT Pipeline Identitario

**Pre-FT (actual, correcto):** Doc D (raw) + Calibration few-shots → ambos CRITICAL → modelo recibe identidad in-context.

**Post-FT (plan):** Modelo internaliza identidad → Doc D se puede comprimir (ARC3 revalidar) → ECHO reactivable (per-lead adaptation sin competir con identidad) → PersonaCompiler reactivable (LLM-rewrite de Doc D seguro si modelo ya conoce la voz).

**FeedbackCapture:** Mantener ON como data accumulator. Añadir TTL 90d para preference pairs. Post-FT: descartar datos base-model, usar solo post-FT para PersonaCompiler.

**Pipeline chain futura:** FeedbackCapture → PersonaCompiler → personality_docs → Creator Style Loader → style section. StyleRetriever como canal paralelo con guard de exclusión mutua vs Calibration. **No activar ningún eslabón adicional pre-FT.**

---

## 8. Matriz Visual Consolidada

Sistemas activos con interacciones. Marcadores: █ Tipo 1, ▓ Tipo 2, ░ Tipo 3, · Tipo 4, ← Tipo 5, + Tipo 6. Mayúscula=MEDIUM+, minúscula=LOW. D=DORMANT.

```
        1   2   4   6   8   9  10  11  12  13  14  15  17  19  20  22  23  25  29  30
  1  Doc D  ░   █   █   ░   ░   ░   ░   ░   .   .   .   ░   .   .   .   .   ░   .   .
  2  Norm   .   .   .   ░   .   ░   +   +   ░   .   ░   ←   .   .   .   .   ░   .   .
  4  RAG        .   +   .   .   +   .   .   .   .   .   .   .   .   ░   .   .   .   .
  6  Mem            .   ▓   +   .   .   .   .   .   .   .   +   +   .   ░   .   .   ▓
  8  DNA                .   ░   .   .   .   .   .   .   .   ░   +   .   ░   .   .   +
  9  CnvSt                  .   .   .   .   .   .   .   .   █   +   .   █   .   .   ░
 10  Calib                      .   ░   ░   .   .   .   .   .   .   ░   .   ░   .   .
 11  QR                             .   +   +   .   .   +   .   .   .   .   .   ←   .
 12  AEcho                              .   +   .   .   +   .   .   .   .   .   ░   .
 13  Guard                                  .   +   +   ░   .   .   .   .   .   .   .
 14  OVal                                       .   +   .   .   .   .   .   .   .   .
 15  Fixes                                          .   .   .   .   .   .   .   .   .
 17  LC                                                 .   .   .   .   .   .   .   ←
 19  Frust                                                  .   +   ░   ░   .   .   ░
 20  CtxDt                                                      .   ░   +   .   .   +
 22  Intnt                                                          .   .   .   .   .
 23  Scorer                                                             .   .   .   .
 25  SLoad                                                                  .   .   .
 29  Conf                                                                       .   .
 30  Commit                                                                         .
```

**Sistemas DORMANT no mostrados:** #7 Episodic, #27 PersonaCompiler, #28 StyleRetriever (9 pares dormant).
**Sistemas aislados:** #21 Sensitive (zero interactions), #16 Splitter (solo +6 con LC).

**Hotspots:** Conv State (#9) tiene 2 Tipo 1 activos (con DNA y Frustration) + 1 Tipo 1 (con Scorer). Es el nodo más peligroso de la matriz.

---

## 9. Comparación Completa con W8

| Métrica | Valor |
|---------|-------|
| Hallazgos W8 Fase C totales | **13** (10 interacción + 3 producción) |
| RESUELTOS por Sprint 5 | **1** (W8 1.1 downgraded por ARC1 + has_doc_d) |
| DORMANT por desactivación | **5** (W8 2.1, 2.2, 2.6, 3.11, 4.1) |
| SIGUEN VIVOS | **7** (W8 2.10, 3.1, 3.4, 3.5, P1, P2, P3) |
| NUEVOS en S6 | **10** |
| **Delta neto** | **+3** (de 13 a 17 activos — pero 5 de los nuevos son SUB-MEDIUM) |

**Hallazgos nuevos S6 (10):**

| ID | Hallazgo | Severidad |
|----|---------|-----------|
| R.4 | DNA × Conv State sell contradiction | Tipo 1 BLOQUEANTE |
| R.5 | Conv State × Frustration sell contradiction | Tipo 1 BLOQUEANTE |
| C.8 | Conv State × Scorer sell contradiction | Tipo 1 MEDIUM |
| — | ARC1 Budget accounting bug | Estructural MEDIUM |
| — | Dual Intent Classification | Estructural MEDIUM |
| T5.1 | SBS bypass M3+M4+M5 | Tipo 5 MEDIUM |
| X.2 | Memory × Scorer XML fragile | Tipo 3 MEDIUM |
| G.1 | Intent → Calibration cascade | Tipo 3 MEDIUM |
| G.2 | Intent → RAG cascade | Tipo 3 MEDIUM |
| R.1 | Memory × DNA partial redundancy | Tipo 2 LOW |

**Interpretación:** Sprint 5 resolvió los conflictos de ESPACIO (budget competition, separación de secciones) pero no los de SEMÁNTICA (señales contradictorias dentro del mismo bloque). Los nuevos hallazgos son mayoritariamente semánticos — el tipo de bug que ARC1 no puede resolver porque opera a nivel de tokens, no de significado.

---

## 10. Decisión Estratégica: Sprint 6 FT Timing

**Pregunta:** ¿Iniciar fine-tuning ANTES o DESPUÉS de resolver los bloqueantes activos?

### Opción A: FT inmediato (paralelo a fixes)

**A favor:**
- FT tarda semanas. Empezar ya maximiza paralelismo.
- Δv5 = +4.3 demuestra que el pipeline es funcional. Los bloqueantes degradan edge cases, no el caso general.
- ECHO y PersonaCompiler necesitan FT para reactivarse — cuanto antes FT, antes se desbloquean.

**En contra (evidencia de fases previas):**
- **Training data contaminada.** Si FT entrena sobre output del pipeline actual, aprende las inconsistencias de sell/don't-sell. Un modelo fine-tuned que a veces vende a FAMILIA y a veces no — porque los training examples tienen ambas conductas — es PEOR que el base model (que al menos sigue las instrucciones de mayor atención posicional).
- **ARC1 budget distorsionado.** Los prompts de training tendrían 5-15% más tokens de los que el budget reporta. Si post-FT se corrige el budget (truncando recalling), el modelo fine-tuned vería prompts diferentes a los de entrenamiento. Distributional shift.
- **T5.1 enmascaró SBS.** Sin fix, FT no puede evaluar si SBS mejora post-FT. La revalidación quedaría bloqueada hasta post-FT + fix, duplicando trabajo.

### Opción B: Fixes primero, FT después

**A favor:**
- **Calidad de training data.** Los 3 fixes rápidos (sell arbitration, T5.1, P2) eliminan las inconsistencias más dañinas. FT sobre pipeline limpio produce un modelo más consistente.
- **Evidencia empírica.** Sprint 2 y Sprint 5 demostraron que comprimir/distorsionar señales de identidad regresa (S1 -10.9, H -10.0). Training data con contradicciones de sell es una forma diferente del mismo problema: el modelo aprende señales inconsistentes que no puede resolver.
- **Coste bajo.** Los 3 fixes rápidos suman 4-5 días de ingeniería. FT tarda 2-4 semanas. El delay es <15% del timeline total.
- **SBS/PPA medible.** Con T5.1 corregido, SBS puede medirse con CCEE ANTES de FT. Si SBS es positivo, el training data incluirá respuestas SBS-refinadas — mejor base para FT.

**En contra:**
- Delay de 1 semana antes de empezar FT.
- Los fixes podrían introducir nuevas regresiones que requieren otro CCEE cycle.

### Recomendación: OPCIÓN B — Fixes primero

**Con convicción: 85/15 a favor de fixes primero.**

La evidencia es clara: Sprint 2 y Sprint 5 demostraron que identity signal quality es el factor más sensible del pipeline. Training data contaminada con contradicciones sell/don't-sell es exactamente el tipo de signal pollution que produce regresiones post-FT difíciles de diagnosticar. Un modelo fine-tuned con comportamiento comercial inconsistente es peor que el base model con los mismos bloqueantes — porque el base model al menos es predecible (sigue atención posicional), mientras el fine-tuned model tiene la inconsistencia INTERNALIZED.

**El coste es mínimo:** 5-7 días para los 3 fixes rápidos + 1 CCEE verification. Contra 2-4 semanas de FT. El delay es <20% del timeline y la calidad de training data mejora significativamente.

**Riesgos de Opción B:**
- Los fixes podrían regresionarse. Mitigación: CCEE 50×3+MT post-fix.
- ARC1 budget fix puede ser complejo. Mitigación: usar Opción B (aumentar cap) como quick-win, dejar Opción C (sub-arbitraje) para post-FT.

**Riesgos de Opción A (la rechazada):**
- Training data contaminada → modelo inconsistente → difícil de diagnosticar post-FT.
- Posible necesidad de re-fine-tuning si fixes cambian significativamente el prompt structure.

---

## 11. Roadmap Accionable Post-Matriz — Top 10

| # | Acción | Esfuerzo | Δ CCEE est. | Dependencias | Worker |
|---|--------|----------|-------------|-------------|--------|
| 1 | **Sell/Don't-Sell arbitration** — función `resolve_sell_intent()` con prioridad Sensitive>Frust≥DNA>Scorer>ConvState | 2-3d | +1.0-2.0 | Ninguna | Opus 4.6 extended thinking (trade-offs de prioridad) |
| 2 | **Fix T5.1 SBS ordering** — mover SBS antes de anti-echo chain en postprocessing.py | 0.5d | Habilita revalidación SBS | Ninguna | Sonnet 4.6 (mecánico) |
| 3 | **Fix P2 payment link ordering** — mover 7d antes de 7c | 0.5d | No mueve CCEE | Ninguna | Sonnet 4.6 (mecánico) |
| 4 | **CCEE verification post-fixes** — 50×3+MT con #1, #2, #3 aplicados | 0.5d setup | Baseline para FT | #1, #2, #3 completados | Sonnet 4.6 (ejecución) |
| 5 | **Revalidar SBS/PPA** — activar tras fix T5.1, CCEE 50×3+MT | 0.5d + CCEE | +0.5-1.5 esperado | #2 + tests SBS fixed | Sonnet 4.6 (ejecución) |
| 6 | **Backpatch Intent dual** — reconciliar classify_intent_simple con full classifier | 0.5d | +0.2-0.4 | Ninguna | Sonnet 4.6 (mecánico) |
| 7 | **Fix X.2 Scorer XML parsing** — parser XML-aware para ARC2 memory | 0.5d | No mueve CCEE directamente (previene regresión futura) | Ninguna | Sonnet 4.6 (mecánico) |
| 8 | **ARC1 Budget cap increase** — recalling cap 400→800 como quick-win | 0.5d | +0.3-0.5 | Ninguna | Sonnet 4.6 (mecánico) |
| 9 | **Guard Gold Examples** — exclusión mutua vs Creator Style Loader + CCEE | 1-2d + CCEE | Incierto | #4 completado | Opus 4.6 (diseño guard) |
| 10 | **Commitment dedup ARC2** — nightly auto-fulfill de commitments matcheados | 1d | No mueve CCEE directamente | Ninguna | Sonnet 4.6 (mecánico) |

**Timeline total pre-FT:** ~7 días (acciones 1-4 en paralelo parcial) + 1 CCEE → ready para FT data collection.

---

## Cross-Check Final (NOTA 5)

| Check | ¿Cumple? |
|-------|----------|
| Todos los hallazgos Fases 3-7 sintetizados | ✅ 41+25+8+7+5 pares cubiertos |
| Ningún MEDIUM/ALTA fuera del roadmap | ✅ BLQ 1-4 + X.2, G.1/G.2, T5.1 todos en roadmap |
| 3 Tipo 1 en sección bloqueantes con propuesta | ✅ R.4, R.5, C.8 en BLQ-1 |
| ARC1 budget bug separado como arquitectónico | ✅ BLQ-2 |
| Dual Intent Classification en bloqueantes | ✅ BLQ-3 |
| Commitment dedup ARC2 nightly en roadmap | ✅ Acción #10 |
| SBS/PPA con T5.1 dependency documentada | ✅ Sección 6 + Acción #2→#5 |
| FeedbackCapture con TTL policy | ✅ Sección 7 |
| Lead Categorizer cerrado como intrínseco | ✅ Sección 4 |
| ECHO post-FT only | ✅ Sección 7 |

---

*S6 Re-Matriz completada. 8 fases, 103 pares evaluados, 89 analizados en profundidad. Veredicto: Sprint 5 resolvió la competencia por espacio (ARC1) pero no la fragmentación semántica (sell/don't-sell). 5-7 días de fixes rápidos → CCEE verification → FT data collection. SBS/PPA es el candidato de reactivación más prometedor.*
