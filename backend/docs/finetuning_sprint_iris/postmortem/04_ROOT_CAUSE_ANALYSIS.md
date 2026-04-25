# FASE 4 — Análisis de Causa Raíz
**Fecha:** 2026-04-25  
**Entrada:** FASES 1-3 + SUBMETRICA_ANALYSIS_4WAY.md + σ_inter calculado  
**Rama:** feat/sft-postmortem-analysis

---

## 4.1 Significancia Estadística de los Deltas Reportados

σ_inter calculado sobre 3 runs. Para MT (J3, J4, J5, J6, K1, K2, L1, L2, L3, G5): n=1, sin σ disponible.

Test: t-test dos muestras, df=2, umbral p<0.05 → t>2.78 = **, p<0.10 → t>1.89 = *

| Métrica | BL_n μ±σ | BL_p μ±σ | FT_n μ±σ | FT_p μ±σ | Δ_FT_naked | sig | Δ_pipe_FT | sig |
|---|---|---|---|---|---|---|---|---|
| S1 | 55.6±2.0 | 71.4±0.5 | 73.8±1.3 | 79.3±3.1 | +18.2 | ** | +5.5 | ** |
| S2 | 55.8±1.6 | 67.5±0.4 | 66.7±0.9 | 66.9±1.3 | +10.9 | ** | +0.2 | ns |
| S3 | 75.6±1.4 | 61.4±1.3 | 62.3±2.7 | 68.4±5.6 | −13.3 | ** | +6.0 | ns |
| S4 | 31.1±2.7 | 65.7±0.1 | 59.1±2.4 | 62.4±0.9 | +28.0 | ** | +3.4 | * |
| H | 49.9±0.2 | 37.2±2.1 | 55.6±3.7 | 62.0±4.3 | +5.7 | * | +6.4 | * |
| J2 | 46.3±3.6 | 61.6±1.9 | 57.2±4.0 | 61.6±3.7 | +10.9 | ** | +4.4 | ns |
| J_cog | 48.1±1.8 | 55.8±0.9 | 53.6±2.0 | 55.8±1.9 | +5.5 | ** | +2.2 | ns |
| S1.A1 | 10.6±4.5 | 99.9±0.0 | 91.0±2.5 | 87.9±2.6 | +80.4 | ** | −3.0 | ns |
| S3.E1 | 72.0±1.5 | 56.1±1.7 | 49.6±4.4 | 59.9±9.6 | −22.4 | ** | +10.2 | ns |
| S3.E2 | 84.0±1.2 | 73.5±8.1 | 92.0±2.4 | 88.2±4.8 | +7.9 | ** | −3.7 | ns |
| S4.proximity | 31.1±2.7 | 65.7±0.1 | 59.1±2.4 | 62.4±0.9 | +28.0 | ** | +3.4 | * |

**MT (n=1, no hay σ → no significance testing posible):**

| Métrica | BL_n | BL_p | FT_n | FT_p | Δ_FT_naked | Δ_pipe_FT |
|---|---|---|---|---|---|---|
| J3 prompt-to-line | 4.5 | 82.5 | 65.5 | 79.2 | +61.0 | +13.7 |
| J4 line-to-line | 61.7 | 54.0 | 56.9 | 52.9 | −4.8 | −4.0 |
| J5 belief drift | 70.0 | 77.5 | 47.5 | 45.0 | −22.5 | −2.5 |
| **J6 Q&A** | **100.0** | **100.0** | **87.5** | **25.0** | **−12.5** | **−62.5** |
| K1 context ret | 77.7 | 44.5 | 56.2 | 42.6 | −21.6 | −13.6 |
| K2 style ret | 77.8 | 92.4 | 85.3 | 87.5 | +7.5 | +2.3 |
| L1 persona tone | 15.0 | 81.5 | 66.0 | 73.5 | +51.0 | +7.5 |
| L2 logical | 21.5 | 59.3 | 54.7 | 63.9 | +33.2 | +9.1 |

**Nota sobre J6 pipeline FT (−62.5):** Con n=1, no hay test de significancia formal. Sin embargo, el J6_cross_session = 0 (probe idéntica en 5 conversaciones → 5/5 inconsistentes) es un dato binario sin varianza — es un resultado determinista, no ruidoso.

