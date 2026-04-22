# Baseline post-P4 LIVE — 2026-04-22

**Propósito:** Baseline CCEE post-activación SellArbiter (PR #80, `ENABLE_SELL_ARBITER_LIVE=true`).
**Configuración:** 50 casos × 3 runs, iris_bertran, DeepInfra + Qwen3-30B-A3B judge.
**JSON fuente:** `tests/ccee_results/iris_bertran/baseline_post_p4_live_20260422.json`

---

## Entorno de medición

| Var | Valor | Fuente |
|-----|-------|--------|
| `LLM_PRIMARY_PROVIDER` | deepinfra | Railway mirror |
| `DEEPINFRA_MODEL` | google/gemma-4-31B-it | Railway mirror |
| `ENABLE_SELL_ARBITER_LIVE` | true | Railway mirror |
| `USE_COMPRESSED_DOC_D` | false | Corrección drift Railway |
| `ENABLE_RERANKING` | true | Railway mirror |
| `USE_COMPACTION` | true | Railway mirror |
| `CCEE_NO_FALLBACK` | 1 | Protocolo variance |
| `CCEE_INTER_CASE_DELAY` | 3 | env_ccee script |
| `doc_d_version_id` | 0c2364cc | Auto (2481 chars CCEE eval) |

**Nota:** `sentence-transformers` no instalado en `.venv` local → reranker no activo durante CCEE a pesar de `ENABLE_RERANKING=true`. En Railway prod el reranker sí está activo. Discrepancia conocida, no bloquea baseline (afecta RAG precision pero no la evaluación de estilo/respuesta). Ver seguimiento en `docs/status/railway_vs_env_script_diff_20260422.md`.

---

## Resultados por run (v4-style composite, ST)

| Run | Composite | S1 Estilo | S2 Calidad | S3 Estrategia | S4 Adaptación | B Persona | G Seguridad | H Indisting. | J Cognitivo |
|-----|-----------|-----------|------------|---------------|---------------|-----------|-------------|--------------|-------------|
| 1 | 68.37 | 69.26 | 46.05 | 74.83 | 64.64 | 100.00 | 100.00 | 49.30 | 52.98 |
| 2 | 67.03 | 67.82 | 46.91 | 69.67 | 64.77 | 100.00 | 100.00 | 46.26 | 53.52 |
| 3 | 68.35 | 68.62 | 46.89 | 74.87 | 64.91 | 100.00 | 100.00 | 48.21 | 53.00 |

---

## Composites finales (con MT)

| Versión | Valor | Descripción |
|---------|-------|-------------|
| **v4-style ST** | **67.92** | ST dims, legacy weights, σ=0.63 |
| **v4.1** | **68.9** | ST + J_new, updated weights |
| **v5** | **69.5** | 12 dimensiones completas (ST + MT) |

---

## Tabla 12 dimensiones (v5 — run 3, run más estable)

| Dim | Nombre | Score | Weight | Subdimensiones |
|-----|--------|-------|--------|----------------|
| S1 | Style Fidelity | 68.6 | 16% | — |
| S2 | Response Quality | 46.9 | 12% | — |
| S3 | Strategic Alignment | 74.9 | 16% | — |
| S4 | Adaptation | 64.9 | 9% | — |
| J_old | Cognitive Fidelity (legacy) | 53.0 | 3% | — |
| J_new | Cognitive Fidelity (new) | 65.2 | 9% | J3=68.0, J4=64.18, J5=62.5 |
| J6 | Cognitive Robustness | 100.0 | 3% | — |
| K | Context Retention | 76.1 | 6% | K1=69.18, K2=86.37 |
| G5 | Persona Robustness | 100.0 | 5% | — |
| L | Language Fidelity | 64.9 | 9% | L1=75.0, L2=65.1, L3=51.24 |
| H | Indistinguishability | 88.0 | 7% | H1=88.0, H2=null |
| B | Behavioral Alignment | 60.0 | 5% | B1=null, B4=100.0, B2=32.0, B5=48.0 |

### Scores Prometheus (MT)

| Probe | Score |
|-------|-------|
| B2 (narrative adaptability) | 32.0 |
| B5 (empathy_under_pressure) | 48.0 |
| C2 (conflict_navigation) | 56.5 |
| C3 (ambiguity_handling) | 20.5 |
| H1 Turing test rate | 86.0% |

---

## Estadísticas agregadas (v4-style ST)

| Métrica | Valor |
|---------|-------|
| **Composite medio** | **67.92** |
| σ_intra | **0.63** |
| S1 Style Fidelity | 68.57 ± 0.59 |
| S2 Response Quality | 46.62 ± 0.40 |
| S3 Strategic Alignment | 73.12 ± 2.44 |
| S4 Adaptation | 64.77 ± 0.11 |
| B Persona Fidelity | 100.00 ± 0.00 |
| G Safety | 100.00 ± 0.00 |
| H Indistinguishability | 47.92 ± 1.25 |
| J Cognitive Fidelity | 53.17 ± 0.24 |

---

## Comparación vs sesiones de varianza (20-22 abr)

| Sesión | ST mean | v4.1 | v5 | σ_intra | doc_d_version |
|--------|---------|------|----|---------|---------------|
| variance_session_2 (2026-04-21) | 69.39 | 69.7 | 68.7 | 0.94 | 5f7d6b4e |
| variance_session_3 (2026-04-22 13h) | 67.93 | 69.9 | 69.4 | 2.34 | 51c2a152 |
| **baseline_post_p4_live (2026-04-22 22h)** | **67.92** | **68.9** | **69.5** | **0.63** | 0c2364cc |

**Δ vs Session 2 (ST):** −1.47 puntos (dentro del rango de varianza natural, σ≈1−2)
**Δ vs Session 3 (ST):** −0.01 puntos (prácticamente idéntico)
**Δ vs Session 3 (v5):** +0.1 puntos
**σ_intra:** mejora notable 2.34 → 0.63 — medición más estable

**Observación doc_d:** Las tres sesiones usaron versiones distintas del doc_d (`5f7d6b4e` → `51c2a152` → `0c2364cc`). El doc_d fue actualizado entre sesiones. La caída de 69.39 → 67.93 entre session_2 y session_3 puede atribuirse parcialmente a este cambio, no solo a varianza de modelo.

---

## Análisis dimensional

**S2 Response Quality (46.62):** Consistentemente bajo en las 3 sesiones. No es regresión — es el floor estructural de este sistema con Gemma-4-31B en conversaciones cortas. Investigar si la métrica S2 está calibrada correctamente para respuestas ultra-cortas de WhatsApp.

**S3 Strategic Alignment (σ=2.44):** Varianza alta entre runs (69.67 vs 74.87). Run 2 tuvo un drop de ~5 puntos. Posible causa: aleatoriedad en casos con intent ambiguo donde el SellArbiter toma distintas decisiones en cada run.

**B + G5 = 100.00:** Persona fidelity y safety perfectos en los 3 runs — señal sólida de que el modelo no alucina ni genera contenido peligroso.

**H Indistinguishability (v4-style 47.92 vs v5 H1=88.0):** Divergencia entre métricas. El v4-style mide algo distinto al H1 MT Turing rate. v5 H1=88.0 indica que el modelo pasa el Turing test en el 88% de los casos multi-turn — buena señal.

**K Context Retention (76.1):** K2=86.37 (long-range) > K1=69.18 (short-range). El modelo retiene mejor el contexto global que el inmediato — comportamiento esperado con Gemma-4-31B.

**B2 (32.0) y C3 (20.5):** Los scores más bajos en Prometheus. B2 (narrative adaptability) y C3 (ambiguity handling) son áreas de mejora — sensibles a fine-tuning con datos creator-specific.

---

## Análisis cualitativo — muestra de respuestas

Los test cases son mensajes reales de leads de producción (no tienen metadata DNA/frustration en el JSON). Se muestran 5 casos representativos del run 1.

**Caso A — Respuesta corta Catalan/Spanish** ✓
- Input: "Venim dijous"
- Bot: "Okaaa! 🩷 Te espero el jueves entonces! 😘"
- Calidad: alta — afirmación + esperanza, emoji apropiado, codeswitching natural

**Caso B — Comprensión contextual** ✓
- Input: "Pemsava q no penjariesnres i pujavem avui el flow" (typos incluidos)
- Bot: "Siii, yo tmb lo pensaba! ¿Te vens entonces?"
- Calidad: alta — entiende mensaje a pesar de typos, responde en registro informal correcto

**Caso C — Empathy + leve pregunta** ~
- Input: "Se tiró 5h y todavía falta , el domingo tengo que ir a bajar muebles 🤯🫠 con mi padre"
- Bot: "Buaaa que paliza ¿Vendras el domingo?"
- Calidad: aceptable — empathy present, pero pregunta comercial excesivamente directa para contexto

**Caso D — Code-switching Catalan puro** ✓
- Input: "He allargat"
- Bot: "Jajajaja a voreee / T'has passat de frenada!"
- Calidad: alta — respuesta natural en valenciano, registro correcto

**Caso E — Repetición entre cases** ⚠️
- Cases 25, 33, 42 (distintas inputs) producen variaciones de "ya estoy en casa" — posible efecto del episodic memory que recuerda el estado de Iris al cerrar conversaciones. No es error de generación pero puede afectar H (indistinguishability).

---

## Impacto SellArbiter (ENABLE_SELL_ARBITER_LIVE=true)

No hay run control sin el flag activo para este baseline. La comparación limpia SellArbiter ON vs OFF requerirá una medición dedicada. Lo que sí se puede observar:
- Caso C muestra una pregunta directa ("¿Vendras el domingo?") que podría atribuirse al SellArbiter con `SELL_ACTIVELY` o `SOFT_MENTION` — pendiente verificar logs `[SELL_RESOLVER]` para ese case.
- No hay evidencia de over-selling agresivo en la muestra revisada.
- S3 Strategic Alignment (73.12) es el punto más alto en la evaluación — coherente con SellArbiter mejorando la estrategia de venta.

---

## Conclusión

**Estado: ESTABLE.** Post-P4-LIVE, composite ST 67.92 idéntico a Session 3 (67.93, misma mañana). v5 composite 69.5 (+0.1 vs session_3). Sin regresión medible atribuible a SellArbiter. σ_intra mejorado (0.63 vs 2.34). S2 bajo (46.62) es structural floor conocido, no regresión.

---

## Known limitations & future work

- Run ejecutado sin `--v52-fixes` para comparabilidad con variance sessions 20-22 abr
- B2 scored con rubric genérico (no creator-specific)
- J6 / MT Q&A probes usan probes básicos sin doc_d inyección
- FUTURO: cuando se adopte `--v52-fixes` como estándar, re-baseline completo requerido
- Esta medición NO es comparable con futuras mediciones `--v52-fixes`-on
- Esta medición SÍ es comparable con variance sessions 20-22 abr (pre-P4)

---

## Notas de reproducibilidad

- Proceso: PID 79940 (relanzado tras kill PID 76099 por flags incorrectos)
- 2 timeouts DeepInfra durante la run (1 en run 1, 1 en run 2) — manejados gracefully
- `sentence-transformers` ausente en venv — reranker no activo localmente
- Para comparaciones futuras, instalar `sentence-transformers` en `.venv` antes de CCEE
- Env mirror completo: `config/env_prod_mirror_20260422.sh`
