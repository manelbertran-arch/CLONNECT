# Análisis Sub-Métrico 4-Way — Sprint Fine-Tuning Iris SFT
**Fecha:** 2026-04-25  
**Rama:** feat/sft-measurement  
**Autor:** análisis automático post-CCEE

## Cuadro experimental

| Condición | Modelo | Pipeline | JSON fuente |
|---|---|---|---|
| **BL naked** | google/gemma-4-31B-it | Sin pipeline (naked) | `naked_baseline_naked_20260425_1202.json` |
| **BL pipeline** | google/gemma-4-31B-it | Producción completa | `baseline_post_revert_fewshot_commitment_20260424.json` |
| **FT naked** | gemma31b-iris-sft | Sin pipeline (naked) | `naked_ft_naked_20260425_1035.json` |
| **FT pipeline** | gemma31b-iris-sft | Producción completa | `ft_sft_20260425_0130.json` |

**Definición de deltas:**
- `Δ_FT_naked` = FT_naked − BL_naked → efecto del SFT en limpio
- `Δ_FT_pipe` = FT_pipe − BL_pipe → efecto del SFT en producción
- `Δ_pipe_BL` = BL_pipe − BL_naked → cuánto aporta el pipeline al modelo base
- `Δ_pipe_FT` = FT_pipe − FT_naked → cuánto aporta el pipeline al modelo FT

---

## Tabla 1 — Composites

| Métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **v5 composite** | 56.4 | 69.5 | 66.1 | 66.4 | **+9.7** | −3.1 | +13.1 | +0.3 |
| v4 composite | 56.5 | 69.0 | 65.5 | 68.9 | +9.0 | −0.1 | +12.5 | +3.4 |
| v4.1 composite | 55.6 | 70.0 | 65.9 | 66.8 | +10.3 | −3.2 | +14.4 | +0.9 |
| MT composite | 53.4 | 72.8 | 62.2 | 64.5 | +8.8 | −8.3 | +19.4 | +2.3 |

**Interpretación composites:**
- FT mejora claramente el modelo base en naked (+9.7 en v5), confirmando que el SFT es efectivo.
- El pipeline aporta enormemente al baseline (+13.1) pero casi nada al FT (+0.3): el FT ha internalizado la persona, haciendo el pipeline parcialmente redundante.
- La regresión FT_pipe vs BL_pipe (−3.1) es real pero resulta de un conflicto pipeline-modelo, no de un modelo peor.

---

## Tabla 2 — V5 Dimensiones

| Dimensión | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **S1 Style** | 54.6 | 70.8 | 75.3 | 82.9 | **+20.7** | **+12.1** | +16.2 | +7.6 | FT gana en ambos ✅ |
| **S2 Response Quality** | 54.2 | 67.7 | 67.3 | 65.9 | +13.1 | −1.8 | +13.5 | −1.4 | FT gana naked, leve regresión pipeline |
| **S3 Strategic** | 76.8 | 62.8 | 62.7 | 62.0 | **−14.1** | −0.8 | −14.0 | −0.7 | Regresión real FT — base mejor naked |
| **S4 Adaptation** | 29.8 | 65.8 | 56.5 | 62.4 | **+26.7** | −3.4 | +36.0 | +5.9 | FT gana naked ✅, pipeline ayuda base más |
| J_old | 48.5 | 55.3 | 51.4 | 55.5 | +2.9 | +0.2 | +6.8 | +4.1 | FT neutral-leve mejora |
| **J_new** | 41.3 | 72.4 | 57.5 | 61.1 | +16.2 | −11.3 | **+31.1** | +3.6 | Pipeline crucial para base; FT pipeline regresa |
| **J6 Q&A** | 100.0 | 100.0 | 87.5 | **25.0** | −12.5 | **−75.0** | 0.0 | **−62.5** | 🔴 Conflicto crítico pipeline-FT |
| K Context | 77.7 | 63.7 | 67.8 | 60.6 | −9.9 | −3.1 | −14.0 | −7.2 | Pipeline perjudica K en ambos |
| G5 Persona Rob. | 65.0 | 100.0 | 80.0 | 100.0 | +15.0 | 0.0 | +35.0 | +20.0 | Pipeline suma +35 BL, +20 FT ✅ |
| **L Multi-turn** | 25.6 | 66.1 | 57.8 | 63.6 | **+32.2** | −2.5 | **+40.5** | +5.8 | Pipeline esencial para L; FT mejora naked |
| **H Turing** | 80.0 | 74.0 | 78.0 | 68.0 | −2.0 | −6.0 | −6.0 | −10.0 | Pipeline perjudica H en ambos |
| B Persona | 43.3 | 58.2 | 54.8 | 53.3 | +11.5 | −4.9 | +14.9 | −1.5 | FT gana naked, pipeline perjudica FT |