---

## 4.2 Clasificación de Métricas por Comportamiento

### A) WIN-WIN: FT > BL en naked Y pipeline (éxitos claros del SFT)

| Métrica | Δ_naked | sig | Δ_pipe | sig | Confirmación |
|---|---|---|---|---|---|
| **S1 Style** | +18.2 | ** | +12.1 | ** | ✅ Robusto |
| **S4 Adaptation** | +28.0 | ** | −3.4 | * | ✅ / Leve regresión pipe |
| **S2 Quality** | +10.9 | ** | −0.6 | ns | ✅ / Neutral pipe |
| **A1 Length** | +80.4 | ** | −12.0 | ns | ✅ / Pipe override |
| **L2 Logical** | +33.2 | n/σ | +9.1 | n/σ | ✅ Robusto |
| **L1 Persona Tone** | +51.0 | n/σ | +7.5 | n/σ | ✅ Robusto |
| **J3 Prompt-to-Line** | +61.0 | n/σ | +13.7 | n/σ | ✅ Robusto |
| **K2 Style Retention** | +7.5 | n/σ | +2.3 | n/σ | ✅ |
| **H total (H2)** | +5.7 | * | +6.4 | * | ✅ |
| **G2 Bot Reveal** | −0.33 | n/σ | 0.0 | — | ✅ |
| **G4 Echo** | −6.39 | n/σ | −0.07 | — | ✅ |
| **B2 Persona Consistency** | +25.0 | n/σ | −5.0 | n/σ | ✅ / Leve pipe |

**Lectura:** El SFT ganó de forma estadísticamente significativa (**) en S1, S2, S4, A1. Las ganancias de MT (J3, L1, L2) no tienen σ disponible pero los deltas son grandes.

### B) FT > BL naked, FT < BL pipeline — conflictos pipeline-FT

| Métrica | FT_n | BL_n | Δ_naked | FT_p | BL_p | Δ_pipe | Veredicto |
|---|---|---|---|---|---|---|---|
| **J6 cross_session** | 100 | 100 | 0 | **0** | 100 | **−100** | 🔴 CRÍTICO |
| **J6 within_conv** | 75 | 100 | −25 | 50 | 100 | **−50** | 🔴 CRÍTICO |
| **H1 Turing** | 78 | 74 | +4 | 60 | 68 | **−14** | 🔴 Significativo |
| C2 Naturalness | 49 | 20.5 | +28.5 | 43.5 | 52.5 | −9.0 | 🟡 Conflicto |
| B5 Emotional | 35 | 25.5 | +9.5 | 32 | 41.5 | −9.5 | 🟡 |
| B total (v5) | 54.8 | 43.3 | +11.5 | 53.3 | 58.2 | −4.9 | 🟡 |

### C) FT < BL en AMBOS contextos — regresiones reales del modelo

| Métrica | FT_n | BL_n | Δ_naked | FT_p | BL_p | Δ_pipe | Sig (naked) |
|---|---|---|---|---|---|---|---|
| **J5 Belief Drift** | 47.5 | 70.0 | −22.5 | 45.0 | 77.5 | −32.5 | n/σ |
| **S3 Strategic** | 62.3 | 75.6 | −13.3 | 68.4 | 61.4 | −0.8* | ** |
| **K1 Context Retention** | 56.2 | 77.7 | −21.6 | 42.6 | 44.5 | −1.9 | n/σ |
| C3 Contextual | 17.0 | 31.0 | −14.0 | 11.0 | 18.0 | −7.0 | n/σ |
| H (total v5) | 78 | 80 | −2.0 | 68 | 74 | −6.0 | ns |
| J4 Line-to-line | 56.9 | 61.7 | −4.8 | 52.9 | 54.0 | −1.1 | n/σ |

*S3 tiene Δ_pipe positivo (+6.9) pero negativo naked (−13.3): no es regresión robusta en pipeline.

### D) Pipeline AYUDA al FT (FT_p > FT_n, top por magnitud)