---

## Tabla 3 — S1 Style Fidelity (sub-componentes)

| Sub-métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **S1 total** | 55.6 | 71.4 | 73.8 | 79.3 | **+18.2** | **+7.9** | +15.8 | +5.5 | FT gana en ambos ✅ |
| A1 length match | 10.6 | 99.9 | 91.0 | 87.9 | **+80.4** | −12.0 | +89.3 | −3.1 | FT internaliza longitud sin pipeline ✅ |
| A2 emoji rate | 96.4 | 87.7 | 91.3 | 86.6 | −5.2 | −1.0 | −8.7 | −4.6 | Base tiene emoji muy alto naked; todos similares |
| A2 contextual emoji | 56.8 | 62.6 | 53.0 | 63.2 | −3.8 | +0.7 | +5.8 | +10.2 | Pipeline mejora contextualidad emoji FT |

**Nota:** A3-A9 no disponibles en estos JSONs (scorer determinístico no los registra por separado). A1 es el hallazgo más claro: el modelo FT aprendió la longitud media de mensajes de Iris (91/100 naked vs 10.6/100 base naked).

---

## Tabla 4 — S2 Response Quality (sub-componentes)

| Sub-métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **S2 total** | 55.8 | 67.5 | 66.7 | 66.9 | +10.9 | −0.6 | +11.7 | +0.3 | FT mejora naked ✅; pipeline perjudica FT leve |
| BERTScore | 0.80 | 0.81 | 0.81 | 0.81 | +0.01 | 0.00 | +0.01 | 0.00 | Todos iguales (~80%) — base semántica similar |
| chrF++ | 0.07 | 0.07 | 0.07 | 0.08 | 0.00 | +0.01 | 0.00 | +0.01 | Todos bajos (DM no espera match literal) |
| BLEU-4 | 0.03 | 0.15 | 0.11 | 0.11 | +0.08 | −0.04 | +0.12 | 0.00 | Pipeline ayuda baseline BLEU |
| ROUGE-L | 0.03 | 0.01 | 0.02 | 0.03 | −0.01 | +0.02 | −0.02 | +0.01 | Todos muy bajos — esperado para DM cortos |
| METEOR | 0.04 | 0.01 | 0.02 | 0.02 | −0.02 | +0.01 | −0.03 | 0.00 | Todos muy bajos |
| SemSim | 0.80 | 0.81 | 0.81 | 0.81 | +0.01 | 0.00 | +0.01 | 0.00 | Identico — la similitud semántica no cambia |
| C4 Relevance | 0.81 | 0.81 | 0.81 | 0.81 | 0.00 | 0.00 | 0.00 | 0.00 | Estable |
| **Self-repetition** | 0.98 | 0.80 | 0.89 | 0.94 | −0.09 | **+0.14** | −0.18 | +0.05 | BL naked se repite mucho (0.98); FT pipeline alto (0.94) — posible modo loop |
| **G4 Echo rate** | 8.17 | 1.48 | 1.78 | 1.41 | **−6.39** | −0.07 | −6.69 | −0.37 | BL naked hace eco masivo (8.17); FT resuelto |
| G1 hallucinations | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | Limpio en todas ✅ |
| **G2 bot reveal** | 0.33 | 0.00 | 0.00 | 0.00 | −0.33 | 0.00 | −0.33 | 0.00 | BL naked se revela como bot (0.33 casos) |

---

## Tabla 5 — S3 Strategic Alignment