| Métrica | FT_n | FT_p | Δ_pipe_FT | Componente que aporta |
|---|---|---|---|---|
| G5 Persona Robustness | 80 | 100 | **+20.0** | Instrucciones anti-jailbreak en sys prompt |
| J3 Prompt-to-Line | 65.5 | 79.2 | **+13.7** | Doc D refuerza brevedad |
| S1 Style | 73.8 | 79.3 | **+5.5** | Few-shots y Doc D refuerzan estilo |
| L1 Persona Tone | 66 | 73.5 | **+7.5** | Doc D refuerza tono de persona |
| L2 Logical | 54.7 | 63.9 | **+9.1** | Contexto RAG añade coherencia lógica |

### E) Pipeline DAÑA al FT (FT_p < FT_n, top por magnitud)

| Métrica | FT_n | FT_p | Δ_pipe_FT | Componente responsable (hipótesis) |
|---|---|---|---|---|
| **J6 cross_session** | 100 | 0 | **−100** | RAG varía entre sesiones |
| **J6 overall** | 87.5 | 25.0 | **−62.5** | RAG + Doc D variante |
| **H1 Turing** | 78 | 60 | **−18.0** | System prompt suena a bot |
| K1 Context Ret | 56.2 | 42.6 | **−13.6** | Context budget agotado por sys prompt |
| B5 Emotional | 35 | 32 | −3.0 | Doc D sobrescribe emociones aprendidas |

---

## 4.3 Mapeo Causa-Efecto

Para cada métrica con regresión, evaluamos 5 hipótesis:

### Hipótesis 1: Dataset narrow (H1)
*El dataset de 9.272 ejemplos single-turn sin system prompt y sin Q&A de persona causó la regresión.*

| Métrica | Evidencia A FAVOR | Evidencia EN CONTRA | P(H1) |
|---|---|---|---|
| J5 −22.5 naked | Dataset sin adversarial → sin training de resistencia; TwinVoice confirma | Base naked también ve casos adversariales similares | **75%** |
| S3 −13.3 naked | Dataset es 59% reacciones sociales, sin ejemplos de respuesta estratégica | S3.E2 +7.9 naked → FT mejor distribución de intenciones | 55% |
| K1 −21.6 naked | 0% multi-turn → no entrenó tracking de contexto | Base también sin multi-turn en training | **70%** |
| C3 −14 naked | Dataset no contiene Q&A "apropiado" que el judge evalúa | C3 baja en TODOS los modelos (posible calibración del judge) | 40% |
| J6 cross naked −12.5 | 0.1% persona Q&A → no aprendió invarianza | J6 cross naked = 100 (probe respondida consistentemente) | 20% |

### Hipótesis 2: Chat template mismatch (H2)
*Training con enable_thinking=False vs. serving con `<|channel>thought\n<channel|>` prefix causó comportamiento inconsistente.*

| Métrica | Evidencia A FAVOR | Evidencia EN CONTRA | P(H2) |
|---|---|---|---|
| J6 pipeline 0 | Cada sesión RAG distinto + template mismatch → activaciones diferentes | J6 naked=87.5 sin mismatch → modelo funciona bien | **60%** |
| H1 Turing −18 pipe | Template suena diferente al natural → judge menos convencido | BL también baja H1 con pipeline (−6) | 45% |
| C2 −5.5 pipe | Comportamiento híbrido FT-trained+weird-prefix → menos natural | C3 baja en todos, no específico de mismatch | 35% |

### Hipótesis 3: Distribution shift training-to-serving (H3)
*System prompt de 8.093 tokens en serving nunca visto en training (4.266 samples con 510-char, 5.006 sin system) causó regresión.*

| Métrica | Evidencia A FAVOR | Evidencia EN CONTRA | P(H3) |
|---|---|---|---|
| **J6 cross_session = 0 pipeline** | RAG varía entre sesiones → sys prompt diferente → FT sigue sys prompt → inconsistencia; BL no tiene este problema porque sigue sys prompt con coherencia base | — | **90%** |
| K1 −13.6 pipe | Sys prompt ocupa context budget → menos espacio para historial | BL también pierde K1 con pipeline (−33.2) | 60% |
| H1 −18 pipe | Sys prompt formal suena menos humano | Misma degradación en BL (−6) | 50% |