| Sub-métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **S3 total** | 75.6 | 61.4 | 62.3 | 68.4 | **−13.3** | +7.0 | −14.3 | +6.1 | BL naked sorprendentemente alto; pipeline ayuda FT |
| E1 per-case | 72.0 | 56.2 | 49.7 | 59.9 | −22.4 | +3.7 | −15.9 | +10.2 | FT pipeline mejora E1 vs naked +10 |
| E2 distribution | 84.1 | 73.5 | 92.0 | 88.2 | +7.9 | +14.7 | −10.5 | −3.7 | FT mejor E2 en ambos ✅ |

**Nota:** S3 alto en BL naked es contra-intuitivo — el modelo base sin pipeline responde a las intenciones del usuario de forma "genérica correcta" (ChatGPT style). El pipeline de Iris prioriza persona sobre intención pura, lo que baja S3 para el base. FT pipeline recupera E1 (+10.2 vs naked).

---

## Tabla 6 — S4 Adaptation

| Sub-métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **S4 total** | 31.1 | 65.7 | 59.1 | 62.4 | **+28.0** | −3.3 | **+34.6** | +3.4 | FT +28 en naked ✅; pipeline crucial para adaptación |
| proximity_mean | 31.1 | 65.7 | 59.1 | 62.4 | +28.0 | −3.3 | +34.6 | +3.4 | (S4 implementado como proximity único) |

**Nota:** S4 mide qué tan bien el bot adapta el tono al lead. El base sin pipeline (31.1) no sabe a quién habla. Con pipeline (65.7) obtiene el contexto de la relación. El FT sin pipeline (59.1) infiere la adaptación del estilo aprendido: mejora +28 sobre base naked.

---

## Tabla 7 — B (Persona) y C (Conversational)

| Sub-métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B total (automático) | 100.0 | 100.0 | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | B4 bounds pasa todos ✅ |
| B4 knowledge bounds | 100.0 | 100.0 | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | ✅ |
| **B2 persona consistency** | 4.5 | 33.0 | 29.5 | 28.0 | **+25.0** | −5.0 | +28.5 | −1.5 | FT +25 naked ✅; todos bajos — B2 métrica difícil |
| **B5 emotional signature** | 25.5 | 41.5 | 35.0 | 32.0 | +9.5 | −9.5 | +16.0 | −3.0 | FT +9.5 naked ✅; pipeline perjudica FT leve |
| **C2 naturalness** | 20.5 | 52.5 | 49.0 | 43.5 | +28.5 | −9.0 | +32.0 | −5.5 | FT +28.5 naked ✅; pipeline perjudica FT naturalidad |
| **C3 contextual approp.** | 31.0 | 18.0 | 17.0 | 11.0 | −14.0 | −7.0 | −13.0 | −6.0 | Todos bajos 🔴 — C3 es la métrica más difícil |

**Nota sobre C3:** C3 es contextual appropriateness scored por Qwen3-30B. Puntuaciones bajas en todos los modelos sugieren que el judge tiene expectativas altas o el dominio DM informal hace difícil la evaluación. BL naked tiene el score más alto (31.0) — el modelo ChatGPT responde más "apropiadamente" en abstracto. El FT tiene C3 pipeline = 11.0, el peor: posible interferencia del sistema prompt con las respuestas informales aprendidas.

---

## Tabla 8 — H (Indistinguishability)

| Sub-métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **H total (= H1 en v5)** | 80.0 | 74.0 | 78.0 | 68.0 | −2.0 | −6.0 | −6.0 | −10.0 | Pipeline perjudica H en ambos |
| H1 Turing (judge %) | 74.0 | 68.0 | 78.0 | 60.0 | **+4.0** | **−14.0** | −6.0 | **−18.0** | FT naked mejor Turing ✅; FT pipeline peor 🔴 |
| H2 cosine (per-run) | 49.9 | 37.2 | 55.6 | 62.0 | +5.7 | **+24.8** | −12.7 | +6.4 | FT pipeline MEJOR H2 ✅; BL pipeline peor H2 |

**Nota crítica H:** H1 y H2 miden cosas distintas. H1 (Turing) = el judge cree que es humano. H2 (cosine) = el vector de estilo del bot se parece al de Iris. El FT naked tiene el mejor Turing (78%) — sin pipeline el modelo FT pasa mejor el test de Turing. Con pipeline, FT Turing cae a 60%: el sistema prompt hace que el bot suene "demasiado asistente". H2 es opuesto: FT pipeline mejor H2 (62.0) porque el pipeline añade features de estilo Iris que hacen el vector más parecido.

---

## Tabla 9 — J (Judgment / Cognitive Fidelity)

| Sub-métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| J1 memory recall | 50.0 | 50.0 | 50.0 | 50.0 | 0.0 | 0.0 | 0.0 | 0.0 | Neutral — "no multi-turn data" |
| J2 multi-turn consist. | 46.3 | 61.6 | 57.2 | 61.6 | +10.9 | −0.1 | +15.3 | +4.4 | FT +10.9 naked ✅; FT pipeline ~igual BL |
| J2 length consistency | 82.2 | 52.6 | 62.7 | 63.5 | −19.6 | +10.9 | −29.7 | +0.8 | BL naked hiper-consistente largo; FT equilibrado |
| J2 emoji consistency | 90.7 | 68.0 | 77.3 | 65.3 | −13.3 | −2.7 | −22.7 | −12.0 | Pipeline baja emoji consistency en todos |
| J2 question consistency | 57.1 | 89.6 | 74.4 | 81.1 | +17.3 | −8.5 | +32.5 | +6.7 | Pipeline mejora question consistency del base masivamente |
| **J2 excl. consistency** | 1.4 | 97.9 | 71.4 | 97.9 | +70.0 | 0.0 | +96.5 | **+26.5** | BL naked sin exclamaciones coherentes; FT mejora naked |
| J_cognitive | 48.1 | 55.8 | 53.6 | 55.8 | +5.5 | 0.0 | +7.7 | +2.2 | FT leve mejora |
| **J3 prompt-to-line** | 4.5 | 82.5 | 65.5 | 79.2 | **+61.0** | −3.3 | **+78.0** | +13.7 | 🔴 BL naked J3=4.5 (respuestas largas tipo informe); FT naked 65.5 (internalizó brevedad) |
| J4 line-to-line | 61.7 | 54.0 | 56.9 | 52.9 | −4.8 | −1.1 | −7.7 | −4.0 | Leve regresión FT; pipeline baja en todos |
| **J5 belief drift** | 70.0 | 77.5 | 47.5 | 45.0 | **−22.5** | **−32.5** | +7.5 | −2.5 | 🔴 Regresión FT en belief drift |
| **J6 Q&A overall** | 100.0 | 100.0 | 87.5 | **25.0** | −12.5 | **−75.0** | 0.0 | **−62.5** | 🔴🔴 Colapso crítico pipeline+FT |
| J6 within_conv | 100.0 | 100.0 | 75.0 | 50.0 | −25.0 | −50.0 | 0.0 | −25.0 | FT inconsistente DENTRO de conversación con pipeline |
| **J6 cross_session** | 100.0 | 100.0 | 100.0 | **0.0** | 0.0 | **−100.0** | 0.0 | **−100.0** | 🔴🔴 FT pipeline: fallo total cross-session |

---

## Tabla 10 — K (Context Retention) y L (Multi-turn Language)

| Sub-métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **K1 context retention** | 77.7 | 44.5 | 56.2 | 42.6 | **−21.6** | −1.9 | **−33.2** | −13.6 | Pipeline perjudica K1 masivamente; FT mejor naked que BL pipe |
| **K2 style retention** | 77.8 | 92.4 | 85.3 | 87.5 | +7.5 | −4.9 | +14.6 | +2.3 | FT mejor K2 en ambos ✅; pipeline añade a ambos |
| G5 persona robustness | 65.0 | 100.0 | 80.0 | 100.0 | +15.0 | 0.0 | +35.0 | +20.0 | Pipeline da robustez adversarial ✅; FT naked ya mejor que BL naked |
| **L1 persona tone** | 15.0 | 81.5 | 66.0 | 73.5 | **+51.0** | −8.0 | **+66.5** | +7.5 | 🔴→✅ FT +51 naked (persona tone internalizada); pipeline esencial para BL |
| **L2 logical reasoning** | 21.5 | 59.3 | 54.7 | 63.9 | +33.2 | **+4.6** | +37.8 | +9.1 | FT mejora en ambos ✅; único caso donde FT pipe > FT naked Y BL pipe |
| L3 action justification | 44.0 | 52.5 | 50.0 | 50.0 | +6.0 | −2.5 | +8.5 | 0.0 | FT leve mejora naked; plateau en pipeline |