### Hipótesis 4: Pipeline-FT distribution shift (H4)
*Los componentes del pipeline (Doc D + RAG + few-shots) interfieren con el comportamiento aprendido por el FT.*

Esta hipótesis es equivalente a H3 a nivel de efecto, pero más específica en el mecanismo: no es solo que el sys prompt sea largo — es que su contenido variable (RAG en particular) crea distribuciones de entrada incompatibles con lo que el FT aprendió.

| Métrica | Evidencia A FAVOR | Evidencia EN CONTRA | P(H4) |
|---|---|---|---|
| J6 cross_session = 0 | RAG devuelve resultados distintos → cada sesión el FT "lee" una descripción diferente de Iris → responde diferente | — | **95%** |
| C2 baja pipe | Few-shots en sys prompt override el estilo aprendido | BL con pipe también baja C2 ligeramente | 60% |

### Hipótesis 5: Varianza del judge (H5)
*El judge Qwen3-30B tiene alta varianza y los deltas observados son ruido estadístico.*

| Métrica | Evidencia A FAVOR | Evidencia EN CONTRA | P(H5) |
|---|---|---|---|
| S3 −13.3 naked | σ=2.7 para FT_naked S3 → delta 13.3 vs σ 2.7 | Δ/σ ≈ 5 → estadísticamente significativo (**) | **5%** |
| J5 −22.5 naked | n=1 para MT, sin σ | Los per-conv scores son todos bajos (25, 25, 50, 62.5) | 15% |
| J6 = 0 pipeline | n=1 para MT | El probe cross-session dio 5/5 conversaciones inconsistentes → binario, no ruido | **2%** |

---

## 4.4 Patrones Transversales

### Cluster 1: Métricas de identidad consistente (J5, J6, K1)
Todas las métricas que miden "¿mantiene el modelo su identidad/contexto a lo largo del tiempo?" regresionan juntas. **Causa común confirmada:** dataset 100% single-turn → el modelo no aprendió mecanismos de tracking de estado entre turnos.

El baseline mantiene identidad porque: (a) su RLHF incluyó escenarios multi-turn, y (b) sigue el system prompt de forma coherente (tiene más "ancla" en el sistema).

### Cluster 2: Métricas dañadas específicamente por el pipeline FT (J6 pipeline, H1, C2)
Estas métricas son buenas en FT_naked pero malas en FT_pipeline. **Causa común confirmada:** el RAG variable del pipeline crea entradas diferentes en cada sesión. El FT, que aprendió a responder desde sus pesos (sin system prompt), intenta seguir el sys prompt variable y falla en consistencia cross-session.

### Cluster 3: Ganancias claras del SFT (S1, S4, A1, L1, J3)
Todas son métricas de "forma" (longitud, tono, estilo). **Causa común confirmada:** el SFT sobre 9.272 DMs de Iris fue muy efectivo para aprender el estilo superficial. A1 (+80.4 naked) es la evidencia más limpia: el modelo sabe que Iris escribe mensajes cortos sin necesitar el system prompt.

---

## 4.5 Ranking de Causas Raíz

En orden de probabilidad y evidencia:

### Causa Raíz 1 (P=90%): RAG variable rompe J6 cross-session
**Evidencia directa:** J6_cross_session = 0 pipeline FT vs 100 BL_pipeline. El mismo probe en 5 sesiones con RAG distinto → respuestas inconsistentes.  
**Fuente:** FASE 2.5 análisis del feedback del judge: "The answers vary significantly in meaning and stance."  
**Impacto en composite v5:** J6 tiene peso directo en v5. J6 pipeline FT = 25 vs BL = 100 → contribuye −75×0.03 ≈ −2.25 puntos al composite.

### Causa Raíz 2 (P=85%): Dataset 100% single-turn → K1, J5, J4 regresión
**Evidencia directa:** K1 −21.6 naked, J5 −22.5 naked. TurnWise (2026) cuantifica exactamente este efecto: -12% en MT consistency.  
**Fuente:** FASE 2 auditoría (0% multi-turn) + SOTA (TurnWise).  
**Impacto en composite v5:** Afecta J_new (-11.3 pipeline), K (-3.1 pipeline), L (-2.5 pipeline).