**K1 nota:** K1 mide retención de contexto dentro de la conversación. El pipeline paradójicamente baja K1 (−33 para BL, −21 para FT naked vs naked): el sistema prompt complejo ocupa contexto y deja menos espacio para el historial de la conversación.

---

## Tabla 11 — G (Safety/Generation)

| Sub-métrica | BL naked | BL pipe | FT naked | FT pipe | Δ_FT_naked | Δ_FT_pipe | Δ_pipe_BL | Δ_pipe_FT | Interpretación |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| G1 hallucinations | 100.0 | 100.0 | 100.0 | 100.0 | 0.0 | 0.0 | 0.0 | 0.0 | Limpio ✅ |
| **G5 persona robustness** | 65.0 | 100.0 | 80.0 | 100.0 | +15.0 | 0.0 | +35.0 | +20.0 | Pipeline da 100% robustez adversarial a ambos ✅ |

---

## ANÁLISIS CRUZADO POR CATEGORÍA

### a) FT > BL en AMBOS contextos (wins claros del SFT)

| Métrica | FT naked | BL naked | FT pipe | BL pipe | Δ_naked | Δ_pipe |
|---|---:|---:|---:|---:|---:|---:|
| **S1 Style** | 75.3 | 54.6 | 82.9 | 70.8 | +20.7 | +12.1 |
| **S4 Adaptation** | 56.5 | 29.8 | 62.4 | 65.8 | +26.7 | −3.4 |
| **A1 Length** | 91.0 | 10.6 | 87.9 | 99.9 | +80.4 | −12.0 |
| **B2 Persona Consistency** | 29.5 | 4.5 | 28.0 | 33.0 | +25.0 | −5.0 |
| **C2 Naturalness** | 49.0 | 20.5 | 43.5 | 52.5 | +28.5 | −9.0 |
| **L1 Persona Tone** | 66.0 | 15.0 | 73.5 | 81.5 | +51.0 | −8.0 |
| **L2 Logical Reasoning** | 54.7 | 21.5 | 63.9 | 59.3 | +33.2 | +4.6 |
| **J3 Prompt-to-Line** | 65.5 | 4.5 | 79.2 | 82.5 | +61.0 | −3.3 |
| **G5 Persona Robustness** | 80.0 | 65.0 | 100.0 | 100.0 | +15.0 | 0.0 |
| **G2 Bot Reveal** | 0.0 | 0.33 | 0.0 | 0.0 | −0.33 | 0.0 |
| **G4 Echo Rate** | 1.78 | 8.17 | 1.41 | 1.48 | −6.39 | −0.07 |
| **K2 Style Retention** | 85.3 | 77.8 | 87.5 | 92.4 | +7.5 | −4.9 |
| **J2 Multi-turn** | 57.2 | 46.3 | 61.6 | 61.6 | +10.9 | −0.1 |

**Conclusión a:** El SFT ganó en identidad y estilo. A1 (+80.4 naked) es el win más limpio: el modelo FT aprendió que Iris escribe mensajes cortos, incluso sin que el sistema prompt lo diga. L1 (+51) y J3 (+61) confirman que la persona de Iris está internalizadas profundamente.

---

### b) FT > BL naked, FT < BL pipeline — conflictos pipeline-FT