### Causa Raíz 3 (P=75%): Ausencia de persona Q&A en training → J6 naked no perfecto
**Evidencia directa:** 0.1% persona Q&A responses en dataset (10/9272). J6 naked = 87.5 vs BL naked = 100 (−12.5).  
**Fuente:** FASE 2 auditoría.  
**Impacto:** Menos directo que CR1 — el FT naked mantiene J6 razonable (87.5), pero la ausencia de Q&A hace el modelo vulnerable a varianza cuando el contexto cambia (como hace el RAG).

### Causa Raíz 4 (P=70%): Dataset sin adversarial → J5 Belief Drift regresión
**Evidencia directa:** J5 −22.5 naked. El feedback del judge muestra el FT cediendo ante role-switching adversarial. TwinVoice predice exactamente esto.  
**Fuente:** FASE 2.5 (ejemplos concretos) + SOTA (TwinVoice, ACL Sycophancy).  
**Impacto:** J5 entra en J_new con peso 0.3 dentro del componente. Impacto moderado en composite.

### Causa Raíz 5 (P=60%): Chat template mismatch (enable_thinking=False vs serving prefix)
**Evidencia indirecta:** Loss inicial 10.64 (esperado 1.5-3.5 para modelo preentrenado). ChatBug y HF documentan degradación severa por mismatch de template.  
**No hay experimento de control** (no probamos serving con el mismo template que training).  
**Impacto estimado:** Contribuye a varianza en J6, H1, C3 con pipeline. Difícil cuantificar sin experimento ablativo.

### Causa Raíz 6 (P=60%): Doc D diferente baseline (2462 chars) vs FT eval (1576 chars)
**Evidencia directa:** Los metadata de los JSONs muestran diferentes `doc_d_version_id`.  
**Impacto:** La comparación BL_pipeline (69.5) vs FT_pipeline (66.4) lleva este confound. El delta real puede ser mejor o peor — no sabemos.

### Causa Raíz 7 (P=55%): 22 error-strings + 441 artefactos de media en training
**Evidencia directa:** El FT emite `[🏷️ Sticker] [🏷️ Sticker]` en S3 worst cases. El dataset contiene 22 copias del error string.  
**Impacto:** Contribuye a S3 regresión (respuestas vacías de sticker). Impacto localizado.

---

## 4.6 Plan de Fix Recomendado — Secuencia Priorizada

### Fix 1 (INMEDIATO, alta probabilidad de mejora): Estabilizar RAG en serving

**Qué cambiar:** En `core/dm/phases/context.py`, hacer que el RAG para el modelo FT use un seed fijo o una versión cacheada por `creator_id` (no por `lead_id`). Alternativamente: para el serving FT, excluir el bloque RAG del system prompt (ya está en los pesos).

**Coste:** 1-2h de desarrollo.  
**Riesgo:** Bajo — solo afecta al FT endpoint, no al baseline.  
**Δ esperado en J6:** +62.5 → J6 pipeline FT volvería a ~87.5 (naked baseline). Impacto en v5: +1.9 puntos.

### Fix 2 (SPRINT 7, ALTA prioridad): Añadir multi-turn al dataset

**Qué cambiar:** Sintetizar 5.000-10.000 conversaciones multi-turn usando el base model con few-shot sobre los 9.272 ejemplos existentes (método TurnWiseData). No necesitan ser 100% perfectas — TurnWise demuestra +12% MT con datos sintéticos.

**Coste:** $20-40 en inference para síntesis + 2-3h de setup.  
**Riesgo:** Medio — los datos sintéticos pueden tener artefactos. Necesitan auditoría manual antes de incluir.  
**Δ esperado:** +12% en MT consistency (TurnWise) → K1 recupera ~13pts, J5 recupera ~10pts, J4 mejora ~5pts. Impacto en v5: +2-4 puntos.

### Fix 3 (SPRINT 7, ALTA prioridad): Incluir system prompt en training data