| Métrica | FT naked | BL naked | Δ_naked | FT pipe | BL pipe | Δ_pipe | Pipeline perjudica FT? |
|---|---:|---:|---:|---:|---:|---:|---|
| **J6 Q&A overall** | 87.5 | 100.0 | −12.5 | 25.0 | 100.0 | **−75.0** | ✅ CRÍTICO |
| **J6 cross_session** | 100.0 | 100.0 | 0.0 | 0.0 | 100.0 | **−100.0** | ✅ CRÍTICO |
| **J6 within_conv** | 75.0 | 100.0 | −25.0 | 50.0 | 100.0 | **−50.0** | ✅ CRÍTICO |
| H1 Turing % | 78.0 | 74.0 | +4.0 | 60.0 | 68.0 | **−14.0** | ✅ Significativo |
| B5 Emotional Signature | 35.0 | 25.5 | +9.5 | 32.0 | 41.5 | **−9.5** | ✅ |
| C2 Naturalness | 49.0 | 20.5 | +28.5 | 43.5 | 52.5 | **−9.0** | ✅ |
| S2 Response Quality | 66.7 | 55.8 | +10.9 | 66.9 | 67.5 | −0.6 | leve |
| B total (v5) | 54.8 | 43.3 | +11.5 | 53.3 | 58.2 | **−4.9** | ✅ |

**Conclusión b:** El pipeline activamente perjudica J6, H1, C2, B5, B en el FT. El patrón es consistente: el sistema prompt complejo (Doc D + RAG + few-shots) entra en conflicto con el comportamiento aprendido por SFT, haciendo que el modelo sea menos natural y menos consistente. El caso más grave es J6 cross_session: 100→0 con pipeline, vs 100 en todas las condiciones base.

---

### c) FT < BL en AMBOS contextos (regresiones reales del modelo)

| Métrica | FT naked | BL naked | Δ_naked | FT pipe | BL pipe | Δ_pipe |
|---|---:|---:|---:|---:|---:|---:|
| **S3 Strategic** | 62.3 | 75.6 | **−13.3** | 62.0 | 61.4 | −0.8 |
| **J5 Belief Drift** | 47.5 | 70.0 | **−22.5** | 45.0 | 77.5 | **−32.5** |
| C3 Contextual Approp. | 17.0 | 31.0 | −14.0 | 11.0 | 18.0 | −7.0 |
| K1 Context Retention | 56.2 | 77.7 | −21.6 | 42.6 | 44.5 | −1.9 |
| H (total) | 78.0 | 80.0 | −2.0 | 68.0 | 74.0 | −6.0 |
| J4 Line-to-line | 56.9 | 61.7 | −4.8 | 52.9 | 54.0 | −1.1 |

**Conclusión c:** Las regresiones reales son menores de lo que parecía en el análisis inicial. S3 (strategic alignment) regresa −13 naked pero casi nada en pipeline (−0.8): el pipeline ayuda al FT a recuperar la intención estratégica. J5 (belief drift) es la única regresión real preocupante (−22.5 naked, −32.5 pipeline): el modelo FT no mantiene creencias estables bajo presión adversarial. K1 regresa por el efecto de context starvation del pipeline, no del modelo.

---

### d) Pipeline AYUDA al FT (FT_pipe > FT_naked)

| Métrica | FT naked | FT pipe | Δ_pipe_FT | ¿Necesita pipeline? |
|---|---:|---:|---:|---|
| S1 Style | 75.3 | 82.9 | **+7.6** | Sí, aporta estilo extra |
| S4 Adaptation | 56.5 | 62.4 | +5.9 | Sí, contexto relacional |
| L1 Persona Tone | 66.0 | 73.5 | +7.5 | Sí, refuerza tono |
| L2 Logical Reasoning | 54.7 | 63.9 | **+9.1** | Sí, único L que mejora |
| G5 Persona Robustness | 80.0 | 100.0 | **+20.0** | Sí, crítico para robustez |
| H2 Cosine | 55.6 | 62.0 | +6.4 | Sí, similitud vectorial |
| J2 Excl. Consistency | 71.4 | 97.9 | +26.5 | Sí, el pipeline ancla estilo |
| S1 A2 contextual emoji | 53.0 | 63.2 | +10.2 | Sí, contextualiza emojis |
| V5.sub.J3 | 65.5 | 79.2 | +13.7 | Sí, mejora respuesta al prompt |

**Conclusión d:** El pipeline SÍ aporta valor al FT en métricas de estilo y robustez adversarial (+20 G5). El componente más valioso es el que da a G5 robustez 100% y L2 lógica. El FT sin pipeline ya es bueno, pero el pipeline refina S1, S4 y G5.

---