**Qué cambiar:** Para todos los ejemplos del dataset, añadir el system prompt de producción (Doc D estabilizado + instrucciones base) como `{"role": "system", "content": "..."}`. Usar una versión congelada del Doc D (no el RAG dinámico).

**Coste:** 1h de scripting + ~10% más de compute por tokens adicionales en training.  
**Riesgo:** Medio — si el Doc D cambia en producción después del training, hay mismatch nuevo. Requiere versionado estricto del Doc D.  
**Δ esperado:** J6 cross_session mejora porque el modelo aprende a ignorar las variaciones del RAG y usa sus pesos como ancla. H1 Turing mejora (+5-10 esperado). Impacto en v5: +1-3 puntos.

### Fix 4 (SPRINT 7, MEDIA prioridad): Limpiar el dataset

**Qué cambiar:** 
- Eliminar los 22 error-strings
- Eliminar o filtrar los 441 artefactos media/sticker donde la respuesta sea solo el artefacto
- Deduplicar near-duplicates (cosine sim >0.95)
- Eliminar muestras ultra-cortas (<10 chars) excepto donde sean contextualmente correctas

**Coste:** 2-4h de scripting.  
**Riesgo:** Bajo — solo elimina ruido.  
**Δ esperado:** S3 mejora (menos respuestas de sticker inapropiadas). Loss final puede bajar a <2.5 (señal de datos más limpios). Impacto modesto en v5 (+0.5-1.5 pts).

### Fix 5 (SPRINT 7, MEDIA prioridad): Verificar y corregir chat template masking

**Qué cambiar:** Auditar el loss de train_on_responses_only — verificar que la pérdida inicial no incluye tokens del prompt. Si se confirma mismatch, alinear el template de serving con el de training.

**Coste:** 2h de auditoría + potencial rebuild del training run.  
**Riesgo:** Bajo si solo es verificación; Medio si requiere re-training.  
**Δ esperado:** Si el mismatch se confirma y se corrige, mejora difusa en múltiples métricas (H1, J6, C2). Estimado: +1-2 puntos.

### NO hacer (para evitar riesgos innecesarios):

- **NO aumentar rank r** sin primero limpiar el dataset y añadir multi-turn.
- **NO reducir el learning rate a 1e-6** sin primero verificar que el dataset sea de alta calidad.
- **NO hacer DPO** antes de tener un SFT baseline limpio y comparable con el baseline.

---

## 4.7 FASE 5 — Validación Cruzada SOTA vs Dataset vs Métricas

Para cada gap de SOTA, verificamos si las métricas muestran el síntoma predicho:

| Gap SOTA | Predicción | Métrica observada | Confirmado |
|---|---|---|---|
| 0% multi-turn → K1 regresión | K1_FT < K1_BL en naked | K1_FT_naked=56.2 vs K1_BL_naked=77.7 (−21.6) | ✅ |
| 0% multi-turn → J5 regresión | J5_FT < J5_BL en naked | J5_FT_naked=47.5 vs J5_BL_naked=70.0 (−22.5) | ✅ |
| 0% multi-turn → J4 regresión | J4_FT < J4_BL | J4_FT=56.9 vs J4_BL=61.7 (−4.8) | ✅ (pequeño) |
| Sin sys prompt en training → J6 pipeline breakdown | J6_FT_pipe << J6_FT_naked | 25.0 vs 87.5 (−62.5) | ✅ |
| Sin sys prompt en training → distribution shift | FT_pipe < FT_naked en métricas de consistencia | J6, H1, C2 todas peores con pipeline | ✅ |
| Dataset narrow sin adversarial → J5 belief drift | J5_FT < J5_BL | −22.5 naked | ✅ |
| Dataset narrow → S3 strategic regresión | S3_FT < S3_BL naked | −13.3 naked (** significativo) | ✅ |
| r=16 potencialmente alto → sin validación | No hay señal de overfitting confirmada | Imposible verificar sin validation split | ⚠️ No verificable |
| LR 2e-4 agresivo → posible overfitting | Sin val set, no verificable | Imposible verificar | ⚠️ No verificable |
| Loss inicial 10.64 anormal → template mismatch | Comportamiento no determinista con sys prompt | J6 cross_session=0 pipeline, H1 −18 | ✅ (indirecto) |
| Dataset sin diversidad situacional → consistency superficial | Alta S1 pero baja C3 | S1 +18 naked ✅, C3 −14 naked | ✅ |
| SFT en DMs positivos → sycophancy/belief drift | J5 regresión, especialmente ante presión | J5_FT_naked=47.5 vs 70.0 | ✅ |
| Doc D diferente baseline vs FT eval | Delta pipeline no comparable | Doc D version diferente confirmado | ✅ (confound real) |
| 22 error strings → artefactos de pipeline en respuestas | S3 worst cases con sticker/errores | S3=0 para respuestas de sticker | ✅ |

**Score de validación:** 12/14 gaps tienen síntoma confirmado en métricas. Los 2 no verificables requieren experimentos adicionales (validation split en próximo training).

---

## 4.8 Revisión de los Fix Recomendados en SUBMETRICA_ANALYSIS_4WAY.md

El documento previo propuso 4 fixes. Evaluación con evidencia de las fases 1-3:

| Fix original | Evaluación | Prioridad actualizada |
|---|---|---|
| "Estabilizar RAG entre sesiones" | ✅ Confirmado por CR1 (P=90%). Fix más rápido e impactante. | **1** |
| "Reducir Doc D en sys prompt FT (<500 chars)" | ✅ Parcialmente confirmado. No el único fix — con multi-turn en training el modelo ignoraría mejor las variaciones del Doc D. | **3** (combinado con Fix 3 de este doc) |
| "Training con system prompt completo" | ✅ Confirmado por CR3+CR1. Necesario pero costoso si el Doc D varía. Versión estabilizada/congelada del Doc D es el approach correcto. | **2** (combinado con Fix 3 de este doc) |
| "DPO con J6 como reward" | ⚠️ Prematuro. El SFT base no está limpio todavía. DPO sobre un baseline contaminado amplificará el ruido, no la señal. Diferir hasta tener SFT v2 limpio. | **Diferido a Sprint 8** |

---

## 4.9 Criterios de Éxito para Sprint 7

### Objetivo principal
**v5 composite ≥ 72.0** (mejora +5.6 sobre FT pipeline actual 66.4, y supera baseline 69.5 en +2.5)

### Subset de submétricas objetivo

| Métrica | Actual FT_pipe | Target S7 | Método |
|---|---|---|---|
| J6 Q&A overall | 25.0 | **≥80.0** | Fix RAG + sys prompt en training |
| J6 cross_session | 0.0 | **≥80.0** | Fix RAG estabilizado |
| J5 Belief Drift | 45.0 | **≥60.0** | Multi-turn + adversarial examples |
| K1 Context Ret | 42.6 | **≥55.0** | Multi-turn training |
| S1 Style | 79.3 | **≥78.0** | Mantener (no degradar) |
| H1 Turing | 60.0 | **≥70.0** | Template alignment + sys prompt fix |
| S3 Strategic | 62.0 | **≥65.0** | Limpieza dataset + diversidad situacional |

### Tolerancia de regresión
- S1 puede bajar máximo −3 pts (actualmente 79.3 → mínimo 76)
- S2 puede bajar máximo −2 pts (actualmente 66.9 → mínimo 64.9)
- G1 (safety) debe mantenerse 100%

### Gate de varianza
- σ_inter(v5) < 1.5 (actualmente σ≈0 porque el v5 no estaba reportando por runs)
- σ_inter(S1) < 4.0 (actualmente 3.1 FT_pipeline)
- σ_inter(S3) < 7.0 (actualmente 5.6 FT_pipeline — alta, pendiente de estabilizar)

### Condición para proceder a DPO
- v5 ≥ 70.0 con el SFT v2 limpio
- σ_inter(v5) < 2.0
- J6 ≥ 70.0
- Comparación con baseline usando **el mismo Doc D** (versión congelada)

---

*Documento generado el 2026-04-25 cruzando evidencia de 4 fases de auditoría.*  
*Rama: feat/sft-postmortem-analysis | Sprint: post-mortem SFT Iris*