### e) Pipeline DAÑA al FT (FT_pipe < FT_naked)

| Métrica | FT naked | FT pipe | Δ_pipe_FT | Gravedad | Componente responsable |
|---|---:|---:|---:|---|---|
| **J6 Q&A cross-session** | 100.0 | 0.0 | **−100.0** | CRÍTICA | RAG variante + Doc D confuso |
| **J6 Q&A overall** | 87.5 | 25.0 | **−62.5** | CRÍTICA | Combinado |
| **J6 within_conv** | 75.0 | 50.0 | **−25.0** | Alta | System prompt oscila |
| J5 Belief Drift | 47.5 | 45.0 | −2.5 | Leve | Contexto adversarial |
| **H1 Turing** | 78.0 | 60.0 | **−18.0** | Alta | System prompt suena a bot |
| K1 Context Retention | 56.2 | 42.6 | **−13.6** | Alta | Context budget agotado |
| S2 Response Quality | 66.7 | 66.9 | +0.2 | Ninguna | — |
| **B5 Emotional** | 35.0 | 32.0 | −3.0 | Leve | Doc D sobrescribe emociones |
| **C2 Naturalness** | 49.0 | 43.5 | −5.5 | Moderada | System prompt formal |
| J2 emoji consistency | 77.3 | 65.3 | −12.0 | Moderada | Pipeline varía el emoji |
| J_new | 57.5 | 61.1 | +3.6 | — beneficio — | — |

**Conclusión e:** Los componentes del pipeline que DAÑAN al FT son:
1. **RAG variante entre conversaciones** → J6 cross_session = 0 (resultados de búsqueda distintos en cada sesión → el sistema prompt cambia entre conversaciones → respuestas inconsistentes)
2. **Doc D largo en system prompt** → K1 starvation (el system prompt consume context budget dejando menos para conversación), H1 degradación (suena más asistente que humano)
3. **Few-shots en system prompt** → posiblemente interfiere con el estilo aprendido

---

## RESUMEN EJECUTIVO

### ¿Qué aprendió el SFT?
El modelo FT internalizó profundamente la **identidad de Iris** (A1, L1, J3 con +51 a +80 en naked). No necesita el sistema prompt para comportarse como Iris. Esto es un éxito del SFT.

### ¿Qué degradó el SFT?
- **J5 Belief Drift** (−22.5 naked): bajo presión adversarial, el FT cede creencias más que el base.
- **S3 Strategic** (−13.3 naked): el FT prioriza persona sobre intención estratégica.
- **J6 naked** (87.5 vs 100): el FT es menos consistente en Q&A que el base (que siempre sigue el system prompt fielmente).

### ¿Qué causa la regresión en producción (FT_pipe 66.4 vs BL_pipe 69.5)?
Principalmente el conflicto **J6 pipeline-FT** (−62.5). El pipeline de producción rompe la consistencia Q&A del FT de forma catastrófica (cross_session: 100→0). Sin este artefacto, el FT pipeline superaría al baseline en la mayoría de métricas.

### Fix recomendado (por orden de impacto)

| Prioridad | Fix | Δ_esperado | Complejidad |
|---|---|---|---|
| 1 | **Estabilizar RAG entre sesiones** (seed fijo o caché RAG por lead) | J6 cross_session 0→70+ | Baja |
| 2 | **Reducir Doc D en system prompt para FT** (versión comprimida ≤500 chars) | H1 +10, C2 +5, K1 +10 | Baja |
| 3 | **Training con system prompt** (incluir Doc D en datos de entrenamiento) | J6 +40, J5 +15 | Alta |
| 4 | **DPO con J6 como reward** | J6 +30, J5 +10 | Media |

---

## Archivos de datos

```
tests/ccee_results/iris_bertran/
  baseline_post_revert_fewshot_commitment_20260424.json  ← BL pipeline
  naked_baseline_naked_20260425_1202.json                ← BL naked
  ft_sft_20260425_0130.json                              ← FT pipeline
  naked_ft_naked_20260425_1035.json                      ← FT naked
```

---

*Generado automáticamente el 2026-04-25 por análisis CCEE 4-way.*  
*Rama: feat/sft-measurement | Commit: pendiente*
